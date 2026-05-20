"""Extract Sankey figdata (detail + summary) with audit-friendly exclusions.

Source of truth for flow detail:
- outputs/latest/summary/医生评测汇总.xlsx -> sheet: 通过退出明细

Exclusion rules (per project requirements):
- D1 anomaly cases (d1_decision_anomalies) do not participate in calculations.
- For cases that fail at D3, their D4 stage does not participate in calculations.

Outputs:
- analysis_viz/data/derived/figdata/outputs_latest/sankey/Fig7__sankey_flow_source.xlsx
  - detail_all: raw flow detail (standardized columns)
  - detail_used: after exclusions/blanking
  - excluded_d1_anomaly
  - excluded_d3_fail_d4_blank
  - nodes_summary_used
  - links_summary_used
  - meta
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
RAW_DOCTOR_SUMMARY = ROOT / "analysis_viz" / "data" / "raw" / "医生评测汇总.xlsx"
RAW_METRICS_SOURCE = ROOT / "analysis_viz" / "data" / "raw" / "metrics_source_data.xlsx"

OUT_DIR = ROOT / "analysis_viz" / "data" / "derived" / "figdata" / "outputs_latest" / "sankey"
OUT_XLSX = OUT_DIR / "Fig7__sankey_flow_source.xlsx"


MODEL_SHORT = {
    "deepseek-v3-1-think-250821": "deepseek-v3",
    "gpt-5-2025-08-07": "gpt-5",
    "gemini-2.5-pro": "gemini-2.5p",
    "grok-4": "grok-4",
    "claude-opus-4-1-20250805-thinking": "claude-4.1",
}

STAGE_RENAME = {
    "D1_Loop": "门诊检查",
    "D1_Decision": "门诊决策",
    "D2_Loop": "入院检查",
    "D2_Decision": "入院决策",
    "D3_Decision": "术后康复",
    "D4_Plan": "随访计划",
}


def _is_d3_pass(value: str) -> bool:
    v = str(value or "")
    return ("通过一审" in v) or ("通过二审" in v)


def _build_nodes_summary(df_used: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for stage in STAGE_RENAME.values():
        counts = df_used[stage].fillna("").astype(str)
        counts = counts[counts.str.strip() != ""]
        vc = counts.value_counts()
        for label, n in vc.items():
            rows.append({"stage": stage, "label": label, "n_cases": int(n)})
    return pd.DataFrame(rows)


def _build_links_summary(df_used: pd.DataFrame) -> pd.DataFrame:
    stages = list(STAGE_RENAME.values())
    rows: list[dict[str, object]] = []
    for a, b in zip(stages[:-1], stages[1:]):
        sub = df_used[[a, b]].copy()
        sub[a] = sub[a].fillna("").astype(str)
        sub[b] = sub[b].fillna("").astype(str)
        sub = sub[(sub[a].str.strip() != "") & (sub[b].str.strip() != "")]
        if sub.empty:
            continue
        grouped = sub.groupby([a, b], dropna=False).size().reset_index(name="n_cases")
        grouped.insert(0, "from_stage", a)
        grouped.insert(1, "to_stage", b)
        grouped.rename(columns={a: "from_label", b: "to_label"}, inplace=True)
        rows.extend(grouped.to_dict(orient="records"))
    return pd.DataFrame(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df_flow = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="通过退出明细")
    df_flow = df_flow.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    df_flow["model_short"] = df_flow["model"].map(MODEL_SHORT).fillna(df_flow["model"].astype(str))

    # Rename stage columns to unified paper naming
    for k, v in STAGE_RENAME.items():
        if k in df_flow.columns:
            df_flow.rename(columns={k: v}, inplace=True)

    # D1 anomalies list
    df_d1 = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="d1_decision_anomalies")
    d1_set = set(zip(df_d1["center"].astype(str), df_d1["model"].astype(str), df_d1["case_id"].astype(str)))
    key_series = list(zip(df_flow["center"].astype(str), df_flow["model"].astype(str), df_flow["case_id"].astype(str)))
    df_flow["is_d1_anomaly"] = [k in d1_set for k in key_series]

    excluded_d1 = df_flow[df_flow["is_d1_anomaly"]].copy()
    df_used = df_flow[~df_flow["is_d1_anomaly"]].copy()

    # D3 fail => D4 blank (do not participate in D4 computations)
    d3_col = STAGE_RENAME["D3_Decision"]
    d4_col = STAGE_RENAME["D4_Plan"]
    d3_pass = df_used[d3_col].apply(_is_d3_pass)
    excluded_d3_fail = df_used[~d3_pass].copy()
    df_used.loc[~d3_pass, d4_col] = ""

    nodes_summary = _build_nodes_summary(df_used)
    links_summary = _build_links_summary(df_used)

    meta = pd.DataFrame(
        [
            {"key": "raw_flow_rows", "value": int(len(df_flow))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "used_rows", "value": int(len(df_used))},
            {"key": "d3_fail_rows_d4_blank", "value": int(len(excluded_d3_fail))},
            {"key": "rule_d1", "value": "D1 anomaly cases excluded from calculations"},
            {"key": "rule_gate3_d4", "value": "D3 fail cases: D4 blanked so not counted"},
        ]
    )

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        df_flow.to_excel(writer, sheet_name="detail_all", index=False)
        df_used.to_excel(writer, sheet_name="detail_used", index=False)
        excluded_d1.to_excel(writer, sheet_name="excluded_d1_anomaly", index=False)
        excluded_d3_fail.to_excel(writer, sheet_name="excluded_d3_fail_d4_blank", index=False)
        nodes_summary.to_excel(writer, sheet_name="nodes_summary_used", index=False)
        links_summary.to_excel(writer, sheet_name="links_summary_used", index=False)
        meta.to_excel(writer, sheet_name="meta", index=False)


if __name__ == "__main__":
    main()

