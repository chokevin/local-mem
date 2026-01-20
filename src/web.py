"""
Web UI for viewing workstreams.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from .storage import DEFAULT_PROFILE, WorkstreamStorage
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
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class CreateWorkstreamModel(BaseModel):
    """Pydantic model for creating a workstream."""

    name: str = Field(..., min_length=1, description="Name of the workstream")
    summary: str = Field(..., description="Summary/description of the workstream")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")
    parent_id: str | None = Field(default=None, alias="parentId", description="Parent workstream ID")

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

# Cookie name for profile persistence
PROFILE_COOKIE = "workstream_profile"

# Available profiles
PROFILES = ["test", "prod"]

app = FastAPI(title="Workstream Dashboard")

# Storage instances for each profile
_storages: dict[str, WorkstreamStorage] = {}


def get_storage(profile: str) -> WorkstreamStorage:
    """Get or create storage for a profile."""
    if profile not in _storages:
        _storages[profile] = WorkstreamStorage(profile=profile)
    return _storages[profile]


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
    
    <div class="instructions" id="instructions">
        <p>🖱️ Drag nodes to reposition · 🔍 Scroll to zoom · 👆 Click for details</p>
    </div>
    
    <div id="data-container" hx-ext="sse" sse-connect="/events?profile={current_profile}" sse-swap="message" hx-swap="innerHTML"></div>
    
    <script>
        let svg, simulation, nodeGroup, linkGroup;
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
            const zoom = d3.zoom()
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
        
        document.addEventListener('DOMContentLoaded', () => {{
            initGraph();
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
        selected_profile = (
            workstream_profile if workstream_profile in PROFILES else DEFAULT_PROFILE
        )
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
                last_mod = (
                    current_modified if current_modified > 0 else -1.0
                )  # Mark as sent
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
async def get_workstream(
    workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)
):
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
async def delete_workstream(
    workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)
):
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
async def get_notes(
    workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)
):
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


@app.delete("/api/workstreams/{workstream_id}/notes/{note_index}", response_model=WorkstreamResponse)
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
async def get_children(
    workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)
):
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
async def search_workstreams(
    data: SearchModel, profile: str = Query(default=DEFAULT_PROFILE)
):
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


def main():
    """Run the web UI server."""
    import argparse
    import signal
    import socket
    import sys

    import uvicorn

    parser = argparse.ArgumentParser(description="Workstream Dashboard")
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to run on (default: 8080)"
    )
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
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
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
