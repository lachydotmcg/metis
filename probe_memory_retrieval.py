r"""Small read-only probe for memory retrieval depth.

Usage:
    python probe_memory_retrieval.py C:\path\to\memory_dir
    python probe_memory_retrieval.py C:\path\to\memory_dir --seed note-name
"""

from __future__ import annotations

import argparse

from memory_retrieval import (
    backlink_counts,
    build_graph,
    format_context,
    retrieve,
)


def _pick_seed(graph) -> str:
    counts = backlink_counts(graph)
    if not counts:
        raise SystemExit("no markdown notes found")
    return sorted(counts, key=lambda name: (-counts[name], name.lower()))[0]


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Probe how much context depth 1/2/3 retrieves.")
    parser.add_argument("memory_dir")
    parser.add_argument("--seed", default=None,
                        help="seed note name; defaults to most-backlinked note")
    parser.add_argument("--max-chars", type=int, default=1_000_000,
                        help="large cap used only for measuring chars")
    args = parser.parse_args(argv)

    graph = build_graph(args.memory_dir)
    seed = args.seed or _pick_seed(graph)
    edge_count = sum(len(targets) for targets in graph.edges.values())
    print(f"memory_dir={args.memory_dir}")
    print(f"seed={seed!r}")
    print(
        f"nodes={len(graph.nodes)} edges={edge_count} "
        f"dangling_sources={len(graph.dangling)}")
    if edge_count == 0:
        print("note=no wikilinks found; depth will not expand")
    for depth in (1, 2, 3):
        notes = retrieve(graph, [seed], depth=depth)
        context = format_context(notes, max_chars=args.max_chars)
        print(f"depth={depth} notes={len(notes)} chars={len(context)}")


if __name__ == "__main__":
    main()
