from pathlib import Path

from devops_ci.evaluation import evaluate_fixtures


def test_all_labeled_fixtures_pass():
    fixtures = Path(__file__).parent / "fixtures"
    report = evaluate_fixtures(fixtures)

    assert report.total == 7
    assert report.failed == 0, report.model_dump_json(indent=2)
    assert report.accuracy == 1.0
