"""Run and resume the mechanism prototype. Fake backend is offline and diagnostic only."""
import argparse
import importlib.metadata
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from evidence_core import LocalBM25Retriever, digest
from evidence_workflow import build_graph
from run_safety import RunLock, atomic_json, new_attempt

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def emit(path, event):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


class Backend:
    def __init__(self, name, attempt, model, max_calls, max_tokens, thinking='default', reasoning_effort=None):
        self.name, self.attempt, self.model = name, attempt, model
        self.max_calls, self.max_tokens = max_calls, max_tokens
        self.calls, self.client = 0, None
        self.thinking, self.reasoning_effort = thinking, reasoning_effort

    def complete(self, stage, system, payload):
        if self.calls >= self.max_calls:
            raise RuntimeError('Per-case API call cap reached')
        self.calls += 1
        request_id = f'{self.attempt.name}:{self.calls}'
        base = {'request_id': request_id, 'stage': stage, 'backend': self.name,
                'at': datetime.now(timezone.utc).isoformat()}
        messages = [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
        emit(self.attempt / 'requests.jsonl', {**base, 'event': 'request_started',
                                              'model': self.model, 'messages': messages,
                                              'temperature': 0, 'max_tokens': self.max_tokens,
                                              'thinking': self.thinking, 'reasoning_effort': self.reasoning_effort})
        start = time.monotonic()
        try:
            if self.name == 'fake':
                # This is an engineering fixture, never a model accuracy result.
                source = payload['evidence'][0]
                option = sorted(payload['case']['options'])[0]
                value = {'answer': option, 'confidence': 0.5,
                         'brief_basis': 'OFFLINE FIXTURE: always selects the first option.',
                         'claims': [{'option': option, 'relation': 'supports',
                                     'text': 'Fixture source citation, without semantic verification.',
                                     'citations': [{'evidence_id': source['evidence_id'], 'quote': source['text']}],
                                     'parent_claim_ids': []}]}
                raw, usage, response_model = json.dumps(value), None, 'fake'
                finish_reason = 'stop'
            else:
                from dotenv import dotenv_values
                from openai import OpenAI
                if self.client is None:
                    env = dotenv_values(ROOT / '.env')
                    if not env.get('DEEPSEEK_API_KEY'):
                        raise ValueError('Missing DEEPSEEK_API_KEY')
                    self.client = OpenAI(api_key=env['DEEPSEEK_API_KEY'],
                                         base_url=env.get('DEEPSEEK_BASE_URL') or 'https://api.deepseek.com',
                                         timeout=90, max_retries=0)
                extra = {}
                if self.thinking != 'default':
                    extra['extra_body'] = {'thinking': {'type': self.thinking}}
                if self.reasoning_effort:
                    extra['reasoning_effort'] = self.reasoning_effort
                response = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=0,
                    max_tokens=self.max_tokens, response_format={'type': 'json_object'}, **extra)
                raw = response.choices[0].message.content or ''
                usage = response.usage.model_dump() if response.usage else None
                response_model = response.model
                finish_reason = response.choices[0].finish_reason
            emit(self.attempt / 'requests.jsonl', {**base, 'event': 'response_received',
                                                  'raw': raw, 'usage': usage, 'response_model': response_model,
                                                  'finish_reason': finish_reason,
                                                  'seconds': time.monotonic()-start})
            if finish_reason == 'length':
                raise OutputTruncatedError('Output token limit reached')
            return json.loads(raw)
        except Exception as exc:
            # Do not write exception messages which may contain credentials or request URLs.
            emit(self.attempt / 'requests.jsonl', {**base, 'event': 'request_failed',
                                                  'error_type': type(exc).__name__})
            raise

    def close(self):
        if self.client is not None:
            self.client.close()


class OutputTruncatedError(RuntimeError):
    pass


def accounting(run):
    events = [event for path in run.glob('cases/*/attempts/*/requests.jsonl') for event in read_jsonl(path)]
    starts = [row for row in events if row['event'] == 'request_started']
    responses = [row for row in events if row['event'] == 'response_received']
    terminal = {row['request_id'] for row in events if row['event'] in ['response_received', 'request_failed']}
    return {'attempted_calls_all_attempts': len(starts), 'responses_all_attempts': len(responses),
            'paid_api_calls_attempted': sum(row['backend'] != 'fake' for row in starts),
            'calls_with_unknown_outcome': sum(row['request_id'] not in terminal for row in starts),
            'usage_available_responses': sum(row['usage'] is not None for row in responses),
            'reported_tokens_all_attempts': {key: sum((row.get('usage') or {}).get(key, 0) or 0 for row in responses)
                                            for key in ['prompt_tokens', 'completion_tokens', 'total_tokens']},
            'note': 'All attempts included. Unreturned usage and unknown request outcomes cannot be reconstructed as billing.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--backend', choices=['fake', 'deepseek'], default='fake')
    parser.add_argument('--limit', type=int, default=1)
    parser.add_argument('--top-k', type=int, default=6)
    parser.add_argument('--lexical-mode', choices=['raw', 'content_terms'], default='raw')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--max-tokens', type=int, default=2048)
    parser.add_argument('--thinking', choices=['default', 'enabled', 'disabled'], default='default')
    parser.add_argument('--reasoning-effort', choices=['high', 'max'])
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--skip-single-control', action='store_true', help='Connectivity debug only: omit the seven-call single-agent control')
    args = parser.parse_args()
    if not (1 <= args.limit <= 30 and 1 <= args.top_k <= 12 and 1 <= args.repeats <= 5 and 128 <= args.max_tokens <= 16384):
        parser.error('Expected limit 1..30, top-k 1..12, repeats 1..5, max-tokens 128..16384')
    samples = read_jsonl(args.inputs)
    if len(samples) < args.limit:
        parser.error('Requested more samples than exist')
    samples = samples[:args.limit]
    if len({row['id'] for row in samples}) != len(samples):
        parser.error('Duplicate sample IDs')
    for row in samples:
        if set(row) != {'id', 'question', 'options'} or not isinstance(row['id'], str) or not row['id'].isalnum():
            parser.error('Expected safe unique id, question, options only; do not supply labels')
    # Explicitly disable optional cloud tracing for this local experiment.
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    retriever = LocalBM25Retriever.from_jsonl(args.corpus, args.top_k, args.lexical_mode)
    model, endpoint_hash = 'fake', None
    if args.backend == 'deepseek':
        if any(doc.metadata['source_url'].startswith('fixture:') for doc in retriever.documents):
            parser.error('Fixture corpus is only for offline tests; supply a reviewed medical corpus for live calls')
        from dotenv import dotenv_values
        env = dotenv_values(ROOT / '.env')
        model = env.get('DEEPSEEK_MODEL') or 'deepseek-flash'
        endpoint_hash = digest(env.get('DEEPSEEK_BASE_URL') or 'https://api.deepseek.com')
    source_paths = [Path(__file__), Path(__file__).with_name('evidence_core.py'),
                    Path(__file__).with_name('evidence_workflow.py'), Path(__file__).with_name('run_safety.py')]
    config = {'schema_version': 1, 'experiment': 'fixed_three_expert_known_copy_development',
              'backend': args.backend, 'model': model, 'endpoint_hash': endpoint_hash,
              'inputs_sha256': digest(args.inputs.read_text(encoding='utf-8')),
              'corpus_sha256': digest(args.corpus.read_text(encoding='utf-8')),
              'sample_ids': [row['id'] for row in samples], 'top_k': args.top_k,
              'lexical_mode': args.lexical_mode,
              'repeats': args.repeats, 'max_calls_per_case': 19 if args.skip_single_control else 26,
              'max_output_tokens_per_call': args.max_tokens,
              'thinking': args.thinking, 'reasoning_effort': args.reasoning_effort,
              'single_control': not args.skip_single_control,
              'sources': {path.name: digest(path.read_text(encoding='utf-8')) for path in source_paths},
              'packages': {name: importlib.metadata.version(name) for name in ['langgraph', 'langchain-core', 'rank-bm25', 'openai']}}
    run = args.run_dir.resolve()
    run.mkdir(parents=True, exist_ok=True)
    with RunLock(run / '.run.lock'):
        if (run / 'config.json').exists():
            if json.loads((run / 'config.json').read_text(encoding='utf-8')) != config:
                raise SystemExit('Resume fingerprint differs. Use a new run directory.')
        else:
            atomic_json(run / 'config.json', config)
            for path in source_paths:
                (run / ('snapshot_' + path.name)).write_bytes(path.read_bytes())
        results = []
        for sample in samples:
            case = run / 'cases' / sample['id']
            with RunLock(case / '.case.lock'):
                result_path = case / 'result.json'
                old = json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else None
                if old and (old['status'] == 'completed' or not args.retry_failed):
                    results.append(old)
                    continue
                attempt = new_attempt(case)
                backend = Backend(args.backend, attempt, model, config['max_calls_per_case'], args.max_tokens,
                                  args.thinking, args.reasoning_effort)
                result = {'id': sample['id'], 'attempt_id': attempt.name, 'backend': args.backend, 'status': 'error'}
                start = time.monotonic()
                state = {'sample': sample}
                try:
                    graph = build_graph(retriever, backend, args.repeats, not args.skip_single_control)
                    for update in graph.stream(state, stream_mode='updates'):
                        for node, values in update.items():
                            state.update(values)
                            atomic_json(attempt / f'checkpoint_{node}.json', state)
                    result.update(status='completed', state=state)
                except Exception as exc:
                    result.update(error_type=type(exc).__name__)
                finally:
                    backend.close()
                result.update(duration_seconds=time.monotonic()-start, calls=backend.calls,
                              finished_at=datetime.now(timezone.utc).isoformat())
                atomic_json(attempt / 'result.json', result)
                atomic_json(result_path, result)
                results.append(result)
                print(json.dumps({'done': len(results), 'id': sample['id'], 'status': result['status'],
                                  'calls': backend.calls}), flush=True)
        atomic_json(run / 'results.json', results)
        summary = {'planned': len(samples), 'completed': sum(row['status'] == 'completed' for row in results),
                   'backend': args.backend, 'scientific_result': False,
                   'purpose': 'Development prototype; fake results test plumbing only.', **accounting(run)}
        atomic_json(run / 'summary.json', summary)
        print(json.dumps(summary), flush=True)
        if summary['completed'] != len(samples):
            raise SystemExit('Some cases failed; inspect saved attempts. No silent retries were made.')


if __name__ == '__main__':
    main()
