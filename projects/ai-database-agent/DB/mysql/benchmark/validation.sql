-- 基础规模
SELECT COUNT(*) AS base_table_count
FROM information_schema.tables
WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE';

SELECT
    COUNT(*) AS total_columns,
    SUM(column_comment <> '') AS commented_columns,
    ROUND(SUM(column_comment <> '') / COUNT(*) * 100, 2) AS comment_percentage
FROM information_schema.columns
WHERE table_schema = DATABASE();

SELECT COUNT(*) AS declared_foreign_keys
FROM information_schema.referential_constraints
WHERE constraint_schema = DATABASE();

-- 隐含关系匹配率
SELECT
    't_a01.c01 -> org_employee.employee_no' AS relation_name,
    COUNT(*) AS total_rows,
    SUM(e.employee_id IS NOT NULL) AS matched_rows,
    ROUND(SUM(e.employee_id IS NOT NULL) / COUNT(*) * 100, 4) AS match_percentage
FROM t_a01 a
LEFT JOIN org_employee e ON e.employee_no = a.c01
UNION ALL
SELECT
    't_a02.c01 -> org_employee.employee_no',
    COUNT(*),
    SUM(e.employee_id IS NOT NULL),
    ROUND(SUM(e.employee_id IS NOT NULL) / COUNT(*) * 100, 4)
FROM t_a02 a
LEFT JOIN org_employee e ON e.employee_no = a.c01
UNION ALL
SELECT
    't_b01.c02 -> crm_customer.customer_code',
    COUNT(*),
    SUM(c.customer_id IS NOT NULL),
    ROUND(SUM(c.customer_id IS NOT NULL) / COUNT(*) * 100, 4)
FROM t_b01 b
LEFT JOIN crm_customer c ON c.customer_code = b.c02
UNION ALL
SELECT
    't_c01.c02 -> md_product.sku',
    COUNT(*),
    SUM(p.product_id IS NOT NULL),
    ROUND(SUM(p.product_id IS NOT NULL) / COUNT(*) * 100, 4)
FROM t_c01 t
LEFT JOIN md_product p ON p.sku = t.c02
UNION ALL
SELECT
    't_x9.c01 -> crm_customer.customer_code',
    COUNT(*),
    SUM(c.customer_id IS NOT NULL),
    ROUND(SUM(c.customer_id IS NOT NULL) / COUNT(*) * 100, 4)
FROM t_x9 x
LEFT JOIN crm_customer c ON c.customer_code = x.c01;

-- 中文拼音缩写表的隐含关系匹配率
SELECT
    'rs_gzff.ygbh -> org_employee.employee_no' AS relation_name,
    COUNT(*) AS total_rows,
    ROUND(SUM(e.employee_id IS NOT NULL) / COUNT(*) * 100, 4) AS match_percentage
FROM rs_gzff g
LEFT JOIN org_employee e ON e.employee_no = g.ygbh
UNION ALL
SELECT
    'xs_hkhx.ddbh -> sale_order.sales_order_no',
    COUNT(*),
    ROUND(SUM(s.sales_order_id IS NOT NULL) / COUNT(*) * 100, 4)
FROM xs_hkhx h
LEFT JOIN sale_order s ON s.sales_order_no = h.ddbh
UNION ALL
SELECT
    'ck_pdjl.spbm -> md_product.sku',
    COUNT(*),
    ROUND(SUM(p.product_id IS NOT NULL) / COUNT(*) * 100, 4)
FROM ck_pdjl d
LEFT JOIN md_product p ON p.sku = d.spbm
UNION ALL
SELECT
    'rs_jcjl.yybm -> org_department.department_code',
    COUNT(*),
    ROUND(SUM(d.department_id IS NOT NULL) / COUNT(*) * 100, 4)
FROM rs_jcjl j
LEFT JOIN org_department d ON d.department_code = j.yybm
UNION ALL
SELECT
    'kh_hfjl.lxrbh -> crm_contact.contact_id',
    COUNT(*),
    ROUND(SUM(c.contact_id IS NOT NULL) / COUNT(*) * 100, 4)
FROM kh_hfjl h
LEFT JOIN crm_contact c ON c.contact_id = h.lxrbh;

-- 稳定公式应返回0条异常
SELECT COUNT(*) AS payroll_formula_errors
FROM rs_gzff
WHERE sfgz <> jbgz + jt + jj - kk;

SELECT COUNT(*) AS stocktake_formula_errors
FROM ck_pdjl
WHERE cysl <> pdsl - zmsl;

-- 典型业务查询：2026年6月各部门餐饮报销金额
SELECT
    d.department_name,
    ROUND(SUM(i.amount), 2) AS meal_expense_amount
FROM fin_expense_claim c
JOIN fin_expense_item i ON i.claim_id = c.claim_id
JOIN org_department d ON d.department_id = c.department_id
WHERE i.category_code = 'MEAL'
  AND i.expense_date >= '2026-06-01'
  AND i.expense_date < '2026-07-01'
  AND c.claim_status IN ('APPROVED', 'PAID')
GROUP BY d.department_id, d.department_name
ORDER BY meal_expense_amount DESC;
