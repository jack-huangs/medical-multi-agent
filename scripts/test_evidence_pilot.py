"""Offline tests for causal controls, provenance validation, locking and restart safety."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evidence_core import (LocalBM25Retriever, retrieve, validate_opinion, intervention, ledger)
from evidence_workflow import build_graph
from run_evidence_pilot import Backend, accounting, read_jsonl
from run_safety import RunLock, new_attempt
from score_evidence_pilot import evaluate
from import_evidence_article import convert
from resume_evidence_debug import ReplayBackend, replay_key, replay_records

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples/evidence_dependency'


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        os.environ['LANGSMITH_TRACING'] = 'false'
        os.environ['LANGCHAIN_TRACING_V2'] = 'false'
        self.sample = read_jsonl(FIXTURE / 'inputs.jsonl')[0]
        self.retriever = LocalBM25Retriever.from_jsonl(FIXTURE / 'corpus.jsonl', k=3)
        self.evidence = retrieve(self.retriever, self.sample)

    def opinion(self):
        source = self.evidence[0]
        return {'answer': 'A', 'confidence': 0.5, 'brief_basis': 'test', 'claims': [
            {'option': 'A', 'relation': 'supports', 'text': 'test claim',
             'citations': [{'evidence_id': source['evidence_id'], 'quote': source['text']}], 'parent_claim_ids': []}]}

    def test_labels_rejected_and_retrieval_deterministic(self):
        with self.assertRaises(ValueError):
            retrieve(self.retriever, {**self.sample, 'answer_idx': 'A'})
        self.assertEqual(self.evidence, retrieve(self.retriever, self.sample))

    def test_content_term_retrieval_keeps_negation_and_clinical_terms(self):
        from evidence_core import retrieval_tokens
        tokens = retrieval_tokens('A patient has no ferritin elevation and 120 mm Hg', 'content_terms')
        self.assertNotIn('patient', tokens)
        self.assertIn('no', tokens)
        self.assertIn('ferritin', tokens)
        self.assertIn('120', tokens)

    def test_unknown_citation_and_fabricated_quote_rejected(self):
        for change in [{'evidence_id': 'UNKNOWN'}, {'quote': 'This sentence never existed in the source.'}]:
            value = self.opinion()
            value['claims'][0]['citations'][0].update(change)
            with self.assertRaises(ValueError):
                validate_opinion(value, self.sample['options'], self.evidence, 'I0')

    def test_inherited_paraphrase_keeps_roots_without_new_evidence(self):
        parent = validate_opinion(self.opinion(), self.sample['options'], self.evidence, 'I0')
        value = self.opinion()
        value['claims'][0].update(text='A differently phrased claim', citations=[], parent_claim_ids=['I0.C1'])
        child = validate_opinion(value, self.sample['options'], self.evidence, 'R0', [parent])
        self.assertEqual(parent['claims'][0]['root_ids'], child['claims'][0]['root_ids'])
        entries = ledger([parent, child])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['known_root_contributions'], 1)
        self.assertEqual(len(entries[0]['claim_ids']), 2)

    def test_same_document_different_passages_not_collapsed(self):
        evidence = [row for row in self.evidence if row['document_id'] == 'toy-handbook']
        opinions = []
        for i, source in enumerate(evidence):
            value = self.opinion()
            value['claims'][0]['citations'] = [{'evidence_id': source['evidence_id'], 'quote': source['text']}]
            opinions.append(validate_opinion(value, self.sample['options'], self.evidence, str(i)))
        self.assertEqual(len(ledger(opinions)), 2)

    def test_support_and_refutation_are_preserved(self):
        support = validate_opinion(self.opinion(), self.sample['options'], self.evidence, 'I0')
        value = self.opinion()
        value['claims'][0]['relation'] = 'refutes'
        refute = validate_opinion(value, self.sample['options'], self.evidence, 'I1')
        self.assertEqual({row['relation'] for row in ledger([support, refute])}, {'supports', 'refutes'})

    def test_intervention_preserves_base_evidence_and_dedup_control(self):
        before = copy.deepcopy(self.evidence)
        arms = {name: intervention(self.evidence, self.sample['id'], name) for name in ['original', 'repeated', 'dedup', 'dependency']}
        self.assertEqual(before, self.evidence)
        self.assertEqual(arms['original'], arms['dedup'])
        self.assertEqual(arms['repeated'], arms['dependency'])
        self.assertEqual(len({row['target_evidence_id'] for row in arms.values()}), 1)
        self.assertEqual(sum(len(x['text']) for x in arms['original']['slots']), sum(len(x['text']) for x in arms['repeated']['slots']))

    def test_full_graph_has_isolated_initial_prompts_and_shared_start(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt = new_attempt(Path(temp) / 'cases' / 'toy001')
            backend = Backend('fake', attempt, 'fake', 26, 512)
            result = build_graph(self.retriever, backend).invoke({'sample': self.sample})
            self.assertEqual(backend.calls, 26)
            self.assertEqual(len({arm['initial_hash'] for arm in result['arms'].values()}), 1)
            events = read_jsonl(attempt / 'requests.jsonl')
            requests = [row for row in events if row['event'] == 'request_started']
            initial = [row for row in requests if row['stage'].startswith('initial/')]
            self.assertEqual(len(initial), 3)
            for row in initial:
                payload = json.loads(row['messages'][1]['content'])
                self.assertEqual(set(payload), {'case', 'evidence'})
                self.assertEqual(set(payload['case']), {'id', 'question', 'options'})
            self.assertEqual(accounting(Path(temp))['paid_api_calls_attempted'], 0)

    def test_budget_blocks_additional_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend('fake', new_attempt(temp), 'fake', 0, 512)
            with self.assertRaises(RuntimeError):
                backend.complete('test', '', {})

    def test_replay_requires_exact_prompt_and_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            attempt = new_attempt(source / 'cases' / 'x')
            payload = {'case': self.sample, 'evidence': self.evidence}
            backend = Backend('fake', attempt, 'fake', 1, 512)
            expected = backend.complete('initial/0', 'system', payload)
            cache = replay_records(source)
            self.assertEqual(len(cache), 1)
            replay = ReplayBackend('fake', new_attempt(Path(temp) / 'target'), 'fake', 0, 8192, cache=cache)
            self.assertEqual(replay.complete('initial/0', 'system', payload), expected)
            self.assertEqual(replay.calls, 0)
            with self.assertRaises(RuntimeError):
                replay.complete('initial/0', 'changed system', payload)
            events = read_jsonl(attempt / 'requests.jsonl')
            events[-1]['finish_reason'] = 'length'
            (attempt / 'requests.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in events), encoding='utf-8')
            self.assertEqual(replay_records(source), {})

    def test_import_requires_matching_id_and_explicit_reuse_license(self):
        xml = b'<article><front><article-meta><article-id pub-id-type="pmc">123</article-id><title-group><article-title>Fixture</article-title></title-group><permissions><license><p>https://creativecommons.org/licenses/by/4.0/</p></license></permissions></article-meta></front><body><p>This is a long synthetic paragraph for checking import and source attribution. It is deliberately not medical evidence.</p></body></article>'
        title, license_text, chunks = convert(xml, 'PMC123')
        self.assertEqual(title, 'Fixture')
        self.assertEqual(chunks[0]['root_id'], 'PMC123:p0')
        plain_license = xml.replace(b'https://creativecommons.org/licenses/by/4.0/', b'Creative Commons Attribution License CC-BY 4.0.')
        self.assertTrue(convert(plain_license, 'PMC123')[2])
        with self.assertRaises(ValueError):
            convert(plain_license.replace(b'CC-BY 4.0', b'CC-BY-NC 4.0'), 'PMC123')
        with self.assertRaises(ValueError):
            convert(xml, 'PMC999')
        with self.assertRaises(ValueError):
            convert(xml.replace(b'creativecommons.org/licenses/by/4.0/', b'copyright.example/all-rights-reserved'), 'PMC123')

    def test_connectivity_mode_omits_single_control_and_has_19_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            backend = Backend('fake', new_attempt(temp), 'fake', 19, 512)
            result = build_graph(self.retriever, backend, single_control=False).invoke({'sample': self.sample})
            self.assertEqual(backend.calls, 19)
            self.assertEqual(result['single'], {})
            scored = evaluate([{'id': self.sample['id'], 'status': 'completed', 'state': result}],
                              {self.sample['id']: 'A'}, ['original', 'repeated', 'dedup', 'dependency'])
            self.assertEqual(scored['not_run_conditions'], ['single'])
            self.assertNotIn('single', scored['condition_summary'])

    def test_killed_lock_holder_does_not_leave_permanent_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'lock'
            child = 'from run_safety import RunLock; import sys,os;\nwith RunLock(sys.argv[1]): os._exit(9)'
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', child, str(path)], cwd=ROOT / 'scripts', capture_output=True)
            self.assertEqual(result.returncode, 9)
            with RunLock(path):
                pass

    def test_lock_blocks_another_process_and_releases_after_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'lock'
            child = 'from run_safety import RunLock; import sys;\nwith RunLock(sys.argv[1]): print("acquired")'
            command = [sys.executable, '-X', 'utf8', '-c', child, str(path)]
            with RunLock(path):
                result = subprocess.run(command, cwd=ROOT / 'scripts', capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Another process holds', result.stderr)
            result = subprocess.run(command, cwd=ROOT / 'scripts', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            # The child's process has exited. Its stale lock file is harmless.
            with RunLock(path):
                pass

    def test_cli_resume_does_not_append_calls_or_overwrite_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / 'run'
            inputs = Path(temp) / 'inputs.jsonl'
            inputs.write_text(json.dumps({**self.sample, 'id': 'a'*64})+'\n', encoding='utf-8')
            command = [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/run_evidence_pilot.py'), '--inputs', str(inputs),
                       '--corpus', str(FIXTURE / 'corpus.jsonl'), '--run-dir', str(run), '--top-k', '3']
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            paths = list(run.glob('cases/*/attempts/*/requests.jsonl'))
            original = paths[0].read_bytes()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(paths[0].read_bytes(), original)
            self.assertEqual(len(list(run.glob('cases/*/attempts/*/requests.jsonl'))), 1)
            self.assertEqual(accounting(run)['attempted_calls_all_attempts'], 26)

    def test_consensus_denominators_and_missing_answers(self):
        def arm(answer, votes):
            return {'final': {'answer': answer, 'confidence': .5}, 'revised': [{'answer': vote} for vote in votes]}
        row = {'id': 'x', 'status': 'completed', 'state': {'arms': {'original': arm('B', ['B']*3),
               'repeated': arm('A', ['A', 'A', 'B'])}}}
        report = evaluate([row, {'id': 'y', 'status': 'error'}], {'x': 'A', 'y': 'A'})
        summary = report['condition_summary']['original']
        self.assertEqual(summary['wrong_unanimity_per_all'], .5)
        self.assertEqual(summary['wrong_unanimity_per_unanimous'], 1)
        self.assertIsNone(report['condition_summary']['repeated']['wrong_unanimity_per_unanimous'])
        self.assertEqual(report['paired_changes']['original_to_repeated']['wrong_to_correct'], 1)


if __name__ == '__main__':
    unittest.main()
