"""
Pytest fixtures for E2E testing with Playwright.
"""

import asyncio
import os
import socket
import time
from collections.abc import Generator
from multiprocessing import Process

import httpx
import pytest
from playwright.sync_api import Browser, Page, Playwright, sync_playwright

# E2E test server runs on a different port than Docker (8080)
E2E_PORT = 8081
E2E_BASE_URL = f"http://127.0.0.1:{E2E_PORT}"


def _is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _run_server():
    """Run the web server in a subprocess."""
    import uvicorn
    from src.web import app
    
    # Force test profile
    os.environ["MEM_PROFILE"] = "test"
    
    uvicorn.run(app, host="127.0.0.1", port=E2E_PORT, log_level="warning")


def _wait_for_server(url: str, timeout: float = 10.0) -> bool:
    """Wait for server to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code == 200:
                return True
        except (httpx.RequestError, httpx.TimeoutException):
            pass
        time.sleep(0.1)
    return False


@pytest.fixture(scope="session")
def web_server() -> Generator[str, None, None]:
    """Start/stop the web server for E2E tests."""
    if _is_port_in_use(E2E_PORT):
        # Server already running (maybe from Docker or manual start)
        yield E2E_BASE_URL
        return
    
    # Start server in subprocess
    proc = Process(target=_run_server, daemon=True)
    proc.start()
    
    # Wait for server to be ready
    if not _wait_for_server(E2E_BASE_URL):
        proc.terminate()
        proc.join(timeout=5)
        pytest.fail(f"Server failed to start on {E2E_BASE_URL}")
    
    yield E2E_BASE_URL
    
    # Cleanup
    proc.terminate()
    proc.join(timeout=5)


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    """Provide a Playwright instance."""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Generator[Browser, None, None]:
    """Provide a browser instance."""
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture
def page(browser: Browser, web_server: str) -> Generator[Page, None, None]:
    """Provide a fresh page for each test."""
    context = browser.new_context()
    page = context.new_page()
    yield page
    page.close()
    context.close()


@pytest.fixture
def api_client(web_server: str) -> Generator[httpx.Client, None, None]:
    """Provide an HTTP client for API calls."""
    with httpx.Client(base_url=web_server, timeout=10.0) as client:
        yield client


@pytest.fixture(autouse=True)
def clean_test_data(api_client: httpx.Client) -> Generator[None, None, None]:
    """Clean up test workstreams before and after each test."""
    # Get current workstreams and delete any with test prefix
    _cleanup_test_workstreams(api_client)
    yield
    _cleanup_test_workstreams(api_client)


def _cleanup_test_workstreams(client: httpx.Client):
    """Delete workstreams created during E2E tests."""
    try:
        resp = client.get("/api/workstreams", params={"profile": "test"})
        if resp.status_code == 200:
            workstreams = resp.json()
            for ws in workstreams:
                if ws.get("name", "").startswith("E2E_"):
                    client.delete(
                        f"/api/workstreams/{ws['id']}", 
                        params={"profile": "test"}
                    )
    except Exception:
        pass  # Ignore cleanup errors
