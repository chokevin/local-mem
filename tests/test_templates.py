"""
Tests for the TemplateStorage class.
"""

from pathlib import Path

import pytest

from src.storage import WorkstreamStorage
from src.templates import (
    CreateTemplateRequest,
    InstantiateTemplateRequest,
    TemplateStorage,
    WorkstreamTemplate,
)


@pytest.fixture
async def template_storage(tmp_path: Path) -> TemplateStorage:
    """Create a template storage instance with a temporary directory."""
    storage = TemplateStorage(str(tmp_path / "data"))
    await storage.initialize()
    return storage


@pytest.fixture
async def workstream_storage(tmp_path: Path) -> WorkstreamStorage:
    """Create a workstream storage instance with a temporary directory."""
    storage = WorkstreamStorage(str(tmp_path / "data"))
    await storage.initialize()
    return storage


@pytest.mark.asyncio
async def test_create_template(template_storage: TemplateStorage) -> None:
    """Test creating a template."""
    request = CreateTemplateRequest(
        name="Python Project",
        description="Template for Python projects",
        default_tags=["python", "backend"],
        default_metadata={"testingInfo": "pytest"},
        note_templates=["SETUP: Run `pip install -e .`"],
    )

    template = await template_storage.create_template(request)

    assert template.id.startswith("tmpl-")
    assert template.name == "Python Project"
    assert template.description == "Template for Python projects"
    assert "python" in template.default_tags
    assert "backend" in template.default_tags
    assert template.default_metadata == {"testingInfo": "pytest"}
    assert len(template.note_templates) == 1


@pytest.mark.asyncio
async def test_get_template(template_storage: TemplateStorage) -> None:
    """Test getting a template by ID."""
    request = CreateTemplateRequest(
        name="Test Template",
        description="A test template",
    )
    created = await template_storage.create_template(request)

    retrieved = await template_storage.get_template(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == created.name


@pytest.mark.asyncio
async def test_get_nonexistent_template(template_storage: TemplateStorage) -> None:
    """Test getting a nonexistent template."""
    result = await template_storage.get_template("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_templates(template_storage: TemplateStorage) -> None:
    """Test listing all templates."""
    # Create multiple templates
    for i in range(3):
        await template_storage.create_template(
            CreateTemplateRequest(
                name=f"Template {i}",
                description=f"Description {i}",
            )
        )

    templates = await template_storage.list_templates()

    assert len(templates) == 3


@pytest.mark.asyncio
async def test_delete_template(template_storage: TemplateStorage) -> None:
    """Test deleting a template."""
    created = await template_storage.create_template(
        CreateTemplateRequest(
            name="To Delete",
            description="This will be deleted",
        )
    )

    deleted = await template_storage.delete_template(created.id)
    assert deleted is True

    # Verify it's gone
    result = await template_storage.get_template(created.id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent_template(template_storage: TemplateStorage) -> None:
    """Test deleting a nonexistent template."""
    deleted = await template_storage.delete_template("nonexistent-id")
    assert deleted is False


@pytest.mark.asyncio
async def test_create_from_template(
    template_storage: TemplateStorage, workstream_storage: WorkstreamStorage
) -> None:
    """Test creating a workstream from a template."""
    # Create a template
    template = await template_storage.create_template(
        CreateTemplateRequest(
            name="API Project",
            description="Template for API projects",
            default_tags=["api", "backend"],
            default_metadata={"connectionInfo": "localhost:8080"},
            note_templates=["SETUP: Check README for installation"],
        )
    )

    # Create workstream from template
    request = InstantiateTemplateRequest(
        template_id=template.id,
        name="My API Project",
        summary="My new API project",
    )
    workstream = await template_storage.create_from_template(request, workstream_storage)

    assert workstream is not None
    assert workstream.name == "My API Project"
    assert workstream.summary == "My new API project"
    assert "api" in workstream.tags
    assert "backend" in workstream.tags
    assert workstream.metadata.connection_info == "localhost:8080"
    assert len(workstream.notes) == 1
    assert "SETUP" in workstream.notes[0]


@pytest.mark.asyncio
async def test_create_from_template_with_overrides(
    template_storage: TemplateStorage, workstream_storage: WorkstreamStorage
) -> None:
    """Test creating a workstream from a template with overrides."""
    # Create a template
    template = await template_storage.create_template(
        CreateTemplateRequest(
            name="Service Template",
            description="Template for services",
            default_tags=["service"],
            default_metadata={"testingInfo": "make test"},
        )
    )

    # Create workstream with overrides
    request = InstantiateTemplateRequest(
        template_id=template.id,
        name="User Service",
        summary="User management service",
        additional_tags=["user", "auth"],
        metadata_overrides={"testingInfo": "npm test", "connectionInfo": "localhost:3000"},
    )
    workstream = await template_storage.create_from_template(request, workstream_storage)

    assert workstream is not None
    assert "service" in workstream.tags  # From template
    assert "user" in workstream.tags  # Additional
    assert "auth" in workstream.tags  # Additional
    # Override wins
    assert workstream.metadata.testing_info == "npm test"
    # New field added
    assert workstream.metadata.connection_info == "localhost:3000"


@pytest.mark.asyncio
async def test_create_from_nonexistent_template(
    template_storage: TemplateStorage, workstream_storage: WorkstreamStorage
) -> None:
    """Test creating a workstream from a nonexistent template."""
    request = InstantiateTemplateRequest(
        template_id="nonexistent-template-id",
        name="Test Workstream",
        summary="Test summary",
    )
    workstream = await template_storage.create_from_template(request, workstream_storage)

    assert workstream is None


@pytest.mark.asyncio
async def test_template_persistence(tmp_path: Path) -> None:
    """Test that templates persist across storage instances."""
    data_dir = str(tmp_path / "data")

    # Create first instance and add template
    storage1 = TemplateStorage(data_dir)
    await storage1.initialize()
    await storage1.create_template(
        CreateTemplateRequest(
            name="Persistent Template",
            description="This should persist",
        )
    )

    # Create second instance and verify template
    storage2 = TemplateStorage(data_dir)
    await storage2.initialize()

    templates = await storage2.list_templates()
    assert len(templates) == 1
    assert templates[0].name == "Persistent Template"


@pytest.mark.asyncio
async def test_template_to_dict() -> None:
    """Test template serialization to dict."""
    template = WorkstreamTemplate(
        id="tmpl-123",
        name="Test Template",
        description="Test description",
        default_tags=["tag1", "tag2"],
        default_metadata={"key": "value"},
        note_templates=["Note 1"],
    )

    data = template.to_dict()

    assert data["id"] == "tmpl-123"
    assert data["name"] == "Test Template"
    assert data["description"] == "Test description"
    assert data["defaultTags"] == ["tag1", "tag2"]
    assert data["defaultMetadata"] == {"key": "value"}
    assert data["noteTemplates"] == ["Note 1"]


@pytest.mark.asyncio
async def test_template_from_dict() -> None:
    """Test template deserialization from dict."""
    data = {
        "id": "tmpl-456",
        "name": "From Dict",
        "description": "Created from dict",
        "defaultTags": ["a", "b"],
        "defaultMetadata": {"foo": "bar"},
        "noteTemplates": ["Initial note"],
        "createdAt": "2024-01-01T00:00:00",
        "updatedAt": "2024-01-02T00:00:00",
    }

    template = WorkstreamTemplate.from_dict(data)

    assert template.id == "tmpl-456"
    assert template.name == "From Dict"
    assert template.description == "Created from dict"
    assert template.default_tags == ["a", "b"]
    assert template.default_metadata == {"foo": "bar"}
    assert template.note_templates == ["Initial note"]
    assert template.created_at == "2024-01-01T00:00:00"
    assert template.updated_at == "2024-01-02T00:00:00"


@pytest.mark.asyncio
async def test_create_from_template_with_parent(
    template_storage: TemplateStorage, workstream_storage: WorkstreamStorage
) -> None:
    """Test creating a workstream from a template with a parent."""
    # Create parent workstream
    from src.types import CreateWorkstreamRequest

    parent = await workstream_storage.create(
        CreateWorkstreamRequest(name="Parent Project", summary="Parent")
    )

    # Create template
    template = await template_storage.create_template(
        CreateTemplateRequest(
            name="Child Template",
            description="Template for child workstreams",
        )
    )

    # Create workstream with parent
    request = InstantiateTemplateRequest(
        template_id=template.id,
        name="Child Workstream",
        summary="A child workstream",
        parent_id=parent.id,
    )
    workstream = await template_storage.create_from_template(request, workstream_storage)

    assert workstream is not None
    assert workstream.parent_id == parent.id
