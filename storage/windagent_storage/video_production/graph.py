"""
Artifact dependency graph (plan 05 §14.2, gate VP18_ARTIFACT_INVALIDATION_VERIFIED).

An edge records that artifact A was created from input B:

    artifact_id -> depends_on_artifact_id | domain_revision_hash
    dependency_type : GENERATED_FROM | REVISION | REFERENCE | AUDIO_INPUT | CHARACTER_BINDING
    reason

The graph supports inbound/outbound queries so invalidation can be scoped to
the MINIMAL affected set (§14.2, §14.3):

- screenplay revision -> cinematic plan -> shot plan -> prompt/request ->
  frames/references -> clips -> final cut;
- character reference -> ONLY bound/dependent shots and downstream cuts;
- BGM -> audio mix and final cut, NOT visual clips.

Fail-closed:

- unknown node / unknown dependency target raises ValidationError
  (an invalidation or query on a graph that references a node it does not
  know would otherwise be silently wrong);
- a dependency cycle raises ValidationError — a cyclic graph has no
  well-defined minimal invalidation scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from windagent_core.errors.exceptions import ValidationError

GRAPH_SCHEMA_VERSION = "1.0.0"


class ArtifactDependencyType(str, Enum):
    """Typed edges in the artifact dependency graph (§14.2).

    Propagation semantics (§14.3):

    - GENERATED_FROM: artifact is a direct downstream product of another
      artifact (screenplay -> plan -> shot plan -> prompt -> clips -> cut);
    - REVISION: artifact depends on a domain revision hash (its validity
      depends on the revision being unchanged);
    - REFERENCE: artifact references another artifact (e.g. a shot binds a
      character bible asset) — scope to bound dependents only;
    - CHARACTER_BINDING: a shot is bound to a character bible artifact;
      a character change invalidates ONLY these shots and their downstream;
    - AUDIO_INPUT: audio artifact feeds the mix/final cut — a BGM change
      invalidates audio mix + final cut but NEVER visual clips.
    """

    GENERATED_FROM = "GENERATED_FROM"
    REVISION = "REVISION"
    REFERENCE = "REFERENCE"
    CHARACTER_BINDING = "CHARACTER_BINDING"
    AUDIO_INPUT = "AUDIO_INPUT"


@dataclass(frozen=True)
class ArtifactDependencyEdge:
    """One dependency edge: artifact depends on another artifact or revision."""

    artifact_id: str
    depends_on_artifact_id: Optional[str] = None
    domain_revision_hash: Optional[str] = None
    dependency_type: ArtifactDependencyType = ArtifactDependencyType.GENERATED_FROM
    reason: str = ""

    def __post_init__(self) -> None:
        if (self.depends_on_artifact_id is None) == (self.domain_revision_hash is None):
            raise ValidationError(
                "Edge must reference exactly one of depends_on_artifact_id or domain_revision_hash",
                code="WINDAGENT_ERR_VALIDATION",
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "depends_on_artifact_id": self.depends_on_artifact_id,
            "domain_revision_hash": self.domain_revision_hash,
            "dependency_type": self.dependency_type.value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactDependencyEdge":
        return cls(
            artifact_id=data["artifact_id"],
            depends_on_artifact_id=data.get("depends_on_artifact_id"),
            domain_revision_hash=data.get("domain_revision_hash"),
            dependency_type=ArtifactDependencyType(data.get("dependency_type", "GENERATED_FROM")),
            reason=data.get("reason", ""),
        )


class ArtifactDependencyGraph:
    """Deterministic dependency graph over artifact ids + revision hashes.

    Construction validates every edge: an unknown artifact node (either side)
    or a cycle is rejected at add-time so downstream queries are always sound.
    """

    def __init__(self) -> None:
        self._edges: List[ArtifactDependencyEdge] = []
        self._known_nodes: Set[str] = set()

    # -- construction ------------------------------------------------------
    def register_node(self, artifact_id: str) -> None:
        self._known_nodes.add(artifact_id)

    def add_edge(self, edge: ArtifactDependencyEdge) -> None:
        if edge.artifact_id not in self._known_nodes:
            raise ValidationError(
                f"Unknown artifact node {edge.artifact_id!r} in dependency graph",
                code="WINDAGENT_ERR_VALIDATION",
                details={"artifact_id": edge.artifact_id},
            )
        if edge.depends_on_artifact_id is not None and edge.depends_on_artifact_id not in self._known_nodes:
            raise ValidationError(
                f"Dependency target {edge.depends_on_artifact_id!r} is not a known artifact node",
                code="WINDAGENT_ERR_VALIDATION",
                details={"depends_on": edge.depends_on_artifact_id},
            )
        self._edges.append(edge)
        self._assert_acyclic()

    # -- queries -----------------------------------------------------------
    def edges(self) -> List[ArtifactDependencyEdge]:
        return list(self._edges)

    def has_node(self, artifact_id: str) -> bool:
        """Public membership check (fail-closed callers use this, not internals)."""
        return artifact_id in self._known_nodes

    def outbound(self, artifact_id: str) -> List[ArtifactDependencyEdge]:
        """Edges where the given artifact depends on something (its inputs)."""
        return [e for e in self._edges if e.artifact_id == artifact_id]

    def inbound(self, artifact_id: str) -> List[ArtifactDependencyEdge]:
        """Edges where something depends on the given artifact (its dependents)."""
        return [
            e for e in self._edges
            if e.depends_on_artifact_id == artifact_id
        ]

    def inbound_by_type(
        self,
        artifact_id: str,
        dependency_types: Set[ArtifactDependencyType],
    ) -> List[ArtifactDependencyEdge]:
        return [
            e for e in self.inbound(artifact_id)
            if e.dependency_type in dependency_types
        ]

    def transitive_inbound(
        self,
        artifact_id: str,
        dependency_types: Optional[Set[ArtifactDependencyType]] = None,
    ) -> Set[str]:
        """ALL artifacts transitively depending on the given artifact.

        With `dependency_types` set, traversal only follows edges of those
        types — this is how invalidation scopes to the minimal affected set
        (§14.3: BGM never propagates through visual-clip edges).
        """
        affected: Set[str] = set()
        stack: List[str] = [artifact_id]
        while stack:
            current = stack.pop()
            for edge in self.inbound(current):
                if dependency_types is not None and edge.dependency_type not in dependency_types:
                    continue
                if edge.artifact_id in affected:
                    continue
                affected.add(edge.artifact_id)
                stack.append(edge.artifact_id)
        return affected

    def dependent_revision_hashes(self, artifact_id: str) -> List[str]:
        """Revision hashes that downstream artifacts depend on (query aid)."""
        out = set()
        for edge in self.outbound(artifact_id):
            if edge.domain_revision_hash:
                out.add(edge.domain_revision_hash)
        return sorted(out)

    # -- validation ---------------------------------------------------------
    def _assert_acyclic(self) -> None:
        """Reject the graph if it contains any cycle (full DFS over all nodes)."""
        visiting: Set[str] = set()
        done: Set[str] = set()

        def visit(node: str) -> None:
            if node in done:
                return
            if node in visiting:
                raise ValidationError(
                    f"Dependency graph contains a cycle involving {node!r}",
                    code="WINDAGENT_ERR_VALIDATION",
                )
            visiting.add(node)
            for edge in self.outbound(node):
                if edge.depends_on_artifact_id:
                    visit(edge.depends_on_artifact_id)
            visiting.discard(node)
            done.add(node)

        for node in sorted(self._known_nodes):
            visit(node)

    def has_cycle(self) -> bool:
        try:
            self._assert_acyclic()
        except ValidationError:
            return True
        return False

    def validate(self) -> None:
        """Fail-closed: unknown nodes or cycles make the graph unusable."""
        if self._edges and not self._known_nodes:
            raise ValidationError("Dependency graph has edges but no registered nodes", code="WINDAGENT_ERR_VALIDATION")
        for edge in self._edges:
            if edge.artifact_id not in self._known_nodes:
                raise ValidationError(f"Unknown artifact node {edge.artifact_id!r}", code="WINDAGENT_ERR_VALIDATION")
            if edge.depends_on_artifact_id and edge.depends_on_artifact_id not in self._known_nodes:
                raise ValidationError(
                    f"Unknown dependency target {edge.depends_on_artifact_id!r}",
                    code="WINDAGENT_ERR_VALIDATION",
                )
        self._assert_acyclic()

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "nodes": sorted(self._known_nodes),
            "edges": [e.to_dict() for e in self._edges],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactDependencyGraph":
        graph = cls()
        for node in data.get("nodes", []):
            graph.register_node(node)
        for raw in data.get("edges", []):
            graph.add_edge(ArtifactDependencyEdge.from_dict(raw))
        return graph


def build_character_scope(
    graph: ArtifactDependencyGraph,
    character_artifact_id: str,
) -> Tuple[List[str], List[str]]:
    """Return (bound_shots, downstream_cuts) for a character bible change (§14.3).

    - bound_shots: shots with a CHARACTER_BINDING edge FROM the character
      artifact (only the shots actually bound to this character);
    - downstream_cuts: GENERATED_FROM dependents of those shots (clips, cuts)
      — never other characters' shots.
    """
    bound_shots = sorted(
        e.artifact_id
        for e in graph.inbound_by_type(character_artifact_id, {ArtifactDependencyType.CHARACTER_BINDING})
    )
    downstream: Set[str] = set()
    for shot in bound_shots:
        downstream.update(
            graph.transitive_inbound(shot, {ArtifactDependencyType.GENERATED_FROM})
        )
    return bound_shots, sorted(downstream - set(bound_shots))


def build_bgm_scope(
    graph: ArtifactDependencyGraph,
    bgm_artifact_id: str,
) -> List[str]:
    """Affected artifacts for a BGM change (§14.3): audio mix + final cut ONLY.

    Traversal follows AUDIO_INPUT edges and their GENERATED_FROM dependents
    (mix -> final cut) but NEVER visual-clip edges, so video clips survive a
    BGM change.
    """
    audio_dependents = sorted(
        graph.transitive_inbound(bgm_artifact_id, {ArtifactDependencyType.AUDIO_INPUT})
    )
    downstream: Set[str] = set(audio_dependents)
    for node in audio_dependents:
        downstream.update(
            graph.transitive_inbound(node, {ArtifactDependencyType.GENERATED_FROM})
        )
    return sorted(downstream)


__all__ = [
    "GRAPH_SCHEMA_VERSION",
    "ArtifactDependencyType",
    "ArtifactDependencyEdge",
    "ArtifactDependencyGraph",
    "build_character_scope",
    "build_bgm_scope",
]
