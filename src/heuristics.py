"""
Heuristics for detecting relationships between workstreams.

Relationship detection patterns:
1. Tag overlap - Projects sharing tags are likely related
2. Name containment - "Jupiter - Networking" suggests Jupiter is parent
3. Summary similarity - Keyword overlap in descriptions
4. Metadata overlap - Same regions, repos, components
5. Cross-references - Mentions of other project names/IDs in notes
6. Program tags - Tags like "program", "initiative" suggest parent role
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .types import RelationshipSuggestion, Workstream


# Tags that indicate a workstream is likely a parent/program
PROGRAM_TAGS = {"program", "initiative", "project", "portfolio", "epic", "parent"}

# Minimum thresholds for suggestions
MIN_TAG_OVERLAP = 2  # At least 2 shared tags to suggest "related"
MIN_CONFIDENCE = 0.3  # Don't suggest below this confidence


@dataclass
class HeuristicResult:
    """Result from a single heuristic check."""

    confidence: float
    reason: str


def _tag_overlap_heuristic(ws1: Workstream, ws2: Workstream) -> Optional[HeuristicResult]:
    """Check for tag overlap between workstreams."""
    if not ws1.tags or not ws2.tags:
        return None

    shared_tags = set(ws1.tags) & set(ws2.tags)
    # Exclude program tags from overlap count for "related" detection
    shared_non_program = shared_tags - PROGRAM_TAGS

    if len(shared_non_program) >= MIN_TAG_OVERLAP:
        confidence = min(0.8, 0.3 + (len(shared_non_program) * 0.15))
        return HeuristicResult(
            confidence=confidence,
            reason=f"Share {len(shared_non_program)} tags: {', '.join(sorted(shared_non_program))}",
        )
    return None


def _name_containment_heuristic(
    potential_parent: Workstream, potential_child: Workstream
) -> Optional[HeuristicResult]:
    """Check if parent name appears in child name (suggests hierarchy)."""
    parent_name = potential_parent.name.lower().strip()
    child_name = potential_child.name.lower().strip()

    # Skip if names are too similar (probably same project)
    if parent_name == child_name:
        return None

    # Check if parent name appears in child name
    # e.g., "Jupiter" in "Jupiter - Networking" or "Jupiter Networking"
    if parent_name in child_name:
        confidence = 0.7
        return HeuristicResult(
            confidence=confidence,
            reason=f"Child name contains parent name '{potential_parent.name}'",
        )

    # Check for prefix pattern: "Parent: Child" or "Parent - Child"
    patterns = [
        rf"^{re.escape(parent_name)}\s*[-:]\s*",  # "Jupiter - " or "Jupiter: "
        rf"^{re.escape(parent_name)}\s+",  # "Jupiter Networking"
    ]
    for pattern in patterns:
        if re.match(pattern, child_name, re.IGNORECASE):
            return HeuristicResult(
                confidence=0.75,
                reason=f"Child name prefixed with parent name '{potential_parent.name}'",
            )

    return None


def _program_tag_heuristic(ws: Workstream) -> bool:
    """Check if workstream has program-indicating tags."""
    return bool(set(ws.tags) & PROGRAM_TAGS)


def _summary_similarity_heuristic(
    ws1: Workstream, ws2: Workstream
) -> Optional[HeuristicResult]:
    """Check for keyword overlap in summaries."""
    # Simple keyword extraction (words > 4 chars, lowercase)
    def extract_keywords(text: str) -> set[str]:
        words = re.findall(r"\b[a-zA-Z]{5,}\b", text.lower())
        # Filter common words
        stopwords = {
            "about",
            "after",
            "being",
            "between",
            "could",
            "during",
            "every",
            "first",
            "through",
            "under",
            "using",
            "where",
            "which",
            "while",
            "would",
            "their",
            "there",
            "these",
            "those",
            "should",
            "including",
            "working",
        }
        return set(words) - stopwords

    kw1 = extract_keywords(ws1.summary)
    kw2 = extract_keywords(ws2.summary)

    if not kw1 or not kw2:
        return None

    overlap = kw1 & kw2
    if len(overlap) >= 3:
        # Jaccard similarity
        jaccard = len(overlap) / len(kw1 | kw2)
        confidence = min(0.6, jaccard + 0.2)
        return HeuristicResult(
            confidence=confidence,
            reason=f"Summary keyword overlap: {', '.join(sorted(list(overlap)[:5]))}",
        )
    return None


def _cross_reference_heuristic(
    ws1: Workstream, ws2: Workstream
) -> Optional[HeuristicResult]:
    """Check if one workstream mentions the other in notes."""
    # Check if ws2's name or ID appears in ws1's notes
    ws1_notes_text = " ".join(ws1.notes).lower()
    ws2_notes_text = " ".join(ws2.notes).lower()

    # Check ID references
    if ws2.id in ws1_notes_text:
        return HeuristicResult(
            confidence=0.9,
            reason=f"References workstream ID '{ws2.id}' in notes",
        )
    if ws1.id in ws2_notes_text:
        return HeuristicResult(
            confidence=0.9,
            reason=f"Referenced by workstream in its notes",
        )

    # Check name references (if name is distinctive enough)
    if len(ws2.name) > 5 and ws2.name.lower() in ws1_notes_text:
        return HeuristicResult(
            confidence=0.7,
            reason=f"Mentions '{ws2.name}' in notes",
        )
    if len(ws1.name) > 5 and ws1.name.lower() in ws2_notes_text:
        return HeuristicResult(
            confidence=0.7,
            reason=f"Mentioned by '{ws2.name}' in its notes",
        )

    return None


def _shared_tag_parent_heuristic(
    potential_parent: Workstream, potential_child: Workstream
) -> Optional[HeuristicResult]:
    """
    If parent has a program tag AND child shares that tag, suggest parent relationship.
    e.g., Jupiter (tags: program, jupiter) and Networking (tags: jupiter, networking)
    """
    parent_program_tags = set(potential_parent.tags) & PROGRAM_TAGS
    if not parent_program_tags:
        return None

    # Check if parent's name (lowercased) appears as a tag in child
    parent_name_tag = potential_parent.name.lower().replace(" ", "-")
    parent_name_tag_simple = potential_parent.name.lower().replace(" ", "")

    child_tags_lower = {t.lower() for t in potential_child.tags}

    if (
        parent_name_tag in child_tags_lower
        or parent_name_tag_simple in child_tags_lower
        or potential_parent.name.lower() in child_tags_lower
    ):
        return HeuristicResult(
            confidence=0.85,
            reason=f"Child tagged with parent's name '{potential_parent.name}' and parent has program tag",
        )

    return None


def suggest_relationships(
    workstreams: list[Workstream],
) -> list[RelationshipSuggestion]:
    """
    Analyze workstreams and suggest relationships between them.

    Returns a list of relationship suggestions sorted by confidence.
    """
    suggestions: list[RelationshipSuggestion] = []

    for i, ws1 in enumerate(workstreams):
        for ws2 in workstreams[i + 1 :]:
            # Skip if already explicitly linked
            if ws1.parent_id == ws2.id or ws2.parent_id == ws1.id:
                continue

            # Check parent-child heuristics
            # ws1 as potential parent
            if _program_tag_heuristic(ws1):
                result = _shared_tag_parent_heuristic(ws1, ws2)
                if result and result.confidence >= MIN_CONFIDENCE:
                    suggestions.append(
                        RelationshipSuggestion(
                            source_id=ws2.id,
                            target_id=ws1.id,
                            relationship_type="parent",
                            confidence=result.confidence,
                            reason=result.reason,
                        )
                    )
                    continue  # Don't add duplicate suggestions

                result = _name_containment_heuristic(ws1, ws2)
                if result and result.confidence >= MIN_CONFIDENCE:
                    suggestions.append(
                        RelationshipSuggestion(
                            source_id=ws2.id,
                            target_id=ws1.id,
                            relationship_type="parent",
                            confidence=result.confidence,
                            reason=result.reason,
                        )
                    )
                    continue

            # ws2 as potential parent
            if _program_tag_heuristic(ws2):
                result = _shared_tag_parent_heuristic(ws2, ws1)
                if result and result.confidence >= MIN_CONFIDENCE:
                    suggestions.append(
                        RelationshipSuggestion(
                            source_id=ws1.id,
                            target_id=ws2.id,
                            relationship_type="parent",
                            confidence=result.confidence,
                            reason=result.reason,
                        )
                    )
                    continue

                result = _name_containment_heuristic(ws2, ws1)
                if result and result.confidence >= MIN_CONFIDENCE:
                    suggestions.append(
                        RelationshipSuggestion(
                            source_id=ws1.id,
                            target_id=ws2.id,
                            relationship_type="parent",
                            confidence=result.confidence,
                            reason=result.reason,
                        )
                    )
                    continue

            # Check cross-references (high confidence)
            result = _cross_reference_heuristic(ws1, ws2)
            if result and result.confidence >= MIN_CONFIDENCE:
                suggestions.append(
                    RelationshipSuggestion(
                        source_id=ws1.id,
                        target_id=ws2.id,
                        relationship_type="related",
                        confidence=result.confidence,
                        reason=result.reason,
                    )
                )
                continue

            # Check tag overlap for "related" relationship
            result = _tag_overlap_heuristic(ws1, ws2)
            if result and result.confidence >= MIN_CONFIDENCE:
                suggestions.append(
                    RelationshipSuggestion(
                        source_id=ws1.id,
                        target_id=ws2.id,
                        relationship_type="related",
                        confidence=result.confidence,
                        reason=result.reason,
                    )
                )
                continue

            # Check summary similarity
            result = _summary_similarity_heuristic(ws1, ws2)
            if result and result.confidence >= MIN_CONFIDENCE:
                suggestions.append(
                    RelationshipSuggestion(
                        source_id=ws1.id,
                        target_id=ws2.id,
                        relationship_type="similar",
                        confidence=result.confidence,
                        reason=result.reason,
                    )
                )

    # Sort by confidence descending
    suggestions.sort(key=lambda s: s.confidence, reverse=True)
    return suggestions


def get_children(
    parent_id: str, workstreams: list[Workstream]
) -> list[Workstream]:
    """Get all direct children of a workstream."""
    return [ws for ws in workstreams if ws.parent_id == parent_id]


def get_descendants(
    parent_id: str, workstreams: list[Workstream]
) -> list[Workstream]:
    """Get all descendants (children, grandchildren, etc.) of a workstream."""
    descendants = []
    children = get_children(parent_id, workstreams)
    descendants.extend(children)
    for child in children:
        descendants.extend(get_descendants(child.id, workstreams))
    return descendants


def build_tree(workstreams: list[Workstream]) -> dict:
    """
    Build a tree structure from workstreams.

    Returns a dict with:
    - roots: list of workstreams with no parent
    - children: dict mapping parent_id -> list of children
    """
    children_map: dict[str, list[Workstream]] = {}
    roots: list[Workstream] = []

    for ws in workstreams:
        if ws.parent_id:
            if ws.parent_id not in children_map:
                children_map[ws.parent_id] = []
            children_map[ws.parent_id].append(ws)
        else:
            roots.append(ws)

    return {"roots": roots, "children": children_map}
