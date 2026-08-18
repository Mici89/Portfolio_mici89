#!/usr/bin/env python3
"""Generate deterministic MySQL seed data for the legacy enterprise benchmark."""

from __future__ import annotations

import argparse
import calendar
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Sequence


SEED = 20260727
RNG = random.Random(SEED)


def sql_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, datetime):
        value = value.isoformat(sep=" ")
    elif isinstance(value, date):
        value = value.isoformat()
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def write_insert(
    fp,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
    batch_size: int = 500,
) -> int:
    batch: list[Sequence[object]] = []
    total = 0

    def flush() -> None:
        nonlocal total
        if not batch:
            return
        fp.write(f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n")
        fp.write(",\n".join(
            "(" + ", ".join(sql_value(value) for value in row) + ")"
            for row in batch
        ))
        fp.write(";\n\n")
        total += len(batch)
        batch.clear()

    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            flush()
    flush()
    return total


def random_date(start: date, end: date) -> date:
    return start + timedelta(days=RNG.randint(0, (end - start).days))


def month_iter(start_year: int, start_month: int, count: int) -> list[str]:
    values = []
    year, month = start_year, start_month
    for _ in range(count):
        values.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return values


def money(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def build_seed(output: Path) -> dict[str, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    start = date(2025, 1, 1)
    end = date(2026, 7, 20)

    departments = [
        (1, "D001", "总经理办公室", None, 1, "CC001", 1),
        (2, "D010", "人力资源部", 1, 2, "CC010", 1),
        (3, "D020", "财务部", 1, 3, "CC020", 1),
        (4, "D030", "销售部", 1, 4, "CC030", 1),
        (5, "D040", "采购部", 1, 5, "CC040", 1),
        (6, "D050", "研发中心", 1, 6, "CC050", 1),
        (7, "D051", "平台研发部", 6, 7, "CC051", 1),
        (8, "D052", "应用研发部", 6, 8, "CC052", 1),
        (9, "D060", "生产运营部", 1, 9, "CC060", 1),
        (10, "D070", "质量管理部", 1, 10, "CC070", 1),
        (11, "D080", "仓储物流部", 1, 11, "CC080", 1),
        (12, "D090", "信息技术部", 1, 12, "CC090", 1),
    ]

    positions = [
        (1, "POS001", "总经理", "M5", "管理", 50000, 80000, 1),
        (2, "POS002", "部门经理", "M3", "管理", 25000, 45000, 1),
        (3, "POS003", "业务主管", "M1", "管理", 16000, 26000, 1),
        (4, "POS010", "高级销售经理", "P7", "销售", 16000, 30000, 1),
        (5, "POS011", "销售专员", "P5", "销售", 8000, 16000, 1),
        (6, "POS020", "高级研发工程师", "P7", "技术", 22000, 38000, 1),
        (7, "POS021", "研发工程师", "P5", "技术", 12000, 24000, 1),
        (8, "POS030", "采购专员", "P5", "供应链", 9000, 17000, 1),
        (9, "POS040", "财务会计", "P5", "财务", 10000, 18000, 1),
        (10, "POS041", "财务分析师", "P6", "财务", 14000, 24000, 1),
        (11, "POS050", "仓库管理员", "P4", "供应链", 7000, 13000, 1),
        (12, "POS060", "质量工程师", "P5", "质量", 10000, 19000, 1),
        (13, "POS070", "人力资源专员", "P5", "人力资源", 9000, 17000, 1),
        (14, "POS080", "IT运维工程师", "P6", "技术", 13000, 23000, 1),
        (15, "POS090", "生产计划员", "P5", "生产", 9000, 16000, 1),
    ]

    surnames = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜谢邹喻柏水窦章")
    given_names = [
        "伟", "芳", "娜", "敏", "静", "磊", "军", "洋", "勇", "艳",
        "杰", "娟", "涛", "明", "超", "秀英", "霞", "平", "刚", "桂英",
        "晨", "宇", "欣", "凯", "雪", "浩然", "雨桐", "子涵", "思远", "若溪",
    ]
    position_by_department = {
        1: [1, 2, 3],
        2: [2, 3, 13],
        3: [2, 3, 9, 10],
        4: [2, 3, 4, 5],
        5: [2, 3, 8],
        6: [2, 3, 6, 7],
        7: [2, 3, 6, 7],
        8: [2, 3, 6, 7],
        9: [2, 3, 15],
        10: [2, 3, 12],
        11: [2, 3, 11],
        12: [2, 3, 14],
    }
    employee_rows = []
    employee_meta: dict[int, dict[str, object]] = {}
    for employee_id in range(1, 301):
        department_id = ((employee_id - 1) % len(departments)) + 1
        if employee_id == 1:
            position_id = 1
        elif employee_id <= len(departments):
            position_id = 2
        else:
            position_id = RNG.choice(position_by_department[department_id][1:])
        manager_id = None if employee_id == 1 else (1 if employee_id <= 12 else department_id)
        employee_no = f"E{employee_id:05d}"
        employee_name = RNG.choice(surnames) + RNG.choice(given_names)
        gender = RNG.choice(["M", "F"])
        hire_date = random_date(date(2015, 1, 1), date(2026, 4, 30))
        status_roll = RNG.random()
        if status_roll < 0.08:
            status = "LEFT"
            leave_date = random_date(max(hire_date + timedelta(days=30), date(2025, 1, 1)), end)
        elif hire_date >= date(2026, 3, 1):
            status = "PROBATION"
            leave_date = None
        else:
            status = "ACTIVE"
            leave_date = None
        mobile = None if RNG.random() < 0.04 else f"1{RNG.choice([3,5,7,8,9])}{RNG.randint(100000000, 999999999)}"
        id_card = None if RNG.random() < 0.03 else f"310101{RNG.randint(1970, 2002)}{RNG.randint(1,12):02d}{RNG.randint(1,28):02d}{RNG.randint(1000,9999)}"
        employee_rows.append((
            employee_id, employee_no, employee_name, gender, mobile,
            f"{employee_no.lower()}@example-corp.test", department_id,
            position_id, manager_id, hire_date, leave_date, status, id_card,
            datetime.combine(hire_date, datetime.min.time()),
        ))
        employee_meta[employee_id] = {
            "no": employee_no,
            "department_id": department_id,
            "position_id": position_id,
            "status": status,
        }

    categories = [
        (1, "CAT01", "工业传感器", None),
        (2, "CAT02", "控制器", None),
        (3, "CAT03", "通信模块", None),
        (4, "CAT04", "执行器", None),
        (5, "CAT05", "检测仪器", None),
        (6, "CAT06", "电源模块", None),
        (7, "CAT07", "机械组件", None),
        (8, "CAT08", "线缆与接插件", None),
        (9, "CAT09", "软件授权", None),
        (10, "CAT10", "售后备件", None),
        (11, "CAT11", "温度传感器", 1),
        (12, "CAT12", "压力传感器", 1),
    ]
    category_names = {row[0]: row[2] for row in categories}

    with output.open("w", encoding="utf-8", newline="\n") as fp:
        fp.write("-- Generated deterministically by generator/generate_seed.py\n")
        fp.write(f"-- Seed: {SEED}\n\n")
        fp.write("SET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS = 0;\n\n")

        counts["org_department"] = write_insert(
            fp, "org_department",
            ["department_id", "department_code", "department_name", "parent_department_id",
             "manager_employee_id", "cost_center_code", "status"],
            departments,
        )
        counts["hr_position"] = write_insert(
            fp, "hr_position",
            ["position_id", "position_code", "position_name", "position_level",
             "job_family", "min_salary", "max_salary", "status"],
            positions,
        )
        counts["org_employee"] = write_insert(
            fp, "org_employee",
            ["employee_id", "employee_no", "employee_name", "gender", "mobile", "email",
             "department_id", "position_id", "manager_id", "hire_date", "leave_date",
             "employment_status", "id_card_no", "created_at"],
            employee_rows,
        )

        user_rows = []
        roles = ["EMPLOYEE", "EMPLOYEE", "EMPLOYEE", "MANAGER", "FINANCE", "SALES"]
        for user_id, employee_id in enumerate(range(1, 181), 1):
            user_rows.append((
                user_id, f"user{employee_id:05d}", employee_id,
                "$2b$12$simulation.only.not.a.real.password.hash",
                RNG.choice(roles), 1 if RNG.random() < 0.03 else 0,
                datetime(2026, 7, RNG.randint(1, 20), RNG.randint(7, 21), RNG.randint(0, 59), 0),
                datetime(2024, 1, 1),
            ))
        counts["iam_user"] = write_insert(
            fp, "iam_user",
            ["user_id", "login_name", "employee_id", "password_hash", "role_code",
             "is_locked", "last_login_at", "created_at"],
            user_rows,
        )

        provinces = ["上海", "江苏", "浙江", "广东", "山东", "四川", "湖北", "福建", "北京", "安徽"]
        industries = ["汽车制造", "电子设备", "新能源", "化工", "医药", "食品加工", "物流", "机械制造"]
        company_suffixes = ["科技有限公司", "智能制造有限公司", "工业设备有限公司", "自动化股份有限公司", "供应链有限公司"]
        sales_employee_ids = [eid for eid, meta in employee_meta.items() if meta["department_id"] == 4 and meta["status"] != "LEFT"]
        customer_rows = []
        customer_meta = {}
        for customer_id in range(1, 121):
            customer_code = f"C{customer_id:05d}"
            province = RNG.choice(provinces)
            name = province + RNG.choice(["华辰", "远航", "恒信", "启明", "新锐", "博盛", "联创", "德润"]) + RNG.choice(company_suffixes)
            credit_level = RNG.choices(["A", "B", "C", "D"], weights=[30, 45, 20, 5])[0]
            credit_limit = {"A": 2000000, "B": 1000000, "C": 400000, "D": 100000}[credit_level] * RNG.uniform(0.7, 1.3)
            status = "INACTIVE" if RNG.random() < 0.05 else "ACTIVE"
            customer_type = RNG.choices(
                ["ENTERPRISE", "DISTRIBUTOR", "RETAIL"], [60, 30, 10]
            )[0]
            industry = RNG.choice(industries)
            account_manager_id = RNG.choice(sales_employee_ids)
            created_at = random_date(date(2018, 1, 1), end)
            row = (
                customer_id, customer_code, name, customer_type, industry,
                province, credit_level, money(credit_limit),
                account_manager_id, status, created_at,
            )
            customer_rows.append(row)
            customer_meta[customer_id] = {
                "code": customer_code,
                "credit_limit": money(credit_limit),
                "level": credit_level,
                "account_manager_id": account_manager_id,
            }
        counts["crm_customer"] = write_insert(
            fp, "crm_customer",
            ["customer_id", "customer_code", "customer_name", "customer_type", "industry",
             "province", "credit_level", "credit_limit", "account_manager_id", "status", "created_at"],
            customer_rows,
        )

        contact_rows = []
        contact_id = 1
        for customer_id in range(1, 121):
            for idx in range(RNG.randint(1, 3)):
                contact_rows.append((
                    contact_id, customer_id, RNG.choice(surnames) + RNG.choice(given_names),
                    RNG.choice(["采购经理", "技术总监", "财务经理", "总经理", "项目经理"]),
                    None if RNG.random() < 0.03 else f"1{RNG.choice([3,5,7,8,9])}{RNG.randint(100000000, 999999999)}",
                    f"contact{contact_id}@customer.test", 1 if idx == 0 else 0,
                    random_date(date(2020, 1, 1), end),
                ))
                contact_id += 1
        counts["crm_contact"] = write_insert(
            fp, "crm_contact",
            ["contact_id", "customer_id", "contact_name", "title", "mobile", "email",
             "is_primary", "created_at"],
            contact_rows,
        )

        counts["md_product_category"] = write_insert(
            fp, "md_product_category",
            ["category_id", "category_code", "category_name", "parent_category_id"],
            categories,
        )
        product_rows = []
        product_meta = {}
        units = ["件", "套", "台", "米", "个"]
        specs = ["基础型", "增强型", "工业级", "高精度", "耐高温", "低功耗"]
        for product_id in range(1, 301):
            category_id = RNG.randint(1, 12)
            sku = f"SKU-{category_id:02d}-{product_id:05d}"
            cost = RNG.uniform(20, 8000)
            price = cost * RNG.uniform(1.25, 2.2)
            product_rows.append((
                product_id, sku, f"{category_names[category_id]}-{RNG.choice(specs)}-{product_id:03d}",
                category_id, f"{RNG.choice(['A','B','C','X'])}{RNG.randint(10,999)}",
                RNG.choice(units), money(cost), money(price), RNG.randint(10, 200),
                "DISCONTINUED" if RNG.random() < 0.04 else "ACTIVE",
                random_date(date(2019, 1, 1), end),
            ))
            product_meta[product_id] = {"sku": sku, "cost": money(cost), "price": money(price)}
        counts["md_product"] = write_insert(
            fp, "md_product",
            ["product_id", "sku", "product_name", "category_id", "specification",
             "unit", "standard_cost", "list_price", "safety_stock", "status", "created_at"],
            product_rows,
        )

        supplier_rows = []
        for supplier_id in range(1, 61):
            province = RNG.choice(provinces)
            supplier_rows.append((
                supplier_id, f"S{supplier_id:04d}",
                province + RNG.choice(["宏达", "精工", "科创", "兴业", "联合", "恒泰"]) + RNG.choice(company_suffixes),
                RNG.choices(["A", "B", "C"], [30, 55, 15])[0], province,
                RNG.choice(surnames) + RNG.choice(given_names),
                f"1{RNG.choice([3,5,7,8,9])}{RNG.randint(100000000, 999999999)}",
                RNG.choice([15, 30, 45, 60]),
                "SUSPENDED" if RNG.random() < 0.04 else "ACTIVE",
            ))
        counts["scm_supplier"] = write_insert(
            fp, "scm_supplier",
            ["supplier_id", "supplier_code", "supplier_name", "supplier_level", "province",
             "contact_name", "contact_mobile", "payment_terms_days", "status"],
            supplier_rows,
        )

        warehouse_rows = [
            (1, "WH-SH", "上海中央仓", "上海", 11, 1),
            (2, "WH-SZ", "苏州成品仓", "江苏", 23, 1),
            (3, "WH-GZ", "广州区域仓", "广东", 35, 1),
            (4, "WH-CD", "成都区域仓", "四川", 47, 1),
            (5, "WH-BJ", "北京备件仓", "北京", 59, 1),
        ]
        counts["scm_warehouse"] = write_insert(
            fp, "scm_warehouse",
            ["warehouse_id", "warehouse_code", "warehouse_name", "province",
             "manager_employee_id", "status"],
            warehouse_rows,
        )

        buyer_ids = [eid for eid, meta in employee_meta.items() if meta["department_id"] == 5 and meta["status"] != "LEFT"]
        purchase_headers = []
        purchase_lines = []
        purchase_order_meta = {}
        purchase_line_id = 1
        for order_id in range(1, 351):
            order_date = random_date(start, end)
            status = RNG.choices(["DRAFT", "APPROVED", "PARTIAL", "RECEIVED", "CANCELLED"], [5, 15, 15, 60, 5])[0]
            total = Decimal("0")
            line_buffer = []
            for line_no in range(1, RNG.randint(2, 6) + 1):
                product_id = RNG.randint(1, 300)
                qty = RNG.randint(10, 500)
                unit_price = money(float(product_meta[product_id]["cost"]) * RNG.uniform(0.85, 1.12))
                received = 0 if status in ("DRAFT", "APPROVED", "CANCELLED") else (
                    qty if status == "RECEIVED" else RNG.randint(1, qty)
                )
                amount = money(qty * float(unit_price) * 1.13)
                line_buffer.append((
                    purchase_line_id, order_id, line_no, product_id, qty,
                    received, unit_price, Decimal("0.1300"), amount,
                ))
                purchase_line_id += 1
                total += amount
            po_no = f"PO{order_date:%Y%m}{order_id:06d}"
            purchase_headers.append((
                order_id, po_no, RNG.randint(1, 60), RNG.choice(buyer_ids),
                RNG.randint(1, 5), order_date,
                order_date + timedelta(days=RNG.randint(5, 30)), status, total,
                datetime.combine(order_date, datetime.min.time()) + timedelta(hours=9),
            ))
            purchase_lines.extend(line_buffer)
            purchase_order_meta[order_id] = po_no
        counts["scm_purchase_order"] = write_insert(
            fp, "scm_purchase_order",
            ["purchase_order_id", "purchase_order_no", "supplier_id", "buyer_employee_id",
             "warehouse_id", "order_date", "expected_date", "order_status", "total_amount", "created_at"],
            purchase_headers,
        )
        counts["scm_purchase_order_line"] = write_insert(
            fp, "scm_purchase_order_line",
            ["purchase_order_line_id", "purchase_order_id", "line_no", "product_id",
             "ordered_qty", "received_qty", "unit_price", "tax_rate", "line_amount"],
            purchase_lines,
        )

        sales_headers = []
        sales_lines = []
        sales_line_id = 1
        sales_order_meta = {}
        for order_id in range(1, 1201):
            order_date = random_date(start, end)
            status = RNG.choices(["DRAFT", "CONFIRMED", "PARTIAL", "SHIPPED", "CANCELLED"], [3, 15, 12, 65, 5])[0]
            total = Decimal("0")
            line_buffer = []
            for line_no in range(1, RNG.randint(2, 6) + 1):
                product_id = RNG.randint(1, 300)
                qty = RNG.randint(1, 80)
                discount = RNG.choice([0, 0, 0.03, 0.05, 0.08, 0.10, 0.15])
                unit_price = money(float(product_meta[product_id]["price"]) * RNG.uniform(0.92, 1.08))
                shipped = 0 if status in ("DRAFT", "CONFIRMED", "CANCELLED") else (
                    qty if status == "SHIPPED" else RNG.randint(1, qty)
                )
                amount = money(qty * float(unit_price) * (1 - discount) * 1.13)
                line_buffer.append((
                    sales_line_id, order_id, line_no, product_id, qty, shipped,
                    unit_price, Decimal(f"{discount:.4f}"), Decimal("0.1300"), amount,
                ))
                sales_line_id += 1
                total += amount
            customer_id = RNG.randint(1, 120)
            paid_ratio = 0 if status in ("DRAFT", "CANCELLED") else RNG.choice([0, 0.3, 0.5, 0.8, 1, 1])
            paid = money(float(total) * paid_ratio)
            so_no = f"SO{order_date:%Y%m}{order_id:06d}"
            sales_employee_id = RNG.choice(sales_employee_ids)
            sales_headers.append((
                order_id, so_no, customer_id, sales_employee_id, RNG.randint(1, 5),
                order_date, order_date + timedelta(days=RNG.randint(3, 25)), status,
                "CNY", total, paid,
                datetime.combine(order_date, datetime.min.time()) + timedelta(hours=RNG.randint(8, 18)),
            ))
            sales_lines.extend(line_buffer)
            sales_order_meta[order_id] = {
                "no": so_no, "customer_id": customer_id, "date": order_date,
                "paid": paid, "status": status,
                "sales_employee_id": sales_employee_id,
            }
        counts["sale_order"] = write_insert(
            fp, "sale_order",
            ["sales_order_id", "sales_order_no", "customer_id", "sales_employee_id",
             "warehouse_id", "order_date", "required_date", "order_status", "currency",
             "total_amount", "paid_amount", "created_at"],
            sales_headers,
        )
        counts["sale_order_line"] = write_insert(
            fp, "sale_order_line",
            ["sales_order_line_id", "sales_order_id", "line_no", "product_id",
             "ordered_qty", "shipped_qty", "unit_price", "discount_rate", "tax_rate", "line_amount"],
            sales_lines,
        )

        stock_rows = []
        stock_id = 1
        for warehouse_id in range(1, 6):
            for product_id in range(1, 301):
                on_hand = RNG.randint(0, 1200)
                allocated = RNG.randint(0, min(on_hand, 250))
                stock_rows.append((
                    stock_id, warehouse_id, product_id, on_hand, allocated,
                    datetime(2026, 6, RNG.randint(1, 30), RNG.randint(8, 18), 0, 0),
                    datetime(2026, 7, 20, 18, 0, 0),
                ))
                stock_id += 1
        counts["inv_stock"] = write_insert(
            fp, "inv_stock",
            ["stock_id", "warehouse_id", "product_id", "quantity_on_hand",
             "quantity_allocated", "last_counted_at", "updated_at"],
            stock_rows,
        )

        claim_headers = []
        claim_items = []
        approval_rows = []
        item_id = 1
        approval_id = 1
        expense_categories = ["MEAL", "TRAVEL", "HOTEL", "TRANSPORT", "OFFICE", "TRAINING", "CLIENT"]
        vendors = ["悦华餐饮", "城市出行", "华住酒店", "东方航空", "联华办公", "智学培训", "高铁管家"]
        active_employee_ids = [eid for eid, meta in employee_meta.items() if meta["status"] != "LEFT"]
        approver_ids = list(range(1, 13))
        for claim_id in range(1, 651):
            applicant_id = RNG.choice(active_employee_ids)
            expense_date = random_date(start, end)
            submitted_date = min(expense_date + timedelta(days=RNG.randint(1, 15)), end)
            status = RNG.choices(["DRAFT", "SUBMITTED", "APPROVED", "PAID", "REJECTED"], [5, 10, 35, 45, 5])[0]
            total = Decimal("0")
            item_buffer = []
            for _ in range(RNG.randint(1, 4)):
                category = RNG.choice(expense_categories)
                ranges = {
                    "MEAL": (30, 800), "TRAVEL": (200, 3000), "HOTEL": (300, 2500),
                    "TRANSPORT": (10, 500), "OFFICE": (20, 1500),
                    "TRAINING": (300, 5000), "CLIENT": (200, 5000),
                }
                amount = money(RNG.uniform(*ranges[category]))
                total += amount
                vendor = RNG.choice(vendors)
                item_buffer.append((
                    item_id, claim_id, expense_date, category,
                    f"{vendor}{category.lower()}费用", amount,
                    None if RNG.random() < 0.08 else f"INV{claim_id:06d}{item_id:06d}",
                    vendor,
                ))
                item_id += 1
            approved_by = RNG.choice(approver_ids) if status in ("APPROVED", "PAID", "REJECTED") else None
            approved_at = (
                datetime.combine(submitted_date + timedelta(days=RNG.randint(1, 5)), datetime.min.time()) + timedelta(hours=14)
                if approved_by else None
            )
            claim_headers.append((
                claim_id, f"BX{submitted_date:%Y%m}{claim_id:06d}", applicant_id,
                employee_meta[applicant_id]["department_id"], submitted_date,
                status, total, approved_by, approved_at,
                datetime.combine(submitted_date, datetime.min.time()) + timedelta(hours=9),
            ))
            claim_items.extend(item_buffer)
            if status != "DRAFT":
                action = "REJECT" if status == "REJECTED" else ("APPROVE" if approved_by else "SUBMIT")
                approval_rows.append((
                    approval_id, "EXPENSE_CLAIM", claim_id, 1,
                    approved_by or applicant_id, action,
                    approved_at or datetime.combine(submitted_date, datetime.min.time()) + timedelta(hours=10),
                    "资料齐全" if action == "APPROVE" else ("票据不符合要求" if action == "REJECT" else "提交审批"),
                ))
                approval_id += 1
        counts["fin_expense_claim"] = write_insert(
            fp, "fin_expense_claim",
            ["claim_id", "claim_no", "applicant_id", "department_id", "submitted_date",
             "claim_status", "total_amount", "approved_by", "approved_at", "created_at"],
            claim_headers,
        )
        counts["fin_expense_item"] = write_insert(
            fp, "fin_expense_item",
            ["item_id", "claim_id", "expense_date", "category_code", "description",
             "amount", "invoice_no", "vendor_name"],
            claim_items,
        )
        counts["wf_approval_log"] = write_insert(
            fp, "wf_approval_log",
            ["approval_id", "business_type", "business_id", "step_no", "approver_id",
             "action_code", "action_time", "opinion"],
            approval_rows,
        )

        # Legacy payroll snapshots: c01 joins org_employee.employee_no.
        position_salary = {row[0]: (row[5], row[6]) for row in positions}
        payroll_rows = []
        payroll_id = 1
        for month in month_iter(2025, 8, 12):
            year, month_no = map(int, month.split("-"))
            month_end = calendar.monthrange(year, month_no)[1]
            for employee_id, meta in employee_meta.items():
                min_salary, max_salary = position_salary[int(meta["position_id"])]
                base = money(RNG.uniform(min_salary, max_salary))
                allowance = money(RNG.uniform(300, 2500))
                bonus = money(RNG.uniform(0, float(base) * 0.30))
                deduction = money(RNG.uniform(300, 2500))
                net = money(float(base + allowance + bonus - deduction))
                paid_flag = "N" if month == "2026-07" and RNG.random() < 0.12 else "Y"
                payroll_rows.append((
                    payroll_id, meta["no"], month, base, allowance, bonus,
                    deduction, net, paid_flag,
                    datetime(year, month_no, month_end, 20, 0, 0),
                ))
                payroll_id += 1
        counts["t_a01"] = write_insert(
            fp, "t_a01",
            ["k1", "c01", "d01", "n01", "n02", "n03", "n04", "n05", "f01", "ts01"],
            payroll_rows,
        )

        # Legacy attendance: a few rows intentionally use unknown employee codes.
        attendance_rows = []
        attendance_id = 1
        attendance_start = date(2026, 3, 2)
        attendance_end = date(2026, 7, 17)
        current = attendance_start
        while current <= attendance_end:
            if current.weekday() < 5:
                for employee_id, meta in employee_meta.items():
                    if meta["status"] == "LEFT" and RNG.random() < 0.75:
                        continue
                    state = RNG.choices(["N", "L", "A", "T", "S"], [85, 6, 2, 4, 3])[0]
                    hours = {"N": 8, "L": RNG.uniform(6, 7.9), "A": 0, "T": 8, "S": 0}[state]
                    late_minutes = RNG.randint(5, 90) if state == "L" else 0
                    attendance_rows.append((
                        attendance_id, meta["no"], current, state,
                        money(hours), late_minutes, f"DEV-{RNG.randint(1, 8):02d}",
                        datetime.combine(current, datetime.min.time()) + timedelta(hours=18),
                    ))
                    attendance_id += 1
                if RNG.random() < 0.12:
                    attendance_rows.append((
                        attendance_id, f"E9{RNG.randint(9000,9999)}", current, "N",
                        Decimal("8.00"), 0, "DEV-99",
                        datetime.combine(current, datetime.min.time()) + timedelta(hours=18),
                    ))
                    attendance_id += 1
            current += timedelta(days=1)
        counts["t_a02"] = write_insert(
            fp, "t_a02",
            ["k1", "c01", "d01", "c02", "n01", "n02", "c03", "ts01"],
            attendance_rows,
        )

        # Legacy customer receipts: c02 joins crm_customer.customer_code.
        receipt_rows = []
        receipt_order_links = []
        receipt_id = 1
        for order_id, meta in sales_order_meta.items():
            paid = Decimal(meta["paid"])
            if paid <= 0:
                continue
            customer_code = customer_meta[int(meta["customer_id"])]["code"]
            payment_date = min(meta["date"] + timedelta(days=RNG.randint(3, 60)), end)
            receipt_rows.append((
                receipt_id, f"RC{payment_date:%Y%m}{receipt_id:07d}", customer_code,
                payment_date, paid, RNG.choice(["BANK", "ALIPAY", "WECHAT", "DRAFT"]),
                f"REF-{RNG.randint(10000000,99999999)}",
                "R" if RNG.random() < 0.03 else "N",
                datetime.combine(payment_date, datetime.min.time()) + timedelta(hours=15),
            ))
            receipt_order_links.append((receipt_id, order_id))
            receipt_id += 1
        counts["t_b01"] = write_insert(
            fp, "t_b01",
            ["k1", "c01", "c02", "d01", "n01", "c03", "c04", "f01", "ts01"],
            receipt_rows,
        )

        # Legacy inventory movement: c01/c02 join warehouse_code/sku.
        warehouse_codes = {row[0]: row[1] for row in warehouse_rows}
        movement_rows = []
        movement_id = 1
        for _ in range(5000):
            warehouse_id = RNG.randint(1, 5)
            product_id = RNG.randint(1, 300)
            movement_type = RNG.choices(["IN", "OUT", "ADJ"], [45, 45, 10])[0]
            qty = RNG.randint(1, 200)
            signed_qty = qty if movement_type == "IN" else (-qty if movement_type == "OUT" else RNG.randint(-20, 20))
            movement_date = random_date(start, end)
            if movement_type == "IN":
                source_type = "PO"
                source_id = RNG.randint(1, 350)
                source_no = purchase_order_meta[source_id]
            elif movement_type == "OUT":
                source_type = "SO"
                source_id = RNG.randint(1, 1200)
                source_no = sales_order_meta[source_id]["no"]
            else:
                source_type = "COUNT"
                source_no = f"PD{movement_date:%Y%m}{movement_id:06d}"
            sku = product_meta[product_id]["sku"]
            if RNG.random() < 0.008:
                sku = f"OLD-SKU-{RNG.randint(1, 20):03d}"
            movement_rows.append((
                movement_id, warehouse_codes[warehouse_id], sku,
                datetime.combine(movement_date, datetime.min.time()) + timedelta(hours=RNG.randint(7, 22)),
                movement_type, signed_qty, source_type, source_no,
                datetime.combine(movement_date, datetime.min.time()) + timedelta(hours=23),
            ))
            movement_id += 1
        counts["t_c01"] = write_insert(
            fp, "t_c01",
            ["k1", "c01", "c02", "d01", "c03", "n01", "c04", "c05", "ts01"],
            movement_rows,
        )

        # Legacy credit-risk snapshot: c01 joins customer_code.
        risk_rows = []
        for customer_id, meta in customer_meta.items():
            overdue_days = RNG.choices([0, 7, 15, 30, 60, 90], [55, 12, 12, 10, 7, 4])[0]
            available = money(float(meta["credit_limit"]) * RNG.uniform(0.05, 0.95))
            risk_rows.append((
                customer_id, meta["code"], meta["level"], available, overdue_days,
                None if overdue_days == 0 else end - timedelta(days=overdue_days),
                "Y" if overdue_days >= 60 else "N", datetime(2026, 7, 20, 23, 0, 0),
            ))
        counts["t_x9"] = write_insert(
            fp, "t_x9",
            ["k1", "c01", "c02", "n01", "n02", "d01", "f01", "ts01"],
            risk_rows,
        )

        # Pinyin-abbreviation legacy tables. They intentionally omit declared
        # foreign keys so relationship discovery must compare actual values.
        gzff_rows = []
        for row in payroll_rows:
            payroll_id, employee_no, month, base, allowance, bonus, deduction, net, paid_flag, _ = row
            year, month_no = map(int, month.split("-"))
            if month_no == 12:
                pay_date = date(year + 1, 1, 5)
            else:
                pay_date = date(year, month_no + 1, 5)
            gzff_rows.append((
                payroll_id, employee_no, month, base, allowance, bonus,
                deduction, net, pay_date if paid_flag == "Y" else None, paid_flag,
            ))
        counts["rs_gzff"] = write_insert(
            fp, "rs_gzff",
            ["id", "ygbh", "gzny", "jbgz", "jt", "jj", "kk", "sfgz", "ffrq", "ffzt"],
            gzff_rows,
        )

        hkhx_rows = []
        receipt_by_id = {int(row[0]): row for row in receipt_rows}
        for receipt_pk, order_id in receipt_order_links:
            receipt = receipt_by_id[receipt_pk]
            order_meta = sales_order_meta[order_id]
            is_reversed = receipt[7] == "R"
            hkhx_rows.append((
                receipt_pk,
                receipt[1],
                receipt[2],
                order_meta["no"],
                receipt[3],
                receipt[4],
                Decimal("0.00") if is_reversed else receipt[4],
                "C" if is_reversed else "Y",
                employee_meta[int(order_meta["sales_employee_id"])]["no"],
                receipt[8],
            ))
        counts["xs_hkhx"] = write_insert(
            fp, "xs_hkhx",
            ["id", "hkdh", "khbh", "ddbh", "hkrq", "hkje", "hxje",
             "hxzt", "jbrbh", "djrq"],
            hkhx_rows,
        )

        warehouse_by_id = {int(row[0]): row for row in warehouse_rows}
        pdjl_rows = []
        variance_cycle = [0, 0, 0, 0, 1, -1, 2, -2, 5, -5]
        for stock in stock_rows:
            stock_id, warehouse_id, product_id, on_hand, _, counted_at, _ = stock
            warehouse = warehouse_by_id[int(warehouse_id)]
            variance = variance_cycle[(int(stock_id) - 1) % len(variance_cycle)]
            counted_qty = Decimal(on_hand) + Decimal(variance)
            pdjl_rows.append((
                stock_id,
                f"PD{counted_at:%Y%m}{stock_id:06d}",
                warehouse[1],
                product_meta[int(product_id)]["sku"],
                counted_at.date(),
                on_hand,
                counted_qty,
                variance,
                employee_meta[int(warehouse[4])]["no"],
                "Y" if variance == 0 else "D",
            ))
        counts["ck_pdjl"] = write_insert(
            fp, "ck_pdjl",
            ["id", "pddh", "ckbh", "spbm", "pdrq", "zmsl", "pdsl",
             "cysl", "pdrbh", "pdzt"],
            pdjl_rows,
        )

        department_codes = {int(row[0]): row[1] for row in departments}
        jcjl_rows = []
        jc_id = 1
        for employee_id, meta in employee_meta.items():
            record_count = 2 if employee_id % 2 == 0 else 1
            for record_no in range(record_count):
                is_reward = (employee_id + record_no) % 4 != 0
                amount = Decimal(200 + (employee_id % 9) * 100)
                if not is_reward:
                    amount = -amount
                manager_id = 1 if employee_id == 1 else (
                    1 if employee_id <= 12 else int(meta["department_id"])
                )
                event_date = date(2025, 1, 1) + timedelta(
                    days=(employee_id * 13 + record_no * 97) % 560
                )
                jcjl_rows.append((
                    jc_id,
                    f"JC{event_date:%Y%m}{jc_id:06d}",
                    meta["no"],
                    event_date,
                    "JL" if is_reward else "CF",
                    amount,
                    department_codes[int(meta["department_id"])],
                    employee_meta[manager_id]["no"],
                    "Y",
                    "季度绩效表现" if is_reward else "考勤纪律处理",
                ))
                jc_id += 1
        counts["rs_jcjl"] = write_insert(
            fp, "rs_jcjl",
            ["id", "jcbh", "ygbh", "fsrq", "jclx", "jcje",
             "yybm", "sprbh", "zt", "bz"],
            jcjl_rows,
        )

        hfjl_rows = []
        followup_methods = ["DH", "WX", "SM", "YJ"]
        followup_results = ["YX", "DGJ", "WXY", "ZJ"]
        for contact in contact_rows:
            contact_id, customer_id, contact_name, _, mobile, _, _, created_at = contact
            followup_date = min(created_at + timedelta(days=30 + contact_id % 180), end)
            result = followup_results[(contact_id - 1) % len(followup_results)]
            manager_id = int(customer_meta[int(customer_id)]["account_manager_id"])
            hfjl_rows.append((
                contact_id,
                customer_meta[int(customer_id)]["code"],
                contact_id,
                contact_name,
                followup_date,
                followup_methods[(contact_id - 1) % len(followup_methods)],
                mobile,
                employee_meta[manager_id]["no"],
                result,
                followup_date + timedelta(days=30) if result == "DGJ" else None,
            ))
        counts["kh_hfjl"] = write_insert(
            fp, "kh_hfjl",
            ["id", "khbh", "lxrbh", "lxrxm", "hfrq", "hffs",
             "lxdh", "hfrbh", "hfjg", "xyhfrq"],
            hfjl_rows,
        )

        fp.write("SET FOREIGN_KEY_CHECKS = 1;\n")

    return counts


def main() -> None:
    default_output = Path(__file__).resolve().parents[1] / "init" / "02_seed.sql"
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=default_output)
    args = parser.parse_args()
    counts = build_seed(args.output.resolve())
    print(f"Generated {args.output.resolve()}")
    for table, count in counts.items():
        print(f"{table:30s} {count:8d}")
    print(f"{'TOTAL':30s} {sum(counts.values()):8d}")


if __name__ == "__main__":
    main()
