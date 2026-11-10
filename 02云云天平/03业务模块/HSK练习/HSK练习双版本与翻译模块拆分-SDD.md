# HSK 练习双版本（2\.0 / 3\.0）与翻译模块拆分 · 软件设计文档

> 定位：本文档回答【怎么做】——HSK 练习如何同时支撑 2.0 / 3.0 两套大纲，以及「翻译」如何从写作模块里拆成独立入口。
> 服务：`practice-service`（网关前缀 `/api/practice`）
> 依据：2026-11-10 双版本首页 UI 截图（2.0 四宫格 / 3.0 五行列表）+ 代码基线 + TEST / PROD 实测
> 文档版本：v1.1｜更新日期：2026-11-10｜状态：**待评审**
> 前置：[HSK练习模块首页-设计方案](HSK练习模块首页-设计方案.md)、[HSK翻译练习-独立模块接口方案](HSK翻译练习-独立模块接口方案.md)、[HSK练习-共用题库方案](HSK练习-共用题库方案.md)
> 🔴 **本文纠正前置文档的三处过时结论**，见 §9 ADR-06
> 🔴 **v1.1 口径**：本次**不新建任何内容表**，全部改造落在既有 5 张题库表（`exam_paper` / `question` / `question_group` / `speaking_exam_paper` / `speaking_exam_paper_question`）上，**零 DDL**。翻译的 4 道题、口语 3.0 的 5 道题已在 `question` 里，只是 `section_mapping` 归错了模块；练习侧的 `practice_paper_structure` 是**投影不是真相源**，可由题库派生。三处必须先定的语义冲突见 §3.2.2。

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
| 7 | HSK3.0 编排层配置（`practice_paper_structure` / `practice_module_level_config`）由题库**派生生成**的口径（PROD 当前为 0 行） |

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

#### 3\.1\.2 三层数据模型（内容层 / 编排层 / 作答层）

**题库里已经有 5 张表承载了全部考试内容，本次不再新建任何内容表**，只在既有列上收口语义。判断一个字段该放哪层，只问一句：*删掉练习侧配置，这个信息还在不在？* 在 → 内容层；不在 → 编排层。

| 层       | 表                                                                              | 承载什么                                                                        | 是否真相源                       |
| ------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------- | --------------------------- |
| **内容层** | `exam_paper` / `question` / `question_group`                                   | 版本、等级、模块归属（`section_mapping`）、题型（`type_id_mapping`）、部分号（`section`）、音频、题干、答案 | ✅ **唯一真相源**                 |
| （口语分支）  | `speaking_exam_paper` / `speaking_exam_paper_question`                         | HSK**2.0** 口语卷与题（`level` 用 `Beginner/Intermediate/Advanced` 三档）             | ✅ 2.0 口语唯一真相源               |
| **编排层** | `practice_paper_structure` / `practice_part_setting`                           | 三语名称、时长、满分、作答提示语、作答交互模式（`answer_mode`）、部分顺序                                 | ⚠️ **投影**，可由内容层派生，**不是真相源** |
|         | `practice_module_level_config` / `practice_paper_setting` / `hsk_level_config` | 模块开关、卷上下架、等级名称                                                              | ⚠️ 投影 + 少量运营开关              |
| **作答层** | `practice_record` / `writing_attempt` / `speaking_attempt`                     | 练习记录                                                                        | 只引用上层 ID，不反推                |

```
┌─────────────────── 内容层（真相源，本次零 DDL）───────────────────┐
│  exam_paper  version / level / exam_type / deleted_prac           │
│      │                                                            │
│      ├────< question       section_mapping / section /            │
│      │        │            type_id_mapping / layout / group_id    │
│      │        └── group_id ──> question_group  (大题包，翻译 2 组) │
│      │                                                            │
│      └────< (口语分支) speaking_exam_paper ──< _question          │
│                            仅 HSK2.0 使用                         │
└────────────────────────────┬──────────────────────────────────────┘
                             │ 派生（§3.2.4，可校验、可重跑）
┌────────────────────────────▼──────────────────────────────────────┐
│  编排层（投影）：practice_paper_structure → practice_part_setting  │
│                  practice_module_level_config / practice_paper_setting │
└────────────────────────────┬──────────────────────────────────────┘
                             │ 引用 paperId / structureId
┌────────────────────────────▼──────────────────────────────────────┐
│  作答层：writing_attempt（写作+翻译共用） / speaking_attempt /      │
│          practice_record                                          │
└───────────────────────────────────────────────────────────────────┘

practice_user_preference ← 用户「上次练到哪」，唯一键 (user_id, section_mapping)，**无 version**（ADR-03）
```

> 🔴 **一句话记住**：`exam_paper.version` 是版本开关的唯一依据，`question.section_mapping` 是模块归属的唯一依据。翻译不需要新表，它已经有 4 道题躺在 `question` 里；口语 3.0 也不需要新表，它已经有 5 道题躺在 `question` 里。

#### 3\.1\.3 业务规则（必须落进代码的 8 条）

| # | 规则 | 落点 |
|---|---|---|
| R1 | `version` 只有 `HSK2.0` / `HSK3.0` 两个合法值，缺省 `HSK2.0`，非法 → 400 | `PracticeVersion.of` |
| R2 | `HSK7-9` 是**一个**等级，数值 `7`；禁止对 levelCode 做 `parseInt` 裸解析 | `PracticeLevelCode` |
| R3 | `exam_paper.level` 在两库取值不一致（TEST `"7"` / PROD `"7-9"`），查询必须用 `IN (候选集)` | `PracticeLevelCode.dbLevels` |
| R4 | 翻译仅 `HSK3.0`；`version=HSK2.0` 调 `/translation/**` → 返回空数组 / 空对象，**不报 404**（前端据此置灰） | `TranslationCatalogServiceImpl` |
| R5 | 口语按版本**分流读源**：2.0 → `speaking_exam_paper`（`SEC_SPEAK`），3.0 → `exam_paper` + `question.SEC_SPEAKING`；**不合并、不去重**（详见 §3.2.2 冲突 1） | `SpeakingCatalogServiceImpl` |
| R6 | 目录只下发题数 > 0 的等级 / 卷 / 板块 | 各 Catalog Service |
| R7 | **内容层是唯一真相源**：凡能从 `exam_paper`/`question` 算出的字段（板块、部分号、题量、题型），不得只存在于编排层；编排层随时可重建 | 派生脚本 + Code Review 卡点 |
| R8 | `practice_paper_structure` 与题库做 JOIN 时，`version`/`content_type` 必须显式 `CONVERT ... COLLATE utf8mb4_0900_ai_ci`，否则 `ERROR 1267` | Mapper |

### 3\.2 数据库设计

#### 3\.2\.1 五张内容表的改造判定（本次要动的只有语义，不是结构）

| 表 | 关键列（现状即可用） | 改结构 | 本次改造动作 |
|---|---|---|---|
| `exam_paper` | `version` varchar(30)、`level` varchar(40)、`exam_type` tinyint、`deleted_prac` | ❌ | ① `version` 作**版本隔离唯一键**（值域收口到 `HSK2.0`/`HSK3.0`，靠代码枚举校验，不加 CHECK 约束，避免卡住导入）② `level='7-9'` 走候选集（D3）③ `deleted_prac=1` = 练习侧下架（考试侧不受影响） |
| `question` | `section_mapping`、`section`、`type_id_mapping`、`group_id`、`layout`、`audio_url`、`score`、`deleted_prac` | ❌ | ① `section_mapping` **决定模块归属**：`SEC_LISTEN/SEC_READ/SEC_WRITE/SEC_TRANSLATION/SEC_SPEAKING` ② `section` 是**模块内**部分号 1–4 ③ `type_id_mapping='example_question'` 是例题，**统计题量必须排除** ④ `layout` 只读，**禁止新增取值**（4 处代码依赖） |
| `question_group` | `section_mapping`、`start/end_number`、`group_title`、`passage`、`deleted_prac` | ❌ | 翻译已有 2 组（笔译 / 口译，`section` 分别 1 / 2），**无需新建翻译组表** |
| `speaking_exam_paper` | `version`、`level`（2.0 用 `Beginner/Intermediate/Advanced`）、`total_time`、`deleted_prac` | ❌ | **仅 2.0 使用**；TEST 里那 5 张 HSK3.0 卷冻结为只读历史数据（见 §3.2.2 冲突 1） |
| `speaking_exam_paper_question` | `question_type_mapping`、`practice_audio_url`、`mock_audio_url`、`reference_answer`、`deleted_prac` | ❌ | 同上；2.0 口语的题型字典以本表 `question_type_mapping` 为准 |

**练习侧「能不能练」现在有两个开关，别搞混**：

| 开关 | 位置 | 语义 | 谁维护 |
|---|---|---|---|
| `deleted_prac` | **5 张题库表各自一列**（2026-11-10 新增） | 这题/这卷**内容本身**不适合练习（如纯考试听力设备测试题） | 题库管理侧 |
| `practice_paper_setting.enabled/visible` | 编排层 | **运营临时**上下架，内容没变 | 运营后台 |

两者是 **AND** 关系：任一侧关掉都不出现在目录。目录查询必须同时带 `deleted_prac=0` 与 `practice_paper_setting.enabled=1`。

> 🔴 **D11：`deleted_prac` 列 PROD 还没有（见 §3.2.3）**。TEST 已加、代码已接，但 PROD 未执行 DDL。**派生脚本与目录 SQL 里带 `deleted_prac=0` 在 PROD 会直接 `Unknown column`**，必须先 DDL 再上线。

**结论：本次零 DDL。** 双版本、翻译独立、口语 3.0 三件事全部落在既有列上；唯一前置 DDL 是 PROD 补 `deleted_prac`（D11，已在 TEST 验证过），以及 P1 建议的 collation 对齐（§3.2.5）。

**为什么不新建表**：翻译 4 道题、口语 3.0 的 5 道题都已存在于 `question`，只是被 `section_mapping` 归到了非写作板块；新建 `translation_*` 等于把同一份题干复制两遍，评分、报告、统计全要重造（ADR-02 方案 C 的代价）。

#### 3\.2\.2 三处语义冲突与裁定（不定这三条，代码一定写歪）

**冲突 1：HSK3.0 口语有两套数据，必须指定唯一读源**

实测（2026-11-10）：

| 读源 | TEST | PROD |
|---|---|---|
| `exam_paper` + `question`（`section_mapping='SEC_SPEAKING'`） | 1 卷 5 题（卷 `2104188199979532289`，number 87–91，带 `audio_url`） | **1 卷 5 题（同）** |
| `speaking_exam_paper` + `_question`（`version='HSK3.0'`） | 5 卷（3/4/5/6/7-9 级各 1） | **0 卷** ← 🔴 |

两边 `number` 87–91 完全一致，`source` 与 `exam_paper` 一一对应（`HSK3_1`/`HSK4_1`/`HSK5_1`/`HSK6_1`/`HSK7-9_1`）——**这是同源双录，不是两份内容**。

| 方案 | 评价 |
|---|---|
| **A. 3.0 只认 `exam_paper` + `question.SEC_SPEAKING`（采纳）** | PROD 只有这条有数据，切 3.0 立刻可用；`speaking_exam_paper` 退回「2.0 专用」 |
| B. 3.0 只认 `speaking_exam_paper` | PROD 是 0 卷，必须先补 5 卷 + 78 题（TEST 现有量，含引导语/大纲等辅助条）录入，纯阻塞 |
| C. 两套都读、按 source 去重合并 | 去重键靠 `source` 字符串，改一个字就重复出卡；且两套 `level` 写法不同（`7` vs `7-9`） |

裁定 A。`SpeakingCatalogServiceImpl` 按版本分流：`HSK2.0 → speaking_exam_paper`、`HSK3.0 → exam_paper(+question)`，两条路共用同一个 DTO，前端无感。
**TEST 那 5 张 HSK3.0 口语卷**不删、不写，标记为历史数据（P2 若改用 B 方案再启用）。

**冲突 2：部分号有两套口径，差一个固定基址**

| | `question.section` | `practice_paper_structure.sort_order` |
|---|---|---|
| 含义 | **模块内**部分号 | **全局**部分号（跨模块累加） |
| 阅读第 1 部分 | `1` | `5` |
| 写作第 1 部分 | `1` | `21` |

实测基址（全量比对 1087 行结构表，不含口语分支的 114 行）：

| 模块 | 基址 | sort_order 范围 | 与题库聚合一致率 |
|---|---|---|---|
| `SEC_LISTEN` | 0 | 1–4 | **446 / 446 精确**（两版本均 100%） |
| `SEC_READ` | 4 | 5–8 | 314 / 474 |
| `SEC_WRITE` | 20 | 21–22 | **166 / 166 精确** |
| `SEC_TRANSLATION` | 22 | 23–24 | 1 / 1（仅笔译） |
| `SEC_SPEAK` | — | 1–3 | 独立空间，`paper_id` 指向 `speaking_exam_paper`（114/114），与题库不对齐 |

阅读 160 行对不上的**不是映射错**：结构表对部分卷拆得比题库细（结构表 4 个部分，题库 `section` 只有 3 个值），例如卷 `2095422163625046017` 结构表有 `sort_order=4`（第 0 部分）与 `qc=20`（第 6 部分），题库实际是 1/2/3 各 10 题。

裁定：
- 听力 / 写作 / 翻译 → **允许由内容层派生**结构行（100% 可验证）
- 阅读 → **以结构表人工编排为准**，派生结果只作新卷初稿
- 基址落 `PracticeSectionCode.base(module)` 常量，禁止再散落 `5`/`21` 这种魔数

**冲突 3：作答模式两套枚举，`layout` 推不出 `answer_mode`**

| `type_id_mapping` | `question.layout` | `part_setting.answer_mode` | 判定 |
|---|---|---|---|
| `translation_written` | `input` | **`TEXT`** | 正确 |
| `writing_short_essay` | `input` | **`SINGLE`** | 🔴 应为 `TEXT`，存量错配（B-09） |
| `reading_sent_match` | `choice` | `MATCH` | 正确 |
| `reading_cloze` | `choiceGrid` | `SINGLE` | 正确 |
| `listening_img_match` | `choiceGrid` | `MATCH` | 正确 |

同样是 `input`，翻译是 `TEXT`、作文是 `SINGLE`；同样是 `choiceGrid`，图片匹配是 `MATCH`、完形是 `SINGLE`。**`layout` 是渲染布局，`answer_mode` 是作答交互，两者多对多。**

裁定：`answer_mode` 必须按 `type_code` 查字典（`PracticeTypeRegistry`），**禁止从 `layout` 推导**。写作的 `SINGLE` 存量错配登记 B-09，P1 只对新写条目用 `TEXT`，不改 2.0 现网行为。

#### 3\.2\.3 数据缺口（改成「可派生的缺口」后，阻塞性质变了）

实测 TEST（`8.138.185.11`）/ PROD（`43.99.57.11`），2026-11-10：

| # | 缺口 | TEST | PROD | 影响 | 处置 | 级别 |
|---|---|---|---|---|---|---|
| **D1** | HSK3.0 的 `practice_paper_structure` + `practice_part_setting` | 135 行，完整 | **0 行** | PROD 的 HSK3.0 **完全无目录**，切到 3.0 五张卡全空 | **由 §3.2.4 脚本从内容层派生**（听力/写作 100% 可校验，阅读取结构表人工编排） | **P0 执行项**（已可代码化，非手工阻塞） |
| **D2** | 翻译口译板块（`section=2`）缺 structure + part_setting | 缺 | 缺 | 口译板块不出现，`/translation/papers/{id}/parts` 只回 1 个板块 | 补 1 行 structure（`sort_order=24`，基址 22+2）+ 1 行 part_setting；题库侧 `question.section=2` 的 2 题已存在 | **P0 阻塞** |
| **D3** | `exam_paper.level` 7-9 级取值不一致 | `"7"` | `"7-9"` | 任何 `String.valueOf(7)` 精确匹配在 PROD 命中 0 卷（且 `Integer.parseInt("7-9")` 直接 500） | 代码用 `IN ('7','7-9')` 容错（R3）；数据侧统一为 `"7-9"` 作为 P1 收敛 | **P0 阻塞** |
| **D4** | `practice_module_level_config` 的 HSK3.0 行 | 28 行 | **0 行** | 同上，等级列表为空 | 与 D1 同批派生（`(version, hsk_level, section_mapping)` 去重即可） | **P0 执行项** |
| D5 | `writing_evaluation_policy` 无 `TRANSLATION_WRITTEN` | 缺 | 缺 | 笔译交卷后评分任务查不到策略 → 报告卡在「生成中/失败」 | P0：**不入队**，报告直接 `feedbackStatus=UNAVAILABLE`；P1 补 1 行策略 | P0 规避 |
| D6 | 翻译 4 题的 `answer` 全为 `(略)`、`analysis` 为空 | 4/4 | 4/4 | AI 评分无参照物（主观题本就无对错） | 题库补参考译文 | P1 |
| D7 | 口语 3.0 的 `SEC_SPEAKING` 无 structure / part_setting | 缺 | 缺 | 7-9 级口语题（5 题）任何入口都看不到 | 按冲突 1 裁定走 `exam_paper`，同样由脚本派生 | **P0 执行项** |
| D8 | HSK3.0 卷数量偏少 | 15 卷（1–4 级各 3、5/6/7 各 1） | 同 | 3.0 列表只有 1–3 张卡 | 题库导入 | 已知 |
| **D9** | 阅读部分号口径不一致 | 160 / 474 行结构表与 `question.section` 对不上（2.0 与 3.0 都有） | 同 | 派生阅读目录会与现网人工编排不一致 | **以结构表为准**，派生结果只作新卷初稿（§3.2.2 冲突 2） | 已知，不阻塞 |
| **D10** | `practice_paper_structure.version` collation 与全表不一致 | `utf8mb4_unicode_ci` vs `utf8mb4_0900_ai_ci` | 同 | 任何跨表 `version` JOIN 直接 `ERROR 1267` | P0 代码侧 `CONVERT`；P1 一次对齐（§3.2.5） | **P0 阻塞**（踩到就 500） |
| **D11** | `deleted_prac` 列 PROD 不存在 | 5 张表均已加列 | **5 张表全缺** | 目录/派生 SQL 带 `deleted_prac=0` → `Unknown column`，接口直接 500 | 上线前先执行 DDL（TEST 已有同构语句可复用）；DDL 前 PROD 侧 SQL 需临时去掉该条件 | **P0 阻塞**（DDL 前置） |

> 🔴 **真正的阻塞只剩三条：D2（口译缺 1 行）、D3（level 取值）、D10（collation）**，都是小改动。
> D1 / D4 / D7 从「手工补 135 行配置」降级为「跑一遍幂等脚本」——因为内容层（`exam_paper` + `question`）在 PROD 是齐的，缺的只是投影。

#### 3\.2\.4 内容层 → 编排层的派生口径（一条 SQL，可校验、可重跑）

**核心映射**：`structure.sort_order = 模块基址 + question.section`，基址 `LISTEN=0 / READ=4 / WRITE=20 / TRANSLATION=22`。

```sql
-- ① 板块（practice_paper_structure）—— 逐 (paper, section_mapping, section) 派生
SELECT p.id                                                AS paper_id,
       p.version,
       CAST(REPLACE(p.level, '-9', '') AS UNSIGNED)         AS hsk_level,
       q.section_mapping                                    AS content_type,
       CAST(q.section AS SIGNED)
         + CASE q.section_mapping
             WHEN 'SEC_LISTEN'      THEN 0
             WHEN 'SEC_READ'        THEN 4
             WHEN 'SEC_WRITE'       THEN 20
             WHEN 'SEC_TRANSLATION' THEN 22
           END                                              AS sort_order,
       CONCAT('第', q.section, '部分')                       AS section_name,
       COUNT(*)                                             AS question_count
FROM exam_paper p
JOIN question q ON q.paper_id = p.id AND q.deleted = 0
WHERE p.deleted = 0 AND p.exam_type = 1 AND p.deleted_prac = 0   -- ⚠️ PROD 缺 deleted_prac 列（D11），DDL 前临时去掉此项
  AND q.section_mapping IN ('SEC_LISTEN','SEC_READ','SEC_WRITE','SEC_TRANSLATION','SEC_SPEAKING')
  AND (q.type_id_mapping IS NULL OR q.type_id_mapping <> 'example_question')  -- ← 例题必须排除
  AND q.section IS NOT NULL AND q.section <> ''                                -- ← 空部分号的脏数据不入目录
GROUP BY p.id, p.version, p.level, q.section_mapping, q.section;

-- ② 题型/作答模式（practice_part_setting）—— 严格按 type_code 查字典，不从 layout 推
--    同一个 type_code 在一个 section 内必须只有一个 answer_mode，否则该行不进目录并告警

-- ③ 等级开关（practice_module_level_config）—— 由 ① 的 (version, hsk_level, content_type) 去重

-- ④ 卷上下架（practice_paper_setting）—— 每张参与练习的卷 1 行（enabled=1, visible=1）
```

**上线前必须先跑的一致性校验**（不需要改库即可执行，用于回答「派生会不会改变现网」）：

```sql
WITH s AS (
  SELECT paper_id, version,
         CONVERT(content_type USING utf8mb4) COLLATE utf8mb4_0900_ai_ci AS content_type,  -- ← 见 §3.2.5
         sort_order, question_count
  FROM practice_paper_structure WHERE deleted = 0
), d AS (
  SELECT q.paper_id, q.section_mapping AS content_type,
         CAST(q.section AS SIGNED) + CASE q.section_mapping
             WHEN 'SEC_LISTEN' THEN 0 WHEN 'SEC_READ' THEN 4
             WHEN 'SEC_WRITE' THEN 20 WHEN 'SEC_TRANSLATION' THEN 22 END AS so,
         COUNT(*) AS qc
  FROM question q WHERE q.deleted = 0
    AND (q.type_id_mapping IS NULL OR q.type_id_mapping <> 'example_question')
  GROUP BY q.paper_id, q.section_mapping, q.section
)
SELECT s.version, s.content_type, COUNT(*) AS s_rows,
       SUM(d.qc IS NULL) AS miss, SUM(d.qc <> s.question_count) AS qc_diff,
       SUM(d.qc = s.question_count) AS exact
FROM s LEFT JOIN d
  ON d.paper_id = s.paper_id AND d.content_type = s.content_type AND d.so = s.sort_order
GROUP BY s.version, s.content_type;
```

实测结论（TEST，2026-11-10）：`SEC_LISTEN` 446/446、`SEC_WRITE` 166/166、`SEC_TRANSLATION` 1/1 **全部精确**；`SEC_READ` 314/474（差异原因与处置见冲突 2）。

约束：
1. 生成脚本必须**幂等**（`INSERT ... ON DUPLICATE KEY UPDATE`），只写 `deleted=0` 的行；
2. `practice_paper_setting` 必须为每张新卷补 1 行，否则 `PracticeCatalogBatchLoader` 会整卷丢弃；
3. `answer_mode` 取值域需扩展：现有 `SINGLE/MATCH/ORDER/RECORD`，翻译笔译为 `TEXT`（TEST 已有该值，PROD 无）；
4. **阅读不自动覆盖**：`SEC_READ` 已有行一律跳过，只补缺失行（避免用派生值改掉人工编排）；
5. 脚本走五闸门 + DRY-RUN + 备份，见 [02改库红线与五闸门](../../02软件架构/02数据库/02改库红线与五闸门.md)。

#### 3\.2\.5 唯一键与 collation（一个已实测踩到的坑）

| 唯一键 | 影响 |
|---|---|
| `practice_module_level_config :: uk_module_level (version, level, section_mapping)` | 已含 `version`，**两版本天然共存**，无需改键 |
| `practice_part_setting :: uk_part_code (paper_id, section_mapping, section_code)` | 翻译 `section_code=1`（笔译）/ `2`（口译）可共存，但目前只建了 1 行（D2） |
| `practice_user_preference :: uk_preference_user_module (user_id, section_mapping)` | **不含 version** → 两版本写同一行会覆盖，P0 靠「3.0 不写」规避（ADR-03） |

🔴 **collation 不一致（D10）**：

| 表.列 | collation |
|---|---|
| `practice_paper_structure.version` / `.content_type` | `utf8mb4_unicode_ci` |
| `exam_paper.version` / `question.section_mapping` / `practice_module_level_config.version` / `hsk_level_config.version` | `utf8mb4_0900_ai_ci` |

两库**完全一致地**存在这个差异。后果：任何 `ps.version = ep.version`、`ps.content_type = q.section_mapping` 的 JOIN 直接
`ERROR 1267 Illegal mix of collations`（本次探查已实际触发一次，不是理论风险）。

处置：
- **P0**：Mapper 里一律 `CONVERT(x USING utf8mb4) COLLATE utf8mb4_0900_ai_ci`，或干脆不 JOIN（两张表分开查、内存里拼）
- **P1**：`ALTER TABLE practice_paper_structure MODIFY version varchar(30) COLLATE utf8mb4_0900_ai_ci`（连同 `content_type`），一次对齐；走五闸门 + 备份

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
| 14 | GET | `/speaking/levels` | `VERSION = "HSK2.0"` 常量；`SEC_SPEAK` 单映射 | 常量改参数；按版本**分流读源**（2.0 → `speaking_exam_paper`，3.0 → `exam_paper` + `SEC_SPEAKING`），**不合并去重**（ADR-07） |
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

### ADR-07 HSK3.0 口语读 `exam_paper`，不读 `speaking_exam_paper`

| 方案 | 数据现状 | 评价 |
|---|---|---|
| **A. 3.0 读 `exam_paper` + `question.SEC_SPEAKING`（采纳）** | PROD 1 卷 5 题 ✅ / TEST 同 | 立即可用；与听力/阅读/写作/翻译**同一张卷同一条链路**，`paperId` 天然对齐，不必维护两套 ID |
| B. 3.0 读 `speaking_exam_paper` | TEST 5 卷 / **PROD 0 卷** | 必须先补 5 卷 + 69 题录入才能上线，纯数据阻塞 |
| C. 两套都读、按 `source` 合并 | 两套并存 | 去重靠字符串 `source`，且 `level` 写法不同（`7` vs `7-9`）；合并逻辑本身就是新的 bug 面 |

**选 A 的根本理由**：HSK3.0 的设计前提是「一张卷包含听、读、写、译、说五段」，而 2.0 的口语是独立考试（`Beginner/Intermediate/Advanced` 三档，与 HSK1–6 不同构）。**把 3.0 口语塞进 2.0 的口语表，等于把两种不同的考试结构强行统一**，`level` 语义（`3` vs `Beginner`）就先冲突了。

**代价**：`SpeakingCatalogServiceImpl` 出现一个 `if (version)` 分支，两条查询路径。用统一的 `SpeakingPaperView` DTO 收口，分支只存在于 Repository 层。

**遗留**：TEST 那 5 张 HSK3.0 口语卷不删不写，标记历史数据。若 P2 决定转为 B 方案，需要先补 PROD 数据，并写一次 `question → speaking_exam_paper_question` 的搬运脚本。

### ADR-08 不新建翻译表，也不在 5 张表上加列

| 方案 | 代价 |
|---|---|
| **A. 复用 `question` + `section_mapping='SEC_TRANSLATION'`（采纳）** | 0 DDL、0 数据迁移；代价是写作与翻译共用 `writing_attempt`，靠 `content_type` + `section_mapping` 双条件隔离 |
| B. 在 `exam_paper` 加 `has_translation` / 在 `question` 加 `module_code` 列 | 冗余列，必然与 `section_mapping` 不一致；且 `manage` 导入链路、`exam-service` 都要跟着改 |
| C. 新建 `translation_paper` / `translation_question` | 题干复制两遍，AI 评分、报告、统计三套口径重造（ADR-02 方案 C） |

**判定标准**：一个信息如果能从既有列**确定性推出**（如「这卷有没有翻译」= `EXISTS(section_mapping='SEC_TRANSLATION')`），就绝不加列；只有推不出来的（如「部分中文名」「建议时长」）才允许进编排层。

**唯一可能加列的场景**（P2 再议）：若产品要求「同一卷的翻译可单独上下架」，需要一个卷级开关，那时加 `practice_paper_setting` 的模块级行，而不是改题库表。

### ADR-09 collation 用代码兼容，P0 不动 DDL

| 方案 | 评价 |
|---|---|
| **P0：Mapper 里 `CONVERT ... COLLATE`（采纳）** | 零 DDL、零锁表风险；代价是每个跨表 JOIN 都要写一坨，容易被后人漏掉 |
| P0：立刻 `ALTER TABLE` 改 collation | `practice_paper_structure` 是小表（约 1200 行），技术上可行，但属于**改结构**，需要停机窗口 + 回归 `practice-service` 全部查询 |
| 都不做 | 一定会踩 `ERROR 1267`，且报错信息不含业务语义，排查成本高 |

**为什么 P0 选代码**：本次已有 16 个端点要改，再叠加一次表结构变更会让回归面失控。代码侧把 collation 转换收进一个 Mapper `<sql>` 片段复用，P1 再一次性对齐 DDL 并删除转换。

---

## 10\. 修订记录

| 版本 | 修改内容 | 修改人 | 日期 |
|---|---|---|---|
| v1.0 | 初稿：双版本目录改造、翻译独立模块、聚合接口、数据缺口与 ADR | | 2026-11-10 |
| **v1.1** | **改为「基于既有 5 张题库表改造」口径**：① §3.1.2 重画为内容层/编排层/作答层三层模型；② §3.2.1 明确五表逐表改造判定（零 DDL）+ `deleted_prac` 与运营上下架的 AND 关系；③ 新增 §3.2.2 三处语义冲突裁定（口语双轨 / 部分号基址 / answer_mode 不可由 layout 推导）；④ §3.2.4 派生口径补上基址映射与一致性校验 SQL；⑤ 新增 §3.2.5 collation 陷阱（D10）、ADR-07/08/09；⑥ D1/D4/D7 由「手工补配置」降级为「跑脚本」；⑦ 新增 B-09/B-10、D9/D10/**D11（PROD 缺 `deleted_prac`）** | | 2026-11-10 |

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

| 期 | 范围 | 前置 | 完成判据 |
|---|---|---|---|
| **P0-a** | 修 B-01 / B-02 / B-03 三条存量缺陷 | 无 | TEST 听力 intro 不 500；PROD 听力列表不混版；HSK7-9 写作可开练习 |
| **P0-b** | `PracticeVersion` / `PracticeLevelCode` / `PracticeModuleCatalog` 三个支撑类 | — | 单测覆盖 `HSK7-9`、`'7-9'`、非法版本 |
| **P0-c** | 16 个目录端点加 `version` | P0-b | HSK2.0 全链路零回归 |
| **P0-d** | 聚合接口 `GET /hsk/modules` | P0-c | 2.0 四卡 / 3.0 五卡，布局与角标正确 |
| **P0-e** | 翻译目录 4 + 写链路 6 + `validatePart` 放宽 | **D2 补口译配置** | 翻译笔译可练到交卷；写作 `structureId` 打翻译 → 400 |
| **P0-f** | **数据补全 D1 / D2 / D3 / D4 / D7 / D11**（跑派生脚本 + 补口译 2 行 + level 收敛 + PROD 补 `deleted_prac`） | **D11 的 DDL 先于一切**；五闸门 + DRY-RUN + 备份 | PROD 切 3.0 五卡有数据 |
| P1 | 偏好表加 `version`；ID 改 String；`dataVersion` ETag；角标后台可配；补 `TRANSLATION_WRITTEN` 策略；**D10 collation 对齐**；B-09 修正 | P0 上线观察 | — |
| P2 | 口译 ASR + 自动评分；若转 ADR-07 方案 B，补 PROD 口语卷并做 `question → speaking_exam_paper_question` 搬运 | `ai-service` 接入 | — |

> 🔴 **P0-f 已从「不可代码化的手工补配置」变为「跑一遍幂等脚本」**：内容层（`exam_paper` + `question`）在 PROD 是齐的，缺的只是编排层的投影。脚本先跑一致性校验（§3.2.4），确认对现网 2.0 零改动后，再补 3.0。
> 顺序建议：**P0-a（修 B-01/02/03）→ P0-b/c（支撑类 + 版本参数）→ P0-f 的 D2/D3（小数据修补）→ P0-d/e（聚合接口 + 翻译）→ P0-f 主脚本**。
