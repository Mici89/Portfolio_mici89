#!/usr/bin/env python3
"""AI_DB benchmark 评测脚本：提交自然语言问题到查询 API，记录 SQL/回答/状态。

用法: python3 eval_nl2sql.py [--base http://127.0.0.1:8000]
先确保后端已启动且 MySQL 可连接。
"""
import argparse
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(path: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


QUESTIONS = [
    # (编号, 题目, 类别)
    (6, "统计各部门当前在职员工人数", "query"),
    (7, "查询 2026 年上半年销售额最高的 10 个客户，取消订单不计入", "query"),
    (8, "查询每个仓库库存低于产品安全库存的产品数量", "query"),
    (9, "统计 2026 年 6 月各部门已批准或已付款的餐饮报销金额", "query"),
    (10, "找出销售订单金额与明细汇总金额不一致的订单", "query"),
    (11, "查询采购订单按时到货率，取消和草稿订单不计入", "query"),
    (12, "找出已离职但仍拥有未锁定系统账号的员工", "query"),
    (15, "统计 2026 年 6 月各部门员工的平均实发工资", "query"),
    (16, "查询 2026 年 6 月迟到次数最多的 10 名员工", "query"),
    (17, "统计 2026 年上半年各客户的有效收款金额，冲销记录不计入", "query"),
    (18, "找出出现历史 SKU、无法匹配产品主数据的库存流水", "query"),
    (19, "对比每个客户的主数据授信额度和遗留风控表剩余可用额度", "query"),
    (20, "查询已被冻结授信但 2026 年仍然产生销售订单的客户", "query"),
    (21, "哪些产品在所有仓库的可用库存都低于安全库存，同时过去 90 天仍有销售？", "query"),
    (22, "找出 2026 年销售额增长但有效收款下降的客户", "query"),
    (23, "哪些部门的人均报销金额和迟到率同时高于全公司平均值？", "query"),
    (24, "检查实发工资是否满足“基本工资 + 津贴 + 奖金 - 扣款”，列出异常记录", "query"),
]


def main() -> None:
    global BASE  # noqa: PLW0603
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--questions", default="6-24", help="如 6-24 或 6,7,8")
    args = parser.parse_args()
    BASE = args.base

    # 解析题目范围
    wanted = set()
    for part in args.questions.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            wanted.update(range(int(lo), int(hi) + 1))
        else:
            wanted.add(int(part))

    print(f"[1/2] 扫描数据库结构...")
    snap = post("/api/v1/database-snapshots/default/scan", {})
    snap_id = snap["snapshot_id"]
    print(f"      snapshot: {snap_id}  tables={snap['scan_statistics']['table_count']}")

    print(f"[2/2] 运行 {len(wanted)} 道查询题...")
    results = []
    for number, question, kind in QUESTIONS:
        if number not in wanted:
            continue
        print(f"  Q{number}: {question[:40]}...")
        t0 = time.time()
        try:
            resp = post(
                f"/api/v1/database-query/snapshots/{snap_id}",
                {"question": question},
                timeout=240,
            )
            elapsed = time.time() - t0
            attempts = resp.get("attempts", [])
            explanation = resp.get("explanation") or {}
            sql = ""
            if attempts:
                sql = (attempts[-1].get("plan") or {}).get("sql", "")
            results.append({
                "number": number,
                "question": question,
                "query_id": resp.get("query_id"),
                "status": resp.get("status"),
                "attempt_count": len(attempts),
                "answer": explanation.get("answer", ""),
                "limitations": explanation.get("limitations", []),
                "sql": sql,
                "elapsed_s": round(elapsed, 1),
            })
            print(f"      -> {resp.get('status')} attempts={len(attempts)} {elapsed:.1f}s")
        except Exception as exc:
            results.append({
                "number": number,
                "question": question,
                "status": "error",
                "error": str(exc)[:200],
            })
            print(f"      -> ERROR {str(exc)[:100]}")

    out = "benchmark_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in results if r.get("status") == "completed")
    err = sum(1 for r in results if r.get("status") == "error")
    print(f"\n完成 {len(results)} 题: completed={ok} error={err}")
    print(f"结果已写入 {out}")


if __name__ == "__main__":
    main()
