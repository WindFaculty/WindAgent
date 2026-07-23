"""
Repository Intelligence Index & Retrieval Port for WindAgent Context Package.
Manages symbol graph, dependency lookup, code retrieval, and stale context detection.
"""

from __future__ import annotations
import logging
from typing import Dict, List

from windagent_context.provenance import ContextItem, ContextItemProvenance
from windagent_context.budget import estimate_tokens

logger = logging.getLogger("windagent.context.repository")


class RepositoryIndex:
    def __init__(self):
        self._symbols: Dict[str, Dict[str, Any]] = {}
        self._file_mtimes: Dict[str, float] = {}

    def add_symbol(self, symbol_name: str, file_path: str, line_range: str, content: str, mtime: float = 1.0) -> None:
        self._symbols[symbol_name] = {
            "symbol_name": symbol_name,
            "file_path": file_path,
            "line_range": line_range,
            "content": content,
            "mtime": mtime,
        }
        self._file_mtimes[file_path] = mtime

    def is_stale(self, file_path: str, current_mtime: float) -> bool:
        known = self._file_mtimes.get(file_path)
        if known is None:
            return True
        return current_mtime > known

    def retrieve_symbol(self, query: str, max_results: int = 5) -> List[ContextItem]:
        """Retrieves symbols matching query pattern with provenance metadata."""
        results: List[ContextItem] = []
        query_lower = query.lower()

        for name, data in self._symbols.items():
            if query_lower in name.lower() or query_lower in data["content"].lower():
                cost = estimate_tokens(data["content"])
                prov = ContextItemProvenance(
                    source="repository_index",
                    file_path=data["file_path"],
                    line_range=data["line_range"],
                    retrieval_reason=f"Matched symbol search query '{query}'",
                    token_cost=cost,
                    freshness=1.0,
                    confidence=0.9,
                )
                item = ContextItem(
                    item_id=f"sym_{name}",
                    content=data["content"],
                    provenance=prov,
                )
                results.append(item)
                if len(results) >= max_results:
                    break

        return results
