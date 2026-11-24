"""Command line entry point: validate, run, compare."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agents import AgentLoadError, ReplayAgent, load_agent
from .compare import Thresholds, compare_runs
from .golden import GoldenSetError, load_golden
from .judge import JudgeError, make_judge
from .report import render_comparison_markdown, render_comparison_text, render_run_text
from .runner import DEFAULT_JUDGE_PASS_MARK, load_run, run_eval, save_run

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_USAGE = 2

DEFAULT_GOLDEN = "golden/golden_set.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalharness", description="Evaluate a customer service agent and gate on regressions."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="check the golden set is well formed")
    validate.add_argument("--golden", default=DEFAULT_GOLDEN)

    run = sub.add_parser("run", help="run the golden set through an agent")
    run.add_argument("--golden", default=DEFAULT_GOLDEN)
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--agent", help="callable to import, as package.module:callable")
    source.add_argument("--replies", help="JSONL file of recorded replies keyed by case id")
    run.add_argument("--judge", choices=["mock", "claude", "none"], default=None,
                     help="defaults to the EVAL_JUDGE environment variable, then mock")
    run.add_argument("--judge-pass-mark", type=float, default=DEFAULT_JUDGE_PASS_MARK)
    run.add_argument("--label", default="run")
    run.add_argument("--out", required=True, help="where to write the run JSON")
    run.add_argument("--fail-under", type=float, default=None,
                     help="exit 1 when the pass rate is below this fraction, for example 0.9")

    compare = sub.add_parser("compare", help="compare a candidate run with a baseline run")
    compare.add_argument("baseline")
    compare.add_argument("candidate")
    compare.add_argument("--report", help="write a markdown report to this path")
    compare.add_argument("--max-pass-rate-drop", type=float, default=Thresholds.max_pass_rate_drop)
    compare.add_argument("--max-judge-drop", type=float, default=Thresholds.max_judge_drop)
    compare.add_argument("--case-judge-drop", type=float, default=Thresholds.case_judge_drop)
    compare.add_argument("--allow-critical-failures", action="store_true",
                         help="do not fail just because a critical case fails")
    compare.add_argument("--fail-on-judge-drift", action="store_true",
                         help="fail when a single case's judge score drops sharply")
    return parser


def _cmd_validate(args: argparse.Namespace) -> int:
    cases = load_golden(args.golden)
    critical = sum(1 for c in cases if c.severity == "critical")
    categories = sorted({c.category for c in cases})
    print(f"{args.golden}: {len(cases)} cases, {critical} critical, "
          f"{len(categories)} categories ({', '.join(categories)})")
    return EXIT_OK


def _cmd_run(args: argparse.Namespace) -> int:
    cases = load_golden(args.golden)
    if args.agent:
        agent, agent_name = load_agent(args.agent), args.agent
    else:
        agent, agent_name = ReplayAgent(args.replies), f"replay:{Path(args.replies).name}"
    judge = make_judge(args.judge)
    run = run_eval(cases, agent, judge, label=args.label, agent_name=agent_name,
                   judge_pass_mark=args.judge_pass_mark)
    save_run(run, args.out)
    print(render_run_text(run))
    print(f"wrote {args.out}")
    if args.fail_under is not None and run["summary"]["pass_rate"] < args.fail_under:
        print(f"pass rate is below --fail-under {args.fail_under}")
        return EXIT_REGRESSION
    return EXIT_OK


def _cmd_compare(args: argparse.Namespace) -> int:
    thresholds = Thresholds(
        max_pass_rate_drop=args.max_pass_rate_drop,
        max_judge_drop=args.max_judge_drop,
        case_judge_drop=args.case_judge_drop,
        fail_on_critical=not args.allow_critical_failures,
        fail_on_judge_drift=args.fail_on_judge_drift,
    )
    comparison = compare_runs(load_run(args.baseline), load_run(args.candidate), thresholds)
    print(render_comparison_text(comparison))
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_comparison_markdown(comparison))
        print(f"wrote {args.report}")
    return EXIT_REGRESSION if comparison.regressed else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"validate": _cmd_validate, "run": _cmd_run, "compare": _cmd_compare}
    try:
        return handlers[args.command](args)
    except GoldenSetError as exc:
        print("golden set problems:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
    except (AgentLoadError, JudgeError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
