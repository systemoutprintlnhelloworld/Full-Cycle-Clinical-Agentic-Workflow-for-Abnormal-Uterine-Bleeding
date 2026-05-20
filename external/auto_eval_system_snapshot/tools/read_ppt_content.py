
import zipfile
import re
import os
import sys

def extract_pptx_text(path):
    text_content = []
    try:
        with zipfile.ZipFile(path, 'r') as z:
            for file in z.namelist():
                if file.startswith("ppt/slides/slide"):
                    xml_content = z.read(file).decode("utf-8")
                    texts = re.findall(r'<a:t[^>]*>(.*?)</a:t>', xml_content)
                    if texts:
                        text_content.append(f"--- Slide {file} ---")
                        text_content.extend(texts)
        return "\n".join(text_content)
    except Exception as e:
        return f"Error reading PPTX: {e}"

def extract_ppt_strings(path):
    text_content = []
    try:
        with open(path, 'rb') as f:
            content = f.read()
            # Extract printable strings longer than 4 chars
            matches = re.findall(b'[\x20-\x7E]{4,}', content)
            text_content = [m.decode('utf-8', errors='ignore') for m in matches]
        return "\n".join(text_content)
    except Exception as e:
        return f"Error reading PPT binary: {e}"

if __name__ == "__main__":
    base_dir = r"d:\研究生\项目\课题7-临床评测\自动测评系统\docs"
    pptx_path = os.path.join(base_dir, "评测流程讲解与查漏(持续更新).pptx")
    ppt_path = os.path.join(base_dir, "汇报11.30.ppt")

    print(f"=== Content from {pptx_path} ===")
    print(extract_pptx_text(pptx_path)[:2000]) # Print first 2000 chars

    print(f"\n\n=== Content from {ppt_path} (Strings) ===")
    print(extract_ppt_strings(ppt_path)[:2000])
