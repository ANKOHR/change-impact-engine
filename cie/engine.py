"""Deterministic, conservative module-level static analysis."""
import ast
import itertools
import json
import re
from collections import Counter, deque
from pathlib import Path, PurePosixPath

BANNER = "Predictions are static-analysis heuristics over a synthetic codebase, not guarantees of breakage."


def dumps(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def module_name(path):
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def graph(src):
    root = Path(src)
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.py"))
    modules = {module_name(p): p for p in files}
    edges, unresolved, symbols = set(), [], {}
    for file in files:
        tree = ast.parse((root / file).read_text(encoding="utf-8"), filename=file)
        symbols[file] = sorted({n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))})
        aliases = {}
        def resolve(target, node, alias=None):
            candidate = target
            if candidate in modules:
                dest = modules[candidate]
                if dest != file:
                    edges.add((dest, file, "import"))
                if alias:
                    aliases[alias] = dest
            else:
                unresolved.append({"file": file, "line": node.lineno, "target": target, "reason": "outside snapshot or unknown import"})
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    resolve(item.name, node, item.asname or item.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                package = module_name(file).split(".")
                if not file.endswith("__init__.py"):
                    package = package[:-1]
                prefix = ".".join(package[:len(package) - node.level + 1]) if node.level else ""
                base = ".".join(filter(None, [prefix, node.module]))
                for item in node.names:
                    if item.name == "*":
                        unresolved.append({"file": file, "line": node.lineno, "target": base + ".*", "reason": "wildcard binding unresolved"})
                        resolve(base, node)
                    else:
                        target = base + "." + item.name
                        resolve(target if target in modules else base, node, item.asname or item.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                head = name.split(".")[0]
                if name == "__import__" or name.endswith(".import_module") or name == "import_module":
                    unresolved.append({"file": file, "line": node.lineno, "target": ast.unparse(node), "reason": "dynamic import unresolved"})
                elif head in aliases:
                    edges.add((aliases[head], file, "call"))
    adjacency = {f: sorted({b for a, b, _ in edges if a == f}) for f in files}
    # Mutual reachability partitions produce cycle components without duplicate rotations.
    def reachable(start):
        seen, pending = set(), [start]
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(adjacency[node])
        return seen
    reach = {f: reachable(f) for f in files}
    groups = {tuple(sorted(g for g in files if g in reach[f] and f in reach[g])) for f in files}
    return {"nodes": files, "symbols": symbols, "edges": [{"source": a, "target": b, "kind": k} for a, b, k in sorted(edges)], "cycles": [list(g) for g in sorted(groups) if len(g) > 1], "unresolved": sorted(unresolved, key=lambda x: (x["file"], x["line"], x["target"]))}


def history(log):
    commits = json.loads(Path(log).read_text(encoding="utf-8"))
    counts, pairs = Counter(), Counter()
    for commit in commits:
        files = sorted(set(commit["files"]))
        counts.update(files)
        pairs.update(itertools.combinations(files, 2))
    scores = [{"files": [a, b], "score": pairs[a, b] / (counts[a] + counts[b] - pairs[a, b]), "together": pairs[a, b]} for a, b in itertools.combinations(sorted(counts), 2)]
    return {"formula": "Jaccard: commits(A and B) / commits(A or B); absent pairs score 0", "threshold": 0.5, "scores": scores}


def parse_diff(text, src):
    touched, ranges = set(), {}
    current = None
    for line in text.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            path = line[4:].split("\t")[0]
            if path == "/dev/null":
                continue
            path = re.sub(r"^[ab]/", "", path)
            if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts or ":" in path or "\\" in path:
                raise ValueError("Diff paths must stay inside the snapshot")
            touched.add(path)
            current = path
        elif line.startswith("@@") and current:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start, count = int(match[1]), int(match[2] or 1)
                ranges.setdefault(current, []).append((start, start + max(count, 1) - 1))
    result = []
    for file in sorted(touched):
        names = set()
        path = Path(src) / file
        if path.is_file():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and any(start <= node.end_lineno and end >= node.lineno for start, end in ranges.get(file, [])):
                    names.add(node.name)
        result.append({"file": file, "symbols": sorted(names)})
    return result


def impact(src, diff, log=None, workflow_map=None):
    g = graph(src)
    touched = parse_diff(Path(diff).read_text(encoding="utf-8"), src)
    seeds = {x["file"] for x in touched}
    found = {f: [] for f in sorted(seeds)}
    queue = deque(sorted(seeds))
    while queue:
        node = queue.popleft()
        for edge in g["edges"]:
            if edge["source"] == node and edge["target"] not in found:
                found[edge["target"]] = found[node] + [edge]
                queue.append(edge["target"])
    items = []
    for file, path in sorted(found.items()):
        band = "high" if len(path) <= 1 else "medium"
        items.append({"file": file, "confidence": band, "rationale": "directly touched" if not path else "direct static edge" if len(path) == 1 else "transitive static reachability", "evidence_path": path})
    if log:
        for pair in history(log)["scores"]:
            if pair["score"] >= 0.5 and seeds.intersection(pair["files"]):
                for file in pair["files"]:
                    if file not in found:
                        items.append({"file": file, "confidence": "low", "rationale": "co-change only", "evidence_path": [], "co_change": pair})
                        found[file] = []
    items.sort(key=lambda x: ({"high": 0, "medium": 1, "low": 2}[x["confidence"]], x["file"]))
    mapping = json.loads(Path(workflow_map).read_text(encoding="utf-8")) if workflow_map else {}
    apis = [{"module": api, "workflows": sorted(workflows), "evidence": next(x for x in items if x["file"] == api)} for api, workflows in sorted(mapping.items()) if api in found]
    return {"banner": BANNER, "touched_files": touched, "affected_modules": items, "affected_services": [x for x in items if x["file"].startswith("services/")], "affected_tests": [x for x in items if x["file"].startswith("tests/") or PurePosixPath(x["file"]).name.startswith("test_")], "api_surfaces": apis, "workflows": sorted({w for api in apis for w in api["workflows"]}), "unresolved": g["unresolved"]}


def report(data, format="json"):
    if format == "json":
        return dumps(data)
    lines = ["# Change Impact Engine blast-radius report", "", data["banner"], "", "## Touched files"]
    lines += [f"- {x['file']}: symbols {', '.join(x['symbols']) or '(module or unknown)'}" for x in data["touched_files"]]
    for title, key in [("Affected modules", "affected_modules"), ("Affected services", "affected_services"), ("Affected tests", "affected_tests")]:
        lines += ["", "## " + title]
        for item in data[key]:
            path = "; ".join(f"{e['source']} -> {e['target']} ({e['kind']})" for e in item["evidence_path"])
            if "co_change" in item:
                path = "co-change " + dumps(item["co_change"]).strip().replace("\n", " ")
            lines.append(f"- {item['file']} [{item['confidence']}]: {item['rationale']}. Evidence: {path or 'diff touches this file'}")
    lines += ["", "## API surfaces and customer workflows"]
    lines += [f"- {x['module']}: {', '.join(x['workflows'])}; reachable with {x['evidence']['confidence']} confidence (see module evidence above)" for x in data["api_surfaces"]]
    lines += ["", "## Unresolved analysis", dumps(data["unresolved"]).strip()]
    return "\n".join(lines) + "\n"
