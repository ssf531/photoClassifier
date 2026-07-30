import json
from pathlib import Path

from core.api.schema_export import export_schema


def test_export_schema_writes_a_valid_openapi_document_covering_known_routes(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "openapi.json"

    export_schema(output_path)

    schema = json.loads(output_path.read_text(encoding="utf-8"))
    assert schema["openapi"].startswith("3.")
    assert "/health" in schema["paths"]
    assert "/version" in schema["paths"]
    assert "/api/v1/thumbnails/{photo_id}" in schema["paths"]
