"""
Temporal activities for indexing operations.

Activities are the building blocks that perform actual work.
They wrap existing indexer functionality to make it durable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from temporalio import activity

# Import existing indexers
from ..indexers import GitHubIndexer
from ..indexers.local_repo_indexer import LocalRepoIndexer
from ..server import extract_project_context
from ..storage import WorkstreamStorage
from ..types import CreateWorkstreamRequest, UpdateWorkstreamRequest

# Re-export data classes for convenience
from .data import IndexGitHubRepoInput, IndexLocalRepoInput, IndexResult


@activity.defn
async def fetch_github_repo_metadata(input: IndexGitHubRepoInput) -> dict[str, Any]:
    """Fetch metadata from GitHub repository."""
    activity.logger.info(f"Fetching GitHub repo metadata: {input.owner}/{input.repo}")

    indexer = GitHubIndexer()
    repo_data = await indexer.fetch_repo(input.owner, input.repo)

    return {
        "description": repo_data.get("description"),
        "topics": repo_data.get("topics", []),
        "default_branch": repo_data.get("default_branch"),
        "html_url": repo_data.get("html_url"),
    }


@activity.defn
async def fetch_github_readme(input: IndexGitHubRepoInput) -> str | None:
    """Fetch README content from GitHub repository."""
    activity.logger.info(f"Fetching README: {input.owner}/{input.repo}")

    indexer = GitHubIndexer()
    return await indexer.fetch_readme(input.owner, input.repo)


@activity.defn
async def fetch_github_prs_and_issues(
    input: IndexGitHubRepoInput,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch recent PRs and issues from GitHub repository."""
    activity.logger.info(f"Fetching PRs/issues: {input.owner}/{input.repo}")

    indexer = GitHubIndexer()
    prs = await indexer.fetch_recent_prs(input.owner, input.repo)
    issues = await indexer.fetch_recent_issues(input.owner, input.repo)

    return {"prs": prs, "issues": issues}


@activity.defn
async def save_github_workstream(
    input: IndexGitHubRepoInput,
    metadata: dict[str, Any],
    readme: str | None,
    prs_issues: dict[str, list[dict[str, Any]]],
) -> IndexResult:
    """Save indexed GitHub repo as a workstream."""
    activity.logger.info(f"Saving workstream: {input.owner}/{input.repo}")

    try:
        storage = WorkstreamStorage(profile=input.profile)
        await storage._load()

        # Build workstream request
        name = f"{input.owner}/{input.repo}"
        summary = metadata.get("description") or f"GitHub repository: {name}"
        tags = ["github", "indexed"] + metadata.get("topics", [])[:5]

        ws_metadata = {
            "source": "github",
            "repo_url": metadata.get("html_url", f"https://github.com/{input.owner}/{input.repo}"),
        }

        # Check for existing workstream
        existing = None
        all_ws = await storage.list()
        for ws in all_ws:
            if ws.name == name:
                existing = ws
                break

        if existing:
            request = UpdateWorkstreamRequest(
                id=existing.id,
                name=name,
                summary=summary,
                tags=tags,
                metadata=ws_metadata,
            )
            workstream = await storage.update(request)
        else:
            request = CreateWorkstreamRequest(
                name=name,
                summary=summary,
                tags=tags,
                metadata=ws_metadata,
            )
            workstream = await storage.create(request)

        # Add notes
        notes_added = 0
        if readme and not existing:
            readme_preview = readme[:1500]
            if len(readme) > 1500:
                readme_preview += "\n... (truncated)"
            await storage.add_note(workstream.id, f"CONTEXT: README\n{readme_preview}", "context")
            notes_added += 1

        if prs_issues.get("prs") and not existing:
            pr_summary = "CHANGED: Recent Pull Requests\n"
            for pr in prs_issues["prs"][:5]:
                state = "✓" if pr["state"] == "merged" else ("○" if pr["state"] == "open" else "✗")
                pr_summary += f"- {state} #{pr['number']}: {pr['title']}\n"
            await storage.add_note(workstream.id, pr_summary.strip(), "changed")
            notes_added += 1

        if prs_issues.get("issues") and not existing:
            issue_summary = "CONTEXT: Recent Issues\n"
            for issue in prs_issues["issues"][:5]:
                state = "○" if issue["state"] == "open" else "✓"
                labels = f" [{', '.join(issue['labels'][:3])}]" if issue.get("labels") else ""
                issue_summary += f"- {state} #{issue['number']}: {issue['title']}{labels}\n"
            await storage.add_note(workstream.id, issue_summary.strip(), "context")
            notes_added += 1

        return IndexResult(
            success=True,
            workstream_id=workstream.id,
            workstream_name=workstream.name,
            notes_added=notes_added,
        )

    except Exception as e:
        activity.logger.error(f"Failed to save workstream: {e}")
        return IndexResult(success=False, error=str(e))


@activity.defn
async def scan_local_repo(input: IndexLocalRepoInput) -> dict[str, Any]:
    """Scan local repository for files and metadata."""
    activity.logger.info(f"Scanning local repo: {input.repo_path}")

    repo_path = Path(input.repo_path).expanduser().resolve()

    if not repo_path.exists():
        raise ValueError(f"Repository path does not exist: {repo_path}")

    indexer = LocalRepoIndexer(str(repo_path))
    ws_request, notes = await indexer.index_repository()

    return {
        "name": ws_request.name,
        "summary": ws_request.summary,
        "tags": ws_request.tags,
        "metadata": ws_request.metadata,
        "notes": notes,
    }


@activity.defn
async def extract_local_repo_context(input: IndexLocalRepoInput) -> dict[str, Any]:
    """Extract project context (build system, languages, etc.) from local repo."""
    activity.logger.info(f"Extracting context: {input.repo_path}")

    repo_path = Path(input.repo_path).expanduser().resolve()
    context = extract_project_context(repo_path)

    return context


@activity.defn
async def save_local_workstream(
    input: IndexLocalRepoInput,
    scan_result: dict[str, Any],
    context: dict[str, Any],
) -> IndexResult:
    """Save indexed local repo as a workstream."""
    activity.logger.info(f"Saving local workstream: {input.repo_path}")

    try:
        storage = WorkstreamStorage(profile=input.profile)
        await storage._load()

        repo_path = Path(input.repo_path).expanduser().resolve()
        repo_path_str = str(repo_path)

        # Merge context into metadata
        metadata = scan_result.get("metadata", {})
        metadata["is_monorepo"] = context.get("is_monorepo", False)
        metadata["commands"] = context.get("commands", {})
        metadata["setup_instructions"] = context.get("setup", [])
        metadata["project_type"] = context.get("project_type", "unknown")
        metadata["build_system"] = context.get("build_system", [])
        metadata["architectures"] = context.get("architectures", [])
        metadata["languages"] = context.get("languages", [])
        metadata["ci_cd"] = context.get("ci_cd", [])
        metadata["deployment"] = context.get("deployment", {})
        if context.get("services"):
            metadata["services"] = context["services"]

        # Check for existing workstream
        existing = None
        all_ws = await storage.list()
        for ws in all_ws:
            ws_repo_path = None
            if hasattr(ws.metadata, "extra") and ws.metadata.extra:
                ws_repo_path = ws.metadata.extra.get("repo_path")
            elif hasattr(ws.metadata, "__dict__"):
                ws_repo_path = ws.metadata.__dict__.get("repo_path")
            if ws_repo_path == repo_path_str:
                existing = ws
                break

        if existing:
            request = UpdateWorkstreamRequest(
                id=existing.id,
                name=scan_result["name"],
                summary=scan_result["summary"],
                tags=scan_result["tags"],
                metadata=metadata,
            )
            workstream = await storage.update(request)
        else:
            request = CreateWorkstreamRequest(
                name=scan_result["name"],
                summary=scan_result["summary"],
                tags=scan_result["tags"],
                metadata=metadata,
            )
            workstream = await storage.create(request)

        # Add notes (only for new workstreams)
        notes_added = 0
        if not existing:
            for note in scan_result.get("notes", []):
                await storage.add_note(
                    workstream.id,
                    note["content"],
                    note.get("category", "context"),
                )
                notes_added += 1

        # Handle monorepo services
        services_indexed = 0
        if context.get("is_monorepo") and context.get("services"):
            for svc_name, svc_info in context["services"].items():
                svc_path = repo_path / svc_info["path"]
                svc_path_str = str(svc_path)

                # Check for existing service workstream
                existing_svc = None
                for ws in all_ws:
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
                    svc_update = UpdateWorkstreamRequest(
                        id=existing_svc.id,
                        name=f"Service: {svc_name}",
                        summary=f"Monorepo service - {svc_info['type']} module",
                        tags=["service", svc_info["type"], svc_name],
                        parent_id=workstream.id,
                        metadata=svc_metadata,
                    )
                    await storage.update(svc_update)
                else:
                    svc_request = CreateWorkstreamRequest(
                        name=f"Service: {svc_name}",
                        summary=f"Monorepo service - {svc_info['type']} module at {svc_info['path']}",
                        tags=["service", svc_info["type"], svc_name],
                        parent_id=workstream.id,
                        metadata=svc_metadata,
                    )
                    svc_ws = await storage.create(svc_request)

                    # Add README note if exists
                    readme_file = svc_path / "README.md"
                    if readme_file.exists():
                        try:
                            readme_content = readme_file.read_text()[:3000]
                            await storage.add_note(
                                svc_ws.id, f"[README]\n{readme_content}", "context"
                            )
                        except Exception:
                            pass

                services_indexed += 1

        return IndexResult(
            success=True,
            workstream_id=workstream.id,
            workstream_name=workstream.name,
            notes_added=notes_added,
            services_indexed=services_indexed,
        )

    except Exception as e:
        activity.logger.error(f"Failed to save local workstream: {e}")
        return IndexResult(success=False, error=str(e))
