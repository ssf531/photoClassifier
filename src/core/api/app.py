import uuid
from io import BytesIO
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from core.api.auth import generate_launch_token, make_bearer_token_dependency
from core.domain.scheduler import TaskScheduler
from core.domain.settings import AppSettings
from core.domain.thumbnails import ThumbSize
from core.domain.version import CORE_API_VERSION
from core.infrastructure.thumbnail_service import (
    PhotoNotFoundError,
    PhotoNotHashedError,
    ThumbnailService,
)

UI_DIST_DIR = Path(__file__).resolve().parents[3] / "src" / "ui" / "dist"


def _make_placeholder_jpeg() -> bytes:
    image = Image.new("RGB", (256, 256), (200, 200, 200))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


_PLACEHOLDER_JPEG = _make_placeholder_jpeg()
_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


def create_app(
    token: str | None = None,
    scheduler: TaskScheduler | None = None,
    settings: AppSettings | None = None,
    thumbnail_service: ThumbnailService | None = None,
) -> FastAPI:
    launch_token = token or generate_launch_token()
    require_bearer_token = make_bearer_token_dependency(launch_token)

    app = FastAPI(title="Photo Intelligence Core", version=CORE_API_VERSION)
    app.state.launch_token = launch_token
    app.state.scheduler = scheduler
    app.state.settings = settings
    app.state.thumbnail_service = thumbnail_service

    @app.get("/health", dependencies=[Depends(require_bearer_token)])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/version", dependencies=[Depends(require_bearer_token)])
    def version() -> dict[str, str]:
        return {"core_api_version": CORE_API_VERSION}

    @app.get("/api/v1/thumbnails/{photo_id}", dependencies=[Depends(require_bearer_token)])
    async def get_thumbnail(photo_id: uuid.UUID, size: ThumbSize, request: Request) -> Response:
        service = request.app.state.thumbnail_service
        if service is None:
            raise HTTPException(status_code=503, detail="thumbnail service not configured")

        try:
            outcome = await service.get_or_generate(photo_id, size)
        except PhotoNotFoundError as exc:
            raise HTTPException(status_code=404, detail="photo not found") from exc
        except PhotoNotHashedError as exc:
            raise HTTPException(status_code=409, detail="photo has not been hashed yet") from exc

        if request.headers.get("if-none-match") == outcome.etag:
            return Response(status_code=304)

        if outcome.path is None:
            return Response(
                content=_PLACEHOLDER_JPEG,
                media_type="image/jpeg",
                headers={"X-Thumbnail-Degraded": outcome.degraded_reason or "unknown"},
            )

        return FileResponse(
            outcome.path,
            media_type="image/jpeg",
            headers={"ETag": outcome.etag, "Cache-Control": _IMMUTABLE_CACHE_CONTROL},
        )

    if UI_DIST_DIR.is_dir():
        app.mount("/", StaticFiles(directory=UI_DIST_DIR, html=True), name="ui")

    return app
