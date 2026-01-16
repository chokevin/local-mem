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
3. Push branch and notify user to review/merge
4. After merge, checkout `main` and pull latest

```bash
# Create branch
git checkout -b kecho/feature-name

# Commit
git add .
git commit -m "Short description

- Detail 1
- Detail 2"

# Push
git push -u origin kecho/feature-name

# After merge
git checkout main && git pull origin main
```

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
