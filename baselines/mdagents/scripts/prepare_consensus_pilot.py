# 文件用途：冻结旧 MedQA pilot/reserve/demonstrations 分组及标签。
"""Freeze development inputs and evaluator-only labels without calling an API."""

import hashlib
import json
import random
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SEED = 20260923


# 根据题目内容生成身份标识，帮助固定样本和检查重复。
def identity(row):
    # Exact normalized matches only; this does not detect semantic contamination.
    content = {
        "question": " ".join(row["question"].split()).casefold(),
        "options": {
            key: " ".join(value.split()).casefold()
            for key, value in sorted(row["options"].items())
        },
    }
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# 读取原始题目记录，后续分别生成输入和评估标签。
def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    train_path = ROOT / "data/medqa/train.jsonl"
    test_path = ROOT / "data/medqa/test.jsonl"
    train, test = read_rows(train_path), read_rows(test_path)
    test_ids = {identity(row) for row in test}
    seen, eligible = set(), []
    excluded_overlap = excluded_duplicate = 0
    for index, row in enumerate(train):
        sample_id = identity(row)
        if sample_id in test_ids:
            excluded_overlap += 1
        elif sample_id in seen:
            excluded_duplicate += 1
        else:
            seen.add(sample_id)
            eligible.append((index, sample_id, row))
    if len(eligible) < 305:
        raise SystemExit("Need at least 305 distinct development and demonstration examples.")
    selected = random.Random(SEED).sample(eligible, 305)
    groups = {"pilot_100": selected[:100], "reserve_200": selected[100:300], "demonstrations_5": selected[300:]}
    out = ROOT / "baselines/mdagents/runs/consensus_pilot_20260923"
    if out.exists():
        raise SystemExit(f"Refusing to replace a frozen pilot: {out}")
    assert len({sample_id for _, sample_id, _ in selected}) == 305
    assert not {sample_id for _, sample_id, _ in selected} & test_ids
    for _, _, row in selected:
        assert row["answer_idx"] in row["options"]
    metadata = {
        "status": "prepared_not_executed",
        "seed": SEED,
        "source": "MedQA training split; development only",
        "train_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
        "test_sha256": hashlib.sha256(test_path.read_bytes()).hexdigest(),
        "train_rows": len(train), "test_rows": len(test),
        "excluded_train_rows_matching_test": excluded_overlap,
        "excluded_duplicate_train_rows": excluded_duplicate,
        "overlap_check": "normalized question plus options; semantic overlap not checked",
        "groups": {},
    }
    out.mkdir(parents=True)
    for name, rows in groups.items():
        inputs, labels = [], []
        for index, sample_id, row in rows:
            inputs.append({"id": sample_id, "question": row["question"], "options": row["options"]})
            labels.append({"id": sample_id, "answer_idx": row["answer_idx"], "answer": row["answer"]})
        assert all("answer_idx" not in row and "answer" not in row for row in inputs)
        for suffix, payload in [("inputs", inputs), ("labels", labels)]:
            (out / f"{name}.{suffix}.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in payload), encoding="utf-8"
            )
        metadata["groups"][name] = {
            "count": len(rows),
            "train_row_indices_zero_based": [index for index, _, _ in rows],
            "meta_info_counts": dict(Counter(str(row.get("meta_info", "unknown")) for _, _, row in rows)),
        }
    (out / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), **metadata}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
