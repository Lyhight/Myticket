import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.evals.statistics import wilson_interval


class KnowledgeRetriever(Protocol):
    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 3,
    ) -> list[dict[str, Any]]: ...


class RagEvalReport(BaseModel):
    total_cases: int
    positive_cases: int
    negative_cases: int
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    recall_at_3_ci95: tuple[float, float]
    recall_at_5_ci95: tuple[float, float]
    mrr: float
    mrr_at_10: float
    source_accuracy: float
    irrelevant_rejection_rate: float
    irrelevant_rejection_rate_ci95: tuple[float, float]
    failures: list[dict[str, Any]] = Field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return self.model_dump()


class RagEvalRunner:
    def __init__(
        self,
        retriever: KnowledgeRetriever,
        *,
        max_rank: int = 10,
    ):
        self.retriever = retriever
        self.max_rank = max_rank

    async def run_file(self, path: Path) -> RagEvalReport:
        cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        return await self.run(cases)

    async def run(self, cases: list[dict[str, Any]]) -> RagEvalReport:
        positives = [
            case
            for case in cases
            if case.get("expected_source") or case.get("expected_sources")
        ]
        negatives = [case for case in cases if case not in positives]
        hit_at_1 = 0
        hit_at_3 = 0
        hit_at_5 = 0
        reciprocal_rank_sum = 0.0
        reciprocal_rank_at_10_sum = 0.0
        rejected = 0
        failures: list[dict[str, Any]] = []

        for case in cases:
            results = await self.retriever.retrieve(
                case["query"],
                top_k=max(self.max_rank, 10),
            )
            actual_sources = [
                str(item.get("source")) for item in results
            ]
            expected_source = case.get("expected_source")
            expected_sources = case.get("expected_sources")
            if expected_sources is None:
                expected_sources = (
                    [expected_source] if expected_source is not None else []
                )

            if not expected_sources:
                if not results:
                    rejected += 1
                else:
                    failures.append(
                        {
                            "id": case["id"],
                            "type": "false_positive",
                            "query": case["query"],
                            "actual_sources": actual_sources,
                        }
                    )
                continue

            ranks = [
                actual_sources.index(source) + 1
                for source in expected_sources
                if source in actual_sources
            ]
            rank = min(ranks) if ranks else None

            if rank == 1:
                hit_at_1 += 1
            if rank is not None and rank <= 3:
                hit_at_3 += 1
            if rank is not None and rank <= 5:
                hit_at_5 += 1
            if rank is not None and rank <= self.max_rank:
                reciprocal_rank_sum += 1 / rank
            if rank is not None and rank <= 10:
                reciprocal_rank_at_10_sum += 1 / rank
            if rank is None or rank > self.max_rank:
                failures.append(
                    {
                        "id": case["id"],
                        "type": "miss",
                        "query": case["query"],
                        "expected_sources": expected_sources,
                        "actual_sources": actual_sources,
                    }
                )

        positive_count = len(positives)
        negative_count = len(negatives)
        return RagEvalReport(
            total_cases=len(cases),
            positive_cases=positive_count,
            negative_cases=negative_count,
            recall_at_1=(hit_at_1 / positive_count if positive_count else 0),
            recall_at_3=(hit_at_3 / positive_count if positive_count else 0),
            recall_at_5=(hit_at_5 / positive_count if positive_count else 0),
            recall_at_3_ci95=wilson_interval(hit_at_3, positive_count),
            recall_at_5_ci95=wilson_interval(hit_at_5, positive_count),
            mrr=(
                reciprocal_rank_sum / positive_count
                if positive_count
                else 0
            ),
            mrr_at_10=(
                reciprocal_rank_at_10_sum / positive_count
                if positive_count
                else 0
            ),
            source_accuracy=(
                hit_at_1 / positive_count if positive_count else 0
            ),
            irrelevant_rejection_rate=(
                rejected / negative_count if negative_count else 0
            ),
            irrelevant_rejection_rate_ci95=wilson_interval(
                rejected,
                negative_count,
            ),
            failures=failures,
        )
