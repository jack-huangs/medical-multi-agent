"""Offline corpus/query diagnostics; topic-only retrieval is a manual diagnostic control."""
import json
from collections import Counter
from pathlib import Path

from evidence_core import LocalBM25Retriever
from run_evidence_pilot import ROOT, read_jsonl
from run_safety import atomic_json


def main():
    base = ROOT / 'runs/evidence_dependency'
    corpus = base / 'hard_corpus_v1'
    manifest = json.loads((corpus / 'manifest.json').read_text(encoding='utf-8'))
    topics = {r['id']: r for r in manifest['query_log']}
    retriever = LocalBM25Retriever.from_jsonl(corpus / 'corpus.jsonl', 6, 'content_terms')
    rows, top_hits = [], Counter()
    modes = ['question_and_options', 'question_only', 'manual_topic_only']
    for sample in read_jsonl(base / 'hard_dev30/inputs.jsonl'):
        info = topics[sample['id']]
        queries = [sample['question'] + '\n' + '\n'.join(sample['options'].values()),
                   sample['question'], info['topic']]
        item = {'id': sample['id'], 'topic': info['topic'],
                'accepted_topic_articles': info['accepted_articles'], 'modes': {}}
        for name, query in zip(modes, queries):
            docs = retriever.invoke(query)
            retrieved_ids = {d.metadata['document_id'] for d in docs}
            if name == modes[0]: top_hits[docs[0].metadata['chunk_id']] += 1
            item['modes'][name] = {'topic_origin_document_match': bool(retrieved_ids & set(info['accepted_articles'])),
                                   'unique_documents': len(retrieved_ids),
                                   'chunks': [{'chunk_id': d.metadata['chunk_id'], 'title': d.metadata.get('title'),
                                               'score': d.metadata['retrieval_score']} for d in docs]}
        rows.append(item)
    accepted = [r for r in rows if r['accepted_topic_articles']]
    summary = {'n': len(rows), 'topics_with_accepted_article': len(accepted),
               'topic_origin_matches': {name: sum(r['modes'][name]['topic_origin_document_match'] for r in rows) for name in modes},
               'with_articles_but_full_query_misses': [r['id'] for r in accepted if not r['modes'][modes[0]]['topic_origin_document_match']],
               'most_frequent_top1_chunks': top_hits.most_common(5)}
    note = ('Search-origin document matching is a proxy, not clinical relevance or evidence sufficiency. '
            'Manual topics were selected by an assistant from inputs/options; topic-only is an informed diagnostic control, '
            'not an automatic retriever or an unbiased clinical baseline. No labels or API calls used.')
    atomic_json(corpus / 'query_diagnostics.json', {'summary': summary, 'cases': rows, 'note': note})
    lines = ['# 查询与语料覆盖排查', '', note, '', '| 查询方式 | 命中本题主题搜索所得文章 / 30 |', '|---|---:|']
    for name in modes: lines.append(f"| {name} | {summary['topic_origin_matches'][name]} |")
    lines.extend(['', '## 有已收录主题文章，但完整查询未命中的题目', ''])
    lines.extend('- ' + ident for ident in summary['with_articles_but_full_query_misses'])
    lines.extend(['', '查询诊断不改变当前冻结实验的检索方式或语料。主题匹配改善不能替代逐片段适用性与引用蕴含检查。'])
    (corpus / 'query_diagnostics.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
