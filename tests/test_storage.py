"""
Tests for the WorkstreamStorage class.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.storage import WorkstreamStorage
from src.types import CreateWorkstreamRequest, UpdateWorkstreamRequest


@pytest.fixture
async def storage(tmp_path: Path) -> WorkstreamStorage:
    """Create a storage instance with a temporary directory."""
    storage = WorkstreamStorage(str(tmp_path / "data"))
    await storage.initialize()
    return storage


@pytest.mark.asyncio
async def test_create_workstream(storage: WorkstreamStorage) -> None:
    """Test creating a workstream."""
    request = CreateWorkstreamRequest(
        name="Test Project",
        summary="A test project for testing",
        tags=["test", "demo"],
        metadata={
            "hostIps": ["192.168.1.100"],
            "connectionInfo": "ssh user@host",
            "testingInfo": "pytest",
        },
    )
    
    workstream = await storage.create(request)
    
    assert workstream.id.startswith("ws-")
    assert workstream.name == "Test Project"
    assert workstream.summary == "A test project for testing"
    assert "test" in workstream.tags
    assert "demo" in workstream.tags
    assert workstream.metadata.host_ips == ["192.168.1.100"]
    assert workstream.metadata.connection_info == "ssh user@host"
    assert workstream.metadata.testing_info == "pytest"


@pytest.mark.asyncio
async def test_get_workstream(storage: WorkstreamStorage) -> None:
    """Test getting a workstream by ID."""
    request = CreateWorkstreamRequest(
        name="Test Project",
        summary="A test project",
    )
    created = await storage.create(request)
    
    retrieved = await storage.get(created.id)
    
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == created.name


@pytest.mark.asyncio
async def test_get_nonexistent_workstream(storage: WorkstreamStorage) -> None:
    """Test getting a nonexistent workstream."""
    result = await storage.get("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_workstreams(storage: WorkstreamStorage) -> None:
    """Test listing all workstreams."""
    # Create multiple workstreams
    for i in range(3):
        await storage.create(CreateWorkstreamRequest(
            name=f"Project {i}",
            summary=f"Description {i}",
        ))
    
    workstreams = await storage.list()
    
    assert len(workstreams) == 3


@pytest.mark.asyncio
async def test_update_workstream(storage: WorkstreamStorage) -> None:
    """Test updating a workstream."""
    created = await storage.create(CreateWorkstreamRequest(
        name="Original Name",
        summary="Original summary",
        tags=["original"],
    ))
    
    updated = await storage.update(UpdateWorkstreamRequest(
        id=created.id,
        name="Updated Name",
        summary="Updated summary",
        tags=["updated"],
    ))
    
    assert updated is not None
    assert updated.name == "Updated Name"
    assert updated.summary == "Updated summary"
    assert updated.tags == ["updated"]


@pytest.mark.asyncio
async def test_update_partial(storage: WorkstreamStorage) -> None:
    """Test partial update of a workstream."""
    created = await storage.create(CreateWorkstreamRequest(
        name="Original Name",
        summary="Original summary",
    ))
    
    updated = await storage.update(UpdateWorkstreamRequest(
        id=created.id,
        name="Updated Name",
        # summary not provided, should remain unchanged
    ))
    
    assert updated is not None
    assert updated.name == "Updated Name"
    assert updated.summary == "Original summary"


@pytest.mark.asyncio
async def test_delete_workstream(storage: WorkstreamStorage) -> None:
    """Test deleting a workstream."""
    created = await storage.create(CreateWorkstreamRequest(
        name="To Delete",
        summary="This will be deleted",
    ))
    
    deleted = await storage.delete(created.id)
    assert deleted is True
    
    # Verify it's gone
    result = await storage.get(created.id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent(storage: WorkstreamStorage) -> None:
    """Test deleting a nonexistent workstream."""
    deleted = await storage.delete("nonexistent-id")
    assert deleted is False


@pytest.mark.asyncio
async def test_add_tags(storage: WorkstreamStorage) -> None:
    """Test adding tags to a workstream."""
    created = await storage.create(CreateWorkstreamRequest(
        name="Tagged Project",
        summary="A project with tags",
        tags=["initial"],
    ))
    
    updated = await storage.add_tags(created.id, ["new1", "new2"])
    
    assert updated is not None
    assert "initial" in updated.tags
    assert "new1" in updated.tags
    assert "new2" in updated.tags


@pytest.mark.asyncio
async def test_add_duplicate_tags(storage: WorkstreamStorage) -> None:
    """Test adding duplicate tags (should not create duplicates)."""
    created = await storage.create(CreateWorkstreamRequest(
        name="Tagged Project",
        summary="A project with tags",
        tags=["existing"],
    ))
    
    updated = await storage.add_tags(created.id, ["existing", "new"])
    
    assert updated is not None
    # Should have 2 unique tags, not 3
    assert len(updated.tags) == 2
    assert "existing" in updated.tags
    assert "new" in updated.tags


@pytest.mark.asyncio
async def test_search_by_tags_any(storage: WorkstreamStorage) -> None:
    """Test searching by tags (match any)."""
    await storage.create(CreateWorkstreamRequest(
        name="Project A",
        summary="First project",
        tags=["python", "backend"],
    ))
    await storage.create(CreateWorkstreamRequest(
        name="Project B",
        summary="Second project",
        tags=["javascript", "frontend"],
    ))
    await storage.create(CreateWorkstreamRequest(
        name="Project C",
        summary="Third project",
        tags=["python", "frontend"],
    ))
    
    results = await storage.search_by_tags(["python"], match_all=False)
    
    assert len(results) == 2
    names = [r.name for r in results]
    assert "Project A" in names
    assert "Project C" in names


@pytest.mark.asyncio
async def test_search_by_tags_all(storage: WorkstreamStorage) -> None:
    """Test searching by tags (match all)."""
    await storage.create(CreateWorkstreamRequest(
        name="Project A",
        summary="First project",
        tags=["python", "backend"],
    ))
    await storage.create(CreateWorkstreamRequest(
        name="Project B",
        summary="Second project",
        tags=["python", "frontend"],
    ))
    
    results = await storage.search_by_tags(["python", "backend"], match_all=True)
    
    assert len(results) == 1
    assert results[0].name == "Project A"


@pytest.mark.asyncio
async def test_search_by_text(storage: WorkstreamStorage) -> None:
    """Test searching by name or summary text."""
    await storage.create(CreateWorkstreamRequest(
        name="API Migration",
        summary="Migrating to new API",
    ))
    await storage.create(CreateWorkstreamRequest(
        name="UI Redesign",
        summary="New dashboard design",
    ))
    
    results = await storage.search("API")
    
    assert len(results) == 1
    assert results[0].name == "API Migration"


@pytest.mark.asyncio
async def test_search_case_insensitive(storage: WorkstreamStorage) -> None:
    """Test that search is case insensitive."""
    await storage.create(CreateWorkstreamRequest(
        name="API Project",
        summary="Working on API",
    ))
    
    results = await storage.search("api")
    assert len(results) == 1
    
    results = await storage.search("API")
    assert len(results) == 1
    
    results = await storage.search("Api")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_persistence(tmp_path: Path) -> None:
    """Test that data persists across storage instances."""
    data_dir = str(tmp_path / "data")
    
    # Create first instance and add data
    storage1 = WorkstreamStorage(data_dir)
    await storage1.initialize()
    await storage1.create(CreateWorkstreamRequest(
        name="Persistent Project",
        summary="This should persist",
    ))
    
    # Create second instance and verify data
    storage2 = WorkstreamStorage(data_dir)
    await storage2.initialize()
    
    workstreams = await storage2.list()
    assert len(workstreams) == 1
    assert workstreams[0].name == "Persistent Project"


@pytest.mark.asyncio
async def test_add_note(storage: WorkstreamStorage) -> None:
    """Test adding notes to a workstream."""
    workstream = await storage.create(CreateWorkstreamRequest(
        name="Project with Notes",
        summary="Testing notes feature",
    ))
    
    original_updated_at = workstream.updated_at
    import asyncio
    await asyncio.sleep(0.01)  # Ensure timestamp changes
    result = await storage.add_note(workstream.id, "First note")
    
    assert result is not None
    assert len(result.notes) == 1
    assert "First note" in result.notes[0]
    assert result.updated_at != original_updated_at


@pytest.mark.asyncio
async def test_add_multiple_notes(storage: WorkstreamStorage) -> None:
    """Test adding multiple notes to a workstream."""
    workstream = await storage.create(CreateWorkstreamRequest(
        name="Project with Notes",
        summary="Testing notes feature",
    ))
    
    await storage.add_note(workstream.id, "Note 1")
    await storage.add_note(workstream.id, "Note 2")
    result = await storage.add_note(workstream.id, "Note 3")
    
    assert len(result.notes) == 3
    assert "Note 1" in result.notes[0]
    assert "Note 2" in result.notes[1]
    assert "Note 3" in result.notes[2]


@pytest.mark.asyncio
async def test_get_notes(storage: WorkstreamStorage) -> None:
    """Test getting notes for a workstream."""
    workstream = await storage.create(CreateWorkstreamRequest(
        name="Project with Notes",
        summary="Testing notes feature",
    ))
    
    await storage.add_note(workstream.id, "Test note")
    
    notes = await storage.get_notes(workstream.id)
    
    assert notes is not None
    assert len(notes) == 1
    assert "Test note" in notes[0]


@pytest.mark.asyncio
async def test_get_notes_nonexistent(storage: WorkstreamStorage) -> None:
    """Test getting notes for nonexistent workstream."""
    notes = await storage.get_notes("nonexistent-id")
    assert notes is None


@pytest.mark.asyncio
async def test_add_note_nonexistent(storage: WorkstreamStorage) -> None:
    """Test adding note to nonexistent workstream."""
    result = await storage.add_note("nonexistent-id", "Some note")
    assert result is None
