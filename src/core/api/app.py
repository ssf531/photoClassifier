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
from core.domain.builtin_filters import BuiltinFilterListResponse
from core.domain.collections import (
    AddCollectionMembersRequest,
    CollectionCreateRequest,
    CollectionListResponse,
    CollectionMembersResponse,
    CollectionSummary,
)
from core.domain.copy_export import CopyReport, CopyToFolderRequest
from core.domain.duplicates import DuplicateGroupListResponse
from core.domain.export import ExportCollectionXmpRequest, ExportReport, ExportXmpRequest
from core.domain.library import (
    AiResultSummary,
    LibraryRootCreateRequest,
    LibraryRootResponse,
    PhotoDetailResponse,
    PhotoListResponse,
    PhotoSummary,
    ScanRequest,
    ScanResponse,
)
from core.domain.plugins import PluginListResponse, PluginSummary, PluginUpdateRequest
from core.domain.problems import (
    IgnoreProblemsRequest,
    ProblemListResponse,
    RetryProblemsRequest,
    RetryProblemsResponse,
)
from core.domain.recommendations import RecommendationListResponse
from core.domain.scheduler import JobProgress, JobSpec, TaskScheduler
from core.domain.search import (
    SearchQueryRequest,
    SearchResponse,
    SearchResultItem,
    SearchService,
    search_query_from_request,
)
from core.domain.settings import AppSettings, SettingsPatch, SettingsService
from core.domain.thumbnails import ThumbSize
from core.domain.version import CORE_API_VERSION, HealthResponse, VersionResponse
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.builtin_filters import BUILTIN_FILTER_PRESETS
from core.infrastructure.collection_manager import CollectionManager, UnknownCollectionError
from core.infrastructure.copy_export_manager import CopyExportManager
from core.infrastructure.db.library_models import LibraryRoot
from core.infrastructure.diagnostics_bundle import DiagnosticsBundleBuilder
from core.infrastructure.duplicate_review_service import DuplicateReviewService
from core.infrastructure.export_presets import UnknownPresetError, get_preset
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.problems_service import ProblemsService
from core.infrastructure.recommendation_engine import RecommendationEngine
from core.infrastructure.scan_job import SCAN_JOB_TYPE
from core.infrastructure.thumbnail_service import (
    PhotoNotFoundError,
    PhotoNotHashedError,
    ThumbnailService,
)
from core.infrastructure.xmp_export_manager import XmpExportManager

_MAX_PLUGIN_LIST_LIMIT = 500

_MAX_PHOTO_LIST_LIMIT = 500

_MAX_COLLECTION_MEMBERS_LIMIT = 500

_MAX_DUPLICATE_GROUP_LIST_LIMIT = 500

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
    metadata_repo: MetadataRepository | None = None,
    ai_result_repo: AiResultRepository | None = None,
    search_service: SearchService | None = None,
    settings_service: SettingsService | None = None,
    plugin_repo: PluginRepository | None = None,
    library_root_repo: LibraryRootRepository | None = None,
    collection_manager: CollectionManager | None = None,
    recommendation_engine: RecommendationEngine | None = None,
    duplicate_review_service: DuplicateReviewService | None = None,
    xmp_export_manager: XmpExportManager | None = None,
    copy_export_manager: CopyExportManager | None = None,
    problems_service: ProblemsService | None = None,
    diagnostics_bundle_builder: DiagnosticsBundleBuilder | None = None,
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
    app.state.metadata_repo = metadata_repo
    app.state.ai_result_repo = ai_result_repo
    app.state.search_service = search_service
    app.state.settings_service = settings_service
    app.state.plugin_repo = plugin_repo
    app.state.library_root_repo = library_root_repo
    app.state.collection_manager = collection_manager
    app.state.recommendation_engine = recommendation_engine
    app.state.duplicate_review_service = duplicate_review_service
    app.state.xmp_export_manager = xmp_export_manager
    app.state.copy_export_manager = copy_export_manager
    app.state.problems_service = problems_service
    app.state.diagnostics_bundle_builder = diagnostics_bundle_builder

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

    @app.get("/api/v1/photos/{photo_id}", dependencies=[Depends(require_bearer_token)])
    async def get_photo_detail(photo_id: uuid.UUID, request: Request) -> PhotoDetailResponse:
        photo_repo_ = request.app.state.photo_repo
        metadata_repo_ = request.app.state.metadata_repo
        ai_result_repo_ = request.app.state.ai_result_repo
        if photo_repo_ is None or metadata_repo_ is None or ai_result_repo_ is None:
            raise HTTPException(status_code=503, detail="photo detail service not configured")

        photo = await photo_repo_.get(photo_id)
        if photo is None:
            raise HTTPException(status_code=404, detail="photo not found")

        metadata = await metadata_repo_.get_by_photo_id(photo_id)
        ai_results = await ai_result_repo_.list_current_by_photo(photo_id)

        return PhotoDetailResponse(
            id=photo.id,
            relative_path=photo.relative_path,
            captured_at_utc=photo.captured_at_utc,
            camera_make=metadata.camera_make if metadata else None,
            camera_model=metadata.camera_model if metadata else None,
            width=metadata.width if metadata else None,
            height=metadata.height if metadata else None,
            ai_results=[
                AiResultSummary(
                    capability=r.capability,
                    payload=r.payload,
                    confidence=r.confidence,
                    model_version=r.model_version,
                )
                for r in ai_results
            ],
        )

    @app.post("/api/v1/search", dependencies=[Depends(require_bearer_token)])
    async def search(query: SearchQueryRequest, request: Request) -> SearchResponse:
        service = request.app.state.search_service
        photo_repo_ = request.app.state.photo_repo
        if service is None or photo_repo_ is None:
            raise HTTPException(status_code=503, detail="search service not configured")

        results = await service.search(search_query_from_request(query))

        # Preserve the service's rank order exactly -- no re-sorting here or
        # on the client (TASK-068 depends on this holding all the way to the
        # UI: the server did the ranking, the client only ever renders it).
        items: list[SearchResultItem] = []
        for result in results.results:
            photo = await photo_repo_.get(result.photo_id)
            if photo is None:
                continue
            items.append(
                SearchResultItem(
                    id=photo.id,
                    relative_path=photo.relative_path,
                    captured_at_utc=photo.captured_at_utc,
                    score=result.score,
                )
            )
        return SearchResponse(items=items)

    @app.get("/api/v1/settings", dependencies=[Depends(require_bearer_token)])
    async def get_settings(request: Request) -> AppSettings:
        service: SettingsService | None = request.app.state.settings_service
        if service is None:
            raise HTTPException(status_code=503, detail="settings service not configured")
        return service.get()

    @app.patch("/api/v1/settings", dependencies=[Depends(require_bearer_token)])
    async def update_settings(patch: SettingsPatch, request: Request) -> AppSettings:
        service: SettingsService | None = request.app.state.settings_service
        if service is None:
            raise HTTPException(status_code=503, detail="settings service not configured")
        return await service.update(patch)

    @app.get("/api/v1/plugins", dependencies=[Depends(require_bearer_token)])
    async def list_plugins(request: Request) -> PluginListResponse:
        repo = request.app.state.plugin_repo
        if repo is None:
            raise HTTPException(status_code=503, detail="plugin repository not configured")
        plugins = await repo.list(limit=_MAX_PLUGIN_LIST_LIMIT, offset=0)
        return PluginListResponse(
            items=[
                PluginSummary(
                    id=p.id,
                    name=p.name,
                    capability_types=p.capability_types,
                    version=p.version,
                    source=p.source,
                    enabled=p.enabled,
                    permissions=p.permissions,
                )
                for p in plugins
            ]
        )

    @app.patch("/api/v1/plugins/{plugin_id}", dependencies=[Depends(require_bearer_token)])
    async def update_plugin(
        plugin_id: str, patch: PluginUpdateRequest, request: Request
    ) -> PluginSummary:
        repo = request.app.state.plugin_repo
        if repo is None:
            raise HTTPException(status_code=503, detail="plugin repository not configured")
        plugin = await repo.get(plugin_id)
        if plugin is None:
            raise HTTPException(status_code=404, detail="plugin not found")
        plugin.enabled = patch.enabled
        updated = await repo.upsert(plugin)
        return PluginSummary(
            id=updated.id,
            name=updated.name,
            capability_types=updated.capability_types,
            version=updated.version,
            source=updated.source,
            enabled=updated.enabled,
            permissions=updated.permissions,
        )

    @app.post("/api/v1/library-roots", dependencies=[Depends(require_bearer_token)])
    async def create_library_root(
        body: LibraryRootCreateRequest, request: Request
    ) -> LibraryRootResponse:
        repo = request.app.state.library_root_repo
        if repo is None:
            raise HTTPException(status_code=503, detail="library root repository not configured")
        existing = await repo.get_by_path(body.path)
        root = existing if existing is not None else await repo.create(LibraryRoot(path=body.path))
        return LibraryRootResponse(id=root.id, path=root.path)

    @app.post("/api/v1/scan", dependencies=[Depends(require_bearer_token)])
    async def trigger_scan(body: ScanRequest, request: Request) -> ScanResponse:
        scheduler_ = request.app.state.scheduler
        library_root_repo_ = request.app.state.library_root_repo
        if scheduler_ is None or library_root_repo_ is None:
            raise HTTPException(status_code=503, detail="scan service not configured")
        root = await library_root_repo_.get(body.library_root_id)
        if root is None:
            raise HTTPException(status_code=404, detail="library root not found")
        job_id = await scheduler_.enqueue(
            JobSpec(job_type=SCAN_JOB_TYPE, params={"library_root_id": str(body.library_root_id)})
        )
        return ScanResponse(job_id=job_id)

    @app.get("/api/v1/collections", dependencies=[Depends(require_bearer_token)])
    async def list_collections(request: Request) -> CollectionListResponse:
        manager = request.app.state.collection_manager
        if manager is None:
            raise HTTPException(status_code=503, detail="collection manager not configured")
        return CollectionListResponse(items=await manager.list_collections())

    @app.post("/api/v1/collections", dependencies=[Depends(require_bearer_token)])
    async def create_collection(
        body: CollectionCreateRequest, request: Request
    ) -> CollectionSummary:
        manager = request.app.state.collection_manager
        if manager is None:
            raise HTTPException(status_code=503, detail="collection manager not configured")
        if body.search_query is not None:
            collection = await manager.create_smart(body.name, body.search_query)
        else:
            collection = await manager.create(body.name)
        return CollectionSummary(
            id=collection.id,
            name=collection.name,
            type=collection.type,
            created_at=collection.created_at,
            item_count=0,
        )

    @app.post(
        "/api/v1/collections/{collection_id}/members",
        dependencies=[Depends(require_bearer_token)],
    )
    async def add_collection_members(
        collection_id: uuid.UUID, body: AddCollectionMembersRequest, request: Request
    ) -> None:
        manager = request.app.state.collection_manager
        if manager is None:
            raise HTTPException(status_code=503, detail="collection manager not configured")
        try:
            await manager.add_members(collection_id, body.photo_ids)
        except UnknownCollectionError as exc:
            raise HTTPException(status_code=404, detail="collection not found") from exc

    @app.get(
        "/api/v1/collections/{collection_id}/members",
        dependencies=[Depends(require_bearer_token)],
    )
    async def list_collection_members(
        collection_id: uuid.UUID, request: Request, limit: int = 100, offset: int = 0
    ) -> CollectionMembersResponse:
        manager = request.app.state.collection_manager
        if manager is None:
            raise HTTPException(status_code=503, detail="collection manager not configured")
        if not 1 <= limit <= _MAX_COLLECTION_MEMBERS_LIMIT:
            raise HTTPException(
                status_code=422,
                detail=f"limit must be between 1 and {_MAX_COLLECTION_MEMBERS_LIMIT}",
            )
        try:
            photo_ids = await manager.list_members(collection_id, limit=limit, offset=offset)
        except UnknownCollectionError as exc:
            raise HTTPException(status_code=404, detail="collection not found") from exc
        next_offset = offset + limit if len(photo_ids) == limit else None
        return CollectionMembersResponse(photo_ids=photo_ids, next_offset=next_offset)

    @app.get("/api/v1/recommendations", dependencies=[Depends(require_bearer_token)])
    async def list_recommendations(request: Request) -> RecommendationListResponse:
        engine = request.app.state.recommendation_engine
        if engine is None:
            raise HTTPException(status_code=503, detail="recommendation engine not configured")
        return RecommendationListResponse(items=await engine.list_recommendations())

    @app.get("/api/v1/duplicate-groups", dependencies=[Depends(require_bearer_token)])
    async def list_duplicate_groups(
        request: Request, limit: int = 100, offset: int = 0
    ) -> DuplicateGroupListResponse:
        service = request.app.state.duplicate_review_service
        if service is None:
            raise HTTPException(status_code=503, detail="duplicate review service not configured")
        if not 1 <= limit <= _MAX_DUPLICATE_GROUP_LIST_LIMIT:
            raise HTTPException(
                status_code=422,
                detail=f"limit must be between 1 and {_MAX_DUPLICATE_GROUP_LIST_LIMIT}",
            )
        groups = await service.list_groups(limit=limit, offset=offset)
        next_offset = offset + limit if len(groups) == limit else None
        return DuplicateGroupListResponse(items=groups, next_offset=next_offset)

    @app.get("/api/v1/builtin-filters", dependencies=[Depends(require_bearer_token)])
    async def list_builtin_filters() -> BuiltinFilterListResponse:
        return BuiltinFilterListResponse(items=BUILTIN_FILTER_PRESETS)

    @app.post("/api/v1/export/xmp", dependencies=[Depends(require_bearer_token)])
    async def export_xmp(body: ExportXmpRequest, request: Request) -> ExportReport:
        manager = request.app.state.xmp_export_manager
        if manager is None:
            raise HTTPException(status_code=503, detail="XMP export manager not configured")
        try:
            preset = get_preset(body.preset)
        except UnknownPresetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ExportReport(items=await manager.export_xmp(body.photo_ids, preset))

    @app.post(
        "/api/v1/collections/{collection_id}/export/xmp",
        dependencies=[Depends(require_bearer_token)],
    )
    async def export_collection_xmp(
        collection_id: uuid.UUID, body: ExportCollectionXmpRequest, request: Request
    ) -> ExportReport:
        collection_manager_ = request.app.state.collection_manager
        xmp_export_manager_ = request.app.state.xmp_export_manager
        if collection_manager_ is None or xmp_export_manager_ is None:
            raise HTTPException(status_code=503, detail="export not configured")
        try:
            preset = get_preset(body.preset)
        except UnknownPresetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            photo_ids = await collection_manager_.list_all_members(collection_id)
        except UnknownCollectionError as exc:
            raise HTTPException(status_code=404, detail="collection not found") from exc
        return ExportReport(items=await xmp_export_manager_.export_xmp(photo_ids, preset))

    @app.post("/api/v1/export/copy", dependencies=[Depends(require_bearer_token)])
    async def copy_to_folder(body: CopyToFolderRequest, request: Request) -> CopyReport:
        manager = request.app.state.copy_export_manager
        if manager is None:
            raise HTTPException(status_code=503, detail="copy export manager not configured")
        items = await manager.copy_to_folder(body.photo_ids, body.destination_folder)
        return CopyReport(items=items)

    @app.get("/api/v1/problems", dependencies=[Depends(require_bearer_token)])
    async def list_problems(request: Request) -> ProblemListResponse:
        service = request.app.state.problems_service
        if service is None:
            raise HTTPException(status_code=503, detail="problems service not configured")
        return ProblemListResponse(groups=await service.list_problems())

    @app.post("/api/v1/problems/retry", dependencies=[Depends(require_bearer_token)])
    async def retry_problems(body: RetryProblemsRequest, request: Request) -> RetryProblemsResponse:
        service = request.app.state.problems_service
        if service is None:
            raise HTTPException(status_code=503, detail="problems service not configured")
        job_id = await service.retry(body.photo_ids)
        return RetryProblemsResponse(job_id=str(job_id))

    @app.post("/api/v1/problems/ignore", dependencies=[Depends(require_bearer_token)])
    async def ignore_problems(body: IgnoreProblemsRequest, request: Request) -> None:
        service = request.app.state.problems_service
        if service is None:
            raise HTTPException(status_code=503, detail="problems service not configured")
        await service.ignore(body.photo_ids)

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

    @app.get("/api/v1/diagnostics/bundle", dependencies=[Depends(require_bearer_or_query_token)])
    async def diagnostics_bundle(request: Request, include_paths: bool = False) -> Response:
        builder = request.app.state.diagnostics_bundle_builder
        if builder is None:
            raise HTTPException(status_code=503, detail="diagnostics bundle not configured")
        content = await builder.build(include_paths=include_paths)
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="diagnostics-bundle.zip"'},
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
