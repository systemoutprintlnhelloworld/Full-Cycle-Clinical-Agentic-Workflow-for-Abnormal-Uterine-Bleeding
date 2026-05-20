from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd
from openpyxl import load_workbook

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from llm_judge_metrics.status import detect_d1_skipped_to_d2


def _parse_model_from_stem(stem: str, suffix: str) -> str:
    name = stem.replace("Evaluation_Summary_", "")
    if suffix in name:
        name = name.replace(suffix, "")
    return name


def _backup_file(path: Path, backup_root: Path, stamp: str, backed_up: set[Path]) -> None:
    if path in backed_up:
        return
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / f"{path.stem}_{stamp}{path.suffix}"
    if backup_path.exists():
        idx = 1
        while True:
            candidate = backup_root / f"{path.stem}_{stamp}_{idx}{path.suffix}"
            if not candidate.exists():
                backup_path = candidate
                break
            idx += 1
    shutil.copy2(path, backup_path)
    backed_up.add(path)


def _build_gate3_fail_map(data_root: Path) -> dict[tuple[str, str], set[str]]:
    gate3_map: dict[tuple[str, str], set[str]] = {}
    for center_dir in data_root.iterdir():
        if not center_dir.is_dir():
            continue
        name = center_dir.name.lower()
        if name.startswith(("backup", "bkup", "archive", "tmp")):
            continue
        center = center_dir.name
        judge_dir = center_dir / "judge agent"
        if not judge_dir.exists():
            continue
        for path in judge_dir.glob("Evaluation_Summary_*_CN_Judge_Parsed.xlsx"):
            model = _parse_model_from_stem(path.stem, "_CN_Judge_Parsed")
            try:
                d3 = pd.read_excel(path, sheet_name="D3_Surgery_Decision")
            except Exception:
                continue
            if d3.empty or "Gate3_不通过标记" not in d3.columns:
                continue
            cid_col = d3.columns[0]
            gate3 = pd.to_numeric(d3["Gate3_不通过标记"], errors="coerce")
            fail_ids = d3.loc[gate3 == 1, cid_col].astype(str).str.strip()
            gate3_map[(center, model)] = {cid for cid in fail_ids if cid}
    return gate3_map


def _load_doctor_special_cases(doctor_root: Path) -> dict[tuple[str, str], set[str]]:
    special_map: dict[tuple[str, str], set[str]] = {}
    if not doctor_root.exists():
        return special_map
    for path in doctor_root.rglob("*.xlsx"):
        if path.name.startswith("~$"):
            continue
        parts = [p.lower() for p in path.parts]
        if any(p.startswith("bkup") for p in parts):
            continue
        try:
            df = pd.read_excel(path, sheet_name="评分覆盖率")
        except Exception:
            continue
        if df.empty or "术后_状态" not in df.columns:
            continue
        mask = df["术后_状态"].astype(str).str.contains("流程终止于入院决策", na=False)
        if not mask.any():
            continue
        sub = df.loc[mask, ["中心", "模型名称", "病例ID"]]
        for _, row in sub.iterrows():
            center = str(row.get("中心", "")).strip()
            model = str(row.get("模型名称", "")).strip()
            cid = str(row.get("病例ID", "")).strip()
            if not (center and model and cid):
                continue
            special_map.setdefault((center, model), set()).add(cid)
    return special_map


def _build_special_case_map(data_root: Path, doctor_root: Path | None = None) -> dict[tuple[str, str], set[str]]:
    special_map: dict[tuple[str, str], set[str]] = {}
    doctor_special = _load_doctor_special_cases(doctor_root) if doctor_root else {}
    for center_dir in data_root.iterdir():
        if not center_dir.is_dir():
            continue
        name = center_dir.name.lower()
        if name.startswith(("backup", "bkup", "archive", "tmp")):
            continue
        center = center_dir.name
        doc_dir = center_dir / "doc agent"
        if not doc_dir.exists():
            continue
        for path in doc_dir.glob("Evaluation_Summary_*_CN_Parsed.xlsx"):
            model = _parse_model_from_stem(path.stem, "_CN_Parsed")
            special_cases: set[str] = set()
            special_sheet_present = False
            try:
                xl = pd.ExcelFile(path)
                for sheet in ["D2_Admission_Decision_特殊D1", "D2_Admission_Loop_特殊D1", "D1_Outpatient_Loop_特殊D1"]:
                    if sheet not in xl.sheet_names:
                        continue
                    special_sheet_present = True
                    df_special = xl.parse(sheet)
                    if df_special.empty:
                        continue
                    cid_col = df_special.columns[0]
                    ids = df_special[cid_col].dropna().astype(str).str.strip().tolist()
                    special_cases.update({cid for cid in ids if cid})
            except Exception:
                special_cases = set()
            if not special_sheet_present and not special_cases:
                try:
                    d1_loop = pd.read_excel(path, sheet_name="D1_Outpatient_Loop")
                    d1_dec = pd.read_excel(path, sheet_name="D1_Outpatient_Decision")
                    d2_loop = pd.read_excel(path, sheet_name="D2_Admission_Loop")
                    d2_dec = pd.read_excel(path, sheet_name="D2_Admission_Decision")
                except Exception:
                    continue
                doc_sheets = {
                    "D1_Outpatient_Loop": d1_loop,
                    "D1_Outpatient_Decision": d1_dec,
                    "D2_Admission_Loop": d2_loop,
                    "D2_Admission_Decision": d2_dec,
                }
                special_cases = detect_d1_skipped_to_d2(doc_sheets)
            if not special_sheet_present and not special_cases:
                special_cases = doctor_special.get((center, model), set())
            special_map[(center, model)] = {str(cid).strip() for cid in special_cases if str(cid).strip()}
    return special_map


def _clear_rows(df: pd.DataFrame, mask: pd.Series, keep_cols: set[str]) -> None:
    for col in df.columns:
        if col in keep_cols:
            continue
        df.loc[mask, col] = pd.NA
    if "状态" in df.columns:
        df.loc[mask, "状态"] = "未经过"


def _split_data_workbook(path: Path, special_ids: set[str], gate3_fail_ids: set[str]) -> None:
    target_sheets = ["D1_Outpatient_Loop", "D2_Admission_Loop", "D2_Admission_Decision"]
    xl = pd.ExcelFile(path)
    with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        for sheet in target_sheets:
            if sheet not in xl.sheet_names:
                continue
            df = xl.parse(sheet)
            if df.empty:
                continue
            cid_col = df.columns[0]
            mask = df[cid_col].astype(str).str.strip().isin(special_ids)
            if sheet == "D1_Outpatient_Loop":
                special_df = df.loc[mask].copy()
                normal_df = df.copy()
                normal_df.to_excel(writer, sheet_name=sheet, index=False)
                special_sheet_name = f"{sheet}_特殊D1"
                if not special_df.empty:
                    special_df.to_excel(writer, sheet_name=special_sheet_name, index=False)
                else:
                    pd.DataFrame(columns=df.columns).to_excel(writer, sheet_name=special_sheet_name, index=False)
                continue
            normal_df = df.loc[~mask].copy()
            normal_df.to_excel(writer, sheet_name=sheet, index=False)
            if sheet == "D2_Admission_Decision":
                special_df = df.loc[mask].copy()
                special_sheet_name = f"{sheet}_特殊D1"
                if not special_df.empty:
                    special_df.to_excel(writer, sheet_name=special_sheet_name, index=False)
                else:
                    pd.DataFrame(columns=df.columns).to_excel(writer, sheet_name=special_sheet_name, index=False)

        if gate3_fail_ids and "D4_Rehab_Plan" in xl.sheet_names:
            df4 = xl.parse("D4_Rehab_Plan")
            if not df4.empty:
                cid_col = df4.columns[0]
                mask4 = df4[cid_col].astype(str).str.strip().isin(gate3_fail_ids)
                df4 = df4.copy()
                special_df4 = df4.loc[mask4].copy()
                if mask4.any():
                    keep_cols = {cid_col, "状态"}
                    _clear_rows(df4, mask4, keep_cols)
                df4.to_excel(writer, sheet_name="D4_Rehab_Plan", index=False)
                if not special_df4.empty:
                    special_df4.to_excel(writer, sheet_name="D4_Rehab_Plan_Gate3不通过", index=False)
                else:
                    pd.DataFrame(columns=df4.columns).to_excel(
                        writer, sheet_name="D4_Rehab_Plan_Gate3不通过", index=False
                    )

    try:
        wb = load_workbook(path)
        for name in [s for s in wb.sheetnames if s.endswith("_正常")]:
            del wb[name]
        if "D2_Admission_Loop_特殊D1" in wb.sheetnames:
            del wb["D2_Admission_Loop_特殊D1"]
        wb.save(path)
    except Exception:
        pass


def _split_doctor_workbook(
    path: Path,
    special_triplets: set[tuple[str, str, str]],
    gate3_triplets: set[tuple[str, str, str]],
) -> None:
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return
    if len(xl.sheet_names) < 2:
        return
    score_sheet = "评分" if "评分" in xl.sheet_names else xl.sheet_names[0]
    cover_sheet = "评分覆盖率" if "评分覆盖率" in xl.sheet_names else xl.sheet_names[1]
    score_df = xl.parse(score_sheet)
    cover_df = xl.parse(cover_sheet)
    required = {"病例ID", "模型名称", "中心", "行号"}
    if not required.issubset(set(cover_df.columns)):
        return
    keys = list(
        zip(
            cover_df["中心"].astype(str),
            cover_df["模型名称"].astype(str),
            cover_df["病例ID"].astype(str).str.strip(),
        )
    )
    special_mask = pd.Series([k in special_triplets for k in keys], index=cover_df.index)
    special_cover = cover_df.loc[special_mask].copy()
    normal_cover = cover_df.loc[~special_mask].copy()

    cover_cols = ["行号", "模型名称", "中心", "病例ID"]
    cover_cols += [c for c in cover_df.columns if c not in cover_cols]
    cover_df = cover_df.loc[:, cover_cols]

    merged_score = score_df.merge(
        cover_df,
        on=["行号", "模型名称"],
        how="left",
        suffixes=("", "_覆盖率"),
    )
    special_mask = pd.Series(
        [
            (
                str(row.get("中心", "")).strip(),
                str(row.get("模型名称", "")).strip(),
                str(row.get("病例ID", "")).strip(),
            )
            in special_triplets
            for _, row in merged_score.iterrows()
        ],
        index=merged_score.index,
    )
    score_special = merged_score.loc[special_mask].copy()
    score_normal = merged_score.loc[~special_mask].copy()

    base_cols = [c for c in ["行号", "模型名称", "评分状态", "中心", "病例ID"] if c in merged_score.columns]

    def stage_cols(prefix: str) -> list[str]:
        return [c for c in merged_score.columns if str(c).startswith(prefix)]

    def mask_to_columns(df: pd.DataFrame, keep: set[str]) -> pd.DataFrame:
        masked = df.copy()
        for col in masked.columns:
            if col not in keep:
                masked[col] = pd.NA
        return masked

    d1_loop_keep = set(base_cols + stage_cols("门诊A"))
    d2_dec_keep = set(base_cols + stage_cols("住院B"))
    d4_keep = set(base_cols + stage_cols("康复"))

    score_d1_loop_special = mask_to_columns(score_special, d1_loop_keep)
    score_d2_dec_special = mask_to_columns(score_special, d2_dec_keep)

    gate3_mask = pd.Series(
        [
            (str(row.get("中心", "")).strip(), str(row.get("模型名称", "")).strip(), str(row.get("病例ID", "")).strip())
            in gate3_triplets
            for _, row in merged_score.iterrows()
        ],
        index=merged_score.index,
    )
    score_d4_gate3 = mask_to_columns(merged_score.loc[gate3_mask].copy(), d4_keep)

    with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        score_special.to_excel(writer, sheet_name="评分_D2特殊", index=False)
        score_normal.to_excel(writer, sheet_name="评分_D2正常", index=False)
        score_d1_loop_special.to_excel(writer, sheet_name="评分_D1特殊_门诊A", index=False)
        score_d2_dec_special.to_excel(writer, sheet_name="评分_D1特殊_住院B", index=False)
        score_d4_gate3.to_excel(writer, sheet_name="评分_D4Gate3不通过", index=False)

    try:
        wb = load_workbook(path)
        for name in ["评分覆盖率_D2特殊", "评分覆盖率_D2正常"]:
            if name in wb.sheetnames:
                del wb[name]
        wb.save(path)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Split D1 special cases into separate sheets.")
    parser.add_argument("--data-root", default="data", help="Data root directory.")
    parser.add_argument(
        "--doctor-root",
        default=None,
        help="Doctor review root directory (default: <project_root_parent>/医生评测结果).",
    )
    parser.add_argument("--skip-doctor", action="store_true", help="Skip splitting doctor review workbooks.")
    parser.add_argument("--skip-data", action="store_true", help="Skip splitting data workbooks.")
    parser.add_argument("--center", default=None, help="Only process a specific center.")
    parser.add_argument("--model", default=None, help="Only process a specific model.")
    parser.add_argument("--doctor-include", default=None, help="Substring filter for doctor files.")
    parser.add_argument("--doctor-exclude", default=None, help="Substring exclude for doctor files.")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    project_root = Path(__file__).resolve().parents[2]
    doctor_root = Path(args.doctor_root) if args.doctor_root else project_root.parent / "医生评测结果"
    backup_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backed_up: set[Path] = set()

    special_map = _build_special_case_map(data_root, doctor_root)
    gate3_map = _build_gate3_fail_map(data_root)
    special_triplets: set[tuple[str, str, str]] = set()
    gate3_triplets: set[tuple[str, str, str]] = set()
    for (center, model), ids in special_map.items():
        for cid in ids:
            special_triplets.add((center, model, cid))
    for (center, model), ids in gate3_map.items():
        for cid in ids:
            gate3_triplets.add((center, model, cid))

    # Split doc/judge data
    if not args.skip_data:
        for center_dir in data_root.iterdir():
            if not center_dir.is_dir():
                continue
            name = center_dir.name.lower()
            if name.startswith(("backup", "bkup", "archive", "tmp")):
                continue
            center = center_dir.name
            if args.center and center != args.center:
                continue
            for agent, suffix in [("doc agent", "_CN_Parsed"), ("judge agent", "_CN_Judge_Parsed")]:
                agent_dir = center_dir / agent
                if not agent_dir.exists():
                    continue
                for path in agent_dir.glob(f"Evaluation_Summary_*{suffix}.xlsx"):
                    model = _parse_model_from_stem(path.stem, suffix)
                    if args.model and model != args.model:
                        continue
                    special_ids = special_map.get((center, model), set())
                    gate3_ids = gate3_map.get((center, model), set())
                    backup_root = agent_dir / f"bkup_{backup_stamp}"
                    _backup_file(path, backup_root, backup_stamp, backed_up)
                    _split_data_workbook(path, special_ids, gate3_ids)

    # Split doctor scoring
    if not args.skip_doctor and doctor_root.exists():
        for path in doctor_root.rglob("*.xlsx"):
            if path.name.startswith("~$"):
                continue
            parts = [p.lower() for p in path.parts]
            if any(p.startswith("bkup") for p in parts):
                continue
            if args.doctor_include and args.doctor_include not in str(path):
                continue
            if args.doctor_exclude and args.doctor_exclude in str(path):
                continue
            backup_root = doctor_root / f"bkup_{backup_stamp}"
            _backup_file(path, backup_root, backup_stamp, backed_up)
            _split_doctor_workbook(path, special_triplets, gate3_triplets)

    # Write summary note (for downstream users)
    summary_dir = project_root / "outputs" / "latest" / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    md_path = summary_dir / "特殊病例隔离说明.md"
    md_lines = [
        "# 特殊病例隔离说明",
        "",
        "本次隔离优先使用 D2_Admission_Decision_特殊D1 工作表；若为空则回退到医生评分覆盖率“术后_状态=未经过（流程终止于入院决策）”；最后才回退到 D1未经过且直接进入D2 规则。",
        f"备份目录：data/*/doc agent 或 judge agent 下的 bkup_{backup_stamp}；医生评测结果目录下的 bkup_{backup_stamp}。",
        "",
        "已新增/覆盖的工作表：",
        "- data/*/doc agent 与 judge agent：",
        "  - D1_Outpatient_Loop：新增 D1_Outpatient_Loop_特殊D1（保留原字段，用于特殊D1门诊A计分）。",
        "  - D2_Admission_Loop：原表仅保留正常病例（不再拆D2 loop特殊）。",
        "  - D2_Admission_Decision：原表仅保留正常病例；新增 D2_Admission_Decision_特殊D1。",
        "  - D4_Rehab_Plan：Gate3_不通过标记=1 的病例被标记为未经过并清空评分列；新增 D4_Rehab_Plan_Gate3不通过。",
        "- 医生评测结果文件：",
        "  - 评分_D2特殊 / 评分_D2正常（已合并覆盖率列）",
        "  - 评分_D1特殊_门诊A / 评分_D1特殊_住院B",
        "  - 评分_D4Gate3不通过",
        "",
        "注意：D1特殊病例在 D1 loop 的评分保留在原表，同时在 D1_Outpatient_Loop_特殊D1 中提供额外核查。",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
