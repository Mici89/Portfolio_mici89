"use client";

import { useState } from "react";

const demoContent = {
  "ai-database-agent": [
    ["提问", "查询今年华东区域已签收但结算未完成的运单"],
    ["语义", "区域 → REGION_DICT · 状态 → T_YD01.STATUS_CD"],
    ["结果", "返回真实查询结果，并保留 SQL、字段映射与证据来源"],
  ],
  "enterprise-radar": [
    ["主体", "按名称搜索并选择统一社会信用代码对应企业"],
    ["扫描", "工商信息与风险工具并发执行，异常项进入关注清单"],
    ["交付", "生成风险摘要、AI 分析与 PDF / JSON 报告"],
  ],
  "enterprise-knowledge-agent": [
    ["问题", "差旅报销超过 5000 元需要谁审批？"],
    ["检索", "Agent 在当前知识库调用混合检索并读取候选片段"],
    ["回答", "按制度原文作答，并显示文档、页码与引用片段"],
  ],
} as const;

export function ProjectDemo({ slug }: { slug: keyof typeof demoContent }) {
  const [active, setActive] = useState(0);
  const items = demoContent[slug];

  return (
    <div className="demo-shell">
      <div className="demo-toolbar"><i /><i /><i /><span>interactive evidence preview</span></div>
      <div className="demo-layout">
        <div className="demo-steps" role="tablist" aria-label="演示步骤">
          {items.map(([label], index) => (
            <button key={label} className={active === index ? "active" : ""} onClick={() => setActive(index)} role="tab" aria-selected={active === index}>
              <span>0{index + 1}</span>{label}
            </button>
          ))}
        </div>
        <div className="demo-output" role="tabpanel">
          <small>{items[active][0]}</small>
          <p>{items[active][1]}</p>
          <div className="trace-line"><span>status</span><strong>verified</strong></div>
          <div className="trace-line"><span>source</span><strong>bounded context</strong></div>
        </div>
      </div>
    </div>
  );
}
