# PostgreSQL 生产存储与迁移

2026-10-20 · V2.23。2.1 的生产 SQL 联调已验收，累计 34/38。SQL、对话原文、批次摘要、人格/关系、记忆状态及本地实体索引均已在真实 PostgreSQL 验证。参考宿主仍按单进程运行；多 worker 编排与分布式租约不属于这次验收。

## 运行

设置 `COMPANION_LITE_MODE=false`、`COMPANION_POSTGRES_URL` 和 `COMPANION_REDIS_URL`，通过宿主环境或忽略的配置注入凭据。数据库管理员提前安装/创建 `vector` 扩展，再给应用账号本数据库的表/索引管理权限。应用无需超级用户。缺少扩展或初始化失败会阻止启动，不会吞掉失败后继续使用已中止事务。

默认豆包向量仍为 1024 维。新表采用 HNSW 余弦索引，避免在空表上训练 IVFFlat 100 个列表；已有 IVFFlat 不自动删除，应在备份和检查查询计划后由管理员决定是否移除。这里未做容量、并发吞吐或 ANN 召回率基准。

SQL 的标签列为 JSON/JSONB；写入绑定 JSON 文本并显式转换，读取兼容驱动返回的列表或文本。静态 `scripts/init_pgvector.sql` 与运行时已对齐，不再新增运行时无法填写的必填 `entry_id`。

## 历史结构

先备份并停止写入，在后端目录或已安装的 wheel 环境运行：

```text
python -m memory_system.postgres_schema
python -m memory_system.postgres_schema --apply
```

第一条只输出结构变更列表。第二条在同一个事务中保留数据地转换文本向量与数组标签，并解除废弃别名列的必填限制，原 ID、别名、内容和约束值保留。源码入口 `python tools/migrate_postgres.py` 等效。

向量值无效时整笔回滚；已固定为其他维度的向量列拒绝转换，需要管理员显式重新生成向量。正常启动对可转换文本列使用 `ALTER ... USING`，不再删除/重建向量列；老数组标签/必填别名要求先显式迁移。旧 `users.user_id` 所有权字段若存在，隐私导出/删除也按该字段匹配非 UUID 用户，避免漏清历史用户行。

## 可重复验证

使用专用 `companion_test_*` / `companion_*_qa` 数据库和独立缓存，将连接放入 `COMPANION_TEST_POSTGRES_URL`、`COMPANION_TEST_REDIS_URL`：

```text
python integration/scripts/smoke_postgres.py
python integration/scripts/smoke_postgres_migration.py
```

第一项启动真实参考宿主，两个进程验证非超级用户的向量写入/查询、标签、失败回滚、重启原文/摘要、并发关系去重、账号/会话隔离、图谱依据、导出/删除与旧代次写入屏障。使用固定合成向量，不调用模型。第二项在临时 schema 验证迁移的只读预览、内容保留、幂等、非法值回滚、维度拒绝及旧用户归属；事务最终回滚整个测试 schema。

CI 已新增 PostgreSQL/pgvector 与 Redis 7 服务和上述门禁，但本轮尚未在远端运行 workflow。本机实际运行 PostgreSQL 17.11、从官方 v0.8.7 源码编译的 pgvector；临时缓存为官方 Microsoft Garnet v2.2.3 的真实 Redis 兼容服务，发布 SHA256 已验证。它不替代 Redis 7 的独立部署验收。

另用合成用户和隔离配置完成真实方舟 1024 维向量、三轮批次压缩、SQL 提交、进程重启以及新会话回忆城市。真实调用只读取私有配置，输出报告不含密钥。后端完整 765 passed（40.47 秒，严格线程警告），存储/人格/隐私子集 133 passed（4.52 秒）；Web 无变动，沿用 V2.21 的81项与双端构建。Neo4j/旧图归属迁移、平台、实际 Docker/远端 CI 与3D仍待验收。

软件来源：[PostgreSQL Windows](https://www.postgresql.org/download/windows/)、[EDB 免安装包](https://www.enterprisedb.com/download-postgresql-binaries)、[pgvector](https://github.com/pgvector/pgvector)、[Garnet](https://github.com/microsoft/garnet/releases)。
