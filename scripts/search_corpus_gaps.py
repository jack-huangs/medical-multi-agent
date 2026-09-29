# 文件用途：为已知语料缺口搜索候选文章，保留查询与响应，不修改冻结语料。
"""Search candidate references for known corpus gaps, without changing frozen evidence."""
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from run_evidence_pilot import ROOT
from run_safety import atomic_json, RunLock

# 数字是冻结开发集中的零起始位置；这里按语料缺口选主题，不按模型答错的题来选。
QUERIES = {
    4: '(venlafaxine AND (normetanephrine OR metanephrine))',
    5: '(syncope AND (micturition OR "aortic stenosis"))',
    10: '("monoclonal gammopathy" AND (diagnosis OR evaluation))',
    14: '(iliopsoas AND "Thomas test")',
    15: '(barbiturate AND overdose)',
    16: '("cervicogenic dizziness" AND diagnosis)',
    18: '("sacral torsion" AND osteopathic)',
    21: '("intellectual disability" AND ("differential diagnosis" OR "learning disability"))',
    22: '("necrotizing enterocolitis" AND ("gestational age" OR onset))',
    23: '(bronchoscopy AND (pneumothorax OR handover))',
}


# 按预先固定的主题搜索候选文章；保存原始响应，暂不加入实验语料。
def search(item):
    index, terms, out = item
    query = f'{terms} AND OPEN_ACCESS:Y AND IN_EPMC:Y'
    url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urllib.parse.urlencode(
        {'query': query, 'format': 'json', 'pageSize': 20, 'resultType': 'core'})
    path = out / f'search_{index:02d}.json'
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
        else:
            with urllib.request.urlopen(url, timeout=40) as response:
                data = json.loads(response.read())
            atomic_json(path, data)
        hits = [h for h in data.get('resultList', {}).get('result', []) if h.get('pmcid')]
        # 只在已返回的候选中优先选综述，再看被引次数；这不等于临床质量排名。
        hits.sort(key=lambda h: (not any('review' in p.lower() for p in h.get('pubTypeList', {}).get('pubType', [])),
                                 -h.get('citedByCount', 0), h['pmcid']))
        return {'index': index, 'query': query, 'url': url, 'hit_count': data.get('hitCount'),
                'candidates': [{'pmcid': h['pmcid'], 'title': h.get('title'), 'year': h.get('pubYear'),
                                'publication_types': h.get('pubTypeList', {}).get('pubType', []),
                                'cited_by': h.get('citedByCount', 0), 'license': h.get('license')} for h in hits[:5]]}
    except Exception as exc:
        return {'index': index, 'query': query, 'url': url, 'error_type': type(exc).__name__, 'candidates': []}


def main():
    out = ROOT / 'runs/evidence_dependency/corpus_gap_candidates_20260925'
    out.mkdir(exist_ok=True)
    with RunLock(out / '.search.lock'):
        if (out / 'manifest.json').exists():
            raise SystemExit('Frozen candidate search already exists')
        atomic_json(out / 'query_plan.json', {'queries': QUERIES,
                    'selection': 'Known missing topics, using prior frozen topics only; no labels or model outcomes.',
                    'limits': '10 queries, top20 relevance results, prefer review within retrieved hits; 3 workers; no retry.'})
        # 并发下载公开检索结果，不调用大模型；候选仍需许可和原文相关性复核。
        with ThreadPoolExecutor(max_workers=3) as executor:
            rows = list(executor.map(search, [(i, terms, out) for i, terms in QUERIES.items()]))
        atomic_json(out / 'manifest.json', {'at': datetime.now(timezone.utc).isoformat(), 'searches': rows,
                    'note': 'Candidates only. Licensing and full-text relevance still require review; nothing appended to corpus v1.'})
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))


if __name__ == '__main__':
    main()
