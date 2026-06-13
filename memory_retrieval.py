"""Dependency-light retrieval over wikilinked markdown memory notes.

The helper is intentionally read-only: it scans markdown files, builds a link
graph, and returns note bodies a caller can inject into a model prompt.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import re


FRONTMATTER_DELIM = "---"
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")


@dataclass(frozen=True)
class Note:
    name: str
    description: str
    type: str
    path: Path
    body: str
    links: list[str]


@dataclass(frozen=True)
class Graph:
    nodes: dict[str, Note]
    edges: dict[str, list[str]]
    dangling: dict[str, list[str]]


@dataclass(frozen=True)
class RetrievedNote:
    name: str
    description: str
    type: str
    path: Path
    body: str
    distance: int
    backlink_count: int


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        return {}, text

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIM:
            end = i
            break
    if end is None:
        return {}, text

    data: dict[str, str] = {}
    section: str | None = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        indent = len(raw) - len(raw.lstrip())
        key, value = raw.split(":", 1)
        key = key.strip()
        value = _strip_quotes(value)
        if indent == 0:
            section = key if not value else None
            if value:
                data[key] = value
        elif section == "metadata":
            data[f"metadata.{key}"] = value

    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return data, body


def _extract_links(body: str) -> list[str]:
    seen: set[str] = set()
    links: list[str] = []
    for match in WIKILINK_RE.finditer(body):
        target = match.group(1).strip()
        if target and target not in seen:
            links.append(target)
            seen.add(target)
    return links


def build_graph(memory_dir: str | Path) -> Graph:
    """Scan markdown files and return nodes, outgoing links, and dangling links."""
    base = Path(memory_dir)
    nodes: dict[str, Note] = {}
    for path in sorted(base.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(text)
        name = frontmatter.get("name") or path.stem
        note = Note(
            name=name,
            description=frontmatter.get("description", ""),
            type=frontmatter.get("metadata.type", frontmatter.get("type", "")),
            path=path,
            body=body,
            links=_extract_links(body),
        )
        nodes[name] = note

    edges = {name: note.links for name, note in nodes.items()}
    dangling = {
        name: [target for target in targets if target not in nodes]
        for name, targets in edges.items()
    }
    dangling = {name: targets for name, targets in dangling.items() if targets}
    return Graph(nodes=nodes, edges=edges, dangling=dangling)


def backlink_counts(graph: Graph) -> dict[str, int]:
    """Count how many other existing notes link to each note."""
    counts = {name: 0 for name in graph.nodes}
    for source, targets in graph.edges.items():
        for target in set(targets):
            if target in counts and target != source:
                counts[target] += 1
    return counts


def retrieve(graph: Graph, seed_names: str | list[str],
             depth: int = 2) -> list[RetrievedNote]:
    """Breadth-first retrieve notes reachable from seeds within depth hops."""
    if isinstance(seed_names, str):
        seeds = [seed_names]
    else:
        seeds = list(seed_names)
    depth = max(0, depth)

    distances: dict[str, int] = {}
    seed_order: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()
    for index, seed in enumerate(seeds):
        if seed not in graph.nodes or seed in distances:
            continue
        distances[seed] = 0
        seed_order[seed] = index
        queue.append((seed, 0))

    while queue:
        name, distance = queue.popleft()
        if distance >= depth:
            continue
        for target in graph.edges.get(name, []):
            if target not in graph.nodes or target in distances:
                continue
            distances[target] = distance + 1
            queue.append((target, distance + 1))

    backlinks = backlink_counts(graph)

    def sort_key(name: str) -> tuple[int, int, int, str]:
        distance = distances[name]
        is_seed = 0 if distance == 0 else 1
        order = seed_order.get(name, 10**9)
        return is_seed, distance, order if distance == 0 else -backlinks[name], name.lower()

    ordered = sorted(distances, key=sort_key)
    return [
        RetrievedNote(
            name=name,
            description=graph.nodes[name].description,
            type=graph.nodes[name].type,
            path=graph.nodes[name].path,
            body=graph.nodes[name].body,
            distance=distances[name],
            backlink_count=backlinks[name],
        )
        for name in ordered
    ]


def _note_block(note: RetrievedNote) -> str:
    meta = [
        f"# {note.name}",
        f"path: {note.path}",
        f"distance: {note.distance}",
        f"backlinks: {note.backlink_count}",
    ]
    if note.type:
        meta.append(f"type: {note.type}")
    if note.description:
        meta.append(f"description: {note.description}")
    return "\n".join(meta) + "\n\n" + note.body.strip()


def format_context(notes: list[RetrievedNote], max_chars: int = 8000) -> str:
    """Concatenate retrieved notes in relevance order, capped at max_chars."""
    parts: list[str] = []
    used = 0
    dropped = 0
    for note in notes:
        block = _note_block(note)
        addition = block if not parts else "\n\n---\n\n" + block
        if used + len(addition) > max_chars:
            dropped += 1
            continue
        parts.append(addition if parts else block)
        used += len(addition)

    text = "".join(parts)
    if dropped:
        marker = f"\n\n[... dropped {dropped} note(s) due to max_chars={max_chars} ...]"
        if len(text) + len(marker) <= max_chars:
            text += marker
        elif max_chars >= len(marker):
            text = text[:max_chars - len(marker)].rstrip() + marker
        else:
            text = text[:max_chars]
    return text
