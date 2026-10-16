FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/run_agent_worker.py backend/seed_demo_data.py backend/seed_knowledge_base.py ./
COPY synthetic_data /synthetic_data

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
