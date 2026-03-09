# lightweight state-machine helper used by graph_controller.py
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


class Node:
    def __init__(
        self,
        name: str,
        func: Callable[["Graph", Dict[str, Any]], Optional[str]],
    ):
        self.name = name
        self.func = func


class Graph:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.start: Optional[str] = None

    def add_node(self, node: Node):
        self.nodes[node.name] = node
        if self.start is None:
            self.start = node.name

    def run(self, context: Dict[str, Any] = None) -> Dict[str, Any]:
        if context is None:
            context = {}
        current = self.start
        while current:
            node = self.nodes[current]
            next_node = node.func(self, context)
            current = next_node
        return context
