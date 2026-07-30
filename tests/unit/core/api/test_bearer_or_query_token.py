import pytest
from fastapi import HTTPException

from core.api.auth import make_bearer_or_query_token_dependency

TOKEN = "known-token"


def test_accepts_a_correct_bearer_header() -> None:
    require_token = make_bearer_or_query_token_dependency(TOKEN)

    require_token(f"Bearer {TOKEN}", None)


def test_accepts_a_correct_query_token() -> None:
    require_token = make_bearer_or_query_token_dependency(TOKEN)

    require_token(None, TOKEN)


def test_rejects_when_neither_is_correct() -> None:
    require_token = make_bearer_or_query_token_dependency(TOKEN)

    with pytest.raises(HTTPException) as exc_info:
        require_token("Bearer wrong", "wrong")

    assert exc_info.value.status_code == 401


def test_rejects_when_both_are_missing() -> None:
    require_token = make_bearer_or_query_token_dependency(TOKEN)

    with pytest.raises(HTTPException):
        require_token(None, None)
