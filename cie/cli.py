"""Command-line interface with deterministic JSON and Markdown output."""
import argparse
import json
import sys
from pathlib import Path
from .engine import dumps, graph, history, impact, report
from .fixtures import fixtures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Static impact heuristics for synthetic Python snapshots")
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("fixtures")
    p.add_argument("--out", required=True)
    p = subs.add_parser("graph")
    p.add_argument("--src", required=True)
    p = subs.add_parser("history")
    p.add_argument("--log", required=True)
    for command in ("impact", "report"):
        p = subs.add_parser(command)
        p.add_argument("--src", help="Python snapshot directory")
        p.add_argument("--diff", help="Unified diff against the snapshot")
        p.add_argument("--log")
        p.add_argument("--workflows")
        p.add_argument("--format", choices=("md", "json"), default="json")
        if command == "report":
            p.add_argument("--input", help="Previously generated impact JSON")
    args = parser.parse_args(argv)
    try:
        if args.command == "fixtures":
            output = dumps(fixtures(args.out))
        elif args.command == "graph":
            if not Path(args.src).is_dir():
                raise ValueError("Snapshot directory does not exist")
            output = dumps(graph(args.src))
        elif args.command == "history":
            output = dumps(history(args.log))
        else:
            if args.command == "report" and args.input:
                data = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
                from .engine import BANNER
                data["banner"] = BANNER
            else:
                if not args.src or not args.diff:
                    parser.error("--src and --diff are required unless report --input is used")
                if not Path(args.src).is_dir():
                    raise ValueError("Snapshot directory does not exist")
                data = impact(args.src, args.diff, args.log, args.workflows)
            output = report(data, args.format)
        sys.stdout.write(output)
        return 0
    except (OSError, ValueError, SyntaxError, KeyError, TypeError) as exc:
        parser.exit(2, f"cie: {exc}\n")
