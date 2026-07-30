import secrets
from collections.abc import Callable

from fastapi import Header, HTTPException, Query, status


def generate_launch_token() -> str:
    return secrets.token_urlsafe(32)


def make_bearer_token_dependency(token: str) -> Callable[[str | None], None]:
    expected = f"Bearer {token}"

    def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
        if authorization != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing bearer token",
            )

    return require_bearer_token


def make_bearer_or_query_token_dependency(token: str) -> Callable[[str | None, str | None], None]:
    """Same check as `make_bearer_token_dependency`, plus a `?token=` query
    parameter -- for routes an `<img src>` loads directly, since browsers'
    native image loading can't attach an Authorization header (the same
    constraint the job-progress WebSocket route already works around).
    """
    expected = f"Bearer {token}"

    def require_token(
        authorization: str | None = Header(default=None),
        query_token: str | None = Query(default=None, alias="token"),
    ) -> None:
        if authorization == expected or query_token == token:
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing bearer token",
        )

    return require_token
