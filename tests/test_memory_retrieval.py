"""Plain-assert tests for wikilinked markdown memory retrieval."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_retrieval import (
    backlink_counts,
    build_graph,
    format_context,
    retrieve,
)


def _note(path: Path, name: str, body: str,
          description: str = "", note_type: str = "fact") -> None:
    path.write_text(
        "\n".join([
            "---",
            f"name: {name}",
            f"description: {description}",
            "metadata:",
            f"  type: {note_type}",
            "---",
            body,
        ]),
        encoding="utf-8",
    )


def test_build_graph_records_edges_and_dangling_links():
    with tempfile.TemporaryDirectory(prefix="metis_memory_test_") as td:
        base = Path(td)
        _note(base / "alpha.md", "alpha", "Alpha links [[beta]] and [[missing]].")
        _note(base / "beta.md", "beta", "Beta links [[gamma|Gamma note]].")
        _note(base / "gamma.md", "gamma", "Gamma links nowhere.")

        graph = build_graph(base)
        assert sorted(graph.nodes) == ["alpha", "beta", "gamma"]
        assert graph.nodes["alpha"].description == ""
        assert graph.nodes["alpha"].type == "fact"
        assert graph.edges["alpha"] == ["beta", "missing"]
        assert graph.edges["beta"] == ["gamma"]
        assert graph.dangling == {"alpha": ["missing"]}


def test_backlink_counts_existing_notes_only():
    with tempfile.TemporaryDirectory(prefix="metis_memory_test_") as td:
        base = Path(td)
        _note(base / "alpha.md", "alpha", "[[beta]] [[missing]]")
        _note(base / "beta.md", "beta", "[[gamma]]")
        _note(base / "delta.md", "delta", "[[beta]]")
        _note(base / "gamma.md", "gamma", "[[beta]]")

        counts = backlink_counts(build_graph(base))
        assert counts["beta"] == 3
        assert counts["gamma"] == 1
        assert counts["alpha"] == 0
        assert "missing" not in counts


def test_retrieve_orders_by_seed_distance_then_backlinks():
    with tempfile.TemporaryDirectory(prefix="metis_memory_test_") as td:
        base = Path(td)
        _note(base / "alpha.md", "alpha", "[[beta]] [[gamma]]")
        _note(base / "beta.md", "beta", "[[epsilon]]")
        _note(base / "gamma.md", "gamma", "[[epsilon]]")
        _note(base / "delta.md", "delta", "[[gamma]]")
        _note(base / "epsilon.md", "epsilon", "Leaf.")

        graph = build_graph(base)
        depth1 = retrieve(graph, ["alpha"], depth=1)
        assert [n.name for n in depth1] == ["alpha", "gamma", "beta"]
        assert depth1[1].backlink_count == 2

        depth2 = retrieve(graph, ["alpha"], depth=2)
        assert [n.name for n in depth2] == [
            "alpha", "gamma", "beta", "epsilon"]
        assert depth2[-1].distance == 2
        assert depth2[-1].path.name == "epsilon.md"
        assert "Leaf." in depth2[-1].body


def test_format_context_caps_chars_and_notes_drops():
    with tempfile.TemporaryDirectory(prefix="metis_memory_test_") as td:
        base = Path(td)
        _note(base / "alpha.md", "alpha", "A" * 20)
        _note(base / "beta.md", "beta", "B" * 20)
        graph = build_graph(base)
        notes = retrieve(graph, ["alpha", "beta"], depth=0)

        text = format_context(notes, max_chars=160)
        assert "# alpha" in text
        assert "dropped 1 note" in text
        assert len(text) <= 160


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok {fn.__name__}")
    print(f"OK - {len(fns)} test groups passed")
