"""Regression checks for strict offline response replay."""
import json
import unittest
from audit_evidence_run import replay


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.sample = {'id': 'x', 'question': 'fixture', 'options': {'A': 'amber', 'B': 'blue'}}
        self.evidence = [{'evidence_id': 'E1', 'root_id': 'root', 'text': 'Amber is the fixture color.'}]
        self.value = {'answer': 'A', 'confidence': .5, 'brief_basis': 'fixture', 'claims': [
            {'option': 'A', 'relation': 'supports', 'text': 'fixture',
             'citations': [{'evidence_id': 'E1', 'quote': 'Amber is the fixture color.'}], 'parent_claim_ids': []}]}

    def events(self, stage, value=None, finish='stop'):
        return [{'request_id': stage, 'stage': stage, 'event': 'request_started'},
                {'request_id': stage, 'stage': stage, 'event': 'response_received',
                 'raw': json.dumps(self.value if value is None else value), 'finish_reason': finish}]

    def test_shared_root_is_reported_without_truth_inference(self):
        events = sum([self.events(f'initial/{i}') for i in range(3)], [])
        result = replay(events, self.sample, self.evidence)
        self.assertEqual(result['validated_responses'], 3)
        self.assertEqual(result['phases']['initial']['shared_option_relation_root_groups'], 1)
        self.assertNotIn('correct', result)

    def test_invalid_quote_and_truncation_are_not_accepted(self):
        self.value['claims'][0]['citations'][0]['quote'] = 'fabricated source quote'
        result = replay(self.events('initial/0') + self.events('initial/1', finish='length'), self.sample, self.evidence)
        self.assertEqual(result['validated_responses'], 0)
        self.assertEqual(result['issues']['unfinished_response'], 1)
        self.assertIn('Quote is not a verbatim span of the cited evidence', result['issues'])

    def test_revisions_require_all_initial_parents(self):
        result = replay(self.events('original/revise/0'), self.sample, self.evidence)
        self.assertEqual(result['issues'], {'required_parent_opinion_unavailable': 1})
        self.assertFalse(result['phases']['original']['complete'])


if __name__ == '__main__':
    unittest.main()
