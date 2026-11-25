from __future__ import annotations

from app.core.config import Settings


def _origins(value: str) -> list[str]:
    return Settings(cors_origins=value).cors_origins_list


def test_plain_comma_list() -> None:
    assert _origins("https://a.vercel.app,https://b.vercel.app") == [
        "https://a.vercel.app",
        "https://b.vercel.app",
    ]


def test_quoted_entries_and_whitespace() -> None:
    assert _origins(" 'https://a.vercel.app' , \"https://b.vercel.app\" ") == [
        "https://a.vercel.app",
        "https://b.vercel.app",
    ]


def test_trailing_slashes_are_removed() -> None:
    assert _origins("https://a.vercel.app/,http://localhost:5173/") == [
        "https://a.vercel.app",
        "http://localhost:5173",
    ]


def test_json_array_is_accepted() -> None:
    assert _origins('["https://a.vercel.app", "https://b.vercel.app"]') == [
        "https://a.vercel.app",
        "https://b.vercel.app",
    ]


def test_empty_and_blank_entries_are_dropped() -> None:
    assert _origins("") == []
    assert _origins(" , ,") == []


def test_duplicates_are_collapsed() -> None:
    assert _origins("https://a.vercel.app,https://a.vercel.app/") == ["https://a.vercel.app"]

def test_full_env_line_is_accepted() -> None:
    assert _origins("CORS_ORIGINS=https://a.vercel.app,https://b.vercel.app") == [
        "https://a.vercel.app",
        "https://b.vercel.app",
    ]