from pathlib import Path

import pytest
from devops_ci.policy import AgentPolicy, PermissionPolicy, load_policy
from pydantic import ValidationError


def test_repository_policy_is_valid_and_read_only():
    root = Path(__file__).parents[3]
    policy = load_policy(root / ".github/agent/policy.yaml")

    assert policy.investigation.max_steps == 12
    assert policy.permissions.repository_write is False
    assert "Run Tests" in policy.allowed_workflows


@pytest.mark.parametrize(
    "permission",
    [
        "repository_write",
        "execute_pull_request_code",
        "create_pull_requests",
        "automatic_merge",
    ],
)
def test_phase_zero_rejects_write_permissions(permission):
    with pytest.raises(ValidationError, match="Phase 0/1 policy forbids"):
        PermissionPolicy(**{permission: True})


def test_default_policy_is_read_only():
    assert AgentPolicy().permissions == PermissionPolicy()
