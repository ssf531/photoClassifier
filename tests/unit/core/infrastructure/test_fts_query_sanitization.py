from core.infrastructure.fts_search_index import _sanitize_fts_query


def test_sanitize_quotes_each_word_as_its_own_phrase() -> None:
    assert _sanitize_fts_query("beach sunset") == '"beach" "sunset"'


def test_sanitize_neutralizes_fts5_operator_characters() -> None:
    # A bare hyphen is FTS5's column-exclusion/NOT operator; unquoted, this
    # raises "no such column: term" instead of matching literal text.
    assert _sanitize_fts_query("wi-fi") == '"wi-fi"'
    assert _sanitize_fts_query("nonexistent-term-xyz") == '"nonexistent-term-xyz"'


def test_sanitize_escapes_embedded_double_quotes() -> None:
    assert _sanitize_fts_query('say "hi"') == '"say" """hi"""'


def test_sanitize_empty_query_returns_empty_string() -> None:
    assert _sanitize_fts_query("   ") == ""
