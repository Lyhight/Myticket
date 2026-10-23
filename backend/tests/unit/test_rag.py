from app.agent.rag import (
    HybridKnowledgeRetriever,
    KeywordKnowledgeRetriever,
    KnowledgeBaseService,
    KnowledgeChunker,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.agent.vector_index import VectorSearchHit
import pytest


class FakeEmbeddingClient:
    model = "fake-embedding"

    async def embed(self, texts):
        vectors = []
        for text in texts:
            if "退款" in text or "钱退回来" in text:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


class FailingEmbeddingClient:
    model = "failing-embedding"

    async def embed(self, texts):
        raise RuntimeError("embedding unavailable")


class RecordingVectorIndex:
    def __init__(self):
        self.chunks = []
        self.deleted_document_ids = []

    async def replace_document(self, document_id, chunks):
        self.chunks = list(chunks)

    async def delete_document(self, document_id):
        self.deleted_document_ids.append(document_id)

    async def search(self, vector, *, limit, score_threshold=0.0):
        refund = next(
            chunk for chunk in self.chunks if "退款" in chunk.content
        )
        return [VectorSearchHit(chunk_id=refund.id, score=0.97)]


class FailingVectorIndex(RecordingVectorIndex):
    async def search(self, vector, *, limit, score_threshold=0.0):
        raise RuntimeError("qdrant unavailable")


def test_chunker_splits_with_overlap() -> None:
    chunks = KnowledgeChunker(
        chunk_size=10,
        overlap=2,
    ).split("abcdefghijklmnopqrst")

    assert chunks == ["abcdefghij", "ijklmnopqr", "qrst"]


def test_chunker_prefers_sentence_boundary() -> None:
    chunks = KnowledgeChunker(
        chunk_size=16,
        overlap=3,
    ).split("第一条退款规则。第二条物流规则很长很长。第三条规则。")

    assert chunks[0].endswith("。")


async def test_rag_ingests_and_retrieves_relevant_chunks(
    db_session,
) -> None:
    repository = KnowledgeRepository(db_session)
    service = KnowledgeBaseService(repository)
    retriever = KeywordKnowledgeRetriever(repository)

    await service.ingest(
        title="退款政策",
        source="policy/refund.md",
        content="已付款但未发货的订单，可以申请退款。",
    )
    await service.ingest(
        title="物流说明",
        source="policy/logistics.md",
        content="物流单号可以用于查询包裹当前位置。",
    )

    results = await retriever.retrieve(
        "未发货订单怎么退款",
        top_k=2,
    )

    assert results
    assert results[0]["title"] == "退款政策"
    assert results[0]["source"] == "policy/refund.md"
    assert "申请退款" in str(results[0]["content"])
    assert float(results[0]["score"]) > 0
    assert results[0]["retrieval_method"] == "keyword"
    assert str(results[0]["citation_id"]).startswith("KB-")
    assert results[0]["document_version"] == 1


async def test_same_document_is_not_reversioned_without_changes(
    db_session,
) -> None:
    repository = KnowledgeRepository(db_session)
    service = KnowledgeBaseService(repository)
    await service.ingest(
        title="退款政策",
        source="policy/versioned.md",
        content="未发货订单可以退款。",
    )
    await service.ingest(
        title="退款政策",
        source="policy/versioned.md",
        content="未发货订单可以退款。",
    )
    document = (await repository.list_documents())[0]
    assert document.version == 1

    await service.ingest(
        title="退款政策更新",
        source="policy/versioned.md",
        content="未发货订单可以立即申请退款。",
    )
    await db_session.refresh(document)
    assert document.version == 2


async def test_ingest_rejects_documents_with_too_many_chunks(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.agent.rag.settings.knowledge_max_chunks", 2)
    service = KnowledgeBaseService(KnowledgeRepository(db_session))

    with pytest.raises(ValueError, match="too many chunks"):
        await service.ingest(
            title="超长文档",
            source="policy/too-long.md",
            content="退款规则。" * 500,
        )


async def test_rag_returns_empty_for_unrelated_query(
    db_session,
) -> None:
    repository = KnowledgeRepository(db_session)
    await KnowledgeBaseService(repository).ingest(
        title="退款政策",
        source="policy/refund.md",
        content="未发货订单可以申请退款。",
    )

    results = await KeywordKnowledgeRetriever(
        repository
    ).retrieve("会员积分兑换")

    assert results == []


async def test_rag_rejects_single_generic_bigram_overlap(
    db_session,
) -> None:
    repository = KnowledgeRepository(db_session)
    await KnowledgeBaseService(repository).ingest(
        title="优惠券政策",
        source="policy/coupon.md",
        content="优惠券仅适用于指定商品。",
    )

    results = await KeywordKnowledgeRetriever(
        repository
    ).retrieve("商品有哪些颜色和尺寸")

    assert results == []


async def test_hybrid_rag_finds_semantic_match_without_keywords(
    db_session,
) -> None:
    repository = KnowledgeRepository(db_session)
    embedding_client = FakeEmbeddingClient()
    service = KnowledgeBaseService(
        repository,
        embedding_client=embedding_client,
    )
    await service.ingest(
        title="售后资金规则",
        source="policy/refund-vector.md",
        content="退款申请审核通过后按原支付路径返还。",
    )
    await service.ingest(
        title="配送规则",
        source="policy/shipping-vector.md",
        content="包裹发出后可使用运单号码查询。",
    )

    results = await HybridKnowledgeRetriever(
        repository,
        embedding_client=embedding_client,
    ).retrieve("钱退回来要走什么路径")

    assert results[0]["source"] == "policy/refund-vector.md"
    assert results[0]["retrieval_method"] == "hybrid"
    assert float(results[0]["vector_score"]) == 1.0


async def test_hybrid_rag_falls_back_to_keyword_search(
    db_session,
) -> None:
    repository = KnowledgeRepository(db_session)
    await KnowledgeBaseService(repository).ingest(
        title="积分政策",
        source="policy/points.md",
        content="订单完成后增加会员积分。",
    )

    results = await HybridKnowledgeRetriever(
        repository,
        embedding_client=FailingEmbeddingClient(),
    ).retrieve("会员积分")

    assert results
    assert results[0]["source"] == "policy/points.md"
    assert results[0]["retrieval_method"] == "keyword_fallback"


async def test_hybrid_rag_uses_qdrant_vector_index(db_session) -> None:
    repository = KnowledgeRepository(db_session)
    embedding_client = FakeEmbeddingClient()
    vector_index = RecordingVectorIndex()
    service = KnowledgeBaseService(
        repository,
        embedding_client=embedding_client,
        vector_index=vector_index,
    )
    await service.ingest(
        title="售后规则",
        source="policy/indexed-refund.md",
        content="款项会在审核后沿原支付路径退款。",
    )

    results = await HybridKnowledgeRetriever(
        repository,
        embedding_client=embedding_client,
        vector_index=vector_index,
    ).retrieve("钱退回来要走什么路径")

    assert results[0]["source"] == "policy/indexed-refund.md"
    assert results[0]["vector_backend"] == "qdrant_hnsw"
    assert results[0]["vector_score"] == 0.97


async def test_qdrant_failure_falls_back_to_local_vector_scan(
    db_session,
) -> None:
    repository = KnowledgeRepository(db_session)
    embedding_client = FakeEmbeddingClient()
    vector_index = FailingVectorIndex()
    service = KnowledgeBaseService(
        repository,
        embedding_client=embedding_client,
        vector_index=vector_index,
    )
    await service.ingest(
        title="售后规则",
        source="policy/fallback-refund.md",
        content="退款审核后会沿原支付路径返还。",
    )

    results = await HybridKnowledgeRetriever(
        repository,
        embedding_client=embedding_client,
        vector_index=vector_index,
    ).retrieve("钱退回来要走什么路径")

    assert results[0]["vector_backend"] == "local_scan_fallback"
    assert results[0]["vector_score"] == 1.0
