from typing import Protocol, List, Dict, Any
from graph.store import GraphStore

class Rule(Protocol):
    def __call__(self, store: GraphStore) -> List[Dict[str, Any]]:
        ...

SEVERITY = ("low","medium","high")
