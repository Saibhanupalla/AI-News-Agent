"""Phase 0 smoke tests: the harness itself works."""

import pipeline
from pipeline.__main__ import build_parser


def test_package_imports() -> None:
    assert pipeline.__version__


def test_cli_parses_ingest() -> None:
    args = build_parser().parse_args(["ingest", "--date", "2026-08-24"])
    assert args.command == "ingest"
    assert args.date == "2026-08-24"


def test_cli_parses_run_no_llm() -> None:
    args = build_parser().parse_args(["run", "--date", "today", "--no-llm"])
    assert args.command == "run"
    assert args.no_llm is True
