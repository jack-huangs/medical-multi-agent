"""Offline checks for ten-option scoring, label isolation and explicit reasoning settings."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from prepare_hard_pilot import stem, fingerprint
from run_difficulty_probe import validate, worker
from run_evidence_pilot import Backend, OutputTruncatedError, read_jsonl
from run_safety import new_attempt


class ProbeTests(unittest.TestCase):
    def test_ten_options_and_invalid_answers(self):
        options = dict(zip('ABCDEFGHIJ', map(str, range(10))))
        value = {'answer': 'J', 'confidence': .7, 'brief_basis': 'Concise evidence summary.'}
        self.assertEqual(validate(value, options)['answer'], 'J')
        for bad in [{**value, 'answer': 'K'}, {**value, 'confidence': float('nan')},
                    {**value, 'confidence': True}, {**value, 'brief_basis': 'x'*601}]:
            with self.assertRaises(ValueError):
                validate(bad, options)

    def test_embedded_choices_removed_and_fingerprint_order_invariant(self):
        self.assertEqual(stem('Question?\nAnswer Choices: (A) alpha (B) beta'), 'Question?')
        self.assertEqual(fingerprint('Question?', {'A':'Alpha', 'B':'Beta'}),
                         fingerprint('QUESTION?\nAnswer Choices: omitted', {'A':'Beta', 'B':'Alpha'}))

    def test_labels_are_rejected_before_any_client_is_created(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                worker({'id':'one', 'question':'x', 'options':{'A':'a'}, 'answer_idx':'A'}, 'test', Path(temp), {})

    def test_explicit_thinking_request_and_truncation_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt = new_attempt(temp)
            backend = Backend('deepseek', attempt, 'test-model', 1, 16384, 'enabled', 'high')
            create = Mock(return_value=SimpleNamespace(
                model='test-model', usage=SimpleNamespace(model_dump=lambda: {'total_tokens':16384}),
                choices=[SimpleNamespace(message=SimpleNamespace(content=''), finish_reason='length')]))
            backend.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
            with self.assertRaises(OutputTruncatedError):
                backend.complete('probe', 'instruction', {'case': {'id':'x'}})
            request = create.call_args.kwargs
            self.assertEqual(request['extra_body'], {'thinking': {'type':'enabled'}})
            self.assertEqual(request['reasoning_effort'], 'high')
            self.assertEqual(request['max_tokens'], 16384)
            events = read_jsonl(attempt / 'requests.jsonl')
            self.assertEqual([r['event'] for r in events], ['request_started','response_received','request_failed'])
            self.assertEqual(events[1]['finish_reason'], 'length')


if __name__ == '__main__':
    unittest.main()
