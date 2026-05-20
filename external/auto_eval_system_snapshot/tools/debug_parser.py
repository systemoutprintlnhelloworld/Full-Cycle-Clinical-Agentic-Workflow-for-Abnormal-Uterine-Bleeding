from parse_html_trace import HtmlTraceParser
import json

def debug():
    path = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Wuhan\deepseek-v3-1-think-250821\html_traces\deepseek-v3-1-think-250821_Wuhan_wuhan_10_trace.html"
    print(f"Parsing: {path}")
    
    parser = HtmlTraceParser(path)
    if not parser.load():
        print("Failed to load")
        return

    print(f"Loops Found: {len(parser.d2_loops)}")
    for i, loop in enumerate(parser.d2_loops):
        print(f"--- Loop {i+1} ---")
        print("Keys:", loop.keys())
        print("Doc JSON Len:", len(loop.get("Doc_Raw_JSON", "")))
        print("Judge JSON Len:", len(loop.get("Judge_Raw_JSON", "")))
        print("Judge JSON Content:", loop.get("Judge_Raw_JSON", "")[:100])
        print("Judge Match Count:", loop.get("Judge_Match_Count"))

if __name__ == "__main__":
    debug()
