# local-mem (Python)

A local MCP (Model Context Protocol) server for organizing work into segments (workstreams) with tagging, summaries, and metadata. Easily attach to your VS Code session to manage and reference your work.

## 🚀 Quick Start

### Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"
```

### Running the Server

```bash
# Run the MCP server
python -m src.server

# Or use the installed command
local-mem
```

### Using the CLI

```bash
# List all workstreams
python -m src.cli list

# Search by name or summary
python -m src.cli search "API project"

# Search by tags
python -m src.cli tags backend python

# Get a specific workstream
python -m src.cli get ws-1234567890-abc123

# Show help
python -m src.cli help
```

## 🧪 Testing

```bash
# Run all tests
make test

# Run tests with coverage
make test-cov

# Run specific test file
pytest tests/test_storage.py -v

# Run specific test
pytest tests/test_storage.py::test_create_workstream -v
```

## 📁 Project Structure

```
local-mem/
├── src/
│   ├── __init__.py      # Package exports
│   ├── types.py         # Data models (Workstream, etc.)
│   ├── storage.py       # File-based storage
│   ├── server.py        # MCP server implementation
│   └── cli.py           # CLI utility
├── tests/
│   ├── __init__.py
│   ├── test_types.py    # Unit tests for types
│   ├── test_storage.py  # Unit tests for storage
│   └── test_server.py   # Integration tests for server
├── pyproject.toml       # Project configuration
├── Makefile             # Development commands
└── README_PYTHON.md     # This file
```

## 🔧 Development Commands

```bash
make help        # Show all commands
make dev         # Install dev dependencies
make test        # Run tests
make test-cov    # Run tests with coverage
make lint        # Check code style
make format      # Format code
make typecheck   # Run type checker
make check       # Run all checks
make clean       # Clean build artifacts
```

## 🔌 VS Code Integration

Add to your MCP settings (e.g., Claude Dev settings):

```json
{
  "mcpServers": {
    "local-mem": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/absolute/path/to/local-mem"
    }
  }
}
```

Or if you have the package installed:

```json
{
  "mcpServers": {
    "local-mem": {
      "command": "local-mem"
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `create_workstream` | Create a new workstream with name, summary, tags, and metadata |
| `list_workstreams` | List all workstreams |
| `get_workstream` | Get a workstream by ID |
| `update_workstream` | Update an existing workstream |
| `delete_workstream` | Delete a workstream |
| `add_tags` | Add tags to an existing workstream |
| `search_by_tags` | Search workstreams by tags |
| `search_workstreams` | Search by name or summary text |

## Data Storage

Workstreams are stored in `./data/workstreams.json`. This file is automatically created when you first create a workstream.
