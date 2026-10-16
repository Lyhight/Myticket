import asyncio
import logging

from prometheus_client import start_http_server

from app.core.config import settings
from app.core.logging import configure_logging
from app.workers.agent_worker import AgentWorker


if __name__ == "__main__":
    configure_logging()
    if settings.agent_worker_metrics_port:
        start_http_server(settings.agent_worker_metrics_port)
        logging.getLogger(__name__).info(
            "agent_worker_metrics_started port=%s",
            settings.agent_worker_metrics_port,
        )
    try:
        asyncio.run(AgentWorker().run_forever())
    except KeyboardInterrupt:
        pass
