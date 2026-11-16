"""Best-effort secret redaction. Redaction is defense in depth, not a guarantee."""

import re
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionResult:
    text: str
    count: int


class Redactor:
    def __init__(self, known_secrets: Iterable[str] = ()):
        # Short values produce excessive false positives and are not useful masks.
        self.known_secrets = sorted(
            {value for value in known_secrets if value and len(value) >= 4},
            key=len,
            reverse=True,
        )
        self.patterns = [
            (
                re.compile(
                    r"-----BEGIN [^-]*PRIVATE KEY-----.*?"
                    r"-----END [^-]*PRIVATE KEY-----",
                    re.DOTALL,
                ),
                "[REDACTED_PRIVATE_KEY]",
            ),
            (
                re.compile(
                    r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b"
                ),
                "[REDACTED_GITHUB_TOKEN]",
            ),
            (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY]"),
            (
                re.compile(
                    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
                ),
                "[REDACTED_JWT]",
            ),
            (
                re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]+"),
                lambda match: match.group(1) + "[REDACTED]",
            ),
            (
                re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@/]+)(@)"),
                lambda match: match.group(1) + "[REDACTED]" + match.group(3),
            ),
            (
                re.compile(
                    r"(?i)\b(api[_-]?key|access[_-]?key|secret[_-]?key|token|"
                    r"password|passwd|authorization|cookie)(\s*[:=]\s*)"
                    r"([\"']?)([^\s,\"';]+)"
                ),
                lambda match: (
                    match.group(1)
                    + match.group(2)
                    + match.group(3)
                    + "[REDACTED]"
                    + match.group(3)
                ),
            ),
        ]

    def redact(self, text: str) -> RedactionResult:
        redacted = text
        count = 0

        for secret in self.known_secrets:
            occurrences = redacted.count(secret)
            if occurrences:
                redacted = redacted.replace(secret, "[REDACTED_KNOWN_SECRET]")
                count += occurrences

        for pattern, replacement in self.patterns:
            redacted, substitutions = pattern.subn(replacement, redacted)
            count += substitutions

        return RedactionResult(text=redacted, count=count)
