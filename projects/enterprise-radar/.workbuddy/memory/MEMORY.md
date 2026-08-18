# 企信雷达（QCC Risk Radar）项目速览

企业风险尽调工具，Streamlit 应用，数据来自企查查智能体数据平台 MCP 服务 + DeepSeek 大模型。

## 技术栈
- 前端：Streamlit（`app.py` 入口）
- 数据：企查查 MCP `streamable_http`（两个 endpoint：company / risk）
- 大模型：DeepSeek Chat（风控综合意见，评分锁定为规则引擎值）
- 报告：ReportLab 生成中文 PDF（依赖 macOS Arial Unicode.ttf，缺失则回退 STSong-Light）

## 核心模块（services/）
- `qcc_client.py`：MCP 客户端封装、auth、payload 提取、企业搜索/工商登记/风险扫描
- `report_service.py`：编排报告（并行调工具→规则评分→下钻明细→AI 分析）
- `risk_scoring.py`：规则引擎 V1，16 个负面因子权重 10~40，12 个关注因子（诉讼类只分诊不扣分）；等级 <20 低 / 20-49 中 / 50-79 高 / ≥80 严重，封顶 100
- `ai_analysis.py`：DeepSeek 生成 JSON 意见，强制作废模型评分、限定 decision 枚举
- `pdf_report.py` / `ui/report_view.py`：PDF 与 Streamlit 渲染

## 关键设计约束
- 搜索后需人工确认主体（不自动选第一条）
- 评分规则生成、非企查查官方；诉讼计数只分诊不扣分；模型评分被锁定防漂移
- 配置在 `.env`：QCC_API_KEY / QCC_COMPANY_MCP_URL / QCC_RISK_MCP_URL / DEEPSEEK_API_KEY

## 注意点
- `test_*.py` 实为调试脚本（无 assert、含 input()），非真正的 pytest 自动化测试
- PDF 字体在非 macOS 部署需确认字体回退可用
