"""
Temporal workflows for indexing operations.

Workflows orchestrate activities and define the overall indexing flow.
They are durable - if a worker crashes, the workflow resumes from the last checkpoint.

IMPORTANT: Workflows run in a sandbox and cannot import most external libraries.
Only activity function references (not implementations) should be imported here.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import only data classes - these are safe for sandbox
from .data import IndexGitHubRepoInput, IndexLocalRepoInput, IndexResult


# Activity function references - these are just strings at workflow validation time
@workflow.defn
class IndexGitHubRepoWorkflow:
    """Workflow for indexing a GitHub repository.

    Steps:
    1. Fetch repository metadata (description, topics)
    2. Fetch README content
    3. Fetch recent PRs and issues
    4. Save as workstream with notes
    """

    @workflow.run
    async def run(self, input: IndexGitHubRepoInput) -> IndexResult:
        workflow.logger.info(f"Starting GitHub indexing: {input.owner}/{input.repo}")

        # Step 1: Fetch metadata
        metadata: dict[str, Any] = await workflow.execute_activity(
            "fetch_github_repo_metadata",
            input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )

        # Step 2: Fetch README (parallel with step 3)
        readme_task = workflow.execute_activity(
            "fetch_github_readme",
            input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )

        # Step 3: Fetch PRs and issues
        prs_issues_task = workflow.execute_activity(
            "fetch_github_prs_and_issues",
            input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )

        # Wait for both
        readme: str | None = await readme_task
        prs_issues: dict[str, list[dict[str, Any]]] = await prs_issues_task

        # Step 4: Save workstream
        result = await workflow.execute_activity(
            "save_github_workstream",
            args=[input, metadata, readme, prs_issues],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
            result_type=IndexResult,
        )

        workflow.logger.info(f"GitHub indexing complete: {result.workstream_id}")
        return result


@workflow.defn
class IndexLocalRepoWorkflow:
    """Workflow for indexing a local repository.

    Steps:
    1. Scan repository for files and metadata
    2. Extract project context (build system, CI/CD, etc.)
    3. Save as workstream with notes
    """

    @workflow.run
    async def run(self, input: IndexLocalRepoInput) -> IndexResult:
        workflow.logger.info(f"Starting local repo indexing: {input.repo_path}")

        # Step 1: Scan repository
        scan_result: dict[str, Any] = await workflow.execute_activity(
            "scan_local_repo",
            input,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )

        # Step 2: Extract project context
        context: dict[str, Any] = await workflow.execute_activity(
            "extract_local_repo_context",
            input,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )

        # Step 3: Save workstream
        result = await workflow.execute_activity(
            "save_local_workstream",
            args=[input, scan_result, context],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
            result_type=IndexResult,
        )

        workflow.logger.info(f"Local repo indexing complete: {result.workstream_id}")
        return result
