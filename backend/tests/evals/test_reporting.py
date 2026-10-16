import csv
import json

from app.evals.reporting import write_report_bundle


def test_report_bundle_exports_json_csv_and_markdown(tmp_path) -> None:
    paths = write_report_bundle(
        {"rag": {"recall_at_5": 0.8, "failures": []}},
        tmp_path,
        metadata={"experiment": "keyword"},
    )

    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["metadata"]["experiment"] == "keyword"
    with paths["csv"].open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{"section": "rag", "metric": "recall_at_5", "value": "0.8"}]
    assert "Recall" not in paths["markdown"].read_text(encoding="utf-8")
