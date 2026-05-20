import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
import logging
from math import pi

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set style
sns.set(style="whitegrid")
plt.rcParams['font.sans-serif'] = ['SimHei'] # For Chinese characters
plt.rcParams['axes.unicode_minus'] = False

class Visualizer:
    def __init__(self, summary_path: str, raw_data_path: str, output_dir: str):
        self.summary_df = pd.read_csv(summary_path)
        self.raw_df = pd.read_csv(raw_data_path)
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
    def generate_all(self):
        self.plot_radar_charts()
        self.plot_funnel_stacked_bar()
        self.plot_loop_boxplot()
        # self.plot_calibration() # Needs raw confidence data extraction

    def plot_radar_charts(self):
        """Generates Radar Chart for Model Comparison (Center Average)"""
        # Metrics to show
        metrics = ["Metric_Check_Recall", "Metric_Check_Precision", "Metric_Check_F1", "Gate1_Pass_Rate", "Gate2_Pass_Rate"]
        labels = ["Recall", "Precision", "F1", "Gate1 Pass", "Gate2 Pass"]
        
        # Aggregate by Model (average across centers)
        model_avg = self.summary_df.groupby("Model")[metrics].mean().reset_index()
        
        # Setup plot
        N = len(metrics)
        angles = [n / float(N) * 2 * pi for n in range(N)]
        angles += angles[:1] # Close the circle
        
        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
        
        for _, row in model_avg.iterrows():
            values = row[metrics].values.flatten().tolist()
            values += values[:1]
            ax.plot(angles, values, linewidth=1, linestyle='solid', label=row["Model"])
            ax.fill(angles, values, alpha=0.1)
            
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels)
        plt.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1))
        plt.title("Model Performance Overview (Avg across Centers)")
        
        out_path = os.path.join(self.output_dir, "model_radar_comparison.png")
        plt.savefig(out_path)
        logger.info(f"Saved Radar Chart: {out_path}")
        plt.close()

    def plot_funnel_stacked_bar(self):
        """Gate Pass Rate Stacked Bar Chart by Model"""
        # Data prep
        # We want to show drop-off: Input -> Gate1 -> Gate2 -> Gate3
        # But here we just plot Pass Rates for simplicity as per plan
        
        df = self.summary_df.groupby("Model")[["Gate1_Pass_Rate", "Gate2_Pass_Rate", "Gate3_Pass_Rate"]].mean()
        
        ax = df.plot(kind='bar', stacked=False, figsize=(10, 6))
        plt.title("Gate Pass Rates by Model")
        plt.ylabel("Pass Rate")
        plt.ylim(0, 1.0)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        out_path = os.path.join(self.output_dir, "gate_pass_rates.png")
        plt.savefig(out_path)
        logger.info(f"Saved Gate Pass Chart: {out_path}")
        plt.close()

    def plot_loop_boxplot(self):
        """Boxplot of D1 Loop Counts by Center"""
        plt.figure(figsize=(10, 6))
        sns.boxplot(x="Center", y="Metric_Loop_Count_D1", hue="Model", data=self.raw_df)
        plt.title("Outpatient Loop Count Distribution")
        plt.ylabel("Loop Count")
        plt.tight_layout()
        
        out_path = os.path.join(self.output_dir, "loop_count_boxplot.png")
        plt.savefig(out_path)
        logger.info(f"Saved Loop Boxplot: {out_path}")
        plt.close()

if __name__ == "__main__":
    viz = Visualizer(
        summary_path=r"D:\研究生\项目\课题7-临床评测\自动测评系统\analysis\metrics_summary.csv",
        raw_data_path=r"D:\研究生\项目\课题7-临床评测\自动测评系统\analysis\merged_data.csv",
        output_dir=r"D:\研究生\项目\课题7-临床评测\自动测评系统\analysis\output\charts"
    )
    viz.generate_all()
