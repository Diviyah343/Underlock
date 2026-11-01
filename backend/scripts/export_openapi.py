import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
OPENAPI_PATH = BACKEND_ROOT / "openapi.json"
TYPES_PATH = REPOSITORY_ROOT / "frontend" / "src" / "api" / "types.ts"
sys.path.insert(0, str(BACKEND_ROOT))

from api.main import app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--openapi-only",
        action="store_true",
        help="write openapi.json without generating the frontend TypeScript file",
    )
    args = parser.parse_args()

    OPENAPI_PATH.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    if args.openapi_only:
        return

    TYPES_PATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["npx", "--yes", "openapi-typescript", str(OPENAPI_PATH), "-o", str(TYPES_PATH)],
        cwd=REPOSITORY_ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
