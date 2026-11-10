# HSK 练习双版本（2.0 / 3.0）与翻译模块拆分 · 软件设计文档

> 服务：`practice-service`（网关前缀 `/api/practice`）｜版本 v2.3｜2026-11-10｜状态：待评审
> 依据：2026-11-10 双版本首页 UI 截图 + 代码基线 + TEST / PROD 实测
> 前置：[首页设计方案](HSK练习模块首页-设计方案.md)、[翻译独立模块接口方案](HSK翻译练习-独立模块接口方案.md)、[共用题库方案](HSK练习-共用题库方案.md)（本文修正其中三处过时结论，见 §9.1）
>
> **v2.3 变更**：上下架改为**正向布尔 + 双场景**——`deleted_prac` 已在库中改为 `enabled_prac tinyint NOT NULL DEFAULT 1`（`1` 启用 / `0` 下架），并新增对称的 `enabled_exam`，两列铺到 5 张内容表（卷 / 题组 / 题 / 口语卷 / 口语题）；`practice_module_part_config` 同步新增 `enabled tinyint NOT NULL DEFAULT 1` 作板块开关，`deleted` 回到纯逻辑删除。全文字段名、0/1 语义、SQL、迁移陷阱、四级开关（现为五级）已同步。

---

## 1. 概述

### 1.1 目标

一套代码同时服务 HSK 2.0 与 3.0 两套大纲：用户切换版本后，等级范围、模块数量、卡片顺序与布局随之变化，且**两套练习进度互不污染**。同时把「翻译」从写作模块里拆成独立入口。

### 1.2 范围

| # | 覆盖 |
|---|---|
| 1 | 目录层（等级 → 卷 → 板块）全面支持 `version` 入参，缺省 `HSK2.0` |
| 2 | 新增首页聚合接口 `GET /hsk/modules`，下发卡片顺序、布局、角标、可用性 |
| 3 | 翻译（`SEC_TRANSLATION`）剥离为独立入口 `/translation/**` |
| 4 | `HSK7-9` ↔ 数字 `7` 双向映射收口，消灭 4 处硬编码版本常量与 3 处 `level` 解析缺陷 |
| 5 | 上下架统一为**正向布尔 + 双场景**：`enabled_prac` / `enabled_exam` 两列铺到 5 张内容表（卷 / 题组 / 题 / 口语卷 / 口语题），练习侧只读 `_prac`；板块开关改用新表 `practice_module_part_config.enabled`；三张旧表（`practice_paper_structure` / `practice_part_setting` / `practice_paper_setting`）**全部 drop** |
| 6 | 全部作答表删 `structure_id`，统一用 `(paper_id, section_mapping, section)` 定位；`practice_record` 另删 `practice_name`、启用 `question_ids` 快照 |

**不覆盖**：口语评测链路（仅补版本过滤）、翻译自动评分（P2）、`exam-service` / `manage` 的业务逻辑（实体已随 5 表加 `enabledPrac` / `enabledExam` 字段，仅字段映射，无逻辑改动）、首页视觉还原（见首页设计方案）。

### 1.3 术语

| 术语 | 说明 |
|---|---|
| 版本 | 仅两个合法值：`HSK2.0` / `HSK3.0` |
| 等级编码 | `HSK1`…`HSK6`、`HSK7-9`（**不是 `HSK7`**） |
| 模块映射 | `SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` / `SEC_SPEAK` / `SEC_TRANSLATION` / `SEC_CSCA`（`SEC_SPEAKING` 是未被代码引用的历史编码，本次清掉） |
| 板块 | 一张卷里的一段（如「听力第 2 部分」），配置落 `practice_module_part_config`，题量由 `question` 现算 |
| 上下架 | 内容是否对用户可见。**正向布尔**：`enabled_prac`（练习侧）/ `enabled_exam`（考试侧），`1` 启用、`0` 下架；两列铺在 `exam_paper` / `question` / `question_group` / `speaking_exam_paper` / `_question` 上 |
| 三元组 | `(paper_id, section_mapping, section)`，全部作答表的唯一身份，取代原 `structure_id` |

---

## 2. 总体设计

### 2.1 系统上下文

```
iOS / Android
   │  Authorization: Bearer <JWT>   X-Client-Type: APP   Accept-Language: zh|en|vi
   ▼
gateway  /api/practice/**（未在白名单，全部要求登录）
   ▼
practice-service
   ├─► MySQL xuexitest
   │     ├─ 题库（只读）：exam_paper（enabled_prac 卷级上下架）/ question（题级）/ question_group
   │     ├─ 口语内容：speaking_exam_paper / _question（2.0 与 3.0 共用）
   │     ├─ 模块配置：practice_module_level_config（模块开关 / 能力描述 / 时长）
   │     ├─ 板块配置：practice_module_part_config（板块名三语 / 题型 / 板块开关）
   │     ├─ 等级字典：hsk_level_config
   │     └─ 作答：practice_record / practice_answer / practice_report
   │              writing_* / speaking_*（翻译复用写作链路）
   ├─► ai-service        口语评测（翻译评分 P2）
   └─► system-service    口译录音上传（前端直传，本服务只存 URL）
```

无 Redis、无 Feign。

### 2.2 分层与子模块

| 层                         | 包                                              | 职责                                    | 本次改动       |
| ------------------------- | ---------------------------------------------- | ------------------------------------- | ---------- |
| Controller                | `{listen,read,write,speak,trans}/*/controller` | 解析 `version` / `levelCode` / `userId` | 加参数        |
| Catalog Service           | `*/service/impl/*CatalogServiceImpl`           | 等级 / 卷 / 板块目录 + 进度聚合                  | 版本化 + 换配置源 |
| Attempt / Answer / Submit | `writing/*`、各模块 `*ServiceImpl`                 | 作答、保存、交卷、报告                           | 仅准入校验      |
| Domain Support            | `core/support`                                 | 值对象、模块注册表、目录装载                        | 新增 4 个类    |
| Mapper                    | `core/mapper` + XML                            | 数据访问                                  | 少量 SQL 加条件 |

子模块：版本上下文、模块注册表、首页聚合、听力/阅读/写作/口语目录、**翻译目录（新）**、**翻译写链路（新，薄封装）**。

### 2.3 四条设计原则

1. **版本上下文只作用在目录层。** 作答链路拿 `(paperId, section_mapping, section)`，版本已被三者唯一确定 → `attempt/answer/submit/report` 不加 `version`。改动面从 40+ 端点收敛到 16 个目录端点。
2. **版本与等级编码收口成两个值对象。** 现状是 4 个模块各写一遍 `"HSK" + level` 与裸 `parseInt`，`HSK7-9` 必踩坑。全局只允许 `PracticeVersion` / `PracticeLevelCode` 解析等级。
3. **翻译走「目录独立 + 作答复用」。** 目录 `/translation/**` 独立，写链路薄封装后委托既有 `Writing*Service`，不复制表、不复制评分。
4. **目录只下发「有题的节点」。** 题数为 0 的等级 / 卷 / 板块在服务端消失，前端拿到的必是可用数据。

---

## 3. 详细设计

### 3.1 领域模型

#### 3.1.1 版本与等级值对象（`core/support/`）

**`PracticeVersion`（枚举）**：`HSK2_0("HSK2.0")` / `HSK3_0("HSK3.0")`。
`of(String)`：空 → `HSK2_0`；**严格大小写**（`hsk3.0` 必须 400，不做 `toLowerCase`，否则掩盖前端 bug）；非法 → `BusinessException(400, PRACTICE_VERSION_INVALID)`。

**`PracticeLevelCode`（静态工具）**

| 方法 | 输入 → 输出 | 说明 |
|---|---|---|
| `parse(code)` | `HSK1`…`HSK6`、`HSK7-9` → `1`…`7` | 非法抛 404 |
| `of(level)` | `7` → `"HSK7-9"` | **唯一**的 level→code 出口 |
| `dbLevels(level)` | `7` → `["7","7-9"]` | DB 侧 `exam_paper.level` 候选集（两库取值不一致） |
| `parseDbLevel(dbLevel)` | `"7"` / `"7-9"` → `7` | 从 `exam_paper.level` 反解 |


#### 3.1.3 数据模型：两层

```
内容层（真相源，含四级状态位）              配置层（模板 + 开关）
exam_paper                                  practice_module_level_config
  version / level                          (version, level, section_mapping)
  deleted        ← 逻辑删除                 enabled / total_question_count
  enabled_prac   ← 练习侧上下架 ★           suggested_duration_minutes
  enabled_exam   ← 考试侧上下架（不看）      ability_description × 3 语
  └─< question_group                       practice_module_part_config ★
       enabled_prac / enabled_exam         (version, level, section_mapping,
       └─< question                          section) ← 唯一键含板块号
            section_mapping ← 模块归属       part_name × 3 / type_code
            section         ← 部分号 1..N   standard_question_count
            type_id_mapping ← 题型编码       enabled ← 板块开关 ★
            layout          ← 渲染布局       deleted ← 逻辑删除
speaking_exam_paper（2.0 + 3.0 口语）
  enabled_prac / enabled_exam
  └─< speaking_exam_paper_question
       enabled_prac / enabled_exam
        │
        └──► 装配：part_config 当骨架 + question 补实际题量（缺行兜底）
                    ▼
             作答层：practice_record 用 (paper_id, section_mapping, section) 定位
```

> **两套开关是正交的**：`enabled_prac` / `enabled_exam` 是**场景维度**（这份内容给练习用、给考试用），配置层的 `enabled` 是**运营维度**（这个板块这一刻开不开）。练习侧只看前者里的 `_prac` 一个，考试侧只看 `_exam`。

| 层   | 表                                                    | 承载                                                   | 真相源   |
| --- | ---------------------------------------------------- | ---------------------------------------------------- | ----- |
| 内容  | `exam_paper` / `question`                            | 版本、等级、**卷级 / 题级上下架（`enabled_prac`）**、模块归属、部分号、题型、题干、**实际题量** | ✅     |
| 内容  | `question_group`                                     | 板块内的材料 / 大题容器（1 板块 : N group），**不参与结构装配**；带 `enabled_prac` 但练习侧不单独判（材料随题走） | ✅     |
| 内容  | `speaking_exam_paper` / `_question`                  | 口语内容（**2.0 与 3.0 共用**，`level` 2.0 为 `Beginner/Intermediate/Advanced`、3.0 为 `3..7-9`） | ✅     |
| 配置  | `practice_module_level_config`                       | 版本 × 等级 × 模块：模块开关、标准总题量、时长、能力描述三语                    | ✅     |
| 配置  | **`practice_module_part_config`**                    | 版本 × 等级 × 模块 × **板块**：名三语、题型编码、标准题量、**板块开关 `enabled`**、`deleted` 逻辑删除（`answerMode` 由 `type_code` 映射，不入库） | ✅     |
| 作答  | `practice_record` / `practice_report` / `writing_*` / `speaking_*` | 练习记录，统一用 `(paper_id, section_mapping, section)` 定位 | 只引用上层 |
| 退场  | `practice_paper_structure` / `practice_part_setting` / `practice_paper_setting` | 三张表 **P0 直接 drop**，不保留 ID 注册表（§3.2.6 / §3.2.7） | —     |

> **一句话**：`question` 去重出「有哪些板块」，`part_config` 给「板块叫什么、能不能练」，`exam_paper.enabled_prac` 给「哪些卷能练」，`level_config` 给「哪些模块开放」。中间那三张表都没有独有信息。

#### 3.1.4 业务规则（落进代码的 15 条）

| #    | 规则                                                                                                                              | 落点                              |
| ---- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| R1   | `version` 只有两个合法值，缺省 2.0，非法 → 400                                                                                               | `PracticeVersion.of`            |
| R2   | `HSK7-9` 是一个等级，数值 `7`；禁止裸 `parseInt(levelCode)`                                                                                 | `PracticeLevelCode`             |
| R3   | `exam_paper.level` 两库取值不一致（TEST `"7"` / PROD `"7-9"`,上生产记得改为7），查询必须 `IN (候选集)`                                                  | `PracticeLevelCode.dbLevels`    |
| R4   | 翻译仅 3.0；2.0 调 `/translation/**` 返回空数组 / 空对象，前端无这个模块展示                                                                           | `TranslationCatalogServiceImpl` |
| R5   | 口语内容统一读 `speaking_exam_paper`（**2.0 与 3.0 都在这里**）；`question` 里的 `SEC_SPEAKING` 5 条为HSK7-9级试卷的口语题目，两边都要读                         | `SpeakingCatalogServiceImpl`    |
| R6   | 目录根据卷、板块、题目开启开关下发                                                                                                               | 各 Catalog Service               |
| R7   | 板块配置只存一处：名称/题型/顺序/开关只写 `practice_module_part_config`                                                                            | Code Review 卡点                  |
| R8   | 实际题量必须现算：`standard_question_count` 是标准值，下发前被 `question` 计数覆盖                                                                    | 各 Catalog Service               |
| R9   | **代码中不得再出现 `structureId`**：`practice_paper_structure` / `practice_part_setting` 本次直接 drop，无 ID 注册表                              | Code Review 卡点                  |
| R10  | 全部作答表只认三元组 `(paper_id, section_mapping, section)`，`structure_id` 列在 P0 全部删除                                                     | 各 Record / Attempt Service      |
| R11  | 卷级上下架只认 `exam_paper.enabled_prac`：`1` = 可练，`0` = 下架。**列表、详情、开始作答三条路径必须都判**，任一处漏判就是下架卷可直达                                        | 各 Catalog / Record Service      |
| R12  | 卷状态只写一处：`enabled_prac` 在 `exam_paper` 上是整卷级，跨 2~3 个模块同时生效，禁止再引入任何模块级卷状态                                                         | Code Review 卡点                  |
| R12b | **练习侧只读 `enabled_prac`，一律不看 `enabled_exam`**：两张开关正交，运营为考试下架的题不得连带从练习消失（反之亦然）。`enabled_exam` 属考试侧，本模块不读写                         | Code Review 卡点                  |
| R13  | 板块开关只影响「新练习下发哪些板块」：不得删题、不得改 `question.deleted`、不得过滤历史 `question_ids` 快照                                                         | Catalog / Record Service        |
| R14  | **`enabled = 0` 不算缺行**：只有「这一行根本不存在」才兜底（`第{section}部分`、视为开放）；`enabled = 0` 是显式关闭，必须不下发。查询不能先过滤 `enabled = 1`，否则被关板块掉进"缺行"档被兜底放出来 | 各 Catalog Service               |
| R14b | 板块开关用 `enabled`（0 关 / 1 开），`deleted` 恢复纯逻辑删除语义。两者都不为 0 之外的值：`enabled` 只由运营改，`deleted` 只在建/删模板行时动                                | Code Review 卡点                  |
| R15  | `speaking_attempt.paper_id` 指向 `speaking_exam_paper.id`（与 `exam_paper.id` 零交集），其三元组语义为「口语卷 × `SEC_SPEAK` × 部分号」                 | `Speaking*Service`              |

---

### 3.2 数据库设计

#### 3.2.1 表的处置

| 表 | TEST 行数 | 处理 | 说明 |
|---|---|---|---|
| `exam_paper` | 167（活 136） | ✅ TEST 已改；**PROD 待补 2 列** | `version` 管版本、`level` 管等级、**`enabled_prac` 管练习侧上下架**、`enabled_exam` 管考试侧（练习不读） |
| `question` | 13624 | ✅ TEST 已改；**PROD 待补 2 列** | `section_mapping` 定模块、`section` 定部分号、`type_id_mapping` 定题型；`enabled_prac` 为**题级上下架** |
| `question_group` | 1038 | ✅ TEST 已改；**PROD 待补 2 列** | 翻译两个大题组已在；不参与结构装配。带 `enabled_prac` 但练习侧不单独判（材料随题走） |
| `speaking_exam_paper` / `_question` | 38 / 837 | ✅ TEST 已改；**PROD 待补 2 列** | **2.0 与 3.0 口语内容都在这两张表**（R5）；两表各有 `enabled_prac` |
| `practice_module_level_config` | 49 | ✅ 保留，删 `parts_config` 列（TEST 已删） | 模块级配置 |
| **`practice_module_part_config`** | **132** | ✅ TEST 已建 + **已补 `enabled` 列**；仍缺唯一键 | 板块级配置；**开关用 `enabled`（0关/1开），`deleted` 回到纯逻辑删除**（§3.2.2） |
| `hsk_level_config` | 13 | ✅ 零改 | 等级三语名称 |
| `practice_paper_setting` | 206 / 116 | ❌ **P0 drop** | 卷级上下架由 `exam_paper.enabled_prac` 完整替代（§3.2.7） |
| `practice_paper_structure` | 1290 | ❌ **P0 drop** | 无独有信息：板块来自 `question` 去重 + `part_config` 取名（§3.2.6） |
| `practice_part_setting` | 1294 | ❌ **P0 drop** | 与 structure 1:1，题型编码已进 `part_config`；作答模式改由字典映射 |
| `practice_record` | 889 | ⚠️ 瘦身：删 `structure_id` + `practice_name`，启用 `question_ids` | §3.2.5 |
| `practice_report` | 477 | ⚠️ 瘦身：删 `structure_id` | 有 `practice_record_id` 可回溯 |
| `writing_attempt` / `speaking_attempt` | 217 / 283 | ⚠️ **加两列 → 回填 → 删 `structure_id`** | §3.2.6 |
| `practice_question_option_pool` | 2347 | ⏳ P2 退场（先加两列，再改 `pool_code`） | 数据可推但自身不完整（§3.2.6） |

> 一句话：**本次之后，库里不存在任何一张「结构表」，也不再存在 `structure_id` 这个字段。** 板块的「有哪些」由 `question` 去重得出，「叫什么、开不开」由 `practice_module_part_config` 给出。

#### 3.2.2 板块配置表 `practice_module_part_config`

**表结构以数据库现有定义为准**（TEST 已建，132 行）：

```sql
CREATE TABLE `practice_module_part_config` (
  `id`                      bigint       NOT NULL COMMENT '板块配置ID',
  `version`                 varchar(30)  NOT NULL COMMENT '考试大纲版本（HSK2.0 / HSK3.0）',
  `level`                   int          NOT NULL COMMENT 'HSK等级；与主表同类型同口径，3.0 的 7-9 级统一存 7',
  `section_mapping`         varchar(50)  NOT NULL COMMENT '模块编码（SEC_LISTEN/READ/WRITE/TRANSLATION/SPEAKING）',
  `section`                 int          NOT NULL COMMENT '模块内部分号 1..N；对齐 question.section，唯一键第四列',
  `part_name`               varchar(100) NOT NULL COMMENT '板块名中文（第一部分）',
  `part_name_en`            varchar(255)          DEFAULT NULL COMMENT '板块名英文',
  `part_name_vi`            varchar(255)          DEFAULT NULL COMMENT '板块名越南语',
  `type_code`               varchar(64)  NOT NULL COMMENT '题型稳定编码，取值域 = question.type_id_mapping',
  `type_name`               varchar(100)          DEFAULT NULL COMMENT '题型名中文',
  `type_name_en`            varchar(255)          DEFAULT NULL COMMENT '题型名英文',
  `type_name_vi`            varchar(255)          DEFAULT NULL COMMENT '题型名越南语',
  `standard_question_count` int          NOT NULL DEFAULT '0' COMMENT '标准题量',
  `sort_order`              int          NOT NULL DEFAULT '0' COMMENT '展示顺序',
  `enabled`                 tinyint      NOT NULL DEFAULT '1' COMMENT '是否启用：0否，1是',
  `deleted`                 int          NOT NULL DEFAULT '0' COMMENT '逻辑删除标记：0正常，1删除',
  `created_by`              bigint                DEFAULT NULL COMMENT '创建人ID',
  `update_by`               bigint                DEFAULT NULL COMMENT '更新人ID',
  `created_time`            bigint                DEFAULT NULL COMMENT '创建时间',
  `updated_time`            bigint                DEFAULT NULL COMMENT '修改时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
  COMMENT='练习板块级配置表（等级级模板 + 板块开关）';
```

**板块开关 = `enabled`**（`0` 关闭 / `1` 开放），位置在 `sort_order` 之后、`deleted` 之前。`deleted` 回到**纯逻辑删除**语义，只有建/删模板行时才动——两列分工明确，不再让一列兼任两种含义。

| 项                  | 现状                               | 处置                                                             |
| ------------------ | -------------------------------- | -------------------------------------------------------------- |
| **板块开关**           | `enabled tinyint NOT NULL DEFAULT 1` | ✅ **已加**（TEST 132 行全为 1）                                  |
| 逻辑删除 `deleted`     | `int NOT NULL DEFAULT 0`         | ✅ 保留，**不再当开关用**                                              |
| 作答模式 `answer_mode` | 无此列                              | **不加列**：由 `type_code` 经 `PracticeTypeRegistry` 映射              |
| 唯一键                | 只有 `PRIMARY (id)`                | 建议补 `uk_module_part`：既防重，又能保证「关了一个板块后仍只有一行，改 `enabled` 即可重新开放」 |

```sql
-- 先查重，必须返回 0 行（实测 TEST 无重复，132 行）
SELECT version, level, section_mapping, section, COUNT(*) c
FROM practice_module_part_config
GROUP BY version, level, section_mapping, section HAVING c > 1;

-- 只在唯一键上补，不动任何列
ALTER TABLE practice_module_part_config
  ADD UNIQUE KEY `uk_module_part` (`version`,`level`,`section_mapping`,`section`) USING BTREE;
```

> 唯一键**不含 `enabled` / `deleted`**，正是想要的：关板块 = 把该行 `enabled` 置 0，开回来 = 置 1，全程只有一行，不会因为"关了再建"而堆出重复行。

**🔴 改用 `enabled` 之后陷阱仍在：查询不能先过滤 `enabled=1`**

因为「`enabled = 0`」和「这一行根本不存在」仍是两种不同状态（换列不换问题）：

| 状态 | 含义 | 目录表现 |
|---|---|---|
| 有行，`enabled = 1`（`deleted=0`） | 已配置，开放 | 下发，名称/题型取该行 |
| 有行，`enabled = 0`（`deleted=0`） | **运营明确关闭** | **不下发** |
| 有行，`deleted = 1` | 模板行已删除 | 视同没有行（不参与兜底排重） |
| 没有行 | 未配置过 | 按 R14 兜底开放，名称为 `第N部分` |

如果先 `WHERE enabled = 1` 过滤，被关闭的板块就会掉进"没有行"那一档，被 R14 的兜底逻辑重新放出来——**开关直接失效**。正确做法是查出该等级该模块的全部行（不带 `enabled` / `deleted` 条件），在内存里分两拨：

```sql
SELECT section, part_name, part_name_en, part_name_vi,
       type_code, type_name, standard_question_count, sort_order, enabled, deleted
FROM practice_module_part_config
WHERE version = ? AND section_mapping = ? [AND level = ?]
ORDER BY level, sort_order;
-- 注意：没有 AND enabled = 1，也没有 AND deleted = 0
```

- `enabled = 1 AND deleted = 0` 的行 → 板块骨架
- `enabled = 0 AND deleted = 0` 的行 → 加入 `closedSections` 集合，**该 section 一律不下发，且不参与兜底**
- `deleted = 1` 的行 → 丢掉，两个集合都不进
- `question` 里出现、但两个集合都没有的 section → 才按 R14 兜底

> `level` 用 `int` 与主表 `practice_module_level_config` 一致；写入时把 `exam_paper.level` 的 `'7-9'` 归一到 `7`，读侧仍用候选集 `IN ('7','7-9')`（R3）。
>
> 两张配置表现在**列结构一致**：都是 `enabled`（开关）+ `deleted`（逻辑删除）两列分工。`level_config` 的 `enabled` 管整卡，`part_config` 的 `enabled` 管单个板块。

**`answer_mode` 的取值（字典，不入库）**：`type_code` → 作答交互。

| `type_code` 段 | `answerMode` |
|---|---|
| `listen_*` / `read_*` / `*_choose` 类 | `SINGLE` |
| `*_match` / `*_img_match` / `*_sent_match` | `MATCH` |
| `*_order` / `*_sentence_order` | `ORDER` |
| `*_speak` / `*_repeat` / `*_retell` / `read_aloud` / `answer_question` | `RECORD` |
| `translation_written` / `*_essay` / `chart_analysis` / `topic_essay` | `TEXT` |

映射表与现网 `practice_part_setting.answer_mode` 逐行比对一次（旧表是服役值），差异记入附录 A 的 B-09。


#### 3.2.4 目录装配（读时装配，不写中间表）

```sql
-- ① 模块开关（一版本×模块 = 等级数行）
SELECT level, section_mapping, enabled, total_question_count, suggested_duration_minutes
FROM practice_module_level_config
WHERE deleted = 0 AND version = ? AND section_mapping = ? [AND level = ?];

-- ② 板块骨架 + 板块开关（故意不带 enabled / deleted 条件，理由见 §3.2.2）
SELECT level, section, part_name, part_name_en, part_name_vi,
       type_code, type_name, standard_question_count, sort_order, enabled, deleted
FROM practice_module_part_config
WHERE version = ? AND section_mapping = ? [AND level = ?]
ORDER BY level, sort_order;

-- ③ 卷列表（enabled_prac 即卷级上下架；1 = 可练）
SELECT id, level, source, description, created_time
FROM exam_paper
WHERE deleted = 0 AND exam_type = 1 AND enabled_prac = 1
  AND version = ? AND level IN (?, ...)      -- 7-9 候选集（R3）
ORDER BY level, id;                          -- 原 setting.sort_order 与 id 升序 100% 等价

-- ④ 每卷每板块实际题量（按卷批量，勿逐卷查；题级上下架在这里生效）
SELECT paper_id, section_mapping, CAST(section AS SIGNED) AS section_no, COUNT(*) AS actual_count
FROM question
WHERE deleted = 0 AND enabled_prac = 1 AND paper_id IN (...)
  AND (type_id_mapping IS NULL OR type_id_mapping <> 'example_question')
  AND section IS NOT NULL AND section <> ''
GROUP BY paper_id, section_mapping, section;
```

装配顺序（服务端内存）：
1. 把 ② 的结果分两拨：`enabled = 1 AND deleted = 0` → 骨架（按 `sort_order` 排序）；`enabled = 0 AND deleted = 0` → `closedSections` 集合；`deleted = 1` 的行直接丢；
2. 只有「既不在骨架、也不在 `closedSections`」的 `section` 才按 R14 兜底（`第{section}部分`，视为开放）；
3. 用 ④ 的 `actual_count` **覆盖** `standard_question_count`（④ 已排除 `enabled_prac = 0` 的单题，所以单题下架会自动缩小题量）；
4. `actual_count = 0` 的板块不下发（R6）——**这一条同时兜住了「板块开着但题全被单题下架」**；
5. 模块 `enabled = 0` → 整模块不下发，**不再求值板块**；
6. 板块在 `closedSections` 里 → 该板块不下发，历史记录不受影响（R13）；
7. `answerMode` 由 `type_code` 经 `PracticeTypeRegistry` 映射后下发（不入库，§3.2.2）。

**口语是唯一走另一张内容表的模块**：②③④ 换成 `speaking_exam_paper`（`enabled_prac = 1`）+ `speaking_exam_paper_question`（`enabled_prac = 1`）的计数，板块骨架仍来自 `practice_module_part_config`（`section_mapping = 'SEC_SPEAK'`，`section` 为 1/2/3）。

🔴 **取题必须由配置驱动，不能再靠硬编码题型白名单**：现在 `SpeakingSourceQuestionMapper.xml` 用 `PartCodeCase` 把 8 个题型硬编码映射到 `PART_1/2/3`，而新配置里已有 6 个 `type_code` 不在其中（3.0 L4/L5/L6 的 `listen_retell`、L7 的 `applied_read_speak` / `listen_material_answer` / `viewpoint_express`），`selectByPart` 的 `question_type_mapping IN (...)` 白名单同样漏掉它们 → **这些板块目前取不到任何题**（缺陷 B-19）。改造后取题条件改为：

```sql
WHERE paper_id = ? AND deleted = 0 AND enabled_prac = 1 AND number > 0
  AND question_type_mapping = (SELECT type_code FROM practice_module_part_config
                               WHERE version=? AND level=? AND section_mapping='SEC_SPEAK' AND section=?)
```

一个板块一个 `type_code`，新增题型只需加配置行，不改代码。

#### 3.2.5 `practice_record` 改造

**实测等价性**（改造前提，已验证而非假设）

| 验证项 | TEST | PROD |
|---|---|---|
| `part_setting.section_code` = 同板块 `question.section` | 1087 / 1087 | 480 / 480 |
| 三元组能查到题的记录 | 906 / 907 | **1343 / 1343** |
| 旧路径（`structure_id`）与新路径（三元组）取题数 | 905 / 907 | **1343 / 1343 零差异** |
| `practice_name` = `structure.section_name` | 905 / 905 | 1343 / 1343 |

TEST 唯一差异是造数（`id=1111111`、`structure_id=111`），改造时一并软删。
代码层同样成立：`PracticeQuestionMapper.xml` 的 `selectByStructure` 内部就是 `JOIN practice_part_setting ON q.section = pps.section_code`，`structureId` 只是三元组的代理键；同文件的 `selectByPart(paperId, sectionMapping, sectionCode)` 早已存在。

**目标结构**

| 列 | 现状 | 判定 |
|---|---|---|
| `structure_id` | 963 行有值，存在脏值（`2082292518405345282` 的值 = `paper_id`） | ❌ 删 |
| `practice_name` | 与 `section_name` 100% 一致（纯复制）；格式跨模块不统一（听力 `第1部分` 649 条 / 阅读 `第一部分` 257 条） | ❌ 删 |
| `section` varchar(50) | 全非空，取值 `1–4`，与 `question.section` 同口径 | ✅ 升为定位键 |
| `question_ids` json | 列已存在，CSCA 已用（56 / 21 条），HSK 全 NULL | ✅ 启用为题目快照 |

**🔴 CSCA 也在这张表里，删列前必须一并改代码**：CSCA 记录 `paper_id = 0`（哨兵）、`section_mapping = 'SEC_CSCA'`、`section` 存**科目名**（`math` / `physics` / `arts_chinese` / `chemistry` / `science_chinese`），其 `structure_id = 6e18 + sha256("csca|科目|语言")` 是**库里无对应行的纯占位值**。

实测每个科目只对应 1 个 `structure_id`（TEST 5 科目 5 个、PROD 5 科目 5 个，无一对多），因此 `(paper_id, section_mapping, section)` 与 `structure_id` 完全等价。删列后 CSCA 侧须改 3 处：`CscaRecordServiceImpl` 建轮、`CscaSubmissionServiceImpl` 提交、`CscaReportMapper` 报告插入——把 `CscaStructureIds.of(...)` 换成 `sectionMapping='SEC_CSCA'` + `section=科目码`，`CscaStructureIds` 类可整体删除。

```sql
ALTER TABLE practice_record DROP COLUMN structure_id, DROP COLUMN practice_name;

-- 索引必须显式重建
DROP INDEX idx_record_active ON practice_record;
CREATE INDEX idx_record_active ON practice_record
  (user_id, paper_id, section_mapping, section, status);

ALTER TABLE practice_record MODIFY COLUMN question_ids json NULL
  COMMENT '本次练习题集快照（自然序 question.id 数组；创建时写入，此后不改）';
```

> 🔴 **索引是隐藏坑**：`DROP COLUMN structure_id` 会让 MySQL 把它从 `idx_record_active` 里静默剔除，索引退化为 `(user_id, paper_id, status)`，而新查询按 `(user_id, paper_id, section_mapping, section, status)` 过滤 → 全表扫。

**查询改写（7 处 Mapper）**

| 方法 | 旧 | 新 |
|---|---|---|
| `selectInProgress` / `selectInProgressForUpdate` | `paper_id + structure_id` | `paper_id + section_mapping + section` |
| `selectLatestSubmitted` / `selectLatestReady` / `selectByAllStatus` | `structure_id` | 同上 |
| `selectInProgressByStructures` / `selectLatestReadyByStructures` | `structure_id IN (...)` | `paper_id IN (...) + section_mapping IN (...)`，内存分组 |

批量方法服务于目录页「每板块是否有草稿 / 报告」角标，改成一次查全卷比 `IN (1201 个 structureId)` 更省。

**接口契约变更**

| 旧 | 新 |
|---|---|
| `POST /listening/records/start {paperId, structureId}` | `{paperId, section}` |
| `GET /listening/parts/{structureId}/reports/latest` | `GET /listening/papers/{paperId}/parts/{section}/reports/latest` |
| `POST /reading/records/start {paperId, structureId}` | `{paperId, section}` |
| `GET /reading/parts/{structureId}/reports/latest` | `GET /reading/papers/{paperId}/parts/{section}/reports/latest` |

前端改拿目录响应里的 `partCode`（= `section`）+ 卷 `id`。**目录响应不再下发 `structureId`**——它随结构表一起消失，不留 deprecated 字段，避免前端继续依赖。

**`question_ids` 用法**

| 时机 | 动作 |
|---|---|
| `start` | 查该板块全部题目 ID → 排序 → 写入，`total_questions = JSON_LENGTH` |
| `resume` | 不重算，直接按记录里的 `question_ids` 拉题（题序不变） |
| `submit` | 只统计，不改 |
| 报告 | 以 `question_ids` 为准，不现查题库 → 题库改版后仍可复现 |

#### 3.2.6 作答表回填三元组，结构表直接 drop

**前置验证已完成（2026-11-10，两库实测）**

| 验证项 | TEST | PROD |
|---|---|---|
| 三元组 ↔ `structure_id` 是否一对一 | 1201 / 1201，0 处歧义 | 648 / 648，0 处歧义 |
| 一个 `structure_id` 是否只对应一个 `section_code` | 是（1294 行，0 例外） | 是（648 行，0 例外） |
| `writing_attempt` 能 join 到 structure + part_setting | 217 / 217 | 284 / 284 |
| `speaking_attempt` 同上 | 283 / 283 | 473 / 473 |
| `option_pool` 同上 | 2505 / 2505 | 1150 / 1150 |
| `writing_attempt` 回填后能取到题 | 217 / 217 | 284 / 284 |

> 结论：**没有任何一行会丢**。所以 `practice_paper_structure` / `practice_part_setting` 不需要保留成「ID 注册表」，可以在 P0 直接 drop。

**三张表各自的部分号来源**

| 表 | 部分号从哪来 | 备注 |
|---|---|---|
| `practice_record` | 列已存在（`1–4`） | 零回填 |
| `practice_report` | 通过 `practice_record_id` 回溯 | 零回填 |
| `writing_attempt` | `part_setting.section_code` → 纯数字 | 100% 可脚本回填 |
| `speaking_attempt` | `part_setting.section_code` 是 **`PART_1/2/3`** | `SUBSTRING(section_code,6)` → `1/2/3` |
| `practice_question_option_pool` | 同 writing，纯数字 | P2 处理 |

**回填 SQL（P0，五闸门 + DRY-RUN + 备份）**

```sql
-- ① writing_attempt
ALTER TABLE writing_attempt
  ADD COLUMN section_mapping varchar(50) NULL AFTER paper_id,
  ADD COLUMN section int NULL AFTER section_mapping;

UPDATE writing_attempt x
JOIN practice_paper_structure s ON s.id = x.structure_id
JOIN practice_part_setting  pps ON pps.structure_id = s.id
SET x.section_mapping = CONVERT(s.content_type USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
    x.section         = CAST(pps.section_code AS SIGNED);

-- ② speaking_attempt（section_code 形如 PART_2）
ALTER TABLE speaking_attempt
  ADD COLUMN section_mapping varchar(50) NULL AFTER paper_id,
  ADD COLUMN section int NULL AFTER section_mapping;

UPDATE speaking_attempt x
JOIN practice_paper_structure s ON s.id = x.structure_id
JOIN practice_part_setting  pps ON pps.structure_id = s.id
SET x.section_mapping = CONVERT(s.content_type USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
    x.section         = CAST(SUBSTRING(pps.section_code, 6) AS SIGNED);

-- ③ 回填校验：必须 0 行残留
SELECT COUNT(*) FROM writing_attempt  WHERE section_mapping IS NULL OR section IS NULL;
SELECT COUNT(*) FROM speaking_attempt WHERE section_mapping IS NULL OR section IS NULL;

-- ④ 回填通过后才允许删列
ALTER TABLE writing_attempt  DROP COLUMN structure_id, MODIFY section INT NOT NULL;
ALTER TABLE speaking_attempt DROP COLUMN structure_id, MODIFY section INT NOT NULL;
```

**🔴 三张表的索引都会静默降级，必须显式重建**（`DROP COLUMN` 会自动从复合索引里剔除该列，不报错）

| 表 | 现有索引 | 删列后变成 | 应重建为 |
|---|---|---|---|
| `practice_record` | `idx_record_active (user_id, paper_id, structure_id, status)` | `(user_id, paper_id, status)` | `(user_id, paper_id, section_mapping, section, status)` |
| `writing_attempt` | `idx_writing_attempt_active (user_id, paper_id, structure_id, question_set_version, status)` | `(user_id, paper_id, question_set_version, status)` | `(user_id, paper_id, section_mapping, section, question_set_version, status)` |
| `speaking_attempt` | `idx_speaking_attempt_part (user_id, structure_id, status)` | **只剩 `(user_id)`，索引基本作废** | `(user_id, paper_id, section_mapping, section, status)` |

```sql
DROP INDEX idx_writing_attempt_active ON writing_attempt;
CREATE INDEX idx_writing_attempt_active ON writing_attempt
  (user_id, paper_id, section_mapping, section, question_set_version, status);

DROP INDEX idx_speaking_attempt_part ON speaking_attempt;
CREATE INDEX idx_speaking_attempt_part ON speaking_attempt
  (user_id, paper_id, section_mapping, section, status);
```

**`practice_paper_structure` 的历史 ID 不能重算**：`20…` 479 行 / `70…` 608 / `80…` 114，稳定公式只覆盖 248 / 1201（20.6%）。但因为**所有引用方都已回填成三元组**，这个事实不再有影响——没有谁需要它。

**drop 顺序**（对应 §10 的 P0-e / P0-h / P0-i / P0-j，此处只列依赖关系）

```
① 目录换源（P0-e）：PracticeCatalogBatchLoader 不再读两张结构表
② 加列 + 回填 + 校验（P0-h）：writing_attempt / speaking_attempt 三元组齐备，0 残留
③ 删代码里的 structureId（随 P0-h 一起）：实体 / Mapper / Controller / DTO
④ DROP TABLE practice_part_setting → practice_paper_structure（P0-j）
```

**代码改动面**

| 位置 | 动作 |
|---|---|
| `PracticeRecordMapper`（7 个方法） | `structure_id` → `paper_id + section_mapping + section` |
| `PracticeQuestionMapper#selectByStructure` | 直接改用已有的 `selectByPart(paperId, sectionMapping, sectionCode)`；**该 Mapper 3 处出题 SQL 均已带 `AND enabled_prac = 1`**（题级下架在出题侧已生效） |
| `PracticeCatalogBatchLoader` | 删掉 structure / part_setting 两次查询，改读 `practice_module_part_config` |
| `PracticePaperStructureMapper` / `PracticePartSettingMapper` | 整文件删除 |
| `PracticePartSetting` / `PracticePaperStructure` 实体 | 整文件删除 |
| `PracticeRecord` / `PracticeReport` / `PracticeQuestionOptionPool` 实体 | 删 `structureId` 字段 |
| `CscaStructureIds` + 3 处 CSCA 调用 | 改用 `SEC_CSCA` + 科目码（§3.2.5） |
| 各 Controller / DTO 的 `structureId` 入参出参 | 改 `paperId + section`（§3.2.5 接口表） |
| `ListeningReportController` / `ReadingReportController` | 路径 `parts/{structureId}/...` → `papers/{paperId}/parts/{section}/...` |

**`practice_question_option_pool`（P2）**：加两列回填后按题目关联，退场前置三件事——① 补 `reading_cloze` 缺失记录（TEST 90 / PROD 90 全无）；② `pool_code` 去掉 `structureId`，改 `{section_mapping}_{paperId}_{section}_{sha256(option_content)}`；③ 答题快照 `optionPoolCode` 改现算（现在由 `ReadingSnapshotSupport` 读表写入）。它不阻塞结构表 drop，因为结构表先走完 P0。

#### 3.2.7 卷级上下架改由 `exam_paper.enabled_prac` 承担

`practice_paper_setting` 一行 = 一张卷，`exam_paper` 也是一行 = 一张卷，两者 `paper_id` 严格 1:1。它的三个开关在真实卷上**从未被使用**：

| 字段 | TEST | PROD | 真实卷上的使用情况 |
|---|---|---|---|
| `enabled = 0` | 2 行 | 5 行 | **全部是孤儿行**（`paper_id` 在 `exam_paper` 里不存在） |
| `visible = 0` | 0 行 | 0 行 | 从未使用 |
| `deleted = 1` | 31 行 | 0 行 | **全部是孤儿行** |

于是这张表对真实卷只剩下一个信息：**这一行存不存在**。而"存在 = 上架"这个语义，正是 `exam_paper.enabled_prac` 的语义（列注释即「练习是否启用：0否，1是」）。

**卷序也不是独有信息**：`sort_order` 在 TEST 13 个「版本×等级」组、PROD 6 个组上都与 `id` 升序**完全一致**（逐组比对，0 处不同），属纯冗余。

**顺带纠正一处旧判断**：过去认为「PROD 每级 20 张卷只上架 10 张，是运营刻意控量」。实测不成立——那 10 张是 `exam_paper.deleted = 1`（软删），本来就被 `deleted=0` 挡在外面，与 `practice_paper_setting` 无关。真正"有卷但无 setting 行"的**活卷只有 16 张**：

| 范围 | 活卷（`deleted=0`） | 有 setting 行 | 无 setting 行 |
|---|---|---|---|
| TEST 2.0 + 3.0 | 136 | 136 | **0** |
| PROD 2.0 | 61 | 60 | **1**（L1） |
| PROD 3.0 | 15 | 0 | **15**（整版未放开） |
| PROD 另计 `deleted=1` 的卷 | 61 张（被 `deleted` 挡住，与本表无关） | 0 | — |

也就是说这张表在现网实际只承载了「2.0 L1 的 1 张 + 3.0 的 15 张未上架」这一个信息。

**收益**：库存表少一张；「缺行 = 下架」这个隐式、不可查询的语义消失，改为显式列值，运营能直接 `WHERE enabled_prac = 0` 查出现在下架了哪些卷，也能审计。

**代价**：放弃"可分享链接直达但不上列表"这一档（`enabled` 与 `visible` 的两级语义）。实测该能力从未被真实卷使用，且 C 端目前也没有对应的分享入口。

##### 迁移口径（陷阱在 DEFAULT 的方向）

`enabled_prac` 是**正向布尔**（`1` = 启用），所以加列时 `DEFAULT '1'` 会把本该下架的卷一次性全部放出来——和早期用 `deleted_prac`（`DEFAULT '0'`）时是同一个陷阱，只是方向相反。

```sql
-- ① 5 张内容表统一加两列（TEST 已完成，PROD 全缺 = D11）
ALTER TABLE exam_paper
  ADD COLUMN enabled_prac tinyint NOT NULL DEFAULT '1' COMMENT '练习是否启用：0否，1是',
  ADD COLUMN enabled_exam tinyint NOT NULL DEFAULT '1' COMMENT '考试是否启用：0否，1是';
-- question / question_group / speaking_exam_paper / speaking_exam_paper_question 同一条，列定义逐字一致

-- ② 必须同一批次：把「当前无 setting 行」的活卷置 0，否则 PROD 目录从 60 卷涨到 76 卷
-- 注意 deleted = 0：那 61 张软删卷已被 deleted 挡住，不参与
UPDATE exam_paper p
SET p.enabled_prac = 0
WHERE p.exam_type = 1 AND p.deleted = 0
  AND NOT EXISTS (SELECT 1 FROM practice_paper_setting s WHERE s.paper_id = p.id);
```

- **TEST 实测已就绪**：5 张表都有这两列，取值 `167 / 13624 / 1038 / 38 / 837` 行**全为 1**（全部上架），无历史数据要修。
- **PROD**：76 张活卷里 60 张有 setting 行、16 张缺行 → ② 之后 60 张为 1、16 张为 0，与现网一致（2.0 每级 10 张、3.0 全 0）。3.0 正式放开时把那 15 张改回 `1`。
- 孤儿行 69（TEST）/ 56（PROD）随表退场自然消失，无需单独清理（原 D12 关闭）。

##### 🔴 `enabled_exam` 的边界：练习侧一行都不许读

`enabled_prac` / `enabled_exam` 是**两个独立的上下架通道**，同一行的两个值可以任意组合：

| `enabled_prac` | `enabled_exam` | 含义 | 练习侧 |
|---|---|---|---|
| 1 | 1 | 练习、考试都在用 | ✅ 可见 |
| 1 | 0 | **只在练习出现**（考试下架，比如该题只适合练） | ✅ 可见 |
| 0 | 1 | 只在考试出现（练习下架，比如已练烂/有争议） | ❌ 不可见 |
| 0 | 0 | 全面下线 | ❌ 不可见 |

所以 `practice-service` 的全部查询条件只能是 `enabled_prac = 1`，**不能写成 `enabled_prac = 1 AND enabled_exam = 1`，也不能用 `OR`** —— 一旦混进来，`enabled_exam=0` 的题会被连带从练习踢出去，而运营的本意恰恰是"只关考试"。

##### 代码现状（已改 / 待改）

已随本次字段改造改完（编译通过的前提）：

| 位置 | 现状 |
|---|---|
| `ListeningCatalogServiceImpl:65` / `ReadingCatalogServiceImpl:120` / `WritingCatalogServiceImpl:156` | ✅ 已 `.eq(PracticePaper::getEnabledPrac, 1)` |
| `PracticeQuestionMapper.xml`（3 处） | ✅ 已 `AND enabled_prac = 1` —— **题级上下架已生效** |
| `CscaQuestionMapper.xml`（5 处） | ✅ 已 `p.enabled_prac = 1` / `q.enabled_prac = 1` / `g.enabled_prac = 1` |
| `SpeakingSourcePaperMapper.xml` / `SpeakingSourceQuestionMapper.xml` | ✅ 已 `enabled_prac = 1`，`resultMap` 已映射两列 |
| 5 张表对应实体（exam-service + manage 各一套） | ✅ 已加 `enabledPrac` / `enabledExam` 字段 |

还欠（属 P0-i，`practice_paper_setting` 退场时一并做）：

| 位置 | 现状 | 改成 |
|---|---|---|
| `SharedPaperEligibility.isEligible` | ❌ 仍只判 `deleted == 0 && examType == 1`，**没判 `enabledPrac`** | 补 `&& Integer.valueOf(1).equals(paper.getEnabledPrac())`（B-17） |
| `PracticeCatalogBatchLoader:77` | 仍查 setting 三条件 | 删该查询，`visiblePaperIds` 直接用入参 |
| `ReadingRecordServiceImpl:179` / `WritingAttemptServiceImpl:225` | 用 `setting` 判准入 | 改判 `paper.getEnabledPrac() == 1` |
| `ReadingCatalogServiceImpl:131` / `SpeakingCatalogServiceImpl:167` / `WritingCatalogServiceImpl:167` | 按 `getSortOrder()` 排序 | 改 `id` 升序 |

> ⚠️ `SharedPaperEligibility` 这一条最危险：目录侧已经用 `enabled_prac = 1` 过滤了，**但准入侧没同步**——下架卷在列表里看不见，却仍能通过详情 / 开始作答接口直接进入。三条路径必须同口径（R11）。

---

### 3.3 接口设计

> 路径为 service 内路径，客户端实际调用加网关前缀 `/api/practice`。

#### 3.3.1 版本参数

| 项 | 规定 |
|---|---|
| 参数名 / 位置 | `version`，query string（不用 header，也不用 path） |
| 类型 / 必填 | `string`，枚举 `HSK2.0` / `HSK3.0`；缺省 `HSK2.0` |
| 大小写 | **敏感**，`hsk3.0` → 400 |
| 特殊值 | 无（不提供 `ALL` / `LATEST`） |

#### 3.3.2 存量 16 端点改造

| # | 方法 | 路径 | 现状 | 改造 |
|---|---|---|---|---|
| 1 | GET | `/listening/levels` | 无 `version`、无 `exam_type` 过滤 | 加 `version`、补 `exam_type=1`、走资格判定 |
| 2 | GET | `/listening/levels/{levelCode}/intro` | `selectOne` 不带 version → 两版本同等级共存时抛 `TooManyResults` | `selectOne` 带 `version` + `deleted=0` |
| 3 | GET | `/listening/papers/{paperId}/parts` | 配置查询无 version | 同 2；板块来源改配置表 + 题量现算 |
| 4 | GET | `/reading/levels` | `VERSION` 常量 | 常量改参数 |
| 5 | GET | `/reading/levels/{code}/intro` | 常量 + 裸 `parseInt` → `HSK7-9` 必 404 | 改 `PracticeLevelCode` |
| 6 | GET | `/reading/papers` | 常量 + `eq(level, "7")` 匹配不到 PROD 的 `"7-9"` | `level IN (dbLevels)` |
| 7 | GET | `/reading/papers/{paperId}/parts` | 无版本校验 | 卷 `version` 与入参不符 → 404 |
| 8 | GET | `/reading/preferences` | 表无 version 列 | **P0 不改**（见 §3.3.6） |
| 9 | PUT | `/reading/preferences/level` | 同上，`HSK7-9` 会 404 | P0 仅 2.0 可写；P1 加 version 列 |
| 10–12 | GET | `/writing/levels`、`/levels/{code}/intro`、`/papers` | 常量；`parseLevel` 正则只到 `HSK[1-6]`；`introSections` 的 switch 只到 6 | 常量改参数；补 `7` 分支（图表描述 1 + 话题作文 1） |
| 13 | GET | `/writing/papers/{paperId}/parts` | `Integer.parseInt(paper.getLevel())` → `"7-9"` 抛 500 | 改 `PracticeLevelCode.parseDbLevel` |
| 14–16 | GET | `/speaking/levels`、`/papers`、`/papers/{paperId}/parts` | 常量 + `SEC_SPEAK` 单映射 | 常量改参数；**2.0 / 3.0 都读 `speaking_exam_paper`**（R5），卷 `/parts` 的来源改 `practice_module_part_config` |

> 统一约定：`version` 必须**同时**作为 `practice_module_level_config.version` 与 `exam_paper.version` 的条件，漏一处会出现「等级列表是 2.0、卷列表是 3.0」。


#### 3.3.4 翻译模块

**目录 4 个（P0）**

| # | 路径 | 说明 |
|---|---|---|
| T1 | `GET /translation/levels?version=HSK3.0` | 2.0 → `[]` |
| T2 | `GET /translation/levels/{levelCode}/intro` | 单对象，`sections[]` 来自板块配置 |
| T3 | `GET /translation/papers?levelCode=HSK7-9&version=HSK3.0` | 卷清单，过滤 `totalQuestionCount=0` |
| T4 | `GET /translation/papers/{paperId}/parts` | 板块列表，**必须下发 `answerMode`** |

`answerMode` = `TEXT`（笔译）/ `RECORD`（口译），正是两张卡渲染不同的根因。

**写链路 6 个（P0，薄封装委托 `Writing*Service`）**

| # | 路径 | 委托 |
|---|---|---|
| T5 | `POST /translation/attempts/start` | `WritingAttemptService#start` |
| T6 | `GET /translation/attempts/{attemptId}` | `#get` |
| T7 | `GET /translation/attempts/{attemptId}/questions` | `#listQuestions` |
| T8 | `PUT /translation/attempts/{attemptId}/answers` | `WritingAnswerService#save` |
| T9 | `POST /translation/attempts/{attemptId}/submissions` | `WritingSubmissionService#submit` |
| T10 | `GET /translation/reports/{reportId}` | `WritingReportService#get` |

**统一前置校验**（每个封装方法第一行）：按 `(paperId, section)` 校验**内容侧的真实归属**——`question` 里该卷该板块的 `section_mapping` 必须为 `SEC_TRANSLATION`，否则 400 `SECTION_MAPPING_MISMATCH`。

```sql
SELECT DISTINCT section_mapping FROM question
WHERE paper_id = ? AND deleted = 0 AND enabled_prac = 1 AND CAST(section AS SIGNED) = ?;
```

> 带 `enabled_prac = 1` 是有意的：若该板块的题被逐题下架，这里会返回空集 → **按 404 处理**（板块不可练），而不是放行后让用户进到一个 0 题的作答页。空集与"归属不符"要分别给出 404 / 400。

> 原来这层校验靠 `structureRegistry(structureId).content_type`，结构表 drop 后改由**内容自己**回答「这个板块属于哪个模块」——比注册表更可信（结构表本身可能写错）。不要改成信任前端传的 `sectionMapping`，那等于取消防串号。

**必须放宽 1 处存量校验** `WritingAttemptServiceImpl#validatePart`：

```
现状：!WRITING.equals(contentType) || !WRITING.equals(sectionMapping) → 404
改为：!WRITING_COMPATIBLE.contains(contentType) || !contentType.equals(sectionMapping)
      WRITING_COMPATIBLE = Set.of("SEC_WRITE", "SEC_TRANSLATION")
```

不加这条，翻译**根本开不了练习**。这是「目录独立、作答复用」的唯一侵入点，必须与目录隔离成对评审。

#### 3.3.5 异常处理

| 场景 | 处理 |
|---|---|
| `version` 非法 | 400 `PRACTICE_VERSION_INVALID` |
| `levelCode` 在该版本下不存在 | 404，沿用各模块原有文案 |
| `paperId` 的 version 与入参不符 | 404「试卷不存在」（**不提示版本不符**，避免探测） |
| `sectionMapping` 与模块不匹配 | 400 `SECTION_MAPPING_MISMATCH` |
| 目录查询异常 | 整卡 `available=false` + `LOAD_FAILED`，**不 500 整页** |
| 报告评分策略缺失（翻译 P0） | 报告正常返回，`feedbackStatus=UNAVAILABLE`、`score=null` |
| 板块配置缺行（R14） | 兜底命名 + 视为开放，记 `WARN` 日志供运营补配 |

#### 3.3.6 板块开关的读写边界

| 侧 | 行为 | 端点 |
|---|---|---|
| C 端 | 只读，按 `enabled` + `enabled_prac` 过滤，**不暴露开关字段** | 既有 16 端点，零新增 |
| 运营端（板块） | 改该行的 `enabled`（`0` 关闭 / `1` 开放）即开关板块；**不要删行**，删行等于回到"未配置"，会被 R14 兜底放出来；`deleted` 只在真的不要这个板块时才置 1 | `GET /hsk/module-config/parts?version=&level=&sectionMapping=`、`PATCH /hsk/module-config/parts/{id}` |
| 运营端（卷 / 题） | 改 `exam_paper.enabled_prac`、`question.enabled_prac`（`1` 上架 / `0` 下架），整卷 / 单题生效；考试侧改对应的 `enabled_exam` | 沿用题库管理侧现有卷 / 题编辑能力，**本次不新增接口** |
| 本次不做 | 批量上下架、板块级灰度、按用户差异化 | — |

> C 端响应结构不变（`parts[]` 仍只有 `partCode / partName×3 / typeCode / answerMode / questionCount`），保证 2.0 现网响应可逐字段 diff。

---

### 3.4 五级开关与求值顺序

| 级 | 开关 | 粒度 | 关掉之后 |
|---|---|---|---|
| L1 版本 | 前端选择 / `exam_paper.version` | 版本 | 整版不出现 |
| L2 模块 | `practice_module_level_config.enabled` | 版本×等级×模块 | 整卡消失，**不再求值下级** |
| L3 卷 | `exam_paper.enabled_prac`（`1` 可练 / `0` 下架） | 卷 | 不在列表、详情与作答均拒绝 |
| L4 板块 | `practice_module_part_config.enabled`（`1` 开放 / `0` 关闭） | 版本×等级×模块×板块 | 该板块不下发，新练习不含其题目 |
| L5 题 | `question.enabled_prac`（`1` 上架 / `0` 下架） | 单题 | 题量现算时不计入；算完为 0 则该板块按 R6 不下发 |

必须**自上而下短路**：L2 关 → 返回 `[]`，不查板块；L4 关 → 不求值 L5。

**L4 与 L5 是两道不同的闸**：L4 是「这整段你练不到」（板块骨架都不下发），L5 是「这段还在，但里面某几题不能出」。运营场景不同——整段题型有问题关 L4，单题有问题关 L5。代码上 L5 天然落在 `WHERE enabled_prac = 1` 里，不需要额外分支；L4 关掉的板块不应再去数题。

五者正交，实测佐证：「`level_config` 说开但 0 张卷在架」的组合 PROD 5 组、TEST 11 组（口语卷在 `speaking_exam_paper`、写作 L1–L2 被关）。

**关闭板块 / 下架单题后历史记录**：已有 `question_ids` 快照不受影响，仍可回看、出报告（板块标注「已关闭」）；新开练习不再下发该板块题目。不要把「关闭」实现成删题或过滤快照，否则历史报告凭空少题。

---

### 3.5 核心流程

**首页首屏**
```
GET /hsk/modules?version=HSK3.0 → 解析版本 → 模块元数据 → 批量查等级开关 → 批量查卷 → (可选)进度 → 排序返回
前端：layout=LIST 渲染 1 列 5 行；TRANSLATION.available=true → 可点
      entryLevelCode 非空 → 直达卷列表；否则 → 等级选择页
```

**翻译开始练习（含准入链）**
```
POST /translation/attempts/start {paperId, section}
 → requireAuthenticatedAppUserId（仅委托）
 → 前置校验：question 里 (paperId, section) 的 section_mapping == SEC_TRANSLATION
 → WritingAttemptServiceImpl#start
     ├─ requirePaper：卷有效 + exam_type=1 + enabled_prac=1 + level ≥ 3
     ├─ validatePart：contentType ∈ {SEC_WRITE, SEC_TRANSLATION} 且 == sectionMapping
     ├─ 已有 IN_PROGRESS → 直接返回（幂等）
     └─ 新建 attempt，快照 section_mapping / section / paperVersion / questionSetVersion
 → 返回 attemptId（String）
```

**版本切换**
```
清空已选 levelCode / 卷列表 / 滚动位置 / 本地「上次练习」→ GET /hsk/modules?version=<new>
```
> 不要复用旧 `levelCode` 打新版本 `/papers`：2.0 的 `HSK1` 在 3.0 下虽存在但卷集合不同；`HSK7-9` 在 2.0 下直接 404。

---

### 3.6 缓存 / 异步 / 权限

| 项 | 方案 |
|---|---|
| 模块元数据 | 进程内常量，无缓存 |
| 目录结果 | P0 不缓存（单等级 ≤ 21 卷）；P1 可加 Caffeine，`key = version + levelCode + module`，TTL 60s |
| 进度 | **禁止缓存**（用户态） |
| `dataVersion` | P1 引入：相关表 `MAX(updated_time)` 作 ETag，供前端失效 |
| 评分异步 | 翻译 P0 **不入队**：交卷先查 policy，无则直接 `UNAVAILABLE`；P1 补 `TRANSLATION_WRITTEN` 后开启 |
| 口译 ASR | P2，复用 `ai-service` |
| 登录 | 全部端点必须登录，`userId` 只从 `BaseController#getCurrentUserId` 取，不接受前端传 |

---

## 4. 错误码

沿用 `BusinessException(code, message)`（code 为 HTTP 语义码）。新增错误码**只在新增端点使用**，存量端点文案不动。

| code | message | 触发 |
|---|---|---|
| 400 | `PRACTICE_VERSION_INVALID` | `version` 不在白名单 |
| 400 | `SECTION_MAPPING_MISMATCH` | `(paperId, section)` 的实际模块不属于该接口 |
| 404 | `TRANSLATION_NOT_IN_VERSION` | 2.0 调翻译写链路（目录接口返回空数组不报错） |
| 409 | `TRANSLATION_NOT_SCORABLE` | 翻译交卷但无评分策略（P0 不报错，仅 P1 使用） |

数据异常（`parseInt("7-9")` 一类）本次要消灭：全部改走 `PracticeLevelCode`，改不净的包成 500 `QUESTION_DATA_INVALID`。

---

## 5. 安全

| 项 | 措施 |
|---|---|
| 参数注入 | `version` / `levelCode` 走白名单枚举；SQL 全部参数绑定 |
| 越权 | `attempt` 校验 `userId` 归属；翻译薄封装必须校验 `(paperId, section)` 的实际 `section_mapping`，否则可用写作板块串号 |
| 版本探测 | 卷版本不符统一回「试卷不存在」 |
| 答案泄露 | `answer` / `analysis` 不得在作答阶段 `/questions` 下发，只在报告接口给 |
| 音频 | 前端直传 `system-service /file/uploadVoice`，本服务只存 URL，不代理二进制 |
| ID 精度 | 新增端点 ID 一律 String（19 位雪花超 JS 安全整数）；存量 Long 于 P1 统一 |

---

## 6. 性能与容量

| 场景 | 数据量 | 设计 |
|---|---|---|
| 首页聚合 | 5 模块 × ≤ 7 等级 | SQL ≤ 5 次，全部批量；P95 ≤ 150ms |
| 卷列表 | 2.0 单等级 20–21 卷、3.0 1–3 卷 | 无分页，上限 21 |
| 题量统计 | 按卷批量 IN 查询 | 禁止逐卷循环 |
| 容量 | 3.0 补齐后 15 卷 ≈ 1059 题，相对 2.0 的 10561 题属小量级 | — |

索引：`exam_paper` 现以主键为主，3.0 仅 15 行不构成问题；卷数翻倍再评估 `(version, level, exam_type)` 复合索引。`question` 侧查询模式不变。

---

## 7. 依赖

| 依赖 | 用途 | 降级 |
|---|---|---|
| MySQL `xuexitest` | 全部数据 | 强依赖 |
| gateway | `/api/practice/**` → `lb://practice-service` | — |
| `ai-service` | 口语评测（翻译 P2） | 失败 → 报告 `TEMPORARILY_UNAVAILABLE` |
| `system-service` | 口译录音上传 | 前端提示重录 |
| `auth-service` | JWT 签发校验 | — |

**无新增依赖**：不引入 Redis、MQ，不新建内容表。

---

## 8. 测试要点

**版本隔离**
1. 不传 `version` → `layout=GRID_2`、4 卡、`TRANSLATION.available=false`。
2. `version=HSK3.0` → `layout=LIST`、5 卡、翻译 `entryLevelCode=HSK7-9`。
3. `hsk3.0`（小写）/ `HSK4.0` → 400，不得静默降级。
4. `/reading/levels?version=HSK3.0` → 7 个等级含 `HSK7-9`；2.0 → 6 个不含。
5. `/reading/papers?levelCode=HSK7-9&version=HSK3.0` 在 **PROD** 能查到卷（验证 R3 候选集）。🔴 最易漏。

**翻译独立**
6. 2.0 调 `/translation/levels` → `[]`，不 404。
7. 3.0 → 1 个等级，`totalQuestionCount=4`。
8. `/translation/papers/{id}/parts` → 2 个板块：笔译 `TEXT`、口译 `RECORD`。
9. 拿写作卷的 section 打翻译 → 400；拿翻译卷的 section 打写作 → 仍 404（写作侧不放宽）。
10. 笔译交卷 → 报告 `UNAVAILABLE`、`score=null`（P0 预期）。
11. `/writing/papers/{id}/parts` 不含翻译板块（回归）。

**存量回归**
12. 2.0 四模块全链路（等级→卷→板块→答题→报告）与改造前逐字段一致。
13. PROD `/listening/levels?levelCode=HSK1` 不再混入 3.0 卷。
14. TEST `/listening/levels/HSK1/intro` 不再 500。
15. PROD `/writing/papers/{HSK7-9 卷}/parts` 不再 500。
16. 存量 `writing_attempt`（PROD 284 / TEST 217）仍可打开续练。

**边界**
17. 未登录 → 401。
18. 某模块数据缺失 → 该卡 `available=false`，不全页 500。
19. 不存在的 `paperId` → 404 不 500。
20. `enabled_prac = 0` 的卷 → **列表不出现、详情报 404、开始作答报 404**（三处都测，B-17）。
21. 卷级上下架与模块/板块开关互不干扰：卷下架但模块开 → 该等级仍有其他卷；模块关但卷上架 → 整卡消失。

**上下架（`enabled_prac` / `enabled_exam`）**
22. `question.enabled_prac = 0` 的单题 → 目录题量 `-1`，答题时不出现在该板块题目列表；其它板块不受影响。
23. 某板块全部题都被单题下架 → 该板块因 `actual_count = 0` 不下发（R6），**不报错**。
24. 🔴 `enabled_prac = 1` 但 `enabled_exam = 0` → **练习侧必须仍可见**（只关了考试）；反向 `enabled_prac = 0, enabled_exam = 1` → 练习侧不可见。这两条是 B-20 的回归判据。
25. 全表 `grep enabledExam` / `grep enabled_exam` 在 `practice-service` 内 **零命中**（练习侧不得出现这一列）。

**板块开关**
26. 关 `HSK2.0/L1/SEC_LISTEN/section=2` → 目录只剩另外三个板块，其题量名称题型不受影响。
27. 新开练习不含 section=2 的题；历史记录仍可打开、报告题数不变（R13）。
28. 关整模块 → 整卡消失，不再受板块开关影响（短路顺序）。
29. **区分「关闭」与「未配置」**：把某行 `enabled` 置 0 → 该板块**消失**；把该行物理删掉 → 该板块**仍出现**且名称为 `第N部分`（R14）。这两条必须分别测，否则开关会被兜底逻辑吃掉。
30. `deleted = 1` 的行视同不存在：既不下发，也不参与兜底排重。
31. 结构表 drop 后口语 6 个新题型板块（3.0 L4/L5/L6 的 `listen_retell`、L7 的三个）**都能取到题**——这是 B-19 的回归判据。
32. 并发改同模块不同板块 → 两条都生效，无覆盖丢失。
33. 源码 `grep -r structure_id` 零命中；`practice_part_setting` / `practice_paper_structure` 已 drop；带 `structureId` 的旧请求 → 400 而非 500。

---

## 9. 关键取舍

### 9.1 纠正前置文档的三处过时结论

| 前置文档结论 | 实测 | 影响 |
|---|---|---|
| 「写作目录会多出翻译第 3 部分，需在 `listParts` 排除 `SEC_TRANSLATION`」 | `PracticeCatalogBatchLoader#assemble` 已按 `content_type = module` 过滤 | ✅ 该改动不需要做，翻译独立对写作目录零侵入 |
| 「`PracticeSections.isWriting()` 含翻译，只需薄封装」 | `validatePart` 硬判 `WRITING.equals(contentType)`，翻译 → 404；`PracticeSections` 类不存在 | 🔴 必须放宽 `validatePart`（§3.3.4） |
| 「各接口已有 `?version=` 入参」 | 4 个模块全是 `private static final String VERSION = "HSK2.0"`，无 Controller 接收 version | 🔴 版本参数是新增，16 个端点全改 |

### 9.2 版本用 query param

不用 header（隐式全局态，排障困难）、不用 path（路径翻倍，且版本是内容开关不是 API 版本）。代价是 16 个端点加参数、前端每请求都带，可接受。

### 9.3 翻译：目录独立 + 作答复用

| 方案 | 新增端点 | 持久层 | 存量侵入 | 结论 |
|---|---|---|---|---|
| 只分目录 | 4 | 复用 `writing_*` | 0 | ❌ 前端要两个 basePath |
| **目录独立 + 薄封装** | **4 + 6** | **复用 `writing_*`** | **1 处** | ✅ 采纳 |
| 完全独立 | 14 | 新建 7 张表 | 0 | ❌ 评分/报告/统计重造，工期最长 |

风险：放宽 `validatePart` 后写作与翻译共用 attempt 表，靠 `content_type` + `section_mapping` 双条件隔离，这两个条件必须成对评审。

### 9.4 `level='7-9'` 用代码容错，不立刻改数据

PROD 直接 `UPDATE exam_paper.level` 会动题库表，`exam-service` 读同一列，回归面大且违反「题库只读」。故先用 `IN ('7','7-9')`，P1 在导入流程统一写 `'7-9'` 后再删兼容分支。

### 9.5 板块配置拆成行式表

产品要「第一部分、第二部分单独控制开关」。`parts_config` 元素**没有 `section`、只有 `sortOrder`**，与 `question.section` 靠数组位置隐式对齐（TEST 38/46 行成立）。一旦允许关板块，数组必须留占位元素，`sortOrder` 就退化成「不可删的编号」——那它本来就该是 `section` 列。

| 方案 | 结论 |
|---|---|
| 元素补 `section` + 开关键 | 可行但不彻底：JSON 里没有唯一约束、开关写成 `"0"` 也存得进、审计只到整行、SQL 只能 `JSON_EXTRACT`，且"关一个板块"要么删元素（后续错位）要么留占位（`sortOrder` 退化成编号） |
| **拉平成 `practice_module_part_config`** | ✅ 唯一键防重、开关是独立的 `enabled` 列（`deleted` 只管逻辑删除）、`UPDATE ... SET enabled=0 WHERE section=2` 只锁一行 |
| 单表 `section=0` 表示模块行 | ❌ 一半字段永远 NULL，接口处处判 `section=0` |
| 不拆，靠前端隐藏 | ❌ 题目仍下发，用户仍能练到 |

**行数不增长**：新表挂 `(version, level, section_mapping, section)`，132 行封顶，由等级数决定，不随卷数膨胀；旧 `practice_part_setting` 挂 `structure_id`（卷级），1294 行且随题库扩容增长。这是**降粒度**，不是复活旧表。

### 9.6 `practice_record` 用三元组、删 `practice_name`

`structure_id` 是 `(paper_id, section_mapping, section)` 的代理键（`selectByStructure` 内部即三元组 JOIN），而 `practice_record` 三列本来就齐备，是第 4 份等价信息；实测新旧路径取题数 PROD 1343/1343 零差异。`practice_name` 与 `section_name` 100% 一致，纯复制。

「不能做唯一键」不是保留理由：重复组（TEST 131 / PROD 106）确实存在，但业务语义始终是取最新一条，从不需要唯一约束。

**同一个口径贯彻到全部作答表**：`writing_attempt`(217/284) 与 `speaking_attempt`(283/473) 原本只有 `paper_id + structure_id`，实测都能 100% 回填出三元组（§3.2.6），所以不留「结构表当 ID 注册表」这个尾巴，P0 一次删干净。接口风格也不再分叉——所有模块都用 `paperId + section`。

### 9.7 卷级上下架用 `exam_paper.enabled_prac`，`practice_paper_setting` drop

两个候选位置，只有一个是对的：

**❌ 不能并入 `practice_module_level_config`** —— 粒度 1:N 反向。一行配置 = 一个「版本 × 等级 × 模块」，它下面挂 1~21 张卷（TEST 2.0 每级 20~21 张、3.0 每级 1~3 张），`enabled` 是 `tinyint`，只能表达"整级整模块开关"，管不到其中某一张卷；且一张卷横跨 2~3 个模块（TEST 43 张 2 模块、92 张 3 模块、1 张 5 模块），下架是整卷行为，写进模块级配置要写 2~3 份，必然分叉。

**✅ 并回 `exam_paper` 是对的** —— `paper_id` 与 `exam_paper.id` 严格 1:1，粒度天然匹配；`enabled_prac` 是练习侧专用列（`enabled_exam` 才是考试侧），同表并列、互不干扰（CSCA 的 `exam_type=2` 卷同样带这两列）。同一套列模式一路铺到 `question` / `question_group` / `speaking_exam_paper` / `_question` 四张表，**卷、题组、题三个层级都能单独上下架，不需要另建任何表**。

**为什么这张表现在是空的**：三个开关在真实卷上 100% 全开（`enabled=0` 的 2/5 行、`deleted=1` 的 31 行**全部是孤儿行**），`sort_order` 也与 `id` 升序完全一致。它对真实卷只剩「行存不存在」一个信息，而这个信息 `enabled_prac` 一个列就能表达，还能查、能审计（§3.2.7）。

**代价**：放弃"可直达但不上列表"的两级语义，实测从未使用。

### 9.7b 上下架用正向布尔 + 双场景列，不用 `deleted_*`

最终落库的形态是 `enabled_prac` / `enabled_exam` 两列 `tinyint NOT NULL DEFAULT 1`，而不是一个 `deleted_prac`。

**为什么不用 `deleted_*`**：负数语义（"删了 = 下架"）要读的人在心里做一次反转，且同样的信息运营得用 `WHERE deleted_prac <> 0` 反查"下架了哪些"。正列直接 `WHERE enabled_prac = 0`，SQL 和字段名说的是同一件事；`tinyint` 也把值域压到 0/1，不会再出现历史上那种 `deleted = 2` 的意外值。

**为什么要两列而不是一列**：练习和考试对同一份内容的需求不同步——某题有争议，可能只关考试、仍允许练习；某题已被练烂，可能只关练习、留给考试。一列 `enabled` 表达不了这种组合，硬塞一个 `enabled_prac` 又会让考试侧去读一个名字里带 prac 的字段，语义混乱。两列各自归属一侧，边界清楚（R12b）。

**代价是纪律**：两列并存意味着任何一侧都可能误读另一侧。练习侧全量 grep `enabled_exam` 必须零命中（B-20），这个靠 Code Review 卡点，不靠类型系统。

### 9.8 口语内容统一读 `speaking_exam_paper`（2.0 / 3.0 都是）

一度以为 3.0 口语应该在 `exam_paper` + `SEC_SPEAKING` 里。实测推翻：

| 事实 | TEST | PROD |
|---|---|---|
| `speaking_exam_paper` 3.0 卷 | 5 张（L3/L4/L5/L6/L7-9），78 题 | 0 张（3.0 未放开） |
| `speaking_exam_paper` 2.0 卷 | 33 张，759 题 | 33 张，759 题 |
| `question` 里 `SEC_SPEAKING` | 5 题，1 张卷 | 同 |

`question` 里那 5 题所在的 `paper_id` 在 `exam_paper` 是 L7 的一张卷，与 `speaking_exam_paper` 的 5 张口语卷**毫无关系**——它是造数残留。代码侧 4 处常量全部是 `SEC_SPEAK`，`SEC_SPEAKING` 从未被引用。

因此：口语不分版本，统一读 `speaking_exam_paper` / `_question`，`section_mapping` 用 `SEC_SPEAK`（2.0 部分号来自配置的 `PART_1/2/3` → `1/2/3`）。`SEC_SPEAKING` 的配置行（TEST 1 行模块 + 3 行板块）与 `question` 里 5 条造数一并清掉。

---

## 10. 落地分期

| 期 | 范围 | 前置 | 完成判据 |
|---|---|---|---|
| **P0-a** | 修三条存量缺陷（附录 A：B-01/B-02/B-03） | — | TEST 听力 intro 不 500；PROD 听力列表不混版；HSK7-9 写作可开练 |
| **P0-b** | 四个支撑类：`PracticeVersion` / `PracticeLevelCode` / `PracticeModuleCatalog` / `PracticeTypeRegistry`（题型字典 `typeCode → answerMode`） | — | 单测覆盖 `HSK7-9`、`'7-9'`、非法版本、5 种 `answerMode` |
| **P0-c** | 16 个目录端点加 `version` | P0-b | 2.0 全链路零回归 |
| **P0-c2** | **`practice_module_part_config` 收尾**：TEST 已建表迁数据（132 行）+ 已补 `enabled` 列 → 补唯一键（`answer_mode` 不入库走字典、开关读 `enabled` 而非 `deleted`）→ 清 `SEC_SPEAKING` 残留配置 | P0-b | 表含 `uk_module_part`；132 行 `enabled` 全 1；`type_code` 全部能映射到 `answerMode`；关板块后目录不出现 |
| **P0-c3** | 板块开关接口 `PATCH /hsk/module-config/parts/{id}` | P0-c2 | 关板块后目录不出现，新练习不下发其题目，历史记录不受影响 |
| **P0-d** | 聚合接口 `GET /hsk/modules` | P0-c | 2.0 四卡 / 3.0 五卡，布局角标正确 |
| **P0-e** | **重写 `PracticeCatalogBatchLoader`**：从「查 structure + part_setting」改为「读板块配置 + 算题量」 | P0-c2 | 2.0 四模块目录与现网**逐字段一致** |
| **P0-f** | 翻译目录 4 + 写链路 6 + `validatePart` 放宽 | P0-e | 笔译/口译都能练到交卷；写作卷的 section 打翻译 → 400 |
| **P0-g** | **PROD 数据补全**：**5 张内容表加 `enabled_prac` + `enabled_exam`**（`DEFAULT 1`）**+ 同批把 16 张无 setting 行的活卷置 0**（§3.2.7 陷阱） → 28 行模块配置 → 15 行板块配置 → `layout` 回填 → level 收敛。3.0 正式放开时再把该版本 15 张卷改回 `enabled_prac = 1` | DDL 最先；五闸门 + DRY-RUN + 备份 | 目录卷数不变（2.0 每级 10 张、3.0 全 0）；5 表两组新列非空率 100%；3.0 放开后五卡有数据；`layout` 非空率 100%；板块配置 21/21 |
| **P0-h** | **作答表统一三元组**：`practice_record` 删 2 列 + 重建索引；`writing_attempt` / `speaking_attempt` 加两列 → 回填 → 校验 0 残留；7 处 Mapper 改三元组；接口改 `(paperId, section)`；CSCA 3 处改 `SEC_CSCA + 科目码` | P0-e | 抽 100 条历史记录新旧路径取题 ID 一致；`EXPLAIN` 走新索引；新记录 `question_ids` 非空且长度 = `total_questions`；回填校验 0 残留 |
| **P0-i** | **`practice_paper_setting` 退场**：删 `PracticeCatalogBatchLoader` 里的 setting 查询；`ReadingRecordServiceImpl` / `WritingAttemptServiceImpl` 的准入改判 `enabled_prac`；3 处 `getSortOrder()` 排序改 `id`；`SharedPaperEligibility` 补判 `enabled_prac`（B-17）；最后 `DROP TABLE practice_paper_setting` | P0-g 数据已铺好 | 4 模块目录与现网逐字段一致；下架卷在列表/详情/作答三处均不可达；表已 drop |
| **P0-j** | **结构表 drop**：确认代码中 `structureId` 出现次数 = 0 → `DROP TABLE practice_part_setting` → `DROP TABLE practice_paper_structure` | P0-h 回填校验通过 + P0-e 已换源 | 两表不存在；`grep -r structure_id` 源码零命中；全链路回归通过 |
| P1 | 偏好表加 `version`；ID 改 String；`dataVersion` ETag；角标后台可配；补 `TRANSLATION_WRITTEN` 策略；collation 对齐（D10 随表退场自动消失）；B-09 修正；板块级时长/满分/提示语加列 | P0 上线观察 | — |
| P2 | `option_pool` 三步退场（补 90 条 → `pool_code` 去 structureId → 快照现算）；口译 ASR + 自动评分 | P0-j 稳定 | — |

> 🔴 **最大风险点是 P0-e**：唯一会改变 2.0 现网行为的改造（目录换源）。验收法：同一批请求（4 模块 × 版本 × 等级），新旧响应 **JSON 逐字段 diff 必须为空**，建议先存旧实现快照。
>
> **结构表不能先 drop**：`practice_part_setting` / `practice_paper_structure` 必须等 P0-e（换源）+ P0-h（回填校验）都通过再删，否则回滚无路。删之前用 `SELECT COUNT(*) FROM 表` 留基线，`DROP` 前做全表导出备份。
>
> 顺序：**P0-a → P0-b → P0-c2 → P0-c → P0-c3 → P0-e → P0-f → P0-g → P0-h → P0-i → P0-j**。

---

## 附录 A：存量缺陷（本次顺带修）

| # | 缺陷 | 位置 | 症状 | 严重度 |
|---|---|---|---|---|
| B-01 | `selectOne` 未带 `version` | `ListeningCatalogServiceImpl#getIntro`、`#listParts` | 两版本同等级共存 → `TooManyResultsException` → 500（TEST 已触发） | 🔴 高 |
| B-02 | 卷查询无 `version` / `exam_type` 过滤 | `ListeningCatalogServiceImpl#getLevelOverview` | 混入 3 张 3.0 卷且 `totalCount=0`（PROD 已触发） | 🔴 高 |
| B-03 | 裸 `Integer.parseInt(paper.getLevel())` | `WritingAttemptServiceImpl#requirePaper`、`WritingCatalogServiceImpl#listParts`、`ReadingCatalogServiceImpl#paperResponse` | PROD 的 `'7-9'` → `NumberFormatException` → 500 | 🔴 高 |
| B-04 | `parseLevel` 只认 `HSK[1-6]` | `WritingCatalogServiceImpl#parseLevel` | `HSK7-9` → 404 | 🟡 中 |
| B-05 | `"HSK" + level` 拼 code | 阅读/写作/口语 Catalog、`getPreference` | 返回 `"HSK7"`，前端查不到 | 🟡 中 |
| B-06 | `levelCode` 裸 `parseInt` | `ReadingCatalogServiceImpl#requireModule`、`ListeningCatalogServiceImpl#parseLevel` | `HSK7-9` → 404/500 | 🟡 中 |
| B-07 | 目录 ID 为 `Long` | 各 Paper 响应 | 19 位雪花丢精度（新增端点改 String，存量 P1） | 🟡 中 |
| B-08 | `writing_evaluation_policy` 缺 3 个题型 | 表数据 | `TRANSLATION_WRITTEN` / `CHART_ANALYSIS` / `TOPIC_ESSAY` 交卷后报告永久「生成中」 | 🟡 中 |
| B-09 | `answer_mode` 与题型语义错配：写作类 `layout=input` 却标 `SINGLE`，而翻译标 `TEXT` | `practice_part_setting` 数据 | 3.0 作文按单选渲染 | 🟡 中（3.0 未上线） |
| B-10 | 3.0 口语在 `question`（5 条）与 `speaking_exam_paper`（5 张卷 78 题）双录，且 `question` 那条是造数残留 | 题库数据 | 若按 `question` 配料会读到 1 张假卷 → 口语目录近乎空 | 🟡 中（P0-c2 软删 5 条） |
| B-11 | `practice_paper_setting` 孤儿行：TEST 69（38 活跃 + 31 软删）/ PROD 56（全活跃），占全表 34% / 48% | 运营表数据 | 现网被 `IN` 天然过滤；**退场后自然消失，无需清理** | 🟢 低（已被 P0-i 覆盖） |
| B-12 | `practice_paper_setting` 三个开关在真实卷上零使用：`enabled=0` 的 2/5 行、`deleted=1` 的 31 行**全是孤儿行**，`visible` 全表为 1 | 运营表数据 | 这张表对真实卷只剩「行是否存在」；`sort_order` 也与 `id` 升序完全一致 → 由 `enabled_prac` 替代（§3.2.7） | 🟢 低（P0-i 退场） |
| B-13 | 共享选项池缺记录：`reading_cloze` TEST 90/690 无池记录、PROD 90/90 全无；`pool_code` 内嵌 `structureId` | `practice_question_option_pool` | 选词填空退化成每题重复渲染 6 个选项 | 🟡 中（P2 前置） |
| B-14 | `question.layout` PROD 缺失 47.7%（6469/13574），TEST 100% | `question` 数据 | 4 处代码依赖它渲染 → 近一半题交互错乱 | 🔴 高（P0-g 回填） |
| B-15 | 口语编码分裂：`SEC_SPEAK` 与 `SEC_SPEAKING` 并存（TEST 配置 `SEC_SPEAKING` 1 行模块 + 3 行板块，与 `SEC_SPEAK` L7 重复），代码 4 处只用 `SEC_SPEAK` | 配置数据 | 保留 `SEC_SPEAKING` 就是永久孤儿配置 | 🟡 中（P0-c2 删 4 行） |
| B-16 | PROD `HSK2.0 L2 SEC_LISTEN` 的 `total_question_count=35`，但四板块求和 40 | 配置数据 | 进度条分母口径不一 | 🟢 低（拆表时以实际计数为准） |
| B-17 | `SharedPaperEligibility.isEligible` 只判 `deleted` + `examType`，**不判 `enabledPrac`**；而 4 个 Catalog 已改为 `enabled_prac = 1` | 4 处调用（阅读/写作 Catalog、Record） | **口径已经分叉**：目录看不到下架卷，详情 / 开始作答却能进入 → 下架卷可直达。补一行 `&& enabledPrac == 1` 即修 | 🔴 高（P0-i 必改，建议提前到 P0-c 后立刻做） |
| B-18 | `practice_module_part_config` 只有 `PRIMARY (id)`，无唯一键 | TEST 实际表 | 同一 `(version, level, section_mapping, section)` 可重复插入 → 开关判定出现两行矛盾（一行 `enabled=1` 一行 `enabled=0`，取哪行决定板块开不开）。实测 132 行当前无重复，补键只防未来 | 🟡 中（P0-c2 补 `uk_module_part`） |
| B-20 | `enabled_prac` / `enabled_exam` 双开关在同一行并存，练习侧若误用 `AND enabled_exam = 1` 或 `OR` | 各 Mapper / Service | 运营为「只关考试」而下架的内容会连带从练习消失；反向漏判则已下架内容仍在练习出现 | 🟡 中（R12b 卡点 + Code Review grep `enabled_exam` 仅允许出现在考试服务） |
| B-19 | 口语取题靠 `PartCodeCase` 硬编码 8 个题型 → `PART_1/2/3`，`selectByPart` 的题型白名单同样只列这 8 个 | `SpeakingSourceQuestionMapper.xml` | 新配置里 6 个 `type_code` 不在白名单：3.0 L4/L5/L6 的 `listen_retell`、L7 的 `applied_read_speak` / `listen_material_answer` / `viewpoint_express` → **这些板块取题返回空**，用户看到"有题但点进去没题" | 🔴 高（P0-e 必改） |

> B-01 / B-02 / B-03 **不等本次改造上线就该修**：前两条现网已发生，第三条是 3.0 放开的必炸点。

---

## 附录 B：数据缺口（P0 阻塞项）

| # | 缺口 | TEST | PROD | 处置 |
|---|---|---|---|---|
| **D3** | `exam_paper.level` 的 7-9 取值不一致 | `"7"` | `"7-9"` | 代码用候选集 `IN ('7','7-9')`（R3） |
| **D4** | 3.0 的模块配置行 | 28 行 | **0 行** | 补 28 行 + 对应板块明细行 |
| **D11** | `enabled_prac` / `enabled_exam` 两列不存在 | **5 表已有**（`exam_paper`/`question`/`question_group`/`speaking_exam_paper`/`_question`） | **5 表全缺** | 上线前 DDL，**最先做**；`DEFAULT 1` 必须与「16 张无 setting 行活卷置 0」同一批次（§3.2.7） |
| **D13** | 3.0 卷全部未上架 | 15/15 | **0/15** | 迁移时随缺行规则置 `enabled_prac = 0`；3.0 正式放开的那一版改回 `1`（不是新增 setting 行） |
| **D14** | `question.layout` 大面积缺失 | 100% 有值 | **47.7% NULL** | 按 TEST 同题回填 |
| **D15** | 2.0 的板块配置只有听力有值 | 46/49 | **6/21**（阅读 6 / 写作 6 / 口语 3 行全 NULL） | 与 D4 同批，按题库 `question.section` 生成 |
| D5 | `writing_evaluation_policy` 无 `TRANSLATION_WRITTEN` | 缺 | 缺 | P0 不入队，直接 `UNAVAILABLE`；P1 补 |
| D6 | 翻译 4 题 `answer` 全为 `(略)` | 4/4 | 4/4 | 题库补参考译文（P1） |
| D8 | 3.0 卷数偏少 | 15 卷 | 15 卷 | 题库导入（已知） |
| D10 | ~~`practice_paper_structure` 的 collation 与其余表不一致~~ | 同 | 同 | **已关闭**：该表 P0 drop，collation 冲突随之消失；P0-e/P0-h 期间仍需跨表比较时用 `CONVERT ... COLLATE utf8mb4_0900_ai_ci` |
| ~~D12~~ | ~~`practice_paper_setting` 孤儿行~~ | ~~69~~ | ~~56~~ | **已关闭**：表 drop，孤儿行随之消失 |
| **D16** | `practice_module_part_config` 表 | **已建，132 行** | **不存在** | P0-g 建表（DDL 用 §3.2.2 完整形态，一次到位不重复 ALTER） |

> 遗留 P1：板块级时长 / 满分 / 提示语（同表加列即可）。

---

## 附录 C：关键实测基线（2026-11-10）

| 项 | TEST | PROD |
|---|---|---|
| `exam_paper`（`exam_type=1`）2.0 / 3.0 | 121 / 15 卷，全部 `deleted=0` | 122 / 15 卷，其中 **61 张 `deleted=1`**（全是 2.0，每级 10 张） |
| 活卷数（`deleted=0`） | 136 | **76** |
| 实际上架卷数（有 setting 行） | 136 | **60**（2.0 的 60 张；3.0 全 0） |
| `practice_paper_setting` 真实卷上的开关使用 | `enabled=0`/`visible=0`/`deleted=1` **均为 0**（非全开行全是孤儿行） | 同 |
| `setting.sort_order` == `id` 升序 | 13/13 组一致 | 6/6 组一致 |
| `practice_paper_setting` 孤儿行 | 69 / 205（34%） | 56 / 116（48%） |
| `practice_module_level_config` 2.0 / 3.0 | 21 / 28 行（**`parts_config` 列已删**） | 21 / **0** 行（`parts_config` 列仍在） |
| `practice_module_part_config` | **已建，132 行**；`enabled` 列已加（全 1）；无唯一键（B-18） | **表不存在**（D16） |
| `enabled_prac` / `enabled_exam`（5 张内容表） | **全有**，取值全 1（167 / 13624 / 1038 / 38 / 837 行） | **全缺**（D11），`deleted_prac` 也从未存在 |
| `parts_config` 非空行 / 元素总数 | 46/49、132 个（列已删，仅存档表可查） | 6/21、20 个 |
| `parts[].sortOrder` == `question.section` | 38/46 行（8 行是 2.0 口语） | 6/6（只有听力有值） |
| 三元组 ↔ `structure_id` 是否一对一 | 1201 / 1201，0 歧义 | 648 / 648，0 歧义 |
| `writing_attempt` / `speaking_attempt` 回填可行性 | 217/217、283/283 | 284/284、473/473 |
| `speaking_attempt.section_code` 编码 | `PART_1/2/3`（283 行全部） | 同（473 行全部） |
| 3.0 口语内容源 | `speaking_exam_paper` 5 卷 78 题 | 0 卷（未放开） |
| `total_question_count` == `SUM(parts)` | 46/46 | 5/6（L2 听力 35≠40） |
| `parts_config` 是否含 `section` / `typeCode` / `answerMode` | **均不含** | 同 |
| `enabled_prac` 列 | 5 表已有 | **5 表全缺** |
| `practice_paper_structure` 2.0 / 3.0 | 1066 / 135 行 | — / **0** 行 |
| 三表行数（structure / part_setting / level_config） | 1201 / 1201 / 49 | 1066 / — / 21 |
| `practice_record` / `practice_report` | 963 / 477 | 1364 / 1011 |
| 新旧取题路径等价性 | 905/907（1 条造数） | **1343/1343 零差异** |
| `question.layout` 填充率 | 100% | **52.3%** |
| `question_group` 覆盖板块 | 592 / 1180（50%） | — |
| `option_pool` / 覆盖题型 | 2505 行 / 6 种全覆盖 | 1150 行 / 5 种（`reading_cloze` 0） |
| 3.0 口语 | `exam_paper` 1 卷 5 题 + `speaking_exam_paper` 5 卷 | `exam_paper` 1 卷 5 题 / 后者 **0 卷** |
| 翻译题 | 4 题（笔译 2 + 口译 2，`answer='(略)'`） | 4 题（同） |
| `part_setting.section_code` = `question.section` | 1087/1087 | 480/480 |

> 复跑：`tmp/_probe_hsk_version.py`、`_probe_five_tables.py`、`_probe_paper_setting4.py`、`_probe_qgroup.py`、`_check_record_slim.py`（全部只读，带 `DATABASE()` / `@@hostname` 闸门）。
