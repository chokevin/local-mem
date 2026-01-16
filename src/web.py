"""
Web UI for viewing workstreams.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from .storage import DEFAULT_PROFILE, WorkstreamStorage

# Available profiles
PROFILES = ["test", "prod"]

app = FastAPI(title="Workstream Dashboard")

# Storage instances for each profile
_storages: dict[str, WorkstreamStorage] = {}

# Track file modification time for SSE updates per profile
_last_modified: dict[str, float] = {}


def get_storage(profile: str) -> WorkstreamStorage:
    """Get or create storage for a profile."""
    if profile not in _storages:
        _storages[profile] = WorkstreamStorage(profile=profile)
    return _storages[profile]


def get_dashboard_html(current_profile: str) -> str:
    """Return the dashboard HTML."""
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
    <title>Workstream Dashboard - {current_profile.title()}</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10/dist/ext/sse.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            min-height: 100vh;
            padding: 2rem;
        }}
        
        .container {{ max-width: 1200px; margin: 0 auto; }}
        
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #30363d;
        }}
        
        .header-left {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        
        h1 {{
            font-size: 1.5rem;
            font-weight: 600;
            color: #f0f6fc;
        }}
        
        .profile-selector {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .profile-selector label {{
            font-size: 0.875rem;
            color: #8b949e;
        }}
        
        .profile-selector select {{
            background: #21262d;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #c9d1d9;
            padding: 0.375rem 0.75rem;
            font-size: 0.875rem;
            cursor: pointer;
        }}
        
        .profile-selector select:hover {{
            border-color: #58a6ff;
        }}
        
        .profile-badge {{
            background: {("#3fb950" if current_profile == "prod" else "#58a6ff")}26;
            color: {"#3fb950" if current_profile == "prod" else "#58a6ff"};
            padding: 0.25rem 0.75rem;
            border-radius: 2rem;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .status {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
            color: #8b949e;
        }}
        
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #3fb950;
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        
        .workstreams {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1rem;
        }}
        
        .workstream-card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 1.25rem;
            transition: border-color 0.2s, transform 0.2s;
        }}
        
        .workstream-card:hover {{
            border-color: #58a6ff;
            transform: translateY(-2px);
        }}
        
        .workstream-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 0.75rem;
        }}
        
        .workstream-name {{
            font-size: 1.125rem;
            font-weight: 600;
            color: #58a6ff;
        }}
        
        .workstream-id {{
            font-size: 0.75rem;
            color: #8b949e;
            font-family: monospace;
        }}
        
        .workstream-summary {{
            color: #c9d1d9;
            font-size: 0.9rem;
            line-height: 1.5;
            margin-bottom: 1rem;
        }}
        
        .tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }}
        
        .tag {{
            background: #388bfd26;
            color: #58a6ff;
            padding: 0.25rem 0.625rem;
            border-radius: 2rem;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        
        .metadata {{
            background: #0d1117;
            border-radius: 6px;
            padding: 0.75rem;
            font-size: 0.8rem;
        }}
        
        .metadata-item {{
            display: flex;
            justify-content: space-between;
            padding: 0.25rem 0;
            border-bottom: 1px solid #21262d;
        }}
        
        .metadata-item:last-child {{ border-bottom: none; }}
        
        .metadata-key {{
            color: #8b949e;
        }}
        
        .metadata-value {{
            color: #c9d1d9;
            font-family: monospace;
            font-size: 0.75rem;
        }}
        
        .notes-section {{
            background: #1c2128;
            border-radius: 6px;
            padding: 0.75rem;
            margin-top: 0.75rem;
            font-size: 0.8rem;
        }}
        
        .notes-header {{
            color: #8b949e;
            font-weight: 500;
            margin-bottom: 0.5rem;
        }}
        
        .note {{
            color: #c9d1d9;
            padding: 0.5rem;
            background: #0d1117;
            border-radius: 4px;
            margin-bottom: 0.5rem;
            font-size: 0.75rem;
            line-height: 1.4;
        }}
        
        .note:last-child {{ margin-bottom: 0; }}
        
        .timestamps {{
            margin-top: 1rem;
            padding-top: 0.75rem;
            border-top: 1px solid #21262d;
            font-size: 0.75rem;
            color: #8b949e;
            display: flex;
            justify-content: space-between;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 4rem 2rem;
            color: #8b949e;
        }}
        
        .empty-state h2 {{
            font-size: 1.25rem;
            margin-bottom: 0.5rem;
            color: #c9d1d9;
        }}
        
        .empty-state p {{
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-left">
                <h1>📋 Workstream Dashboard</h1>
                <span class="profile-badge">{current_profile}</span>
            </div>
            <div class="status">
                <div class="profile-selector">
                    <label for="profile">Profile:</label>
                    <select id="profile" onchange="window.location.href='/?profile=' + this.value">
                        {profile_options}
                    </select>
                </div>
                <div class="status-dot"></div>
                <span>Live</span>
            </div>
        </header>
        
        <main hx-ext="sse" sse-connect="/events?profile={current_profile}" sse-swap="message" hx-swap="innerHTML">
            <div class="empty-state">
                <h2>Connecting...</h2>
                <p>Waiting for workstream data</p>
            </div>
        </main>
    </div>
</body>
</html>
"""


def render_workstreams(workstreams: list) -> str:
    """Render workstreams as HTML cards."""
    if not workstreams:
        return """
        <div class="empty-state">
            <h2>No workstreams yet</h2>
            <p>Create a workstream using the MCP server to see it here</p>
        </div>
        """
    
    cards = []
    for ws in sorted(workstreams, key=lambda x: x.updated_at, reverse=True):
        tags_html = "".join(f'<span class="tag">{tag}</span>' for tag in ws.tags)
        
        # Build metadata section
        metadata_items = []
        meta = ws.metadata
        if meta.host_ips:
            metadata_items.append(f'''
                <div class="metadata-item">
                    <span class="metadata-key">Host IPs</span>
                    <span class="metadata-value">{", ".join(meta.host_ips)}</span>
                </div>
            ''')
        if meta.connection_info:
            metadata_items.append(f'''
                <div class="metadata-item">
                    <span class="metadata-key">Connection</span>
                    <span class="metadata-value">{meta.connection_info}</span>
                </div>
            ''')
        if meta.testing_info:
            metadata_items.append(f'''
                <div class="metadata-item">
                    <span class="metadata-key">Testing</span>
                    <span class="metadata-value">{meta.testing_info}</span>
                </div>
            ''')
        for key, value in meta.extra.items():
            metadata_items.append(f'''
                <div class="metadata-item">
                    <span class="metadata-key">{key}</span>
                    <span class="metadata-value">{value}</span>
                </div>
            ''')
        
        metadata_html = ""
        if metadata_items:
            metadata_html = f'''
                <div class="metadata">
                    {"".join(metadata_items)}
                </div>
            '''
        
        # Build notes section
        notes_html = ""
        if ws.notes:
            notes_list = "".join(f'<div class="note">{note}</div>' for note in ws.notes[-3:])  # Show last 3
            notes_count = f" ({len(ws.notes)} total)" if len(ws.notes) > 3 else ""
            notes_html = f'''
                <div class="notes-section">
                    <div class="notes-header">📝 Notes{notes_count}</div>
                    {notes_list}
                </div>
            '''
        
        # Format timestamps
        created = ws.created_at[:19].replace("T", " ")
        updated = ws.updated_at[:19].replace("T", " ")
        
        cards.append(f'''
            <div class="workstream-card">
                <div class="workstream-header">
                    <span class="workstream-name">{ws.name}</span>
                    <span class="workstream-id">{ws.id}</span>
                </div>
                <p class="workstream-summary">{ws.summary}</p>
                <div class="tags">{tags_html}</div>
                {metadata_html}
                {notes_html}
                <div class="timestamps">
                    <span>Created: {created}</span>
                    <span>Updated: {updated}</span>
                </div>
            </div>
        ''')
    
    return f'<div class="workstreams">{"".join(cards)}</div>'


@app.on_event("startup")
async def startup():
    # Initialize all profile storages
    for profile in PROFILES:
        storage = get_storage(profile)
        await storage.initialize()
        _last_modified[profile] = 0.0


@app.get("/", response_class=HTMLResponse)
async def dashboard(profile: str = Query(default=DEFAULT_PROFILE)):
    """Serve the dashboard page."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    return get_dashboard_html(profile)


@app.get("/events")
async def events(request: Request, profile: str = Query(default=DEFAULT_PROFILE)):
    """SSE endpoint for live updates."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    
    storage = get_storage(profile)
    
    async def event_generator() -> AsyncGenerator[str, None]:
        last_mod = _last_modified.get(profile, 0.0)
        
        while True:
            if await request.is_disconnected():
                break
            
            # Check if data file was modified
            try:
                current_modified = storage.data_file.stat().st_mtime
            except FileNotFoundError:
                current_modified = 0.0
            
            # Always send on first connect or when file changes
            if current_modified != last_mod:
                last_mod = current_modified
                _last_modified[profile] = current_modified
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


@app.get("/api/workstreams/{workstream_id}")
async def get_workstream(workstream_id: str, profile: str = Query(default=DEFAULT_PROFILE)):
    """API endpoint to get a specific workstream."""
    if profile not in PROFILES:
        profile = DEFAULT_PROFILE
    storage = get_storage(profile)
    await storage._load()
    ws = await storage.get(workstream_id)
    if ws:
        return ws.to_dict()
    return {"error": "Not found"}, 404


def main():
    """Run the web UI server."""
    import argparse
    import uvicorn
    
    parser = argparse.ArgumentParser(description="Workstream Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Port to run on (default: 8080)")
    args = parser.parse_args()
    
    print(f"Starting Workstream Dashboard at http://localhost:{args.port}")
    print(f"Available profiles: {', '.join(PROFILES)}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
