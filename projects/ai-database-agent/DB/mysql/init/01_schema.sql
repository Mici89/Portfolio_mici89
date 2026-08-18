SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE org_department (
    department_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '部门主键',
    department_code VARCHAR(20) NOT NULL COMMENT '部门编码',
    department_name VARCHAR(100) NOT NULL COMMENT '部门名称',
    parent_department_id BIGINT UNSIGNED NULL COMMENT '上级部门ID',
    manager_employee_id BIGINT UNSIGNED NULL COMMENT '部门负责人员工ID，因初始化顺序未声明外键',
    cost_center_code VARCHAR(20) NULL COMMENT '成本中心编码',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (department_id),
    UNIQUE KEY uk_department_code (department_code),
    KEY idx_department_parent (parent_department_id),
    CONSTRAINT fk_department_parent
        FOREIGN KEY (parent_department_id) REFERENCES org_department (department_id)
) ENGINE=InnoDB COMMENT='企业组织部门';

CREATE TABLE hr_position (
    position_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '岗位主键',
    position_code VARCHAR(20) NOT NULL COMMENT '岗位编码',
    position_name VARCHAR(100) NOT NULL COMMENT '岗位名称',
    position_level VARCHAR(20) NOT NULL COMMENT '职级，例如P5、M2',
    job_family VARCHAR(50) NOT NULL COMMENT '岗位序列',
    min_salary DECIMAL(12,2) NULL COMMENT '岗位最低月薪',
    max_salary DECIMAL(12,2) NULL COMMENT '岗位最高月薪',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    PRIMARY KEY (position_id),
    UNIQUE KEY uk_position_code (position_code)
) ENGINE=InnoDB COMMENT='岗位主数据';

CREATE TABLE org_employee (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '员工主键',
    employee_no VARCHAR(20) NOT NULL COMMENT '员工工号',
    employee_name VARCHAR(80) NOT NULL COMMENT '员工姓名',
    gender CHAR(1) NULL COMMENT '性别：M男，F女',
    mobile VARCHAR(30) NULL COMMENT '手机号，敏感字段',
    email VARCHAR(120) NULL COMMENT '企业邮箱',
    department_id BIGINT UNSIGNED NOT NULL COMMENT '所属部门ID',
    position_id BIGINT UNSIGNED NOT NULL COMMENT '岗位ID',
    manager_id BIGINT UNSIGNED NULL COMMENT '直属上级员工ID',
    hire_date DATE NOT NULL COMMENT '入职日期',
    leave_date DATE NULL COMMENT '离职日期',
    employment_status VARCHAR(20) NOT NULL COMMENT '在职状态：ACTIVE、PROBATION、LEFT',
    id_card_no VARCHAR(32) NULL COMMENT '身份证号，敏感字段',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (employee_id),
    UNIQUE KEY uk_employee_no (employee_no),
    KEY idx_employee_department (department_id),
    KEY idx_employee_position (position_id),
    KEY idx_employee_manager (manager_id),
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id) REFERENCES org_department (department_id),
    CONSTRAINT fk_employee_position
        FOREIGN KEY (position_id) REFERENCES hr_position (position_id),
    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id) REFERENCES org_employee (employee_id)
) ENGINE=InnoDB COMMENT='员工主数据';

CREATE TABLE iam_user (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '系统用户主键',
    login_name VARCHAR(80) NOT NULL COMMENT '登录名',
    employee_id BIGINT UNSIGNED NULL COMMENT '关联员工ID',
    password_hash VARCHAR(255) NOT NULL COMMENT '模拟密码哈希，不是真实凭据',
    role_code VARCHAR(40) NOT NULL COMMENT '角色编码',
    is_locked TINYINT NOT NULL DEFAULT 0 COMMENT '是否锁定：1是，0否',
    last_login_at DATETIME NULL COMMENT '最后登录时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (user_id),
    UNIQUE KEY uk_user_login_name (login_name),
    KEY idx_user_employee (employee_id),
    CONSTRAINT fk_user_employee
        FOREIGN KEY (employee_id) REFERENCES org_employee (employee_id)
) ENGINE=InnoDB COMMENT='系统登录用户';

CREATE TABLE crm_customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '客户主键',
    customer_code VARCHAR(20) NOT NULL COMMENT '客户编码',
    customer_name VARCHAR(160) NOT NULL COMMENT '客户名称',
    customer_type VARCHAR(30) NOT NULL COMMENT '客户类型：ENTERPRISE、DISTRIBUTOR、RETAIL',
    industry VARCHAR(60) NULL COMMENT '所属行业',
    province VARCHAR(40) NULL COMMENT '所在省份',
    credit_level CHAR(1) NULL COMMENT '信用等级：A、B、C、D',
    credit_limit DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '授信额度',
    account_manager_id BIGINT UNSIGNED NULL COMMENT '客户经理员工ID',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' COMMENT '客户状态',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (customer_id),
    UNIQUE KEY uk_customer_code (customer_code),
    KEY idx_customer_manager (account_manager_id),
    CONSTRAINT fk_customer_manager
        FOREIGN KEY (account_manager_id) REFERENCES org_employee (employee_id)
) ENGINE=InnoDB COMMENT='客户主数据';

CREATE TABLE crm_contact (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '联系人主键',
    customer_id BIGINT UNSIGNED NOT NULL COMMENT '所属客户ID',
    contact_name VARCHAR(80) NOT NULL COMMENT '联系人姓名',
    title VARCHAR(60) NULL COMMENT '职务',
    mobile VARCHAR(30) NULL COMMENT '联系电话，敏感字段',
    email VARCHAR(120) NULL COMMENT '邮箱',
    is_primary TINYINT NOT NULL DEFAULT 0 COMMENT '是否主要联系人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (contact_id),
    KEY idx_contact_customer (customer_id),
    CONSTRAINT fk_contact_customer
        FOREIGN KEY (customer_id) REFERENCES crm_customer (customer_id)
) ENGINE=InnoDB COMMENT='客户联系人';

CREATE TABLE md_product_category (
    category_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '产品分类主键',
    category_code VARCHAR(20) NOT NULL COMMENT '分类编码',
    category_name VARCHAR(100) NOT NULL COMMENT '分类名称',
    parent_category_id BIGINT UNSIGNED NULL COMMENT '上级分类ID',
    PRIMARY KEY (category_id),
    UNIQUE KEY uk_category_code (category_code),
    CONSTRAINT fk_category_parent
        FOREIGN KEY (parent_category_id) REFERENCES md_product_category (category_id)
) ENGINE=InnoDB COMMENT='产品分类';

CREATE TABLE md_product (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '产品主键',
    sku VARCHAR(30) NOT NULL COMMENT '库存单位编码',
    product_name VARCHAR(160) NOT NULL COMMENT '产品名称',
    category_id BIGINT UNSIGNED NOT NULL COMMENT '产品分类ID',
    specification VARCHAR(120) NULL COMMENT '规格型号',
    unit VARCHAR(20) NOT NULL COMMENT '计量单位',
    standard_cost DECIMAL(12,2) NOT NULL COMMENT '标准成本',
    list_price DECIMAL(12,2) NOT NULL COMMENT '标准销售价',
    safety_stock INT NOT NULL DEFAULT 0 COMMENT '安全库存数量',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' COMMENT '产品状态',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (product_id),
    UNIQUE KEY uk_product_sku (sku),
    KEY idx_product_category (category_id),
    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id) REFERENCES md_product_category (category_id)
) ENGINE=InnoDB COMMENT='产品主数据';

CREATE TABLE scm_supplier (
    supplier_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '供应商主键',
    supplier_code VARCHAR(20) NOT NULL COMMENT '供应商编码',
    supplier_name VARCHAR(160) NOT NULL COMMENT '供应商名称',
    supplier_level CHAR(1) NULL COMMENT '供应商等级',
    province VARCHAR(40) NULL COMMENT '所在省份',
    contact_name VARCHAR(80) NULL COMMENT '联系人',
    contact_mobile VARCHAR(30) NULL COMMENT '联系电话',
    payment_terms_days INT NOT NULL DEFAULT 30 COMMENT '账期天数',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' COMMENT '供应商状态',
    PRIMARY KEY (supplier_id),
    UNIQUE KEY uk_supplier_code (supplier_code)
) ENGINE=InnoDB COMMENT='供应商主数据';

CREATE TABLE scm_warehouse (
    warehouse_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '仓库主键',
    warehouse_code VARCHAR(20) NOT NULL COMMENT '仓库编码',
    warehouse_name VARCHAR(100) NOT NULL COMMENT '仓库名称',
    province VARCHAR(40) NULL COMMENT '所在省份',
    manager_employee_id BIGINT UNSIGNED NULL COMMENT '仓库负责人',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用',
    PRIMARY KEY (warehouse_id),
    UNIQUE KEY uk_warehouse_code (warehouse_code),
    CONSTRAINT fk_warehouse_manager
        FOREIGN KEY (manager_employee_id) REFERENCES org_employee (employee_id)
) ENGINE=InnoDB COMMENT='仓库主数据';

CREATE TABLE scm_purchase_order (
    purchase_order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '采购订单主键',
    purchase_order_no VARCHAR(30) NOT NULL COMMENT '采购订单号',
    supplier_id BIGINT UNSIGNED NOT NULL COMMENT '供应商ID',
    buyer_employee_id BIGINT UNSIGNED NOT NULL COMMENT '采购员员工ID',
    warehouse_id BIGINT UNSIGNED NOT NULL COMMENT '收货仓库ID',
    order_date DATE NOT NULL COMMENT '下单日期',
    expected_date DATE NULL COMMENT '预计到货日期',
    order_status VARCHAR(20) NOT NULL COMMENT '订单状态',
    total_amount DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '含税总金额',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (purchase_order_id),
    UNIQUE KEY uk_purchase_order_no (purchase_order_no),
    KEY idx_po_supplier (supplier_id),
    KEY idx_po_buyer (buyer_employee_id),
    CONSTRAINT fk_po_supplier FOREIGN KEY (supplier_id) REFERENCES scm_supplier (supplier_id),
    CONSTRAINT fk_po_buyer FOREIGN KEY (buyer_employee_id) REFERENCES org_employee (employee_id),
    CONSTRAINT fk_po_warehouse FOREIGN KEY (warehouse_id) REFERENCES scm_warehouse (warehouse_id)
) ENGINE=InnoDB COMMENT='采购订单头';

CREATE TABLE scm_purchase_order_line (
    purchase_order_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '采购订单行主键',
    purchase_order_id BIGINT UNSIGNED NOT NULL COMMENT '采购订单ID',
    line_no INT NOT NULL COMMENT '行号',
    product_id BIGINT UNSIGNED NOT NULL COMMENT '产品ID',
    ordered_qty DECIMAL(12,2) NOT NULL COMMENT '采购数量',
    received_qty DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '已收货数量',
    unit_price DECIMAL(12,2) NOT NULL COMMENT '采购单价',
    tax_rate DECIMAL(5,4) NOT NULL DEFAULT 0.13 COMMENT '税率',
    line_amount DECIMAL(14,2) NOT NULL COMMENT '行含税金额',
    PRIMARY KEY (purchase_order_line_id),
    UNIQUE KEY uk_po_line (purchase_order_id, line_no),
    CONSTRAINT fk_po_line_header FOREIGN KEY (purchase_order_id)
        REFERENCES scm_purchase_order (purchase_order_id),
    CONSTRAINT fk_po_line_product FOREIGN KEY (product_id) REFERENCES md_product (product_id)
) ENGINE=InnoDB COMMENT='采购订单明细';

CREATE TABLE sale_order (
    sales_order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '销售订单主键',
    sales_order_no VARCHAR(30) NOT NULL COMMENT '销售订单号',
    customer_id BIGINT UNSIGNED NOT NULL COMMENT '客户ID',
    sales_employee_id BIGINT UNSIGNED NOT NULL COMMENT '销售人员工ID',
    warehouse_id BIGINT UNSIGNED NOT NULL COMMENT '发货仓库ID',
    order_date DATE NOT NULL COMMENT '下单日期',
    required_date DATE NULL COMMENT '客户要求交付日期',
    order_status VARCHAR(20) NOT NULL COMMENT '订单状态',
    currency CHAR(3) NOT NULL DEFAULT 'CNY' COMMENT '币种',
    total_amount DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '订单含税金额',
    paid_amount DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '已收款金额',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (sales_order_id),
    UNIQUE KEY uk_sales_order_no (sales_order_no),
    KEY idx_so_customer (customer_id),
    KEY idx_so_sales (sales_employee_id),
    KEY idx_so_date (order_date),
    CONSTRAINT fk_so_customer FOREIGN KEY (customer_id) REFERENCES crm_customer (customer_id),
    CONSTRAINT fk_so_sales FOREIGN KEY (sales_employee_id) REFERENCES org_employee (employee_id),
    CONSTRAINT fk_so_warehouse FOREIGN KEY (warehouse_id) REFERENCES scm_warehouse (warehouse_id)
) ENGINE=InnoDB COMMENT='销售订单头';

CREATE TABLE sale_order_line (
    sales_order_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '销售订单行主键',
    sales_order_id BIGINT UNSIGNED NOT NULL COMMENT '销售订单ID',
    line_no INT NOT NULL COMMENT '行号',
    product_id BIGINT UNSIGNED NOT NULL COMMENT '产品ID',
    ordered_qty DECIMAL(12,2) NOT NULL COMMENT '订购数量',
    shipped_qty DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '已发货数量',
    unit_price DECIMAL(12,2) NOT NULL COMMENT '成交单价',
    discount_rate DECIMAL(5,4) NOT NULL DEFAULT 0 COMMENT '折扣率',
    tax_rate DECIMAL(5,4) NOT NULL DEFAULT 0.13 COMMENT '税率',
    line_amount DECIMAL(14,2) NOT NULL COMMENT '行含税金额',
    PRIMARY KEY (sales_order_line_id),
    UNIQUE KEY uk_so_line (sales_order_id, line_no),
    KEY idx_so_line_product (product_id),
    CONSTRAINT fk_so_line_header FOREIGN KEY (sales_order_id) REFERENCES sale_order (sales_order_id),
    CONSTRAINT fk_so_line_product FOREIGN KEY (product_id) REFERENCES md_product (product_id)
) ENGINE=InnoDB COMMENT='销售订单明细';

CREATE TABLE inv_stock (
    stock_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '库存记录主键',
    warehouse_id BIGINT UNSIGNED NOT NULL COMMENT '仓库ID',
    product_id BIGINT UNSIGNED NOT NULL COMMENT '产品ID',
    quantity_on_hand DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '账面库存',
    quantity_allocated DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '已分配库存',
    last_counted_at DATETIME NULL COMMENT '最近盘点时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (stock_id),
    UNIQUE KEY uk_stock_warehouse_product (warehouse_id, product_id),
    CONSTRAINT fk_stock_warehouse FOREIGN KEY (warehouse_id) REFERENCES scm_warehouse (warehouse_id),
    CONSTRAINT fk_stock_product FOREIGN KEY (product_id) REFERENCES md_product (product_id)
) ENGINE=InnoDB COMMENT='仓库产品库存余额';

-- 以下三张表只有部分注释，模拟维护质量不一致的业务模块。
CREATE TABLE fin_expense_claim (
    claim_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '报销单主键',
    claim_no VARCHAR(30) NOT NULL,
    applicant_id BIGINT UNSIGNED NOT NULL COMMENT '申请人员工ID',
    department_id BIGINT UNSIGNED NOT NULL,
    submitted_date DATE NOT NULL,
    claim_status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    approved_by BIGINT UNSIGNED NULL,
    approved_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (claim_id),
    UNIQUE KEY uk_claim_no (claim_no),
    KEY idx_claim_applicant (applicant_id),
    KEY idx_claim_department (department_id),
    CONSTRAINT fk_claim_applicant FOREIGN KEY (applicant_id) REFERENCES org_employee (employee_id),
    CONSTRAINT fk_claim_department FOREIGN KEY (department_id) REFERENCES org_department (department_id),
    CONSTRAINT fk_claim_approver FOREIGN KEY (approved_by) REFERENCES org_employee (employee_id)
) ENGINE=InnoDB COMMENT='员工费用报销单';

CREATE TABLE fin_expense_item (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    claim_id BIGINT UNSIGNED NOT NULL COMMENT '报销单ID',
    expense_date DATE NOT NULL,
    category_code VARCHAR(30) NOT NULL,
    description VARCHAR(255) NULL,
    amount DECIMAL(12,2) NOT NULL COMMENT '报销金额',
    invoice_no VARCHAR(60) NULL,
    vendor_name VARCHAR(160) NULL,
    PRIMARY KEY (item_id),
    KEY idx_expense_item_claim (claim_id),
    CONSTRAINT fk_expense_item_claim FOREIGN KEY (claim_id) REFERENCES fin_expense_claim (claim_id)
) ENGINE=InnoDB;

CREATE TABLE wf_approval_log (
    approval_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    business_type VARCHAR(30) NOT NULL COMMENT '业务类型',
    business_id BIGINT UNSIGNED NOT NULL,
    step_no INT NOT NULL,
    approver_id BIGINT UNSIGNED NOT NULL,
    action_code VARCHAR(20) NOT NULL,
    action_time DATETIME NOT NULL,
    opinion VARCHAR(500) NULL,
    PRIMARY KEY (approval_id),
    KEY idx_approval_business (business_type, business_id),
    KEY idx_approval_approver (approver_id),
    CONSTRAINT fk_approval_employee FOREIGN KEY (approver_id) REFERENCES org_employee (employee_id)
) ENGINE=InnoDB;

-- 以下五张遗留表刻意不添加表/列注释，也不声明外键。
-- 真实含义记录在 benchmark/ground_truth.md，供评测时对照。
CREATE TABLE t_a01 (
    k1 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    c01 VARCHAR(20) NOT NULL,
    d01 CHAR(7) NOT NULL,
    n01 DECIMAL(12,2) NOT NULL,
    n02 DECIMAL(12,2) NOT NULL,
    n03 DECIMAL(12,2) NOT NULL,
    n04 DECIMAL(12,2) NOT NULL,
    n05 DECIMAL(12,2) NOT NULL,
    f01 CHAR(1) NOT NULL,
    ts01 DATETIME NOT NULL,
    PRIMARY KEY (k1),
    UNIQUE KEY uk_a01_c01_d01 (c01, d01),
    KEY ix_a01_c01 (c01)
) ENGINE=InnoDB;

CREATE TABLE t_a02 (
    k1 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    c01 VARCHAR(20) NOT NULL,
    d01 DATE NOT NULL,
    c02 CHAR(1) NOT NULL,
    n01 DECIMAL(6,2) NOT NULL,
    n02 INT NOT NULL DEFAULT 0,
    c03 VARCHAR(30) NULL,
    ts01 DATETIME NOT NULL,
    PRIMARY KEY (k1),
    UNIQUE KEY uk_a02_c01_d01 (c01, d01),
    KEY ix_a02_c01 (c01),
    KEY ix_a02_d01 (d01)
) ENGINE=InnoDB;

CREATE TABLE t_b01 (
    k1 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    c01 VARCHAR(30) NOT NULL,
    c02 VARCHAR(20) NOT NULL,
    d01 DATE NOT NULL,
    n01 DECIMAL(14,2) NOT NULL,
    c03 VARCHAR(12) NOT NULL,
    c04 VARCHAR(80) NULL,
    f01 CHAR(1) NOT NULL,
    ts01 DATETIME NOT NULL,
    PRIMARY KEY (k1),
    UNIQUE KEY uk_b01_c01 (c01),
    KEY ix_b01_c02 (c02),
    KEY ix_b01_d01 (d01)
) ENGINE=InnoDB;

CREATE TABLE t_c01 (
    k1 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    c01 VARCHAR(20) NOT NULL,
    c02 VARCHAR(30) NOT NULL,
    d01 DATETIME NOT NULL,
    c03 VARCHAR(8) NOT NULL,
    n01 DECIMAL(14,2) NOT NULL,
    c04 VARCHAR(30) NULL,
    c05 VARCHAR(30) NULL,
    ts01 DATETIME NOT NULL,
    PRIMARY KEY (k1),
    KEY ix_c01_c01_c02 (c01, c02),
    KEY ix_c01_d01 (d01)
) ENGINE=InnoDB;

CREATE TABLE t_x9 (
    k1 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    c01 VARCHAR(20) NOT NULL,
    c02 CHAR(1) NOT NULL,
    n01 DECIMAL(14,2) NOT NULL,
    n02 INT NOT NULL,
    d01 DATE NULL,
    f01 CHAR(1) NOT NULL,
    ts01 DATETIME NOT NULL,
    PRIMARY KEY (k1),
    UNIQUE KEY uk_x9_c01 (c01)
) ENGINE=InnoDB;

-- 以下五张表模拟国内企业历史系统常见的拼音首字母字段命名。
-- 不声明外键，要求关系发现组件通过值匹配、唯一性和业务上下文自动识别关系。
CREATE TABLE rs_gzff (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '记录主键',
    ygbh VARCHAR(20) NOT NULL,
    gzny CHAR(7) NOT NULL COMMENT '工资年月，格式YYYY-MM',
    jbgz DECIMAL(12,2) NOT NULL,
    jt DECIMAL(12,2) NOT NULL,
    jj DECIMAL(12,2) NOT NULL,
    kk DECIMAL(12,2) NOT NULL,
    sfgz DECIMAL(12,2) NOT NULL COMMENT '实发金额',
    ffrq DATE NULL,
    ffzt CHAR(1) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_rs_gzff_ygbh_gzny (ygbh, gzny),
    KEY ix_rs_gzff_ygbh (ygbh),
    KEY ix_rs_gzff_ffrq (ffrq)
) ENGINE=InnoDB COMMENT='工资发放记录（历史系统）';

CREATE TABLE xs_hkhx (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    hkdh VARCHAR(30) NOT NULL,
    khbh VARCHAR(20) NOT NULL,
    ddbh VARCHAR(30) NOT NULL,
    hkrq DATE NOT NULL,
    hkje DECIMAL(14,2) NOT NULL,
    hxje DECIMAL(14,2) NOT NULL,
    hxzt CHAR(1) NOT NULL,
    jbrbh VARCHAR(20) NOT NULL,
    djrq DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_xs_hkhx_hkdh (hkdh),
    KEY ix_xs_hkhx_khbh (khbh),
    KEY ix_xs_hkhx_ddbh (ddbh),
    KEY ix_xs_hkhx_jbrbh (jbrbh)
) ENGINE=InnoDB;

CREATE TABLE ck_pdjl (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '盘点记录主键',
    pddh VARCHAR(30) NOT NULL COMMENT '盘点单号',
    ckbh VARCHAR(20) NOT NULL,
    spbm VARCHAR(30) NOT NULL,
    pdrq DATE NOT NULL,
    zmsl DECIMAL(14,2) NOT NULL,
    pdsl DECIMAL(14,2) NOT NULL,
    cysl DECIMAL(14,2) NOT NULL,
    pdrbh VARCHAR(20) NOT NULL,
    pdzt CHAR(1) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ck_pdjl_pddh (pddh),
    KEY ix_ck_pdjl_ckbh_spbm (ckbh, spbm),
    KEY ix_ck_pdjl_pdrbh (pdrbh)
) ENGINE=InnoDB COMMENT='仓库盘点记录';

CREATE TABLE rs_jcjl (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    jcbh VARCHAR(30) NOT NULL,
    ygbh VARCHAR(20) NOT NULL,
    fsrq DATE NOT NULL,
    jclx CHAR(2) NOT NULL,
    jcje DECIMAL(12,2) NOT NULL,
    yybm VARCHAR(20) NOT NULL,
    sprbh VARCHAR(20) NOT NULL,
    zt CHAR(1) NOT NULL,
    bz VARCHAR(200) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_rs_jcjl_jcbh (jcbh),
    KEY ix_rs_jcjl_ygbh (ygbh),
    KEY ix_rs_jcjl_yybm (yybm),
    KEY ix_rs_jcjl_sprbh (sprbh)
) ENGINE=InnoDB;

CREATE TABLE kh_hfjl (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    khbh VARCHAR(20) NOT NULL,
    lxrbh BIGINT UNSIGNED NOT NULL,
    lxrxm VARCHAR(80) NOT NULL,
    hfrq DATE NOT NULL COMMENT '回访日期',
    hffs CHAR(2) NOT NULL,
    lxdh VARCHAR(30) NULL COMMENT '联系电话',
    hfrbh VARCHAR(20) NOT NULL,
    hfjg VARCHAR(4) NOT NULL,
    xyhfrq DATE NULL,
    PRIMARY KEY (id),
    KEY ix_kh_hfjl_khbh (khbh),
    KEY ix_kh_hfjl_lxrbh (lxrbh),
    KEY ix_kh_hfjl_hfrbh (hfrbh),
    KEY ix_kh_hfjl_hfrq (hfrq)
) ENGINE=InnoDB COMMENT='客户回访记录';

SET FOREIGN_KEY_CHECKS = 1;
