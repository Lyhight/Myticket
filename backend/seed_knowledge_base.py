import asyncio
import json
from pathlib import Path

from app.kb.service import KnowledgeBaseService
from app.db.session import AsyncSessionLocal
from app.repositories.knowledge_repository import KnowledgeRepository


POLICY_ROOT = Path(__file__).parent.parent / "synthetic_data" / "policies"


def load_documents(root: Path = POLICY_ROOT) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents.append({
            "title": str(payload["title"]),
            "source": str(payload["source"]),
            "content": str(payload["content"]),
        })
    if not documents:
        raise RuntimeError(f"No synthetic policies found in {root}")
    return documents


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        service = KnowledgeBaseService(KnowledgeRepository(db))
        for document in load_documents():
            chunks = await service.ingest(**document)
            print(f"seeded {document['source']}: {chunks} chunk(s)")


if __name__ == "__main__":
    asyncio.run(seed())
