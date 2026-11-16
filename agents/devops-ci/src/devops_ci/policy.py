"""Policy loading with fail-closed safety validation."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvestigationPolicy(PolicyModel):
    enabled: bool = True
    max_steps: int = Field(default=12, ge=1, le=50)
    max_deepseek_calls: int = Field(default=6, ge=1, le=12)
    max_tool_calls: int = Field(default=4, ge=0, le=12)
    max_failed_jobs: int = Field(default=5, ge=1, le=20)
    max_log_characters: int = Field(default=200_000, ge=1_000, le=2_000_000)
    max_log_excerpt_characters: int = Field(default=4_000, ge=500, le=20_000)
    max_source_characters: int = Field(default=30_000, ge=1_000, le=100_000)
    timeout_minutes: int = Field(default=10, ge=1, le=60)
    artifact_retention_days: int = Field(default=7, ge=1, le=90)


class PermissionPolicy(PolicyModel):
    repository_write: bool = False
    execute_pull_request_code: bool = False
    create_pull_requests: bool = False
    automatic_merge: bool = False

    @model_validator(mode="after")
    def investigation_must_be_read_only(self):
        enabled_writes = [
            name
            for name in (
                "repository_write",
                "execute_pull_request_code",
                "create_pull_requests",
                "automatic_merge",
            )
            if getattr(self, name)
        ]
        if enabled_writes:
            raise ValueError("Phase 0/1 policy forbids: " + ", ".join(enabled_writes))
        return self


class AgentPolicy(PolicyModel):
    investigation: InvestigationPolicy = Field(default_factory=InvestigationPolicy)
    permissions: PermissionPolicy = Field(default_factory=PermissionPolicy)
    allowed_tools: set[str] = Field(
        default_factory=lambda: {
            "get_workflow_metadata",
            "get_failed_jobs",
            "get_job_logs",
            "get_pull_request_diff",
            "read_repository_file",
            "get_recent_related_failures",
        }
    )
    allowed_workflows: set[str] = Field(default_factory=lambda: {"Run Tests"})


def load_policy(path: str | Path) -> AgentPolicy:
    policy_path = Path(path)
    raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"Policy must be a YAML mapping: {policy_path}")
    return AgentPolicy.model_validate(raw)
