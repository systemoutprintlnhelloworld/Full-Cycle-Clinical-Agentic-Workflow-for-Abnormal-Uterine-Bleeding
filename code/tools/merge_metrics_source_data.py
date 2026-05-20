from pathlib import Path
import pandas as pd

paths = [
    Path(r"outputs/2026-02-03_13-07-40_latest_foshan/metrics_source_data.xlsx"),
    Path(r"outputs/2026-02-03_13-08-29_latest_wuhan/metrics_source_data.xlsx"),
    Path(r"outputs/2026-02-03_13-09-15_latest_xinjiang/metrics_source_data.xlsx"),
]

xls = [pd.ExcelFile(p) for p in paths]
sheets = sorted({s for xl in xls for s in xl.sheet_names})

out = Path(r"outputs/latest/summary/metrics_source_data.xlsx")
out.parent.mkdir(parents=True, exist_ok=True)

with pd.ExcelWriter(out, engine="openpyxl") as writer:
    for sheet in sheets:
        frames = []
        for xl in xls:
            if sheet in xl.sheet_names:
                frames.append(xl.parse(sheet))
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        combined.to_excel(writer, sheet_name=sheet, index=False)

print(out)
print(out.stat().st_size)
