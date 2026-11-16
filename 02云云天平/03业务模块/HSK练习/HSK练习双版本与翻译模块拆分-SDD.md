# HSK 练习双版本（2.0 / 3.0）与翻译模块拆分 · 软件设计文档

> 服务：`practice-service`（网关前缀 `/api/practice`）｜版本 v2.3｜2026-11-10｜状态：待评审
> 依据：2026-11-10 双版本首页 UI 截图 + 代码基线 + TEST 实测
> 前置：[首页设计方案](HSK练习模块首页-设计方案.md)、[翻译独立模块接口方案](HSK翻译练习-独立模块接口方案.md)、[共用题库方案](HSK练习-共用题库方案.md)（本文修正其中三处过时结论，见 §9.1）
>
> 🧭 **基线声明**：本文所有设计、字段、值域、验收**一律以 TEST 库为准**。生产库与 TEST 的差异（缺列 / 缺表 / 值域不同 / 数据缺失）**只在[附录 D](#附录-d生产与测试环境差异登记) 登记**，生产改造不写在本文档里、也不占 §10 分期。
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
| 2 | 新增首页模块卡接口 `GET /hsk/modules`，**纯展示**：只下发卡片顺序、布局与三语名，**不含可用性 / 卷数 / 进度**（角标/图标/主题色由前端按 `moduleCode` 内置，不下发；可用性与进度归 U1） |
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
   │     ├─ 模块配置：practice_module_level_config（模块开关 / 能力描述 / 时长 / 等级显示名 level_name ×3）
   │     ├─ 板块配置：practice_module_part_config（板块名三语 / 题型 / 板块开关）
   │     └─ 作答：practice_record / practice_answer / practice_report
   │              writing_* / speaking_*（翻译复用写作链路）
   ├─► ai-service        口语评测（翻译评分 P2）
   └─► system-service    口译录音上传（前端直传，本服务只存 URL）
```

无 Redis、无 Feign。

### 2.2 分层与子模块

| 层                         | 包                                              | 职责                                    | 本次改动       |
| ------------------------- | ---------------------------------------------- | ------------------------------------- | ---------- |
| Controller                | `{listen,read,write,speak,trans}/*/controller` | 解析 `version` / `level` / `userId` | 加参数；目录与报告 latest 收敛为新增的 `PracticeCatalogController`（U1–U3）/ `PracticeReportController`（CR） |
| Catalog Service           | `*/service/impl/*CatalogServiceImpl`           | 等级 / 卷 / 板块目录 + 进度聚合                  | 版本化 + 换配置源 |
| Attempt / Answer / Submit | `writing/*`、各模块 `*ServiceImpl`                 | 作答、保存、交卷、报告                           | 仅准入校验      |
| Domain Support            | `core/support`                                 | 值对象、模块注册表、目录装载                        | 新增 4 个类    |
| Mapper                    | `core/mapper` + XML                            | 数据访问                                  | 少量 SQL 加条件 |

子模块：版本上下文、模块注册表、首页聚合、听力/阅读/写作/口语目录、**翻译目录（新）**、**翻译写链路（新，薄封装）**。

### 2.3 四条设计原则

1. **版本上下文只作用在目录层。** 作答链路拿 `(paperId, section_mapping, section)`，版本已被三者唯一确定 → `attempt/answer/submit/report` 不加 `version`。2026-11-11 目录端点进一步**合并为统一端点**（接口设计文档 v1.3+，决策 16–19）：目录 15 → 3（**U1–U3**，`module` 全部改 query 且必填——综合卷同一 `paperId` 下多模块板块并存，`paperId` 反查模块不成立，`paperId` 只判卷域）、板块最近报告 4 → 1（**CR**，`module` + `section` 均 query）、删 4 个 `/papers` 与 6 个偏好端点、运营配置端点（D 组）移出本期。**CR 的 `data` 统一「通用报告块 + 模块扩展块」**（决策 20）：**五个模块**（含翻译）共用同一个报告页（正确率 / 答题时间 / 答对情况 / 答题卡「只看错题」），模块专属字段收进 `writing` / `speaking` / `reading` / `translation` 扩展对象。
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
| 配置  | `practice_module_level_config`                       | 版本 × 等级 × 模块：模块开关、标准总题量、时长、能力描述三语、**等级显示名 `level_name`（= 接口 `levelName` 唯一真源）**                    | ✅     |
| 配置  | **`practice_module_part_config`**                    | 版本 × 等级 × 模块 × **板块**：名三语、题型编码、标准题量、**板块开关 `enabled`**、`deleted` 逻辑删除（**不含 `answerMode`**，答题形式逐题读 `question.layout`，§3.2.2b） | ✅     |
| 作答  | `practice_record` / `practice_report` / `writing_*` / `speaking_*` | 练习记录，统一用 `(paper_id, section_mapping, section)` 定位 | 只引用上层 |
| 退场  | `practice_paper_structure` / `practice_part_setting` / `practice_paper_setting` | 三张表 **P0 直接 drop**，不保留 ID 注册表（§3.2.6 / §3.2.7） | —     |

> **一句话**：`question` 去重出「有哪些板块」，`part_config` 给「板块叫什么、能不能练」，`exam_paper.enabled_prac` 给「哪些卷能练」，`level_config` 给「哪些模块开放」。中间那三张表都没有独有信息。

#### 3.1.4 业务规则（落进代码的 15 条）

| #    | 规则                                                                                                                              | 落点                              |
| ---- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| R1   | `version` 只有两个合法值，缺省 2.0，非法 → 400                                                                                               | `PracticeVersion.of`            |
| R2   | `HSK7-9` 是一个等级，数值 `7`；禁止裸 `parseInt(level)`                                                                                 | `PracticeLevelCode`             |
| R3   | `exam_paper.level` 两库取值不一致（TEST `"7"` / PROD `"7-9"`，差异 E11），查询必须 `IN (候选集)`，禁止 `eq("7")`                                                    | `PracticeLevelCode.dbLevels`    |
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
| `exam_paper` | 167（活 136） | ✅ TEST 已改 | `version` 管版本、`level` 管等级、**`enabled_prac` 管练习侧上下架**、`enabled_exam` 管考试侧（练习不读） |
| `question` | 13624 | ✅ TEST 已改 | `section_mapping` 定模块、`section` 定部分号、`type_id_mapping` 定题型；`enabled_prac` 为**题级上下架** |
| `question_group` | 1038 | ✅ TEST 已改 | 翻译两个大题组已在；不参与结构装配。带 `enabled_prac` 但练习侧不单独判（材料随题走） |
| `speaking_exam_paper` / `_question` | 38 / 837 | ✅ TEST 已改 | **2.0 与 3.0 口语内容都在这两张表**（R5）；两表各有 `enabled_prac` |
| `practice_module_level_config` | 49 | ✅ 保留，删 `parts_config` 列（TEST 已删）、**加 `level_name` / `_en` / `_vi` 三列（TEST 已有，2026-11-11）** | 模块级配置；`level_name` ×3（zh `HSK1`…`HSK7-9` + 口语 2.0 `HSKK 初级/中级/高级`；en `HSKK Beginner/Intermediate/Advanced`；vi `HSKK Sơ cấp/Trung cấp/Cao cấp`；`HSK*` 三语同值）是接口 `levelName` **唯一真源**，行粒度「版本 × 等级 × 模块」 |
| **`practice_module_part_config`** | **132** | ✅ TEST 已建 + **已补 `enabled` 列**；仍缺唯一键 | 板块级配置；**开关用 `enabled`（0关/1开），`deleted` 回到纯逻辑删除**（§3.2.2） |
| `hsk_level_config` | 13 | ⛔ **练习侧不使用**（HSK **考试侧**表，归 exam-service 的 `HskLevelConfig`） | 用户口径（2026-11-11）：练习侧**不碰**这张表。`practice-service` 里那份 `PracticeLevelConfig` + `PracticeLevelConfigMapper` 是跨域复制的只读映射，只为取 `levelName`（`一级` / `Level 1` / `Cấp 1`），现由 `practice_module_level_config.level_name` 取代 → **两个文件应删**，阅读 / 写作 Catalog 里那两次 `levelMapper.selectOne` 一并去掉。⚠️ 两个 `level_name` 同名不同义，不可互换 |
| `practice_paper_setting` | 206 / 116 | ❌ **P0 drop** | 卷级上下架由 `exam_paper.enabled_prac` 完整替代（§3.2.7） |
| `practice_paper_structure` | 1290 | ❌ **P0 drop** | 无独有信息：板块来自 `question` 去重 + `part_config` 取名（§3.2.6） |
| `practice_part_setting` | 1294 | ❌ **P0 drop** | 与 structure 1:1，题型编码已进 `part_config`；作答模式改由字典映射 |
| `practice_record` | 889 | ⚠️ 瘦身：删 `structure_id` + `practice_name`，启用 `question_ids` | §3.2.5 |
| `practice_report` | 477 | ⚠️ 瘦身：删 `structure_id` | 有 `practice_record_id` 可回溯 |
| `writing_attempt` / `speaking_attempt` | 217 / 283 | ⚠️ **加两列 → 回填 → 删 `structure_id`** | §3.2.6 |
| `practice_question_option_pool` | 2347 | ⏳ P2 退场（先加两列，再改 `pool_code`） | 数据可推但自身不完整（§3.2.6） |

> 一句话：**本次之后，库里不存在任何一张「结构表」，也不再存在 `structure_id` 这个字段。** 板块的「有哪些」由 `question` 去重得出，「叫什么、开不开」由 `practice_module_part_config` 给出。
>
> 📌 **本文档一律以 TEST 库为唯一基线**。生产库当前与 TEST 存在若干结构和数据差异，**只登记不展开**，集中在[附录 D](#附录-d生产与测试环境差异登记)，生产侧改造另行安排、不占本文档分期。凡出现「PROD」字样，均指「差异参照值」，不是要执行的方案。

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
| 作答模式 `answer_mode` | 无此列 | **不加列，也不做字典**：答题形式直接读 `question.layout`（逐题、已落库，§3.2.2b） |
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

#### 3.2.2b 答题形式读 `question.layout`，不做 `type_code` 字典

**结论**：`answer_mode` 既不进 `part_config`，也不该用 `type_code` 现场映射。答题形式只认 `question.layout`。

**为什么不能用 `type_code` 映射**（实测，2026-11-10）：

| 环境 | `type_id_mapping` | 对应 `layout` 种类 |
|---|---|---|
| PROD | `listening_single` | **4 种**（`imageChoice` / `passageGroup` / `textChoice` / `textChoice_shareAudio`） |
| PROD | `listening_detail_choice` | **4 种** |
| TEST | `SINGLE` | 3 种 |
| TEST | `example_question` | 6 种 |

同一个题型编码在真实数据里横跨多种交互形态，字典一映射就会把「看图选择」渲成「篇章组」。而 `layout` 是**题目行自己的值**，天然准确。

**TEST 的规范化值域（7 个，纯交互形态，非空率 100%）**

| `layout` | 交互 | 出现在 |
|---|---|---|
| `choice` | 单选，点一个选项 | 听 / 读（7377 题） |
| `choiceGrid` | 网格选择（多选 / 匹配） | 听 / 读 / 写（1935 题） |
| `judge` | 对错判断 | 听 / 读（1150 题） |
| `order` | 排序（拖词卡 / 排句子） | 读 / 写（749 题） |
| `input` | 长文本输入 | 写 / 译（246 题） |
| `shortInput` | 短文本输入（填空） | 写（156 题） |
| `record` | 录音 | 说 / 译（7 题） |

> 统计口径：TEST `question` 中 `section_mapping` 非空的 11620 行。另有 1904 行 `section_mapping IS NULL` + `layout='textChoice'`（老值，涉及 31 张未纳入练习的卷），本期不处理。

**环境差异（仅登记；代码一律按 TEST 值实现）**

| 项 | TEST（基线） | PROD（差异参照） |
|---|---|---|
| 非空率 | 100%（13524） | **52.3%**（7105/13574） |
| 值域 | 上表 7 个 | 老值域 8 个：`textChoice` / `textChoice_shareAudio` / `passageGroup` / `textJudge` / `imageMatch` / `imageJudge` / `imageChoice` / `clozeGroup` |
| 缺失分布 | 无 | `SEC_READ` **100% NULL（5108）**、`SEC_WRITE` **100% NULL（927）**、`SEC_TRANSLATION` 4、`SEC_SPEAKING` 5；只有 `SEC_LISTEN` 有值，且是老值 |

老值域混了**题面形态**（`passageGroup` / `clozeGroup` 是「材料 + 一组小题」，不是答题形式），所以生产侧那半球值即使非空也不能直接当答题形式用。

> 差异已登记为附录 D 的 **E6 / E7**（含「生产侧只能按 `question.id` 从 TEST 复制、禁止按值映射」的口径）。**本文档不承接生产数据整改**，生产对齐另行安排。

**口语是例外**：口语内容在 `speaking_exam_paper_question`，**该表没有 `layout` 列**（`question` 里 `SEC_SPEAK` 的 5 条是造数残留）。所以口语 P0 直接按模块定 `record`；要做「朗读 / 自由说话」差异化录音 UI 再补列（P1）。

**下发放哪一层**：

| 层 | 字段 | 说明 |
|---|---|---|
| 题目接口 | `layout`（单值） | 原样透传，前端据此选渲染组件 |
| 板块接口 | `layouts`（去重数组） | 该板块内实际题目的 `layout` 集合。正常 1 个元素；2 个说明混了交互（TEST 2 个板块 / PROD 48 个） |

**不做 enum 换算**：沿用 CSCA 既有约定（`CscaQuestionResponse` 注释：「取哪个字段只由 `layout` 决定，不能按『字段是否为空』猜形态」）。少一层换算就少一处漏配——写作 `WritingLayoutType` 的 switch 白名单只覆盖 5 个老题型，3.0 的 `chart_analysis` / `topic_essay` 直接落 default（B-04），就是现成教训。


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

-- ④ 每卷每板块实际题量 + 答题形式（按卷批量，勿逐卷查；题级上下架在这里生效）
SELECT paper_id, section_mapping, CAST(section AS SIGNED) AS section_no,
       COUNT(*) AS actual_count,
       GROUP_CONCAT(DISTINCT layout ORDER BY layout) AS layouts   -- → parts[].layouts 数组
FROM question
WHERE deleted = 0 AND enabled_prac = 1 AND paper_id IN (...)
  AND (type_id_mapping IS NULL OR type_id_mapping <> 'example_question')
  AND section IS NOT NULL AND section <> ''
GROUP BY paper_id, section_mapping, section;
```

> `layouts` 直接 `GROUP_CONCAT` 出来，不需要额外查询——④ 本来就要扫这批行。`NULL` 的 `layout` 会被 `GROUP_CONCAT` 自动跳过；若某板块全为 NULL 则返回 `NULL`，服务端兜底为空数组并记 `WARN`（生产未对齐时会大量命中，差异 E6 / D14）。

装配顺序（服务端内存）：
1. 把 ② 的结果分两拨：`enabled = 1 AND deleted = 0` → 骨架（按 `sort_order` 排序）；`enabled = 0 AND deleted = 0` → `closedSections` 集合；`deleted = 1` 的行直接丢；
2. 只有「既不在骨架、也不在 `closedSections`」的 `section` 才按 R14 兜底（`第{section}部分`，视为开放）；
3. 用 ④ 的 `actual_count` **覆盖** `standard_question_count`（④ 已排除 `enabled_prac = 0` 的单题，所以单题下架会自动缩小题量）；
4. `actual_count = 0` 的板块不下发（R6）——**这一条同时兜住了「板块开着但题全被单题下架」**；
5. 模块 `enabled = 0` → 整模块不下发，**不再求值板块**；
6. 板块在 `closedSections` 里 → 该板块不下发，历史记录不受影响（R13）；
7. `answerMode` **不再下发**：板块级给 `layouts`（④ 的去重结果），题目级给单值 `layout`，均原样透传（§3.2.2b）。

**口语是唯一走另一张内容表的模块**：②③④ 换成 `speaking_exam_paper`（`enabled_prac = 1`）+ `speaking_exam_paper_question`（`enabled_prac = 1`）的计数，板块骨架仍来自 `practice_module_part_config`（`section_mapping = 'SEC_SPEAK'`，`section` 为 1/2/3）。

🔴 **取题必须由配置驱动，不能再靠硬编码题型白名单**：现在 `SpeakingSourceQuestionMapper.xml` 用 `PartCodeCase` 把 8 个题型硬编码映射到 `PART_1/2/3`，而新配置里已有 6 个 `type_code` 不在其中（3.0 L4/L5/L6 的 `listen_retell`、L7 的 `applied_read_speak` / `listen_material_answer` / `viewpoint_express`），`selectByPart` 的 `question_type_mapping IN (...)` 白名单同样漏掉它们 → **这些板块目前取不到任何题**（缺陷 B-19）。

✅ **2026-11-11 已从根本上解除**：`speaking_exam_paper_question` **新增 `section` 列**（`varchar(50)`，数字 `1`/`2`/`3`；`0` = `opening_music` / `confirm_name` / `confirm_nationality` / `number_confirmation` 这 4 类前导流程题，每卷各 1 条、不属任何板块）。实测 TEST：**37 张有题的卷 `section` 集合都是 `{1,2,3}`**，与 `practice_part_setting` 的 `PART_1/PART_2/PART_3` 逐卷一一对应（38 张卷共 114 行 `PART_N`，多出的 1 张有配置无题）。

故取题改成按 `section` 直接过滤，**不再按业务题型做白名单**——新增题型只要落在某个部分里就能取到：

```sql
WHERE paper_id = ? AND deleted = 0 AND enabled_prac = 1 AND number > 0
  AND section = ?           -- 板块号，数字；PART_ 与业务 type_code 都不再参与取题
  AND question_type_mapping NOT IN ('instructions', 'outline')  -- 保险起见，见下
```

⚠️ **两个边界要分清**：
- 前导 4 类（`opening_music` / `confirm_name` / `confirm_nationality` / `number_confirmation`，`section='0'`，`number` 为 `-4..-1`）被 `section = ?`（1/2/3）天然排除；
- 夹在板块内的 `instructions`（1/2/3 部分各 37/37/19 行）与 `outline`（25/19 行）**`number` 恒为 0**（TEST 实测），本来就已被 `number > 0` 排掉，所以最后一行只是**零成本保险**，不是必须；它的清单固定为这两个词，**不是业务题型白名单**，新题型不受影响。

同理，`PartCodeCase`（`PART_1/2/3` 硬编码映射）整段可以删掉。

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
| `POST /listening/records/start {paperId, structureId}` | `{paperId, sectionMapping, section}`（决策 23 三字段必填） |
| `GET /listening/parts/{structureId}/reports/latest` | `GET /papers/{paperId}/reports/latest?module=listening&section=`（**CR 统一端点**，不带模块前缀，板块号走 query） |
| `POST /reading/records/start {paperId, structureId}` | `{paperId, sectionMapping, section}`（决策 23 三字段必填） |
| `GET /reading/parts/{structureId}/reports/latest` | 同上（CR，`?module=reading&section=`） |

前端改拿目录响应里的 `partCode`（= `section`）+ 卷 `id`。**目录响应不再下发 `structureId`**——它随结构表一起消失，不留 deprecated 字段，避免前端继续依赖。

> 🔴 **五模块答题流程全链路流转**（2026-11-11，接口设计文档 **§4.6** + 决策 21/23，只登记不改端点）：E1 → U1 → U2 → U3 → start（幂等，请求体统一 `{paperId, sectionMapping, section}` 三字段必填——综合卷同号共存，只传 `{paperId, section}` 推不出唯一板块）→ questions（逐题 `layout`，按 `question_ids` 快照）→ answers → pause/会话心跳（随模块）→ submit（`Idempotency-Key` 必填）→ 报告（统一入口 CR；写/说/译异步轮询）。**作答主键五模块统一 `recordId`**（听/读 = `practice_record`，写/译 = `practice_writing_record`，说 = `practice_speaking_record`）；写/译/说**链路以听/读为模板**，路径统一 `/{mod}/records/...`（决策 23，旧 `attempts` 路径 404）；**翻译交卷是 `/submissions`，写作是 `/submit`，不同名**。听/读作答端点沿用既有路径（不在 §3.1 保留端点清单内）。

> 🔴 **attempt 表已退场（2026-11-16，决策 23）**：`writing_attempt` → **`practice_writing_record`**、`speaking_attempt` → **`practice_speaking_record`**（实体 `WritingAttempt` / `SpeakingAttempt` 已映射新表名）。本 SDD 中 §3.2.6 等处的 `writing_attempt` / `speaking_attempt` 为**当时实测的历史实录**，读到时一律按新表名理解；后续迁移脚本执行前需把目标表名替换为新名。

> 🔴 **五模块「取题 / 存储 / 出结果」口径 + 全流程端点明细**（2026-11-16，接口设计文档 **§4.7** + 决策 22）：取题统一三元组 + `question.enabled_prac=1`（口语双源：`question` 或 `speaking_exam_paper_question.enabled_prac=1`，板块域常量 `SEC_SPEAK`）；快照（题目/题组/选项/音频）**提交时冻结**（G2，与现状一致零改造）；听/读交卷即判（逐题比对 `answer` vs `question.answer`、未作答记错、错题数 = 总题数 − 答对数、统计写回记录）；写/译/说按 **`question.has_standard_answer`** 分流（1=交卷即出、0=AI）——⚠️ **该列当前不存在，需新增 + 回填**，落地前判分分流仍以 `type_id` 兜底（铁律 #3），此为新缺口需登记；`idempotency_key` 统一 `{module}-{recordId}-submit`（现状听/读多 `-1` 后缀、写作取客户端头、说/译未落库，均要改）；翻译 P0「恒 UNAVAILABLE」口径随 has_standard_answer 分流作废，CR 翻译填充规则需重写。

> 🔴 **报告表退场 + 会话/暂停端点退场（2026-11-16，决策 24）**：实测报告表已全部退场（`SHOW TABLES LIKE '%report%'` 为空），库里只剩 record 表和 answer 表——**报告 = record + answer 现拼，`reportId` 概念取消**：① 报告详情端点对齐听/读改 `GET /{mod}/records/{recordId}/report`（写/说/B10 同批，旧 `/reports/{reportId}` 路径 404）；② **AI 评分状态 = `practice_writing_answer` / `practice_speaking_answer` 的 `grading_state` 列（已存在，零 DDL）**：`0` = AI 评分中（`reportStatus=GRADING`）、`1` = 评完（`READY`，`points` / `analysis` 就绪）；`has_standard_answer=1` 交卷即出，不影响该状态；③ CR 通用块 `recordId` 五模块全有、`durationSeconds` 一律 = record 表 `end_time − start_time`；④ **写作/口语的 sessions 心跳三端点与 pause 端点注释掉**（练习是倒计时制；听/读既有端点暂不动）；⑤ CR 写/说/译扩展块数据源改 record 统计列（`objective_count` / `objective_correct_count` / `ai_question_count` / `ai_scored_count` / `final_score` / `total_score`），原 C3/C4 形状与 D5「恒 UNAVAILABLE」口径作废。

> 🟡 **五模块各新增答题卡 + 标记接口（2026-11-16，决策 25；二次修订收窄为「作答中答题卡」，三次修订拆开标记与收藏）**：`GET /{mod}/records/{recordId}/answer-card`（听/读/写/说/译同构），响应 `{recordId, paperId, section, totalQuestions, answeredCount, unansweredCount, tagCount, currentQuestionNumber, questions[]}`，`questions[]` 按 `question_ids` 快照顺序逐题 `{order, questionId, answered, isTag, favorite, current}`。🔴 **不下发 `correct`**（CSCA `CscaAnswerCardDTO` 同一原则：答题卡只管答没答/标没标/收没收藏，对错只在交卷后报告出现）。🔴 **标记 ≠ 收藏**：① `isTag` = **标记**（`0`/`1`，落 `*_answer.is_tag`，**本场作答内有效、不跨场次、不影响判分**，与 CSCA `exam_answer.is_tag` 同义）——该列练习侧当前不存在，需 **DDL 加列**，并配标记端点 `PUT /{mod}/records/{recordId}/questions/{questionId}/tag` `{isTag}`（返回 `{questionId, isTag, tagCount}`，未作答题也可标记，`PUT` 幂等）；② `favorite` = **收藏**（用户 × 题目、**跨场次长期有效**、软删复活，独立表 `practice_question_favorite`，`csca_question_favorite` 属考试域不可复用）——**后续版本接入，本期恒 `false`**。`answered` 数据源 = `practice_answer.answered`（口语 = `practice_speaking_answer` 有无记录）。**作答中答题卡用本接口、报告页对错用 CR `answerCard[]`，两处题序同源**（接口设计文档 §4.6.1 约定 8 + §4.7.0 G9/G9b）。

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
| 各 Controller / DTO 的 `structureId` 入参出参 | 改 `paperId + sectionMapping + section`（§3.2.5 接口表 + 接口文档决策 23） |
| `ListeningReportController` / `ReadingReportController` | latest 端点摘除，并入 **CR** `GET /papers/{paperId}/reports/latest?module=&section=`（`module` 必填并决定模块，`section` 必填选板块，`paperId` 只判卷域；委托原查询逻辑，见接口设计文档 §4.3 `PracticeReportController`） |

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

##### 列定义（唯一口径）

```sql
-- TEST 现状即口径：5 张内容表（exam_paper / question / question_group /
-- speaking_exam_paper / speaking_exam_paper_question）列定义逐字一致
ALTER TABLE exam_paper
  ADD COLUMN enabled_prac tinyint NOT NULL DEFAULT '1' COMMENT '练习是否启用：0否，1是',
  ADD COLUMN enabled_exam tinyint NOT NULL DEFAULT '1' COMMENT '考试是否启用：0否，1是';
```

- **TEST 实测已就绪**：5 张表都有这两列，取值 `167 / 13624 / 1038 / 38 / 837` 行**全为 1**（全部上架），无历史数据要修。
- ⚠️ **记住方向陷阱（属验收条件，不是本期动作）**：`enabled_prac` 是**正向布尔**，`DEFAULT '1'` 的语义是「加列即全部上架」。任何环境加列时，必须同批把「本该下架」的卷置 0，否则目录卷数会凭空上涨（早期用 `deleted_prac DEFAULT '0'` 时是同一陷阱的反方向）。生产侧这 16 张已登记为附录 D **E9**，本文档不执行。
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

**等级入参命名**：请求侧（query / path / body）统一叫 **`level`**，**取数字串**（`"1"`–`"6"`、`"7"`= HSK7-9 整级），弃用 `levelCode`；响应侧同样用 `level`（回显同一数字串）+ **`levelName`**（显示名，**取 `practice_module_level_config.level_name` / `_en` / `_vi` 三列，按 `Accept-Language` 三选一，空值回落中文**，不拼接不换算，见 E17）。`levelCode` / `databaseLevel` 全部废弃。路径并入统一端点 **U2** `GET /hsk/levels/{level}/intro?module=`，**取值从 `HSK1` 变成 `1`**（URL 形态变化，属破坏性变更）。

> `"7"` 落到 DB 时是 `exam_paper.level IN ('7','7-9')` 候选集（R3）——TEST 存 `'7'`、PROD 存 `'7-9'`，接口层只认 `"7"`，换算收口在 `PracticeLevelCode`。

#### 3.3.2 存量端点改造（2026-11-11 合并为 U1–U3 + CR）

> 🔴 **2026-11-11 大合并**（接口设计文档 v1.3+，决策 16–17）：目录端点 15 → **3 个统一端点 U1–U3**、板块最近报告 4 → **1 个 CR**。`module` 不再是路径段（改 query 且**必填**——综合卷同一 `paperId` 下听/读/写板块并存，反查不成立；`paperId` 只判卷域，`exam_paper` 与 `speaking_exam_paper` id 域零交集）。下表逐条列出的 `/{mod}/...` 旧路径**全部 404**，「改造」列描述的是该行为在 U1–U3 / CR 中的实现要点。

| # | 方法 | 旧路径（已 404） | 现状 | 改造（落入统一端点） |
|---|---|---|---|---|
| 1 | GET | `/listening/levels` → **U1** | 无 `version`、无 `exam_type` 过滤 | 加 `version`、补 `exam_type=1`、走资格判定；**补 `levelName`** |
| 2 | GET | `/listening/levels/{level}/intro` → **U2** | `selectOne` 不带 version → 两版本同等级共存时抛 `TooManyResults` | `selectOne` 带 `version` + `deleted=0`；补 `level`/`levelName` |
| 3 | GET | `/listening/papers/{paperId}/parts` → **U3** | 配置查询无 version | 同 2；板块来源改配置表 + 题量现算；进度收敛为 `draft`/`report`/`stats` |
| 4 | GET | `/reading/levels` → **U1** | `VERSION` 常量；**返全部等级数组** | 常量改参数；**改单等级概览 + 内嵌 `papers[]`** |
| 5 | GET | `/reading/levels/{code}/intro` → **U2** | 常量 + 裸 `parseInt` → `HSK7-9` 必 404 | 改 `PracticeLevelCode`；`sections` → `parts`、三语、`durationMinutes` |
| ~~6~~ | ~~GET~~ | ~~`/reading/papers`~~ | 常量 + `eq(level, "7")` 匹配不到 PROD 的 `"7-9"` | **删除**，并入 U1 的 `papers[]`（`level IN (dbLevels)` 的口径随迁） |
| 7 | GET | `/reading/papers/{paperId}/parts` → **U3** | 无版本校验 | 卷 `version` 与入参不符 → 404；外层改对象包裹 |
| ~~8~~ | ~~GET~~ | ~~`/reading/preferences`~~ | 后端零内部依赖，仅前端手动读写 | **删除（2026-11-11 拍板）**：连同写作 / 口语同款共 6 个偏好端点一并下线；实体 `PracticeUserPreference` + mapper 已删，库表保留不 drop。「上次练到哪」由前端本地保存或由 `practice_record` 推导 |
| ~~9~~ | ~~PUT~~ | ~~`/reading/preferences/level`~~ | 同上 | **删除（2026-11-11 拍板）**，同 8 |
| 10 | GET | `/writing/levels` → **U1** | 常量；`introSections` 的 switch 只到 6 | 常量改参数；**改单等级概览 + 内嵌 `papers[]`**；补 `7` 分支 |
| 11 | GET | `/writing/levels/{code}/intro` → **U2** | 常量；`parseLevel` 正则只到 `HSK[1-6]` | 数字串校验；`sections` → `parts`、三语 |
| ~~12~~ | ~~GET~~ | ~~`/writing/papers`~~ | 常量 | **删除**，并入 U1 的 `papers[]` |
| 13 | GET | `/writing/papers/{paperId}/parts` → **U3** | `Integer.parseInt(paper.getLevel())` → `"7-9"` 抛 500 | 改 `PracticeLevelCode.parseDbLevel`；进度收敛 |
| 14 | GET | `/speaking/levels` → **U1** | 常量 + `SEC_SPEAK` 单映射；**返数组** | 常量改参数；**改单等级概览 + 内嵌 `papers[]`**；2.0 的 `level` 为 `"1"`–`"3"` |
| 14b | GET | `/speaking/levels/{level}/intro` → **U2** | 文档此前未登记（实现已有） | 补登记；`sections` → `parts`、三语 |
| ~~15~~ | ~~GET~~ | ~~`/speaking/papers`~~ | 常量 | **删除**，并入 U1 的 `papers[]` |
| 16 | GET | `/speaking/papers/{paperId}/parts` → **U3** | 常量 + `SEC_SPEAK` 单映射 | **2.0 / 3.0 都读 `speaking_exam_paper`**（R5）；来源改 `practice_module_part_config`；口语计数进 `stats` |

报告侧同批合并：原 C1–C4 四条 `/{mod}/papers/{paperId}/parts/{section}/reports/latest` → **CR `GET /papers/{paperId}/reports/latest?module=&section=`**（不带模块前缀，模块与板块号都走 query（`module`=`listening`/`reading`/`writing`/`speaking`），响应回显 `module` 判别字段；`section` 各模块统一数字）。

🔴 **CR 的 `data` 统一「通用报告块 + 模块扩展块」（决策 20，2026-11-11）**：通用学习报告页**五个模块**（听/读/写/说/译）**共用一页**（正确率 / 答题时间 `HH:MM:SS` / 答对情况 `3/5` / 答题卡逐题对错 + 「只看错题」），因此不再保留四套 `data` 形状：

- **通用块（字段名五模块一致）**：`module` / `recordId`（🔴 决策 24：**五模块全有**——听/读 = `practice_record.id`、写/译 = `practice_writing_record.id`、说 = `practice_speaking_record.id`；`reportId` 已随报告表退场）/ `paperId` / `section` / `reportStatus`（🔴 决策 24：`READY` / `GRADING` / `FAILED`，写/译/说按 `grading_state`：0=`GRADING`、1=`READY`）/ `submittedTime` / `generatedTime` / `durationSeconds`（🔴 决策 24：一律 = record 表 `end_time − start_time`）/ `totalQuestions` / `answeredCount` / `correctCount` / `wrongCount` / `accuracyRate` / `answerCard[]`（逐题 `{order, correct}`，`correct` 三态：`true` 绿 / `false` 红 / `null` 置灰；「只看错题」前端按 `correct === false` 自滤）
- **`answerCard[]` 构造**：拿各模块 record 表的 `question_ids`（交卷时固化的题目 ID 数组）放进数组——数组顺序即 `order`（下标 +1，与题目下发顺序一致），每题 `correct` 取交卷快照的 `is_correct`（HSK 不判分，以交卷前端传值为准），**不现查题库**（题库改版后历史报告仍可复现）
- **模块扩展块**（🔴 决策 24：数据源改 record + answer 表，原 C3/C4 报告表形状作废）：`reading`（`items[]`）/ `writing`（`gradingState` / `score`= `final_score` / `maxScore` / `objectiveCount` / `objectiveCorrectCount` / `aiQuestionCount` / `aiScoredCount`）/ `speaking`（同口径，`scoredCount` 随 `grading_state`）/ `translation`（**形状同 `writing`**）——只挂 `module` 对应那一个，其余恒 `null`；逐题 AI 反馈走 `GET /{mod}/records/{recordId}/report/questions/{q}`
- **翻译并入 CR**（2026-11-11）：原「先拿 reportId 再查 B10」两跳作废；🔴 决策 24 后 B10 详情端点改 `GET /translation/records/{recordId}/report`（`/translation/reports/{reportId}` 404）；`module=translation&section=1|2`，2.0 的卷查不到 `SEC_TRANSLATION` 板块 → **404**（不是 `data=null`，决策 9 翻译仅 3.0 有数据）
- **字段名归一是破坏性的**：阅读 `totalQuestionCount` → `totalQuestions`；口语 `status` → `reportStatus`；写/说原平铺字段收进扩展块（接口文档 §6.1 #14）
- **填充规则**：听/读全量填充（`is_correct` 以交卷前端传值为准）；写/译/说无客观判分 → 对错字段全 `null`，前端隐藏/置灰对应卡片，只留答题时间 + 扩展块

**统一后的目录模型：三跳（U1–U3）**

| 跳 | 统一端点 | 返回 |
|---|---|---|
| ① **U1** | `GET /hsk/levels?module=&version=&level=` | 单对象 `{module, level, levelName, paperCount, papers[]}` |
| ② **U2** | `GET /hsk/levels/{level}/intro?module=&version=` | 单对象 `{module, level, levelName, abilityDescription×3, totalQuestionCount, durationMinutes, parts[]}` |
| ③ **U3** | `GET /hsk/papers/{paperId}/parts?module=&version=` | 单对象 `{module, paperId, paperCode, parts[]}`（**`module` 必填**，决策 16b——只返回该模块的板块，`paperId` 只判卷域） |

五个模块（听/读/写/说/译）**共用同一套路径与结构**：`module` 是 query 参数（`listening` / `reading` / `writing` / `speaking` / `translation`）；板块数组统一叫 `parts`；时长统一 `durationMinutes`；卷状态统一小写 `not_started`/`in_progress`/`completed`；U3 的进度统一为「4 个通用字段 + `draft`/`report`/`stats` 三个扩展块」。U1–U3 与 CR 的响应统一带 `module` 字段，前端不需要自己记「这份响应属于哪个模块」。四个 `/papers` 端点退场。

> 代价：不再有「一次拿全部等级 + 各等级能力描述」的接口。等级 chip 由前端按版本矩阵渲染，需要能力描述时逐级调 U2；若产品坚持一次拿全，另加 `GET /hsk/levels/all?module=&version=`（只返 `level`/`levelName`/`abilityDescription×3`/`totalQuestionCount`，不含 `parts`，不塞进 U1，避免语义再分叉）。

> 统一约定：`version` 必须**同时**作为 `practice_module_level_config.version` 与 `exam_paper.version` 的条件，漏一处会出现「等级列表是 2.0、卷列表是 3.0」。


#### 3.3.4 翻译模块

**目录 4 个（P0，2026-11-11 已并入 U1–U3）**

| # | 旧路径（已 404） | 去向 |
| --- | --- | --- |
| ~~T1~~ | ~~`GET /translation/levels`~~ | **并入 U1**：`GET /hsk/levels?module=translation&version=&level=`；2.0 → `paperCount=0` + `papers=[]` |
| ~~T2~~ | ~~`GET /translation/levels/{level}/intro`~~ | **并入 U2**：`GET /hsk/levels/{level}/intro?module=translation&version=`；`parts[]` 来自板块配置 |
| ~~T3~~ | ~~`GET /translation/papers`~~ | **删除**，卷清单并入 U1 的 `papers[]` |
| ~~T4~~ | ~~`GET /translation/papers/{paperId}/parts`~~ | **并入 U3**：`GET /hsk/papers/{paperId}/parts`；2 个板块 `translation_written` / `translation_oral` |

⚠️ 板块层**不下发 `layouts`**（2026-11-11 拍板）：笔译 / 口译两张卡的作答形态进题后按题目接口逐题下发的 `layout` 渲染（`input` / `record`）——来自 `question.layout`，不是 `type_code` 字典。

**写链路 6 个（P0，薄封装委托 `Writing*Service`）**

| # | 路径 | 委托 |
|---|---|---|
| T5 | `POST /translation/records/start` | `WritingAttemptService#start` |
| T6 | `GET /translation/records/{recordId}` | `#get` |
| T7 | `GET /translation/records/{recordId}/questions` | `#listQuestions` |
| T8 | `PUT /translation/records/{recordId}/answers` | `WritingAnswerService#save` |
| T9 | `POST /translation/records/{recordId}/submissions` | `WritingSubmissionService#submit` |
| T10 | `GET /translation/records/{recordId}/report` | 🔴 决策 24：原 `/translation/reports/{reportId}` + `WritingReportService#get` 随报告表退场，改 record + answer 现拼 |

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

不加这条，翻译**根本开不了练习**。

> ⚠️ **2026-11-11 实施修正：侵入点不止 `validatePart` 一处，实际 7 处。** 原文「唯一侵入点」低估了：写作链路除板块校验外，题型/布局/答案类型都是**枚举硬编码**、题目归一化是 `switch (type_id_mapping)` 的 5 个写作分支、判卷任务无策略也会照排。落地清单：
>
> | # | 位置 | 改动 |
> |---|---|---|
> | 1 | `WritingQuestionType` / `WritingLayoutType` / `WritingAnswerType` | 各加 2 / 2 / 1 个枚举（`TRANSLATION_WRITTEN`、`TRANSLATION_ORAL` / `INPUT`、`RECORD` / `AUDIO`） |
> | 2 | `WritingQuestionNormalizer` | 加 `translation_written`、`translation_oral` 两分支，原文取 `question.passage`，布局以 `question.layout` 为准 |
> | 3 | `WritingQuestionSetFactory#create` | 增 `expectedMapping` 重载，`content_type` 校验由写死 `SEC_WRITE` 改为等于传入编码 |
> | 4 | `WritingAttemptServiceImpl#validatePart` + `start` | 放宽如上；取题与建快照按传入 `sectionMapping` 走 |
> | 5 | `WritingAnswerServiceImpl#prepare` | 加 `TRANSLATION_WRITTEN`（TEXT）/`TRANSLATION_ORAL`（AUDIO）两条作答校验 |
> | 6 | `WritingSubmissionFinalizer` | 提交前查 `writing_evaluation_policy`，无策略不建判卷任务，报告直接 `READY`/`UNAVAILABLE`（翻译 P0 依赖此行为） |
> | 7 | `WritingReportServiceImpl#requireReady` + `WritingExceptionHandler` | 放行 `UNAVAILABLE` 终态；advice 作用域补 `hsk.translation.controller`，否则 B8 的版本冲突落全局兜底变 500 |
>
> 结论不变（仍走「目录独立 + 作答复用」），但评审要点要从「一处放宽」改成「七处成对回归」：写作侧 5 种题型的开练/作答/交卷/报告必须全部回归。

#### 3.3.5 异常处理

| 场景 | 处理 |
|---|---|
| `version` 非法 | 400 `PRACTICE_VERSION_INVALID` |
| `level` 在该版本下不存在 | 404，沿用各模块原有文案 |
| `paperId` 的 version 与入参不符 | 404「试卷不存在」（**不提示版本不符**，避免探测） |
| `sectionMapping` 与模块不匹配 | 400 `SECTION_MAPPING_MISMATCH` |
| 首页字典查询异常 | 直接冒泡 500（字典没了就没有卡片可渲染，前端只好白屏，不如让监控看到）；字典「查得到但为空」返回 `modules=[]` + WARN，不报错 |
| 报告评分策略缺失（翻译 P0） | 报告正常返回，`feedbackStatus=UNAVAILABLE`、`score=null` |
| 板块配置缺行（R14） | 兜底命名 + 视为开放，记 `WARN` 日志供运营补配 |

#### 3.3.6 板块开关的读写边界

| 侧 | 行为 | 端点 |
|---|---|---|
| C 端 | 只读，按 `enabled` + `enabled_prac` 过滤，**不暴露开关字段** | U1–U3 / CR 统一端点，零新增 |
| 运营端（板块） | 改该行的 `enabled`（`0` 关闭 / `1` 开放）即开关板块；**不要删行**，删行等于回到"未配置"，会被 R14 兜底放出来；`deleted` 只在真的不要这个板块时才置 1 | `GET /hsk/module-config/parts?version=&level=&sectionMapping=`、`PATCH /hsk/module-config/parts/{id}` |
| 运营端（卷 / 题） | 改 `exam_paper.enabled_prac`、`question.enabled_prac`（`1` 上架 / `0` 下架），整卷 / 单题生效；考试侧改对应的 `enabled_exam` | 沿用题库管理侧现有卷 / 题编辑能力，**本次不新增接口** |
| 本次不做 | 批量上下架、板块级灰度、按用户差异化 | — |

> C 端响应结构只增不改（`parts[]` = `partCode / section / partName×3 / typeCode / typeName×3 / questionCount / sortOrder`；`structureId` 删除；`answerMode` 与 `layouts` 均**不下发**——作答形态进题后按题目 `layout` 判）。

---

### 3.4 五级开关与求值顺序

| 级 | 开关 | 粒度 | 关掉之后 |
|---|---|---|---|
| L1 版本 | 前端选择 / `exam_paper.version` | 版本 | 整版不出现 |
| L2 模块 | `practice_module_level_config.enabled` | 版本×等级×模块 | 该模块在该等级不下发（U1 `paperCount=0`），**不再求值下级**。⚠️ **首页卡片不受此开关影响**——首页是字典驱动，开关管的是「有没有卷」 |
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
GET /hsk/modules?version=HSK3.0 → 解析版本 → 查字典（唯一 1 次 SQL）→ 映射卡片 → 按 sortOrder 返回
前端：layout=LIST 渲染 1 列 5 行，全部可点（首页不判可用性）
      点卡片 → GET /hsk/levels?module=xx&version= 拿卷与进度；该版本 0 卷时 U1 返回 paperCount=0
```

**翻译开始练习（含准入链）**
```
POST /translation/records/start {paperId, section}
 → requireAuthenticatedAppUserId（仅委托）
 → 前置校验：question 里 (paperId, section) 的 section_mapping == SEC_TRANSLATION
 → WritingAttemptServiceImpl#start
     ├─ requirePaper：卷有效 + exam_type=1 + enabled_prac=1 + level ≥ 3
     ├─ validatePart：contentType ∈ {SEC_WRITE, SEC_TRANSLATION} 且 == sectionMapping
     ├─ 已有 IN_PROGRESS → 直接返回（幂等）
     └─ 新建记录（practice_writing_record），快照 section_mapping / section / paperVersion / questionSetVersion
 → 返回 recordId（String）
```

**版本切换**
```
清空已选 level / 卷列表 / 滚动位置 / 本地「上次练习」→ GET /hsk/modules?version=<new>
```
> 不要复用旧 `level` 打新版本接口：2.0 的 `1` 在 3.0 下虽存在但卷集合不同；`7` 在 2.0 下返回空 `papers[]`（不 404，前端据 `paperCount=0` 显示空态）。

---

### 3.6 缓存 / 异步 / 权限

| 项 | 方案 |
|---|---|
| 模块元数据 | **取自 `sys_dict` / `sys_dict_item`**（`hsk_practice_module_v2` / `_v3`），随字典缓存刷新，不做进程内常量。字典只承载「有哪些模块、什么顺序、四列 code/文案」（`item_text` 中文名、`item_value`=`section_mapping`、`description`=`moduleCode`、`item_properties`=`{moduleCode,nameEn,nameVi}`），`layout` 在 `sys_dict.remark`；**`icon` / `theme` / `badge` / `entryLevelCode` 不入库**，前端按 `moduleCode` 内置 |
| 目录结果 | P0 不缓存（单等级 ≤ 21 卷）；P1 可加 Caffeine，`key = version + level + module`，TTL 60s |
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
| 参数注入 | `version` / `level` 走白名单枚举；SQL 全部参数绑定 |
| 越权 | `record` 校验 `userId` 归属；翻译薄封装必须校验 `(paperId, sectionMapping, section)` 的实际 `section_mapping`，否则可用写作板块串号 |
| 版本探测 | 卷版本不符统一回「试卷不存在」 |
| 答案泄露 | `answer` / `analysis` 不得在作答阶段 `/questions` 下发，只在报告接口给 |
| 音频 | 前端直传 `system-service /file/uploadVoice`，本服务只存 URL，不代理二进制 |
| ID 精度 | 新增端点 ID 一律 String（19 位雪花超 JS 安全整数）；存量 Long 于 P1 统一 |

---

## 6. 性能与容量

| 场景 | 数据量 | 设计 |
|---|---|---|
| 首页模块卡 | 字典固定 4 / 5 项 | **SQL 恰好 1 次**（`sys_dict ⨝ sys_dict_item`），与模块数无关；P95 ≤ 30ms |
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
1. 不传 `version` → `layout=GRID_2`、**4 卡且不含翻译卡**（字典 v2 无 `SEC_TRANSLATION` 项）。
2. `version=HSK3.0` → `layout=LIST`、5 卡、翻译在第 4 位；响应里**不含** `icon` / `theme` / `badge` / `entryLevelCode` 键。
3. `hsk3.0`（小写）/ `HSK4.0` → 400，不得静默降级。
4. U1 `module=reading&version=HSK3.0&level=7` → **单对象**：`level="7"`、`levelName="HSK7-9"`、`paperCount>0`；2.0 下传 `level=7` → `paperCount=0` + `papers=[]`（不 404）。
4b. U1 一律返单对象（含 `papers[]`），**不再是数组**；旧 5 条 `/{mod}/levels` 与 4 条 `/{mod}/papers` 调用 **404**。
4c. 任一 U3 `/hsk/papers/{id}/parts` → `data` 为 `{module, paperId, paperCode, parts[]}`，且每个 part 都有 `draft`/`report`/`stats` 三个键（无值为 `null`），**无 `layouts` 键**。
4d. CR `GET /papers/{paperId}/reports/latest?module=&section=` → **通用报告块**：五模块（含翻译）顶层字段名一致（`durationSeconds` / `totalQuestions` / `correctCount` / `accuracyRate` / `answerCard[]`…），仅 `module` 对应的扩展块（`reading` / `writing` / `speaking` / `translation`）非 `null`；缺 `module` 或缺 `section` → **400**；旧 `/{mod}/papers/.../reports/latest`（带模块前缀）与更旧的 `/parts/{structureId}/reports/latest` 均 **404**。
4e. CR `answerCard[]`：听力/阅读 `length = totalQuestions` 且逐题有 `correct`；写作纯主观 / 口语未判分 / 翻译 P0 → 对错字段全 `null`（前端隐藏卡片，不 500）。
4f. CR `module=translation`：3.0 翻译卷 `section=1` → 200（`translation` 扩展块同 `writing` 形状，`feedbackStatus=UNAVAILABLE`）；2.0 的卷 → **404**（`SEC_TRANSLATION` 板块不存在）。
5. U1 `module=reading&level=7&version=HSK3.0` 的 `papers[]` 在 **PROD** 能查到卷（验证 R3 候选集）。🔴 最易漏。

**翻译独立**
6. 2.0 调 U1 `module=translation` → `paperCount=0` + `papers=[]`，不 404。
7. 3.0 → `paperCount=1`，`papers[0].totalCount=4`。
8. U3（翻译卷）→ 2 个板块：笔译 `translation_written`、口译 `translation_oral`；**无 `layouts`**。
9. 拿写作卷的 section 打翻译 → 400；拿翻译卷的 section 打写作 → 仍 404（写作侧不放宽）。
10. 笔译交卷 → 报告 `UNAVAILABLE`、`score=null`（P0 预期）。
11. U3（写作卷）不含翻译板块（回归）。

**存量回归**
12. 2.0 四模块全链路（模块卡→U1→U2→U3→答题→CR 报告）与改造前逐字段一致。
13. U1 `module=listening&level=1` 不再混入 3.0 卷（TEST 本身已有 3.0 卷，可直接验）。
14. TEST U2 `module=listening&level=1` 不再 500。
15. U3（HSK7-9 写作卷）不再 500。⚠️ TEST 的 `level='7'` 走不到 `parseInt('7-9')` 分支，**必须用单测/构造数据覆盖 `'7-9'`**（差异 E11 只能这样验）。
16. 存量 `writing_attempt`（TEST 217）仍可打开续练；生产 284 条在生产对齐后回归（附录 D D.3）。

**边界**
17. 未登录 → 401。
18. 首页无用户态：不带 token 与带过期 token 都返回同一份 `modules`（响应零用户数据）；字典为空 → `modules=[]` + 200。
19. 不存在的 `paperId` → 404 不 500。
20. `enabled_prac = 0` 的卷 → **列表不出现、详情报 404、开始作答报 404**（三处都测，B-17）。
21. 卷级上下架与模块/板块开关互不干扰：卷下架但模块开 → 该等级仍有其他卷；模块关但卷上架 → 该等级无卷（U1 `paperCount=0`，首页卡片照常显示）。

**上下架（`enabled_prac` / `enabled_exam`）**
22. `question.enabled_prac = 0` 的单题 → 目录题量 `-1`，答题时不出现在该板块题目列表；其它板块不受影响。
23. 某板块全部题都被单题下架 → 该板块因 `actual_count = 0` 不下发（R6），**不报错**。
24. 🔴 `enabled_prac = 1` 但 `enabled_exam = 0` → **练习侧必须仍可见**（只关了考试）；反向 `enabled_prac = 0, enabled_exam = 1` → 练习侧不可见。这两条是 B-20 的回归判据。
25. 全表 `grep enabledExam` / `grep enabled_exam` 在 `practice-service` 内 **零命中**（练习侧不得出现这一列）。

**板块开关**
26. 关 `HSK2.0/L1/SEC_LISTEN/section=2` → 目录只剩另外三个板块，其题量名称题型不受影响。
27. 新开练习不含 section=2 的题；历史记录仍可打开、报告题数不变（R13）。
28. 关整模块 → 该模块该等级不下发卷，不再受板块开关影响（短路顺序）。
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
| 「各接口已有 `?version=` 入参」 | 4 个模块全是 `private static final String VERSION = "HSK2.0"`，无 Controller 接收 version | 🔴 版本参数是新增；目录端点已合并为 U1–U3（`module` query + `version` query），其余保留端点逐个加参数 |

### 9.2 版本用 query param

不用 header（隐式全局态，排障困难）、不用 path（路径翻倍，且版本是内容开关不是 API 版本）。代价是 U1–U3 与作答链路各端点都要加参数、前端每请求都带，可接受。

### 9.3 翻译：目录独立 + 作答复用

| 方案 | 新增端点 | 持久层 | 存量侵入 | 结论 |
|---|---|---|---|---|
| 只分目录 | 4 | 复用 `writing_*` | 0 | ❌ 前端要两个 basePath |
| **目录独立 + 薄封装** | **4 + 6** | **复用 `writing_*`** | **7 处**（原估 1 处，见 §3.3.4 修正） | ✅ 采纳 |
| 完全独立 | 14 | 新建 7 张表 | 0 | ❌ 评分/报告/统计重造，工期最长 |

风险：放宽 `validatePart` 后写作与翻译共用 attempt 表，靠 `content_type` + `section_mapping` 双条件隔离，这两个条件必须成对评审。

### 9.5 板块配置拆成行式表

产品要「第一部分、第二部分单独控制开关」。`parts_config` 元素**没有 `section`、只有 `sortOrder`**，与 `question.section` 靠数组位置隐式对齐（TEST 38/46 行成立）。一旦允许关板块，数组必须留占位元素，`sortOrder` 就退化成「不可删的编号」——那它本来就该是 `section` 列。

| 方案 | 结论 |
|---|---|
| 元素补 `section` + 开关键 | 可行但不彻底：JSON 里没有唯一约束、开关写成 `"0"` 也存得进、审计只到整行、SQL 只能 `JSON_EXTRACT`，且"关一个板块"要么删元素（后续错位）要么留占位（`sortOrder` 退化成编号） |
| **拉平成 `practice_module_part_config`** | ✅ 唯一键防重、开关是独立的 `enabled` 列（`deleted` 只管逻辑删除）、`UPDATE ... SET enabled=0 WHERE section=2` 只锁一行 |
| 单表 `section=0` 表示模块行 | ❌ 一半字段永远 NULL，接口处处判 `section=0` |
| 不拆，靠前端隐藏 | ❌ 题目仍下发，用户仍能练到 |

**行数不增长**：新表挂 `(version, level, section_mapping, section)`，132 行封顶，由等级数决定，不随卷数膨胀；旧 `practice_part_setting` 挂 `structure_id`（卷级），1294 行且随题库扩容增长。这是**降粒度**，不是复活旧表。

### 9.5b 答题形式读 `question.layout`，不造 `answerMode` 字典

原本打算在 `PracticeTypeRegistry` 里维护 `type_code → answerMode`（`SINGLE` / `MATCH` / `ORDER` / `RECORD` / `TEXT`），再下发到 `parts[]`。实测否决：

| 方案 | 结论 |
|---|---|
| `type_code → answerMode` 字典 | ❌ PROD `listening_single` 一个编码对 **4 种** `layout`、`listening_detail_choice` 也对 4 种；TEST `SINGLE` 对 3 种。字典一映射就把「看图选择」渲成「篇章组」 |
| 落 `part_config.answer_mode` 列 | ❌ 粒度不够：答题形式是**题级**的，一个板块混两种交互（TEST 2 个板块、PROD 48 个）就无处可写 |
| 前端按 `typeCode` 猜 | ❌ 同上，且题型名与交互形态本来是两回事 |
| **读 `question.layout` 原样透传** | ✅ 已经是落库的答题形式，逐题准确；加题型不用改代码；沿用 CSCA 既有约定（`CscaQuestionResponse`：「只由 `layout` 决定，不能按字段是否为空猜形态」） |

**少一层映射就少一处漏配**：写作 `WritingLayoutType` 的 `switch (getTypeIdMapping())` 白名单只覆盖 5 个老题型，3.0 的 `chart_analysis` / `topic_essay` 直接落 default（B-04）。读 `layout` 之后，这类问题从根上不会再有。

**代价**：生产库的 `layout` 缺失 47.7%、值域还是老的一套（混了 `passageGroup` / `clozeGroup` 这种题面形态），**生产要先用上这个方案，须先对齐数据（差异 E6/E7）**；TEST 已是 100% + 7 个规范值，本次开发与验收不受影响。口语内容在 `speaking_exam_paper_question`，那张表没这一列，P0 按模块定 `record`。

### 9.6 `practice_record` 用三元组、删 `practice_name`

`structure_id` 是 `(paper_id, section_mapping, section)` 的代理键（`selectByStructure` 内部即三元组 JOIN），而 `practice_record` 三列本来就齐备，是第 4 份等价信息；实测新旧路径取题数 PROD 1343/1343 零差异。`practice_name` 与 `section_name` 100% 一致，纯复制。

「不能做唯一键」不是保留理由：重复组（TEST 131 / PROD 106）确实存在，但业务语义始终是取最新一条，从不需要唯一约束。

**同一个口径贯彻到全部作答表**：`writing_attempt`(217/284) 与 `speaking_attempt`(283/473) 原本只有 `paper_id + structure_id`，实测都能 100% 回填出三元组（§3.2.6；⚠️ 两表 2026-11-16 已改名 `practice_writing_record` / `practice_speaking_record`），所以不留「结构表当 ID 注册表」这个尾巴，P0 一次删干净。接口风格也不再分叉——所有模块都用 `paperId + sectionMapping + section`（决策 23 三字段）。

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

### 9.8 口语内容读speaking_exam_paper和exam_paperL7的SEC_SPEAKING

一度以为 3.0 口语应该在 `exam_paper` + `SEC_SPEAKING` 里。实测推翻：

| 事实                          | TEST                       | PROD         |
| --------------------------- | -------------------------- | ------------ |
| `speaking_exam_paper` 3.0 卷 | 5 张（L3/L4/L5/L6/L7-9），78 题 | 0 张（3.0 未放开） |
| `speaking_exam_paper` 2.0 卷 | 33 张，759 题                 | 33 张，759 题   |
| `question` 里 `SEC_SPEAKING` | 5 题，1 张卷                   | 同            |

`question` 里那 5 题所在的 `paper_id` 在 `exam_paper` 是 L7 的一张卷，与 `speaking_exam_paper` 的 5 张口语卷**毫无关系**——它是造数残留。代码侧 4 处常量全部是 `SEC_SPEAK`，`SEC_SPEAKING` 从未被引用。

因此：口语不分版本，统一读 `speaking_exam_paper` / `_question`，`section_mapping` 用 `SEC_SPEAK`（2.0 部分号来自配置的 `PART_1/2/3` → `1/2/3`）。`SEC_SPEAKING` 的配置行（TEST 1 行模块 + 3 行板块）与 `question` 里 5 条造数一并清掉。

---

## 10. 落地分期

| 期         | 范围                                                                                                                                                                                                                                                                                                                                             | 前置                                                              | 完成判据                                                                                          |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **P0-a**  | 修三条存量缺陷（附录 A：B-01/B-02/B-03）                                                                                                                                                                                                                                                                                                                   | —                                                               | TEST 听力 intro 不 500；PROD 听力列表不混版；HSK7-9 写作可开练                                                 |
| **P0-b**  | 四个支撑类：`PracticeVersion` / `PracticeLevelCode` / `PracticeModuleCatalog`（**模块元数据从 `sys_dict` 读，不再写死常量**）/ `PracticeLayout`（`layout` 值域 + 主客观判定，**不做值换算**）                                                                                                                                                                                       | —                                                               | 单测覆盖 `HSK7-9`、`'7-9'`、非法版本、7 个 `layout` 值                                                     |
| **P0-c**  | 存量目录端点**合并为 U1–U3 统一端点**（新增 `PracticeCatalogController`）：`module` 改 query 且必填、加 `version`、`/levels` 单对象内嵌 `papers[]`、删 4 个 `/papers`；报告端点合并为 **CR**（新增 `PracticeReportController`，`module`/`section` 走 query，白名单 5 值**含 `translation`**——委托写作链路按 `SEC_TRANSLATION` 过滤），响应按决策 20 重映射为「通用报告块 + 模块扩展块」。旧 15 条 `/{mod}` 目录路径 + 4 条带模块前缀的报告路径全部 404 | P0-b                                                            | 2.0 全链路零回归；旧 `/{mod}/levels`、`/{mod}/papers`、带模块前缀的报告路径调用 404                                 |
| **P0-c2** | **`practice_module_part_config` 收尾**：TEST 已建表迁数据（132 行）+ 已补 `enabled` 列 → 补唯一键（`answer_mode` 不入库、答题形式读 `question.layout`；开关读 `enabled` 而非 `deleted`）→ 清 `SEC_SPEAKING` 残留配置                                                                                                                                                                    | P0-b                                                            | 表含 `uk_module_part`；132 行 `enabled` 全 1；`layouts` 取值全部落在 7 个规范值内；关板块后目录不出现                    |
| **P0-c3** | 板块开关接口 `PATCH /hsk/module-config/parts/{id}`                                                                                                                                                                                                                                                                                                   | P0-c2                                                           | 关板块后目录不出现，新练习不下发其题目，历史记录不受影响                                                                  |
| **P0-d**  | 聚合接口 `GET /hsk/modules`，模块卡改由字典驱动                                                                                                                                                                                                                                                                                                              | P0-c；**TEST 字典数据已就绪**（`hsk_practice_module_v2` 4 项 / `_v3` 5 项） | 2.0 四卡 / 3.0 五卡，卡片顺序与三语名取自字典；改字典 `sort_order` 后顺序即时生效                                         |
| **P0-e**  | **重写 `PracticeCatalogBatchLoader`**：从「查 structure + part_setting」改为「读板块配置 + 算题量」                                                                                                                                                                                                                                                               | P0-c2                                                           | 2.0 四模块目录与现网**逐字段一致**                                                                         |
| **P0-f**  | 翻译目录 4 + 写链路 6 + `validatePart` 放宽                                                                                                                                                                                                                                                                                                             | P0-e                                                            | 笔译/口译都能练到交卷；写作卷的 section 打翻译 → 400                                                            |
| ~~P0-g~~  | ~~生产库数据补全~~                                                                                                                                                                                                                                                                                                                                    | —                                                               | **移出本文档**：生产与 TEST 的结构 / 数据差异只在[附录 D](#附录-d生产与测试环境差异登记) 登记，生产改造另行安排，不进本分期、不影响 P0-a～P0-j 的排期   |
| **P0-h**  | **作答表统一三元组**：`practice_record` 删 2 列 + 重建索引；`writing_attempt` / `speaking_attempt` 加两列 → 回填 → 校验 0 残留；7 处 Mapper 改三元组；接口改 `(paperId, section)`；CSCA 3 处改 `SEC_CSCA + 科目码`                                                                                                                                                                      | P0-e                                                            | 抽 100 条历史记录新旧路径取题 ID 一致；`EXPLAIN` 走新索引；新记录 `question_ids` 非空且长度 = `total_questions`；回填校验 0 残留 |
| **P0-i**  | **`practice_paper_setting` 退场**：删 `PracticeCatalogBatchLoader` 里的 setting 查询；`ReadingRecordServiceImpl` / `WritingAttemptServiceImpl` 的准入改判 `enabled_prac`；3 处 `getSortOrder()` 排序改 `id`；`SharedPaperEligibility` 补判 `enabled_prac`（B-17）；最后 `DROP TABLE practice_paper_setting`                                                               | TEST 数据已就绪（生产差异见附录 D）                                           | 4 模块目录与现网逐字段一致；下架卷在列表/详情/作答三处均不可达；表已 drop                                                     |
| **P0-j**  | **结构表 drop**：确认代码中 `structureId` 出现次数 = 0 → `DROP TABLE practice_part_setting` → `DROP TABLE practice_paper_structure`                                                                                                                                                                                                                         | P0-h 回填校验通过 + P0-e 已换源                                          | 两表不存在；`grep -r structure_id` 源码零命中；全链路回归通过                                                    |
| P1        | ID 改 String；`dataVersion` ETag；角标后台可配；补 `TRANSLATION_WRITTEN` 策略；collation 对齐（D10 随表退场自动消失）；板块级时长/满分/提示语加列；口语表补 `layout` 列。~~偏好表加 `version`~~（偏好接口已整体下线，2026-11-11）                                                                                                                                                                            | P0 上线观察                                                         | —                                                                                             |
| P2        | `option_pool` 三步退场（补 90 条 → `pool_code` 去 structureId → 快照现算）；口译 ASR + 自动评分                                                                                                                                                                                                                                                                    | P0-j 稳定                                                         | —                                                                                             |

> 🔴 **最大风险点是 P0-e**：唯一会改变 2.0 现网行为的改造（目录换源）。验收法：同一批请求（4 模块 × 版本 × 等级），新旧响应 **JSON 逐字段 diff 必须为空**，建议先存旧实现快照。
>
> **结构表不能先 drop**：`practice_part_setting` / `practice_paper_structure` 必须等 P0-e（换源）+ P0-h（回填校验）都通过再删，否则回滚无路。删之前用 `SELECT COUNT(*) FROM 表` 留基线，`DROP` 前做全表导出备份。
>
> 顺序：**P0-a → P0-b → P0-c2 → P0-c → P0-c3 → P0-e → P0-f → P0-h → P0-i → P0-j**（P0-g 已移出，见上）。

> ✅ **2026-11-11 进度更新（P0-c 部分完成）**：`PracticeCatalogController`（U1–U3）已落地，配套新增
> `PracticePartAssembler`（§7.1 装配：`level_config` 短路 → `part_config` **不带 `enabled` 条件**三分拨 → 题量现算 → 兜底「第N部分」）、
> `PracticeCatalogModule`（`module ↔ section_mapping`）、`PracticeLevelCode`（`version` 白名单 + `level` 值域 + `'7'→('7','7-9')` + 2.0 口语文字档位）、
> `PracticeModulePartConfig` 实体/Mapper（此前该表代码零引用）。
>
> 一处**未完成，需单独决策**：
> ① **P0-e 的 `PracticeCatalogBatchLoader` 重写未做**——新 U1–U3 走的是自己的装配器，老 loader 仍从 `structure + part_setting` 取数，两条读路径并存（这正是「目录看得到、开练读不到」的根源，见接口文档 §4.0.6 末尾）。
>
> ✅ **旧 15 条模块内目录端点已摘除（2026-11-11 同批）**：`ListeningCatalogController`（3 条）、`ReadingCatalogController` / `WritingCatalogController` / `SpeakingCatalogController`（各 4 条）的 `@GetMapping` 全部**整块注释**，现全部回落 404；类保留为零映射壳，imports 与 service 字段原样未动（去掉行首 `// ` 即可回滚），待统一目录稳定后整体删除。即 §6.1 第 5/9/12 条达成。
>
> ⚠️ 这意味着**前端必须已切到 U1–U3**，否则旧 15 条路径直接 404（此前它们虽然返回空板块，至少不是 404）。

> ✅ **P0-d 已完成（2026-11-11）**：`GET /hsk/modules` 落地，模块卡**由字典驱动**——卡片顺序、三语名、`sectionMapping`、`moduleCode` 全部来自 `sys_dict` / `sys_dict_item`，代码里零常量（改 `sort_order` 即时生效）。`layout` 取 `sys_dict.remark`（`GRID_2` / `LIST`）。
> 🔴 **口径已收敛为「只做展示」（决策 13b）**：初版曾额外下发 `available` / `disabledReason` / `totalPapers` / `completedPapers` / `inProgressPaperId`（要 7 条 SQL 且必须登录），已全部砍掉——现在 **SQL 只有 1 条、接口完全免登录、响应零用户数据**。可用性 / 卷数 / 进度统一由 U1 提供。
> ⚠️ **踩坑记录**：`sys_dict.remark` 存的是 JSON（`{"layout":"GRID_2"}`），不是裸值 `GRID_2`，服务端必须取 `layout` 键，否则整段 JSON 会被当布局下发。
> 🔴 **上线前提**：`gateway.white-list` 必须加 `/api/practice/hsk/modules`（TEST / PROD 两份 yml 已改），否则免登录调用在网关就被 401。
> 🔴 **生产仍需灌字典（E16）**：未灌时接口正常返回 200 但 `modules=[]`，首页空白——这是数据问题不是代码问题。

---

## 附录 A：存量缺陷（本次顺带修）

| # | 缺陷 | 位置 | 症状 | 严重度 |
|---|---|---|---|---|
| B-01 | `selectOne` 未带 `version` | `ListeningCatalogServiceImpl#getIntro`、`#listParts` | 两版本同等级共存 → `TooManyResultsException` → 500（TEST 已触发） | 🔴 高 |
| B-02 | 卷查询无 `version` / `exam_type` 过滤 | `ListeningCatalogServiceImpl#getLevelOverview` | 混入 3 张 3.0 卷且 `totalCount=0`（PROD 已触发） | 🔴 高 |
| B-03 | 裸 `Integer.parseInt(paper.getLevel())` | `WritingAttemptServiceImpl#requirePaper`、`WritingCatalogServiceImpl#listParts`、`ReadingCatalogServiceImpl#paperResponse` | PROD 的 `'7-9'` → `NumberFormatException` → 500 | 🔴 高 |
| B-04 | `parseLevel` 只认 `HSK[1-6]` | `WritingCatalogServiceImpl#parseLevel` | `HSK7-9` → 404 | 🟡 中 |
| B-05 | `"HSK" + level` 拼 code | 阅读/写作/口语 Catalog、`getPreference` | 返回 `"HSK7"`，前端查不到 | 🟡 中 |
| B-06 | `level` 裸 `parseInt` | `ReadingCatalogServiceImpl#requireModule`、`ListeningCatalogServiceImpl#parseLevel` | `HSK7-9` → 404/500 | 🟡 中 |
| B-07 | 目录 ID 为 `Long` | 各 Paper 响应 | 19 位雪花丢精度（新增端点改 String，存量 P1） | 🟡 中 |
| B-08 | `writing_evaluation_policy` 缺 3 个题型 | 表数据 | `TRANSLATION_WRITTEN` / `CHART_ANALYSIS` / `TOPIC_ESSAY` 交卷后报告永久「生成中」 | 🟡 中 |
| ~~B-09~~ | ~~`answer_mode` 与题型语义错配~~ | — | **已消解**（2026-11-10）：不再有 `answer_mode` 这一层，答题形式直接读 `question.layout`，错配源头消失（§3.2.2b） | ✅ 关闭 |
| B-10 | 3.0 口语在 `question`（5 条）与 `speaking_exam_paper`（5 张卷 78 题）双录，且 `question` 那条是造数残留 | 题库数据 | 若按 `question` 配料会读到 1 张假卷 → 口语目录近乎空 | 🟡 中（P0-c2 软删 5 条） |
| B-11 | `practice_paper_setting` 孤儿行：TEST 69（38 活跃 + 31 软删）/ PROD 56（全活跃），占全表 34% / 48% | 运营表数据 | 现网被 `IN` 天然过滤；**退场后自然消失，无需清理** | 🟢 低（已被 P0-i 覆盖） |
| B-12 | `practice_paper_setting` 三个开关在真实卷上零使用：`enabled=0` 的 2/5 行、`deleted=1` 的 31 行**全是孤儿行**，`visible` 全表为 1 | 运营表数据 | 这张表对真实卷只剩「行是否存在」；`sort_order` 也与 `id` 升序完全一致 → 由 `enabled_prac` 替代（§3.2.7） | 🟢 低（P0-i 退场） |
| B-13 | 共享选项池缺记录：`reading_cloze` TEST 90/690 无池记录、PROD 90/90 全无；`pool_code` 内嵌 `structureId` | `practice_question_option_pool` | 选词填空退化成每题重复渲染 6 个选项 | 🟡 中（P2 前置） |
| B-14 | `question.layout` 生产库缺失 47.7%（6469/13574），值域也是老的一套；TEST 100% 且为 7 个规范值 | `question` 数据 | **对本次开发无影响**（代码按 TEST 实现）；对上生产有影响 → 差异登记附录 D **E6 / E7**，生产对齐另行安排 | 🔴 高（仅生产侧） |
| B-15 | 口语编码分裂：`SEC_SPEAK` 与 `SEC_SPEAKING` 并存（TEST 配置 `SEC_SPEAKING` 1 行模块 + 3 行板块，与 `SEC_SPEAK` L7 重复），代码 4 处只用 `SEC_SPEAK` | 配置数据 | 保留 `SEC_SPEAKING` 就是永久孤儿配置 | 🟡 中（P0-c2 删 4 行） |
| B-16 | PROD `HSK2.0 L2 SEC_LISTEN` 的 `total_question_count=35`，但四板块求和 40 | 配置数据 | 进度条分母口径不一 | 🟢 低（拆表时以实际计数为准） |
| B-17 | `SharedPaperEligibility.isEligible` 只判 `deleted` + `examType`，**不判 `enabledPrac`**；而 4 个 Catalog 已改为 `enabled_prac = 1` | 4 处调用（阅读/写作 Catalog、Record） | **口径已经分叉**：目录看不到下架卷，详情 / 开始作答却能进入 → 下架卷可直达。补一行 `&& enabledPrac == 1` 即修 | 🔴 高（P0-i 必改，建议提前到 P0-c 后立刻做） |
| B-18 | `practice_module_part_config` 只有 `PRIMARY (id)`，无唯一键 | TEST 实际表 | 同一 `(version, level, section_mapping, section)` 可重复插入 → 开关判定出现两行矛盾（一行 `enabled=1` 一行 `enabled=0`，取哪行决定板块开不开）。实测 132 行当前无重复，补键只防未来 | 🟡 中（P0-c2 补 `uk_module_part`） |
| B-20 | `enabled_prac` / `enabled_exam` 双开关在同一行并存，练习侧若误用 `AND enabled_exam = 1` 或 `OR` | 各 Mapper / Service | 运营为「只关考试」而下架的内容会连带从练习消失；反向漏判则已下架内容仍在练习出现 | 🟡 中（R12b 卡点 + Code Review grep `enabled_exam` 仅允许出现在考试服务） |
| B-19 | 口语取题靠 `PartCodeCase` 硬编码 8 个题型 → `PART_1/2/3`，`selectByPart` 的题型白名单同样只列这 8 个 | `SpeakingSourceQuestionMapper.xml` | 新配置里 6 个 `type_code` 不在白名单：3.0 L4/L5/L6 的 `listen_retell`、L7 的 `applied_read_speak` / `listen_material_answer` / `viewpoint_express` → **这些板块取题返回空**，用户看到"有题但点进去没题" | 🔴 高（P0-e 必改） |

> B-01 / B-02 / B-03 **不等本次改造上线就该修**：前两条现网已发生，第三条是 3.0 放开的必炸点。

---

## 附录 B：数据缺口登记（生产侧；TEST 已就绪）

> 本表只回答「生产库比 TEST 少什么」，**不含整改动作**——生产对齐与本文档分期解耦，动作口径见[附录 D](#附录-d生产与测试环境差异登记)。TEST 侧除 D5 / D6 / D8 外均已就绪。

| # | 缺口 | TEST（基线） | PROD（差异） | 对本次开发的影响 |
|---|---|---|---|---|
| **D3** | `exam_paper.level` 的 7-9 取值不一致 | `"7"` | `"7-9"` | **有**：代码必须用候选集 `IN ('7','7-9')`，不能 `eq("7")`（R3） |
| **D4** | 3.0 的模块配置行 | 28 行 | **0 行** | 无（代码按 TEST 28 行走） |
| **D11** | `enabled_prac` / `enabled_exam` 两列不存在 | **5 表已有** | **5 表全缺** | 无；但**生产部署前必须先加列**，否则启动即 `Unknown column` |
| **D13** | 3.0 卷全部未上架 | 15/15 | **0/15** | 无（属运营放量，不是数据缺陷） |
| **D14** | `question.layout` 大面积缺失 | 100% 有值（7 个规范值） | **47.7% NULL**（`SEC_READ` / `SEC_WRITE` 全空） | 无（代码按 TEST 的 7 个值实现）；生产侧口径见附录 D **E6** |
| **D15** | 2.0 的板块配置只有听力有值 | 46/49 | **6/21** | 无（TEST 已铺满） |
| D5 | `writing_evaluation_policy` 无 `TRANSLATION_WRITTEN` | 缺 | 缺 | **有**：P0 不入队，直接 `UNAVAILABLE`；P1 补 |
| D6 | 翻译 4 题 `answer` 全为 `(略)` | 4/4 | 4/4 | 无：题库补参考译文（P1） |
| D8 | 3.0 卷数偏少 | 15 卷 | 15 卷 | 无：题库导入（已知） |
| D10 | ~~`practice_paper_structure` 的 collation 与其余表不一致~~ | 同 | 同 | **已关闭**：该表 P0 drop，冲突随之消失；P0-e/P0-h 期间跨表比较用 `CONVERT ... COLLATE utf8mb4_0900_ai_ci` |
| ~~D12~~ | ~~`practice_paper_setting` 孤儿行~~ | ~~69~~ | ~~56~~ | **已关闭**：表 drop，孤儿行随之消失 |
| **D16** | `practice_module_part_config` 表 | **已建，132 行** | **不存在** | 无；生产建表时直接用 §3.2.2 的完整形态，一次到位 |

> 遗留 P1：板块级时长 / 满分 / 提示语（同表加列即可）。

---

## 附录 C：关键实测基线（2026-11-10，TEST 为准；PROD 列只作差异参照）

| 项 | TEST | PROD |
|---|---|---|
| `exam_paper`（`exam_type=1`）2.0 / 3.0 | 121 / 15 卷，全部 `deleted=0` | 122 / 15 卷，其中 **61 张 `deleted=1`**（全是 2.0，每级 10 张） |
| 活卷数（`deleted=0`） | 136 | **76** |
| 实际上架卷数（有 setting 行） | 136 | **60**（2.0 的 60 张；3.0 全 0） |
| `practice_paper_setting` 真实卷上的开关使用 | `enabled=0`/`visible=0`/`deleted=1` **均为 0**（非全开行全是孤儿行） | 同 |
| `setting.sort_order` == `id` 升序 | 13/13 组一致 | 6/6 组一致 |
| `practice_paper_setting` 孤儿行 | 69 / 205（34%） | 56 / 116（48%） |
| `practice_module_level_config` 2.0 / 3.0 | 21 / 28 行（**`parts_config` 列已删**） | 21 / **0** 行（`parts_config` 列仍在） |
| `practice_module_level_config.level_name` | **已有**（`varchar(20) NOT NULL DEFAULT ''`），49 行 0 空值，`level → level_name` 严格 1:1（7 个值） | **列大概率不存在**（2026-11-11 新增，生产未核验 → 按缺列处理，见 D.1 E18） |
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
| `question.layout` 值域（`section_mapping` 非空） | 7 个规范值，非空率 100% | 老值域 + 非空率 52.3%（D14） |
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

---

## 附录 D：生产与测试环境差异登记

> **本附录只做一件事：记录生产库与 TEST 库不一样的地方。**
> ① 一律以 **TEST 为开发与验收基线**，正文所有结论、字段、值域都按 TEST 写；
> ② 生产改造**不在本文档设计范围**，由生产侧后续单独安排，本节不含 DDL、不含执行顺序、不占 P0 分期；
> ③ 「生产对齐口径」一列只写**约束与陷阱**（例如「不能按值映射」），避免以后动手时再踩一次同样的坑。

### D.1 结构类差异（生产缺列 / 缺表 / 多列）

| # | 差异项 | TEST（基线） | PROD | 对代码的影响 | 生产对齐口径（约束，非本期动作） |
|---|---|---|---|---|---|
| **E1** | `enabled_prac` / `enabled_exam` 两列 | 5 张内容表**都有**，取值全 `1`（167 / 13624 / 1038 / 38 / 837） | **5 表全缺**（`deleted_prac` 也从未存在） | **有**：生产部署该代码前必须先加列，否则启动即 `Unknown column 'enabled_prac'` | 列定义见 §3.2.7；⚠️ 正向布尔 `DEFAULT 1` 与 E9 必须**同批**处理 |
| **E2** | `practice_module_part_config` 表 | **已建，132 行**，含 `enabled` 列 | **表不存在** | 无（代码读表，生产无表则板块全走兜底 → 名称退化为「第N部分」、`type_code` 缺失致口语取不到题） | 直接用 §3.2.2 的完整建表语句，一次到位；数据按 TEST 132 行灌 |
| **E3** | `practice_module_level_config.parts_config` 列 | **已 drop** | **仍在**（6/21 行有值，20 个板块元素） | 无（代码不再读该列） | 生产可直接 drop；drop 前留导出备份 |
| **E4** | `practice_module_level_config` 行数 | 2.0 **21** + 3.0 **28** = 49 | 2.0 **21** + 3.0 **0** = 21 | 无（按 TEST 走） | 3.0 的 28 行模块配置 + 对应板块明细行需补（D4 / D15） |
| **E5** | `practice_module_part_config` 唯一键 | 仍只有 `PRIMARY`（B-18） | — | 无 | 两边都待补 `uk_module_part`（P0-c2） |
| **E17** | `practice_module_level_config.level_name` / `_en` / `_vi` 三列（**接口 `levelName` 唯一真源，三语**） | **已有**：三列均 `varchar(20) NOT NULL DEFAULT ''`，位于 `level` 之后；49 行 0 空值，`level → level_name` 严格 1:1（`HSK1`…`HSK6` / `HSK7-9`；口语 2.0 三行 zh `HSKK 初级/中级/高级` + en `HSKK Beginner/Intermediate/Advanced` + vi `HSKK Sơ cấp/Trung cấp/Cao cấp`，2026-11-11 落库） | **未核验**（该列 2026-11-11 才在 TEST 新增，生产大概率没有） | **有**：缺列则 `levelName` 一律 `null`，前端等级 chip 无文案（`/levels`、`/intro` 都受影响） | 🔴 补列时**不能只 `ADD COLUMN ... DEFAULT ''` 了事**：必须同批刷三列（`tmp/_add_level_name_i18n.py` / `_speak_level_name_PROD.sql`）。⚠️ 生产 3.0 模块配置 0 行（E4），3.0 的 28 行要先补行才有 `level_name` 可填；⚠️ 别与 `hsk_level_config.level_name`（`一级` / `Level 1` / `Cấp 1`）混为一谈——那是**HSK 考试侧**表（exam-service），练习侧**不读**；两个 `level_name` 同名不同义 |

### D.2 数据类差异（同表不同值，会影响生产行为）

| # | 差异项 | TEST（基线） | PROD | 对代码的影响 | 生产对齐口径（约束，非本期动作） |
|---|---|---|---|---|---|
| **E6** | `question.layout` 非空率 | **100%**（13524 行，7 个规范值） | **52.3%**（7105/13574）；`SEC_READ` 100% NULL（5108）、`SEC_WRITE` 100% NULL（927）、`SEC_TRANSLATION` 4、`SEC_SPEAKING` 5 | **无**（代码按 7 个规范值实现）；生产上近一半题取不到交互形态 | 🔴 **只能按 `question.id` 从 TEST 复制，禁止按值映射**（见 E8） |
| **E7** | `question.layout` 值域 | `choice` / `choiceGrid` / `judge` / `order` / `input` / `shortInput` / `record` | 老值域 8 个：`textChoice` / `textChoice_shareAudio` / `passageGroup` / `textJudge` / `imageMatch` / `imageJudge` / `imageChoice` / `clozeGroup` | **无** | 老值混了题面形态（`passageGroup` / `clozeGroup` = 材料+一组小题），不能直接当前端渲染依据 |
| **E8** | `question.id` 域 | 13524 行，**全部包含在 PROD 之内** | 13574 行（多 50 行独有） | 无 | 回填按 id 复制可覆盖 **6439/6469** 行 NULL；剩 30 行 PROD 独有题需人工判定。**按值映射必错**：老值 `textChoice` 一对 3 个新值（`choice` 2419 / `choiceGrid` 200 / 其他），`textChoice_shareAudio` 一对 3（`choice` 929 / `judge` 10 / `input` 6） |
| **E9** | 活卷「有卷但无 `practice_paper_setting` 行」 | **0** 张（136/136 都有行） | **16** 张（2.0 L1 ×1 + 3.0 全 15 张） | 无 | 加列时 `DEFAULT 1` 会把它们一次性放出来 → 目录 60 卷涨到 76 卷，**必须同批置 0** |
| **E10** | 3.0 卷上架 | 15/15 | **0/15**（整版未放开） | 无（属运营放量） | 3.0 放开时把该版本 15 张卷 `enabled_prac` 改 `1`，**不是新增 setting 行** |
| **E11** | `exam_paper.level` 的 HSK7-9 取值 | `"7"` | `"7-9"` | **有（已兼容）**：任何 `parseInt(level)` / `= "7"` 都会在 PROD 炸；代码统一走 `IN ('7','7-9')` 候选集（R3） | 两库取值可否收敛由 DBA 定；代码不依赖收敛 |
| **E12** | `SEC_SPEAKING` 残留配置 | 有：1 行模块配置 + 3 行板块配置（+ `question` 5 条造数题） | **无** | 无 | 只需在 TEST 侧清理（P0-c2），生产无此问题 |
| **E13** | `total_question_count` 与板块求和不一致 | 46/46 一致 | **5/6**（HSK2.0 L2 听力 `35` ≠ 板块求和 `40`） | 无（题量改为现算） | 生产该值不必修，接口已不读它 |
| **E14** | 混 `layouts` 的板块数 | **2** 个 | **48** 个 | 无（前端逐题渲染） | 若产品要求「一板块一交互」，回内容侧改 `layout`，不改接口 |
| **E15** | 3.0 口语内容 | `speaking_exam_paper` 5 卷 78 题 | **0 卷** | 无（代码按 TEST 走） | 随 E10 一起放量 |
| **E16** | `sys_dict` 模块字典（`/hsk/modules` 数据源） | 已建：`hsk_practice_module_v2`（1007，4 项）/ `hsk_practice_module_v3`（1008，5 项） | **0 项**（字典表存在，无这两条） | **有**：生产不补则 `/hsk/modules` 返回空卡片列表（不报错，但首页空白） | 按 TEST 原样灌 9 项。🔴 `item_value` 必须是 **`section_mapping`**（`SEC_LISTEN` 等），`description` 才是 `moduleCode`；`item_properties` 仅 `{moduleCode,nameEn,nameVi}`；`layout`（`GRID_2` / `LIST`）在 `sys_dict.remark` |

### D.3 仅体量差异（不影响判定，仅供核对）

| 项 | TEST | PROD | 说明 |
|---|---|---|---|
| `practice_paper_setting` 孤儿行 | 69 / 205（34%） | 56 / 116（48%） | 表 P0-i drop，两边都无需清理 |
| `practice_paper_structure` 2.0 / 3.0 | 1066 / 135 | — / **0** | 表 P0-j drop；PROD 3.0 无结构行，故不能在 PROD 上验 3.0 结构链路 |
| `writing_attempt` / `speaking_attempt` | 217 / 283 | 284 / 473 | 回填三元组两边都可行（284/284、473/473） |
| `practice_record` / `practice_report` | 963 / 477 | 1364 / 1011 | 纯数据量 |
| `option_pool` | 2505 行 / 6 种题型全覆盖 | 1150 行 / 5 种（`reading_cloze` **0**） | P2 退场前置，先补 TEST 90 条 |
| `parts_config` 非空行（已删列，存档可查） | 46/49，132 个元素 | 6/21，20 个元素 | 仅佐证「生产 2.0 只有听力配了板块」 |

> **一句话**：开发只管 TEST；上生产时按 E1 → E9 → E6/E7 的顺序处理结构与数据，代码本身不需要为生产再加分支——唯一已写进代码的兼容点是 **E11 的等级候选集**。
