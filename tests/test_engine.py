import json
import subprocess
import sys
from pathlib import Path
import pytest
from cie.engine import BANNER, dumps, graph, history, impact, parse_diff, report
from cie.fixtures import FILES, fixtures


@pytest.fixture
def sample(tmp_path):
    fixtures(tmp_path)
    return tmp_path


def analyse(root):
    return impact(root / "src", root / "change.diff", root / "commits.json", root / "workflows.json")


def test_graph_nodes_edges_cycle_dynamic(sample):
    g = graph(sample / "src")
    assert g["nodes"] == sorted(FILES)
    for kind in ("import", "call"):
        assert {"source": "shared/mathlib.py", "target": "services/a.py", "kind": kind} in g["edges"]
        assert {"source": "services/a.py", "target": "services/b.py", "kind": kind} in g["edges"]
    assert g["cycles"] == [["cycle/one.py", "cycle/two.py"]]
    assert len([x for x in g["unresolved"] if x["reason"] == "dynamic import unresolved"]) == 2
    assert not any(x["source"].startswith("unknown") for x in g["edges"])


def test_history_formula_and_floor(sample):
    h = history(sample / "commits.json")
    scores = {tuple(x["files"]): x["score"] for x in h["scores"]}
    assert scores["ops/release.py", "shared/mathlib.py"] == 1 > h["threshold"]
    assert scores["shared/mathlib.py", "unrelated.py"] == 0


def test_impact_confidence_evidence_tests_api(sample):
    data = analyse(sample)
    items = {x["file"]: x for x in data["affected_modules"]}
    assert data["touched_files"] == [{"file": "shared/mathlib.py", "symbols": ["price"]}]
    assert items["services/a.py"]["confidence"] == "high"
    assert items["services/b.py"]["confidence"] == "medium"
    assert [(e["source"], e["target"]) for e in items["services/b.py"]["evidence_path"]] == [("shared/mathlib.py", "services/a.py"), ("services/a.py", "services/b.py")]
    assert items["ops/release.py"]["confidence"] == "low"
    assert {x["file"] for x in data["affected_tests"]} == {"tests/test_a.py", "tests/test_b.py"}
    assert data["api_surfaces"][0]["module"] == "api/orders.py"
    assert data["workflows"] == ["Fictional customer checkout"]
    assert "unrelated.py" not in items


@pytest.mark.parametrize("format", ["json", "md"])
def test_determinism_and_honesty(sample, format):
    first = report(analyse(sample), format)
    assert first.encode() == report(analyse(sample), format).encode()
    assert BANNER in first
    assert "will break" not in first


def test_fixture_determinism(sample, tmp_path):
    other = tmp_path / "other"
    fixtures(other)
    for path in sample.rglob("*"):
        if path.is_file() and other not in path.parents:
            assert path.read_bytes() == (other / path.relative_to(sample)).read_bytes()


@pytest.mark.parametrize("command", ["graph", "history", "impact", "report", "fixtures"])
def test_cli_smoke(sample, command):
    arguments = {"graph": ["--src", str(sample / "src")], "history": ["--log", str(sample / "commits.json")], "fixtures": ["--out", str(sample / "generated")], "impact": ["--src", str(sample / "src"), "--diff", str(sample / "change.diff"), "--log", str(sample / "commits.json"), "--workflows", str(sample / "workflows.json")], "report": ["--src", str(sample / "src"), "--diff", str(sample / "change.diff"), "--format", "md"]}
    result = subprocess.run([sys.executable, "-m", "cie", command, *arguments[command]], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    if command in ("impact", "report"):
        assert BANNER in result.stdout
    else:
        json.loads(result.stdout)


def test_saved_report_and_end_to_end(sample):
    result = subprocess.run([sys.executable, "-m", "cie", "impact", "--src", str(sample / "src"), "--diff", str(sample / "change.diff"), "--log", str(sample / "commits.json"), "--workflows", str(sample / "workflows.json")], capture_output=True, text=True, check=True)
    saved = sample / "impact.json"
    saved.write_text(result.stdout, encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "cie", "report", "--input", str(saved), "--format", "md"], capture_output=True, text=True, check=True)
    assert "Fictional customer checkout" in result.stdout
    assert "services/b.py [medium]" in result.stdout
    assert BANNER in result.stdout


def test_relative_import_and_wildcard(sample):
    (sample / "src/services/relative.py").write_text("from .a import quote\nquote(2)\nfrom .a import *\n", encoding="utf-8")
    g = graph(sample / "src")
    assert {"source": "services/a.py", "target": "services/relative.py", "kind": "call"} in g["edges"]
    assert any(x["reason"] == "wildcard binding unresolved" for x in g["unresolved"])


def test_added_deleted_and_path_rejection(sample):
    assert parse_diff("--- a/gone.py\n+++ /dev/null\n", sample / "src") == [{"file": "gone.py", "symbols": []}]
    assert parse_diff("--- /dev/null\n+++ b/new.py\n", sample / "src") == [{"file": "new.py", "symbols": []}]
    with pytest.raises(ValueError):
        parse_diff("+++ b/../../outside.py", sample / "src")


def test_cli_invalid_input(sample):
    result = subprocess.run([sys.executable, "-m", "cie", "graph", "--src", str(sample / "missing")], capture_output=True, text=True)
    assert result.returncode == 2
    assert "does not exist" in result.stderr


def test_history_deduplicates_commit_files(sample):
    path = sample / "duplicates.json"
    path.write_text(dumps([{"files": ["a.py", "a.py", "b.py"]}, {"files": ["a.py"]}]), encoding="utf-8")
    assert history(path)["scores"][0]["score"] == 0.5
