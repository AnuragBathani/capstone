"""Deterministic log format detection and error extraction."""

import re

from devops_ci.models import ErrorCandidate, LogFormat
from devops_ci.parsers.generic import parse_generic
from devops_ci.parsers.go import GO_ERROR, parse_go
from devops_ci.parsers.jest import parse_jest
from devops_ci.parsers.pytest import parse_pytest


def detect_format(text: str) -> LogFormat:
    if GO_ERROR.search(text) or re.search(r"^\s*--- FAIL:\s+\S+", text, re.MULTILINE):
        return LogFormat.GO
    if re.search(
        r"(?:^FAILED\s+\S+\.py::|^E\s+|={3,}\s*FAILURES\s*={3,})",
        text,
        re.MULTILINE,
    ):
        return LogFormat.PYTEST
    if re.search(r"(?:^\s*FAIL\s+\S+|^\s*●\s+|Cannot find module)", text, re.MULTILINE):
        return LogFormat.JEST
    return LogFormat.GENERIC


def parse_errors(
    text: str, log_format: LogFormat = LogFormat.AUTO
) -> tuple[LogFormat, list[ErrorCandidate]]:
    detected = detect_format(text) if log_format == LogFormat.AUTO else log_format
    parsers = {
        LogFormat.GO: parse_go,
        LogFormat.JEST: parse_jest,
        LogFormat.PYTEST: parse_pytest,
        LogFormat.GENERIC: parse_generic,
    }
    if detected == LogFormat.AUTO:  # Defensive: AUTO is resolved above.
        detected = LogFormat.GENERIC
    return detected, parsers[detected](text)
