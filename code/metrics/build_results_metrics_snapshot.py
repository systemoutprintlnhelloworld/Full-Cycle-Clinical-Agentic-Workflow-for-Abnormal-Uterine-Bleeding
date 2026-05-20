import json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "outputs" / "latest" / "summary"
FIGDATA = ROOT / "论文" / "figdata"
FIGDATA.mkdir(parents=True, exist_ok=True)


def _mean_min_max(series: pd.Series) -> dict:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return {"Mean": np.nan, "Min": np.nan, "Max": np.nan}
    return {"Mean": float(s.mean()), "Min": float(s.min()), "Max": float(s.max())}


def _find_by_substring(root: Path, substring: str) -> Path:
    for p in root.iterdir():
        if substring in p.name:
            return p
    raise FileNotFoundError(substring)


def summarize_algo_metrics() -> pd.DataFrame:
    algo = pd.read_csv(SUMMARY / "algorithmic_metrics_summary_en.csv")
    metric_cols = {
        "D1 Check Match Rate (case mean)": "D1检查匹配率(病例均值)",
        "D2 Check Match Rate (case mean)": "D2检查匹配率(病例均值)",
        "D1 Loop Inefficiency (0-match)": "D1无效循环率(0匹配)",
        "D2 Loop Inefficiency (0-match)": "D2无效循环率(0匹配)",
        "Gate1 Flow Pass Rate": "Gate1流程通过率",
        "Gate2 Flow Pass Rate": "Gate2流程通过率",
        "Gate1 Judge Pass Rate": "Gate1 Judge通过率",
        "Gate2 Judge Pass Rate": "Gate2 Judge通过率",
        "D1 Judge Overall Score": "D1 Judge总分",
        "D2 Judge Overall Score": "D2 Judge总分",
        "D3 Judge Overall Score": "D3 Judge总分",
        "D4 Judge Overall Score": "D4 Judge总分",
        "D1 Diagnosis Score": "D1诊断评分",
        "D1 Check Match Score": "D1检查匹配评分",
        "D1 Check Match Degree": "D1检查匹配度",
        "D2 Revised Dx Score": "D2修正诊断评分",
        "D2 Surgery Plan Score": "D2手术方案评分",
        "D3 Diagnosis Score": "D3最终诊断评分",
        "D3 Post-op Plan Score": "D3术后方案评分",
        "D4 Rehab Score": "D4康复计划评分",
        "D4 Follow-up Score": "D4随访计划评分",
    }
    rows = []
    for col, label in metric_cols.items():
        stats = _mean_min_max(algo[col])
        rows.append({"Metric": label, **stats})
    return pd.DataFrame(rows)


def summarize_stage_table(path: Path, out_name: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    stages = [c for c in df.columns if c != "Model"]
    rows = []
    for stage in stages:
        stats = _mean_min_max(df[stage])
        rows.append({"Stage": stage, **stats})
    out = pd.DataFrame(rows)
    out.to_csv(FIGDATA / out_name, index=False, encoding="utf-8-sig")
    return out


def summarize_simple_stage_avg(path: Path, out_name: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = df.columns.tolist()
    stage_col = cols[0]
    mean_col = cols[1] if len(cols) > 1 else cols[0]
    n_col = cols[2] if len(cols) > 2 else None
    out = df[[stage_col, mean_col] + ([n_col] if n_col else [])].copy()
    out.columns = ["Stage", "Mean"] + (["N"] if n_col else [])
    out.to_csv(FIGDATA / out_name, index=False, encoding="utf-8-sig")
    return out


def summarize_d4_completion() -> dict:
    df = pd.read_csv(SUMMARY / "tmp_flow_d4_completion.csv")
    total_col = df.columns[1]
    done_col = df.columns[2]
    total = pd.to_numeric(df[total_col], errors="coerce").sum()
    done = pd.to_numeric(df[done_col], errors="coerce").sum()
    rate = float(done / total) if total else np.nan
    return {"D4_total": int(total), "D4_done": int(done), "D4_completion": rate}


def summarize_calibration() -> pd.DataFrame:
    df = pd.read_csv(SUMMARY / "calibration_summary_en.csv")
    out = df.groupby("Stage")[["Accuracy", "ECE"]].mean(numeric_only=True).reset_index()
    out.to_csv(FIGDATA / "calibration_stage_avg.csv", index=False, encoding="utf-8-sig")
    return out


def summarize_special_d1() -> pd.DataFrame:
    df = pd.read_csv(SUMMARY / "special_d1_case_counts_en.csv")
    out = df.groupby(["Center", "Model"], as_index=False)["Special Rate"].mean()
    out.to_csv(FIGDATA / "special_d1_case_rates.csv", index=False, encoding="utf-8-sig")
    return out


def summarize_small_llm_metrics() -> pd.DataFrame:
    # find the small-summary xlsx with unicode name
    key = "llm_results_gemini-3-pro-preview-thinking__gala_api_"
    key2 = "\u6c47\u603b"
    p = next(p for p in SUMMARY.iterdir() if key in p.name and key2 in p.name and p.suffix.lower() == ".xlsx")
    xl = pd.ExcelFile(p)
    rows = []

    def _weighted_mean(df: pd.DataFrame, value_col: str, n_col: str) -> float:
        v = pd.to_numeric(df[value_col], errors="coerce")
        n = pd.to_numeric(df[n_col], errors="coerce")
        mask = v.notna() & n.notna()
        if not mask.any():
            return float("nan")
        return float((v[mask] * n[mask]).sum() / n[mask].sum())

    # TopK
    df = xl.parse("诊断TopK语义命中_小规模汇总")
    rows.append({"Metric": "TopK@1", "Mean": _weighted_mean(df, "小规模_k=1命中(任一GT)(0/1)_均值", "小规模_样本数")})
    rows.append({"Metric": "TopK@3", "Mean": _weighted_mean(df, "小规模_k=3命中(任一GT)(0/1)_均值", "小规模_样本数")})
    rows.append({"Metric": "TopK@5", "Mean": _weighted_mean(df, "小规模_k=5命中(任一GT)(0/1)_均值", "小规模_样本数")})

    # Diagnosis quality
    df = xl.parse("诊断质量_小规模汇总")
    rows.append({"Metric": "Diagnosis Accuracy", "Mean": _weighted_mean(df, "小规模_准确性(0-1)_均值", "小规模_样本数")})
    rows.append({"Metric": "Diagnosis Reasonableness", "Mean": _weighted_mean(df, "小规模_合理性(0-1)_均值", "小规模_样本数")})
    rows.append({"Metric": "Diagnosis Logic", "Mean": _weighted_mean(df, "小规模_逻辑性(0-1)_均值", "小规模_样本数")})

    # Unmatched checks
    df = xl.parse("未匹配检查合理性_小规模汇总")
    rows.append({"Metric": "Unmatched Check Meaningful", "Mean": _weighted_mean(df, "小规模_是否仍有临床意义(0/1)_均值", "小规模_样本数")})
    rows.append({"Metric": "Unmatched Check Redundant", "Mean": _weighted_mean(df, "小规模_是否冗余(0/1)_均值", "小规模_样本数")})

    # Rationale chain
    df = xl.parse("推理证据链质量_小规模汇总")
    rows.append({"Metric": "Rationale Chain Quality", "Mean": _weighted_mean(df, "小规模_得分(0-1)_均值", "小规模_样本数")})

    # Fact consistency
    df = xl.parse("事实一致性与信息丢失_小规模汇总")
    rows.append({"Metric": "Fact Consistency", "Mean": _weighted_mean(df, "小规模_一致性得分(0-1)_均值", "小规模_样本数")})
    rows.append({"Metric": "Information Missing", "Mean": _weighted_mean(df, "小规模_信息丢失率(0-1)_均值", "小规模_样本数")})
    rows.append({"Metric": "Fact Overall", "Mean": _weighted_mean(df, "小规模_综合得分(0-1)_均值", "小规模_样本数")})

    # Plan quality
    df = xl.parse("方案质量_小规模汇总")
    rows.append({"Metric": "Plan Overall", "Mean": _weighted_mean(df, "小规模_综合得分(0-1)_均值", "小规模_样本数")})

    # Diagnosis bias
    df = xl.parse("诊断偏向性_小规模汇总")
    rows.append({"Metric": "Diagnosis Bias Degree", "Mean": _weighted_mean(df, "小规模_偏向程度(0-5)_均值", "小规模_样本数")})

    # Rehab/followup
    df = xl.parse("康复-随访计划质量_小规模汇总")
    rows.append({"Metric": "Rehab/Followup Overall", "Mean": _weighted_mean(df, "小规模_综合得分(0-1)_均值", "小规模_样本数")})

    out = pd.DataFrame(rows)
    out.to_csv(FIGDATA / "llm_small_metrics_weighted.csv", index=False, encoding="utf-8-sig")
    return out


def summarize_issue_files() -> dict:
    # parse parse errors and issue list
    parse_key = "\u89e3\u6790\u5f02\u5e38"  # 解析异常
    issues_key = "\u95ee\u9898\u6e05\u5355"  # 问题清单
    parse_p = _find_by_substring(SUMMARY, parse_key)
    issues_p = _find_by_substring(SUMMARY, issues_key)
    parse_df = pd.read_csv(parse_p)
    issues_df = pd.read_csv(issues_p)
    parse_df.to_csv(FIGDATA / "parse_errors_raw.csv", index=False, encoding="utf-8-sig")
    issues_df.to_csv(FIGDATA / "issue_list_raw.csv", index=False, encoding="utf-8-sig")

    parse_breakdown = parse_df.groupby(["来源(医生/裁判)", "工作表", "异常类型"]).size().reset_index(name="Count")
    parse_breakdown.to_csv(FIGDATA / "parse_error_breakdown.csv", index=False, encoding="utf-8-sig")

    issue_cols = [c for c in ["中心", "模型", "需要复核_检查匹配(行数)", "状态疑点(行数)", "解析异常(条数)"] if c in issues_df.columns]
    issues_df[issue_cols].to_csv(FIGDATA / "issues_summary.csv", index=False, encoding="utf-8-sig")

    return {
        "parse_errors": int(len(parse_df)),
        "issue_rows": int(len(issues_df)),
        "issue_check_match": int(pd.to_numeric(issues_df.get("需要复核_检查匹配(行数)", pd.Series([0]*len(issues_df))), errors="coerce").fillna(0).sum()),
        "issue_status": int(pd.to_numeric(issues_df.get("状态疑点(行数)", pd.Series([0]*len(issues_df))), errors="coerce").fillna(0).sum()),
        "issue_parse": int(pd.to_numeric(issues_df.get("解析异常(条数)", pd.Series([0]*len(issues_df))), errors="coerce").fillna(0).sum()),
    }


def summarize_mismatch_cases() -> dict:
    d1 = pd.read_csv(SUMMARY / "d1_gate1_mismatch_cases.csv")
    d2 = pd.read_csv(SUMMARY / "d2_gate2_block_cases.csv")
    return {"d1_mismatch_cases": int(len(d1)), "d2_block_cases": int(len(d2))}


def main() -> None:
    metrics = summarize_algo_metrics()
    metrics.to_csv(FIGDATA / "algorithmic_metrics_overall.csv", index=False, encoding="utf-8-sig")

    # Stage-level summaries
    summarize_stage_table(SUMMARY / "tmp_ai_result_quality_by_model.csv", "ai_result_quality_stage_summary.csv")
    summarize_stage_table(SUMMARY / "tmp_manual_result_quality_by_model.csv", "manual_result_quality_stage_summary.csv")
    summarize_stage_table(SUMMARY / "tmp_ai_reasoning_quality_by_model.csv", "ai_reasoning_quality_stage_summary.csv")
    summarize_stage_table(SUMMARY / "tmp_manual_reasoning_quality_by_model.csv", "manual_reasoning_quality_stage_summary.csv")

    summarize_simple_stage_avg(SUMMARY / "tmp_llm_reasoning_stage_avg.csv", "llm_reasoning_stage_avg.csv")
    summarize_simple_stage_avg(SUMMARY / "tmp_consistency_stage_avg.csv", "consistency_stage_avg.csv")
    summarize_simple_stage_avg(SUMMARY / "tmp_memory_stage_avg.csv", "memory_stage_avg.csv")

    d4_stats = summarize_d4_completion()
    cal = summarize_calibration()
    summarize_special_d1()
    small = summarize_small_llm_metrics()
    issues = summarize_issue_files()
    mismatch = summarize_mismatch_cases()

    snapshot = {
        "d4_completion": d4_stats,
        "calibration_stage_avg": cal.to_dict(orient="records"),
        "small_metrics": small.to_dict(orient="records"),
        **issues,
        **mismatch,
    }
    (FIGDATA / "results_metrics_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
