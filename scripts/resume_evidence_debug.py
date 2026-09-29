# 文件用途：显式调试续跑与成功响应复用；不同预算调试不作正式对照。
"""Single-case diagnostic continuation with exact-request replay.

Allows a different output cap after truncation. This is explicitly NOT an equal-budget
scientific run. Every reuse records its origin; paid calls are separately capped.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from evidence_core import LocalBM25Retriever, digest
from evidence_workflow import build_graph
from run_evidence_pilot import Backend, accounting, emit, read_jsonl
from run_safety import RunLock, atomic_json, new_attempt


# 按请求内容和模型配置生成缓存键；这里只允许调试改变输出上限，不是等预算实验。
def replay_key(stage, model, messages, thinking='default', reasoning_effort=None):
    return digest([stage, model, messages, 0, thinking, reasoning_effort])


# 只缓存正常结束且可解析的响应；截断或没有对应请求的内容不能复用。
def replay_records(source_run):
    cache = {}
    for path in sorted(source_run.glob('cases/*/attempts/*/requests.jsonl')):
        requests = {}
        for row in read_jsonl(path):
            if row['event'] == 'request_started':
                requests[row['request_id']] = row
            elif row['event'] == 'response_received' and row.get('finish_reason') == 'stop':
                request = requests.get(row['request_id'])
                if request is None or request.get('temperature') != 0:
                    continue
                try:
                    json.loads(row['raw'])
                except (ValueError, TypeError):
                    continue
                key = replay_key(row['stage'], request['model'], request['messages'],
                                 request.get('thinking', 'default'), request.get('reasoning_effort'))
                cache[key] = {'response': row, 'source_path': str(path.resolve())}
    return cache


# 优先复用完全匹配的旧响应，找不到时才请求模型，并分别记录新增调用。
class ReplayBackend(Backend):
    def __init__(self, *args, cache, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache, self.reuses = cache, 0

    def complete(self, stage, system, payload):
        messages = [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
        key = replay_key(stage, self.model, messages, self.thinking, self.reasoning_effort)
        if key in self.cache:
            source = self.cache[key]
            self.reuses += 1
            emit(self.attempt / 'requests.jsonl', {
                'event': 'response_reused', 'stage': stage, 'request_hash': key,
                'source_path': source['source_path'], 'source_request_id': source['response']['request_id'],
                'raw': source['response']['raw'], 'new_paid_calls': 0,
            })
            return json.loads(source['response']['raw'])
        return super().complete(stage, system, payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-run', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--max-api-calls', type=int, default=3)
    parser.add_argument('--max-tokens', type=int, default=8192)
    args = parser.parse_args()
    if not 1 <= args.max_api_calls <= 5 or not 4096 <= args.max_tokens <= 8192:
        parser.error('Debug cap: 1..5 API calls and 4096..8192 output tokens')
    import os
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    source = args.from_run.resolve()
    config = json.loads((source / 'config.json').read_text(encoding='utf-8'))
    if len(config['sample_ids']) != 1 or config['single_control'] or config['backend'] != 'deepseek':
        parser.error('Only one-case DeepSeek connectivity runs without single control are supported')
    if digest(args.inputs.read_text(encoding='utf-8')) != config['inputs_sha256'] or digest(args.corpus.read_text(encoding='utf-8')) != config['corpus_sha256']:
        parser.error('Inputs or corpus changed')
    sample = next(row for row in read_jsonl(args.inputs) if row['id'] == config['sample_ids'][0])
    cache = replay_records(source)
    run = args.run_dir.resolve()
    run.mkdir(parents=True, exist_ok=True)
    with RunLock(run / '.run.lock'):
        if (run / 'config.json').exists():
            raise SystemExit('Debug output already exists; inspect it instead of repeating paid calls')
        config = {**config, 'debug_continuation_of': str(source), 'max_new_api_calls': args.max_api_calls,
                  'max_output_tokens_per_new_call': args.max_tokens,
                  'cache_sha256': digest(cache), 'scientific_equal_budget_run': False}
        atomic_json(run / 'config.json', config)
        atomic_json(run / 'replay_sources.json', cache)
        for name in ['resume_evidence_debug.py', 'run_evidence_pilot.py', 'run_safety.py', 'evidence_core.py', 'evidence_workflow.py']:
            (run / ('snapshot_' + name)).write_bytes(Path(__file__).with_name(name).read_bytes())
        attempt = new_attempt(run / 'cases' / sample['id'])
        backend = ReplayBackend('deepseek', attempt, config['model'], args.max_api_calls, args.max_tokens,
                                config.get('thinking', 'default'), config.get('reasoning_effort'), cache=cache)
        state = {'sample': sample}
        result = {'id': sample['id'], 'attempt_id': attempt.name, 'backend': 'deepseek', 'status': 'error'}
        started = time.monotonic()
        try:
            graph = build_graph(LocalBM25Retriever.from_jsonl(args.corpus, config['top_k'], config.get('lexical_mode','raw')), backend,
                                config['repeats'], single_control=False)
            for update in graph.stream(state, stream_mode='updates'):
                for node, values in update.items():
                    state.update(values)
                    atomic_json(attempt / f'checkpoint_{node}.json', state)
            result.update(status='completed', state=state)
        except Exception as exc:
            result.update(error_type=type(exc).__name__)
        finally:
            backend.close()
        result.update(calls=backend.calls, reused_responses=backend.reuses,
                      finished_at=datetime.now(timezone.utc).isoformat(), duration_seconds=time.monotonic()-started)
        atomic_json(attempt / 'result.json', result)
        atomic_json(attempt.parent.parent / 'result.json', result)
        atomic_json(run / 'results.json', [result])
        summary = {'planned': 1, 'completed': int(result['status'] == 'completed'), 'backend': 'deepseek',
                   'scientific_result': False, 'reused_responses': backend.reuses,
                   'source_run_accounting': accounting(source), 'new_run_accounting': accounting(run),
                   'note': 'Debug continuation with changed token cap. Historical response costs belong to their original runs.'}
        atomic_json(run / 'summary.json', summary)
        print(json.dumps(summary), flush=True)
        if result['status'] != 'completed':
            raise SystemExit('Debug continuation failed; preserve records and review without silent retries')


if __name__ == '__main__':
    main()
