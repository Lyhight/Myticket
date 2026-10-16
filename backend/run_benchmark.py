import argparse
import asyncio
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

# Offline rule evaluation must not require a developer's production .env file.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault(
    "JWT_SECRET",
    "benchmark-only-secret-not-for-production-use",
)

from app.agent.versioning import EVAL_DATASET_VERSION, PROMPT_VERSIONS
from app.evals.reporting import write_report_bundle
from app.evals.runner import AgentEvalRunner
from app.evals.safety_runner import SafetyEvalRunner
from app.evals.task_runner import AgentTaskEvalRunner, OfflineWorkflowTaskExecutor
from app.core.config import settings


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MyTicket benchmark suite")
    parser.add_argument("--skip-rag", action="store_true")
    parser.add_argument("--hybrid", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.hybrid and not settings.embedding_enabled:
        parser.error(
            "--hybrid requires EMBEDDING_ENABLED=true and a valid "
            "DASHSCOPE_API_KEY"
        )

    backend_root = Path(__file__).parent
    project_root = backend_root.parent
    dataset_root = project_root / "benchmark" / "datasets"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output or (
        project_root / "benchmark" / "reports" / "runs" / run_id
    )
    component_dataset = backend_root / "evals" / "agent_cases.json"
    task_dataset = dataset_root / "agent_tasks.json"
    safety_dataset = dataset_root / "safety_cases.json"
    workflow_dataset = dataset_root / "workflow_smoke.json"
    rag_dataset = backend_root / "evals" / "rag_cases.json"

    component_report = await AgentEvalRunner().run_file(
        component_dataset
    )
    task_report = await AgentTaskEvalRunner().run_file(
        task_dataset
    )
    safety_report = await SafetyEvalRunner().run_file(
        safety_dataset
    )
    workflow_report = await AgentTaskEvalRunner(
        OfflineWorkflowTaskExecutor(),
        evaluation_mode="offline_agent_workflow_with_fake_tools",
    ).run_file(workflow_dataset)
    reports = {
        "agent_components": component_report.summary(),
        "agent_tasks": task_report.summary(),
        "safety": safety_report.summary(),
        "agent_workflow_smoke": workflow_report.summary(),
    }

    if not args.skip_rag:
        from app.agent.rag import (
            HybridKnowledgeRetriever,
            KeywordKnowledgeRetriever,
        )
        from app.db.session import AsyncSessionLocal
        from app.evals.rag_runner import RagEvalRunner
        from app.repositories.knowledge_repository import KnowledgeRepository

        async with AsyncSessionLocal() as db:
            repository = KnowledgeRepository(db)
            retriever = (
                HybridKnowledgeRetriever(repository)
                if args.hybrid
                else KeywordKnowledgeRetriever(repository)
            )
            rag_report = await RagEvalRunner(
                retriever,
                max_rank=settings.rag_candidate_k,
            ).run_file(
                rag_dataset
            )
            reports["rag"] = rag_report.summary()

    dataset_paths = [
        component_dataset,
        task_dataset,
        safety_dataset,
        workflow_dataset,
    ]
    if not args.skip_rag:
        dataset_paths.append(rag_dataset)

    paths = write_report_bundle(
        reports,
        output_dir,
        metadata={
            "run_id": run_id,
            "dataset_version": EVAL_DATASET_VERSION,
            "prompt_versions": PROMPT_VERSIONS,
            "evaluation_scope": (
                "offline_components_tasks_safety"
                if args.skip_rag
                else "offline_components_tasks_safety_rag"
            ),
            "rag_included": not args.skip_rag,
            "retriever": (
                None
                if args.skip_rag
                else ("hybrid" if args.hybrid else "keyword")
            ),
            "rag_runtime_top_k": settings.rag_top_k,
            "rag_evaluation_depth": settings.rag_candidate_k,
            "embedding_model": (
                settings.embedding_model if args.hybrid else None
            ),
            "embedding_dimensions": (
                settings.embedding_dimensions if args.hybrid else None
            ),
            "dataset_sha256": {
                str(path.relative_to(project_root)): file_sha256(path)
                for path in dataset_paths
            },
        },
    )
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
