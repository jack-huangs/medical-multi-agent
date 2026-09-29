# 文件用途：旧 MDAgents 自适应实验运行器，含隔离 worker、轨迹与评分。
"""Run the frozen development pilot with isolated workers and incremental scoring."""

import argparse
import contextlib
import hashlib
import json
import math
import random
import re
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from run_safety import RunLock, atomic_json, new_attempt

ROOT = Path(__file__).resolve().parents[3]
PILOT = ROOT / 'baselines/mdagents/runs/consensus_pilot_20260923'


# 逐行读取 JSON；每行一条记录，便于处理题目、标签或调用日志。
def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


# 通过公共原子写入工具保存结果，减少中断导致的文件损坏。
def save_json(path, value):
    atomic_json(path, value)


# 兼容旧实验不同的响应结构，取出最终可评分的答案文本。
def answer_text(response):
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        for key in ['majority', '0.0', 0.0]:
            if key in response:
                return answer_text(response[key])
        if len(response) == 1:
            return answer_text(next(iter(response.values())))
    return ''


# 只接受明确选择的选项字母；模糊或矛盾输出留作缺失，避免随意猜答案。
def parse_answer(text, options):
    """Accept explicit selections only; ambiguous output needs manual review."""
    cleaned = re.sub(r'[*_`#]', '', text)
    patterns = [
        r'(?im)(?:^|\n)\s*final\s+answer\s*[:：\-]\s*\(?([A-J])\b',
        r'(?im)(?:^|\n)\s*(?:the\s+)?(?:correct\s+)?answer\s*(?:is\s*[:：]?|[:：])\s*\(?([A-J])\b',
    ]
    for pattern in patterns:
        choices = set(re.findall(pattern, cleaned))
        if choices:
            return next(iter(choices)) if len(choices) == 1 and choices <= set(options) else None
    simple = re.fullmatch(r'\s*\(?([A-J])\)?[.)]?\s*', cleaned)
    if simple and simple[1] in options:
        return simple[1]
    return None


# 估计正确率的 Wilson 置信区间；样本少时，即使全对，区间也不会只剩 100%。
def wilson(correct, count):
    if not count:
        return None
    z = 1.959963984540054
    p = correct / count
    denominator = 1 + z*z/count
    center = (p + z*z/(2*count)) / denominator
    half = z*math.sqrt(p*(1-p)/count + z*z/(4*count*count))/denominator
    return [center-half, center+half]


def worker(sample, demos, config, run_dir):
    case = Path(run_dir) / 'cases' / sample['id']
    with RunLock(case / '.case.lock'):
        result_path = case / 'result.json'
        if result_path.exists():
            return json.loads(result_path.read_text(encoding='utf-8'))
        out = new_attempt(case)
        result = run_worker_attempt(sample, demos, config, out)
        result['attempt_id'] = out.name
        result['trace_relative_path'] = str((out / 'trace.jsonl').relative_to(Path(run_dir)))
        save_json(out / 'result.json', result)
        save_json(result_path, result)
        return result


# 执行某题的一次隔离尝试；调用限制和日志属于本次尝试。
def run_worker_attempt(sample, demos, config, out):
    # Only inputs and independent demonstration labels enter this process.
    sys.path.insert(0, str(ROOT / 'baselines/mdagents/upstream'))
    import utils
    from itertools import count

    utils.AGENT_IDS = count(1)
    random.seed(config['seed'] ^ int(sample['id'][:12], 16))
    started = time.monotonic()
    calls = 0
    original_complete = utils.Agent._complete
    original_client = utils.openai_compatible_client

    def bounded_complete(self, message, temperature=None):
        nonlocal calls
        if calls >= config['max_calls_per_case']:
            raise RuntimeError('Per-case model call budget exhausted')
        if time.monotonic()-started > config['max_seconds_per_case']:
            raise TimeoutError('Per-case time budget exhausted')
        calls += 1
        return original_complete(self, message, temperature)

    def bounded_client(model):
        return original_client(model).with_options(timeout=120.0, max_retries=2)

    utils.Agent._complete = bounded_complete
    utils.openai_compatible_client = bounded_client
    result = {'id': sample['id'], 'status': 'error', 'difficulty': None}
    with (out / 'console.log').open('w', encoding='utf-8') as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        utils.configure_trace_log(out / 'trace.jsonl')
        try:
            question, _ = utils.create_question(sample, 'medqa')
            result['question_presented'] = question
            difficulty = utils.determine_difficulty(question, config['difficulty'], config['model'])
            result['difficulty'] = difficulty
            args = SimpleNamespace(dataset='medqa')
            if difficulty == 'basic':
                response = utils.process_basic_query(question, list(demos), config['model'], args)
            elif difficulty == 'intermediate':
                response = utils.process_intermediate_query(question, list(demos), config['model'], args)
            elif difficulty == 'advanced':
                response = utils.process_advanced_query(question, config['model'], args)
            else:
                raise ValueError('Unrecognized route')
            text = answer_text(response)
            result.update(status='completed', response=response, answer_text=text,
                          prediction=parse_answer(text, sample['options']))
        except Exception as exc:
            # Keep error categories; do not put potentially credential-bearing errors in summaries.
            result.update(error_type=type(exc).__name__)
        finally:
            utils.Agent._complete = original_complete
            utils.openai_compatible_client = original_client
    events = read_jsonl(out / 'trace.jsonl')
    responses = [event for event in events if event['event'] == 'model_response']
    result.update(
        duration_seconds=round(time.monotonic()-started, 3),
        model_calls=calls,
        successful_model_calls=len(responses),
        usage_available_calls=sum(event.get('usage') is not None for event in responses),
        tokens={key: sum((event.get('usage') or {}).get(key, 0) or 0 for event in responses)
                for key in ['prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens']},
        resolved_models=sorted({event['resolved_model'] for event in responses}),
        response_models=sorted({event['response_model'] for event in responses if event.get('response_model')}),
        expert_opinions=[{'stage': event['stage'], 'opinions': event['opinions']}
                         for event in events if event['event'] == 'expert_opinions'],
        routing_responses=[event['response'] for event in responses
                           if event.get('message', '').startswith('Now, given the medical query as below, you need to decide')],
    )
    return result


# 汇总本批已保存结果；不要把日志缺失或失败记录当作正常成功。
def summarize(results, labels, total, elapsed):
    correct = sum(row.get('prediction') == labels[row['id']]['answer_idx'] for row in results)
    errors = sum(row['status'] != 'completed' for row in results)
    parse_failures = sum(row['status'] == 'completed' and row.get('prediction') is None for row in results)
    by_route = {}
    for row in results:
        route = row.get('difficulty') or 'unrouted'
        bucket = by_route.setdefault(route, {'attempted': 0, 'correct': 0})
        bucket['attempted'] += 1
        bucket['correct'] += row.get('prediction') == labels[row['id']]['answer_idx']
    return {
        'status': 'complete' if len(results) == total else 'running',
        'planned': total, 'attempted': len(results), 'correct': correct,
        'incorrect_valid_answers': len(results)-correct-errors-parse_failures,
        'execution_errors': errors, 'parse_failures': parse_failures,
        'accuracy_including_failures': correct/len(results) if results else None,
        'wilson_95_interval_including_failures': wilson(correct, len(results)),
        'by_route': by_route,
        'model_calls': sum(row['model_calls'] for row in results),
        'successful_model_calls': sum(row['successful_model_calls'] for row in results),
        'tokens': {key: sum(row['tokens'][key] for row in results)
                  for key in ['prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens']},
        'elapsed_seconds_this_invocation': round(elapsed, 2),
        'summed_case_seconds': round(sum(row['duration_seconds'] for row in results), 2),
        'resolved_models': sorted({model for row in results for model in row['resolved_models']}),
        'response_models': sorted({model for row in results for model in row['response_models']}),
        'note': 'Development sample from MedQA train; one stochastic run. API usage counts successful responses; SDK transport retries not individually counted.',
    }


# 把当前统计保存为可阅读报告，原始逐题日志仍单独保留。
def write_reports(run, results, labels, samples, summary):
    scored = [{**row, 'gold': labels[row['id']]['answer_idx'],
               'correct': row.get('prediction') == labels[row['id']]['answer_idx']} for row in results]
    save_json(run / 'scored_results.json', scored)
    save_json(run / 'summary.json', summary)
    wrong = [row for row in scored if not row['correct']]
    save_json(run / 'incorrect_or_failed.json', wrong)
    lo, hi = summary['wilson_95_interval_including_failures'] or [0, 0]
    lines = ['# MDAgents 固定 100 题开发摸底', '',
             f"状态：{summary['status']}；已完成 {summary['attempted']}/{summary['planned']} 题。", '',
             f"正确 {summary['correct']}，有效错答 {summary['incorrect_valid_answers']}，执行失败 {summary['execution_errors']}，答案解析失败 {summary['parse_failures']}。", '',
             f"包含失败的正确率：{100*(summary['accuracy_including_failures'] or 0):.1f}%；Wilson 95% 区间：{100*lo:.1f}%–{100*hi:.1f}%。", '',
             f"模型调用：{summary['model_calls']}；成功调用 token 合计：{summary['tokens']['total_tokens']:,}。", '',
             '数据来自 MedQA 训练集的固定开发样本；未用于模型微调。公开题目的预训练暴露未知。单次结果不代表官方测试成绩或临床诊断效果。', '',
             '运行采用修正后的方法实现：初诊意见保底、轮间意见更新、定向消息传递、明确难度标签解析。具体源码快照和参数见本运行目录。', '',
             '| 路由 | 题数 | 正确数 |', '|---|---:|---:|']
    for route, counts in summary['by_route'].items():
        lines.append(f"| {route} | {counts['attempted']} | {counts['correct']} |")
    lines += ['', '## 错答与失败（用于开发分析）', '']
    for row in wrong:
        sample = samples[row['id']]
        lines += [f"### {row['id'][:12]}", '', sample['question'], '',
                  *[f"- {key}: {value}" for key, value in sample['options'].items()], '',
                  f"标准答案：{row['gold']}；预测：{row.get('prediction')}；路由：{row['difficulty']}；状态：{row['status']}。", '',
                  row.get('answer_text', row.get('error_type', '')), '']
    (run / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--difficulty', choices=['adaptive', 'basic', 'intermediate', 'advanced'], default='adaptive')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--sample-group', choices=['pilot_100', 'reserve_200'], default='pilot_100')
    parser.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100 or not 1 <= args.workers <= 8:
        parser.error('limit must be 1..100; workers must be 1..8')
    input_path = PILOT / f'{args.sample_group}.inputs.jsonl'
    all_inputs = read_jsonl(input_path)
    if args.offset < 0 or args.offset + args.limit > len(all_inputs):
        parser.error('Requested range exceeds the frozen sample group.')
    inputs = all_inputs[args.offset:args.offset + args.limit]
    labels = {row['id']: row for row in read_jsonl(PILOT / f'{args.sample_group}.labels.jsonl')}
    demo_inputs = read_jsonl(PILOT / 'demonstrations_5.inputs.jsonl')
    demo_labels = {row['id']: row for row in read_jsonl(PILOT / 'demonstrations_5.labels.jsonl')}
    demos = [{**row, **demo_labels[row['id']]} for row in demo_inputs]
    assert not {row['id'] for row in inputs} & set(demo_labels)
    assert all(set(row) == {'id', 'question', 'options'} for row in inputs)
    run = (args.run_dir or PILOT / ('adaptive_' + datetime.now().strftime('%Y%m%d_%H%M%S'))).resolve()
    run.mkdir(parents=True, exist_ok=True)
    with RunLock(run / '.run.lock'):
        execute_run(args, run, inputs, labels, demos, input_path)


# 保存运行配置及源码版本，安排题目执行并持续写出结果。
def execute_run(args, run, inputs, labels, demos, input_path):
    sources = [ROOT / 'baselines/mdagents/upstream/utils.py', Path(__file__).resolve(),
               ROOT / 'scripts/run_safety.py']
    config = {'seed': 20260923, 'model': args.model, 'difficulty': args.difficulty,
              'sample_group': args.sample_group, 'offset': args.offset,
              'samples': [row['id'] for row in inputs], 'workers': args.workers,
              'max_calls_per_case': 160, 'max_seconds_per_case': 1800,
              'source_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
              'input_sha256': hashlib.sha256(input_path.read_bytes()).hexdigest(),
              'demo_sha256': hashlib.sha256(json.dumps(demos, sort_keys=True).encode()).hexdigest()}
    if (run / 'config.json').exists():
        if json.loads((run / 'config.json').read_text(encoding='utf-8')) != config:
            raise SystemExit('Resume configuration/source differs; use a new directory.')
    else:
        save_json(run / 'config.json', config)
        for path in sources:
            (run / ('snapshot_' + path.name)).write_bytes(path.read_bytes())
    print(json.dumps({'run_dir': str(run), 'planned': len(inputs), 'workers': args.workers}), flush=True)
    results, started = [], time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(worker, sample, demos, config, str(run)) for sample in inputs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            summary = summarize(results, labels, len(inputs), time.monotonic()-started)
            write_reports(run, results, labels, {row['id']: row for row in inputs}, summary)
            print(json.dumps({'done': len(results), 'correct': summary['correct'],
                              'errors': summary['execution_errors'], 'parse_failures': summary['parse_failures'],
                              'last_id': result['id'][:12], 'route': result['difficulty'],
                              'calls': summary['model_calls'], 'tokens': summary['tokens']['total_tokens'],
                              'elapsed_seconds': summary['elapsed_seconds_this_invocation']}), flush=True)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
