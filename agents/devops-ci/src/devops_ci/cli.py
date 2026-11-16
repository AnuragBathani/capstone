"""Command-line entry points for local verification and CI investigation."""

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from devops_ci import __version__
from devops_ci.deepseek import DeepSeekClient, DeepSeekConfig, DeepSeekError
from devops_ci.evaluation import evaluate_fixtures
from devops_ci.github import GitHubClient, GitHubConfig, GitHubError
from devops_ci.models import Investigation, InvestigationEnvelope, LogFormat
from devops_ci.orchestrator import investigate_run
from devops_ci.policy import AgentPolicy, load_policy
from devops_ci.preprocessing import preprocess_log
from devops_ci.publisher import publish_investigation

DEFAULT_POLICY = Path(".github/agent/policy.yaml")
DEFAULT_FIXTURES = Path("agents/devops-ci/tests/fixtures")


def _print_json(value, output: str | None = None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
        print(f"Wrote {output}")
    else:
        print(rendered, end="")


def _policy(path: str) -> AgentPolicy:
    policy_path = Path(path)
    if path == str(DEFAULT_POLICY) and not policy_path.exists():
        return AgentPolicy()
    return load_policy(policy_path)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="devops-ci",
        description="Evidence-first CI investigation with bounded DeepSeek reasoning.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    preprocess = commands.add_parser(
        "preprocess", help="Redact and parse a local CI log without calling an LLM"
    )
    preprocess.add_argument("--log", required=True, help="Path to the raw log")
    preprocess.add_argument(
        "--format", choices=[item.value for item in LogFormat], default="auto"
    )
    preprocess.add_argument("--policy", default=str(DEFAULT_POLICY))
    preprocess.add_argument("--max-characters", type=int)
    preprocess.add_argument(
        "--known-secret-env",
        action="append",
        default=[],
        metavar="ENV_NAME",
        help="Mask the value of this environment variable without exposing it in argv",
    )
    preprocess.add_argument("--output", help="Write evidence JSON to this path")

    evaluate = commands.add_parser("evaluate-parsers", help="Evaluate parsers offline")
    evaluate.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    evaluate.add_argument("--output")

    config = commands.add_parser("check-config", help="Validate policy and environment")
    config.add_argument("--policy", default=str(DEFAULT_POLICY))
    config.add_argument("--require-api-key", action="store_true")

    commands.add_parser(
        "deepseek-smoke",
        help="Send a synthetic JSON connectivity check; no repository data is sent",
    )

    validate = commands.add_parser(
        "validate-report", help="Validate Investigation JSON"
    )
    validate.add_argument("--input", required=True)

    investigate = commands.add_parser(
        "investigate", help="Collect a failed GitHub run and create a validated report"
    )
    investigate.add_argument("--run-id", required=True, type=int)
    investigate.add_argument("--run-attempt", type=int, default=1)
    investigate.add_argument("--policy", default=str(DEFAULT_POLICY))
    investigate.add_argument("--output-dir", required=True)

    publish = commands.add_parser(
        "publish", help="Publish a validated investigation to its PR or an issue"
    )
    publish.add_argument("--input", required=True)

    args = parser.parse_args(argv)

    if args.command == "preprocess":
        policy = _policy(args.policy)
        maximum = args.max_characters or policy.investigation.max_log_characters
        secrets = tuple(
            os.environ[name] for name in args.known_secret_env if os.environ.get(name)
        )
        evidence = preprocess_log(
            Path(args.log).read_text(encoding="utf-8"),
            LogFormat(args.format),
            maximum,
            secrets,
        )
        _print_json(evidence.model_dump(mode="json"), args.output)
        return 0

    if args.command == "evaluate-parsers":
        report = evaluate_fixtures(args.fixtures)
        _print_json(report.model_dump(mode="json"), args.output)
        return 0 if report.failed == 0 else 1

    if args.command == "check-config":
        policy = _policy(args.policy)
        configured = bool(os.getenv("DEEPSEEK_API_KEY", "").strip())
        _print_json(
            {
                "policy_valid": True,
                "read_only": True,
                "max_steps": policy.investigation.max_steps,
                "max_deepseek_calls": policy.investigation.max_deepseek_calls,
                "max_tool_calls": policy.investigation.max_tool_calls,
                "deepseek_api_key_configured": configured,
                "deepseek_base_url": os.getenv(
                    "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
                ),
                "deepseek_model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            }
        )
        if args.require_api_key and not configured:
            print("DEEPSEEK_API_KEY is required", file=sys.stderr)
            return 2
        return 0

    if args.command == "deepseek-smoke":
        client = DeepSeekClient(DeepSeekConfig.from_env())
        _print_json({"deepseek": client.smoke_test(), "repository_data_sent": False})
        return 0

    if args.command == "validate-report":
        report = Investigation.model_validate_json(
            Path(args.input).read_text(encoding="utf-8")
        )
        _print_json({"valid": True, "category": report.category.value})
        return 0

    if args.command == "investigate":
        github = GitHubClient(GitHubConfig.from_env())
        deepseek = None
        if os.getenv("DEEPSEEK_API_KEY", "").strip():
            deepseek = DeepSeekClient(DeepSeekConfig.from_env())
        envelope = investigate_run(
            args.run_id,
            github,
            _policy(args.policy),
            args.output_dir,
            deepseek=deepseek,
            run_attempt=args.run_attempt,
        )
        _print_json(
            {
                "output": str(Path(args.output_dir) / "investigation.json"),
                "analysis_mode": envelope.metadata.analysis_mode,
                "deepseek_calls": envelope.metadata.deepseek_calls,
                "tool_calls": len(envelope.tool_trace),
                "fingerprint": envelope.metadata.fingerprint,
            }
        )
        return 0

    if args.command == "publish":
        envelope = InvestigationEnvelope.model_validate_json(
            Path(args.input).read_text(encoding="utf-8")
        )
        receipt = publish_investigation(envelope, GitHubClient(GitHubConfig.from_env()))
        _print_json(receipt.model_dump(mode="json"))
        return 0

    return 2


def main() -> None:
    try:
        exit_code = run()
    except (
        DeepSeekError,
        GitHubError,
        OSError,
        TypeError,
        ValueError,
        ValidationError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        exit_code = 2
    raise SystemExit(exit_code)
