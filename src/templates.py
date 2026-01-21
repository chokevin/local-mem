"""
Workstream templates for reusable workstream configurations.
"""

from __future__ import annotations

import json
import random
import string
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .storage import DEFAULT_PROFILE, WorkstreamStorage
from .types import CreateWorkstreamRequest, Workstream, WorkstreamMetadata


@dataclass
class WorkstreamTemplate:
    """A reusable template for creating workstreams."""

    id: str
    name: str
    description: str
    default_tags: list[str] = field(default_factory=list)
    default_metadata: dict[str, Any] = field(default_factory=dict)
    note_templates: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "defaultTags": self.default_tags,
            "defaultMetadata": self.default_metadata,
            "noteTemplates": self.note_templates,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkstreamTemplate":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            default_tags=data.get("defaultTags", []),
            default_metadata=data.get("defaultMetadata", {}),
            note_templates=data.get("noteTemplates", []),
            created_at=data.get("createdAt", datetime.now().isoformat()),
            updated_at=data.get("updatedAt", datetime.now().isoformat()),
        )


@dataclass
class CreateTemplateRequest:
    """Request to create a new template."""

    name: str
    description: str
    default_tags: list[str] = field(default_factory=list)
    default_metadata: dict[str, Any] = field(default_factory=dict)
    note_templates: list[str] = field(default_factory=list)


@dataclass
class InstantiateTemplateRequest:
    """Request to create a workstream from a template."""

    template_id: str
    name: str  # Required: workstream name
    summary: str  # Required: workstream summary
    additional_tags: list[str] = field(default_factory=list)
    metadata_overrides: dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None


class TemplateStorage:
    """File-based storage for workstream templates."""

    def __init__(self, data_dir: str = "./data", profile: str | None = None):
        self.data_dir = Path(data_dir)
        self.profile = profile or DEFAULT_PROFILE
        self.data_file = self.data_dir / f"templates.{self.profile}.json"
        self._templates: dict[str, WorkstreamTemplate] = {}

    async def initialize(self) -> None:
        """Initialize storage by creating data directory and loading existing data."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            await self._load()
        except Exception as error:
            print(f"Failed to initialize template storage: {error}")
            raise

    async def _load(self) -> None:
        """Load templates from file."""
        try:
            if self.data_file.exists():
                data = json.loads(self.data_file.read_text(encoding="utf-8"))
                self._templates = {
                    t["id"]: WorkstreamTemplate.from_dict(t) for t in data
                }
            else:
                self._templates = {}
        except FileNotFoundError:
            self._templates = {}

    async def _save(self) -> None:
        """Save templates to file."""
        templates_list = [t.to_dict() for t in self._templates.values()]
        self.data_file.write_text(
            json.dumps(templates_list, indent=2), encoding="utf-8"
        )

    def _generate_id(self) -> str:
        """Generate a unique ID for a template."""
        random_part = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=9)
        )
        return f"tmpl-{int(time.time() * 1000)}-{random_part}"

    async def create_template(
        self, request: CreateTemplateRequest
    ) -> WorkstreamTemplate:
        """Create a new template."""
        now = datetime.now().isoformat()

        template = WorkstreamTemplate(
            id=self._generate_id(),
            name=request.name,
            description=request.description,
            default_tags=request.default_tags or [],
            default_metadata=request.default_metadata or {},
            note_templates=request.note_templates or [],
            created_at=now,
            updated_at=now,
        )

        self._templates[template.id] = template
        await self._save()
        return template

    async def get_template(self, id: str) -> Optional[WorkstreamTemplate]:
        """Get a template by ID."""
        return self._templates.get(id)

    async def list_templates(self) -> list[WorkstreamTemplate]:
        """List all templates."""
        return list(self._templates.values())

    async def delete_template(self, id: str) -> bool:
        """Delete a template."""
        if id in self._templates:
            del self._templates[id]
            await self._save()
            return True
        return False

    async def create_from_template(
        self,
        request: InstantiateTemplateRequest,
        workstream_storage: WorkstreamStorage,
    ) -> Optional[Workstream]:
        """Create a workstream from a template.

        Args:
            request: The instantiation request with template ID and overrides
            workstream_storage: The storage to create the workstream in

        Returns:
            The created workstream, or None if template not found
        """
        template = self._templates.get(request.template_id)
        if not template:
            return None

        # Merge tags: template defaults + additional tags
        merged_tags = list(set(template.default_tags + request.additional_tags))

        # Merge metadata: template defaults + overrides
        merged_metadata = {**template.default_metadata, **request.metadata_overrides}

        # Create the workstream
        ws_request = CreateWorkstreamRequest(
            name=request.name,
            summary=request.summary,
            tags=merged_tags,
            metadata=merged_metadata,
            parent_id=request.parent_id,
        )

        workstream = await workstream_storage.create(ws_request)

        # Add note templates as initial notes
        for note_template in template.note_templates:
            await workstream_storage.add_note(workstream.id, note_template)

        # Refresh to get updated workstream with notes
        return await workstream_storage.get(workstream.id)
