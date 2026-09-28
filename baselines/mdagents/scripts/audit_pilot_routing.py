"""Verify adaptive routing against original API responses, without model calls."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from run_consensus_pilot import read_jsonl, save_json


def audit(run):
    config = json.loads((run / 'config.json').read_text(encoding='utf-8'))
    rows = json.loads((run / 'scored_results.json').read_text(encoding='utf-8'))
    cases = []
    for row in rows:
        trace = run / row.get('trace_relative_path', f"cases/{row['id']}/trace.jsonl")
        events = read_jsonl(trace)
        responses = [event for event in events if event['event'] == 'model_response'
                     and event.get('message', '').startswith('Now, given the medical query as below, you need to decide')]
        raw = [event['response'] for event in responses]
        labels = set(re.findall(r'\b(basic|intermediate|advanced)\b', ' '.join(raw).lower()))
        roles = [event['role'] for event in events if event['event'] == 'agent_created']
        # Route agreement does not establish single-attempt integrity.
        matched = len(raw) >= 1 and labels == {row['difficulty']} and all(value.strip().lower() == row['difficulty'] for value in raw)
        branch_evidence = ('recruiter' not in roles if row['difficulty'] == 'basic' else 'recruiter' in roles)
        logged_calls = sum(event['event'] == 'model_response' for event in events)
        integrity = (len(raw) == 1 and logged_calls == row['successful_model_calls']
                     and logged_calls <= row['model_calls'])
        cases.append({'id': row['id'], 'raw_routing_responses': raw,
                      'executed_route': row['difficulty'], 'matched': matched,
                      'single_attempt_checks_passed': integrity,
                      'logged_successful_calls': logged_calls,
                      'agent_roles': roles, 'branch_matches_agent_roles': branch_evidence,
                      'routing_model': [event.get('response_model') for event in responses]})
    result = {'configured_mode': config['difficulty'], 'audited_count': len(cases),
              'planned_count': len(config['samples']),
              'route_counts': dict(Counter(row['executed_route'] for row in cases)),
              'route_consistency_verified': config['difficulty'] == 'adaptive' and len(cases) == len(config['samples'])
                          and all(row['matched'] and row['branch_matches_agent_roles'] for row in cases),
              'single_attempt_checks_passed': all(row['single_attempt_checks_passed'] for row in cases),
              'integrity_flagged_cases': [row['id'] for row in cases if not row['single_attempt_checks_passed']],
              'note': 'Passing these checks is necessary, not proof of complete billing or absence of overwritten attempts.',
              'cases': cases}
    result['verified'] = result['route_consistency_verified'] and result['single_attempt_checks_passed']
    save_json(run / 'routing_audit.json', result)
    print(json.dumps({key: value for key, value in result.items() if key != 'cases'}))
    if not result['verified']:
        raise SystemExit('Routing verification failed or run is incomplete; inspect routing_audit.json.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    audit(parser.parse_args().run_dir)
