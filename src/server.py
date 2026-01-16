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

from .storage import DEFAULT_PROFILE, WorkstreamStorage
from .types import CreateWorkstreamRequest, UpdateWorkstreamRequest

# Get profile from environment variable or use default
PROFILE = os.environ.get("MEM_PROFILE", DEFAULT_PROFILE)

# Initialize MCP server
server = Server("local-mem")
storage = WorkstreamStorage(profile=PROFILE)


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
            return [TextContent(type="text", text=json.dumps(workstream.to_dict(), indent=2))]

        elif name == "list_workstreams":
            workstreams = await storage.list()
            return [TextContent(
                type="text",
                text=json.dumps([w.to_dict() for w in workstreams], indent=2),
            )]

        elif name == "get_workstream":
            workstream = await storage.get(arguments["id"])
            if not workstream:
                return [TextContent(
                    type="text",
                    text=f'Workstream with ID "{arguments["id"]}" not found',
                )]
            return [TextContent(type="text", text=json.dumps(workstream.to_dict(), indent=2))]

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
                return [TextContent(
                    type="text",
                    text=f'Workstream with ID "{arguments["id"]}" not found',
                )]
            return [TextContent(type="text", text=json.dumps(workstream.to_dict(), indent=2))]

        elif name == "delete_workstream":
            deleted = await storage.delete(arguments["id"])
            if deleted:
                return [TextContent(
                    type="text",
                    text=f'Workstream "{arguments["id"]}" deleted successfully',
                )]
            return [TextContent(
                type="text",
                text=f'Workstream "{arguments["id"]}" not found',
            )]

        elif name == "add_tags":
            workstream = await storage.add_tags(arguments["id"], arguments["tags"])
            if not workstream:
                return [TextContent(
                    type="text",
                    text=f'Workstream with ID "{arguments["id"]}" not found',
                )]
            return [TextContent(type="text", text=json.dumps(workstream.to_dict(), indent=2))]

        elif name == "search_by_tags":
            match_all = arguments.get("matchAll", False)
            workstreams = await storage.search_by_tags(arguments["tags"], match_all)
            return [TextContent(
                type="text",
                text=json.dumps([w.to_dict() for w in workstreams], indent=2),
            )]

        elif name == "search_workstreams":
            workstreams = await storage.search(arguments["query"])
            return [TextContent(
                type="text",
                text=json.dumps([w.to_dict() for w in workstreams], indent=2),
            )]

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
    global storage, PROFILE
    
    # Check for profile argument
    if len(sys.argv) > 1 and sys.argv[1].startswith("--profile="):
        PROFILE = sys.argv[1].split("=")[1]
        storage = WorkstreamStorage(profile=PROFILE)
    
    await storage.initialize()
    print(f"Local Memory MCP Server running on stdio [profile: {PROFILE}]", file=sys.stderr)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
