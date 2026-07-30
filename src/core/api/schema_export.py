import argparse
import json
from pathlib import Path

from core.api.app import create_app


def export_schema(output_path: Path) -> None:
    """Dump the FastAPI app's OpenAPI schema to disk (TASK-062): the source
    the UI's TypeScript client is generated from. `create_app()` needs no
    live dependencies to produce a schema, so this never starts a server.
    """
    schema = create_app(token="schema-export").openapi()
    output_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(prog="export-openapi-schema")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export_schema(args.output)


if __name__ == "__main__":
    main()
