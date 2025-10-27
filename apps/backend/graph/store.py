from __future__ import annotations
from typing import Dict, Any, Optional
import networkx as nx


class GraphStore:
    """Simple property multi-digraph using networkx."""
    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()

    def add_node(self, node_id: str, type: str, props: Optional[Dict[str, Any]] = None, labels=None):
        if props is None: props = {}
        self.g.add_node(node_id, type=type, props=props, labels=labels or [])

    def update_node(self, node_id: str, props: Dict[str, Any]):
        if node_id in self.g.nodes:
            cur = self.g.nodes[node_id].get("props", {})
            cur.update(props or {})
            self.g.nodes[node_id]["props"] = cur

    def remove_node(self, node_id: str):
        if node_id in self.g.nodes:
            self.g.remove_node(node_id)

    def add_edge(self, edge_id: str, type: str, from_id: str, to_id: str, props=None):
        if props is None: props = {}
        self.g.add_edge(from_id, to_id, key=edge_id, type=type, props=props)

    def update_edge(self, edge_id: str, from_id: str, to_id: str, props=None):
        # naive: remove+add
        self.remove_edge(edge_id)
        self.add_edge(edge_id, "updated", from_id, to_id, props or {})

    def remove_edge(self, edge_id: str):
        # search by key
        edges = list(self.g.edges(keys=True))
        for u,v,k in edges:
            if k == edge_id:
                self.g.remove_edge(u,v,k)

    def nodes_by_type(self, type_name: str):
        return [n for n,d in self.g.nodes(data=True) if d.get("type")==type_name]

    def node_props(self, node_id: str) -> Dict[str, Any]:
        return self.g.nodes[node_id].get("props", {}) if node_id in self.g.nodes else {}

    def has_node(self, node_id: str) -> bool:
        return node_id in self.g.nodes

    def edges_iter(self):
        return self.g.edges(keys=True, data=True)
