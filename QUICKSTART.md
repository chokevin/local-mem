# Quick Start Guide

Get started with local-mem in 5 minutes!

## Step 1: Install and Build (2 minutes)

```bash
# Clone and navigate
git clone https://github.com/chokevin/local-mem.git
cd local-mem

# Install dependencies and build
npm install
npm run build
```

## Step 2: Try the CLI (1 minute)

```bash
# Create your first workstream
node dist/cli.js help

# View what's in there (from our tests)
node dist/cli.js list
```

## Step 3: Set Up in VS Code (2 minutes)

1. **Find your MCP settings file:**
   - **macOS**: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
   - **Windows**: `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`
   - **Linux**: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

2. **Add this configuration** (replace `/path/to/local-mem` with your actual path):

```json
{
  "mcpServers": {
    "local-mem": {
      "command": "node",
      "args": ["/path/to/local-mem/dist/index.js"]
    }
  }
}
```

3. **Restart VS Code**

## Step 4: Start Using It!

### In VS Code with Claude Dev

**Example 1: Create a workstream**
```
You: "Create a workstream for my new API project. It's a Node.js REST API for user management. Tag it with 'backend', 'api', and 'nodejs'. The API runs on localhost:3000 and can be tested with npm test."
```

Claude will use the `create_workstream` tool and store all that information for you!

**Example 2: Find your workstreams**
```
You: "What backend projects am I working on?"
```

Claude will use `search_by_tags` with the "backend" tag to show you all your backend workstreams.

**Example 3: Get connection details**
```
You: "How do I connect to my API project?"
```

Claude will retrieve the workstream and show you the connection info!

### Using the CLI

```bash
# List everything
node dist/cli.js list

# Search for specific projects
node dist/cli.js search "API"

# Find by tags
node dist/cli.js tags backend nodejs

# Get details of a specific workstream
node dist/cli.js get ws-1234567890-abc123
```

## Real-World Example

Let's create a complete workstream for a web application:

### Via VS Code/Claude:

```
You: "Create a workstream called 'Customer Dashboard' for our React admin dashboard. 
Summary: 'Admin dashboard for customer management built with React and Material-UI'. 
Tag it with: frontend, react, dashboard, production.
Add metadata:
- Host IPs: localhost:3000, staging.example.com
- Connection: npm run dev for local, ssh deploy@staging.example.com for server
- Testing: npm test && npm run e2e
- Deployment URL: https://staging.example.com/admin
- Figma: https://figma.com/file/abc123"
```

Claude will create a perfectly structured workstream with all this information!

### Later, when you need it:

```
You: "Show me the Customer Dashboard workstream"
```

Claude retrieves it instantly with all your notes, connection details, and testing commands!

## What's Next?

- Read [EXAMPLES.md](EXAMPLES.md) for more detailed usage examples
- Check [VSCODE_SETUP.md](VSCODE_SETUP.md) for troubleshooting VS Code integration
- Review [README.md](README.md) for complete API documentation

## Tips for Success

1. **Be descriptive**: Use clear names and detailed summaries
2. **Tag consistently**: Develop a tagging system (e.g., `frontend`, `backend`, `ml`, `production`)
3. **Update metadata**: Keep connection details and testing info current
4. **Use custom fields**: Add any metadata that helps you (e.g., `slackChannel`, `oncall`, `runbook`)

## Common Use Cases

- **Organizing multiple microservices**: Track each service with its connection details
- **Managing dev/staging/prod environments**: Separate workstreams for each environment
- **Context switching**: Quickly recall how to run and test any project
- **Team knowledge**: Share connection details and testing procedures
- **Bug tracking**: Create workstreams for ongoing investigations

---

You're all set! Start organizing your work and never forget how to connect to your projects again. 🚀
