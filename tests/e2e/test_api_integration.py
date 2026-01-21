"""
E2E tests for API integration with the web UI.
"""

import httpx
import pytest
from playwright.sync_api import Page, expect


class TestAPICreateReflectsInUI:
    """Tests for API creation reflecting in the UI."""

    def test_api_create_reflects_in_ui(
        self, page: Page, web_server: str, api_client: httpx.Client
    ):
        """Create workstream via API, verify it shows in UI."""
        # Load page first
        page.goto(f"{web_server}/?profile=test")
        page.wait_for_load_state("domcontentloaded")
        
        # Wait for SVG visualization
        svg = page.locator("svg")
        expect(svg.first).to_be_visible(timeout=5000)
        
        # Create workstream via API
        resp = api_client.post(
            "/api/workstreams",
            json={
                "name": "E2E_APICreate",
                "summary": "Created via API for UI verification",
                "tags": ["api", "e2e"],
            },
            params={"profile": "test"},
        )
        assert resp.status_code == 201
        workstream = resp.json()
        ws_id = workstream["id"]
        
        try:
            # Wait for SSE to update UI (or refresh)
            workstream_node = page.locator("text:has-text('E2E_APICreate')")
            expect(workstream_node.first).to_be_visible(timeout=10000)
        finally:
            api_client.delete(f"/api/workstreams/{ws_id}", params={"profile": "test"})


class TestAPIDeleteRemovesFromUI:
    """Tests for API deletion reflecting in the UI."""

    def test_api_delete_removes_from_ui(
        self, page: Page, web_server: str, api_client: httpx.Client
    ):
        """Delete workstream via API, verify it disappears from UI."""
        # Create workstream first
        resp = api_client.post(
            "/api/workstreams",
            json={
                "name": "E2E_APIDelete",
                "summary": "Will be deleted",
                "tags": ["api", "e2e", "delete"],
            },
            params={"profile": "test"},
        )
        assert resp.status_code == 201
        workstream = resp.json()
        ws_id = workstream["id"]
        
        # Load page and verify workstream exists
        page.goto(f"{web_server}/?profile=test")
        page.wait_for_load_state("domcontentloaded")
        
        svg = page.locator("svg")
        expect(svg.first).to_be_visible(timeout=5000)
        
        # Verify workstream is visible
        workstream_node = page.locator("text:has-text('E2E_APIDelete')")
        expect(workstream_node.first).to_be_visible(timeout=5000)
        
        # Delete via API
        del_resp = api_client.delete(
            f"/api/workstreams/{ws_id}", 
            params={"profile": "test"}
        )
        assert del_resp.status_code == 200
        
        # Refresh the page to verify deletion (SSE updates may not remove elements)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        
        # Wait for D3 to render
        page.wait_for_timeout(1000)
        
        # Check that the workstream is no longer visible
        workstream_node = page.locator("text:has-text('E2E_APIDelete')")
        expect(workstream_node).to_have_count(0, timeout=5000)


class TestSearchEndpoint:
    """Tests for the search API endpoint."""

    def test_search_by_text(self, api_client: httpx.Client):
        """Test searching workstreams by text query."""
        # Create test workstreams
        ws1_resp = api_client.post(
            "/api/workstreams",
            json={
                "name": "E2E_SearchAlpha",
                "summary": "First searchable workstream",
                "tags": ["search", "alpha"],
            },
            params={"profile": "test"},
        )
        ws2_resp = api_client.post(
            "/api/workstreams",
            json={
                "name": "E2E_SearchBeta",
                "summary": "Second searchable workstream",
                "tags": ["search", "beta"],
            },
            params={"profile": "test"},
        )
        
        assert ws1_resp.status_code == 201
        assert ws2_resp.status_code == 201
        
        ws1 = ws1_resp.json()
        ws2 = ws2_resp.json()
        
        try:
            # Search by name
            search_resp = api_client.post(
                "/api/workstreams/search",
                json={"query": "SearchAlpha"},
                params={"profile": "test"},
            )
            assert search_resp.status_code == 200
            results = search_resp.json()
            
            # Should find at least ws1
            names = [r["name"] for r in results]
            assert "E2E_SearchAlpha" in names
        finally:
            api_client.delete(f"/api/workstreams/{ws1['id']}", params={"profile": "test"})
            api_client.delete(f"/api/workstreams/{ws2['id']}", params={"profile": "test"})

    def test_search_by_tags(self, api_client: httpx.Client):
        """Test searching workstreams by tags."""
        # Create test workstreams with different tags
        ws1_resp = api_client.post(
            "/api/workstreams",
            json={
                "name": "E2E_TagSearchA",
                "summary": "Has unique tag",
                "tags": ["e2e", "uniquetag123"],
            },
            params={"profile": "test"},
        )
        ws2_resp = api_client.post(
            "/api/workstreams",
            json={
                "name": "E2E_TagSearchB",
                "summary": "Has different tag",
                "tags": ["e2e", "differenttag456"],
            },
            params={"profile": "test"},
        )
        
        assert ws1_resp.status_code == 201
        assert ws2_resp.status_code == 201
        
        ws1 = ws1_resp.json()
        ws2 = ws2_resp.json()
        
        try:
            # Search by specific tag
            search_resp = api_client.post(
                "/api/workstreams/search",
                json={"tags": ["uniquetag123"]},
                params={"profile": "test"},
            )
            assert search_resp.status_code == 200
            results = search_resp.json()
            
            names = [r["name"] for r in results]
            assert "E2E_TagSearchA" in names
            assert "E2E_TagSearchB" not in names
        finally:
            api_client.delete(f"/api/workstreams/{ws1['id']}", params={"profile": "test"})
            api_client.delete(f"/api/workstreams/{ws2['id']}", params={"profile": "test"})


class TestAPIWorkstreamOperations:
    """Tests for CRUD operations on workstreams."""

    def test_create_and_get_workstream(self, api_client: httpx.Client):
        """Test creating and retrieving a workstream."""
        # Create
        resp = api_client.post(
            "/api/workstreams",
            json={
                "name": "E2E_CRUD",
                "summary": "CRUD test workstream",
                "tags": ["crud", "e2e"],
            },
            params={"profile": "test"},
        )
        assert resp.status_code == 201
        workstream = resp.json()
        ws_id = workstream["id"]
        
        try:
            # Get
            get_resp = api_client.get(
                f"/api/workstreams/{ws_id}",
                params={"profile": "test"},
            )
            assert get_resp.status_code == 200
            retrieved = get_resp.json()
            assert retrieved["name"] == "E2E_CRUD"
            assert retrieved["summary"] == "CRUD test workstream"
        finally:
            api_client.delete(f"/api/workstreams/{ws_id}", params={"profile": "test"})

    def test_list_workstreams(self, api_client: httpx.Client):
        """Test listing all workstreams."""
        # Create a test workstream
        resp = api_client.post(
            "/api/workstreams",
            json={
                "name": "E2E_List",
                "summary": "List test workstream",
                "tags": ["list", "e2e"],
            },
            params={"profile": "test"},
        )
        assert resp.status_code == 201
        workstream = resp.json()
        ws_id = workstream["id"]
        
        try:
            # List
            list_resp = api_client.get(
                "/api/workstreams",
                params={"profile": "test"},
            )
            assert list_resp.status_code == 200
            workstreams = list_resp.json()
            
            # Should be a list
            assert isinstance(workstreams, list)
            
            # Should contain our workstream
            names = [ws["name"] for ws in workstreams]
            assert "E2E_List" in names
        finally:
            api_client.delete(f"/api/workstreams/{ws_id}", params={"profile": "test"})

    def test_add_note_to_workstream(self, api_client: httpx.Client):
        """Test adding notes to a workstream."""
        # Create workstream
        resp = api_client.post(
            "/api/workstreams",
            json={
                "name": "E2E_Notes",
                "summary": "Notes test workstream",
                "tags": ["notes", "e2e"],
            },
            params={"profile": "test"},
        )
        assert resp.status_code == 201
        workstream = resp.json()
        ws_id = workstream["id"]
        
        try:
            # Add note
            note_resp = api_client.post(
                f"/api/workstreams/{ws_id}/notes",
                json={"note": "This is a test note"},
                params={"profile": "test"},
            )
            assert note_resp.status_code == 200
            updated = note_resp.json()
            
            # Verify note was added
            assert len(updated["notes"]) > 0
            assert "This is a test note" in updated["notes"][0]
        finally:
            api_client.delete(f"/api/workstreams/{ws_id}", params={"profile": "test"})
