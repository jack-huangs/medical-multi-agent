"""Offline scores for the frozen, matched-protocol difficulty probe."""
import argparse
import json
from collections import Counter
from pathlib import Path
from run_evidence_pilot import ROOT, read_jsonl
from evaluation_stats import wilson
from run_safety import atomic_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args()
    files = {'medqa': ROOT / 'runs/evidence_dependency/dev30',
             'medxpertqa_diagnosis_reasoning': ROOT / 'runs/evidence_dependency/hard_dev30'}
    labels = {name: {row['id']: row['answer_idx'] for row in read_jsonl(path / 'labels.jsonl')}
              for name, path in files.items()}
    results = json.loads((args.run_dir / 'results.json').read_text(encoding='utf-8'))
    scored = [{**row, 'gold': labels[row['group']][row['id']],
               'correct': row.get('opinion', {}).get('answer') == labels[row['group']][row['id']]} for row in results]
    groups = {}
    for name in files:
        subset = [row for row in scored if row['group'] == name]
        n, correct = len(subset), sum(row['correct'] for row in subset)
        errors = [row for row in subset if row['status'] != 'completed']
        groups[name] = {'n': n, 'planned': 30, 'correct': correct,
                        'incorrect_valid': sum(row['status'] == 'completed' and not row['correct'] for row in subset),
                        'execution_or_format_failures': len(errors),
                        'error_categories': dict(Counter(row['error_type'] for row in errors)),
                        'accuracy_including_failures': correct/n if n else None,
                        'wilson_95_interval': wilson(correct, n),
                        'valid_answer_accuracy': correct/(n-len(errors)) if n > len(errors) else None}
    metadata = {row['id']: row for row in read_jsonl(files['medxpertqa_diagnosis_reasoning'] / 'metadata.jsonl')}
    for row in scored:
        if row['id'] in metadata:
            row.update(metadata=metadata[row['id']])
    report = {'groups': groups, 'scored_results': scored,
              'note': 'Development subsets. Different questions/tasks and option counts: this is a descriptive matched-protocol comparison, not a paired causal difficulty effect. Wrong answers are not proof of false evidence or wrong consensus.'}
    atomic_json(args.run_dir / 'evaluation.json', report)
    print(json.dumps(groups, ensure_ascii=False))


if __name__ == '__main__':
    main()
