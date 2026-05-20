import os
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = r"D:\研究生\项目\课题7-临床评测\自动测评系统\测评结果"
CENTERS = ["佛山", "武汉", "新疆"]

def main():
    logger.info("开始复制Excel文件到根目录...")
    
    for center in CENTERS:
        center_dir = os.path.join(BASE_DIR, center)
        if not os.path.exists(center_dir):
            logger.warning(f"中心目录不存在: {center_dir}")
            continue
        
        # 遍历模型文件夹
        for model_name in os.listdir(center_dir):
            model_dir = os.path.join(center_dir, model_name)
            if not os.path.isdir(model_dir):
                continue
            
            # 查找Excel文件
            for file in os.listdir(model_dir):
                if file.startswith("Evaluation_Summary_") and file.endswith("_CN.xlsx") and "_Parsed" not in file:
                    src_path = os.path.join(model_dir, file)
                    dst_path = os.path.join(center_dir, file)
                    
                    shutil.copy2(src_path, dst_path)
                    logger.info(f"复制: {file} -> {center}/")
    
    logger.info("✅ 文件复制完成！")

if __name__ == "__main__":
    main()
