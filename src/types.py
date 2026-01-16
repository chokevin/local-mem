"""
Types and data models for the local-mem MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class WorkstreamMetadata:
    """Metadata for a workstream containing key project information."""

    host_ips: list[str] = field(default_factory=list)
    connection_info: Optional[str] = None
    testing_info: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {}
        if self.host_ips:
            result["hostIps"] = self.host_ips
        if self.connection_info:
            result["connectionInfo"] = self.connection_info
        if self.testing_info:
            result["testingInfo"] = self.testing_info
        result.update(self.extra)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkstreamMetadata":
        return cls(
            host_ips=data.get("hostIps", []),
            connection_info=data.get("connectionInfo"),
            testing_info=data.get("testingInfo"),
            extra={
                k: v
                for k, v in data.items()
                if k not in ("hostIps", "connectionInfo", "testingInfo")
            },
        )


@dataclass
class Workstream:
    """Represents a workstream - a segment of work with associated metadata."""

    id: str
    name: str
    summary: str
    tags: list[str] = field(default_factory=list)
    metadata: WorkstreamMetadata = field(default_factory=WorkstreamMetadata)
    notes: list[str] = field(default_factory=list)  # Rich context notes
    parent_id: Optional[str] = None  # Parent workstream ID for hierarchy
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "tags": self.tags,
            "metadata": self.metadata.to_dict(),
            "notes": self.notes,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.parent_id:
            result["parentId"] = self.parent_id
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workstream":
        return cls(
            id=data["id"],
            name=data["name"],
            summary=data["summary"],
            tags=data.get("tags", []),
            metadata=WorkstreamMetadata.from_dict(data.get("metadata", {})),
            notes=data.get("notes", []),
            parent_id=data.get("parentId"),
            created_at=data.get("createdAt", datetime.now().isoformat()),
            updated_at=data.get("updatedAt", datetime.now().isoformat()),
        )


@dataclass
class CreateWorkstreamRequest:
    """Request to create a new workstream."""

    name: str
    summary: str
    tags: list[str] = field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None
    parent_id: Optional[str] = None  # Parent workstream ID


@dataclass
class UpdateWorkstreamRequest:
    """Request to update an existing workstream."""

    id: str
    name: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None
    parent_id: Optional[str] = None  # Can reassign parent


@dataclass
class RelationshipSuggestion:
    """A suggested relationship between workstreams."""

    source_id: str
    target_id: str
    relationship_type: str  # "parent", "child", "related", "similar"
    confidence: float  # 0.0 to 1.0
    reason: str  # Human-readable explanation


@dataclass
class SearchByTagsRequest:
    """Request to search workstreams by tags."""

    tags: list[str]
    match_all: bool = False  # If true, match all tags; if false, match any tag
