import json
from pathlib import Path

import httpx
import pytest
import yaml
from devops_ci.deepseek import DeepSeekClient, DeepSeekConfig
from devops_ci.evidence_validation import (
    EvidenceValidationError,
    validate_investigation,
)
from devops_ci.fingerprint import normalize_error
from devops_ci.github import GitHubClient, GitHubConfig
from devops_ci.models import (
    ErrorCandidate,
    Evidence,
    EvidenceBundle,
    FailedJob,
    Investigation,
    JobEvidence,
    LogEvidence,
    RunContext,
)
from devops_ci.policy import AgentPolicy
from devops_ci.tools import ReadOnlyTools


def test_error_normalization_removes_unstable_values():
    value = "2026-09-09T10:00:00Z /tmp/runner-abcdef1234567890 failed in 2.5s"
    normalized = normalize_error(value)
    assert "2026-09-09" not in normalized
    assert "2.5s" not in normalized
    assert "<timestamp>" in normalized
    assert "<duration>" in normalized


def test_repository_file_rejects_path_traversal_without_network():
    client = GitHubClient(GitHubConfig(repository="acme/capstone", token="secret"))
    with pytest.raises(Exception, match="Unsafe repository file path"):
        client.read_repository_file("../.env", "abc1234", 1000)


def test_repository_tool_rejects_unrelated_sensitive_file():
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Unrelated files must not reach the GitHub API")

    github = GitHubClient(
        GitHubConfig(repository="acme/capstone", token="secret"),
        transport=httpx.MockTransport(forbidden),
    )
    tools = ReadOnlyTools(github, _bundle(), AgentPolicy())
    result = tools.execute(
        "read_repository_file",
        json.dumps({"path": ".env", "ref": "abc1234"}),
    )
    assert "not changed or referenced" in result
    assert tools.trace[0].outcome == "error"


def test_deepseek_retries_retryable_response():
    calls = []
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"status":"ok"}'}}]}
        )

    client = DeepSeekClient(
        DeepSeekConfig(api_key="test-key", max_retries=1),
        transport=httpx.MockTransport(handler),
        sleeper=sleeps.append,
    )
    assert client.smoke_test() == {"status": "ok"}
    assert len(calls) == 2
    assert len(sleeps) == 1


def _bundle():
    context = RunContext(
        repository="acme/capstone",
        run_id=1,
        run_attempt=1,
        workflow_name="Run Tests",
        conclusion="failure",
        head_sha="abc1234",
        pull_request=42,
    )
    job = FailedJob(
        job_id=1, name="test (services/go/api-golang)", service="services/go/api-golang"
    )
    evidence = JobEvidence(
        job=job,
        log=LogEvidence(
            format="go",
            errors=[
                ErrorCandidate(
                    message="undefined: UserResponse", excerpt="undefined: UserResponse"
                )
            ],
            original_characters=24,
            processed_characters=24,
            redaction_count=0,
            truncated=False,
        ),
        redacted_log_tail="undefined: UserResponse",
    )
    return EvidenceBundle(
        context=context, changed_files=[], jobs=[evidence], fingerprint="a" * 64
    )


def test_evidence_validator_rejects_fabricated_excerpt():
    report = Investigation(
        category="application_code",
        service="services/go/api-golang",
        summary="Fabricated",
        confidence=0.9,
        evidence=[Evidence(type="claim", excerpt="not present in any collected log")],
        recommended_action="Check",
        insufficient_evidence=False,
    )
    with pytest.raises(EvidenceValidationError, match="not found"):
        validate_investigation(report, _bundle(), {})


def test_github_only_validation_is_opt_in_and_changes_no_source():
    path = Path(__file__).parents[3] / ".github/workflows/test.yaml"
    data = yaml.safe_load(path.read_text())
    trigger = data[True]
    option = trigger["workflow_dispatch"]["inputs"]["simulate_agent_failure"]
    assert option["default"] is False
    job = data["jobs"]["agent-validation-failure"]
    assert "workflow_dispatch" in job["if"]
    assert "inputs.simulate_agent_failure" in job["if"]
    assert "uses" not in job["steps"][0]
    assert "exit 1" in job["steps"][0]["run"]


def test_new_workflow_is_event_driven_and_sha_pinned():
    path = Path(__file__).parents[3] / ".github/workflows/agent-investigate.yaml"
    raw = path.read_text()
    data = yaml.safe_load(raw)
    trigger = data[True]  # PyYAML uses YAML 1.1, where the key `on` is a boolean.
    assert trigger["workflow_run"]["workflows"] == ["Run Tests"]
    assert trigger["workflow_run"]["types"] == ["completed"]
    assert "pull_request_target" not in raw
    assert raw.count("secrets.GHA_CAPSTONE_PERSONAL_ACCESS_TOKEN") == 2
    assert "secrets.DEEPSEEK_API_KEY" in raw
    assert "secrets.GITHUB_TOKEN" not in raw
    for line in raw.splitlines():
        if "uses:" in line:
            assert len(line.split("@", 1)[1].split()[0]) == 40
