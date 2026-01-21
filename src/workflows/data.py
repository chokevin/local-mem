"""
Data classes for Temporal workflows.

These are kept separate from activities to allow workflows to import them
without triggering sandbox restrictions from activity dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..storage import DEFAULT_PROFILE


@dataclass
class IndexGitHubRepoInput:
    """Input for GitHub repo indexing activity."""

    owner: str
    repo: str
    profile: str = DEFAULT_PROFILE


@dataclass
class IndexLocalRepoInput:
    """Input for local repo indexing activity."""

    repo_path: str
    profile: str = DEFAULT_PROFILE


@dataclass
class IndexResult:
    """Result from an indexing activity."""

    success: bool
    workstream_id: str | None = None
    workstream_name: str | None = None
    error: str | None = None
    notes_added: int = 0
    services_indexed: int = 0
