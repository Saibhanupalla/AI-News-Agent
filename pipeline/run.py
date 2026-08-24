"""Pipeline orchestrator. Stages are wired in as phases land."""

import argparse


def run_command(args: argparse.Namespace) -> int:
    if args.command == "ingest":
        print(f"[stub] ingest for {args.date}: implemented in phase 2")
        return 0
    if args.command == "run":
        print(f"[stub] full run for {args.date}: implemented in phases 2-6")
        return 0
    return 1
