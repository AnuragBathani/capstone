# Capstone – GitHub Actions Course Project

This repository contains the capstone project for the [DevOps Directive GitHub Actions course](https://github.com/sidpalas/devops-directive-github-actions-course). Top-level directories include .github/ (workflows, composite actions, and config), services/ (the microservices), deploy/kubernetes/, utils/, plus a root Taskfile.yaml used by many workflows.  ￼

---

## Repo structure

```bash
.
├── .github/
│   ├── actions/                # Composite actions (e.g., setup-dependencies)
│   ├── utils/                  # release-please config, file-filters, etc.
│   └── workflows/              # All workflow YAML files listed above
├── deploy/
│   └── kubernetes/             # GitOps-style manifests
├── services/
│   ├── go/api-golang
│   ├── node/api-node
│   ├── python/load-generator-python
│   ├── react/client-react
│   └── other/api-golang-migrator
├── utils/                      # Helper scripts/tasks
├── Taskfile.yaml               # Shared task definitions used inside workflows
└── readme-assets/
```

---

## Workflows Overview

![](./readme-assets/workflow-diagram.jpg)

1. **Run Tests** – .github/workflows/test.yaml

    Triggers on push to main (only when files in services/** change), on any pull_request, and via workflow_dispatch. It uses dorny/paths-filter to detect changed services and fans out a matrix job to run tests per service using the local composite action ./.github/actions/setup-dependencies.  ￼

2. **Build and Push Container Images** – .github/workflows/build-push.yaml

    Runs on:
      •	push to main (builds changed services),
      •	tagged releases matching **@[0-9]*.[0-9]*.[0-9]*, and
      •	manual workflow_dispatch (with service and optional version inputs).

    It logs into Docker Hub, sets up QEMU/Buildx, computes version & image tags via task commands, and pushes images. It then triggers the deploy workflow (update-gitops-manifests.yaml) with gh workflow run, but skips that step when running locally by checking env.ACT.  ￼

3. **Update GitOps Manifests** – .github/workflows/update-gitops-manifests.yaml

    Manual only (workflow_dispatch) with inputs for service, version, image_tag, and target environment (development, staging, production). A concurrency group prevents manifest races per service/environment. It updates tags via task utils:update-image-tags-service and commits/pushes changes (again skipping the push when env.ACT is set).  ￼

4. **Release Please** – .github/workflows/release-please.yaml

    Runs on push to main and manually. Uses googleapis/release-please-action with a PAT to open PRs and tag releases across multiple packages defined in .github/utils/release-please-config.json and .github/utils/.release-please-manifest.json.  ￼

5. **Close Stale Issues and PRs** – .github/workflows/close-stale-issues-and-prs.yaml

    Nightly cron (0 0 * * *) + manual trigger, using actions/stale to label/close inactive issues and PRs.  ￼

6. **Security Baseline** – .github/workflows/security-baseline.yaml

    Runs on pull_request, push to main, and manual trigger. It validates the *schema* of `.github/security/security-gates.yaml` (required keys, valid enforcement values, no contradictory `block` + `disabled` entries) and publishes a live enable/enforce dashboard to the job summary.

7. **Secret Scan** – .github/workflows/secret-scan.yaml

    Runs on pull_request, push to main, and manual trigger. Scans the repository with Gitleaks, gated by policy.

8. **SAST** – .github/workflows/sast.yaml

    CodeQL across Go, JavaScript/TypeScript, and Python with the `security-extended` query suite. Results publish to **Security → Code scanning**.

9. **Dependency Scan** – .github/workflows/dependency-scan.yaml

    Trivy filesystem scan across `go.sum`, both `package-lock.json` files, and `poetry.lock`, plus `govulncheck` for the Go service (reachability-aware, and catches stdlib vulnerabilities a lockfile scan cannot see). Paired with `.github/dependabot.yml` for automated remediation PRs.

10. **IaC Scan** – .github/workflows/iac-scan.yaml

    Trivy misconfiguration scanning over the Kubernetes manifests and all five Dockerfiles.

### How the Pieces Fit Together
1.	PR or push to main → Run Tests.
2.	If main changes or a tag is pushed → Build & Push Container Images builds and publishes images, then triggers…
3.	Update GitOps Manifests to roll out the new tag to the chosen environment.
4.	Release Please automates versioning/changelogs across all services.
5.	Close Stale Issues and PRs keeps the project tidy.

---

## Security

Five scanner categories run on every PR in **warn mode** — they report HIGH and CRITICAL findings that have a fix available, but **do not block delivery**:

| Category | Tool | Gate |
|---|---|---|
| SAST | CodeQL (Go, JS/TS, Python) | `sast.yaml` |
| Secret | Gitleaks | `secret-scan.yaml` |
| Dependency / SCA | Trivy `fs` + govulncheck | `dependency-scan.yaml` |
| IaC / misconfiguration | Trivy `config` | `iac-scan.yaml` |
| Container image | Trivy `image` | inside `build-push.yaml`, **before** the push |

### Policy as code

`.github/security/security-gates.yaml` is the single source of truth. Every workflow
reads it at runtime via the `.github/actions/security-policy` composite action and
honours `enabled` / `enforcement` / `block_on_severity`. Moving a gate from `block` to
`warn`, or disabling it, is a one-line edit to that file — no workflow changes.

`Security Baseline` validates the policy's schema on every PR and renders the current
enable/enforce matrix into the job summary.

All checks are currently `enforcement: "warn"`: findings are surfaced in job summaries and
**Security → Code scanning**, but no scanner fails a build. Flipping a check to `"block"`
is a one-line edit to `security-gates.yaml`. Malfunctions still fail — an invalid policy
file, or a manifest that will not parse — so a green pipeline cannot mean "the scan
quietly did nothing".

### Two things worth knowing

- **The container scan runs before the push.** `build-push.yaml` builds with
  `load: true, push: false` and scans the local image first, so findings are known before
  anything is published. In warn mode the push still proceeds; set `container_scan` to
  `enforcement: "block"` and the scan becomes a true gate that stops the push.

- **kluctl templating breaks naive IaC scanning.** Four manifests aren't valid YAML
  (`replicas: {{apiGolang.replicas}}`), so a scanner pointed at `deploy/` skips them
  *silently* — including `api-golang`'s Deployment. `iac-scan.yaml` normalizes the
  templating into a staging copy first and asserts everything parses before scanning.

Accepted findings live in `.trivyignore` and require a justification and an expiry date.
Full details, and the deferred hardening backlog, are in
[`.github/security/README.md`](.github/security/README.md).

---

## Iterating Locally with act

To run workflows locally with act (https://github.com/nektos/act), there are Taskfiles and event configurations located in `.github/workflows/<NAME_OF_WORKFLOW>`

For example to run the `test` workflow:

```bash
➜  capstone git:(main) ✗ cd .github/workflows/test
➜  test git:(main) ✗ task trigger-workflow 
task: [trigger-workflow] act pull_request \
  --container-architecture linux/amd64 \
  -s GITHUB_TOKEN="<GITHUB_TOKEN>" \
  -e <PATH_TO_EVENT_JSON> \
  -P ubuntu-24.04=catthehacker/ubuntu:act-22.04 \
  --directory ../../.. \
  -W .github/workflows/test.yaml
```

The security workflows have harnesses too: `.github/workflows/{sast,dependency-scan,iac-scan,secret-scan}`.

### Docker 28+ workaround

act copies its runner payload into `/var/run/act`, but `/var/run` is a symlink to `/run`
in the `catthehacker` images, and Docker 28 refuses tar extraction through a symlink:

```
failed to copy content to container: Error response from daemon: mkdirat var/run: file exists
```

This is an act/Docker incompatibility, not a problem with the workflows. Build a runner
image with a real `/var/run` and point act at it:

```bash
printf 'FROM catthehacker/ubuntu:act-22.04\nRUN rm -f /var/run && mkdir -p /var/run\n' > /tmp/Dockerfile
DOCKER_BUILDKIT=0 docker build -t act-runner-patched:22.04 /tmp
act workflow_dispatch -P ubuntu-24.04=act-runner-patched:22.04 --pull=false -W .github/workflows/iac-scan.yaml
```

### What does not run under act

`CodeQL` analysis and every `upload-sarif` step are guarded by `if: ${{ !env.ACT }}` —
they need GitHub-hosted infrastructure. Locally you get the policy resolution and the
scanners; SARIF ingest only exercises on a real runner.

