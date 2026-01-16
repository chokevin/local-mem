"""
File-based storage for workstreams.
"""

from __future__ import annotations

import json
import os
import random
import string
import time
from pathlib import Path
from typing import Optional

from .types import (
    CreateWorkstreamRequest,
    UpdateWorkstreamRequest,
    Workstream,
    WorkstreamMetadata,
)


# Default profile
DEFAULT_PROFILE = "test"


class WorkstreamStorage:
    """File-based storage for workstreams."""

    def __init__(self, data_dir: str = "./data", profile: str | None = None):
        self.data_dir = Path(data_dir)
        self.profile = profile or DEFAULT_PROFILE
        self.data_file = self.data_dir / f"workstreams.{self.profile}.json"
        self._workstreams: dict[str, Workstream] = {}

    async def initialize(self) -> None:
        """Initialize storage by creating data directory and loading existing data."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            await self._load()
        except Exception as error:
            print(f"Failed to initialize storage: {error}")
            raise

    async def _load(self) -> None:
        """Load workstreams from file."""
        try:
            if self.data_file.exists():
                data = json.loads(self.data_file.read_text(encoding="utf-8"))
                self._workstreams = {w["id"]: Workstream.from_dict(w) for w in data}
            else:
                self._workstreams = {}
        except FileNotFoundError:
            self._workstreams = {}

    async def _save(self) -> None:
        """Save workstreams to file."""
        workstreams_list = [w.to_dict() for w in self._workstreams.values()]
        self.data_file.write_text(
            json.dumps(workstreams_list, indent=2), encoding="utf-8"
        )

    def _generate_id(self) -> str:
        """Generate a unique ID for a workstream."""
        random_part = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=9)
        )
        return f"ws-{int(time.time() * 1000)}-{random_part}"

    async def create(self, request: CreateWorkstreamRequest) -> Workstream:
        """Create a new workstream."""
        from datetime import datetime

        now = datetime.now().isoformat()
        metadata = WorkstreamMetadata.from_dict(request.metadata or {})

        workstream = Workstream(
            id=self._generate_id(),
            name=request.name,
            summary=request.summary,
            tags=request.tags or [],
            metadata=metadata,
            parent_id=request.parent_id,
            created_at=now,
            updated_at=now,
        )

        self._workstreams[workstream.id] = workstream
        await self._save()
        return workstream

    async def get(self, id: str) -> Optional[Workstream]:
        """Get a workstream by ID."""
        return self._workstreams.get(id)

    async def list(self) -> list[Workstream]:
        """List all workstreams."""
        return list(self._workstreams.values())

    async def update(self, request: UpdateWorkstreamRequest) -> Optional[Workstream]:
        """Update a workstream."""
        from datetime import datetime

        workstream = self._workstreams.get(request.id)
        if not workstream:
            return None

        # Update fields if provided
        if request.name is not None:
            workstream.name = request.name
        if request.summary is not None:
            workstream.summary = request.summary
        if request.tags is not None:
            workstream.tags = request.tags
        if request.metadata is not None:
            # Merge metadata
            existing_metadata = workstream.metadata.to_dict()
            existing_metadata.update(request.metadata)
            workstream.metadata = WorkstreamMetadata.from_dict(existing_metadata)
        if request.parent_id is not None:
            # Allow empty string to clear parent
            workstream.parent_id = request.parent_id if request.parent_id else None

        workstream.updated_at = datetime.now().isoformat()

        self._workstreams[workstream.id] = workstream
        await self._save()
        return workstream

    async def delete(self, id: str) -> bool:
        """Delete a workstream."""
        if id in self._workstreams:
            del self._workstreams[id]
            await self._save()
            return True
        return False

    async def add_tags(self, id: str, tags: list[str]) -> Optional[Workstream]:
        """Add tags to a workstream."""
        from datetime import datetime

        workstream = self._workstreams.get(id)
        if not workstream:
            return None

        # Add unique tags
        unique_tags = set(workstream.tags)
        unique_tags.update(tags)
        workstream.tags = list(unique_tags)
        workstream.updated_at = datetime.now().isoformat()

        self._workstreams[workstream.id] = workstream
        await self._save()
        return workstream

    async def search_by_tags(
        self, tags: list[str], match_all: bool = False
    ) -> list[Workstream]:
        """Search workstreams by tags."""
        workstreams_list = list(self._workstreams.values())

        if match_all:
            # Match all tags
            return [w for w in workstreams_list if all(tag in w.tags for tag in tags)]
        else:
            # Match any tag
            return [w for w in workstreams_list if any(tag in w.tags for tag in tags)]

    async def search(self, query: str) -> list[Workstream]:
        """Search workstreams by name or summary."""
        workstreams_list = list(self._workstreams.values())
        lower_query = query.lower()

        return [
            w
            for w in workstreams_list
            if lower_query in w.name.lower() or lower_query in w.summary.lower()
        ]

    async def add_note(self, id: str, note: str) -> Optional[Workstream]:
        """Add a note to a workstream."""
        from datetime import datetime

        workstream = self._workstreams.get(id)
        if not workstream:
            return None

        # Add timestamped note
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        workstream.notes.append(f"[{timestamp}] {note}")
        workstream.updated_at = datetime.now().isoformat()

        self._workstreams[workstream.id] = workstream
        await self._save()
        return workstream

    async def get_notes(self, id: str) -> Optional[list[str]]:
        """Get all notes for a workstream."""
        workstream = self._workstreams.get(id)
        if not workstream:
            return None
        return workstream.notes

    async def set_parent(self, id: str, parent_id: str | None) -> Optional[Workstream]:
        """Set or clear the parent of a workstream."""
        from datetime import datetime

        workstream = self._workstreams.get(id)
        if not workstream:
            return None

        # Validate parent exists if provided
        if parent_id and parent_id not in self._workstreams:
            return None

        # Prevent circular references
        if parent_id:
            current = parent_id
            while current:
                if current == id:
                    return None  # Would create a cycle
                parent_ws = self._workstreams.get(current)
                current = parent_ws.parent_id if parent_ws else None

        workstream.parent_id = parent_id
        workstream.updated_at = datetime.now().isoformat()
        self._workstreams[workstream.id] = workstream
        await self._save()
        return workstream

    async def get_children(self, parent_id: str) -> list[Workstream]:
        """Get all direct children of a workstream."""
        return [ws for ws in self._workstreams.values() if ws.parent_id == parent_id]

    async def get_tree(self) -> dict:
        """
        Build a tree structure from all workstreams.

        Returns a dict with:
        - roots: list of workstreams with no parent
        - children: dict mapping parent_id -> list of children
        """
        from .heuristics import build_tree

        return build_tree(list(self._workstreams.values()))

    async def suggest_relationships(self) -> list:
        """Suggest relationships between workstreams using heuristics."""
        from .heuristics import suggest_relationships

        return suggest_relationships(list(self._workstreams.values()))
