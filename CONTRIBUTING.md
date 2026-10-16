# Contributing to MyTicket

## Development setup

1. Create a Python 3.12 virtual environment under `backend/.venv`.
2. Install the backend with `python -m pip install -e ".[dev]"` from `backend`.
3. Copy `backend/.env.example` to `backend/.env` and keep the offline defaults
   unless you have configured a valid model provider key.
4. Install frontend dependencies with `npm ci` from `frontend`.

Never commit `.env` files, API keys, access tokens, production data, virtual
environments, `node_modules`, generated reports, or build output.

## Required checks

From the project root on Windows PowerShell:

```powershell
.\scripts\verify_release.ps1
```

Or run the main checks separately:

```powershell
cd backend
python -m pytest -q
python validate_project_config.py
python run_benchmark.py --skip-rag
python run_quality_gate.py --skip-rag

cd ..\frontend
npm run build
```

The offline benchmark is a deterministic regression check. Do not describe it
as real-model or production accuracy. Database RAG changes should also be
validated by the MySQL integration workflow.

## Pull requests

- Keep changes focused and explain the business reason.
- Add or update tests for behavior changes.
- Preserve authorization, confirmation, and idempotency checks around tools.
- Update evaluation datasets when introducing a new supported scenario.
- Document migrations and configuration changes.
- Do not weaken a quality gate merely to make a regression pass.
