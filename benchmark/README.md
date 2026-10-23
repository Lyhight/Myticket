# MyTicket Benchmark

该目录把线上业务实现与离线质量验证分开，便于重复实验和面试演示。

## 指标

- RAG：Recall@1、Recall@3、Recall@5、MRR@10、无关问题拒绝率。
- Agent：组件准确率与任务级成功率；任务只有在所有必要期望字段均正确时才算成功。
- Stateful Tool-Agent：工具选择、参数、最终业务状态、策略违规率与 `Pass^k`。
- Safety：准确率、误拦率（安全样本被拦）和漏放率（风险样本被放行）。

## 运行

从 `backend` 目录执行：

```powershell
python run_benchmark.py --skip-rag
python run_benchmark.py
python run_benchmark.py --hybrid
```

第一条命令完全离线。RAG 评估需要已迁移并写入知识库的数据库。默认报告会按 UTC 时间写入 `benchmark/reports/runs/<run-id>`，不会覆盖历史实验；也可用 `--output` 指定目录。
`--hybrid` 还要求 `EMBEDDING_ENABLED=true` 和有效的
`DASHSCOPE_API_KEY`；缺少配置时会失败，而不会静默降级后产生标签失真的报告。

任务成功率当前标记为 `offline_rule_components`，用于验证分类、抽取、确认、安全等确定性组件的回归，不等价于在线大模型端到端成功率。报告同时输出 95% Wilson 置信区间；小样本即使得到 100%，区间下界也会明显低于 100%，因此不能把它解释成生产效果保证。

`retail_tool_agent` 使用每次试验独立重置的内存业务环境，执行真实
`CustomerServiceAgent` 状态机，并检查多轮对话后的工具轨迹和退款最终状态。
`Pass^k` 表示同一任务的 k 次试验全部成功的任务比例，比单次平均成功率更强调稳定性。
该数据集只借鉴 τ-bench 的“用户任务 + 工具 + 最终环境状态”评测思想，报告明确输出
`official_tau_bench=false`；它不是官方 τ-bench 数据集，也不能对外宣称为官方 τ-bench 分数。

`rag_runtime_top_k=3` 是线上实际注入上下文的数量；评估深度为 10，用于计算 `Recall@5` 与 `MRR@10`。线上主观感知更应关注 `Recall@3`，`Recall@5/MRR@10` 主要用于诊断候选召回与排序。

实验配置位于 `experiments/`；每次实验应记录数据集版本、Prompt 版本和检索策略，避免只比较最终分数而无法复现。

参数依据、可参考范围和仍未解决的生产化边界见 `PARAMETERS.md`。不要把回归门禁中的 100% 当作生产准确率。

项目根目录的 `scripts/verify_release.ps1` 会统一执行离线 Benchmark、质量门禁、
测试、迁移头和前端构建，适合作为提交或面试演示前的本地验收入口。
