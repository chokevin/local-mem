# local-mem

A local MCP (Model Context Protocol) server for organizing work into segments (workstreams) with tagging, summaries, and metadata. Easily attach to your VS Code session to manage and reference your work.

## Features

- 📁 **Workstream Management**: Create, update, delete, and list work segments
- 🏷️ **Tagging System**: Organize workstreams with tags for easy categorization
- 🔍 **Search & Filter**: Find workstreams by tags, name, or summary
- 📋 **Rich Metadata**: Store key information like host IPs, connection info, and testing procedures
- 💾 **Persistent Storage**: File-based storage for your workstreams
- 🔌 **VS Code Integration**: Works as an MCP server in VS Code

## Installation

1. Clone the repository:
```bash
git clone https://github.com/chokevin/local-mem.git
cd local-mem
```

2. Install dependencies:
```bash
npm install
```

3. Build the project:
```bash
npm run build
```

## Usage

### CLI Utility

After building, you can use the CLI to quickly view and search workstreams:

```bash
# List all workstreams
node dist/cli.js list

# Search by name or summary
node dist/cli.js search "API project"

# Search by tags
node dist/cli.js tags backend nodejs

# Get a specific workstream
node dist/cli.js get ws-1234567890-abc123

# Show help
node dist/cli.js help
```

For convenience, you can create an alias in your shell:
```bash
alias local-mem-cli="node /path/to/local-mem/dist/cli.js"
```

### As a Standalone Server

Run the server in development mode:
```bash
npm run dev
```

Or run the built version:
```bash
npm start
```

### VS Code Integration

1. Build the project first:
```bash
npm run build
```

2. Add the server to your VS Code MCP settings. The location depends on your OS:
   - **macOS**: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
   - **Windows**: `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`
   - **Linux**: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

3. Add the following configuration (replace with your absolute path):
```json
{
  "mcpServers": {
    "local-mem": {
      "command": "node",
      "args": [
        "/absolute/path/to/local-mem/dist/index.js"
      ]
    }
  }
}
```

4. Restart VS Code or reload the MCP servers.

## Available Tools

### create_workstream
Create a new workstream with name, summary, tags, and metadata.

**Parameters:**
- `name` (string, required): Name of the workstream
- `summary` (string, required): Description of the workstream
- `tags` (array, optional): Tags for categorization
- `metadata` (object, optional): Additional metadata
  - `hostIps`: Array of host IP addresses
  - `connectionInfo`: Connection instructions
  - `testingInfo`: Testing procedures
  - Any custom fields

**Example:**
```json
{
  "name": "API Migration Project",
  "summary": "Migrating legacy API to new microservices architecture",
  "tags": ["backend", "migration", "api"],
  "metadata": {
    "hostIps": ["192.168.1.100", "10.0.0.50"],
    "connectionInfo": "ssh user@192.168.1.100 -p 2222",
    "testingInfo": "Run: npm test && npm run integration-test"
  }
}
```

### list_workstreams
List all workstreams with their details.

### get_workstream
Get detailed information about a specific workstream by ID.

**Parameters:**
- `id` (string, required): Workstream ID

### update_workstream
Update an existing workstream.

**Parameters:**
- `id` (string, required): Workstream ID
- `name` (string, optional): New name
- `summary` (string, optional): New summary
- `tags` (array, optional): New tags (replaces existing)
- `metadata` (object, optional): Metadata to merge

### delete_workstream
Delete a workstream by ID.

**Parameters:**
- `id` (string, required): Workstream ID

### add_tags
Add tags to an existing workstream without replacing existing tags.

**Parameters:**
- `id` (string, required): Workstream ID
- `tags` (array, required): Tags to add

### search_by_tags
Search workstreams by tags.

**Parameters:**
- `tags` (array, required): Tags to search for
- `matchAll` (boolean, optional): If true, match all tags; if false, match any tag (default: false)

### search_workstreams
Search workstreams by name or summary text.

**Parameters:**
- `query` (string, required): Search query

## Data Storage

Workstreams are stored in `./data/workstreams.json`. This file is automatically created when you first create a workstream.

## Example Workflow

1. **Create a workstream for a new project:**
```
Tool: create_workstream
{
  "name": "Frontend Dashboard Redesign",
  "summary": "Redesigning the admin dashboard with React and Tailwind",
  "tags": ["frontend", "react", "design"],
  "metadata": {
    "hostIps": ["localhost:3000"],
    "connectionInfo": "npm run dev",
    "testingInfo": "npm test -- --coverage"
  }
}
```

2. **List all workstreams:**
```
Tool: list_workstreams
```

3. **Search by tags:**
```
Tool: search_by_tags
{
  "tags": ["frontend", "react"]
}
```

4. **Update with new information:**
```
Tool: update_workstream
{
  "id": "ws-1234567890-abc123",
  "metadata": {
    "deploymentUrl": "https://staging.example.com"
  }
}
```

5. **Add more tags:**
```
Tool: add_tags
{
  "id": "ws-1234567890-abc123",
  "tags": ["tailwind", "responsive"]
}
```

## Development

- `npm run dev`: Run in development mode with auto-reload
- `npm run build`: Build TypeScript to JavaScript
- `npm start`: Run the built version

## License

ISC
