# MyTicket monitoring runbook

## Start the local demonstration stack

```powershell
Copy-Item .env.compose.example .env
docker compose --profile monitoring up --build
```

Monitoring endpoints and credentials are deployment details. Keep them in the
local `.env`, reverse-proxy configuration, or deployment platform Secret; do
not copy them into public project documentation. Change every demonstration
credential before starting a shared stack.

The API and Worker are separate processes and therefore separate scrape targets:

- `myticket-api` → `backend:8000/metrics`
- `myticket-worker` → `worker:9101/metrics`

The provisioned `MyTicket Overview` dashboard includes Agent ratings and
knowledge-gap detection, approval and rejection outcomes, so the feedback
flywheel can be inspected without ad-hoc PromQL.

The Worker endpoint is exposed only inside the Compose network. If API metric
authentication is enabled, provision the token as a secret and add Prometheus
`authorization.credentials_file`; never commit the token to this directory.

## Initial alert response

| Alert | First checks |
|---|---|
| `MyTicketBackendDown` | API container health, migrations, database and Redis connectivity |
| `MyTicketWorkerMetricsDown` | Worker process, database connectivity and metrics port configuration |
| `MyTicketHighHttp5xxRate` | Recent API errors grouped by route and correlated JSON logs |
| `MyTicketHighHttpP95Latency` | Slow routes, database pool pressure and external model latency |
| `MyTicketWorkerFailureBurst` | Task error logs, retry count and dead tasks |
| `MyTicketWorkerLeaseLost` | Worker saturation, DB latency, lease duration and heartbeat failures |
| `MyTicketHighAgentEscalationRate` | Reviewer issues, policy gaps and model/fallback behavior |
| `MyTicketToolFailureBurst` | Tool name, ownership checks and upstream business service health |
| `MyTicketRagFallbackBurst` | Embedding configuration, provider failures and knowledge coverage |

The thresholds are safe demonstration defaults, not universal production SLOs.
Calibrate them with representative traffic, error budgets and on-call feedback.
Production deployments still need Alertmanager notification routing, durable
Prometheus storage, log aggregation, access control and high availability.
