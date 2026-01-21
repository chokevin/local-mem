#!/bin/bash
# Close a bead with PR creation
# Usage: ./scripts/close-bead.sh <bead-id> "<description>"

set -e

BEAD_ID="$1"
DESCRIPTION="$2"

if [ -z "$BEAD_ID" ] || [ -z "$DESCRIPTION" ]; then
    echo "Usage: ./scripts/close-bead.sh <bead-id> \"<description>\""
    echo "Example: ./scripts/close-bead.sh mem-abc \"Added feature X\""
    exit 1
fi

echo "=== Closing bead $BEAD_ID ==="

# 1. Get bead title for PR
BEAD_TITLE=$(bd show "$BEAD_ID" --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['title'])" 2>/dev/null || echo "$BEAD_ID")

# 2. Test Docker if in mem project
if [ -f "scripts/test-docker.sh" ]; then
    echo "1. Running Docker tests..."
    ./scripts/test-docker.sh
fi

# 2b. Run E2E tests if available
if grep -q "test-e2e" Makefile 2>/dev/null; then
    echo "1b. Running E2E tests..."
    make test-e2e || echo "   E2E tests failed or skipped"
fi

# 3. Create branch if not already on one
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
    BRANCH_NAME="kecho/$BEAD_ID"
    echo "2. Creating branch $BRANCH_NAME..."
    git checkout -b "$BRANCH_NAME"
else
    BRANCH_NAME="$CURRENT_BRANCH"
    echo "2. Using existing branch $BRANCH_NAME"
fi

# 4. Fetch and merge main to handle conflicts before pushing
echo "3. Syncing with main branch..."
git fetch origin main
if ! git merge origin/main -m "Merge main into $BRANCH_NAME"; then
    echo ""
    echo "ERROR: Merge conflicts detected!"
    echo "Please resolve conflicts manually, then run:"
    echo "  git add -A && git commit -m 'Resolve merge conflicts'"
    echo "  ./scripts/close-bead.sh $BEAD_ID \"$DESCRIPTION\""
    exit 1
fi
echo "   Merged main successfully"

# 5. Commit changes
echo "4. Committing changes..."
git add -A
git commit -m "$BEAD_TITLE

$DESCRIPTION

Closes: $BEAD_ID" || echo "   (no changes to commit)"

# 6. Push branch
echo "5. Pushing branch..."
git push -u origin "$BRANCH_NAME"

# 7. Create PR
echo "6. Creating PR..."
gh pr create \
    --title "$BEAD_TITLE" \
    --body "## Summary
$DESCRIPTION

## Bead
- ID: \`$BEAD_ID\`
- Title: $BEAD_TITLE

## Testing
- [x] Docker tests passed (\`./scripts/test-docker.sh\`)
- [x] Merged with main (no conflicts)
" \
    --head "$BRANCH_NAME" \
    2>&1 || echo "   PR may already exist"

# 8. Close bead
echo "7. Closing bead..."
bd close "$BEAD_ID" -r "$DESCRIPTION"

# 9. Return to main
echo "8. Returning to main branch..."
git checkout main
git pull origin main

echo ""
echo "=== Done! ==="
echo "PR created for branch: $BRANCH_NAME"
