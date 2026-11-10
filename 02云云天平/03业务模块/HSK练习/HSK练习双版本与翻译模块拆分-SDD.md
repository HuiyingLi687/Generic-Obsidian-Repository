# HSK 练习双版本（2\.0 / 3\.0）与翻译模块拆分 · 软件设计文档

> 定位：本文档回答【怎么做】——HSK 练习如何同时支撑 2.0 / 3.0 两套大纲，以及「翻译」如何从写作模块里拆成独立入口。
> 服务：`practice-service`（网关前缀 `/api/practice`）
> 依据：2026-11-10 双版本首页 UI 截图（2.0 四宫格 / 3.0 五行列表）+ 代码基线 + TEST / PROD 实测
> 文档版本：v1.0｜更新日期：2026-11-10｜状态：**待评审**
> 前置：[HSK练习模块首页-设计方案](HSK练习模块首页-设计方案.md)、[HSK翻译练习-独立模块接口方案](HSK翻译练习-独立模块接口方案.md)、[HSK练习-共用题库方案](HSK练习-共用题库方案.md)
> 🔴 **本文纠正前置文档的三处过时结论**，见 §9 ADR-06

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
| 6 | HSK3.0 目录配置的数据补全口径（PROD 当前为 0 行） |

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
| 板块 | part | 一张卷里的一段（如「听力第 2 部分」），落 `practice_paper_structure` + `practice_part_setting` |

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
        │     ├─ 练习目录配置：practice_paper_structure / practice_part_setting /
        │     │                 practice_module_level_config / practice_paper_setting / hsk_level_config
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

1. **版本上下文只作用在目录层。** 作答链路拿的是 `paperId` / `structureId`，版本已被这两者唯一确定，因此 `attempt/answer/submit/report` **一律不加 `version` 参数**。改动面从 40+ 端点收敛到 16 个目录端点。
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
| 7 | 口语目录 | 等级→卷→板块（`SEC_SPEAK` / `SEC_SPEAKING` 双映射收口） | `speaking/**` |
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
| `SPEAKING` | `SEC_SPEAK` | 口语 | Speaking | mic | `#FF4D8D` | NEW | — | 4 | 5 | 2.0 / 3.0 |

`layout`：`HSK2.0 → GRID_2`（2 列网格）、`HSK3.0 → LIST`（1 列 5 行）。由聚合接口下发，前端不写死。

#### 3\.1\.2 领域实体与关系

```
exam_paper (1) ────< practice_paper_structure (1) ──── (1) practice_part_setting
   │  version/level              │ version/content_type            │ section_mapping/section_code/answer_mode
   │                             │                                  │
   │                             └──────< writing_attempt (翻译/写作共用)
   │
   └──────< question  (section_mapping + section 决定归属板块)

practice_module_level_config   ← 版本 × 等级 × 模块 的开关与题量口径
practice_paper_setting         ← 卷级上下架
hsk_level_config               ← 版本 × 等级 的多语言名称
practice_user_preference       ← 用户维度「上次练到哪」，唯一键 (user_id, section_mapping)，**无 version**
```

#### 3\.1\.3 业务规则（必须落进代码的 6 条）

| # | 规则 | 落点 |
|---|---|---|
| R1 | `version` 只有 `HSK2.0` / `HSK3.0` 两个合法值，缺省 `HSK2.0`，非法 → 400 | `PracticeVersion.of` |
| R2 | `HSK7-9` 是**一个**等级，数值 `7`；禁止对 levelCode 做 `parseInt` 裸解析 | `PracticeLevelCode` |
| R3 | `exam_paper.level` 在两库取值不一致（TEST `"7"` / PROD `"7-9"`），查询必须用 `IN (候选集)` | `PracticeLevelCode.dbLevels` |
| R4 | 翻译仅 `HSK3.0`；`version=HSK2.0` 调 `/translation/**` → 返回空数组 / 空对象，**不报 404**（前端据此置灰） | `TranslationCatalogServiceImpl` |
| R5 | 口语在 HSK3.0 有**两个** sectionMapping（`SEC_SPEAK` 3–7 级、`SEC_SPEAKING` 7 级），目录必须合并去重后按等级下发，不能各自出一张卡 | `SpeakingCatalogServiceImpl` |
| R6 | 目录只下发题数 > 0 的等级 / 卷 / 板块 | 各 Catalog Service |

### 3\.2 数据库设计

#### 3\.2\.1 表清单与版本隔离键

| 表 | 角色 | 版本列 | 等级列 | 本次是否改结构 |
|---|---|---|---|---|
| `exam_paper` | 题库卷（考试/练习共用，`exam_type=1`） | `version` | `level`（varchar） | ❌ |
| `question` | 题库题 | 无（经 `paper_id` 继承） | 无 | ❌ |
| `practice_paper_structure` | 卷 → 板块 | `version` | `hsk_level`（int） | ❌ |
| `practice_part_setting` | 板块 → 题型/作答模式 | 无（经 `structure_id` 继承） | 无 | ❌ |
| `practice_module_level_config` | 版本 × 等级 × 模块开关 | `version` | `level`（int） | ❌ |
| `practice_paper_setting` | 卷上下架 | 无 | 无 | ❌ |
| `hsk_level_config` | 等级名称（三语） | `version` | `level`（int） | ❌ |
| `practice_user_preference` | 用户「上次练到哪」 | **无** | `last_level`（int） | ⭕ P1 加列，见 ADR-03 |
| `writing_attempt` / `writing_answer` / `writing_report` | 写作 + 翻译作答 | 无 | — | ❌ 复用 |

**结论：本次零 DDL（P0）。** 版本隔离完全靠既有 `version` 列 + 查询条件实现。唯一例外是 `practice_user_preference`，P0 用「HSK3.0 不写偏好」规避。

#### 3\.2\.2 唯一键带来的约束

| 唯一键 | 影响 |
|---|---|
| `practice_module_level_config :: uk_module_level (version, level, section_mapping)` | 已含 `version`，**两类版本天然共存**，无需改键 |
| `practice_part_setting :: uk_part_code (paper_id, section_mapping, section_code)` | 翻译的 `section_code=1`（笔译）与 `2`（口译）可共存，但**目前只建了 1 行**，见 D2 |
| `practice_user_preference :: uk_preference_user_module (user_id, section_mapping)` | **不含 version** → 2.0 与 3.0 写同一行会互相覆盖，P0 靠「3.0 不写」规避 |

#### 3\.2\.3 数据缺口（**这是本次真正的阻塞点，接口不是**）

实测 TEST（`8.138.185.11`）/ PROD（`43.99.57.11`），2026-11-10：

| # | 缺口 | TEST | PROD | 影响 | 处置 | 级别 |
|---|---|---|---|---|---|---|
| **D1** | HSK3.0 的 `practice_paper_structure` + `practice_part_setting` | 135 / — 行，完整 | **0 行** | PROD 的 HSK3.0 **完全无目录**，切到 3.0 五张卡全空 | 按「题库推导口径」批量生成，见 §3.2.4 | **P0 阻塞** |
| **D2** | 翻译口译板块（`section=2`）缺 structure + part_setting | 缺 | 缺 | 口译板块不出现，`/translation/papers/{id}/parts` 只回 1 个板块 | 补 1 行 structure（`sort_order=2`）+ 1 行 part_setting（`answer_mode=RECORD`） | **P0 阻塞** |
| **D3** | `exam_paper.level` 7-9 级取值不一致 | `"7"` | `"7-9"` | 任何 `String.valueOf(7)` 精确匹配在 PROD 命中 0 卷（且 `Integer.parseInt("7-9")` 直接 500） | 代码用 `IN ('7','7-9')` 容错（R3）；数据侧统一为 `"7-9"` 作为 P1 收敛 | **P0 阻塞** |
| **D4** | `practice_module_level_config` 的 HSK3.0 行 | 28 行 | **0 行** | 同上，等级列表为空 | 与 D1 同批生成 | **P0 阻塞** |
| D5 | `writing_evaluation_policy` 无 `TRANSLATION_WRITTEN` | 缺 | 缺 | 笔译交卷后评分任务查不到策略 → 报告卡在「生成中/失败」 | P0：**不入队**，报告直接 `feedbackStatus=UNAVAILABLE`；P1 补 1 行策略 | P0 规避 |
| D6 | 翻译 4 题的 `answer` 全为 `(略)`、`analysis` 为空 | 4/4 | 4/4 | AI 评分无参照物（主观题本就无对错） | 题库补参考译文 | P1 |
| D7 | 口语 `SEC_SPEAKING`（HSK7-9）无 structure / part_setting | 缺 | 缺 | 7-9 级口语题（5 题）任何入口都看不到 | P0 置灰；P1 补配置 | P1 |
| D8 | HSK3.0 卷数量偏少 | 15 卷（1–4 级各 3、5/6/7 各 1） | 同 | 3.0 列表只有 1–3 张卡 | 题库导入 | 已知 |

> 🔴 **D1 / D3 / D4 是上线阻塞项**：接口写完了，PROD 切到 HSK3.0 依然是五张空卡。

#### 3\.2\.4 目录配置生成口径（替代逐卷手抄）

不要把 `exam_paper_structure` 的模板再抄一遍。**按题库分组直接生成**，与 [共用题库方案 §2.1③](HSK练习-共用题库方案.md) 同一口径：

```sql
-- ① 板块（practice_paper_structure）
SELECT p.id            AS paper_id,
       p.version,  CAST(REPLACE(p.level,'-9','') AS UNSIGNED) AS hsk_level,
       q.section_mapping AS content_type,
       CONCAT('第', q.section, '部分') AS section_name,
       COUNT(*)        AS question_count,
       q.section       AS sort_order
FROM exam_paper p
JOIN question q ON q.paper_id = p.id AND q.deleted = 0
WHERE p.deleted = 0 AND p.exam_type = 1
  AND p.version = 'HSK3.0'
  AND (q.type_id_mapping IS NULL OR q.type_id_mapping <> 'example_question')
GROUP BY p.id, p.version, p.level, q.section_mapping, q.section;

-- ② 题型/作答模式（practice_part_setting）—— answer_mode 由 type_id_mapping 查题型字典，严格 1:1
-- ③ 等级开关（practice_module_level_config）—— 由 ① 的 (version, hsk_level, content_type) 去重
```

约束：
1. 生成脚本必须**幂等**（`INSERT ... ON DUPLICATE KEY UPDATE`），并区分 `content_type` 与 `section_mapping` 一致；
2. `practice_paper_setting` 需为每张新卷补 1 行（`enabled=1, visible=1`），否则 `PracticeCatalogBatchLoader` 会整卷丢弃；
3. `answer_mode` 取值域需扩展：现有 `SINGLE/MATCH/ORDER/RECORD`，翻译笔译为 `TEXT`（TEST 已有该值，PROD 无）；
4. 脚本走五闸门 + DRY-RUN，见 [02改库红线与五闸门](../../02软件架构/02数据库/02改库红线与五闸门.md)。

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
| 3 | GET | `/listening/papers/{paperId}/parts` | 同上（`parts_config` 查询无 version） | 同上；`parts_config` 与 structure 的「按序号对齐」保留现状 |
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
| 14 | GET | `/speaking/levels` | `VERSION = "HSK2.0"` 常量；`SEC_SPEAK` 单映射 | 常量改参数；合并 `SEC_SPEAK` + `SEC_SPEAKING` 后按等级去重 |
| 15 | GET | `/speaking/papers` | 常量 | 常量改参数 |
| 16 | GET | `/speaking/papers/{paperId}/parts` | 常量校验（`VERSION.equals(paper.getVersion())`） | 改为「与入参 version 一致」 |

> 统一约定：`version` 最终作为 `practice_paper_structure.version` / `practice_module_level_config.version` / `exam_paper.version` 的查询条件，**三处必须同时带上**，漏一处就会出现「等级列表是 2.0、卷列表是 3.0」的错配。

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

T4 关键：`answerMode` 取 `practice_part_setting.answer_mode`，前端据 `TEXT` / `RECORD` 决定渲染输入框还是录音按钮——这正是笔译/口译两张卡长得不一样的根因。

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
partSetting(structureId).section_mapping == "SEC_TRANSLATION"  否则 400 SECTION_MAPPING_MISMATCH
```

> 这条校验是防串号的唯一屏障：不加就能拿写作的 `structureId` 打翻译接口，产生两份进度。

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
| 题库版本号 `dataVersion` | P1 引入：`MAX(updated_time)` over `exam_paper` / `question` / `practice_paper_structure`，作为 `ETag` 下发，前端缓存失效用 |
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

---

## 10\. 修订记录

| 版本 | 修改内容 | 修改人 | 日期 |
|---|---|---|---|
| v1.0 | 初稿：双版本目录改造、翻译独立模块、聚合接口、数据缺口与 ADR | | 2026-11-10 |

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

> B-01 / B-02 / B-03 三条**不需要等本次改造上线就该修**：前两条现网已发生，第三条是 HSK3.0 放开的必炸点。

---

## 附录 C：落地分期

| 期 | 范围 | 前置 | 完成判据 |
|---|---|---|---|
| **P0-a** | 修 B-01 / B-02 / B-03 三条存量缺陷 | 无 | TEST 听力 intro 不 500；PROD 听力列表不混版；HSK7-9 写作可开练习 |
| **P0-b** | `PracticeVersion` / `PracticeLevelCode` / `PracticeModuleCatalog` 三个支撑类 | — | 单测覆盖 `HSK7-9`、`'7-9'`、非法版本 |
| **P0-c** | 16 个目录端点加 `version` | P0-b | HSK2.0 全链路零回归 |
| **P0-d** | 聚合接口 `GET /hsk/modules` | P0-c | 2.0 四卡 / 3.0 五卡，布局与角标正确 |
| **P0-e** | 翻译目录 4 + 写链路 6 + `validatePart` 放宽 | **D2 补口译配置** | 翻译笔译可练到交卷；写作 `structureId` 打翻译 → 400 |
| **P0-f** | **数据补全 D1 / D3 / D4**（HSK3.0 目录 + level 取值收敛） | 五闸门 + DRY-RUN + 备份 | PROD 切 3.0 五卡有数据 |
| P1 | 偏好表加 `version`；ID 改 String；`dataVersion` ETag；角标后台可配；补 `TRANSLATION_WRITTEN` 策略 | P0 上线观察 | — |
| P2 | 口译 ASR + 自动评分；`SEC_SPEAKING` 配置补齐 | `ai-service` 接入 | — |

> 🔴 **P0-f 是唯一不可代码化的关键路径**：D1/D4 在 PROD 是 0 行，接口写得多好，切到 3.0 都是空卡。建议 P0-c 与 P0-f 并行推进，P0-d/P0-e 的联调在 TEST 先行（TEST 已有 HSK3.0 目录）。
