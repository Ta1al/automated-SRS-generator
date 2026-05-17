"""
LangGraph SRS generator workflow.

Architecture:
1. Ingestion: Parse informal input, extract domain/actors
2. Elicitation: Interactive Q&A with 4 grouped batches
3. Drafting: Synthesize into formal SRS sections
4. Diagram generation & finalization
"""

from app.graph.graph import build_graph
from app.graph.state import SRSState

__all__ = ["build_graph", "SRSState"]
