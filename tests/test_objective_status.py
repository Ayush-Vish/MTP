import json
from pathlib import Path

from secguard.objective_status import assess_objectives


def test_committed_objective_artifacts_pass_prototype_gate() -> None:
    project_root = Path(__file__).resolve().parents[1]
    report = assess_objectives(project_root)

    assert report["prototype_complete"] is True
    assert report["journal_validation_complete"] is False
    assert [row["objective"] for row in report["objectives"]] == [1, 2, 3]
    assert all(row["prototype_complete"] for row in report["objectives"])


def test_objective_gate_is_json_serializable() -> None:
    project_root = Path(__file__).resolve().parents[1]
    json.dumps(assess_objectives(project_root))
