# 参数依据与使用边界

这些值是可复现的首版基线，不是行业标准。上线前应使用真实匿名流量做分桶实验，再按延迟、成本和质量共同调参。

| 参数 | 当前值 | 参考性 | 验证方式 |
|---|---:|---|---|
| `RAG_TOP_K` | 3 | 线上上下文预算的起点，减少噪声与 token 成本 | 以 `Recall@3`、回答引用正确率和延迟共同选择 |
| `RAG_CANDIDATE_K` | 10 | 用于 `MRR@10` 的候选诊断深度 | 比较 10/20/50 的召回增益与数据库耗时 |
| `EMBEDDING_DIMENSIONS` | 512 | `text-embedding-v4` 支持的成本优先配置；不是效果最优的证明 | 对 512/1024 做同一数据集 A/B，记录 Recall、MRR、存储和延迟 |
| `*_TIMEOUT_SECONDS` | 15 秒 | 本地演示的容错起点 | 用线上 P95/P99 延迟加安全余量设定 |
| 分类/决策/回复重试 | 2 | 可用性优先，但最坏等待会增加 | 只对超时和可重试错误重试，观察成功增益和尾延迟 |
| Reviewer 重试 | 1 | 安全链路应快速失败并降级到规则审核 | 统计模型审核失败率与规则 fallback 比例 |
| Worker 租约 | 60 秒，约 20 秒心跳 | 覆盖常规 Agent 调用且能在崩溃后较快恢复 | 按真实任务 P99 时长、心跳失败率和恢复时间调整 |
| Worker 最大尝试 | 3 | 防止永久重试，同时容忍短暂外部故障 | 统计按错误类型的重试成功率与死信比例 |
| 上下文字符预算 | 9000 | 当前实现按字符近似，不等同模型 token | 接入模型 tokenizer 后用 token 预算替换 |
| chunk | 500 字符，重叠 80 | 中文短政策的启发式初值 | 扫描 300/500/800 与不同 overlap，按 Recall/MRR 和引用完整性选择 |

`LLM_ENABLED=false` 是可重复、无外部依赖的演示模式；它的结果必须标记为 `offline_rules`。只有显式启用模型并配置密钥后，才可以把实验称为模型链路评估。

## 如何解释评测分数

- `evals/quality_baseline.json` 是小型、确定性回归门禁。某条固定用例从通过变为失败就应阻止合并，因此部分阈值设为 1.0。
- 这不表示系统有 100% 的生产准确率。任务和安全报告包含样本量与 95% Wilson 置信区间；20/20 的任务成功率，其区间下界仍只有约 83.9%。
- `offline_rule_components` 只验证规则分类、抽取、确认与 guardrail 的组合，不包含真实模型、数据库和工具链的端到端不确定性。
- 生产候选目标见 `targets/production-candidate.json`，它只是启动讨论的目标，必须在真实匿名验证集上重新确认。

## 当前仍需生产化的部分

- 检索仍会读取全部活跃 chunk 并在应用内打分；数据量增大后应改为数据库全文索引和向量索引，再保留相同评测接口。
- 限流支持 Redis 原子滑动窗口；本地默认使用内存模式，Compose 使用 Redis。`local` 故障模式会在 Redis 短暂不可用时退回单进程保护，但多实例全局配额会暂时失真；高安全入口可设为 `deny` 直接返回 503。
- token 数仍是字符估算，应该改用与实际模型一致的 tokenizer。
- 本地自动测试主要使用 SQLite 和 Redis mock；CI 已配置 MySQL 8.4、真实 Redis 往返与数据库 RAG 门禁，但仍需由 GitHub Actions 实际执行验证。发布前还需要真实模型沙箱和故障注入测试。
- Prometheus 已覆盖 HTTP、Worker、Agent、RAG 和 Tool 的低基数指标，并提供单机 Grafana 仪表盘与告警规则；多副本应由 Prometheus 分别抓取并聚合。`AgentRun` 提供持久化业务记录和 correlation ID，但日志仍需接入实际 Loki/ELK，告警还需连接 Alertmanager/on-call 渠道，并用真实流量验证保留期、SLO 阈值和告警噪声。
- `offline_agent_workflow_with_fake_tools` 会遍历真实 Agent 状态机，但工具返回值是确定性的替身；它不能替代真实 MySQL、外部模型和并发 worker 的端到端成功率。
- `tau_bench_inspired_offline_retail` 增加了可变业务状态、工具轨迹、参数、策略违规和 `Pass^k` 检查，能发现“回复看似正确但数据库状态错误”的问题；当前 10 个自建用例、每例 3 次仍只是回归集，不是官方 τ-bench 或生产流量验证。后续应接入受控模型沙箱、扩充人工盲标任务并运行真实 MySQL 工具链。
- 本次 `latest` 报告使用 `--skip-rag`，因此不包含可对外宣称的 Recall@5/MRR@10 实测值；必须在已迁移、已灌入知识库的数据库上单独运行关键词与 Hybrid 实验。
- 浏览器已改用 `HttpOnly`、`SameSite=Strict` Cookie；公网 HTTPS 部署必须设置 `AUTH_COOKIE_SECURE=true`，若未来放宽 SameSite 或允许跨站前端，还必须增加独立 CSRF Token 校验。
- 物流数据现在按 `user_id` 隔离；升级已有数据库后需重新运行演示数据初始化，为旧的空归属物流记录补齐所有者。
