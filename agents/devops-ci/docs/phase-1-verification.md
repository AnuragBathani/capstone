# Phase 1 GitHub-Only Verification

You can validate the complete integration from the GitHub UI using repository Actions secrets. No local installation, shell command, or application-code edit is required.

## 1. Prerequisites

### Workflows

Merge these files into the repository's default branch:

- `.github/workflows/agent-investigate.yaml`
- `.github/workflows/test.yaml`
- `agents/devops-ci/`
- `.github/agent/policy.yaml`

A `workflow_run` listener becomes active from the default branch.

### Secrets

Configure this repository secret under **Settings → Secrets and variables → Actions**:

```text
DEEPSEEK_API_KEY
GHA_CAPSTONE_PERSONAL_ACCESS_TOKEN
```

The investigator uses:

```yaml
GH_TOKEN: ${{ secrets.GHA_CAPSTONE_PERSONAL_ACCESS_TOKEN }}
DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
```

The GitHub token must be authorized for this repository. A fine-grained token needs **Actions: read**, **Contents: read**, **Issues: write**, and **Pull requests: write** (plus the automatically included metadata read permission). A classic token needs the corresponding repository access and SSO authorization where applicable.

## 2. Generate a safe failed run from the GitHub UI

1. Open **Actions**.
2. Select **Run Tests**.
3. Click **Run workflow**.
4. Set **Emit a safe synthetic failure to validate the agent end to end** to `true`.
5. Click **Run workflow**.

The `Agent Validation (services/go/api-golang)` job prints a synthetic Go compiler error and exits with status 1. It does not check out or modify application code. Ordinary pushes and PRs never run this validation job.

Expected source-run result:

```text
Run Tests: failure
Agent Validation (services/go/api-golang): failure
```

The failure is intentional and affects only this manually dispatched run.

## 3. Verify automatic investigator triggering

After `Run Tests` reaches `completed/failure`:

1. GitHub emits `workflow_run` with the failed run ID and attempt.
2. **Agent Failure Investigator** starts automatically.
3. It reads `GHA_CAPSTONE_PERSONAL_ACCESS_TOKEN` and `DEEPSEEK_API_KEY` from the workflow environment.
4. It downloads the failed validation job's logs through the GitHub API.
5. It parses and redacts evidence, calls DeepSeek if needed, validates the report, and publishes it.

No log artifact or manual copy/paste is required.

## 4. Verify outputs in the GitHub UI

### Investigation report

For a manual validation run on `main` with no associated PR, open **Issues**. The agent should create or update an issue titled approximately:

```text
[CI] Run Tests failure at <commit>
```

If the failed commit is associated with a PR, the report appears as a PR comment instead.

The report should contain:

- Failed-run link and commit
- `services/go/api-golang`
- Extracted `AgentValidationType` compiler evidence
- Category, confidence, and recommended action
- `analysis_mode: deepseek` when DeepSeek succeeds
- A statement that no code was changed

If DeepSeek cannot be reached, the investigator still publishes a report with `analysis_mode: deterministic_fallback` and a provider/fallback explanation.

### Workflow summary and artifact

Open **Actions → Agent Failure Investigator → the validation run** and verify:

- The job summary contains the investigation.
- The artifact is named `agent-investigation-<run-id>-attempt-<attempt>`.
- It contains only:
  - `investigation.json`
  - `investigation.md`
  - `metadata.json`
  - `tool-trace.json`
- `metadata.json` records the run ID, attempt, fingerprint, model, token counts, and analysis mode.
- No `raw/` directory, API keys, Authorization headers, full prompts, or environment dumps are present.

### Safety and idempotence

- The validation job changes no repository files.
- The investigator does not execute failed-PR code.
- No branch, fix PR, merge, deployment, or production action occurs.
- Repeating publication for the same fingerprint updates the existing issue/comment instead of creating duplicates.

Close the validation issue after the test if desired.

## 5. Validate a PR comment entirely through GitHub

1. In the GitHub web editor, create a branch and edit `services/go/api-golang/test/example_test.go`.
2. Change its condition to `if val != 2` so the test deliberately fails.
3. Propose the change through a pull request.
4. Wait for **Run Tests** and then **Agent Failure Investigator**.
5. Verify the investigator creates or updates one consolidated PR comment.
6. Close the test PR without merging it.

## 6. Investigate an existing failed run manually

1. Copy the run ID from the failed run's URL: `actions/runs/<run-id>`.
2. Open **Actions → Agent Failure Investigator → Run workflow**.
3. Enter the run ID and attempt (normally `1`).
4. Run the workflow and verify the same report and artifact checks above.

## Acceptance boundary

A successful GitHub-only run validates the real trigger, GitHub API log retrieval, secrets, DeepSeek API, evidence processing, and publication. Record the human-confirmed diagnosis in `baseline-template.md`; synthetic validation does not measure real-world root-cause accuracy.
