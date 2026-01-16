# VS Code Integration Guide

This guide walks you through setting up local-mem as an MCP server in VS Code.

## Prerequisites

- VS Code installed
- Claude Dev extension (or another MCP-compatible extension)
- Node.js (v16 or later)

## Setup Steps

### 1. Build the Project

First, ensure the project is built:

```bash
cd /path/to/local-mem
npm install
npm run build
```

### 2. Find Your MCP Settings File

The location of your MCP settings file depends on your operating system:

**macOS:**
```
~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json
```

**Windows:**
```
%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json
```

**Linux:**
```
~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json
```

### 3. Add local-mem Configuration

Edit the MCP settings file and add the local-mem server configuration:

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

**Important:** Replace `/absolute/path/to/local-mem` with the actual absolute path to your local-mem directory.

**Example (macOS/Linux):**
```json
{
  "mcpServers": {
    "local-mem": {
      "command": "node",
      "args": [
        "/Users/yourusername/projects/local-mem/dist/index.js"
      ]
    }
  }
}
```

**Example (Windows):**
```json
{
  "mcpServers": {
    "local-mem": {
      "command": "node",
      "args": [
        "C:\\Users\\yourusername\\projects\\local-mem\\dist\\index.js"
      ]
    }
  }
}
```

### 4. Restart VS Code

After saving the configuration, restart VS Code or reload the MCP servers through the Claude Dev extension.

### 5. Verify Installation

Open Claude Dev in VS Code and check that the local-mem server is connected. You should see it listed in the available MCP servers.

## Using local-mem in VS Code

Once configured, you can use local-mem through Claude Dev (or your MCP client) by calling the available tools:

### Example Conversation

**You:** "Create a new workstream for my API project"

**Claude (via local-mem):** Uses `create_workstream` tool to create a new workstream.

**You:** "List all my workstreams tagged with 'backend'"

**Claude (via local-mem):** Uses `search_by_tags` tool to find matching workstreams.

**You:** "What are the connection details for my API project?"

**Claude (via local-mem):** Uses `get_workstream` or `search_workstreams` to retrieve the information.

## Available Tools in VS Code

When the server is running, Claude can use these tools:

1. **create_workstream** - Create new work segments
2. **list_workstreams** - List all workstreams
3. **get_workstream** - Get details of a specific workstream
4. **update_workstream** - Update existing workstreams
5. **delete_workstream** - Remove workstreams
6. **add_tags** - Add tags to workstreams
7. **search_by_tags** - Search by tags
8. **search_workstreams** - Search by text

## Troubleshooting

### Server Not Showing Up

1. Check that the path in the configuration is correct and absolute
2. Ensure the project is built (`npm run build`)
3. Check VS Code's output panel for errors
4. Restart VS Code completely

### Permission Errors

Make sure the dist/index.js file is readable:
```bash
chmod +x /path/to/local-mem/dist/index.js
```

### Path Issues on Windows

Use forward slashes or escaped backslashes in the JSON configuration:
- `C:/Users/...` or
- `C:\\Users\\...`

### Server Crashes

Check the server logs and ensure:
1. Node.js is installed and accessible
2. All dependencies are installed (`npm install`)
3. The data directory has write permissions

## Data Location

Workstreams are stored in:
```
/path/to/local-mem/data/workstreams.json
```

You can back up this file to preserve your workstream data.

## Updating local-mem

When you update the code:

1. Pull latest changes
2. Rebuild: `npm run build`
3. Restart VS Code or reload MCP servers

No need to modify the VS Code configuration unless the installation path changes.

## Alternative: Using npm link (Advanced)

For development, you can use `npm link`:

1. In local-mem directory:
```bash
npm link
```

2. Update VS Code configuration to:
```json
{
  "mcpServers": {
    "local-mem": {
      "command": "local-mem"
    }
  }
}
```

This makes the `local-mem` command available globally.
