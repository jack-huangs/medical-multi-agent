# 文件用途：筛选困难开发题、去重和拆分模型输入/评估标签。
"""Freeze a diagnosis/reasoning development subset before any model evaluation."""
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from run_safety import RunLock, atomic_json
from download_medxpertqa import OUT as DATA

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/evidence_dependency/hard_dev30'
SEED = 20260924


# 读取每行一个 JSON 的记录文件。
def rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


# 去掉题干中重复嵌入的选项段落，选项继续由 options 字段单独保存。
def stem(question):
    return question.split('Answer Choices:', 1)[0].strip()


# 统一大小写和空白等文本形式，便于比较；这种匹配不能证明两句话医学含义相同。
def normalized(text):
    return ' '.join(re.findall(r'[a-z0-9]+', text.casefold()))


# 对题干和选项内容生成指纹；选项排序后再计算，避免顺序变化被当成新题。
def fingerprint(question, options):
    return hashlib.sha256(json.dumps([normalized(stem(question)), sorted(normalized(v) for v in options.values())], ensure_ascii=False).encode()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with RunLock(OUT / '.prepare.lock'):
        if (OUT / 'manifest.json').exists():
            raise SystemExit('Frozen subset exists; refusing overwrite')
        original = rows(DATA / 'Text/test.jsonl')
        legacy = rows(ROOT / 'data/medqa/train.jsonl') + rows(ROOT / 'data/medqa/test.jsonl')
        legacy_stems = {normalized(stem(row['question'])) for row in legacy}
        legacy_sets = [set(normalized(stem(row['question'])).split()) for row in legacy]
        index = defaultdict(set)
        for i, tokens in enumerate(legacy_sets):
            for token in tokens:
                index[token].add(i)
        candidates, excluded, seen = [], [], set()
        for row in original:
            if row['medical_task'] != 'Diagnosis' or row['question_type'] != 'Reasoning':
                continue
            key = fingerprint(row['question'], row['options'])
            if key in seen or normalized(stem(row['question'])) in legacy_stems:
                excluded.append({'source_id': row['id'], 'reason': 'exact normalized duplicate'})
                continue
            if re.search(r'\b(?:figure|photograph|image|diagram|chart)\b', stem(row['question']), re.I):
                excluded.append({'source_id': row['id'], 'reason': 'conservative visual-reference screen'})
                continue
            seen.add(key)
            candidates.append((row, key))
        # 固定随机种子，只打乱一次；不能看完模型成绩后再重新抽到满意为止。
        random.Random(SEED).shuffle(candidates)
        selected, overlaps = [], []
        for row, key in candidates:
            tokens = set(normalized(stem(row['question'])).split())
            # Candidate search is heuristic; it is not a semantic deduplication guarantee.
            rare = sorted((t for t in tokens if 0 < len(index[t]) < 500), key=lambda t: (len(index[t]), t))[:20]
            counts = Counter(i for token in rare for i in index[token])
            best = max(((len(tokens & legacy_sets[i])/len(tokens | legacy_sets[i]), i)
                        for i, _ in counts.most_common(40)), default=(0, None))
            overlaps.append({'source_id': row['id'], 'max_candidate_token_jaccard': best[0], 'legacy_row_index': best[1]})
            if best[0] >= .75:
                excluded.append({'source_id': row['id'], 'reason': 'candidate MedQA near duplicate Jaccard >= .75'})
                continue
            selected.append((row, key))
            if len(selected) == 30:
                break
        if len(selected) != 30:
            raise ValueError('Insufficient eligible questions')
        inputs = [{'id': key, 'question': stem(row['question']), 'options': row['options']} for row, key in selected]
        # 标签单独保存给评分程序；inputs 里只包含题干、选项和样本 ID。
        labels = [{'id': key, 'answer_idx': row['label']} for row, key in selected]
        assert all(label['answer_idx'] in sample['options'] for label, sample in zip(labels, inputs))
        metadata = [{'id': key, 'source_id': row['id'], 'body_system': row['body_system'],
                     'medical_task': row['medical_task'], 'question_type': row['question_type']} for row, key in selected]
        selected_ids = {row['id'] for row, key in selected}
        for name, records in [('inputs', inputs), ('labels', labels), ('metadata', metadata)]:
            (OUT / f'{name}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records), encoding='utf-8')
        atomic_json(OUT / 'reserved_source_ids.json', [row['id'] for row in original if row['id'] not in selected_ids])
        manifest = {'seed': SEED, 'source_revision': DATA.name,
                    'source_sha256': hashlib.sha256((DATA / 'Text/test.jsonl').read_bytes()).hexdigest(),
                    'source_count': len(original), 'eligible_before_visual_duplicate_filters': 921,
                    'eligible_after_initial_filters': len(candidates), 'selected_count': 30,
                    'remaining_source_questions_not_selected': len(original)-30,
                    'selection': 'Diagnosis + Reasoning; conservative visual-reference screen; shuffled once before model runs; first 30 passing exact/heuristic near-duplicate checks',
                    'source_split': 'official test, explicitly repurposed as local development; do not report as untouched test',
                    'metadata': metadata, 'body_system_counts': dict(Counter(r['body_system'] for r, key in selected)),
                    'excluded': excluded, 'selected_candidate_overlap_audit': overlaps,
                    'limitations': 'MedQA comparison covers normalized exact stems and a lexical candidate heuristic, not semantic duplication or pretraining exposure. Ten-option scores are not directly interchangeable with four-option MedQA scores.'}
        atomic_json(OUT / 'manifest.json', manifest)
        print(json.dumps({k: v for k, v in manifest.items() if k not in ['metadata', 'excluded', 'selected_candidate_overlap_audit']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
