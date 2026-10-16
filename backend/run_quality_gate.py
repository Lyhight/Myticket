import argparse
import asyncio
import json
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("JWT_SECRET", "eval-only-secret-not-for-production-use")

from app.agent.rag import KeywordKnowledgeRetriever
from app.db.session import AsyncSessionLocal
from app.evals.gate import QualityGate
from app.evals.rag_runner import RagEvalRunner
from app.evals.runner import AgentEvalRunner
from app.evals.safety_runner import SafetyEvalRunner
from app.evals.task_runner import AgentTaskEvalRunner, OfflineWorkflowTaskExecutor
from app.repositories.knowledge_repository import KnowledgeRepository


async def main() -> int:
    root = Path(__file__).parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-rag", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    agent_report = await AgentEvalRunner().run_file(
        root / "evals" / "agent_cases.json"
    )
    dataset_root = root.parent / "benchmark" / "datasets"
    task_report = await AgentTaskEvalRunner().run_file(
        dataset_root / "agent_tasks.json"
    )
    safety_report = await SafetyEvalRunner().run_file(
        dataset_root / "safety_cases.json"
    )
    workflow_report = await AgentTaskEvalRunner(
        OfflineWorkflowTaskExecutor(),
        evaluation_mode="offline_agent_workflow_with_fake_tools",
    ).run_file(dataset_root / "workflow_smoke.json")
    rag_summary = None
    if not args.skip_rag:
        async with AsyncSessionLocal() as db:
            retriever = KeywordKnowledgeRetriever(KnowledgeRepository(db))
            rag_report = await RagEvalRunner(retriever).run_file(
                root / "evals" / "rag_cases.json"
            )
            rag_summary = rag_report.summary()

    gate = QualityGate.from_file(
        root / "evals" / "quality_baseline.json"
    )
    if args.skip_rag:
        gate.thresholds.rag_metrics = {}
    report = gate.evaluate(
        agent=agent_report.summary(),
        rag=rag_summary,
        tasks=task_report.summary(),
        workflow=workflow_report.summary(),
        safety=safety_report.summary(),
    )
    output = json.dumps(report.model_dump(), ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
