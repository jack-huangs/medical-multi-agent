"""Offline regressions for scoring and the repaired multi-agent information flow."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'baselines/mdagents/upstream'))
import utils
from run_consensus_pilot import answer_text, parse_answer, wilson


class PilotTests(unittest.TestCase):
    def test_adaptive_route_uses_model_label(self):
        for label in ['basic', 'intermediate', 'advanced']:
            with patch.object(utils, 'Agent') as agent:
                agent.return_value.chat.side_effect = ['Ready', label]
                self.assertEqual(utils.determine_difficulty('fixture', 'adaptive', 'fake'), label)
                self.assertEqual(agent.return_value.chat.call_count, 2)
        with patch.object(utils, 'Agent') as agent:
            agent.return_value.chat.side_effect = ['Ready', 'basic or intermediate']
            with self.assertRaises(ValueError):
                utils.determine_difficulty('fixture', 'adaptive', 'fake')

    def test_score_explicit_and_ambiguous_answers(self):
        options = {'A': 'one', 'B': 'two', 'C': 'three', 'D': 'four'}
        for text, expected in [
            ('**Final Answer: (B) two**\nRationale: option A is wrong.', 'B'),
            ('**Answer:** D) four', 'D'),
            ('The correct answer is (C).', 'C'),
            ('Answer: A\nAnswer: B', None),
            ('We should compare A and B.', None),
            ('Answer: J', None),
        ]:
            self.assertEqual(parse_answer(text, options), expected)
        self.assertEqual(answer_text({'majority': {0.0: 'Answer: A'}}), 'Answer: A')
        lo, hi = wilson(95, 100)
        self.assertAlmostEqual(lo, 0.8882495308)
        self.assertAlmostEqual(hi, 0.9784563208)

    def exercise_discussion(self, communicate):
        summaries, prompts = [], []
        participation = [0]

        class FakeAgent:
            def __init__(self, instruction, role, **kwargs):
                self.role = role

            def chat(self, message, **kwargs):
                prompts.append((self.role, message))
                if self.role == 'recruiter' and 'You can recruit' in message:
                    return '\n'.join(f'{i}. Doctor{i} - Examines evidence. - Hierarchy: Independent' for i in range(1, 6))
                if 'Given the examplers' in message:
                    return 'Answer: A) INITIAL'
                if 'Here are some reports' in message:
                    summaries.append(message)
                if 'whether you want to talk' in message:
                    if self.role == 'doctor1':
                        participation[0] += 1
                        return 'yes' if communicate and participation[0] <= 5 else 'no'
                    return 'no'
                if 'Enter the number' in message:
                    return '2'
                if 'leave your opinion' in message:
                    return 'NEW_EVIDENCE'
                if "Now that you've interacted" in message:
                    return 'Answer: B) UPDATED'
                return 'OK'

            def temp_responses(self, message, **kwargs):
                prompts.append((self.role, message))
                return {0.0: 'Answer: B'}

        with patch.object(utils, 'Agent', FakeAgent), contextlib.redirect_stdout(io.StringIO()):
            utils.process_intermediate_query('fixture question', [], 'fake', SimpleNamespace(dataset='medqa'))
        moderator = next(message for role, message in prompts if role == 'Moderator' and 'Given each agent' in message)
        return summaries, prompts, moderator

    def test_immediate_stop_keeps_initial_opinions(self):
        summaries, _, moderator = self.exercise_discussion(False)
        self.assertEqual(len(summaries), 1)
        self.assertIn('INITIAL', moderator)
        self.assertIn('doctor5', moderator)
        self.assertNotIn('None', moderator)

    def test_later_rounds_and_recipients_receive_updates(self):
        summaries, prompts, moderator = self.exercise_discussion(True)
        self.assertEqual(len(summaries), 2)
        self.assertIn('UPDATED', summaries[1])
        self.assertIn('UPDATED', moderator)
        recipient = [text for role, text in prompts if role == 'doctor2' and "Now that you've interacted" in text]
        self.assertTrue(recipient)
        self.assertIn('NEW_EVIDENCE', recipient[0])


if __name__ == '__main__':
    unittest.main()
