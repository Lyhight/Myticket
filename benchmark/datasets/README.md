# 数据集说明

- `agent_tasks.json`：跨分类、实体、上下文恢复、确认和安全复核的任务级用例。
- `safety_cases.json`：输入注入与输出泄露的正负样本，用于计算误拦率和漏放率。
- `workflow_smoke.json`：穿过真实 Agent 状态机、使用确定性假业务工具的工作流冒烟集。
- `backend/evals/agent_cases.json`：原有组件级回归集，继续保留用于兼容。
- `backend/evals/rag_cases.json`：RAG 来源级召回集，评估 Recall@5 和 MRR@10。

所有样本均为合成数据，不包含真实客户信息。新增用例时必须同时给出稳定的 `id`、场景和期望结果。
