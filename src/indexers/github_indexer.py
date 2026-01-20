"""GitHub repository indexer - imports repo data into workstreams."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from ..types import CreateWorkstreamRequest


@dataclass
class GitHubContent:
    """Extracted content from a GitHub repository."""

    readme: Optional[str] = None
    description: Optional[str] = None
    topics: list[str] = None
    recent_prs: list[dict[str, Any]] = None
    recent_issues: list[dict[str, Any]] = None

    def __post_init__(self):
        if self.topics is None:
            self.topics = []
        if self.recent_prs is None:
            self.recent_prs = []
        if self.recent_issues is None:
            self.recent_issues = []


class GitHubIndexer:
    """Indexes GitHub repositories into workstream format.
    
    Supports both github.com and GitHub Enterprise (EMU).
    
    Args:
        token: GitHub personal access token. Defaults to GITHUB_TOKEN env var.
        base_url: API base URL. Defaults to GITHUB_API_URL env var or https://api.github.com.
                  For GHE: https://api.github.yourcompany.com
    """

    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.base_url = (
            base_url 
            or os.environ.get("GITHUB_API_URL") 
            or "https://api.github.com"
        ).rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "local-mem-indexer",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    async def fetch_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Fetch repository metadata."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/repos/{owner}/{repo}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def fetch_readme(self, owner: str, repo: str) -> Optional[str]:
        """Fetch repository README content."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/readme",
                    headers={**self._headers(), "Accept": "application/vnd.github.raw"},
                )
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError:
                return None

    async def fetch_recent_prs(
        self, owner: str, repo: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Fetch recent pull requests."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/repos/{owner}/{repo}/pulls",
                headers=self._headers(),
                params={"state": "all", "sort": "updated", "per_page": limit},
            )
            response.raise_for_status()
            prs = response.json()
            return [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "url": pr["html_url"],
                    "body": pr.get("body", "")[:500] if pr.get("body") else "",
                }
                for pr in prs
            ]

    async def fetch_recent_issues(
        self, owner: str, repo: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Fetch recent issues (excluding PRs)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/repos/{owner}/{repo}/issues",
                headers=self._headers(),
                params={"state": "all", "sort": "updated", "per_page": limit},
            )
            response.raise_for_status()
            issues = response.json()
            # Filter out pull requests (they appear in issues endpoint too)
            return [
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue["state"],
                    "url": issue["html_url"],
                    "labels": [l["name"] for l in issue.get("labels", [])],
                    "body": issue.get("body", "")[:500] if issue.get("body") else "",
                }
                for issue in issues
                if "pull_request" not in issue
            ]

    async def index_repository(self, owner: str, repo: str) -> GitHubContent:
        """Index a GitHub repository and extract relevant content."""
        content = GitHubContent()

        # Fetch repo metadata
        repo_data = await self.fetch_repo(owner, repo)
        content.description = repo_data.get("description")
        content.topics = repo_data.get("topics", [])

        # Fetch README
        content.readme = await self.fetch_readme(owner, repo)

        # Fetch recent PRs and issues
        content.recent_prs = await self.fetch_recent_prs(owner, repo)
        content.recent_issues = await self.fetch_recent_issues(owner, repo)

        return content

    def _extract_setup_info(self, readme: Optional[str]) -> Optional[str]:
        """Extract setup/installation info from README."""
        if not readme:
            return None

        lines = readme.split("\n")
        setup_sections = []
        in_setup = False
        setup_buffer = []

        for line in lines:
            lower = line.lower()
            # Check for setup-related headers
            if any(
                kw in lower
                for kw in ["# install", "# setup", "# getting started", "## install", "## setup"]
            ):
                if setup_buffer:
                    setup_sections.append("\n".join(setup_buffer))
                in_setup = True
                setup_buffer = [line]
            elif in_setup:
                # End on next major header
                if line.startswith("# ") or (line.startswith("## ") and len(setup_buffer) > 3):
                    setup_sections.append("\n".join(setup_buffer))
                    in_setup = False
                    setup_buffer = []
                else:
                    setup_buffer.append(line)

        if setup_buffer:
            setup_sections.append("\n".join(setup_buffer))

        if setup_sections:
            return "\n\n".join(setup_sections)[:2000]
        return None

    def to_workstream_request(
        self, owner: str, repo: str, content: GitHubContent
    ) -> CreateWorkstreamRequest:
        """Convert indexed content to a CreateWorkstreamRequest."""
        name = f"{owner}/{repo}"
        summary = content.description or f"GitHub repository: {owner}/{repo}"

        # Build tags from topics
        tags = ["github", "indexed"] + content.topics[:5]

        # Build metadata
        metadata: dict[str, Any] = {
            "source": "github",
            "repo_url": f"https://github.com/{owner}/{repo}",
        }

        setup_info = self._extract_setup_info(content.readme)
        if setup_info:
            metadata["testingInfo"] = setup_info

        return CreateWorkstreamRequest(
            name=name,
            summary=summary,
            tags=tags,
            metadata=metadata,
        )

    def extract_notes(self, content: GitHubContent) -> list[str]:
        """Extract notes from indexed content."""
        notes = []

        # Add README summary as context note
        if content.readme:
            readme_preview = content.readme[:1500]
            if len(content.readme) > 1500:
                readme_preview += "\n... (truncated)"
            notes.append(f"CONTEXT: README\n{readme_preview}")

        # Add recent PRs as decisions/changes
        if content.recent_prs:
            pr_summary = "CHANGED: Recent Pull Requests\n"
            for pr in content.recent_prs[:5]:
                state = "✓" if pr["state"] == "merged" else ("○" if pr["state"] == "open" else "✗")
                pr_summary += f"- {state} #{pr['number']}: {pr['title']}\n"
            notes.append(pr_summary.strip())

        # Add recent issues as context
        if content.recent_issues:
            issue_summary = "CONTEXT: Recent Issues\n"
            for issue in content.recent_issues[:5]:
                state = "○" if issue["state"] == "open" else "✓"
                labels = f" [{', '.join(issue['labels'][:3])}]" if issue["labels"] else ""
                issue_summary += f"- {state} #{issue['number']}: {issue['title']}{labels}\n"
            notes.append(issue_summary.strip())

        return notes
