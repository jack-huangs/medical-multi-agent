import unittest
from analyze_consensus_mechanism import analyze, ARMS


def case(ident, initial, revised, final='B'):
    opinion = lambda a: {'answer': a, 'claims': []}
    return {'id': ident, 'status': 'completed', 'state': {
        'initial': [opinion(a) for a in initial], 'initial_hash': 'same',
        'arms': {name: {'initial_hash': 'same', 'revised': [opinion(a) for a in revised],
                        'final': opinion(final), 'intervention': {'target_evidence_id': 'E1'}} for name in ARMS}}}


class MechanismTests(unittest.TestCase):
    def test_preexisting_wrong_agreement_is_not_discussion_induced(self):
        result = analyze([case('x', 'BBB', 'BBB')], {'x': 'A'})
        s = result['summary']['original']
        self.assertEqual(s['persistent_wrong_unanimity_n'], 1)
        self.assertEqual(s['opportunities'], 0)
        self.assertIsNone(s['loss_per_opportunity'])

    def test_correct_expert_lost_and_judge_can_recover(self):
        result = analyze([case('x', 'ABB', 'BBB', final='A')], {'x': 'A'})
        row = result['per_question'][0]
        self.assertTrue(row['correct_expert_lost_to_wrong_unanimity'])
        self.assertTrue(row['final_correct'])
        self.assertTrue(row['judge_disagrees_with_unanimous_experts'])
        self.assertTrue(row['judge_recovers_from_wrong_unanimity'])

    def test_judge_can_introduce_error_without_wrong_expert_consensus(self):
        result = analyze([case('x', 'ABB', 'AAA', final='B')], {'x': 'A'})
        row = result['per_question'][0]
        self.assertTrue(row['judge_overrides_correct_unanimity_to_wrong'])
        self.assertFalse(row['revised_wrong_unanimity'])
        self.assertFalse(row['correct_expert_lost_to_wrong_unanimity'])

    def test_failures_are_explicit_not_false_consensus(self):
        result = analyze([{'id': 'x', 'status': 'error', 'error_type': 'ValueError'}], {'x': 'A'})
        self.assertEqual(result['complete_cases'], 0)
        self.assertEqual(len(result['failed_cases']), 1)
        self.assertIsNone(result['summary']['original']['loss_per_opportunity'])

    def test_final_reuses_initial_support_from_expert_who_changed_answer(self):
        value = case('x', 'BAA', 'AAA', final='B')
        value['state']['initial'][0]['claims'] = [{'claim_id': 'I0.C1', 'option': 'B', 'relation': 'supports'}]
        value['state']['arms']['original']['final']['claims'] = [
            {'claim_id': 'original.F.C1', 'option': 'B', 'relation': 'supports', 'parent_claim_ids': ['I0.C1']}]
        row = analyze([value], {'x': 'A'})['per_question'][0]
        self.assertEqual(row['final_support_reusing_initial_claims_from_changed_experts'], [
            {'final_claim_id': 'original.F.C1', 'initial_parent_id': 'I0.C1', 'expert_revised_answer': 'A'}])

    def test_mismatched_initial_snapshot_is_rejected(self):
        value = case('x', 'AAA', 'AAA')
        value['state']['arms']['original']['initial_hash'] = 'other'
        with self.assertRaises(ValueError):
            analyze([value], {'x': 'A'})


if __name__ == '__main__':
    unittest.main()
