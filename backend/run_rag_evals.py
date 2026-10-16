import argparse
import asyncio
import json
from pathlib import Path

from app.agent.rag import (
    HybridKnowledgeRetriever,
    KeywordKnowledgeRetriever,
)
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.evals.rag_runner import RagEvalRunner
from app.repositories.knowledge_repository import KnowledgeRepository


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Use external embedding service for hybrid retrieval.",
    )
    args = parser.parse_args()
    if args.hybrid and not settings.embedding_enabled:
        parser.error(
            "--hybrid requires EMBEDDING_ENABLED=true and a valid "
            "DASHSCOPE_API_KEY"
        )
    dataset = Path(__file__).parent / "evals" / "rag_cases.json"

    async with AsyncSessionLocal() as db:
        repository = KnowledgeRepository(db)
        retriever = (
            HybridKnowledgeRetriever(repository)
            if args.hybrid
            else KeywordKnowledgeRetriever(repository)
        )
        report = await RagEvalRunner(retriever).run_file(dataset)
        print(
            json.dumps(
                report.summary(),
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
