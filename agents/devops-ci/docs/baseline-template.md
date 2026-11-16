# CI Failure Baseline

Copy one record per real failure before enabling automated investigation. Do not include secrets or complete raw logs.

| Field | Value |
|---|---|
| Workflow run ID | |
| Date | |
| Pull request / commit | |
| Service | |
| Failed command | |
| Human-confirmed category | |
| Human-confirmed root cause | |
| Failure timestamp | |
| First useful human diagnosis timestamp | |
| Resolution timestamp | |
| Number of CI reruns | |
| Evidence that confirmed the diagnosis | |

After Phase 1 shadow mode, compare these values with the agent's category, evidence, confidence, and investigation latency. Parser fixture accuracy is not evidence of real-world root-cause accuracy.
