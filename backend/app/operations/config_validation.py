import json
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path, errors: list[str]) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        errors.append(f"{path}: invalid YAML: {exc}")
        return {}


def _load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        return {}


def validate_project_config(project_root: Path) -> list[str]:
    """Validate cross-file deployment and evaluation configuration invariants."""
    errors: list[str] = []
    compose = _load_yaml(project_root / "docker-compose.yml", errors)
    prometheus = _load_yaml(
        project_root / "monitoring" / "prometheus" / "prometheus.yml",
        errors,
    )
    alerts = _load_yaml(
        project_root / "monitoring" / "prometheus" / "alerts.yml",
        errors,
    )
    datasource = _load_yaml(
        project_root
        / "monitoring"
        / "grafana"
        / "provisioning"
        / "datasources"
        / "prometheus.yml",
        errors,
    )
    dashboard = _load_json(
        project_root
        / "monitoring"
        / "grafana"
        / "dashboards"
        / "myticket-overview.json",
        errors,
    )

    gitignore_path = project_root / ".gitignore"
    try:
        gitignore_lines = {
            line.strip()
            for line in gitignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError as exc:
        errors.append(f"{gitignore_path}: unable to read: {exc}")
        gitignore_lines = set()
    if ".env" not in gitignore_lines:
        errors.append(".gitignore: root .env must be ignored")

    backend_env_example = project_root / "backend" / ".env.example"
    try:
        example_values = dict(
            line.split("=", 1)
            for raw_line in backend_env_example.read_text(
                encoding="utf-8"
            ).splitlines()
            if (line := raw_line.strip())
            and not line.startswith("#")
            and "=" in line
        )
    except OSError as exc:
        errors.append(f"{backend_env_example}: unable to read: {exc}")
        example_values = {}
    for flag in ("LLM_ENABLED", "EMBEDDING_ENABLED"):
        if example_values.get(flag, "").lower() != "false":
            errors.append(f"backend/.env.example: {flag} must default to false")
    if example_values.get("DASHSCOPE_API_KEY"):
        errors.append("backend/.env.example: DASHSCOPE_API_KEY must be empty")

    license_path = project_root / "LICENSE"
    try:
        license_text = license_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{license_path}: unable to read: {exc}")
    else:
        if not license_text.startswith("MIT License"):
            errors.append("LICENSE: expected the MIT License text")
        if "Copyright (c) 2026 Lyhight" not in license_text:
            errors.append("LICENSE: expected the project copyright notice")

    services = compose.get("services", {}) if isinstance(compose, dict) else {}
    required_services = {
        "mysql", "redis", "qdrant", "backend", "worker", "frontend", "prometheus", "grafana"
    }
    missing_services = required_services - set(services)
    if missing_services:
        errors.append(
            "docker-compose.yml: missing services: "
            + ", ".join(sorted(missing_services))
        )

    for service_name in ("prometheus", "grafana"):
        profiles = services.get(service_name, {}).get("profiles", [])
        if "monitoring" not in profiles:
            errors.append(
                f"docker-compose.yml: {service_name} must use the monitoring profile"
            )

    worker_environment = services.get("worker", {}).get("environment", {})
    worker_port = worker_environment.get("AGENT_WORKER_METRICS_PORT")
    jobs = {
        item.get("job_name"): item
        for item in prometheus.get("scrape_configs", [])
        if isinstance(item, dict)
    }
    expected_targets = {
        "myticket-api": "backend:8000",
        "myticket-worker": f"worker:{worker_port}",
    }
    for job_name, expected_target in expected_targets.items():
        static_configs = jobs.get(job_name, {}).get("static_configs", [])
        targets = static_configs[0].get("targets", []) if static_configs else []
        if expected_target not in targets:
            errors.append(
                f"prometheus.yml: {job_name} must scrape {expected_target}"
            )

    rules = []
    for group in alerts.get("groups", []) if isinstance(alerts, dict) else []:
        rules.extend(group.get("rules", []))
    alert_names = [rule.get("alert") for rule in rules]
    if not rules:
        errors.append("alerts.yml: at least one alert rule is required")
    if len(alert_names) != len(set(alert_names)):
        errors.append("alerts.yml: alert names must be unique")
    for rule in rules:
        if not rule.get("expr"):
            errors.append(f"alerts.yml: {rule.get('alert')} has no expression")
        severity = rule.get("labels", {}).get("severity")
        if severity not in {"warning", "critical"}:
            errors.append(
                f"alerts.yml: {rule.get('alert')} has unsupported severity {severity!r}"
            )

    datasources = datasource.get("datasources", []) if isinstance(datasource, dict) else []
    datasource_uids = {item.get("uid") for item in datasources}
    panels = dashboard.get("panels", []) if isinstance(dashboard, dict) else []
    panel_ids = [panel.get("id") for panel in panels]
    if not panels:
        errors.append("Grafana dashboard: at least one panel is required")
    if len(panel_ids) != len(set(panel_ids)):
        errors.append("Grafana dashboard: panel IDs must be unique")
    for panel in panels:
        uid = panel.get("datasource", {}).get("uid")
        if uid not in datasource_uids:
            errors.append(
                f"Grafana panel {panel.get('id')} references unknown datasource {uid!r}"
            )
        if not any(target.get("expr") for target in panel.get("targets", [])):
            errors.append(f"Grafana panel {panel.get('id')} has no PromQL target")

    json_roots = (
        project_root / "backend" / "evals",
        project_root / "benchmark" / "datasets",
        project_root / "benchmark" / "experiments",
        project_root / "benchmark" / "targets",
        project_root / "synthetic_data",
    )
    for root in json_roots:
        for path in root.rglob("*.json"):
            _load_json(path, errors)

    return errors
