"""
Full-text search engine for workstreams using Whoosh.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from whoosh import index
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import ID, KEYWORD, NUMERIC, TEXT, Schema
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.query import And, Or, Term
from whoosh.writing import AsyncWriter

from .types import Workstream


class SearchEngine:
    """Full-text search engine for workstreams."""

    def __init__(self, index_dir: str = "./data/search_index", profile: str = "test"):
        self.index_dir = Path(index_dir) / profile
        self.profile = profile
        self._index: index.Index | None = None
        self._schema = Schema(
            id=ID(stored=True, unique=True),
            name=TEXT(stored=True, analyzer=StemmingAnalyzer()),
            summary=TEXT(stored=True, analyzer=StemmingAnalyzer()),
            notes=TEXT(stored=True, analyzer=StemmingAnalyzer()),
            tags=KEYWORD(stored=True, commas=True, lowercase=True),
            parent_id=ID(stored=True),
            created_at=ID(stored=True),
            updated_at=ID(stored=True),
        )

    def _ensure_index(self) -> index.Index:
        """Ensure the search index exists, creating if necessary."""
        if self._index is not None:
            return self._index

        self.index_dir.mkdir(parents=True, exist_ok=True)

        if index.exists_in(str(self.index_dir)):
            self._index = index.open_dir(str(self.index_dir))
        else:
            self._index = index.create_in(str(self.index_dir), self._schema)

        return self._index

    def index_workstream(self, workstream: Workstream) -> None:
        """Index or update a single workstream."""
        idx = self._ensure_index()
        writer = AsyncWriter(idx)

        # Combine all notes into a single searchable text
        notes_text = " ".join(workstream.notes) if workstream.notes else ""

        writer.update_document(
            id=workstream.id,
            name=workstream.name,
            summary=workstream.summary,
            notes=notes_text,
            tags=",".join(workstream.tags) if workstream.tags else "",
            parent_id=workstream.parent_id or "",
            created_at=workstream.created_at,
            updated_at=workstream.updated_at,
        )
        writer.commit()

    def remove_workstream(self, workstream_id: str) -> None:
        """Remove a workstream from the index."""
        idx = self._ensure_index()
        writer = AsyncWriter(idx)
        writer.delete_by_term("id", workstream_id)
        writer.commit()

    def rebuild_index(self, workstreams: list[Workstream]) -> None:
        """Rebuild the entire index from scratch."""
        # Clear and recreate the index
        if self._index is not None:
            self._index.close()
            self._index = None

        # Remove existing index files
        if self.index_dir.exists():
            import shutil
            shutil.rmtree(self.index_dir)

        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._index = index.create_in(str(self.index_dir), self._schema)

        # Index all workstreams
        writer = self._index.writer()
        for ws in workstreams:
            notes_text = " ".join(ws.notes) if ws.notes else ""
            writer.add_document(
                id=ws.id,
                name=ws.name,
                summary=ws.summary,
                notes=notes_text,
                tags=",".join(ws.tags) if ws.tags else "",
                parent_id=ws.parent_id or "",
                created_at=ws.created_at,
                updated_at=ws.updated_at,
            )
        writer.commit()

    def search(
        self,
        query: str,
        limit: int = 20,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search workstreams with full-text search.

        Args:
            query: Search query string. Supports:
                   - Simple terms: "api deployment"
                   - AND/OR operators: "api AND deployment" or "api OR frontend"
                   - Phrase search: '"exact phrase"'
                   - Field-specific: "name:api" or "tags:python"
            limit: Maximum number of results to return
            fields: Fields to search (default: name, summary, notes, tags)

        Returns:
            List of dicts with workstream data, score, and highlights
        """
        idx = self._ensure_index()

        if fields is None:
            fields = ["name", "summary", "notes", "tags"]

        # Parse query - use OrGroup for default OR behavior between terms
        parser = MultifieldParser(fields, idx.schema, group=OrGroup)
        
        # Handle AND/OR operators in query
        parsed_query = parser.parse(query)

        results = []
        with idx.searcher() as searcher:
            hits = searcher.search(parsed_query, limit=limit)

            for hit in hits:
                result = {
                    "id": hit["id"],
                    "name": hit["name"],
                    "summary": hit["summary"],
                    "tags": hit["tags"].split(",") if hit["tags"] else [],
                    "parent_id": hit["parent_id"] if hit["parent_id"] else None,
                    "score": hit.score,
                    "highlights": {},
                }

                # Generate highlights for matched fields
                for field in fields:
                    if field in hit:
                        highlighted = hit.highlights(field, top=3)
                        if highlighted:
                            result["highlights"][field] = highlighted

                results.append(result)

        return results

    def close(self) -> None:
        """Close the search index."""
        if self._index is not None:
            self._index.close()
            self._index = None


# Global search engine instances per profile
_search_engines: dict[str, SearchEngine] = {}


def get_search_engine(profile: str = "test") -> SearchEngine:
    """Get or create a search engine for a profile."""
    if profile not in _search_engines:
        _search_engines[profile] = SearchEngine(profile=profile)
    return _search_engines[profile]
