"""Shared parser helpers."""


def clean_excerpt(line: str, limit: int = 1_000) -> str:
    return line.strip()[:limit]


def deduplicate(errors):
    unique = []
    seen = set()
    for error in errors:
        key = (
            error.message,
            error.file,
            error.line,
            error.column,
            error.test_name,
        )
        if key not in seen:
            seen.add(key)
            unique.append(error)
    return unique
