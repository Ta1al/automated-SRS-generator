import argparse
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

BASE_DIR = Path(__file__).resolve().parents[1]
NORMALIZED_PATH = BASE_DIR / "data" / "normalized" / "combined.jsonl"
DEFAULT_OUTPUT = BASE_DIR / "data" / "normalized" / "embeddings_index.jsonl"


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_corpus(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Normalized data not found: {path}. Run scripts/normalize_data.py first."
        )
    texts = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            text = record.get("text", "").strip()
            if text:
                texts.append(text)
    return texts


def _create_client(timeout: float | None = None) -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY is not set.")

    default_headers = {}
    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    title = os.getenv("OPENROUTER_APP_TITLE")
    if referer:
        default_headers["HTTP-Referer"] = referer
    if title:
        default_headers["X-Title"] = title

    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers=default_headers or None,
        timeout=timeout,
    )


def embed_texts(client: OpenAI, model: str, texts: list[str], retries: int = 2) -> list[list[float]]:
    attempt = 0
    while True:
        try:
            response = client.embeddings.create(model=model, input=texts)
            return [item.embedding for item in response.data]
        except Exception as exc:
            attempt += 1
            if attempt > retries:
                raise
            print(f"Embedding batch failed ({exc}). Retrying {attempt}/{retries}...")


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute OpenRouter embeddings for RAG.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL path.")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size.")
    parser.add_argument("--retries", type=int, default=2, help="Retry attempts per batch.")
    parser.add_argument("--timeout", type=float, default=120, help="Request timeout in seconds.")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    corpus = load_corpus(NORMALIZED_PATH)
    model = os.getenv("OPENROUTER_EMBED_MODEL", "openai/text-embedding-3-small")

    client = _create_client(timeout=args.timeout)
    print(f"Embedding model: {model}")
    print(f"Corpus size: {len(corpus)}")

    with output_path.open("w", encoding="utf-8") as f:
        for start in range(0, len(corpus), args.batch_size):
            batch = corpus[start : start + args.batch_size]
            embeddings = embed_texts(client, model, batch, retries=args.retries)
            for text, embedding in zip(batch, embeddings):
                record = {
                    "hash": _text_hash(text),
                    "text": text,
                    "embedding": embedding,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            print(f"Embedded {min(start + args.batch_size, len(corpus))}/{len(corpus)}")

    print(f"Wrote embeddings to {output_path}")


if __name__ == "__main__":
    main()
