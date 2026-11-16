"""Pytest/Poetry failure extraction."""

import re

from devops_ci.models import ErrorCandidate
from devops_ci.parsers.common import clean_excerpt, deduplicate

FAILED = re.compile(
    r"^FAILED\s+(?P<file>[^\s:]+\.py)::(?P<test>[^\s]+)"
    r"(?:\s+-\s+(?P<message>.+))?$",
    re.MULTILINE,
)
ERROR_LINE = re.compile(r"^E\s+(?P<message>.+)$", re.MULTILINE)
LOCATION = re.compile(r"(?P<file>[^\s:]+\.py):(?P<line>\d+)(?::|\s)")


def parse_pytest(text: str) -> list[ErrorCandidate]:
    errors = []
    for match in FAILED.finditer(text):
        test_name = match.group("test")
        detail = match.group("message")
        errors.append(
            ErrorCandidate(
                message=detail.strip()
                if detail
                else f"Pytest test failed: {test_name}",
                kind="dependency"
                if detail and "ModuleNotFoundError" in detail
                else "test",
                file=match.group("file"),
                test_name=test_name,
                excerpt=clean_excerpt(match.group(0)),
            )
        )

    # Collection/import failures often have no FAILED summary line.
    if not errors:
        location = LOCATION.search(text)
        for match in ERROR_LINE.finditer(text):
            message = match.group("message").strip()
            errors.append(
                ErrorCandidate(
                    message=message,
                    kind="dependency" if "ModuleNotFoundError" in message else "test",
                    file=location.group("file") if location else None,
                    line=int(location.group("line")) if location else None,
                    excerpt=clean_excerpt(match.group(0)),
                )
            )

    return deduplicate(errors)
