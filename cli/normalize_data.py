import argparse
import json
import re
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parents[1]
REQ_DIR = BASE_DIR / "data" / "requirements"
TEMPLATE_DIR = BASE_DIR / "data" / "SRS-Template"
OUT_DIR = BASE_DIR / "data" / "normalized"


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip()
    text = re.sub(r"\t+", " ", text)
    text = re.sub(r"[ \u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def split_requirements(text: str) -> Iterable[dict]:
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^([A-Z]{1,3})\s*:\s*(.+)$", line)
        if match:
            yield {"category": match.group(1), "text": match.group(2).strip()}
        else:
            yield {"category": None, "text": line}


def split_markdown_sections(text: str) -> Iterable[dict]:
    lines = text.split("\n")
    current_title = None
    buffer: list[str] = []

    def flush():
        nonlocal buffer
        if not buffer:
            return None
        body = "\n".join(buffer).strip()
        if not body:
            buffer = []
            return None
        section = {"title": current_title, "text": body}
        buffer = []
        return section

    for line in lines:
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            section = flush()
            if section:
                yield section
            current_title = heading.group(2).strip()
            continue
        buffer.append(line)

    section = flush()
    if section:
        yield section


def split_paragraphs(text: str) -> Iterable[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def normalize_requirements(output_path: Path) -> int:
    records = []
    for path in REQ_DIR.glob("*.txt"):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        text = normalize_text(raw)
        for idx, req in enumerate(split_requirements(text)):
            records.append(
                {
                    "id": f"requirements:{path.stem}:{idx}",
                    "type": "requirement",
                    "category": req["category"],
                    "source": str(path.name),
                    "text": req["text"],
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records)


def normalize_templates(output_path: Path) -> int:
    records = []
    skip_names = {"readme.md", "license"}
    for path in TEMPLATE_DIR.rglob("*"):
        if path.is_dir():
            continue
        if path.name.lower() in skip_names:
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        text = normalize_text(raw)
        if path.suffix.lower() == ".md":
            sections = list(split_markdown_sections(text))
            if sections:
                for idx, section in enumerate(sections):
                    records.append(
                        {
                            "id": f"template:{path.stem}:{idx}",
                            "type": "template",
                            "section": section["title"],
                            "source": str(path.relative_to(TEMPLATE_DIR)),
                            "text": section["text"],
                        }
                    )
                continue

        for idx, paragraph in enumerate(split_paragraphs(text)):
            records.append(
                {
                    "id": f"template:{path.stem}:{idx}",
                    "type": "template",
                    "section": None,
                    "source": str(path.relative_to(TEMPLATE_DIR)),
                    "text": paragraph,
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records)


def write_combined(requirements_path: Path, templates_path: Path, combined_path: Path) -> int:
    combined_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with combined_path.open("w", encoding="utf-8") as out:
        for path in (requirements_path, templates_path):
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as src:
                for line in src:
                    out.write(line)
                    count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize requirement and template data.")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory for normalized JSONL files.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    req_path = out_dir / "requirements.jsonl"
    tmpl_path = out_dir / "templates.jsonl"
    combined_path = out_dir / "combined.jsonl"

    req_count = normalize_requirements(req_path)
    tmpl_count = normalize_templates(tmpl_path)
    combined_count = write_combined(req_path, tmpl_path, combined_path)

    print(f"Requirements: {req_count} -> {req_path}")
    print(f"Templates: {tmpl_count} -> {tmpl_path}")
    print(f"Combined: {combined_count} -> {combined_path}")


if __name__ == "__main__":
    main()
