# Change Impact Engine

Show it the diff before you merge. It tells you what might break and why it thinks so.

A CPU-only Python CLI that parses a fictional Python snapshot, combines static dependency reachability with synthetic commit history, and produces an evidence-backed blast-radius report. It uses only the Python standard library at runtime. No models, GPU packages, network services, or random generation are used.

## Quickstart

Requires Python 3.10 or newer. Run from the repository root:

```powershell
python -m pip install -e ".[test]"
cie fixtures --out demo
cie graph --src demo/src
cie history --log demo/commits.json
cie impact --src demo/src --diff demo/change.diff --log demo/commits.json --workflows demo/workflows.json
cie report --src demo/src --diff demo/change.diff --log demo/commits.json --workflows demo/workflows.json --format md
python -m pytest -q
```

`python -m cie` also works without installing the console entry point. `impact` and `report` accept `--format json|md`. To save and re-render JSON in PowerShell:

```powershell
cie impact --src demo/src --diff demo/change.diff --log demo/commits.json --workflows demo/workflows.json | Out-File -Encoding utf8 impact.json
cie report --input impact.json --format md
```

Use a snapshot corresponding to the new side of the diff for symbol ranges. Paths in the diff are relative to `--src`, with optional `a/` and `b/` prefixes. Deleted files remain touched seeds with unknown symbols; preserving old dependency edges requires supplying a snapshot that still contains those files. A diff is analysed, never applied.

## Architecture

```text
fictional Python snapshot -> AST imports and calls -> dependency graph
                                                       |
unified diff -> touched files and symbol ranges -> forward breadth-first walk
                                                       |
synthetic commit file sets -> Jaccard coupling ---------+
                                                       |
test import reachability + declared workflow map -------+
                                                       |
                                   confidence rules and evidence paths
                                                       |
                                      JSON / Markdown report with banner
```

Edges point from a dependency to its consumer: `shared/mathlib.py -> services/a.py`. An import edge records the dependency; a call edge records a syntactic call through an imported binding. The CLI walks these edges forward from every touched file. Cycles are reported as sorted strongly connected components. A shortest static path is retained per affected file; ties use sorted file and edge order. Calls and imports between the same files remain separate edge kinds.

## Command catalogue

| Command | Required input | Output |
| --- | --- | --- |
| `fixtures` | `--out` | Fictional source tree, history, diff, map and labels |
| `graph` | `--src` | Nodes, symbols, import/call edges, cycles and unresolved imports |
| `history` | `--log` | Pair scores, counts, declared formula and threshold |
| `impact` | `--src --diff` | Touched symbols, modules, services, tests, APIs and workflows |
| `report` | `--src --diff` or `--input` | JSON or Markdown blast-radius report |

`impact` and `report` optionally accept `--log` and `--workflows`. No hidden working-directory state is needed. CLI errors return exit code 2.

## Confidence rules

| Evidence | Band | Rationale |
| --- | --- | --- |
| File directly touched | high | Direct diff evidence |
| One static import or call edge from a touched file | high | Direct static edge |
| Two or more static edges | medium | Transitive static reachability |
| History coupling only, score at least 0.5 | low | Co-change only |

Static evidence takes precedence over history. Co-change-only items do not seed additional propagation. Bands rank evidence strength, not measured breakage probabilities. Every affected item includes its rationale and an ordered evidence path, or the coupling pair and score. Directly touched items have an empty path because the diff itself is the evidence.

## Co-change formula

For files A and B, coupling is Jaccard similarity over commit membership:

```text
score(A, B) = number of commits containing both A and B
              / number of commits containing A or B
```

Duplicate paths within a commit count once. Pairs never seen together score 0; files absent from the log also have an implicit score of 0. The inclusion threshold is 0.5, inclusive. The JSON log is a list of objects with `files` arrays and optional fictional `id` fields. History is synthetic evidence, never a causal claim.

## Fixture catalogue

All fixtures are fictional and explicitly labelled in source docstrings and `FICTIONAL.txt`.

| Fixture | Planted structure |
| --- | --- |
| `shared/mathlib.py` | Changed pricing function |
| `services/a.py` | Imports and calls the shared function |
| `services/b.py` | Imports and calls service A |
| `api/orders.py` | Imports and calls service B |
| `tests/test_a.py`, `tests/test_b.py` | Known static import coverage |
| `cycle/one.py`, `cycle/two.py` | Two-module cycle |
| `dynamic.py` | Unresolved external and dynamic imports |
| `ops/release.py` | History-only coupling to the shared file, score 1 |
| `unrelated.py` | Independent file, coupling floor 0 |
| `workflows.json` | API path to fictional customer checkout |
| `change.diff`, `commits.json` | Synthetic change and commit file sets |

Workflow maps are JSON objects mapping API module paths to lists of fictional workflow names. Reports include APIs reached statically or coupled historically, with the corresponding evidence and band. Services are files under `services/`; tests are files under `tests/` or named `test_*.py`. Static test reachability is a coverage approximation, not execution coverage.

## HONESTY BOUNDARY

Impact predictions are heuristics from static analysis and synthetic history, not guarantees about real breakage. This project uses no real codebases or customer records. A report claims that an item is reachable from the change through recorded edges, or historically coupled in the fictional log. It never claims that the item will break as fact.

Every JSON and Markdown report carries this banner:

> Predictions are static-analysis heuristics over a synthetic codebase, not guarantees of breakage.

Unknown external imports and dynamic imports are unresolved, never inferred into snapshot nodes. Wildcard bindings are unresolved, although their module dependency can be recorded. AST analysis is module-level and syntactic: it does not execute code, prove call feasibility, resolve arbitrary runtime dispatch, track local alias shadowing, or measure test execution coverage. Hunk ranges identify overlapping symbols, including enclosing classes; impacts propagate at file granularity. Rename paths are conservatively treated as touched old and new files. Standard unified diffs are supported; binary patches have no symbol information. Syntax errors are surfaced, not silently skipped.

## Determinism and validation

Fixtures use fixed literal content, with no RNG and no seed required. Sorted traversal, breadth-first evidence selection, sorted JSON keys and fixed formatting produce byte-identical reports for identical inputs. There are no timestamps or absolute source paths in reports. The pytest suite covers graph edges and cycles, unresolved imports, history formula and threshold, impact bands and paths, tests and workflows, repeat reports, fixture bytes, CLI commands and end-to-end rendering.

Publishing is handled separately. This build performs no remote publication.
