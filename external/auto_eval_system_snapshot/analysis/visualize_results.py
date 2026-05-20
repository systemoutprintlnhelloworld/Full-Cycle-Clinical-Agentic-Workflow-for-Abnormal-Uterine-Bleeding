import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
import math
from matplotlib.patches import Polygon

# Set style
sns.set_theme(style="whitegrid")
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial'] # Support Chinese
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = r"D:\研究生\项目\课题7-临床评测\自动测评系统\output\figures"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

SUMMARY_PATH = r"D:\研究生\项目\课题7-临床评测\自动测评系统\analysis\analysis_summary.csv"
DETAILS_DIR = r"D:\研究生\项目\课题7-临床评测\自动测评系统\output\metrics"

def get_detail_path(stage):
    return os.path.join(DETAILS_DIR, f"Metric_{stage}.xlsx")

def plot_hex_radar(df):
    """Generate 6-Axis Radar Chart for each Center."""
    # 6 axes as requested:
    # D1 Diag, D1 Exam, D2 Diag, D2 Exam/Plan, D3 Surg, D4 Rehab
    # Mapping based on "Score_" cols in global summary
    
    # We need to find columns that match these concepts. 
    # Use fuzzy matching or known substrings.
    # D1 Diag: Score_D1_...诊断...
    # D1 Exam: Score_D1_...检查...
    # D2 Diag: Score_D2_...确诊... or 诊断
    # D2 Plan: Score_D2_...方案... or 治疗
    # D3 Surg: Score_D3_... ? D3 usually just pass? Or has scores?
    # D4 Rehab: Score_D4_...
    
    # Let's inspect df cols first to be safe, but for now we define patterns
    axis_patterns = [
        ('D1 Diagnosis', 'Score_D1', '诊断'),
        ('D1 Exam', 'Score_D1', '检查'),
        ('D2 Diagnosis', 'Score_D2', '能够确诊'), # or 诊断
        ('D2 Plan', 'Score_D2', '治疗'), # or 方案
        ('D3 Surgery', 'Score_D3', '诊断'), # Assuming D3 has some score, if not we skip
        ('D4 Rehab', 'Score_D4', '康复')
    ]
    
    # Check what's actually available in df
    available_axes = []
    for label, stage_prefix, keyword in axis_patterns:
        # Find col
        col = next((c for c in df.columns if stage_prefix in c and keyword in c), None)
        if col:
            available_axes.append((label, col))
        else:
            # Try looser match
            col = next((c for c in df.columns if stage_prefix in c), None)
            if col: 
                # Rename label to generic if specific not found?
                # available_axes.append((f"{stage_prefix} Score", col))
                pass

    if len(available_axes) < 3:
        print("Not enough score columns for Hex Radar.")
        return

    centers = df['Center'].unique()
    
    for center in centers:
        subset = df[df['Center'] == center].copy()
        if subset.empty: continue
        
        labels = [item[0] for item in available_axes]
        
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, polar=True)
        
        # Fixed scale 0-10
        ax.set_ylim(0, 10)
        
        for idx, row in subset.iterrows():
            values = []
            for _, col in available_axes:
                val = row.get(col, 0)
                if pd.isna(val): val = 0
                values.append(val)
            
            # Close loop
            values += values[:1]
            angles = [n / float(len(labels)) * 2 * math.pi for n in range(len(labels))]
            angles += angles[:1]
            
            ax.plot(angles, values, linewidth=2, linestyle='solid', label=row['Model'])
            ax.fill(angles, values, alpha=0.05)
            
        plt.xticks(angles[:-1], labels, fontsize=11)
        plt.yticks([2, 4, 6, 8, 10], color="grey", size=8)
        plt.title(f"Clinical Capability Radar (6-Axis) - {center}", y=1.08, fontsize=15)
        plt.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
        
        out_path = os.path.join(OUTPUT_DIR, f"radar_hex_{center}.png")
        plt.tight_layout()
        plt.savefig(out_path, dpi=100)
        plt.close()
        print(f"Saved Hex Radar: {out_path}")

def plot_sankey_flow(df):
    """
    Simulate a Sankey Diagram using filled curves.
    Flow: Total -> D1 Pass -> D2 Pass -> D3 Pass
    """
    centers = df['Center'].unique()
    
    for center in centers:
        subset = df[df['Center'] == center]
        if subset.empty: continue
        
        models = subset['Model'].unique()
        n_models = len(models)
        
        fig, axes = plt.subplots(n_models, 1, figsize=(10, 3 * n_models), sharex=True)
        if n_models == 1: axes = [axes]
        
        stages = ["Total", "D1 Pass", "D2 Pass", "D3 Pass"]
        x_stages = [0, 1, 2, 3] # x-coordinates
        
        for ax, model in zip(axes, models):
            row = subset[subset['Model'] == model].iloc[0]
            
            # Counts
            counts = [
                row.get('Total_Cases', 0),
                row.get('Count_D1', 0),
                row.get('Count_D2', 0),
                row.get('Count_D3', 0)
            ]
            
            # Normalize to Max = 100% height? Or absolute counts?
            # User might want completion RATE or absolute count. 
            # Let's do Absolute Count but annotated.
            
            # Draw "River"
            # Top line and Bottom line. Center them around y=0?
            # Or just flat bottom? Flat bottom is easier for bar-like sankey.
            # Let's center it for "Funnel" look.
            
            y_upper = [c/2 for c in counts]
            y_lower = [-c/2 for c in counts]
            
            # Smooth curves?
            # Just fill_between with step? Or simple lines.
            # Let's use simple polygon filling for "Trapezoid" segments
            for i in range(len(stages)-1):
                x1, x2 = x_stages[i], x_stages[i+1]
                y1_top, y2_top = y_upper[i], y_upper[i+1]
                y1_bot, y2_bot = y_lower[i], y_lower[i+1]
                
                # Polygon points
                verts = [
                    (x1, y1_bot), (x1, y1_top),
                    (x2, y2_top), (x2, y2_bot)
                ]
                poly = Polygon(verts, facecolor=sns.color_palette("Blues")[i+1], alpha=0.7, edgecolor='none')
                ax.add_patch(poly)
                
                # Add text label for drop
                drop = counts[i] - counts[i+1]
                if drop > 0:
                    mid_x = (x1 + x2) / 2
                    # ax.text(mid_x, (y1_top+y2_top)/2 + (counts[0]*0.1), f"-{int(drop)}", ha='center', color='red', fontsize=8)
            
            # Add vertical lines/bars at nodes
            for i, x in enumerate(x_stages):
                ax.vlines(x, y_lower[i], y_upper[i], colors='black', lw=2)
                ax.text(x, y_upper[i] + (counts[0]*0.05), f"{int(counts[i])}", ha='center', va='bottom', weight='bold')
                if i < len(stages):
                    ax.text(x, y_lower[i] - (counts[0]*0.05), stages[i], ha='center', va='top')

            ax.set_title(f"Flow: {model}", loc='left', fontsize=12)
            ax.set_xlim(-0.5, 3.5)
            ax.set_ylim(-counts[0]*0.7, counts[0]*0.7)
            ax.axis('off')
            
        plt.suptitle(f"Clinical Process Flow (Sankey-style) - {center}", y=0.99)
        plt.tight_layout()
        out_path = os.path.join(OUTPUT_DIR, f"sankey_{center}.png")
        plt.savefig(out_path, dpi=120)
        plt.close()
        print(f"Saved Sankey: {out_path}")

def plot_calibration_curve(summary_df):
    """
    Plot Reliability Diagram: Mean Confidence vs Observed Accuracy.
    Needs detailed data, not just summary.
    We will load Metric_D1/D2/D3 details.
    """
    # Combine all stages that have confidence
    details = []
    
    # D1
    path_d1 = get_detail_path("D1_Decision")
    if os.path.exists(path_d1):
        df = pd.read_excel(path_d1)
        if 'Confidence_Raw' in df.columns:
            df['Stage'] = 'D1'
            details.append(df)
            
    # D2
    path_d2 = get_detail_path("D2_Decision")
    if os.path.exists(path_d2):
        df = pd.read_excel(path_d2)
        if 'Confidence_Raw' in df.columns:
            df['Stage'] = 'D2'
            details.append(df)
            
    # D3
    path_d3 = get_detail_path("D3_Decision")
    if os.path.exists(path_d3):
        df = pd.read_excel(path_d3)
        if 'Confidence_Raw' in df.columns:
            df['Stage'] = 'D3'
            details.append(df)
            
    if not details:
        print("No confidence data found for calibration.")
        return
        
    full_df = pd.concat(details)
    full_df['Confidence'] = pd.to_numeric(full_df['Confidence_Raw'], errors='coerce')
    full_df.dropna(subset=['Confidence'], inplace=True)
    
    # Normalize if needed. Assuming 0-1 for now. If > 1, maybe divide by 5 or 100?
    # Simple heuristic check
    if full_df['Confidence'].max() > 1.0:
        if full_df['Confidence'].max() <= 5.0:
            full_df['Confidence'] /= 5.0
        else:
            full_df['Confidence'] /= 100.0
            
    # Plot
    plt.figure(figsize=(8, 8))
    plt.plot([0, 1], [0, 1], "k:", label="Perfectly Calibrated")
    
    models = full_df['Model'].unique()
    for model in models:
        subset = full_df[full_df['Model'] == model]
        # Binning
        bins = np.linspace(0, 1, 6) # 5 bins
        bin_indices = np.digitize(subset['Confidence'], bins)
        
        prob_true = []
        prob_pred = []
        
        for i in range(1, len(bins)):
            in_bin = subset[bin_indices == i]
            if len(in_bin) > 0:
                prob_true.append(in_bin['Passed'].mean())
                prob_pred.append(in_bin['Confidence'].mean())
            else:
                pass 
                
        plt.plot(prob_pred, prob_true, "s-", label=model)
        
    plt.xlabel("Mean Predicted Confidence")
    plt.ylabel("Fraction of Positives (Pass Rate)")
    plt.title("Confidence Calibration Curve")
    plt.legend(loc="lower right")
    plt.grid(True)
    
    out_path = os.path.join(OUTPUT_DIR, "calibration_curve.png")
    plt.savefig(out_path, dpi=120)
    plt.close()
    print(f"Saved Calibration: {out_path}")

def plot_metrics_table(df):
    """Generate a png table summarizing metrics (Previous function kept)."""
    disp = df.copy()
    
    if 'Loop_D1_Mean' in disp.columns:
        disp['D1 Loop'] = disp.apply(lambda r: f"{r['Loop_D1_Mean']:.2f}", axis=1)
    else: disp['D1 Loop'] = '-'

    if 'Pass_Rate_D2' in disp.columns:
        disp['D2 Pass%'] = (disp['Pass_Rate_D2'] * 100).fillna(0).apply(lambda x: f"{x:.1f}%")
    else: disp['D2 Pass%'] = '-'
        
    if 'Pass_Rate_D3' in disp.columns:
        disp['D3 Pass%'] = (disp['Pass_Rate_D3'] * 100).fillna(0).apply(lambda x: f"{x:.1f}%")
    else: disp['D3 Pass%'] = '-'
        
    if 'Overall_Score' in disp.columns:
        disp['Overall Score'] = disp['Overall_Score'].fillna(0).apply(lambda x: f"{x:.2f}")
    else: disp['Overall Score'] = '-'
        
    cols = ['Center', 'Model', 'D1 Loop', 'D2 Pass%', 'D3 Pass%', 'Overall Score']
    final_table = disp[cols].sort_values(['Center', 'Overall Score'], ascending=[True, False])
    
    fig, ax = plt.subplots(figsize=(12, len(final_table)*0.8 + 2))
    ax.axis('off')
    table = ax.table(cellText=final_table.values, colLabels=final_table.columns, loc='center', cellLoc='center')
    table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1.2, 1.5)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight='bold', color='white'); cell.set_facecolor('#4A90E2')
    
    plt.title("Multi-Model Capability Comparison", y=0.98, fontsize=14, weight='bold')
    out_path = os.path.join(OUTPUT_DIR, "metrics_table.png")
    plt.savefig(out_path, bbox_inches='tight', dpi=150)
    plt.close()
    print(f"Saved Metrics Table: {out_path}")

def plot_violin_chart(d1_path, d2_path):
    """(Previous function kept)"""
    data_list = []
    if os.path.exists(d1_path):
        d1 = pd.read_excel(d1_path)
        if 'Loop_Count' in d1.columns:
            d1['Stage'] = 'D1 Outpatient'
            data_list.append(d1[['Center', 'Model', 'Loop_Count', 'Stage']])
    if os.path.exists(d2_path):
        d2 = pd.read_excel(d2_path)
        if 'Loop_Count' in d2.columns:
            d2['Stage'] = 'D2 Admission'
            data_list.append(d2[['Center', 'Model', 'Loop_Count', 'Stage']])
            
    if not data_list: return
    full_df = pd.concat(data_list)
    plt.figure(figsize=(14, 7))
    sns.violinplot(data=full_df, x='Model', y='Loop_Count', hue='Stage', split=False, inner="quart")
    plt.title("Interaction Loop Distribution (D1 vs D2)")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "violin_loops.png"), dpi=120)
    plt.close()
    print("Saved Violin Plot")

def main():
    if os.path.exists(SUMMARY_PATH):
        summary_df = pd.read_csv(SUMMARY_PATH)
        plot_hex_radar(summary_df)
        plot_sankey_flow(summary_df)
        plot_metrics_table(summary_df)
        plot_calibration_curve(summary_df)
    
    d1_loop_path = os.path.join(DETAILS_DIR, "Metric_D1_Loop.xlsx")
    d2_loop_path = os.path.join(DETAILS_DIR, "Metric_D2_Loop.xlsx")
    plot_violin_chart(d1_loop_path, d2_loop_path)

if __name__ == "__main__":
    main()
