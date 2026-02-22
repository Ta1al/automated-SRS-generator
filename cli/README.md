# CLI Utilities

This directory contains command-line helpers and small scripts used by the
backend engine. Most functionality is also accessible via the FastAPI
service, but the CLI is useful during development and experimentation.

- `normalize_data.py` – reads the raw requirement text files and SRS
  template markdown under `data/`, normalizes whitespace, splits the
  documents into individual chunks, and writes them to JSONL. The output
  serves as the RAG corpus. Run once after updating the source files.

- `preview_normalized.py` – quick viewer that prints the first N records
  from a JSONL file produced by `normalize_data.py`.

- `build_embeddings.py` – computes vector embeddings for the normalized
  corpus. By default it uses a local SentenceTransformers model (CPU),
  but the script previously supported OpenRouter remote embeddings. The
  output is written to `data/normalized/embeddings_index.jsonl` and can
  be reused across runs.

- `clarification_loop.py` – small library of prompt builders, question
  parsing, and simple ``build_llm_prompt`` helper used by both the CLI
  and the graph controller. It is not itself executable.

- `clarification_demo.py` – demo program that exercises
  `clarification_loop.py` by printing generated questions and a LLM
  prompt. Useful for testing prompt formatting.

- `openrouter_app.py` – the main CLI frontend. It supports multiple
  modes: a flat chat-based clarification loop, an optional RAG step
  (BM25 or embeddings), and a `--use-graph` flag to launch the full
  LangGraph state machine. Accepts a variety of flags for dry-runs,
  verbosity and retrieval configuration. Use during early development or
  as a fallback UI.

- `langgraph.py` – tiny in-process state machine library (a couple of
  classes). The graph controller is built on top of this; you can also
  use it to quickly implement other workflows.

- `graph_controller.py` – implements the IEEE‑830 workflow as a graph of
  nodes. Entry/extraction/interview/drafting/diagramming/review nodes
  are defined here; `openrouter_app.py` can run this graph when
  `--use-graph` is supplied. The file contains the logic for stepping
  through the nodes and accumulating context.

The CLI folder is intentionally lightweight—most scripts are small and
intended to be composable. When the project is deployed the FastAPI
service in `backend/` will expose equivalent functionality via HTTP.