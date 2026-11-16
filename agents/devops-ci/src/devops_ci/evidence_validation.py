"""Reject unsupported model claims before anything is published."""

import json
from pathlib import PurePosixPath

from devops_ci.models import EvidenceBundle, Investigation


class EvidenceValidationError(ValueError):
    pass


def _normalized(path: str) -> str:
    value = str(PurePosixPath(path)).removeprefix("./")
    return value


def _known_file(path: str, known_files: set[str]) -> bool:
    normalized = _normalized(path)
    return any(
        normalized == known or known.endswith("/" + normalized) for known in known_files
    )


def validate_investigation(
    report: Investigation,
    bundle: EvidenceBundle,
    observations: dict[str, str],
) -> Investigation:
    known_files = set(bundle.changed_files)
    known_files.update(
        error.file for job in bundle.jobs for error in job.log.errors if error.file
    )
    known_files.update(
        key.removeprefix("file:").split(":", 1)[0]
        for key in observations
        if key.startswith("file:")
    )

    for path in report.suspected_files:
        if not _known_file(path, known_files):
            raise EvidenceValidationError(f"Unsupported file claim: {path}")

    searchable = "\n".join(
        [job.redacted_log_tail for job in bundle.jobs]
        + [json.dumps(value, sort_keys=True) for value in observations.values()]
        + [error.excerpt for job in bundle.jobs for error in job.log.errors]
    )
    for item in report.evidence:
        if item.excerpt.strip() not in searchable:
            raise EvidenceValidationError(
                f"Evidence excerpt was not found in collected data: {item.excerpt[:120]}"
            )
        if item.file and not _known_file(item.file, known_files):
            raise EvidenceValidationError(f"Unsupported evidence file: {item.file}")

    known_services = {job.job.service for job in bundle.jobs if job.job.service}
    if report.service and report.service not in known_services:
        raise EvidenceValidationError(f"Unsupported service claim: {report.service}")
    if (
        report.confidence > 0.5
        and not report.evidence
        and not report.insufficient_evidence
    ):
        raise EvidenceValidationError(
            "Confident diagnosis contains no supporting evidence"
        )
    return report
