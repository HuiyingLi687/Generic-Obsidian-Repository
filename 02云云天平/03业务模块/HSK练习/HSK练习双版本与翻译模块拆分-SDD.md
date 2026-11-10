# HSK 练习双版本（2\.0 / 3\.0）与翻译模块拆分 · 软件设计文档

> 定位：本文档回答【怎么做】——HSK 练习如何同时支撑 2.0 / 3.0 两套大纲，以及「翻译」如何从写作模块里拆成独立入口。
> 服务：`practice-service`（网关前缀 `/api/practice`）
> 依据：2026-11-10 双版本首页 UI 截图（2.0 四宫格 / 3.0 五行列表）+ 代码基线 + TEST / PROD 实测
> 文档版本：v1.6｜更新日期：2026-11-10｜状态：**待评审**
> 前置：[HSK练习模块首页-设计方案](HSK练习模块首页-设计方案.md)、[HSK翻译练习-独立模块接口方案](HSK翻译练习-独立模块接口方案.md)、[HSK练习-共用题库方案](HSK练习-共用题库方案.md)
> 🔴 **本文纠正前置文档的三处过时结论**，见 §9 ADR-06
> 🔴 **v1.2 口径（架构简化）**：**`practice_paper_structure` 与 `practice_part_setting` 退场**，板块配置只保留 `practice_module_level_config` 一张表（用其 `parts_config` JSON）。内容侧不新建任何表，翻译 4 题、口语 3.0 的 5 题都已在 `question` 里，只是 `section_mapping` 归属不同。
> ⚠️ **`structure_id` 分层退出**：`practice_record`（963/1364 行）与 `practice_report` 本次**直接删列**，改用 `(paper_id, section_mapping, section)` 三元组；`writing_attempt` / `speaking_attempt` / `option_pool` 因缺部分号，P2 再改。详见 §3.2.7 / §3.2.8。
> 🔴 **v1.3 新增**：`practice_record` 删 `structure_id` + `practice_name`，**启用已存在但空着的 `question_ids` 作题目快照**；接口从 `structureId` 改为 `paperId + section`（ADR-11）。
> ✅ **v1.4 新增**：评审提出「卷级上下架能否并入 `practice_module_level_config`（加字段）」→ **核查后否决**，§3.2.9 / ADR-12 给出实测证据（PROD 每级 20 卷只上架 10 卷，粒度 1:N 反向）。顺带查出 **D12**（setting 孤儿行 69/56）、**D13**（PROD 的 3.0 卷 0 上架）、**B-11/B-12**；新增规则 R11/R12。
> 🔴 **v1.5 新增**：评审追问「`question_group` 不能当板块配置吗 / `practice_paper_structure` 不能直接从 `exam_paper` 推吗 / `option_pool` 也用不上」→ §3.2.10 逐项核查：**① 不能**（层级低一层 + 覆盖率仅 50%，丢 588 个板块）；**② 能，且 v1.2 已定退场**；**③ 能推但自己就不完整**（`reading_cloze` PROD 0/90）→ P2 退场。新增 **D14 / B-13 / B-14**（PROD `layout` 缺 47.7%）。**结论：板块结构 = `question` 去重 + `parts_config` 取名，不需要任何结构表。**
> ✅ **v1.6 口径变更**：产品要求「**第一部分、第二部分也能单独控制开关**」→ `parts_config` JSON **拆成行式明细表 `practice_module_part_config`**（§3.2.11 / ADR-13）。关键原因不是"JSON 不能存开关"，而是 **`parts_config` 元素里根本没有 `section`，只有 `sortOrder`**，与 `question.section` 靠数组位置隐式对齐——一旦允许关板块就必须留占位元素，位置语义立刻失效。拆表同时把 N4/N5/N6 三条缺口一起关掉（都变成有类型的列）。**表清单从 5 张变 6 张**，且新表挂 `(version, level, module, section)`（等级级 132 行），**不是**复活旧的卷级 `practice_part_setting`（1201 行）。

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
| 7 | **板块配置归并**：`practice_paper_structure` / `practice_part_setting` 退场，改由 `practice_module_part_config`（**v1.6 起行式明细表**）承载（§3.2.6 逐字段证明 / §3.2.11 拆表理由） |
| 8 | HSK3.0 配置补全口径（PROD 的 `practice_module_level_config` 3.0 行 = 0，2.0 的板块配置也只有听力 6 行） |

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
| 板块 | part | 一张卷里的一段（如「听力第 2 部分」），模板落 `practice_module_part_config`（v1.6 起行式表，一行一板块），题量由 `question` 现算 |

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
        │     ├─ 模块配置（版本×等级×模块）：practice_module_level_config（模块开关/能力描述/时长）
        │     ├─ 板块配置（版本×等级×模块×板块）：practice_module_part_config（名称三语/题型/开关）★ v1.6
        │     │                 辅：practice_paper_setting（卷级上下架）/ hsk_level_config（等级字典）
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

**结论先行：`practice_paper_structure` 与 `practice_part_setting` 在信息层面已经多余。** 它们承载的「板块名三语 / 题型名三语 / 顺序 / 题量」，全部可由 **`practice_module_part_config`**（v1.6 起行式明细表）承载，且比旧表少一个数量级（132 行 vs 1201 行）。

> 🔧 **v1.6 修正**：v1.2~v1.5 曾把板块模板放进 `practice_module_level_config.parts_config` 这个 JSON 数组。**JSON 本身没问题，问题在"没有 `section`"**——见 §3.2.11 ②。现在拆成行式表，模块级字段留主表、板块级字段下沉，**语义边界比 JSON 更清楚，而不是更碎**。

| 层         | 表                                                                              | 承载什么                                                                                   | 是否真相源                      |
| --------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- | -------------------------- |
| **内容层**   | `exam_paper` / `question` / `question_group`                                   | 版本、等级、模块归属（`section_mapping`）、题型编码（`type_id_mapping`）、部分号（`section`）、音频、题干、答案、**实际题量** | ✅ **唯一真相源**                |
| （口语分支）    | `speaking_exam_paper` / `speaking_exam_paper_question`                         | HSK**2.0** 口语卷与题（`level` 用 `Beginner/Intermediate/Advanced` 三档）                        | ✅ 2.0 口语唯一真相源              |
| **配置层**   | **`practice_module_level_config`**                                             | 版本 × 等级 × 模块：模块开关、标准总题量、建议时长、能力描述三语                            | ✅ 模块级配置源                |
|           | **`practice_module_part_config`**（v1.6 新增）                                     | 版本 × 等级 × 模块 × **板块**：板块名三语、题型编码、作答模式、标准题量、**板块开关**                              | ✅ **板块级配置源**（ADR-13）      |
|           | `practice_paper_setting`                                                       | 卷级上下架 + 卷序（运营态，**1 卷 1 行**，见 §3.2.9）                                                  | ✅ 运营                       |
| **作答层**   | `practice_record` / `writing_attempt` / `speaking_attempt` / `practice_report` | 练习记录                                                                                   | 只引用上层 ID                   |
| **（退场中）** | `practice_paper_structure` / `practice_part_setting`                           | 板块模板的**行式投影**（1201 + 1201 行，1:1 冗余）                                                    | ⚠️ 降级为 **ID 注册表**，见 §3.2.7 |

```
┌────────── 内容层（真相源）──────────┐    ┌──── 配置层（两张，语义分层）────┐
│ exam_paper                          │    │ practice_module_level_config    │
│   version / level / deleted_prac    │    │  (version, level, section_map)  │
│   ├─< question                      │    │  enabled              ← 模块开关 │
│   │    section_mapping  ← 模块归属   │    │  total_question_count           │
│   │    section          ← 部分号 1-4 │    │  suggested_duration_minutes     │
│   │    type_id_mapping  ← 题型编码   │    │  ability_description × 3 语     │
│   │    layout            ← 渲染布局   │    ├─────────────────────────────────┤
│   └─< question_group  (翻译大题包)   │    │ practice_module_part_config ★   │
│ speaking_exam_paper (仅 2.0 口语)    │    │  (version, level, section_map,  │
└───────────────┬─────────────────────┘    │   section)  ← 唯一键含板块号     │
                │  实际题量 + 实际题型        │  part_name × 3 语               │
                │                          │  type_code / answer_mode        │
                │                          │  standard_question_count        │
                │                          │  enabled    ← 板块开关（v1.6）   │
                │                          └──────────────┬──────────────────┘
                └───────────────┬─────────────────────────┘
                                ▼
              装配：part_config 当骨架，question 补实际题量（缺行按 R14 兜底）
                                │
                                ▼
              GET /{module}/papers/{id}/parts（两处查询 + 内存拼装）
                                │
                                ▼
     作答层：practice_record 用 (paperId, section_mapping, section) 定位，无 structure_id
```

> 🔴 **一句话记住**：`exam_paper.version` 管版本、`question.section_mapping` 管模块归属、`practice_module_part_config` 管板块模板与板块开关——**这三样就够了，旧的两张行式表（卷级 1201 行）是历史包袱**。
> 翻译不需要新表（4 题已在 `question`）；口语 3.0 也不需要（5 题已在 `question`）。

> ⚠️ **`structure_id` 分层退出，不必一刀切**：
> - `practice_record`（963 / 1364 行）**自带完整三元组** `(paper_id, section_mapping, section)` → 本次**直接删 `structure_id`**（§3.2.8）；
> - `practice_report` 有 `practice_record_id` 可回溯 → 同步删；
> - `writing_attempt`（217）/ `speaking_attempt`（283）/ `option_pool`（2505）只存了 `paper_id + structure_id`，**没有部分号** → 需先加两列才能删，排在 P2；
> - 只有这最后 3 张表还在用 `structure_id` 时，`practice_paper_structure` 才需要留作 ID 注册表。详见 §3.2.7。

#### 3\.1\.3 业务规则（必须落进代码的 14 条）

| # | 规则 | 落点 |
|---|---|---|
| R1 | `version` 只有 `HSK2.0` / `HSK3.0` 两个合法值，缺省 `HSK2.0`，非法 → 400 | `PracticeVersion.of` |
| R2 | `HSK7-9` 是**一个**等级，数值 `7`；禁止对 levelCode 做 `parseInt` 裸解析 | `PracticeLevelCode` |
| R3 | `exam_paper.level` 在两库取值不一致（TEST `"7"` / PROD `"7-9"`），查询必须用 `IN (候选集)` | `PracticeLevelCode.dbLevels` |
| R4 | 翻译仅 `HSK3.0`；`version=HSK2.0` 调 `/translation/**` → 返回空数组 / 空对象，**不报 404**（前端据此置灰） | `TranslationCatalogServiceImpl` |
| R5 | 口语按版本**分流读源**：2.0 → `speaking_exam_paper`（`SEC_SPEAK`），3.0 → `exam_paper` + `question.SEC_SPEAKING`；**不合并、不去重**（详见 §3.2.2 冲突 1） | `SpeakingCatalogServiceImpl` |
| R6 | 目录只下发题数 > 0 的等级 / 卷 / 板块 | 各 Catalog Service |
| R7 | **板块配置只存一处**：板块名称/题型/顺序/开关只允许写在 **`practice_module_part_config`**，禁止再往 `structure` / `part_setting` 写展示字段，也禁止回写 `level_config.parts_config`（该列 v1.6 起删除） | Code Review 卡点 |
| R8 | **实际题量必须现算**：`practice_module_part_config.standard_question_count` 是标准题量，接口下发前必须被 `question` 的实际计数覆盖 | 各 Catalog Service |
| R9 | **禁止 join 那两张退场表取展示字段**：新代码只允许从 `practice_module_part_config` + `question` 装配；`practice_paper_structure` 仅可用于 `structureId` 映射 | Code Review 卡点 |
| R10 | **`practice_record` 只认三元组**：`(paper_id, section_mapping, section)` 是定位键，`section` 存模块内部分号（`practice_part_setting.section_code`），**不得再写 `structure_id`** | 各 Record Service |
| R11 | **卷级上下架只认 `practice_paper_setting`**：`enabled=1 AND visible=1 AND deleted=0` 三条件齐备才算在架，**缺行 = 下架**（非"默认上架"）；`level_config.enabled` 是**模块级**开关，禁止用它判断某张卷是否可练 | `PracticeCatalogBatchLoader` / `requirePaper` |
| R12 | **一张卷的状态只写一处**：卷横跨 2~3 个模块（听/读/写同卷），下架必须整卷生效，禁止出现"同卷在不同模块下状态不一致" | Code Review 卡点 |
| R13 | **板块开关只认 `practice_module_part_config.enabled`**：关闭板块**不得**删题、不得改 `question.deleted`、不得过滤历史 `question_ids` 快照——只影响"新练习下发哪些板块" | 各 Catalog Service / Record Service |
| R14 | **配置缺行不阻塞目录**：装配以 `question` 去重出的 `section` 集合为主、配置表为辅；无配置行时用 `第{section}部分` 兜底命名并视为开放，**不报错、不隐藏** | 各 Catalog Service |

### 3\.2 数据库设计

#### 3\.2\.1 表的取舍总表（两退场 / 一留作配置 / 一瘦身）

| 表                                      | TEST 行数   | 处理                     | 理由                                                                                                                   |
| -------------------------------------- | --------- | ---------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `exam_paper`                           | 136 卷     | ✅ 保留，**零改**            | `version` 是版本开关；`level` 是等级；`deleted_prac` 是练习侧停用                                                                    |
| `question`                             | 万余        | ✅ 保留，**零改**            | `section_mapping` 定模块、`section` 定部分号、`type_id_mapping` 定题型                                                           |
| `question_group`                       | —         | ✅ 保留，**零改**            | 翻译 2 个大题组已在（笔译 / 口译）                                                                                                 |
| `speaking_exam_paper` / `_question`    | 33 / —    | ✅ 保留，**仅 2.0 用**       | 3.0 7-9口语走 `exam_paper`<br>3\4\5\6走`speaking_exam_paper` / `_question`                                               |
| **`practice_module_level_config`**     | **49**    | ✅ **保留，模块级配置表**       | 模块开关 / 能力描述三语 / 建议时长 / 标准题量。**v1.6 起删 `parts_config`**（板块下沉到下一行），见 §3.2.11 |
| **`practice_module_part_config`（新）** | **132**   | ✅ **新建（ADR-13）**         | 版本×等级×模块×板块：板块名三语 / 题型编码 / 作答模式 / 标准题量 / **板块开关**。行数是**等级数决定的，不随卷增长** |
| `practice_paper_setting`               | **205**   | ✅ **保留，零改**            | 卷级运营态（`visible` / `enabled` / 卷序），PROD 116 行。**粒度 = 1 卷 / 行，与 `level_config` 的 1 模块 / 行是 1:N，不可合并**（§3.2.9 / ADR-12） |
| `hsk_level_config`                     | 13        | ✅ 保留                   | 等级三语名称，与本议题无关                                                                                                        |
| **`practice_paper_structure`**         | **1201**  | ⚠️ **退场 → 瘦身为 ID 注册表** | 展示字段 100% 冗余；但 `id` 被 7 张作答表引用，不能直接drop（§3.2.7）                                                                      |
| **`practice_part_setting`**            | **1201**  | ⚠️ **退场 → 停写**         | 与 `structure` 是 **1:1**（1201:1201），一 section 一题型；信息并入 `practice_module_part_config`（**注意：新表是等级级 132 行，不是卷级 1201 行**） |
| **`practice_record`**                  | **963**   | ⚠️ **瘦身：删 2 列、启用 1 列** | 删 `structure_id`（三元组已完整）+ `practice_name`（脏快照）；启用 `question_ids` 存题目快照（§3.2.8）                                       |
| `practice_report`                      | 477       | ⚠️ 瘦身：删 `structure_id` | 有 `practice_record_id` 可回溯，冗余                                                                                        |
| `writing_attempt` / `speaking_attempt` | 217 / 283 | ⏳ P2 才动                | 只有 `paper_id + structure_id`，需先补 `section_mapping + section`                                                         |
| `practice_question_option_pool`        | 2505      | ⏳ P2 才动                | 只有 `structure_id + question_id`，是板块题目池                                                                               |

**核心事实：`parts_config` 一个 JSON 数组元素，正好等于 `structure` 一行 + `part_setting` 一行。**（v1.6 起它会被展开成 `practice_module_part_config` 的一行，见 §3.2.11）

```json
// practice_module_level_config.parts_config 的一个元素（实测原文）
{
  "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
  "typeName": "笔译",     "typeNameEn": "Written Translation", "typeNameVi": "Biên dịch viết",
  "sortOrder": 1,        "questionCount": 2
}
```
```sql
-- 展开后的目标形态（practice_module_part_config 一行）
INSERT INTO practice_module_part_config
  (version, level, section_mapping, section, part_name, part_name_en, part_name_vi,
   type_code, type_name, type_name_en, type_name_vi, answer_mode,
   standard_question_count, sort_order, enabled)
VALUES
  ('HSK3.0', 7, 'SEC_TRANSLATION', 1, '第一部分', 'Part 1', 'Phần 1',
   'translation_written', '笔译', 'Written Translation', 'Biên dịch viết', 'TEXT',
   2, 1, 1);
```

> 🔴 **三者的关系**：旧 `structure` + `part_setting`（卷级、1201 行/张）→ v1.2 的 `parts_config`（等级级、132 个元素）→ v1.6 的 `practice_module_part_config`（等级级、132 行，**唯一键含 `section`、开关可单独控制**）。**行数不变，只是从 JSON 变成列。**

#### 3\.2\.2 仍在的三处语义冲突

**冲突 1：HSK3.0 口语有两套数据，必须指定唯一读源**

| 读源 | TEST | PROD |
|---|---|---|
| `exam_paper` + `question`（`section_mapping='SEC_SPEAKING'`） | 1 卷 5 题（卷 `2104188199979532289`，number 87–91，带 `audio_url`） | **1 卷 5 题（同）** |
| `speaking_exam_paper` + `_question`（`version='HSK3.0'`） | 5 卷（3/4/5/6/7-9 级各 1） | **0 卷** ← 🔴 |

两边 `number` 87–91 完全一致，`source` 与 `exam_paper` 一一对应 —— **同源双录，不是两份内容**。

裁定：**3.0 只认 `exam_paper` + `question.SEC_SPEAKING`**；`speaking_exam_paper` 退回 2.0 专用（ADR-07）。TEST 那 5 张 3.0 口语卷冻结为历史数据。

**冲突 2：`question.section` 是模块内部分号，不再是全局号（这条反而变简单了）**

| | 原设计（结构表为主时） | 现设计（`parts_config` / `part_config` 为主） |
|---|---|---|
| 部分号来源 | `practice_paper_structure.sort_order`（全局 1–23，阅读从 5 开始） | **`question.section`（模块内 1–4）+ `part_config.section`（模块内 1–N，v1.6 起是列）** |
| 是否要基址换算 | ✅ 要（LISTEN 0 / READ 4 / WRITE 20 / TRANSLATION 22） | ❌ **不要** |

这是本次架构简化最大的收益：**基址映射整套消失**，不再需要 `PracticeSectionCode.base()`，也不会再出现「结构表 sort_order=5 而题库 section=1」的对不上。

实测佐证：结构表与题库聚合的差异，恰恰全部来自这个全局基址（听力 446/446、写作 166/166、翻译 1/1 精确，因为它们的基址恰好对上；阅读 4+1..4 有 160 行对不上，因为人工拆分与 `section` 粒度不同）。

> ⚠️ **兼容遗留**：P0 期结构表还在（作 ID 注册表），若仍需回读 `sort_order`，按 `section` 与 `part_config.section` 对齐，**不要**再用基址公式反推。

**冲突 3：`parts_config` 缺稳定题型编码与作答模式（从"提示"升级为"阻塞"）**

| `type_id_mapping` | `question.layout` | 原 `part_setting.answer_mode` | 判定 |
|---|---|---|---|
| `translation_written` | `input` | `TEXT` | 正确 |
| `writing_short_essay` | `input` | `SINGLE` | 🔴 应为 `TEXT`，存量错配（B-09） |
| `reading_sent_match` | `choice` | `MATCH` | 正确 |
| `reading_cloze` | `choiceGrid` | `SINGLE` | 正确 |
| `listening_img_match` | `choiceGrid` | `MATCH` | 正确 |

同样是 `input`，翻译是 `TEXT`、作文是 `SINGLE`；同样是 `choiceGrid`，图片匹配是 `MATCH`、完形是 `SINGLE`。**`layout` 是渲染布局，`answer_mode` 是作答交互，多对多，不能互推。**

而 `parts_config` 里**只有 `typeName`（中文名），既无 `typeCode` 也无 `answerMode`**（v1.6 拆表后这两项变成列，见 ADR-13）。所以：

裁定：**必须补 `type_code`（稳定题型编码，取 `question.type_id_mapping` 的取值域）与 `answer_mode`（`SINGLE/MATCH/ORDER/RECORD/TEXT`）**。v1.6 起这两项不再是 JSON 键，而是 `practice_module_part_config` 的**列**（ADR-13）；补齐前，`answer_mode` 只能靠 `PracticeTypeRegistry` 按 `typeName` 反查，属于临时兜底。

#### 3\.2\.3 数据缺口（9 条消失/降级，剩 7 条真阻塞）

| # | 缺口 | TEST | PROD | 影响 | 处置 | 级别 |
|---|---|---|---|---|---|---|
| ~~D1~~ | ~~HSK3.0 的 `practice_paper_structure`~~ | 135 | 0 | ~~3.0 五卡全空~~ | ✅ **消失**：目录改读 `parts_config`，不再需要结构行 | — |
| ~~D2~~ | ~~翻译口译板块缺 structure~~ | 缺 | 缺 | ~~口译不出现~~ | ✅ **消失**：`parts_config` 里**已写好两段**（笔译 2 题 / 口译 2 题，实测原文） | — |
| **D3** | `exam_paper.level` 7-9 取值不一致 | `"7"` | `"7-9"` | `parseInt("7-9")` → 500；`= '7'` 命中 0 卷 | 代码 `IN ('7','7-9')`（R3） | **P0 阻塞** |
| **D4** | `practice_module_level_config` 的 HSK3.0 行 | 28 行 | **0 行** | PROD 切 3.0 无配置 | 补 28 行 + 对应板块明细行（可参考 TEST 同构数据 / 由题库生成） | **P0 阻塞** |
| D5 | `writing_evaluation_policy` 无 `TRANSLATION_WRITTEN` | 缺 | 缺 | 笔译交卷后报告永久「生成中」 | P0 不入队，直接 `UNAVAILABLE`；P1 补策略 | P0 规避 |
| D6 | 翻译 4 题 `answer` 全为 `(略)` | 4/4 | 4/4 | AI 评分无参照 | 题库补参考译文 | P1 |
| ~~D7~~ | ~~口语 3.0 无 structure~~ | 缺 | 缺 | ~~7-9 口语看不到~~ | ✅ **消失在 D4 里**：`SEC_SPEAKING` 的 `parts_config` 已有一段（3 板块） | — |
| D8 | HSK3.0 卷数偏少 | 15 卷 | 15 卷 | 3.0 列表只有 1–3 张卡 | 题库导入 | 已知 |
| ~~D9~~ | ~~阅读部分号两套口径~~ | 160 行 | 同 | ~~派生会改现网~~ | ✅ **消失**：不再派生、不再对齐结构表 | — |
| **D10** | `practice_paper_structure.version` collation 与其他表不一致 | `utf8mb4_unicode_ci` | 同 | 跨表 version JOIN 报 `ERROR 1267` | ✅ **大幅降级**：不再 join 这张表；若 P0 仍需，代码 `CONVERT` | 降为 P1 |
| **D11** | `deleted_prac` 列 PROD 不存在 | 5 表已有 | **5 表全缺** | 目录 SQL 带 `deleted_prac=0` → `Unknown column` | 上线前 DDL | **P0 阻塞** |
| **D12** | `practice_paper_setting` 孤儿行（`paper_id` 无对应卷） | **69**（38 活跃 + 31 软删） | **56**（全活跃） | 现网无感（`IN` 天然过滤）；合并/迁移会带走脏行，运营后台按卷查为空 | P0 收尾 `DELETE ... WHERE paper_id NOT IN (SELECT id FROM exam_paper)`，五闸门 + DRY-RUN | P0 收尾 |
| **D13** | PROD 的 HSK3.0 卷 **全部未上架**（15 张卷、`practice_paper_setting` 0 行） | 15/15 已上架 | **0/15** | 3.0 开了配置也看不到卷 | 随 D4 一起补 15 行 setting（`enabled=1, visible=1, sort_order` 按导入序） | **P0 阻塞（随 D4）** |
| **D14** | `question.layout` PROD 大面积缺失 | 0 / 13524 为空（100% 有值） | **6469 / 13574 为 NULL（47.7%）**（2.0 缺 5846、3.0 缺 623） | practice-service 有 4 处依赖 `layout` 做渲染 → PROD 一半题渲染不出交互 | 按 TEST 同题回填（`type_id_mapping` → `layout` 映射）；P0 前 | **P0 阻塞** |
| ~~N4~~ | ~~`parts_config` 元素缺 `typeCode`~~ | 缺 | 缺 | ~~只能用中文 `typeName` 匹配题型~~ | ✅ **v1.6 关闭**：拆表后是 `type_code` 列，`NOT NULL` 约束 | — |
| ~~N5~~ | ~~`parts_config` 元素缺 `answerMode`~~ | 缺 | 缺 | ~~前端无法确定作答交互~~ | ✅ **v1.6 关闭**：拆表后是 `answer_mode` 列 | — |
| ~~N6~~ | ~~板块级 `enabled`~~ | 缺 | 缺 | ~~板块无法单独关停~~ | ✅ **v1.6 关闭**：拆表后是 `enabled` 列（ADR-13） | — |
| N6b | 板块级 `durationMinutes` / `fullScore` / `description` | 缺 | 缺 | 无板块级时长/满分/提示语 | P1 按需加列（同表加，不再动结构）；`duration` 可先用模块级 `suggested_duration_minutes` | P1 |
| **D15** | **PROD 的 `parts_config` 大面积为空** | 46 / 49 有值 | **6 / 21 有值**（仅 `SEC_LISTEN`）；`SEC_READ` 6 行、`SEC_WRITE` 6 行、`SEC_SPEAK` 3 行全 NULL | **板块级开关在新表里无行可建**；阅读/写作/口语只能靠 `total_question_count` | 与 D4 同一批补：按 TEST 同构 + 题库 `question.section` 现算生成明细行 | **P0 阻塞（随 D4）** |

> 🔴 **真阻塞只剩 7 条**：D3（level 取值）、D11（`deleted_prac` DDL）、D4 + **D13**（PROD 补 28 行配置 + 15 行卷上架）、**D15**（PROD 补 15 行板块配置）、**D14**（PROD 回填 `layout`）。
> 相比 v1.1 的 11 条，删掉两张表反而让缺口清单**短了一半**——因为「结构行」这个中间层不再需要复刻。
> v1.4 新增 D12/D13：前者是历史脏数据，后者是"配置补了但卷没上架"这一层被漏掉——**`level_config` 与 `paper_setting` 是两道闸，补配置不等于能练**（§3.2.9）。
> v1.5 新增 D14：`question.layout` 在 PROD 缺 47.7%，是 §3.2.10 核查 `option_pool` 能否现算时顺带查出来的——**它同时堵死了"用 `layout` 推断共享选项池"这条路**。
> v1.6 变化：**N4/N5/N6 三条由"补 JSON 键"转为"加列"而关闭**（ADR-13）；同时新增 **D15**——原以为 PROD 只是"3.0 没配置"，实测发现 **2.0 的阅读/写作/口语也没有板块配置**，缺的比想象的多。

#### 3\.2\.4 目录装配口径（不再"派生写库"，改为"读时装配"）

**旧设计**：脚本从题库派生 → 写入 `practice_paper_structure` → 接口读表。
**新设计**：接口**运行时**读 `practice_module_part_config`（+ 模块级开关）+ 聚合 `question`，**不写任何中间表**。

```sql
-- ① 模块开关与能力描述（配置层，一版本×模块 = 等级数行）
SELECT level, section_mapping, enabled, total_question_count, suggested_duration_minutes
FROM practice_module_level_config
WHERE deleted = 0 AND version = ? AND section_mapping = ? [AND level = ?];

-- ①b 板块骨架 + 板块开关（配置层，行数 = 板块数）
SELECT level, section_mapping, section, part_name, part_name_en, part_name_vi,
       type_code, type_name, answer_mode, standard_question_count, sort_order, enabled
FROM practice_module_part_config
WHERE deleted = 0 AND version = ? AND section_mapping = ? [AND level = ?]
ORDER BY level, sort_order;

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
1. 以 ①b 的板块行为骨架，按 `sort_order` 排序；**缺行时按 R14 兜底**（用 ③ 的 `section` 生成 `第{section}部分`，视为开放）；
2. 用 ③ 的 `actual_count` **覆盖** `standard_question_count`（后者是**标准题量**，不是每卷实际题量）；
3. `actual_count = 0` 的板块**不下发**（R6）；
4. 模块 `enabled = 0` → 整块模块不下发，**不再求值板块开关**（§3.2.11 ⑥ 的自上而下短路）；
5. 板块 `enabled = 0` → 该板块不下发（但不影响历史记录，R13）；
6. `type_code` / `answer_mode` 直接取列值，**不再回退 `PracticeTypeRegistry` 猜题型**。

> ✅ **收益**：不再需要派生脚本、不再需要幂等考虑、不再需要一致性校验。配置改一行，接口立刻生效；改一个板块的开关，只锁那一行。

#### 3\.2\.5 唯一键（collation 已基本无关）

| 唯一键 | 影响 |
|---|---|
| `practice_module_level_config :: uk_module_level (version, level, section_mapping)` | 已含 `version`，两版本天然共存，**无需改键** |
| `practice_user_preference :: uk_preference_user_module (user_id, section_mapping)` | **不含 version** → 两版本写同一行会覆盖，P0 靠「3.0 不写」规避（ADR-03） |
| ~~`practice_part_setting :: uk_part_code`~~ | 随表退场，不再关心 |

collation 问题（原 D10）只在新老代码仍 join `practice_paper_structure` 时出现；P0 若保留该表作 ID 注册表，查询它时仍应 `CONVERT ... COLLATE utf8mb4_0900_ai_ci`。

#### 3\.2\.6 `parts_config` 承载证明（v1.2~v1.5 的立论依据；v1.6 已拆表，本节保留作字段对照）

实测 `practice_module_level_config` 49 行，**`parts_config` 非空 46 / 49（TEST）**；11 个 `(version, section_mapping)` 组合的键名完全一致：

> 🔧 **v1.6 更正**：此前写「非空率 100%」只对 TEST 的"有值行"成立，是**统计口径错误**。真实情况：
> - TEST 49 行中 **46 行有值**，3 行为空（`SEC_WRITE` 的 2.0 L1/L2 + 3.0 L1，均 `enabled=0`）；
> - **PROD 21 行中只有 6 行有值**（全是 `SEC_LISTEN`），其余 15 行（`SEC_READ` 6 / `SEC_WRITE` 6 / `SEC_SPEAK` 3）`parts_config` 为 **NULL** → 新缺口 **D15**。
>
> 也就是说：**PROD 的阅读、写作、口语三个模块从来没有板块级配置**，只有 `total_question_count` 一个总题量。这直接影响 §3.2.11 的迁移范围与 `total_question_count` 能不能删。

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
| 板块启用 | `enabled` | ❌ | 🔴 **N6，v1.6 从 P1 提到 P0**：改为 `practice_module_part_config.enabled` 列（§3.2.11 / ADR-13） |
| 板块时长 | `duration_minutes` | ❌ | N6；可先用表级 `suggested_duration_minutes` |
| 板块满分 | `full_score` | ❌ | N6 |
| 作答提示语 | `description` | ❌ | N6 |

**必须补的字段（v1.6 起已是列，不再是 JSON 键）**，取值域直接抄题库：
- `type_code` ← `question.type_id_mapping` 的实际取值（如 `reading_img_match`、`translation_written`）
- `answer_mode` ← 原 `part_setting.answer_mode`（`SINGLE` / `MATCH` / `ORDER` / `RECORD` / `TEXT`）
- `enabled` ← 新增，板块级开关（N6）

> 拆表后这三个字段都是**有类型的列 + 唯一键保护**，不再靠 `PracticeTypeRegistry` 按中文 `typeName` 反查兜底。原 N4/N5/N6 三条一并关闭。

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

#### 3\.2\.9 卷级上下架为什么不能并入 `practice_module_level_config`（ADR-12）

**结论：不是"字段不够"，是"粒度对不上"。** `practice_paper_setting` 一行 = **一张卷**，`practice_module_level_config` 一行 = **一个 (版本, 等级, 模块)**；后者一行下面挂 **20~21 张卷**，是 1:N。加字段只能加在"1"这一侧，天然表达不了"N"侧的逐卷差异。

##### ① 决定性证据：同一配置行下，卷是「部分上架」的

PROD 现网实况（`exam_type=1`，实测）：

| version | level | 内容卷数 | 有 setting 行 | **实际上架** |
|---|---|---|---|---|
| HSK2.0 | L1 | 21 | 10 | **10** |
| HSK2.0 | L2–L4 | 各 20 | 各 10 | **各 10** |
| HSK2.0 | L5 | 21 | 10 | **10** |
| HSK2.0 | L6 | 20 | 10 | **10** |
| HSK3.0 | L1–L7 | 3/3/3/3/1/1/1 | **0** | **0** |

> 🔴 **PROD 的 HSK2.0 每个等级有 20~21 张卷，只放 10 张上线。** 也就是说 `(HSK2.0, L1, SEC_LISTEN)` 这一行配置下，卷的状态是「10 开 / 11 关」——`enabled` 是 `tinyint`，**没有任何一个取值能表示"一半开"**。
>
> 而且这是运营常态而非脏数据：6 个等级整齐划一各放 10 张，明显是刻意控制上线量。

对照 TEST：每级 20/21 张**全部上架**（136/136 有 setting 行且全开）。**只在 TEST 看一眼会误判"卷和模块是一回事"**，PROD 才暴露真实粒度。

##### ② 一张卷横跨 2~3 个模块，状态无法归属单一模块行

| 一张卷覆盖的模块数 | TEST 卷数 | PROD 卷数 |
|---|---|---|
| 2 个（如 `SEC_LISTEN + SEC_READ`） | 43 | 44 |
| 3 个（听 + 读 + 写） | 92 | 92 |
| 5 个（七级卷，含译 + 说） | 1 | 1 |

HSK 真题卷本身是"一份卷含听力/阅读/写作"，运营下架**整张卷**，不可能出现"同一张卷听力下架、阅读不下架"。

若强行把卷状态塞进 `parts_config` 或 `level_config` 的新 JSON 字段：

```json
// 反例：不采纳
{
  "partName": "第一部分", ...,
  "papers": [
    { "paperId": 2071849571936096257, "enabled": 1, "visible": 1, "sortOrder": 1 },
    { "paperId": 2071865440930000897, "enabled": 1, "visible": 1, "sortOrder": 2 }
  ]
}
```

| 问题 | 具体后果 |
|---|---|
| **状态副本 ×2~3** | 同一张卷出现在 `SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` 三行 JSON 里，下架一次要改三处，漏一处就"听力没了阅读还在" |
| **整行覆盖写** | JSON 字段无法局部更新，运营 A 下架卷 3、运营 B 同时下架卷 7 → 后写覆盖先写，**丢更新** |
| **`sort_order` 撞名** | `level_config.sort_order` 是模块排序（1~5）；`paper_setting.sort_order` 是卷在等级内的展示序（组内 21 个不同值）。塞进 JSON 后两个 `sortOrder` 语义不同，必然有人读错 |
| **行数爆炸** | 21 卷 × 6 等级 × 3 模块 ≈ 378 个卷状态片段，全部挤在 21 行 JSON 里，任何"某卷在哪一级哪一模块下架了"的运营查询都要全表解析 JSON |

##### ③ 四个开关是正交的，各管一段，缺一不可

| 开关 | 位置 | 粒度 | 管什么 | 现网是否在用 |
|---|---|---|---|---|
| `exam_paper.deleted_prac` | 内容层 | 卷 | 练习侧**内容停用**（题坏了/卷作废） | 未用（TEST 167 张全 0；PROD 该列**尚不存在**，D11） |
| `practice_module_level_config.enabled` | 配置层 | 版本×等级×模块 | 该模块在该等级**是否开放** | 在用（2.0 关 2 行，3.0 关 1 行） |
| `practice_paper_setting.enabled` | 运营层 | 卷 | 该卷**是否可用** | 在用（TEST 有 2 行为 0） |
| `practice_paper_setting.visible` | 运营层 | 卷 | 是否在客户端**列表里显示** | **全表为 1，当前未实际使用**（B-12） |
| **`practice_paper_setting` 缺行** | 运营层 | 卷 | 该卷**未纳入运营** → 视为下架 | **PROD 就是用这一手把每级 20 卷压到 10 卷**（77 张无行） |

> 代码侧证据：`PracticeCatalogBatchLoader#assemble` 用 `.eq(enabled,1).eq(visible,1).eq(deleted,0)` 三条件 `IN` 查询 `paper_id`，**查不到行即视为下架**（非 LEFT JOIN）。所以"缺行"本身就是一种运营态——这正是 PROD 77 张 `exam_type=1` 卷不在目录里的原因。
>
> ⚠️ 注意：PROD 的「每级只放 10 卷」**不是靠 `visible=0` 实现的**（`visible` 全表都是 1），而是靠**不给那 11 张卷建 setting 行**。这意味着「下架」有两种物理形态——`enabled=0` 与"无行"，读取侧必须都当"不可练"处理，这正是 R11 要固化的语义。
>
> 而 `level_config.enabled=1` 但该模块 0 张卷在架的情况，PROD 有 5 组（`SEC_SPEAK` L1–L3 因为口语卷在 `speaking_exam_paper` 里、`SEC_WRITE` L1–L2 被关），TEST 有 11 组。**两个开关各管一段，谁也不能替代谁。**

##### ④ 如果目标真是"砍表"，正解是并回 `exam_paper`，不是并进 `level_config`

`practice_paper_setting` 的主键就是 `paper_id`，与 `exam_paper.id` 是**严格 1:1**——这在范式上属于**垂直拆分**，是可以合回去的；而合进 `level_config` 是 1:N 方向的错误合并。

| 方案 | 可行性 | 评价 |
|---|---|---|
| **A. 保留独立表（采纳）** | ✅ | 116~205 行小表，语义单一，运营直接改。不改 = 零风险 |
| B. 并回 `exam_paper` 加 3 列 | ⚠️ 可行但不划算 | `exam_paper` 是**考试侧共用表**（`exam_type=1` 练习 / `2` 考试，CSCA 31 张也在里面），塞入练习运营字段会污染考试侧；且 `deleted` 与 `exam_paper` 现有 `deleted` / `deleted_prac` 撞名 |
| **C. 并进 `level_config`（用户提案）** | ❌ | 粒度 1:N 反向，见 ①②③ |
| D. 取消卷级控制，只留模块开关 | ❌ | 等于放弃"每级只放 10 卷"的运营能力，PROD 立刻多暴露 **62** 张卷（122 − 60） |

##### ⑤ 顺带查出的新缺口 D12：`practice_paper_setting` 有孤儿行

| 项 | TEST | PROD |
|---|---|---|
| setting 总行数 | 205 | 116 |
| 能 join 到 `exam_paper` | 136（= 练习卷全覆盖） | 60 |
| **孤儿行**（`paper_id` 已不存在） | **69**（38 活跃 + 31 软删） | **56（全部活跃）** |
| `exam_type=1` 卷总数 | 136 | 137 |
| 有 setting 行的卷占比 | 136/136 = 100% | 60/137 = **44%** |

孤儿行不影响现网（`IN candidatePaperIds` 天然过滤），但**任何"把 setting 并进别的表"的迁移都会把它们带过去**。P0 收尾时顺手 `DELETE FROM practice_paper_setting WHERE paper_id NOT IN (SELECT id FROM exam_paper)`（走五闸门，DRY-RUN 先跑）。

**最终裁定**：`practice_paper_setting` **保留、不改结构、不合并**。本次改造只做一件事——在读取侧明确它的定位是"卷级运营态"，与 `level_config`（模块级能力开关）**互补而非冗余**，并在 R11 里把"缺行=下架"这个隐含语义写成显式规则。

#### 3\.2\.10 能不能只用「内容 + 配置」把板块结构推出来（`question_group` / `option_pool` 逐项核查）

评审提出两问：① 前端板块配置能否直接取 `question_group`；② `practice_paper_structure` 能否直接从 `exam_paper` 结构推。**②能，①不能**，`option_pool` 是第三种情况（能推但不完整）。

##### ① `question_group` 不能当结构源：层级低一层 + 覆盖率只 50%

`question_group` **不是板块表，是板块内的"材料/大题"分组**——一篇阅读材料带 5 题、一段音频带 10 题、一个翻译大题带 2 题，各成一行。实测每板块的 group 行数：

| 一个板块内 group 行数 | TEST 板块数 |
|---|---|
| 1 行 | 380 |
| 2 行 | 102 |
| 3 行 | 35 |
| 4 行 | 32 |
| 5 行 | 43 |

**212 个板块有 2~5 个 group 行**——它是板块的**下一层**，直接当结构源会把同一个板块算成 2~5 个。

更要命的是覆盖率。从 `question` 能算出的板块组合共 **1180 个**（卷 × 模块 × 板块），其中：

| 项 | TEST |
|---|---|
| `question` 有题、`question_group` **无行**（会整块丢失） | **588 个** ← 🔴 |
| `question_group` 有行、`question` 无题（空板块） | 0 |
| `question_group` 去重板块数 | 592 / 1180 = **50%** |

丢的集中在阅读与写作（样本如 `(2072872258363949058, SEC_READ, 1)` 有 10 题但无 group 行）。**用它当结构源，一半板块直接消失。**

还有个细节：`section_title` 存的是 **"第1-10题:请判断对错."** 这种**题目区间描述**，不是板块名"第一部分"；`title1_text` 是"听力"（模块名，重复）。而且**没有 `_en` / `_vi`**——三语只能来自 `parts_config`。

> ✅ **`question_group` 的正确用法**：翻译/阅读/听力的**大题容器**（共用题干、共用音频、共用选项区间）。它与板块是 1:N，本次改造**不动它**，只在取题时按 `group_id` 挂载。

##### ② `practice_paper_structure` 确实可以从内容推出来 —— 这正是本次的既定方案

不是取 `exam_paper` 单表（那上面没有板块信息），而是 **`exam_paper` + `question` + `parts_config`** 三样拼：

| 要什么 | 从哪来 |
|---|---|
| 有哪些板块、顺序 | `question` 按 `(paper_id, section_mapping, section)` 去重 → 1180 个，**100% 覆盖** |
| 板块中文名 / 英文名 / 越南语名 | `parts_config[].partName / partNameEn / partNameVi`（按 `(version, level, section_mapping, sortOrder)` 对齐） |
| 题型名三语 / 题型编码 | `parts_config[].typeName × 3 / typeCode` |
| 标准题量 | `parts_config[].questionCount`（会被实际题量覆盖，R8） |
| **实际题量** | `COUNT(question)` 现算 |

这就是 §3.2.4 的"读时装配"——**`practice_paper_structure` 与 `practice_part_setting` 在 v1.2 就已判定退场**，不存在"一定要用它们"。

> ⚠️ 二者仍然留在库里，只因 `writing_attempt`(217) / `speaking_attempt`(283) / `question_option_pool`(2505) 还在引用它们的主键；它们是 **ID 注册表**，不再是配置源（§3.2.7）。

##### ③ `practice_question_option_pool`：数据可推，但**现在推不全**，P2 才能删

这张表是**多题共用一组选项**的池（选词填空、句子匹配、图片匹配）。实测一池 5 题，且**池内 5 题的 `option_content` 完全相同**：

```
reading_cloze（选词填空）第 51–55 题，5 题的 option_content 均为：
{"A":"向","B":"关","C":"突然","D":"同意","E":"声音","F":"世界"}
```

所以"池"在数据上是**冗余的**——同板块内 `option_content` 相同的题自然成池。理论上可用
`sha256(option_content)` 现算，不必落表。

**但现在不能删，两个硬理由：**

| 理由 | 实测 |
|---|---|
| **它自己不完整** | `reading_cloze` TEST 有 690 题、**90 题无池记录**；**PROD 的 90 道题一条池记录都没有**（0/90）→ 这张表从来不是权威源，只是某次批量导入的副产品 |
| **`pool_code` 已嵌 `structureId` 且进了答题快照** | 编码格式 `SEC_READ_{structureId}_{sha256}`；`ReadingSnapshotSupport` 把它写进 `questionSnapshot.optionPoolCode`，并带 `exclusiveSharedOptions=false`。删表要同时改快照生成 + 确认前端消费方式 |

**又不能用 `layout` 现算替代**：PROD 的 `question.layout` **有 6469 / 13574 = 47.7% 为 NULL**（HSK2.0 缺 5846、HSK3.0 缺 623），TEST 则 100% 有值。同一个题型在 PROD 一半有 `layout` 一半没有，判据不可靠。

**裁定**：`option_pool` 保留，**P2 与 `practice_paper_structure` 一起退场**。前置三件事：
1. 补 90 条缺失的池记录；
2. `pool_code` 构造去掉 `structureId`，改为 `{section_mapping}_{paperId}_{section}_{sha256(option_content)}`；
3. 答题快照里的 `optionPoolCode` 改成现算写入，不再读表。

> 🔴 顺带确认一个 D 级缺口（**D14**）：`question.layout` 在 PROD 大面积缺失（47.7%），而 practice-service 有 4 处依赖它做渲染。**3.0 上线前必须按 TEST 回填**，否则 PROD 切 3.0 会有一半题渲染不出交互。这与铁律「`layout` 是练习侧服役列、48% 空」完全对上。

##### ④ 最终表清单：**6 张**（v1.6 起），一张不多

| 层 | 表 | 角色 | 本次动作 |
|---|---|---|---|
| **内容层** | `exam_paper` | 版本 / 等级 / 卷 | 零改 |
| | `question` | 板块归属 / 部分号 / 题型 / 题干 / 实际题量 | 零改（PROD 需回填 `layout`，D14） |
| | `question_group` | 板块内的材料 / 大题容器（1:N） | 零改，**不参与结构装配** |
| | `speaking_exam_paper` / `_question` | 仅 2.0 口语 | 零改 |
| **配置层** | `practice_module_level_config` | 版本×等级×模块：模块开关、能力描述三语、建议时长 | 删 `parts_config`（迁到下一行） |
| | **`practice_module_part_config`（新增）** | **版本×等级×模块×板块：板块名三语、题型编码、作答模式、标准题量、板块开关** | **新建（ADR-13，132 行量级）** |
| **运营层** | `practice_paper_setting` | 卷级上下架 + 卷序 | 零改（ADR-12） |
| **（退场中）** | `practice_paper_structure` / `practice_part_setting` | 板块模板的行式投影 | 停写，仅作 ID 注册表 |
| **（P2 退场）** | `practice_question_option_pool` | 共享选项池 | 补 90 条 → 改 `pool_code` → 退场 |

> 🎯 **一句话**：板块结构 = `question` 去重 + `parts_config` 取名；卷能不能练 = `practice_paper_setting`；模块开不开 = `level_config`。**三张退场表都是"中间投影"，没有一张承载独有信息。**
>
> 🔧 **v1.6 修订**：此清单从 5 张变 **6 张**——板块级不再嵌在 `parts_config` JSON 里，改为独立的 `practice_module_part_config`（§3.2.11 / ADR-13）。原因是「板块级开关」这个需求，JSON 数组承载不了。

#### 3\.2\.11 板块级开关：`parts_config` 拆成行式明细表（ADR-13）

##### ① 需求：板块要能单独关，而现在没有位置放这个开关

产品诉求是「**第一部分、第二部分也能单独控制开关**」。比如 HSK2.0 L1 听力四个部分，运营只想放开前两个。

`practice_module_level_config` 现在的颗粒度是 **(版本, 等级, 模块)**，板块信息压在 `parts_config` JSON 数组里。`enabled` 只有一列、管整行——**开就是四个部分全开，关就是整模块消失**，中间没有第三档。

##### ② 决定性事实：`parts_config` 元素**根本没有 `section`，只有 `sortOrder`**

实测 TEST 49 行的 `parts_config` 元素键集合完全一致：

```
["partName", "typeName", "sortOrder", "partNameEn", "partNameVi",
 "typeNameEn", "typeNameVi", "questionCount"]
```

**没有 `section`**。也就是说，配置里的「第一部分」和题表里的 `question.section=1` 之间，**只靠"数组第几个"这种位置关系隐式对齐**。

实测这个隐式对齐目前是成立的：

| 对照项 | TEST |
|---|---|
| `parts[].sortOrder` 集合 == `question.section` 集合 | **38 行** |
| 不相等 | 8 行（**全部是 `SEC_SPEAK`**，因为 2.0 口语题不在 `question` 表） |
| `parts_config` 为空 | 3 行（`SEC_WRITE` L1/L2，`enabled=0`） |

> 🔴 **这就是"不能只在 JSON 里加个 `enabled` 键"的根因**：一旦允许"关掉第二部分"，数组就必须**保留这个元素当占位**（删了 `sortOrder` 就乱，后面的板块全部错位）。于是数组里出现"存在但关闭"的空洞，`sortOrder` 从"位置"退化成"必须连续且不可删的编号"——那它其实就是 `section`，只是藏在一个没有类型约束的 JSON 里。

##### ③ 三种落法对比

| | 做法 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| **A** | `parts_config` 元素补 `section` + `enabled` 两个键 | 0 DDL、0 迁移，改 JSON 即可 | 无唯一约束（同一 `section` 可重复写两遍）<br>无列类型（`enabled` 写成 `"0"` 字符串也存得进）<br>单板块审计做不到（只知道"这行被谁改过"，不知道"谁关了第二部分"）<br>SQL 无法 `WHERE section=2 AND enabled=0` 直接筛，只能 `JSON_TABLE` 或 `JSON_EXTRACT` | 可用，但把问题留给下一个改的人 |
| **B** | **拉平成 `practice_module_part_config`（采纳）** | 唯一键 `(version, level, section_mapping, section)` 物理防重<br>`enabled` 是列，有类型有默认值<br>改一个板块 = `UPDATE ... WHERE section=2`，只锁一行，审计精确到板块<br>顺带解决 **N4/N5/N6**（`type_code` / `answer_mode` / `enabled` 都变成列） | 多一张表（行数 132，不是 1201）<br>主表要删 `parts_config` | ✅ **采纳** |
| **C** | 单表用 `section=0` 表示"模块行"，`section>0` 表示"板块行" | 不加表 | `ability_description`×3 / `suggested_duration_minutes` 在板块行全 NULL；`part_name`×3 在模块行全 NULL。同一张表一半字段永远是空的，接口映射要处处判 `section==0` | ❌ 单表继承的经典陷阱，不值得 |

> ⚠️ **方案 B 不是"复活 `practice_part_setting`"**，这是最容易被误读的一点：
>
> | | `practice_part_setting`（退场） | `practice_module_part_config`（新增） |
> |---|---|---|
> | 挂在哪 | `structure_id` → 一张卷 | `(version, level, section_mapping)` → 一个等级 |
> | 颗粒度 | **卷级**，每卷复制一套 | **等级级**，每级一套 |
> | TEST 行数 | **1201**（卷数越多涨越快） | **132**（等级数是天花板，永不随卷增长） |
> | 数据性质 | 重复投影（同等级各卷内容相同） | 模板真源（含开关、题型编码） |
>
> 一句话：**从"每卷一份"降到"每级一份"，行数少 9 倍，且不再随题库扩容膨胀。**

##### ④ 目标表结构

```sql
CREATE TABLE `practice_module_part_config` (
  `id`                      bigint       NOT NULL COMMENT '板块配置ID（雪花ID，与现网表一致不自增）',
  `version`                 varchar(30)  NOT NULL COMMENT '考试大纲版本（HSK2.0 / HSK3.0）',
  `level`                   int          NOT NULL COMMENT 'HSK等级；与 practice_module_level_config.level 同类型同口径，HSK3.0 的 7-9 级统一存 7',
  `section_mapping`         varchar(50)  NOT NULL COMMENT '模块映射编码（SEC_LISTEN/SEC_READ/SEC_WRITE/SEC_TRANSLATION/SEC_SPEAKING）',
  `section`                 int          NOT NULL COMMENT '模块内部分号 1..N；严格对齐 question.section，是唯一键第四列',
  `part_name`               varchar(100) NOT NULL COMMENT '板块名中文（第一部分）',
  `part_name_en`            varchar(255)          DEFAULT NULL COMMENT '板块名英文',
  `part_name_vi`            varchar(255)          DEFAULT NULL COMMENT '板块名越南语',
  `type_code`               varchar(64)  NOT NULL COMMENT '题型稳定编码，取值域 = question.type_id_mapping',
  `type_name`               varchar(100)          DEFAULT NULL COMMENT '题型名中文',
  `type_name_en`            varchar(255)          DEFAULT NULL COMMENT '题型名英文',
  `type_name_vi`            varchar(255)          DEFAULT NULL COMMENT '题型名越南语',
  `answer_mode`             varchar(20)  NOT NULL DEFAULT 'SINGLE' COMMENT '作答交互类型：SINGLE/MATCH/ORDER/RECORD/TEXT（长度对齐旧 practice_part_setting）',
  `standard_question_count` int          NOT NULL DEFAULT '0' COMMENT '标准题量；下发前必须被 question 实际计数覆盖',
  `sort_order`              int          NOT NULL DEFAULT '0' COMMENT '展示顺序（与 section 可不等，仅用于编辑态排序）',
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
```

**字段设计口径（每条都有实测依据）**：

| 字段 | 口径 | 依据 |
|---|---|---|
| `id` | `bigint` 雪花，**不自增** | 与 `practice_module_level_config` / `practice_part_setting` 完全一致 |
| `level` | **`int`**，与主表同类型 | 主表 `level` 就是 `int`；新表是它的子表，**同类型才能 JOIN 不加转换** |
| `type_code` | `varchar(64)` | 旧表实测最长 25 字符，`question.type_id_mapping` 同域 |
| `type_name_en` / `_vi` | `varchar(255)` | **旧表就是 255**（实测最长 33），不收窄到 150，避免多语言扩写被截断 |
| `answer_mode` | `varchar(20)` | 旧表就是 20；实测取值只有 `SINGLE/MATCH/ORDER/TEXT/RECORD`（PROD 无 `TEXT`） |
| `standard_question_count` | 有默认值 0 | 命名带 `standard_` 前缀，是为了让"这是标准题量、不是实际题量"这件事写在列名里（防 R8 被违反） |
| `enabled` | `tinyint` 默认 1 | 与主表、旧表同类型 |
| 唯一键 | **不含 `deleted`** | 沿用现网 `uk_module_level` 风格 → ⚠️ 软删后**不能重建同键**，必须复用原行或物理清理 |

> 🔴 **`level` 的类型桥（必读）**：`exam_paper.level` 是 **`varchar`**，且两库取值不一致——TEST 是 `'7'`，**PROD 是 `'7-9'`**（D3）。而 `practice_module_level_config.level` 是 **`int`**，TEST 的 3.0 配置用的就是 `1..7`。
> 所以新表**必须跟主表走 `int`**，并在迁移/写入时把 `'7-9'` 归一到 `7`：
> - 读：`exam_paper.level IN ('7','7-9')`（D3 候选集）→ 归档到 `level = 7` 的板块配置；
> - 写：永远写 `7`，**不要**把 `'7-9'` 塞进 `int` 列（会截断成 7，MySQL 非严格模式下静默通过，严格模式下直接报错）。
>
> 反过来若为省事把新表 `level` 定成 `varchar`，就与主表 `int` 跨类型 JOIN，索引失效 + 隐式转换 - 得不偿失。

主表随之收窄：

```sql
ALTER TABLE `practice_module_level_config` DROP COLUMN `parts_config`;
-- 保留：ability_description×3 / suggested_duration_minutes / enabled / sort_order / total_question_count
```

> 🔴 **`total_question_count` 这次不能删**。TEST 里 46/46 行它都等于 `SUM(parts[].questionCount)`，看着是纯派生值；但 **PROD 有 15 行 `parts_config` 为 NULL**（见 D15），此时 `total_question_count` 是这些模块**唯一的题量来源**。等 PROD 板块配置补齐、且校验 SUM 一致之后，再评估降级为派生字段（P2）。

##### ⑤ 迁移映射：`sortOrder` → `section`，8 行口语是例外

| 情况 | 行数 | 迁移口径 |
|---|---|---|
| `sortOrder` 集合 == `question.section` 集合 | **38**（TEST） | 直接 `section = sortOrder`，可脚本批量，零人工 |
| `SEC_SPEAK`（2.0 L1–L3、3.0 L3–L6、3.0 L7） | **8** | 见下方说明 |
| `parts_config` 为空 | 3（TEST）/ 15（PROD） | 不生成明细行，等 D15/D4 补数据 |

**口语这 8 行为什么特殊**：`speaking_exam_paper_question` 表**没有 `section` 列**（实测列：`id / paper_id / number / question_group / question_type / question_type_mapping / passage / ...`），只有 `number` 题号。所以 2.0 口语的"第一部分/第二部分/第三部分"**在内容层完全无法推导**——它只能来自配置。

> 🎯 这一点顺带回答了一个更根本的疑问：**板块配置不是"可以完全从内容推出的投影"**。听力/阅读/写作的板块能从 `question.section` 去重得到（v1.5 §3.2.10 已证 1180 个组合 100% 覆盖），但**口语不行**。配置层必须存在，而且必须显式存 `section`。

3.0 口语另有一个编码分裂问题（**B-15**）：TEST 里 `SEC_SPEAK` 有 5 行配置（L3–L7）、`SEC_SPEAKING` 有 1 行（L7），而 `question` 表里 3.0 的 `SEC_SPEAK` **0 题**、`SEC_SPEAKING` 3 题；且 L7 两行内容完全相同（应用读说 / 听材料回答问题 / 观点表达）。迁移时必须先统一到 `SEC_SPEAKING`，否则会写出 6 个板块行、其中 3 行是永久孤儿。

##### ⑥ 四级开关的求值顺序（缺一级就会"关不掉"或"多关"）

| 级 | 开关 | 粒度 | 关掉之后 |
|---|---|---|---|
| L1 版本 | 前端选择 / `exam_paper.version` | 版本 | 整版不出现 |
| L2 模块 | `practice_module_level_config.enabled` | 版本×等级×模块 | 该模块整卡消失，**不再求值板块开关** |
| L3 卷 | `practice_paper_setting.enabled` / `visible` / 缺行 | 卷 | 该卷不在列表 / 不可进入 |
| L4 **板块** | **`practice_module_part_config.enabled`** | 版本×等级×模块×板块 | 该板块在目录不出现，新练习不下发其题目 |

求值必须**自上而下短路**：L2 关 → 整模块返回 `[]`，不要去查板块；L2 开 → 按 L3 取在架卷，再按 L4 过滤板块。反过来（先查板块再看模块）会做出"模块关了但接口仍去查 132 行配置"的无用功，也会让缓存键多带一个维度。

##### ⑦ 兜底规则：配置缺行不能阻塞目录

新增规则 **R14**：装配时以 `question` 去重出的 `section` 集合为**主**，`practice_module_part_config` 为**辅**。

- 有题、有配置行 → 用配置的名称/题型/开关；
- 有题、**无配置行** → 用 `第{section}部分` 兜底命名，`enabled` 视为 1，**不报错、不隐藏**；
- 无题、有配置行 → 该板块不出现（无题即无板块，配置行保留供恢复）。

理由：配置是运营数据，题库是业务事实。让"漏配一行"导致整模块不可用，是把运营失误放大成线上故障。

##### ⑧ 关闭板块后，历史记录怎么算

| 对象 | 行为 |
|---|---|
| 已生成的 `practice_record.question_ids` 快照 | **不受影响**，仍可回看、仍可出报告（快照是题目 ID 列表，不依赖板块开关） |
| 新开练习 | 该板块题目**不再下发** |
| 报告/成绩单 | 按快照聚合，板块仍显示（历史上确实做了），但标注"该板块已关闭" |

> 🔴 不要把"板块关闭"实现成"删题"或"过滤 `question_ids`"——那会让历史报告凭空少题、分数对不上。

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
| 板块配置缺行（R14） | **不报错、不隐藏**：用 `第{section}部分` 兜底命名、`enabled` 视为 1，记一条 `WARN` 日志便于运营补配 |

#### 3\.3\.7 板块开关的读写边界（v1.6 新增）

| 侧 | 行为 | 端点 |
|---|---|---|
| **学员端（C 端）** | 只读。目录/开始练习按 `enabled` 过滤，**不暴露开关字段**，前端不需要感知 | 既有 16 端点，零新增 |
| **运营端（管理后台）** | 增删改板块配置行；改 `enabled` 即"上下架一个板块" | `PATCH /hsk/module-config/parts/{id}`、`GET /hsk/module-config/parts?version=&level=&sectionMapping=` |
| **本次不做** | 批量上下架、板块级灰度、按用户/机构差异化开关 | — |

> 🔴 **C 端响应结构不变**：`parts[]` 里仍只返回 `partCode / partName×3 / typeCode / answerMode / questionCount`，**不加 `enabled`**——开关是服务端过滤条件，不是给前端的展示字段。这样 2.0 现网响应可以逐字段 diff 为空（P0-e 验收要求）。

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

### 8\.5 板块开关（v1.6 新增）

23. 把 `HSK2.0 / L1 / SEC_LISTEN / section=2` 置 `enabled=0` → 目录只剩第一部分/三/四；**另三个板块的题量、名称、题型不受影响**。
24. 同上，新开一次练习 → 下发的题**不含** section=2；已存在的历史记录仍可打开、报告题数不变（R13）。
25. 关掉某板块后，`GET /{module}/papers/{id}/parts` 的响应里**不出现该板块**，且 `totalQuestions` 相应减少。
26. 把整模块 `level_config.enabled=0` → 整卡消失，**不再受板块开关影响**（短路顺序，§3.2.11 ⑥）。
27. 删除某板块配置行（或库里本来就没有，PROD 阅读现状 D15）→ 该板块仍出现，名称为兜底 `第N部分`，**不报错**（R14）。
28. 双写期一致性：改一次板块名 → `practice_module_part_config` 与 `parts_config` 两处都变；连续 100 次随机变更后 `diff` 为空（P0-i 删列的前置）。
29. 并发改同一模块下不同板块（线程 A 改 section=1、B 改 section=2）→ 两条都生效，**无覆盖丢失**（这是选方案 B 而非"JSON 加键"的核心理由）。

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

### ADR-12 卷级上下架留在 `practice_paper_setting`，不并入 `practice_module_level_config`

| 方案 | 粒度 | 能否表达「同级 20 卷只放 10 张」 | 评价 |
|---|---|---|---|
| **A. 保留独立表（采纳）** | 1 卷 / 行 | ✅ | 116~205 行小表，零 DDL、零迁移 |
| B. 并进 `level_config` 加字段 | 1 (版本,等级,模块) / 行 | ❌ | **粒度 1:N 反向**，`enabled` 只能全开或全关 |
| C. 并进 `level_config` 加 JSON 卷数组 | 同上 | ⚠️ 勉强能存 | 状态副本 ×2~3、整行覆盖写、`sortOrder` 撞名，见 §3.2.9② |
| D. 并回 `exam_paper` 加 3 列 | 1 卷 / 行 | ✅ | 范式上合法（1:1 垂直拆分的回归），但污染考试侧共用表 |
| E. 取消卷级控制 | — | ❌ | 放弃运营能力，PROD 立刻多暴露 62 张卷 |

**提案背景**：评审时提出「`practice_paper_setting` 能否用 `practice_module_level_config` 加字段替代，少一张表」。**核查后否决**，理由不是"字段不够"，而是**两张表的粒度是 1:N 关系**（一个配置行下挂 20~21 张卷），加字段加在"1"侧，管不了"N"侧的逐卷差异。

**决定性数据**（PROD 现网）：HSK2.0 每级有 20~21 张卷，**只放 10 张上架**（6 个等级整齐各 10 张，是刻意控量）。`enabled` 是 `tinyint`，**没有任何取值能表示"一半开"**。TEST 每级全上架，只看 TEST 会误判两者是一回事——这是本 ADR 最容易踩的坑。

**第二个不可合并点**：一张 HSK 真题卷同时属于 2~3 个模块（TEST 43 张 2 模块、92 张 3 模块、1 张 5 模块），运营下架是**整卷级**的。塞进模块级 JSON 后，同一张卷的状态要写进 2~3 行，改一次要改多处，必然分叉。

**两个开关的正交关系**（都保留、各管一段）：

| 开关 | 管什么 | 粒度 |
|---|---|---|
| `level_config.enabled` | 该模块在该等级**是否开放**（能力开关） | 版本 × 等级 × 模块 |
| `paper_setting.enabled` + **缺行** | 该卷**是否可用**（运营开关）；缺行同样算下架 | 卷 |
| `paper_setting.visible` | 该卷是否上列表（**现网全 1，未使用**，B-12） | 卷 |

实测「`level_config` 说模块开、但 0 张卷在架」的组合：PROD 5 组、TEST 11 组（口语卷在 `speaking_exam_paper` 里、写作 L1–L2 被关），证明两者不能互相替代。

**若确实要砍表**：正解是方案 D（并回 `exam_paper`），因为 `practice_paper_setting.paper_id` 就是主键、与 `exam_paper.id` 严格 1:1，属垂直拆分回归。但 `exam_paper` 是考试侧共用表（`exam_type=1/2`，CSCA 31 张也在内），塞入练习运营字段会污染考试侧，且 `deleted` 与现有 `deleted` / `deleted_prac` 撞名——**收益（少一张 116 行小表）远小于代价**，故不采纳。

**顺带发现 D12**：`practice_paper_setting` 存在孤儿行（TEST 69 / PROD 56，`paper_id` 已无对应卷）。现网被 `IN candidatePaperIds` 天然过滤、无感知，但任何合并/迁移都会把它们带过去 → P0 收尾顺手清理（走五闸门 + DRY-RUN）。

---

### ADR-13 板块配置从 `parts_config` JSON 拆成行式明细表 `practice_module_part_config`

**背景**：产品要求「第一部分、第二部分也能单独控制开关」。现有 `practice_module_level_config.enabled` 只有整行一档——关了就整模块消失，无法只关某个板块。

**候选方案**

| 方案 | 做法 | 否决理由 |
|---|---|---|
| A | `parts_config` 元素补 `section` + `enabled` 两个键 | 可行但不彻底：无唯一约束（同 `section` 可重复）、无列类型（`"0"` 字符串也存得进）、单板块审计缺失、SQL 只能 `JSON_EXTRACT` 过滤 |
| B | **拉平成 `practice_module_part_config`** | ✅ **采纳** |
| C | 单表 `section=0` 表示模块行、`section>0` 表示板块行 | 一半字段永远 NULL，接口处处判 `section==0`，单表继承陷阱 |
| D | 不拆，用"整模块开关 + 前端隐藏板块" | 前端隐藏不是控制——题目仍会下发，用户仍能练到被"隐藏"的板块 |

**采纳 B 的三个理由**

1. **JSON 数组里根本没有 `section`，只有 `sortOrder`。** 实测键集合固定为 8 个，不含 `section`。配置与题表靠"数组第几个"隐式对齐（38/46 行成立）。一旦要允许"关掉第二部分"，数组就必须留占位元素（删了位置全乱），`sortOrder` 就退化成"不可删的编号"——**那它本来就该是 `section` 列**。
2. **开关是运营会反复单独改的状态。** 行式表可以 `UPDATE ... WHERE section=2`，只锁一行、`update_by` 精确到板块；JSON 方案要么读改写整行（并发互覆），要么 `JSON_SET` 定位数组下标（下标随排序变动而脆）。
3. **行数天花板由等级数决定，不由卷数决定。** 旧 `practice_part_setting` 挂 `structure_id`（卷级）→ 1201 行且随题库扩容膨胀；新表挂 `(version, level, section_mapping, section)` → 132 行封顶。**这是"降粒度"而不是"复活旧表"。**

**代价与边界**

- `practice_module_level_config` 要 `DROP COLUMN parts_config`——**一次性双写过渡**（P0 期先双写、比对一致后再删列），不可直接 cut over。
- `total_question_count` **本次保留**：PROD 有 15 行没有 `parts_config`（D15），它是这些模块唯一的题量来源。待 D15 补齐且 `SUM` 校验一致后（P2）再评估降级。
- 2.0 口语（`SEC_SPEAK`）无法从内容推导板块（`speaking_exam_paper_question` 无 `section` 列），迁移时按 `sortOrder` 直接映射、人工抽验 3 级 × 3 板块。
- 3.0 的 `SEC_SPEAK` / `SEC_SPEAKING` 编码分裂（B-15）必须先统一，否则会写出 3 行永久孤儿。

**结论**：新建 `practice_module_part_config`，主表删 `parts_config`；新增规则 **R13**（板块开关只改这一列，不许删题）/ **R14**（配置缺行不阻塞目录）。N4/N5/N6 三条缺口随之关闭。

---

## 10\. 修订记录

| 版本 | 修改内容 | 修改人 | 日期 |
|---|---|---|---|
| v1.0 | 初稿：双版本目录改造、翻译独立模块、聚合接口、数据缺口与 ADR | | 2026-11-10 |
| **v1.1** | **改为「基于既有 5 张题库表改造」口径**：① §3.1.2 重画为内容层/编排层/作答层三层模型；② §3.2.1 明确五表逐表改造判定（零 DDL）+ `deleted_prac` 与运营上下架的 AND 关系；③ 新增 §3.2.2 三处语义冲突裁定（口语双轨 / 部分号基址 / answer_mode 不可由 layout 推导）；④ §3.2.4 派生口径补上基址映射与一致性校验 SQL；⑤ 新增 §3.2.5 collation 陷阱（D10）、ADR-07/08/09；⑥ D1/D4/D7 由「手工补配置」降级为「跑脚本」；⑦ 新增 B-09/B-10、D9/D10/**D11（PROD 缺 `deleted_prac`）** | | 2026-11-10 |

| **v1.2** | **架构简化：两张行式表退场**。① `practice_paper_structure` + `practice_part_setting`（1201+1201 行）退场，板块配置只保留 `practice_module_level_config.parts_config`（49 行，实测 100% 覆盖 §3.2.6）；② §3.1.2 改为「内容层 / 配置层」两层，编排层消失；③ **基址映射与 D1/D2/D7/D9 四条缺口一并消失**；④ 新增 §3.2.4 读时装配口径（不再派生写库）、§3.2.7 `structure_id` 归属；⑤ 新增 ADR-10（ID 注册表不可删）、重写 ADR-08/09；⑥ 新增缺口 N4/N5（`parts_config` 缺 `typeCode`/`answerMode`）、规则 R7/R8/R9；⑦ 附录 C 重排（先换源后补数据，P0-e 为最大回归点） | | 2026-11-10 |
| **v1.3** | **`practice_record` 瘦身 + `structure_id` 分层退出**。① §3.2.8 新增：删 `structure_id` + `practice_name`，**启用已存在但空着的 `question_ids` 作题目快照**；② 接口从 `structureId` 改为 `(paperId, section)`，`structureId` 不再落库；③ §3.2.7 重写为分层退出（`practice_record` 963 / `practice_report` 477 先走，`writing_attempt` / `speaking_attempt` / `option_pool` 留 P2）；④ **ADR-10 翻案**（不再"整表必须留"），新增 ADR-11；⑤ 新增规则 R10、阶段 P0-h；⑥ 附录 A 补 `practice_record` 专项实测（含 `practice_name` 数字体系混用、`structure_id` 脏值、`question_ids` 填充率） | | 2026-11-10 |
| **v1.4** | **卷级上下架归属裁定（评审提案否决）**。① 新增 §3.2.9：从粒度、跨模块、开关正交三个角度证明 `practice_paper_setting` 不能并入 `level_config`，并给出「若真要砍表应并回 `exam_paper`」的正解；② 新增 **ADR-12**；③ 新增规则 **R11**（缺行 = 下架）/ **R12**（卷状态只写一处）；④ 新增缺口 **D12**（setting 孤儿行 TEST 69 / PROD 56）、**D13**（PROD 的 HSK3.0 卷 0 上架）；⑤ 附录 B 新增 **B-11/B-12**；⑥ **附录 A 更正 PROD HSK2.0 卷数 61 → 122**（原数实为"上架卷数"，内容卷数被低估）；⑦ §3.2.1 补 `practice_paper_setting` 行数，P0-g 补「3.0 卷上架 + 孤儿行清理」 | | 2026-11-10 |
| **v1.5** | **「只用内容+配置能否推出板块结构」专项核查**。① 新增 §3.2.10：`question_group` 不能当结构源（层级低一层，一板块含 1~5 个 group；覆盖率 592/1180 = 50%，丢 588 个板块；`section_title` 是题号区间描述且无三语）；`practice_paper_structure` 可由 `exam_paper + question + parts_config` 现算（v1.2 已定退场）；`option_pool` 数据冗余可推但自身不完整（`reading_cloze` PROD 0/90），P2 带 3 步前置退场；② 新增最终表清单（5 张：3 内容 + 1 配置 + 1 运营）；③ 新增缺口 **D14**（PROD `question.layout` 缺 47.7%）、缺陷 **B-13/B-14**；④ P0-g 补 `layout` 回填，P2 补 `option_pool` 三步前置；⑤ 附录 A 补 `question_group` / `option_pool` / `layout` 基线 | | 2026-11-10 |
| **v1.6** | **板块级开关落地：`parts_config` 拆成行式明细表**。① 新增 §3.2.11（八小节）：证明"只在 JSON 里加 `enabled` 键"不够——**`parts_config` 元素根本没有 `section`，只有 `sortOrder`**，与 `question.section` 靠数组位置隐式对齐，一旦允许关板块就必须留占位、位置语义即失效；② 新增 **ADR-13**（四方案对比，采纳"拉平成表"）与目标表 `practice_module_part_config`（唯一键 `version+level+section_mapping+section`）；③ **N4/N5/N6 三条缺口由"补 JSON 键"转为"加列"而关闭**，新增 **N6b**（板块级时长/满分/提示语，P1）；④ 新增缺口 **D15**（PROD 21 行中仅 6 行有 `parts_config`，阅读/写作/口语 15 行全 NULL）、缺陷 **B-15**（3.0 `SEC_SPEAK`/`SEC_SPEAKING` 编码分裂）、**B-16**（PROD L2 听力 35≠40）、**B-17**（缺 `section` 键）；⑤ 规则新增 **R13**（板块开关不许删题）/ **R14**（配置缺行不阻塞目录）；⑥ 附录 A **更正 `parts_config` 非空率 100% → TEST 46/49、PROD 6/21**；⑦ 分期新增 **P0-c2**（建表+迁数据+双写）、**P0-c3**（板块开关接口）、**P0-i**（删列收尾），P0-g 加 D15；⑧ 表清单从 5 张变 **6 张** | | 2026-11-10 |

---

## 附录 A：实测数据基线（2026-11-10，只读侦察）

| 项 | TEST | PROD |
|---|---|---|
| `exam_paper`（`exam_type=1`）HSK2.0 | 121 卷（L1–4 各 20、L5 21、L6 20） | **122 卷（L1 21、L2–4 各 20、L5 21、L6 20）** ← 🔧 v1.4 更正：原记「61 卷」实为**上架卷数**，非内容卷数 |
| **`practice_paper_setting` 总行数** | **205** | **116** |
| **`practice_paper_setting` 能 join 到卷** | 136（练习卷 100% 覆盖） | 60（137 张里仅 44%） |
| **`practice_paper_setting` 孤儿行**（`paper_id` 已无对应卷） | **69**（38 活跃 + 31 软删）← 🔴 D12 | **56**（全部活跃）← 🔴 D12 |
| **实际上架卷数**（`enabled=1 AND visible=1 AND deleted=0`） | 136（每级全上架） | **60**：HSK2.0 每级各 10 张、**HSK3.0 全 0** |
| **`practice_paper_setting` 字段取值域** | `enabled` 1×203/0×2；`visible` **全 1**；`deleted` 0×174/1×31 | `enabled` 全 1；`visible` 全 1；`deleted` 全 0 |
| **一张卷覆盖几个模块**（`DISTINCT section_mapping`） | 2 个×43 卷 / 3 个×92 卷 / 5 个×1 卷 | 2 个×44 / 3 个×92 / 5 个×1 ← 卷级状态不可按模块拆 |
| **`level_config` 开但 0 卷在架的组合数** | **11 组** | **5 组** ← 两个开关正交，ADR-12 |
| **`question_group` 去重板块数** vs `question` 推出的板块数 | **592 / 1180（50%）** ← 不能当结构源 | — |
| **`question` 有题但 `question_group` 无行的板块** | **588 个**（集中阅读 / 写作） | — |
| **`question_group` 一板块内的 group 行数** | 1 行×380 / 2 行×102 / 3 行×35 / 4 行×32 / 5 行×43 | — |
| **`practice_question_option_pool`** | 2505 行 / 522 池（每池最多 5 题）/ 306 个 `structure_id` | 1150 行 / 240 池 / 140 个 |
| **共享池覆盖题型** | 6 种全覆盖（`reading_cloze` 600 / `listening_img_match` 575 / `reading_sent_match` 575 / `reading_word_fill` 325 / `reading_img_match` 230 / `reading_sent_fill` 200） | **5 种**：`reading_cloze` **0 条**（90 道题全缺）← 🔴 B-13 |
| **`reading_cloze` 缺池记录的题** | **90 / 690** ← 🔴 B-13 | **90 / 90**（一条都没有） |
| **共享池内各题 `option_content`** | **完全相同**（5 题共用一组 A–F） | 同 |
| **`question.layout` 填充率** | **13524 / 13524（100%）** | **7105 / 13574（52.3%）** ← 🔴 D14 |
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
| **`parts_config` 覆盖率** | **46 / 49 行非空**（3 行为空：`SEC_WRITE` 2.0 L1/L2 + 3.0 L1，均 `enabled=0`）；11 个 `(version, section)` 组合键名一致 | **6 / 21 行非空**（只有 `SEC_LISTEN`）；`SEC_READ`/`SEC_WRITE`/`SEC_SPEAK` 15 行全 NULL ← 🔴 **D15**，v1.6 更正 |
| **`parts_config` 元素总数** | **132**（每行 2~4 个） | **20**（6 行听力） |
| **`parts[].sortOrder` 集合 == `question.section` 集合** | **38 / 46 行**成立；8 行不等（全部 `SEC_SPEAK`，口语题不在 `question`） | 6 / 6 成立（只有听力有 parts） |
| **`total_question_count` == `SUM(parts[].questionCount)`** | **46 / 46 全部相等**（纯派生值） | 5 / 6 相等；**HSK2.0 L2 听力 35 ≠ 40** ← 🔴 **B-16**（15 行无 parts 无法校验） |
| **`parts_config` 是否含 `section` 键** | **均不含**，只有 `sortOrder` ← 🔴 **ADR-13 的根因** | 同 |
| **`parts_config` 是否含 `typeCode` / `answerMode` / `enabled`** | **均不含** ← 🔴 N4 / N5 / N6 | 同 |
| **`SEC_SPEAK` vs `SEC_SPEAKING` 并存** | 3.0 有 `SEC_SPEAK` **5 行**（L3–L7，15 板块）+ `SEC_SPEAKING` **1 行**（L7，3 板块，内容与 L7 的 `SEC_SPEAK` 完全相同）；`question` 里 3.0 的 `SEC_SPEAK` **0 题** ← 🔴 **B-15** | 21 行中无 `SEC_SPEAKING`（3.0 配置 0 行） |
| **`speaking_exam_paper_question` 是否有 `section` 列** | **没有**（只有 `number` / `question_group`）→ 2.0 口语板块**无法从内容推导** | 同 |
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
| **`practice_question_option_pool`** | 2505 行，`structure_id + question_id + pool_code`（详见 §3.2.10③） | — |
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
| **B-11** | `practice_paper_setting` 有孤儿行（`paper_id` 指向已不存在的卷）：TEST 69 行（38 活跃 + 31 软删）、PROD 56 行（全活跃） | 运营表数据 | 现网无感（查询走 `IN candidatePaperIds` 天然过滤）；但任何合并/迁移会把脏行带走，运营后台按卷查会命中空记录 | 🟡 中（P0 收尾清理，见 D12） |
| **B-12** | `practice_paper_setting.visible` 与 `enabled` 语义重复：现网 `visible` **全表为 1**，实际起作用的只有 `enabled` | 运营表数据 | 运营分不清「下架」该改哪个；本次不合并（删列有回归风险），只在 R11 明确二者共同构成"在架" | 🟢 低（P1 评估收敛为单字段） |
| **B-13** | 共享选项池记录缺失：`reading_cloze`（选词填空）TEST **90/690** 无池记录，**PROD 90/90 全无**；且 `pool_code` 内嵌 `structureId`（`SEC_READ_{structureId}_{sha256}`） | `practice_question_option_pool` | 前端拿不到 `optionPoolCode` → 选词填空题退化成"每题 6 个选项重复渲染"，而不是一个共享选项网格；`structureId` 一删，编码规则即失效 | 🟡 中（P2 前置：补 90 条 + 改编码不含 `structureId` + 改快照现算） |
| **B-14** | `question.layout` PROD 缺失 47.7%（6469/13574），TEST 100% 有值 | `question` 数据 | practice-service 4 处依赖它渲染 → PROD 近一半题交互错乱；同时堵死"用 `layout` 推断共享选项池"的替代方案 | 🔴 高（见 D14，P0 前回填） |
| **B-15** | HSK3.0 口语模块编码分裂：`SEC_SPEAK`（5 行配置，L3–L7）与 `SEC_SPEAKING`（1 行配置，L7）并存；`question` 里 3.0 的 `SEC_SPEAK` **0 题**、`SEC_SPEAKING` 3 题；L7 两行配置内容**完全相同** | `practice_module_level_config` | 拆表时会把同一批板块写两遍（6 行，其中 3 行永久孤儿）；接口按 `SEC_SPEAK` 查 3.0 会命中空板块 | 🟡 中（拆表前统一到 `SEC_SPEAKING`，删 L7 的 `SEC_SPEAK` 行） |
| **B-16** | PROD `HSK2.0 L2 SEC_LISTEN` 的 `total_question_count=35`，但 `parts_config` 四个板块 `questionCount` 求和 **40** | 配置数据 | 模块级题量与板块级题量对不上；接口若改用 `SUM` 口径，标准题量会从 35 变 40，影响进度条分母 | 🟢 低（拆表时以 `question` 实际计数为准，手工核对一次） |
| **B-17** | `parts_config` 元素只有 `sortOrder`、**没有 `section`**，与 `question.section` 靠"数组第几个"隐式对齐 | 配置表结构 | 一旦允许"关掉某个板块"且从数组里删元素，后续板块全部错位；无法在数据库层校验对齐 | 🔴 高（ADR-13 拆表并显式存 `section` 解决） |

> B-01 / B-02 / B-03 三条**不需要等本次改造上线就该修**：前两条现网已发生，第三条是 HSK3.0 放开的必炸点。

---

## 附录 C：落地分期

> v1.2 重排：**先改读路径（代码），再补配置（数据）**。因为配置表只有 49 行，改造成本远低于重写派生脚本。

| 期 | 范围 | 前置 | 完成判据 |
|---|---|---|---|
| **P0-a** | 修 B-01 / B-02 / B-03 三条存量缺陷 | 无 | TEST 听力 intro 不 500；PROD 听力列表不混版；HSK7-9 写作可开练习 |
| **P0-b** | `PracticeVersion` / `PracticeLevelCode` / `PracticeModuleCatalog` / **`PracticeTypeRegistry`**（题型字典：`typeCode → answerMode`） | — | 单测覆盖 `HSK7-9`、`'7-9'`、非法版本、5 种 `answerMode` |
| **P0-c** | 16 个目录端点加 `version` | P0-b | HSK2.0 全链路零回归 |
| **P0-c2** | **新建 `practice_module_part_config` + 迁数据**（ADR-13）：① DDL；② 从 `parts_config` 展开（38 行 `section=sortOrder` 直转、8 行口语人工核对）；③ 补 `type_code` / `answer_mode`（原 N4/N5）；④ 先统一 B-15 的 `SEC_SPEAK` → `SEC_SPEAKING`；⑤ **双写过渡**（读旧、两边都写），比对一致后进入 P0-c3 | P0-b 的字典定稿 | 132 行入库；`SELECT COUNT(*)` 与 `SUM(JSON_LENGTH(parts_config))` 相等；旧读路径响应**零变化** |
| **P0-c3** | **板块开关接口**：`PATCH /hsk/module-config/parts/{id}`（改 `enabled` / 名称 / 顺序） | P0-c2 | 关掉某板块后，目录不再出现该板块，新练习不下发其题目；历史记录不受影响（R13） |
| **P0-d** | 聚合接口 `GET /hsk/modules` | P0-c | 2.0 四卡 / 3.0 五卡，布局与角标正确 |
| **P0-e** | **重写 `PracticeCatalogBatchLoader`**：从「查 structure + part_setting」改为「读 `practice_module_part_config` + `question` 算题量」（配置缺行按 R14 兜底，不阻塞） | P0-c2 | 2.0 四个模块目录与现网**逐字段一致**；结构表停写 |
| **P0-f** | 翻译目录 4 + 写链路 6 + `validatePart` 放宽 | P0-e（目录装配已换源） | 翻译笔译/口译都可练到交卷；写作 `structureId` 打翻译 → 400 |
| **P0-g** | **数据补全：PROD 补 28 行模块配置（D4）+ 15 行板块配置（D15）+ level 收敛（D3）+ `deleted_prac` DDL（D11）+ 3.0 卷上架（15 行 `practice_paper_setting`）+ 孤儿行清理（D12）+ `question.layout` 回填（D14）** | **D11 的 DDL 最先**；五闸门 + DRY-RUN + 备份 | PROD 切 3.0 五卡有数据；`practice_paper_setting` 孤儿行 = 0；3.0 卷在目录可见；PROD `layout` 非空率 = 100%；PROD 板块配置非空 = 21/21 |
| **P0-h** | **`practice_record` 瘦身**：删 `structure_id` + `practice_name`；重建 `idx_record_active` 为 `(user_id, paper_id, section_mapping, section, status)`；7 处 Mapper 改三元组（`selectByStructure` → 已存在的 `selectByPart`）；`question_ids` 全模块启用；接口 `structureId` → `(paperId, section)` | P0-e（目录已换源，前端已能拿 `partCode`） | ① 抽 100 条历史记录，新旧路径取题 **ID 列表完全一致**（PROD 已实测 1343/1343）；② `EXPLAIN` 走新索引；③ HSK 新记录 `question_ids` 非空且 `JSON_LENGTH = total_questions` |
| **P0-i** | **删列收尾**：`ALTER TABLE practice_module_level_config DROP COLUMN parts_config`；`total_question_count` 降级评估（D15 补齐且 `SUM` 校验一致后） | P0-e / P0-g 均稳定运行 ≥ 1 个版本；双写比对连续一致 | `parts_config` 列不存在；无任何代码/脚本读取它；`total_question_count` 与 `SUM(part.standard_question_count)` 差异为 0 |
| P1 | 偏好表加 `version`；ID 改 String；`dataVersion` ETag；角标后台可配；补 `TRANSLATION_WRITTEN` 策略；**D10 collation 对齐**；B-09 修正；**N6b 板块级时长/满分/提示语加列** | P0 上线观察 | — |
| P2 | **彻底删 `practice_paper_structure`**：先给 `writing_attempt`(217) / `speaking_attempt`(283) / `option_pool`(2505) 加 `section_mapping + section` 并回填，再 drop；**`option_pool` 退场前置 3 步**（§3.2.10③）：① 补 `reading_cloze` 缺失记录（TEST 90 / PROD 90）② `pool_code` 改为 `{section_mapping}_{paperId}_{section}_{sha256(option_content)}` 不含 `structureId` ③ 答题快照 `optionPoolCode` 改现算；口译 ASR + 自动评分 | P0-h 稳定运行 + 回填核对完 479 条雪花 ID | — |

> 🔴 **最大的风险点是 P0-e**：它是唯一会改变 2.0 现网行为的改造（目录数据源换源）。
> 验收方法：同一批 16 个请求（4 模块 × versions × levels），新旧接口响应 **JSON 逐字段 diff 必须为空**。建议先把旧实现的结果快照存盘再对比。
>
> ✅ **P0-g 已经从"跑派生脚本写 1201 行"降为"补 28 行模块配置 + 15 行板块配置"**——这是删掉两张表带来的直接收益。
> 顺序：**P0-a → P0-b → P0-c2（建表迁数据双写）→ P0-c → P0-c3（板块开关接口）→ P0-e（换源，重点回归）→ P0-f（翻译）→ P0-g（PROD 补数据）→ P0-h → P0-i（删列）**。
> 🔴 **v1.6 提醒**：P0-c2 的"双写"是关键安全阀。`parts_config` 列在 P0-i 之前一直保留，任何一侧出错都能立刻切回旧读路径，不需要恢复备份。
