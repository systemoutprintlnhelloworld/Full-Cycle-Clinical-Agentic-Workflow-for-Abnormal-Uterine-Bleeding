
import pandas as pd
import os

f = r"data\standardized_eval_dataset.xlsx"
df = pd.read_excel(f)
foshan_df = df[df["Center"] == "Foshan"]

print("Foshan Legacy Sample (Head):")
print(foshan_df.head(2)[["CaseID", "ChiefComplaint"]])

print("\nFoshan V2 Sample (Row 55-60):")
# Legacy is 53 rows. So index 53 starts V2.
print(foshan_df.iloc[55:60][["CaseID", "ChiefComplaint", "BasicInfo"]])
