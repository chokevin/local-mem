#!/bin/bash
# List active beads and their worktrees

REPO_ROOT=$(git rev-parse --show-toplevel)

echo "=== Active Beads ==="
bd list 2>/dev/null || echo "(no open beads)"

echo ""
echo "=== Worktrees ==="
git worktree list

echo ""
echo "=== Bead Worktrees ==="
if [ -d "$REPO_ROOT/.worktrees" ]; then
    for dir in "$REPO_ROOT/.worktrees"/*/; do
        if [ -d "$dir" ]; then
            BEAD_ID=$(basename "$dir")
            BRANCH=$(cd "$dir" && git branch --show-current 2>/dev/null || echo "unknown")
            echo "  $BEAD_ID -> $BRANCH"
        fi
    done
else
    echo "  (none)"
fi
