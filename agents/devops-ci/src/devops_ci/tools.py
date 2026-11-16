"""Strictly bounded read-only tools exposed to DeepSeek."""

import json
from typing import Any

from devops_ci.github import GitHubClient
from devops_ci.models import EvidenceBundle, ToolTraceEntry
from devops_ci.policy import AgentPolicy
from devops_ci.preprocessing import prepare_log
from devops_ci.redaction import Redactor

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_pull_request_diff",
            "description": "Return bounded changed-file patches for the pull request.",
            "parameters": {
                "type": "object",
                "properties": {"pull_request": {"type": "integer", "minimum": 1}},
                "required": ["pull_request"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_repository_file",
            "description": "Read a bounded regular file at the failed commit; never execute it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "ref": {"type": "string", "minLength": 1},
                },
                "required": ["path", "ref"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_logs",
            "description": "Return a redacted tail from an already failed job in this run.",
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "integer", "minimum": 1}},
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
    },
]


class ReadOnlyTools:
    def __init__(
        self,
        github: GitHubClient,
        bundle: EvidenceBundle,
        policy: AgentPolicy,
        known_secrets: tuple[str, ...] = (),
    ):
        self.github = github
        self.bundle = bundle
        self.policy = policy
        self.known_secrets = known_secrets
        self.trace: list[ToolTraceEntry] = []
        self.observations: dict[str, str] = {}

    def schemas(self) -> list[dict[str, Any]]:
        return [
            schema
            for schema in TOOL_SCHEMAS
            if schema["function"]["name"] in self.policy.allowed_tools
        ]

    def execute(self, name: str, raw_arguments: str) -> str:
        arguments: dict[str, str | int] = {}
        try:
            if name not in self.policy.allowed_tools or name not in {
                schema["function"]["name"] for schema in TOOL_SCHEMAS
            }:
                raise ValueError("Tool is not allowed")
            parsed = json.loads(raw_arguments or "{}")
            if not isinstance(parsed, dict):
                raise TypeError("Tool arguments must be an object")
            arguments = {
                str(key): value
                for key, value in parsed.items()
                if isinstance(value, (str, int))
            }
            result = self._dispatch(name, parsed)
            outcome = "success"
            detail = None
        except Exception as exc:  # noqa: BLE001 - model/tool boundary must fail closed.
            result = json.dumps({"error": str(exc)[:300]})
            outcome = "error"
            detail = type(exc).__name__

        redacted = Redactor(self.known_secrets).redact(result).text
        self.trace.append(
            ToolTraceEntry(
                tool=name or "invalid",
                arguments=arguments,
                outcome=outcome,
                returned_characters=len(redacted),
                detail=detail,
            )
        )
        return redacted

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "get_pull_request_diff":
            number = arguments.get("pull_request")
            if number != self.bundle.context.pull_request:
                raise ValueError("Tool may only read the associated pull request")
            if f"pr:{number}" in self.observations:
                return self.observations[f"pr:{number}"]
            files = self.github.get_pull_request_files(number)
            patches = []
            size = 0
            for item in files:
                patch = item.get("patch", "")
                record = {
                    "filename": item.get("filename"),
                    "status": item.get("status"),
                    "patch": patch,
                }
                encoded = json.dumps(record)
                if (
                    size + len(encoded)
                    > self.policy.investigation.max_source_characters
                ):
                    break
                patches.append(record)
                size += len(encoded)
            result = (
                Redactor(self.known_secrets).redact(json.dumps({"files": patches})).text
            )
            self.observations[f"pr:{number}"] = result
            return result

        if name == "read_repository_file":
            path = arguments.get("path")
            ref = arguments.get("ref")
            if not isinstance(path, str) or ref != self.bundle.context.head_sha:
                raise ValueError(
                    "File reads require a path and the exact failed head SHA"
                )
            allowed_files = set(self.bundle.changed_files)
            allowed_files.update(
                error.file
                for job in self.bundle.jobs
                for error in job.log.errors
                if error.file
            )
            normalized = path.removeprefix("./")
            if not any(
                normalized == known.removeprefix("./")
                or known.removeprefix("./").endswith("/" + normalized)
                for known in allowed_files
            ):
                raise ValueError(
                    "File is not changed or referenced by the parsed failure"
                )
            cache_key = f"file:{path}:{ref}"
            if cache_key in self.observations:
                return self.observations[cache_key]
            content = self.github.read_repository_file(
                path, ref, self.policy.investigation.max_source_characters
            )
            content = Redactor(self.known_secrets).redact(content).text
            self.observations[cache_key] = content
            return content

        if name == "get_job_logs":
            job_id = arguments.get("job_id")
            allowed = {job.job.job_id for job in self.bundle.jobs}
            if job_id not in allowed:
                raise ValueError("Tool may only read failed jobs from this run")
            if f"job:{job_id}" in self.observations:
                return self.observations[f"job:{job_id}"]
            raw = self.github.download_job_logs(job_id)
            prepared = prepare_log(
                raw,
                max_characters=self.policy.investigation.max_log_characters,
                known_secrets=self.known_secrets,
            )
            tail = prepared.redacted_text[
                -self.policy.investigation.max_log_excerpt_characters :
            ]
            self.observations[f"job:{job_id}"] = tail
            return tail

        raise ValueError("Unknown tool")
