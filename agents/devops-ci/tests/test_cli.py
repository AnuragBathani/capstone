import json
from pathlib import Path

from devops_ci.cli import run


def test_cli_evaluates_fixtures(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    output = tmp_path / "report.json"

    exit_code = run(
        ["evaluate-parsers", "--fixtures", str(fixtures), "--output", str(output)]
    )

    assert exit_code == 0
    assert json.loads(output.read_text())["accuracy"] == 1.0


def test_cli_preprocess_does_not_need_deepseek_key(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    log = tmp_path / "failure.log"
    log.write_text("main.go:10:2: undefined: MissingType\n")
    output = tmp_path / "evidence.json"

    exit_code = run(["preprocess", "--log", str(log), "--output", str(output)])

    assert exit_code == 0
    evidence = json.loads(output.read_text())
    assert evidence["format"] == "go"
    assert evidence["errors"][0]["message"] == "undefined: MissingType"
