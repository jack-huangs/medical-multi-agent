"""Local retrieval, checked citations and known-lineage evidence accounting.

Lineage identifiers describe known copying, not statistical independence.
No benchmark labels are accepted by this module.
"""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict
from rank_bm25 import BM25Okapi


def normalized(text):
    return ' '.join(text.casefold().split())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def words(text):
    return re.findall(r'[a-z0-9]+', text.lower())


# General English + question boilerplate only; negation and clinical measurements remain.
RETRIEVAL_STOPWORDS = set('a an the and or of to in on at for from with by as is are was were be been being that this these those which what who whose whom where when how his her their he she they him them it its has have had do does did during after before over under into about also than then but if while include includes including following likely most patient patients presents presented presentation physician clinic hospital examination exam physical history reports reported reveals revealed shows show year years old male female man woman boy girl temperature blood pressure pulse respirations rate'.split())


def retrieval_tokens(text, mode):
    tokens = words(text)
    return [word for word in tokens if word not in RETRIEVAL_STOPWORDS] if mode == 'content_terms' else tokens


class LocalBM25Retriever(BaseRetriever):
    """LangChain retriever with deterministic ordering and no paid embedding calls."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    documents: list[Document]
    index: object
    k: int = 6
    lexical_mode: str = 'raw'

    @classmethod
    def from_jsonl(cls, path, k=6, lexical_mode='raw'):
        if lexical_mode not in ['raw', 'content_terms']:
            raise ValueError('Unknown lexical mode')
        rows = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
        seen, documents = set(), []
        for row in rows:
            required = {'document_id', 'chunk_id', 'source_url', 'license', 'locator', 'text'}
            if not required <= row.keys() or any(not isinstance(row[key], str) or not row[key].strip() for key in required):
                raise ValueError('Corpus requires nonempty document_id/chunk_id/source_url/license/locator/text')
            key = row['chunk_id']
            if key in seen or not words(row['text']):
                raise ValueError('Duplicate chunk ID or empty tokenized chunk')
            seen.add(key)
            # Default unit is a passage, NOT an entire paper or URL.
            metadata = {key: value for key, value in row.items() if key != 'text'}
            metadata['root_id'] = row.get('root_id', row['chunk_id'])
            metadata['content_sha256'] = digest(row['text'])
            documents.append(Document(page_content=row['text'], metadata=metadata))
        if not documents:
            raise ValueError('Empty corpus')
        documents.sort(key=lambda doc: doc.metadata['chunk_id'])
        return cls(documents=documents, index=BM25Okapi([retrieval_tokens(doc.page_content, lexical_mode) or ['empty'] for doc in documents]),
                   k=k, lexical_mode=lexical_mode)

    def _get_relevant_documents(self, query, *, run_manager):
        tokens = retrieval_tokens(query, self.lexical_mode)
        if self.lexical_mode == 'content_terms':
            tokens = list(dict.fromkeys(tokens))
        scores = self.index.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), self.documents[i].metadata['chunk_id']))
        return [Document(page_content=self.documents[i].page_content,
                         metadata={**self.documents[i].metadata, 'retrieval_score': float(scores[i])})
                for i in order[:self.k]]


def retrieve(retriever, sample):
    if set(sample) != {'id', 'question', 'options'}:
        raise ValueError('Model input must contain exactly id/question/options; labels are forbidden')
    query = sample['question'] + '\n' + '\n'.join(sample['options'].values())
    docs = retriever.invoke(query)
    return [{'evidence_id': f'E{i+1}', 'text': doc.page_content, **doc.metadata}
            for i, doc in enumerate(docs)]


def evidence_view(evidence):
    # Known lineage is hidden from ordinary baselines; citations/locations are always visible.
    keys = ['evidence_id', 'document_id', 'chunk_id', 'source_url', 'locator', 'text']
    return [{key: item[key] for key in keys} for item in evidence]


def validate_opinion(value, options, evidence, opinion_id, parents=()):
    if not isinstance(value, dict) or value.get('answer') not in options:
        raise ValueError('Invalid answer')
    confidence = value.get('confidence')
    if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
        raise ValueError('Confidence must be in [0,1]')
    if not isinstance(value.get('brief_basis'), str) or len(value['brief_basis']) > 1600:
        raise ValueError('Missing or oversized concise basis')
    claims = value.get('claims')
    if not isinstance(claims, list) or len(claims) > 6:
        raise ValueError('Expected at most six evidence claims')
    evidence_by_id = {item['evidence_id']: item for item in evidence}
    parent_by_id = {claim['claim_id']: claim for opinion in parents for claim in opinion['claims']}
    checked = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or claim.get('option') not in options or claim.get('relation') not in ['supports', 'refutes']:
            raise ValueError('Invalid claim option/relation')
        if not isinstance(claim.get('text'), str) or not claim['text'].strip() or len(claim['text']) > 800:
            raise ValueError('Invalid claim text')
        citations, inherited = claim.get('citations'), claim.get('parent_claim_ids')
        if not isinstance(citations, list) or not isinstance(inherited, list):
            raise ValueError('Citations and parent_claim_ids must be lists')
        roots = set()
        for citation in citations:
            if not isinstance(citation, dict) or citation.get('evidence_id') not in evidence_by_id:
                raise ValueError('Unknown evidence citation')
            source = evidence_by_id[citation['evidence_id']]
            quote = citation.get('quote')
            if not isinstance(quote, str) or len(normalized(quote)) < 12 or normalized(quote) not in normalized(source['text']):
                raise ValueError('Quote is not a verbatim span of the cited evidence')
            roots.add(source['root_id'])
        for parent in inherited:
            if not isinstance(parent, str) or parent not in parent_by_id:
                raise ValueError('Unknown parent claim')
            roots.update(parent_by_id[parent]['root_ids'])
        if not roots:
            raise ValueError('External evidence claims require a checked citation or known parent')
        checked.append({**claim, 'claim_id': f'{opinion_id}.C{index+1}', 'root_ids': sorted(roots)})
    return {'opinion_id': opinion_id, 'answer': value['answer'], 'confidence': confidence,
            'brief_basis': value['brief_basis'], 'claims': checked}


def opinion_view(opinion):
    return {**opinion, 'claims': [{key: value for key, value in claim.items() if key != 'root_ids'}
                                for claim in opinion['claims']]}


def ledger(opinions):
    """Retain all claims but cap repeated support for an option at one per known root.

    Both support and refutation are retained. Counts are descriptive, not probabilities.
    Different roots may still be dependent through training or undiscovered common sources.
    """
    groups = defaultdict(lambda: {'claim_ids': set(), 'opinion_ids': set(), 'claim_texts': set()})
    for opinion in opinions:
        for claim in opinion['claims']:
            for root in claim['root_ids']:
                bucket = groups[(claim['option'], claim['relation'], root)]
                bucket['claim_ids'].add(claim['claim_id'])
                bucket['opinion_ids'].add(opinion['opinion_id'])
                bucket['claim_texts'].add(claim['text'])
    return [{'option': option, 'relation': relation, 'root_id': root,
             'known_root_contributions': 1, **{key: sorted(value) for key, value in bucket.items()}}
            for (option, relation, root), bucket in sorted(groups.items())]


def intervention(evidence, sample_id, condition, repeat_count=3):
    if condition not in ['original', 'repeated', 'dedup', 'dependency'] or repeat_count < 1:
        raise ValueError('Invalid intervention')
    # Predeclared deterministic choice: no access to gold, predictions or source correctness.
    target = sorted(evidence, key=lambda item: digest([sample_id, item['chunk_id']]))[0]
    copies = [{'slot': i, 'evidence_id': target['evidence_id'], 'text': target['text']}
              for i in range(repeat_count)]
    # Dedup is a real text-normalization operation against the retained base evidence.
    seen = {normalized(item['text']) for item in evidence}
    for item in copies:
        blank = condition == 'original' or (condition == 'dedup' and normalized(item['text']) in seen)
        seen.add(normalized(item['text']))
        if blank:
            item['text'] = ' ' * len(item['text'])
            item['evidence_id'] = 'EMPTY'
    return {'target_evidence_id': target['evidence_id'], 'slots': copies,
            'note': 'Repeated delivery of an existing source; no new expert endorsements.',
            'padding': 'character count only; tokenizer length is NOT matched'}
