# Agent Guidelines

Instructions for AI agents working on this codebase.

## Git Workflow

### Branch Naming
Always create branches with the prefix `kecho/` followed by a short descriptive name:

```
kecho/<short_name_of_feature>
```

Examples:
- `kecho/python-rewrite`
- `kecho/add-profile-support`
- `kecho/fix-sse-updates`
- `kecho/ui-improvements`

### Workflow
1. Create a new branch from `main`
2. Make changes and commit with descriptive messages
3. Push branch and create PR with description
4. Notify user to review/merge
5. After merge, checkout `main` and pull latest

```bash
# Create branch
git checkout -b kecho/feature-name

# Commit
git add .
git commit -m "Short description

- Detail 1
- Detail 2"

# Push and create PR with description
git push -u origin kecho/feature-name
gh pr create --title "Short title" --body "## Summary
Brief description of changes

## Changes
- Change 1
- Change 2

## Testing
How it was tested"

# After merge
git checkout main && git pull origin main
```

### Pull Request Requirements
Always include a PR description with:
- **Summary**: Brief description of what the PR does
- **Changes**: Bullet list of specific changes made
- **Testing**: How the changes were tested

### Testing Web UI Changes
Before committing web UI changes, use the browser preview to verify:

```bash
# Open the dashboard in VS Code's Simple Browser
# Use open_simple_browser tool with these URLs:

http://localhost:8080              # Default profile (test)
http://localhost:8080/?profile=prod  # Prod profile
http://localhost:8080/?profile=test  # Explicit test profile
```

Test checklist for web UI:
1. Open default URL - verify data loads (not stuck on "Connecting...")
2. Switch to prod profile - verify data loads
3. Switch back to test profile - verify data loads (regression check)
4. Check cookie persistence - reopen URL without `?profile=` param
5. Verify SSE updates - create/update a workstream via CLI, confirm UI updates live

## Development

### Setup
```bash
make setup  # Creates venv and installs deps with uv
```

### Testing
```bash
make test      # Run all tests
make test-v    # Verbose output
make test-cov  # With coverage
```

### Running
```bash
make ui                    # Start web dashboard (http://localhost:8080)
make run                   # Start MCP server
make cli ARGS="list"       # Use CLI
make cli ARGS="list" PROFILE=prod  # Use prod profile
```

## Profiles
- `test` (default) - For development/testing
- `prod` - For production data

Data files: `data/workstreams.{profile}.json`
