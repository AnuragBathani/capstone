"""Bounded, redacted log preprocessing for LLM evidence bundles."""

from dataclasses import dataclass

from devops_ci.models import LogEvidence, LogFormat
from devops_ci.parsers import parse_errors
from devops_ci.redaction import Redactor

TRUNCATION_MARKER = "\n[... MIDDLE OF LOG TRUNCATED ...]\n"


@dataclass(frozen=True)
class PreparedLog:
    evidence: LogEvidence
    redacted_text: str


def truncate_log(text: str, maximum: int) -> tuple[str, bool]:
    if len(text) <= maximum:
        return text, False
    if maximum <= len(TRUNCATION_MARKER) + 2:
        raise ValueError("maximum log size is too small")

    available = maximum - len(TRUNCATION_MARKER)
    head_size = (available * 7) // 10
    tail_size = available - head_size
    return text[:head_size] + TRUNCATION_MARKER + text[-tail_size:], True


def prepare_log(
    text: str,
    log_format: LogFormat = LogFormat.AUTO,
    max_characters: int = 200_000,
    known_secrets: tuple[str, ...] = (),
) -> PreparedLog:
    bounded, truncated = truncate_log(text, max_characters)
    redaction = Redactor(known_secrets).redact(bounded)
    detected, errors = parse_errors(redaction.text, log_format)
    evidence = LogEvidence(
        format=detected,
        errors=errors,
        original_characters=len(text),
        processed_characters=len(redaction.text),
        redaction_count=redaction.count,
        truncated=truncated,
    )
    return PreparedLog(evidence=evidence, redacted_text=redaction.text)


def preprocess_log(
    text: str,
    log_format: LogFormat = LogFormat.AUTO,
    max_characters: int = 200_000,
    known_secrets: tuple[str, ...] = (),
) -> LogEvidence:
    return prepare_log(text, log_format, max_characters, known_secrets).evidence
