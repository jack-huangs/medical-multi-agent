"""Rescore explicit first-line answers and report input-quality subgroups offline."""
import argparse
import json
import re
from pathlib import Path

from run_consensus_pilot import PILOT, read_jsonl, save_json, wilson


def first_line_selection(text, options):
    lines = [re.sub(r'[*_`#]', '', line).strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    match = re.fullmatch(r'\(?([A-J])\)?[.)]?\s+(.+)', lines[0])
    if not match or match[1] not in options:
        return None

    def normalize(value):
        return ' '.join(value.casefold().split()).rstrip('. ')

    return match[1] if normalize(match[2]) == normalize(options[match[1]]) else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args()
    run = args.run_dir
    config = json.loads((run / 'config.json').read_text(encoding='utf-8'))
    sample_group = config.get('sample_group', 'pilot_100')
    inputs = {row['id']: row for row in read_jsonl(PILOT / f'{sample_group}.inputs.jsonl')}
    labels = {row['id']: row['answer_idx'] for row in read_jsonl(PILOT / f'{sample_group}.labels.jsonl')}
    raw = json.loads((run / 'scored_results.json').read_text(encoding='utf-8'))
    summary = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
    quality = json.loads((run / 'input_quality_review.json').read_text(encoding='utf-8'))
    missing = {row['id'] for row in quality['reviewed_candidates'] if row['visual_reference_without_image']}
    rows, corrections = [], []
    for original in raw:
        row = dict(original)
        if row['status'] == 'completed' and row.get('prediction') is None:
            # The parser sees the model output and options only, never the gold label.
            recovered = first_line_selection(row.get('answer_text', ''), inputs[row['id']]['options'])
            if recovered:
                row['prediction'] = recovered
                corrections.append({'id': row['id'], 'previous_prediction': None, 'prediction': recovered,
                                    'rule': 'First nonempty line is one explicit label followed by exact option text.'})
        row['correct'] = row.get('prediction') == labels[row['id']]
        row['visual_reference_without_image'] = row['id'] in missing
        rows.append(row)
    correct = sum(row['correct'] for row in rows)
    reviewed = {**summary, 'correct': correct,
                'accuracy_including_failures': correct/len(rows),
                'wilson_95_interval_including_failures': wilson(correct, len(rows)),
                'incorrect_valid_answers': sum(row.get('prediction') is not None and not row['correct'] for row in rows),
                'parse_failures': sum(row['status'] == 'completed' and row.get('prediction') is None for row in rows),
                'empty_final_answers': sum(row['status'] == 'completed' and not row.get('answer_text', '').strip() for row in rows),
                'offline_parser_corrections': corrections,
                'subgroups': {}}
    reviewed['by_route'] = {}
    for row in rows:
        route = row.get('difficulty') or 'unrouted'
        bucket = reviewed['by_route'].setdefault(route, {'attempted': 0, 'correct': 0})
        bucket['attempted'] += 1
        bucket['correct'] += row['correct']
    for name, flag in [('explicit_image_reference', True), ('no_explicit_missing_image_reference', False)]:
        group = [row for row in rows if row['visual_reference_without_image'] == flag]
        count = len(group)
        right = sum(row['correct'] for row in group)
        reviewed['subgroups'][name] = {'count': count, 'correct': right,
                                     'accuracy': right/count if count else None,
                                     'wilson_95_interval': wilson(right, count)}
    reviewed['subgroup_note'] = 'Secondary descriptive analysis after inspecting errors; all 100 remain in primary denominator. No guarantee that every unflagged question has complete context.'
    audit_path = run / 'routing_audit.json'
    integrity = json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.exists() else {}
    reviewed['single_attempt_checks_passed'] = integrity.get('single_attempt_checks_passed')
    reviewed['integrity_flagged_cases'] = integrity.get('integrity_flagged_cases', [])
    integrity_note = ('运行完整性检查失败：准确率仅描述保存答案，调用量、token 与过程不可作为正式实验依据。'
                      if reviewed['single_attempt_checks_passed'] is False else
                      '运行完整性检查通过必要检查，但不证明账单完整。' if reviewed['single_attempt_checks_passed'] is True else
                      '尚无独立运行完整性检查记录。')
    reviewed['integrity_note'] = integrity_note
    save_json(run / 'reviewed_summary.json', reviewed)
    save_json(run / 'reviewed_results.json', rows)
    lo, hi = reviewed['wilson_95_interval_including_failures']
    lines = ['# 固定 100 题开发测试：复核结果', '',
             integrity_note, '',
             f"已完成 {len(rows)}/{summary['planned']}；正确 {correct}，有效错答 {reviewed['incorrect_valid_answers']}，执行失败 {reviewed['execution_errors']}，未解析 {reviewed['parse_failures']}。", '',
             f"总体正确率 {100*correct/len(rows):.1f}%，Wilson 95% 区间 {100*lo:.1f}%–{100*hi:.1f}%。", '',
             f"离线格式补识别 {len(corrections)} 题；未重新请求模型，原始日志和原评分保留。", '',
             f"最近一次控制器执行耗时 {summary['elapsed_seconds_this_invocation']:.1f} 秒（不等于跨续跑总时间）；记录的模型调用 {summary['model_calls']} 次；记录的成功响应 token {summary['tokens']['total_tokens']:,}。", '',
             '## 路由', '', '| 路由 | 数量 | 复核后正确 |', '|---|---:|---:|']
    for route in summary['by_route']:
        group = [row for row in rows if (row.get('difficulty') or 'unrouted') == route]
        lines.append(f"| {route} | {len(group)} | {sum(row['correct'] for row in group)} |")
    lines += ['', '## 输入质量分组（探索性）', '', '| 分组 | 数量 | 正确 |', '|---|---:|---:|']
    for name, group in reviewed['subgroups'].items():
        lines.append(f"| {name} | {group['count']} | {group['correct']} |")
    lines += ['', '全体 100 题仍为主要分母。此分组是在发现首道错题缺图后，对全部输入筛查形成的探索性分析；未标记缺图不等于输入一定完整。', '',
              '数据来自公开 MedQA 训练集的固定开发样本，与示例题分离；这是单次模型运行，不是官方测试集结果，也不是临床验证。公开题目在预训练中的暴露未知。', '',
              '## 与标准答案不一致或失败的题目', '']
    for row in rows:
        if row['correct']:
            continue
        sample = inputs[row['id']]
        lines += [f"### {row['id'][:12]}", '', sample['question'], '',
                  *[f"- {key}: {value}" for key, value in sample['options'].items()], '',
                  f"标准答案：{labels[row['id']]}；模型选择：{row.get('prediction')}；引用未提供图片：{row['visual_reference_without_image']}。", '',
                  row.get('answer_text', row.get('error_type', '')), '']
    (run / 'reviewed_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(reviewed, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
