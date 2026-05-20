from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from no_check_d3_ablation.app.runner import NoCheckAblationRunner

AVAILABLE_MODELS = [
    "gemini-2.5-pro",
    "gpt-5-2025-08-07",
    "claude-opus-4-1-20250805-thinking",
    "deepseek-v3-1-think-250821",
    "grok-4",
]

DEFAULT_CENTERS = ["Foshan", "Wuhan", "Xinjiang"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="No-check D3 ablation runner")
    parser.add_argument("--threads", type=int, default=30, help="并发线程数")
    parser.add_argument("--limit-cases", type=int, default=15, help="选择多少个病例组进行测试")
    parser.add_argument("--skip-cases", type=int, default=0, help="跳过前多少个病例组（按筛选后排序）")
    parser.add_argument("--min-eligible-model-count", type=int, default=0, help="病例组最少满足多少模型轨迹才纳入")
    parser.add_argument(
        "--include-case-csv",
        type=str,
        default="",
        help="仅测试该CSV中的病例组，需含 center/case_id 列",
    )
    parser.add_argument("--judge-model", type=str, default="gemini-2.5-pro", help="Judge 模型")
    parser.add_argument("--models", nargs="+", default=AVAILABLE_MODELS, help="参与消融实验的模型列表")
    parser.add_argument("--centers", nargs="+", default=DEFAULT_CENTERS, help="参与实验的中心")
    parser.add_argument("--run-label", type=str, help="输出目录标签")
    parser.add_argument("--task-retries", type=int, default=3, help="单任务级别最大重试次数")
    return parser


def load_include_case_keys(csv_path: str) -> set[tuple[str, str]]:
    path = Path(csv_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"include-case-csv 不存在: {path}")
    keys: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return keys
        lowered = {name.lower(): name for name in reader.fieldnames}
        center_col = lowered.get("center")
        case_col = lowered.get("case_id")
        if not center_col or not case_col:
            raise ValueError(f"include-case-csv 缺少 center/case_id 列: {path}")
        for row in reader:
            center = str(row.get(center_col) or "").strip()
            case_id = str(row.get(case_col) or "").strip()
            if center and case_id:
                keys.add((center, case_id))
    return keys


def setup_logging(run_root: Path) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    log_path = run_root / "run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    # 降噪：避免 doctor/judge/httpx 大量 INFO 淹没进度条
    noisy_loggers = [
        "httpx",
        "openai",
        "auto_eval_system.modules.doctor_agent",
        "auto_eval_system.modules.judge_agent",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    run_label = args.run_label or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = REPO_ROOT / "output_ablation_no_check_d3" / run_label
    setup_logging(run_root)

    logging.info("启动无检查 D3 消融实验，run_label=%s", run_label)
    logging.info("中心=%s", args.centers)
    logging.info("模型=%s", args.models)
    logging.info("judge_model=%s", args.judge_model)
    logging.info(
        "threads=%s skip_cases=%s limit_cases=%s min_eligible_model_count=%s task_retries=%s",
        args.threads,
        args.skip_cases,
        args.limit_cases,
        args.min_eligible_model_count,
        args.task_retries,
    )
    logging.info("渠道策略：运行时改写路由；gemini 优先 duckcoding，duck 不可用时自动降级为仅星辰。")

    include_case_keys: set[tuple[str, str]] | None = None
    if args.include_case_csv:
        include_case_keys = load_include_case_keys(args.include_case_csv)
        logging.info("include_case_csv=%s, case_groups=%s", args.include_case_csv, len(include_case_keys))

    runner = NoCheckAblationRunner(
        repo_root=REPO_ROOT,
        run_root=run_root,
        centers=args.centers,
        models=args.models,
        judge_model=args.judge_model,
        max_workers=args.threads,
        task_retries=args.task_retries,
    )
    rows = runner.run(
        limit_cases=args.limit_cases,
        skip_cases=args.skip_cases,
        include_case_keys=include_case_keys,
        min_eligible_model_count=args.min_eligible_model_count,
    )
    logging.info("实验结束，共写出 %s 条 summary 记录。", len(rows))


if __name__ == "__main__":
    main()
