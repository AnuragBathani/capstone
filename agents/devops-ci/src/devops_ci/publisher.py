"""Idempotent PR/issue publication and GitHub job summaries."""

import os
from pathlib import Path

from devops_ci.github import GitHubClient
from devops_ci.models import InvestigationEnvelope, PublishReceipt
from devops_ci.reporting import render_markdown


def publish_investigation(
    envelope: InvestigationEnvelope,
    github: GitHubClient,
) -> PublishReceipt:
    body = render_markdown(envelope)
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(body + "\n")

    metadata = envelope.metadata
    marker = f"<!-- devops-ci-agent:fingerprint={metadata.fingerprint} -->"
    if metadata.pull_request:
        number = metadata.pull_request
        existing = github.find_comment(number, marker)
        if existing:
            result = github.update_comment(existing["id"], body)
            return PublishReceipt(
                destination="pull_request",
                identifier=number,
                url=result.get("html_url"),
                updated=True,
            )
        result = github.create_comment(number, body)
        return PublishReceipt(
            destination="pull_request", identifier=number, url=result.get("html_url")
        )

    title = f"[CI] {metadata.workflow_name} failure at {metadata.head_sha[:8]}"
    for issue in github.list_open_issues():
        if marker in issue.get("body", "") and "pull_request" not in issue:
            number = issue["number"]
            result = github.update_issue(number, title, body)
            return PublishReceipt(
                destination="issue",
                identifier=number,
                url=result.get("html_url"),
                updated=True,
            )
    result = github.create_issue(title, body)
    return PublishReceipt(
        destination="issue", identifier=result.get("number"), url=result.get("html_url")
    )
