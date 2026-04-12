"""Lightweight Mermaid syntax retrieval for diagram generation prompts.

This module provides a tiny in-memory corpus of Mermaid syntax rules/examples
and returns the most relevant snippets for a requested diagram type.
"""

from __future__ import annotations

import re
from collections import Counter


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _score(query_tokens: Counter[str], candidate: str) -> float:
    candidate_tokens = _tokenize(candidate)
    if not candidate_tokens:
        return 0.0

    candidate_counts = Counter(candidate_tokens)
    overlap = sum(min(query_tokens[token], candidate_counts[token]) for token in query_tokens)
    if overlap <= 0:
        return 0.0

    return overlap / max(10, len(candidate_tokens))


_SYNTAX_SNIPPETS: dict[str, list[str]] = {
    "flowchart": [
        "Start with flowchart plus direction (TB/TD/BT/RL/LR), for example: flowchart TD.",
        "Use safe node IDs: letters, digits, underscore only (A, API_Gateway, DB1). Avoid reserved-looking IDs and punctuation-heavy IDs.",
        "Define text labels with bracket syntax: A[Text], B{Decision}, C((Circle)), D[(Database)]. Keep labels short and plain.",
        "If labels contain special characters like parentheses, wrap them in quotes: A[\"Text with (parens)\"].",
        "Lowercase 'end' as a node text can break flowcharts; use End/END instead.",
        "Link syntax: A --> B, labeled links A -->|Yes| C, open links A --- B, dotted links A -.-> B, thick links A ==> B.",
        "Circle/cross edge markers exist (--o / --x). If a target node starts with o/x, use capitalization or spacing to avoid accidental edge marker parsing.",
        "Subgraphs are allowed: subgraph Name ... end. Use explicit direction inside subgraph only when needed.",
        "Prefer readable multi-line links over dense chaining (& and long one-liners) to reduce syntax mistakes.",
        "Example (doc-aligned safe pattern): flowchart TD\n    User[\"User Request\"] --> API[API Gateway]\n    API --> Auth{Authorized}\n    Auth -->|Yes| Service[Core Service]\n    Auth -->|No| Reject[Access Denied]\n    Service --> DB[(Database)]",
        "Example with modern shape syntax (v11.3+): flowchart TD\n    In@{ shape: lean-r, label: \"Input\" } --> Proc@{ shape: rect, label: \"Process\" }\n    Proc --> Out@{ shape: lean-l, label: \"Output\" }",
    ],
    "sequence": [
        "sequenceDiagram starts a sequence diagram. Define participants before message exchanges.",
        "Sequence messages: A->>B: request, B-->>A: response. Keep participant names simple words or quoted strings.",
        "Use participant declarations for clarity: participant User, participant System.",
        "Example: sequenceDiagram\n    participant User\n    participant System\n    User->>System: Submit request\n    System-->>User: Return result",
    ],
    "er": [
        "erDiagram starts an ER diagram. Entities are uppercase names and relationships are declared between entities.",
        "Relationship connectors include ||, |o, o|, }o, |{ with -- between entity names.",
        "Entity attributes are declared in braces: ENTITY { string id int version }.",
        "Example: erDiagram\n    USER ||--o{ ORDER : places\n    ORDER ||--|{ ORDER_ITEM : contains\n    ORDER {\n      string id\n      datetime created_at\n    }",
    ],
}


def retrieve_mermaid_syntax(diagram_type: str, query: str, top_k: int = 3) -> str:
    """Return top-k Mermaid syntax snippets for the requested diagram type."""
    key = diagram_type.strip().lower()
    snippets = _SYNTAX_SNIPPETS.get(key, [])
    if not snippets:
        return ""

    query_tokens = Counter(_tokenize(query or ""))
    if not query_tokens:
        return "\n\n".join(f"- {item}" for item in snippets[:top_k])

    ranked = sorted(
        snippets,
        key=lambda item: _score(query_tokens, item),
        reverse=True,
    )

    return "\n\n".join(f"- {item}" for item in ranked[:top_k])
