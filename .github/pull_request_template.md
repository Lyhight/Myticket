## Summary

Describe the user or operational problem and the chosen solution.

## Validation

- [ ] Backend tests pass
- [ ] Frontend build passes, if affected
- [ ] Project configuration validation passes
- [ ] Offline quality gate passes
- [ ] MySQL/RAG integration was run, if affected

## Safety and operations

- [ ] No secret, `.env`, real customer data, or generated report is included
- [ ] Authorization and tenant ownership remain enforced
- [ ] High-risk tool calls still require confirmation or trusted human approval
- [ ] Write operations remain idempotent
- [ ] Migrations, metrics, alerts, and documentation were updated where needed

## Evaluation boundary

State whether the evidence is an offline rule regression, fake-tool workflow
test, database integration result, or real-model evaluation.
