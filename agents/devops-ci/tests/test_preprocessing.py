from devops_ci.models import LogFormat
from devops_ci.preprocessing import preprocess_log, truncate_log


def test_preprocessing_bounds_and_parses_log():
    text = "ignored prefix\n" * 200
    text += "services/go/api-golang/main.go:42:9: undefined: UserResponse\n"
    evidence = preprocess_log(text, max_characters=1_000)

    assert evidence.truncated is True
    assert evidence.processed_characters <= 1_000
    assert evidence.format == LogFormat.GO
    assert evidence.errors[0].message == "undefined: UserResponse"


def test_short_log_is_not_truncated():
    text = "nothing useful"
    bounded, truncated = truncate_log(text, 1_000)
    assert bounded == text
    assert truncated is False
