"""CLI entry point: python -m pipeline <command>."""

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Daily AI/tech briefing pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    ingest = sub.add_parser("ingest", help="Fetch RSS feeds and write normalized articles")
    ingest.add_argument("--date", required=True, help="YYYY-MM-DD or 'today'")

    run = sub.add_parser("run", help="Full pipeline: ingest through edition JSON")
    run.add_argument("--date", required=True, help="YYYY-MM-DD or 'today'")
    run.add_argument(
        "--no-llm",
        action="store_true",
        help="Stop after the quality gate (no GEMINI_API_KEY needed)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    # Imported lazily so `--help` works before later phases exist.
    from pipeline.run import run_command

    return run_command(args)


if __name__ == "__main__":
    sys.exit(main())
