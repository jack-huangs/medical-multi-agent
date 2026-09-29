# 文件用途：导入 Europe PMC 开放许可文章，保留 XML、来源和段落位置。
"""Import a CC BY PMC article through Europe PMC's fullTextXML service."""
import argparse
import hashlib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from run_safety import RunLock, atomic_json


# 提取 XML 标签内的文字并整理空白，去掉标签本身。
def text_of(node):
    return ' '.join(''.join(node.itertext()).split()) if node is not None else ''


# 从 XML 核验文章身份和 CC BY 许可，再提取正文段落；许可通过不代表内容适用。
def convert(data, pmcid):
    root = ET.fromstring(data)
    licenses = root.findall('.//license')
    license_text = ' '.join(text_of(node) for node in licenses)
    license_markup = ' '.join(ET.tostring(node, encoding='unicode') for node in licenses)
    if not (re.search(r'creativecommons\.org/licenses/by/\d', license_markup)
            or re.search(r'\bCC[- ]BY\s+\d', license_text, re.I)):
        raise ValueError('This minimal importer accepts explicitly CC BY licensed articles only')
    title = text_of(root.find('.//article-title'))
    ids = [text_of(node) for node in root.findall('.//article-id') if node.get('pub-id-type') in ['pmc', 'pmcid']]
    if not any(value.removeprefix('PMC') == pmcid.removeprefix('PMC') for value in ids):
        raise ValueError('Returned article identifier does not match requested PMCID')
    chunks = []
    # Abstract and body only. No bibliography extraction and no generated evidence.
    nodes = root.findall('./front/article-meta/abstract//p') + root.findall('./body//p')
    for ordinal, node in enumerate(nodes):
        if node.findall('.//p'):
            continue
        paragraph = text_of(node)
        if len(paragraph) < 80:
            continue
        root_id = f'{pmcid}:p{ordinal}'
        for start in range(0, len(paragraph), 1600):
            text = paragraph[start:start+1600]
            if len(text) < 40:
                continue
            chunks.append({'document_id': pmcid, 'chunk_id': f'{root_id}:c{start}',
                           'root_id': root_id, 'title': title,
                           'source_url': f'https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/',
                           'license': license_text, 'locator': f'abstract/body p ordinal={ordinal}; normalized characters {start}:{start+len(text)}',
                           'text': text})
    if not chunks:
        raise ValueError('No text chunks extracted')
    return title, license_text, chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pmcid')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'PMC\d+', args.pmcid):
        parser.error('Expected a PMCID such as PMC6386825')
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with RunLock(out / '.import.lock'):
        if (out / 'manifest.json').exists():
            raise SystemExit('Corpus snapshot exists; refusing overwrite')
        url = f'https://www.ebi.ac.uk/europepmc/webservices/rest/{args.pmcid}/fullTextXML'
        with urllib.request.urlopen(url, timeout=40) as response:
            data = response.read()
        title, license_text, chunks = convert(data, args.pmcid)
        (out / 'source.xml').write_bytes(data)
        content = ''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in chunks)
        (out / 'corpus.jsonl').write_text(content, encoding='utf-8')
        atomic_json(out / 'manifest.json', {
            'pmcid': args.pmcid, 'title': title, 'download_url': url, 'license': license_text,
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'raw_xml_sha256': hashlib.sha256(data).hexdigest(),
            'corpus_sha256': hashlib.sha256((out / 'corpus.jsonl').read_bytes()).hexdigest(),
            'chunks': len(chunks), 'selection': 'Topic-selected for a single development connectivity check, not a benchmark corpus',
            'lineage_scope': 'Only shared paragraph ancestry known; citation-chain dependence is not inferred',
        })
        print(json.dumps({'title': title, 'chunks': len(chunks), 'output': str(out)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
