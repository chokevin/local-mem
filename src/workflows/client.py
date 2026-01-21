#!/usr/bin/env python3
"""
Client for starting Temporal workflows.

This module provides functions to start indexing workflows from CLI or API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from temporalio.client import Client

from .workflows import (
    IndexGitHubRepoInput,
    IndexGitHubRepoWorkflow,
    IndexLocalRepoInput,
    IndexLocalRepoWorkflow,
    IndexResult,
)

# Task queue must match the worker
TASK_QUEUE = "mem-indexing"


@dataclass
class WorkflowHandle:
    """Handle to a running or completed workflow."""

    workflow_id: str
    run_id: str


async def get_temporal_client() -> Client:
    """Get a connected Temporal client."""
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    return await Client.connect(temporal_address)


async def start_github_indexing(
    owner: str,
    repo: str,
    profile: str = "test",
    client: Optional[Client] = None,
) -> WorkflowHandle:
    """Start a GitHub repository indexing workflow.

    Args:
        owner: GitHub repository owner
        repo: GitHub repository name
        profile: Storage profile to use
        client: Optional existing Temporal client

    Returns:
        WorkflowHandle with workflow_id and run_id
    """
    import uuid

    if client is None:
        client = await get_temporal_client()

    workflow_id = f"index-github-{owner}-{repo}-{uuid.uuid4().hex[:8]}"
    input_data = IndexGitHubRepoInput(owner=owner, repo=repo, profile=profile)

    handle = await client.start_workflow(
        IndexGitHubRepoWorkflow.run,
        input_data,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return WorkflowHandle(workflow_id=handle.id, run_id=handle.result_run_id)


async def start_local_indexing(
    repo_path: str,
    profile: str = "test",
    client: Optional[Client] = None,
) -> WorkflowHandle:
    """Start a local repository indexing workflow.

    Args:
        repo_path: Path to the local repository
        profile: Storage profile to use
        client: Optional existing Temporal client

    Returns:
        WorkflowHandle with workflow_id and run_id
    """
    import uuid

    if client is None:
        client = await get_temporal_client()

    # Create a unique workflow ID from the repo path + timestamp
    repo_name = repo_path.rstrip("/").split("/")[-1]
    workflow_id = f"index-local-{repo_name}-{uuid.uuid4().hex[:8]}"
    input_data = IndexLocalRepoInput(repo_path=repo_path, profile=profile)

    handle = await client.start_workflow(
        IndexLocalRepoWorkflow.run,
        input_data,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return WorkflowHandle(workflow_id=handle.id, run_id=handle.result_run_id)


async def get_workflow_result(
    workflow_id: str,
    client: Optional[Client] = None,
) -> IndexResult:
    """Get the result of a completed workflow.

    Args:
        workflow_id: The workflow ID to check
        client: Optional existing Temporal client

    Returns:
        IndexResult with success status and workstream details
    """
    if client is None:
        client = await get_temporal_client()

    handle = client.get_workflow_handle(workflow_id)
    result = await handle.result()

    # Convert dict to IndexResult if needed
    if isinstance(result, dict):
        return IndexResult(**result)
    return result


async def get_workflow_status(
    workflow_id: str,
    client: Optional[Client] = None,
) -> dict:
    """Get the status of a workflow.

    Args:
        workflow_id: The workflow ID to check
        client: Optional existing Temporal client

    Returns:
        Dict with status, start_time, close_time, etc.
    """
    if client is None:
        client = await get_temporal_client()

    handle = client.get_workflow_handle(workflow_id)
    desc = await handle.describe()

    return {
        "workflow_id": desc.id,
        "run_id": desc.run_id,
        "status": desc.status.name,
        "workflow_type": desc.workflow_type,
        "task_queue": desc.task_queue,
        "start_time": desc.start_time.isoformat() if desc.start_time else None,
        "close_time": desc.close_time.isoformat() if desc.close_time else None,
        "execution_time": desc.execution_time.isoformat() if desc.execution_time else None,
    }


async def list_workflows(
    client: Optional[Client] = None,
    query: str = "",
) -> list[dict]:
    """List workflows with optional query filter.

    Args:
        client: Optional existing Temporal client
        query: Optional Temporal query string (e.g., 'WorkflowType="IndexLocalRepoWorkflow"')

    Returns:
        List of workflow summaries
    """
    if client is None:
        client = await get_temporal_client()

    workflows = []
    async for wf in client.list_workflows(query=query):
        workflows.append({
            "workflow_id": wf.id,
            "run_id": wf.run_id,
            "status": wf.status.name,
            "workflow_type": wf.workflow_type,
            "start_time": wf.start_time.isoformat() if wf.start_time else None,
            "close_time": wf.close_time.isoformat() if wf.close_time else None,
        })

    return workflows
