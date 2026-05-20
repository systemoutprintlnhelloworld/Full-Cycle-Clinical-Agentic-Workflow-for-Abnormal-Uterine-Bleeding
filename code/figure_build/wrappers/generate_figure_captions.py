"""Generate caption.md for figure directories containing multiple images."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FIG_ROOT = ROOT / "analysis_viz" / "figures"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}


def _topic_from_name(file_name: str) -> str:
    name = file_name.lower()
    if "sankey" in name:
        return "病例在六个环节中的流向与退出路径"
    if "alignment" in name:
        return "人工评分与LLM评估在结果或推理层面的对齐程度"
    if "memory" in name:
        return "模型跨环节记忆保持能力"
    if "consistency" in name:
        return "模型在多环节决策中的一致性表现"
    if "reasoning" in name:
        return "推理链条质量与证据完整性"
    if "calibration" in name:
        return "置信度校准误差与可靠性关系"
    if "check_match" in name:
        return "检查建议与GT的匹配率"
    if "loop_inefficiency" in name:
        return "重复检查与低效循环程度"
    if "judge_score" in name or "judge_scores" in name:
        return "Judge score在中心、模型与环节上的分布差异"
    if "dataset" in name or name.startswith("fig1"):
        return "数据集构成、覆盖度与难度分布"
    if "special" in name or "d1" in name or "d3" in name:
        return "特殊病例与异常路径的行为特征"
    return "核心指标在中心、模型与环节维度下的统计特征"


def _caption_for(file_name: str) -> str:
    topic = _topic_from_name(file_name)
    return (
        f"该图用于展示“{topic}”的定量结果。横轴通常表示模型、中心或环节类别，纵轴表示对应指标值、比例或评分；"
        f"颜色与图例区分不同模型（deepseek-v3、gpt-5、gemini-2.5p、grok-4、claude-4.1），"
        "分组/分面用于比较三中心差异。该图用于支撑论文中关于性能差异、稳定性与可解释性的结论。"
    )


def main() -> None:
    target_dirs: list[Path] = []
    for directory in sorted(FIG_ROOT.rglob("*")):
        if not directory.is_dir():
            continue
        images = [
            file
            for file in sorted(directory.iterdir())
            if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
        ]
        if len(images) < 2:
            continue
        target_dirs.append(directory)

    for directory in target_dirs:
        images = [
            file
            for file in sorted(directory.iterdir())
            if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
        ]
        lines: list[str] = []
        lines.append(f"# 图注（{directory.relative_to(ROOT).as_posix()}）")
        lines.append("")
        lines.append("说明：以下图注面向论文写作与审阅，逐图解释图中元素、比较维度与解读目的。")
        lines.append("")
        for image_file in images:
            lines.append(f"## {image_file.name}")
            lines.append(_caption_for(image_file.name))
            lines.append("")

        target = directory / "caption.md"
        target.write_text("\n".join(lines), encoding="utf-8")
        print("WROTE", target)


if __name__ == "__main__":
    main()
