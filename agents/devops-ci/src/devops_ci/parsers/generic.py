"""Conservative fallback extraction for unknown log formats."""

import re

from devops_ci.models import ErrorCandidate
from devops_ci.parsers.common import clean_excerpt, deduplicate

GENERIC_ERROR = re.compile(
    r"^\s*(?:\d{4}-\d{2}-\d{2}T\S+\s+)?"
    r"(?P<message>(?:Error|ERROR|Fatal|FATAL|Timeout|Timed out)\b.*)$",
    re.MULTILINE,
)
EXIT_CODE = re.compile(r"^\s*.*Process completed with exit code\s+\d+.*$", re.MULTILINE)


def parse_generic(text: str) -> list[ErrorCandidate]:
    errors = []
    for match in GENERIC_ERROR.finditer(text):
        message = match.group("message").strip()
        lowered = message.lower()
        errors.append(
            ErrorCandidate(
                message=message,
                kind="network"
                if any(word in lowered for word in ("timeout", "timed out", "network"))
                else "generic",
                excerpt=clean_excerpt(match.group(0)),
            )
        )

    if not errors:
        match = EXIT_CODE.search(text)
        if match:
            message = clean_excerpt(match.group(0))
            errors.append(ErrorCandidate(message=message, excerpt=message))

    return deduplicate(errors[:10])
