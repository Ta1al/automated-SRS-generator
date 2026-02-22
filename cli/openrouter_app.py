import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Iterable
from dotenv import load_dotenv
from openai import OpenAI
from rank_bm25 import BM25Okapi
# make sure parent directory is on sys.path when running the script
sys.path.append(str(Path(__file__).resolve().parents[1]))

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

from cli.clarification_loop import build_question_prompt, parse_questions

BASE_DIR = Path(__file__).resolve().parents[1]
NORMALIZED_PATH = BASE_DIR / "data" / "normalized" / "combined.jsonl"
EMBEDDINGS_CACHE_PATH = BASE_DIR / "data" / "normalized" / "embeddings_cache.jsonl"
EMBEDDINGS_INDEX_PATH = BASE_DIR / "data" / "normalized" / "embeddings_index.jsonl"


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


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in text.split() if t.strip()]


def retrieve_context(corpus: list[str], query: str, k: int = 5) -> list[str]:
    tokenized = [tokenize(doc) for doc in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [corpus[i] for i in ranked[:k]]


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_embeddings_cache(path: Path) -> dict[str, list[float]]:
    if not path.exists():
        return {}
    cache: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            cache[record["hash"]] = record["embedding"]
    return cache


def load_embeddings_index(path: Path) -> dict[str, list[float]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Embeddings index not found: {path}. Run cli/build_embeddings.py first."
        )
    cache: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            cache[record["hash"]] = record["embedding"]
    return cache


def build_embeddings_from_index(corpus: list[str], index_path: Path) -> list[list[float]]:
    index = load_embeddings_index(index_path)
    embeddings: list[list[float]] = []
    missing = 0
    for text in corpus:
        text_hash = _text_hash(text)
        embedding = index.get(text_hash)
        if embedding is None:
            missing += 1
            embeddings.append([])
        else:
            embeddings.append(embedding)

    if missing:
        raise ValueError(
            f"Embeddings index missing {missing} items. Rebuild the index to match the corpus."
        )
    return embeddings


def append_embeddings_cache(path: Path, entries: list[dict]) -> None:
    if not entries:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def embed_texts(
    client: OpenAI,
    model: str,
    texts: list[str],
    retries: int = 2,
) -> list[list[float]]:
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


def build_corpus_embeddings(
    client: OpenAI,
    model: str,
    corpus: list[str],
    cache_path: Path,
    batch_size: int = 64,
    verbose: bool = False,
    retries: int = 2,
) -> list[list[float]]:
    cache = load_embeddings_cache(cache_path)
    embeddings: list[list[float]] = []
    pending_texts: list[str] = []
    pending_hashes: list[str] = []
    cache_hits = 0

    for text in corpus:
        text_hash = _text_hash(text)
        if text_hash in cache:
            embeddings.append(cache[text_hash])
            cache_hits += 1
        else:
            embeddings.append([])
            pending_texts.append(text)
            pending_hashes.append(text_hash)

    if verbose:
        print(f"Embedding cache hits: {cache_hits}")
        print(f"Embedding cache misses: {len(pending_texts)}")

    new_entries: list[dict] = []
    if pending_texts:
        total_batches = math.ceil(len(pending_texts) / batch_size)
        for batch_index, start in enumerate(range(0, len(pending_texts), batch_size), start=1):
            batch_texts = pending_texts[start : start + batch_size]
            batch_hashes = pending_hashes[start : start + batch_size]
            if verbose:
                print(f"Embedding batch {batch_index}/{total_batches} ({len(batch_texts)} items)")
            batch_embeddings = embed_texts(client, model, batch_texts, retries=retries)
            for text_hash, embedding in zip(batch_hashes, batch_embeddings):
                cache[text_hash] = embedding
                new_entries.append({"hash": text_hash, "embedding": embedding})

        append_embeddings_cache(cache_path, new_entries)

    for idx, text in enumerate(corpus):
        if not embeddings[idx]:
            embeddings[idx] = cache[_text_hash(text)]

    return embeddings


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_context_embeddings(
    corpus: list[str],
    corpus_embeddings: list[list[float]],
    query_embedding: list[float],
    k: int = 5,
) -> list[str]:
    scored = [
        (idx, _cosine_similarity(query_embedding, embedding))
        for idx, embedding in enumerate(corpus_embeddings)
    ]
    ranked = sorted(scored, key=lambda item: item[1], reverse=True)
    return [corpus[idx] for idx, _ in ranked[:k]]


def ask_questions(questions: Iterable) -> dict[str, str]:
    answers: dict[str, str] = {}
    for question in questions:
        print(f"\n[{question.section}] {question.prompt}")
        for idx, option in enumerate(question.options, start=1):
            print(f"  {idx}. {option}")
        choice = input("Select an option or type your own answer: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(question.options):
            answers[question.question_id] = question.options[int(choice) - 1]
        else:
            answers[question.question_id] = choice
    return answers


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


def call_openrouter(
    system_prompt: str,
    user_prompt: str,
    dry_run: bool = False,
    stream: bool = False,
    timeout: float | None = None,
) -> str:
    if dry_run:
        return "[DRY RUN] OpenRouter call skipped."

    client = _create_client(timeout=timeout)
    model = os.getenv("OPENROUTER_MODEL")

    try:
        if stream:
            stream_resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                stream=True,
            )
            chunks: list[str] = []
            for event in stream_resp:
                delta = event.choices[0].delta.content
                if delta:
                    print(delta, end="", flush=True)
                    chunks.append(delta)
            print()
            return "".join(chunks)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        hint = (
            "Check OPENROUTER_API_KEY, model access, and optional HTTP-Referer/X-Title."
            if status_code == 403
            else ""
        )
        raise RuntimeError(f"OpenRouter request failed. {hint}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Clarification loop + RAG demo using OpenRouter.")
    parser.add_argument("--idea", help="Initial user idea text.")
    parser.add_argument("--k", type=int, default=5, help="Number of context items to retrieve.")
    parser.add_argument("--max-questions", type=int, default=6, help="Max clarification questions.")
    parser.add_argument("--rounds", type=int, default=2, help="Max clarification rounds.")
    parser.add_argument("--dry-run", action="store_true", help="Skip OpenRouter call.")
    parser.add_argument("--stream", action="store_true", help="Stream LLM response to console.")
    parser.add_argument("--verbose", action="store_true", help="Print extra debugging details.")
    parser.add_argument("--use-precomputed", action="store_true", help="Use precomputed embeddings index.")
    parser.add_argument("--embed-index-path", default=str(EMBEDDINGS_INDEX_PATH), help="Path to embeddings index JSONL.")
    parser.add_argument("--use-graph", action="store_true", help="Run the LangGraph workflow instead of the normal loop.")
    parser.add_argument(
        "--rag",
        choices=["bm25", "embed"],
        default="bm25",
        help="Retrieval method to use for context.",
    )
    args = parser.parse_args()

    idea = args.idea or input("Describe your product idea: ").strip()
    if args.use_graph:
        from graph_controller import build_graph

        print("Running stateful graph workflow...")
        ctx = build_graph().run({"idea": idea})
        print("\n--- graph output ---")
        print(json.dumps(ctx, ensure_ascii=False, indent=2))
        return

    corpus = load_corpus(NORMALIZED_PATH)

    if args.rag == "embed" and args.dry_run:
        if args.verbose:
            print("Embedding RAG disabled in dry-run; falling back to BM25.")
        args.rag = "bm25"

    if args.rag == "embed":
        client = _create_client()
        embed_model = os.getenv("OPENROUTER_EMBED_MODEL", "openai/text-embedding-3-small")
        if args.use_precomputed:
            if args.verbose:
                print(f"Loading embeddings index: {args.embed_index_path}")
            corpus_embeddings = build_embeddings_from_index(
                corpus,
                Path(args.embed_index_path),
            )
        else:
            print("Building embeddings-based context (this may take a while)...")
            if args.verbose:
                print(f"Embedding model: {embed_model}")
            corpus_embeddings = build_corpus_embeddings(
                client,
                embed_model,
                corpus,
                EMBEDDINGS_CACHE_PATH,
                verbose=args.verbose,
            )
        if args.verbose:
            print("Embedding query text...")
        query_embedding = embed_texts(client, embed_model, [idea])[0]
        if args.verbose:
            print("Ranking context by cosine similarity...")
        context = retrieve_context_embeddings(
            corpus,
            corpus_embeddings,
            query_embedding,
            k=args.k,
        )
    else:
        context = retrieve_context(corpus, idea, k=args.k)
    answers: dict[str, str] = {}

    if args.verbose:
        print(f"Loaded corpus items: {len(corpus)}")
        print(f"Retrieved context items: {len(context)}")
        for idx, item in enumerate(context, start=1):
            print(f"  [{idx}] {item}")

    for _ in range(args.rounds):
        prompts = build_question_prompt(
            idea,
            answers,
            context,
            max_questions=args.max_questions,
        )
        if args.verbose:
            print("\n--- Prompt (system) ---")
            print(prompts["system"])
            print("\n--- Prompt (user) ---")
            print(prompts["user"])

        reply = call_openrouter(
            prompts["system"],
            prompts["user"],
            dry_run=args.dry_run,
            stream=args.stream,
            timeout=args.timeout,
        )

        if args.dry_run:
            break

        if args.verbose and not args.stream:
            print("\n--- LLM Response (raw) ---")
            print(reply)

        try:
            questions = parse_questions(reply)
        except ValueError as exc:
            print("\n--- OpenRouter Response (raw) ---")
            print(reply)
            raise SystemExit(str(exc)) from exc

        if not questions:
            print("\nNo further clarification questions.")
            break

        new_answers = ask_questions(questions)
        answers.update(new_answers)

    print("\n--- Collected Answers ---")
    print(json.dumps(answers, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
