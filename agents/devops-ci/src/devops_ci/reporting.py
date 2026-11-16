"""Deterministic Markdown rendering from validated investigation JSON."""

from devops_ci.models import InvestigationEnvelope


def render_markdown(envelope: InvestigationEnvelope) -> str:
    metadata = envelope.metadata
    report = envelope.investigation
    lines = [
        f"<!-- devops-ci-agent:fingerprint={metadata.fingerprint} -->",
        f"<!-- devops-ci-agent:run={metadata.run_id};attempt={metadata.run_attempt} -->",
        "### CI Failure Investigation",
        "",
        f"- **Workflow:** [{metadata.workflow_name}]({metadata.workflow_url})"
        if metadata.workflow_url
        else f"- **Workflow:** {metadata.workflow_name}",
        f"- **Commit:** `{metadata.head_sha}`",
        f"- **Service:** `{report.service or 'multiple/unknown'}`",
        f"- **Category:** `{report.category.value}`",
        f"- **Confidence:** {report.confidence:.0%}",
        f"- **Analysis mode:** `{metadata.analysis_mode}`",
        "",
        report.summary[:10_000],
        "",
    ]
    if report.evidence:
        lines.extend(["**Supporting evidence**", ""])
        for item in report.evidence[:10]:
            location = (
                f" (`{item.file}:{item.line}`)"
                if item.file and item.line
                else (f" (`{item.file}`)" if item.file else "")
            )
            lines.extend(
                [
                    f"- {item.type}{location}:",
                    "",
                    "```text",
                    item.excerpt[:2_000],
                    "```",
                    "",
                ]
            )
    if report.suspected_files:
        lines.extend(
            [
                "**Suspected files**",
                "",
                *[f"- `{path}`" for path in report.suspected_files[:20]],
                "",
            ]
        )
    if report.reproduction_command:
        lines.extend(
            [
                "**Reproduce**",
                "",
                "```bash",
                report.reproduction_command[:1_000],
                "```",
                "",
            ]
        )
    lines.extend(["**Recommended action**", "", report.recommended_action[:10_000], ""])
    if report.insufficient_evidence:
        lines.extend(
            [
                "> The available evidence is insufficient for a confident root-cause diagnosis.",
                "",
            ]
        )
    if metadata.provider_error:
        lines.extend([f"> DeepSeek fallback: {metadata.provider_error[:300]}", ""])
    lines.extend(
        [
            "---",
            (
                f"DeepSeek calls: {metadata.deepseek_calls}; tool calls: {len(envelope.tool_trace)}; "
                f"tokens: {metadata.prompt_tokens + metadata.completion_tokens}."
            ),
            "This was a read-only investigation. No code was changed and no PR code was executed by the investigator.",
        ]
    )
    return "\n".join(lines)
