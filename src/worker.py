#!/usr/bin/env python3
"""
Temporal worker for mem indexing workflows.

This worker connects to the Temporal server and executes indexing workflows.

Usage:
    python -m src.worker

Environment variables:
    TEMPORAL_ADDRESS: Temporal server address (default: localhost:7233)
    MEM_PROFILE: Storage profile to use (default: test)
"""

from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

# Import workflows (sandbox-safe)
from .workflows import IndexGitHubRepoWorkflow, IndexLocalRepoWorkflow

# Import activities directly (not through __init__ to avoid import issues)
from .workflows.activities import (
    extract_local_repo_context,
    fetch_github_prs_and_issues,
    fetch_github_readme,
    fetch_github_repo_metadata,
    save_github_workstream,
    save_local_workstream,
    scan_local_repo,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Task queue name - workflows and activities are routed here
TASK_QUEUE = "mem-indexing"


async def run_worker():
    """Start the Temporal worker."""
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    logger.info(f"Connecting to Temporal server at {temporal_address}")

    # Connect to Temporal
    client = await Client.connect(temporal_address)
    logger.info("Connected to Temporal server")

    # Create worker with all workflows and activities
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            IndexGitHubRepoWorkflow,
            IndexLocalRepoWorkflow,
        ],
        activities=[
            fetch_github_repo_metadata,
            fetch_github_readme,
            fetch_github_prs_and_issues,
            save_github_workstream,
            scan_local_repo,
            extract_local_repo_context,
            save_local_workstream,
        ],
    )

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")
    await worker.run()


def main():
    """Entry point for the worker."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")


if __name__ == "__main__":
    main()
