"""Stable failure fingerprints for deduplication and report updates."""

import hashlib
import re

from devops_ci.models import JobEvidence

TIMESTAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}T\S+")
DURATION = re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|m)\b", re.IGNORECASE)
HEX_ID = re.compile(r"\b[0-9a-f]{12,64}\b", re.IGNORECASE)
TEMP_PATH = re.compile(r"(?:/tmp/|/home/runner/work/|/Users/runner/work/)\S+")


def normalize_error(value: str) -> str:
    value = TIMESTAMP.sub("<timestamp>", value)
    value = DURATION.sub("<duration>", value)
    value = HEX_ID.sub("<id>", value)
    value = TEMP_PATH.sub("<temporary-path>", value)
    return " ".join(value.lower().split())


def fingerprint_failure(workflow_name: str, jobs: list[JobEvidence]) -> str:
    signatures = []
    for job in jobs:
        errors = sorted(
            normalize_error(f"{error.file or ''}:{error.line or ''}:{error.message}")
            for error in job.log.errors
        )
        if not errors:
            errors = [normalize_error(job.redacted_log_tail[-1_000:])]
        signatures.append(
            "|".join(
                [job.job.service or job.job.name, job.job.failed_step or "", *errors]
            )
        )
    canonical = workflow_name.lower() + "\n" + "\n".join(sorted(signatures))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
