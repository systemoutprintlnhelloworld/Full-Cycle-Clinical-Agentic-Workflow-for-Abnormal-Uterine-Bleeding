from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean


def load_cases(demo_data_dir: Path) -> list[dict]:
    cases: list[dict] = []
    for path in sorted(demo_data_dir.glob("toy_case_*.json")):
        with path.open("r", encoding="utf-8") as handle:
            cases.append(json.load(handle))
    if not cases:
        raise FileNotFoundError(f"No toy_case_*.json files found in {demo_data_dir}")
    return cases


def summarize_case(case: dict) -> dict:
    stages = case.get("stages", [])
    scores = [float(stage["judge_score"]) for stage in stages if "judge_score" in stage]
    return {
        "case_id": case.get("case_id"),
        "center": case.get("center"),
        "n_stages": len(stages),
        "stage_ids": [stage.get("stage_id") for stage in stages],
        "mean_demo_judge_score": round(mean(scores), 3) if scores else None,
        "contains_real_patient_data": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reviewer-safe offline toy demo.")
    parser.add_argument("--demo-data", default="demo_data", help="Directory with toy_case_*.json files.")
    parser.add_argument("--out", default="outputs/demo_summary.json", help="Output summary JSON path.")
    args = parser.parse_args()

    demo_data_dir = Path(args.demo_data)
    out_path = Path(args.out)
    cases = load_cases(demo_data_dir)
    summary = {
        "demo_type": "offline_synthetic_no_api",
        "n_cases": len(cases),
        "cases": [summarize_case(case) for case in cases],
        "notes": [
            "This demo uses synthetic toy cases only.",
            "No LLM API calls are made.",
            "No patient-level raw clinical records are included.",
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
