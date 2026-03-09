import json
from pathlib import Path
from typing import Any, Dict, Optional

from cli.openrouter_app import (
    call_openrouter,
    load_corpus,
    retrieve_context,
    retrieve_context_embeddings,
    ask_questions,
    build_question_prompt,
    parse_questions,
)
from langgraph import Graph, Node

IEEE_CHECKLIST = [
    "Functional requirements",
    "External interfaces",
    "Design constraints",
    "Non-functional attributes (performance, security, …)",
]


def entry_node(graph: Graph, ctx: Dict[str, Any]) -> Optional[str]:
    ctx["idea"] = ctx.get("idea") or input("Describe your product in one sentence: ").strip()
    return "extraction"


def extraction_node(graph: Graph, ctx: Dict[str, Any]) -> Optional[str]:
    prompt = (
        "Extract the primary entities (users, data elements, goals) from this idea:\n\n"
        f"{ctx['idea']}\n\n"
        "Respond with a JSON object: {\"users\":…, \"data\":…, \"goals\":…}."
    )
    resp = call_openrouter("", prompt)
    try:
        ctx["entities"] = json.loads(resp)
    except Exception:
        ctx["entities"] = {"raw": resp}
    return "interview"


def interview_node(graph: Graph, ctx: Dict[str, Any]) -> Optional[str]:
    answers = ctx.setdefault("answers", {})
    for section in IEEE_CHECKLIST:
        if not answers.get(section):
            q_prompt = (
                f"The idea is: {ctx['idea']}\n"
                f"Entities: {ctx.get('entities')}\n\n"
                f"Ask a question to clarify the '{section}'."
            )
            q_resp = call_openrouter("", q_prompt)
            print(f"\n[clarify – {section}] {q_resp}")
            ans = input("Answer: ").strip()
            answers[section] = ans
    return "drafting"


def drafting_node(graph: Graph, ctx: Dict[str, Any]) -> Optional[str]:
    statements = []
    for section, answer in ctx.get("answers", {}).items():
        statements.append(f"The system shall {answer}.  // {section}")
    ctx["draft"] = "\n".join(statements)
    return "diagramming"


def diagramming_node(graph: Graph, ctx: Dict[str, Any]) -> Optional[str]:
    users = ctx.get("entities", {}).get("users", [])
    data = ctx.get("entities", {}).get("data", [])
    lines = ["```mermaid", "flowchart LR"]
    for u in users:
        for d in data:
            lines.append(f"    {u} -->|uses| {d}")
    lines.append("```")
    ctx["diagram"] = "\n".join(lines)
    return "review"


def review_node(graph: Graph, ctx: Dict[str, Any]) -> Optional[str]:
    prompt = (
        "Review the following SRS draft for ambiguities or contradictions:\n\n"
        f"{ctx.get('draft')}\n\n"
        "List any issues as bullet points."
    )
    ctx["review"] = call_openrouter("", prompt)
    return None


def build_graph() -> Graph:
    g = Graph()
    g.add_node(Node("entry", entry_node))
    g.add_node(Node("extraction", extraction_node))
    g.add_node(Node("interview", interview_node))
    g.add_node(Node("drafting", drafting_node))
    g.add_node(Node("diagramming", diagramming_node))
    g.add_node(Node("review", review_node))
    return g


def main():
    graph = build_graph()
    ctx = graph.run()
    print("\n--- final state ---")
    print(json.dumps(ctx, indent=2))


if __name__ == "__main__":
    main()
