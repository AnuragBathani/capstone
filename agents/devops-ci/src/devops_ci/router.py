"""Conservative deterministic routing before any paid model request."""

from devops_ci.models import (
    Evidence,
    FailureCategory,
    Investigation,
    JobEvidence,
    RoutingDecision,
)


def route_failure(jobs: list[JobEvidence]) -> RoutingDecision:
    errors = [error for job in jobs for error in job.log.errors]
    meaningful = [
        error
        for error in errors
        if "process completed with exit code" not in error.message.lower()
    ]
    if meaningful and all(error.kind == "network" for error in meaningful):
        return RoutingDecision(
            route="deterministic",
            reason="All extracted failures are network/timeout errors; no speculative LLM diagnosis is needed.",
        )
    return RoutingDecision(
        route="deepseek",
        reason="The failure requires correlation with the PR diff, source, or additional log evidence.",
    )


def deterministic_network_report(jobs: list[JobEvidence]) -> Investigation:
    evidence = [
        Evidence(type="network_error", excerpt=error.excerpt)
        for job in jobs
        for error in job.log.errors
        if error.kind == "network"
    ]
    messages = sorted({item.excerpt for item in evidence})
    service = jobs[0].job.service if len(jobs) == 1 else None
    return Investigation(
        category=FailureCategory.INFRASTRUCTURE_NETWORK,
        service=service,
        summary="The failed step reported a network or timeout error: " + messages[0],
        confidence=0.86,
        evidence=evidence,
        reproduction_command=None,
        recommended_action=(
            "Check the referenced external service and rerun the failed jobs if the outage was transient. "
            "Do not change application code without additional evidence."
        ),
        insufficient_evidence=False,
    )
