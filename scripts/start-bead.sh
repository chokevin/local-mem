#!/bin/bash
# Start a new bead with its own git worktree
# Usage: ./scripts/start-bead.sh "<title>" [priority]

set -e

TITLE="$1"
PRIORITY="${2:-2}"

if [ -z "$TITLE" ]; then
    echo "Usage: ./scripts/start-bead.sh \"<title>\" [priority]"
    echo "Example: ./scripts/start-bead.sh \"Add user authentication\" 1"
    exit 1
fi

# Ensure we're in repo root
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

# Create bead
echo "Creating bead..."
BEAD_OUTPUT=$(bd create --title "$TITLE" --priority "$PRIORITY" --json)
BEAD_ID=$(echo "$BEAD_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "✓ Created bead: $BEAD_ID"

# Create worktree directory
WORKTREE_DIR="$REPO_ROOT/.worktrees/$BEAD_ID"
BRANCH_NAME="kecho/$BEAD_ID"

# Fetch latest main
git fetch origin main

# Create worktree with new branch from main
echo "Creating worktree at $WORKTREE_DIR..."
mkdir -p "$REPO_ROOT/.worktrees"
git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR" origin/main

echo ""
echo "=== Bead started ==="
echo "  Bead ID:    $BEAD_ID"
echo "  Title:      $TITLE"
echo "  Branch:     $BRANCH_NAME"
echo "  Worktree:   $WORKTREE_DIR"
echo ""
echo "To work on this bead:"
echo "  cd $WORKTREE_DIR"
echo ""
echo "When done:"
echo "  ./scripts/close-bead.sh $BEAD_ID \"<description>\""
