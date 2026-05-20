# System Output Header Report

## Sheet: 门诊检查循环
Count: 32
| Index | Column Name |
|---|---|
| 1 | CaseID |
| 2 | Timestamp |
| 3 | Model |
| 4 | Center |
| 5 | Loop_Count |
| 6 | Loop1_AI_Request |
| 7 | Loop1_Judge_Match_Count |
| 8 | Loop1_Judge_Total_Count |
| 9 | Loop1_Judge_Reason |
| 10 | Loop1_Judge_Response |
| 11 | Loop1_Judge_Warning |
| 12 | Loop1_Score_Match |
| 13 | Loop1_Score_Reasonable |
| 14 | Loop1_Score_Overall |
| 15 | Loop2_AI_Request |
| 16 | Loop2_Judge_Match_Count |
| 17 | Loop2_Judge_Total_Count |
| 18 | Loop2_Judge_Reason |
| 19 | Loop2_Judge_Response |
| 20 | Loop2_Judge_Warning |
| 21 | Loop2_Score_Match |
| 22 | Loop2_Score_Reasonable |
| 23 | Loop2_Score_Overall |
| 24 | Loop3_AI_Request |
| 25 | Loop3_Judge_Match_Count |
| 26 | Loop3_Judge_Total_Count |
| 27 | Loop3_Judge_Reason |
| 28 | Loop3_Judge_Response |
| 29 | Loop3_Judge_Warning |
| 30 | Loop3_Score_Match |
| 31 | Loop3_Score_Reasonable |
| 32 | Loop3_Score_Overall |


## Sheet: 门诊决策
Count: 25
| Index | Column Name |
|---|---|
| 1 | CaseID |
| 2 | Timestamp |
| 3 | Model |
| 4 | Center |
| 5 | Status |
| 6 | Context_Summary |
| 7 | Loop_Count |
| 8 | AI_Need_More_Checks |
| 9 | AI_Diagnosis_Info |
| 10 | AI_Preliminary_Diagnosis |
| 11 | AI_Suggested_Checks |
| 12 | AI_Diagnosis_Reasoning |
| 13 | AI_Check_Reasoning |
| 14 | AI_Conf_Diagnosis |
| 15 | AI_Conf_Check |
| 16 | AI_Raw_JSON |
| 17 | GT_Outpatient_Checks |
| 18 | GT_Admission_Diagnosis |
| 19 | Gate_Diagnosis_Match |
| 20 | Gate_Diagnosis_Reason |
| 21 | Gate_Diagnosis_Score |
| 22 | Gate_Check_Match |
| 23 | Gate_Check_Score |
| 24 | Gate_Proceed |
| 25 | Gate_Overall_Score |


## Sheet: 入院检查循环
Count: 32
| Index | Column Name |
|---|---|
| 1 | CaseID |
| 2 | Timestamp |
| 3 | Model |
| 4 | Center |
| 5 | Loop_Count |
| 6 | Loop1_AI_Request |
| 7 | Loop1_Judge_Match_Count |
| 8 | Loop1_Judge_Total_Count |
| 9 | Loop1_Judge_Reason |
| 10 | Loop1_Judge_Response |
| 11 | Loop1_Judge_Warning |
| 12 | Loop1_Score_Match |
| 13 | Loop1_Score_Reasonable |
| 14 | Loop1_Score_Overall |
| 15 | Loop2_AI_Request |
| 16 | Loop2_Judge_Match_Count |
| 17 | Loop2_Judge_Total_Count |
| 18 | Loop2_Judge_Reason |
| 19 | Loop2_Judge_Response |
| 20 | Loop2_Judge_Warning |
| 21 | Loop2_Score_Match |
| 22 | Loop2_Score_Reasonable |
| 23 | Loop2_Score_Overall |
| 24 | Loop3_AI_Request |
| 25 | Loop3_Judge_Match_Count |
| 26 | Loop3_Judge_Total_Count |
| 27 | Loop3_Judge_Reason |
| 28 | Loop3_Judge_Response |
| 29 | Loop3_Judge_Warning |
| 30 | Loop3_Score_Match |
| 31 | Loop3_Score_Reasonable |
| 32 | Loop3_Score_Overall |


## Sheet: 入院决策
Count: 27
| Index | Column Name |
|---|---|
| 1 | CaseID |
| 2 | Timestamp |
| 3 | Model |
| 4 | Center |
| 5 | Context_Summary |
| 6 | Loop_Count |
| 7 | AI_Can_Diagnose |
| 8 | AI_History_Review |
| 9 | AI_Revised_Diagnosis |
| 10 | AI_Diagnosis_Reasoning |
| 11 | AI_Treatment_Plan |
| 12 | AI_Treatment_Reasoning |
| 13 | AI_PostOp_Summary |
| 14 | AI_Conf_Diagnosis |
| 15 | AI_Conf_Treatment |
| 16 | AI_Raw_JSON |
| 17 | GT_Revised_Diagnosis |
| 18 | GT_Surgery_Plan |
| 19 | Gate_Diagnosis_Match |
| 20 | Gate_Diagnosis_Reason |
| 21 | Gate_Diagnosis_Score |
| 22 | Gate_Surgery_Match |
| 23 | Gate_Surgery_Reason |
| 24 | Gate_Surgery_Feedback |
| 25 | Gate_Surgery_Score |
| 26 | Gate_Proceed |
| 27 | Gate_Overall_Score |


## Sheet: 手术决策
Count: 23
| Index | Column Name |
|---|---|
| 1 | CaseID |
| 2 | Timestamp |
| 3 | Model |
| 4 | Center |
| 5 | AI_Final_Diagnosis |
| 6 | AI_Final_Thinking |
| 7 | AI_PostOp_Plan |
| 8 | AI_PostOp_Thinking |
| 9 | AI_Info_Summary |
| 10 | AI_Conf_Diagnosis |
| 11 | AI_Conf_Plan |
| 12 | AI_Raw_JSON |
| 13 | GT_Final_Diagnosis |
| 14 | GT_PostOp_Plan |
| 15 | Judge_Diagnosis_Match |
| 16 | Judge_Diagnosis_Reason |
| 17 | Judge_Diagnosis_Score |
| 18 | Judge_Plan_Match |
| 19 | Judge_Plan_Reason |
| 20 | Judge_Plan_Score |
| 21 | Judge_Need_More_Info |
| 22 | Judge_Proceed |
| 23 | Judge_Overall_Score |


## Sheet: 出院康复
Count: 26
| Index | Column Name |
|---|---|
| 1 | CaseID |
| 2 | Timestamp |
| 3 | Model |
| 4 | Center |
| 5 | AI_Rehab_Plan |
| 6 | AI_Rehab_Thinking |
| 7 | AI_Rehab_Basis |
| 8 | AI_Followup_Need |
| 9 | AI_Followup_Plan |
| 10 | AI_Followup_Thinking |
| 11 | AI_Followup_Basis |
| 12 | AI_Info_Summary |
| 13 | AI_Conf_Rehab |
| 14 | AI_Conf_Followup |
| 15 | AI_Raw_JSON |
| 16 | GT_Patient_Wishes |
| 17 | GT_Rehab_Plan |
| 18 | GT_Followup_Plan |
| 19 | Judge_Rehab_Eval |
| 20 | Judge_Rehab_Reason |
| 21 | Judge_Rehab_Score |
| 22 | Judge_Followup_Eval |
| 23 | Judge_Followup_Reason |
| 24 | Judge_Followup_Score |
| 25 | Judge_Overall_Feedback |
| 26 | Judge_Overall_Score |

