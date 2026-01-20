#!/bin/bash
# List active beads, worktrees, and related PRs

REPO_ROOT=$(git rev-parse --show-toplevel)

echo "=== Open Beads ==="
bd list 2>/dev/null || echo "(no open beads)"

echo ""
echo "=== Closed Beads (recent) ==="
bd list --status closed 2>/dev/null | head -10 || echo "(none)"

echo ""
echo "=== Active Worktrees ==="
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

echo ""
echo "=== Recent PRs ==="
gh pr list --state all --limit 5 --json number,title,state,headRefName \
    --template '{{range .}}  #{{.number}} [{{.state}}] {{.title}} ({{.headRefName}}){{"\n"}}{{end}}' 2>/dev/null || echo "  (gh cli not available)"
