import httpx
from devops_ci.github import GitHubClient, GitHubConfig
from devops_ci.models import Investigation, InvestigationEnvelope, InvestigationMetadata
from devops_ci.publisher import publish_investigation


def test_main_branch_failure_creates_then_updates_issue():
    created = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/issues") and request.method == "GET":
            return httpx.Response(200, json=created)
        if request.url.path.endswith("/issues") and request.method == "POST":
            payload = __import__("json").loads(request.content)
            issue = {
                "number": 9,
                "body": payload["body"],
                "html_url": "https://github.test/issues/9",
            }
            created.append(issue)
            return httpx.Response(201, json=issue)
        if request.url.path.endswith("/issues/9") and request.method == "PATCH":
            created[0]["body"] = __import__("json").loads(request.content)["body"]
            return httpx.Response(200, json=created[0])
        raise AssertionError(request.url.path)

    envelope = InvestigationEnvelope(
        metadata=InvestigationMetadata(
            repository="acme/capstone",
            run_id=123,
            run_attempt=1,
            head_sha="abc1234",
            workflow_name="Run Tests",
            fingerprint="b" * 64,
            analysis_mode="deterministic",
            routing_reason="test",
            deepseek_calls=0,
            prompt_tokens=0,
            completion_tokens=0,
            duration_seconds=0.1,
        ),
        investigation=Investigation(
            category="infrastructure_network",
            summary="Registry timeout",
            confidence=0.8,
            recommended_action="Retry after the registry recovers",
            insufficient_evidence=False,
        ),
    )
    client = GitHubClient(
        GitHubConfig(repository="acme/capstone", token="token"),
        transport=httpx.MockTransport(handler),
    )

    first = publish_investigation(envelope, client)
    second = publish_investigation(envelope, client)

    assert first.destination == "issue"
    assert first.updated is False
    assert second.updated is True
    assert len(created) == 1
