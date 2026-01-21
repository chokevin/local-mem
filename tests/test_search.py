"""
Tests for full-text search functionality.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.search import SearchEngine
from src.storage import WorkstreamStorage
from src.types import CreateWorkstreamRequest, Workstream


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test data."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def search_engine(temp_dir):
    """Create a search engine for testing."""
    return SearchEngine(index_dir=temp_dir, profile="test")


@pytest.fixture
def sample_workstreams():
    """Create sample workstreams for testing."""
    return [
        Workstream(
            id="ws-1",
            name="API Gateway",
            summary="Building a REST API gateway with authentication",
            tags=["api", "backend", "auth"],
            notes=["[2024-01-01] Started implementation", "[2024-01-02] Added OAuth support"],
        ),
        Workstream(
            id="ws-2",
            name="Frontend Dashboard",
            summary="React dashboard for monitoring services",
            tags=["frontend", "react", "monitoring"],
            notes=["[2024-01-03] Created component library"],
        ),
        Workstream(
            id="ws-3",
            name="Database Migration",
            summary="Migrating from MySQL to PostgreSQL",
            tags=["database", "backend", "migration"],
            notes=["[2024-01-04] Schema analysis complete", "[2024-01-05] Started data migration"],
        ),
    ]


class TestSearchEngine:
    """Tests for the SearchEngine class."""

    def test_rebuild_index(self, search_engine, sample_workstreams):
        """Test rebuilding the entire index."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("API")
        assert len(results) == 1
        assert results[0]["id"] == "ws-1"

    def test_simple_search(self, search_engine, sample_workstreams):
        """Test simple text search."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("dashboard")
        assert len(results) == 1
        assert results[0]["id"] == "ws-2"

    def test_search_in_notes(self, search_engine, sample_workstreams):
        """Test searching in notes content."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("OAuth")
        assert len(results) == 1
        assert results[0]["id"] == "ws-1"

    def test_search_by_tags(self, search_engine, sample_workstreams):
        """Test searching by tag keywords."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("backend")
        assert len(results) == 2
        ids = {r["id"] for r in results}
        assert ids == {"ws-1", "ws-3"}

    def test_and_operator(self, search_engine, sample_workstreams):
        """Test AND operator in queries."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("backend AND migration")
        assert len(results) == 1
        assert results[0]["id"] == "ws-3"

    def test_or_operator(self, search_engine, sample_workstreams):
        """Test OR operator in queries."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("dashboard OR migration")
        assert len(results) == 2
        ids = {r["id"] for r in results}
        assert ids == {"ws-2", "ws-3"}

    def test_field_specific_search(self, search_engine, sample_workstreams):
        """Test field-specific search."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("name:Gateway")
        assert len(results) == 1
        assert results[0]["id"] == "ws-1"

    def test_search_limit(self, search_engine, sample_workstreams):
        """Test search result limit."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("backend OR frontend OR database", limit=2)
        assert len(results) == 2

    def test_search_with_score(self, search_engine, sample_workstreams):
        """Test that search results include relevance scores."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("API")
        assert len(results) > 0
        assert "score" in results[0]
        assert results[0]["score"] > 0

    def test_index_workstream(self, search_engine, sample_workstreams):
        """Test indexing a single workstream."""
        search_engine.rebuild_index(sample_workstreams[:2])
        
        # Should not find ws-3 yet
        results = search_engine.search("PostgreSQL")
        assert len(results) == 0
        
        # Index ws-3
        search_engine.index_workstream(sample_workstreams[2])
        
        # Now should find it
        results = search_engine.search("PostgreSQL")
        assert len(results) == 1
        assert results[0]["id"] == "ws-3"

    def test_remove_workstream(self, search_engine, sample_workstreams):
        """Test removing a workstream from the index."""
        search_engine.rebuild_index(sample_workstreams)
        
        # Should find ws-1
        results = search_engine.search("API")
        assert len(results) == 1
        
        # Remove ws-1
        search_engine.remove_workstream("ws-1")
        
        # Should not find it anymore
        results = search_engine.search("API Gateway")
        assert len(results) == 0

    def test_update_workstream(self, search_engine, sample_workstreams):
        """Test updating a workstream in the index."""
        search_engine.rebuild_index(sample_workstreams)
        
        # Update ws-1
        ws = sample_workstreams[0]
        ws.summary = "Updated to GraphQL API"
        search_engine.index_workstream(ws)
        
        # Should find with new content
        results = search_engine.search("GraphQL")
        assert len(results) == 1
        assert results[0]["id"] == "ws-1"

    def test_empty_search(self, search_engine, sample_workstreams):
        """Test searching with no matching results."""
        search_engine.rebuild_index(sample_workstreams)
        results = search_engine.search("nonexistent term xyz123")
        assert len(results) == 0


class TestStorageFulltextSearch:
    """Tests for full-text search integration with storage."""

    @pytest.fixture
    async def storage(self, temp_dir):
        """Create a storage instance for testing."""
        storage = WorkstreamStorage(data_dir=temp_dir, profile="test")
        await storage.initialize()
        return storage

    async def test_fulltext_search_method(self, storage):
        """Test the fulltext_search method on storage."""
        # Create some workstreams
        await storage.create(CreateWorkstreamRequest(
            name="Search Test",
            summary="Testing full-text search functionality",
            tags=["search", "test"],
        ))
        await storage.create(CreateWorkstreamRequest(
            name="Other Project",
            summary="Unrelated work item",
            tags=["other"],
        ))
        
        results = await storage.fulltext_search("search")
        assert len(results) >= 1
        assert any(r["name"] == "Search Test" for r in results)

    async def test_search_index_auto_update_on_create(self, storage):
        """Test that creating a workstream updates the index."""
        ws = await storage.create(CreateWorkstreamRequest(
            name="New Workstream",
            summary="Just created this workstream",
            tags=["new"],
        ))
        
        results = await storage.fulltext_search("created")
        assert len(results) == 1
        assert results[0]["id"] == ws.id

    async def test_search_index_auto_update_on_update(self, storage):
        """Test that updating a workstream updates the index."""
        ws = await storage.create(CreateWorkstreamRequest(
            name="Original Name",
            summary="Original summary",
            tags=["original"],
        ))
        
        from src.types import UpdateWorkstreamRequest
        await storage.update(UpdateWorkstreamRequest(
            id=ws.id,
            summary="Completely different content about databases",
        ))
        
        results = await storage.fulltext_search("databases")
        assert len(results) == 1
        assert results[0]["id"] == ws.id

    async def test_search_index_auto_update_on_delete(self, storage):
        """Test that deleting a workstream removes it from index."""
        ws = await storage.create(CreateWorkstreamRequest(
            name="To Be Deleted",
            summary="This will be removed",
            tags=["temporary"],
        ))
        
        # Verify it's searchable
        results = await storage.fulltext_search("removed")
        assert len(results) == 1
        
        # Delete it
        await storage.delete(ws.id)
        
        # Should not be found
        results = await storage.fulltext_search("removed")
        assert len(results) == 0

    async def test_search_index_auto_update_on_add_note(self, storage):
        """Test that adding a note updates the index."""
        ws = await storage.create(CreateWorkstreamRequest(
            name="Note Test",
            summary="Testing notes",
            tags=["notes"],
        ))
        
        await storage.add_note(ws.id, "Important information about kubernetes deployment")
        
        results = await storage.fulltext_search("kubernetes")
        assert len(results) == 1
        assert results[0]["id"] == ws.id
