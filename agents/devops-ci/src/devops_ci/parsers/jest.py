"""Jest/npm failure extraction."""

import re

from devops_ci.models import ErrorCandidate
from devops_ci.parsers.common import clean_excerpt, deduplicate

TEST_FILE = re.compile(r"^\s*FAIL\s+(?P<file>\S+)", re.MULTILINE)
HEADING = re.compile(r"^\s*●\s+(?P<heading>.+)$", re.MULTILINE)
MODULE_MISSING = re.compile(r"^\s*Cannot find module\s+.+$", re.MULTILINE)
LOCATION = re.compile(
    r"(?P<file>[^\s():]+\.(?:js|jsx|ts|tsx)):(?P<line>\d+):(?P<column>\d+)"
)
EXPECTED = re.compile(r"^\s*Expected:\s*(?P<value>.+)$", re.MULTILINE)
RECEIVED = re.compile(r"^\s*Received:\s*(?P<value>.+)$", re.MULTILINE)


def parse_jest(text: str) -> list[ErrorCandidate]:
    errors = []
    file_match = TEST_FILE.search(text)
    test_file = file_match.group("file") if file_match else None
    location = LOCATION.search(text)

    for match in MODULE_MISSING.finditer(text):
        message = match.group(0).strip()
        errors.append(
            ErrorCandidate(
                message=message,
                kind="dependency",
                file=test_file,
                line=int(location.group("line")) if location else None,
                column=int(location.group("column")) if location else None,
                excerpt=clean_excerpt(message),
            )
        )

    if not errors:
        headings = [m.group("heading").strip() for m in HEADING.finditer(text)]
        expected = EXPECTED.search(text)
        received = RECEIVED.search(text)
        details = []
        if expected:
            details.append(f"Expected: {expected.group('value').strip()}")
        if received:
            details.append(f"Received: {received.group('value').strip()}")

        for heading in headings:
            message = f"Jest failure: {heading}"
            if details:
                message += " — " + "; ".join(details)
            errors.append(
                ErrorCandidate(
                    message=message,
                    kind="test",
                    file=test_file or (location.group("file") if location else None),
                    line=int(location.group("line")) if location else None,
                    column=int(location.group("column")) if location else None,
                    test_name=None
                    if heading == "Test suite failed to run"
                    else heading,
                    excerpt=clean_excerpt(" | ".join([heading, *details])),
                )
            )

    return deduplicate(errors)
