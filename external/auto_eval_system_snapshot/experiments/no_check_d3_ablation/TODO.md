# TODO

## 用户需求快照

- [x] 不修改原有自动测评系统任何现有代码
- [x] 创建独立消融实验项目
- [x] 流程固定到 D3 结束，不进入 gate 阶段
- [x] Judge 只打分，不决定是否进入下一阶段
- [x] 仅测试 baseline 中 D1/D2/D3 均顺利通过的模型-病例轨迹
- [x] 删除检查相关动态获取信息过程
- [x] 治疗方案与手术方案匹配后再给信息的机制改为默认给手术信息
- [x] Doctor 输入上下文不注入门诊/入院检查结果
- [x] D1 仅输出初步诊断，D1 不做方案匹配评分
- [x] 小规模测试 15 个病例
- [x] 并发 45 线程
- [x] 所有 gemini 调用走星辰（运行时强制）
- [x] 完成独立 workflow / judge / runner / checkpoint
- [x] 完成 15 病例联调（run_label: smoke15_20260411_45t_v4_xingchen_fixd1）
- [x] 输出汇总结果与日志
- [x] 失败轨迹续跑上下文导出（failed_tasks_for_resume.csv）

## 当前实现原则

- 优先复用原系统只读模块：`DoctorAgent`、`JudgeAgent`、`DataLoader`、`HtmlTraceLogger`
- 所有新 prompt、新 workflow、新输出目录、新 checkpoint 独立维护
- 先保证 doctor 自动化决策与 judge 打分链路通，再扩展大规模运行
