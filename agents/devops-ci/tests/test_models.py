from pathlib import Path

import pytest
from devops_ci.models import FailureCategory, Investigation
from pydantic import ValidationError


def test_example_investigation_matches_contract():
    example = Path(__file__).parents[1] / "examples/go-investigation.json"
    report = Investigation.model_validate_json(example.read_text(encoding="utf-8"))
    assert report.category == FailureCategory.APPLICATION_CODE
    assert report.confidence == 0.93


def test_investigation_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        Investigation(
            category="unknown",
            summary="Insufficient evidence",
            confidence=1.5,
            recommended_action="Inspect the complete log",
            insufficient_evidence=True,
        )
