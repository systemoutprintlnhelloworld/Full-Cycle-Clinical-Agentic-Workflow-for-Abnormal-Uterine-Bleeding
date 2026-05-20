# Protected render policy

The user explicitly required that existing `FigXX/render` files must not be affected.

For this repository creation step, the policy was:

1. Copy only; never move or delete source files.
2. Exclude every path matching `\Fig\d+\render\`.
3. Do not run figure-generation scripts that can overwrite the existing render outputs.
4. Hash the original protected render files before and after organization.
5. Verify that the new repository contains no `Fig*/render` directory.

The protected source directory was:

`D:/研究生/项目/课题7-临床评测/LLM as judge评分系统 & 量化指标系统/work/paper_crosscheck/2026-05-14_v2-subplots_submission_fix/submission_bundle/`

The protection manifests are stored in the original project under:

`work/paper_crosscheck/2026-05-20_submission_code_repo_organize/`

