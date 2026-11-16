"""Typed contracts for evidence, investigation state, and publication."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LogFormat(str, Enum):
    AUTO = "auto"
    GO = "go"
    JEST = "jest"
    PYTEST = "pytest"
    GENERIC = "generic"


class FailureCategory(str, Enum):
    APPLICATION_CODE = "application_code"
    TEST_FAILURE = "test_failure"
    FLAKY_TEST = "flaky_test"
    DEPENDENCY_BUILD = "dependency_build"
    DOCKER_BUILD = "docker_build"
    SECURITY_FINDING = "security_finding"
    TERRAFORM_PROVIDER = "terraform_provider"
    INFRASTRUCTURE_NETWORK = "infrastructure_network"
    CI_CONFIGURATION = "ci_configuration"
    UNKNOWN = "unknown"


class ErrorCandidate(ContractModel):
    message: str = Field(min_length=1)
    kind: Literal["compile", "test", "dependency", "network", "generic"] = "generic"
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    test_name: str | None = None
    excerpt: str = Field(min_length=1)


class LogEvidence(ContractModel):
    format: LogFormat
    errors: list[ErrorCandidate]
    original_characters: int = Field(ge=0)
    processed_characters: int = Field(ge=0)
    redaction_count: int = Field(ge=0)
    truncated: bool


class Evidence(ContractModel):
    type: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    file: str | None = None
    line: int | None = Field(default=None, ge=1)


class Investigation(ContractModel):
    category: FailureCategory
    service: str | None = None
    summary: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    suspected_files: list[str] = Field(default_factory=list)
    reproduction_command: str | None = None
    recommended_action: str = Field(min_length=1)
    insufficient_evidence: bool


class RunContext(ContractModel):
    repository: str
    run_id: int = Field(gt=0)
    run_attempt: int = Field(ge=1)
    workflow_name: str
    conclusion: str
    head_sha: str
    head_branch: str | None = None
    html_url: str | None = None
    pull_request: int | None = Field(default=None, gt=0)


class FailedJob(ContractModel):
    job_id: int = Field(gt=0)
    name: str
    service: str | None = None
    failed_step: str | None = None


class JobEvidence(ContractModel):
    job: FailedJob
    log: LogEvidence
    redacted_log_tail: str = Field(max_length=20_000)


class EvidenceBundle(ContractModel):
    context: RunContext
    changed_files: list[str] = Field(default_factory=list)
    jobs: list[JobEvidence]
    fingerprint: str = Field(min_length=64, max_length=64)


class RoutingDecision(ContractModel):
    route: Literal["deterministic", "deepseek"]
    reason: str


class ToolTraceEntry(ContractModel):
    tool: str
    arguments: dict[str, str | int]
    outcome: Literal["success", "error"]
    returned_characters: int = Field(ge=0)
    detail: str | None = None


class InvestigationMetadata(ContractModel):
    repository: str
    run_id: int
    run_attempt: int
    head_sha: str
    pull_request: int | None = None
    workflow_name: str
    workflow_url: str | None = None
    fingerprint: str
    analysis_mode: Literal["deterministic", "deepseek", "deterministic_fallback"]
    routing_reason: str
    model: str | None = None
    deepseek_calls: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    provider_error: str | None = None


class InvestigationEnvelope(ContractModel):
    metadata: InvestigationMetadata
    investigation: Investigation
    tool_trace: list[ToolTraceEntry] = Field(default_factory=list)


class PublishReceipt(ContractModel):
    destination: Literal["pull_request", "issue", "summary"]
    identifier: int | None = None
    url: str | None = None
    updated: bool = False


class FixtureExpectation(ContractModel):
    format: LogFormat
    error_substrings: list[str] = Field(default_factory=list)
    expected_file: str | None = None
    min_errors: int = Field(default=1, ge=0)


class FixtureEvaluation(ContractModel):
    name: str
    passed: bool
    detected_format: LogFormat
    error_count: int
    failures: list[str] = Field(default_factory=list)


class EvaluationReport(ContractModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    accuracy: float = Field(ge=0, le=1)
    results: list[FixtureEvaluation]
