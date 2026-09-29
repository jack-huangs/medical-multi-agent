# 文件用途：按冻结检索主题建立困难题共享文献库和下载清单。
"""Build a small topic-union CC BY corpus, with gold-blind queries frozen in source.

Development only: lexical/semantic relevance still needs review. All questions use
the same union corpus; no per-question answer or label is supplied to retrieval.
"""
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from import_evidence_article import convert
from run_evidence_pilot import read_jsonl, ROOT
from run_safety import RunLock, atomic_json

TOPICS = [
    'microcytic anemia ferritin inflammation',
    'infant hepatomegaly hypoglycemia glycogen storage',
    'primary amenorrhea adolescent evaluation',
    'cellulitis catheter staphylococcus streptococcus',
    'venlafaxine normetanephrine false positive',
    'syncope micturition aortic stenosis',
    'daptomycin pneumonia surfactant',
    'acute stroke initial assessment glucose',
    'functional structural scoliosis bending',
    'cerebral palsy scoliosis pulmonary',
    'monoclonal gammopathy diagnostic evaluation',
    'giant cell arteritis visual loss glucocorticoids',
    'radial head dysfunction supination',
    'rheumatoid arthritis treatment liver enzymes',
    'iliopsoas somatic dysfunction Thomas test',
    'primidone barbiturate overdose respiratory depression',
    'cervicogenic dizziness somatic dysfunction',
    'superior vena cava syndrome lymphoma management',
    'sacral torsion osteopathic diagnosis',
    'scoliosis vertebral rotation rib hump',
    'cardiac myxoma diastolic murmur',
    'intellectual disability learning language differential diagnosis',
    'necrotizing enterocolitis gestational age onset',
    'bronchoscopy handover pneumothorax safety',
    'virilization testosterone adrenal ovarian evaluation',
    'etomidate adrenal suppression sepsis intubation',
    'pediatric hydrocarbon ingestion management',
    'aortic dissection acute kidney injury diagnosis',
    'primary ovarian insufficiency diagnostic evaluation',
    'urinary retention acute kidney injury urine output',
]


# 下载公开文章或检索响应；设置超时，防止网络请求无限等待。
def get(url):
    with urllib.request.urlopen(url, timeout=40) as response:
        return response.read()


def main():
    inputs = ROOT / 'runs/evidence_dependency/hard_dev30/inputs.jsonl'
    samples = read_jsonl(inputs)
    if len(samples) != len(TOPICS):
        raise ValueError('The frozen topic list expects exactly 30 development questions')
    out = ROOT / 'runs/evidence_dependency/hard_corpus_v1'
    out.mkdir(parents=True, exist_ok=True)
    with RunLock(out / '.build.lock'):
        if (out / 'manifest.json').exists():
            raise SystemExit('Frozen corpus exists; refusing overwrite')
        queries = [{'id': row['id'], 'topic': topic} for row, topic in zip(samples, TOPICS)]
        atomic_json(out / 'queries.json', {'inputs_sha256': hashlib.sha256(inputs.read_bytes()).hexdigest(),
                                         'selection': 'Prepared from question text/options before reading probe scores or labels',
                                         'queries': queries})
        article_dir = out / 'articles'
        article_dir.mkdir(exist_ok=True)
        pool, query_log, articles = {}, [], {}
        # Two query formulations are declared before search; use fallback only if no licensed article is obtained.
        for i, item in enumerate(queries):
            accepted = []
            attempts = []
            for fallback in [False, True]:
                terms = item['topic'].split()
                topic = item['topic'] if not fallback else ' '.join(terms[:3])
                query = f'TITLE_ABS:({topic}) AND OPEN_ACCESS:Y AND IN_EPMC:Y'
                url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urllib.parse.urlencode(
                    {'query': query, 'format': 'json', 'pageSize': 6, 'resultType': 'core'})
                cache_path = out / f'search_{i:02d}_{int(fallback)}.json'
                try:
                    data = cache_path.read_bytes() if cache_path.exists() else get(url)
                    cache_path.write_bytes(data)
                    response = json.loads(data)
                except Exception as exc:
                    attempts.append({'query': query, 'error_type': type(exc).__name__})
                    continue
                hits = response.get('resultList', {}).get('result', [])
                hits = sorted(hits, key=lambda hit: not any('review' in kind.lower() for kind in hit.get('pubTypeList', {}).get('pubType', [])))
                for hit in hits:
                    pmcid = hit.get('pmcid')
                    if not pmcid:
                        continue
                    path = article_dir / f'{pmcid}.xml'
                    try:
                        raw = path.read_bytes() if path.exists() else get(f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML')
                        path.write_bytes(raw)
                        title, license_text, chunks = convert(raw, pmcid)
                        for chunk in chunks:
                            pool[chunk['chunk_id']] = chunk
                        articles[pmcid] = {'title': title, 'license': license_text, 'chunks': len(chunks),
                                           'xml_sha256': hashlib.sha256(raw).hexdigest()}
                        accepted.append(pmcid)
                        attempts.append({'query': query, 'pmcid': pmcid, 'status': 'accepted', 'title': title})
                    except Exception as exc:
                        attempts.append({'query': query, 'pmcid': pmcid, 'status': 'skipped', 'error_type': type(exc).__name__})
                    time.sleep(.15)
                    if len(set(accepted)) >= 2:
                        break
                if accepted:
                    break
            query_log.append({**item, 'accepted_articles': sorted(set(accepted)), 'attempts': attempts})
            atomic_json(out / 'progress.json', {'processed_topics': i+1, 'articles': len(articles),
                                               'chunks': len(pool), 'query_log': query_log})
            print(json.dumps({'topic': i+1, 'accepted': len(set(accepted)), 'articles': len(articles), 'chunks': len(pool)}), flush=True)
        corpus = out / 'corpus.jsonl'
        corpus.write_text(''.join(json.dumps(pool[key], ensure_ascii=False)+'\n' for key in sorted(pool)), encoding='utf-8')
        atomic_json(out / 'manifest.json', {'created_at': datetime.now(timezone.utc).isoformat(),
                    'purpose': 'Development topic-union corpus, not an unbiased comprehensive medical reference corpus',
                    'corpus_sha256': hashlib.sha256(corpus.read_bytes()).hexdigest(),
                    'query_file_sha256': hashlib.sha256((out / 'queries.json').read_bytes()).hexdigest(),
                    'articles': articles, 'chunks': len(pool), 'query_log': query_log,
                    'topics_without_licensed_hit': [r['id'] for r in query_log if not r['accepted_articles']],
                    'quality': 'License and XML identity checked; full clinical relevance and entailment NOT adjudicated'})


if __name__ == '__main__':
    main()
