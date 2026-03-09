import argparse
import hashlib
import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parents[1]
NORMALIZED_PATH = BASE_DIR / "data" / "normalized" / "combined.jsonl"
DEFAULT_OUTPUT = BASE_DIR / "data" / "normalized" / "embeddings_index.jsonl"


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_corpus(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Normalized data not found: {path}. Run cli/normalize_data.py first."
        )
    texts = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            text = record.get("text", "").strip()
            if text:
                texts.append(text)
    return texts


def embed_texts(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return embeddings.tolist()


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute local embeddings for RAG.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL path.")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size.")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2", help="Local embedding model name.")
    parser.add_argument("--device", default="cpu", help="Device to run embeddings on (cpu or cuda).")
    parser.add_argument("--max-items", type=int, default=0, help="Limit number of items (0 = all).")
    parser.add_argument("--probe", action="store_true", help="Encode a single probe text then exit.")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    corpus = load_corpus(NORMALIZED_PATH)
    if args.max_items and args.max_items > 0:
        corpus = corpus[: args.max_items]

    print(f"Embedding model: {args.model}")
    print(f"Corpus size: {len(corpus)}")

    model = SentenceTransformer(args.model, device=args.device)

    if args.probe:
        embed_texts(model, ["probe text"])
        print("Probe request succeeded.")
        return

    try:
        with output_path.open("w", encoding="utf-8") as f:
            for start in range(0, len(corpus), args.batch_size):
                batch = corpus[start : start + args.batch_size]
                print(f"Embedding batch of {len(batch)} texts...")
                embeddings = embed_texts(model, batch)
                for text, embedding in zip(batch, embeddings):
                    record = {
                        "hash": _text_hash(text),
                        "text": text,
                        "embedding": embedding,
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

                print(f"Embedded {min(start + args.batch_size, len(corpus))}/{len(corpus)}")

        print(f"Wrote embeddings to {output_path}")
    except KeyboardInterrupt:
        print("\nInterrupted by user. Partial embeddings may be saved.")


if __name__ == "__main__":
    main()
