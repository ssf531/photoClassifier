import json
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from PIL import Image

from core.api.auth import (
    generate_launch_token,
    make_bearer_or_query_token_dependency,
    make_bearer_token_dependency,
)
from core.domain.library import PhotoListResponse, PhotoSummary
from core.domain.scheduler import JobProgress, TaskScheduler
from core.domain.settings import AppSettings
from core.domain.thumbnails import ThumbSize
from core.domain.version import CORE_API_VERSION, HealthResponse, VersionResponse
from core.infrastructure.library_repository import PhotoRepository
from core.infrastructure.thumbnail_service import (
    PhotoNotFoundError,
    PhotoNotHashedError,
    ThumbnailService,
)

_MAX_PHOTO_LIST_LIMIT = 500

UI_DIST_DIR = Path(__file__).resolve().parents[3] / "src" / "ui" / "dist"


def _make_placeholder_jpeg() -> bytes:
    image = Image.new("RGB", (256, 256), (200, 200, 200))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


_PLACEHOLDER_JPEG = _make_placeholder_jpeg()
_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _job_progress_payload(progress: JobProgress) -> dict[str, str | float]:
    return {
        "job_id": str(progress.job_id),
        "job_type": progress.job_type,
        "status": progress.status.value,
        "progress_pct": progress.progress_pct,
    }


def _index_html_with_launch_token(index_path: Path, launch_token: str) -> str:
    """Because UI and API share one process (ADR-0002), the bearer token is
    never written to disk or passed via stdin -- it reaches the browser by
    being embedded directly in the served index.html, the only page the
    server controls before any API call can happen.
    """
    html = index_path.read_text(encoding="utf-8")
    script = f"<script>window.__LAUNCH_TOKEN__ = {json.dumps(launch_token)};</script>\n</head>"
    return html.replace("</head>", script, 1)


def create_app(
    token: str | None = None,
    scheduler: TaskScheduler | None = None,
    settings: AppSettings | None = None,
    thumbnail_service: ThumbnailService | None = None,
    photo_repo: PhotoRepository | None = None,
    ui_dist_dir: Path = UI_DIST_DIR,
) -> FastAPI:
    launch_token = token or generate_launch_token()
    require_bearer_token = make_bearer_token_dependency(launch_token)
    require_bearer_or_query_token = make_bearer_or_query_token_dependency(launch_token)

    app = FastAPI(title="Photo Intelligence Core", version=CORE_API_VERSION)
    app.state.launch_token = launch_token
    app.state.scheduler = scheduler
    app.state.settings = settings
    app.state.thumbnail_service = thumbnail_service
    app.state.photo_repo = photo_repo

    @app.get("/health", dependencies=[Depends(require_bearer_token)])
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/version", dependencies=[Depends(require_bearer_token)])
    def version() -> VersionResponse:
        return VersionResponse(core_api_version=CORE_API_VERSION)

    @app.get("/api/v1/photos", dependencies=[Depends(require_bearer_token)])
    async def list_photos(request: Request, limit: int = 100, offset: int = 0) -> PhotoListResponse:
        repo = request.app.state.photo_repo
        if repo is None:
            raise HTTPException(status_code=503, detail="photo repository not configured")
        if not 1 <= limit <= _MAX_PHOTO_LIST_LIMIT:
            raise HTTPException(
                status_code=422, detail=f"limit must be between 1 and {_MAX_PHOTO_LIST_LIMIT}"
            )

        photos = await repo.list_active_for_grid(limit=limit, offset=offset)
        items = [
            PhotoSummary(id=p.id, relative_path=p.relative_path, captured_at_utc=p.captured_at_utc)
            for p in photos
        ]
        next_offset = offset + limit if len(items) == limit else None
        return PhotoListResponse(items=items, next_offset=next_offset)

    @app.get("/api/v1/thumbnails/{photo_id}", dependencies=[Depends(require_bearer_or_query_token)])
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

    @app.websocket("/api/v1/jobs/progress")
    async def job_progress(websocket: WebSocket, token: str | None = None) -> None:
        # Browsers' native WebSocket API can't set an Authorization header,
        # so the launch token travels as a query parameter here instead.
        if token != launch_token:
            await websocket.close(code=1008)
            return

        scheduler = websocket.app.state.scheduler
        if scheduler is None:
            await websocket.close(code=1011)
            return

        await websocket.accept()
        try:
            async for progress in scheduler.progress_stream():
                await websocket.send_json(_job_progress_payload(progress))
        except WebSocketDisconnect:
            return
        await websocket.close()

    index_path = ui_dist_dir / "index.html"
    if index_path.is_file():
        index_html = _index_html_with_launch_token(index_path, launch_token)
        resolved_dist_dir = ui_dist_dir.resolve()

        @app.get("/{full_path:path}")
        async def spa(full_path: str) -> Response:
            # Client-side routes (TASK-064) have no corresponding file on
            # disk -- any request that isn't a real built asset falls back
            # to index.html, exactly like a browser history-API SPA needs
            # to survive a direct navigation or refresh.
            candidate = (resolved_dist_dir / full_path).resolve()
            if full_path and candidate.is_file() and candidate.is_relative_to(resolved_dist_dir):
                return FileResponse(candidate)
            return HTMLResponse(index_html)

    return app
