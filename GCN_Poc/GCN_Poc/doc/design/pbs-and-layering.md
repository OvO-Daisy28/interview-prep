# 分层组织与 PBS 设计方案（第 3 点，超关键）

> 日期：2026-08-14
> 关联：`ragflow-dev-research.md`（研究计划）、`二次开发范围分析.md`、`ragflow_concepts_explained.md`、`architecture.md`
> 状态：首轮设计（**PBS 编码先占位**，待甲方 SNS 编码规范校准）
> 决策前提：RAGFlow 原生**只有平铺的知识库（dataset）列表 + chunk**，没有"分层分类"概念；**PBS 是客户领域概念**（技术规范书 PDF 4.2.3/4.2.3.3 全文 27 处，原文称"系统、设备、部件等 PBS 对象"），RAGFlow 内核同样没有，因此 PBS 组织需新建/二开。本方案全部为**新建/二开**，不依赖 RAGFlow 内核改动即可起步。

## 一、结论先行

本项目的"知识组织"由两个**正交维度**构成，必须分开设计，不能混为一谈：

1. **分层分类维度**（知识怎么归类）：给知识库/知识加一层分类目录树。规范书要求两类视角——**按知识类型**（设备/参数/操作/故障/部件/标准）和**按专业维度**（机械/电气/仪控/运行/维修/安全）。
2. **PBS 分解维度**（知识挂在设备的哪个部位）：Plant Breakdown Structure，电厂/设备分解结构（技术规范书 PDF 4.2.3/4.2.3.3 原文称"系统、设备、部件等 PBS 对象"，树形为 系统→子系统→设备→部件→零件）。PBS 是**分解结构**，SNS（《核电厂设备文件结构化标准编码体系（SNS）编码规范》）是**给 PBS 节点编码的规范**——两者是"结构 vs 编码"的互补关系，不是同一回事。每个参数/故障/操作/备件都必须挂到某个 PBS 节点。

两者关系：**信息块（Information Block）是交汇点**——一条信息块同时带 `pbs_code`（挂在哪）+ `knowledge_type`（是什么类型知识）+ `specialty`（哪个专业）+ 内容 + 来源 + 审核 + 版本。

落地采用**双轨存储 + 一层适配**：
- **权威结构化底座（PostgreSQL，新建）**：PBS 树 + 信息块 + 枚举字典，支撑增删改查/版本/多维检索。
- **图谱（RAGFlow KG，二开）**："系统PBS"作为 10 类实体之一，PBS 层级用"组成/从属"关系连成图，支撑跨章节/跨设备图遍历（GraphRAG 全局题）。
- **标签（RAGFlow 文档/chunk，二开）**：每份文档/chunk 打 `pbs_code` 路径 + 专业维度标签，供检索适配层做**域限定查询**。
- **检索适配层（新建）**：统一入口，把"用户当前 PBS 域 / 知识类型 / 专业"翻译成 RAGFlow 的 tag 过滤 + KG 子图范围。

---

## 二、分层分类维度设计

### 2.1 RAGFlow 现状

- 原生 `dataset` 是**平铺列表**，无层级、无分类目录（`ragflow_concepts_explained.md:154`）。
- 规范书 4.2.3 要求"知识库分层分类管理"，定论为**需二开加分类目录层**。

### 2.2 分类目录树（新建，受我们系统管理，RAGFlow 侧用 tag/dataset 映射）

建议两轴分类，组合成导航树：

| 轴 | 取值 | 作用 |
|---|---|---|
| 知识类型轴 | 设备 / 参数 / 操作 / 故障 / 部件 / 标准（规范书 4.2.3） | 决定信息块 schema 与展示模板 |
| 专业维度轴 | 机械 / 电气 / 仪控 / 运行 / 维修 / 安全（二次开发范围分析 2.2） | 权限隔离 + 精准检索 |

**RAGFlow 侧落地决策（待定，建议）**：
- **dataset 维度 = 知识类型**（如 `kb_params` / `kb_fault`），便于按类型走不同解析/检索策略；
- **tag 维度 = 专业维度 + pbs_code 路径**，用于域限定。
- 也可反过来（dataset=业务域）。**推荐先用"dataset=知识类型"**，因为规范书把"参数/故障/操作"明确列为不同类型知识，且解析与审核流程按类型差异大。

---

## 三、PBS 分解维度设计（双轨）

### 3.1 PBS 树形结构（领域标准）

```
核电站 (Plant)
 └─ 系统 (System)            例：反应堆冷却剂系统
     └─ 子系统 (Subsystem)    例：压力边界子系统
         └─ 设备 (Equipment)  例：主泵
             └─ 部件 (Component) 例：泵壳
                 └─ 零件 (Part)    例：密封圈
```

客户规范书明确引用 **SNS**（《核电厂设备文件结构化标准编码体系（SNS）编码规范》与《核电厂设备文件结构化信息码编码规范》）作为 PBS 节点编码标准；KKS 是另一种电厂标识系统，列为备选/待确认。中广核最终采用的具体编码细则需甲方提供规范文档校准（见第八节）。

### 3.2 双轨映射

| 存储 | 内容 | 承担职责 |
|---|---|---|
| **PostgreSQL `pbs_node`** | PBS 权威树（code/name/level/parent/类型） | 结构化增删改查、层级展开、版本、与信息块外键关联 |
| **RAGFlow KG** | "系统PBS"实体 + 组成/从属关系边 | 图遍历、GraphRAG 全局跨设备汇总 |
| **RAGFlow chunk tag** | `pbs:<code>`、`spec:<专业>` | 检索适配层做域限定过滤 |

### 3.3 pbs_code 占位方案（待 SNS 校准）

- **占位格式**：`SYS-SUB-EQP-CMP-PRT`（系统-子系统-设备-部件-零件，逐级可空）。
- **关联键**：所有信息块、文档、chunk 都通过 `pbs_code` 关联到 `pbs_node`，形成统一回溯链。
- **校准项**：拿到甲方 SNS/KKS 编码规范后，将占位格式替换为真实编码，并建立"编码↔节点类型"映射表。

---

## 三-B、时序维度（时序知识图谱，规范书 4.2.3.3）

> 客户（及项目经理）对"时序知识图谱"的诉求：不是另起一套图谱，而是**按设备生命周期阶段版本化**图谱，并用**时序标签**串联。

- **规范书原文（4.2.3 / 4.2.3.3）**：系统应支持**按时间节点独立构建知识图谱**；针对同一设备/系统，不同阶段（设计 / 制造 / 安装调试 / 运行）产生的文件应分别构建该时间节点下的版本，并通过**时序标签**形成串联关系；调用知识/图谱辅助内容时须**明确标注所引用知识的时间节点**。
- **设计含义**：在 PBS + 专业维度之外，新增一个**时间节点（阶段）维度**，作为信息块与图谱版本的第三正交轴：
  - `information_block` 增加 `time_node`（设计/制造/安装调试/运行）字段，同一 PBS 对象在不同阶段的知识各自成版本，通过时序标签/边串联成演化链。
  - RAGFlow KG 侧：同一实体在不同 `time_node` 下的图谱作为**版本**，用"时序/版本演化"关系边连接（二开点）。
  - 检索适配层：结果须回传 `time_node`，并支持"跨阶段串联追溯"与"指定阶段取值"。
- **RAGFlow 现状**：原生**不支持**图谱版本化与时序标签，属二开需求（与 PBS、专业维度同属信息块/图谱扩展维度）。

---

## 四、信息块（Information Block）数据模型

规范书定义信息块 = PBS对象 + 专业维度 + 信息类型 + 内容 + 来源 + 审核状态 + 版本（`ragflow_concepts_explained.md:80`）。三类信息块：参数 / 文档 / 关系（二次开发范围分析 2.1）。

### 4.1 PostgreSQL 表结构草案

```sql
-- PBS 权威树
CREATE TABLE pbs_node (
    pbs_code      VARCHAR(64) PRIMARY KEY,   -- 占位 SYS-SUB-EQP-CMP-PRT，待 SNS 校准
    name          VARCHAR(128) NOT NULL,
    node_level    SMALLINT NOT NULL,          -- 1系统 2子系统 3设备 4部件 5零件
    parent_code   VARCHAR(64) REFERENCES pbs_node(pbs_code),
    node_type     VARCHAR(16) NOT NULL,       -- 系统/子系统/设备/部件/零件
    description   TEXT,
    created_at    TIMESTAMP DEFAULT now()
);

-- 枚举字典（内容数据库子系统要求，≥500 条术语待建）
CREATE TABLE enum_dict (
    enum_type   VARCHAR(32) NOT NULL,  -- knowledge_type / specialty / info_category / review_status
    enum_code   VARCHAR(32) NOT NULL,
    enum_label  VARCHAR(64) NOT NULL,
    PRIMARY KEY (enum_type, enum_code)
);

-- 信息块（知识管理单元）
CREATE TABLE information_block (
    id                BIGSERIAL PRIMARY KEY,
    pbs_code          VARCHAR(64) NOT NULL REFERENCES pbs_node(pbs_code),
    knowledge_type    VARCHAR(32) NOT NULL,   -- 设备/参数/操作/故障/部件/标准
    specialty         VARCHAR(32) NOT NULL,   -- 机械/电气/仪控/运行/维修/安全
    info_category     VARCHAR(16) NOT NULL,   -- 参数/文档/关系
    time_node         VARCHAR(16),            -- 时序维度：设计/制造/安装调试/运行（规范书 4.2.3.3）
    content           TEXT NOT NULL,
    source_doc_id     VARCHAR(64),
    source_chunk_id   VARCHAR(64),
    confidence        JSONB,                  -- {来源, 审核, 时间, 一致性} 多维置信度
    review_status     VARCHAR(16) DEFAULT 'pending', -- pending/approved/rejected
    version           INT DEFAULT 1,
    valid_from        TIMESTAMP,
    valid_to          TIMESTAMP,
    created_at        TIMESTAMP DEFAULT now(),
    updated_at        TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_ib_pbs      ON information_block(pbs_code);
CREATE INDEX idx_ib_ktype    ON information_block(knowledge_type);
CREATE INDEX idx_ib_specialty ON information_block(specialty);
```

### 4.2 与 RAGFlow 的"双写"边界

- 结构化信息块入 **PostgreSQL**（权威、可版本化、可多维检索）。
- 同一内容的向量/图谱入 **RAGFlow**（检索/推理）。
- 检索适配层优先查 PostgreSQL 做精确域限定，再回 RAGFlow 取语义块（与 architecture 决策 8 双写一致）。

---

## 五、检索适配层如何利用分层 + PBS

统一查询入口接收结构化上下文：`{ pbs_scope, knowledge_type, specialty, query }`。

1. **域限定**：`pbs_scope` 展开为 PBS 子树的所有 `pbs_code`，转成 RAGFlow chunk tag 过滤（`pbs:<code>` IN 子树）。
2. **类型/专业限定**：`knowledge_type` / `specialty` 转 tag 过滤，实现权限隔离与精准召回。
3. **图谱范围**：KG 查询时以 `pbs_scope` 对应的"系统PBS"实体为根，限定子图，避免全图爆炸（呼应 architecture 4.3 路由与决策 8 分域）。
4. **回传标注**：检索结果统一补 `pbs_code` / `specialty` / `time_node` / `confidence` / `source`，满足规范书"检索结果含 PBS/专业维度/时序节点/置信度/来源"（二次开发范围分析 2.2、规范书 4.2.3.3）。

---

## 六、RAGFlow 侧二开点清单（本方案触发）

| 二开点 | 内容 | 依据 |
|---|---|---|
| 分类目录层 | dataset 之上加分类树（或外部系统管理 + RAGFlow tag 映射） | 二次开发范围分析 2.2 |
| chunk 标签 | 写入 `pbs:<code>` + `spec:<专业>` | 本文 3.2/5 |
| KG PBS 实体 | "系统PBS"实体 + 组成/从属边，领域 Prompt（10 实体/6 关系） | ragflow_concepts 6.2/6.3 |
| 检索返回扩展 | 补 pbs_code/置信度/专业维度 | 二次开发范围分析 2.2 |
| 文档/KB 元数据 | PBS 归属、专业维度字段 | 同上 |
| 时序标签/版本 | 图谱按 time_node 版本化 + 时序边；信息块 time_node 字段 | 规范书 4.2.3.3 |

---

## 七、验收标准

- [ ] PBS 树可在 PostgreSQL 建树、展开任意节点的祖先/后代链。
- [ ] 一条信息块能同时带 pbs_code + 知识类型 + 专业维度 + 内容 + 来源 + 审核 + 版本，并可版本回溯。
- [ ] 检索适配层能按 pbs_scope 限定返回，且结果带 pbs_code/置信度/专业维度标注。
- [ ] RAGFlow KG 中"系统PBS"实体与组成/从属边可被 GraphRAG 全局题命中（跨设备汇总）。
- [ ] 信息块可按 `time_node`（阶段）版本化，检索结果回传 `time_node` 并支持跨阶段串联追溯（规范书 4.2.3.3 时序知识图谱）。

---

## 八、待甲方校准项（阻塞项，用户已确认"先占位"）

1. **SNS/KKS 编码规范**：决定 `pbs_code` 真实格式与节点类型映射。占位期间用 `SYS-SUB-EQP-CMP-PRT`。
2. **存量样本**：3-5 类设备手册，用于验证 PBS 对象识别准确率（二次开发范围分析 3.3.6）。
3. **dataset 维度取舍**：dataset=知识类型 vs 业务域，需与内容数据库子系统设计对齐（建议前者）。

> 注：以上不影响本方案结构落地；拿到规范后仅替换编码映射与补全枚举字典。
