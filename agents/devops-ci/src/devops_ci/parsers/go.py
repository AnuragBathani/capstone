"""Go compiler and go test log extraction."""

import re

from devops_ci.models import ErrorCandidate
from devops_ci.parsers.common import clean_excerpt, deduplicate

GO_ERROR = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}T\S+\s+)?"
    r"(?P<file>[^\s:]+\.go):(?P<line>\d+):(?P<column>\d+):\s*"
    r"(?P<message>.+)$",
    re.MULTILINE,
)
GO_TEST_FAILURE = re.compile(r"^\s*--- FAIL:\s+(?P<name>\S+)", re.MULTILINE)
GO_PANIC = re.compile(r"^\s*panic:\s*(?P<message>.+)$", re.MULTILINE)


def parse_go(text: str) -> list[ErrorCandidate]:
    errors = []
    for match in GO_ERROR.finditer(text):
        message = match.group("message").strip()
        errors.append(
            ErrorCandidate(
                message=message,
                kind="dependency" if "module" in message.lower() else "compile",
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("column")),
                excerpt=clean_excerpt(match.group(0)),
            )
        )

    for match in GO_TEST_FAILURE.finditer(text):
        name = match.group("name")
        errors.append(
            ErrorCandidate(
                message=f"Go test failed: {name}",
                kind="test",
                test_name=name,
                excerpt=clean_excerpt(match.group(0)),
            )
        )

    if not errors:
        panic = GO_PANIC.search(text)
        if panic:
            errors.append(
                ErrorCandidate(
                    message=f"Go panic: {panic.group('message').strip()}",
                    excerpt=clean_excerpt(panic.group(0)),
                )
            )

    return deduplicate(errors)
