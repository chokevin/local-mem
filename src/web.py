"""
Web UI for viewing workstreams.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Cookie, FastAPI, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from .storage import DEFAULT_PROFILE, WorkstreamStorage

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
            background: linear-gradient(135deg, #8b949e20, #8b949e10);
            color: #8b949e;
            border: 1px solid #8b949e30;
        }}
        
        .panel-type .type-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}
        
        .panel-type.program .type-dot {{ background: #f0883e; box-shadow: 0 0 8px #f0883e; }}
        .panel-type.project .type-dot {{ background: #58a6ff; box-shadow: 0 0 8px #58a6ff; }}
        .panel-type.standalone .type-dot {{ background: #8b949e; }}
        
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
    <svg id="graph"></svg>
    
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
                <div class="panel-section-title">Notes</div>
                <div id="panel-notes"></div>
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
            <div class="legend-dot" style="background: #8b949e"></div>
            <span>Standalone</span>
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
            
            // Build nodes
            nodes = workstreams.map(ws => {{
                const isProgram = parentIds.has(ws.id);
                const isProject = !!ws.parentId;
                return {{
                    id: ws.id,
                    name: ws.name,
                    type: isProgram ? 'program' : (isProject ? 'project' : 'standalone'),
                    parentId: ws.parentId,
                    tags: ws.tags || [],
                    radius: isProgram ? 28 : (isProject ? 20 : 16),
                    color: isProgram ? '#f0883e' : (isProject ? '#58a6ff' : '#8b949e')
                }};
            }});
            
            // Build links with varying strengths based on affinity
            links = [];
            
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
                .distance(d => d.type === 'parent-child' ? 100 : 180)
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
                .attr('class', 'node')
                .call(d3.drag()
                    .on('start', dragstarted)
                    .on('drag', dragged)
                    .on('end', dragended)
                )
                .on('click', (event, d) => {{
                    event.stopPropagation();
                    selectNode(d);
                }});
            
            // Node circle
            nodeEnter.append('circle')
                .attr('r', d => d.radius)
                .attr('fill', d => d.color);
            
            // Inner highlight
            nodeEnter.append('circle')
                .attr('r', d => d.radius * 0.4)
                .attr('fill', 'rgba(255,255,255,0.3)');
            
            // Label
            nodeEnter.append('text')
                .attr('class', 'node-label')
                .attr('dy', d => d.radius + 16)
                .text(d => d.name.length > 18 ? d.name.slice(0, 16) + '...' : d.name);
            
            // Sublabel (tag count)
            nodeEnter.append('text')
                .attr('class', 'node-sublabel')
                .attr('dy', d => d.radius + 28)
                .text(d => `${{d.tags.length}} tags`);
            
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
            if (ws.notes && ws.notes.length > 0) {{
                notesSection.style.display = 'block';
                notesContainer.innerHTML = ws.notes.map(n => `<div class="panel-note">${{n}}</div>`).join('');
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
    import json
    import html
    
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


@app.get("/api/workstreams/{workstream_id}")
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
    return {"error": "Not found"}, 404


def main():
    """Run the web UI server."""
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Workstream Dashboard")
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to run on (default: 8080)"
    )
    args = parser.parse_args()

    print(f"Starting Workstream Dashboard at http://localhost:{args.port}")
    print(f"Available profiles: {', '.join(PROFILES)}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
