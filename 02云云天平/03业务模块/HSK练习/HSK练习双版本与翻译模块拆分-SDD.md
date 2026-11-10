# HSK 练习双版本（2\.0 / 3\.0）与翻译模块拆分 · 软件设计文档

> 定位：本文档回答【怎么做】——HSK 练习如何同时支撑 2.0 / 3.0 两套大纲，以及「翻译」如何从写作模块里拆成独立入口。
> 服务：`practice-service`（网关前缀 `/api/practice`）
> 依据：2026-11-10 双版本首页 UI 截图（2.0 四宫格 / 3.0 五行列表）+ 代码基线 + TEST / PROD 实测
> 文档版本：v1.3｜更新日期：2026-11-10｜状态：**待评审**
> 前置：[HSK练习模块首页-设计方案](HSK练习模块首页-设计方案.md)、[HSK翻译练习-独立模块接口方案](HSK翻译练习-独立模块接口方案.md)、[HSK练习-共用题库方案](HSK练习-共用题库方案.md)
> 🔴 **本文纠正前置文档的三处过时结论**，见 §9 ADR-06
> 🔴 **v1.2 口径（架构简化）**：**`practice_paper_structure` 与 `practice_part_setting` 退场**，板块配置只保留 `practice_module_level_config` 一张表（用其 `parts_config` JSON）。内容侧不新建任何表，翻译 4 题、口语 3.0 的 5 题都已在 `question` 里，只是 `section_mapping` 归属不同。
> ⚠️ **`structure_id` 分层退出**：`practice_record`（963/1364 行）与 `practice_report` 本次**直接删列**，改用 `(paper_id, section_mapping, section)` 三元组；`writing_attempt` / `speaking_attempt` / `option_pool` 因缺部分号，P2 再改。详见 §3.2.7 / §3.2.8。
> 🔴 **v1.3 新增**：`practice_record` 删 `structure_id` + `practice_name`，**启用已存在但空着的 `question_ids` 作题目快照**；接口从 `structureId` 改为 `paperId + section`（ADR-11）。

---

## 1\. 概述

### 1\.1 文档目的

描述 HSK 练习「双版本并存 + 翻译独立入口」的技术落地方案，供开发、测试、评审使用，作为编码与改库依据。

### 1\.2 范围

**本文覆盖**

| # | 内容 |
|---|---|
| 1 | 练习目录层（等级 → 卷 → 板块）全面支持 `version` 入参，缺省 `HSK2.0` |
| 2 | 新增首页聚合接口 `GET /hsk/modules`，下发 5 张卡的顺序、布局形态、角标与可用性 |
| 3 | 翻译（`SEC_TRANSLATION`）从写作模块剥离为独立入口 `/translation/**` |
| 4 | 等级编码 `HSK7-9` ↔ 数字 `7` 的双向映射收口 |
| 5 | 存量 4 处硬编码版本常量、3 处 `level` 解析缺陷的修复 |
| 6 | 基于**既有 5 张题库表**的双版本隔离（`exam_paper.version`）与翻译/口语识别（`question.section_mapping`），零 DDL |
| 7 | **板块配置归并**：`practice_paper_structure` / `practice_part_setting` 退场，改由 `practice_module_level_config.parts_config` 承载（§3.2.6 逐字段证明） |
| 8 | HSK3.0 配置补全口径（PROD 的 28 行 `parts_config` 当前为 0） |

**本文不覆盖**

- 口语作答题的评测链路（`speaking_exam_paper_question` 副本表、ASR 评测）——沿用现状，仅补版本过滤
- 翻译的主观题自动评分（`ai-service` 未接翻译）——P2
- `exam-service` 考试侧、`manage` 题库管理侧——一行不动
- 首页 UI 的视觉还原（尺寸/颜色/动效）——见首页设计方案 §2

### 1\.3 术语与缩略词

| 缩写 | 全称 | 说明 |
|---|---|---|
| SDD | Software Design Document | 软件设计文档 |
| DO | Data Object | 数据库实体 |
| DTO | Data Transfer Object | 传输对象 |
| 版本 | HSK 大纲版本 | 仅两个合法值：`HSK2.0`、`HSK3.0` |
| 等级编码 | levelCode | `HSK1`…`HSK6`、`HSK7-9`（**注意不是 `HSK7`**） |
| 模块映射 | sectionMapping | `SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` / `SEC_SPEAK` / `SEC_SPEAKING` / `SEC_TRANSLATION` |
| 板块 | part | 一张卷里的一段（如「听力第 2 部分」），模板落 `practice_module_level_config.parts_config`，题量由 `question` 现算 |

---

## 2\. 总体设计

### 2\.1 业务目标

一份代码库同时服务两套 HSK 大纲：用户下拉切换 2.0 / 3.0 后，等级范围、模块数量、卡片顺序与布局全部随之变化，且**两套练习进度不得互相污染**。

### 2\.2 系统上下文

```
iOS / Android 客户端
        │  Authorization: Bearer <JWT>   X-Client-Type: APP   Accept-Language: zh|en|vi
        ▼
gateway  /api/practice/**  ──（未在白名单，全部要求登录）
        ▼
practice-service
        ├─► MySQL xuexitest
        │     ├─ 题库（只读）：exam_paper / question / question_group / question_shared_audio
        │     ├─ 板块配置（v1.2 唯一配置表）：practice_module_level_config（parts_config JSON）
        │     │                 辅：practice_paper_setting / hsk_level_config
        │     ├─ structureId 注册表：practice_paper_structure（5 列，仅 ID 映射，不存展示信息）
        │     └─ 练习作答：practice_record / practice_answer / practice_report
        │                  writing_attempt / writing_answer / writing_report（翻译复用）
        ├─► ai-service  http://ai-service:8083   （口语评测；翻译评分 P2）
        └─► system-service  /file/uploadVoice    （口译录音上传，前端直传后回传 URL）
```

> `practice-service` 无 Redis，无 Feign；跨服务只有「前端直传 system-service 拿音频 URL」这一条隐性依赖。

### 2\.3 架构方案

**分层**

| 层 | 包 | 职责 | 本次是否改 |
|---|---|---|---|
| Controller | `{listen,read,write,speak,trans}/*/controller` | 解析 `version` / `levelCode` / `userId`，不做业务 | ✅ 加参数 |
| Catalog Service | `*/service/impl/*CatalogServiceImpl` | 等级 / 卷 / 板块目录 + 进度聚合 | ✅ 版本化 |
| Attempt / Answer / Submit | `writing/*`、各模块 `*ServiceImpl` | 作答、保存、交卷、报告 | ⭕ 仅准入校验 |
| Domain Support | `core/support` | 目录装载、资格判定、新版本/等级值对象 | ✅ 新增 3 个类 |
| Mapper | `core/mapper` + XML | 数据访问 | ✅ 少量 SQL 加条件 |

**核心设计思路（四条）**

1. **版本上下文只作用在目录层。** 作答链路拿的是 `(paperId, section)`（听力/阅读，v1.3 起）或 `paperId + structureId`（写作/口语，P2 统一），版本已被这两者唯一确定，因此 `attempt/answer/submit/report` **一律不加 `version` 参数**。改动面从 40+ 端点收敛到 16 个目录端点。
2. **版本与等级编码收口成两个值对象。** 现状是 4 个模块各写一遍 `"HSK" + level` 和 `Integer.parseInt(code.replace("HSK",""))`，`HSK7-9` 必然踩坑（[附录 B](#附录-b存量缺陷清单)）。新增 `PracticeVersion`、`PracticeLevelCode`，全局只有它们能解析和格式化等级。
3. **翻译走「目录独立 + 作答复用」。** 目录接口 `/translation/**` 独立；写链路薄封装后委托既有 `Writing*Service`，不复制表、不复制评分。
4. **目录只下发「有题的节点」。** 沿用现有 `.filter(total > 0)` 语义并上提到 SQL：`question` 里没有对应 `section_mapping` 的等级/卷/板块不出现在响应中，空卷空板块在服务端消失。

### 2\.4 模块划分

| # | 子模块 | 职责 | 对应包 |
|---|---|---|---|
| 1 | 版本上下文 | 解析校验 `version`、等级编码双向映射、DB 等级候选集 | `core/support/PracticeVersion`、`PracticeLevelCode` |
| 2 | 模块注册表 | 5 个模块的编码/名称/图标/主题/角标/布局/版本适用范围 | `core/support/PracticeModuleCatalog` |
| 3 | 首页聚合 | 按版本装配 5 张卡 + 各自可用性 + 轻量进度 | `core/controller/HskModuleController` |
| 4 | 听力目录 | 等级→卷（内嵌）→板块 | `listening/**` |
| 5 | 阅读目录 | 等级→卷→板块 + 偏好 | `reading/**` |
| 6 | 写作目录 | 等级→卷→板块（**已按 `SEC_WRITE` 过滤，翻译不再混入**） | `writing/**` |
| 7 | 口语目录 | 等级→卷→板块（**按版本分流**：2.0 读 `speaking_exam_paper` / 3.0 读 `exam_paper`，ADR-07） | `speaking/**` |
| 8 | **翻译目录（新增）** | 等级→卷→板块（`SEC_TRANSLATION`） | `translation/**`（新建） |
| 9 | **翻译写链路（新增）** | 薄封装，委托 `Writing*Service` | `translation/**`（新建） |

---

## 3\. 详细设计

### 3\.1 领域模型

#### 3\.1\.1 值对象（新增，`core/support/`）

**`PracticeVersion`（枚举）**

| 枚举 | 字面量 | 说明 |
|---|---|---|
| `HSK2_0` | `"HSK2.0"` | 缺省值 |
| `HSK3_0` | `"HSK3.0"` | — |

行为：
- `of(String raw)`：null / 空 → `HSK2_0`；**严格大小写匹配**（不做 `trim().toLowerCase()`，`hsk3.0` 必须 400，否则误命中会掩盖前端 bug）
- 非法值 → `BusinessException(400, "PRACTICE_VERSION_INVALID")`

**`PracticeLevelCode`（静态工具）**

| 方法 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `parse(String code)` | `HSK1`…`HSK6`、`HSK7-9` | `1`…`7` | 非法抛 404 |
| `of(int level)` | `7` | `"HSK7-9"` | **唯一**的 level→code 出口 |
| `dbLevels(int level)` | `7` | `["7","7-9"]` | DB 侧 `exam_paper.level` 候选集，见 [D3](#32-数据库设计) |
| `parseDbLevel(String dbLevel)` | `"7"` / `"7-9"` | `7` | 从 `exam_paper.level` 反解，容错破折号 |

**`PracticeModuleCatalog`（常量）**

固化的 5 个模块元数据，`sortOrder` / `layout` / `badge` **按版本分别配置**：

| moduleCode | sectionMapping | name | nameEn | icon | theme | badge(2.0) | badge(3.0) | sort 2.0 | sort 3.0 | 可用版本 |
|---|---|---|---|---|---|---|---|---|---|---|
| `LISTENING` | `SEC_LISTEN` | 听力 | Listening | headphone | `#5B6CF9` | — | — | 1 | 1 | 2.0 / 3.0 |
| `READING` | `SEC_READ` | 阅读 | Reading | book | `#34C759` | HOT | HOT | 2 | 2 | 2.0 / 3.0 |
| `WRITING` | `SEC_WRITE` | 写作 | Writing | pen | `#FFB020` | — | — | 3 | 3 | 2.0 / 3.0 |
| `TRANSLATION` | `SEC_TRANSLATION` | 翻译 | Translating | translate | `#8B5CF6` | **不出现** | NEW | — | 4 | **仅 3.0** |
| `SPEAKING` | `SEC_SPEAK`（2.0）/ `SEC_SPEAKING`（3.0） | 口语 | Speaking | mic | `#FF4D8D` | NEW | — | 4 | 5 | 2.0 / 3.0 |

`layout`：`HSK2.0 → GRID_2`（2 列网格）、`HSK3.0 → LIST`（1 列 5 行）。由聚合接口下发，前端不写死。

#### 3\.1\.2 两层数据模型（内容层 / 配置层）

**结论先行：`practice_paper_structure` 与 `practice_part_setting` 在信息层面已经多余。** 它们承载的「板块名三语 / 题型名三语 / 顺序 / 题量」，已被 `practice_module_level_config.parts_config` 这个 JSON 数组**全覆盖**（键名逐一对得上，见 §3.2.6）。所以板块配置只需要**一张表**。

| 层         | 表                                                                              | 承载什么                                                                                   | 是否真相源                      |
| --------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- | -------------------------- |
| **内容层**   | `exam_paper` / `question` / `question_group`                                   | 版本、等级、模块归属（`section_mapping`）、题型编码（`type_id_mapping`）、部分号（`section`）、音频、题干、答案、**实际题量** | ✅ **唯一真相源**                |
| （口语分支）    | `speaking_exam_paper` / `speaking_exam_paper_question`                         | HSK**2.0** 口语卷与题（`level` 用 `Beginner/Intermediate/Advanced` 三档）                        | ✅ 2.0 口语唯一真相源              |
| **配置层**   | **`practice_module_level_config`**                                             | 版本 × 等级 × 模块：开关、标准题量、建议时长、能力描述三语、**`parts_config`（板块模板数组）**                            | ✅ **唯一配置表**                |
|           | `practice_paper_setting`                                                       | 卷级上下架（运营态）                                                                             | ✅ 运营                       |
| **作答层**   | `practice_record` / `writing_attempt` / `speaking_attempt` / `practice_report` | 练习记录                                                                                   | 只引用上层 ID                   |
| **（退场中）** | `practice_paper_structure` / `practice_part_setting`                           | 板块模板的**行式投影**（1201 + 1201 行，1:1 冗余）                                                    | ⚠️ 降级为 **ID 注册表**，见 §3.2.7 |

```
┌────────── 内容层（真相源）──────────┐    ┌──── 配置层（唯一配置表）────┐
│ exam_paper                          │    │ practice_module_level_config│
│   version / level / deleted_prac    │    │  (version, level, section)  │
│   ├─< question                      │    │  enabled                    │
│   │    section_mapping  ← 模块归属   │    │  total_question_count       │
│   │    section          ← 部分号 1-4 │    │  suggested_duration_minutes │
│   │    type_id_mapping  ← 题型编码   │    │  parts_config (JSON 数组) ★  │
│   │    layout            ← 渲染布局   │    │   ├ partName × 3 语         │
│   └─< question_group  (翻译大题包)   │    │   ├ typeName × 3 语         │
│ speaking_exam_paper (仅 2.0 口语)    │    │   ├ sortOrder               │
└───────────────┬─────────────────────┘    │   └ questionCount（标准）    │
                │  实际题量 + 实际题型        └──────────────┬──────────────┘
                └───────────────┬─────────────────────────┘
                                ▼
              装配：parts_config 当骨架，question 补实际题量
                                │
                                ▼
              GET /{module}/papers/{id}/parts（两处查询 + 内存拼装）
                                │
                                ▼
     作答层：practice_record 用 (paperId, section_mapping, section) 定位，无 structure_id
```

> 🔴 **一句话记住**：`exam_paper.version` 管版本、`question.section_mapping` 管模块归属、`practice_module_level_config.parts_config` 管板块模板——**这三样就够了，中间那两张行式表是历史包袱**。
> 翻译不需要新表（4 题已在 `question`）；口语 3.0 也不需要（5 题已在 `question`）。

> ⚠️ **`structure_id` 分层退出，不必一刀切**：
> - `practice_record`（963 / 1364 行）**自带完整三元组** `(paper_id, section_mapping, section)` → 本次**直接删 `structure_id`**（§3.2.8）；
> - `practice_report` 有 `practice_record_id` 可回溯 → 同步删；
> - `writing_attempt`（217）/ `speaking_attempt`（283）/ `option_pool`（2505）只存了 `paper_id + structure_id`，**没有部分号** → 需先加两列才能删，排在 P2；
> - 只有这最后 3 张表还在用 `structure_id` 时，`practice_paper_structure` 才需要留作 ID 注册表。详见 §3.2.7。

#### 3\.1\.3 业务规则（必须落进代码的 10 条）

| # | 规则 | 落点 |
|---|---|---|
| R1 | `version` 只有 `HSK2.0` / `HSK3.0` 两个合法值，缺省 `HSK2.0`，非法 → 400 | `PracticeVersion.of` |
| R2 | `HSK7-9` 是**一个**等级，数值 `7`；禁止对 levelCode 做 `parseInt` 裸解析 | `PracticeLevelCode` |
| R3 | `exam_paper.level` 在两库取值不一致（TEST `"7"` / PROD `"7-9"`），查询必须用 `IN (候选集)` | `PracticeLevelCode.dbLevels` |
| R4 | 翻译仅 `HSK3.0`；`version=HSK2.0` 调 `/translation/**` → 返回空数组 / 空对象，**不报 404**（前端据此置灰） | `TranslationCatalogServiceImpl` |
| R5 | 口语按版本**分流读源**：2.0 → `speaking_exam_paper`（`SEC_SPEAK`），3.0 → `exam_paper` + `question.SEC_SPEAKING`；**不合并、不去重**（详见 §3.2.2 冲突 1） | `SpeakingCatalogServiceImpl` |
| R6 | 目录只下发题数 > 0 的等级 / 卷 / 板块 | 各 Catalog Service |
| R7 | **板块配置只存一处**：板块名称/题型/顺序只允许写在 `practice_module_level_config.parts_config`，禁止再往 `structure` / `part_setting` 写展示字段 | Code Review 卡点 |
| R8 | **实际题量必须现算**：`parts_config.questionCount` 是标准题量，接口下发前必须被 `question` 的实际计数覆盖 | 各 Catalog Service |
| R9 | **禁止 join 那两张退场表取展示字段**：新代码只允许从 `parts_config` + `question` 装配；`practice_paper_structure` 仅可用于 `structureId` 映射 | Code Review 卡点 |
| R10 | **`practice_record` 只认三元组**：`(paper_id, section_mapping, section)` 是定位键，`section` 存模块内部分号（`practice_part_setting.section_code`），**不得再写 `structure_id`** | 各 Record Service |

### 3\.2 数据库设计

#### 3\.2\.1 表的取舍总表（两退场 / 一留作配置 / 一瘦身）

| 表 | TEST 行数 | 处理 | 理由 |
|---|---|---|---|
| `exam_paper` | 136 卷 | ✅ 保留，**零改** | `version` 是版本开关；`level` 是等级；`deleted_prac` 是练习侧停用 |
| `question` | 万余 | ✅ 保留，**零改** | `section_mapping` 定模块、`section` 定部分号、`type_id_mapping` 定题型 |
| `question_group` | — | ✅ 保留，**零改** | 翻译 2 个大题组已在（笔译 / 口译） |
| `speaking_exam_paper` / `_question` | 33 / — | ✅ 保留，**仅 2.0 用** | 3.0 口语走 `exam_paper`（ADR-07） |
| **`practice_module_level_config`** | **49** | ✅ **保留，作为唯一配置表** | `parts_config` 已 100% 覆盖全部 49 行（2.0 21 + 3.0 28），见 §3.2.6 |
| `practice_paper_setting` | — | ✅ 保留 | 运营侧卷上下架，语义独立 |
| `hsk_level_config` | 13 | ✅ 保留 | 等级三语名称，与本议题无关 |
| **`practice_paper_structure`** | **1201** | ⚠️ **退场 → 瘦身为 ID 注册表** | 展示字段 100% 冗余；但 `id` 被 7 张作答表引用，不能直接drop（§3.2.7） |
| **`practice_part_setting`** | **1201** | ⚠️ **退场 → 停写** | 与 `structure` 是 **1:1**（1201:1201），且一 section 一题型，信息可并入 `parts_config` 元素 |
| **`practice_record`** | **963** | ⚠️ **瘦身：删 2 列、启用 1 列** | 删 `structure_id`（三元组已完整）+ `practice_name`（脏快照）；启用 `question_ids` 存题目快照（§3.2.8） |
| `practice_report` | 477 | ⚠️ 瘦身：删 `structure_id` | 有 `practice_record_id` 可回溯，冗余 |
| `writing_attempt` / `speaking_attempt` | 217 / 283 | ⏳ P2 才动 | 只有 `paper_id + structure_id`，需先补 `section_mapping + section` |
| `practice_question_option_pool` | 2505 | ⏳ P2 才动 | 只有 `structure_id + question_id`，是板块题目池 |

**核心事实：`parts_config` 一个 JSON 数组元素，正好等于 `structure` 一行 + `part_setting` 一行。**

```json
// practice_module_level_config.parts_config 的一个元素（实测原文）
{
  "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
  "typeName": "笔译",     "typeNameEn": "Written Translation", "typeNameVi": "Biên dịch viết",
  "sortOrder": 1,        "questionCount": 2
}
```
```
// 等价的两行关系表
practice_paper_structure: section_name='第一部分', section_name_en='Part 1', sort_order=23, question_count=2
practice_part_setting   : type_name='笔译',      type_name_en='Written Translation', answer_mode='TEXT'
```

> 🔴 **顺序变了**：原来的设计是「结构表是主，`parts_config` 是备」；现在反过来——**`parts_config` 是主，结构表退场**。

#### 3\.2\.2 仍在的三处语义冲突

**冲突 1：HSK3.0 口语有两套数据，必须指定唯一读源**

| 读源 | TEST | PROD |
|---|---|---|
| `exam_paper` + `question`（`section_mapping='SEC_SPEAKING'`） | 1 卷 5 题（卷 `2104188199979532289`，number 87–91，带 `audio_url`） | **1 卷 5 题（同）** |
| `speaking_exam_paper` + `_question`（`version='HSK3.0'`） | 5 卷（3/4/5/6/7-9 级各 1） | **0 卷** ← 🔴 |

两边 `number` 87–91 完全一致，`source` 与 `exam_paper` 一一对应 —— **同源双录，不是两份内容**。

裁定：**3.0 只认 `exam_paper` + `question.SEC_SPEAKING`**；`speaking_exam_paper` 退回 2.0 专用（ADR-07）。TEST 那 5 张 3.0 口语卷冻结为历史数据。

**冲突 2：`question.section` 是模块内部分号，不再是全局号（这条反而变简单了）**

| | 原设计（结构表为主时） | 现设计（`parts_config` 为主） |
|---|---|---|
| 部分号来源 | `practice_paper_structure.sort_order`（全局 1–23，阅读从 5 开始） | **`question.section`（模块内 1–4）+ `parts_config[].sortOrder`（模块内 1–N）** |
| 是否要基址换算 | ✅ 要（LISTEN 0 / READ 4 / WRITE 20 / TRANSLATION 22） | ❌ **不要** |

这是本次架构简化最大的收益：**基址映射整套消失**，不再需要 `PracticeSectionCode.base()`，也不会再出现「结构表 sort_order=5 而题库 section=1」的对不上。

实测佐证：结构表与题库聚合的差异，恰恰全部来自这个全局基址（听力 446/446、写作 166/166、翻译 1/1 精确，因为它们的基址恰好对上；阅读 4+1..4 有 160 行对不上，因为人工拆分与 `section` 粒度不同）。

> ⚠️ **兼容遗留**：P0 期结构表还在（作 ID 注册表），若仍需回读 `sort_order`，按 `section` 与 `parts_config[].sortOrder` 对齐，**不要**再用基址公式反推。

**冲突 3：`parts_config` 缺稳定题型编码与作答模式（从"提示"升级为"阻塞"）**

| `type_id_mapping` | `question.layout` | 原 `part_setting.answer_mode` | 判定 |
|---|---|---|---|
| `translation_written` | `input` | `TEXT` | 正确 |
| `writing_short_essay` | `input` | `SINGLE` | 🔴 应为 `TEXT`，存量错配（B-09） |
| `reading_sent_match` | `choice` | `MATCH` | 正确 |
| `reading_cloze` | `choiceGrid` | `SINGLE` | 正确 |
| `listening_img_match` | `choiceGrid` | `MATCH` | 正确 |

同样是 `input`，翻译是 `TEXT`、作文是 `SINGLE`；同样是 `choiceGrid`，图片匹配是 `MATCH`、完形是 `SINGLE`。**`layout` 是渲染布局，`answer_mode` 是作答交互，多对多，不能互推。**

而 `parts_config` 里**只有 `typeName`（中文名），既无 `typeCode` 也无 `answerMode`**。所以：

裁定：**必须给 `parts_config` 元素补两个键** —— `typeCode`（稳定题型编码，取 `question.type_id_mapping` 的取值域）与 `answerMode`（`SINGLE/MATCH/ORDER/RECORD/TEXT`）。补齐前，`answer_mode` 只能靠 `PracticeTypeRegistry` 按 `typeName` 反查，属于临时兜底。

#### 3\.2\.3 数据缺口（9 条消失/降级，剩 4 条真阻塞）

| # | 缺口 | TEST | PROD | 影响 | 处置 | 级别 |
|---|---|---|---|---|---|---|
| ~~D1~~ | ~~HSK3.0 的 `practice_paper_structure`~~ | 135 | 0 | ~~3.0 五卡全空~~ | ✅ **消失**：目录改读 `parts_config`，不再需要结构行 | — |
| ~~D2~~ | ~~翻译口译板块缺 structure~~ | 缺 | 缺 | ~~口译不出现~~ | ✅ **消失**：`parts_config` 里**已写好两段**（笔译 2 题 / 口译 2 题，实测原文） | — |
| **D3** | `exam_paper.level` 7-9 取值不一致 | `"7"` | `"7-9"` | `parseInt("7-9")` → 500；`= '7'` 命中 0 卷 | 代码 `IN ('7','7-9')`（R3） | **P0 阻塞** |
| **D4** | `practice_module_level_config` 的 HSK3.0 行 | 28 行 | **0 行** | PROD 切 3.0 无配置 | 补 28 行 `parts_config`（可参考 TEST 同构数据 / 由题库生成） | **P0 阻塞** |
| D5 | `writing_evaluation_policy` 无 `TRANSLATION_WRITTEN` | 缺 | 缺 | 笔译交卷后报告永久「生成中」 | P0 不入队，直接 `UNAVAILABLE`；P1 补策略 | P0 规避 |
| D6 | 翻译 4 题 `answer` 全为 `(略)` | 4/4 | 4/4 | AI 评分无参照 | 题库补参考译文 | P1 |
| ~~D7~~ | ~~口语 3.0 无 structure~~ | 缺 | 缺 | ~~7-9 口语看不到~~ | ✅ **消失在 D4 里**：`SEC_SPEAKING` 的 `parts_config` 已有一段（3 板块） | — |
| D8 | HSK3.0 卷数偏少 | 15 卷 | 15 卷 | 3.0 列表只有 1–3 张卡 | 题库导入 | 已知 |
| ~~D9~~ | ~~阅读部分号两套口径~~ | 160 行 | 同 | ~~派生会改现网~~ | ✅ **消失**：不再派生、不再对齐结构表 | — |
| **D10** | `practice_paper_structure.version` collation 与其他表不一致 | `utf8mb4_unicode_ci` | 同 | 跨表 version JOIN 报 `ERROR 1267` | ✅ **大幅降级**：不再 join 这张表；若 P0 仍需，代码 `CONVERT` | 降为 P1 |
| **D11** | `deleted_prac` 列 PROD 不存在 | 5 表已有 | **5 表全缺** | 目录 SQL 带 `deleted_prac=0` → `Unknown column` | 上线前 DDL | **P0 阻塞** |
| **N4** | `parts_config` 元素缺 `typeCode` | 缺 | 缺 | 只能用中文 `typeName` 匹配题型 → 改名即崩 | 补键（28 + 21 行配置一次性刷） | **P0 阻塞** |
| **N5** | `parts_config` 元素缺 `answerMode` | 缺 | 缺 | 前端无法确定作答交互 | 补键 | **P0 阻塞** |
| N6 | 板块级 `enabled` / `durationMinutes` / `fullScore` / `description` | 缺 | 缺 | 板块无法单独关停、无板块级时长满分与提示语 | P1 按需补键；`duration` 可先用表级 `suggested_duration_minutes` | P1 |

> 🔴 **真阻塞只剩 4 条**：D3（level 取值）、D11（`deleted_prac` DDL）、D4（PROD 补 28 行配置）、N4/N5（`parts_config` 补两个键）。
> 相比 v1.1 的 11 条，删掉两张表反而让缺口清单**短了一半**——因为「结构行」这个中间层不再需要复刻。

#### 3\.2\.4 目录装配口径（不再"派生写库"，改为"读时装配"）

**旧设计**：脚本从题库派生 → 写入 `practice_paper_structure` → 接口读表。
**新设计**：接口**运行时**读 `parts_config` + 聚合 `question`，**不写任何中间表**。

```sql
-- ① 板块骨架 + 标准题量（配置层，一次查询，行数 = 板块数）
SELECT level, section_mapping, enabled, total_question_count,
       suggested_duration_minutes, parts_config
FROM practice_module_level_config
WHERE deleted = 0 AND version = ? AND section_mapping = ? [AND level = ?];

-- ② 卷列表（内容层）
SELECT id, level, source, description, created_time
FROM exam_paper
WHERE deleted = 0 AND exam_type = 1 AND deleted_prac = 0   -- ⚠️ PROD 缺 deleted_prac（D11）
  AND version = ?
  AND level IN (?, ...)                                    -- 7-9 级候选集（D3）
ORDER BY level, source;

-- ③ 每卷每板块的实际题量（内容层，按卷批量取，勿逐卷查）
SELECT paper_id, section_mapping, CAST(section AS SIGNED) AS section_no, COUNT(*) AS actual_count
FROM question
WHERE deleted = 0 AND deleted_prac = 0 AND paper_id IN (...)
  AND (type_id_mapping IS NULL OR type_id_mapping <> 'example_question')
  AND section IS NOT NULL AND section <> ''
GROUP BY paper_id, section_mapping, section;
```

装配规则（服务端内存完成）：
1. 以 `parts_config[]` 为骨架，按 `sortOrder` 排序；
2. 用 ③ 的 `actual_count` **覆盖** `questionCount`（`parts_config` 里的是**标准题量**，不是每卷实际题量）；
3. `actual_count = 0` 的板块**不下发**（R6）；
4. `enabled = 0` 的整块模块不下发；
5. `typeCode` / `answerMode` 从补齐后的配置取，缺失时回退 `PracticeTypeRegistry`。

> ✅ **收益**：不再需要派生脚本、不再需要幂等考虑、不再需要一致性校验。配置改一行，接口立刻生效。

#### 3\.2\.5 唯一键（collation 已基本无关）

| 唯一键 | 影响 |
|---|---|
| `practice_module_level_config :: uk_module_level (version, level, section_mapping)` | 已含 `version`，两版本天然共存，**无需改键** |
| `practice_user_preference :: uk_preference_user_module (user_id, section_mapping)` | **不含 version** → 两版本写同一行会覆盖，P0 靠「3.0 不写」规避（ADR-03） |
| ~~`practice_part_setting :: uk_part_code`~~ | 随表退场，不再关心 |

collation 问题（原 D10）只在新老代码仍 join `practice_paper_structure` 时出现；P0 若保留该表作 ID 注册表，查询它时仍应 `CONVERT ... COLLATE utf8mb4_0900_ai_ci`。

#### 3\.2\.6 `parts_config` 承载证明（逐字段对照）

实测 `practice_module_level_config` 49 行，**`parts_config` 非空率 100%**；11 个 `(version, section_mapping)` 组合的键名完全一致：

`["partName", "typeName", "sortOrder", "partNameEn", "partNameVi", "typeNameEn", "typeNameVi", "questionCount"]`

| 需求字段 | 原 `structure` / `part_setting` | `parts_config` 键 | 结论 |
|---|---|---|---|
| 板块中文名 | `section_name` | `partName` | ✅ 已有 |
| 板块英文名 | `section_name_en` | `partNameEn` | ✅ 已有 |
| 板块越南名 | `section_name_vi` | `partNameVi` | ✅ 已有 |
| 板块顺序 | `sort_order` | `sortOrder` | ✅ 已有（且是模块内号，无需基址） |
| 题型中文名 | `type_name` | `typeName` | ✅ 已有 |
| 题型英/越名 | `type_name_en` / `_vi` | `typeNameEn` / `typeNameVi` | ✅ 已有 |
| 标准题量 | `question_count` | `questionCount` | ✅ 已有 |
| **稳定题型编码** | `type_code` | ❌ | 🔴 **N4，必须补** |
| **作答交互模式** | `answer_mode` | ❌ | 🔴 **N5，必须补** |
| 板块启用 | `enabled` | ❌ | N6，P1 |
| 板块时长 | `duration_minutes` | ❌ | N6；可先用表级 `suggested_duration_minutes` |
| 板块满分 | `full_score` | ❌ | N6 |
| 作答提示语 | `description` | ❌ | N6 |

**必须补的两个键，取值域直接抄题库**：
- `typeCode` ← `question.type_id_mapping` 的实际取值（如 `reading_img_match`、`translation_written`）
- `answerMode` ← 原 `part_setting.answer_mode`（`SINGLE` / `MATCH` / `ORDER` / `RECORD` / `TEXT`）

**翻译的 `parts_config` 实测原文**（证明 D2 已消失）：
```json
[
  {"partName":"第一部分","typeName":"笔译","sortOrder":1,"questionCount":2,
   "partNameEn":"Part 1","partNameVi":"Phần 1","typeNameEn":"Written Translation","typeNameVi":"Biên dịch viết"},
  {"partName":"第二部分","typeName":"口译","sortOrder":2,"questionCount":2,
   "partNameEn":"Part 2","partNameVi":"Phần 2","typeNameEn":"Oral Interpretation","typeNameVi":"Phiên dịch nói"}
]
```

#### 3\.2\.7 `structure_id` 分层退出（不再"必须保留整表"）

**7 张表引用 `structure_id`，但退出难度完全不同**：

| 表 | TEST / PROD 行数 | `paper_id` | `section_mapping` | `section` | 能否立即脱离 | 处置 |
|---|---|---|---|---|---|---|
| **`practice_record`** | 963 / 1364 | ✅ | ✅ | ✅ **1–4** | ✅ **能** | **P0 删 `structure_id`** |
| `practice_report` | 477 / 1011 | ✅ | ✗ | ✗ | ✅ 能（`practice_record_id` 回溯） | **P0 删** |
| `writing_attempt` | 217 / 284 | ✅ | ✗ | ✗ | ❌ 缺部分号 | P2 加两列 |
| `speaking_attempt` | 283 / 473 | ✅ | ✗ | ✗ | ❌ 缺部分号 | P2 加两列 |
| `practice_question_option_pool` | 2505 / 1150 | ✗ | ✗ | ✗ | ❌ 缺部分号 | P2 改为按题目关联 |
| `writing_report` / `speaking_report` | 151 / 183 | ✅ | ✗ | ✗ | ✅ 能（`attempt_id` 回溯） | P2 |

> 🔑 **`practice_record` 是唯一"已经什么都有"的表**：`paper_id` + `section_mapping` + `section` 三列齐备，`structure_id` 从第一天起就是冗余。它当初存在只是因为这个组合**没法做唯一键**（实测 TEST 有 131 组、PROD 有 106 组重复），于是拿来当查询键用——但重复组本身不影响「取最新一条」的语义。

**历史 ID 无法可靠重算**（这一点没变，但它只影响剩下 3 张表）：

| ID 号段 | 行数 | 性质 |
|---|---|---|
| `20…`（雪花） | 479 | 老数据，**不可重算** |
| `70…`（7e18 稳定） | 608 | 由 `stableId('structure', ...)` 算出 |
| `80…`（8e18） | 114 | 口语分支 |

稳定公式存在：`7e18 + sha256("structure|<paperId>|<module>|<section>")[:12] % 1e18`，
但**全量穷举 240 种组合只命中 248 / 1201（20.6%）** → 不能靠重算替代表。

**因此 `practice_paper_structure` 的寿命与最后 3 张表绑定，不再与全部 7 张绑定**：

| 阶段 | 谁还在用 `structure_id` | `practice_paper_structure` 的命运 |
|---|---|---|
| **P0（本次）** | `writing_attempt` / `speaking_attempt` / `option_pool` | 保留为 **5 列 ID 注册表**（`id/paper_id/content_type/sort_order/version`），展示字段停写 |
| P2 | 无 | **可彻底 drop**，ADR-10 降级为历史记录 |

**P0 的写入约定**：
1. 新卷入库时**仍写**这 5 列（`stableId('structure', paperId, content_type, section)`）；
2. `section_name` / `question_count` / `duration_minutes` / `full_score` / `description` **一律不写**，由 `parts_config` + `question` 现算；
3. `practice_part_setting` **完全停写**；
4. 新查询**不得** join 这两张表取展示字段（R9）；
5. **`practice_record` 不得再写 `structure_id`**（R10）。

#### 3\.2\.8 `practice_record` 改造（删 2 列 / 启用 1 列）

> ✅ **先给结论：这个改造不是"设计上可行"，是"已经验证等价"**。以下三条实测把风险降到最低。

| 验证项 | TEST | PROD |
|---|---|---|
| `practice_part_setting.section_code` = 同板块 `question.section` | **1087 / 1087 一致，0 差异** | 480 / 480 一致 |
| `practice_record` 的三元组能查到题 | **906 / 907**（1 条脏记录） | **1343 / 1343 全中** |
| 旧路径（`structure_id` → `part_setting`）与新路径（三元组）**取到的题数完全一致** | **905 / 907**（仅 1 条差异） | **1343 / 1343，零差异** |
| `practice_name` = `structure.section_name` | **905 / 905** | **1343 / 1343** |

**TEST 那条唯一差异已被定性为造数**：记录 `id=1111111`、`paper_id=2095483421053284353`、`section=SEC_CSCA/section=1`、`structure_id=111`、`practice_name=csca_arts_chinese` —— ID 是 `1111111`、`structure_id` 是 `111`，明显是手工插入的测试数据，不对应任何真实板块。**改造时可一并软删，PROD 无此记录。**

> 🔑 **更关键的是：代码里等价方法已经写好了。**
> `PracticeQuestionMapper.xml` 中 `selectByStructure` 的实现本身就是
> ```sql
> INNER JOIN practice_part_setting pps
>   ON q.paper_id = pps.paper_id
>  AND q.section_mapping = pps.section_mapping
>  AND q.section = pps.section_code
> WHERE pps.structure_id = #{structureId}
> ```
> 也就是说 `structureId` 只是「`(paper_id, section_mapping, section_code)` 三元组」的**代理键**，绕了一圈。
> 而同文件里 **`selectByPart(paperId, sectionMapping, sectionCode)` 早已存在**、逻辑正是三元组直查。
> 所以改造不是"重写取题链路"，而是**换个已存在的方法调用**。

##### ① 现状：28 列里有 2 列是废的，1 列是空的

| 列 | 现状 | 判定 |
|---|---|---|
| `structure_id` bigint NOT NULL | 963 行全有值，但**实测存在脏值**：记录 `2082292518405345282` 的 `structure_id` 直接等于 `paper_id` | ❌ **删** |
| `practice_name` varchar(255) NOT NULL | 与 `structure.section_name` **100% 一致**（TEST 905/905、PROD 1343/1343，零差异）——纯复制；但格式**跨模块不统一**：听力 `第1部分`(649 条)、阅读 `第一部分`(257 条) | ❌ **删** |
| `section` varchar(50) NULL | 全部非空，来自 `practice_part_setting.section_code`（代码 L90 `.section(partSetting(...).getSectionCode())`），取值 `1/2/3/4`，与 `question.section` **同口径** | ✅ **升为定位键** |
| `section_mapping` varchar(50) NOT NULL | 全部非空，`SEC_LISTEN` / `SEC_READ` / `SEC_CSCA` | ✅ 保留 |
| `question_ids` json NULL | 列**已存在**，CSCA 已用（56 / 21 条），**HSK 全为 NULL** | ✅ **启用** |

**`practice_name` 为什么该删**：实测它与 `structure.section_name` **100% 完全相同**（TEST 905/905、PROD 1343/1343），是纯复制，零独立信息。而 `section_name` 本身已被 `parts_config.partName` 取代（§3.2.6）。

删除还有个附带收益：**顺手统一了名称格式**。现状是听力写 `第1部分`（649 条，阿拉伯数字）、阅读写 `第一部分`（257 条，中文数字）——不是同一板块两种写法，而是**两个模块的历史写法不同**。改由 `parts_config.partName` 统一供给后，这类不一致自然消失。

**`question_ids` 为什么该启用**：现在 `total_questions = questions.size()`（创建时算的），题库一旦补题/软删题，历史记录就对不上。实测抽 6 条 HSK 记录 `total_questions` 与题库现算**恰好一致**（5 = 5），说明目前是"整板块固定题、不抽题"；但 HSK3.0 导入期题目必变，且 CSCA 已走抽题模式——存快照是唯一稳的做法。

##### ② 目标结构（删 2 列，其余不动）

```sql
-- 删除（P0，需先备份）
-- ALTER TABLE practice_record DROP COLUMN structure_id, DROP COLUMN practice_name;

-- 索引必须同步换列（否则删除列后索引自动消失、查询全表扫）
-- DROP INDEX idx_record_active ON practice_record;
-- CREATE INDEX idx_record_active ON practice_record (user_id, paper_id, section_mapping, section, status);

-- question_ids 从"仅 CSCA"扩展为"全模块必填"，语义明确
-- ALTER TABLE practice_record MODIFY COLUMN question_ids json NULL
--   COMMENT '本次练习题集快照（自然序 question.id 数组；创建时写入，此后不改）';
```

> ⚠️ **索引是这次改造最大的隐藏坑**：`idx_record_active (user_id, paper_id, structure_id, status)` 一旦 `DROP COLUMN structure_id`，MySQL 会**自动把该列从索引里去掉**，索引退化为 `(user_id, paper_id, status)`，而新查询按 `(user_id, paper_id, section_mapping, section, status)` 过滤 → **全表扫**。必须显式重建。

##### ③ 查询改写（7 处 Mapper 全量）

| Mapper 方法 | 旧条件 | 新条件 |
|---|---|---|
| `selectInProgress` | `paper_id + structure_id` | `paper_id + section_mapping + section` |
| `selectInProgressForUpdate` | 同上 | 同上 |
| `selectLatestSubmitted` | `structure_id` | `paper_id + section_mapping + section` |
| `selectLatestReady` | `structure_id` | 同上 |
| `selectByAllStatus` | `structure_id` | 同上 |
| `selectInProgressByStructures` | `structure_id IN (...)` | `(paper_id, section_mapping, section) IN (...)` 或按 `IN` 拆两次 |
| `selectLatestReadyByStructures` | 同上 | 同上 |

> 批量方法（`ByStructures`）的两个调用方是目录页「每板块是否有草稿 / 是否有报告」角标。改成三元组后 SQL 变长，但可以**一次查全卷再内存分组**（`paper_id IN (...)` + `section_mapping IN (...)`），反而比 `IN (1201 个 structureId)` 更省。

##### ④ 接口契约变更（这就是"不要接口 id"的落地）

| 旧 | 新 | 说明 |
|---|---|---|
| `POST /listening/records/start` `{paperId, structureId, restart}` | `{paperId, section, restart}` | `section` 是部分号 `1–4`；`sectionMapping` 由路径中的模块隐含 |
| `GET /listening/parts/{structureId}/reports/latest` | `GET /listening/papers/{paperId}/parts/{section}/reports/latest` | 必须带 `paperId`——不同卷的同 `section` 是不同板块 |
| `POST /reading/records/start` `{paperId, structureId}` | `{paperId, section}` | 同听力 |
| `GET /reading/parts/{structureId}/reports/latest` | `GET /reading/papers/{paperId}/parts/{section}/reports/latest` | 同上 |

**前端感知**：原来拿目录接口返回的 `structureId` 直接回传，现在拿同一个响应里的 `partCode`（= `section`）+ 卷 `id` 回传。**目录接口的 `structureId` 字段可以同时保留一个版本做兼容**（标 `deprecated`），但服务端**不再落库**。

##### ⑤ `question_ids` 快照的写入时机与用法

| 时机 | 动作 |
|---|---|
| 创建记录（`start`） | 查出该板块全部题目 ID → 排序 → 写 `question_ids`，同时 `total_questions = JSON_LENGTH` |
| 续答（`resume`） | **不重算**，直接用记录里的 `question_ids` 拉题（保证"上次练到哪"的题序不变） |
| 提交（`submit`） | 只统计，不改 `question_ids` |
| 报告生成 | 以 `question_ids` 为准，**不用现查题库** → 题库改版后报告仍可复现 |

> 🎯 这一列的价值不在"省一次查询"，而在**快照隔离**：HSK3.0 导入期题目会增删改，没有它，一个月前练的记录点进去可能少题或多题。

##### ⑥ `writing_attempt` / `speaking_attempt` 为什么这次不动

它们只有 `paper_id + structure_id`，**没有 `section_mapping` 也没有 `section`**：

```
writing_attempt:  ... paper_id, structure_id, level_code, ...   ← level_code 是等级，不是部分号
speaking_attempt: ... paper_id, structure_id, level_code, ...
```

要删 `structure_id`，必须先加 `section_mapping + section` 并**回填 217 + 283 条历史数据**（回填值可从 `practice_paper_structure` join 得到，但那张表本身也有 479 条雪花 ID 需核对）。这一步风险与收益不成正比，**放 P2 与 `option_pool` 一起做**。做完后 `practice_paper_structure` 才能真正 drop。

### 3\.3 接口设计

> 路径均为 **service 内路径**，客户端实际调用需加网关前缀 `/api/practice`。

#### 3\.3\.1 版本参数规范（16 个存量端点统一适用）

| 项 | 规定 |
|---|---|
| 参数名 | `version` |
| 位置 | query string（**不用 header**，理由见 ADR-01） |
| 类型 | `string`，枚举 `HSK2.0` / `HSK3.0` |
| 必填 | 否，缺省 `HSK2.0` |
| 大小写 | **敏感**，`hsk3.0` → 400 |
| 特殊值 | 无（不提供 `ALL` / `LATEST`） |

#### 3\.3\.2 存量端点改造清单（16 个）

| # | 方法 | 路径 | 现状 | 改造 |
|---|---|---|---|---|
| 1 | GET | `/listening/levels` | **无 version 过滤、无 `exam_type` 过滤**；直接按 `level` 取卷 | 加 `version`；补 `exam_type=1`；卷查询走 `SharedPaperEligibility` |
| 2 | GET | `/listening/levels/{levelCode}/intro` | `selectOne` **不带 version** → 两版本同等级各 1 行时抛 `TooManyResults` | 加 `version`；`selectOne` 带 `version` + `deleted=0`；`levelCode` 走 `PracticeLevelCode` |
| 3 | GET | `/listening/papers/{paperId}/parts` | 同上（`parts_config` 查询无 version） | 同上；板块来源**改为 `parts_config` + `question` 计数**（§3.2.4），不再读 structure/part_setting |
| 4 | GET | `/reading/levels` | `VERSION = "HSK2.0"` 常量 | 常量改参数 |
| 5 | GET | `/reading/levels/{code}/intro` | 常量；`Integer.parseInt(code.replace("HSK",""))` → `HSK7-9` 必 404 | 常量改参数；改 `PracticeLevelCode` |
| 6 | GET | `/reading/papers` | 常量；`eq(level, String.valueOf(7))` 与 PROD 的 `"7-9"` 不匹配 | 常量改参数；`level IN (dbLevels)` |
| 7 | GET | `/reading/papers/{paperId}/parts` | 无版本校验 | 校验卷的 `paper.version` 与入参一致，不一致 → 404 |
| 8 | GET | `/reading/preferences` | 无 version，表无 version 列 | **P0 不改**（ADR-03） |
| 9 | PUT | `/reading/preferences/level` | 同上；`HSK7-9` 会 404 | P0 前端只在 `HSK2.0` 下调；P1 加 version 列 |
| 10 | GET | `/writing/levels` | `VERSION = "HSK2.0"` 常量 | 常量改参数 |
| 11 | GET | `/writing/levels/{code}/intro` | 常量；`parseLevel` 正则 `HSK[1-6]` → `HSK7-9` 404；`introSections` 的 `switch` 只到 6 | 常量改参数；改 `PracticeLevelCode`；`switch` 补 `7` 分支（图表描述 1 + 话题作文 1） |
| 12 | GET | `/writing/papers` | 常量 | 常量改参数 |
| 13 | GET | `/writing/papers/{paperId}/parts` | `Integer.parseInt(paper.getLevel()) < 3` → `"7-9"` 抛 `NumberFormatException`（500） | 改 `PracticeLevelCode.parseDbLevel(...)` |
| 14 | GET | `/speaking/levels` | `VERSION = "HSK2.0"` 常量；`SEC_SPEAK` 单映射 | 常量改参数；按版本**分流读源**（2.0 → `speaking_exam_paper`，3.0 → `exam_paper` + `SEC_SPEAKING`），**不合并去重**（ADR-07） |
| 15 | GET | `/speaking/papers` | 常量 | 常量改参数 |
| 16 | GET | `/speaking/papers/{paperId}/parts` | 常量校验（`VERSION.equals(paper.getVersion())`） | 改为「与入参 version 一致」 |

> 统一约定：`version` 最终作为 `practice_module_level_config.version` / `exam_paper.version` 的查询条件，**两处必须同时带上**（v1.2 起结构表不再参与目录查询），漏一处就会出现「等级列表是 2.0、卷列表是 3.0」的错配。

#### 3\.3\.3 新增：首页聚合接口

```
GET /hsk/modules?version=HSK3.0
```

响应（示意，`data` 内）：

```json
{
  "version": "HSK3.0",
  "layout": "LIST",
  "header": "专项突破 · 听力/阅读/写作/翻译/口语",
  "modules": [
    {
      "moduleCode": "LISTENING",
      "sectionMapping": "SEC_LISTEN",
      "name": "听力",
      "nameEn": "Listening",
      "icon": "headphone",
      "theme": "#5B6CF9",
      "badge": null,
      "available": true,
      "disabledReason": null,
      "entryLevelCode": null,
      "sortOrder": 1,
      "progress": { "totalPapers": 15, "completedPapers": 2, "inProgressPaperId": "2104193520701620225" }
    },
    {
      "moduleCode": "TRANSLATION",
      "sectionMapping": "SEC_TRANSLATION",
      "badge": "NEW",
      "available": true,
      "entryLevelCode": "HSK7-9",
      "sortOrder": 4,
      "progress": { "totalPapers": 1, "completedPapers": 0, "inProgressPaperId": null }
    }
  ]
}
```

字段规则：

| 字段 | 规则 |
|---|---|
| `layout` | `GRID_2`（2.0）/ `LIST`（3.0）；前端据此切换 2 列网格与 1 列列表，**不写死** |
| `available` | `false` 时前端**置灰 + Toast**，不隐藏（保持卡片数量稳定）；判定 = 该版本下 `module_level_config` 存在 `enabled=1` 且至少一个等级有题 |
| `disabledReason` | 文案键，如 `MODULE_NOT_IN_VERSION` / `NO_CONTENT`；前端本地化 |
| `entryLevelCode` | 非空表示**跳过等级选择页**直达卷列表（翻译固定 `HSK7-9`） |
| `badge` | 运营角标，按版本配置，P1 改为后台可配 |
| `progress` | 未登录恒为 `{0,0,null}`；`paperId` 一律 **String** |

#### 3\.3\.4 新增：翻译模块（目录 4 + 写链路 6）

**目录（P0）**

| # | 方法 | 路径 | 说明 |
|---|---|---|---|
| T1 | GET | `/translation/levels?version=HSK3.0` | 数组；`HSK2.0` → `[]` |
| T2 | GET | `/translation/levels/{levelCode}/intro?version=HSK3.0` | 单对象，`sections[]` 来自 `parts_config` |
| T3 | GET | `/translation/papers?levelCode=HSK7-9&version=HSK3.0` | 卷清单，过滤 `totalQuestionCount=0` |
| T4 | GET | `/translation/papers/{paperId}/parts` | 板块列表，**必须下发 `answerMode`** |

T4 关键：`answerMode` 取 `practice_module_level_config.parts_config[].answerMode`（N5 补齐后），前端据 `TEXT` / `RECORD` 决定渲染输入框还是录音按钮——这正是笔译/口译两张卡长得不一样的根因。

```json
{
  "paperId": "2104188199979532289",
  "paperCode": "HSK7-9_1",
  "parts": [
    { "structureId": "7000178435150355785", "partCode": "1", "partName": "第1部分",
      "questionType": "translation_written", "questionTypeName": "笔译",
      "answerMode": "TEXT", "questionCount": 2,
      "status": "NOT_STARTED", "draftAttemptId": null, "latestReportId": null, "hasReport": false }
  ]
}
```

**写链路（P0 只做 6 个，其余 P1）**

| # | 方法 | 路径 | 委托 |
|---|---|---|---|
| T5 | POST | `/translation/attempts/start` `{paperId, structureId}` | `WritingAttemptService#start` |
| T6 | GET | `/translation/attempts/{attemptId}` | `#get` |
| T7 | GET | `/translation/attempts/{attemptId}/questions` | `#listQuestions` |
| T8 | PUT | `/translation/attempts/{attemptId}/answers` | `WritingAnswerService#save` |
| T9 | POST | `/translation/attempts/{attemptId}/submit` | `WritingSubmissionService#submit` |
| T10 | GET | `/translation/reports/{reportId}` | `WritingReportService#get` |

**统一前置校验（每个封装方法第一行）**：

```
structureRegistry(structureId).content_type == "SEC_TRANSLATION"  否则 400 SECTION_MAPPING_MISMATCH
```

> 这条校验是防串号的唯一屏障：不加就能拿写作的 `structureId` 打翻译接口，产生两份进度。
> v1.2 起 `structureId` 的模块归属从 **ID 注册表**（`practice_paper_structure` 保留的 5 列）取，不再从 `practice_part_setting` 取。

**为了让委托成立，必须放宽 1 处存量校验**（`WritingAttemptServiceImpl#validatePart`）：

```
现状：!WRITING.equals(structure.getContentType()) || !WRITING.equals(part.getSectionMapping())  → 404
改为：!PracticeModuleCodes.WRITING_COMPATIBLE.contains(contentType) || !contentType.equals(sectionMapping)
      其中 WRITING_COMPATIBLE = Set.of("SEC_WRITE", "SEC_TRANSLATION")
```

> 不加这条，翻译**根本开不了练习**（`SEC_TRANSLATION` 会被判 404）。这是"目录独立、作答复用"这个方案的**唯一侵入点**，必须与目录隔离成对评审。

#### 3\.3\.5 服务端执行顺序（聚合接口，重点）

```
1. 解析 version（白名单校验，失败 400）
2. 取模块元数据（PracticeModuleCatalog，按 version 过滤 + 排序）
3. 批量查 practice_module_level_config（version + section_mapping IN (...) + enabled=1 + deleted=0）
   → 得到每个模块「有哪些等级」；无行的模块 available=false
4. 批量查 exam_paper（version + exam_type=1 + level IN dbLevels(该等级集)）
   → 按模块统计 totalPapers；题数为 0 的卷剔除
5. 若带 userId：批量查 practice_record / writing_attempt 的进行中与已完成（一次 IN 查询，禁止循环单查）
   → 填充 progress
6. 按 sortOrder 排序返回
```

性能约束：**SQL 次数 ≤ 5，且与模块数无关**（步骤 3/4/5 全部批量）。

#### 3\.3\.6 异常处理

| 场景 | 处理 |
|---|---|
| `version` 非法 | 400 `PRACTICE_VERSION_INVALID` |
| `levelCode` 在该版本下不存在 | 404，文案按模块（沿用现状「阅读等级不存在」等） |
| `paperId` 的 `version` 与入参不符 | 404，「试卷不存在」（**不提示版本不符**，避免探测） |
| `sectionMapping` 与模块不匹配 | 400 `SECTION_MAPPING_MISMATCH` |
| 目录查询异常 | 整卡 `available=false` + `disabledReason=LOAD_FAILED`，**不 500 整页** |
| 报告评分策略缺失（翻译 P0） | 报告正常返回，`feedbackStatus=UNAVAILABLE`，`score=null` |

### 3\.4 核心流程设计

#### 流程 1：首页首屏

```
客户端 → GET /hsk/modules?version=HSK3.0
       → 解析 version → 取 5 模块元数据 → 批量查等级开关 → 批量查卷
       → （可选）批量查进度 → 排序返回
前端   → layout=LIST 渲染 1 列 5 行；TRANSLATION.available=true → 可点
       → 点击：entryLevelCode 非空 → 直达 /translation/papers；否则 → 等级选择页
```

#### 流程 2：翻译开始练习（含准入链）

```
① 前端 POST /translation/attempts/start {paperId, structureId}
② Controller：requireAuthenticatedAppUserId → 仅委托，无业务
③ 薄封装：section_mapping == SEC_TRANSLATION ? 继续 : 400
④ WritingAttemptServiceImpl#start
     ├─ requirePaper：exam_paper 有效 + exam_type=1 + practice_paper_setting 上架 + level ≥ 3
     ├─ validatePart：content_type ∈ {SEC_WRITE, SEC_TRANSLATION} 且 == section_mapping
     ├─ 已有 IN_PROGRESS 的 attempt → 直接返回（幂等）
     └─ 新建 attempt，快照 paperVersion / sectionVersion / questionSetVersion
⑤ 返回 attemptId（String）
```

#### 流程 3：版本切换

```
用户切换版本 → 前端清空：已选 levelCode / 卷列表 / 滚动位置 / 本地「上次练习」
            → GET /hsk/modules?version=<new>
            → 若上次停在 3.0 的翻译，切回 2.0 时该卡 available=false → 置灰
```

> 🔴 **不要复用旧 `levelCode` 打新版本的 `/papers`**：2.0 的 `HSK1` 在 3.0 下虽然存在，但卷集合完全不同；`HSK7-9` 在 2.0 下直接 404。

### 3\.5 缓存设计

| 项 | 方案 |
|---|---|
| 模块元数据 | 进程内常量，无缓存（`PracticeModuleCatalog`） |
| 目录结果 | P0 **不缓存**（数据量小：单等级 ≤ 21 卷）；P1 可加 Caffeine，`key = version + levelCode + module`，TTL 60s |
| 进度部分 | **禁止缓存**（用户态） |
| 题库版本号 `dataVersion` | P1 引入：`MAX(updated_time)` over `exam_paper` / `question` / `practice_module_level_config`，作为 `ETag` 下发，前端缓存失效用 |
| 击穿/雪崩 | P0 无缓存即无此风险；P1 用「同 key 单飞 + 随机 TTL ±10%」 |

### 3\.6 异步设计

| 任务 | 触发 | 现状 | 本次 |
|---|---|---|---|
| 写作/翻译评分 | 交卷后 `writing_evaluation_task` | 异步执行器轮询；policy 缺失 → 任务失败 → 报告卡住 | **翻译 P0 不入队**：交卷时先查 policy，无则直接 `UNAVAILABLE`；P1 补 `TRANSLATION_WRITTEN` 后开启 |
| 口译 ASR + 评测 | — | 未接 | P2，复用 `ai-service` 的 `SpeechAssessment` |
| 报告生成 | 交卷后同步写 `writing_report` 骨架 | — | 不变 |

### 3\.7 权限设计

| 端点 | 登录 | 用户态 | 说明 |
|---|---|---|---|
| `/hsk/modules` | ✅ 必须 | `userId` 从 JWT 取 | 未登录不返回进度，直接要求登录 |
| 各模块 `/levels`、`/papers`、`/parts` | ✅ 必须 | — | 网关白名单未放行 HSK 练习（只有 `/api/practice/csca/catalog` 免登录） |
| `/translation/**` | ✅ 必须 | — | 与写作一致 |
| `preferences` | ✅ 必须 | 按 `userId` 隔离 | 唯一键 `(user_id, section_mapping)` |

数据权限：`userId` **只能**从 `BaseController#getCurrentUserId(request, clientType)` 取，任何接口不接受前端传 `userId`（现状已满足，翻译薄封装必须照抄这一条）。

---

## 4\. 异常与错误码设计

**现有约定（沿用，不重构）**：`BusinessException(code, message)`，`code` 为 HTTP 语义码（400/404/409/500），`message` 为中文文案，由全局异常处理器包成 `Result`。

本次新增的错误码**只在新增端点使用**，存量端点文案不动（避免前端改判断）：

| code | message | 触发 | 使用端点 |
|---|---|---|---|
| 400 | `PRACTICE_VERSION_INVALID` | `version` 不在白名单 | 全部新增 + 16 个改造端点 |
| 400 | `SECTION_MAPPING_MISMATCH` | `structureId` 不属于该模块 | `/translation/attempts/**` |
| 404 | `TRANSLATION_NOT_IN_VERSION` | `version=HSK2.0` 调写链路（目录接口返回空数组不报错） | `/translation/attempts/**` |
| 404 | 各模块原有文案 | 等级/卷/板块不存在 | 存量 |
| 409 | `TRANSLATION_NOT_SCORABLE` | 翻译交卷但无评分策略（P0 返回 `UNAVAILABLE` 而非报错，此码仅 P1 使用） | `/translation/reports/**` |

**业务异常 vs 系统异常**

| 类型 | 判定 | 处理 |
|---|---|---|
| 业务异常 | `BusinessException` | 保留 code + 文案，日志 `WARN` |
| 数据异常 | `NumberFormatException`（`parseInt("7-9")` 一类） | **本次要消灭的**：全部改走 `PracticeLevelCode`，改不完的地方包成 500 `QUESTION_DATA_INVALID` |
| 系统异常 | 其他 | 500 + 通用文案，日志 `ERROR` 带 traceId |

---

## 5\. 安全设计

| 项 | 措施 |
|---|---|
| 参数防注入 | `version` / `levelCode` 走**白名单枚举**后再用；SQL 全部 MyBatis 参数绑定，无字符串拼接 |
| 越权防护 | `attempt` 必须 `userId` 匹配（`requireOwned`）；翻译薄封装必须做 `section_mapping` 校验，否则可用写作 `structureId` 串号 |
| 版本降级探测 | 卷 `version` 与入参不符统一回「试卷不存在」，不暴露差异 |
| 敏感数据 | 无 PII；`answer` / `analysis`（参考答案）**不得**在作答阶段的 `/questions` 接口下发，只在报告接口给 |
| 令牌 | 沿用网关 JWT 校验 + `auth-service` 签发，本模块不引入新鉴权 |
| 音频上行 | 口译录音由前端直传 `system-service /file/uploadVoice`（MIME 校验 + MinIO），本服务只存 URL，**不代理二进制** |
| ID 精度 | 新增端点 ID 一律 `String`（19 位雪花超 JS 安全整数）；存量端点为 `Long`，P1 统一改造需前端同步 |

---

## 6\. 性能\&容量设计

| 场景 | 数据量（实测） | 设计 |
|---|---|---|
| 首页聚合 | 5 模块 × ≤7 等级 | SQL ≤ 5 次，全部批量；目标 P95 ≤ 150ms |
| 等级列表 | 单版本 ≤ 7 行 | 无分页 |
| 卷列表 | HSK2.0 单等级 20–21 卷、HSK3.0 1–3 卷 | 无分页（上限 21）；P1 若导入大批卷再加 `pageSize` |
| 板块列表 | 单卷 ≤ 6 板块 | 无分页 |
| 题量统计 | `selectCountsByParts` 一次 IN 查询覆盖整批卷 | 禁止逐卷循环查 |

**慢查询注意点**

1. `exam_paper` 按 `version + level + exam_type + deleted` 查询，现有索引以主键为主——HSK3.0 只有 15 行，量级不构成问题；若后续 HSK2.0 卷数翻倍再评估加 `(version, level, exam_type)` 复合索引。
2. `practice_paper_structure` 已有 `idx_practice_structure_level (version, hsk_level)` 与 `idx_practice_structure_paper (paper_id, content_type, sort_order)`，本次查询模式完全命中。
3. `question` 侧 `selectCountsByParts` 按 `(paper_id, section_mapping, section)` 过滤，属现网已跑通的路径，不改。

**容量预估**：HSK3.0 全面补齐后 15 卷 × 约 50–90 题/卷 ≈ 1059 题（现网实测），相对 HSK2.0 的 10561 题属小量级。

---

## 7\. 依赖与第三方

| 依赖 | 用途 | 地址/版本 | 超时 | 降级 |
|---|---|---|---|---|
| MySQL `xuexitest` | 全部数据 | TEST `8.138.185.11` / PROD `43.99.57.11` | 15s（连接） | 无（强依赖） |
| gateway | `/api/practice/**` → `lb://practice-service` | Spring Cloud Gateway | — | — |
| `ai-service` | 口语评测（翻译 P2） | `SPEAKING_AI_BASE_URL`，默认 `http://ai-service:8083` | 沿用 speaking 配置 | 评测失败 → 报告 `TEMPORARILY_UNAVAILABLE` |
| `system-service` | 口译录音上传 | `POST /file/uploadVoice` | 前端直传，本服务不参与 | 上传失败前端提示重录 |
| `auth-service` | JWT 签发/校验 | 网关侧 | — | 无 |

**无新增依赖**：本次不引入 Redis、不引入 MQ、不引入新表。

---

## 8\. 测试要点

### 8\.1 版本隔离

1. `GET /hsk/modules` 不传 `version` → `layout=GRID_2`、4 个模块、`TRANSLATION.available=false`。
2. 传 `version=HSK3.0` → `layout=LIST`、5 个模块、`TRANSLATION.available=true`、`TRANSLATION.entryLevelCode=HSK7-9`。
3. `version=hsk3.0`（小写）→ **400**，不得静默降级为 2.0。
4. `version=HSK4.0` → 400。
5. `/reading/levels?version=HSK3.0` 返回 7 个等级，含 `levelCode=HSK7-9`；`?version=HSK2.0` 返回 6 个，不含。
6. `/reading/papers?levelCode=HSK7-9&version=HSK3.0` → PROD 下**能查到卷**（验证 D3 的 `IN` 容错生效）。🔴 这是最容易漏的用例。

### 8\.2 翻译独立

7. `version=HSK2.0` 调 `/translation/levels` → `[]`（不 404）。
8. `version=HSK3.0` → 1 个等级 `HSK7-9`，`totalQuestionCount=4`。
9. `/translation/papers/{id}/parts` → **2 个板块**：笔译 `answerMode=TEXT`、口译 `answerMode=RECORD`（依赖 D2 补配置；未补则只回 1 个，用例预期同步降级）。
10. 拿**写作**的 `structureId` 打 `/translation/attempts/start` → 400 `SECTION_MAPPING_MISMATCH`。
11. 拿**翻译**的 `structureId` 打 `/writing/attempts/start` → 仍 404（写作侧不应放宽，只有翻译入口能进）。
12. 翻译笔译：开始 → 答题 → 交卷 → 报告 `feedbackStatus=UNAVAILABLE`、`score=null`（P0 预期，不是 bug）。
13. `/writing/papers/{id}/parts` **不含**翻译板块（`content_type` 已过滤，回归确认）。

### 8\.3 存量回归（重点，改的都是老接口）

14. HSK2.0 全链路：听力/阅读/写作/口语 四张卡的等级→卷→板块→答题→报告，与改造前逐字段对比一致。
15. `/listening/levels?levelCode=HSK1` 在 **PROD** 下不再混入 HSK3.0 的卷（当前会混 3 张 0 题卡，见附录 B-02）。
16. `/listening/levels/HSK1/intro` 在 **TEST** 下不再 500（当前两版本同等级 2 行 → `TooManyResults`，附录 B-01）。
17. `/writing/papers/{HSK7-9卷}/parts` 在 PROD 下不再 500（`Integer.parseInt("7-9")`，附录 B-03）。
18. 已有 `writing_attempt`（PROD 284 条 / TEST 217 条，全部 HSK2.0）仍可正常打开与续练。

### 8\.4 边界与异常

19. 未登录（无 JWT）调任意 HSK 练习端点 → 401（网关拦截）。
20. 目录内某模块数据缺失 → 该卡 `available=false`，其余 4 卡正常，**不全页 500**。
21. `paperId` 传不存在的雪花 → 404，不 500。
22. `question` 表存在但 `practice_paper_setting` 缺失的卷 → 不出现在目录（不出现「点进去空白」）。

---

## 9\. 风险与备选方案

### ADR-01 版本用 query param，不用 header / path

| 方案 | 评价 |
|---|---|
| **query `?version=`（采纳）** | 与现有 `levelCode` 同风格；可缓存可埋点；本地调试直观 |
| header `X-HSK-Version` | 隐式全局态，日志与网关白名单不易察觉，排障困难 |
| path `/v2/...`、`/v3/...` | 路径翻倍，网关、前端 basePath、埋点全要动；且版本是**内容开关**不是 API 版本 |

**代价**：16 个端点都要加参数，且前端每个请求都要带。可接受。

### ADR-02 翻译走「目录独立 + 作答复用」（切法 B）

| | A：只分目录 | **B：目录独立 + 写链路薄封装（采纳）** | C：完全独立 |
|---|---|---|---|
| 新增端点 | 4 目录 | 4 目录 + 6 写（P0） | 14 端点 + 7 张新表 |
| 前端 | 目录 `/translation`、答题 `/writing` 双 basePath | 全 `/translation` | 全 `/translation` |
| 持久层 | 复用 `writing_*` | 复用 `writing_*` | 新建 `translation_*` |
| 存量侵入 | 0 | **1 处**（`validatePart` 的 contentType 放宽） | 0，但评分/报告/统计重造 |
| 风险 | 后人误改易串号 | 薄封装漏校验会串号（已用统一前置校验兜住） | 工期最长，两套报表口径 |

**选 B 的理由**：用户诉求是「翻译模块分开」，前端必须只见 `/translation/**`；而 A 做不到、C 的代价全在评分链路重造上。
**关键风险**：`validatePart` 放宽后，写作与翻译共用 attempt 表——靠 `content_type` + `section_mapping` 双条件保证互不越界，**这两个条件必须成对评审**。

### ADR-03 用户偏好表 P0 不加 `version`

| 方案 | 评价 |
|---|---|
| **P0：只有 `HSK2.0` 才写偏好，3.0 用本地存储（采纳）** | 零 DDL、零数据迁移；代价是 3.0 换设备丢「上次练到哪」 |
| P1：`practice_user_preference` 加 `version` + 唯一键改 `(user_id, section_mapping, version)` | 正确解，但要改唯一键 + 存量 16 行回填 `HSK2.0`，走五闸门 |

**风险**：若 P0 就允许 3.0 写偏好，会覆盖 2.0 的 `last_level`（2.0 只有 1–6，3.0 有 1–7），用户切回 2.0 会看到不存在的等级。**故 P0 必须硬性禁止 3.0 写偏好**（服务端 `version != HSK2.0` 直接 409，不只靠前端约束）。

### ADR-04 `level='7-9'` 用代码容错，不立刻统一数据

| 方案 | 评价 |
|---|---|
| **代码 `IN ('7','7-9')` + 数据 P1 收敛（采纳）** | 立刻可用，不被数据阻塞；缺点是长期留一个兼容分支 |
| 立刻 UPDATE PROD `exam_paper.level='7'` | 动题库表，`exam-service` 可能读同一列，回归面大；且违反「题库只读」原则 |

**收敛路径**：P1 在 `manage` 的导入流程里统一写 `'7-9'`，并给出一次性的存量修正脚本（走五闸门 + 备份），届时删除 `dbLevels` 的 `'7'` 候选。

### ADR-05 首页聚合接口 vs 前端并发 5 请求

| 方案 | 评价 |
|---|---|
| **聚合接口 `GET /hsk/modules`（采纳）** | 1 次请求；顺序/角标/布局/可用性都由后端定，运营调整不发版 |
| 前端并发打 5 个 `/levels` | 0 后端改动，但首屏 5 个 RTT；版本×可用矩阵写死在客户端，后端放开等级范围客户端要跟版 |

**代价**：需要新增一个 Controller + 常量表（纯新增，无侵入）。

### ADR-06 纠正前置文档的三处过时结论

| 前置文档结论 | 实测代码 | 影响 |
|---|---|---|
| 「写作卷板块列表会多出『翻译第 3 部分』，需在 `WritingCatalogServiceImpl#listParts` 显式排除 `SEC_TRANSLATION`」 | `PracticeCatalogBatchLoader#assemble` **已按 `content_type = module` 过滤**（`eq(getContentType, module)`），写作目录天然只出 `SEC_WRITE` | ✅ 该改动**不需要做**；翻译独立化对写作目录**零侵入** |
| 「`PracticeSections.isWriting()` 含 `SEC_TRANSLATION`，翻译已能开练习，只需薄封装」 | `WritingAttemptServiceImpl#validatePart` **硬判 `WRITING.equals(contentType)`**，`SEC_TRANSLATION` → 404；`PracticeSections` 类不存在 | 🔴 必须放宽 `validatePart`（见 §3.3.4），否则翻译**开不了练习** |
| 「各接口已有 `?version=` 入参」 | 4 个模块的 `VERSION` 全是 `private static final String VERSION = "HSK2.0"`，**没有任何 Controller 接收 version** | 🔴 版本参数是**新增**，不是复用；16 个端点全部要改 |

### ADR-07 HSK3.0 口语读 `exam_paper`，不读 `speaking_exam_paper`

| 方案 | 数据现状 | 评价 |
|---|---|---|
| **A. 3.0 读 `exam_paper` + `question.SEC_SPEAKING`（采纳）** | PROD 1 卷 5 题 ✅ / TEST 同 | 立即可用；与听力/阅读/写作/翻译**同一张卷同一条链路**，`paperId` 天然对齐，不必维护两套 ID |
| B. 3.0 读 `speaking_exam_paper` | TEST 5 卷 / **PROD 0 卷** | 必须先补 5 卷 + 69 题录入才能上线，纯数据阻塞 |
| C. 两套都读、按 `source` 合并 | 两套并存 | 去重靠字符串 `source`，且 `level` 写法不同（`7` vs `7-9`）；合并逻辑本身就是新的 bug 面 |

**选 A 的根本理由**：HSK3.0 的设计前提是「一张卷包含听、读、写、译、说五段」，而 2.0 的口语是独立考试（`Beginner/Intermediate/Advanced` 三档，与 HSK1–6 不同构）。**把 3.0 口语塞进 2.0 的口语表，等于把两种不同的考试结构强行统一**，`level` 语义（`3` vs `Beginner`）就先冲突了。

**代价**：`SpeakingCatalogServiceImpl` 出现一个 `if (version)` 分支，两条查询路径。用统一的 `SpeakingPaperView` DTO 收口，分支只存在于 Repository 层。

**遗留**：TEST 那 5 张 HSK3.0 口语卷不删不写，标记历史数据。若 P2 决定转为 B 方案，需要先补 PROD 数据，并写一次 `question → speaking_exam_paper_question` 的搬运脚本。

### ADR-08 板块配置归并到 `practice_module_level_config`，两张行式表退场

| 方案 | 表数 | 配置行数 | 评价 |
|---|---|---|---|
| **A. `parts_config` JSON 为唯一配置（采纳）** | 1 | **49** | 一个元素 = 一个板块；改配置改一行 JSON；无派生、无幂等 |
| B. 维持 `structure` + `part_setting` | 3 | 1201 + 1201 + 49 | 每张卷复刻一份模板，新增卷要跑脚本；PROD 3.0 至今 0 行就是这么来的 |
| C. 拆成 `part_template` + `part_type` 规范化多表 | 4+ | 更多 | 过度设计：板块模板的基数只有 49，不需要第三范式 |

**决定性证据**：`parts_config` 的键名（`partName/partNameEn/partNameVi/typeName/typeNameEn/typeNameVi/sortOrder/questionCount`）与 `structure + part_setting` 的字段**逐个对应**，且 49 行配置 100% 非空（§3.2.6）。1201 行 × 2 的表，只是把 49 行模板按卷复制了 24 遍。

**收益**（不只是少两张表）：
1. **基址映射消失**：不再有「阅读 sort_order 从 5 开始」这种全局号，直接用 `question.section`（模块内 1–4）；
2. **D1/D2/D7/D9 四条缺口一次性消失**：它们全是「没给某张卷复刻模板」造成的；
3. **翻译口译板块已有配置**：`SEC_TRANSLATION.parts_config` 里本来就写了笔译 + 口译两段，只是结构表漏建；
4. **新卷零维护**：导入题库后自动出现在目录里，不需要再跑派生脚本。

**代价**：
1. 必须给 `parts_config` 补 `typeCode` / `answerMode` 两个键（N4/N5），否则只能用中文题型名匹配；
2. `PracticeCatalogBatchLoader` 要重写（从「查两张表 + 组装快照」变成「读一份 JSON + 算题量」）；
3. `parts_config.questionCount` 是**标准题量**，实际题量必须现算（R8）。

### ADR-09 collation 问题随表退场而降级

| 方案 | 评价 |
|---|---|
| **不专门处理（采纳，v1.2 起）** | 主路径不再 join `practice_paper_structure`，`ERROR 1267` 自然消失；仅在 ID 注册表查询时需 `CONVERT` |
| 代码侧统一 `CONVERT` 片段 | v1.1 的方案；现在只剩 ID 映射一处用到，成本已很低 |
| P1 一次 `ALTER` 对齐 | 仍然建议做（表还会留一段时间），但不阻塞上线 |

原 D10 从「P0 阻塞」降为 P1：**因为那张表不再是查询主路径**。

### ADR-10 `structure_id` 分层退出，`practice_paper_structure` 的寿命绑定剩余 3 表

| 方案 | 数据迁移 | 历史记录 | 建议 |
|---|---|---|---|
| **A. 分层退出（采纳，v1.3 修订）** | `practice_record` / `practice_report` 删列（740 行） | 全稳 | ✅ **P0** |
| B. 全部 7 表一次改完 | 7 表 DDL + 回填 217+283 条 | 需重建关联 | P2 |
| C. 一张都不改，保留整表 | 0 | 全稳 | ❌ 表白留 1201 行 |

**v1.2 的论断"`structure_id` 必须保留"过于保守，v1.3 翻案为分层退出。** 理由：

1. **`practice_record` 本来就三重冗余**：`paper_id` + `section_mapping` + `section` 三列全有值，`structure_id` 是第 4 份等价信息；
2. **它自己的数据已经证明不可靠**：TEST 有一条记录（`2082292518405345282`）的 `structure_id` 直接写成了 `paper_id`——因为查询按三元组过滤，这个错值从未被发现，但也说明 `structure_id` 并没有真正承担"定位"职责；
3. **"不能做唯一键"不是保留理由**：131 / 106 组重复确实存在，但业务语义始终是「取 `ORDER BY updated_time DESC LIMIT 1`」，从来不需要唯一约束。

**剩下的硬骨头只有 3 张表**：`writing_attempt`(217) / `speaking_attempt`(283) / `option_pool`(2505) 只有 `paper_id + structure_id`，没有部分号。给它们补 `section_mapping + section` 并回填，就能真正 drop 表。这一步放 P2，因为：
- 回填要从 `practice_paper_structure` join，而该表有 479 条雪花 ID（不可重算）需逐一核对；
- 收益是"少一张已无信息量的表"，不是功能。

**P0 之后这张表的新定位**：`(paper_id, content_type, section) → structure_id` 的**稳定映射**，5 列、1201 行、只增不改。

### ADR-11 `practice_record` 定位键改用三元组，删除 `practice_name`

| 方案 | 定位键 | 名称来源 | 评价 |
|---|---|---|---|
| **A. 三元组 + 现算名称（采纳）** | `(paper_id, section_mapping, section)` | `parts_config.partName` 现算 | 少 2 列、无影子数据、接口不再暴露内部 ID |
| B. 保留 `structure_id` | `structure_id` | `practice_name` 快照 | 现状：多一份冗余 + 一份格式混乱的快照 |
| C. 三元组 + 保留 `practice_name` | 三元组 | 快照 | 名称与配置可能长期不一致，反而更糟 |

**`practice_name` 该删的决定性证据**：实测它与 `structure.section_name` **100% 完全相同**（TEST 905/905、PROD 1343/1343）——纯粹是复制，没有一比特独立信息。而 `section_name` 已被 `parts_config.partName` 取代。

**顺带修正 v1.2 的一个误判**：`第1部分`(649) 与 `第一部分`(257) 的差异，不是"同一板块两种写法"，而是**听力模块用阿拉伯数字、阅读模块用中文数字**。这是模块间格式不统一，改由 `parts_config` 统一供给后自动消失。

**为什么不是"设计可行"而是"已验证等价"**：`selectByStructure` 的内部实现就是 `JOIN part_setting ON q.section = pps.section_code`——`structureId` 只是三元组的代理键。新旧路径实测取题数：TEST 905/907（差 1 条脏记录）、**PROD 1343/1343 零差异**。且 `selectByPart` 方法早已存在。

**"接口不要 ID"的收益不只是好看**：
- 前端不用先查目录拿 `structureId` 再回传，只要有 `paperId + partNo` 就能开练；
- 服务端不再有"`structureId` 属于哪个模块"的校验需求（`sectionMapping` 由路径隐含），从根上消灭"拿写作的 `structureId` 打翻译接口"这类串号（原 §6 的 `SECTION_MAPPING_MISMATCH` 校验可简化）；
- 目录接口的 `structureId` 变成纯展示字段（甚至可下线），前后端契约更稳定。

**代价**：`practice_report` 也要删 `structure_id`；`writing_attempt` / `speaking_attempt` 暂不能改（见 ADR-10），所以**同一套接口风格会短期不一致**——听力/阅读用 `section`，写作/口语仍用 `structureId`。P2 统一。

---

## 10\. 修订记录

| 版本 | 修改内容 | 修改人 | 日期 |
|---|---|---|---|
| v1.0 | 初稿：双版本目录改造、翻译独立模块、聚合接口、数据缺口与 ADR | | 2026-11-10 |
| **v1.1** | **改为「基于既有 5 张题库表改造」口径**：① §3.1.2 重画为内容层/编排层/作答层三层模型；② §3.2.1 明确五表逐表改造判定（零 DDL）+ `deleted_prac` 与运营上下架的 AND 关系；③ 新增 §3.2.2 三处语义冲突裁定（口语双轨 / 部分号基址 / answer_mode 不可由 layout 推导）；④ §3.2.4 派生口径补上基址映射与一致性校验 SQL；⑤ 新增 §3.2.5 collation 陷阱（D10）、ADR-07/08/09；⑥ D1/D4/D7 由「手工补配置」降级为「跑脚本」；⑦ 新增 B-09/B-10、D9/D10/**D11（PROD 缺 `deleted_prac`）** | | 2026-11-10 |

| **v1.2** | **架构简化：两张行式表退场**。① `practice_paper_structure` + `practice_part_setting`（1201+1201 行）退场，板块配置只保留 `practice_module_level_config.parts_config`（49 行，实测 100% 覆盖 §3.2.6）；② §3.1.2 改为「内容层 / 配置层」两层，编排层消失；③ **基址映射与 D1/D2/D7/D9 四条缺口一并消失**；④ 新增 §3.2.4 读时装配口径（不再派生写库）、§3.2.7 `structure_id` 归属；⑤ 新增 ADR-10（ID 注册表不可删）、重写 ADR-08/09；⑥ 新增缺口 N4/N5（`parts_config` 缺 `typeCode`/`answerMode`）、规则 R7/R8/R9；⑦ 附录 C 重排（先换源后补数据，P0-e 为最大回归点） | | 2026-11-10 |
| **v1.3** | **`practice_record` 瘦身 + `structure_id` 分层退出**。① §3.2.8 新增：删 `structure_id` + `practice_name`，**启用已存在但空着的 `question_ids` 作题目快照**；② 接口从 `structureId` 改为 `(paperId, section)`，`structureId` 不再落库；③ §3.2.7 重写为分层退出（`practice_record` 963 / `practice_report` 477 先走，`writing_attempt` / `speaking_attempt` / `option_pool` 留 P2）；④ **ADR-10 翻案**（不再"整表必须留"），新增 ADR-11；⑤ 新增规则 R10、阶段 P0-h；⑥ 附录 A 补 `practice_record` 专项实测（含 `practice_name` 数字体系混用、`structure_id` 脏值、`question_ids` 填充率） | | 2026-11-10 |

---

## 附录 A：实测数据基线（2026-11-10，只读侦察）

| 项 | TEST | PROD |
|---|---|---|
| `exam_paper`（`exam_type=1`）HSK2.0 | 121 卷（L1–4 各 20、L5 21、L6 20） | 61 卷（L1 11、L2–6 各 10） |
| `exam_paper`（`exam_type=1`）HSK3.0 | 15 卷（L1–4 各 3、L5/L6/L7 各 1） | 15 卷（同） |
| HSK7-9 卷的 `level` 原值 | **`"7"`** | **`"7-9"`** ← 🔴 两库不一致 |
| `practice_module_level_config` HSK2.0 | 21 行（LISTEN 6 / READ 6 / SPEAK 3 / WRITE 6，WRITE 中 4 行 enabled） | 同 |
| `practice_module_level_config` HSK3.0 | **28 行**（LISTEN 7 / READ 7 / SPEAK 5 / SPEAKING 1 / TRANSLATION 1 / WRITE 7） | **0 行** ← 🔴 |
| `practice_paper_structure` HSK2.0 | 1066 行 | — |
| `practice_paper_structure` HSK3.0 | **135 行**（LISTEN 44 / READ 51 / SPEAK 15 / WRITE 24 / TRANSLATION 1） | **0 行** ← 🔴 |
| `practice_part_setting` 的 `answer_mode` 取值域 | SINGLE / MATCH / ORDER / RECORD / **TEXT** | SINGLE / MATCH / ORDER / RECORD（无 TEXT） |
| 翻译的 structure / part_setting | 1 / 1（仅笔译 `section_code=1`、`answer_mode=TEXT`） | 0 / 0 |
| 翻译题（`question.section_mapping='SEC_TRANSLATION'`） | 4（笔译 2 + 口译 2，`answer='(略)'`，正文在 `passage`） | 4（同） |
| `writing_evaluation_policy` 覆盖题型 | WORD_ORDER / HANZI_INPUT / PICTURE_SENTENCE / KEYWORD_ESSAY / SUMMARY_WRITING | 同（**均无 `TRANSLATION_WRITTEN`**） |
| `writing_attempt`（按卷版本） | HSK2.0 217 条 | HSK2.0 284 条（**无 HSK3.0 / 翻译记录**） |
| `practice_record` | READ 257 / LISTEN 649 / CSCA 57 | READ 482 / LISTEN 861 / CSCA 21 |
| `speaking_exam_paper` | HSK2.0 33 / HSK3.0 5 | HSK2.0 33 |
| `hsk_level_config` | HSK2.0 6 行（L1–6）/ HSK3.0 7 行（L1–7） | 同 |
| **`question` 里的 3.0 板块分布**（按 `section_mapping`） | LISTEN 15 卷 / READ 12 卷 / WRITE 6 卷 / **TRANSLATION 1 卷 4 题** / **SPEAKING 1 卷 5 题** | 同 |
| **3.0 各卷题量**（听/读/写/译/说） | L1 24/24/0/0/0、L2–L4 约 30/32/12/0/0、L5 35/35/2/0/0、L6 40/40/2/0/0、**L7 40/40/2/4/5** | 同 |
| **口语 3.0 双轨** | `exam_paper` 1 卷 5 题 + `speaking_exam_paper` 5 卷（number 87–91 完全同源） | `exam_paper` 1 卷 5 题 / `speaking_exam_paper` **0 卷** ← 🔴 |
| **部分号基址一致性**（结构表 vs 题库聚合） | LISTEN 446/446、WRITE 166/166、TRANSLATION 1/1 全对；**READ 314/474** | — |
| **collation 差异** | `practice_paper_structure.version/content_type` = `utf8mb4_unicode_ci`，其余表 `utf8mb4_0900_ai_ci` | **完全相同地存在** ← 🔴 |
| **`deleted_prac` 列**（练习侧停用） | 5 张表**均已加**（2026-11-10） | 5 张表**全缺** ← 🔴 D11 |
| **三表行数**（`structure` / `part_setting` / `level_config`） | **1201 / 1201 / 49**（1:1:24） | 1066 / — / 21 |
| **`parts_config` 覆盖率** | **49 / 49 行非空（100%）**，11 个 `(version, section)` 组合键名一致 | 21 行（3.0 的 28 行为 0） |
| **`parts_config` 是否含 `typeCode` / `answerMode`** | **均不含** ← 🔴 N4 / N5 | 同 |
| **`structure.id` 号段分布** | `20…` 479（雪花）/ `70…` 608 / `80…` 114 | — |
| **历史 ID 公式可复现率** | **248 / 1201（20.6%）**，穷举 240 种组合 | — |
| **引用 `structure_id` 的表** | **7 张**，其中仅 `practice_record` 自带完整三元组 | 同 |
| **`practice_record` 行数** | **963** | **1364** |
| **`practice_record` 的 `section` / `section_mapping`** | **0 条为空**（全为模块内部分号 1–4） | **0 条为空** |
| **`practice_record.question_ids`** | **56 条非空**（全是 CSCA）/ **907 条空** | **21 条非空** / **1343 条空** |
| **`practice_record.practice_name`** | 与 `section_name` **905/905 完全一致**（纯复制）；听力 `第1部分`(649) vs 阅读 `第一部分`(257)，**模块间格式不同** | 与 `section_name` **1343/1343 一致** |
| **`practice_record.structure_id` 脏值** | **至少 1 条**（`2082292518405345282` 的值 = `paper_id`） | — |
| **同 `(user,paper,module,section)` 重复组** | **131 组**（不能做唯一键，但业务本就取最新） | **106 组** |
| **`practice_record` 索引** | 仅 `idx_record_active (user_id,paper_id,structure_id,status)` | 同 |
| **`practice_report`** | 477 行，有 `practice_record_id`，`structure_id` 冗余 | — |
| **`writing_attempt` / `speaking_attempt`** | 217 / 283 行，**只有 `paper_id + structure_id`，无部分号** | — |
| **`practice_question_option_pool`** | 2505 行，只有 `structure_id + question_id` | — |
| **`part_setting.section_code` = `question.section`** | **1087/1087 一致，0 差异** | 480/480 一致 |
| **新旧取题路径等价性**（`structure_id` vs 三元组） | **905/907**（1 条 `SEC_CSCA section=1` 脏记录） | **1343/1343 零差异** |
| **三元组查不到题的 record** | 1 条（`SEC_CSCA / section=1 / structure_id=111`） | **0 条** |

> 复跑脚本：`tmp/_probe_hsk_version.py`（只读，带 `DATABASE()` / `@@hostname` 闸门）。

---

## 附录 B：存量缺陷清单（本次顺带修）

| # | 缺陷 | 位置 | 触发条件 | 症状 | 严重度 |
|---|---|---|---|---|---|
| B-01 | `selectOne` 未带 `version` | `ListeningCatalogServiceImpl#getIntro`、`#listParts` | **TEST 已触发**：两版本同 `section_mapping + level` 各 1 行 | `TooManyResultsException` → 500 | 🔴 高（TEST） |
| B-02 | 卷查询无 `version` / 无 `exam_type` 过滤 | `ListeningCatalogServiceImpl#getLevelOverview` | **PROD 已触发**：HSK3.0 有 15 卷，L1–6 与 2.0 重叠 | 听力列表混入 3 张 HSK3.0 卷，且 `totalCount=0`（无结构行） | 🔴 高（PROD） |
| B-03 | `Integer.parseInt(paper.getLevel())` | `WritingAttemptServiceImpl#requirePaper`、`WritingCatalogServiceImpl#listParts`、`ReadingCatalogServiceImpl#paperResponse` | PROD 的 HSK7-9 卷 `level='7-9'` | `NumberFormatException` → 500 | 🔴 高（PROD，一旦放开 3.0 必炸） |
| B-04 | `parseLevel` 只认 `HSK[1-6]` | `WritingCatalogServiceImpl#parseLevel` | `levelCode=HSK7-9` | 404「写作等级不存在」 | 🟡 中 |
| B-05 | `"HSK" + level` 拼 levelCode | `Reading/Writing/SpeakingCatalogServiceImpl`、`getPreference` | level=7 | 返回 `"HSK7"`，前端查不到 | 🟡 中 |
| B-06 | `levelCode` 裸 `parseInt` | `ReadingCatalogServiceImpl#requireModule`、`ListeningCatalogServiceImpl#parseLevel` | `HSK7-9` | `NumberFormatException` → 404/500 | 🟡 中 |
| B-07 | 目录 ID 为 `Long` | `Reading/Writing/Listening` 的 Paper 响应 | 19 位雪花 | 前端 `JSON.parse` 丢末位精度 | 🟡 中（新增端点改 String，存量 P1） |
| B-08 | `writing_evaluation_policy` 缺 3 个题型 | 表数据 | `TRANSLATION_WRITTEN` / `CHART_ANALYSIS` / `TOPIC_ESSAY` | HSK3.0 写作 7-9 与翻译交卷后报告永久「生成中」 | 🟡 中 |
| **B-09** | `answer_mode` 与题型语义错配：写作类 `layout=input` 却标 `SINGLE`（`writing_short_essay`/`writing_pic_sentence` 等），而翻译 `translation_written` 标 `TEXT` | `practice_part_setting` 数据 | 3.0 作文按 `SINGLE` 渲染 → 前端可能出「单选」交互或直接空白 | 🟡 中（3.0 未上线，尚不影响现网） |
| **B-10** | HSK3.0 口语在 `question` 与 `speaking_exam_paper` 双录（同源，number 87–91 一致） | 题库数据 | 改一处不改另一处会造成同题不同内容 | 🟢 低（已由 ADR-07 冻结一侧，不再读第二份） |

> B-01 / B-02 / B-03 三条**不需要等本次改造上线就该修**：前两条现网已发生，第三条是 HSK3.0 放开的必炸点。

---

## 附录 C：落地分期

> v1.2 重排：**先改读路径（代码），再补配置（数据）**。因为配置表只有 49 行，改造成本远低于重写派生脚本。

| 期 | 范围 | 前置 | 完成判据 |
|---|---|---|---|
| **P0-a** | 修 B-01 / B-02 / B-03 三条存量缺陷 | 无 | TEST 听力 intro 不 500；PROD 听力列表不混版；HSK7-9 写作可开练习 |
| **P0-b** | `PracticeVersion` / `PracticeLevelCode` / `PracticeModuleCatalog` / **`PracticeTypeRegistry`**（题型字典：`typeCode → answerMode`） | — | 单测覆盖 `HSK7-9`、`'7-9'`、非法版本、5 种 `answerMode` |
| **P0-c** | 16 个目录端点加 `version` | P0-b | HSK2.0 全链路零回归 |
| **P0-c2** | **`parts_config` 补键 N4/N5**（`typeCode` + `answerMode`），49 行一次性刷新 | P0-b 的字典定稿 | 每个板块都能按 `typeCode` 找到 `answerMode`，无一条回退 |
| **P0-d** | 聚合接口 `GET /hsk/modules` | P0-c | 2.0 四卡 / 3.0 五卡，布局与角标正确 |
| **P0-e** | **重写 `PracticeCatalogBatchLoader`**：从「查 structure + part_setting」改为「读 `parts_config` + 算题量」 | P0-c2 | 2.0 四个模块目录与现网**逐字段一致**；结构表停写 |
| **P0-f** | 翻译目录 4 + 写链路 6 + `validatePart` 放宽 | P0-e（目录装配已换源） | 翻译笔译/口译都可练到交卷；写作 `structureId` 打翻译 → 400 |
| **P0-g** | **数据补全：PROD 补 28 行 `parts_config`（D4）+ level 收敛（D3）+ `deleted_prac` DDL（D11）** | **D11 的 DDL 最先**；五闸门 + DRY-RUN + 备份 | PROD 切 3.0 五卡有数据 |
| **P0-h** | **`practice_record` 瘦身**：删 `structure_id` + `practice_name`；重建 `idx_record_active` 为 `(user_id, paper_id, section_mapping, section, status)`；7 处 Mapper 改三元组（`selectByStructure` → 已存在的 `selectByPart`）；`question_ids` 全模块启用；接口 `structureId` → `(paperId, section)` | P0-e（目录已换源，前端已能拿 `partCode`） | ① 抽 100 条历史记录，新旧路径取题 **ID 列表完全一致**（PROD 已实测 1343/1343）；② `EXPLAIN` 走新索引；③ HSK 新记录 `question_ids` 非空且 `JSON_LENGTH = total_questions` |
| P1 | 偏好表加 `version`；ID 改 String；`dataVersion` ETag；角标后台可配；补 `TRANSLATION_WRITTEN` 策略；**D10 collation 对齐**；B-09 修正；`parts_config` 补 N6（板块级 enabled/时长/满分/提示语） | P0 上线观察 | — |
| P2 | **彻底删 `practice_paper_structure`**：先给 `writing_attempt`(217) / `speaking_attempt`(283) / `option_pool`(2505) 加 `section_mapping + section` 并回填，再 drop；口译 ASR + 自动评分 | P0-h 稳定运行 + 回填核对完 479 条雪花 ID | — |

> 🔴 **最大的风险点是 P0-e**：它是唯一会改变 2.0 现网行为的改造（目录数据源换源）。
> 验收方法：同一批 16 个请求（4 模块 × versions × levels），新旧接口响应 **JSON 逐字段 diff 必须为空**。建议先把旧实现的结果快照存盘再对比。
>
> ✅ **P0-g 已经从"跑派生脚本写 1201 行"降为"补 28 行 JSON"**——这是删掉两张表带来的直接收益。
> 顺序：**P0-a → P0-b → P0-c2（键补齐）→ P0-c → P0-e（换源，重点回归）→ P0-f（翻译）→ P0-g（PROD 补数据）**。
