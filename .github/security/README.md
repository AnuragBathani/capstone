# Security Program

Policy and guardrail artifacts for the DevSecOps rollout.

## How enforcement works

`security-gates.yaml` is the **single source of truth**. It is not documentation —
every security workflow reads it at runtime through the
[`security-policy`](../actions/security-policy/action.yaml) composite action and
honours the result.

```
security-gates.yaml
        │
        └── .github/actions/security-policy   ->  enabled / enforcement / severity / exit_code
                    │
                    ├── sast.yaml              (CodeQL)
                    ├── secret-scan.yaml       (Gitleaks)
                    ├── dependency-scan.yaml   (Trivy fs + govulncheck)
                    ├── iac-scan.yaml          (Trivy config)
                    └── build-push.yaml        (Trivy image — gates the push)
```

Turning a gate off, or dropping it from `block` to `warn`, is a **one-line edit to
the policy file**. No workflow changes are required.

| Field | Meaning |
|---|---|
| `checks.<name>.enabled` | `false` skips the scan entirely |
| `checks.<name>.enforcement` | `"off"` / `"warn"` (report only) / `"block"` (fail the job) |
| `block_on_severity` | Severity **floor** — `high` also blocks on `critical` |

> `enforcement` values are quoted on purpose. YAML 1.1 parses a bare `off` as the
> boolean `false`, which would silently break policy resolution. The parsers coerce
> `false` back to `"off"` defensively, but keep the quotes.

## Current posture

All five implemented checks are `enabled: true, enforcement: "warn"` at
**HIGH and above**: they run on every PR and publish findings, but **never fail a job**.
Delivery is not blocked. DAST remains disabled — it needs an ephemeral environment.

Every vulnerability scan runs with `--ignore-unfixed`, so only findings with an
available fix are reported.

To start gating on a check, change its `enforcement` to `"block"` in
`security-gates.yaml`. Nothing else changes — no workflow edits.

### What still fails a job

Warn mode silences *findings*, not *malfunctions*. These remain hard failures, because
each one means the scanning itself is broken or incomplete — which is exactly the state
a passing pipeline must not hide:

- `security-gates.yaml` missing, unparseable, or failing schema validation
- an unknown check name requested from the `security-policy` action
- a Kubernetes manifest that still will not parse after normalization (the scan would
  silently skip it)

## The container gate

`build-push.yaml` builds the image **locally first** (`load: true, push: false`) and
scans it before pushing. Scanning after the push would mean a vulnerable image is already
public by the time the finding lands.

In the current `warn` posture the push proceeds regardless of findings. Setting
`container_scan` to `enforcement: "block"` turns this into a real gate: a non-zero scan
stops the `docker push` step from running.

## IaC scanning and kluctl templating

Four manifests are not valid YAML, because kluctl templating sits where a value
begins (e.g. `replicas: {{apiGolang.replicas}}`). A scanner pointed straight at
`deploy/` **skips them silently** — including `api-golang`'s Deployment.

`iac-scan.yaml` therefore copies `deploy/` into a workspace-local staging directory,
substitutes `{{ ... }}` with `1` (which keeps both `replicas:` and `image: repo:TAG`
type-valid), asserts every manifest now parses, and scans that. Vendored upstream
Helm charts are excluded — they are not our configuration to answer for.

*Higher-fidelity alternative, not currently implemented:* scan the output of
`kluctl render -t staging --offline-kubernetes` — you would be scanning exactly what
gets deployed, at the cost of a kluctl dependency in CI and Helm-chart noise.

## Accepting a finding

Add it to [`.trivyignore`](../../.trivyignore) with who accepted it, why it is not
exploitable here, and an expiry date. Entries without all three should be rejected
in review. An empty file is the goal.

## Deferred

Not in the current rollout, in rough priority order:

1. **Workflow shell injection** — `build-push.yaml` and `update-gitops-manifests.yaml`
   interpolate `${{ inputs.version }}` and similar directly into `run:` blocks, in jobs
   that hold the deploy PAT. `version` is a free-form `workflow_dispatch` string.
2. **Deploy PAT scope** — `GHA_CAPSTONE_PERSONAL_ACCESS_TOKEN` is a long-lived
   user-scoped token reaching four workflows.
3. **SHA-pin the remaining actions** — `dorny/paths-filter`, `gitleaks/gitleaks-action`,
   `docker/setup-buildx-action`, and the scanner actions added here are still on mutable
   tags. Dependabot's `github-actions` ecosystem will start raising these.
4. **DAST** against an ephemeral staging environment.
5. **SBOM + image signing** (Syft / Cosign) with provenance attestation.
