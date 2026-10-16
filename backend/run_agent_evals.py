import asyncio
import json
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("JWT_SECRET", "eval-only-secret-not-for-production-use")

from app.evals.runner import AgentEvalRunner


async def main() -> None:
    dataset = Path(__file__).parent / "evals" / "agent_cases.json"
    report = await AgentEvalRunner().run_file(dataset)
    print(
        json.dumps(
            report.summary(),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
