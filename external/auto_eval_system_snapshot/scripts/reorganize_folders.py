import os
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = r"D:\研究生\项目\课题7-临床评测\自动测评系统\测评结果"

# Mapping: v2 folder -> clean target folder
FOLDER_MAPPING = {
    "Foshan-v2": "佛山",
    "Wuhan_Fixed-v2": "武汉",
    "Xinjiang-v2": "新疆"
}

def main():
    logger.info("开始整理文件夹结构...")
    
    for v2_folder, target_folder in FOLDER_MAPPING.items():
        v2_path = os.path.join(BASE_DIR, v2_folder)
        target_path = os.path.join(BASE_DIR, target_folder)
        
        if not os.path.exists(v2_path):
            logger.warning(f"源文件夹不存在: {v2_path}")
            continue
        
        # Create target if not exists
        if not os.path.exists(target_path):
            os.makedirs(target_path)
            logger.info(f"创建目标文件夹: {target_path}")
        
        # Copy contents (model folders)
        for model_name in os.listdir(v2_path):
            src_model_dir = os.path.join(v2_path, model_name)
            if not os.path.isdir(src_model_dir):
                continue
            
            dst_model_dir = os.path.join(target_path, model_name)
            
            # Remove existing if present, then copy
            if os.path.exists(dst_model_dir):
                shutil.rmtree(dst_model_dir)
                logger.info(f"移除旧版本: {dst_model_dir}")
            
            shutil.copytree(src_model_dir, dst_model_dir)
            logger.info(f"复制: {model_name} -> {target_folder}/{model_name}")
        
        # Delete v2 folder
        shutil.rmtree(v2_path)
        logger.info(f"删除源文件夹: {v2_folder}")
    
    logger.info("✅ 文件夹结构整理完成！")

if __name__ == "__main__":
    main()
