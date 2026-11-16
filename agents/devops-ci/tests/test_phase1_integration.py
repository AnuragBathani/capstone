import json

import httpx
from devops_ci.deepseek import DeepSeekClient, DeepSeekConfig
from devops_ci.github import GitHubClient, GitHubConfig
from devops_ci.orchestrator import investigate_run
from devops_ci.policy import AgentPolicy
from devops_ci.publisher import publish_investigation

GO_LOG = """token=test-github-token
services/go/api-golang/main.go:42:9: undefined: UserResponse
FAIL    api-golang/test [build failed]
Error: Process completed with exit code 1.
"""

DIAGNOSIS = {
    "category": "application_code",
    "service": "services/go/api-golang",
    "summary": "The PR introduces UserResponse without defining or importing it.",
    "confidence": 0.93,
    "evidence": [
        {
            "type": "compiler_error",
            "excerpt": "undefined: UserResponse",
            "file": "services/go/api-golang/main.go",
            "line": 42,
        },
        {"type": "pull_request_diff", "excerpt": "response := UserResponse{}"},
    ],
    "suspected_files": ["services/go/api-golang/main.go"],
    "reproduction_command": "cd services/go/api-golang && task test",
    "recommended_action": "Define or import UserResponse, or use the intended response type.",
    "insufficient_evidence": False,
}


def test_end_to_end_deepseek_tool_call_and_idempotent_pr_publication(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    github_requests = []
    comments = []

    def github_handler(request: httpx.Request) -> httpx.Response:
        github_requests.append(f"{request.method} {request.url.path}")
        path = request.url.path
        if path.endswith("/actions/runs/123"):
            return httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "Run Tests",
                    "conclusion": "failure",
                    "head_sha": "abc1234",
                    "head_branch": "feature/test",
                    "html_url": "https://github.test/runs/123",
                    "pull_requests": [{"number": 42}],
                },
            )
        if path.endswith("/actions/runs/123/jobs"):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 987,
                            "name": "test (services/go/api-golang)",
                            "conclusion": "failure",
                            "steps": [{"name": "Run Tests", "conclusion": "failure"}],
                        },
                        {
                            "id": 988,
                            "name": "test (services/react/client-react)",
                            "conclusion": "success",
                            "steps": [],
                        },
                    ]
                },
            )
        if path.endswith("/actions/jobs/987/logs"):
            return httpx.Response(200, text=GO_LOG)
        if path.endswith("/pulls/42/files"):
            return httpx.Response(
                200,
                json=[
                    {
                        "filename": "services/go/api-golang/main.go",
                        "status": "modified",
                        "patch": "+func getUser() {\n+    response := UserResponse{}\n+}",
                    }
                ],
            )
        if path.endswith("/issues/42/comments") and request.method == "GET":
            return httpx.Response(200, json=comments)
        if path.endswith("/issues/42/comments") and request.method == "POST":
            body = request.read().decode()
            comment = {
                "id": 55,
                "body": json.loads(body)["body"],
                "html_url": "https://github.test/comments/55",
            }
            comments.append(comment)
            return httpx.Response(201, json=comment)
        if path.endswith("/issues/comments/55") and request.method == "PATCH":
            comments[0]["body"] = json.loads(request.read())["body"]
            return httpx.Response(200, json=comments[0])
        raise AssertionError(f"Unexpected GitHub request: {request.method} {path}")

    deepseek_payloads = []

    def deepseek_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        deepseek_payloads.append(payload)
        if len(deepseek_payloads) == 1:
            assert "tools" in payload
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "get_pull_request_diff",
                                            "arguments": '{"pull_request":42}',
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
                headers={"x-request-id": "ds-1"},
            )
        # The second response contains the final JSON directly after the tool observation.
        assert "tools" in payload
        assert any(
            message["role"] == "tool" and "UserResponse" in message["content"]
            for message in payload["messages"]
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": json.dumps(DIAGNOSIS)}}
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    github = GitHubClient(
        GitHubConfig(repository="acme/capstone", token="test-github-token"),
        transport=httpx.MockTransport(github_handler),
    )
    deepseek = DeepSeekClient(
        DeepSeekConfig(api_key="test-deepseek-key", max_retries=0),
        transport=httpx.MockTransport(deepseek_handler),
    )
    output = tmp_path / "output"

    envelope = investigate_run(123, github, AgentPolicy(), output, deepseek)

    assert envelope.metadata.analysis_mode == "deepseek"
    assert envelope.metadata.deepseek_calls == 2
    assert envelope.metadata.prompt_tokens == 30
    assert envelope.metadata.completion_tokens == 15
    assert envelope.metadata.pull_request == 42
    assert len(envelope.tool_trace) == 1
    assert envelope.investigation.summary == DIAGNOSIS["summary"]
    assert not (output / "raw").exists()
    assert (output / "investigation.json").is_file()
    assert "test-github-token" not in (output / "evidence.json").read_text()
    assert not any(path.endswith("/actions/jobs/988/logs") for path in github_requests)

    serialized_payloads = json.dumps(deepseek_payloads)
    assert "test-github-token" not in serialized_payloads
    assert "test-deepseek-key" not in serialized_payloads

    first = publish_investigation(envelope, github)
    second = publish_investigation(envelope, github)
    assert first.destination == "pull_request"
    assert first.updated is False
    assert second.updated is True
    assert len(comments) == 1
    assert "no code was changed" in comments[0]["body"].lower()


def test_network_failure_uses_deterministic_fast_path(tmp_path):
    def github_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/actions/runs/123"):
            return httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "Run Tests",
                    "conclusion": "failure",
                    "head_sha": "abc1234",
                    "pull_requests": [],
                },
            )
        if path.endswith("/commits/abc1234/pulls"):
            return httpx.Response(200, json=[])
        if path.endswith("/actions/runs/123/jobs"):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 987,
                            "name": "test (services/go/api-golang)",
                            "conclusion": "failure",
                            "steps": [{"name": "Build", "conclusion": "failure"}],
                        }
                    ]
                },
            )
        if path.endswith("/actions/jobs/987/logs"):
            return httpx.Response(
                200,
                text="Error: network timeout while contacting registry\n"
                "Error: Process completed with exit code 1.\n",
            )
        raise AssertionError(path)

    def forbidden_deepseek(request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            "DeepSeek must not be called for deterministic network failures"
        )

    github = GitHubClient(
        GitHubConfig(repository="acme/capstone", token="test-github-token"),
        transport=httpx.MockTransport(github_handler),
    )
    deepseek = DeepSeekClient(
        DeepSeekConfig(api_key="test-deepseek-key", max_retries=0),
        transport=httpx.MockTransport(forbidden_deepseek),
    )

    envelope = investigate_run(123, github, AgentPolicy(), tmp_path / "out", deepseek)

    assert envelope.metadata.analysis_mode == "deterministic"
    assert envelope.metadata.deepseek_calls == 0
    assert envelope.investigation.category.value == "infrastructure_network"
    assert not (tmp_path / "out/raw").exists()


def test_unsupported_model_file_claim_falls_back(tmp_path):
    invalid = dict(DIAGNOSIS)
    invalid["suspected_files"] = ["services/go/api-golang/not-in-evidence.go"]

    def github_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/actions/runs/123"):
            return httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "Run Tests",
                    "conclusion": "failure",
                    "head_sha": "abc1234",
                    "pull_requests": [{"number": 42}],
                },
            )
        if path.endswith("/actions/runs/123/jobs"):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 987,
                            "name": "test (services/go/api-golang)",
                            "conclusion": "failure",
                            "steps": [],
                        }
                    ]
                },
            )
        if path.endswith("/actions/jobs/987/logs"):
            return httpx.Response(200, text=GO_LOG)
        if path.endswith("/pulls/42/files"):
            return httpx.Response(
                200,
                json=[
                    {
                        "filename": "services/go/api-golang/main.go",
                        "patch": "+response := UserResponse{}",
                    }
                ],
            )
        raise AssertionError(path)

    def deepseek_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": json.dumps(invalid)}}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    envelope = investigate_run(
        123,
        GitHubClient(
            GitHubConfig(repository="acme/capstone", token="test-github-token"),
            transport=httpx.MockTransport(github_handler),
        ),
        AgentPolicy(),
        tmp_path / "out",
        DeepSeekClient(
            DeepSeekConfig(api_key="test-deepseek-key", max_retries=0),
            transport=httpx.MockTransport(deepseek_handler),
        ),
    )

    assert envelope.metadata.analysis_mode == "deterministic_fallback"
    assert "Unsupported file claim" in envelope.metadata.provider_error
    assert envelope.investigation.insufficient_evidence is True
