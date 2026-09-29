# 文件用途：BM25 检索、结构化意见验证、引用检查、来源账本和重复证据干预。
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


# 统一大小写和空白等文本形式，便于比较；这种匹配不能证明两句话医学含义相同。
def normalized(text):
    return ' '.join(text.casefold().split())


# 给内容计算稳定指纹，用来判断数据或配置有没有变化，不用于评判内容是否正确。
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# 把英文和数字切成检索用的词；这是简单分词，不包含医学语义理解。
def words(text):
    return re.findall(r'[a-z0-9]+', text.lower())


# General English + question boilerplate only; negation and clinical measurements remain.
RETRIEVAL_STOPWORDS = set('a an the and or of to in on at for from with by as is are was were be been being that this these those which what who whose whom where when how his her their he she they him them it its has have had do does did during after before over under into about also than then but if while include includes including following likely most patient patients presents presented presentation physician clinic hospital examination exam physical history reports reported reveals revealed shows show year years old male female man woman boy girl temperature blood pressure pulse respirations rate'.split())


# 去掉通用词以减少检索噪声；保留否定词和临床数值，避免改变题意。
def retrieval_tokens(text, mode):
    tokens = words(text)
    return [word for word in tokens if word not in RETRIEVAL_STOPWORDS] if mode == 'content_terms' else tokens


# 本地关键词检索器：给片段打分并返回前 k 条，不需要调用付费向量接口。
class LocalBM25Retriever(BaseRetriever):
    """LangChain retriever with deterministic ordering and no paid embedding calls."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    documents: list[Document]
    index: object
    k: int = 6
    lexical_mode: str = 'raw'

    # 读取证据库并核对来源字段；默认把片段当作根来源，不把整篇文章混成一条证据。
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

    # 按 BM25 分数排序；同分时按片段 ID 排序，使离线结果可重复。
    def _get_relevant_documents(self, query, *, run_manager):
        tokens = retrieval_tokens(query, self.lexical_mode)
        if self.lexical_mode == 'content_terms':
            tokens = list(dict.fromkeys(tokens))
        scores = self.index.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), self.documents[i].metadata['chunk_id']))
        return [Document(page_content=self.documents[i].page_content,
                         metadata={**self.documents[i].metadata, 'retrieval_score': float(scores[i])})
                for i in order[:self.k]]


# 只接收题目与选项；严格拒绝标准答案字段，防止答案泄漏给模型。
def retrieve(retriever, sample):
    if set(sample) != {'id', 'question', 'options'}:
        raise ValueError('Model input must contain exactly id/question/options; labels are forbidden')
    query = sample['question'] + '\n' + '\n'.join(sample['options'].values())
    docs = retriever.invoke(query)
    return [{'evidence_id': f'E{i+1}', 'text': doc.page_content, **doc.metadata}
            for i, doc in enumerate(docs)]


# 挑出专家可以看到的证据字段；普通组看不到额外的已知来源映射。
def evidence_view(evidence):
    # Known lineage is hidden from ordinary baselines; citations/locations are always visible.
    keys = ['evidence_id', 'document_id', 'chunk_id', 'source_url', 'locator', 'text']
    return [{key: item[key] for key in keys} for item in evidence]


# 检查回答格式、原文引用和父观点；能验证引文存在，但不能验证它真的支持医学结论。
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
    # 父观点就是这条主张所继承的旧主张，例如 I0.C1 表示初始专家 0 的第 1 条主张。
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
            # 直接引用原文：记下这段证据的根来源。
            roots.add(source['root_id'])
        for parent in inherited:
            if not isinstance(parent, str) or parent not in parent_by_id:
                raise ValueError('Unknown parent claim')
            # 继承别人的观点：沿用旧来源，不能因为换了说法就生成一份“新证据”。
            roots.update(parent_by_id[parent]['root_ids'])
        if not roots:
            raise ValueError('External evidence claims require a checked citation or known parent')
        checked.append({**claim, 'claim_id': f'{opinion_id}.C{index+1}', 'root_ids': sorted(roots)})
    return {'opinion_id': opinion_id, 'answer': value['answer'], 'confidence': confidence,
            'brief_basis': value['brief_basis'], 'claims': checked}


# 保留观点和引用，隐藏内部追踪用的根来源字段，供普通讨论组阅读。
def opinion_view(opinion):
    return {**opinion, 'claims': [{key: value for key, value in claim.items() if key != 'root_ids'}
                                for claim in opinion['claims']]}


# 同一选项、支持或反驳方向、根来源合并为一组，避免把同一依据重复计数。
def ledger(opinions):
    """Retain all claims but cap repeated support for an option at one per known root.

    Both support and refutation are retained. Counts are descriptive, not probabilities.
    Different roots may still be dependent through training or undiscovered common sources.
    """
    groups = defaultdict(lambda: {'claim_ids': set(), 'opinion_ids': set(), 'claim_texts': set()})
    for opinion in opinions:
        for claim in opinion['claims']:
            for root in claim['root_ids']:
                # 同一来源被三位专家引用，记录三人的传播关系，但来源贡献仍只计一次。
                bucket = groups[(claim['option'], claim['relation'], root)]
                bucket['claim_ids'].add(claim['claim_id'])
                bucket['opinion_ids'].add(opinion['opinion_id'])
                bucket['claim_texts'].add(claim['text'])
    return [{'option': option, 'relation': relation, 'root_id': root,
             'known_root_contributions': 1, **{key: sorted(value) for key, value in bucket.items()}}
            for (option, relation, root), bucket in sorted(groups.items())]


# 固定选择一条已有证据，构造重复或去重条件；选择过程不看标准答案。
def intervention(evidence, sample_id, condition, repeat_count=3):
    if condition not in ['original', 'repeated', 'dedup', 'dependency'] or repeat_count < 1:
        raise ValueError('Invalid intervention')
    # Predeclared deterministic choice: no access to gold, predictions or source correctness.
    target = sorted(evidence, key=lambda item: digest([sample_id, item['chunk_id']]))[0]
    # 这些是同一段证据的重复展示，不是假造三个独立专家的背书。
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
