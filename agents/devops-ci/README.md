# DevOps CI Agent — Phases 0 and 1

An evidence-first GitHub Actions failure investigator using deterministic parsing and bounded DeepSeek reasoning. It reads failed-run evidence and publishes reports; it does **not** modify source, execute PR code, create fix PRs, merge, or deploy.

## Implemented

### Phase 0: foundation

- Typed Pydantic evidence, investigation, run-state, and publication contracts
- Fail-closed read-only YAML policy
- Best-effort secret redaction and bounded head/tail log processing
- Go, Jest, Pytest, and generic error extraction
- Seven labeled parser fixtures
- DeepSeek OpenAI-compatible JSON client using `deepseek-chat`

### Phase 1: automatic read-only investigation

- `workflow_run` trigger for the existing `Run Tests` workflow
- Manual `workflow_dispatch` investigation by run ID
- GitHub API retrieval of run metadata, latest failed jobs, and failed-job logs
- No changes or log-upload steps required in `test.yaml`
- Failed-job-only processing with raw-log cleanup in `finally`
- Failure fingerprints and latest-branch concurrency
- Deterministic network/timeout fast path with no model call
- Bounded DeepSeek tool calling for associated PR diffs, exact-commit source, and failed-job logs
- Source reads restricted to changed/parser-referenced files
- Model schema and evidence-citation validation
- Deterministic fallback on missing credentials, provider errors, invalid JSON, or unsupported claims
- Idempotent PR comments by fingerprint; main/no-PR failures create or update issues
- Job summaries and sanitized seven-day artifacts; raw logs and prompts are excluded
- Retry, token accounting, time/size/call limits, and mocked end-to-end tests

## Install

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e './agents/devops-ci[dev]'
```

Python 3.11 or newer is required.

## Offline verification

```bash
.venv/bin/pytest agents/devops-ci/tests
.venv/bin/ruff check agents/devops-ci/src agents/devops-ci/tests
.venv/bin/ruff format --check agents/devops-ci/src agents/devops-ci/tests
.venv/bin/devops-ci evaluate-parsers
.venv/bin/devops-ci check-config
.venv/bin/devops-ci validate-report \
  --input agents/devops-ci/examples/go-investigation.json
```

Current verified results:

- 28 tests passed
- Ruff lint and format checks passed
- 7/7 parser fixtures passed
- Investigation schema and read-only policy validated

The end-to-end test uses real orchestration with mocked GitHub and DeepSeek HTTP APIs. It verifies log retrieval, redaction, a DeepSeek PR-diff tool request, diagnosis validation, raw-log deletion, and PR-comment create/update behavior without live credentials.

## Preprocess a local log without DeepSeek

```bash
.venv/bin/devops-ci preprocess \
  --log /path/to/github-actions-job.log \
  --output evidence.json
```

The output contains extracted errors and metadata, not the complete raw log. Redaction is defense in depth, not a guarantee; review data before sending it to an external provider.

## Verify DeepSeek connectivity

```bash
export DEEPSEEK_API_KEY='your-key'
export DEEPSEEK_MODEL='deepseek-chat'
export DEEPSEEK_BASE_URL='https://api.deepseek.com'

.venv/bin/devops-ci check-config --require-api-key
.venv/bin/devops-ci deepseek-smoke
```

Expected:

```json
{
  "deepseek": {"status": "ok"},
  "repository_data_sent": false
}
```

The smoke test sends only a synthetic prompt and may incur a small provider charge. Offline tests never call DeepSeek.

## Investigate and publish a real failed run manually

Required environment:

```bash
export GITHUB_REPOSITORY='AnuragBathani/capstone'
export GH_TOKEN='a-token-with-actions-read-and-pr-write'
export DEEPSEEK_API_KEY='your-key'
```

Investigate without publishing:

```bash
.venv/bin/devops-ci investigate \
  --run-id 123456789 \
  --run-attempt 1 \
  --output-dir agent-output/manual-123456789
```

Inspect `investigation.json`, `investigation.md`, and `tool-trace.json`. Confirm they contain no sensitive data before publication.

Publish or update the associated PR comment:

```bash
.venv/bin/devops-ci publish \
  --input agent-output/manual-123456789/investigation.json
```

Without a DeepSeek key, `investigate` still produces a deterministic fallback report.

## Enable automatic GitHub Actions investigation

1. Merge `.github/workflows/agent-investigate.yaml` and `agents/devops-ci/` into the repository's default branch. `workflow_run` listeners must exist on the default branch.
2. Add the `DEEPSEEK_API_KEY` Actions repository secret.
3. Keep the workflow's explicit permissions restricted to `actions: read`, `contents: read`, `pull-requests: write`, and `issues: write`.
4. For GitHub-only end-to-end validation, open **Actions → Run Tests → Run workflow**, set `simulate_agent_failure` to `true`, and run it. This emits a synthetic failure without editing application code.
5. Confirm `Run Tests` finishes first, then `Agent Failure Investigator` starts automatically.
6. Verify a report issue (or associated PR comment), a job summary, and a sanitized artifact appear. Use a deliberately failing test PR when you specifically want to validate PR comments.

GitHub API calls use the `GHA_CAPSTONE_PERSONAL_ACCESS_TOKEN` Actions secret, and DeepSeek uses `DEEPSEEK_API_KEY`. No local setup is needed.

See `docs/phase-1-verification.md` for a concrete safe test and acceptance checklist.

## Data handling

- GitHub remains the system of record for original logs, runs, commits, comments, and issues.
- Raw downloaded logs exist only temporarily and are deleted in `finally`.
- DeepSeek receives only bounded, redacted evidence and approved tool observations.
- DeepSeek is stateless from the application's perspective; conversation state exists only in runner memory.
- Artifacts contain validated reports and sanitized traces, not raw logs, complete prompts, environment variables, or credentials.
- PR comments are updated using a failure-fingerprint marker instead of creating a comment per push.

## Current boundary

The agent diagnoses and reports only. Automated repair, dependency remediation, deployment investigation, production rollback, and automatic merging are not enabled.
