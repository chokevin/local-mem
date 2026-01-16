#!/usr/bin/env python3
"""
CLI utility for interacting with local-mem workstreams.
Useful for debugging and quick access to workstream data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .storage import DEFAULT_PROFILE, WorkstreamStorage
from .types import CreateWorkstreamRequest


async def cmd_list(storage: WorkstreamStorage) -> None:
    """List all workstreams."""
    workstreams = await storage.list()
    if not workstreams:
        print("No workstreams found.")
        return

    print(f"\nFound {len(workstreams)} workstream(s):\n")
    for w in workstreams:
        print(f"ID: {w.id}")
        print(f"Name: {w.name}")
        print(f"Summary: {w.summary}")
        print(f"Tags: {', '.join(w.tags)}")
        print(f"Created: {w.created_at}")
        print(f"Updated: {w.updated_at}")
        metadata = w.metadata.to_dict()
        if metadata:
            print(f"Metadata: {json.dumps(metadata, indent=2)}")
        print("---")


async def cmd_create(
    storage: WorkstreamStorage, 
    name: str, 
    summary: str, 
    tags: list[str] | None = None,
    metadata: dict | None = None
) -> None:
    """Create a new workstream."""
    request = CreateWorkstreamRequest(
        name=name,
        summary=summary,
        tags=tags or [],
        metadata=metadata,
    )
    workstream = await storage.create(request)
    print(f"Created workstream: {workstream.id}")
    print(json.dumps(workstream.to_dict(), indent=2))


async def cmd_delete(storage: WorkstreamStorage, workstream_id: str) -> None:
    """Delete a workstream."""
    deleted = await storage.delete(workstream_id)
    if deleted:
        print(f"Deleted workstream: {workstream_id}")
    else:
        print(f"Workstream {workstream_id} not found", file=sys.stderr)
        sys.exit(1)


async def cmd_get(storage: WorkstreamStorage, workstream_id: str) -> None:
    """Get a specific workstream."""
    workstream = await storage.get(workstream_id)
    if not workstream:
        print(f"Workstream {workstream_id} not found", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(workstream.to_dict(), indent=2))


async def cmd_search(storage: WorkstreamStorage, query: str) -> None:
    """Search workstreams by name or summary."""
    results = await storage.search(query)
    print(f"Found {len(results)} result(s):")
    for w in results:
        print(f"- {w.name} ({w.id})")
        print(f"  {w.summary}")


async def cmd_tags(storage: WorkstreamStorage, tags: list[str]) -> None:
    """Search workstreams by tags."""
    results = await storage.search_by_tags(tags, match_all=False)
    print(f"Found {len(results)} workstream(s) with tags: {', '.join(tags)}")
    for w in results:
        print(f"- {w.name} ({w.id})")
        print(f"  Tags: {', '.join(w.tags)}")


async def cmd_note(storage: WorkstreamStorage, workstream_id: str, note: str) -> None:
    """Add a note to a workstream."""
    workstream = await storage.add_note(workstream_id, note)
    if not workstream:
        print(f"Workstream {workstream_id} not found", file=sys.stderr)
        sys.exit(1)
    print(f"Note added to '{workstream.name}'. Total notes: {len(workstream.notes)}")


async def cmd_notes(storage: WorkstreamStorage, workstream_id: str) -> None:
    """Show all notes for a workstream."""
    notes = await storage.get_notes(workstream_id)
    if notes is None:
        print(f"Workstream {workstream_id} not found", file=sys.stderr)
        sys.exit(1)
    if not notes:
        print("No notes yet.")
        return
    print(f"Notes ({len(notes)}):\n")
    for note in notes:
        print(note)
        print()


def show_help() -> None:
    """Show help message."""
    print(f"""
local-mem CLI utility

Usage:
  local-mem <command> [options]

Commands:
  list, ls                          List all workstreams
  create <name> <summary> [--tags]  Create a new workstream
  get <id>                          Get a workstream by ID
  delete <id>                       Delete a workstream
  search <query>                    Search workstreams by name or summary
  tags <tag1> [tag2]                Search workstreams by tags
  note <id> <note>                  Add a note to a workstream
  notes <id>                        Show all notes for a workstream
  help                              Show this help message

Options:
  --profile, -p <name>              Profile to use (default: {DEFAULT_PROFILE})
                                    Available: test, prod

Examples:
  local-mem list
  local-mem list --profile prod
  local-mem create "My Project" "Working on the API" --tags backend,api
  local-mem get ws-1234567890-abc123
  local-mem note ws-123 "Deployed to staging, testing in progress"
  local-mem notes ws-123
  local-mem delete ws-1234567890-abc123
  local-mem search "API project"
  local-mem tags backend nodejs
    """)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CLI utility for local-mem workstreams",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", default="help")
    parser.add_argument("args", nargs="*")
    parser.add_argument("--tags", "-t", help="Comma-separated tags")
    parser.add_argument("--metadata", "-m", help="JSON metadata")
    parser.add_argument("--profile", "-p", default=DEFAULT_PROFILE, help=f"Profile to use (default: {DEFAULT_PROFILE})")
    
    args = parser.parse_args()
    
    storage = WorkstreamStorage(profile=args.profile)
    await storage.initialize()
    
    print(f"[profile: {args.profile}]")

    command = args.command
    cmd_args = args.args

    if command in ("list", "ls"):
        await cmd_list(storage)
    elif command == "create":
        if len(cmd_args) < 2:
            print("Error: Please provide name and summary", file=sys.stderr)
            print('Usage: local-mem create "Name" "Summary" [--tags tag1,tag2]', file=sys.stderr)
            sys.exit(1)
        tags = args.tags.split(",") if args.tags else []
        metadata = json.loads(args.metadata) if args.metadata else None
        await cmd_create(storage, cmd_args[0], cmd_args[1], tags, metadata)
    elif command == "get":
        if not cmd_args:
            print("Error: Please provide a workstream ID", file=sys.stderr)
            sys.exit(1)
        await cmd_get(storage, cmd_args[0])
    elif command == "delete":
        if not cmd_args:
            print("Error: Please provide a workstream ID", file=sys.stderr)
            sys.exit(1)
        await cmd_delete(storage, cmd_args[0])
    elif command == "search":
        if not cmd_args:
            print("Error: Please provide a search query", file=sys.stderr)
            sys.exit(1)
        await cmd_search(storage, " ".join(cmd_args))
    elif command == "tags":
        if not cmd_args:
            print("Error: Please provide at least one tag", file=sys.stderr)
            sys.exit(1)
        await cmd_tags(storage, cmd_args)
    elif command == "note":
        if len(cmd_args) < 2:
            print("Error: Please provide workstream ID and note", file=sys.stderr)
            print('Usage: local-mem note <id> "Your note here"', file=sys.stderr)
            sys.exit(1)
        await cmd_note(storage, cmd_args[0], " ".join(cmd_args[1:]))
    elif command == "notes":
        if not cmd_args:
            print("Error: Please provide a workstream ID", file=sys.stderr)
            sys.exit(1)
        await cmd_notes(storage, cmd_args[0])
    elif command in ("help", "--help", "-h"):
        show_help()
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print('Run "local-mem help" for usage information', file=sys.stderr)
        sys.exit(1)


def run() -> None:
    """Entry point for the CLI."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
