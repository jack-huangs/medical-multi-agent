"""Inspect a frozen corpus without an LLM or gold-label access."""
import json
from pathlib import Path
from evidence_core import LocalBM25Retriever, retrieve
from run_evidence_pilot import ROOT, read_jsonl
from run_safety import atomic_json


def main():
    base = ROOT / 'runs/evidence_dependency'
    corpus = base / 'hard_corpus_v1'
    manifest = json.loads((corpus / 'manifest.json').read_text(encoding='utf-8'))
    retriever = LocalBM25Retriever.from_jsonl(corpus / 'corpus.jsonl', k=6)
    content_retriever = LocalBM25Retriever.from_jsonl(corpus / 'corpus.jsonl', k=6, lexical_mode='content_terms')
    samples = read_jsonl(base / 'hard_dev30/inputs.jsonl')
    sources = {row['id']: row for row in manifest['query_log']}
    preview = []
    for sample in samples:
        evidence = retrieve(retriever, sample)
        content_evidence = retrieve(content_retriever, sample)
        preview.append({'id': sample['id'], 'topic': sources[sample['id']]['topic'],
                        'topic_search_accepted_articles': sources[sample['id']]['accepted_articles'],
                        'unique_retrieved_documents': len({row['document_id'] for row in evidence}),
                        'retrieved_topic_search_document': bool({row['document_id'] for row in evidence} & set(sources[sample['id']]['accepted_articles'])),
                        'evidence': evidence,
                        'content_term_evidence': content_evidence,
                        'content_term_topic_document_match': bool({row['document_id'] for row in content_evidence} & set(sources[sample['id']]['accepted_articles'])),
                        'clinical_relevance_review': 'pending; matching search-origin document is only a retrieval diagnostic'})
    summary = {'questions': len(preview), 'articles': len(manifest['articles']), 'chunks': manifest['chunks'],
               'topics_with_accepted_article': sum(bool(row['topic_search_accepted_articles']) for row in preview),
               'questions_retrieving_own_topic_search_document': sum(row['retrieved_topic_search_document'] for row in preview),
               'content_term_topic_document_matches': sum(row['content_term_topic_document_match'] for row in preview),
               'note': 'No gold labels or API calls. Topic-origin match is not medical evidence sufficiency/entailment.'}
    atomic_json(corpus / 'retrieval_preview.json', {'summary': summary, 'cases': preview})
    lines = ['# Hard-pilot RAG retrieval preview', '', summary['note'], '',
             '| ID prefix | Topic | Topic-search docs | Content-term retrieved titles |', '|---|---|---:|---|']
    for row in preview:
        titles = list(dict.fromkeys(e['title'].replace('|','/') for e in row['content_term_evidence']))
        lines.append(f"| {row['id'][:12]} | {row['topic']} | {len(row['topic_search_accepted_articles'])} | {'; '.join(titles)} |")
    (corpus / 'retrieval_preview.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
