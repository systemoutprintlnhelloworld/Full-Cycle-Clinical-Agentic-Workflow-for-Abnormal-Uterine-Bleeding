from __future__ import annotations

import argparse
from pathlib import Path

from llm_judge_metrics.runner import run_metrics


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute metrics and export human-review workbooks (reads data/ only; writes outputs/ + work/)."
    )
    p.add_argument("--tag", default="latest", help="run tag suffix in run_id (default: latest -> outputs/latest, work/latest)")
    p.add_argument("--data-root", default="data", help="data root directory (default: data)")
    p.add_argument("--outputs-root", default="outputs", help="outputs root directory (default: outputs)")
    p.add_argument("--work-root", default="work", help="work root directory (default: work)")
    p.add_argument(
        "--centers",
        nargs="*",
        default=None,
        help="optional centers to include (default: all under data/)",
    )
    p.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="optional doc models to include (default: all found in each center)",
    )
    p.add_argument(
        "--match-score-threshold",
        type=float,
        default=0.5,
        help="threshold for round inefficiency proxy when using judge match score (default: 0.5)",
    )
    p.add_argument(
        "--export-raw-excel",
        action="store_true",
        help="export full raw workbook to work/<run_id>/_raw (default: off; review workbook is always generated)",
    )
    p.add_argument(
        "--no-excel",
        action="store_true",
        help="(deprecated) kept for compatibility; raw workbook is off by default",
    )
    p.add_argument(
        "--split-by",
        default="center-model",
        choices=["center-model", "none"],
        help="output layout (default: center-model; writes per center/model folders)",
    )
    p.add_argument(
        "--llm-task-scope",
        default="review_only",
        choices=["review_only", "all"],
        help="LLM task generation scope (default: review_only; all=generate tasks for all cases)",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()
    project_root = Path(__file__).resolve().parents[1]

    run_metrics(
        project_root=project_root,
        data_root=Path(args.data_root),
        outputs_root=Path(args.outputs_root),
        work_root=Path(args.work_root),
        tag=args.tag,
        centers=args.centers,
        models=args.models,
        match_score_threshold=args.match_score_threshold,
        export_excel=(args.export_raw_excel and not args.no_excel),
        split_by=args.split_by,
        llm_task_scope=args.llm_task_scope,
    )


if __name__ == "__main__":
    main()
