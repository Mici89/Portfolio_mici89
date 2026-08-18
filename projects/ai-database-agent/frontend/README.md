# AI Database Agent Frontend

本地可视化工作台，覆盖：

1. 配置 MySQL、PostgreSQL、SQL Server、Oracle 或使用默认连接
2. 测试连接并扫描数据库结构
3. 浏览表、字段、索引和显式关系
4. 对选定表运行 Database Understanding Agent
5. 分层展示结论、业务依据、查询结果和原始 SQL
6. 整表或多选字段人工审核
7. 直接修改不认可的字段含义并生成 `vN-rM` 审核版本
8. 使用审核语义或 AI Catalog 运行自然语言查询
9. 展示字段映射、只读 SQL、真实结果和业务解释
10. 通过对话继续添加过滤条件、替换维度或增加指标
11. 自动识别新增、更新和删除数据的自然语言指令
12. 展示修改前数据、影响行数、安全检查与待执行 SQL
13. 在操作卡片中确认或取消，确认后展示事务回查结果
14. 匿名用户保持只读，数据库操作员登录后才能发起写操作
15. 新主题自动清理旧查询条件，省略年份的日期使用当前年份
16. 结果表展示完整有界查询结果，5行摘要仅用于模型上下文

## 本地启动

先启动后端：

```bash
cd projects/ai-database-agent/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

再启动前端：

```bash
cd projects/ai-database-agent/frontend
npm install
npm run dev
```

访问：

- 数据库工作台：<http://localhost:3000>
- 语义目录、证据与审核：<http://localhost:3000/catalog>
- 智能查询：<http://localhost:3000/query>

前端只连接 FastAPI，不接触 `DEEPSEEK_API_KEY`。大模型密钥和调用均位于后端。
操作员登录使用后端签名的 HttpOnly Cookie，密码不会保存到前端或浏览器存储。
# Portfolio demo

无需配置数据库或模型 Key 的作品演示入口：启动开发服务后访问 `/demo`。
