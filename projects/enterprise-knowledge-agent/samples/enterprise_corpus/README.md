# 企业知识库测试样本

这套样本用于测试文档解析、结构化切片、PDF 表格提取、混合检索和引用来源展示。

## 文件清单

| 文件 | 格式 | 主要内容 | 建议测试点 |
|---|---|---|---|
| `hr_employee_handbook.md` | Markdown | 入职、考勤、年假、远程办公、绩效和福利 | 标题路径、段落切片、制度问答 |
| `information_security_policy.md` | Markdown | 信息分级、账号、终端、钓鱼邮件、事件响应 | 章节检索、精确规则、拒答 |
| `expense_and_procurement_policy.txt` | TXT | 差旅、招待、采购、报销、预算和付款 | 长文本、关键词检索、金额规则 |
| `it_service_management.txt` | TXT | IT 服务台、P1/P2/P3/P4、变更、备份和监控 | 优先级比较、流程问答 |
| `customer_service_manual.pdf` | PDF | 客户服务、故障升级和服务等级 | PDF 页码、表格和引用 |
| `finance_shared_service_guide.pdf` | PDF | 财务共享、收入、月结、付款和审批 | PDF 表格、审批矩阵、页码 |

## 推荐问题

```text
员工每年有多少天带薪年假？
申请年假需要提前多久？
五万元以上的采购需要几家供应商报价？
P1 故障要求多少分钟内响应？
严格机密信息可以通过个人邮箱传输吗？
客户服务中的 S2 问题应该如何处理？
供应商账户变更需要哪些核验？
```

## 使用方式

在前端进入知识库后，可以逐个上传文件。建议先上传全部六个文件，再分别测试跨文档检索和引用来源。

当前项目支持 TXT、Markdown 和 PDF；不支持 DOCX、Excel、图片扫描件。如果需要测试扫描 PDF，需要另外接入 OCR 解析器。
