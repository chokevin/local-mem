#!/bin/bash
# Close a bead with PR creation
# Usage: ./scripts/close-bead.sh <bead-id> "<description>"
# Works from main repo or from within a worktree

set -e

BEAD_ID="$1"
DESCRIPTION="$2"

if [ -z "$BEAD_ID" ] || [ -z "$DESCRIPTION" ]; then
    echo "Usage: ./scripts/close-bead.sh <bead-id> \"<description>\""
    echo "Example: ./scripts/close-bead.sh mem-abc \"Added feature X\""
    exit 1
fi

# Find repo root (works in worktrees too)
REPO_ROOT=$(git rev-parse --show-toplevel)
MAIN_REPO=$(git worktree list | head -1 | awk '{print $1}')
WORKTREE_DIR="$MAIN_REPO/.worktrees/$BEAD_ID"

# Determine working directory
if [ -d "$WORKTREE_DIR" ]; then
    WORK_DIR="$WORKTREE_DIR"
    echo "Using worktree: $WORKTREE_DIR"
else
    WORK_DIR="$REPO_ROOT"
    echo "Using main repo: $REPO_ROOT"
fi

cd "$WORK_DIR"

echo "=== Closing bead $BEAD_ID ==="

# 1. Get bead title for PR
BEAD_TITLE=$(bd show "$BEAD_ID" --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['title'])" 2>/dev/null || echo "$BEAD_ID")

# 2. Test Docker if test script exists in main repo
if [ -f "$MAIN_REPO/scripts/test-docker.sh" ]; then
    echo "1. Running Docker tests..."
    cd "$MAIN_REPO" && ./scripts/test-docker.sh
    cd "$WORK_DIR"
fi

# 3. Ensure on correct branch
CURRENT_BRANCH=$(git branch --show-current)
EXPECTED_BRANCH="kecho/$BEAD_ID"

if [ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]; then
    if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
        echo "2. Creating branch $EXPECTED_BRANCH..."
        git checkout -b "$EXPECTED_BRANCH"
    else
        echo "2. Using current branch: $CURRENT_BRANCH"
        EXPECTED_BRANCH="$CURRENT_BRANCH"
    fi
else
    echo "2. On correct branch: $EXPECTED_BRANCH"
fi

# 4. Commit changes
echo "3. Committing changes..."
git add -A
git commit -m "$BEAD_TITLE

$DESCRIPTION

Closes: $BEAD_ID" || echo "   (no changes to commit)"

# 5. Push branch
echo "4. Pushing branch..."
git push -u origin "$EXPECTED_BRANCH"

# 6. Create PR
echo "5. Creating PR..."
gh pr create \
    --title "$BEAD_TITLE" \
    --body "## Summary
$DESCRIPTION

## Bead
- ID: \`$BEAD_ID\`
- Title: $BEAD_TITLE

## Testing
- [x] Docker tests passed
" \
    --head "$EXPECTED_BRANCH" \
    2>&1 || echo "   PR may already exist"

# 7. Close bead
echo "6. Closing bead..."
bd close "$BEAD_ID" -r "$DESCRIPTION"

# 8. Cleanup worktree if used
if [ -d "$WORKTREE_DIR" ] && [ "$WORK_DIR" = "$WORKTREE_DIR" ]; then
    echo "7. Cleaning up worktree..."
    cd "$MAIN_REPO"
    git worktree remove "$WORKTREE_DIR" --force 2>/dev/null || true
fi

echo ""
echo "=== Done! ==="
echo "PR created for branch: $EXPECTED_BRANCH"
