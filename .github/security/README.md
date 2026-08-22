# Security Program Baseline

This folder contains policy and guardrail artifacts for the DevSecOps rollout.

## Baseline Scope

The baseline rollout is governance only:
- define a single source of truth policy for security checks
- validate policy structure in CI
- keep current test/build/deploy behavior unchanged

No vulnerability scanner is enforced in this phase.

## Files

- `security-gates.yaml`: policy contract for scan enablement, enforcement mode, severity threshold, and phase ownership.

## Branch Protection

Configure branch protection in GitHub for `main` with required checks:
- `Run Tests`
- `Security Baseline`

## Next Steps

- Enable SAST, secret scanning, and dependency scanning.
- Enable container image scanning before push.
- Enable DAST against staging.
