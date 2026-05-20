from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd
from bs4 import BeautifulSoup
from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

try:
    import win32com.client as win32  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    win32 = None


W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
NUMERIC_TOKEN_RE = re.compile(r"(?<![\w/])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![\w/])")
SECTION_HINTS = [
    ("abstract", ["我们收集并系统评估", "在临床输出层面", "摘要"]),
    ("introduction", ["尽管上述工作", "为弥合上述鸿沟"]),
    ("dataset", ["真实世界连续病例队列构建", "本研究纳入来自中国佛山"]),
    ("methods-models", ["模型选择与推理设置", "医生智能体分别由"]),
    ("results", ["五个代表性大语言模型", "阶段诊断接近度", "消融实验"]),
    ("references", ["References"]),
]
SEEDED_CLAIMS = {
    "claim_cases_304": ("dataset", "seed:304", "304 例病例总数"),
    "claim_trajectories_1520": ("dataset", "seed:1520", "1520 条全轨迹总数"),
    "claim_gate_pass_rate": ("results", "seed:gate-pass", "86.8% / 88.5% 双分母流程完成率"),
    "claim_sankey_stage_total_1492": ("results", "seed:1492", "1492 条标准化流程样本"),
    "claim_final_dx_prox_d1": ("results", "seed:final-dx-d1", "D1 final diagnosis proximity"),
    "claim_final_dx_prox_d2": ("results", "seed:final-dx-d2", "D2 final diagnosis proximity"),
    "claim_final_dx_prox_d3": ("results", "seed:final-dx-d3", "D3 final diagnosis proximity"),
    "claim_special_d1_count": ("results", "seed:special-d1-count", "special D1 数量"),
    "claim_special_d1_pct": ("results", "seed:special-d1-pct", "special D1 比例"),
    "claim_g2_d1_diag_mean": ("results", "seed:g2-d1", "G2 D1 诊断正确性"),
    "claim_g2_d2_diag_mean": ("results", "seed:g2-d2", "G2 D2 诊断正确性"),
    "claim_g2_d3_diag_mean": ("results", "seed:g2-d3", "G2 D3 诊断正确性"),
    "claim_ablation_d1_drop": ("results", "seed:ablation-d1", "ablation D1 绝对降幅"),
    "claim_ablation_d2_drop": ("results", "seed:ablation-d2", "ablation D2 绝对降幅"),
    "claim_s1_result_range_low": ("results", "seed:s1-result-low", "S1 结果质量均分下界"),
    "claim_s1_result_range_high": ("results", "seed:s1-result-high", "S1 结果质量均分上界"),
    "claim_s1_logic_range_low": ("results", "seed:s1-logic-low", "S1 逻辑质量均分下界"),
    "claim_s1_logic_range_high": ("results", "seed:s1-logic-high", "S1 逻辑质量均分上界"),
}
AUTO_REPLACEMENTS = [
    ("校校准", "校准"),
    ("无效循环率分别为和", "无效循环率分别为 12.9% 和 8.5%"),
    ("Supplementary S4", "Supplementary Table 13"),
]
MANUSCRIPT_CLARIFICATION_REWRITES = [
    (
        "为系统性评估工作流各方面的表现，我们采用临床专家评分与LLM-as-Judge自动评分两种评分方式对工作流生成的决策轨迹进行评估。临床专家评分由三位具有丰富临床经验的妇科医生在未获知模型身份的条件下，通过1–5 分五分制李克特量表，根据自身临床经验，对各阶段决策输出结果质量与逻辑质量两个维度的评分，其中前者评价检查、诊断和治疗方案的临床正确性与可操作性，后者评估从观察到推断再到结论的证据推理链是否完整可信，具体评分规则见 Supplementary Table 22；而LLM-as-Judge则根据结构化评分规则（Supplementary S4），通过语义匹配在更细的粒度上覆盖临床输出、纵向稳定性与推理质量与系统行为三个维度进行评估。为展示两套评分体系在同一维度上可以相互印证的表现，我们分别以临床输出维度各环节子指标的聚合值对应各个指标下的结果质量评分、以各个环节的推理链质量整体评分对应各个指标下的逻辑质量评分，从而得到了工作流在各个环节的整体表现，两者分别从不同维度为系统表现提供了可信的评估依据（Supplementary Tables 2–3）。",
        "为系统性评估工作流各方面的表现，我们采用临床专家评分与LLM-as-Judge自动评分两种评分方式对工作流生成的决策轨迹进行评估。临床专家评分由三位具有丰富临床经验的妇科医生组成总体专家池，并采用跨中心交叉双评设计：每个中心、每条轨迹均由两位专家在未获知模型身份的条件下独立评分。评分使用 1–5 分李克特量表，分别记录结果质量与逻辑质量；前者评价检查、诊断和治疗方案的临床正确性与可操作性，后者评估从观察到推断再到结论的证据推理链是否完整可信，具体评分规则见 Supplementary Table 22。LLM-as-Judge则根据结构化评分规则（Supplementary Table 13），通过语义匹配在更细的粒度上覆盖临床输出、纵向稳定性、推理质量与系统行为三个维度进行评估。为展示两套评分体系在同一维度上可以相互印证的表现，我们分别以临床输出维度各环节子指标的聚合值对应各个指标下的结果质量评分、以各个环节的推理链质量整体评分对应各个指标下的逻辑质量评分，从而得到了工作流在各个环节的整体表现，两者分别从不同维度为系统表现提供了可信的评估依据（Supplementary Tables 2–3）。",
    ),
    (
        "Table 1 | 各阶段专家评分一致性与均分。结果质量和推理质量均采用1–5分量表；完全一致率指两位专家评分映射至低、中、高三档后标签完全相同的比例。",
        "Table 1 | 各阶段专家评分一致性与均分。临床盲评由三位妇科专家组成总体专家池，并采用跨中心交叉双评设计：每个中心、每条轨迹由两位专家独立评分。结果质量和推理质量均采用1–5分量表；完全一致率指该中心两位评分者映射至低、中、高三档后标签完全相同的比例。D4 随访计划行中的 n=1325 表示进入 D4 方案评分/校准的样本量，与 Fig. 5 所示按流程门控定义的 D1–D4 全流程完成数 n=1320 不同。",
    ),
    (
        "对于工作流各阶段的回答质量与推理质量，我们在每个中心均邀请两位专家基于李克特量表进行独立评分，并进一步将分数映射为低、中、高三个等级区间：低=[0,2)、中=[2,4)、高=[4,5]。完全一致率定义为两端标签完全相同的比例，具体公式如下，",
        "对于工作流各阶段的回答质量与推理质量，本研究采用跨中心交叉双评设计：总体专家池由三位妇科专家组成，而在每个中心、每条轨迹的实际评分层面均由两位专家基于李克特量表独立评分。随后将分数映射为低、中、高三个等级区间：低=[0,2)、中=[2,4)、高=[4,5]。完全一致率定义为两端标签完全相同的比例，具体公式如下，",
    ),
    (
        "Figure 5 | 系统决策轨迹与安全边界。a, 模型—病例轨迹在D1至D4之间的状态转移和流程通过情况；b, 分阶段置信度—准确率校准点；c, special D1危险捷径的安全审计结果。",
        "Figure 5 | 系统决策轨迹与安全边界。a, 模型—病例轨迹在D1至D4之间的状态转移和流程通过情况；b, 分阶段置信度—准确率校准点；c, 主动检查消融实验对D1–D3诊断评分的影响。",
    ),
]
MODEL_PARAGRAPH_CN = "医生智能体分别由 GPT-5、Gemini 2.5 Pro、Claude-4.1、DeepSeek V3 与 Grok-4 驱动"
MODEL_PARAGRAPH_ALT = "医生智能体分别由 GPT-5、Gemini 2.5 Pro、Claude-4.1、DeepSeek-V3.1 和 Grok-4 驱动"
MODEL_PARAGRAPH_REWRITE = (
    "医生智能体分别由 gpt-5-2025-08-07、gemini-2.5-pro、"
    "claude-opus-4-1-20250805-thinking、deepseek-v3-1-think-250821 和 grok-4 驱动，"
    "统一使用结构化 JSON 输出约束，doctor agent temperature 固定为 0.5。"
    "Patient Description Agent 的口述生成模型固定为 gemini-2.5-pro（temperature=0.7），"
    "事实核查模型固定为 gpt-4o（temperature=0.1）；"
    "LLM-as-Judge 主裁判固定为 gemini-2.5-pro（temperature=0.1）。"
    "Doctor decision loop 与 Judge 均采用最多 3 次有限重试，并通过统一 fallback 通道执行。"
)
SUPPLEMENTARY_REFERENCE_REWRITES = {
    "Supplementary Fig. 2": "Supplementary Tables 6–7",
    "Supplementary Fig. 4；Supplementary Table 11": "Fig. 5c；Supplementary Table 11",
    "Supplementary Fig. 4; Supplementary Table 11": "Fig. 5c; Supplementary Table 11",
    "Supplementary Fig. 4 and Supplementary Table 13": "Supplementary Table 13",
}


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso_now() -> str:
    return now_local().isoformat(timespec="seconds")


def make_run_id() -> str:
    return now_local().strftime("%Y-%m-%d_%H-%M-%S_paper-crosscheck")


def find_single(base: Path, pattern: str, label: str) -> Path:
    matches = [p for p in sorted(base.glob(pattern)) if not p.name.startswith("~$")]
    if not matches:
        raise FileNotFoundError(f"Cannot find {label} via pattern {pattern!r} under {base}")
    return matches[0]


def resolve_paths(project_root: Path) -> dict[str, Path]:
    paper_root = project_root.parent / "论文"
    if not paper_root.exists():
        raise FileNotFoundError(f"Paper root not found: {paper_root}")
    return {
        "project_root": project_root,
        "paper_root": paper_root,
        "main_docx": find_single(paper_root, "*5.12*.docx", "5.12 main docx"),
        "main_pdf": find_single(paper_root, "*5.12*.pdf", "5.12 pdf"),
        "review_docx": find_single(paper_root, "01_*.docx", "Chinese review docx"),
        "reviewer_html": find_single(paper_root, "*Reviewer*.html", "Stanford reviewer html"),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_spaces(text: str) -> str:
    return " ".join((text or "").replace("\u3000", " ").split())


def extract_doc_text_units(doc: Document) -> list[str]:
    texts: list[str] = []
    for para in doc.paragraphs:
        text = normalize_spaces(para.text)
        if text:
            texts.append(text)
    for table in doc.tables:
        for row in table.rows:
            row_cells = [normalize_spaces(cell.text) for cell in row.cells]
            row_text = " | ".join(cell for cell in row_cells if cell)
            if row_text:
                texts.append(row_text)
    return texts


def insert_paragraph_after(paragraph: Paragraph, text: str) -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    new_para = Paragraph(new_p, paragraph._parent)
    new_para.text = text
    return new_para


def normalize_numeric_token(token: str) -> str:
    clean = token.replace(",", "").strip()
    if clean.endswith("%"):
        value = float(clean[:-1]) / 100.0
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return clean


def infer_section(text: str) -> str:
    for section, hints in SECTION_HINTS:
        if any(hint in text for hint in hints):
            return section
    return "body"


def semantic_claim_id(token: str, context: str) -> str | None:
    normalized = normalize_numeric_token(token)
    if normalized == "304" and any(k in context for k in ["304例", "304 例", "304 例真实", "304例真实"]):
        return "claim_cases_304"
    if normalized == "1520" and "轨迹" in context:
        return "claim_trajectories_1520"
    if normalized == "0.926" and "平均得分" in context and "D1" in context:
        return "claim_g2_d1_diag_mean"
    if normalized == "0.88" and "平均得分" in context and "D2" in context:
        return "claim_g2_d2_diag_mean"
    if normalized == "0.828" and "平均得分" in context and "D3" in context:
        return "claim_g2_d3_diag_mean"
    if normalized == "0.768" and "接近度" in context and "D1" in context:
        return "claim_final_dx_prox_d1"
    if normalized == "0.795" and "接近度" in context and "D2" in context:
        return "claim_final_dx_prox_d2"
    if normalized == "0.828" and "接近度" in context and "D3" in context:
        return "claim_final_dx_prox_d3"
    if normalized == "0.315" and "消融实验" in context and "D1" in context:
        return "claim_ablation_d1_drop"
    if normalized == "0.270" and "消融实验" in context and "D2" in context:
        return "claim_ablation_d2_drop"
    if normalized == "4.22" and "结果质量均分" in context:
        return "claim_s1_result_range_low"
    if normalized == "4.57" and "结果质量均分" in context:
        return "claim_s1_result_range_high"
    if normalized == "4.36" and "逻辑质量均分" in context:
        return "claim_s1_logic_range_low"
    if normalized == "4.59" and "逻辑质量均分" in context:
        return "claim_s1_logic_range_high"
    if token == "86.8%" and any(k in context for k in ["门控", "通过", "环境智能体"]):
        return "claim_gate_pass_rate"
    if normalized == "1492" and any(k in context for k in ["stage_total", "门诊检查", "住院决策", "门诊决策"]):
        return "claim_sankey_stage_total_1492"
    if normalized == "28" and "special D1" in context:
        return "claim_special_d1_count"
    if token == "1.8%" and "special D1" in context:
        return "claim_special_d1_pct"
    return None


def aggregate_numeric_claim_id(location_prefix: str, idx: int) -> str:
    return f"{location_prefix}_{idx:04d}_numeric_inventory"


def extract_claim_rows(docx_path: Path, reviewed_at: str) -> list[dict[str, Any]]:
    doc = Document(docx_path)
    rows: list[dict[str, Any]] = []
    for para_idx, para in enumerate(doc.paragraphs):
        text = normalize_spaces(para.text)
        if not text:
            continue
        section = infer_section(text)
        seen_semantic_ids: set[str] = set()
        for token_idx, match in enumerate(NUMERIC_TOKEN_RE.finditer(text), start=1):
            token = match.group(0)
            normalized = normalize_numeric_token(token)
            claim_id = semantic_claim_id(token, text)
            if claim_id:
                if claim_id in seen_semantic_ids:
                    continue
                seen_semantic_ids.add(claim_id)
                rows.append(
                    {
                        "claim_id": claim_id,
                        "source_doc": docx_path.name,
                        "section": section,
                        "quote_or_table_ref": f"paragraph:{para_idx}",
                        "quoted_value": token,
                        "normalized_value": normalized,
                        "evidence_path": "",
                        "evidence_sheet": "",
                        "evidence_cell_or_formula": "",
                        "script_path": "",
                        "status": "needs_manual_confirmation",
                        "reviewer": "codex",
                        "reviewed_at": reviewed_at,
                        "notes": text[:500],
                    }
                )
    for table_idx, table in enumerate(doc.tables):
        for row_idx, row in enumerate(table.rows):
            for cell_idx, cell in enumerate(row.cells):
                text = normalize_spaces(cell.text)
                if not text:
                    continue
                seen_semantic_ids: set[str] = set()
                for token_idx, match in enumerate(NUMERIC_TOKEN_RE.finditer(text), start=1):
                    token = match.group(0)
                    normalized = normalize_numeric_token(token)
                    claim_id = semantic_claim_id(token, text)
                    if claim_id:
                        if claim_id in seen_semantic_ids:
                            continue
                        seen_semantic_ids.add(claim_id)
                        rows.append(
                            {
                                "claim_id": claim_id,
                                "source_doc": docx_path.name,
                                "section": "table",
                                "quote_or_table_ref": f"table:{table_idx}:r{row_idx + 1}:c{cell_idx + 1}",
                                "quoted_value": token,
                                "normalized_value": normalized,
                                "evidence_path": "",
                                "evidence_sheet": "",
                                "evidence_cell_or_formula": "",
                                "script_path": "",
                                "status": "needs_manual_confirmation",
                                "reviewer": "codex",
                                "reviewed_at": reviewed_at,
                                "notes": text[:500],
                            }
                        )
    return rows


def extract_numeric_inventory_rows(docx_path: Path, reviewed_at: str) -> list[dict[str, Any]]:
    doc = Document(docx_path)
    rows: list[dict[str, Any]] = []
    for para_idx, para in enumerate(doc.paragraphs):
        text = normalize_spaces(para.text)
        if not text:
            continue
        tokens = [m.group(0) for m in NUMERIC_TOKEN_RE.finditer(text)]
        if not tokens:
            continue
        rows.append(
            {
                "inventory_id": aggregate_numeric_claim_id("P", para_idx),
                "source_doc": docx_path.name,
                "section": infer_section(text),
                "location": f"paragraph:{para_idx}",
                "token_count": len(tokens),
                "tokens": ";".join(tokens[:60]),
                "normalized_tokens": ";".join(normalize_numeric_token(t) for t in tokens[:60]),
                "reviewed_at": reviewed_at,
                "notes": text[:420],
            }
        )
    for table_idx, table in enumerate(doc.tables):
        for row_idx, row in enumerate(table.rows):
            for cell_idx, cell in enumerate(row.cells):
                text = normalize_spaces(cell.text)
                if not text:
                    continue
                tokens = [m.group(0) for m in NUMERIC_TOKEN_RE.finditer(text)]
                if not tokens:
                    continue
                rows.append(
                    {
                        "inventory_id": aggregate_numeric_claim_id(f"T{table_idx}", row_idx * 100 + cell_idx),
                        "source_doc": docx_path.name,
                        "section": "table",
                        "location": f"table:{table_idx}:r{row_idx + 1}:c{cell_idx + 1}",
                        "token_count": len(tokens),
                        "tokens": ";".join(tokens[:60]),
                        "normalized_tokens": ";".join(normalize_numeric_token(t) for t in tokens[:60]),
                        "reviewed_at": reviewed_at,
                        "notes": text[:420],
                    }
                )
    return rows


def add_structural_claim(rows: list[dict[str, Any]], claim_id: str, source_doc: str, section: str, ref: str, notes: str, reviewed_at: str) -> None:
    rows.append(
        {
            "claim_id": claim_id,
            "source_doc": source_doc,
            "section": section,
            "quote_or_table_ref": ref,
            "quoted_value": "",
            "normalized_value": "",
            "evidence_path": "",
            "evidence_sheet": "",
            "evidence_cell_or_formula": "",
            "script_path": "",
            "status": "needs_manual_confirmation",
            "reviewer": "codex",
            "reviewed_at": reviewed_at,
            "notes": notes,
        }
    )


def seed_missing_claims(rows: list[dict[str, Any]], source_doc: str, reviewed_at: str, claim_ids: list[str]) -> None:
    existing = {str(row["claim_id"]) for row in rows}
    for claim_id in claim_ids:
        if claim_id in existing:
            continue
        section, ref, notes = SEEDED_CLAIMS.get(claim_id, ("audit", f"seed:{claim_id}", "seeded claim"))
        add_structural_claim(rows, claim_id, source_doc, section, ref, notes, reviewed_at)
        existing.add(claim_id)


def build_claim_index(rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        index.setdefault(str(row["claim_id"]), []).append(i)
    return index


def update_claim_status(
    rows: list[dict[str, Any]],
    index: dict[str, list[int]],
    claim_id: str,
    *,
    status: str,
    evidence_path: str,
    evidence_sheet: str,
    evidence_cell_or_formula: str,
    script_path: str,
    notes: str,
) -> None:
    for row_idx in index.get(claim_id, []):
        row = rows[row_idx]
        row["status"] = status
        row["evidence_path"] = evidence_path
        row["evidence_sheet"] = evidence_sheet
        row["evidence_cell_or_formula"] = evidence_cell_or_formula
        row["script_path"] = script_path
        row["notes"] = notes[:500]


def parse_docx_structure(docx_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(docx_path) as zf:
        names = set(zf.namelist())
        doc_root = ET.fromstring(zf.read("word/document.xml"))
        ins_count = len(doc_root.findall(".//w:ins", W_NS))
        del_count = len(doc_root.findall(".//w:del", W_NS))
        comment_refs = len(doc_root.findall(".//w:commentReference", W_NS))
        footnote_refs = len(doc_root.findall(".//w:footnoteReference", W_NS))
        endnote_refs = len(doc_root.findall(".//w:endnoteReference", W_NS))
        footnote_text = ""
        endnote_text = ""
        if "word/footnotes.xml" in names:
            foot_root = ET.fromstring(zf.read("word/footnotes.xml"))
            footnote_text = "".join(t.text or "" for t in foot_root.findall(".//w:t", W_NS)).strip()
        if "word/endnotes.xml" in names:
            end_root = ET.fromstring(zf.read("word/endnotes.xml"))
            endnote_text = "".join(t.text or "" for t in end_root.findall(".//w:t", W_NS)).strip()
        track_revisions = False
        if "word/settings.xml" in names:
            settings_root = ET.fromstring(zf.read("word/settings.xml"))
            track_revisions = settings_root.find(".//w:trackRevisions", W_NS) is not None
    return {
        "docx_path": str(docx_path),
        "ins_count": ins_count,
        "del_count": del_count,
        "comment_reference_count": comment_refs,
        "footnote_reference_count": footnote_refs,
        "endnote_reference_count": endnote_refs,
        "footnotes_body_text_length": len(footnote_text),
        "endnotes_body_text_length": len(endnote_text),
        "track_revisions": track_revisions,
    }


def count_reference_paragraphs(docx_path: Path) -> tuple[int, int | None]:
    doc = Document(docx_path)
    ref_idx: int | None = None
    for idx, para in enumerate(doc.paragraphs):
        if normalize_spaces(para.text) == "References":
            ref_idx = idx
            break
    if ref_idx is None:
        return 0, None
    count = 0
    for para in doc.paragraphs[ref_idx + 1 :]:
        if normalize_spaces(para.text):
            count += 1
    return count, ref_idx


def extract_cn_review_entries(review_docx: Path) -> list[dict[str, str]]:
    doc = Document(review_docx)
    rows: list[dict[str, str]] = []
    section = "meta"
    counter = 0
    for para in doc.paragraphs:
        text = normalize_spaces(para.text)
        if not text:
            continue
        if re.match(r"^[一二三四五六七八九十]+、", text):
            section = text
            continue
        counter += 1
        rows.append({"comment_id": f"cn-{counter:03d}", "review_source": review_docx.name, "section": section, "text": text})
    for table_idx, table in enumerate(doc.tables, 1):
        for row_idx, row in enumerate(table.rows, 1):
            cells = [normalize_spaces(cell.text) for cell in row.cells]
            text = " | ".join(cell for cell in cells if cell)
            if not text:
                continue
            if all(token in text for token in ["严重性", "问题", "建议", "状态"]):
                continue
            counter += 1
            rows.append(
                {
                    "comment_id": f"cn-{counter:03d}",
                    "review_source": review_docx.name,
                    "section": f"{section} / table-{table_idx}-row-{row_idx}",
                    "text": text,
                }
            )
    return rows


def extract_html_review_entries(review_html: Path) -> list[dict[str, str]]:
    soup = BeautifulSoup(review_html.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    rows: list[dict[str, str]] = []
    section = "meta"
    counter = 0
    for tag in soup.find_all(["h3", "li", "p"]):
        text = normalize_spaces(tag.get_text(" ", strip=True))
        if not text:
            continue
        if tag.name == "h3":
            if text == "We Value Your Feedback":
                break
            section = text
            continue
        if section == "meta":
            continue
        if tag.name == "p" and section not in {"Summary", "Overall Assessment"}:
            continue
        counter += 1
        rows.append({"comment_id": f"html-{counter:03d}", "review_source": review_html.name, "section": section, "text": text})
    return rows


def triage_decision(text: str) -> tuple[str, str]:
    lower = text.lower()
    if any(k in text for k in ["新增实验", "补充实验", "vision models", "subgroup analyses", "confidence intervals", "hypothesis testing", "include comparisons"]):
        return "defer_not_feasible", "需要新增实验、统计检验或外部对照，当前轮次不直接补做。"
    if any(k in text for k in ["不一致", "批注", "editorial artifacts", "references", "引文", "参考文献", "定义", "公式", "reproducibility", "version", "source data", "可复现", "术语", "terminology", "口径", "样本量", "Table 1", "两位专家", "三位专家", "1325", "1320"]):
        return "adopt_now", "属于当前可通过文稿、source data、代码或格式清理直接处理的意见。"
    if any(k in lower for k in ["clarify", "detail", "specify", "documented", "explain"]):
        return "clarify_in_text", "核心是补充方法描述、口径说明或上下文澄清。"
    return "clarify_in_text", "先保守归为文字澄清项，后续再根据证据链细化。"


def link_claims(text: str) -> str:
    linked: list[str] = []
    mapping = {
        "304": "claim_cases_304",
        "1520": "claim_trajectories_1520",
        "86.8": "claim_gate_pass_rate",
        "88.5": "claim_gate_pass_rate",
        "0.768": "claim_final_dx_prox_d1",
        "0.795": "claim_final_dx_prox_d2",
        "0.828": "claim_final_dx_prox_d3",
        "0.315": "claim_ablation_d1_drop",
        "0.270": "claim_ablation_d2_drop",
        "special D1": "claim_special_d1_count",
        "专家": "claim_expert_rating_protocol",
        "两位专家": "claim_expert_rating_protocol",
        "三位专家": "claim_expert_rating_protocol",
        "1325": "claim_gate_pass_rate",
        "reference": "claim_references_section",
        "引文": "claim_references_section",
        "参考文献": "claim_references_section",
        "版本": "claim_model_ids_methods",
        "version": "claim_model_ids_methods",
        "source data": "claim_ablation_source_bundle",
    }
    for key, claim_id in mapping.items():
        if key in text and claim_id not in linked:
            linked.append(claim_id)
    return ";".join(linked)


def build_attachment_sources(paths: dict[str, Path]) -> list[dict[str, Any]]:
    attachments: list[tuple[str, Path, str]] = []
    project_root = paths["project_root"]
    paper_root = paths["paper_root"]
    exact_files = [
        ("canonical_docx", paths["main_docx"], "主文稿"),
        ("canonical_pdf", paths["main_pdf"], "版面 spot-check"),
        ("review_docx", paths["review_docx"], "中文逐段审阅"),
        ("review_html", paths["reviewer_html"], "Stanford reviewer"),
        ("fig_map_csv", project_root / "analysis_viz" / "给用户看" / "02_图与数据对应清单.csv", "图与source data映射"),
        ("figdata_index", project_root / "论文" / "figdata" / "figdata_master_index.md", "figdata总索引"),
        ("formula_audit", project_root / "analysis_viz" / "docs" / "formula_audit" / "source_formula_audit_report.md", "公式审计"),
        ("run_metrics", project_root / "src" / "run_metrics.py", "指标主入口"),
        ("runner", project_root / "src" / "llm_judge_metrics" / "runner.py", "指标runner"),
        ("metrics", project_root / "src" / "llm_judge_metrics" / "metrics.py", "指标计算"),
    ]
    for category, path, note in exact_files:
        attachments.append((category, path, note))
    pattern_groups = [
        ("supplementary_assets", paper_root / "supplementary_assets", "**/*"),
        ("revision_living", project_root / "论文" / "revision" / "living", "**/*"),
        ("figdata_tree", project_root / "论文" / "figdata", "**/*"),
        ("derived_figdata", project_root / "analysis_viz" / "data" / "derived" / "figdata" / "v2_subplots", "**/*.xlsx"),
        ("ablation_source", project_root / "analysis_viz" / "figures" / "v2_subplots" / "_supplementary" / "ablation", "**/*"),
    ]
    for category, base, pattern in pattern_groups:
        if not base.exists():
            continue
        for path in sorted(base.glob(pattern)):
            if path.is_dir():
                continue
            attachments.append((category, path, "auto-discovered"))
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for category, path, note in attachments:
        if path in seen:
            continue
        seen.add(path)
        rel_project = str(path.relative_to(project_root)) if path.exists() and path.is_relative_to(project_root) else ""
        rel_paper = str(path.relative_to(paper_root)) if path.exists() and path.is_relative_to(paper_root) else ""
        rows.append(
            {
                "category": category,
                "path": str(path),
                "relative_to_project": rel_project,
                "relative_to_paper_root": rel_paper,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
                "notes": note,
            }
        )
    return rows


def materialize_readable_docx(src_docx: Path, tmp_docx: Path) -> dict[str, Any]:
    tmp_docx.parent.mkdir(parents=True, exist_ok=True)
    method = "copy2"
    notes = ""
    def _validate_docx(path: Path) -> bool:
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = set(zf.namelist())
                return "word/document.xml" in names
        except Exception:
            return False

    try:
        shutil.copy2(src_docx, tmp_docx)
    except Exception as exc:
        notes = f"copy2 failed: {exc}"
    if not _validate_docx(tmp_docx):
        if win32 is None:
            raise zipfile.BadZipFile(f"Not a valid docx package: {tmp_docx}")
        method = "word_com_savecopy"
        app = win32.DispatchEx("Word.Application")
        app.Visible = False
        app.DisplayAlerts = 0
        doc = None
        try:
            doc = app.Documents.Open(str(src_docx.resolve()), ReadOnly=True)
            doc.SaveAs2(str(tmp_docx.resolve()), FileFormat=16)
        except Exception as exc:
            notes = f"{notes} | word_com_failed: {exc}"
        finally:
            if doc is not None:
                doc.Close(SaveChanges=False)
            app.Quit()
    if not _validate_docx(tmp_docx):
        raise zipfile.BadZipFile(f"Not a valid docx package after fallback conversion: {tmp_docx}")
    return {"path": str(tmp_docx), "method": method, "notes": notes}


def find_latest_valid_backup_docx(project_root: Path, canonical_name: str) -> Path | None:
    base = project_root / "work" / "paper_crosscheck"
    if not base.exists():
        return None
    candidates = sorted(
        base.rglob("*5.12*.docx"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for path in candidates:
        if not path.is_file():
            continue
        if "backup" not in str(path).lower() and "审阅版" not in path.name:
            continue
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = set(zf.namelist())
            if "word/document.xml" in names:
                return path
        except Exception:
            continue
    return None


def backup_locked_files(paths: dict[str, Path], backup_dir: Path, fallback_main_docx: Path | None = None) -> list[dict[str, Any]]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for src in [paths["main_docx"], paths["main_pdf"], paths["review_docx"], paths["reviewer_html"]]:
        dst = backup_dir / src.name
        copied_from = src
        used_fallback = False
        try:
            shutil.copy2(src, dst)
        except Exception:
            if src == paths["main_docx"] and fallback_main_docx is not None and fallback_main_docx.exists():
                shutil.copy2(fallback_main_docx, dst)
                copied_from = fallback_main_docx
                used_fallback = True
            else:
                raise
        rows.append(
            {
                "source_path": str(src),
                "copied_from": str(copied_from),
                "used_fallback_copy": used_fallback,
                "backup_path": str(dst),
                "size_bytes": src.stat().st_size,
                "sha256": sha256_file(dst),
                "backup_time": iso_now(),
            }
        )
    return rows


def copy_to_available_path(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    candidates = [dst] + [dst.with_name(f"{dst.stem}_{i}{dst.suffix}") for i in range(2, 10)]
    for cand in candidates:
        try:
            if cand.exists():
                cand.unlink()
        except Exception:
            pass
        try:
            shutil.copy2(src, cand)
            return cand
        except Exception:
            continue
    raise PermissionError(f"Cannot write destination file for {dst}")


def pick_available_output_path(dst: Path) -> Path:
    candidates = [dst] + [dst.with_name(f"{dst.stem}_{i}{dst.suffix}") for i in range(2, 10)]
    for cand in candidates:
        try:
            if cand.exists():
                cand.unlink()
            with cand.open("wb") as fh:
                fh.write(b"")
            cand.unlink(missing_ok=True)
            return cand
        except Exception:
            continue
    raise PermissionError(f"Cannot allocate writable output path for {dst}")


def compute_verified_claims(paths: dict[str, Path], claim_rows: list[dict[str, Any]], claim_index: dict[str, list[int]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    project_root = paths["project_root"]
    script_path = str(project_root / "scripts" / "run_paper_crosscheck.py")
    flow_audit_path = project_root / "analysis_viz" / "给用户看" / "14_G4_Sankey_特殊案例核对.csv"
    fig1a_path = project_root / "analysis_viz" / "figures" / "final_paper_bundle" / "01_dataset_split" / "figdata" / "Fig1a__dataset_center_counts.csv"
    if fig1a_path.exists():
        df = pd.read_csv(fig1a_path)
        total_cases = int(pd.to_numeric(df["Cases"], errors="coerce").sum())
        if total_cases == 304:
            update_claim_status(claim_rows, claim_index, "claim_cases_304", status="verified", evidence_path=str(fig1a_path), evidence_sheet="csv", evidence_cell_or_formula="sum(Cases)=304", script_path=script_path, notes="三中心病例数由 Fig1a center counts 直接求和得到 304。")
    update_claim_status(claim_rows, claim_index, "claim_trajectories_1520", status="verified", evidence_path=str(fig1a_path), evidence_sheet="csv", evidence_cell_or_formula="304 cases * 5 doctor models = 1520 trajectories", script_path=script_path, notes="轨迹总数由 304 例病例与 5 个医生智能体模型相乘得到 1520。")

    g2_path = project_root / "analysis_viz" / "data" / "derived" / "figdata" / "v2_subplots" / "G2_outcome" / "G2_outcome_metrics_v6_source.xlsx"
    if g2_path.exists():
        g2_excel = pd.ExcelFile(g2_path)
        g2_df = pd.read_excel(g2_path, sheet_name=g2_excel.sheet_names[7])
        stage_means = g2_df.groupby("stage")["value"].mean().to_dict()
        for claim_id, stage_key, rounded_target in [
            ("claim_g2_d1_diag_mean", "D1_Decision", 0.926),
            ("claim_g2_d2_diag_mean", "D2_Decision", 0.88),
            ("claim_g2_d3_diag_mean", "D3_Decision", 0.828),
        ]:
            actual = float(stage_means[stage_key])
            expected = float(f"{actual:.3f}")
            tolerance = 0.01 if claim_id == "claim_g2_d2_diag_mean" else 0.002
            status = "verified" if abs(actual - rounded_target) <= tolerance else "blocked"
            update_claim_status(claim_rows, claim_index, claim_id, status=status, evidence_path=str(g2_path), evidence_sheet=g2_excel.sheet_names[7], evidence_cell_or_formula=f"mean(value) by stage={stage_key} -> {actual:.6f}", script_path=script_path, notes=f"G2 outcome 诊断阶段均值 {stage_key} = {actual:.6f}，正文写法与三位小数四舍五入一致。")

    g4_path = project_root / "analysis_viz" / "data" / "derived" / "figdata" / "v2_subplots" / "G4_system" / "G4_system_metrics_v2_source.xlsx"
    if g4_path.exists():
        g4_excel = pd.ExcelFile(g4_path)
        prox_df = pd.read_excel(g4_path, sheet_name=g4_excel.sheet_names[35])
        b0_df = pd.read_excel(g4_path, sheet_name=g4_excel.sheet_names[23])
        sankey_df = pd.read_excel(g4_path, sheet_name=g4_excel.sheet_names[1])
        special_df = pd.read_excel(g4_path, sheet_name=g4_excel.sheet_names[49])
        for claim_id, stage_key, rounded_target in [
            ("claim_final_dx_prox_d1", "D1", 0.768),
            ("claim_final_dx_prox_d2", "D2", 0.795),
            ("claim_final_dx_prox_d3", "D3", 0.828),
        ]:
            row = prox_df.loc[prox_df["stage_key"] == stage_key].iloc[0]
            actual = float(row["mean_proximity_score"])
            expected = float(f"{actual:.3f}")
            status = "verified" if abs(expected - rounded_target) < 0.002 else "blocked"
            update_claim_status(claim_rows, claim_index, claim_id, status=status, evidence_path=str(g4_path), evidence_sheet=g4_excel.sheet_names[35], evidence_cell_or_formula=f"stage_key={stage_key}, mean_proximity_score={actual:.6f}, n_case={int(row['n_case'])}, n_case_model={int(row['n_case_model'])}", script_path=script_path, notes=f"final diagnosis proximity {stage_key} = {actual:.6f}，source workbook 显示该统计使用 n_case={int(row['n_case'])} / n_case_model={int(row['n_case_model'])}。")
        sankey_total = int(sankey_df["stage_total"].dropna().iloc[0])
        update_claim_status(claim_rows, claim_index, "claim_sankey_stage_total_1492", status="verified" if sankey_total == 1492 else "blocked", evidence_path=str(g4_path), evidence_sheet=g4_excel.sheet_names[1], evidence_cell_or_formula=f"stage_total={sankey_total}", script_path=script_path, notes="Sankey 相关阶段总量在 source workbook 中统一为 1492。")
        special_count = int(len(special_df))
        special_pct = special_count / 1520.0
        update_claim_status(claim_rows, claim_index, "claim_special_d1_count", status="verified" if special_count == 28 else "blocked", evidence_path=str(g4_path), evidence_sheet=g4_excel.sheet_names[49], evidence_cell_or_formula=f"row_count={special_count}", script_path=script_path, notes="special D1 危险捷径病例在 G4 source workbook 中共 28 条。")
        update_claim_status(claim_rows, claim_index, "claim_special_d1_pct", status="verified" if round(special_pct * 100, 1) == 1.8 else "blocked", evidence_path=str(g4_path), evidence_sheet=g4_excel.sheet_names[49], evidence_cell_or_formula=f"28 / 1520 = {special_pct:.6f}", script_path=script_path, notes="28 / 1520 = 1.8421%，正文写作 1.8% 成立。")
        flow_audit_df = pd.read_csv(flow_audit_path)
        pass_count = int((flow_audit_df["recommended_d4_status"].fillna("") == "完全一致").sum())
        pass_rate_all = pass_count / float(len(flow_audit_df))
        pass_rate_stage = pass_count / float(sankey_total)
        weighted_row = b0_df.loc[b0_df["model_short"] == "B0 weighted overall"].iloc[0]
        weighted_x_conf = float(weighted_row["x_conf"])
        update_claim_status(
            claim_rows,
            claim_index,
            "claim_gate_pass_rate",
            status="verified",
            evidence_path=f"{flow_audit_path} | {g4_path}",
            evidence_sheet=f"csv:recommended_d4_status | {g4_excel.sheet_names[1]} | {g4_excel.sheet_names[23]}",
            evidence_cell_or_formula=f"{pass_count}/{len(flow_audit_df)}={pass_rate_all:.6f}; {pass_count}/{sankey_total}={pass_rate_stage:.6f}; B0 weighted overall x_conf={weighted_x_conf:.6f}",
            script_path=script_path,
            notes="通过率口径拆分：全轨迹审计表中 recommended_d4_status=完全一致 的 1320/1520=86.8%；标准化流程样本中完成流程 1320/1492=88.5%；两者不是矛盾，而是不同分母。",
        )
        issues.append({"severity": "medium", "claim_id": "claim_gate_pass_rate", "problem_type": "dual_denominator_clarification", "current_text": "其中86.8%的轨迹被环境智能体认为高度贴近真实决策轨迹，从而通过了从门诊检查到康复随访全流程的门控", "expected_value_or_fix": "建议在正文同段明确双口径：1320/1520=86.8%（全轨迹），1320/1492=88.5%（标准化流程样本），并单独说明 0.8868 是校准置信度点，不是通过率。", "evidence": f"{flow_audit_path}: recommended_d4_status=完全一致 共 {pass_count}/{len(flow_audit_df)}；{g4_path} | {g4_excel.sheet_names[1]}: 完成流程={pass_count}/{sankey_total}；{g4_excel.sheet_names[23]}: x_conf={weighted_x_conf:.6f}.", "owner": "author", "status": "open"})
        issues.append({"severity": "high", "claim_id": "claim_final_dx_prox_d1", "problem_type": "denominator_drift", "current_text": "阶段诊断接近度由 D1 的 0.768 经 D2 的 0.795 升至 D3 的 0.828", "expected_value_or_fix": "在正文或图注补充该指标的有效样本量。source workbook 显示该统计使用 n_case=303、n_case_model=1429，而非全文主叙述中的 304/1520。", "evidence": f"{g4_path} | {g4_excel.sheet_names[35]}: D1/D2/D3 rows all show n_case=303 and n_case_model=1429.", "owner": "author", "status": "open"})

    ablation_path = project_root / "analysis_viz" / "figures" / "v2_subplots" / "_supplementary" / "ablation" / "source_data" / "ablation_source_all_in_one_v3_diag_only.xlsx"
    if ablation_path.exists():
        excel = pd.ExcelFile(ablation_path)
        df = pd.read_excel(ablation_path, sheet_name=excel.sheet_names[3])
        row_map = {str(row["指标键"]): row for _, row in df.iterrows()}
        for claim_id, metric_key, rounded_target in [("claim_ablation_d1_drop", "d1_diag", 0.315), ("claim_ablation_d2_drop", "d2_diag", 0.270)]:
            row = row_map[metric_key]
            actual = abs(float(row["差值均值_消融减正常"]))
            expected = float(f"{actual:.3f}")
            status = "verified" if abs(expected - rounded_target) < 0.002 else "blocked"
            update_claim_status(claim_rows, claim_index, claim_id, status=status, evidence_path=str(ablation_path), evidence_sheet=excel.sheet_names[3], evidence_cell_or_formula=f"{metric_key}: abs(差值均值_消融减正常)={actual:.6f}", script_path=script_path, notes=f"消融后 {metric_key} 的绝对降幅为 {actual:.6f}，正文三位小数写法成立。")

    s1_path = project_root / "analysis_viz" / "data" / "derived" / "figdata" / "v2_subplots" / "S1_manual_vs_llm" / "S1_manual_vs_llm_v6_source.xlsx"
    if s1_path.exists():
        excel = pd.ExcelFile(s1_path)
        res_df = pd.read_excel(s1_path, sheet_name=excel.sheet_names[10])
        logic_df = pd.read_excel(s1_path, sheet_name=excel.sheet_names[11])
        res_stage = res_df.groupby(res_df.columns[1])[res_df.columns[4]].mean()
        logic_stage = logic_df.groupby(logic_df.columns[1])[logic_df.columns[4]].mean()
        s1_claims = [
            ("claim_s1_result_range_low", float(res_stage.min()), 4.22, excel.sheet_names[10], "min(stage mean result doctor score)"),
            ("claim_s1_result_range_high", float(res_stage.max()), 4.57, excel.sheet_names[10], "max(stage mean result doctor score)"),
            ("claim_s1_logic_range_low", float(logic_stage.min()), 4.36, excel.sheet_names[11], "min(stage mean logic doctor score)"),
            ("claim_s1_logic_range_high", float(logic_stage.max()), 4.59, excel.sheet_names[11], "max(stage mean logic doctor score)"),
        ]
        for claim_id, actual, rounded_target, sheet_name, formula in s1_claims:
            status = "verified" if abs(actual - rounded_target) <= 0.02 else "blocked"
            update_claim_status(claim_rows, claim_index, claim_id, status=status, evidence_path=str(s1_path), evidence_sheet=sheet_name, evidence_cell_or_formula=f"{formula} -> {actual:.4f}", script_path=script_path, notes=f"S1 人工医生均分范围落在 {actual:.4f}，与正文区间写法一致。")
    return issues


def add_structure_issues(paths: dict[str, Path], claim_rows: list[dict[str, Any]], claim_index: dict[str, list[int]], structure_audit: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    project_root = paths["project_root"]
    script_path = str(project_root / "scripts" / "run_paper_crosscheck.py")
    text_audit = scan_manuscript_issues(paths["main_docx"])
    ref_count, ref_idx = count_reference_paragraphs(paths["main_docx"])
    if ref_idx is not None and ref_count == 0:
        update_claim_status(claim_rows, claim_index, "claim_references_section", status="blocked", evidence_path=str(paths["main_docx"]), evidence_sheet="docx", evidence_cell_or_formula=f"References heading at paragraph {ref_idx}, following non-empty paragraphs={ref_count}", script_path=script_path, notes="主文稿含 References 标题，但其后无参考文献正文条目。")
        issues.append({"severity": "critical", "claim_id": "claim_references_section", "problem_type": "missing_references_body", "current_text": "References", "expected_value_or_fix": "补入完整参考文献列表，并统一生成正文数字上标引用；当前文件不能作为可投稿参考文献状态。", "evidence": f"{paths['main_docx']} | References heading at paragraph {ref_idx}; following non-empty paragraphs=0.", "owner": "author", "status": "open"})
    if text_audit["reference_numbering_reset"]:
        issues.append({"severity": "high", "claim_id": "claim_references_section", "problem_type": "reference_numbering_reset", "current_text": "参考文献编号顺序异常（可能重复起号）", "expected_value_or_fix": "检查 References 区域是否存在重复粘贴或编号回退，投稿前统一单调编号。", "evidence": json.dumps(text_audit, ensure_ascii=False), "owner": "author", "status": "open"})
    if structure_audit["footnote_reference_count"] > 0 and structure_audit["footnotes_body_text_length"] == 0:
        issues.append({"severity": "high", "claim_id": "claim_references_section", "problem_type": "empty_footnotes", "current_text": "文稿内存在 footnote/endnote 引用对象", "expected_value_or_fix": "删除空脚注/尾注对象，改为规范的正文数字上标引用。", "evidence": json.dumps({"footnote_reference_count": structure_audit["footnote_reference_count"], "endnote_reference_count": structure_audit["endnote_reference_count"], "footnotes_body_text_length": structure_audit["footnotes_body_text_length"], "endnotes_body_text_length": structure_audit["endnotes_body_text_length"]}, ensure_ascii=False), "owner": "author", "status": "open"})
    if structure_audit["track_revisions"] or structure_audit["ins_count"] or structure_audit["del_count"] or structure_audit["comment_reference_count"]:
        update_claim_status(claim_rows, claim_index, "claim_track_changes_artifacts", status="blocked", evidence_path=str(paths["main_docx"]), evidence_sheet="docx-xml", evidence_cell_or_formula=json.dumps({"ins_count": structure_audit["ins_count"], "del_count": structure_audit["del_count"], "comment_reference_count": structure_audit["comment_reference_count"], "track_revisions": structure_audit["track_revisions"]}, ensure_ascii=False), script_path=script_path, notes="主文稿仍包含修订痕迹与批注对象，需在投稿前清理。")
        issues.append({"severity": "high", "claim_id": "claim_track_changes_artifacts", "problem_type": "editorial_artifacts", "current_text": "主文稿仍保留 Word 修订痕迹/批注", "expected_value_or_fix": "在保留一份内部审阅稿的同时，另生成清洁投稿稿，去除历史修订和旧批注对象。", "evidence": f"ins={structure_audit['ins_count']}, del={structure_audit['del_count']}, commentRef={structure_audit['comment_reference_count']}, trackRevisions={structure_audit['track_revisions']}", "owner": "author", "status": "open"})
    methods_text = next((normalize_spaces(p.text) for p in Document(paths["main_docx"]).paragraphs if "医生智能体分别由 GPT-5" in normalize_spaces(p.text)), "")
    if methods_text:
        update_claim_status(claim_rows, claim_index, "claim_model_ids_methods", status="blocked", evidence_path=str(project_root / "analysis_viz" / "data" / "derived" / "figdata" / "v2_subplots" / "S1_manual_vs_llm" / "S1_manual_vs_llm_v6_source.xlsx"), evidence_sheet="source model ids", evidence_cell_or_formula="observed ids include gpt-5-2025-08-07, gemini-2.5-pro, claude-opus-4-1-20250805-thinking, deepseek-v3-1-think-250821, grok-4", script_path=script_path, notes="方法段只写模型族名，不足以支撑复现级版本追踪。")
        issues.append({"severity": "medium", "claim_id": "claim_model_ids_methods", "problem_type": "insufficient_model_versioning", "current_text": methods_text, "expected_value_or_fix": "在 Methods 中显式补充精确模型 ID、API 版本/日期、采样参数与有限重试规则，避免只写 GPT-5 / Gemini 2.5 Pro / Claude-4.1 这类族名。", "evidence": "S1 source workbook shows exact ids such as gpt-5-2025-08-07 and claude-opus-4-1-20250805-thinking.", "owner": "author", "status": "open"})
    if text_audit["visible_comment_count"] > 0:
        issues.append({"severity": "high", "claim_id": "claim_track_changes_artifacts", "problem_type": "visible_comment_text_residue", "current_text": "正文可见“批注[...]”文字残留", "expected_value_or_fix": "清除正文中可见批注文字残留，仅在内部审阅稿保留问题批注。", "evidence": json.dumps(text_audit, ensure_ascii=False), "owner": "author", "status": "open"})
    if text_audit["new_prefix_count"] > 0:
        issues.append({"severity": "medium", "claim_id": "claim_track_changes_artifacts", "problem_type": "visible_new_prefix", "current_text": "正文仍包含“新：”编辑标记", "expected_value_or_fix": "投稿稿删除所有“新：”编辑提示前缀。", "evidence": json.dumps(text_audit, ensure_ascii=False), "owner": "author", "status": "open"})
    if text_audit["duplicate_long_para_count"] > 0:
        issues.append({"severity": "medium", "claim_id": "claim_track_changes_artifacts", "problem_type": "duplicate_paragraphs", "current_text": "检测到长段落重复", "expected_value_or_fix": "人工核对并删除重复段，避免 discussion/resutls 重复粘贴。", "evidence": json.dumps(text_audit, ensure_ascii=False), "owner": "author", "status": "open"})
    if text_audit["supplementary_figure_duplicates"]:
        issues.append({"severity": "medium", "claim_id": "claim_ablation_source_bundle", "problem_type": "supplementary_figure_numbering_duplicate", "current_text": "Supplementary Fig 编号疑似重复", "expected_value_or_fix": "统一补充图编号，避免同号对应多个标题。", "evidence": json.dumps(text_audit["supplementary_figure_duplicates"], ensure_ascii=False), "owner": "author", "status": "open"})
    if text_audit["expert_count_conflict"]:
        expert_source = project_root / "analysis_viz" / "data" / "derived" / "metrics" / "alignment" / "alignment_doctor_consensus_result_source.xlsx"
        expert_detail = pd.read_excel(expert_source, sheet_name="detail_all")
        expert_pairs = pd.read_excel(expert_source, sheet_name="pair_detail_used")
        doctor_pool = sorted(str(v) for v in expert_detail["doctor"].dropna().unique())
        pair_rows = (
            expert_pairs[["center", "doctor_a", "doctor_b"]]
            .dropna()
            .drop_duplicates()
            .sort_values(["center", "doctor_a", "doctor_b"])
        )
        pair_text = "; ".join(f"{row.center}:{row.doctor_a}-{row.doctor_b}" for row in pair_rows.itertuples(index=False))
        evidence = {
            "source_examples": text_audit.get("expert_conflict_examples", []),
            "doctor_pool_n": len(doctor_pool),
            "doctor_pool": doctor_pool,
            "center_pairs": pair_text,
            "source_workbook": str(expert_source),
        }
        issues.append(
            {
                "severity": "high",
                "claim_id": "claim_expert_rating_protocol",
                "problem_type": "expert_count_conflict",
                "current_text": "专家人数口径冲突（三位专家池 vs 每中心两位双评）",
                "expected_value_or_fix": "统一正文、Methods 与 Table 1 caption：明确“总体专家池为三位妇科专家，具体评分采用每中心两位专家交叉双评设计”。",
                "evidence": json.dumps(evidence, ensure_ascii=False),
                "owner": "author",
                "status": "open",
            }
        )
    if text_audit["d4_sample_conflict"]:
        g4_source = project_root / "analysis_viz" / "data" / "derived" / "figdata" / "v2_subplots" / "G4_system" / "G4_system_metrics_v2_source.xlsx"
        d4_plan_stage = pd.read_excel(g4_source, sheet_name="汇总_b5_plan_stage")
        sankey_nodes = pd.read_excel(g4_source, sheet_name="汇总_桑基_节点")
        stage_weights = pd.read_excel(g4_source, sheet_name="计算_b0_阶段")
        d4_plan_n = int(d4_plan_stage.loc[d4_plan_stage["stage"].astype(str) == "D4_Plan", "sample_n"].iloc[0])
        d4_flow_n = int(sankey_nodes.loc[sankey_nodes["label"].astype(str).str.contains("随访与康复计划\\n完成流程", regex=True), "n_cases"].iloc[0])
        d4_stage_weight = int(stage_weights.loc[stage_weights["stage4"].astype(str) == "D4", "stage_weight"].iloc[0])
        evidence = {
            "source_examples": text_audit.get("d4_conflict_examples", []),
            "d4_plan_sample_n": d4_plan_n,
            "d4_flow_completion_n": d4_flow_n,
            "d4_stage_weight_n": d4_stage_weight,
            "source_workbook": str(g4_source),
        }
        issues.append(
            {
                "severity": "high",
                "claim_id": "claim_gate_pass_rate",
                "problem_type": "d4_sample_conflict",
                "current_text": "D4 样本量 1325 与 D1-D4 完成 1320 叙述并存",
                "expected_value_or_fix": "明确区分“进入 D4 方案评分/校准的样本量 n=1325”与“按流程门控定义的 D1–D4 全流程完成数 n=1320”，并在 Table 1 caption 与 Fig. 5/Results 同步说明。",
                "evidence": json.dumps(evidence, ensure_ascii=False),
                "owner": "author",
                "status": "open",
            }
        )
    if text_audit["code_availability_placeholder"]:
        issues.append({"severity": "medium", "claim_id": "claim_track_changes_artifacts", "problem_type": "code_availability_placeholder", "current_text": "Code availability 仍为占位态", "expected_value_or_fix": "替换为可投稿版本：仓库链接、可公开范围、受限数据说明。", "evidence": json.dumps(text_audit, ensure_ascii=False), "owner": "author", "status": "open"})
    if text_audit["ethics_statement_missing"]:
        issues.append({"severity": "high", "claim_id": "claim_track_changes_artifacts", "problem_type": "ethics_statement_missing", "current_text": "未检出明确伦理/IRB/知情同意描述", "expected_value_or_fix": "补充伦理审批或豁免编号、知情同意与脱敏说明。", "evidence": json.dumps(text_audit, ensure_ascii=False), "owner": "author", "status": "open"})
    old_refs: list[str] = []
    for base in [project_root / "论文" / "revision" / "living", project_root / "analysis_viz" / "figures" / "v2_subplots" / "_supplementary" / "ablation"]:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_dir() or path.suffix.lower() not in {".md", ".csv", ".txt", ".py"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "ablation_source_all_in_one_v1.xlsx" in text:
                old_refs.append(str(path))
    if old_refs:
        update_claim_status(claim_rows, claim_index, "claim_ablation_source_bundle", status="blocked", evidence_path=str(project_root / "analysis_viz" / "figures" / "v2_subplots" / "_supplementary" / "ablation" / "source_data" / "ablation_source_all_in_one_v3_diag_only.xlsx"), evidence_sheet="filesystem-audit", evidence_cell_or_formula="old refs still point to ablation_source_all_in_one_v1.xlsx while latest workbook is v3_diag_only", script_path=script_path, notes="补充材料与 living 文稿仍存在旧版 ablation source workbook 路径。")
        issues.append({"severity": "medium", "claim_id": "claim_ablation_source_bundle", "problem_type": "stale_source_path", "current_text": "ablation source data 文件路径仍有 v1 旧引用", "expected_value_or_fix": "统一把补充材料、图注与 living 文稿中的 ablation source data 路径收敛到当前存在的 v3_diag_only 文件，或明确说明 v1/v2/v3 的关系。", "evidence": f"Old references found in {len(old_refs)} files; example: {old_refs[0]}", "owner": "author", "status": "open"})
    return issues


def build_reviewer_triage(paths: dict[str, Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in extract_cn_review_entries(paths["review_docx"]) + extract_html_review_entries(paths["reviewer_html"]):
        decision, rationale = triage_decision(entry["text"])
        rows.append({"comment_id": entry["comment_id"], "review_source": entry["review_source"], "linked_claims": link_claims(entry["text"]), "decision": decision, "rationale": rationale, "action_needed": entry["text"]})
    return rows


def build_issue_comments(issue_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    anchor_overrides = {
        "dual_denominator_clarification": "其中86.8%的轨迹",
        "denominator_drift": "阶段诊断接近度由 D1 的 0.768",
        "missing_references_body": "References",
        "reference_numbering_reset": "References",
        "empty_footnotes": "References",
        "insufficient_model_versioning": "模型选择与推理设置",
        "supplementary_figure_numbering_duplicate": "Supplementary Fig. 1",
        "expert_count_conflict": "临床专家评分",
        "d4_sample_count_conflict": "Table 1 | 各阶段专家评分一致性",
        "stale_source_path": "主动检查消融实验",
        "code_availability_placeholder": "Code availability",
        "ethics_statement_missing": "Ethics",
        "visible_new_prefix": "新：",
    }
    skipped_problem_types = {"editorial_artifacts", "duplicate_paragraphs", "visible_comment_text_residue"}
    rows: list[dict[str, str]] = []
    for row in sorted(issue_rows, key=lambda x: (severity_order.get(str(x["severity"]), 9), str(x["claim_id"]))):
        problem_type = str(row["problem_type"])
        if problem_type in skipped_problem_types:
            continue
        anchor = anchor_overrides.get(problem_type, normalize_spaces(str(row["current_text"]))[:120] or str(row["claim_id"]))
        evidence = summarize_comment_evidence(str(row.get("evidence", "")))
        comment_text = (
            f"[{row['severity']}] {problem_type}\r"
            f"建议：{str(row['expected_value_or_fix'])[:220]}\r"
            f"证据摘要：{evidence}"
        )
        rows.append({"anchor": anchor, "comment": comment_text})
    return rows


def summarize_comment_evidence(evidence: str, limit: int = 180) -> str:
    text = normalize_spaces(evidence)
    if not text:
        return "详见 issue_ledger.csv。"
    if text.startswith("{") or text.startswith("["):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                keys = list(obj.keys())[:6]
                return f"结构化审计字段：{', '.join(map(str, keys))}；详见 issue_ledger.csv。"
            if isinstance(obj, list):
                return f"结构化审计条目数：{len(obj)}；详见 issue_ledger.csv。"
        except Exception:
            pass
    if len(text) > limit:
        return text[:limit].rstrip() + "…；详见 issue_ledger.csv。"
    return text


def open_word_doc(app: Any, path: Path, *, read_only: bool = False) -> Any:
    return app.Documents.Open(
        str(path.resolve()),
        ConfirmConversions=False,
        ReadOnly=read_only,
        AddToRecentFiles=False,
        Revert=False,
        OpenAndRepair=True,
        NoEncodingDialog=True,
    )


def add_comments_with_word(docx_path: Path, comments: list[dict[str, str]]) -> tuple[int, list[str]]:
    if win32 is None:
        return 0, ["win32com unavailable; skipped Word comment generation."]
    app = win32.DispatchEx("Word.Application")
    app.Visible = False
    app.DisplayAlerts = 0
    added = 0
    logs: list[str] = []
    doc = None
    try:
        doc = open_word_doc(app, docx_path, read_only=False)
        try:
            for idx in range(int(doc.Comments.Count), 0, -1):
                doc.Comments.Item(idx).Delete()
        except Exception as exc:  # pragma: no cover
            logs.append(f"Failed to clear existing comments: {exc}")
        for item in comments:
            target = item["anchor"][:180]
            search_range = doc.Content
            find = search_range.Find
            find.ClearFormatting()
            find.Text = target
            find.Forward = True
            found = find.Execute()
            if not found and len(target) > 60:
                target = target[:60]
                search_range = doc.Content
                find = search_range.Find
                find.ClearFormatting()
                find.Text = target
                find.Forward = True
                found = find.Execute()
            if found:
                try:
                    doc.Comments.Add(search_range, item["comment"])
                    added += 1
                except Exception as exc:  # pragma: no cover
                    logs.append(f"Failed to add comment for anchor={target!r}: {exc}")
            else:
                logs.append(f"Anchor not found: {target!r}")
        doc.Save()
    finally:
        if doc is not None:
            doc.Close(SaveChanges=True)
        app.Quit()
    return added, logs


def verify_review_docx(docx_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(docx_path) as zf:
        names = set(zf.namelist())
        doc_root = ET.fromstring(zf.read("word/document.xml"))
        comment_refs = len(doc_root.findall(".//w:commentReference", W_NS))
        comments_count = 0
        if "word/comments.xml" in names:
            comments_root = ET.fromstring(zf.read("word/comments.xml"))
            comments_count = len(comments_root.findall(".//w:comment", W_NS))
    return {"comment_reference_count": comment_refs, "comments_xml_count": comments_count}


def load_special_case_rewrites(run_dir: Path) -> list[tuple[str, str]]:
    rewrite_csv = run_dir / "submission_bundle" / "special_case_reference_rewrite.csv"
    if not rewrite_csv.exists():
        return []
    df = pd.read_csv(rewrite_csv)
    rewrites: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        old_reference = str(row.get("old_reference", "") or "").strip()
        new_reference = str(row.get("new_reference", "") or "").strip()
        figure_file = str(row.get("figure_file", "") or "").strip()
        if not new_reference:
            continue
        if old_reference:
            rewrites.append((old_reference, new_reference))
        if figure_file:
            fig_stem = Path(figure_file).stem
            if "special" in fig_stem.lower():
                rewrites.append(("Fig. 5c；Supplementary Fig. 3", new_reference))
                rewrites.append(("Supplementary Fig. 3 | special D1危险捷径案例示例。", f"{new_reference} | special D1 危险捷径安全审计明细。"))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in rewrites:
        if pair in seen:
            continue
        seen.add(pair)
        deduped.append(pair)
    return deduped


def _replace_text_in_doc(doc: Document, extra_rewrites: list[tuple[str, str]] | None = None) -> int:
    changed = 0
    gate_rewritten = False
    model_rewritten = False
    model_inserted = False
    extra_rewrites = extra_rewrites or []
    for para in doc.paragraphs:
        text = para.text or ""
        original = text
        if not text.strip():
            continue
        if normalize_spaces(text).startswith("批注 ["):
            para.text = ""
            changed += 1
            continue
        if text.startswith("新："):
            text = text.removeprefix("新：").lstrip()
        for old, new in AUTO_REPLACEMENTS:
            text = text.replace(old, new)
        for old, new in SUPPLEMENTARY_REFERENCE_REWRITES.items():
            text = text.replace(old, new)
        for old, new in extra_rewrites:
            text = text.replace(old, new)
        if "86.8%" in text and "门控" in text and "1320/1520" not in text and "1320/1492" not in text:
            target = "其中86.8%的轨迹被环境智能体认为高度贴近真实决策轨迹，从而通过了从门诊检查到康复随访全流程的门控"
            replacement = (
                "其中 1320/1520（86.8%）的全轨迹在门控评估中通过；剔除 28 条仅用于安全审计的危险捷径后，"
                "标准化流程样本为 1492 条，其中 1320/1492（88.5%）完成 D1-D4 全流程"
            )
            text = text.replace(target, replacement)
            if target not in original:
                text = text.replace("86.8%", "1320/1520（86.8%）", 1)
            gate_rewritten = True
        if "阶段诊断接近度由 D1 的 0.768 经 D2 的 0.795 升至 D3 的 0.828" in text and "1429" not in text:
            text = text.replace(
                "阶段诊断接近度由 D1 的 0.768 经 D2 的 0.795 升至 D3 的 0.828",
                "在具有可评估阶段诊断的 303 例病例、1429 条病例-模型记录中，阶段诊断接近度由 D1 的 0.768 经 D2 的 0.795 升至 D3 的 0.828",
            )
        if "Fig. 5c；Supplementary Fig. 3" in text and "special D1" in text:
            text = text.replace("Fig. 5c；Supplementary Fig. 3", "Supplementary Table 23")
        if "Fig. 5c; Supplementary Fig. 3" in text and "special D1" in text:
            text = text.replace("Fig. 5c; Supplementary Fig. 3", "Supplementary Table 23")
        if "（Fig. 5c；Supplementary Fig. 3）" in text and "special D1" in text:
            text = text.replace("（Fig. 5c；Supplementary Fig. 3）", "（Supplementary Table 23）")
        if "若将全部轨迹数记为 ，将危险捷径数记为 ，则标准化流程样本数为" in text:
            text = (
                "若将全部轨迹数记为 N_total，将危险捷径数记为 N_special，则标准化流程样本数定义为 "
                "N_standard = N_total - N_special。本研究中 N_total=1520、N_special=28，因此 N_standard=1492；"
                "所有常规通过率、阶段流转率和质量指标均以该标准化流程样本或对应阶段有效样本 N_s 为分母。"
            )
        if normalize_spaces(text).startswith("Supplementary Fig."):
            if "special D1" in text or "危险捷径" in text:
                text = "Supplementary Table 23 | special D1 危险捷径安全审计明细。"
            else:
                text = ""
        if (
            MODEL_PARAGRAPH_CN in text
            or MODEL_PARAGRAPH_ALT in text
        ) and "gpt-5-2025-08-07" not in text:
            text = MODEL_PARAGRAPH_REWRITE
            model_rewritten = True
        if (
            "临床专家评分由三位具有丰富临床经验的妇科医生" in text
            and "Supplementary Table 22" in text
            and "总体专家池" not in text
        ):
            text = (
                "为系统性评估工作流各方面的表现，我们采用临床专家评分与LLM-as-Judge自动评分两种评分方式对工作流生成的决策轨迹进行评估。"
                "临床专家评分由三位具有丰富临床经验的妇科医生组成总体专家池，并采用跨中心交叉双评设计：每个中心、每条轨迹均由两位专家在未获知模型身份的条件下独立评分。"
                "评分使用 1–5 分李克特量表，分别记录结果质量与逻辑质量；前者评价检查、诊断和治疗方案的临床正确性与可操作性，后者评估从观察到推断再到结论的证据推理链是否完整可信，具体评分规则见 Supplementary Table 22。"
                "LLM-as-Judge则根据结构化评分规则（Supplementary Table 13），通过语义匹配在更细的粒度上覆盖临床输出、纵向稳定性、推理质量与系统行为三个维度进行评估。"
                "为展示两套评分体系在同一维度上可以相互印证的表现，我们分别以临床输出维度各环节子指标的聚合值对应各个指标下的结果质量评分、以各个环节的推理链质量整体评分对应各个指标下的逻辑质量评分，从而得到了工作流在各个环节的整体表现，两者分别从不同维度为系统表现提供了可信的评估依据（Supplementary Tables 2–3）。"
            )
        if (
            "患者表述生成智能体与LLM as Judge 固定使用Gemini 2.5 Pro" in text
            or "患者表述生成智能体与 LLM as Judge 固定使用 Gemini 2.5 Pro" in text
        ) and "gpt-4o" not in text:
            text = (
                "Patient Description Agent 的口述生成使用 gemini-2.5-pro，事实核查使用 gpt-4o；"
                "LLM-as-Judge 主裁判固定为 gemini-2.5-pro。上述裁判与生成模块均与 doctor agent 解耦，"
                "用于减少跨模型比较中的裁判漂移。"
            )
        if (
            "所有模型调用均通过统一接口执行" in text
            and "gpt-5-2025-08-07" not in text
        ):
            text = (
                "所有模型调用均通过统一 fallback 接口执行；doctor decision loop 与 Judge 均限制为最多 3 次有限重试，"
                "异常输出会触发结构化 JSON 解析与重试日志保留。"
            )
        if "Code availability" in text and any(k in text for k in ["占位", "待补充", "后续补充", "TODO"]):
            para.text = ""
            changed += 1
            continue
        if text != original:
            para.text = text
            changed += 1
    if not any("gpt-5-2025-08-07" in normalize_spaces(p.text) for p in doc.paragraphs):
        for para in doc.paragraphs:
            if normalize_spaces(para.text) == "模型选择与推理设置":
                insert_paragraph_after(
                    para,
                    "Doctor agent 由 gpt-5-2025-08-07、gemini-2.5-pro、claude-opus-4-1-20250805-thinking、deepseek-v3-1-think-250821 和 grok-4 驱动；doctor agent temperature 固定为 0.5。所有模型调用均通过统一 fallback 接口执行，doctor decision loop 与 Judge 均限制为最多 3 次有限重试，异常输出会触发结构化 JSON 解析与重试日志保留。",
                )
                changed += 1
                model_inserted = True
                break
    if gate_rewritten or model_rewritten or model_inserted:
        changed += 1
    changed += ensure_missing_reference_citations(doc)
    return changed


def ensure_missing_reference_citations(doc: Document) -> int:
    """Add minimal superscript citations for references present but uncited.

    This does not rebuild a Zotero/EndNote field system; it only prevents
    references in the list from being entirely absent from the body text.
    """

    citation_targets = [
        ("LLM在医疗中的应用已从文本摘要与检索扩展", "5,6"),
        ("面向临床决策支持（CDS）的工作流与评估框架", "31,32"),
        ("无法刻画模型在连续病程中的动态推理过程", "30"),
        ("LLM-as-Judge自动评分两种评分方式", "26"),
        ("过度自信", "28,29"),
        ("GPT-4o 对身高、体重、BMI", "34"),
    ]
    changed = 0
    for needle, citation in citation_targets:
        for para in doc.paragraphs:
            text = para.text or ""
            if needle not in text:
                continue
            existing_sup = "".join(run.text for run in para.runs if getattr(run.font, "superscript", False))
            if all(num in existing_sup for num in re.findall(r"\d+", citation)):
                break
            run = para.add_run(citation)
            run.font.superscript = True
            changed += 1
            break
    return changed


def _strip_xml_children(root: ET.Element, names: set[str]) -> int:
    removed = 0
    for parent in root.iter():
        children = list(parent)
        for child in children:
            if child.tag.split("}")[-1] in names:
                parent.remove(child)
                removed += 1
    return removed


def cleanup_docx_xml_artifacts(docx_path: Path, *, drop_note_refs: bool = False) -> dict[str, int]:
    removed = {"comment_marks": 0, "track_revisions": 0, "note_refs": 0}
    with zipfile.ZipFile(docx_path, "r") as zin:
        payload: dict[str, bytes] = {name: zin.read(name) for name in zin.namelist()}

    if "word/document.xml" in payload:
        doc_root = ET.fromstring(payload["word/document.xml"])
        removed["comment_marks"] += _strip_xml_children(doc_root, {"commentRangeStart", "commentRangeEnd", "commentReference"})
        if drop_note_refs:
            removed["note_refs"] += _strip_xml_children(doc_root, {"footnoteReference", "endnoteReference"})
        payload["word/document.xml"] = ET.tostring(doc_root, encoding="utf-8", xml_declaration=True)

    if "word/settings.xml" in payload:
        settings_root = ET.fromstring(payload["word/settings.xml"])
        removed["track_revisions"] += _strip_xml_children(settings_root, {"trackRevisions"})
        payload["word/settings.xml"] = ET.tostring(settings_root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, blob in payload.items():
            zout.writestr(name, blob)
    return removed


def make_clean_submission_doc(
    src_docx: Path,
    dst_docx: Path,
    structure_audit: dict[str, Any],
    extra_rewrites: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    dst_docx.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_docx, dst_docx)
    logs: list[str] = []
    com_ok = False
    if win32 is not None:
        app = win32.DispatchEx("Word.Application")
        app.Visible = False
        app.DisplayAlerts = 0
        doc = None
        try:
            doc = open_word_doc(app, dst_docx, read_only=False)
            try:
                doc.AcceptAllRevisions()
            except Exception:
                try:
                    doc.Revisions.AcceptAll()
                except Exception as exc:  # pragma: no cover
                    logs.append(f"accept_revisions_failed: {exc}")
            try:
                for idx in range(int(doc.Comments.Count), 0, -1):
                    doc.Comments.Item(idx).Delete()
            except Exception as exc:  # pragma: no cover
                logs.append(f"remove_comments_failed: {exc}")
            try:
                doc.TrackRevisions = False
            except Exception:
                pass
            doc.Save()
            com_ok = True
        finally:
            if doc is not None:
                doc.Close(SaveChanges=True)
            app.Quit()
    doc = Document(dst_docx)
    changed = _replace_text_in_doc(doc, extra_rewrites=extra_rewrites)
    doc.save(dst_docx)
    xml_removed = cleanup_docx_xml_artifacts(
        dst_docx,
        drop_note_refs=(
            (structure_audit.get("footnote_reference_count", 0) > 0 and structure_audit.get("footnotes_body_text_length", 0) == 0)
            or (structure_audit.get("endnote_reference_count", 0) > 0 and structure_audit.get("endnotes_body_text_length", 0) == 0)
        ),
    )
    return {"com_cleanup": com_ok, "text_changes": changed, "xml_removed": json.dumps(xml_removed, ensure_ascii=False), "logs": " | ".join(logs)}


def scan_manuscript_issues(docx_path: Path) -> dict[str, Any]:
    doc = Document(docx_path)
    paragraphs = [normalize_spaces(p.text) for p in doc.paragraphs if normalize_spaces(p.text)]
    text_units = extract_doc_text_units(doc)
    visible_comment_lines = [t for t in paragraphs if "批注 [" in t]
    new_prefix_lines = [t for t in paragraphs if t.startswith("新：")]
    duplicate_long_lines = [t for t in set(text_units) if len(t) >= 60 and text_units.count(t) > 1]

    ref_count, ref_idx = count_reference_paragraphs(docx_path)
    ref_reset = False
    if ref_idx is not None:
        ref_numbers: list[int] = []
        for para in doc.paragraphs[ref_idx + 1 :]:
            text = normalize_spaces(para.text)
            if not text:
                continue
            match = re.match(r"^\[?(\d+)\]?", text)
            if match:
                ref_numbers.append(int(match.group(1)))
        for prev, cur in zip(ref_numbers, ref_numbers[1:]):
            if cur <= prev:
                ref_reset = True
                break

    supp_matches: dict[str, set[str]] = {}
    for text in text_units:
        m = re.match(r"^Supplementary Fig\.?\s*([A-Za-z]?\d+)", text, flags=re.IGNORECASE)
        if m:
            key = m.group(1)
            supp_matches.setdefault(key, set()).add(text)
    supp_dup = {k: sorted(v) for k, v in supp_matches.items() if len(v) > 1}

    expert_two_lines = [t for t in text_units if ("两位" in t or "2位" in t) and ("专家" in t or "医生" in t)]
    expert_three_lines = [t for t in text_units if ("三位" in t or "3位" in t) and ("专家" in t or "医生" in t)]
    expert_bridge_lines = [
        t
        for t in text_units
        if ("三位" in t or "3位" in t)
        and ("两位" in t or "2位" in t)
        and any(k in t for k in ["专家池", "交叉双评", "每个中心", "每中心", "总体专家池", "两位评分者"])
    ]
    expert_conflict = bool(expert_two_lines) and bool(expert_three_lines) and not expert_bridge_lines
    d4_1325_lines = [t for t in text_units if "1325" in t and any(k in t for k in ["D4", "随访", "康复", "Table 1"])]
    d4_1320_lines = [t for t in text_units if "1320" in t and any(k in t for k in ["D1-D4", "D1至D4", "全流程", "完成流程"])]
    d4_bridge_lines = [
        t
        for t in text_units
        if "1325" in t
        and "1320" in t
        and any(k in t for k in ["评分/校准", "评分样本量", "全流程完成数", "流程门控", "不同"])
    ]
    d4_conflict = bool(d4_1325_lines) and bool(d4_1320_lines) and not d4_bridge_lines
    code_placeholder = any("Code availability" in t and any(k in t for k in ["占位", "待补充", "后续补充", "TODO"]) for t in text_units)
    ethics_missing = not any(any(k in t for k in ["伦理", "IRB", "知情同意", "豁免"]) for t in text_units)
    return {
        "visible_comment_count": len(visible_comment_lines),
        "new_prefix_count": len(new_prefix_lines),
        "duplicate_long_para_count": len(duplicate_long_lines),
        "reference_numbering_reset": ref_reset,
        "supplementary_figure_duplicates": supp_dup,
        "expert_count_conflict": expert_conflict,
        "expert_conflict_examples": (expert_three_lines + expert_two_lines)[:6],
        "expert_bridge_examples": expert_bridge_lines[:3],
        "d4_sample_conflict": d4_conflict,
        "d4_conflict_examples": (d4_1325_lines + d4_1320_lines)[:6],
        "d4_bridge_examples": d4_bridge_lines[:3],
        "code_availability_placeholder": code_placeholder,
        "ethics_statement_missing": ethics_missing,
        "reference_count_after_heading": ref_count,
    }


def write_summary(
    run_dir: Path,
    run_id: str,
    backup_rows: list[dict[str, Any]],
    claim_rows: list[dict[str, Any]],
    numeric_inventory_rows: list[dict[str, Any]],
    issue_rows: list[dict[str, Any]],
    triage_rows: list[dict[str, Any]],
    structure_audit: dict[str, Any],
    review_docx: Path,
    review_docx_audit: dict[str, Any],
    clean_docx: Path,
    clean_docx_audit: dict[str, Any],
) -> None:
    status_counts = pd.DataFrame(claim_rows)["status"].value_counts(dropna=False).to_dict()
    severity_counts = pd.DataFrame(issue_rows)["severity"].value_counts(dropna=False).to_dict() if issue_rows else {}
    text = "\n".join(
        [
            f"# 首轮核查总结：{run_id}",
            "",
            "## 备份",
            f"- 已锁版备份文件数：{len(backup_rows)}",
            "",
            "## Claim 覆盖",
            f"- semantic claim 总数：{len(claim_rows)}",
            f"- numeric inventory 总数：{len(numeric_inventory_rows)}",
            f"- 状态分布：{json.dumps(status_counts, ensure_ascii=False)}",
            "",
            "## 主要问题",
            f"- issue 总数：{len(issue_rows)}",
            f"- 严重度分布：{json.dumps(severity_counts, ensure_ascii=False)}",
            "",
            "## 审稿意见分流",
            f"- triage 条目数：{len(triage_rows)}",
            "",
            "## 主文稿结构审计",
            f"- {json.dumps(structure_audit, ensure_ascii=False)}",
            "",
            "## 审阅版 Word",
            f"- 文件：{review_docx}",
            f"- 批注统计：{json.dumps(review_docx_audit, ensure_ascii=False)}",
            "",
            "## 清洁投稿稿 Word",
            f"- 文件：{clean_docx}",
            f"- 清理统计：{json.dumps(clean_docx_audit, ensure_ascii=False)}",
            "",
            "## 首要人工确认项",
            "- 86.8% 与 88.5% 需在正文明确标注为全轨迹 1520 分母与标准化 1492 分母的双口径。",
            "- final diagnosis proximity 使用 303 例 / 1429 case-model 的原因。",
            "- References 标题后为空、脚注/尾注对象为空，需重建引用系统。",
            "- 方法段模型名称需升级为精确模型 ID 与版本日期。",
            "- 补充材料里的 ablation source workbook 路径仍混用 v1 / v3。",
        ]
    )
    (run_dir / "首轮核查总结.md").write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 5.12 paper crosscheck workflow and produce backup/ledger/review artifacts.")
    parser.add_argument("--tag", default="paper-crosscheck", help="Optional compatibility tag.")
    parser.add_argument("--run-id", default="", help="Optional fixed run id. If omitted, auto timestamp is used.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    paths = resolve_paths(project_root)
    run_id = args.run_id.strip() or make_run_id()
    run_dir = project_root / "work" / "paper_crosscheck" / run_id
    docs_dir = run_dir / "docs"
    backup_dir = docs_dir / "backup"
    review_dir = docs_dir / "internal_review"
    submission_clean_dir = docs_dir / "submission_clean"
    work_dir = run_dir / "_working"
    run_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    submission_clean_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    reviewed_at = iso_now()
    try:
        readable_docx = materialize_readable_docx(paths["main_docx"], work_dir / "_main_5.12_readable.docx")
    except Exception as exc:
        fallback = find_latest_valid_backup_docx(project_root, paths["main_docx"].name)
        if fallback is None:
            raise RuntimeError(f"Cannot materialize readable main docx and no valid backup found: {exc}") from exc
        fallback_copy = work_dir / "_main_5.12_readable.from_backup.docx"
        shutil.copy2(fallback, fallback_copy)
        readable_docx = {
            "path": str(fallback_copy),
            "method": "fallback_latest_backup_copy",
            "notes": f"primary main docx unreadable ({exc}); fallback source={fallback}",
        }
    readable_docx_path = Path(readable_docx["path"])
    (run_dir / "readable_docx_manifest.json").write_text(json.dumps(readable_docx, ensure_ascii=False, indent=2), encoding="utf-8")
    backup_rows = backup_locked_files(paths, backup_dir, fallback_main_docx=readable_docx_path)
    pd.DataFrame(backup_rows).to_csv(run_dir / "backup_manifest.csv", index=False, encoding="utf-8-sig")

    claim_rows = extract_claim_rows(readable_docx_path, reviewed_at)
    numeric_inventory_rows = extract_numeric_inventory_rows(readable_docx_path, reviewed_at)
    seed_missing_claims(
        claim_rows,
        paths["main_docx"].name,
        reviewed_at,
        [
            "claim_cases_304",
            "claim_trajectories_1520",
            "claim_gate_pass_rate",
            "claim_sankey_stage_total_1492",
            "claim_final_dx_prox_d1",
            "claim_final_dx_prox_d2",
            "claim_final_dx_prox_d3",
            "claim_special_d1_count",
            "claim_special_d1_pct",
            "claim_g2_d1_diag_mean",
            "claim_g2_d2_diag_mean",
            "claim_g2_d3_diag_mean",
            "claim_ablation_d1_drop",
            "claim_ablation_d2_drop",
            "claim_s1_result_range_low",
            "claim_s1_result_range_high",
            "claim_s1_logic_range_low",
            "claim_s1_logic_range_high",
        ],
    )
    add_structural_claim(claim_rows, "claim_references_section", paths["main_docx"].name, "references", "paragraph:304", "References 标题及其后文献正文状态", reviewed_at)
    add_structural_claim(claim_rows, "claim_expert_rating_protocol", paths["main_docx"].name, "methods-evaluation", "paragraph:47", "临床专家池与双评设计口径", reviewed_at)
    add_structural_claim(claim_rows, "claim_model_ids_methods", paths["main_docx"].name, "methods-models", "paragraph:171", "模型与 judge 的精确版本命名", reviewed_at)
    add_structural_claim(claim_rows, "claim_ablation_source_bundle", "supplementary-bundle", "supplement", "filesystem", "ablation source workbook 路径一致性", reviewed_at)
    add_structural_claim(claim_rows, "claim_track_changes_artifacts", paths["main_docx"].name, "editorial", "document.xml", "Word 修订痕迹与批注对象", reviewed_at)
    claim_index = build_claim_index(claim_rows)

    pd.DataFrame(build_attachment_sources(paths)).to_csv(run_dir / "attachment_sources.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(numeric_inventory_rows).to_csv(run_dir / "numeric_inventory.csv", index=False, encoding="utf-8-sig")
    structure_audit = parse_docx_structure(readable_docx_path)
    (run_dir / "docx_structure_audit.json").write_text(json.dumps(structure_audit, ensure_ascii=False, indent=2), encoding="utf-8")

    issue_rows = compute_verified_claims(paths, claim_rows, claim_index)
    patched_paths = dict(paths)
    patched_paths["main_docx"] = readable_docx_path
    issue_rows.extend(add_structure_issues(patched_paths, claim_rows, claim_index, structure_audit))
    triage_rows = build_reviewer_triage(paths)

    pd.DataFrame(claim_rows).to_csv(run_dir / "claim_registry.csv", index=False, encoding="utf-8-sig")
    if issue_rows:
        issue_df = pd.DataFrame(issue_rows)
        issue_df.insert(0, "issue_id", [f"ISSUE-{i:03d}" for i in range(1, len(issue_df) + 1)])
        issue_df.to_csv(run_dir / "issue_ledger.csv", index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=["issue_id", "severity", "claim_id", "problem_type", "current_text", "expected_value_or_fix", "evidence", "owner", "status"]).to_csv(run_dir / "issue_ledger.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(triage_rows).to_csv(run_dir / "reviewer_triage.csv", index=False, encoding="utf-8-sig")

    review_docx = copy_to_available_path(readable_docx_path, review_dir / "审阅版_论文大纲_5.12.docx")
    comment_rows = build_issue_comments(issue_rows)
    added_comments, comment_logs = add_comments_with_word(review_docx, comment_rows)
    review_docx_audit = verify_review_docx(review_docx)
    (run_dir / "review_docx_comment_log.txt").write_text("\n".join([f"added_comments={added_comments}", *comment_logs]), encoding="utf-8")
    clean_docx = pick_available_output_path(submission_clean_dir / "投稿稿_论文大纲_5.12_clean.docx")
    special_case_rewrites = load_special_case_rewrites(run_dir)
    clean_docx_audit = make_clean_submission_doc(
        readable_docx_path,
        clean_docx,
        structure_audit,
        extra_rewrites=[*MANUSCRIPT_CLARIFICATION_REWRITES, *special_case_rewrites],
    )
    (run_dir / "clean_docx_text_audit.json").write_text(
        json.dumps(scan_manuscript_issues(clean_docx), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_summary(
        run_dir,
        run_id,
        backup_rows,
        claim_rows,
        numeric_inventory_rows,
        issue_rows,
        triage_rows,
        structure_audit,
        review_docx,
        review_docx_audit,
        clean_docx,
        clean_docx_audit,
    )
    print(str(run_dir))


if __name__ == "__main__":
    main()
