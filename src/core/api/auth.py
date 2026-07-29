import secrets
from collections.abc import Callable

from fastapi import Header, HTTPException, status


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
