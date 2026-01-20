#!/usr/bin/env python3
"""
Local Memory MCP Server
Organizes work into segments (workstreams) with tagging and metadata.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)

from .indexers import GitHubIndexer
from .storage import DEFAULT_PROFILE, WorkstreamStorage
from .templates import (
    CreateTemplateRequest,
    InstantiateTemplateRequest,
    TemplateStorage,
)
from .types import CreateWorkstreamRequest, UpdateWorkstreamRequest
from .indexers.outlook_indexer import OutlookIndexer
from .indexers.teams_indexer import TeamsIndexer, TeamsIndexerError

# Get profile from environment variable or use default
PROFILE = os.environ.get("MEM_PROFILE", DEFAULT_PROFILE)

# Initialize MCP server
server = Server("local-mem")
storage = WorkstreamStorage(profile=PROFILE)
template_storage = TemplateStorage(profile=PROFILE)


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
        Tool(
            name="index_teams_chat",
            description="""Index Microsoft Teams chat messages as workstreams.

Requires Azure AD app registration with Graph API permissions.
Set these environment variables:
- MICROSOFT_CLIENT_ID: Azure AD application client ID
- MICROSOFT_CLIENT_SECRET: Azure AD client secret
- MICROSOFT_TENANT_ID: Azure AD tenant ID

If team_id and channel_id are not provided, lists available teams and channels.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "team_id": {
                        "type": "string",
                        "description": "Teams team ID (optional - omit to list teams)",
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Teams channel ID (optional - omit to list channels)",
                    },
                    "message_limit": {
                        "type": "integer",
                        "description": "Maximum number of messages to index (default: 50)",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="index_outlook_emails",
            description="""Index Outlook emails and create workstreams from email threads.

Requires Azure AD app registration with Mail.Read permission.
Set these environment variables:
- MICROSOFT_CLIENT_ID: Azure AD application client ID
- MICROSOFT_CLIENT_SECRET: Azure AD client secret
- MICROSOFT_TENANT_ID: Azure AD tenant ID""",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "Mail folder to index (default: inbox). Can be 'inbox', 'sent', 'drafts', 'archive', or custom folder name.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Filter emails received after this date (ISO format, e.g., '2024-01-01')",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Filter emails received before this date (ISO format)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of emails to fetch (default: 100)",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "Only index unread emails (default: false)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional tags to add to all created workstreams",
                    },
                },
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
            return [TextContent(type="text", text="\n\n".join(notes))]

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

        elif name == "index_teams_chat":
            team_id = arguments.get("team_id")
            channel_id = arguments.get("channel_id")
            message_limit = arguments.get("message_limit", 50)

            try:
                indexer = TeamsIndexer()
            except TeamsIndexerError as e:
                return [
                    TextContent(
                        type="text",
                        text=f"Teams indexer error: {e}",
                    )
                ]

            # If no team_id, list available teams
            if not team_id:
                try:
                    teams = indexer.list_teams()
                    if not teams:
                        return [
                            TextContent(type="text", text="No teams found.")
                        ]
                    teams_list = "\n".join(
                        f"- {t.display_name} (ID: {t.id})" for t in teams
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"Available teams:\n{teams_list}\n\n"
                            "Call again with team_id to list channels.",
                        )
                    ]
                except TeamsIndexerError as e:
                    return [
                        TextContent(type="text", text=f"Failed to list teams: {e}")
                    ]

            # If team_id but no channel_id, list channels
            if not channel_id:
                try:
                    channels = indexer.list_channels(team_id)
                    if not channels:
                        return [
                            TextContent(
                                type="text",
                                text=f"No channels found in team {team_id}.",
                            )
                        ]
                    channels_list = "\n".join(
                        f"- {c.display_name} (ID: {c.id})" for c in channels
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"Available channels in team {team_id}:\n{channels_list}\n\n"
                            "Call again with channel_id to index messages.",
                        )
                    ]
                except TeamsIndexerError as e:
                    return [
                        TextContent(
                            type="text", text=f"Failed to list channels: {e}"
                        )
                    ]

            # Index the channel
            try:
                workstream_requests = await indexer.index_channel(
                    team_id, channel_id, message_limit
                )
            except TeamsIndexerError as e:
                return [
                    TextContent(
                        type="text", text=f"Failed to index channel: {e}"
                    )
                ]

            if not workstream_requests:
                return [
                    TextContent(
                        type="text",
                        text="No message threads found to index.",
                    )
                ]

            # Create workstreams for each thread
            created_workstreams = []
            for request in workstream_requests:
                workstream = await storage.create(request)
                created_workstreams.append(workstream)

            return [
                TextContent(
                    type="text",
                    text=f"Indexed {len(created_workstreams)} chat threads as workstreams.\n\n"
                    + json.dumps(
                        [w.to_dict() for w in created_workstreams], indent=2
                    ),
                )
            ]

        elif name == "index_outlook_emails":
            folder = arguments.get("folder", "inbox")
            start_date = arguments.get("start_date")
            end_date = arguments.get("end_date")
            max_results = arguments.get("max_results", 100)
            unread_only = arguments.get("unread_only", False)
            additional_tags = arguments.get("tags", [])

            try:
                indexer = OutlookIndexer()
            except ValueError as e:
                return [
                    TextContent(
                        type="text",
                        text=f"Outlook indexer configuration error: {e}",
                    )
                ]

            try:
                workstream_requests = await indexer.index_emails(
                    folder=folder,
                    start_date=start_date,
                    end_date=end_date,
                    max_results=max_results,
                    unread_only=unread_only,
                    additional_tags=additional_tags,
                )
            except Exception as e:
                await indexer.close()
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to index Outlook emails: {e}",
                    )
                ]

            await indexer.close()

            if not workstream_requests:
                return [
                    TextContent(
                        type="text",
                        text=f"No email threads found in '{folder}' with the specified filters.",
                    )
                ]

            # Create workstreams for each email thread
            created_workstreams = []
            for request in workstream_requests:
                workstream = await storage.create(request)
                created_workstreams.append(workstream)

            return [
                TextContent(
                    type="text",
                    text=f"Indexed {len(created_workstreams)} email threads from '{folder}' as workstreams.\n\n"
                    + json.dumps(
                        [w.to_dict() for w in created_workstreams], indent=2
                    ),
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
