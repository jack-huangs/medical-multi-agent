"""Separate pre-existing wrong agreement from discussion-induced wrong agreement."""
import argparse
import json
from pathlib import Path

from evidence_core import ledger
from run_safety import atomic_json

ARMS = ['original', 'repeated', 'dedup', 'dependency']


def agreement(answers, gold):
    complete = len(answers) == 3
    unanimous = complete and len(set(answers)) == 1
    return {'complete': complete, 'unanimous': unanimous,
            'wrong_unanimous': unanimous and answers[0] != gold,
            'correct_experts': sum(a == gold for a in answers)}


def analyze(results, labels):
    rows = []
    for result in results:
        if result['status'] != 'completed':
            continue
        state, gold = result['state'], labels[result['id']]
        initial = [o['answer'] for o in state['initial']]
        before = agreement(initial, gold)
        if not before['complete']:
            raise ValueError('Completed case must contain three initial experts')
        for name in ARMS:
            arm = state['arms'][name]
            if arm['initial_hash'] != state['initial_hash']:
                raise ValueError('Arms did not share the same initial opinions')
            revised = [o['answer'] for o in arm['revised']]
            after = agreement(revised, gold)
            if not after['complete']:
                raise ValueError('Completed arm must contain three revised experts')
            roots = ledger(arm['revised'])
            opportunity = before['correct_experts'] > 0 and not before['unanimous']
            initial_claims = {c['claim_id']: (i, c) for i, o in enumerate(state['initial']) for c in o.get('claims', [])}
            historical_support = []
            for claim in arm['final'].get('claims', []):
                if claim['option'] != arm['final']['answer'] or claim['relation'] != 'supports':
                    continue
                for parent_id in claim['parent_claim_ids']:
                    if parent_id not in initial_claims:
                        continue
                    index, parent = initial_claims[parent_id]
                    if (initial[index] == arm['final']['answer'] and revised[index] != arm['final']['answer']
                            and parent['option'] == arm['final']['answer'] and parent['relation'] == 'supports'):
                        historical_support.append({'final_claim_id': claim['claim_id'], 'initial_parent_id': parent_id,
                                                   'expert_revised_answer': revised[index]})
            rows.append({'id': result['id'], 'condition': name, 'gold': gold,
                         'initial_answers': initial, 'revised_answers': revised,
                         'initial_wrong_unanimity': before['wrong_unanimous'],
                         'revised_wrong_unanimity': after['wrong_unanimous'],
                         'initial_disagreement_with_correct_expert': opportunity,
                         'correct_expert_lost_to_wrong_unanimity': opportunity and after['wrong_unanimous'],
                         'new_wrong_unanimity_from_any_disagreement': not before['unanimous'] and after['wrong_unanimous'],
                         'persistent_wrong_unanimity': before['wrong_unanimous'] and after['wrong_unanimous'],
                         'final_answer': arm['final']['answer'],
                         'final_correct': arm['final']['answer'] == gold,
                         'judge_disagrees_with_unanimous_experts': after['unanimous'] and arm['final']['answer'] != revised[0],
                         'judge_overrides_correct_unanimity_to_wrong': after['unanimous'] and revised[0] == gold and arm['final']['answer'] != gold,
                         'judge_recovers_from_wrong_unanimity': after['wrong_unanimous'] and arm['final']['answer'] == gold,
                         'final_support_reusing_initial_claims_from_changed_experts': historical_support,
                         'multi_expert_shared_root_groups': sum(len(g['opinion_ids']) > 1 for g in roots),
                         'copied_evidence_id': arm['intervention']['target_evidence_id']})
    summaries = {}
    for name in ARMS:
        subset = [r for r in rows if r['condition'] == name]
        opportunities = sum(r['initial_disagreement_with_correct_expert'] for r in subset)
        losses = sum(r['correct_expert_lost_to_wrong_unanimity'] for r in subset)
        summaries[name] = {'complete_cases': len(subset), 'opportunities': opportunities,
                           'correct_expert_lost_to_wrong_unanimity_n': losses,
                           'loss_per_opportunity': losses/opportunities if opportunities else None,
                           'persistent_wrong_unanimity_n': sum(r['persistent_wrong_unanimity'] for r in subset),
                           'judge_overrides_correct_unanimity_to_wrong_n': sum(r['judge_overrides_correct_unanimity_to_wrong'] for r in subset),
                           'judge_recovers_from_wrong_unanimity_n': sum(r['judge_recovers_from_wrong_unanimity'] for r in subset),
                           'new_wrong_unanimity_from_any_disagreement_n': sum(r['new_wrong_unanimity_from_any_disagreement'] for r in subset)}
    return {'planned_cases': len(results), 'complete_cases': sum(r['status'] == 'completed' for r in results),
            'failed_cases': [{'id': r['id'], 'error_type': r.get('error_type')} for r in results if r['status'] != 'completed'],
            'summary': summaries, 'per_question': rows,
            'note': 'Post-run label-based descriptive analysis. Failures excluded from mechanism denominators, '
                    'but retained in planned-case accuracy by the main scorer. Agreement means exactly three revised experts. '
                    'A shared root is not proof of copying or a cause of error. No clinical truth adjudication.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--labels', type=Path, required=True)
    args = parser.parse_args()
    results = json.loads((args.run_dir / 'results.json').read_text(encoding='utf-8'))
    labels = {r['id']: r['answer_idx'] for r in (json.loads(s) for s in args.labels.read_text(encoding='utf-8').splitlines() if s.strip())}
    report = analyze(results, labels)
    atomic_json(args.run_dir / 'mechanism_analysis.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'per_question'}))


if __name__ == '__main__':
    main()
