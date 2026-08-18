# AI Database Agent · Portfolio Edition

这是项目的作品展示版本，面向 HR 和技术面试官提供两种入口：

- **离线演示**：无需数据库、无需 LLM Key，打开前端 `/demo` 即可按流程演示。
- **真实模式**：配置 DeepSeek API 和本地数据库后，进入完整的数据库连接、理解、查询和写操作流程。

## 30 秒启动离线演示

```bash
cd frontend
npm install
npm run dev
```

打开 <http://localhost:3000/demo>，点击底部“下一步”依次查看四个阶段。

## 演示内容

1. 扫描物流数据库结构：表、字段、外键关系和业务域。
2. Understanding Graph 进行两轮数据取证，生成语义目录版本。
3. 自然语言生成 SQL，展示结构化语义帧、规则校验和查询结果。
4. UPDATE 写操作展示 Action Plan、影响预览、人工确认和事务回查。

离线模式使用固定的物流业务 fixture 和 deterministic mock LLM，数据仅用于作品展示，不代表真实生产数据。

## 展示素材

- [完整页面录屏（约 70 秒）](demo-screen-recording.mp4)
- [结构扫描截图](demo-scan.png)
- [自然语言查询截图](demo-query.png)
- [人工确认写入截图](demo-action.png)
- [录屏讲解脚本](demo-script.md)

## 真实模式

真实模式的配置和后端启动方式见项目根目录 README。请只使用 `.env.example`，不要提交 API Key、真实数据库地址或密码。

## 项目边界

- 离线演示用于展示产品流程，不执行真实数据库写入。
- 真实模式的数据库适配能力以实际测试结果为准；不同数据库仍存在方言和 schema 访问差异。
- 事务失败支持数据库级回滚，不提供已提交业务写操作的撤销。
