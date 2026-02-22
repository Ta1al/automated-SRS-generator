import argparse
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PATH = BASE_DIR / "data" / "normalized" / "combined.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview normalized JSONL records.")
    parser.add_argument("--path", default=str(DEFAULT_PATH), help="Path to JSONL file.")
    parser.add_argument("--limit", type=int, default=5, help="Number of records to show.")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx >= args.limit:
                break
            print(json.loads(line))


if __name__ == "__main__":
    main()
