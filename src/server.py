#!/usr/bin/env python3
"""
Local Memory MCP Server
Organizes work into segments (workstreams) with tagging and metadata.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)

from .indexers import GitHubIndexer
from .indexers.local_repo_indexer import LocalRepoIndexer
from .storage import DEFAULT_PROFILE, WorkstreamStorage
from .templates import (
    CreateTemplateRequest,
    InstantiateTemplateRequest,
    TemplateStorage,
)
from .types import CreateWorkstreamRequest, UpdateWorkstreamRequest

# Get profile from environment variable or use default
PROFILE = os.environ.get("MEM_PROFILE", DEFAULT_PROFILE)

# Initialize MCP server
server = Server("local-mem")
storage = WorkstreamStorage(profile=PROFILE)
template_storage = TemplateStorage(profile=PROFILE)


def extract_project_context(path: Path) -> dict[str, Any]:
    """Extract project context (build/test commands, setup instructions) from a directory.
    
    Handles both single projects and monorepos with multiple services.
    """
    context: dict[str, Any] = {
        "project_type": "unknown",
        "is_monorepo": False,
        "commands": {},
        "setup": [],
        "services": {},  # For monorepos: service_name -> {path, commands, type}
    }
    
    makefile = path / "Makefile"
    package_json = path / "package.json"
    pyproject = path / "pyproject.toml"
    cargo_toml = path / "Cargo.toml"
    go_mod = path / "go.mod"
    
    # Check for monorepo patterns
    services_dir = path / "services"
    packages_dir = path / "packages"
    
    # Find all nested project files (indicates monorepo)
    nested_go_mods = list(path.glob("*/go.mod")) + list(path.glob("*/*/go.mod"))
    nested_package_jsons = [p for p in path.glob("*/package.json") if "node_modules" not in str(p)]
    nested_cargo_tomls = list(path.glob("*/Cargo.toml"))
    
    is_monorepo = (
        services_dir.exists() or 
        packages_dir.exists() or 
        len(nested_go_mods) > 1 or 
        len(nested_package_jsons) > 1
    )
    context["is_monorepo"] = is_monorepo
    
    # Extract root-level commands from Makefile
    if makefile.exists():
        context["project_type"] = "make"
        try:
            content = makefile.read_text()
            targets = re.findall(r'^([a-zA-Z_-]+):', content, re.MULTILINE)
            
            # Standard commands
            common = {"build": None, "test": None, "lint": None, "install": None,
                      "setup": None, "dev": None, "run": None, "clean": None,
                      "check": None, "fmt": None, "format": None}
            
            # Language-specific commands (for monorepos)
            lang_commands = {
                "go": {"test": None, "lint": None, "check": None, "fmt": None},
                "python": {"test": None, "lint": None, "check": None},
                "rust": {"test": None, "lint": None, "check": None},
            }
            
            for t in targets:
                tl = t.lower()
                # Root commands
                if tl in common:
                    common[tl] = f"make {t}"
                elif "test" in tl and "-" not in tl:
                    common["test"] = common["test"] or f"make {t}"
                elif "build" in tl and "-" not in tl:
                    common["build"] = common["build"] or f"make {t}"
                elif "lint" in tl and "-" not in tl:
                    common["lint"] = common["lint"] or f"make {t}"
                
                # Language-specific (e.g., test-go, lint-python)
                for lang in lang_commands:
                    if tl == f"test-{lang}" or tl == f"test_{lang}":
                        lang_commands[lang]["test"] = f"make {t}"
                    elif tl == f"lint-{lang}" or tl == f"lint_{lang}":
                        lang_commands[lang]["lint"] = f"make {t}"
                    elif tl == f"check-{lang}" or tl == f"check_{lang}":
                        lang_commands[lang]["check"] = f"make {t}"
                    elif tl == f"fmt-{lang}" or tl == f"fmt_{lang}":
                        lang_commands[lang]["fmt"] = f"make {t}"
            
            context["commands"] = {k: v for k, v in common.items() if v}
            
            # Add language-specific commands if this is a monorepo
            if is_monorepo:
                context["commands"]["by_language"] = {
                    lang: {k: v for k, v in cmds.items() if v}
                    for lang, cmds in lang_commands.items()
                    if any(cmds.values())
                }
            
            # Setup commands
            if "install-tools" in targets:
                context["setup"].append("make install-tools")
            if "setup" in targets:
                context["setup"].append("make setup")
                
        except Exception:
            pass
    
    # Index services in monorepo
    if is_monorepo and services_dir.exists():
        for svc_path in services_dir.iterdir():
            if svc_path.is_dir() and not svc_path.name.startswith("."):
                svc_info = {"path": str(svc_path.relative_to(path)), "type": "unknown", "commands": {}}
                
                # Detect service type
                if (svc_path / "go.mod").exists():
                    svc_info["type"] = "go"
                    svc_info["commands"] = {
                        "build": f"cd {svc_info['path']} && go build ./...",
                        "test": f"cd {svc_info['path']} && go test ./...",
                    }
                elif (svc_path / "Cargo.toml").exists():
                    svc_info["type"] = "rust"
                    svc_info["commands"] = {
                        "build": f"cd {svc_info['path']} && cargo build",
                        "test": f"cd {svc_info['path']} && cargo test",
                    }
                elif (svc_path / "package.json").exists():
                    svc_info["type"] = "node"
                    svc_info["commands"] = {
                        "build": f"cd {svc_info['path']} && npm run build",
                        "test": f"cd {svc_info['path']} && npm test",
                    }
                elif (svc_path / "pyproject.toml").exists():
                    svc_info["type"] = "python"
                    svc_info["commands"] = {
                        "test": f"cd {svc_info['path']} && pytest",
                    }
                
                # Check for service-specific README
                if (svc_path / "README.md").exists():
                    svc_info["has_readme"] = True
                
                context["services"][svc_path.name] = svc_info
    
    # Fallback for non-monorepo projects
    if not is_monorepo:
        if package_json.exists():
            context["project_type"] = "node" if context["project_type"] == "unknown" else context["project_type"]
            try:
                pkg = json.loads(package_json.read_text())
                scripts = pkg.get("scripts", {})
                if "build" in scripts:
                    context["commands"]["build"] = "npm run build"
                if "test" in scripts:
                    context["commands"]["test"] = "npm run test"
                if "lint" in scripts:
                    context["commands"]["lint"] = "npm run lint"
                context["setup"].append("npm install")
            except Exception:
                pass
        
        if pyproject.exists():
            context["project_type"] = "python" if context["project_type"] == "unknown" else context["project_type"]
            context["commands"].setdefault("test", "pytest")
            context["commands"].setdefault("lint", "ruff check .")
            if (path / "uv.lock").exists():
                context["setup"].append("uv sync")
            elif (path / "requirements.txt").exists():
                context["setup"].append("pip install -r requirements.txt")
            else:
                context["setup"].append("pip install -e .")
        
        if cargo_toml.exists():
            context["project_type"] = "rust" if context["project_type"] == "unknown" else context["project_type"]
            context["commands"]["build"] = "cargo build"
            context["commands"]["test"] = "cargo test"
            context["commands"]["lint"] = "cargo clippy"
        
        if go_mod.exists():
            context["project_type"] = "go" if context["project_type"] == "unknown" else context["project_type"]
            context["commands"]["build"] = "go build ./..."
            context["commands"]["test"] = "go test ./..."
            context["commands"]["lint"] = "golangci-lint run"
    
    return context


def get_tools() -> list[Tool]:
    """Return the list of available tools."""
    return [
        Tool(
            name="create_workstream",
            description="Create a new workstream (work segment) with name, summary, tags, and metadata",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the workstream",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Summary/description of the workstream",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to organize the workstream (optional)",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Additional metadata like hostIps, connectionInfo, testingInfo (optional)",
                        "properties": {
                            "hostIps": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Host IP addresses",
                            },
                            "connectionInfo": {
                                "type": "string",
                                "description": "How to connect to the system",
                            },
                            "testingInfo": {
                                "type": "string",
                                "description": "How to test the system",
                            },
                        },
                    },
                },
                "required": ["name", "summary"],
            },
        ),
        Tool(
            name="list_workstreams",
            description="List all workstreams",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_workstream",
            description="Get detailed information about a specific workstream by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Workstream ID",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="update_workstream",
            description="Update an existing workstream",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Workstream ID",
                    },
                    "name": {
                        "type": "string",
                        "description": "New name (optional)",
                    },
                    "summary": {
                        "type": "string",
                        "description": "New summary (optional)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New tags (optional, replaces existing)",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Metadata to merge with existing (optional)",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="delete_workstream",
            description="Delete a workstream by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Workstream ID",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="add_tags",
            description="Add tags to an existing workstream",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Workstream ID",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to add",
                    },
                },
                "required": ["id", "tags"],
            },
        ),
        Tool(
            name="search_by_tags",
            description="Search workstreams by tags",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to search for",
                    },
                    "matchAll": {
                        "type": "boolean",
                        "description": "If true, match all tags; if false, match any tag (default: false)",
                    },
                },
                "required": ["tags"],
            },
        ),
        Tool(
            name="search_workstreams",
            description="Search workstreams by name or summary text",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="add_note",
            description="""Add a contextual note to a workstream. Notes should capture information that helps resume work later.

HIGH-VALUE notes (add these):
- DECISION: Design choices with rationale ("Chose X over Y because Z")
- BLOCKER: Issues encountered and how they were resolved
- CHANGED: Dependency updates, breaking changes, migrations
- CONTEXT: External requirements, stakeholder input, priority shifts
- TRIED: Approaches attempted that didn't work (avoid repeating)
- RESUME: Where to pick up, what's next, current state

LOW-VALUE notes (skip these):
- File structure (already in repo)
- How to run commands (already in README)
- Basic project description (that's the summary field)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Workstream ID",
                    },
                    "note": {
                        "type": "string",
                        "description": "The note content. Start with a category prefix (DECISION:, BLOCKER:, CHANGED:, CONTEXT:, TRIED:, RESUME:) for better organization.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["decision", "blocker", "changed", "context", "tried", "resume", "other"],
                        "description": "Category of the note (optional, helps with filtering)",
                    },
                },
                "required": ["id", "note"],
            },
        ),
        Tool(
            name="get_notes",
            description="Get all notes for a workstream",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Workstream ID",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="edit_note",
            description="Edit an existing note in a workstream by index",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Workstream ID",
                    },
                    "note_index": {
                        "type": "integer",
                        "description": "Index of the note to edit (0-based)",
                    },
                    "content": {
                        "type": "string",
                        "description": "New content for the note",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["decision", "blocker", "changed", "context", "tried", "resume", "other"],
                        "description": "Category of the note (optional)",
                    },
                },
                "required": ["id", "note_index", "content"],
            },
        ),
        Tool(
            name="delete_note",
            description="Delete a note from a workstream by index",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Workstream ID",
                    },
                    "note_index": {
                        "type": "integer",
                        "description": "Index of the note to delete (0-based)",
                    },
                },
                "required": ["id", "note_index"],
            },
        ),
        Tool(
            name="index_github_repo",
            description="Index a GitHub repository and create a workstream with its README, recent PRs, and issues. Requires GITHUB_TOKEN environment variable for authentication.",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner (username or organization)",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                },
                "required": ["owner", "repo"],
            },
        ),
        # Template tools
        Tool(
            name="create_template",
            description="Create a reusable workstream template with default tags, metadata, and note templates",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Template name",
                    },
                    "description": {
                        "type": "string",
                        "description": "Template description",
                    },
                    "default_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Default tags to apply to workstreams created from this template",
                    },
                    "default_metadata": {
                        "type": "object",
                        "description": "Default metadata for workstreams created from this template",
                    },
                    "note_templates": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Initial notes to add to workstreams created from this template",
                    },
                },
                "required": ["name", "description"],
            },
        ),
        Tool(
            name="list_templates",
            description="List all workstream templates",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="create_workstream_from_template",
            description="Create a new workstream from a template, optionally with overrides",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "string",
                        "description": "Template ID to use",
                    },
                    "name": {
                        "type": "string",
                        "description": "Workstream name",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Workstream summary/description",
                    },
                    "additional_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional tags to add (merged with template defaults)",
                    },
                    "metadata_overrides": {
                        "type": "object",
                        "description": "Metadata to override template defaults",
                    },
                    "parent_id": {
                        "type": "string",
                        "description": "Parent workstream ID (optional)",
                    },
                },
                "required": ["template_id", "name", "summary"],
            },
        ),
        Tool(
            name="get_project_context",
            description="""Get project context for a directory path. Returns build commands, test commands, 
setup instructions, and service information for monorepos. Automatically detects project type.

Use this when starting work on a project to understand how to build, test, and work with it.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the project directory. Defaults to current working directory.",
                    },
                },
            },
        ),
        Tool(
            name="index_local_repo",
            description="""Index a local git repository and create a workstream with project context.
Extracts README, docs, Makefile targets, build/test commands, and git history.
Handles monorepos by detecting services and their individual build/test commands.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the local git repository",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional tags to add to the workstream",
                    },
                },
                "required": ["path"],
            },
        ),
    ]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return the list of available tools."""
    return get_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "create_workstream":
            request = CreateWorkstreamRequest(
                name=arguments["name"],
                summary=arguments["summary"],
                tags=arguments.get("tags", []),
                metadata=arguments.get("metadata"),
            )
            workstream = await storage.create(request)
            return [
                TextContent(
                    type="text", text=json.dumps(workstream.to_dict(), indent=2)
                )
            ]

        elif name == "list_workstreams":
            workstreams = await storage.list()
            return [
                TextContent(
                    type="text",
                    text=json.dumps([w.to_dict() for w in workstreams], indent=2),
                )
            ]

        elif name == "get_workstream":
            workstream = await storage.get(arguments["id"])
            if not workstream:
                return [
                    TextContent(
                        type="text",
                        text=f'Workstream with ID "{arguments["id"]}" not found',
                    )
                ]
            return [
                TextContent(
                    type="text", text=json.dumps(workstream.to_dict(), indent=2)
                )
            ]

        elif name == "update_workstream":
            request = UpdateWorkstreamRequest(
                id=arguments["id"],
                name=arguments.get("name"),
                summary=arguments.get("summary"),
                tags=arguments.get("tags"),
                metadata=arguments.get("metadata"),
            )
            workstream = await storage.update(request)
            if not workstream:
                return [
                    TextContent(
                        type="text",
                        text=f'Workstream with ID "{arguments["id"]}" not found',
                    )
                ]
            return [
                TextContent(
                    type="text", text=json.dumps(workstream.to_dict(), indent=2)
                )
            ]

        elif name == "delete_workstream":
            deleted = await storage.delete(arguments["id"])
            if deleted:
                return [
                    TextContent(
                        type="text",
                        text=f'Workstream "{arguments["id"]}" deleted successfully',
                    )
                ]
            return [
                TextContent(
                    type="text",
                    text=f'Workstream "{arguments["id"]}" not found',
                )
            ]

        elif name == "add_tags":
            workstream = await storage.add_tags(arguments["id"], arguments["tags"])
            if not workstream:
                return [
                    TextContent(
                        type="text",
                        text=f'Workstream with ID "{arguments["id"]}" not found',
                    )
                ]
            return [
                TextContent(
                    type="text", text=json.dumps(workstream.to_dict(), indent=2)
                )
            ]

        elif name == "search_by_tags":
            match_all = arguments.get("matchAll", False)
            workstreams = await storage.search_by_tags(arguments["tags"], match_all)
            return [
                TextContent(
                    type="text",
                    text=json.dumps([w.to_dict() for w in workstreams], indent=2),
                )
            ]

        elif name == "search_workstreams":
            workstreams = await storage.search(arguments["query"])
            return [
                TextContent(
                    type="text",
                    text=json.dumps([w.to_dict() for w in workstreams], indent=2),
                )
            ]

        elif name == "add_note":
            category = arguments.get("category")
            workstream = await storage.add_note(
                arguments["id"], arguments["note"], category
            )
            if not workstream:
                return [
                    TextContent(
                        type="text",
                        text=f'Workstream with ID "{arguments["id"]}" not found',
                    )
                ]
            return [
                TextContent(
                    type="text",
                    text=f'Note added to "{workstream.name}". Total notes: {len(workstream.notes)}',
                )
            ]

        elif name == "get_notes":
            notes = await storage.get_notes(arguments["id"])
            if notes is None:
                return [
                    TextContent(
                        type="text",
                        text=f'Workstream with ID "{arguments["id"]}" not found',
                    )
                ]
            if not notes:
                return [TextContent(type="text", text="No notes yet.")]
            # Include index for easier reference
            indexed_notes = [f"[{i}] {note}" for i, note in enumerate(notes)]
            return [TextContent(type="text", text="\n\n".join(indexed_notes))]

        elif name == "edit_note":
            category = arguments.get("category")
            workstream = await storage.update_note(
                arguments["id"],
                arguments["note_index"],
                arguments["content"],
                category,
            )
            if not workstream:
                return [
                    TextContent(
                        type="text",
                        text=f'Workstream with ID "{arguments["id"]}" not found or note index {arguments["note_index"]} is out of range',
                    )
                ]
            return [
                TextContent(
                    type="text",
                    text=f'Note {arguments["note_index"]} updated in "{workstream.name}". Total notes: {len(workstream.notes)}',
                )
            ]

        elif name == "delete_note":
            workstream = await storage.delete_note(
                arguments["id"], arguments["note_index"]
            )
            if not workstream:
                return [
                    TextContent(
                        type="text",
                        text=f'Workstream with ID "{arguments["id"]}" not found or note index {arguments["note_index"]} is out of range',
                    )
                ]
            return [
                TextContent(
                    type="text",
                    text=f'Note {arguments["note_index"]} deleted from "{workstream.name}". Remaining notes: {len(workstream.notes)}',
                )
            ]

        elif name == "index_github_repo":
            owner = arguments["owner"]
            repo = arguments["repo"]

            indexer = GitHubIndexer()
            try:
                content = await indexer.index_repository(owner, repo)
            except Exception as e:
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to index repository: {e}",
                    )
                ]

            # Create workstream from indexed content
            request = indexer.to_workstream_request(owner, repo, content)
            workstream = await storage.create(request)

            # Add extracted notes
            notes = indexer.extract_notes(content)
            for note in notes:
                await storage.add_note(workstream.id, note)

            # Refresh to get updated workstream with notes
            workstream = await storage.get(workstream.id)

            return [
                TextContent(
                    type="text",
                    text=f'Indexed {owner}/{repo} as workstream "{workstream.id}".\n'
                    f"Added {len(notes)} notes (README, PRs, issues).\n\n"
                    f"{json.dumps(workstream.to_dict(), indent=2)}",
                )
            ]

        elif name == "create_template":
            request = CreateTemplateRequest(
                name=arguments["name"],
                description=arguments["description"],
                default_tags=arguments.get("default_tags", []),
                default_metadata=arguments.get("default_metadata", {}),
                note_templates=arguments.get("note_templates", []),
            )
            template = await template_storage.create_template(request)
            return [
                TextContent(
                    type="text", text=json.dumps(template.to_dict(), indent=2)
                )
            ]

        elif name == "list_templates":
            templates = await template_storage.list_templates()
            return [
                TextContent(
                    type="text",
                    text=json.dumps([t.to_dict() for t in templates], indent=2),
                )
            ]

        elif name == "create_workstream_from_template":
            request = InstantiateTemplateRequest(
                template_id=arguments["template_id"],
                name=arguments["name"],
                summary=arguments["summary"],
                additional_tags=arguments.get("additional_tags", []),
                metadata_overrides=arguments.get("metadata_overrides", {}),
                parent_id=arguments.get("parent_id"),
            )
            workstream = await template_storage.create_from_template(request, storage)
            if not workstream:
                return [
                    TextContent(
                        type="text",
                        text=f'Template with ID "{arguments["template_id"]}" not found',
                    )
                ]
            return [
                TextContent(
                    type="text", text=json.dumps(workstream.to_dict(), indent=2)
                )
            ]

        elif name == "get_project_context":
            path_str = arguments.get("path", os.getcwd())
            path = Path(path_str).expanduser().resolve()
            
            if not path.exists():
                return [TextContent(type="text", text=f"Path does not exist: {path}")]
            
            context = extract_project_context(path)
            
            # Check if we have an indexed workstream for this path
            workstreams = await storage.list()
            matching_ws = None
            for ws in workstreams:
                ws_meta = ws.metadata
                ws_path = ""
                if hasattr(ws_meta, 'extra') and ws_meta.extra:
                    ws_path = ws_meta.extra.get("repo_path", "")
                elif hasattr(ws_meta, '__dict__'):
                    ws_path = getattr(ws_meta, 'repo_path', "") or ws_meta.__dict__.get("repo_path", "")
                if ws_path and Path(ws_path).resolve() == path:
                    matching_ws = ws
                    break
            
            result = {
                "path": str(path),
                "is_monorepo": context.get("is_monorepo", False),
                "project_type": context.get("project_type", "unknown"),
                "commands": context.get("commands", {}),
                "setup_instructions": context.get("setup", []),
                "services": context.get("services", {}),
                "indexed_workstream_id": matching_ws.id if matching_ws else None,
            }
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "index_local_repo":
            path_str = arguments.get("path")
            additional_tags = arguments.get("tags", [])
            
            if not path_str:
                return [TextContent(type="text", text="Path is required")]
            
            path = Path(path_str).expanduser().resolve()
            
            try:
                indexer = LocalRepoIndexer(str(path))
                ws_request, notes = await indexer.index_repository()
                
                # Add additional tags
                ws_request.tags = list(set(ws_request.tags + additional_tags))
                
                # Extract and add project context to metadata
                context = extract_project_context(path)
                ws_request.metadata["is_monorepo"] = context.get("is_monorepo", False)
                ws_request.metadata["commands"] = context.get("commands", {})
                ws_request.metadata["setup_instructions"] = context.get("setup", [])
                ws_request.metadata["project_type"] = context.get("project_type", "unknown")
                if context.get("services"):
                    ws_request.metadata["services"] = context["services"]
                
                # Create workstream
                workstream = await storage.create(ws_request)
                
                # Add notes
                for note in notes:
                    await storage.add_note(
                        workstream.id,
                        note["content"],
                        note.get("category", "CONTEXT"),
                    )
                
                # Add quick reference note for monorepos
                if context.get("is_monorepo") and context.get("services"):
                    services_list = "\n".join([
                        f"  - {name}: {info['type']} ({info['path']})" 
                        for name, info in context["services"].items()
                    ])
                    quick_ref = f"""[QUICK REFERENCE] Monorepo Commands:

ROOT: {', '.join(context.get('setup', []))}
Test: {context['commands'].get('test', 'N/A')} | Lint: {context['commands'].get('lint', 'N/A')}

SERVICES ({len(context['services'])}):
{services_list}
"""
                    await storage.add_note(workstream.id, quick_ref, "REFERENCE")
                    
                    # Create child workstreams for each service
                    for svc_name, svc_info in context["services"].items():
                        svc_path = path / svc_info["path"]
                        
                        # Read service README if exists
                        readme_content = ""
                        readme_file = svc_path / "README.md"
                        if readme_file.exists():
                            try:
                                readme_content = readme_file.read_text()[:3000]
                            except Exception:
                                pass
                        
                        # Create child workstream
                        svc_request = CreateWorkstreamRequest(
                            name=f"Service: {svc_name}",
                            summary=f"Monorepo service - {svc_info['type']} module at {svc_info['path']}",
                            tags=["service", svc_info["type"], svc_name] + additional_tags,
                            parent_id=workstream.id,
                            metadata={
                                "service_name": svc_name,
                                "service_type": svc_info["type"],
                                "service_path": svc_info["path"],
                                "commands": svc_info.get("commands", {}),
                                "repo_path": str(svc_path),
                            },
                        )
                        svc_ws = await storage.create(svc_request)
                        
                        # Add README note if exists
                        if readme_content:
                            await storage.add_note(svc_ws.id, f"[README]\n{readme_content}", "CONTEXT")
                        
                        # Add quick reference for service
                        cmds = svc_info.get("commands", {})
                        svc_ref = f"""[QUICK REFERENCE] {svc_name}
Type: {svc_info['type']}
Path: cd {svc_info['path']}
Build: {cmds.get('build', 'N/A')}
Test: {cmds.get('test', 'N/A')}
"""
                        await storage.add_note(svc_ws.id, svc_ref, "REFERENCE")
                
                # Reload to get notes
                workstream = await storage.get(workstream.id)
                
                # Get children count for response
                children = await storage.get_children(workstream.id)
                
                return [
                    TextContent(
                        type="text",
                        text=f"Indexed local repository: {path}\n"
                        + f"Created {len(children)} child workstreams for services\n\n"
                        + json.dumps(workstream.to_dict(), indent=2),
                    )
                ]
            except Exception as e:
                return [TextContent(type="text", text=f"Failed to index repository: {e}")]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as error:
        return [TextContent(type="text", text=f"Error executing tool {name}: {error}")]


@server.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources (workstreams)."""
    workstreams = await storage.list()
    return [
        Resource(
            uri=f"workstream://{w.id}",
            name=w.name,
            description=w.summary,
            mimeType="application/json",
        )
        for w in workstreams
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    if not uri.startswith("workstream://"):
        raise ValueError("Invalid resource URI")

    workstream_id = uri.replace("workstream://", "")
    workstream = await storage.get(workstream_id)

    if not workstream:
        raise ValueError(f"Workstream {workstream_id} not found")

    return json.dumps(workstream.to_dict(), indent=2)


async def main() -> None:
    """Run the MCP server."""
    global storage, template_storage, PROFILE

    # Check for profile argument
    if len(sys.argv) > 1 and sys.argv[1].startswith("--profile="):
        PROFILE = sys.argv[1].split("=")[1]
        storage = WorkstreamStorage(profile=PROFILE)
        template_storage = TemplateStorage(profile=PROFILE)

    await storage.initialize()
    await template_storage.initialize()
    print(
        f"Local Memory MCP Server running on stdio [profile: {PROFILE}]",
        file=sys.stderr,
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
