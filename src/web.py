"""
Web UI for viewing workstreams.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import Body, Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from .storage import DEFAULT_PROFILE, WorkstreamStorage
from .templates import (
    CreateTemplateRequest,
    InstantiateTemplateRequest,
    TemplateStorage,
)
from .types import CreateWorkstreamRequest, UpdateWorkstreamRequest


# Pydantic models for REST API request/response validation
class WorkstreamMetadataModel(BaseModel):
    """Pydantic model for workstream metadata."""

    host_ips: list[str] = Field(default_factory=list, alias="hostIps")
    connection_info: str | None = Field(default=None, alias="connectionInfo")
    testing_info: str | None = Field(default=None, alias="testingInfo")

    model_config = {"extra": "allow", "populate_by_name": True}


class WorkstreamResponse(BaseModel):
    """Pydantic model for workstream response."""

    id: str
    name: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    parent_id: str | None = Field(default=None, alias="parentId")
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")
    blocks: list[str] = Field(default_factory=list)
    related_to: list[str] = Field(default_factory=list, alias="relatedTo")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class CreateWorkstreamModel(BaseModel):
    """Pydantic model for creating a workstream."""

    name: str = Field(..., min_length=1, description="Name of the workstream")
    summary: str = Field(..., description="Summary/description of the workstream")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")
    parent_id: str | None = Field(
        default=None, alias="parentId", description="Parent workstream ID"
    )

    model_config = {"populate_by_name": True}


class UpdateWorkstreamModel(BaseModel):
    """Pydantic model for updating a workstream."""

    name: str | None = Field(default=None, min_length=1, description="New name")
    summary: str | None = Field(default=None, description="New summary")
    tags: list[str] | None = Field(default=None, description="New tags")
    metadata: dict[str, Any] | None = Field(default=None, description="New metadata")
    parent_id: str | None = Field(default=None, alias="parentId", description="New parent ID")

    model_config = {"populate_by_name": True}


class AddNoteModel(BaseModel):
    """Pydantic model for adding a note."""

    note: str = Field(..., min_length=1, description="Note content")
    category: str | None = Field(
        default=None,
        description="Note category (decision, blocker, changed, context, tried, resume, other)",
    )


class UpdateNoteModel(BaseModel):
    """Pydantic model for updating a note."""

    content: str = Field(..., min_length=1, description="New note content")
    category: str | None = Field(
        default=None,
        description="Note category (decision, blocker, changed, context, tried, resume, other)",
    )


class SearchModel(BaseModel):
    """Pydantic model for search requests."""

    query: str | None = Field(default=None, description="Text search query")
    tags: list[str] | None = Field(default=None, description="Tags to search for")
    match_all: bool = Field(
        default=False, alias="matchAll", description="Match all tags (AND) vs any (OR)"
    )

    model_config = {"populate_by_name": True}


# Pydantic models for Template API
class TemplateResponse(BaseModel):
    """Pydantic model for template response."""

    id: str
    name: str
    description: str
    default_tags: list[str] = Field(default_factory=list, alias="defaultTags")
    default_metadata: dict[str, Any] = Field(default_factory=dict, alias="defaultMetadata")
    note_templates: list[str] = Field(default_factory=list, alias="noteTemplates")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class CreateTemplateModel(BaseModel):
    """Pydantic model for creating a template."""

    name: str = Field(..., min_length=1, description="Template name")
    description: str = Field(..., description="Template description")
    default_tags: list[str] = Field(
        default_factory=list, alias="defaultTags", description="Default tags for workstreams"
    )
    default_metadata: dict[str, Any] = Field(
        default_factory=dict, alias="defaultMetadata", description="Default metadata"
    )
    note_templates: list[str] = Field(
        default_factory=list, alias="noteTemplates", description="Initial note templates"
    )

    model_config = {"populate_by_name": True}


class InstantiateTemplateModel(BaseModel):
    """Pydantic model for instantiating a template."""

    name: str = Field(..., min_length=1, description="Workstream name")
    summary: str = Field(..., description="Workstream summary")
    additional_tags: list[str] = Field(
        default_factory=list, alias="additionalTags", description="Additional tags"
    )
    metadata_overrides: dict[str, Any] = Field(
        default_factory=dict, alias="metadataOverrides", description="Metadata overrides"
    )
    parent_id: str | None = Field(
        default=None, alias="parentId", description="Parent workstream ID"
    )

    model_config = {"populate_by_name": True}


class AddRelationshipModel(BaseModel):
    """Pydantic model for adding a relationship."""

    target_id: str = Field(..., alias="targetId", description="Target workstream ID")
    relationship_type: str = Field(
        ...,
        alias="relationshipType",
        description="Relationship type: depends_on, blocks, or related_to",
    )

    model_config = {"populate_by_name": True}


class RelationshipsResponse(BaseModel):
    """Pydantic model for relationships response."""

    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")
    blocks: list[str] = Field(default_factory=list)
    related_to: list[str] = Field(default_factory=list, alias="relatedTo")
    blocked_by: list[str] = Field(default_factory=list, alias="blockedBy")
    dependents: list[str] = Field(default_factory=list)
    related_from: list[str] = Field(default_factory=list, alias="relatedFrom")

    model_config = {"populate_by_name": True}


# Cookie name for profile persistence
PROFILE_COOKIE = "workstream_profile"

# Available profiles
PROFILES = ["test", "prod"]

app = FastAPI(title="Workstream Dashboard")

# Storage instances for each profile
_storages: dict[str, WorkstreamStorage] = {}
_template_storages: dict[str, TemplateStorage] = {}


def get_storage(profile: str) -> WorkstreamStorage:
    """Get or create storage for a profile."""
    if profile not in _storages:
        _storages[profile] = WorkstreamStorage(profile=profile)
    return _storages[profile]


def get_template_storage(profile: str) -> TemplateStorage:
    """Get or create template storage for a profile."""
    if profile not in _template_storages:
        _template_storages[profile] = TemplateStorage(profile=profile)
    return _template_storages[profile]


def get_dashboard_html(current_profile: str) -> str:
    """Return the dashboard HTML with map visualization."""
    # Build profile selector options
    profile_options = "".join(
        f'<option value="{p}" {"selected" if p == current_profile else ""}>{p.title()}</option>'
        for p in PROFILES
    )

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Workstream Clusters - {current_profile.title()}</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10/dist/ext/sse.js"></script>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            min-height: 100vh;
            overflow: hidden;
        }}
        
        #graph {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }}
        
        .header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 100;
            padding: 1rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: linear-gradient(to bottom, rgba(13,17,23,0.95) 0%, rgba(13,17,23,0) 100%);
            pointer-events: none;
        }}
        
        .header > * {{ pointer-events: auto; }}
        
        .header-left {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        
        h1 {{
            font-size: 1.25rem;
            font-weight: 600;
            color: #f0f6fc;
        }}
        
        .profile-badge {{
            background: {("#3fb950" if current_profile == "prod" else "#58a6ff")}33;
            color: {"#3fb950" if current_profile == "prod" else "#58a6ff"};
            padding: 0.25rem 0.75rem;
            border-radius: 2rem;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .controls {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        
        /* Focus Selector (workstreams) */
        .focus-selector {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .focus-selector label {{
            font-size: 0.8rem;
            color: #8b949e;
        }}
        
        .focus-selector select {{
            background: #21262d;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #c9d1d9;
            padding: 0.5rem 0.75rem;
            font-size: 0.85rem;
            cursor: pointer;
            min-width: 200px;
        }}
        
        .focus-selector select:hover {{
            border-color: #58a6ff;
        }}
        
        /* Floating Action Button for Indexing */
        .fab {{
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            width: 56px;
            height: 56px;
            border-radius: 50%;
            background: linear-gradient(135deg, #238636, #2ea043);
            border: none;
            color: white;
            font-size: 1.5rem;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(35, 134, 54, 0.4);
            z-index: 200;
            transition: transform 0.2s, box-shadow 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .fab:hover {{
            transform: scale(1.1);
            box-shadow: 0 6px 20px rgba(35, 134, 54, 0.6);
        }}
        
        .fab:active {{
            transform: scale(0.95);
        }}
        
        /* Index Modal */
        .modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            z-index: 300;
            display: none;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(4px);
        }}
        
        .modal-overlay.active {{
            display: flex;
            animation: fadeIn 0.2s ease-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        
        .modal {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            width: 90%;
            max-width: 500px;
            max-height: 80vh;
            overflow: hidden;
            animation: slideUp 0.3s ease-out;
        }}
        
        @keyframes slideUp {{
            from {{ transform: translateY(20px); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}
        
        .modal-header {{
            padding: 1rem 1.5rem;
            border-bottom: 1px solid #30363d;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .modal-header h2 {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #f0f6fc;
        }}
        
        .modal-close {{
            background: none;
            border: none;
            color: #8b949e;
            font-size: 1.5rem;
            cursor: pointer;
            padding: 0;
            line-height: 1;
        }}
        
        .modal-close:hover {{
            color: #f0f6fc;
        }}
        
        .modal-body {{
            padding: 1rem;
            max-height: 60vh;
            overflow-y: auto;
        }}
        
        .repo-list {{
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}
        
        .repo-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            background: #21262d;
            border: 1px solid #30363d;
            border-radius: 8px;
            transition: border-color 0.2s;
        }}
        
        .repo-item:hover {{
            border-color: #58a6ff;
        }}
        
        .repo-item.indexing {{
            border-color: #58a6ff;
            background: rgba(88, 166, 255, 0.1);
        }}
        
        .repo-info {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        
        .repo-icon {{
            font-size: 1.2rem;
        }}
        
        .repo-name {{
            font-weight: 500;
            color: #c9d1d9;
        }}
        
        .repo-status {{
            font-size: 0.75rem;
            color: #8b949e;
        }}
        
        .repo-status.indexed {{
            color: #3fb950;
        }}
        
        .repo-action {{
            background: #238636;
            border: none;
            border-radius: 6px;
            color: white;
            padding: 0.4rem 0.75rem;
            font-size: 0.75rem;
            cursor: pointer;
            transition: background 0.2s;
        }}
        
        .repo-action:hover {{
            background: #2ea043;
        }}
        
        .repo-action.reindex {{
            background: #21262d;
            border: 1px solid #30363d;
        }}
        
        .repo-action.reindex:hover {{
            background: #30363d;
        }}
        
        .repo-action:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        
        .repo-item-info {{
            flex: 1;
            min-width: 0;
        }}
        
        .repo-item-name {{
            font-weight: 500;
            color: #c9d1d9;
            margin-bottom: 0.25rem;
        }}
        
        .repo-item-path {{
            font-size: 0.75rem;
            color: #6e7681;
            font-family: 'SF Mono', Monaco, monospace;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        
        .repo-item-action {{
            background: #238636;
            border: none;
            border-radius: 6px;
            color: white;
            padding: 0.5rem 1rem;
            font-size: 0.8rem;
            cursor: pointer;
            transition: background 0.2s;
            white-space: nowrap;
        }}
        
        .repo-item-action:hover {{
            background: #2ea043;
        }}
        
        .repo-item-action:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        
        .repo-item.indexed {{
            border-color: #3fb950;
        }}
        
        .repo-item.indexed .repo-item-name {{
            color: #3fb950;
        }}
        
        .repo-item.indexed .repo-item-action {{
            background: #21262d;
            border: 1px solid #30363d;
            color: #8b949e;
        }}
        
        .repo-item.indexed .repo-item-action:hover {{
            background: #30363d;
            color: #c9d1d9;
        }}
        
        /* ============== Focus Mode ============== */
        .focus-mode .graph-node:not(.focused) {{
            opacity: 0.2;
            transition: opacity 0.5s ease;
        }}
        
        .focus-mode .graph-node.focused {{
            opacity: 1;
            transform: scale(1.5);
            transition: all 0.5s ease;
        }}
        
        .focus-mode .graph-link:not(.focused) {{
            opacity: 0.1;
        }}
        
        .focus-mode .graph-link.focused {{
            opacity: 1;
            stroke-width: 3px;
        }}
        
        /* Focus Panel - Full height overlay */
        .focus-panel {{
            position: fixed;
            top: 0;
            left: 0;
            width: 480px;
            height: 100vh;
            background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
            border-right: 1px solid #30363d;
            z-index: 250;
            transform: translateX(-100%);
            transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        
        .focus-panel.visible {{
            transform: translateX(0);
        }}
        
        .focus-panel-header {{
            padding: 1.5rem;
            border-bottom: 1px solid #30363d;
            background: rgba(22, 27, 34, 0.8);
            backdrop-filter: blur(10px);
        }}
        
        .focus-panel-header h2 {{
            font-size: 1.4rem;
            font-weight: 600;
            color: #f0f6fc;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        
        .focus-panel-close {{
            position: absolute;
            top: 1.25rem;
            right: 1.25rem;
            background: transparent;
            border: 1px solid #30363d;
            color: #8b949e;
            cursor: pointer;
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.25rem;
            transition: all 0.2s;
        }}
        
        .focus-panel-close:hover {{
            background: #21262d;
            color: #f0f6fc;
            border-color: #8b949e;
        }}
        
        .focus-type-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.3rem 0.6rem;
            border-radius: 4px;
            font-size: 0.65rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .focus-type-badge.program {{
            background: rgba(240, 136, 62, 0.2);
            color: #f0883e;
        }}
        
        .focus-type-badge.project {{
            background: rgba(88, 166, 255, 0.2);
            color: #58a6ff;
        }}
        
        .focus-type-badge.task {{
            background: rgba(163, 113, 247, 0.2);
            color: #a371f7;
        }}
        
        .focus-panel-body {{
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
        }}
        
        .focus-section {{
            margin-bottom: 1.5rem;
        }}
        
        .focus-section-title {{
            font-size: 0.7rem;
            font-weight: 600;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .focus-section-title .add-btn {{
            margin-left: auto;
            background: #238636;
            border: none;
            border-radius: 4px;
            color: white;
            width: 20px;
            height: 20px;
            font-size: 1rem;
            line-height: 1;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }}
        
        .focus-section-title .add-btn:hover {{
            background: #2ea043;
        }}
        
        .todo-add-form {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 0.75rem;
            padding: 0.5rem;
            background: rgba(33, 38, 45, 0.8);
            border-radius: 6px;
            border: 1px solid #30363d;
        }}
        
        .todo-add-form input {{
            flex: 1;
            background: #21262d;
            border: 1px solid #30363d;
            border-radius: 4px;
            color: #c9d1d9;
            padding: 0.4rem 0.6rem;
            font-size: 0.85rem;
        }}
        
        .todo-add-form input:focus {{
            outline: none;
            border-color: #58a6ff;
        }}
        
        .todo-add-form button {{
            background: #238636;
            border: none;
            border-radius: 4px;
            color: white;
            padding: 0.4rem 0.75rem;
            font-size: 0.8rem;
            cursor: pointer;
        }}
        
        .todo-add-form button:last-child {{
            background: #21262d;
            border: 1px solid #30363d;
            color: #8b949e;
        }}
        
        .todo-add-form button:hover {{
            opacity: 0.9;
        }}
        
        .focus-summary {{
            font-size: 0.9rem;
            color: #c9d1d9;
            line-height: 1.6;
            padding: 0.75rem;
            background: rgba(33, 38, 45, 0.5);
            border-radius: 8px;
            border: 1px solid #30363d;
        }}
        
        .focus-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        
        .focus-tag {{
            background: #21262d;
            color: #8b949e;
            padding: 0.35rem 0.65rem;
            border-radius: 4px;
            font-size: 0.75rem;
            border: 1px solid #30363d;
        }}
        
        /* Activity/Commits */
        .activity-list {{
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}
        
        .activity-item {{
            padding: 0.75rem;
            background: rgba(33, 38, 45, 0.5);
            border: 1px solid #30363d;
            border-radius: 8px;
            transition: border-color 0.2s;
        }}
        
        .activity-item:hover {{
            border-color: #58a6ff;
        }}
        
        .activity-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.4rem;
        }}
        
        .activity-sha {{
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.75rem;
            color: #58a6ff;
        }}
        
        .activity-time {{
            font-size: 0.7rem;
            color: #6e7681;
        }}
        
        .activity-message {{
            font-size: 0.85rem;
            color: #c9d1d9;
            line-height: 1.4;
        }}
        
        .activity-author {{
            font-size: 0.7rem;
            color: #8b949e;
            margin-top: 0.3rem;
        }}
        
        /* Connections */
        .connection-list {{
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }}
        
        .connection-item {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.6rem 0.75rem;
            background: rgba(33, 38, 45, 0.5);
            border: 1px solid #30363d;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .connection-item:hover {{
            background: rgba(33, 38, 45, 0.8);
            border-color: #58a6ff;
        }}
        
        .connection-type {{
            font-size: 0.65rem;
            color: #8b949e;
            text-transform: uppercase;
            min-width: 60px;
        }}
        
        .connection-name {{
            font-size: 0.85rem;
            color: #c9d1d9;
            flex: 1;
        }}
        
        /* TODOs */
        .todo-list {{
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }}
        
        .todo-item {{
            display: flex;
            align-items: flex-start;
            gap: 0.5rem;
            padding: 0.5rem 0.75rem;
            background: rgba(33, 38, 45, 0.5);
            border: 1px solid #30363d;
            border-radius: 6px;
        }}
        
        .todo-checkbox {{
            color: #6e7681;
            font-size: 0.9rem;
        }}
        
        .todo-text {{
            font-size: 0.85rem;
            color: #c9d1d9;
        }}
        
        .empty-section {{
            color: #6e7681;
            font-size: 0.8rem;
            font-style: italic;
            padding: 0.5rem;
        }}
        
        .show-more-btn {{
            width: 100%;
            padding: 0.5rem;
            margin-top: 0.5rem;
            background: #21262d;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #58a6ff;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .show-more-btn:hover {{
            background: #30363d;
            border-color: #58a6ff;
        }}
        
        /* Branch list */
        .branch-list {{
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }}
        
        .branch-item {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 0.75rem;
            background: rgba(33, 38, 45, 0.5);
            border: 1px solid #30363d;
            border-radius: 6px;
        }}
        
        .branch-item.current {{
            border-color: #3fb950;
            background: rgba(63, 185, 80, 0.1);
        }}
        
        .branch-icon {{
            font-size: 0.9rem;
        }}
        
        .branch-name {{
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.8rem;
            color: #c9d1d9;
            flex: 1;
        }}
        
        .branch-item.current .branch-name {{
            color: #3fb950;
        }}
        
        .branch-time {{
            font-size: 0.7rem;
            color: #6e7681;
        }}
        
        .repo-action.loading {{
            position: relative;
            color: transparent;
            pointer-events: none;
        }}
        
        .repo-action.loading::after {{
            content: "";
            position: absolute;
            width: 12px;
            height: 12px;
            top: 50%;
            left: 50%;
            margin: -6px 0 0 -6px;
            border: 2px solid #fff;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}
        
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        
        /* Indexing Status Panel */
        .indexing-panel {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 350px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
            z-index: 1000;
            overflow: hidden;
            display: none;
        }}
        
        .indexing-panel.active {{
            display: block;
            animation: slideIn 0.3s ease-out;
        }}
        
        @keyframes slideIn {{
            from {{ transform: translateY(20px); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}
        
        .indexing-header {{
            background: #21262d;
            padding: 12px 16px;
            border-bottom: 1px solid #30363d;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .indexing-header h3 {{
            margin: 0;
            font-size: 0.9rem;
            color: #f0f6fc;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .indexing-header .spinner {{
            width: 14px;
            height: 14px;
            border: 2px solid #30363d;
            border-top-color: #58a6ff;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}
        
        .indexing-timer {{
            font-family: monospace;
            font-size: 0.85rem;
            color: #8b949e;
        }}
        
        .indexing-body {{
            padding: 12px 16px;
            max-height: 200px;
            overflow-y: auto;
        }}
        
        .indexing-step {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 6px 0;
            font-size: 0.8rem;
            color: #8b949e;
        }}
        
        .indexing-step.active {{
            color: #c9d1d9;
        }}
        
        .indexing-step.done {{
            color: #3fb950;
        }}
        
        .indexing-step .icon {{
            width: 16px;
            text-align: center;
            flex-shrink: 0;
        }}
        
        .indexing-step.active .icon::after {{
            content: '◉';
            color: #58a6ff;
        }}
        
        .indexing-step.done .icon::after {{
            content: '✓';
        }}
        
        .indexing-step.pending .icon::after {{
            content: '○';
            color: #6e7681;
        }}
        
        .indexing-step .text {{
            flex: 1;
        }}
        
        .indexing-step .detail {{
            font-size: 0.75rem;
            color: #6e7681;
            margin-top: 2px;
        }}
        
        .indexing-progress {{
            height: 3px;
            background: #21262d;
        }}
        
        .indexing-progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, #238636, #3fb950);
            transition: width 0.3s ease;
        }}
        
        .indexing-complete {{
            background: #238636;
            color: #fff;
            padding: 12px 16px;
            text-align: center;
            font-size: 0.85rem;
        }}
        
        .profile-selector select {{
            background: #21262d;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #c9d1d9;
            padding: 0.375rem 0.75rem;
            font-size: 0.8rem;
            cursor: pointer;
        }}
        
        .status {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.8rem;
            color: #6e7681;
        }}
        
        .status-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #3fb950;
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}
        
        .link {{
            stroke-opacity: 0.6;
            fill: none;
        }}
        
        .link.parent-child {{
            stroke: #58a6ff;
            stroke-width: 2;
        }}
        
        .link.tag-shared {{
            stroke: #30363d;
            stroke-width: 1;
            stroke-dasharray: 4,4;
        }}
        
        .link.hub-link {{
            stroke: url(#hubLinkGradient);
            stroke-width: 1.5;
            stroke-opacity: 0.5;
        }}
        
        .link.hub-link:hover {{
            stroke-opacity: 0.8;
        }}
        
        .node.hub-node circle {{
            fill: url(#hubGradient);
            stroke: #58a6ff;
            stroke-width: 2;
            filter: drop-shadow(0 0 12px rgba(88, 166, 255, 0.4));
        }}
        
        .node.hub-node text {{
            fill: #c9d1d9;
            font-size: 11px;
            font-weight: 600;
        }}
        
        .node {{
            cursor: pointer;
        }}
        
        .node circle {{
            stroke: #0d1117;
            stroke-width: 2;
            transition: all 0.3s ease;
        }}
        
        .node:hover circle {{
            stroke-width: 3;
            filter: brightness(1.2) drop-shadow(0 0 8px currentColor);
        }}
        
        .node.selected circle {{
            stroke: #fff;
            stroke-width: 3;
            filter: drop-shadow(0 0 20px currentColor);
        }}
        
        .node.dimmed {{
            opacity: 0.25;
        }}
        
        .node.connected {{
            opacity: 1;
        }}
        
        .link {{
            transition: all 0.3s ease;
        }}
        
        .link.dimmed {{
            opacity: 0.08;
        }}
        
        .link.highlighted {{
            stroke-opacity: 1;
            stroke-width: 3 !important;
        }}
        
        .link.highlighted.parent-child {{
            stroke: #58a6ff;
            filter: drop-shadow(0 0 4px #58a6ff);
        }}
        
        .node-label {{
            font-size: 11px;
            fill: #c9d1d9;
            text-anchor: middle;
            pointer-events: none;
            text-shadow: 0 1px 3px #0d1117, 0 0 8px #0d1117;
        }}
        
        .node-sublabel {{
            font-size: 9px;
            fill: #6e7681;
            text-anchor: middle;
            pointer-events: none;
        }}
        
        .detail-panel {{
            position: fixed;
            top: 0;
            right: 0;
            width: 420px;
            height: 100vh;
            background: #161b22;
            border-left: 1px solid #30363d;
            display: flex;
            flex-direction: column;
            z-index: 200;
            transform: translateX(100%);
            transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        
        .detail-panel.visible {{
            transform: translateX(0);
        }}
        
        .panel-header {{
            padding: 1.5rem;
            border-bottom: 1px solid #30363d;
            position: relative;
        }}
        
        .panel-header .close-btn {{
            position: absolute;
            top: 1.25rem;
            right: 1.25rem;
            background: transparent;
            border: 1px solid #30363d;
            color: #8b949e;
            cursor: pointer;
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.25rem;
            transition: all 0.2s;
        }}
        
        .panel-header .close-btn:hover {{
            background: #21262d;
            color: #f0f6fc;
            border-color: #8b949e;
        }}
        
        .panel-type {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.35rem 0.75rem;
            border-radius: 6px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.75rem;
        }}
        
        .panel-type.program {{
            background: linear-gradient(135deg, #f0883e20, #f0883e10);
            color: #f0883e;
            border: 1px solid #f0883e30;
        }}
        
        .panel-type.project {{
            background: linear-gradient(135deg, #58a6ff20, #58a6ff10);
            color: #58a6ff;
            border: 1px solid #58a6ff30;
        }}
        
        .panel-type.standalone {{
            background: linear-gradient(135deg, #3fb95020, #3fb95010);
            color: #3fb950;
            border: 1px solid #3fb95030;
        }}
        
        .panel-type .type-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}
        
        .panel-type.program .type-dot {{ background: #f0883e; box-shadow: 0 0 8px #f0883e; }}
        .panel-type.project .type-dot {{ background: #58a6ff; box-shadow: 0 0 8px #58a6ff; }}
        .panel-type.standalone .type-dot {{ background: #3fb950; box-shadow: 0 0 8px #3fb950; }}
        
        .panel-header h2 {{
            font-size: 1.35rem;
            font-weight: 600;
            color: #f0f6fc;
            margin: 0;
            padding-right: 40px;
            line-height: 1.3;
        }}
        
        .panel-body {{
            flex: 1;
            overflow-y: auto;
            padding: 1.5rem;
        }}
        
        .panel-section {{
            margin-bottom: 1.75rem;
        }}
        
        .panel-section:last-child {{
            margin-bottom: 0;
        }}
        
        .panel-section-title {{
            font-size: 0.65rem;
            font-weight: 600;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .panel-section-title::after {{
            content: '';
            flex: 1;
            height: 1px;
            background: #30363d;
        }}
        
        .panel-summary {{
            color: #c9d1d9;
            font-size: 0.95rem;
            line-height: 1.7;
        }}
        
        .panel-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        
        .panel-tag {{
            background: #21262d;
            color: #58a6ff;
            padding: 0.4rem 0.75rem;
            border-radius: 100px;
            font-size: 0.75rem;
            font-weight: 500;
            border: 1px solid #30363d;
            transition: all 0.2s;
        }}
        
        .panel-tag:hover {{
            background: #30363d;
            border-color: #58a6ff50;
        }}
        
        .panel-connections {{
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}
        
        .panel-connection {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem;
            background: #0d1117;
            border-radius: 10px;
            border: 1px solid #21262d;
            transition: all 0.2s;
            cursor: pointer;
        }}
        
        .panel-connection:hover {{
            background: #161b22;
            border-color: #30363d;
        }}
        
        .panel-connection .conn-icon {{
            width: 36px;
            height: 36px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
        }}
        
        .panel-connection .conn-icon.parent {{
            background: linear-gradient(135deg, #f0883e30, #f0883e15);
            color: #f0883e;
        }}
        
        .panel-connection .conn-icon.child {{
            background: linear-gradient(135deg, #58a6ff30, #58a6ff15);
            color: #58a6ff;
        }}
        
        .panel-connection .conn-icon.shared {{
            background: linear-gradient(135deg, #a371f730, #a371f715);
            color: #a371f7;
        }}
        
        .panel-connection .conn-info {{
            flex: 1;
            min-width: 0;
        }}
        
        .panel-connection .conn-name {{
            font-size: 0.85rem;
            font-weight: 500;
            color: #f0f6fc;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .panel-connection .conn-type {{
            font-size: 0.7rem;
            color: #8b949e;
            margin-top: 0.125rem;
        }}
        
        .panel-note {{
            background: #0d1117;
            padding: 1rem;
            border-radius: 10px;
            font-size: 0.85rem;
            line-height: 1.6;
            color: #c9d1d9;
            margin-bottom: 0.75rem;
            border-left: 3px solid #30363d;
        }}
        
        .panel-note:last-child {{
            margin-bottom: 0;
        }}
        
        .panel-note.note-decision {{
            border-left-color: #3fb950;
            background: linear-gradient(90deg, #3fb95010 0%, #0d1117 30%);
        }}
        
        .panel-note.note-blocker {{
            border-left-color: #f85149;
            background: linear-gradient(90deg, #f8514910 0%, #0d1117 30%);
        }}
        
        .panel-note.note-changed {{
            border-left-color: #a371f7;
            background: linear-gradient(90deg, #a371f710 0%, #0d1117 30%);
        }}
        
        .panel-note.note-context {{
            border-left-color: #58a6ff;
            background: linear-gradient(90deg, #58a6ff10 0%, #0d1117 30%);
        }}
        
        .panel-note.note-tried {{
            border-left-color: #f0883e;
            background: linear-gradient(90deg, #f0883e10 0%, #0d1117 30%);
        }}
        
        .panel-note.note-resume {{
            border-left-color: #d29922;
            background: linear-gradient(90deg, #d2992210 0%, #0d1117 30%);
        }}
        
        .note-category {{
            display: inline-block;
            font-size: 0.65rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            margin-bottom: 0.5rem;
        }}
        
        .note-decision .note-category {{ background: #3fb95020; color: #3fb950; }}
        .note-blocker .note-category {{ background: #f8514920; color: #f85149; }}
        .note-changed .note-category {{ background: #a371f720; color: #a371f7; }}
        .note-context .note-category {{ background: #58a6ff20; color: #58a6ff; }}
        .note-tried .note-category {{ background: #f0883e20; color: #f0883e; }}
        .note-resume .note-category {{ background: #d2992220; color: #d29922; }}
        
        .note-timestamp {{
            font-size: 0.7rem;
            color: #6e7681;
            margin-bottom: 0.25rem;
        }}
        
        .note-content {{
            color: #c9d1d9;
        }}
        
        .notes-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            padding: 0.5rem 0;
        }}
        
        .notes-header:hover {{
            opacity: 0.8;
        }}
        
        .notes-toggle {{
            background: none;
            border: none;
            color: #8b949e;
            font-size: 0.75rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }}
        
        .notes-toggle:hover {{
            color: #c9d1d9;
        }}
        
        .notes-container {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
        }}
        
        .notes-container.expanded {{
            max-height: 2000px;
        }}
        
        .notes-summary {{
            font-size: 0.8rem;
            color: #6e7681;
            padding: 0.5rem 0;
        }}
        
        .notes-pagination {{
            display: flex;
            justify-content: center;
            gap: 0.5rem;
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid #21262d;
        }}
        
        .notes-page-btn {{
            background: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            padding: 0.4rem 0.75rem;
            border-radius: 6px;
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .notes-page-btn:hover {{
            background: #30363d;
            border-color: #8b949e;
        }}
        
        .notes-page-btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        
        .notes-page-btn.active {{
            background: #58a6ff;
            border-color: #58a6ff;
            color: #0d1117;
        }}
        
        .panel-meta {{
            display: grid;
            gap: 0.75rem;
        }}
        
        .panel-meta-item {{
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
            padding: 0.75rem;
            background: #0d1117;
            border-radius: 8px;
        }}
        
        .panel-meta-item .meta-label {{
            font-size: 0.65rem;
            font-weight: 600;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .panel-meta-item .meta-value {{
            font-size: 0.8rem;
            color: #c9d1d9;
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
            word-break: break-all;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 2rem;
            color: #6e7681;
            font-size: 0.85rem;
        }}
        
        .legend {{
            position: fixed;
            bottom: 1.5rem;
            right: 1.5rem;
            background: rgba(22, 27, 34, 0.9);
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            font-size: 0.75rem;
            backdrop-filter: blur(10px);
            z-index: 100;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.375rem;
            color: #c9d1d9;
        }}
        
        .legend-item:last-child {{
            margin-bottom: 0;
        }}
        
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        
        .instructions {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
            color: #6e7681;
            font-size: 0.85rem;
            pointer-events: none;
            opacity: 0.8;
        }}
        
        .instructions.hidden {{
            display: none;
        }}
        
        #data-container {{
            display: none;
        }}
    </style>
</head>
<body>
    <svg id="graph">
        <defs>
            <radialGradient id="hubGradient" cx="50%" cy="50%" r="50%">
                <stop offset="0%" style="stop-color:#58a6ff;stop-opacity:0.3" />
                <stop offset="50%" style="stop-color:#30363d;stop-opacity:0.6" />
                <stop offset="100%" style="stop-color:#21262d;stop-opacity:0.8" />
            </radialGradient>
            <linearGradient id="hubLinkGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style="stop-color:#58a6ff;stop-opacity:0.6" />
                <stop offset="100%" style="stop-color:#30363d;stop-opacity:0.2" />
            </linearGradient>
        </defs>
    </svg>
    
    <div class="header">
        <div class="header-left">
            <h1>⚛️ Workstream Clusters</h1>
            <span class="profile-badge">{current_profile}</span>
        </div>
        <div class="controls">
            <div class="focus-selector">
                <label>🔍 Focus:</label>
                <select id="focus-select" onchange="onFocusSelect(this.value)">
                    <option value="">All workstreams</option>
                </select>
            </div>
            <div class="profile-selector">
                <select onchange="document.cookie = 'workstream_profile=' + this.value + ';max-age=31536000;path=/'; window.location.href='/?profile=' + this.value">
                    {profile_options}
                </select>
            </div>
            <div class="status">
                <div class="status-dot"></div>
                <span>Live</span>
            </div>
        </div>
    </div>
    
    <!-- Floating Action Button for Indexing -->
    <button class="fab" onclick="openIndexModal()" title="Index a repository">
        <span>+</span>
    </button>
    
    <!-- Index Modal -->
    <div class="modal-overlay" id="index-modal">
        <div class="modal">
            <div class="modal-header">
                <h2>📁 Index Repository</h2>
                <button class="modal-close" onclick="closeIndexModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="repo-list" id="repo-list">
                    <div class="empty-state">Loading repositories...</div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Focus Panel - Full height info panel -->
    <div class="focus-panel" id="focus-panel">
        <div class="focus-panel-header">
            <button class="focus-panel-close" onclick="exitFocusMode()">&times;</button>
            <h2>
                <span id="focus-name">Project Name</span>
            </h2>
            <span class="focus-type-badge project" id="focus-type-badge">
                <span class="type-dot"></span>
                <span id="focus-type-label">Project</span>
            </span>
        </div>
        <div class="focus-panel-body">
            <div class="focus-section" id="focus-summary-section">
                <div class="focus-section-title">📝 Summary</div>
                <div class="focus-summary" id="focus-summary">Loading...</div>
            </div>
            
            <div class="focus-section" id="focus-tags-section">
                <div class="focus-section-title">🏷️ Tags</div>
                <div class="focus-tags" id="focus-tags"></div>
            </div>
            
            <div class="focus-section" id="focus-todos-section">
                <div class="focus-section-title">
                    ✅ TODOs
                    <button class="add-btn" onclick="showAddTodoForm()" title="Add TODO">+</button>
                </div>
                <div class="todo-add-form" id="todo-add-form" style="display:none">
                    <input type="text" id="todo-input" placeholder="Enter TODO..." onkeydown="if(event.key==='Enter')addTodo()">
                    <button onclick="addTodo()">Add</button>
                    <button onclick="hideAddTodoForm()">Cancel</button>
                </div>
                <div class="todo-list" id="focus-todos">
                    <div class="empty-section">No TODOs found</div>
                </div>
            </div>
            
            <div class="focus-section" id="focus-branches-section">
                <div class="focus-section-title">🌿 Active Branches</div>
                <div class="branch-list" id="focus-branches">
                    <div class="empty-section">Loading branches...</div>
                </div>
                <button class="show-more-btn" id="branches-show-more" style="display:none" onclick="showMoreBranches()">Show more</button>
            </div>
            
            <div class="focus-section" id="focus-activity-section">
                <div class="focus-section-title">📊 Recent Activity</div>
                <div class="activity-list" id="focus-activity">
                    <div class="empty-section">Loading activity...</div>
                </div>
                <button class="show-more-btn" id="activity-show-more" style="display:none" onclick="showMoreActivity()">Show more</button>
            </div>
            
            <div class="focus-section" id="focus-connections-section">
                <div class="focus-section-title">🔗 Connections</div>
                <div class="connection-list" id="focus-connections">
                    <div class="empty-section">Loading connections...</div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="detail-panel" id="detail-panel">
        <div class="panel-header">
            <button class="close-btn" onclick="hidePanel()">&times;</button>
            <div class="panel-type" id="panel-type">
                <span class="type-dot"></span>
                <span id="panel-type-label">Project</span>
            </div>
            <h2 id="panel-name"></h2>
        </div>
        <div class="panel-body">
            <div class="panel-section">
                <div class="panel-section-title">Summary</div>
                <div class="panel-summary" id="panel-summary"></div>
            </div>
            <div class="panel-section" id="panel-tags-section">
                <div class="panel-section-title">Tags</div>
                <div class="panel-tags" id="panel-tags"></div>
            </div>
            <div class="panel-section" id="panel-connections-section" style="display:none">
                <div class="panel-section-title">Connections</div>
                <div class="panel-connections" id="panel-connections"></div>
            </div>
            <div class="panel-section" id="panel-notes-section" style="display:none">
                <div class="notes-header" onclick="toggleNotes()">
                    <div class="panel-section-title" style="margin-bottom:0">Notes <span id="notes-count"></span></div>
                    <button class="notes-toggle" id="notes-toggle">
                        <span id="toggle-icon">▶</span> <span id="toggle-text">Show</span>
                    </button>
                </div>
                <div class="notes-summary" id="notes-summary"></div>
                <div class="notes-container" id="notes-container">
                    <div id="panel-notes"></div>
                    <div class="notes-pagination" id="notes-pagination"></div>
                </div>
            </div>
            <div class="panel-section" id="panel-meta-section" style="display:none">
                <div class="panel-section-title">Metadata</div>
                <div class="panel-meta" id="panel-meta"></div>
            </div>
        </div>
    </div>
    
    <div class="legend">
        <div class="legend-item">
            <div class="legend-dot" style="background: #f0883e"></div>
            <span>Program</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot" style="background: #58a6ff"></div>
            <span>Project</span>
        </div>
        <div class="legend-item">
            <div class="legend-dot" style="background: #3fb950"></div>
            <span>Not Connected</span>
        </div>
    </div>
    
    <!-- Indexing Status Panel -->
    <div class="indexing-panel" id="indexing-panel">
        <div class="indexing-progress">
            <div class="indexing-progress-bar" id="indexing-progress-bar" style="width: 0%"></div>
        </div>
        <div class="indexing-header">
            <h3><div class="spinner"></div> Indexing Repository</h3>
            <span class="indexing-timer" id="indexing-timer">0:00</span>
        </div>
        <div class="indexing-body" id="indexing-steps">
            <!-- Steps populated by JavaScript -->
        </div>
    </div>
    
    <div class="instructions" id="instructions">
        <p>🖱️ Drag nodes to reposition · 🔍 Scroll to zoom · 👆 Click for details</p>
    </div>
    
    <div id="data-container" hx-ext="sse" sse-connect="/events?profile={current_profile}" sse-swap="message" hx-swap="innerHTML"></div>
    
    <script>
        let svg, simulation, nodeGroup, linkGroup, zoom;
        let nodes = [], links = [];
        let selectedNode = null;
        let workstreamData = {{}};
        
        const width = window.innerWidth;
        const height = window.innerHeight;
        
        function initGraph() {{
            svg = d3.select('#graph')
                .attr('width', width)
                .attr('height', height);
            
            // Add zoom behavior
            zoom = d3.zoom()
                .scaleExtent([0.3, 3])
                .on('zoom', (event) => {{
                    container.attr('transform', event.transform);
                }});
            
            svg.call(zoom);
            
            // Click outside to deselect
            svg.on('click', () => hidePanel());
            
            // Container for zoomable content
            const container = svg.append('g');
            
            // Links layer (behind nodes)
            linkGroup = container.append('g').attr('class', 'links');
            
            // Nodes layer
            nodeGroup = container.append('g').attr('class', 'nodes');
            
            // Initialize force simulation
            simulation = d3.forceSimulation()
                .force('charge', d3.forceManyBody().strength(-400))
                .force('center', d3.forceCenter(width / 2, height / 2))
                .force('collision', d3.forceCollide().radius(d => d.radius + 20))
                .on('tick', ticked);
        }}
        
        function createGraph(workstreams) {{
            if (!workstreams || workstreams.length === 0) return;
            
            document.getElementById('instructions').classList.add('hidden');
            
            workstreamData = {{}};
            workstreams.forEach(ws => workstreamData[ws.id] = ws);
            
            // Determine node types
            const parentIds = new Set(workstreams.filter(w => w.parentId).map(w => w.parentId));
            
            // Build nodes - start with hub node (You - the center of all workstreams)
            nodes = [{{
                id: '__hub__',
                name: 'You',
                type: 'hub',
                tags: [],
                radius: 18,
                color: '#58a6ff',
                fx: width / 2,  // Fixed at center
                fy: height / 2
            }}];
            
            // Add workstream nodes
            workstreams.forEach(ws => {{
                const isProgram = parentIds.has(ws.id);
                const isProject = !!ws.parentId;
                nodes.push({{
                    id: ws.id,
                    name: ws.name,
                    type: isProgram ? 'program' : (isProject ? 'project' : 'standalone'),
                    parentId: ws.parentId,
                    tags: ws.tags || [],
                    radius: isProgram ? 28 : (isProject ? 20 : 16),
                    color: isProgram ? '#f0883e' : (isProject ? '#58a6ff' : '#3fb950')
                }});
            }});
            
            // Build links with varying strengths based on affinity
            links = [];
            
            // Hub links - connect everything to center (very weak)
            workstreams.forEach(ws => {{
                links.push({{
                    source: '__hub__',
                    target: ws.id,
                    type: 'hub-link',
                    strength: 0.03
                }});
            }});
            
            // Parent-child links (strong attraction)
            workstreams.forEach(ws => {{
                if (ws.parentId) {{
                    links.push({{
                        source: ws.parentId,
                        target: ws.id,
                        type: 'parent-child',
                        strength: 0.8
                    }});
                }}
            }});
            
            // Tag-based links (weaker attraction for shared tags)
            const tagMap = {{}};
            workstreams.forEach(ws => {{
                (ws.tags || []).forEach(tag => {{
                    if (!tagMap[tag]) tagMap[tag] = [];
                    tagMap[tag].push(ws.id);
                }});
            }});
            
            Object.values(tagMap).forEach(ids => {{
                if (ids.length >= 2 && ids.length <= 6) {{
                    for (let i = 0; i < ids.length; i++) {{
                        for (let j = i + 1; j < ids.length; j++) {{
                            // Don't duplicate parent-child links
                            const ws1 = workstreamData[ids[i]];
                            const ws2 = workstreamData[ids[j]];
                            if (ws1.parentId !== ws2.id && ws2.parentId !== ws1.id) {{
                                links.push({{
                                    source: ids[i],
                                    target: ids[j],
                                    type: 'tag-shared',
                                    strength: 0.2
                                }});
                            }}
                        }}
                    }}
                }}
            }});
            
            // Update force simulation
            simulation.nodes(nodes);
            
            simulation.force('link', d3.forceLink(links)
                .id(d => d.id)
                .distance(d => d.type === 'parent-child' ? 100 : (d.type === 'hub-link' ? 250 : 180))
                .strength(d => d.strength)
            );
            
            // Render links
            const link = linkGroup.selectAll('line')
                .data(links, d => `${{d.source.id || d.source}}-${{d.target.id || d.target}}`);
            
            link.exit().remove();
            
            link.enter()
                .append('line')
                .attr('class', d => `link ${{d.type}}`)
                .merge(link);
            
            // Render nodes
            const node = nodeGroup.selectAll('.node')
                .data(nodes, d => d.id);
            
            node.exit().remove();
            
            const nodeEnter = node.enter()
                .append('g')
                .attr('class', d => d.type === 'hub' ? 'node hub-node' : 'node')
                .call(d3.drag()
                    .on('start', dragstarted)
                    .on('drag', dragged)
                    .on('end', dragended)
                )
                .on('click', (event, d) => {{
                    event.stopPropagation();
                    if (d.type !== 'hub') selectNode(d);
                }});
            
            // Node circle
            nodeEnter.append('circle')
                .attr('r', d => d.radius)
                .attr('fill', d => d.type === 'hub' ? 'url(#hubGradient)' : d.color);
            
            // Inner highlight (skip for hub)
            nodeEnter.filter(d => d.type !== 'hub')
                .append('circle')
                .attr('r', d => d.radius * 0.4)
                .attr('fill', 'rgba(255,255,255,0.3)');
            
            // Label
            nodeEnter.append('text')
                .attr('class', 'node-label')
                .attr('dy', d => d.radius + 16)
                .text(d => d.type === 'hub' ? 'You' : (d.name.length > 18 ? d.name.slice(0, 16) + '...' : d.name));
            
            // Sublabel (tag count) - skip for hub, add connection count for hub
            nodeEnter.filter(d => d.type !== 'hub')
                .append('text')
                .attr('class', 'node-sublabel')
                .attr('dy', d => d.radius + 28)
                .text(d => `${{d.tags.length}} tags`);
            
            // Hub sublabel - show connected count
            nodeEnter.filter(d => d.type === 'hub')
                .append('text')
                .attr('class', 'node-sublabel')
                .attr('dy', d => d.radius + 28)
                .text(d => `${{workstreams.length}} workstreams`);
            
            simulation.alpha(1).restart();
        }}
        
        function ticked() {{
            linkGroup.selectAll('line')
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);
            
            nodeGroup.selectAll('.node')
                .attr('transform', d => `translate(${{d.x}},${{d.y}})`);
        }}
        
        function dragstarted(event, d) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }}
        
        function dragged(event, d) {{
            d.fx = event.x;
            d.fy = event.y;
        }}
        
        function dragended(event, d) {{
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }}
        
        function selectNode(d) {{
            // Deselect previous
            nodeGroup.selectAll('.node').classed('selected', false);
            linkGroup.selectAll('line').classed('highlighted', false).classed('dimmed', false);
            nodeGroup.selectAll('.node').classed('dimmed', false).classed('connected', false);
            
            // Select new
            nodeGroup.selectAll('.node')
                .filter(n => n.id === d.id)
                .classed('selected', true);
            
            // Find connected nodes
            const connectedIds = new Set([d.id]);
            links.forEach(link => {{
                const sourceId = link.source.id || link.source;
                const targetId = link.target.id || link.target;
                if (sourceId === d.id) connectedIds.add(targetId);
                if (targetId === d.id) connectedIds.add(sourceId);
            }});
            
            // Dim unconnected nodes, highlight connected ones
            nodeGroup.selectAll('.node')
                .classed('dimmed', n => !connectedIds.has(n.id))
                .classed('connected', n => connectedIds.has(n.id) && n.id !== d.id);
            
            // Highlight connected links, dim others
            linkGroup.selectAll('line')
                .classed('highlighted', link => {{
                    const sourceId = link.source.id || link.source;
                    const targetId = link.target.id || link.target;
                    return sourceId === d.id || targetId === d.id;
                }})
                .classed('dimmed', link => {{
                    const sourceId = link.source.id || link.source;
                    const targetId = link.target.id || link.target;
                    return sourceId !== d.id && targetId !== d.id;
                }});
            
            selectedNode = d.id;
            showPanel(workstreamData[d.id], connectedIds);
        }}
        
        function showPanel(ws, connectedIds) {{
            if (!ws) return;
            
            const panel = document.getElementById('detail-panel');
            const isProgram = Object.values(workstreamData).some(w => w.parentId === ws.id);
            const isProject = !!ws.parentId;
            const typeClass = isProgram ? 'program' : (isProject ? 'project' : 'standalone');
            const typeLabel = isProgram ? 'Program' : (isProject ? 'Project' : 'Standalone');
            
            // Header
            const panelType = document.getElementById('panel-type');
            panelType.className = 'panel-type ' + typeClass;
            document.getElementById('panel-type-label').textContent = typeLabel;
            document.getElementById('panel-name').textContent = ws.name;
            
            // Summary
            document.getElementById('panel-summary').textContent = ws.summary || 'No summary available.';
            
            // Tags
            const tagsSection = document.getElementById('panel-tags-section');
            const tagsContainer = document.getElementById('panel-tags');
            if (ws.tags && ws.tags.length > 0) {{
                tagsSection.style.display = 'block';
                tagsContainer.innerHTML = ws.tags.map(t => `<span class="panel-tag">${{t}}</span>`).join('');
            }} else {{
                tagsSection.style.display = 'none';
            }}
            
            // Connections
            const connectionsSection = document.getElementById('panel-connections-section');
            const connectionsContainer = document.getElementById('panel-connections');
            const connections = [];
            
            // Parent connection
            if (ws.parentId && workstreamData[ws.parentId]) {{
                connections.push({{
                    id: ws.parentId,
                    name: workstreamData[ws.parentId].name,
                    type: 'Parent Program',
                    icon: '↑',
                    iconClass: 'parent'
                }});
            }}
            
            // Child connections
            Object.values(workstreamData).forEach(w => {{
                if (w.parentId === ws.id) {{
                    connections.push({{
                        id: w.id,
                        name: w.name,
                        type: 'Child Project',
                        icon: '↓',
                        iconClass: 'child'
                    }});
                }}
            }});
            
            // Tag-based connections
            if (connectedIds) {{
                connectedIds.forEach(id => {{
                    if (id !== ws.id) {{
                        const other = workstreamData[id];
                        if (other && other.parentId !== ws.id && ws.parentId !== other.id) {{
                            const sharedTags = (ws.tags || []).filter(t => (other.tags || []).includes(t));
                            if (sharedTags.length > 0) {{
                                connections.push({{
                                    id: other.id,
                                    name: other.name,
                                    type: sharedTags.join(', '),
                                    icon: '⟷',
                                    iconClass: 'shared'
                                }});
                            }}
                        }}
                    }}
                }});
            }}
            
            if (connections.length > 0) {{
                connectionsSection.style.display = 'block';
                connectionsContainer.innerHTML = connections.map(c => `
                    <div class="panel-connection" onclick="navigateToNode('${{c.id}}')">
                        <div class="conn-icon ${{c.iconClass}}">${{c.icon}}</div>
                        <div class="conn-info">
                            <div class="conn-name">${{c.name}}</div>
                            <div class="conn-type">${{c.type}}</div>
                        </div>
                    </div>
                `).join('');
            }} else {{
                connectionsSection.style.display = 'none';
            }}
            
            // Notes
            const notesSection = document.getElementById('panel-notes-section');
            const notesContainer = document.getElementById('panel-notes');
            const notesSummary = document.getElementById('notes-summary');
            const notesCount = document.getElementById('notes-count');
            const notesPagination = document.getElementById('notes-pagination');
            
            if (ws.notes && ws.notes.length > 0) {{
                notesSection.style.display = 'block';
                notesCount.textContent = `(${{ws.notes.length}})`;
                
                // Parse and categorize notes
                const parsedNotes = ws.notes.map(n => {{
                    const categoryMatch = n.match(/\\[(DECISION|BLOCKER|CHANGED|CONTEXT|TRIED|RESUME)\\]/i);
                    const timestampMatch = n.match(/^\\[(\\d{{4}}-\\d{{2}}-\\d{{2}} \\d{{2}}:\\d{{2}})\\]/);
                    let category = categoryMatch ? categoryMatch[1].toLowerCase() : null;
                    let timestamp = timestampMatch ? timestampMatch[1] : null;
                    let content = n;
                    if (timestampMatch) content = content.replace(timestampMatch[0], '').trim();
                    if (categoryMatch) content = content.replace(`[${{categoryMatch[1]}}]`, '').trim();
                    return {{ category, timestamp, content, raw: n }};
                }}).reverse(); // Most recent first
                
                // Store for pagination
                window.currentNotes = parsedNotes;
                window.notesPerPage = 3;
                window.currentNotesPage = 0;
                
                // Show summary of most recent key note
                const keyNote = parsedNotes.find(n => n.category);
                if (keyNote) {{
                    const categoryColors = {{
                        decision: '#3fb950', blocker: '#f85149', changed: '#a371f7',
                        context: '#58a6ff', tried: '#f0883e', resume: '#d29922'
                    }};
                    const preview = keyNote.content.length > 80 ? keyNote.content.slice(0, 80) + '...' : keyNote.content;
                    notesSummary.innerHTML = `<span style="color:${{categoryColors[keyNote.category] || '#8b949e'}}">${{keyNote.category.toUpperCase()}}:</span> ${{preview}}`;
                }} else {{
                    const preview = parsedNotes[0].content.length > 80 ? parsedNotes[0].content.slice(0, 80) + '...' : parsedNotes[0].content;
                    notesSummary.textContent = preview;
                }}
                
                // Reset collapsed state
                document.getElementById('notes-container').classList.remove('expanded');
                document.getElementById('toggle-icon').textContent = '▶';
                document.getElementById('toggle-text').textContent = 'Show';
                
                renderNotesPage(0);
            }} else {{
                notesSection.style.display = 'none';
            }}
            
            // Metadata
            const metaSection = document.getElementById('panel-meta-section');
            const metaContainer = document.getElementById('panel-meta');
            const meta = ws.metadata || {{}};
            const metaItems = [];
            if (meta.hostIps) metaItems.push(['Host IPs', meta.hostIps.join(', ')]);
            if (meta.connectionInfo) metaItems.push(['Connection', meta.connectionInfo]);
            if (meta.testingInfo) metaItems.push(['Testing', meta.testingInfo]);
            Object.entries(meta).forEach(([k, v]) => {{
                if (!['hostIps', 'connectionInfo', 'testingInfo'].includes(k)) {{
                    metaItems.push([k, Array.isArray(v) ? v.join(', ') : v]);
                }}
            }});
            
            if (metaItems.length > 0) {{
                metaSection.style.display = 'block';
                metaContainer.innerHTML = metaItems.map(([k, v]) => `
                    <div class="panel-meta-item">
                        <span class="meta-label">${{k}}</span>
                        <span class="meta-value">${{v}}</span>
                    </div>
                `).join('');
            }} else {{
                metaSection.style.display = 'none';
            }}
            
            // Show panel
            panel.classList.add('visible');
        }}
        
        function navigateToNode(id) {{
            const node = nodes.find(n => n.id === id);
            if (node) {{
                selectNode(node);
            }}
        }}
        
        function hidePanel() {{
            const panel = document.getElementById('detail-panel');
            panel.classList.remove('visible');
            
            // Reset all highlighting
            nodeGroup.selectAll('.node').classed('selected', false).classed('dimmed', false).classed('connected', false);
            linkGroup.selectAll('line').classed('highlighted', false).classed('dimmed', false);
            
            selectedNode = null;
        }}
        
        function toggleNotes() {{
            const container = document.getElementById('notes-container');
            const icon = document.getElementById('toggle-icon');
            const text = document.getElementById('toggle-text');
            const isExpanded = container.classList.contains('expanded');
            
            if (isExpanded) {{
                container.classList.remove('expanded');
                icon.textContent = '▶';
                text.textContent = 'Show';
            }} else {{
                container.classList.add('expanded');
                icon.textContent = '▼';
                text.textContent = 'Hide';
            }}
        }}
        
        function renderNotesPage(page) {{
            const notes = window.currentNotes || [];
            const perPage = window.notesPerPage || 3;
            const totalPages = Math.ceil(notes.length / perPage);
            window.currentNotesPage = page;
            
            const start = page * perPage;
            const end = Math.min(start + perPage, notes.length);
            const pageNotes = notes.slice(start, end);
            
            const notesContainer = document.getElementById('panel-notes');
            notesContainer.innerHTML = pageNotes.map(n => {{
                const categoryClass = n.category ? `note-${{n.category}}` : '';
                const categoryBadge = n.category ? `<div class="note-category">${{n.category}}</div>` : '';
                const timestamp = n.timestamp ? `<div class="note-timestamp">${{n.timestamp}}</div>` : '';
                return `<div class="panel-note ${{categoryClass}}">
                    ${{categoryBadge}}
                    ${{timestamp}}
                    <div class="note-content">${{n.content}}</div>
                </div>`;
            }}).join('');
            
            // Render pagination
            const pagination = document.getElementById('notes-pagination');
            if (totalPages > 1) {{
                let paginationHtml = `
                    <button class="notes-page-btn" onclick="renderNotesPage(${{page - 1}})" ${{page === 0 ? 'disabled' : ''}}>← Prev</button>
                    <span style="color:#6e7681;font-size:0.75rem;padding:0.4rem">${{page + 1}} / ${{totalPages}}</span>
                    <button class="notes-page-btn" onclick="renderNotesPage(${{page + 1}})" ${{page >= totalPages - 1 ? 'disabled' : ''}}>Next →</button>
                `;
                pagination.innerHTML = paginationHtml;
                pagination.style.display = 'flex';
            }} else {{
                pagination.style.display = 'none';
            }}
        }}
        
        // Handle resize
        window.addEventListener('resize', () => {{
            const w = window.innerWidth;
            const h = window.innerHeight;
            svg.attr('width', w).attr('height', h);
            simulation.force('center', d3.forceCenter(w / 2, h / 2));
            simulation.alpha(0.3).restart();
        }});
        
        // Parse SSE data
        const observer = new MutationObserver(() => {{
            const container = document.getElementById('data-container');
            const div = container.querySelector('[data-workstreams]');
            if (div) {{
                try {{
                    let jsonStr = div.getAttribute('data-workstreams');
                    const txt = document.createElement('textarea');
                    txt.innerHTML = jsonStr;
                    jsonStr = txt.value;
                    
                    const workstreams = JSON.parse(jsonStr);
                    createGraph(workstreams);
                }} catch (e) {{
                    console.error('Parse error:', e);
                }}
            }}
        }});
        
        // ============== Repo Selector ==============
        let reposData = [];
        let focusedWorkstreamId = null;
        
        // ============== Focus Selector ==============
        function populateFocusSelector() {{
            const select = document.getElementById('focus-select');
            select.innerHTML = '<option value="">All workstreams</option>';
            
            // Get focused workstream from cookie
            const focusedId = getCookie('focused_workstream');
            
            Object.values(workstreamData).forEach(ws => {{
                const option = document.createElement('option');
                option.value = ws.id;
                option.textContent = ws.name;
                if (ws.id === focusedId) {{
                    option.selected = true;
                    focusedWorkstreamId = ws.id;
                }}
                select.appendChild(option);
            }});
            
            // Apply initial focus if set
            if (focusedWorkstreamId) {{
                applyFocus(focusedWorkstreamId);
            }}
        }}
        
        function onFocusSelect(workstreamId) {{
            focusedWorkstreamId = workstreamId || null;
            
            // Save to cookie
            if (workstreamId) {{
                document.cookie = `focused_workstream=${{workstreamId}};max-age=31536000;path=/`;
            }} else {{
                document.cookie = 'focused_workstream=;max-age=0;path=/';
            }}
            
            applyFocus(workstreamId);
        }}
        
        function applyFocus(workstreamId) {{
            if (workstreamId && workstreamData[workstreamId]) {{
                const ws = workstreamData[workstreamId];
                enterFocusMode(ws);
            }} else {{
                exitFocusMode();
            }}
        }}
        
        async function enterFocusMode(ws) {{
            // Store current focused workstream ID for TODO adding
            currentFocusedWsId = ws.id;
            
            // Add focus mode class to body
            document.body.classList.add('focus-mode');
            
            // Show focus panel
            const panel = document.getElementById('focus-panel');
            panel.classList.add('visible');
            
            // Hide detail panel if open
            hidePanel();
            
            // Get type from metadata or default
            const wsType = (ws.metadata && ws.metadata.type) || 'project';
            
            // Update panel content
            document.getElementById('focus-name').textContent = ws.name;
            document.getElementById('focus-type-label').textContent = wsType;
            
            const badge = document.getElementById('focus-type-badge');
            badge.className = `focus-type-badge ${{wsType}}`;
            
            document.getElementById('focus-summary').textContent = ws.summary || 'No summary available';
            
            // Tags
            const tagsContainer = document.getElementById('focus-tags');
            if (ws.tags && ws.tags.length > 0) {{
                tagsContainer.innerHTML = ws.tags.map(tag => 
                    `<span class="focus-tag">${{tag}}</span>`
                ).join('');
            }} else {{
                tagsContainer.innerHTML = '<span class="empty-section">No tags</span>';
            }}
            
            // Dim non-focused nodes and highlight focused one
            applyGraphFocusEffect(ws.id);
            
            // Center graph on focused node
            const node = nodes.find(n => n.id === ws.id);
            if (node && svg) {{
                // Shift center to right to account for panel
                const transform = d3.zoomIdentity
                    .translate(window.innerWidth / 2 + 200, window.innerHeight / 2)
                    .scale(1.2)
                    .translate(-node.x, -node.y);
                svg.transition().duration(750).call(zoom.transform, transform);
            }}
            
            // Load async data
            console.log('Loading focus data for:', ws.id);
            loadFocusBranches(ws.id);
            loadFocusActivity(ws.id);
            loadFocusConnections(ws.id);
            extractTodosFromNotes(ws);
        }}
        
        function exitFocusMode() {{
            document.body.classList.remove('focus-mode');
            
            const panel = document.getElementById('focus-panel');
            panel.classList.remove('visible');
            
            // Reset graph effects
            resetGraphFocusEffect();
            
            // Reset zoom
            if (svg) {{
                svg.transition().duration(750).call(zoom.transform, d3.zoomIdentity);
            }}
            
            // Reset dropdown
            document.getElementById('focus-select').value = '';
            focusedWorkstreamId = null;
            document.cookie = 'focused_workstream=;max-age=0;path=/';
        }}
        
        function applyGraphFocusEffect(workstreamId) {{
            // Dim all nodes except focused
            nodeGroup.selectAll('circle')
                .transition().duration(500)
                .attr('opacity', d => d.id === workstreamId ? 1 : 0.2)
                .attr('r', d => d.id === workstreamId ? (d.size || 20) * 1.5 : (d.size || 20));
            
            nodeGroup.selectAll('text')
                .transition().duration(500)
                .attr('opacity', d => d.id === workstreamId ? 1 : 0.2);
            
            // Highlight connected links
            const connectedIds = new Set([workstreamId]);
            links.forEach(link => {{
                const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
                const targetId = typeof link.target === 'object' ? link.target.id : link.target;
                if (sourceId === workstreamId) connectedIds.add(targetId);
                if (targetId === workstreamId) connectedIds.add(sourceId);
            }});
            
            linkGroup.selectAll('line')
                .transition().duration(500)
                .attr('opacity', d => {{
                    const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                    const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                    return (sourceId === workstreamId || targetId === workstreamId) ? 1 : 0.1;
                }})
                .attr('stroke-width', d => {{
                    const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                    const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                    return (sourceId === workstreamId || targetId === workstreamId) ? 3 : 1;
                }});
        }}
        
        function resetGraphFocusEffect() {{
            nodeGroup.selectAll('circle')
                .transition().duration(500)
                .attr('opacity', 1)
                .attr('r', d => d.size || 20);
            
            nodeGroup.selectAll('text')
                .transition().duration(500)
                .attr('opacity', 1);
            
            linkGroup.selectAll('line')
                .transition().duration(500)
                .attr('opacity', 0.6)
                .attr('stroke-width', 1);
        }}
        
        let allCommits = [];
        let activityPage = 0;
        const ACTIVITY_PAGE_SIZE = 5;
        
        async function loadFocusActivity(workstreamId) {{
            const container = document.getElementById('focus-activity');
            const showMoreBtn = document.getElementById('activity-show-more');
            container.innerHTML = '<div class="empty-section">Loading activity...</div>';
            showMoreBtn.style.display = 'none';
            
            try {{
                console.log('Fetching activity for:', workstreamId);
                const response = await fetch(`/api/workstreams/${{workstreamId}}/activity?profile={current_profile}&days=30`);
                const data = await response.json();
                console.log('Activity response:', data);
                
                if (data.commits && data.commits.length > 0) {{
                    allCommits = data.commits;
                    activityPage = 0;
                    renderActivityPage();
                    
                    // Show "Show more" if there are more commits
                    if (allCommits.length > ACTIVITY_PAGE_SIZE) {{
                        showMoreBtn.style.display = 'block';
                    }}
                }} else {{
                    container.innerHTML = `<div class="empty-section">${{data.error || 'No recent commits'}}</div>`;
                }}
            }} catch (e) {{
                console.error('Failed to load activity:', e);
                container.innerHTML = '<div class="empty-section">Failed to load activity</div>';
            }}
        }}
        
        function renderActivityPage() {{
            const container = document.getElementById('focus-activity');
            const showMoreBtn = document.getElementById('activity-show-more');
            const start = 0;
            const end = (activityPage + 1) * ACTIVITY_PAGE_SIZE;
            const visibleCommits = allCommits.slice(start, end);
            
            container.innerHTML = visibleCommits.map(commit => {{
                const date = new Date(commit.timestamp * 1000);
                const timeAgo = getTimeAgo(date);
                return `
                    <div class="activity-item">
                        <div class="activity-header">
                            <span class="activity-sha">${{commit.sha}}</span>
                            <span class="activity-time">${{timeAgo}}</span>
                        </div>
                        <div class="activity-message">${{escapeHtml(commit.message)}}</div>
                        <div class="activity-author">by ${{escapeHtml(commit.author)}}</div>
                    </div>
                `;
            }}).join('');
            
            // Hide show more if all shown
            if (end >= allCommits.length) {{
                showMoreBtn.style.display = 'none';
            }} else {{
                showMoreBtn.style.display = 'block';
            }}
        }}
        
        function showMoreActivity() {{
            activityPage++;
            renderActivityPage();
        }}
        
        let allBranches = [];
        let branchesPage = 0;
        const BRANCHES_PAGE_SIZE = 3;
        
        async function loadFocusBranches(workstreamId) {{
            const container = document.getElementById('focus-branches');
            const showMoreBtn = document.getElementById('branches-show-more');
            container.innerHTML = '<div class="empty-section">Loading branches...</div>';
            showMoreBtn.style.display = 'none';
            
            try {{
                const response = await fetch(`/api/workstreams/${{workstreamId}}/branches?profile={current_profile}&days=14`);
                const data = await response.json();
                
                if (data.branches && data.branches.length > 0) {{
                    allBranches = data.branches;
                    branchesPage = 0;
                    renderBranchesPage();
                    
                    if (allBranches.length > BRANCHES_PAGE_SIZE) {{
                        showMoreBtn.style.display = 'block';
                    }}
                }} else {{
                    container.innerHTML = `<div class="empty-section">${{data.error || 'No recent branches'}}</div>`;
                }}
            }} catch (e) {{
                console.error('Failed to load branches:', e);
                container.innerHTML = '<div class="empty-section">Failed to load branches</div>';
            }}
        }}
        
        function renderBranchesPage() {{
            const container = document.getElementById('focus-branches');
            const showMoreBtn = document.getElementById('branches-show-more');
            const end = (branchesPage + 1) * BRANCHES_PAGE_SIZE;
            const visibleBranches = allBranches.slice(0, end);
            
            container.innerHTML = visibleBranches.map(branch => `
                <div class="branch-item ${{branch.current ? 'current' : ''}}">
                    <span class="branch-icon">${{branch.current ? '●' : '○'}}</span>
                    <span class="branch-name">${{escapeHtml(branch.name)}}</span>
                    <span class="branch-time">${{escapeHtml(branch.time)}}</span>
                </div>
            `).join('');
            
            if (end >= allBranches.length) {{
                showMoreBtn.style.display = 'none';
            }} else {{
                showMoreBtn.style.display = 'block';
            }}
        }}
        
        function showMoreBranches() {{
            branchesPage++;
            renderBranchesPage();
        }}
        
        // TODO functions
        let currentFocusedWsId = null;
        
        function showAddTodoForm() {{
            document.getElementById('todo-add-form').style.display = 'flex';
            document.getElementById('todo-input').focus();
        }}
        
        function hideAddTodoForm() {{
            document.getElementById('todo-add-form').style.display = 'none';
            document.getElementById('todo-input').value = '';
        }}
        
        async function addTodo() {{
            const input = document.getElementById('todo-input');
            const text = input.value.trim();
            if (!text || !currentFocusedWsId) return;
            
            try {{
                // Add as a note with TODO prefix
                const response = await fetch(`/api/workstreams/${{currentFocusedWsId}}/notes?profile={current_profile}`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ content: `TODO: ${{text}}` }})
                }});
                
                if (response.ok) {{
                    hideAddTodoForm();
                    // Refresh the workstream data and TODOs
                    const wsResponse = await fetch(`/api/workstreams/${{currentFocusedWsId}}?profile={current_profile}`);
                    const ws = await wsResponse.json();
                    workstreamData[currentFocusedWsId] = ws;
                    extractTodosFromNotes(ws);
                }}
            }} catch (e) {{
                console.error('Failed to add TODO:', e);
            }}
        }}
        
        async function loadFocusConnections(workstreamId) {{
            const container = document.getElementById('focus-connections');
            container.innerHTML = '<div class="empty-section">Loading connections...</div>';
            
            try {{
                console.log('Fetching connections for:', workstreamId);
                const response = await fetch(`/api/workstreams/${{workstreamId}}/connections?profile={current_profile}`);
                const data = await response.json();
                console.log('Connections response:', data);
                
                const items = [];
                
                if (data.parent) {{
                    items.push(`
                        <div class="connection-item" onclick="focusOnWorkstream('${{data.parent.id}}')">
                            <span class="connection-type">Parent</span>
                            <span class="connection-name">${{escapeHtml(data.parent.name)}}</span>
                        </div>
                    `);
                }}
                
                data.children?.forEach(child => {{
                    items.push(`
                        <div class="connection-item" onclick="focusOnWorkstream('${{child.id}}')">
                            <span class="connection-type">Child</span>
                            <span class="connection-name">${{escapeHtml(child.name)}}</span>
                        </div>
                    `);
                }});
                
                data.dependents?.forEach(dep => {{
                    items.push(`
                        <div class="connection-item" onclick="focusOnWorkstream('${{dep.id}}')">
                            <span class="connection-type">Depends</span>
                            <span class="connection-name">${{escapeHtml(dep.name)}}</span>
                        </div>
                    `);
                }});
                
                // Relationships
                if (data.relationships) {{
                    Object.entries(data.relationships).forEach(([relType, targets]) => {{
                        targets?.forEach(targetId => {{
                            const targetWs = workstreamData[targetId];
                            if (targetWs) {{
                                items.push(`
                                    <div class="connection-item" onclick="focusOnWorkstream('${{targetId}}')">
                                        <span class="connection-type">${{relType}}</span>
                                        <span class="connection-name">${{escapeHtml(targetWs.name)}}</span>
                                    </div>
                                `);
                            }}
                        }});
                    }});
                }}
                
                container.innerHTML = items.length > 0 ? items.join('') : '<div class="empty-section">No connections</div>';
            }} catch (e) {{
                container.innerHTML = '<div class="empty-section">Failed to load connections</div>';
            }}
        }}
        
        function extractTodosFromNotes(ws) {{
            const container = document.getElementById('focus-todos');
            const todos = [];
            
            // Parse notes for TODO patterns
            if (ws.notes && ws.notes.length > 0) {{
                ws.notes.forEach(note => {{
                    // Notes can be strings or objects with content
                    const content = typeof note === 'string' ? note : (note.content || '');
                    // Match TODO, FIXME, [ ], [x] patterns
                    const todoMatches = content.match(/(?:TODO|FIXME|\\[ \\]|\\[x\\])\\s*:?\\s*.+/gi) || [];
                    todoMatches.forEach(match => {{
                        const isDone = match.includes('[x]');
                        const text = match.replace(/^(TODO|FIXME|\\[ \\]|\\[x\\])\\s*:?\\s*/i, '');
                        todos.push({{ text, done: isDone }});
                    }});
                }});
            }}
            
            if (todos.length > 0) {{
                container.innerHTML = todos.map(todo => `
                    <div class="todo-item">
                        <span class="todo-checkbox">${{todo.done ? '☑' : '☐'}}</span>
                        <span class="todo-text">${{escapeHtml(todo.text)}}</span>
                    </div>
                `).join('');
            }} else {{
                container.innerHTML = '<div class="empty-section">No TODOs found in notes</div>';
            }}
        }}
        
        function focusOnWorkstream(workstreamId) {{
            document.getElementById('focus-select').value = workstreamId;
            onFocusSelect(workstreamId);
        }}
        
        function getTimeAgo(date) {{
            const seconds = Math.floor((new Date() - date) / 1000);
            const intervals = [
                {{ label: 'year', seconds: 31536000 }},
                {{ label: 'month', seconds: 2592000 }},
                {{ label: 'day', seconds: 86400 }},
                {{ label: 'hour', seconds: 3600 }},
                {{ label: 'minute', seconds: 60 }}
            ];
            for (const interval of intervals) {{
                const count = Math.floor(seconds / interval.seconds);
                if (count >= 1) {{
                    return count === 1 ? `1 ${{interval.label}} ago` : `${{count}} ${{interval.label}}s ago`;
                }}
            }}
            return 'just now';
        }}
        
        function escapeHtml(str) {{
            if (!str) return '';
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }}
        
        // Escape key to exit focus mode
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape' && document.body.classList.contains('focus-mode')) {{
                exitFocusMode();
            }}
        }});
        
        function getCookie(name) {{
            const value = `; ${{document.cookie}}`;
            const parts = value.split(`; ${{name}}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return null;
        }}
        
        function highlightNode(workstreamId) {{
            // Update node visuals
            nodeGroup.selectAll('circle')
                .attr('stroke', d => d.id === workstreamId ? '#58a6ff' : 'none')
                .attr('stroke-width', d => d.id === workstreamId ? 3 : 0);
        }}
        
        // ============== Indexing Status Panel ==============
        let indexingStartTime = null;
        let indexingTimerInterval = null;
        
        const INDEXING_STEPS = [
            {{ id: 'init', label: 'Initializing', detail: 'Preparing to index repository' }},
            {{ id: 'scan', label: 'Scanning Files', detail: 'Finding documentation and config files' }},
            {{ id: 'readme', label: 'Processing README', detail: 'Extracting project overview' }},
            {{ id: 'docs', label: 'Indexing Documentation', detail: 'Processing docs folder' }},
            {{ id: 'context', label: 'Extracting Context', detail: 'Build system, CI/CD, architecture' }},
            {{ id: 'services', label: 'Detecting Services', detail: 'Scanning for monorepo services' }},
            {{ id: 'commits', label: 'Analyzing Commits', detail: 'Recent git history' }},
            {{ id: 'save', label: 'Saving Workstream', detail: 'Creating workstream record' }},
        ];
        
        function showIndexingPanel(repoName) {{
            const panel = document.getElementById('indexing-panel');
            const stepsContainer = document.getElementById('indexing-steps');
            
            // Reset and show panel
            panel.classList.add('active');
            document.getElementById('indexing-progress-bar').style.width = '0%';
            document.getElementById('indexing-timer').textContent = '0:00';
            
            // Populate steps
            stepsContainer.innerHTML = INDEXING_STEPS.map((step, i) => `
                <div class="indexing-step pending" id="step-${{step.id}}">
                    <span class="icon"></span>
                    <div class="text">
                        <div>${{step.label}}</div>
                        <div class="detail">${{step.detail}}</div>
                    </div>
                </div>
            `).join('');
            
            // Start timer
            indexingStartTime = Date.now();
            indexingTimerInterval = setInterval(updateIndexingTimer, 1000);
            
            // Start first step
            updateIndexingStep('init', 'active');
        }}
        
        function updateIndexingTimer() {{
            const elapsed = Math.floor((Date.now() - indexingStartTime) / 1000);
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            document.getElementById('indexing-timer').textContent = `${{mins}}:${{secs.toString().padStart(2, '0')}}`;
        }}
        
        function updateIndexingStep(stepId, status) {{
            const stepEl = document.getElementById(`step-${{stepId}}`);
            if (!stepEl) return;
            
            // Update step status
            stepEl.className = `indexing-step ${{status}}`;
            
            // Update progress bar
            const stepIndex = INDEXING_STEPS.findIndex(s => s.id === stepId);
            const progress = ((stepIndex + (status === 'done' ? 1 : 0.5)) / INDEXING_STEPS.length) * 100;
            document.getElementById('indexing-progress-bar').style.width = `${{progress}}%`;
            
            // Auto-scroll to show current step
            stepEl.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
        }}
        
        function hideIndexingPanel(success = true) {{
            clearInterval(indexingTimerInterval);
            
            const panel = document.getElementById('indexing-panel');
            const elapsed = Math.floor((Date.now() - indexingStartTime) / 1000);
            
            if (success) {{
                // Show completion state briefly
                document.getElementById('indexing-progress-bar').style.width = '100%';
                const header = panel.querySelector('.indexing-header');
                header.innerHTML = `<h3>✓ Indexing Complete</h3><span class="indexing-timer">${{elapsed}}s</span>`;
                header.querySelector('h3').style.color = '#3fb950';
                
                setTimeout(() => {{
                    panel.classList.remove('active');
                }}, 2000);
            }} else {{
                panel.classList.remove('active');
            }}
        }}
        
        // ============== Index Modal ==============
        async function loadReposForModal() {{
            try {{
                const response = await fetch('/api/repos?profile={current_profile}');
                reposData = await response.json();
                renderRepoList();
            }} catch (e) {{
                console.error('Failed to load repos:', e);
                document.getElementById('repo-list').innerHTML = 
                    '<div class="empty-state">Failed to load repositories</div>';
            }}
        }}
        
        function renderRepoList() {{
            const container = document.getElementById('repo-list');
            
            if (reposData.length === 0) {{
                container.innerHTML = '<div class="empty-state">No repositories found in dev folder</div>';
                return;
            }}
            
            container.innerHTML = reposData.map(repo => `
                <div class="repo-item ${{repo.indexed ? 'indexed' : ''}}" data-path="${{repo.path}}">
                    <div class="repo-item-info">
                        <div class="repo-item-name">
                            ${{repo.indexed ? '✓ ' : ''}}${{repo.name}}
                        </div>
                        <div class="repo-item-path">${{repo.path}}</div>
                    </div>
                    <button class="repo-item-action" onclick="indexRepo('${{repo.path.replace(/'/g, "\\\\'")}}')">
                        ${{repo.indexed ? 'Re-index' : 'Index'}}
                    </button>
                </div>
            `).join('');
        }}
        
        function openIndexModal() {{
            document.getElementById('index-modal').classList.add('active');
            loadReposForModal();
        }}
        
        function closeIndexModal() {{
            document.getElementById('index-modal').classList.remove('active');
        }}
        
        // Close modal on backdrop click
        document.getElementById('index-modal').addEventListener('click', (e) => {{
            if (e.target.classList.contains('modal-overlay')) {{
                closeIndexModal();
            }}
        }});
        
        async function indexRepo(repoPath) {{
            const repoName = repoPath.split('/').pop();
            
            // Find and disable the button
            const repoItem = document.querySelector(`.repo-item[data-path="${{repoPath}}"]`);
            const btn = repoItem?.querySelector('.repo-item-action');
            if (btn) {{
                btn.disabled = true;
                btn.textContent = 'Indexing...';
            }}
            
            // Show indexing panel
            showIndexingPanel(repoName);
            
            try {{
                // Simulate step progression (actual indexing happens server-side)
                const progressInterval = setInterval(() => {{
                    // Progress handled by panel or SSE
                }}, 400);
                
                const response = await fetch('/api/repos/index?profile={current_profile}', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ path: repoPath }})
                }});
                
                clearInterval(progressInterval);
                
                // Mark all steps done
                INDEXING_STEPS.forEach(step => updateIndexingStep(step.id, 'done'));
                
                if (!response.ok) {{
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to index');
                }}
                
                const ws = await response.json();
                
                // Show success
                hideIndexingPanel(true);
                
                // Close modal and refresh
                closeIndexModal();
                
                // Refresh page to show new workstream
                setTimeout(() => location.reload(), 2000);
                
            }} catch (e) {{
                console.error('Failed to index repo:', e);
                hideIndexingPanel(false);
                if (btn) {{
                    btn.disabled = false;
                    btn.textContent = reposData.find(r => r.path === repoPath)?.indexed ? 'Re-index' : 'Index';
                }}
                alert('Failed to index repository: ' + e.message);
            }}
        }}
        
        document.addEventListener('DOMContentLoaded', () => {{
            initGraph();
            // Populate focus selector after workstreams are loaded
            setTimeout(populateFocusSelector, 100);
            observer.observe(document.getElementById('data-container'), {{ childList: true, subtree: true }});
        }});
    </script>
</body>
</html>
"""


def render_workstreams(workstreams: list) -> str:
    """Render workstreams as JSON data for the 3D graph."""
    import html
    import json

    if not workstreams:
        return '<div data-workstreams="[]"></div>'

    # Convert workstreams to JSON-serializable format
    ws_data = [ws.to_dict() for ws in workstreams]
    json_str = json.dumps(ws_data)
    # Escape for HTML attribute
    escaped = html.escape(json_str)

    return f'<div data-workstreams="{escaped}"></div>'


@app.on_event("startup")
async def startup():
    # Initialize all profile storages
    for profile in PROFILES:
        storage = get_storage(profile)
        await storage.initialize()


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    response: Response,
    profile: str | None = Query(default=None),
    workstream_profile: str | None = Cookie(default=None),
):
    """Serve the dashboard page."""
    # Priority: query param > cookie > default
    if profile is not None:
        selected_profile = profile if profile in PROFILES else DEFAULT_PROFILE
    elif workstream_profile is not None:
        selected_profile = workstream_profile if workstream_profile in PROFILES else DEFAULT_PROFILE
    else:
        selected_profile = DEFAULT_PROFILE

    # Set cookie to persist the profile choice
    response.set_cookie(
        key=PROFILE_COOKIE,
        value=selected_profile,
        max_age=60 * 60 * 24 * 365,  # 1 year
        httponly=False,  # Allow JS access for profile switcher
        samesite="lax",
    )

    return get_dashboard_html(selected_profile)


@app.get("/events")
async def events(request: Request, profile: str = Query(default=DEFAULT_PROFILE)):
    """SSE endpoint for live updates."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE

    storage = get_storage(profile)

    async def event_generator() -> AsyncGenerator[str, None]:
        # Track last modification time for THIS connection (not global)
        last_mod = 0.0  # Start at 0 to force initial send

        while True:
            if await request.is_disconnected():
                break

            # Check if data file was modified
            try:
                current_modified = storage.data_file.stat().st_mtime
            except FileNotFoundError:
                current_modified = 0.0

            # Send on first connect (last_mod=0) or when file changes
            if current_modified != last_mod or last_mod == 0.0:
                last_mod = current_modified if current_modified > 0 else -1.0  # Mark as sent
                await storage._load()  # Reload data
                workstreams = await storage.list()
                html = render_workstreams(workstreams)
                # Escape newlines for SSE
                html_escaped = html.replace("\n", "")
                yield f"data: {html_escaped}\n\n"

            await asyncio.sleep(1)  # Poll every second

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/workstreams")
async def list_workstreams(profile: str = Query(default=DEFAULT_PROFILE)):
    """API endpoint to list all workstreams."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()  # Ensure fresh data
    workstreams = await storage.list()
    return [ws.to_dict() for ws in workstreams]


@app.get("/api/workstreams/{workstream_id}", response_model=WorkstreamResponse)
async def get_workstream(workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """API endpoint to get a specific workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()
    ws = await storage.get(workstream_id)
    if ws:
        return ws.to_dict()
    raise HTTPException(status_code=404, detail="Workstream not found")


@app.post("/api/workstreams", response_model=WorkstreamResponse, status_code=201)
async def create_workstream(
    data: CreateWorkstreamModel, profile: str = Query(default=DEFAULT_PROFILE)
):
    """Create a new workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    # Validate parent exists if provided
    if data.parent_id:
        parent = await storage.get(data.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent workstream not found")

    request = CreateWorkstreamRequest(
        name=data.name,
        summary=data.summary,
        tags=data.tags,
        metadata=data.metadata,
        parent_id=data.parent_id,
    )
    ws = await storage.create(request)
    return ws.to_dict()


@app.put("/api/workstreams/{workstream_id}", response_model=WorkstreamResponse)
async def update_workstream(
    workstream_id: str,
    data: UpdateWorkstreamModel,
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Update an existing workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    # Validate workstream exists
    existing = await storage.get(workstream_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Workstream not found")

    # Validate parent exists if provided
    if data.parent_id:
        parent = await storage.get(data.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent workstream not found")

    request = UpdateWorkstreamRequest(
        id=workstream_id,
        name=data.name,
        summary=data.summary,
        tags=data.tags,
        metadata=data.metadata,
        parent_id=data.parent_id,
    )
    ws = await storage.update(request)
    return ws.to_dict()


@app.delete("/api/workstreams/{workstream_id}")
async def delete_workstream(workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """Delete a workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    success = await storage.delete(workstream_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workstream not found")
    return {"message": "Workstream deleted successfully"}


@app.post("/api/workstreams/{workstream_id}/notes", response_model=WorkstreamResponse)
async def add_note(
    workstream_id: str,
    data: AddNoteModel,
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Add a note to a workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    ws = await storage.add_note(workstream_id, data.note, data.category)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstream not found")
    return ws.to_dict()


@app.get("/api/workstreams/{workstream_id}/notes")
async def get_notes(workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """Get all notes for a workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    notes = await storage.get_notes(workstream_id)
    if notes is None:
        raise HTTPException(status_code=404, detail="Workstream not found")
    return {"notes": [{"index": i, "content": note} for i, note in enumerate(notes)]}


@app.put("/api/workstreams/{workstream_id}/notes/{note_index}", response_model=WorkstreamResponse)
async def update_note(
    workstream_id: str,
    note_index: int,
    data: UpdateNoteModel,
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Update a note at a specific index."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    ws = await storage.update_note(workstream_id, note_index, data.content, data.category)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstream or note not found")
    return ws.to_dict()


@app.delete(
    "/api/workstreams/{workstream_id}/notes/{note_index}", response_model=WorkstreamResponse
)
async def delete_note(
    workstream_id: str,
    note_index: int,
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Delete a note at a specific index."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    ws = await storage.delete_note(workstream_id, note_index)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstream or note not found")
    return ws.to_dict()


@app.get("/api/workstreams/{workstream_id}/children")
async def get_children(workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """Get all direct children of a workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    # Validate parent exists
    parent = await storage.get(workstream_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Workstream not found")

    children = await storage.get_children(workstream_id)
    return [ws.to_dict() for ws in children]


@app.post("/api/workstreams/search")
async def search_workstreams(data: SearchModel, profile: str = Query(default=DEFAULT_PROFILE)):
    """Search workstreams by query text or tags."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    results = []

    # Search by text query
    if data.query:
        text_results = await storage.search(data.query)
        results.extend(text_results)

    # Search by tags
    if data.tags:
        tag_results = await storage.search_by_tags(data.tags, data.match_all)
        # Merge results (avoid duplicates)
        existing_ids = {ws.id for ws in results}
        for ws in tag_results:
            if ws.id not in existing_ids:
                results.append(ws)

    return [ws.to_dict() for ws in results]


# ============== Template API Endpoints ==============


@app.get("/api/templates")
async def list_templates(profile: str = Query(default=DEFAULT_PROFILE)):
    """List all templates."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    template_storage = get_template_storage(profile)
    await template_storage.initialize()

    templates = await template_storage.list_templates()
    return [t.to_dict() for t in templates]


@app.post("/api/templates", response_model=TemplateResponse, status_code=201)
async def create_template(data: CreateTemplateModel, profile: str = Query(default=DEFAULT_PROFILE)):
    """Create a new template."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    template_storage = get_template_storage(profile)
    await template_storage.initialize()

    request = CreateTemplateRequest(
        name=data.name,
        description=data.description,
        default_tags=data.default_tags,
        default_metadata=data.default_metadata,
        note_templates=data.note_templates,
    )
    template = await template_storage.create_template(request)
    return template.to_dict()


@app.get("/api/templates/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """Get a template by ID."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    template_storage = get_template_storage(profile)
    await template_storage.initialize()

    template = await template_storage.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template.to_dict()


@app.delete("/api/templates/{template_id}")
async def delete_template(template_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """Delete a template."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    template_storage = get_template_storage(profile)
    await template_storage.initialize()

    deleted = await template_storage.delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": f"Template {template_id} deleted"}


@app.post(
    "/api/templates/{template_id}/instantiate", response_model=WorkstreamResponse, status_code=201
)
async def instantiate_template(
    template_id: str,
    data: InstantiateTemplateModel,
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Create a workstream from a template."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    template_storage = get_template_storage(profile)
    await template_storage.initialize()
    storage = get_storage(profile)
    await storage._load()

    request = InstantiateTemplateRequest(
        template_id=template_id,
        name=data.name,
        summary=data.summary,
        additional_tags=data.additional_tags,
        metadata_overrides=data.metadata_overrides,
        parent_id=data.parent_id,
    )

    workstream = await template_storage.create_from_template(request, storage)
    if not workstream:
        raise HTTPException(status_code=404, detail="Template not found")
    return workstream.to_dict()


class SearchRequest(BaseModel):
    """Request body for search endpoint."""

    q: str
    limit: int = 20
    fields: list[str] | None = None


class SearchResult(BaseModel):
    """A single search result."""

    id: str
    name: str
    summary: str
    tags: list[str]
    parent_id: str | None
    score: float
    highlights: dict[str, str]


class SearchResponse(BaseModel):
    """Response from search endpoint."""

    query: str
    total: int
    results: list[SearchResult]


@app.post("/api/search")
async def search_workstreams(
    request: SearchRequest,
    profile: str = Query(default=DEFAULT_PROFILE),
) -> SearchResponse:
    """
    Full-text search across workstreams.

    Supports AND/OR operators, phrase search, and field-specific queries.

    Examples:
    - Simple: {"q": "api deployment"}
    - AND: {"q": "api AND deployment"}
    - OR: {"q": "frontend OR backend"}
    - Phrase: {"q": '"exact phrase"'}
    - Field-specific: {"q": "name:api tags:python"}
    """
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    # Rebuild index if needed (first search after load)
    search_engine = storage._get_search_engine()
    results = search_engine.search(
        query=request.q,
        limit=request.limit,
        fields=request.fields,
    )

    return SearchResponse(
        query=request.q,
        total=len(results),
        results=[SearchResult(**r) for r in results],
    )


# Relationship endpoints
@app.get("/api/workstreams/{workstream_id}/relationships", response_model=RelationshipsResponse)
async def get_relationships(workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """Get all relationships for a workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    relationships = await storage.get_relationships(workstream_id)
    if relationships is None:
        raise HTTPException(status_code=404, detail="Workstream not found")
    return relationships


@app.post("/api/workstreams/{workstream_id}/relationships", response_model=WorkstreamResponse)
async def add_relationship(
    workstream_id: str,
    data: AddRelationshipModel,
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Add a relationship to a workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    # Validate relationship type
    if data.relationship_type not in storage.RELATIONSHIP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid relationship type. Must be one of: {', '.join(storage.RELATIONSHIP_TYPES)}",
        )

    # Validate target exists
    target = await storage.get(data.target_id)
    if not target:
        raise HTTPException(status_code=400, detail="Target workstream not found")

    # Prevent self-reference
    if workstream_id == data.target_id:
        raise HTTPException(status_code=400, detail="Cannot create relationship to self")

    ws = await storage.add_relationship(workstream_id, data.target_id, data.relationship_type)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstream not found")
    return ws.to_dict()


@app.delete("/api/workstreams/{workstream_id}/relationships/{relationship_type}/{target_id}")
async def remove_relationship(
    workstream_id: str,
    relationship_type: str,
    target_id: str,
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Remove a relationship from a workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    # Validate relationship type
    if relationship_type not in storage.RELATIONSHIP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid relationship type. Must be one of: {', '.join(storage.RELATIONSHIP_TYPES)}",
        )

    ws = await storage.remove_relationship(workstream_id, target_id, relationship_type)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstream not found")
    return {"message": "Relationship removed successfully"}


@app.get("/api/workstreams/{workstream_id}/dependents")
async def get_dependents(workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """Get all workstreams that depend on this one."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    # Validate workstream exists
    ws = await storage.get(workstream_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstream not found")

    dependents = await storage.get_dependents(workstream_id)
    return [ws.to_dict() for ws in dependents]


@app.get("/api/workstreams/{workstream_id}/activity")
async def get_activity(
    workstream_id: str,
    profile: str = Query(default=DEFAULT_PROFILE),
    days: int = Query(default=7, description="Number of days of activity to fetch"),
):
    """Get recent git activity (commits) for a workstream's repo."""
    import subprocess
    from datetime import datetime, timedelta

    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    ws = await storage.get(workstream_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstream not found")

    # Get repo path from metadata
    repo_path = None
    if ws.metadata:
        if hasattr(ws.metadata, 'extra') and ws.metadata.extra:
            repo_path = ws.metadata.extra.get("repo_path")
        elif hasattr(ws.metadata, '__dict__'):
            repo_path = ws.metadata.__dict__.get("repo_path")
    
    if not repo_path:
        return {"commits": [], "error": "No repo path found"}

    # Handle container path mapping (e.g., /host-dev/... -> ~/dev/...)
    if repo_path.startswith("/host-dev/"):
        repo_name = repo_path.replace("/host-dev/", "")
        repo_path = str(Path.home() / "dev" / repo_name)

    # Check if path exists
    if not Path(repo_path).exists():
        return {"commits": [], "error": f"Repo path not found: {repo_path}"}

    # Get recent commits
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                repo_path,
                "log",
                f"--since={since_date}",
                "--pretty=format:%H|%an|%ae|%at|%s",
                "-n",
                "20",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        commits = []
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                parts = line.split("|", 4)
                if len(parts) == 5:
                    commits.append(
                        {
                            "sha": parts[0][:7],
                            "author": parts[1],
                            "email": parts[2],
                            "timestamp": int(parts[3]),
                            "message": parts[4],
                        }
                    )
        return {"commits": commits, "repo_path": repo_path}
    except Exception as e:
        return {"commits": [], "error": str(e)}


@app.get("/api/workstreams/{workstream_id}/branches")
async def get_branches(
    workstream_id: str,
    profile: str = Query(default=DEFAULT_PROFILE),
    days: int = Query(default=14, description="Filter branches active in last N days"),
):
    """Get active git branches for a workstream's repo."""
    import subprocess
    from datetime import datetime, timedelta

    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    ws = await storage.get(workstream_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstream not found")

    # Get repo path from metadata
    repo_path = None
    if ws.metadata:
        if hasattr(ws.metadata, 'extra') and ws.metadata.extra:
            repo_path = ws.metadata.extra.get("repo_path")
        elif hasattr(ws.metadata, '__dict__'):
            repo_path = ws.metadata.__dict__.get("repo_path")

    if not repo_path:
        return {"branches": [], "error": "No repo path found"}

    # Handle container path mapping
    if repo_path.startswith("/host-dev/"):
        repo_name = repo_path.replace("/host-dev/", "")
        repo_path = str(Path.home() / "dev" / repo_name)

    if not Path(repo_path).exists():
        return {"branches": [], "error": f"Repo path not found: {repo_path}"}

    try:
        # Get current branch
        current_result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        current_branch = current_result.stdout.strip() if current_result.returncode == 0 else None

        # Get branches with commit timestamps
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        result = subprocess.run(
            [
                "git", "-C", repo_path, "for-each-ref",
                "--sort=-committerdate",
                "--format=%(refname:short)|%(committerdate:relative)|%(committerdate:unix)|%(subject)",
                "refs/heads/"
            ],
            capture_output=True, text=True, timeout=10
        )
        
        branches = []
        cutoff_timestamp = (datetime.now() - timedelta(days=days)).timestamp()
        
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                parts = line.split("|", 3)
                if len(parts) >= 3:
                    try:
                        commit_ts = int(parts[2])
                        # Only include branches with activity in last N days
                        if commit_ts >= cutoff_timestamp:
                            branches.append({
                                "name": parts[0],
                                "time": parts[1],
                                "message": parts[3] if len(parts) > 3 else "",
                                "current": parts[0] == current_branch
                            })
                    except ValueError:
                        pass
        
        return {"branches": branches, "current": current_branch, "repo_path": repo_path}
    except Exception as e:
        return {"branches": [], "error": str(e)}


@app.get("/api/workstreams/{workstream_id}/connections")
async def get_connections(workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """Get all connected workstreams (relationships, children, dependents)."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    ws = await storage.get(workstream_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workstream not found")

    def ws_to_summary(w):
        ws_type = "project"
        if w.metadata and hasattr(w.metadata, 'extra') and w.metadata.extra:
            ws_type = w.metadata.extra.get("type", "project")
        return {"id": w.id, "name": w.name, "type": ws_type}

    # Get relationships
    relationships = await storage.get_relationships(workstream_id)

    # Get children
    children = await storage.get_children(workstream_id)

    # Get dependents
    dependents = await storage.get_dependents(workstream_id)

    # Get parent if exists
    parent = None
    if ws.parent_id:
        parent_ws = await storage.get(ws.parent_id)
        if parent_ws:
            parent = ws_to_summary(parent_ws)

    # Handle relationships - could be dict or Pydantic model
    rel_data = {}
    if relationships:
        if hasattr(relationships, 'model_dump'):
            rel_data = relationships.model_dump()
        elif isinstance(relationships, dict):
            rel_data = relationships

    return {
        "parent": parent,
        "children": [ws_to_summary(c) for c in children],
        "dependents": [ws_to_summary(d) for d in dependents],
        "relationships": rel_data,
    }


# ============== Repo Scanner API ==============

# Configurable dev directory (can be overridden via env var)
DEV_DIRECTORY = Path(os.environ.get("MEM_DEV_DIR", os.path.expanduser("~/dev")))


class RepoInfo(BaseModel):
    """Information about a local repository."""

    name: str
    path: str
    indexed: bool = False
    workstream_id: str | None = None


@app.get("/api/repos")
async def list_repos(profile: str = Query(default=DEFAULT_PROFILE)) -> list[RepoInfo]:
    """List all git repositories in the dev directory."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    repos = []

    if not DEV_DIRECTORY.exists():
        return repos

    # Get all indexed workstreams to check which repos are already indexed
    # Match by repo name since paths may differ (container vs host)
    workstreams = await storage.list()
    indexed_repos = {}  # name -> workstream_id
    for ws in workstreams:
        # Check metadata for repo_path
        meta = ws.metadata
        repo_path = None
        if hasattr(meta, "extra") and meta.extra:
            repo_path = meta.extra.get("repo_path")
        elif hasattr(meta, "__dict__"):
            repo_path = getattr(meta, "repo_path", None) or meta.__dict__.get("repo_path")
        if repo_path:
            # Extract repo name from path
            repo_name = Path(repo_path).name
            indexed_repos[repo_name] = ws.id

    # Scan dev directory for git repos
    for item in DEV_DIRECTORY.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            git_dir = item / ".git"
            if git_dir.exists():
                resolved_path = str(item.resolve())
                repos.append(
                    RepoInfo(
                        name=item.name,
                        path=resolved_path,
                        indexed=item.name in indexed_repos,
                        workstream_id=indexed_repos.get(item.name),
                    )
                )

    # Sort by name
    repos.sort(key=lambda r: r.name.lower())
    return repos


@app.post("/api/repos/index")
async def index_repo(
    path: str = Body(..., embed=True),
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Index a local repository and create or update a workstream."""
    from .indexers.local_repo_indexer import LocalRepoIndexer
    from .server import extract_project_context
    from .types import UpdateWorkstreamRequest

    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()

    repo_path = Path(path).expanduser().resolve()

    # Handle path mapping: if path doesn't exist, try mapping common host paths to container paths
    if not repo_path.exists():
        # Common mappings: /Users/*/dev/* -> /host-dev/*
        path_str = str(repo_path)
        if "/dev/" in path_str:
            # Extract repo name and try container path
            repo_name = repo_path.name
            container_path = DEV_DIRECTORY / repo_name
            if container_path.exists():
                repo_path = container_path

    repo_path_str = str(repo_path)

    if not repo_path.exists():
        raise HTTPException(status_code=404, detail=f"Path does not exist: {repo_path}")

    if not (repo_path / ".git").exists():
        raise HTTPException(status_code=400, detail=f"Not a git repository: {repo_path}")

    # Check for existing workstream with same repo_path
    existing_workstream = None
    all_workstreams = await storage.list()
    for ws in all_workstreams:
        ws_repo_path = None
        if hasattr(ws.metadata, "extra") and ws.metadata.extra:
            ws_repo_path = ws.metadata.extra.get("repo_path")
        elif hasattr(ws.metadata, "__dict__"):
            ws_repo_path = ws.metadata.__dict__.get("repo_path")
        if ws_repo_path == repo_path_str:
            existing_workstream = ws
            break

    try:
        indexer = LocalRepoIndexer(str(repo_path))
        ws_request, notes = await indexer.index_repository()

        # Extract and add project context to metadata
        context = extract_project_context(repo_path)
        ws_request.metadata["is_monorepo"] = context.get("is_monorepo", False)
        ws_request.metadata["commands"] = context.get("commands", {})
        ws_request.metadata["setup_instructions"] = context.get("setup", [])
        ws_request.metadata["project_type"] = context.get("project_type", "unknown")
        ws_request.metadata["build_system"] = context.get("build_system", [])
        ws_request.metadata["architectures"] = context.get("architectures", [])
        ws_request.metadata["languages"] = context.get("languages", [])
        ws_request.metadata["ci_cd"] = context.get("ci_cd", [])
        ws_request.metadata["deployment"] = context.get("deployment", {})
        if context.get("services"):
            ws_request.metadata["services"] = context["services"]

        # Create or update workstream
        if existing_workstream:
            # Update existing workstream
            update_request = UpdateWorkstreamRequest(
                id=existing_workstream.id,
                name=ws_request.name,
                summary=ws_request.summary,
                tags=ws_request.tags,
                metadata=ws_request.metadata,
            )
            workstream = await storage.update(update_request)
        else:
            # Create new workstream
            workstream = await storage.create(ws_request)

        # Add notes (only for new workstreams to avoid duplicates)
        if not existing_workstream:
            for note in notes:
                await storage.add_note(
                    workstream.id,
                    note["content"],
                    note.get("category", "CONTEXT"),
                )

        # Create or update child workstreams for monorepo services
        if context.get("is_monorepo") and context.get("services"):
            for svc_name, svc_info in context["services"].items():
                svc_path = repo_path / svc_info["path"]
                svc_path_str = str(svc_path)

                # Check for existing service workstream
                existing_svc = None
                for ws in all_workstreams:
                    ws_repo_path = None
                    if hasattr(ws.metadata, "extra") and ws.metadata.extra:
                        ws_repo_path = ws.metadata.extra.get("repo_path")
                    elif hasattr(ws.metadata, "__dict__"):
                        ws_repo_path = ws.metadata.__dict__.get("repo_path")
                    if ws_repo_path == svc_path_str:
                        existing_svc = ws
                        break

                svc_metadata = {
                    "service_name": svc_name,
                    "service_type": svc_info["type"],
                    "service_path": svc_info["path"],
                    "commands": svc_info.get("commands", {}),
                    "repo_path": svc_path_str,
                }

                if existing_svc:
                    # Update existing service workstream
                    svc_update = UpdateWorkstreamRequest(
                        id=existing_svc.id,
                        name=f"Service: {svc_name}",
                        summary=f"Monorepo service - {svc_info['type']} module at {svc_info['path']}",
                        tags=["service", svc_info["type"], svc_name],
                        parent_id=workstream.id,
                        metadata=svc_metadata,
                    )
                    svc_ws = await storage.update(svc_update)
                else:
                    # Create new service workstream
                    svc_request = CreateWorkstreamRequest(
                        name=f"Service: {svc_name}",
                        summary=f"Monorepo service - {svc_info['type']} module at {svc_info['path']}",
                        tags=["service", svc_info["type"], svc_name],
                        parent_id=workstream.id,
                        metadata=svc_metadata,
                    )
                    svc_ws = await storage.create(svc_request)

                    # Add README note if exists (only for new services)
                    readme_file = svc_path / "README.md"
                    if readme_file.exists():
                        try:
                            readme_content = readme_file.read_text()[:3000]
                            await storage.add_note(
                                svc_ws.id, f"[README]\n{readme_content}", "CONTEXT"
                            )
                        except Exception:
                            pass

        # Reload to get notes
        workstream = await storage.get(workstream.id)

        return workstream.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index repository: {e}")


@app.get("/api/repos/active")
async def get_active_repo(
    active_repo: str | None = Cookie(default=None),
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Get the currently active repository."""
    return {"active_repo": active_repo}


@app.post("/api/repos/active")
async def set_active_repo(
    response: Response,
    path: str = Body(..., embed=True),
):
    """Set the active repository (stored in cookie)."""
    response.set_cookie(
        key="active_repo",
        value=path,
        max_age=60 * 60 * 24 * 365,  # 1 year
        httponly=False,  # Allow JS access
    )
    return {"active_repo": path}


# ============== Temporal Workflow API ==============


class WorkflowStatus(BaseModel):
    """Status of a Temporal workflow."""

    workflow_id: str
    run_id: str | None = None
    status: str
    workflow_type: str | None = None
    start_time: str | None = None
    close_time: str | None = None
    error: str | None = None


@app.post("/api/workflows/index-local")
async def start_index_local_workflow(
    path: str = Body(..., embed=True),
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Start a Temporal workflow to index a local repository.

    Returns immediately with workflow ID for status tracking.
    """
    import os

    # Check if Temporal is available
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")

    try:
        from .workflows.client import start_local_indexing

        handle = await start_local_indexing(path, profile=profile)
        return {
            "workflow_id": handle.workflow_id,
            "run_id": handle.run_id,
            "status": "RUNNING",
            "message": f"Indexing workflow started for {path}",
        }
    except Exception as e:
        # Fall back to sync indexing if Temporal is not available
        raise HTTPException(
            status_code=503,
            detail=f"Temporal workflow service unavailable: {e}. Use /api/repos/index for sync indexing.",
        )


@app.post("/api/workflows/index-github")
async def start_index_github_workflow(
    owner: str = Body(...),
    repo: str = Body(...),
    profile: str = Query(default=DEFAULT_PROFILE),
):
    """Start a Temporal workflow to index a GitHub repository.

    Returns immediately with workflow ID for status tracking.
    """
    try:
        from .workflows.client import start_github_indexing

        handle = await start_github_indexing(owner, repo, profile=profile)
        return {
            "workflow_id": handle.workflow_id,
            "run_id": handle.run_id,
            "status": "RUNNING",
            "message": f"Indexing workflow started for {owner}/{repo}",
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Temporal workflow service unavailable: {e}")


@app.get("/api/workflows/{workflow_id}")
async def get_workflow_status(workflow_id: str) -> WorkflowStatus:
    """Get the status of a workflow."""
    try:
        from .workflows.client import get_workflow_status as get_status

        status = await get_status(workflow_id)
        return WorkflowStatus(**status)
    except Exception as e:
        return WorkflowStatus(
            workflow_id=workflow_id,
            status="ERROR",
            error=str(e),
        )


@app.get("/api/workflows/{workflow_id}/result")
async def get_workflow_result_endpoint(workflow_id: str):
    """Get the result of a completed workflow."""
    try:
        from .workflows.client import get_workflow_result

        result = await get_workflow_result(workflow_id)
        return {
            "success": result.success,
            "workstream_id": result.workstream_id,
            "workstream_name": result.workstream_name,
            "notes_added": result.notes_added,
            "services_indexed": result.services_indexed,
            "error": result.error,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflows")
async def list_workflows_endpoint(
    workflow_type: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
):
    """List recent workflows."""
    try:
        from .workflows.client import list_workflows

        query = ""
        if workflow_type:
            query = f'WorkflowType="{workflow_type}"'

        workflows = await list_workflows(query=query)
        return {"workflows": workflows[:limit]}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Temporal service unavailable: {e}")


def main():
    """Run the web UI server."""
    import argparse
    import signal
    import socket
    import sys

    import uvicorn

    parser = argparse.ArgumentParser(description="Workstream Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Port to run on (default: 8080)")
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--force", "-f", action="store_true", help="Kill existing process on port if needed"
    )
    args = parser.parse_args()

    def is_port_in_use(port: int) -> bool:
        """Check if a port is already in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def kill_process_on_port(port: int) -> bool:
        """Kill process using the given port. Returns True if successful."""
        import subprocess

        try:
            # Find PID using the port
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    if pid:
                        subprocess.run(["kill", "-9", pid], timeout=5)
                        print(f"Killed existing process {pid} on port {port}")
                return True
        except Exception as e:
            print(f"Warning: Could not kill process on port {port}: {e}")
        return False

    # Check if port is in use
    if is_port_in_use(args.port):
        if args.force:
            print(f"Port {args.port} in use, killing existing process...")
            kill_process_on_port(args.port)
            # Brief wait for port to be released
            import time

            time.sleep(0.5)
        else:
            print(f"Error: Port {args.port} is already in use.")
            print("  - Run with --force to kill the existing process")
            print("  - Or use --port <number> to use a different port")
            sys.exit(1)

    print(f"Starting Workstream Dashboard at http://localhost:{args.port}")
    print(f"Available profiles: {', '.join(PROFILES)}")
    print("Press Ctrl+C to stop")

    # Configure uvicorn for clean shutdown
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",  # Reduce noise
        timeout_graceful_shutdown=2,  # Quick shutdown
    )
    server = uvicorn.Server(config)

    # Handle signals for clean shutdown
    def signal_handler(signum, frame):
        print("\nShutting down...")
        server.should_exit = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        server.run()
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
