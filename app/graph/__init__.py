"""
LangGraph SRS generator workflow.

5-Phase Architecture:
1. Ingestion: Parse informal input, extract domain/actors
2. Elicitation: Interactive Q&A with 4 grouped batches
3. Outline Review: Generate IEEE 830 outline, user approval
4. Drafting: Synthesize into formal SRS sections
5. Review & Refine: User edits, regeneration, finalization
"""

from app.graph.graph import build_graph
from app.graph.state import SRSState

__all__ = ["build_graph", "SRSState"]
