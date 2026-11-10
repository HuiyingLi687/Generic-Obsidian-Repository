# HSK 练习双版本（2.0 / 3.0）与翻译模块拆分 · 软件设计文档

> 服务：`practice-service`（网关前缀 `/api/practice`）｜版本 v2.1｜2026-11-10｜状态：待评审
> 依据：2026-11-10 双版本首页 UI 截图 + 代码基线 + TEST / PROD 实测
> 前置：[首页设计方案](HSK练习模块首页-设计方案.md)、[翻译独立模块接口方案](HSK翻译练习-独立模块接口方案.md)、[共用题库方案](HSK练习-共用题库方案.md)（本文修正其中三处过时结论，见 §9.1）

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
| 5 | 板块配置改用新表 `practice_module_part_config`，支持**板块级开关**；两张旧行式表退场 |
| 6 | `practice_record` 删 2 列、启用 1 列（题目快照） |

**不覆盖**：口语评测链路（仅补版本过滤）、翻译自动评分（P2）、`exam-service` / `manage`（一行不动）、首页视觉还原（见首页设计方案）。

### 1.3 术语

| 术语 | 说明 |
|---|---|
| 版本 | 仅两个合法值：`HSK2.0` / `HSK3.0` |
| 等级编码 | `HSK1`…`HSK6`、`HSK7-9`（**不是 `HSK7`**） |
| 模块映射 | `SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` / `SEC_SPEAK` / `SEC_SPEAKING` / `SEC_TRANSLATION` |
| 板块 | 一张卷里的一段（如「听力第 2 部分」），配置落 `practice_module_part_config`，题量由 `question` 现算 |

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
   │     ├─ 题库（只读）：exam_paper（含 deleted_prac 卷级上下架）/ question / question_group
   │     ├─ 模块配置：practice_module_level_config（模块开关 / 能力描述 / 时长）
   │     ├─ 板块配置：practice_module_part_config（板块名三语 / 题型 / 板块开关）★新增
   │     ├─ 等级字典：hsk_level_config
   │     ├─ ID 注册表：practice_paper_structure（5 列，仅 ID 映射，退场中）
   │     └─ 作答：practice_record / practice_answer / practice_report
   │              writing_*（翻译复用）
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

1. **版本上下文只作用在目录层。** 作答链路拿 `(paperId, section)`（听力/阅读/翻译）或 `paperId + structureId`（写作/口语），版本已被二者唯一确定 → `attempt/answer/submit/report` 不加 `version`。改动面从 40+ 端点收敛到 16 个目录端点。
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

#### 3.1.2 模块注册表（`PracticeModuleCatalog`）

5 个模块元数据，`sortOrder` / `layout` / `badge` 按版本分别配置：

| moduleCode | sectionMapping | 名称 | icon | theme | badge 2.0 | badge 3.0 | sort 2.0 | sort 3.0 | 可用版本 |
|---|---|---|---|---|---|---|---|---|---|
| `LISTENING` | `SEC_LISTEN` | 听力 | headphone | `#5B6CF9` | — | — | 1 | 1 | 2.0 / 3.0 |
| `READING` | `SEC_READ` | 阅读 | book | `#34C759` | HOT | HOT | 2 | 2 | 2.0 / 3.0 |
| `WRITING` | `SEC_WRITE` | 写作 | pen | `#FFB020` | — | — | 3 | 3 | 2.0 / 3.0 |
| `TRANSLATION` | `SEC_TRANSLATION` | 翻译 | translate | `#8B5CF6` | 不出现 | NEW | — | 4 | **仅 3.0** |
| `SPEAKING` | `SEC_SPEAK` / `SEC_SPEAKING` | 口语 | mic | `#FF4D8D` | NEW | — | 4 | 5 | 2.0 / 3.0 |

`layout`：`HSK2.0 → GRID_2`（2 列网格）、`HSK3.0 → LIST`（1 列 5 行）。由接口下发，前端不写死。

#### 3.1.3 数据模型：两层

```
内容层（真相源，含卷级状态位）            配置层（模板 + 开关）
exam_paper                                practice_module_level_config
  version / level                        (version, level, section_mapping)
  deleted_prac ← 卷级上下架（运营开关）     enabled / total_question_count
  └─< question                            suggested_duration_minutes
       section_mapping ← 模块归属          ability_description × 3 语
       section         ← 部分号 1..N     practice_module_part_config ★
       type_id_mapping ← 题型编码         (version, level, section_mapping,
       layout          ← 渲染布局              section) ← 唯一键含板块号
  └─< question_group（材料/大题容器）      part_name × 3 / type_code
speaking_exam_paper（仅 2.0 口语）         answer_mode / standard_question_count
                                          enabled ← 板块开关
        │
        └──► 装配：part_config 当骨架 + question 补实际题量（缺行兜底）
                    ▼
             作答层：practice_record 用 (paper_id, section_mapping, section) 定位
```

| 层 | 表 | 承载 | 真相源 |
|---|---|---|---|
| 内容 | `exam_paper` / `question` | 版本、等级、**卷级上下架**、模块归属、部分号、题型、题干、**实际题量** | ✅ |
| 内容 | `question_group` | 板块内的材料 / 大题容器（1 板块 : N group），**不参与结构装配** | ✅ |
| 内容 | `speaking_exam_paper` / `_question` | 仅 2.0 口语（`level` 用 `Beginner/Intermediate/Advanced`） | ✅ |
| 配置 | `practice_module_level_config` | 版本 × 等级 × 模块：模块开关、标准总题量、时长、能力描述三语 | ✅ |
| 配置 | **`practice_module_part_config`** | 版本 × 等级 × 模块 × **板块**：名三语、题型、作答模式、标准题量、**板块开关** | ✅ |
| 作答 | `practice_record` / `practice_report` / `writing_*` | 练习记录 | 只引用上层 |
| 退场 | `practice_paper_setting` | 卷级运营态，**已被 `exam_paper.deleted_prac` 完整替代**（§3.2.7） | — |
| 退场 | `practice_paper_structure` / `practice_part_setting` | 板块模板的卷级投影（1201+1201 行），**仅供 `structureId` 映射** | ⚠️ |

> **一句话**：`question` 去重出「有哪些板块」，`part_config` 给「板块叫什么、能不能练」，`exam_paper.deleted_prac` 给「哪些卷能练」，`level_config` 给「哪些模块开放」。中间那三张表都没有独有信息。

#### 3.1.4 业务规则（落进代码的 14 条）

| # | 规则 | 落点 |
|---|---|---|
| R1 | `version` 只有两个合法值，缺省 2.0，非法 → 400 | `PracticeVersion.of` |
| R2 | `HSK7-9` 是一个等级，数值 `7`；禁止裸 `parseInt(levelCode)` | `PracticeLevelCode` |
| R3 | `exam_paper.level` 两库取值不一致（TEST `"7"` / PROD `"7-9"`），查询必须 `IN (候选集)` | `PracticeLevelCode.dbLevels` |
| R4 | 翻译仅 3.0；2.0 调 `/translation/**` 返回空数组 / 空对象，**不报 404**（前端据此置灰） | `TranslationCatalogServiceImpl` |
| R5 | 口语按版本分流读源：2.0 → `speaking_exam_paper`，3.0 → `exam_paper` + `SEC_SPEAKING`；**不合并、不去重** | `SpeakingCatalogServiceImpl` |
| R6 | 目录只下发题数 > 0 的等级 / 卷 / 板块 | 各 Catalog Service |
| R7 | 板块配置只存一处：名称/题型/顺序/开关只写 `practice_module_part_config`，禁止回写 `structure` / `part_setting` / `parts_config` | Code Review 卡点 |
| R8 | 实际题量必须现算：`standard_question_count` 是标准值，下发前被 `question` 计数覆盖 | 各 Catalog Service |
| R9 | 禁止 join 两张退场表取展示字段，`practice_paper_structure` 仅用于 `structureId` 映射 | Code Review 卡点 |
| R10 | `practice_record` 只认三元组 `(paper_id, section_mapping, section)`，不得再写 `structure_id` | 各 Record Service |
| R11 | 卷级上下架只认 `exam_paper.deleted_prac`：`0` = 可练，`非 0` = 下架。**列表、详情、开始作答三条路径必须都判**，任一处漏判就是下架卷可直达 | 各 Catalog / Record Service |
| R12 | 卷状态只写一处：`deleted_prac` 在 `exam_paper` 上是整卷级，跨 2~3 个模块同时生效，禁止再引入任何模块级卷状态 | Code Review 卡点 |
| R13 | 板块开关只影响「新练习下发哪些板块」：不得删题、不得改 `question.deleted`、不得过滤历史 `question_ids` 快照 | Catalog / Record Service |
| R14 | 配置缺行不阻塞目录：以 `question` 的 `section` 为主、配置为辅，缺行用 `第{section}部分` 兜底并视为开放 | 各 Catalog Service |

---

### 3.2 数据库设计

#### 3.2.1 表的处置

| 表 | TEST 行数 | 处理 | 说明 |
|---|---|---|---|
| `exam_paper` | 136 卷 | ✅ 零改（PROD 需补 `deleted_prac` 列） | `version` 管版本、`level` 管等级、**`deleted_prac` 管卷级上下架** |
| `question` | 万余 | ✅ 零改 | `section_mapping` 定模块、`section` 定部分号、`type_id_mapping` 定题型 |
| `question_group` | — | ✅ 零改 | 翻译两个大题组已在；不参与结构装配 |
| `speaking_exam_paper` / `_question` | 33 | ✅ 零改，仅 2.0 用 | 3.0 口语走 `exam_paper`（R5） |
| `practice_module_level_config` | 49 | ✅ 保留，删 `parts_config` 列 | 模块级配置 |
| **`practice_module_part_config`** | **132** | ✅ **新建** | 板块级配置 + 板块开关 |
| `practice_paper_setting` | 205 | ⚠️ **退场 → 由 `exam_paper.deleted_prac` 替代** | 对真实卷只保留「在不在练习里」一个信息（§3.2.7） |
| `hsk_level_config` | 13 | ✅ 零改 | 等级三语名称 |
| `practice_paper_structure` | 1201 | ⚠️ 退场 → 5 列 ID 注册表 | `id` 仍被 3 张作答表引用（§3.2.6） |
| `practice_part_setting` | 1201 | ⚠️ 退场 → 停写 | 与 structure 1:1，信息已并入新表 |
| `practice_record` | 963 | ⚠️ 瘦身：删 2 列 / 启用 1 列 | §3.2.5 |
| `practice_report` | 477 | ⚠️ 瘦身：删 `structure_id` | 有 `practice_record_id` 可回溯 |
| `writing_attempt` / `speaking_attempt` | 217 / 283 | ⏳ P2 | 缺部分号，需先补两列 |
| `practice_question_option_pool` | 2505 | ⏳ P2 | 数据可推但自身不完整（§3.2.6） |

#### 3.2.2 新增表 `practice_module_part_config`

```sql
CREATE TABLE `practice_module_part_config` (
  `id`                      bigint       NOT NULL COMMENT '板块配置ID（雪花ID，不自增）',
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
  `answer_mode`             varchar(20)  NOT NULL DEFAULT 'SINGLE' COMMENT '作答交互：SINGLE/MATCH/ORDER/RECORD/TEXT',
  `standard_question_count` int          NOT NULL DEFAULT '0' COMMENT '标准题量；下发前必须被 question 实际计数覆盖',
  `sort_order`              int          NOT NULL DEFAULT '0' COMMENT '展示顺序',
  `enabled`                 tinyint      NOT NULL DEFAULT '1' COMMENT '板块开关：0关闭，1开放',
  `deleted`                 int          NOT NULL DEFAULT '0' COMMENT '逻辑删除标记：0正常，1删除',
  `created_by`              bigint                DEFAULT NULL COMMENT '创建人ID',
  `update_by`               bigint                DEFAULT NULL COMMENT '更新人ID',
  `created_time`            bigint                DEFAULT NULL COMMENT '创建时间',
  `updated_time`            bigint                DEFAULT NULL COMMENT '修改时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_module_part` (`version`,`level`,`section_mapping`,`section`) USING BTREE,
  KEY `idx_part_on` (`version`,`level`,`section_mapping`,`enabled`,`sort_order`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
  COMMENT='练习板块级配置表（等级级模板 + 板块开关）';

-- 主表随之收窄
ALTER TABLE `practice_module_level_config` DROP COLUMN `parts_config`;
```

**字段口径**

| 字段 | 口径 | 依据 |
|---|---|---|
| `id` | 雪花，不自增 | 与现网两张配置表一致 |
| `level` | `int`，与主表同类型 | 主表 `level` 就是 `int`，同类型才能无转换 JOIN |
| `type_code` | `varchar(64)` | 旧表实测最长 25 字符，与 `question.type_id_mapping` 同域 |
| `type_name_en/_vi`、`part_name_en/_vi` | `varchar(255)` | 旧表即 255，不收窄以免多语言扩写截断 |
| `answer_mode` | `varchar(20)` | 旧表即 20；实测取值 `SINGLE/MATCH/ORDER/TEXT/RECORD` |
| `standard_question_count` | 前缀 `standard_` | 把「这是标准题量、不是实际题量」写进列名，防 R8 被违反 |
| 唯一键 | 不含 `deleted` | 沿用现网 `uk_module_level` 风格；代价是软删后**不能重建同键**，需复用原行或物理清理 |

> 🔴 **`level` 的类型桥**：`exam_paper.level` 是 `varchar`（TEST `'7'` / PROD `'7-9'`），主表 `level` 是 `int`。新表是主表子表，**必须跟 `int`**：读侧 `exam_paper.level IN ('7','7-9')` 归档到 `level = 7`；写侧永远写 `7`，不要试图把 `'7-9'` 塞进 `int`。若把新表定成 `varchar`，与主表就是跨类型 JOIN，索引失效。

**`total_question_count` 本次不删**：TEST 46/46 行它等于 `SUM(parts.questionCount)`，看着纯派生；但 PROD 有 15 行没有板块配置，它是这些模块唯一的题量来源。等补齐且 SUM 校验一致后再评估（P2）。

#### 3.2.3 板块配置迁移（`sortOrder` → `section`）

源：`practice_module_level_config.parts_config` 的 JSON 数组元素，键固定 8 个：
`partName / partNameEn / partNameVi / typeName / typeNameEn / typeNameVi / sortOrder / questionCount`。

| 情况 | 行数（TEST） | 迁移口径 |
|---|---|---|
| `sortOrder` 集合 == `question.section` 集合 | 38 | `section = sortOrder`，脚本批量，零人工 |
| `SEC_SPEAK`（2.0 L1–L3、3.0 L3–L6、3.0 L7） | 8 | 人工核对后写入（见下） |
| `parts_config` 为空 | 3（TEST）/ 15（PROD） | 不生成明细行，等数据补齐 |

- `type_code` 取同板块 `question.type_id_mapping`；`answer_mode` 沿用旧 `practice_part_setting.answer_mode`（按 `paper_id + section_mapping + section_code` 定位），缺失时按题型字典补。
- **2.0 口语无法从内容推导**：`speaking_exam_paper_question` 没有 `section` 列（只有 `number` / `question_group`），板块划分只能来自配置 → 必须显式存 `section`。
- **3.0 口语编码需先统一**：TEST 里 `SEC_SPEAK`（5 行配置，L3–L7）与 `SEC_SPEAKING`（1 行，L7）并存，而 `question` 里 3.0 的 `SEC_SPEAK` **0 题**。迁表前统一到 `SEC_SPEAKING`，否则写出 3 行永久孤儿。

示例（翻译）：原 `parts_config` 元素

```json
{"partName":"第一部分","typeName":"笔译","sortOrder":1,"questionCount":2,
 "partNameEn":"Part 1","partNameVi":"Phần 1","typeNameEn":"Written Translation","typeNameVi":"Biên dịch viết"}
```

对应新表一行

```sql
INSERT INTO practice_module_part_config
  (version, level, section_mapping, section, part_name, part_name_en, part_name_vi,
   type_code, type_name, type_name_en, type_name_vi, answer_mode,
   standard_question_count, sort_order, enabled)
VALUES ( 'HSK3.0', 7, 'SEC_TRANSLATION', 1, '第一部分', 'Part 1', 'Phần 1',
         'translation_written', '笔译', 'Written Translation', 'Biên dịch viết', 'TEXT',
         2, 1, 1);
```

#### 3.2.4 目录装配（读时装配，不写中间表）

```sql
-- ① 模块开关（一版本×模块 = 等级数行）
SELECT level, section_mapping, enabled, total_question_count, suggested_duration_minutes
FROM practice_module_level_config
WHERE deleted = 0 AND version = ? AND section_mapping = ? [AND level = ?];

-- ② 板块骨架 + 板块开关
SELECT level, section, part_name, part_name_en, part_name_vi,
       type_code, type_name, answer_mode, standard_question_count, sort_order, enabled
FROM practice_module_part_config
WHERE deleted = 0 AND version = ? AND section_mapping = ? [AND level = ?]
ORDER BY level, sort_order;

-- ③ 卷列表（deleted_prac 即卷级上下架）
SELECT id, level, source, description, created_time
FROM exam_paper
WHERE deleted = 0 AND exam_type = 1 AND deleted_prac = 0
  AND version = ? AND level IN (?, ...)      -- 7-9 候选集（R3）
ORDER BY level, id;                          -- 原 setting.sort_order 与 id 升序 100% 等价

-- ④ 每卷每板块实际题量（按卷批量，勿逐卷查）
SELECT paper_id, section_mapping, CAST(section AS SIGNED) AS section_no, COUNT(*) AS actual_count
FROM question
WHERE deleted = 0 AND deleted_prac = 0 AND paper_id IN (...)
  AND (type_id_mapping IS NULL OR type_id_mapping <> 'example_question')
  AND section IS NOT NULL AND section <> ''
GROUP BY paper_id, section_mapping, section;
```

装配顺序（服务端内存）：
1. 以 ② 为骨架，按 `sort_order` 排序；缺行按 R14 兜底（用 ④ 的 `section` 生成 `第{section}部分`，视为开放）；
2. 用 ④ 的 `actual_count` **覆盖** `standard_question_count`；
3. `actual_count = 0` 的板块不下发（R6）；
4. 模块 `enabled = 0` → 整模块不下发，**不再求值板块**；
5. 板块 `enabled = 0` → 该板块不下发，历史记录不受影响（R13）；
6. `type_code` / `answer_mode` 直接取列值，不再回退字典猜题型。

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

前端改拿目录响应里的 `partCode`（= `section`）+ 卷 `id`。目录响应的 `structureId` 可保留一版标 `deprecated`，但服务端不再落库。

**`question_ids` 用法**

| 时机 | 动作 |
|---|---|
| `start` | 查该板块全部题目 ID → 排序 → 写入，`total_questions = JSON_LENGTH` |
| `resume` | 不重算，直接按记录里的 `question_ids` 拉题（题序不变） |
| `submit` | 只统计，不改 |
| 报告 | 以 `question_ids` 为准，不现查题库 → 题库改版后仍可复现 |

#### 3.2.6 退场表与 `structure_id`

| 表 | TEST / PROD | 有三元组 | 处置 |
|---|---|---|---|
| `practice_record` | 963 / 1364 | ✅ 全有 | P0 删 `structure_id` |
| `practice_report` | 477 / 1011 | 有 `practice_record_id` 可回溯 | P0 删 |
| `writing_attempt` | 217 / 284 | ❌ 仅 `paper_id + structure_id` | P2 补两列 |
| `speaking_attempt` | 283 / 473 | ❌ 同上 | P2 补两列 |
| `practice_question_option_pool` | 2505 / 1150 | ❌ 仅 `structure_id + question_id` | P2 改为按题目关联 |
| `writing_report` / `speaking_report` | 151 / 183 | 有 `attempt_id` | P2 |

`practice_paper_structure` 历史 ID 无法重算：`20…`（雪花）479 行、`70…` 608 行、`80…` 114 行；稳定公式只覆盖 248 / 1201（20.6%）。因此它的寿命绑定剩余 3 张表：

- **P0**：保留 5 列 ID 注册表（`id / paper_id / content_type / sort_order / version`），展示字段停写；新卷入库仍写这 5 列（`stableId('structure', paperId, content_type, section)`）。
- **P2**：3 张表补完部分号后 drop。

`practice_question_option_pool` 退场前置三件事：① 补 `reading_cloze` 缺失记录（TEST 90 / PROD 90）；② `pool_code` 去掉 `structureId`，改为 `{section_mapping}_{paperId}_{section}_{sha256(option_content)}`；③ 答题快照的 `optionPoolCode` 改为现算（现在由 `ReadingSnapshotSupport` 读表写入）。

#### 3.2.7 卷级上下架改由 `exam_paper.deleted_prac` 承担

`practice_paper_setting` 一行 = 一张卷，`exam_paper` 也是一行 = 一张卷，两者 `paper_id` 严格 1:1。它的三个开关在真实卷上**从未被使用**：

| 字段 | TEST | PROD | 真实卷上的使用情况 |
|---|---|---|---|
| `enabled = 0` | 2 行 | 5 行 | **全部是孤儿行**（`paper_id` 在 `exam_paper` 里不存在） |
| `visible = 0` | 0 行 | 0 行 | 从未使用 |
| `deleted = 1` | 31 行 | 0 行 | **全部是孤儿行** |

于是这张表对真实卷只剩下一个信息：**这一行存不存在**。而"存在 = 上架"这个语义，正是 `exam_paper.deleted_prac` 的语义（列注释即「练习是否使用」）。

**卷序也不是独有信息**：`sort_order` 在 TEST 7 个等级、PROD 6 个等级上都与 `id` 升序**完全一致**（逐等级比对，0 处不同），属纯冗余。

**收益**：库存表少一张；「缺行 = 下架」这个隐式、不可查询的语义消失，改为显式列值，运营能直接 `WHERE deleted_prac = 1` 查出现在下架了哪些卷，也能审计。

**代价**：放弃"可分享链接直达但不上列表"这一档（`enabled` 与 `visible` 的两级语义）。实测该能力从未被真实卷使用，且 C 端目前也没有对应的分享入口。

##### 迁移口径（有一个必须避开的陷阱）

```sql
-- PROD 当前没有这一列（D11）；加列的默认值会把 77 张下架卷全部放出来
ALTER TABLE exam_paper ADD COLUMN deleted_prac int NOT NULL DEFAULT '0' COMMENT '练习是否使用：0使用，非0下架';

-- 必须在同一批次内，把「当前无 setting 行」的卷标为下架，否则目录从 60 卷暴涨到 137 卷
UPDATE exam_paper p
SET p.deleted_prac = 1
WHERE p.exam_type = 1 AND p.deleted = 0
  AND NOT EXISTS (SELECT 1 FROM practice_paper_setting s WHERE s.paper_id = p.id);
```

- TEST 136 张卷全部有 setting 行 → 迁移后 `deleted_prac` 全为 0，**上架卷数不变**。
- PROD 137 张 `exam_type=1` 卷里 60 张有行、77 张缺行 → 迁移后 60 张可练，与现网一致（2.0 每级 10 张、3.0 全 0）。
- 孤儿行 69（TEST）/ 56（PROD）随表退场自然消失，无需单独清理（原 D12 关闭）。

##### 代码改动点（5 处）

| 位置 | 现状 | 改成 |
|---|---|---|
| `ListeningCatalogServiceImpl:65` | 已 `.eq(getDeletedPrac, 0)` | 不变 ✔ |
| `ReadingCatalogServiceImpl:120` | 已 `.eq(getDeletedPrac, 0)` | 不变 ✔ |
| `WritingCatalogServiceImpl:156` | 已 `.eq(getDeletedPrac, 0)` | 不变 ✔ |
| `PracticeCatalogBatchLoader:77` | 查 setting 三条件过滤 | 删除该查询，`visiblePaperIds` 直接用入参 |
| `ReadingRecordServiceImpl:179` / `WritingAttemptServiceImpl:225` | 用 `setting` 判准入 | 改判 `paper.getDeletedPrac() == 0` |
| `ReadingCatalogServiceImpl:131` / `SpeakingCatalogServiceImpl:167` / `WritingCatalogServiceImpl:167` | 按 `getSortOrder()` 排序 | 改 `id` 升序 |

> ⚠️ `SharedPaperEligibility.isEligible` 只判 `deleted = 0 && examType = 1`，**没有判 `deleted_prac`**。删表后若不补这一条，已下架卷仍可通过详情/开始作答接口进入（新缺陷 B-17）。

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
| 14–16 | GET | `/speaking/levels`、`/papers`、`/papers/{paperId}/parts` | 常量 + `SEC_SPEAK` 单映射 | 常量改参数；按版本分流读源（R5） |

> 统一约定：`version` 必须**同时**作为 `practice_module_level_config.version` 与 `exam_paper.version` 的条件，漏一处会出现「等级列表是 2.0、卷列表是 3.0」。

#### 3.3.3 首页聚合接口

```
GET /hsk/modules?version=HSK3.0
```

```json
{
  "version": "HSK3.0",
  "layout": "LIST",
  "header": "专项突破 · 听力/阅读/写作/翻译/口语",
  "modules": [
    { "moduleCode": "LISTENING", "sectionMapping": "SEC_LISTEN", "name": "听力",
      "nameEn": "Listening", "icon": "headphone", "theme": "#5B6CF9",
      "badge": null, "available": true, "disabledReason": null,
      "entryLevelCode": null, "sortOrder": 1,
      "progress": { "totalPapers": 15, "completedPapers": 2, "inProgressPaperId": "2104193520701620225" } },
    { "moduleCode": "TRANSLATION", "sectionMapping": "SEC_TRANSLATION", "name": "翻译",
      "badge": "NEW", "available": true, "disabledReason": null,
      "entryLevelCode": "HSK7-9", "sortOrder": 4,
      "progress": { "totalPapers": 1, "completedPapers": 0, "inProgressPaperId": null } }
  ]
}
```

| 字段 | 规则 |
|---|---|
| `layout` | `GRID_2` / `LIST`，前端据此切换，不写死 |
| `available` | `false` 时置灰 + Toast，不隐藏（保持卡片数稳定）。判定 = 存在 `enabled=1` 的配置行且至少一个等级有题 |
| `disabledReason` | 文案键：`MODULE_NOT_IN_VERSION` / `NO_CONTENT` / `LOAD_FAILED` |
| `entryLevelCode` | 非空表示跳过等级选择页直达卷列表（翻译固定 `HSK7-9`） |
| `badge` | 按版本配置，P1 改后台可配 |
| `progress` | 未登录恒为 `{0,0,null}`；`paperId` 一律 String |

**服务端执行顺序**（SQL ≤ 5 次，与模块数无关）：
1. 解析 `version` → 2. 取模块元数据（按版本过滤 + 排序）→ 3. 批量查 `level_config` 得各模块可用等级 → 4. 批量查 `exam_paper` 统计 `totalPapers`（题数 0 的卷剔除）→ 5. 带 `userId` 时批量查进行中 / 已完成记录 → 6. 按 `sortOrder` 返回。

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

**统一前置校验**（每个封装方法第一行）：`structureRegistry(structureId).content_type == "SEC_TRANSLATION"`，否则 400 `SECTION_MAPPING_MISMATCH`。这是防串号的唯一屏障。

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
| C 端 | 只读，按 `enabled` 过滤，**不暴露开关字段** | 既有 16 端点，零新增 |
| 运营端（板块） | 增删改板块配置行，改 `enabled` 即开关板块 | `GET /hsk/module-config/parts?version=&level=&sectionMapping=`、`PATCH /hsk/module-config/parts/{id}` |
| 运营端（卷） | 改 `exam_paper.deleted_prac`（0 上架 / 非 0 下架），整卷生效 | 沿用题库管理侧现有卷编辑能力，**本次不新增接口** |
| 本次不做 | 批量上下架、板块级灰度、按用户差异化 | — |

> C 端响应结构不变（`parts[]` 仍只有 `partCode / partName×3 / typeCode / answerMode / questionCount`），保证 2.0 现网响应可逐字段 diff。

---

### 3.4 四级开关与求值顺序

| 级 | 开关 | 粒度 | 关掉之后 |
|---|---|---|---|
| L1 版本 | 前端选择 / `exam_paper.version` | 版本 | 整版不出现 |
| L2 模块 | `practice_module_level_config.enabled` | 版本×等级×模块 | 整卡消失，**不再求值下级** |
| L3 卷 | `exam_paper.deleted_prac`（0 可练 / 非 0 下架） | 卷 | 不在列表、详情与作答均拒绝 |
| L4 板块 | `practice_module_part_config.enabled` | 版本×等级×模块×板块 | 该板块不下发，新练习不含其题目 |

必须**自上而下短路**：L2 关 → 返回 `[]`，不查板块。

四者正交，实测佐证：「`level_config` 说开但 0 张卷在架」的组合 PROD 5 组、TEST 11 组（口语卷在 `speaking_exam_paper`、写作 L1–L2 被关）。

**关闭板块后历史记录**：已有 `question_ids` 快照不受影响，仍可回看、出报告（板块标注「已关闭」）；新开练习不再下发该板块题目。不要把「关闭」实现成删题或过滤快照，否则历史报告凭空少题。

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
POST /translation/attempts/start {paperId, structureId}
 → requireAuthenticatedAppUserId（仅委托）
 → 薄封装校验 section_mapping == SEC_TRANSLATION
 → WritingAttemptServiceImpl#start
     ├─ requirePaper：卷有效 + exam_type=1 + 上架 + level ≥ 3
     ├─ validatePart：contentType ∈ {SEC_WRITE, SEC_TRANSLATION} 且 == sectionMapping
     ├─ 已有 IN_PROGRESS → 直接返回（幂等）
     └─ 新建 attempt，快照 paperVersion / sectionVersion / questionSetVersion
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
| 400 | `SECTION_MAPPING_MISMATCH` | `structureId` 不属于该模块 |
| 404 | `TRANSLATION_NOT_IN_VERSION` | 2.0 调翻译写链路（目录接口返回空数组不报错） |
| 409 | `TRANSLATION_NOT_SCORABLE` | 翻译交卷但无评分策略（P0 不报错，仅 P1 使用） |

数据异常（`parseInt("7-9")` 一类）本次要消灭：全部改走 `PracticeLevelCode`，改不净的包成 500 `QUESTION_DATA_INVALID`。

---

## 5. 安全

| 项 | 措施 |
|---|---|
| 参数注入 | `version` / `levelCode` 走白名单枚举；SQL 全部参数绑定 |
| 越权 | `attempt` 校验 `userId` 归属；翻译薄封装必须校验 `section_mapping`，否则可用写作 `structureId` 串号 |
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
9. 拿写作 `structureId` 打翻译 → 400；拿翻译 `structureId` 打写作 → 仍 404（写作侧不放宽）。
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
20. `deleted_prac = 1` 的卷 → **列表不出现、详情报 404、开始作答报 404**（三处都测，B-17）。
21. 卷级上下架与模块/板块开关互不干扰：卷下架但模块开 → 该等级仍有其他卷；模块关但卷上架 → 整卡消失。

**板块开关**
22. 关 `HSK2.0/L1/SEC_LISTEN/section=2` → 目录只剩另外三个板块，其题量名称题型不受影响。
23. 新开练习不含 section=2 的题；历史记录仍可打开、报告题数不变（R13）。
24. 关整模块 → 整卡消失，不再受板块开关影响（短路顺序）。
25. 删掉某板块配置行 → 该板块仍出现，名称为 `第N部分`，不报错（R14）。
26. 双写期：改一次板块名两侧都变，连续 100 次随机变更后 diff 为空。
27. 并发改同模块不同板块 → 两条都生效，无覆盖丢失。

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
| 元素补 `section` + `enabled` 两键 | 可行但不彻底：无唯一约束、`enabled` 写成 `"0"` 也存得进、审计只到整行、SQL 只能 `JSON_EXTRACT` |
| **拉平成 `practice_module_part_config`** | ✅ 唯一键防重、开关是列、`UPDATE ... WHERE section=2` 只锁一行 |
| 单表 `section=0` 表示模块行 | ❌ 一半字段永远 NULL，接口处处判 `section=0` |
| 不拆，靠前端隐藏 | ❌ 题目仍下发，用户仍能练到 |

**行数不增长**：新表挂 `(version, level, section_mapping, section)`，132 行封顶，由等级数决定，不随卷数膨胀；旧 `practice_part_setting` 挂 `structure_id`（卷级），1201 行且随题库扩容增长。这是**降粒度**，不是复活旧表。

### 9.6 `practice_record` 用三元组、删 `practice_name`

`structure_id` 是 `(paper_id, section_mapping, section)` 的代理键（`selectByStructure` 内部即三元组 JOIN），而 `practice_record` 三列本来就齐备，是第 4 份等价信息；实测新旧路径取题数 PROD 1343/1343 零差异。`practice_name` 与 `section_name` 100% 一致，纯复制。

「不能做唯一键」不是保留理由：重复组（TEST 131 / PROD 106）确实存在，但业务语义始终是取最新一条，从不需要唯一约束。

代价：`writing_attempt` / `speaking_attempt` 这次不动，**接口风格短期不一致**（听力/阅读/翻译用 `section`，写作/口语仍用 `structureId`），P2 统一。

### 9.7 卷级上下架用 `exam_paper.deleted_prac`，`practice_paper_setting` 退场

两个候选位置，只有一个是对的：

**❌ 不能并入 `practice_module_level_config`** —— 粒度 1:N 反向。PROD 的 HSK2.0 每级 20~21 张卷只上架 10 张（6 级整齐各 10，刻意控量），`enabled` 是 `tinyint`，没有取值能表示"一半开"；且一张卷横跨 2~3 个模块（TEST 43 张 2 模块、92 张 3 模块），写进模块级配置要写多份，必然分叉。TEST 每级全上架，只看 TEST 会误判。

**✅ 并回 `exam_paper` 是对的** —— `paper_id` 与 `exam_paper.id` 严格 1:1，粒度天然匹配；`deleted_prac` 本来就是练习侧专用列（注释「练习是否使用」），不是为本次改造新塞的字段，不存在"污染考试侧"的问题（CSCA 的 `exam_type=2` 卷同样带这一列且全为 0）。

**为什么这张表现在是空的**：三个开关在真实卷上 100% 全开（`enabled=0` 的 2/5 行、`deleted=1` 的 31 行**全部是孤儿行**），`sort_order` 也与 `id` 升序完全一致。它对真实卷只剩「行存不存在」一个信息，而这个信息 `deleted_prac` 一个列就能表达，还能查、能审计（§3.2.7）。

**代价**：放弃"可直达但不上列表"的两级语义，实测从未使用。

### 9.8 3.0 口语读 `exam_paper`，不读 `speaking_exam_paper`

3.0 设计前提是「一张卷含听读写译说」，而 2.0 口语是独立考试（`Beginner/Intermediate/Advanced` 三档，与 HSK1–6 不同构）。实测 3.0 口语在两边同源双录（number 87–91 一致），`speaking_exam_paper` 的 3.0 卷在 PROD 为 0。故 3.0 只认 `exam_paper` + `SEC_SPEAKING`，2.0 那张表退回专用。TEST 的 5 张 3.0 口语卷冻结为历史数据。

---

## 10. 落地分期

| 期 | 范围 | 前置 | 完成判据 |
|---|---|---|---|
| **P0-a** | 修三条存量缺陷（附录 A：B-01/B-02/B-03） | — | TEST 听力 intro 不 500；PROD 听力列表不混版；HSK7-9 写作可开练 |
| **P0-b** | 四个支撑类：`PracticeVersion` / `PracticeLevelCode` / `PracticeModuleCatalog` / `PracticeTypeRegistry`（题型字典 `typeCode → answerMode`） | — | 单测覆盖 `HSK7-9`、`'7-9'`、非法版本、5 种 `answerMode` |
| **P0-c** | 16 个目录端点加 `version` | P0-b | 2.0 全链路零回归 |
| **P0-c2** | **新建 `practice_module_part_config` + 迁数据**：DDL → 从 `parts_config` 展开（38 行直转、8 行口语核对）→ 补 `type_code`/`answer_mode` → 先统一 `SEC_SPEAK`→`SEC_SPEAKING` → **双写过渡** | P0-b | 132 行入库；行数与 `SUM(JSON_LENGTH(parts_config))` 相等；旧读路径响应零变化 |
| **P0-c3** | 板块开关接口 `PATCH /hsk/module-config/parts/{id}` | P0-c2 | 关板块后目录不出现，新练习不下发其题目，历史记录不受影响 |
| **P0-d** | 聚合接口 `GET /hsk/modules` | P0-c | 2.0 四卡 / 3.0 五卡，布局角标正确 |
| **P0-e** | **重写 `PracticeCatalogBatchLoader`**：从「查 structure + part_setting」改为「读板块配置 + 算题量」 | P0-c2 | 2.0 四模块目录与现网**逐字段一致**；结构表停写 |
| **P0-f** | 翻译目录 4 + 写链路 6 + `validatePart` 放宽 | P0-e | 笔译/口译都能练到交卷；写作 `structureId` 打翻译 → 400 |
| **P0-g** | **PROD 数据补全**：`deleted_prac` DDL **+ 把 77 张无 setting 行的卷标 1**（同一批次，见 §3.2.7 陷阱） → 28 行模块配置 → 15 行板块配置 → `layout` 回填 → level 收敛。3.0 正式放开时再把该版本 15 张卷改回 `deleted_prac = 0` | DDL 最先；五闸门 + DRY-RUN + 备份 | 目录卷数不变（2.0 每级 10 张、3.0 全 0）；3.0 放开后五卡有数据；`layout` 非空率 100%；板块配置 21/21 |
| **P0-h** | `practice_record` 瘦身：删两列、重建索引、7 处 Mapper 改三元组、接口改 `(paperId, section)` | P0-e | 抽 100 条历史记录新旧路径取题 ID 一致；`EXPLAIN` 走新索引；新记录 `question_ids` 非空且长度 = `total_questions` |
| **P0-i** | **`practice_paper_setting` 退场**：删 `PracticeCatalogBatchLoader` 里的 setting 查询；`ReadingRecordServiceImpl` / `WritingAttemptServiceImpl` 的准入改判 `deleted_prac`；3 处 `getSortOrder()` 排序改 `id`；`SharedPaperEligibility` 补判 `deleted_prac`（B-17）；最后 `DROP TABLE practice_paper_setting` | P0-g 数据已铺好 | 4 模块目录与现网逐字段一致；下架卷在列表/详情/作答三处均不可达；表已 drop |
| **P0-j** | 删列收尾：`DROP COLUMN parts_config` | P0-e/g 稳定运行 ≥ 1 版本，双写比对连续一致 | 无代码/脚本读取该列 |
| P1 | 偏好表加 `version`；ID 改 String；`dataVersion` ETag；角标后台可配；补 `TRANSLATION_WRITTEN` 策略；collation 对齐；B-09 修正；板块级时长/满分/提示语加列 | P0 上线观察 | — |
| P2 | drop `practice_paper_structure`（先给 3 表补部分号回填）；`option_pool` 三步退场；口译 ASR + 自动评分 | P0-h 稳定 + 479 条雪花 ID 核对完 | — |

> 🔴 **最大风险点是 P0-e**：唯一会改变 2.0 现网行为的改造（目录换源）。验收法：同一批请求（4 模块 × 版本 × 等级），新旧响应 **JSON 逐字段 diff 必须为空**，建议先存旧实现快照。
>
> **双写是安全阀**：`parts_config` 列在 P0-i 前一直保留，任何一侧出错可立刻切回旧读路径，不需要恢复备份。
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
| B-10 | 3.0 口语在 `question` 与 `speaking_exam_paper` 双录（同源） | 题库数据 | 改一处不改另一处会同题不同内容 | 🟢 低（已冻结一侧） |
| B-11 | `practice_paper_setting` 孤儿行：TEST 69（38 活跃 + 31 软删）/ PROD 56（全活跃），占全表 34% / 48% | 运营表数据 | 现网被 `IN` 天然过滤；**退场后自然消失，无需清理** | 🟢 低（已被 P0-i 覆盖） |
| B-12 | `practice_paper_setting` 三个开关在真实卷上零使用：`enabled=0` 的 2/5 行、`deleted=1` 的 31 行**全是孤儿行**，`visible` 全表为 1 | 运营表数据 | 这张表对真实卷只剩「行是否存在」；`sort_order` 也与 `id` 升序完全一致 → 由 `deleted_prac` 替代（§3.2.7） | 🟢 低（P0-i 退场） |
| B-13 | 共享选项池缺记录：`reading_cloze` TEST 90/690 无池记录、PROD 90/90 全无；`pool_code` 内嵌 `structureId` | `practice_question_option_pool` | 选词填空退化成每题重复渲染 6 个选项 | 🟡 中（P2 前置） |
| B-14 | `question.layout` PROD 缺失 47.7%（6469/13574），TEST 100% | `question` 数据 | 4 处代码依赖它渲染 → 近一半题交互错乱 | 🔴 高（P0-g 回填） |
| B-15 | 3.0 口语编码分裂：`SEC_SPEAK`（5 行）与 `SEC_SPEAKING`（1 行）并存，`question` 里 3.0 的 `SEC_SPEAK` 0 题 | 配置数据 | 拆表会写出 3 行永久孤儿 | 🟡 中（P0-c2 前统一） |
| B-16 | PROD `HSK2.0 L2 SEC_LISTEN` 的 `total_question_count=35`，但四板块求和 40 | 配置数据 | 进度条分母口径不一 | 🟢 低（拆表时以实际计数为准） |
| B-17 | `SharedPaperEligibility.isEligible` 只判 `deleted` + `examType`，**不判 `deleted_prac`** | 4 处调用（阅读/写作 Catalog、Record） | 卷在列表被过滤、但详情/开始作答可进入 → 下架卷可直达。删 `setting` 后必须先补这一条 | 🔴 高（P0-i 必改） |

> B-01 / B-02 / B-03 **不等本次改造上线就该修**：前两条现网已发生，第三条是 3.0 放开的必炸点。

---

## 附录 B：数据缺口（P0 阻塞项）

| # | 缺口 | TEST | PROD | 处置 |
|---|---|---|---|---|
| **D3** | `exam_paper.level` 的 7-9 取值不一致 | `"7"` | `"7-9"` | 代码用候选集 `IN ('7','7-9')`（R3） |
| **D4** | 3.0 的模块配置行 | 28 行 | **0 行** | 补 28 行 + 对应板块明细行 |
| **D11** | `deleted_prac` 列不存在 | 5 表已有 | **5 表全缺** | 上线前 DDL，**最先做**；必须与「77 张无 setting 行卷标 1」同一批次（§3.2.7） |
| **D13** | 3.0 卷全部未上架 | 15/15 | **0/15** | 迁移时随缺行规则标 `deleted_prac = 1`；3.0 正式放开的那一版改回 `0`（不是新增 setting 行） |
| **D14** | `question.layout` 大面积缺失 | 100% 有值 | **47.7% NULL** | 按 TEST 同题回填 |
| **D15** | 2.0 的板块配置只有听力有值 | 46/49 | **6/21**（阅读 6 / 写作 6 / 口语 3 行全 NULL） | 与 D4 同批，按题库 `question.section` 生成 |
| D5 | `writing_evaluation_policy` 无 `TRANSLATION_WRITTEN` | 缺 | 缺 | P0 不入队，直接 `UNAVAILABLE`；P1 补 |
| D6 | 翻译 4 题 `answer` 全为 `(略)` | 4/4 | 4/4 | 题库补参考译文（P1） |
| D8 | 3.0 卷数偏少 | 15 卷 | 15 卷 | 题库导入（已知） |
| D10 | `practice_paper_structure` 的 collation 为 `utf8mb4_unicode_ci`，与其余表不一致 | 同 | 同 | 主路径不再 join 该表 → P1 对齐；仍需查时 `CONVERT ... COLLATE utf8mb4_0900_ai_ci` |
| ~~D12~~ | ~~`practice_paper_setting` 孤儿行~~ | ~~69~~ | ~~56~~ | **已关闭**：表退场，孤儿行随之消失 |

> 遗留 P1：板块级时长 / 满分 / 提示语（同表加列即可）。

---

## 附录 C：关键实测基线（2026-11-10）

| 项 | TEST | PROD |
|---|---|---|
| `exam_paper`（`exam_type=1`）2.0 / 3.0 | 121 / 15 卷 | 122 / 15 卷 |
| 实际上架卷数 | 136（每级全上架） | **60**（2.0 每级 10 张、3.0 全 0） |
| `practice_paper_setting` 真实卷上的开关使用 | `enabled=0`/`visible=0`/`deleted=1` **均为 0**（非全开行全是孤儿行） | 同 |
| `setting.sort_order` == `id` 升序 | 7/7 等级一致 | 6/6 等级一致 |
| `practice_paper_setting` 孤儿行 | 69 / 205（34%） | 56 / 116（48%） |
| `practice_module_level_config` 2.0 / 3.0 | 21 / 28 行 | 21 / **0** 行 |
| `parts_config` 非空行 / 元素总数 | 46/49、132 个 | 6/21、20 个 |
| `parts[].sortOrder` == `question.section` | 38/46 行（8 行是 2.0 口语） | 6/6（只有听力有值） |
| `total_question_count` == `SUM(parts)` | 46/46 | 5/6（L2 听力 35≠40） |
| `parts_config` 是否含 `section` / `typeCode` / `answerMode` | **均不含** | 同 |
| `deleted_prac` 列 | 5 表已有 | **5 表全缺** |
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
