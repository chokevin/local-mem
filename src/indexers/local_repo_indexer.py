"""Local repository indexer - imports local git repo data into workstreams."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import subprocess

from ..types import CreateWorkstreamRequest


class LocalRepoIndexer:
    """Indexes local git repositories into workstream format.
    
    Extracts README, docs, key config files, and git history info.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).expanduser().resolve()
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {self.repo_path}")

    def _read_file(self, *path_parts: str, max_size: int = 50000) -> Optional[str]:
        """Read a file from the repo, return None if not found."""
        file_path = self.repo_path / Path(*path_parts)
        if file_path.exists() and file_path.is_file():
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                return content[:max_size] if len(content) > max_size else content
            except Exception:
                return None
        return None

    def _find_files(self, patterns: list[str]) -> list[Path]:
        """Find files matching patterns."""
        found = []
        for pattern in patterns:
            found.extend(self.repo_path.glob(pattern))
        return found

    def _get_git_info(self) -> dict:
        """Extract git repository information."""
        info = {}
        try:
            # Get remote URL
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=self.repo_path, capture_output=True, text=True
            )
            if result.returncode == 0:
                info['remote_url'] = result.stdout.strip()

            # Get recent commits
            result = subprocess.run(
                ['git', 'log', '--oneline', '-20'],
                cwd=self.repo_path, capture_output=True, text=True
            )
            if result.returncode == 0:
                info['recent_commits'] = result.stdout.strip().split('\n')

            # Get branches
            result = subprocess.run(
                ['git', 'branch', '-a'],
                cwd=self.repo_path, capture_output=True, text=True
            )
            if result.returncode == 0:
                info['branches'] = [b.strip() for b in result.stdout.strip().split('\n')]

        except Exception:
            pass
        return info

    async def index_repository(self) -> tuple[CreateWorkstreamRequest, list[dict]]:
        """Index the local repository and create a workstream request.
        
        Returns:
            Tuple of (CreateWorkstreamRequest, list of notes to add)
        """
        repo_name = self.repo_path.name
        
        # Read key files
        readme = (
            self._read_file('README.md') or 
            self._read_file('README.rst') or 
            self._read_file('README.txt') or 
            self._read_file('README')
        )
        contributing = self._read_file('CONTRIBUTING.md')
        claude_md = self._read_file('CLAUDE.md')
        agents_md = self._read_file('AGENTS.md')
        makefile = self._read_file('Makefile')
        
        # Find docs
        doc_files = self._find_files(['docs/**/*.md', 'doc/**/*.md', 'documentation/**/*.md'])
        
        # Get git info
        git_info = self._get_git_info()
        
        # Build notes
        notes = []
        
        if readme:
            notes.append({
                'category': 'context',
                'content': f"README:\n{readme[:5000]}"
            })
        
        if claude_md:
            notes.append({
                'category': 'context', 
                'content': f"CLAUDE.md (AI guidance):\n{claude_md}"
            })
        
        if agents_md:
            notes.append({
                'category': 'context',
                'content': f"AGENTS.md:\n{agents_md}"
            })
        
        if contributing:
            notes.append({
                'category': 'context',
                'content': f"CONTRIBUTING.md:\n{contributing[:3000]}"
            })
        
        if makefile:
            notes.append({
                'category': 'context',
                'content': f"Makefile targets:\n{makefile[:3000]}"
            })
        
        # Add key docs (first 5)
        for doc_path in doc_files[:5]:
            relative_path = doc_path.relative_to(self.repo_path)
            content = self._read_file(str(relative_path))
            if content:
                notes.append({
                    'category': 'context',
                    'content': f"Doc: {relative_path}\n{content[:3000]}"
                })
        
        # Add git info
        if git_info.get('recent_commits'):
            notes.append({
                'category': 'context',
                'content': f"Recent commits:\n" + '\n'.join(git_info['recent_commits'][:10])
            })
        
        # Build tags
        tags = ['github', 'local-repo', repo_name]
        
        # Detect languages/frameworks
        if (self.repo_path / 'go.mod').exists() or (self.repo_path / 'go.work').exists():
            tags.append('golang')
        if (self.repo_path / 'package.json').exists():
            tags.append('nodejs')
        if (self.repo_path / 'pyproject.toml').exists() or (self.repo_path / 'setup.py').exists():
            tags.append('python')
        if (self.repo_path / 'Cargo.toml').exists() or (self.repo_path / 'Cargo.toml.example').exists():
            tags.append('rust')
        if (self.repo_path / 'Makefile').exists():
            tags.append('makefile')
        if (self.repo_path / 'Dockerfile').exists():
            tags.append('docker')
        if (self.repo_path / '.github').exists():
            tags.append('github-actions')
        
        # Build summary
        summary = f"Local repository: {self.repo_path}"
        if git_info.get('remote_url'):
            summary += f"\nRemote: {git_info['remote_url']}"
        
        request = CreateWorkstreamRequest(
            name=f"Project: {repo_name}",
            summary=summary,
            tags=tags,
            metadata={
                'repo_path': str(self.repo_path),
                'remote_url': git_info.get('remote_url', ''),
                'languages': [t for t in tags if t in ['golang', 'python', 'nodejs', 'rust']],
            }
        )
        
        return request, notes
