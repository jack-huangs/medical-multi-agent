"""Freeze 30 previously unused development inputs, separately from labels. No API calls."""
import json
import re
from pathlib import Path
from run_safety import atomic_json, RunLock
import hashlib

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'baselines/mdagents/runs/consensus_pilot_20260923'
OUTPUT = ROOT / 'runs/evidence_dependency/dev30'
PATTERN = r'figure|photograph|shown|image|diagram|chart|below|following table'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with RunLock(OUTPUT / '.prepare.lock'):
        if (OUTPUT / 'manifest.json').exists():
            raise SystemExit('Frozen sample already exists; refusing overwrite.')
        path = SOURCE / 'reserve_200.inputs.jsonl'
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        candidates = rows[100:]
        selected = [row for row in candidates if not re.search(PATTERN, row['question']+' '+str(row['options']), re.I)][:30]
        assert len(selected) == 30
        # Selection depends on input completeness only; labels are first read below.
        labels = {row['id']: row for row in [json.loads(line) for line in (SOURCE / 'reserve_200.labels.jsonl').read_text(encoding='utf-8').splitlines()]}
        for name, values in [('inputs', selected), ('labels', [labels[row['id']] for row in selected])]:
            (OUTPUT / f'{name}.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in values), encoding='utf-8')
        atomic_json(OUTPUT / 'manifest.json', {
            'source': str(path.relative_to(ROOT)), 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'selection': 'reserve_200 indices 100..199; first 30 passing the predeclared conservative visual-reference filter',
            'filter': PATTERN, 'sample_ids': [row['id'] for row in selected],
            'quality_review': 'All 30 input texts inspected by the coding assistant on 2026-09-23: no explicitly required missing visual identified. This is not clinician adjudication.',
            'quality_notes': 'Original units/wording and minor punctuation artifacts preserved; no answer correctness review used for selection.',
            'split': 'development; not official test; public pretraining exposure unknown',
        })
        print(json.dumps({'count': len(selected), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()
