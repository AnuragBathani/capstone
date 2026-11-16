"""Offline parser evaluation against labeled failure fixtures."""

from pathlib import Path

from devops_ci.models import (
    EvaluationReport,
    FixtureEvaluation,
    FixtureExpectation,
    LogFormat,
)
from devops_ci.preprocessing import preprocess_log


def evaluate_fixture(directory: Path) -> FixtureEvaluation:
    log_path = directory / "logs.txt"
    expectation_path = directory / "expected.json"
    expectation = FixtureExpectation.model_validate_json(
        expectation_path.read_text(encoding="utf-8")
    )
    evidence = preprocess_log(log_path.read_text(encoding="utf-8"), LogFormat.AUTO)
    failures = []

    if evidence.format != expectation.format:
        failures.append(
            f"format: expected {expectation.format.value}, got {evidence.format.value}"
        )
    if len(evidence.errors) < expectation.min_errors:
        failures.append(
            f"errors: expected at least {expectation.min_errors}, got {len(evidence.errors)}"
        )

    searchable = "\n".join(
        f"{error.message}\n{error.excerpt}" for error in evidence.errors
    ).lower()
    for substring in expectation.error_substrings:
        if substring.lower() not in searchable:
            failures.append(f"missing error text: {substring}")

    if expectation.expected_file and not any(
        error.file == expectation.expected_file for error in evidence.errors
    ):
        failures.append(f"missing file: {expectation.expected_file}")

    return FixtureEvaluation(
        name=directory.name,
        passed=not failures,
        detected_format=evidence.format,
        error_count=len(evidence.errors),
        failures=failures,
    )


def evaluate_fixtures(fixtures_path: str | Path) -> EvaluationReport:
    root = Path(fixtures_path)
    if not root.is_dir():
        raise ValueError(f"Fixture directory does not exist: {root}")

    directories = sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "expected.json").is_file()
    )
    if not directories:
        raise ValueError(f"No labeled fixtures found in {root}")

    results = [evaluate_fixture(directory) for directory in directories]
    passed = sum(result.passed for result in results)
    total = len(results)
    return EvaluationReport(
        total=total,
        passed=passed,
        failed=total - passed,
        accuracy=passed / total,
        results=results,
    )
