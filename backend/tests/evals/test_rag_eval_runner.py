from app.evals.rag_runner import RagEvalRunner


class FakeRetriever:
    async def retrieve(self, query: str, *, top_k: int = 3):
        mapping = {
            "first": [
                {"source": "source-a"},
                {"source": "source-b"},
            ],
            "second": [
                {"source": "source-x"},
                {"source": "source-b"},
            ],
            "irrelevant": [],
        }
        return mapping[query][:top_k]


async def test_rag_eval_metrics() -> None:
    report = await RagEvalRunner(FakeRetriever()).run(
        [
            {"id": "1", "query": "first", "expected_source": "source-a"},
            {"id": "2", "query": "second", "expected_source": "source-b"},
            {"id": "3", "query": "irrelevant", "expected_source": None},
        ]
    )

    assert report.total_cases == 3
    assert report.recall_at_1 == 0.5
    assert report.recall_at_3 == 1.0
    assert report.recall_at_5 == 1.0
    assert report.mrr == 0.75
    assert report.mrr_at_10 == 0.75
    assert report.source_accuracy == 0.5
    assert report.irrelevant_rejection_rate == 1.0
    assert report.failures == []


async def test_rag_eval_accepts_multiple_relevant_sources() -> None:
    report = await RagEvalRunner(FakeRetriever()).run([
        {
            "id": "multi",
            "query": "second",
            "expected_sources": ["source-a", "source-b"],
        }
    ])

    assert report.recall_at_1 == 0.0
    assert report.recall_at_5 == 1.0
    assert report.mrr_at_10 == 0.5
