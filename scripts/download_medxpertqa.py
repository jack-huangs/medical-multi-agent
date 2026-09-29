# 文件用途：下载固定官方 MedXpertQA 版本并记录校验信息。
"""Fetch only the official Text split, at an immutable Hugging Face revision."""
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from run_safety import RunLock, atomic_json

ROOT = Path(__file__).resolve().parents[1]
REPO = 'TsinghuaC3I/MedXpertQA'
REVISION = '7e7c465a68eb2b866926bfa59c8c9d17a8daba65'
OUT = ROOT / 'data/medxpertqa' / REVISION


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with RunLock(OUT / '.download.lock'):
        if (OUT / 'manifest.json').exists():
            print('Frozen download already exists: ' + str(OUT))
            return
        files = {}
        for name in ['README.md', 'Text/dev.jsonl', 'Text/test.jsonl']:
            url = f'https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{name}'
            path = OUT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=60) as response:
                content = response.read()
            path.write_bytes(content)
            files[name] = {'url': url, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
            if name.endswith('.jsonl'):
                rows = [json.loads(line) for line in content.decode().splitlines() if line.strip()]
                files[name].update(count=len(rows), fields=sorted(rows[0]),
                                   option_counts=sorted({len(row['options']) for row in rows}))
        atomic_json(OUT / 'manifest.json', {'repository': REPO, 'revision': REVISION,
                    'downloaded_at': datetime.now(timezone.utc).isoformat(), 'files': files,
                    'license_from_dataset_card': 'MIT',
                    'publication_note': 'Keep question text and examples local; dataset authors request not posting examples online.'})
        print(json.dumps({'output': str(OUT), 'files': files}, ensure_ascii=False))


if __name__ == '__main__':
    main()
