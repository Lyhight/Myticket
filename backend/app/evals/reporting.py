import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _metric_rows(section: str, value: Any, prefix: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "failures":
                continue
            path = f"{prefix}.{key}" if prefix else key
            rows.extend(_metric_rows(section, child, path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            rows.extend(_metric_rows(section, child, f"{prefix}[{index}]"))
    elif isinstance(value, (str, int, float, bool)):
        rows.append({"section": section, "metric": prefix, "value": value})
    return rows


def write_report_bundle(
    reports: dict[str, dict[str, Any]],
    output_dir: Path,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Export machine-readable JSON, spreadsheet-friendly CSV and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "reports": reports,
    }
    json_path = output_dir / "benchmark-report.json"
    csv_path = output_dir / "benchmark-metrics.csv"
    markdown_path = output_dir / "benchmark-report.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rows = [
        row
        for section, report in reports.items()
        for row in _metric_rows(section, report)
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["section", "metric", "value"])
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# MyTicket Benchmark Report", ""]
    if metadata:
        lines.extend(["## Run metadata", "", "```json"])
        lines.append(json.dumps(metadata, ensure_ascii=False, indent=2))
        lines.extend(["```", ""])
    for section, report in reports.items():
        lines.extend([f"## {section}", "", "| Metric | Value |", "|---|---:|"])
        for row in _metric_rows(section, report):
            lines.append(f"| {row['metric']} | {row['value']} |")
        failures = report.get("failures", [])
        lines.extend(["", f"Failures: {len(failures)}", ""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "markdown": markdown_path}
