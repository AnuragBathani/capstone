"""Small GitHub REST client used by the trusted, read-only investigator."""

import base64
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

import httpx


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubConfig:
    repository: str
    token: str
    api_url: str = "https://api.github.com"
    timeout_seconds: float = 30.0
    max_log_bytes: int = 5_000_000

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        repository = os.getenv("GITHUB_REPOSITORY", "").strip()
        token = os.getenv("GH_TOKEN", os.getenv("GITHUB_TOKEN", "")).strip()
        if not repository or "/" not in repository:
            raise GitHubError("GITHUB_REPOSITORY must be owner/repository")
        if not token:
            raise GitHubError("GH_TOKEN or GITHUB_TOKEN is not configured")
        return cls(
            repository=repository,
            token=token,
            api_url=os.getenv("GITHUB_API_URL", cls.api_url).rstrip("/"),
        )


class GitHubClient:
    def __init__(
        self,
        config: GitHubConfig,
        transport: httpx.BaseTransport | None = None,
    ):
        if config.repository.count("/") != 1:
            raise GitHubError("repository must be owner/repository")
        self.config = config
        self.transport = transport
        self.base = f"{config.api_url}/repos/{config.repository}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            with httpx.Client(
                timeout=self.config.timeout_seconds,
                follow_redirects=True,
                transport=self.transport,
            ) as client:
                response = client.request(
                    method,
                    self.base + path,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            detail = response.text[:500].replace(self.config.token, "[REDACTED]")
            raise GitHubError(
                f"GitHub returned HTTP {response.status_code} for {path}: {detail}"
            )
        return response

    def _json(self, method: str, path: str, **kwargs) -> Any:
        try:
            return self._request(method, path, **kwargs).json()
        except ValueError as exc:
            raise GitHubError(f"GitHub returned invalid JSON for {path}") from exc

    def get_workflow_run(self, run_id: int) -> dict[str, Any]:
        return self._json("GET", f"/actions/runs/{run_id}")

    def get_latest_jobs(self, run_id: int) -> list[dict[str, Any]]:
        jobs = []
        for page in range(1, 6):
            body = self._json(
                "GET",
                f"/actions/runs/{run_id}/jobs",
                params={"filter": "latest", "per_page": 100, "page": page},
            )
            batch = body.get("jobs", [])
            jobs.extend(batch)
            if len(batch) < 100:
                break
        return jobs

    def download_job_logs(self, job_id: int) -> str:
        response = self._request("GET", f"/actions/jobs/{job_id}/logs")
        if len(response.content) > self.config.max_log_bytes:
            raise GitHubError(
                f"Job log exceeds {self.config.max_log_bytes} byte download limit"
            )
        return response.content.decode("utf-8", errors="replace")

    def get_pull_requests_for_commit(self, sha: str) -> list[dict[str, Any]]:
        result = self._json("GET", f"/commits/{quote(sha, safe='')}/pulls")
        return result if isinstance(result, list) else []

    def get_pull_request_files(self, number: int) -> list[dict[str, Any]]:
        files = []
        for page in range(1, 6):
            batch = self._json(
                "GET",
                f"/pulls/{number}/files",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(batch, list):
                raise GitHubError("GitHub PR files response must be a list")
            files.extend(batch)
            if len(batch) < 100:
                break
        return files

    def read_repository_file(self, path: str, ref: str, maximum: int) -> str:
        candidate = PurePosixPath(path)
        if (
            not path
            or "\\" in path
            or candidate.is_absolute()
            or ".." in candidate.parts
            or ".git" in candidate.parts
        ):
            raise GitHubError("Unsafe repository file path")
        body = self._json(
            "GET",
            f"/contents/{quote(path, safe='/')}",
            params={"ref": ref},
        )
        if body.get("type") != "file" or body.get("encoding") != "base64":
            raise GitHubError("Repository path is not a supported regular file")
        try:
            content = base64.b64decode(body["content"]).decode(
                "utf-8", errors="replace"
            )
        except (KeyError, ValueError) as exc:
            raise GitHubError("Could not decode repository file") from exc
        return content[:maximum]

    def list_issue_comments(self, number: int) -> list[dict[str, Any]]:
        result = self._json(
            "GET", f"/issues/{number}/comments", params={"per_page": 100}
        )
        return result if isinstance(result, list) else []

    def find_comment(self, number: int, marker: str) -> dict[str, Any] | None:
        for comment in self.list_issue_comments(number):
            if marker in comment.get("body", ""):
                return comment
        return None

    def create_comment(self, number: int, body: str) -> dict[str, Any]:
        return self._json(
            "POST", f"/issues/{number}/comments", json_body={"body": body}
        )

    def update_comment(self, comment_id: int, body: str) -> dict[str, Any]:
        return self._json(
            "PATCH", f"/issues/comments/{comment_id}", json_body={"body": body}
        )

    def list_open_issues(self) -> list[dict[str, Any]]:
        result = self._json(
            "GET",
            "/issues",
            params={"state": "open", "per_page": 100},
        )
        return result if isinstance(result, list) else []

    def create_issue(self, title: str, body: str) -> dict[str, Any]:
        return self._json(
            "POST",
            "/issues",
            json_body={"title": title, "body": body},
        )

    def update_issue(self, number: int, title: str, body: str) -> dict[str, Any]:
        return self._json(
            "PATCH", f"/issues/{number}", json_body={"title": title, "body": body}
        )
