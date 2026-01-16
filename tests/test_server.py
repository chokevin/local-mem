"""
Tests for the MCP server functionality.
"""

import json
import pytest

from src.server import get_tools, storage, call_tool


@pytest.fixture(autouse=True)
async def reset_storage(tmp_path):
    """Reset storage before each test."""
    # Override storage data directory for testing
    storage.data_dir = tmp_path / "data"
    storage.data_file = storage.data_dir / "workstreams.json"
    storage._workstreams = {}
    await storage.initialize()


def test_get_tools():
    """Test that all expected tools are defined."""
    tools = get_tools()
    tool_names = [t.name for t in tools]
    
    expected_tools = [
        "create_workstream",
        "list_workstreams",
        "get_workstream",
        "update_workstream",
        "delete_workstream",
        "add_tags",
        "search_by_tags",
        "search_workstreams",
    ]
    
    for expected in expected_tools:
        assert expected in tool_names, f"Missing tool: {expected}"


def test_tool_schemas():
    """Test that tool schemas have required fields."""
    tools = get_tools()
    
    for tool in tools:
        assert tool.name, "Tool missing name"
        assert tool.description, f"Tool {tool.name} missing description"
        assert tool.inputSchema, f"Tool {tool.name} missing inputSchema"
        assert "type" in tool.inputSchema
        assert tool.inputSchema["type"] == "object"


@pytest.mark.asyncio
async def test_create_workstream_tool():
    """Test the create_workstream tool."""
    result = await call_tool("create_workstream", {
        "name": "Test Project",
        "summary": "A test workstream",
        "tags": ["test"],
    })
    
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["name"] == "Test Project"
    assert data["summary"] == "A test workstream"
    assert "test" in data["tags"]


@pytest.mark.asyncio
async def test_list_workstreams_tool():
    """Test the list_workstreams tool."""
    # Create a few workstreams
    await call_tool("create_workstream", {
        "name": "Project 1",
        "summary": "First project",
    })
    await call_tool("create_workstream", {
        "name": "Project 2",
        "summary": "Second project",
    })
    
    result = await call_tool("list_workstreams", {})
    
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_workstream_tool():
    """Test the get_workstream tool."""
    # Create a workstream
    create_result = await call_tool("create_workstream", {
        "name": "Get Test",
        "summary": "Test getting",
    })
    created = json.loads(create_result[0].text)
    
    # Get it back
    result = await call_tool("get_workstream", {"id": created["id"]})
    
    data = json.loads(result[0].text)
    assert data["name"] == "Get Test"


@pytest.mark.asyncio
async def test_get_workstream_not_found():
    """Test getting a non-existent workstream."""
    result = await call_tool("get_workstream", {"id": "nonexistent"})
    
    assert "not found" in result[0].text


@pytest.mark.asyncio
async def test_update_workstream_tool():
    """Test the update_workstream tool."""
    # Create a workstream
    create_result = await call_tool("create_workstream", {
        "name": "Original",
        "summary": "Original summary",
    })
    created = json.loads(create_result[0].text)
    
    # Update it
    result = await call_tool("update_workstream", {
        "id": created["id"],
        "name": "Updated",
    })
    
    data = json.loads(result[0].text)
    assert data["name"] == "Updated"
    assert data["summary"] == "Original summary"  # Should be unchanged


@pytest.mark.asyncio
async def test_delete_workstream_tool():
    """Test the delete_workstream tool."""
    # Create a workstream
    create_result = await call_tool("create_workstream", {
        "name": "To Delete",
        "summary": "Will be deleted",
    })
    created = json.loads(create_result[0].text)
    
    # Delete it
    result = await call_tool("delete_workstream", {"id": created["id"]})
    
    assert "deleted successfully" in result[0].text
    
    # Verify it's gone
    get_result = await call_tool("get_workstream", {"id": created["id"]})
    assert "not found" in get_result[0].text


@pytest.mark.asyncio
async def test_add_tags_tool():
    """Test the add_tags tool."""
    # Create a workstream
    create_result = await call_tool("create_workstream", {
        "name": "Tag Test",
        "summary": "Testing tags",
        "tags": ["initial"],
    })
    created = json.loads(create_result[0].text)
    
    # Add tags
    result = await call_tool("add_tags", {
        "id": created["id"],
        "tags": ["new1", "new2"],
    })
    
    data = json.loads(result[0].text)
    assert "initial" in data["tags"]
    assert "new1" in data["tags"]
    assert "new2" in data["tags"]


@pytest.mark.asyncio
async def test_search_by_tags_tool():
    """Test the search_by_tags tool."""
    # Create workstreams with different tags
    await call_tool("create_workstream", {
        "name": "Python Project",
        "summary": "A Python project",
        "tags": ["python", "backend"],
    })
    await call_tool("create_workstream", {
        "name": "JS Project",
        "summary": "A JavaScript project",
        "tags": ["javascript", "frontend"],
    })
    
    # Search for python tag
    result = await call_tool("search_by_tags", {"tags": ["python"]})
    
    data = json.loads(result[0].text)
    assert len(data) == 1
    assert data[0]["name"] == "Python Project"


@pytest.mark.asyncio
async def test_search_workstreams_tool():
    """Test the search_workstreams tool."""
    # Create workstreams
    await call_tool("create_workstream", {
        "name": "API Migration",
        "summary": "Migrating APIs",
    })
    await call_tool("create_workstream", {
        "name": "UI Update",
        "summary": "Updating user interface",
    })
    
    # Search
    result = await call_tool("search_workstreams", {"query": "API"})
    
    data = json.loads(result[0].text)
    assert len(data) == 1
    assert data[0]["name"] == "API Migration"


@pytest.mark.asyncio
async def test_unknown_tool():
    """Test calling an unknown tool."""
    result = await call_tool("unknown_tool", {})
    
    assert "Unknown tool" in result[0].text
