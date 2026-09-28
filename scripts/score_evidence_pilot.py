"""Offline scoring. This is the only evaluation component that reads gold labels."""
import argparse
import json
from pathlib import Path
from run_safety import atomic_json

ARMS = ['original', 'repeated', 'dedup', 'dependency', 'single']


def evaluate(results, labels, arms=None):
    arms = ARMS if arms is None else arms
    if len({row['id'] for row in results}) != len(results):
        raise ValueError('Duplicate case IDs')
    table, summaries = [], {}
    for row in results:
        gold = labels[row['id']]
        state = row.get('state', {})
        initial_answers = [opinion['answer'] for opinion in state.get('initial', [])]
        for name in arms:
            arm = state.get('single', {}) if name == 'single' else state.get('arms', {}).get(name, {})
            final = arm.get('final', {})
            revised = arm.get('revised', [])
            choices = [opinion['answer'] for opinion in revised]
            unanimous = len(choices) == 3 and len(set(choices)) == 1
            wrong_unanimity = unanimous and choices[0] != gold
            agent_pairs = list(zip(initial_answers, choices)) if len(initial_answers) == len(choices) == 3 else []
            table.append({'id': row['id'], 'condition': name, 'status': row['status'],
                          'gold': gold, 'answer': final.get('answer'), 'correct': final.get('answer') == gold,
                          'confidence': final.get('confidence'), 'unanimous': unanimous,
                          'initial_expert_answers': initial_answers if name != 'single' else [],
                          'revised_expert_answers': choices,
                          'experts_correct_to_wrong': sum(a == gold and b != gold for a, b in agent_pairs),
                          'experts_wrong_to_correct': sum(a != gold and b == gold for a, b in agent_pairs),
                          'wrong_unanimity': wrong_unanimity})
    for name in arms:
        subset = [row for row in table if row['condition'] == name]
        total = len(subset)
        unanimous = sum(row['unanimous'] for row in subset)
        wrong = sum(row['wrong_unanimity'] for row in subset)
        summaries[name] = {'n': total, 'correct': sum(row['correct'] for row in subset),
                           'missing_answers': sum(row['answer'] is None for row in subset),
                           'accuracy_including_failures': sum(row['correct'] for row in subset)/total if total else None,
                           'unanimous_n': unanimous if name != 'single' else None,
                           'wrong_unanimity_n': wrong if name != 'single' else None,
                           'wrong_unanimity_per_all': wrong/total if total and name != 'single' else None,
                           'wrong_unanimity_per_unanimous': wrong/unanimous if unanimous else None}
    indexed = {(row['id'], row['condition']): row for row in table}
    pairs = {}
    for first, second in [('original', 'repeated'), ('repeated', 'dedup'),
                          ('repeated', 'dependency'), ('dedup', 'dependency'), ('single', 'dependency')]:
        if first not in arms or second not in arms:
            continue
        a = [indexed[(row['id'], first)] for row in results]
        b = [indexed[(row['id'], second)] for row in results]
        valid = [(x, y) for x, y in zip(a, b) if x['answer'] is not None and y['answer'] is not None]
        pairs[f'{first}_to_{second}'] = {
            'planned_pairs': len(results), 'valid_answer_pairs': len(valid),
            'correct_to_wrong': sum(x['correct'] and not y['correct'] for x, y in valid),
            'wrong_to_correct': sum(not x['correct'] and y['correct'] for x, y in valid),
            'mean_self_report_confidence_change': sum(y['confidence']-x['confidence'] for x, y in valid)/len(valid) if valid else None}
    return {'condition_summary': summaries, 'not_run_conditions': [name for name in ARMS if name not in arms],
            'paired_changes': pairs, 'per_question': table,
            'note': 'Descriptive development results only. Pair at the original-question level. Self-reported confidence is not calibrated.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--labels', type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads((args.run_dir / 'results.json').read_text(encoding='utf-8'))
    labels = {row['id']: row['answer_idx'] for row in [json.loads(line) for line in args.labels.read_text(encoding='utf-8').splitlines() if line.strip()]}
    config = json.loads((args.run_dir / 'config.json').read_text(encoding='utf-8'))
    report = evaluate(rows, labels, ARMS if config.get('single_control', True) else ARMS[:-1])
    report['backend'] = config['backend']
    report['is_model_effectiveness_evidence'] = False
    if report['backend'] == 'fake':
        report['note'] = 'OFFLINE FIXTURE ONLY. Scores have no medical/model effectiveness interpretation.'
    atomic_json(args.run_dir / 'evaluation.json', report)
    print(json.dumps({key: value for key, value in report.items() if key != 'per_question'}))


if __name__ == '__main__':
    main()
