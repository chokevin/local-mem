"""
Tests for the types module.
"""

import pytest

from src.types import Workstream, WorkstreamMetadata


def test_workstream_metadata_to_dict() -> None:
    """Test converting WorkstreamMetadata to dict."""
    metadata = WorkstreamMetadata(
        host_ips=["192.168.1.1", "10.0.0.1"],
        connection_info="ssh user@host",
        testing_info="pytest",
        extra={"custom": "value"},
    )
    
    result = metadata.to_dict()
    
    assert result["hostIps"] == ["192.168.1.1", "10.0.0.1"]
    assert result["connectionInfo"] == "ssh user@host"
    assert result["testingInfo"] == "pytest"
    assert result["custom"] == "value"


def test_workstream_metadata_from_dict() -> None:
    """Test creating WorkstreamMetadata from dict."""
    data = {
        "hostIps": ["192.168.1.1"],
        "connectionInfo": "ssh user@host",
        "testingInfo": "pytest",
        "custom": "value",
    }
    
    metadata = WorkstreamMetadata.from_dict(data)
    
    assert metadata.host_ips == ["192.168.1.1"]
    assert metadata.connection_info == "ssh user@host"
    assert metadata.testing_info == "pytest"
    assert metadata.extra == {"custom": "value"}


def test_workstream_metadata_empty() -> None:
    """Test empty WorkstreamMetadata."""
    metadata = WorkstreamMetadata()
    result = metadata.to_dict()
    
    # Should be empty dict when no values set
    assert result == {}


def test_workstream_to_dict() -> None:
    """Test converting Workstream to dict."""
    workstream = Workstream(
        id="ws-123",
        name="Test Project",
        summary="A test project",
        tags=["test", "demo"],
        metadata=WorkstreamMetadata(host_ips=["192.168.1.1"]),
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )
    
    result = workstream.to_dict()
    
    assert result["id"] == "ws-123"
    assert result["name"] == "Test Project"
    assert result["summary"] == "A test project"
    assert result["tags"] == ["test", "demo"]
    assert result["metadata"]["hostIps"] == ["192.168.1.1"]
    assert result["createdAt"] == "2024-01-01T00:00:00"
    assert result["updatedAt"] == "2024-01-01T00:00:00"


def test_workstream_from_dict() -> None:
    """Test creating Workstream from dict."""
    data = {
        "id": "ws-123",
        "name": "Test Project",
        "summary": "A test project",
        "tags": ["test"],
        "metadata": {"hostIps": ["192.168.1.1"]},
        "createdAt": "2024-01-01T00:00:00",
        "updatedAt": "2024-01-01T00:00:00",
    }
    
    workstream = Workstream.from_dict(data)
    
    assert workstream.id == "ws-123"
    assert workstream.name == "Test Project"
    assert workstream.summary == "A test project"
    assert workstream.tags == ["test"]
    assert workstream.metadata.host_ips == ["192.168.1.1"]
    assert workstream.created_at == "2024-01-01T00:00:00"
    assert workstream.updated_at == "2024-01-01T00:00:00"


def test_workstream_roundtrip() -> None:
    """Test that converting to dict and back preserves data."""
    original = Workstream(
        id="ws-456",
        name="Roundtrip Test",
        summary="Testing serialization",
        tags=["test", "serialization"],
        metadata=WorkstreamMetadata(
            host_ips=["10.0.0.1"],
            connection_info="connect here",
            testing_info="test this way",
            extra={"custom": "data"},
        ),
        created_at="2024-06-15T12:00:00",
        updated_at="2024-06-15T13:00:00",
    )
    
    # Convert to dict and back
    data = original.to_dict()
    restored = Workstream.from_dict(data)
    
    assert restored.id == original.id
    assert restored.name == original.name
    assert restored.summary == original.summary
    assert restored.tags == original.tags
    assert restored.metadata.host_ips == original.metadata.host_ips
    assert restored.metadata.connection_info == original.metadata.connection_info
    assert restored.metadata.testing_info == original.metadata.testing_info
    assert restored.metadata.extra == original.metadata.extra
    assert restored.created_at == original.created_at
    assert restored.updated_at == original.updated_at
