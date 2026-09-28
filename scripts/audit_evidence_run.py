"""Replay evidence validation offline; never repair outputs or score partial cases."""
import argparse
import json
from collections import Counter
from pathlib import Path

from evidence_core import digest, ledger, validate_opinion
from run_evidence_pilot import accounting, read_jsonl
from run_safety import atomic_json


def stage_context(stage, opinions):
    parts = stage.split('/')
    if len(parts) == 2 and parts[0] == 'initial':
        return f'I{int(parts[1])}', []
    if len(parts) == 2 and parts[0] == 'single':
        n = int(parts[1])
        return f'S{n}', [opinions[f'S{i}'] for i in range(n)]
    if len(parts) == 3 and parts[1] == 'revise':
        return f'{parts[0]}.R{int(parts[2])}', [opinions[f'I{i}'] for i in range(3)]
    if len(parts) == 2 and parts[1] == 'aggregate':
        return f'{parts[0]}.F', ([opinions[f'I{i}'] for i in range(3)] +
                                [opinions[f'{parts[0]}.R{i}'] for i in range(3)])
    raise ValueError('Unrecognized stage')


def replay(events, sample, evidence):
    starts, opinions, calls, usage_by_phase = {}, {}, [], {}
    for event in events:
        key = event['request_id']
        if event['event'] == 'request_started':
            starts[key] = event
            continue
        if event['event'] != 'response_received':
            continue
        phase = event['stage'].split('/')[0]
        usage = usage_by_phase.setdefault(phase, {'responses': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
        usage['responses'] += 1
        for metric in ['prompt_tokens', 'completion_tokens', 'total_tokens']:
            usage[metric] += (event.get('usage') or {}).get(metric, 0) or 0
        row = {'stage': event['stage'], 'request_id': key,
               'finish_reason': event.get('finish_reason'), 'valid': False}
        if key not in starts:
            row['issue'] = 'missing_request_start'
        elif event.get('finish_reason') != 'stop':
            row['issue'] = 'unfinished_response'
        else:
            try:
                value = json.loads(event['raw'])
                opinion_id, parents = stage_context(event['stage'], opinions)
                opinion = validate_opinion(value, sample['options'], evidence, opinion_id, parents)
                opinions[opinion_id] = opinion
                row.update(valid=True, answer=opinion['answer'], confidence=opinion['confidence'],
                           claim_count=len(opinion['claims']),
                           citation_count=sum(len(c['citations']) for c in opinion['claims']),
                           inherited_claim_count=sum(bool(c['parent_claim_ids']) for c in opinion['claims']))
            except json.JSONDecodeError:
                row['issue'] = 'invalid_json'
            except KeyError:
                row['issue'] = 'required_parent_opinion_unavailable'
            except ValueError as exc:
                # Only fixed validator messages, never backend exception strings or credentials.
                row['issue'] = str(exc)
        calls.append(row)
    phases = {}
    groups = {'initial': [f'I{i}' for i in range(3)]}
    for name in ['original', 'repeated', 'dedup', 'dependency']:
        groups[name] = [f'{name}.R{i}' for i in range(3)]
    for name, ids in groups.items():
        selected = [opinions[i] for i in ids if i in opinions]
        roots = ledger(selected)
        phases[name] = {'validated_experts': len(selected), 'complete': len(selected) == 3,
                        'answers': [o['answer'] for o in selected],
                        'shared_option_relation_root_groups': sum(len(g['opinion_ids']) > 1 for g in roots),
                        'ledger': roots}
    requests_by_stage = {r['stage']: r for r in starts.values()}
    identical_controls = []
    for i in range(3):
        original = requests_by_stage.get(f'original/revise/{i}')
        dedup = requests_by_stage.get(f'dedup/revise/{i}')
        if original and dedup and 'messages' in original and 'messages' in dedup:
            identical_controls.append({'expert': i,
                'original_dedup_messages_identical': digest(original['messages']) == digest(dedup['messages'])})
    return {'calls': calls, 'phases': phases, 'reported_usage_by_phase': usage_by_phase,
            'negative_control_prompt_checks': identical_controls,
            'issues': dict(Counter(c['issue'] for c in calls if not c['valid'])),
            'validated_responses': sum(c['valid'] for c in calls)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args()
    run = args.run_dir
    config = json.loads((run / 'config.json').read_text(encoding='utf-8'))
    if config['sources']['evidence_core.py'] != digest(Path(__file__).with_name('evidence_core.py').read_text(encoding='utf-8')):
        raise SystemExit('Validator differs from the run snapshot; audit using its original validator.')
    attempts = []
    for path in sorted(run.glob('cases/*/attempts/*/requests.jsonl')):
        checkpoint = path.parent / 'checkpoint_retrieve.json'
        state = json.loads(checkpoint.read_text(encoding='utf-8'))
        report = replay(read_jsonl(path), state['sample'], state['evidence'])
        report.update(id=state['sample']['id'], attempt_id=path.parent.name)
        attempts.append(report)
    summary = {'attempts': len(attempts), 'validated_responses': sum(a['validated_responses'] for a in attempts),
               'validation_issues': dict(sum((Counter(a['issues']) for a in attempts), Counter())),
               **accounting(run)}
    report = {'summary': summary, 'attempts': attempts,
              'note': 'Offline schema/citation/lineage audit only, not entailment or clinical truth. '
                      'Partial calls are diagnostic and must not replace complete-case arm results.'}
    atomic_json(run / 'validation_audit.json', report)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
