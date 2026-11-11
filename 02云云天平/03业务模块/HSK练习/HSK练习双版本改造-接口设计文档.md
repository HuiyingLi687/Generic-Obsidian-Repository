# HSK 练习双版本（2.0 / 3.0）与翻译模块拆分 · 接口设计文档

> 版本：v1.1｜更新日期：2026-11-10
> 影响服务：practice-service（改造 + 新增）；exam-service / manage 仅实体加字段
> 关联文档：[HSK练习双版本与翻译模块拆分-SDD](HSK练习双版本与翻译模块拆分-SDD.md)
> 开发：待填｜测试：待填｜前端：待填
>
> 🧭 **基线声明**：本文所有字段、值域、用例、验收**一律以 TEST 库为准**。生产库与 TEST 的差异只在 **§9.1** 登记（明细见 SDD 附录 D），生产改造另行安排，不在本文档范围内。

---

## 改动标记约定

- 【新增】：本次迭代新增的字段 / 接口 / 业务逻辑
- 【修改】：原有字段，本次修改约束、含义或取值逻辑
- 【删除】：原有字段，本次移除
- 【无变更】：原有内容，本次迭代不做任何改动

---

## 0. 变更决策记录

| # | 决策项 | 取值规则 |
|---|---|---|
| 1 | 版本参数形态 | `version` 走 query string，枚举 `HSK2.0` / `HSK3.0`，缺省 `HSK2.0`，**大小写敏感**，无 `ALL` / `LATEST` |
| 2 | 板块定位键 | 全面弃用 `structureId`，改用 `section`（板块号，整数）。`practice_paper_structure` / `practice_part_setting` 两表本期 drop |
| 3 | `section` 取值 | 与 `question.section` 对齐，`1..N`。口语也是 `1/2/3`，不再用 `PART_1` |
| 4 | `partCode` 取值 | **保持不变**：口语 `PART_{section}`（如 `PART_1`），其余模块 `{section}`（如 `"1"`）。服务端由 `section` 派生，不再查表 |
| 5 | 板块字段来源 | `parts[]` 全部字段直取 `practice_module_part_config` 同名列，三语同发；**不下发 `answerMode`**（答题形式由**题目接口逐题下发 `layout`** 判定，见 §4.0.5） |
| 5b | 答题形式真源 | **`question.layout`**，原样透传、不做枚举换算。`typeCode` 只表业务语义（题型名 / 评分策略），**不能反推答题形式**（PROD 实测同一 `type_id_mapping` 对 4 种 layout） |
| 6 | 报告 latest 路径 | 旧 `/parts/{structureId}/reports/latest` **直接删除**，换 `/papers/{paperId}/parts/{section}/reports/latest`，不保留兼容 |
| 7 | 上下架口径 | 练习侧只读 `enabled_prac = 1`；`enabled`（板块）/ `exam_paper.enabled_prac`（卷）/ `question.enabled_prac`（题）三级独立，详见 SDD §3.4 |
| 8 | 板块开关 | `practice_module_part_config.enabled`：`1` 开放 / `0` 关闭。`deleted` 回到纯逻辑删除，不作开关 |
| 9 | 翻译版本门槛 | 翻译仅 `HSK3.0` 有数据。2.0 调目录接口返回**空数组 / 空对象**，不报 404 |
| 10 | 翻译作答复用写作链路 | 6 个写链路端点薄封装委托 `Writing*Service`，唯一侵入点是 `validatePart` 放宽 `contentType` 白名单 |
| 11 | 环境基线 | **以 TEST 为准**。生产差异只在 §9.1 登记，不改字段契约、不写进接口行为 |
| 12 | 等级入参命名 | 请求与响应一律用 **`level`**（query / path / body），**取数字串**（`"1"`–`"6"`、`"7"`=HSK7-9 整级）；显示名另给 `levelName`。`levelCode` / `databaseLevel` 全部废弃 |
| 13 | 模块卡数据源 | `/hsk/modules` 的模块卡**取自字典表**（`hsk_practice_module_v2` / `_v3`），不做进程内常量。字段一列一义：`item_text`=中文名、`item_value`=`sectionMapping`、`description`=`moduleCode`、`sort_order`=顺序、`item_properties` 只放 `moduleCode`/`nameEn`/`nameVi` 的 JSON；`layout` 存 `sys_dict.remark`。`icon`/`theme`/`badge`/`entryLevelCode` **不入库、不下发**，前端按 `moduleCode` 内置 |
| 14 | **目录接口统一为三跳** | 5 个模块同一套 3 端点：`/{mod}/levels`（单对象 + `papers[]`）→ `/{mod}/levels/{level}/intro` → `/{mod}/papers/{paperId}/parts`（对象包裹）。**4 个 `/papers` 端点删除**；板块数组统一 `parts`、时长统一 `durationMinutes`、卷状态统一小写 |
| 15 | **`/parts` 进度字段** | 4 个通用字段（`status`/`doneCount`/`correctCount`/`wrongCount`）+ 3 个扩展块（`draft`/`report`/`stats`）。**不再平铺** `draftRecordId` / `draftAttemptId` / `latestReportId` / `feedbackStatus` 等模块专属字段 |

---

## 1. 现状问题列表（本次要修复的 bug）

| # | 问题描述 | 带来的后果 |
|---|---|---|
| 1 | `ListeningCatalogServiceImpl#getIntro` / `#listParts` 的 `selectOne` 不带 `version` | 两版本同等级共存时抛 `TooManyResultsException` → **TEST 已 500** |
| 2 | `ListeningCatalogServiceImpl#getLevelOverview` 卷查询无 `version` / `exam_type` 过滤 | PROD 听力列表混入 3 张 3.0 卷，且 `totalCount=0` |
| 3 | `WritingAttemptServiceImpl#requirePaper`、`WritingCatalogServiceImpl#listParts`、`ReadingCatalogServiceImpl#paperResponse` 裸调 `Integer.parseInt(paper.getLevel())` | PROD 的 `level='7-9'` → `NumberFormatException` → **500** |
| 4 | `WritingCatalogServiceImpl#parseLevel` 正则只认 `HSK[1-6]` | `HSK7-9` → 404，3.0 最高等级无法进入 |
| 5 | 阅读/写作/口语 Catalog 用 `"HSK" + level` 拼 code | 返回 `"HSK7"`，前端按 `HSK7-9` 查不到 |
| 6 | `SharedPaperEligibility.isEligible` 只判 `deleted` + `examType`，**不判 `enabled_prac`** | 目录已过滤下架卷，但详情 / 开始作答仍可进入 → **下架卷可直达** |
| 7 | 板块列表 `structureId` 与结构表强绑定 | 结构表 drop 后前端拿不到定位键；且 `structureId` 是 `(paper_id, section_mapping, section)` 的代理键，冗余 |
| 8 | 板块名 / 题型名只有中文单语（听力除外） | 靠 `Accept-Language` 服务端选一个语言，切换语言要重发请求 |
| 9 | 口语取题靠 `PartCodeCase` 硬编码 8 个题型 | 3.0 L4/L5/L6 的 `listen_retell`、L7 的 `applied_read_speak` / `listen_material_answer` / `viewpoint_express` 取不到题 |
| 10 | 翻译挂在写作模块内，无独立入口 | 3.0 首页无法出「翻译」卡片 |

---

## 2. 数据模型变更

> 只写改动部分。完整 DDL 见 SDD §3.2。

### 2.1 数据表改动

| 表名 | 改动内容 |
|---|---|
| `exam_paper` | 【新增】`enabled_prac tinyint NOT NULL DEFAULT 1`（练习侧上下架）、`enabled_exam tinyint NOT NULL DEFAULT 1`（考试侧）。原名 `deleted_prac`，本次一并改名并反转 0/1 |
| `question` | 【新增】同上两列。`question.enabled_prac` 为**题级上下架** |
| `question_group` | 【新增】同上两列（练习侧不单独判，材料随题走） |
| `speaking_exam_paper` | 【新增】同上两列 |
| `speaking_exam_paper_question` | 【新增】同上两列 |
| `practice_module_part_config` | 【新增】`enabled tinyint NOT NULL DEFAULT 1`（板块开关），位置在 `sort_order` 之后、`deleted` 之前。**仍缺唯一键** `uk_module_part (version, level, section_mapping, section)` |
| `practice_module_level_config` | 【删除】`parts_config` 列（板块配置已拉平成行式表） |
| `practice_paper_setting` | 【删除】整表 drop（卷级上下架由 `exam_paper.enabled_prac` 替代） |
| `practice_paper_structure` | 【删除】整表 drop |
| `practice_part_setting` | 【删除】整表 drop |
| `practice_record` | 【删除】`structure_id`、`practice_name`；【启用】`question_ids` 快照 |
| `practice_report` | 【删除】`structure_id` |
| `writing_attempt` | 【新增】`section_mapping`、`section` 两列（回填后删 `structure_id`） |
| `speaking_attempt` | 【新增】同上两列（`section_code` 是 `PART_1/2/3`，回填取 `SUBSTRING(section_code, 6)`） |
| `sys_dict` / `sys_dict_item` | 【仅数据，不改表结构】新增 `hsk_practice_module_v2`（1007，4 项）/ `hsk_practice_module_v3`（1008，5 项），作为 `/hsk/modules` 的模块卡数据源 |

> 以上均为 **TEST 现状**（5 张内容表两列已就位、`part_config` 132 行含 `enabled`）。生产库缺哪些列 / 表不在此展开，统一见 §9.1。

### 2.2 枚举与取值域更新

| 字段                         | 值                                         | 含义                                                                               |
| -------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------- |
| `version`                  | `HSK2.0` / `HSK3.0`                       | 【修改】由代码常量改为请求参数，缺省 `HSK2.0`                                                      |
| `level`                    | `"1"`…`"6"`、`"7"`                    | 【修改】请求参数名由 `levelCode` 统一为 `level`，**取数字串**；响应里也叫 `level`（回显同一数字串）+ `levelName`（显示名）。`"7"` 是 HSK7-9 **整级**，查询走候选集 `IN ('7','7-9')`；禁止 `HSK7` 这种拼接值 |
| `exam_paper.level`（DB）     | TEST `"7"` / PROD `"7-9"`                 | 【无变更】查询必须用候选集 `IN ('7','7-9')`                                                   |
| `section`                  | `1`…`N`                                   | 【新增】板块号，替代 `structureId`                                                         |
| `partCode`                 | `"1"`/`"2"`… 或 `PART_1`/`PART_2`/`PART_3` | 【无变更】口语带 `PART_` 前缀，其余纯数字串                                                       |
| `enabled` / `enabled_prac` | `0` / `1`                                 | 【新增】`1` 启用，`0` 关闭。正向布尔，不再是 `deleted_*`                                           |
| `typeCode`                 | 见 SDD §3.2.2                              | 【新增】`question.type_id_mapping` 稳定编码，如 `translation_written` / `translation_oral` |

### 2.3 板块配置实测取值（TEST，2026-11-10）

| 维度 | 取值 |
|---|---|
| 总行数 | 132（`HSK2.0` 57 / `HSK3.0` 75） |
| `SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` | 40 / 44 / 19 |
| `SEC_SPEAK` | 24（2.0 L1–L3、3.0 L3–L7 各 3 个板块） |
| `SEC_TRANSLATION` | **2**（3.0 L7：`section=1` 笔译 `translation_written`、`section=2` 口译 `translation_oral`） |
| `SEC_SPEAKING` | 3（历史编码残留，需清） |

---

## 3. 接口总览清单

> 路径为 service 内路径，客户端实际调用加网关前缀 `/api/practice`。
> 鉴权：**全部端点必须登录**（`Authorization: Bearer <JWT>` + `X-Client-Type: APP`）。

| #   | Method | Path                                                         | 用途           | 接口类型 | 改动简述                                                            |
| --- | ------ | ------------------------------------------------------------ | ------------ | ---- | --------------------------------------------------------------- |
| A1  | GET    | `/listening/levels`                                          | 听力等级概览 + 卷列表 | 改造   | 加 `version`、补 `exam_type=1`、走 `enabled_prac` 判定；**加 `levelName`** |
| A2  | GET    | `/listening/levels/{level}/intro`                        | 听力等级备考说明     | 改造   | `selectOne` 带 `version` + `deleted=0`；`parts[]` 三语 + `typeCode`；加 `level`/`levelName` |
| A3  | GET    | `/listening/papers/{paperId}/parts`                          | 听力卷板块列表      | 改造   | 加 `version`；板块换源配置表；`structureId` → `section`；进度收敛为 `draft`/`report`/`stats` |
| A4  | GET    | `/reading/levels`                                            | 阅读等级概览 + 卷列表 | 改造   | **从「等级数组」改为「单等级概览 + 内嵌 `papers[]`」**（照听力）；常量改 `version` |
| A5  | GET    | `/reading/levels/{level}/intro`                          | 阅读等级备考说明     | 改造   | `version` + `PracticeLevelCode` 解析；`sections` → `parts`、三语、`durationMinutes` |
| ~~A6~~ | ~~GET~~ | ~~`/reading/papers`~~                                     | ~~阅读卷列表~~    | **删除** | **并入 A4 的 `papers[]`** |
| A7  | GET    | `/reading/papers/{paperId}/parts`                            | 阅读卷板块列表      | 改造   | 卷 `version` 与入参不符 → 404；`structureId` → `section`；**外层加对象包裹** |
| A8  | GET    | `/reading/preferences`                                       | 阅读偏好         | 无变更  | P0 不动（表无 `version` 列）                                           |
| A9  | PUT    | `/reading/preferences/level`                                 | 更新阅读偏好       | 无变更  | P0 仅 2.0 可写                                                     |
| A10 | GET    | `/writing/levels`                                            | 写作等级概览 + 卷列表 | 改造   | 同 A4；补 `HSK7-9` 分支                                              |
| A11 | GET    | `/writing/levels/{level}/intro`                          | 写作等级备考说明     | 改造   | `parseLevel` 正则扩到 `HSK7-9`；`sections` → `parts`、三语                   |
| ~~A12~~ | ~~GET~~ | ~~`/writing/papers`~~                                    | ~~写作卷列表~~    | **删除** | **并入 A10 的 `papers[]`** |
| A13 | GET    | `/writing/papers/{paperId}/parts`                            | 写作卷板块列表      | 改造   | `parseDbLevel` 替代裸 `parseInt`；`structureId` → `section`；进度收敛 |
| A14 | GET    | `/speaking/levels`                                           | 口语等级概览 + 卷列表 | 改造   | 同 A4；**2.0 的 `level` 是 `"1"`–`"3"`，`levelName` 显示 HSKK 初/中/高**（换算表 §4.0.6） |
| A14b | GET   | `/speaking/levels/{level}/intro`                             | 口语等级备考说明     | 改造   | **原文档缺这个端点，补登记**；`sections` → `parts`、三语              |
| ~~A15~~ | ~~GET~~ | ~~`/speaking/papers`~~                                   | ~~口语卷列表~~    | **删除** | **并入 A14 的 `papers[]`** |
| A16 | GET    | `/speaking/papers/{paperId}/parts`                           | 口语卷板块列表      | 改造   | 板块换源配置表；`structureId` → `section`；口语计数进 `stats`           |
| B1  | GET    | `/translation/levels`                                        | 翻译等级概览 + 卷列表 | 新增   | 同 A4；2.0 → `paperCount=0` + `papers=[]`                          |
| B2  | GET    | `/translation/levels/{level}/intro`                      | 翻译等级备考说明     | 新增   | `parts[]` 来自板块配置                                               |
| ~~B3~~ | ~~GET~~ | ~~`/translation/papers`~~                                | ~~翻译卷列表~~    | **删除** | **并入 B1 的 `papers[]`** |
| B4  | GET    | `/translation/papers/{paperId}/parts`                        | 翻译卷板块列表      | 新增   | 2 个板块：笔译 / 口译                                                   |
| B5  | POST   | `/translation/attempts/start`                                | 开始翻译练习       | 新增   | 委托 `WritingAttemptService#start`                                |
| B6  | GET    | `/translation/attempts/{attemptId}`                          | 练习详情         | 新增   | 委托 `#get`                                                       |
| B7  | GET    | `/translation/attempts/{attemptId}/questions`                | 题目列表         | 新增   | 委托 `#listQuestions`                                             |
| B8  | PUT    | `/translation/attempts/{attemptId}/answers`                  | 批量保存答案       | 新增   | 委托 `WritingAnswerService#save`                                  |
| B9  | POST   | `/translation/attempts/{attemptId}/submissions`              | 交卷           | 新增   | 委托 `WritingSubmissionService#submit`                            |
| B10 | GET    | `/translation/reports/{reportId}`                            | 报告详情         | 新增   | 委托 `WritingReportService#get`                                   |
| C1  | GET    | `/listening/papers/{paperId}/parts/{section}/reports/latest` | 听力板块最近报告     | 改造   | 路径 `structureId` → `paperId + section`                          |
| C2  | GET    | `/reading/papers/{paperId}/parts/{section}/reports/latest`   | 阅读板块最近报告     | 改造   | 同上                                                              |
| C3  | GET    | `/writing/papers/{paperId}/parts/{section}/reports/latest`   | 写作板块最近报告     | 改造   | 同上                                                              |
| C4  | GET    | `/speaking/papers/{paperId}/parts/{section}/reports/latest`  | 口语板块最近报告     | 改造   | 同上                                                              |
| D1  | GET    | `/hsk/module-config/parts`                                   | 运营：查板块配置     | 新增   | 按 `version + level + sectionMapping` 查，**含 `enabled=0` 行**      |
| D2  | PATCH  | `/hsk/module-config/parts/{id}`                              | 运营：开关板块      | 新增   | 只改 `enabled`（可选 `sort_order`），不建行不删行                            |
| E1  | GET    | `/hsk/modules`                                               | 首页模块卡聚合      | 新增   | 一次返回布局 + 卡片 + 可用性 + 进度                                          |

**统计（共 30 个）**

| 类型 | 数量 | 明细 |
|---|---|---|
| 改造 | 17 | A 组 13（A1–A5、A7、A10、A11、A13、A14、A14b、A16）+ C 组 4 |
| 新增 | 11 | B 组 9（B1、B2、B4–B10）+ D 组 2 + E 组 1 |
| **删除** | **4** | A6 `/reading/papers`、A12 `/writing/papers`、A15 `/speaking/papers`、B3 `/translation/papers`（全部并入各自模块的 `/levels`） |
| 无变更（仅登记） | 2 | A8 `GET /reading/preferences`、A9 `PUT /reading/preferences/level` |

> **目录接口从「四跳」变「三跳」**：模块卡 → `/{mod}/levels?version=&level=`（等级概览 + 卷列表）→ `/{mod}/papers/{paperId}/parts` → 答题。听力本来就是这套，本次其余四个模块向它对齐（§4.0.6）。

---

## 4. 改动接口详情

### 4.0 公共约定（先读这一节）

#### 4.0.1 公共 Header

| Header | 位置 | 必填 | 约束&说明 |
|---|---|---|---|
| `Authorization` | header | 是 | `Bearer <JWT>` |
| `X-Client-Type` | header | 否 | 【无变更】`APP` / `WEB`，影响 `userId` 解析方式 |
| `Accept-Language` | header | 否 | `zh` / `en` / `vi`。**本次起不再影响 `parts[]` 语言**（三语同发），仅影响题干等其它文案 |
| `Idempotency-Key` | header | 提交类必填 | 【无变更】仅 `POST /submissions` 使用 |

#### 4.0.2 `version` 参数

| 项 | 规定 |
|---|---|
| 参数名 / 位置 | `version`，query string |
| 类型 / 必填 | `String`，**必填**（缺省按 `HSK2.0` 处理） |
| 白名单 | `HSK2.0` / `HSK3.0` |
| 大小写 | **敏感**，`hsk3.0` → 400 `PRACTICE_VERSION_INVALID` |
| 落点 | 必须**同时**作为 `practice_module_level_config.version` 与 `exam_paper.version` 的条件，漏一处会出现「等级列表是 2.0、卷列表是 3.0」 |

#### 4.0.3 统一的 Part 对象（五个模块的 `/intro` 与 `/parts` 共用）

`parts[]` / `sections[]` 的元素统一为下面这套字段，全部直取 `practice_module_part_config` 同名列：

```json
{
  "partCode": "1",
  "section": 1,
  "partName": "第一部分",
  "partNameEn": "Part 1",
  "partNameVi": "Phần 1",
  "typeCode": "listening_judge",
  "typeName": "看图判断题",
  "typeNameEn": "Picture Judgment",
  "typeNameVi": "Nhận định hình ảnh",
  "questionCount": 10,
  "sortOrder": 1,
  "layouts": ["judge"]
}
```

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `partCode` | String | 【无变更】 | 口语 `PART_{section}`（如 `PART_1`），其余模块 `{section}`（如 `"1"`）。**值域不变**，服务端由 `section` 派生 |
| `section` | Integer | 【新增】 | 板块号 `1..N`。**替代原 `structureId`**，后续所有作答 / 报告接口都用它定位 |
| `structureId` | Long | 【删除】 | 结构表 drop，不再下发。前端如仍在用，必须同步改为 `section` |
| `partName` | String | 【无变更】 | `part_name`，中文 |
| `partNameEn` | String | 【新增】 | `part_name_en`，非空 |
| `partNameVi` | String | 【新增】 | `part_name_vi`，非空 |
| `typeCode` | String | 【新增】 | `type_code`。**原阅读/写作/口语的 `questionType` 改名为 `typeCode`**，值不变 |
| `typeName` | String | 【修改】 | `type_name`。听力原本就叫 `typeName`；阅读/写作/口语原 `questionTypeName` **改名为 `typeName`** |
| `typeNameEn` | String | 【新增】 | `type_name_en`，非空 |
| `typeNameVi` | String | 【新增】 | `type_name_vi`，非空 |
| `questionCount` | Integer | 【修改】 | 口径由「配置的标准题量」改为「`question` 现算的实际题量（已排除 `enabled_prac=0` 的单题）」。**`questionCount = 0` 的板块不下发** |
| `sortOrder` | Integer | 【修改】 | `sort_order`。阅读/写作/口语的 `/parts` 原本没有该字段，本次统一补上 |
| `layouts` | Array\<String\> | 【新增】 | 该板块内**实际题目**的 `question.layout` 去重集合，按出现顺序。**答题形式看这个**（§4.0.5）。正常只有一个元素；`["input","record"]` 表示该板块混了两种交互 |

> **不再下发 `answerMode`**。`answerMode` 是「`typeCode` → 一套自定义枚举」的二次映射，而 `question.layout` 已经是落库的答题形式，直接透传即可——**少一层映射就少一处漏配**（写作 `WritingLayoutType` 的 switch 白名单漏了 3.0 的 `chart_analysis` / `topic_essay` 就是现成教训，B-04）。
> **三语实测填充率 132/132**，前端可放心直接取，不需要回退。

**可选字段 `durationMinutes`（仅口语）**：板块级建议时长，只有口语有（`speaking_exam_paper_question` 按板块推）。其余模块不下发该键。它**不是**模块级的 `durationMinutes`（那个在 `/intro` 顶层）。

**`/papers/{paperId}/parts` 追加的进度字段（`/intro` 的 `parts[]` 没有这组字段）**

五模块统一用下面 4 个通用字段 + 2 个扩展块，**前端一套渲染逻辑**：

```json
{
  "status": "in_progress",
  "doneCount": 4,
  "correctCount": null,
  "wrongCount": null,
  "draft":  { "id": 88123, "answeredCount": 4, "currentQuestionId": 90012 },
  "report": { "id": 88100, "hasReport": true, "status": "READY" },
  "stats":  null
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | String | 统一小写：`not_started` / `in_progress` / `completed`。**原阅读/写作/口语/翻译的大写枚举本次统一为小写** |
| `doneCount` | Integer | 已作答题数（口语 = 已录音题数） |
| `correctCount` | Integer | 正确数；**未提交或主观题为 `null`**（写作/翻译/口语恒 `null`） |
| `wrongCount` | Integer | 错误数，规则同上 |
| `draft` | Object \| null | 进行中草稿，无则 `null`。见下表 |
| `report` | Object \| null | 最近一次已出报告，无则 `null`。见下表 |
| `stats` | Object \| null | **模块特有计数**，目前只有口语返回，其余模块恒 `null`（见下表） |

`draft` / `report` / `stats` 三块的内部字段：

| 块 | 字段 | 类型 | 说明 |
|---|---|---|---|
| `draft` | `id` | Long | 草稿主键。听力/阅读 = `practice_record.id`；写作/翻译 = `writing_attempt.id`；口语 = `speaking_attempt.id` |
| `draft` | `answeredCount` | Integer | 草稿已答题数（续练时恢复进度用） |
| `draft` | `currentQuestionId` | Long \| null | 停在的题，无则 `null`（「继续上次位置」用） |
| `report` | `id` | Long | 报告主键。写作/翻译/口语 = 独立报告表 ID（可直接调 `GET /translation/reports/{id}`）；听力/阅读的报告以 `practice_record` 为载体，此值 = 该记录 ID，**查详情仍走 C 组 `/reports/latest`** |
| `report` | `hasReport` | Boolean | 是否已有可看报告 |
| `report` | `status` | String \| null | 报告状态：`READY` / `PENDING` / `FAILED` / `UNAVAILABLE`。听力/阅读恒 `READY`；写作/翻译取 `feedbackStatus`；口语取 `reportStatus` |
| `stats` | `recordedCount` | Integer | 【口语】已录音题数 |
| `stats` | `scoredCount` | Integer | 【口语】已评分题数 |
| `stats` | `unansweredCount` | Integer | 【口语】未作答（未录音）题数 |
| `stats` | `failedCount` | Integer | 【口语】录音/评分失败题数 |

> **为什么把这些塞进扩展块而不是平铺**：听力原本只有 `status/doneCount`，阅读有 `draftRecordId/draftCurrentQuestionId`，写作有 `draftAttemptId/latestAttemptId/latestReportId/feedbackStatus`，口语有 `recordedCount/scoredCount/unansweredCount/failedCount`。平铺后必有大量恒 `null` 的字段，且同名不同义（`recordId` vs `attemptId` 都是「草稿 ID」）。收敛成 `draft.id` / `report.id` 后，前端只判「块是否为 `null`」，不判模块。

**各接口原本有没有这些字段（决定「新增」还是「改名」）**

| 接口 | 原本已有 | 本次新增 | 本次改名 |
|---|---|---|---|
| 听力 `/intro` 的 `parts[]` | `partName` ×3、`typeName` ×3、`questionCount`、`sortOrder` | `partCode`、`section`、`typeCode` | — |
| 听力 `/parts` 的 `parts[]` | `partName`（单语）、`typeName`（单语）、`questionCount`、`sortOrder` | `partCode`、`section`、`typeCode`、`partNameEn/Vi`、`typeNameEn/Vi` | — |
| 阅读 `/intro` 的 `sections[]` | `partCode`、`partName`、`questionType`、`questionTypeName`、`questionCount`、`sortOrder` | `section`、`partNameEn/Vi`、`typeNameEn/Vi` | `questionType` → `typeCode`；`questionTypeName` → `typeName` |
| 阅读 `/parts` 的 `parts[]` | `structureId`、`partCode`、`partName`、`questionType`、`questionTypeName`、`questionCount` | `section`、`partNameEn/Vi`、`typeNameEn/Vi`、`sortOrder` | 同上；`structureId` 删除 |
| 写作 `/intro` 的 `sections[]` | 同阅读 `/intro`（**无 `sortOrder`**） | `section`、`partNameEn/Vi`、`typeNameEn/Vi`、`sortOrder` | 同阅读 |
| 写作 `/parts` 的 `parts[]` | `structureId`、`partCode`、`partName`、`questionType`、`questionTypeName`、`questionCount` | `section`、`partNameEn/Vi`、`typeNameEn/Vi`、`sortOrder` | 同上；`structureId` 删除 |
| 口语 `/intro` 的 `sections[]` | 同写作 `/intro` | `section`、`partNameEn/Vi`、`typeNameEn/Vi`、`sortOrder` | 同阅读 |
| 口语 `/parts` 的 `parts[]` | `structureId`、`partCode`、`partName`、`questionType`、`questionTypeName`、`questionCount`、`suggestedDurationMinutes` | `section`、`partNameEn/Vi`、`typeNameEn/Vi`、`sortOrder` | 同上；`structureId` 删除 |

> 听力是唯一「原本没有 `partCode`」的模块，前端如果对听力做过按数组下标的特殊处理，本次可以改用 `partCode` / `section`。

#### 4.0.4 板块的可见性规则（五级开关，决定「下发什么」）

| 级 | 开关 | 关掉之后 |
|---|---|---|
| L2 模块 | `practice_module_level_config.enabled = 0` | 整卡消失，等级接口返回 `[]`，**不再求值下级** |
| L3 卷 | `exam_paper.enabled_prac = 0` | 不在列表；详情 / 开始作答 404 |
| L4 板块 | `practice_module_part_config.enabled = 0` | 该板块不下发，且**不参与兜底** |
| L5 题 | `question.enabled_prac = 0` | 题量现算时不计入；算完为 0 则板块不下发 |

**兜底规则（缺行 ≠ 关闭）**：`practice_module_part_config` **没有该 `section` 的行**时，按 `第N部分` 兜底命名、视为开放，并记 `WARN` 日志。所以：

- `enabled = 0` → 板块**消失**
- 行被物理删除 → 板块**仍出现**（名称为 `第N部分`）

运营只能改 `enabled`，不能删行。这条必须分别测试（§8 用例 29）。

#### 4.0.5 答题形式：`question.layout` 是唯一真源

**结论**：前端「这道题怎么作答」只看 `question.layout`，不看 `typeCode`，也不需要服务端另造 `answerMode` 枚举。

`typeCode`（题型编码）管**业务语义**——叫什么题型、走哪套评分策略；`layout` 管**交互形态**。两者**不能互推**，实测：

| 环境 | `type_id_mapping` | 对应 `layout` 种类 |
|---|---|---|
| PROD | `listening_single` | **4 种**（`imageChoice` / `passageGroup` / `textChoice` / `textChoice_shareAudio`） |
| PROD | `listening_detail_choice` | **4 种** |
| TEST | `SINGLE` | 3 种（`clozeGroup` / `passageGroup` / `textChoice`） |
| TEST | `example_question` | 6 种（示例题，各种题型都有） |

所以「按 `typeCode` 猜答题形式」在 PROD 上必然猜错，必须读 `layout`。

**TEST 的规范化值域（7 个，纯交互形态）**

| `layout` | 交互 | 作答值 | 出现在 |
|---|---|---|---|
| `choice` | 单选：点一个选项 | 单值 | 听 / 读（主力，7377 题） |
| `choiceGrid` | 网格选择：多选 / 匹配，棋盘格布局 | 多值 | 听 / 读 / 写（1935 题） |
| `judge` | 对错判断 | 单值（T/F） | 听 / 读（1150 题） |
| `order` | 排序：拖动词卡 / 句子排序 | 有序多值 | 读 / 写（749 题） |
| `input` | 长文本输入 | 文本 | 写 / 译（246 题） |
| `shortInput` | 短文本输入（填空，逐字） | 文本 | 写（156 题） |
| `record` | 录音 | 音频 | 说 / 译（7 题） |

> 实测口径：TEST `question` 中 `section_mapping` 非空的 11620 行，`layout` 非空率 **100%**、值域正好这 7 个。
> 另有 **1904 行** `section_mapping IS NULL` 且 `layout='textChoice'`（老值，涉及 31 张卷），属**未纳入练习模块的卷**，不进目录，本次不处理。

**生产库的值域是另一套、缺失近半（差异登记，不影响接口契约）**

| 项 | TEST（契约基线） | PROD（差异） |
|---|---|---|
| `layout` 非空率 | **100%**（13524/13524） | **52.3%**（7105/13574） |
| 值域 | 上表 7 个 | 老值：`textChoice` / `textChoice_shareAudio` / `passageGroup` / `textJudge` / `imageMatch` / `imageJudge` / `imageChoice` / `clozeGroup` |
| 缺失分布 | 无 | `SEC_READ` **100% NULL（5108）**、`SEC_WRITE` **100% NULL（927）**、`SEC_TRANSLATION` 4、`SEC_SPEAKING` 5；只有 `SEC_LISTEN` 有值，且是老值域 |

老值域混了**题面形态**（`passageGroup` / `clozeGroup` 是「材料 + 一组小题」，不是答题形式）。

> 这是**环境差异**，不是接口设计问题：本接口只约定「原样透传 `layout`」，值域按 TEST 的 7 个走。生产要补数据时**只能按 `question.id` 从 TEST 复制**（可覆盖 6439/6469）、**禁止按值映射**（老值 `textChoice` 一对 3 个新值、`textChoice_shareAudio` 也一对 3，映射必把多选错成单选）——口径登记在 §9.1，本文档不执行。

**口语是例外：那张表没有 `layout`**

口语内容不在 `question`，在 `speaking_exam_paper_question`，**该表没有 `layout` 列**（`question` 里 `SEC_SPEAK` 的 5 条是造数残留，不读）。所以：

- 口语答题形式 P0 **按模块直接定**：全部 `record`（口语就是录音，没有别的交互）
- 若要支持「朗读 vs 自由说话」的差异化录音 UI，需给该表补 `layout` 列，或按 `question_type_mapping` 映射——**P1 再定**（§10 第 9 条）

**四个模块的现状（决定改动量）**

| 模块 | 取题接口 | 当前是否下发 | 处置 |
|---|---|---|---|
| 听力 | `GET /listening/records/{recordId}/questions` | ✅ 已有 `layout`，原样透传 | 不动 |
| 阅读 | `GET /reading/records/{recordId}/questions` | ❌ **没有**（只有 `typeId` / `typeIdMapping` / `content` / `passage` / `optionContent`） | **补 `layout`** |
| 写作 | `GET /writing/attempts/{attemptId}/questions` | ⚠️ 有 `layoutType`，但**不是读 `layout`**，是按 `type_id_mapping` 硬编码 switch 出来的枚举 | **改为读 `layout` 原样透传**（顺带修 B-04） |
| 翻译 | `GET /translation/attempts/{attemptId}/questions` | ❌ 新增接口 | **直接下发 `layout`** |
| 口语 | `GET /speaking/attempts/{attemptId}/questions` | ❌ 没有 | P0 恒 `record`，前端按模块写死；P1 补 |

**写作这一处必须改，否则 3.0 直接挂**：`WritingQuestionNormalizer` 的 `switch (question.getTypeIdMapping())` 只覆盖 5 个老题型（`write_complete_sent` / `write_character_writing` / `write_make_sent` / `write_short_essay` / `write_summary`），3.0 新增的 `chart_analysis` / `topic_essay` 不在其中 → 落到 default 分支（抛异常或空）。改为读 `layout` 后，加题型**不需要改代码**，只要运营填对 `layout`。

**一条 UI 约定（沿用 CSCA 既有做法）**：`layout` **原样透传、不推算、不做 enum 换算**。理由是 `CscaQuestionResponse` 已经这么做了，且注释写得很明确——「取哪个字段只由 `layout` 决定，**不能按『字段是否为空』猜形态**」（`clozeGroup` 的 `content` 与 `passage` 可能都为空）。四个 HSK 模块沿用同一约定，前端一套解析逻辑。

#### 4.0.6 目录三跳模型（5 个模块统一，照听力）

**结论**：听力、阅读、写作、口语、翻译的目录接口**收敛为同一套 3 个端点、同一套响应结构**。听力的「`/levels` 内嵌 `papers[]`」模型胜出，其余四个模块向它对齐。

| # | 端点 | 返回 | 用途 |
|---|---|---|---|
| 1 | `GET /{module}/levels?version=&level=` | **单对象** `{ level, levelName, paperCount, papers[] }` | 等级概览 + 该等级全部卷的作答进度 |
| 2 | `GET /{module}/levels/{level}/intro?version=` | **单对象** `{ level, levelName, abilityDescription×3, totalQuestionCount, durationMinutes, parts[] }` | 该等级备考说明 |
| 3 | `GET /{module}/papers/{paperId}/parts?version=` | **单对象** `{ paperId, paperCode, parts[] }` | 卷内板块 + 进度 |

`{module}` 取值：`listening` / `reading` / `writing` / `speaking` / `translation`。

**七条统一规定**

| # | 规定 | 与旧实现的差别 |
|---|---|---|
| 1 | **响应一律是对象，不再是裸数组** | 阅读/写作/口语/翻译的 `/levels`、`/papers`、`/parts` 原本都返 `data: [...]`，全部改为对象包裹 |
| 2 | **`/{module}/papers` 删除** | 阅读/写作/口语/翻译的卷列表并入端点 1 的 `papers[]`；听力本就无此接口（A6/A12/A15/B3 标【删除】） |
| 3 | **`level` 是数字串**（`"1"`–`"7"`），请求与响应同值同域。`"7"` 代表 **HSK7-9 整级**；DB 里 `'7'`(TEST) / `'7-9'`(PROD) 两种存法都靠候选集 `IN ('7','7-9')` 兜住 | 原阅读返数值 `7`、口语返 `databaseLevel`、听力回显 `"1"`——统一成「**数字串 `level` + `levelName` 显示名**」；`levelCode` / `databaseLevel` / 数值 `level` 一律不再下发 |
| 4 | **新增 `levelName`**（本地化显示名，`Accept-Language` 决定） | 听力原本只有 `level`，本次补 `levelName`；其余模块的 `levelName` 保留 |
| 5 | **板块数组统一叫 `parts`** | 阅读/写作/口语/翻译原叫 `sections` |
| 6 | **时长统一叫 `durationMinutes`** | 原 `suggestDurationMinutes`，本次改名 |
| 7 | **卷对象统一 5 字段**：`{ paperId, paperCode, status, completedCount, totalCount }` | 原阅读/写作/翻译用 `totalQuestionCount` / `completedQuestionCount` / `paperName`，口语还有 `recordedCount` / `scoredCount`；全部收敛（口语的评分统计移到板块页 `stats`） |

**`level` 的值域按模块 × 版本不同（唯一一处不统一，因为数据本就不同）**

| 模块 | `HSK2.0` | `HSK3.0` | 数据来源 |
|---|---|---|---|
| 听力 / 阅读 | `"1"`–`"6"` | `"1"`–`"6"`、`"7"` | `exam_paper.level` = `'1'…'6'` / `'7'`(TEST)、`'7-9'`(PROD) |
| 写作 | `"3"`–`"6"`（1/2 级 `enabled=0`） | `"2"`–`"6"`、`"7"` | 同上 |
| 翻译 | 无（返回空） | 仅 `"7"` | `exam_paper.level` |
| 口语 | `"1"` / `"2"` / `"3"`（HSKK 初/中/高） | `"3"`–`"6"`、`"7"` | `level_config.level`；卷侧 `speaking_exam_paper.level` = `Beginner`/`Intermediate`/`Advanced`（2.0）、`'3'…'6'` / `'7-9'`（3.0） |

> ⚠️ **口语卷的 `level` 是唯一与「数字串」不一致的地方**（`Beginner` / `Intermediate` / `Advanced`），接口对外仍用数字串，靠一张换算表兜住（**只能落在 `PracticeLevelCode` 一个地方**，禁止各接口自行拼接）。只有 `levelName` 需要按版本区分：

| 版本 | 接口 `level` | `level_config.level` | 卷 `level` | `levelName`（zh） |
|---|---|---|---|---|
| HSK2.0 口语 | `"1"` | 1 | `Beginner` | HSKK 初级 |
| HSK2.0 口语 | `"2"` | 2 | `Intermediate` | HSKK 中级 |
| HSK2.0 口语 | `"3"` | 3 | `Advanced` | HSKK 高级 |
| HSK3.0 口语 | `"3"`–`"6"` | 3–6 | `'3'…'6'` | HSK 3 – HSK 6 |
| HSK3.0 口语 | `"7"` | 7 | `'7-9'` | HSK 7-9 |

> 即：**同一个 `"3"` 在 2.0 口语是「HSKK 高级」、在 3.0 口语是「HSK 3」** —— `levelName` 必须按「模块 + 版本」取，不能只按 `level` 数值查字典。


**卷状态枚举统一为小写**

| 值 | 含义 |
|---|---|
| `not_started` | 未开始 |
| `in_progress` | 进行中 |
| `completed` | 已完成 |

> 原阅读/写作/口语/翻译返的是 `NOT_STARTED` / `IN_PROGRESS` / `COMPLETED`，本次全部改小写——**这是破坏性变更，必须与前端同批上线**（§6.1）。全部模块只有这一种枚举，不再「按模块分别处理」。

**模块无内容时不报错**

| 场景 | 返回 |
|---|---|
| 2.0 调 `/translation/levels` | 200，`paperCount = 0`、`papers = []` |
| 某等级无卷（如写作 2.0 的 `"1"`/`"2"`） | 200，`paperCount = 0`、`papers = []` |
| 该等级 `level_config.enabled = 0` 或 `deleted = 1` | 200，空对象同上；**不 404**（前端据此显示「该等级暂未开放」） |

**等级选择页的数据源（三跳带来的唯一代价）**

改成三跳后，不再有「一次拿全部等级 + 各等级能力描述」的接口。P0 采用：

1. 等级 chip 由前端按版本矩阵渲染（`HSK2.0`：听/读 `1`–`6`、写 `3`–`6`、口 `1`–`3`（HSKK 初/中/高）；`HSK3.0`：听/读 `1`–`7`、写 `2`–`7`、口 `3`–`7`）
2. 需要显示每级能力描述时，逐级调端点 2（6–7 个并发请求，可本地缓存 1 天）

> 若产品坚持「一次请求拿全部等级」，再加 `GET /{module}/levels/all?version=`（只返 `{level, levelName, abilityDescription×3, totalQuestionCount}`，不含 `parts`），**不塞进端点 1**——否则「单等级概览」与「全等级列表」两个语义又会分叉回旧问题。见 §10 第 14 条。

---

### 4.1 目录端点（A 组：13 个改造 + 3 个删除）

#### A1 `GET /listening/levels`

**用途**：听力模块等级概览 + 该等级下全部试卷的答题情况
**鉴权**：需要登录

**入参说明**

| 参数名             | 位置     | 类型     | 必填  | 约束&说明                          |
| --------------- | ------ | ------ | --- | ------------------------------ |
| `version`       | query  | String | 是   | 【新增】`HSK2.0` / `HSK3.0`，缺省 2.0 |
| `level`         | query  | String | 否   | 【无变更】不传则取用户上次选择，再缺省 `1`        |
| `X-Client-Type` | header | String | 否   | 【无变更】                          |

**请求示例**

```http
GET /api/practice/listening/levels?version=HSK2.0&level=1
Authorization: Bearer xxx
X-Client-Type: APP
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "1",
    "levelName": "HSK1",
    "paperCount": 20,
    "papers": [
      { "paperId": 2104193520701620225, "paperCode": "HSK1听力模拟卷1",
        "status": "in_progress", "completedCount": 8, "totalCount": 20 }
    ]
  }
}
```

**返回字段说明**

| 字段                        | 类型      | 改动标记  | 说明                                                                                 |
| ------------------------- | ------- | ----- | ---------------------------------------------------------------------------------- |
| `level`                   | String  | 【无变更】 | 数字串 `"1"`…`"6"`、`"7"`（`7` = HSK7-9 整级），与请求参数同值同域（§4.0.6 规定 3）。听力原本就是数字串，**本次不改取值** |
| `levelName`               | String  | 【新增】  | 本地化显示名（`HSK1` / `HSK7-9`），随 `Accept-Language`                                      |
| `paperCount`              | Integer | 【修改】  | 该等级卷数。**旧实现混入 3.0 卷且 `totalCount=0`，本次修正**                                         |
| `papers[].paperId`        | Long    | 【无变更】 | 试卷 ID（19 位，**P1 改 String**）                                                        |
| `papers[].paperCode`      | String  | 【无变更】 | 试卷名称，取 `exam_paper.source`                                                         |
| `papers[].status`         | String  | 【无变更】 | `not_started` / `in_progress` / `completed`                                        |
| `papers[].completedCount` | Integer | 【无变更】 | 已答题数                                                                               |
| `papers[].totalCount`     | Integer | 【修改】  | 总题数。**旧实现为 0**（未按 `section_mapping` 过滤），本次改为现算                                     |

**服务端内部执行顺序**

1. 校验登录，解析 `version`（非法 → 400）
2. 校验 `level` 在白名单内（`"1"`–`"7"`）→ 查库时 `"7"` 展开成候选集 `IN ('7','7-9')`
3. 查 `exam_paper`：`version = ? AND exam_type = 1 AND deleted = 0 AND enabled_prac = 1 AND level IN (候选集)`
4. 批量查 `question` 统计每卷 `SEC_LISTEN` 题数（`deleted=0 AND enabled_prac=1`），`totalCount=0` 的卷剔除
5. 带 `userId` 批量查进行中 / 已完成记录，填充 `status` / `completedCount`
6. 返回

**本接口抛出错误码**：400 / 401

---

#### A2 `GET /listening/levels/{level}/intro`

**用途**：听力等级备考说明（能力描述 + 题型结构）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `level` | path | String | 是 | 【修改】数字串 `1`…`6`、`7`（原传 `HSK1` 形式，现改数字串，**URL 形态变化**） |
| `version` | query | String | 是 | 【新增】 |

**请求示例**

```http
GET /api/practice/listening/levels/1/intro?version=HSK2.0
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "1",
    "levelName": "HSK 1",
    "abilityDescription": "能理解并使用一些非常简单的中文词语和句子",
    "abilityDescriptionEn": "Can understand and use very simple Chinese words and sentences",
    "abilityDescriptionVi": "Có thể hiểu và sử dụng một số từ và câu tiếng Trung rất đơn giản",
    "totalQuestionCount": 20,
    "durationMinutes": 20,
    "parts": [
      { "partCode": "1", "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeCode": "listening_judge", "typeName": "看图判断题", "typeNameEn": "Picture Judgment",
        "typeNameVi": "Nhận định hình ảnh", "questionCount": 5, "sortOrder": 1, "layouts": ["judge"] }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `level` / `levelName` | String | 【新增】 | 等级编码 + 本地化名，与 A1 同义（§4.0.6 规定 3/4） |
| `abilityDescription` × 3 | String | 【无变更】 | 三语能力描述，来自 `practice_module_level_config` |
| `totalQuestionCount` | Integer | 【无变更】 | 模块标准总题量 |
| `durationMinutes` | Integer | 【无变更】 | 建议时长（分钟） |
| `parts[]` | Array | 【修改】 | **来源从 `parts_config` JSON 改为 `practice_module_part_config` 行式表**；字段见 §4.0.3，其中 `partCode` / `section` / `typeCode` / `partNameEn` / `partNameVi` / `typeNameVi` / `layouts` 为新增 |

**服务端内部执行顺序**

1. 校验登录，解析 `version`、`level`
2. `practice_module_level_config` 按 `version + level + SEC_LISTEN + deleted=0` 查**唯一一行**（旧实现无 version → 两版本共存时 `TooManyResultsException`，B-01）
3. `practice_module_part_config` 按 `version + level + SEC_LISTEN` 查**全量行**（不带 `enabled` 条件）→ 内存分拨：`enabled=1 AND deleted=0` 进骨架、`enabled=0 AND deleted=0` 进 `closedSections`、`deleted=1` 丢弃
4. 现算每个板块题量，`0` 的不下发
5. 兜底：`question` 里出现但既不在骨架也不在 `closedSections` 的 `section`，命名 `第N部分`、视为开放、记 `WARN`

**本接口抛出错误码**：400 / 401 / 404

---

#### A3 `GET /listening/papers/{paperId}/parts`

**用途**：听力某张卷的板块列表 + 用户进度
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `paperId` | path | Long | 是 | 【无变更】 |
| `version` | query | String | 是 | 【新增】卷的 `version` 与入参不符 → 404（**不提示版本不符**，避免探测） |

**请求示例**

```http
GET /api/practice/listening/papers/2104193520701620225/parts?version=HSK2.0
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "paperId": 2104193520701620225,
    "paperCode": "HSK1听力模拟卷1",
    "parts": [
      { "partCode": "1", "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeCode": "listening_judge", "typeName": "看图判断题", "typeNameEn": "Picture Judgment",
        "typeNameVi": "Nhận định hình ảnh", "questionCount": 5, "sortOrder": 1, "layouts": ["judge"],
        "status": "completed", "doneCount": 5, "correctCount": 4, "wrongCount": 1,
        "draft": null,
        "report": { "id": 88100, "hasReport": true, "status": "READY" },
        "stats": null },
      { "partCode": "2", "section": 2, "partName": "第二部分", "partNameEn": "Part 2", "partNameVi": "Phần 2",
        "typeCode": "listening_pic_choice", "typeName": "看图选择题", "typeNameEn": "Picture Choice",
        "typeNameVi": "Lựa chọn hình ảnh", "questionCount": 5, "sortOrder": 2, "layouts": ["choice"],
        "status": "in_progress", "doneCount": 2, "correctCount": null, "wrongCount": null,
        "draft": { "id": 88123, "answeredCount": 2, "currentQuestionId": 90012 },
        "report": null,
        "stats": null }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `paperId` / `paperCode` | — | 【无变更】 | 外层对象本次**从裸数组改成对象包裹**（§4.0.6 规定 1） |
| `parts[].structureId` | Long | 【删除】 | 改 `section` |
| `parts[]` 基础字段 | — | 见 §4.0.3 | `partCode` / `section` / 三语名 / `typeCode` / `questionCount` / `sortOrder` / `layouts` |
| `parts[].status` | String | 【无变更】 | `not_started` / `in_progress` / `completed` |
| `parts[].doneCount` | Integer | 【无变更】 | 已答题数 |
| `parts[].correctCount` | Integer | 【无变更】 | 正确数，仅已提交板块有值，否则 `null` |
| `parts[].wrongCount` | Integer | 【无变更】 | 错误数，规则同上 |
| `parts[].draft` | Object | 【修改】 | **原本是平铺的 `draftRecordId` / `draftAnsweredCount` / `draftCurrentQuestionId`（听力只有前两项）**，本次收敛成 `{id, answeredCount, currentQuestionId}`（§4.0.3 扩展块）；无草稿为 `null` |
| `parts[].report` | Object | 【修改】 | 原本是平铺的 `hasReport` / `latestRecordId`，收敛成 `{id, hasReport, status}`；听力/阅读 `status` 恒 `READY` |
| `parts[].stats` | Object | 【新增】 | 听力恒 `null`（仅口语有值） |

**服务端内部执行顺序**

1. 校验登录、`version`
2. 查卷：`id = ? AND version = ? AND exam_type = 1 AND deleted = 0 AND enabled_prac = 1`，不满足 → 404
3. 板块骨架 + 开关分流（同 A2 步骤 3）
4. 现算题量（`question` 按 `paper_id + SEC_LISTEN + section` 计数，排除 `example_question` 与 `enabled_prac=0`）
5. 按 `section` 查用户在本卷的 `practice_record`，填充 `status` / `doneCount`
6. `correctCount` / `wrongCount` 取自最近一次已出报告的记录

**本接口抛出错误码**：400 / 401 / 404

---

#### A4 `GET /reading/levels`

**用途**：阅读模块「当前等级概览 + 该等级全部卷的作答进度」（原「全部等级列表」）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `version` | query | String | 是 | 【新增】旧实现是代码常量 |
| `level` | query | String | 否 | 【新增】数字串 `"1"`…`"6"`、`"7"`；不传取用户上次选择，再缺省 `"1"` |

**请求示例**

```http
GET /api/practice/reading/levels?version=HSK3.0&level=7
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "7",
    "levelName": "HSK 7-9",
    "paperCount": 15,
    "papers": [
      { "paperId": 2104193520701620226, "paperCode": "HSK7-9阅读模拟卷1",
        "status": "in_progress", "completedCount": 12, "totalCount": 40 }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `level` | String | 【修改】 | 原「数值 `7` + `levelCode`」双字段，**统一为数字串** `"7"`（`levelCode` 删除）；显示名另给 `levelName`（§4.0.6 规定 3） |
| `levelName` | String | 【无变更】 | 本地化显示名 |
| `paperCount` | Integer | 【新增】 | 该等级可练卷数（`totalCount=0` 的卷不计） |
| `papers[]` | Array | 【新增】 | 原先由 A6 单独返回，现内嵌；**A6 已删除** |
| `papers[].paperId` / `paperCode` | — | 【无变更】 | `paperCode` 取 `source`；原 `paperName` 与之同值，删除 |
| `papers[].status` | String | 【修改】 | **原大写 `NOT_STARTED` 改小写** `not_started`（§4.0.6） |
| `papers[].completedCount` / `totalCount` | Integer | 【修改】 | 原 `completedQuestionCount` / `totalQuestionCount` **改名**，口径不变（`totalCount` 现算，排除 `enabled_prac=0` 的题） |
| ~~`levelId`~~ | — | 【删除】 | 内部主键不下发 |
| ~~`abilityDesc` / `totalQuestionCount` / `suggestDurationMinutes` / `sections[]`~~ | — | 【删除】 | 全部挪到 A5 `/levels/{level}/intro` |

**服务端内部执行顺序**

1. 校验登录、`version`
2. 解析 `level`（缺省：用户上次选择 → `"1"`）；`"7"` 展开成候选集 `IN ('7','7-9')`
3. 查 `practice_module_level_config`：`version = ? AND level = ? AND section_mapping = 'SEC_READ' AND enabled = 1 AND deleted = 0`；**查不到 → `paperCount=0` + `papers=[]`，不 404**
4. 查卷：`version=? AND exam_type=1 AND deleted=0 AND enabled_prac=1 AND level IN (候选集)`；现算 `SEC_READ` 题量，`totalCount=0` 剔除
5. 带 `userId` 批量查进行中 / 已完成记录，填 `status` / `completedCount`
6. 返回

**本接口抛出错误码**：400 / 401

---

#### A5 `GET /reading/levels/{level}/intro`

**用途**：阅读单等级备考说明（原 A5 的 `sections[]` 改 `parts[]`，补齐三语与 `levelName`）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `level` | path | String | 是 | 【修改】数字串 `7`（= HSK7-9 整级）；**旧实现裸 `parseInt("7-9")` 必 500/404**（B-06），改走 `PracticeLevelCode` |
| `version` | query | String | 是 | 【新增】 |

**请求示例**

```http
GET /api/practice/reading/levels/7/intro?version=HSK3.0
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "7",
    "levelName": "HSK 7-9",
    "abilityDescription": "能理解多种话题的中文材料并进行推断",
    "abilityDescriptionEn": "Can understand Chinese materials on a variety of topics and make inferences",
    "abilityDescriptionVi": "Có thể hiểu tài liệu tiếng Trung về nhiều chủ đề và suy luận",
    "totalQuestionCount": 40,
    "durationMinutes": 60,
    "parts": [
      { "partCode": "1", "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeCode": "reading_detail_choice", "typeName": "细节选择题", "typeNameEn": "Detail Multiple Choice",
        "typeNameVi": "Lựa chọn chi tiết", "questionCount": 10, "sortOrder": 1, "layouts": ["choice"] }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `level` / `levelName` | String | 【新增】 | 与 A4 同义 |
| `abilityDescription` × 3 | String | 【修改】 | 原只有单语 `abilityDesc`（随 `Accept-Language`），**改为三语同发**，字段名与小节名对齐（`abilityDesc` → `abilityDescription`） |
| `totalQuestionCount` | Integer | 【无变更】 | 模块标准总题量 |
| `durationMinutes` | Integer | 【修改】 | 原 `suggestDurationMinutes` **改名**，值不变 |
| `parts[]` | Array | 【修改】 | 原 `sections[]` **改名为 `parts`**；字段见 §4.0.3，`questionType` → `typeCode`、`questionTypeName` → `typeName` |
| ~~`levelId`~~ | — | 【删除】 | 内部主键不下发 |

**服务端内部执行顺序**

1. 校验登录、`version`、`level`
2. `practice_module_level_config` 按 `version + level + SEC_READ + deleted=0` 查唯一一行（**不能带 `enabled=1` 再判空**，否则关掉的等级会被当成「不存在」而 404；应查全量后内存判 `enabled`）
3. `practice_module_part_config` 按 `version + level + SEC_READ` 查全量行 → 内存分拨（§4.0.4）
4. 现算每个板块题量，`0` 的不下发
5. 兜底：`question` 里出现但配置里没有的 `section`，命名 `第N部分`、视为开放、记 `WARN`

**本接口抛出错误码**：400 / 401 / 404

---

#### A6 `GET /reading/papers` 【已删除，并入 A4】

**用途**：~~阅读某等级的试卷列表~~ → 已合并进 A4 的 `papers[]`

| 项 | 结论 |
|---|---|
| 端点 | **删除**（不保留兼容，不返 410） |
| 原因 | 与听力模型对齐：卷列表由 `GET /reading/levels?version=&level=` 的 `papers[]` 一并返回（§4.0.6 规定 2），避免「等级」与「卷」两个接口各自维护一套过滤条件 |
| 前端动作 | 原 `GET /reading/papers?level=7&version=HSK3.0` → `GET /reading/levels?level=7&version=HSK3.0`；从 `data.papers` 取值 |
| 字段变化 | `paperName` 删（与 `paperCode` 同值）、`totalQuestionCount` → `totalCount`、`completedQuestionCount` → `completedCount`、`status` 改小写 |

**本接口已不存在，调用必然 404**（路由删除后，网关会返回 `{"code":500}` + HTTP 200 的 `NoResourceFoundException`，排查见 §5 注）。

---

#### A7 `GET /reading/papers/{paperId}/parts`

**用途**：阅读某张卷的板块列表 + 草稿 / 报告进度
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `paperId` | path | Long | 是 | 【无变更】 |
| `version` | query | String | 是 | 【新增】卷 `version` 不符 → 404 |

**请求示例**

```http
GET /api/practice/reading/papers/2104193520701620226/parts?version=HSK3.0
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "paperId": 2104193520701620226,
    "paperCode": "HSK7-9阅读模拟卷1",
    "parts": [
      { "partCode": "1", "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeCode": "reading_detail_choice", "typeName": "细节选择题", "typeNameEn": "Detail Multiple Choice",
        "typeNameVi": "Lựa chọn chi tiết", "questionCount": 10, "sortOrder": 1, "layouts": ["choice"],
        "status": "completed", "doneCount": 10, "correctCount": 8, "wrongCount": 2,
        "draft": null,
        "report": { "id": 88100, "hasReport": true, "status": "READY" },
        "stats": null }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `paperId` / `paperCode` | — | 【新增】 | **外层从裸数组改成对象包裹**（§4.0.6 规定 1），前端取 `data.parts` |
| `structureId` | Long | 【删除】 | 改 `section` |
| `partCode` / `partName` / `questionCount` | — | 见 §4.0.3 | |
| `status` | String | 【修改】 | **新增通用进度字段**，原接口没有，用 `draftRecordId != null` 猜状态 → 改为显式 `not_started` / `in_progress` / `completed` |
| `doneCount` | Integer | 【修改】 | 原 `draftAnsweredCount` 改名并升级为「通用已答数」（含已提交的那次） |
| `correctCount` / `wrongCount` | Integer | 【无变更】 | 最近报告正误题数 |
| `draft` | Object | 【修改】 | 原平铺 `draftRecordId` / `draftAnsweredCount` / `draftCurrentQuestionId` → 收敛为 `{id, answeredCount, currentQuestionId}` |
| `report` | Object | 【修改】 | 原平铺 `hasReport` / `latestRecordId` → 收敛为 `{id, hasReport, status}` |
| `stats` | Object | 【新增】 | 阅读恒 `null` |

**服务端内部执行顺序**

1. 登录、`version`
2. 查卷：`id=? AND version=? AND exam_type=1 AND deleted=0 AND enabled_prac=1`，不满足 → 404
3. 板块骨架 + 开关分流 + 现算题量（§7.1）
4. 按 `section` 查 `practice_record` 草稿与最近报告

**本接口抛出错误码**：400 / 401 / 404

---

#### A8 `GET /reading/preferences` 【无变更】

**用途**：查询阅读偏好
**鉴权**：需要登录

P0 **不改代码**。原因：`practice_reading_preference` 表没有 `version` 列，2.0 / 3.0 共用一个偏好。P1 加列后再拆分。

**返回**：`{ userId, lastLevel, lastLevelCode, lastPaperId }`（全部【无变更】）

> ⚠️ 已知瑕疵：`lastLevelCode` 由 `"HSK" + lastLevel` 拼接，`7` 会输出 `HSK7`（B-05）。P0 不动，前端对 3.0 的偏好回填需容错。

---

#### A9 `PUT /reading/preferences/level` 【无变更】

**用途**：更新最近选择的阅读等级
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `level` | body | String | 是 | 【修改】参数名 `levelCode` → `level`，值域不变 |

P0 **只保证 2.0 可写**；3.0 传 `HSK7-9` 会 404（表无 `version` 列时的既有行为）。P1 加列后统一。

---

#### A10 `GET /writing/levels`

**用途**：写作模块「当前等级概览 + 该等级全部卷的作答进度」（原「全部等级列表」）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `version` | query | String | 是 | 【新增】旧实现是代码常量 |
| `level` | query | String | 否 | 【新增】数字串 `"1"`…`"6"`、`"7"`；不传取上次选择，再缺省该版本**最低可用**等级（2.0 = `"3"`，1/2 级 `enabled=0`；3.0 = `"2"`） |

**请求示例**

```http
GET /api/practice/writing/levels?version=HSK3.0&level=7
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "7",
    "levelName": "HSK 7-9",
    "paperCount": 15,
    "papers": [
      { "paperId": 2104193520701620227, "paperCode": "HSK7-9写作模拟卷1",
        "status": "not_started", "completedCount": 0, "totalCount": 2 }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `level` | String | 【修改】 | 原数值 `7` + `levelCode` 双字段 → 统一数字串 `"7"`（§4.0.6 规定 3） |
| `levelName` | String | 【无变更】 | 本地化名 |
| `paperCount` | Integer | 【新增】 | 该等级可练卷数（`totalCount=0` 的卷不计） |
| `papers[]` | Array | 【新增】 | 原先由 A12 单独返回，现内嵌；**A12 已删除** |
| `papers[].paperId` / `paperCode` | — | 【无变更】 | `paperCode` 取 `source`；`paperName` 删除 |
| `papers[].status` | String | 【修改】 | **大写改小写** `not_started` |
| `papers[].completedCount` / `totalCount` | Integer | 【修改】 | 原 `completedQuestionCount` / `totalQuestionCount` 改名；写作 `totalCount` 是**题数**（HSK7-9 为 2），不是卷数 |
| ~~`levelId` / `writingAvailable`~~ | — | 【删除】 | `levelId` 是内部主键；`writingAvailable` 与 `level_config.enabled` 重复，等级关掉时本就不出现在 `papers` 里 |
| ~~`abilityDesc` / `totalQuestionCount` / `suggestDurationMinutes` / `sections[]`~~ | — | 【删除】 | 全部挪到 A11 `/levels/{level}/intro` |

**服务端内部执行顺序**

1. 登录 → `version`
2. 解析 `level`（缺省按版本矩阵取最低可用等级）
3. `practice_module_level_config`：`version + level + SEC_WRITE + deleted=0`；内存判 `enabled`，关掉 → `paperCount=0` + `papers=[]`
4. 查卷 + 现算 `SEC_WRITE` 题量，`totalCount=0` 剔除
5. 带 `userId` 批量查 `writing_attempt` 填进度

**本接口抛出错误码**：400 / 401

---

#### A11 `GET /writing/levels/{level}/intro`

**用途**：写作单等级备考说明
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `level` | path | String | 是 | 【修改】数字串 `1`…`7`；`parseLevel` 不再用 `HSK[1-6]` 正则匹配，直接按数字串校验 |
| `version` | query | String | 是 | 【新增】 |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "7",
    "levelName": "HSK 7-9",
    "abilityDescription": "能用中文撰写观点明确的文章",
    "abilityDescriptionEn": "Can write articles with a clear point of view in Chinese",
    "abilityDescriptionVi": "Có thể viết bài tiếng Trung với quan điểm rõ ràng",
    "totalQuestionCount": 2,
    "durationMinutes": 55,
    "parts": [
      { "partCode": "1", "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeCode": "chart_analysis", "typeName": "图表描述", "typeNameEn": "Chart Description",
        "typeNameVi": "Mô tả biểu đồ", "questionCount": 1, "sortOrder": 1, "layouts": ["input"] },
      { "partCode": "2", "section": 2, "partName": "第二部分", "partNameEn": "Part 2", "partNameVi": "Phần 2",
        "typeCode": "topic_essay", "typeName": "话题作文", "typeNameEn": "Topic Essay",
        "typeNameVi": "Bài luận chủ đề", "questionCount": 1, "sortOrder": 2, "layouts": ["input"] }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `level` / `levelName` | String | 【新增】 | 与 A10 同义 |
| `abilityDescription` × 3 | String | 【修改】 | 原单语 `abilityDesc` → 三语，字段改名为 `abilityDescription` |
| `totalQuestionCount` | Integer | 【无变更】 | |
| `durationMinutes` | Integer | 【修改】 | 原 `suggestDurationMinutes` 改名 |
| `parts[]` | Array | 【修改】 | 原 `sections[]` 改名为 `parts`；**3.0 的 `HSK7-9` 新增两个板块**（`chart_analysis` + `topic_essay`），旧 `introSections` switch 只到 6 级（B-04） |

> **写作 3.0 的 `HSK7-9` 是本次新增分支**：`introSections` 的 `switch` 补 `7` 分支即可，但更彻底的做法是**直接读 `practice_module_part_config`**（不再按 level 写死板块），否则以后每加一个等级都要改代码。

**本接口抛出错误码**：400 / 401 / 404

---

#### A12 `GET /writing/papers` 【已删除，并入 A10】

| 项 | 结论 |
|---|---|
| 端点 | **删除** |
| 原因 | 卷列表由 `GET /writing/levels?version=&level=` 的 `papers[]` 一并返回（§4.0.6 规定 2） |
| 前端动作 | `GET /writing/papers?level=7&version=HSK3.0` → `GET /writing/levels?level=7&version=HSK3.0`，取 `data.papers` |
| 字段变化 | `paperName` 删、`totalQuestionCount` → `totalCount`、`completedQuestionCount` → `completedCount`、`status` 改小写 |

---

#### A13 `GET /writing/papers/{paperId}/parts`

**用途**：写作某张卷的板块列表 + 草稿 / 报告进度
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `paperId` | path | Long | 是 | 【无变更】 |
| `version` | query | String | 是 | 【新增】 |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "paperId": 2104193520701620227,
    "paperCode": "HSK7-9写作模拟卷1",
    "parts": [
      { "partCode": "1", "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeCode": "chart_analysis", "typeName": "图表描述", "typeNameEn": "Chart Description",
        "typeNameVi": "Mô tả biểu đồ", "questionCount": 1, "sortOrder": 1, "layouts": ["input"],
        "status": "in_progress", "doneCount": 1, "correctCount": null, "wrongCount": null,
        "draft": { "id": 5512, "answeredCount": 1, "currentQuestionId": 91001 },
        "report": { "id": 7712, "hasReport": true, "status": "READY" },
        "stats": null }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `paperId` / `paperCode` | — | 【新增】 | 外层从裸数组改对象包裹（§4.0.6 规定 1） |
| `structureId` | Long | 【删除】 | 改 `section` |
| `status` | String | 【新增】 | 通用进度字段，原接口没有 |
| `doneCount` | Integer | 【修改】 | 原 `answeredCount` / `draftAnsweredCount` 两个口径统一成一个 |
| `correctCount` / `wrongCount` | Integer | 【无变更】 | 写作主观题**恒 `null`**（HSK 无客观判分） |
| `draft` | Object | 【修改】 | 原 `draftAttemptId` / `draftAnsweredCount` / `draftCurrentQuestionId` → `{id, answeredCount, currentQuestionId}` |
| `report` | Object | 【修改】 | 原 `latestAttemptId` / `latestReportId` / `feedbackStatus` / `hasReport` → `{id, hasReport, status}`；`status` 取 `feedbackStatus`（`PENDING` / `READY` / `FAILED` / `UNAVAILABLE`） |
| `stats` | Object | 【新增】 | 写作恒 `null` |

**服务端内部执行顺序**

1. 登录、`version`
2. 查卷 → **`PracticeLevelCode.parseDbLevel(paper.getLevel())`**，`"7-9"` 不再抛 `NumberFormatException`（B-03）
3. 板块骨架 + 开关分流 + 现算题量
4. 按 `section` 查 `writing_attempt` 草稿与最近报告

**本接口抛出错误码**：400 / 401 / 404

---

#### A14 `GET /speaking/levels`

**用途**：口语模块「当前等级概览 + 该等级全部卷的作答进度」（原「全部等级列表」）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `version` | query | String | 是 | 【新增】旧实现是代码常量 |
| `level` | query | String | 否 | 【新增】数字串：2.0 为 `"1"`–`"3"`（HSKK 初/中/高），3.0 为 `"3"`–`"7"`。不传取上次选择，再缺省该版本最低等级 |

**请求示例**

```http
GET /api/practice/speaking/levels?version=HSK2.0&level=3
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "3",
    "levelName": "HSKK 高级",
    "paperCount": 11,
    "papers": [
      { "paperId": 2095069502045491202, "paperCode": "H91000",
        "status": "in_progress", "completedCount": 2, "totalCount": 5 }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `level` | String | 【修改】 | 数字串（**原返回 `levelCode` + `databaseLevel` 两个字段**：前者是 `HSK7` 之类的错误拼接、后者是裸数值，本次收敛成一个数字串，显示名交给 `levelName`，见 §4.0.6 换算表） |
| `levelName` | String | 【无变更】 | 本地化名 |
| `paperCount` | Integer | 【新增】 | 该等级可练卷数 |
| `papers[]` | Array | 【新增】 | 原先由 A15 单独返回，现内嵌；**A15 已删除** |
| `papers[].paperId` | Long | 【无变更】 | **指向 `speaking_exam_paper.id`**，与 `exam_paper.id` 零交集 |
| `papers[].paperCode` | String | 【无变更】 | `speaking_exam_paper.source`（如 `H91000`） |
| `papers[].status` | String | 【修改】 | **大写改小写** |
| `papers[].completedCount` / `totalCount` | Integer | 【修改】 | 原 `completedCount` 保留语义（已完成题数）；`totalCount` = 卷内题数（现算，排除 `enabled_prac=0`） |
| ~~`levelId` / `databaseLevel` / `enabled` / `abilityDescription` / `sections[]`~~ | — | 【删除】 | `levelId` / `databaseLevel` 是内部值；`enabled` 与 `level_config.enabled` 重复；`abilityDescription` 与 `parts` 挪到 A14b `/intro` |
| ~~`papers[].recordedCount` / `scoredCount`~~ | — | 【删除】 | 录音 / 评分统计移到板块页 `parts[].stats`（卷列表只显示一条进度） |

**关键改动**：**2.0 与 3.0 口语内容都读 `speaking_exam_paper`**（旧 ADR「3.0 读 `exam_paper`」是错的）。`question` 里 `SEC_SPEAKING` 的 5 条是造数残留，不读。

**服务端内部执行顺序**

1. 登录 → `version`
2. 解析 `level` 数字串 → 2.0 走 `1/2/3 ↔ Beginner/Intermediate/Advanced` 换算（§4.0.6），3.0 直接按数字串查 `speaking_exam_paper.level`
3. `practice_module_level_config`：`version + level(数值) + SEC_SPEAK + deleted=0`；内存判 `enabled`
4. 查 `speaking_exam_paper`：`version=? AND level IN (候选) AND deleted=0 AND enabled_prac=1`
5. 现算题量（`speaking_exam_paper_question`，`number>0`、`enabled_prac=1`），`totalCount=0` 剔除
6. 带 `userId` 批量查 `speaking_attempt` 填进度

**本接口抛出错误码**：400 / 401

---

#### A14b `GET /speaking/levels/{level}/intro`

**用途**：口语单等级备考说明
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `level` | path | String | 是 | 值域同 A14（数字串）；2.0 传 `1`/`2`/`3` |
| `version` | query | String | 是 | 【新增】 |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "3",
    "levelName": "HSKK 高级",
    "abilityDescription": "能就复杂话题进行连贯表达",
    "abilityDescriptionEn": "Can express coherently on complex topics",
    "abilityDescriptionVi": "Có thể diễn đạt mạch lạc về các chủ đề phức tạp",
    "totalQuestionCount": 5,
    "durationMinutes": 24,
    "parts": [
      { "partCode": "PART_1", "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeCode": "applied_read_speak", "typeName": "应用读说", "typeNameEn": "Apply and read aloud",
        "typeNameVi": "Đọc và nói ứng dụng", "questionCount": 1, "sortOrder": 1, "layouts": ["record"],
        "durationMinutes": 5 }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `level` / `levelName` | String | 【新增】 | 与 A14 同义 |
| `abilityDescription` × 3 | String | 【修改】 | 原单语 → 三语同发 |
| `durationMinutes` | Integer | 【修改】 | 原 `suggestedDurationMinutes` **改名**（注意口语原字段是 `suggested*`，阅读是 `suggest*`，两者都收敛到 `durationMinutes`） |
| `parts[]` | Array | 【修改】 | 原 `sections[]` 改名；**`partCode` 保持 `PART_1` 形态**，同时给 `section=1`；**口语板块独有的 `durationMinutes`**（板块级时长）放在 Part 内 |
| `parts[].questionCount` | Integer | 【修改】 | **口语取题改按 `part_config.type_code`**，不再用 `PartCodeCase` 硬编码 8 个题型；`listen_retell` / `applied_read_speak` / `listen_material_answer` / `viewpoint_express` 等新题型从此能取到题（B-19） |

**本接口抛出错误码**：400 / 401 / 404

---

#### A15 `GET /speaking/papers` 【已删除，并入 A14】

| 项 | 结论 |
|---|---|
| 端点 | **删除** |
| 原因 | 卷列表由 `GET /speaking/levels?version=&level=` 的 `papers[]` 一并返回（§4.0.6 规定 2） |
| 前端动作 | `GET /speaking/papers?level=7&version=HSK3.0` → `GET /speaking/levels?level=7&version=HSK3.0`，取 `data.papers` |
| 字段变化 | `levelCode` 删（等级在 `data.level` 上一层）、`paperName` 删、`totalQuestionCount` → `totalCount`、`recordedCount`/`scoredCount` 移到 `parts[].stats`、`status` 改小写 |

---

#### A16 `GET /speaking/papers/{paperId}/parts`

**用途**：口语某张卷的板块列表 + 录音 / 评分进度
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `paperId` | path | Long | 是 | 【无变更】`speaking_exam_paper.id` |
| `version` | query | String | 是 | 【新增】 |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "paperId": 2095069502045491202,
    "paperCode": "H91000",
    "parts": [
      { "partCode": "PART_3", "section": 3, "partName": "第三部分", "partNameEn": "Part 3", "partNameVi": "Phần 3",
        "typeCode": "viewpoint_express", "typeName": "观点表达", "typeNameEn": "Expressing Viewpoints",
        "typeNameVi": "Thể hiện quan điểm", "questionCount": 1, "sortOrder": 3, "layouts": ["record"],
        "durationMinutes": 5,
        "status": "in_progress", "doneCount": 1, "correctCount": null, "wrongCount": null,
        "draft": { "id": 6620, "answeredCount": 1, "currentQuestionId": 92001 },
        "report": { "id": 8801, "hasReport": true, "status": "READY" },
        "stats": { "recordedCount": 1, "scoredCount": 1, "unansweredCount": 0, "failedCount": 0 } }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `paperId` / `paperCode` | — | 【新增】 | 外层从裸数组改对象包裹（§4.0.6 规定 1） |
| `structureId` | Long | 【删除】 | 改 `section` |
| `partCode` | String | 【无变更】 | **`PART_1` / `PART_2` / `PART_3` 形态不变** |
| `durationMinutes` | Integer | 【修改】 | 原 `suggestedDurationMinutes` 改名（口语独有的板块级时长） |
| `status` / `doneCount` | — | 【新增】 | 通用进度字段（`doneCount` = 已录音题数） |
| `correctCount` / `wrongCount` | Integer | 【无变更】 | 口语恒 `null`（无客观判分） |
| `draft` | Object | 【修改】 | 原 `draftAttemptId` / `draftCurrentQuestionId` → `{id, answeredCount, currentQuestionId}` |
| `report` | Object | 【修改】 | 原 `latestAttemptId` / `latestReportId` / `reportStatus` → `{id, hasReport, status}` |
| `stats` | Object | 【修改】 | 原平铺 `recordedCount` / `scoredCount` / `unansweredCount` / `failedCount` → 收敛为 `stats` 块（口语是唯一有该块的模块） |

**服务端内部执行顺序**

1. 登录、`version`
2. 查 `speaking_exam_paper`：`id=? AND deleted=0 AND enabled_prac=1`
3. 板块骨架来自 `practice_module_part_config`（`section_mapping='SEC_SPEAK'`），**不再按硬编码题型白名单**
4. 取题：`speaking_exam_paper_question WHERE paper_id=? AND deleted=0 AND enabled_prac=1 AND number>0 AND question_type_mapping = <该板块 type_code>`
5. 按 `section` 查 `speaking_attempt` 草稿与报告

> ⚠️ 口语的 `paperId` 域与其它三个模块**不重叠**：`speaking_attempt.paper_id` 指向 `speaking_exam_paper.id`。前端不要把听力/阅读的 `paperId` 传进来，会返回 404。

**本接口抛出错误码**：400 / 401 / 404

---

### 4.2 翻译模块（B 组：9 个新增 + 1 个删除）

#### 翻译模块的实测数据基线（TEST，2026-11-10）

| 项 | 值 |
|---|---|
| 版本 / 等级 | 仅 `HSK3.0` / `HSK7-9`（DB `level='7'`） |
| 卷 | **1 张**：`paperId=2104188199979532289`，`source='HSK7-9_1'` |
| 板块 | **2 个**：`section=1` 笔译 `translation_written`（2 题）、`section=2` 口译 `translation_oral`（2 题） |
| 总题数 | 4 |
| 2.0 | 无任何翻译数据 → 目录接口返回 `[]` / 空对象 |

> 2.0 不报 404 是**有意设计**：前端据「空数组」把翻译卡置灰，不需要额外判版本。

---

#### B1 `GET /translation/levels`

**用途**：翻译模块「当前等级概览 + 该等级全部卷的作答进度」
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `version` | query | String | 是 | 【新增】`HSK2.0` → `paperCount=0` + `papers=[]` |
| `level` | query | String | 否 | 【新增】仅 `HSK7-9`（本期唯一等级）。不传按 `HSK7-9` 处理；传其它值 → 空结果（不 404） |

**请求示例**

```http
GET /api/practice/translation/levels?version=HSK3.0&level=7
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "7",
    "levelName": "HSK 7-9",
    "paperCount": 1,
    "papers": [
      { "paperId": 2104188199979532289, "paperCode": "HSK7-9_1",
        "status": "not_started", "completedCount": 0, "totalCount": 4 }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| `level` / `levelName` | String | 等级编码 + 本地化名（§4.0.6） |
| `paperCount` | Integer | 该等级可练卷数（`totalCount=0` 剔除） |
| `papers[]` | Array | 与 A4/A10/A14 完全同构 |
| `papers[].status` | String | `not_started` / `in_progress` / `completed` |
| `papers[].completedCount` / `totalCount` | Integer | 只统计 `SEC_TRANSLATION` 的题（`totalCount` 现算） |

> 原实现返「等级数组 + `sections[]`」，现改为与听力同构的单等级概览；能力描述与板块结构挪到 B2。

**服务端内部执行顺序**

1. 登录 → `version`。`HSK2.0` **直接返回 `paperCount=0` + `papers=[]`**，不查库
2. 解析 `level`（非 `HSK7-9` → 空结果）
3. 查 `practice_module_level_config`：`version + level + SEC_TRANSLATION + deleted=0`，内存判 `enabled`
4. 查卷：`version=? AND level IN (候选集) AND exam_type=1 AND deleted=0 AND enabled_prac=1`
5. 现算 `SEC_TRANSLATION` 题量，`totalCount=0` 剔除
6. 批量查 `writing_attempt`（翻译复用写作链路）填充进度

**本接口抛出错误码**：400 / 401

---

#### B2 `GET /translation/levels/{level}/intro`

**用途**：翻译单等级备考说明
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `level` | path | String | 是 | `HSK7-9`（本期唯一） |
| `version` | query | String | 是 | 【新增】 |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "level": "7",
    "levelName": "HSK 7-9",
    "abilityDescription": "能准确理解并进行中英互译",
    "abilityDescriptionEn": "Can understand accurately and translate between Chinese and English",
    "abilityDescriptionVi": "Có thể hiểu chính xác và dịch giữa tiếng Trung và tiếng Anh",
    "totalQuestionCount": 4,
    "durationMinutes": 30,
    "parts": [
      { "partCode": "1", "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeCode": "translation_written", "typeName": "笔译", "typeNameEn": "Written Translation",
        "typeNameVi": "Biên dịch viết", "questionCount": 2, "sortOrder": 1, "layouts": ["input"] },
      { "partCode": "2", "section": 2, "partName": "第二部分", "partNameEn": "Part 2", "partNameVi": "Phần 2",
        "typeCode": "translation_oral", "typeName": "口译", "typeNameEn": "Oral Interpretation",
        "typeNameVi": "Phiên dịch nói", "questionCount": 2, "sortOrder": 2, "layouts": ["record"] }
    ]
  }
}
```

**返回字段说明**：与 A5/A11/A14b 完全同构。2.0 → **返回空对象**（`level` 保留回显，其余字段 `null` / `[]`），**不 404**——前端据「`totalQuestionCount == null` 或 `parts` 为空」显示空态。

**本接口抛出错误码**：400 / 401 / 404

---

#### B3 `GET /translation/papers` 【已删除，并入 B1】

| 项 | 结论 |
|---|---|
| 端点 | **删除** |
| 原因 | 卷列表由 `GET /translation/levels?version=&level=` 的 `papers[]` 一并返回（§4.0.6 规定 2） |
| 前端动作 | `GET /translation/papers?level=7&version=HSK3.0` → `GET /translation/levels?level=7&version=HSK3.0`，取 `data.papers` |
| 字段变化 | `paperName` 删、`totalQuestionCount` → `totalCount`、`completedQuestionCount` → `completedCount`、`status` 改小写 |

---

#### B4 `GET /translation/papers/{paperId}/parts`

**用途**：翻译某张卷的板块列表（笔译 / 口译两张卡）
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `paperId` | path | Long | 是 | 【无变更】 |
| `version` | query | String | 是 | 【新增】卷 `version` 不符 → 404 |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "paperId": 2104188199979532289,
    "paperCode": "HSK7-9_1",
    "parts": [
      { "partCode": "1", "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeCode": "translation_written", "typeName": "笔译", "typeNameEn": "Written Translation",
        "typeNameVi": "Biên dịch viết", "questionCount": 2, "sortOrder": 1, "layouts": ["input"],
        "status": "not_started", "doneCount": 0, "correctCount": null, "wrongCount": null,
        "draft": null, "report": null, "stats": null },
      { "partCode": "2", "section": 2, "partName": "第二部分", "partNameEn": "Part 2", "partNameVi": "Phần 2",
        "typeCode": "translation_oral", "typeName": "口译", "typeNameEn": "Oral Interpretation",
        "typeNameVi": "Phiên dịch nói", "questionCount": 2, "sortOrder": 2, "layouts": ["record"],
        "status": "not_started", "doneCount": 0, "correctCount": null, "wrongCount": null,
        "draft": null, "report": null, "stats": null }
    ]
  }
}
```

**返回字段说明**：与 A13 完全同构（`WritingPartResponse` 复用）+ §4.0.6 的对象包裹。**前端按 `layouts` 渲染两张卡**（答题形式看 `layouts`，不看 `typeCode`，§4.0.5）：

| `layouts` | `typeCode` | 卡片 | 作答交互 |
|---|---|---|---|
| `["input"]` | `translation_written` | 笔译 | 文本输入 |
| `["record"]` | `translation_oral` | 口译 | 录音上传 |

> `typeCode` 用来显示题型名（「笔译」/「口译」），`layouts` 用来决定渲染哪个作答组件。两者在翻译这 4 题上恰好一一对应，但**判断分支要写在 `layouts` 上**——`typeCode` 是可扩展的（以后加题型不必改前端渲染分支）。

**服务端内部执行顺序**

1. 登录、`version`
2. 查卷：`id=? AND version=? AND exam_type=1 AND deleted=0 AND enabled_prac=1`，不满足 → 404
3. 板块来自 `practice_module_part_config`（`SEC_TRANSLATION`）
4. 现算题量
5. 按 `section` 查 `writing_attempt` 草稿与报告

**本接口抛出错误码**：400 / 401 / 404

---

#### B5 `POST /translation/attempts/start`

**用途**：开始翻译练习（新建或复用草稿）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `paperId` | body | Long | 是 | 【新增】 |
| `section` | body | Integer | 是 | 【新增】**替代原 `structureId`** |
| `X-Client-Type` | header | String | 否 | 【无变更】 |

**请求示例**

```json
{ "paperId": 2104188199979532289, "section": 1 }
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "attemptId": 5512,
    "paperId": 2104188199979532289,
    "section": 1,
    "sectionMapping": "SEC_TRANSLATION",
    "level": "7",
    "status": "IN_PROGRESS",
    "feedbackStatus": "PENDING",
    "currentQuestionId": 91001,
    "currentQuestionNumber": 1,
    "answerVersion": 0,
    "totalQuestions": 2,
    "answeredCount": 0,
    "accumulatedActiveSeconds": 0,
    "resumeElapsedSeconds": 0,
    "readingSeconds": 0,
    "writingSeconds": 0,
    "sourceViewCount": 0,
    "syllabusVersion": "HSK3.0",
    "paperVersion": "v1",
    "sectionVersion": "v1",
    "questionSetVersion": "qs-20261110-01",
    "restored": false
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `attemptId` | Long | 【新增】 | `writing_attempt.id`（翻译复用写作链路） |
| `paperId` | Long | 【新增】 | |
| `structureId` | Long | 【删除】 | **原写作接口有此字段，翻译版直接改为 `section`** |
| `section` | Integer | 【新增】 | 板块号 |
| `sectionMapping` | String | 【新增】 | 翻译恒为 `SEC_TRANSLATION` |
| `level` / `status` / `feedbackStatus` | — | 【新增】 | `level` 是等级编码（与目录接口同义）；`status` 本次仍是**大写**（作答链路，见 §10 第 17 条） |
| `currentQuestionId` / `currentQuestionNumber` / `answerVersion` | — | 【新增】 | 续练定位 |
| `totalQuestions` / `answeredCount` | Integer | 【新增】 | |
| `accumulatedActiveSeconds` / `resumeElapsedSeconds` / `readingSeconds` / `writingSeconds` / `sourceViewCount` | Integer | 【新增】 | 计时统计 |
| `syllabusVersion` / `paperVersion` / `sectionVersion` / `questionSetVersion` | String | 【新增】 | 版本快照，交卷时校验 |
| `restored` | Boolean | 【新增】 | 是否复用了已有草稿（幂等命中） |

**服务端内部执行顺序**

1. 校验登录（委托 `requireAuthenticatedAppUserId`）
2. **前置归属校验**：`question` 里 `(paperId, section)` 的 `section_mapping` 必须为 `SEC_TRANSLATION`
   ```sql
   SELECT DISTINCT section_mapping FROM question
   WHERE paper_id = ? AND deleted = 0 AND enabled_prac = 1 AND CAST(section AS SIGNED) = ?;
   ```
   - 返回空集 → **404**（板块不可练，题被逐题下架或不存在）
   - 返回非 `SEC_TRANSLATION` → **400 `SECTION_MAPPING_MISMATCH`**
3. 委托 `WritingAttemptServiceImpl#start`
   - `requirePaper`：卷有效 + `exam_type=1` + **`enabled_prac=1`** + `level ≥ 3`
   - `validatePart`：`contentType ∈ {SEC_WRITE, SEC_TRANSLATION}` 且 `== sectionMapping`（**本次放宽，否则翻译开不了练习**）
   - 已有 `IN_PROGRESS` → 直接返回（`restored=true`）
   - 新建 attempt，快照 `section_mapping` / `section` / `paperVersion` / `questionSetVersion`

**本接口抛出错误码**：400 / 401 / 404

---

#### B6 `GET /translation/attempts/{attemptId}`

**用途**：查询练习详情（续练 / 断点恢复）
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `attemptId` | path | Long | 是 | |
| `section` | query | Integer | 否 | 【新增】传则校验 attempt 归属该板块 |

**返回**：结构同 B5（`WritingAttemptResponse`）。字段标记全部【新增】。

**服务端内部执行顺序**：登录 → 校验 attempt 属于当前用户（否则 404）→ 若传 `section` 则校验一致 → 组装计时与进度

**本接口抛出错误码**：401 / 404

---

#### B7 `GET /translation/attempts/{attemptId}/questions`

**用途**：取本次练习的题目快照
**鉴权**：需要登录

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": [
    { "questionId": 91001, "questionNumber": 1, "questionType": "translation_written",
      "layout": "input", "evaluationMode": "AI", "contentVersion": "v1", "policyVersion": "p1",
      "data": { "stem": "把下面的句子翻译成英文……", "sourceText": "…", "targetLanguage": "en" } },
    { "questionId": 91002, "questionNumber": 2, "questionType": "translation_oral",
      "layout": "record", "evaluationMode": "AI", "contentVersion": "v1", "policyVersion": "p1",
      "data": { "stem": "听音频后口头翻译……", "sourceText": "…", "targetLanguage": "en",
                "recordingRules": { "maxSeconds": 90 } } }
  ]
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `questionId` | Long | 【新增】 | |
| `questionNumber` | Integer | 【新增】 | 板块内题号，从 1 开始 |
| `questionType` | String | 【新增】 | 等于 `typeCode`（`translation_written` / `translation_oral`），**表业务语义，不表交互** |
| `layout` | String | 【新增】 | **答题形式，直取 `question.layout` 原样透传**（§4.0.5）。翻译实测只有两个值：`input`（笔译，2 题）/ `record`（口译，2 题）。前端按它选渲染组件，**不要按 `questionType` 判断** |
| `evaluationMode` | String | 【新增】 | `AI` / `RULE` / `NONE` |
| `contentVersion` / `policyVersion` | String | 【新增】 | 内容与评分策略版本 |
| `data` | Object | 【新增】 | **题目内容原始结构，字段随题型变化**（题干 / 原文 / 目标语言 / 参考要点等），前端按 `layout` 决定取哪些字段渲染 |

**服务端内部执行顺序**：登录 → 校验 attempt 归属 → 按 attempt 快照的 `question_ids`（或三元组）取题（`deleted=0 AND enabled_prac=1`）→ 组装

> ⚠️ 已开练的 attempt 用**快照**取题，不重新过滤 `enabled_prac`；`enabled_prac` 只影响**新开**练习。这条是 R13，改错会导致历史报告少题。

**本接口抛出错误码**：401 / 404

---

#### B8 `PUT /translation/attempts/{attemptId}/answers`

**用途**：批量保存答案（含自动保存）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `deviceId` | body | String | 否 | 【新增】设备标识 |
| `baseVersion` | body | Long | 是 | 【新增】客户端手上的 `answerVersion`，用于乐观锁 |
| `clientSequence` | body | Long | 否 | 【新增】客户端递增序号 |
| `clientUpdatedAt` | body | Long | 否 | 【新增】客户端时间戳（毫秒） |
| `lastQuestionId` | body | Long | 否 | 【新增】最后停留题目，用于续练定位 |
| `answers[].questionId` | body | Long | 是 | 【新增】 |
| `answers[].answerType` | body | String | 是 | 【新增】笔译 `TEXT` / 口译 `AUDIO` |
| `answers[].answer` | body | Object | 是 | 【新增】答案体，`TEXT` 传 `{text}`，`AUDIO` 传 `{url, durationMs}` |

**请求示例**

```json
{
  "deviceId": "ios-abc",
  "baseVersion": 3,
  "clientSequence": 7,
  "clientUpdatedAt": 1762773900000,
  "lastQuestionId": 91002,
  "answers": [
    { "questionId": 91001, "answerType": "TEXT", "answer": { "text": "The meeting has been postponed." } }
  ]
}
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "attemptId": 5512,
    "serverVersion": 4,
    "updatedTime": 1762773901000,
    "answeredCount": 1,
    "currentQuestionId": 91002,
    "idempotent": false,
    "answers": [
      { "questionId": 91001, "answerType": "TEXT",
        "answer": { "text": "The meeting has been postponed." }, "answered": true,
        "graphemeCount": 33, "matchedKeywords": null, "serverVersion": 4,
        "lastModifiedTime": 1762773901000 }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `attemptId` / `serverVersion` / `updatedTime` | — | 【新增】 | `serverVersion` 供下次 `baseVersion` |
| `answeredCount` / `currentQuestionId` | — | 【新增】 | |
| `idempotent` | Boolean | 【新增】 | 是否命中幂等（重复提交同一批答案） |
| `answers[]` | Array | 【新增】 | `graphemeCount` 为字符数（笔译计字），`matchedKeywords` 为命中关键词 |

**本接口抛出错误码**：400（`baseVersion` 冲突）/ 401 / 404 / 409（版本冲突需走 `conflicts/resolve`）

---

#### B9 `POST /translation/attempts/{attemptId}/submissions`

**用途**：交卷并触发评分
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `Idempotency-Key` | header | String | **是** | 【新增】幂等键，重复提交同一 key 返回同一结果 |
| `expectedAnswerVersion` | body | Long | 是 | 【新增】期望的答案版本，不一致 → 409 |
| `questionSetVersion` | body | String | 是 | 【新增】开练时拿到的题目集合版本 |

**请求示例**

```json
{ "expectedAnswerVersion": 4, "questionSetVersion": "qs-20261110-01" }
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "attemptId": 5512,
    "reportId": 7712,
    "evaluationStatus": "PENDING",
    "feedbackStatus": "UNAVAILABLE",
    "feedbackLanguage": "zh",
    "completedCount": 2,
    "totalCount": 2
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `attemptId` / `reportId` | Long | 【新增】 | `reportId` 立即返回，报告可能仍在生成 |
| `evaluationStatus` | String | 【新增】 | `PENDING` / `READY` / `FAILED` |
| `feedbackStatus` | String | 【新增】 | **翻译 P0 恒为 `UNAVAILABLE`**（`writing_evaluation_policy` 缺 `TRANSLATION_WRITTEN` 策略，见 D5）。报告结构与状态正常返回，只是 `score` 为 `null` |
| `feedbackLanguage` | String | 【新增】 | 取自 `Accept-Language` |
| `completedCount` / `totalCount` | Integer | 【新增】 | 已答 / 总题数 |

**服务端内部执行顺序**

1. 登录 → 校验 attempt 归属
2. 校验 `expectedAnswerVersion == attempt.answerVersion`，不等 → 409
3. 校验 `questionSetVersion`，不等 → 409
4. 委托 `WritingSubmissionService#submit`，事务内：写 `writing_submission` → 更新 attempt 状态 → 创建 `writing_report`（`status=PENDING`）
5. P0 **不入队评分**：先查 `writing_evaluation_policy`，无策略直接置 `feedbackStatus=UNAVAILABLE` 返回

**本接口抛出错误码**：400 / 401 / 404 / 409

---

#### B10 `GET /translation/reports/{reportId}`

**用途**：获取翻译练习报告
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `reportId` | path | Long | 是 | |

**返回完整示例（P0，无评分策略）**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "reportId": 7712,
    "attemptId": 5512,
    "paperId": 2104188199979532289,
    "section": 1,
    "evaluationStatus": "READY",
    "feedbackStatus": "UNAVAILABLE",
    "feedbackLanguage": "zh",
    "score": null,
    "maxScore": null,
    "scorePercent": null,
    "answeredCount": 2,
    "totalQuestions": 2,
    "completionPercent": 100.00,
    "objectiveCorrectCount": null,
    "objectiveWrongCount": null,
    "objectiveUnansweredCount": null,
    "objectiveAccuracyPercent": null,
    "subjectiveFullScoreCount": null,
    "subjectiveImprovementCount": null,
    "subjectiveUnansweredCount": null,
    "accumulatedActiveSeconds": 620,
    "readingSeconds": 180,
    "writingSeconds": 440,
    "sourceViewCount": 2,
    "submittedTime": 1762773901000,
    "generatedTime": 1762773905000,
    "aiUnlocked": false,
    "questions": []
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `reportId` / `attemptId` / `paperId` | Long | 【新增】 | |
| `structureId` | Long | 【删除】 | 改 `section` |
| `section` | Integer | 【新增】 | |
| `evaluationStatus` | String | 【新增】 | |
| `feedbackStatus` | String | 【新增】 | P0 翻译恒 `UNAVAILABLE` |
| `score` / `maxScore` / `scorePercent` | BigDecimal | 【新增】 | P0 全 `null` |
| `completionPercent` / `objectiveAccuracyPercent` | BigDecimal | 【新增】 | |
| `objective*` / `subjective*` 系列 | Integer | 【新增】 | 客观题统计（翻译无客观题，全 `null`）；主观题分档统计 |
| `accumulatedActiveSeconds` / `readingSeconds` / `writingSeconds` / `sourceViewCount` | Integer | 【新增】 | 计时统计 |
| `submittedTime` / `generatedTime` | Long | 【新增】 | 毫秒时间戳 |
| `aiUnlocked` | Boolean | 【新增】 | AI 点评是否解锁 |
| `questions[]` | Array | 【新增】 | 逐题明细（`WritingReportItemResponse`）。P0 无评分时为空数组 |

**本接口抛出错误码**：401 / 404

---

### 4.3 板块最近报告（C 组，4 个路径改造）

四个模块的这个接口**只改路径与定位方式**，响应结构除 `structureId → section` 外不变。

| 模块 | 旧路径（删除） | 新路径 |
|---|---|---|
| 听力 | `GET /listening/parts/{structureId}/reports/latest` | `GET /listening/papers/{paperId}/parts/{section}/reports/latest` |
| 阅读 | `GET /reading/parts/{structureId}/reports/latest` | `GET /reading/papers/{paperId}/parts/{section}/reports/latest` |
| 写作 | `GET /writing/parts/{structureId}/reports/latest` | `GET /writing/papers/{paperId}/parts/{section}/reports/latest` |
| 口语 | `GET /speaking/parts/{structureId}/reports/latest` | `GET /speaking/papers/{paperId}/parts/{section}/reports/latest` |

> 旧路径**直接删除，不保留兼容**。前端必须与后端同批上线。

#### C1 `GET /listening/papers/{paperId}/parts/{section}/reports/latest`

**用途**：查某卷某板块最近一次已出报告的摘要
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `paperId` | path | Long | 是 | 【新增】 |
| `section` | path | Integer | 是 | 【新增】替代 `structureId` |
| `version` | query | String | 否 | 【新增】建议传，用于卷归属校验 |

**请求示例**

```http
GET /api/practice/listening/papers/2104193520701620225/parts/1/reports/latest?version=HSK2.0
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 88100,
    "reportId": 7710,
    "reportStatus": "READY",
    "totalQuestions": 5,
    "answeredCount": 5,
    "correctCount": 4,
    "wrongCount": 1,
    "accuracyRate": 80,
    "durationSeconds": 320
  }
}
```

**返回字段说明**：全部【无变更】。`data` 为 `null` 表示该板块还没有报告（**不报 404**）。

**服务端内部执行顺序**：登录 → 按 `(paperId, section)` 定位 `practice_record`（三元组）→ 取最近一条已出报告的记录 → 组装

**本接口抛出错误码**：401 / 404（卷不存在或不属于当前版本）

---

#### C2 `GET /reading/papers/{paperId}/parts/{section}/reports/latest`

**用途**：阅读板块最近报告
**鉴权**：需要登录

入参同 C1。

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "reportId": 7810, "recordId": 88200, "paperId": 2104193520701620226,
    "section": 1, "status": 2, "reportStatus": "READY",
    "totalQuestionCount": 10, "answeredCount": 10, "correctCount": 8, "wrongCount": 2,
    "accuracyRate": 80.00, "durationSeconds": 600, "submittedTime": 1762773901000,
    "items": []
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `reportId` / `recordId` / `paperId` | Long | 【无变更】 | |
| `structureId` | Long | 【删除】 | 改 `section` |
| `section` | Integer | 【新增】 | |
| `status` | Integer | 【无变更】 | 数值状态码（历史字段，与 `reportStatus` 并存） |
| `reportStatus` | String | 【无变更】 | `PENDING` / `READY` / `FAILED` |
| `totalQuestionCount` / `answeredCount` / `correctCount` / `wrongCount` | Integer | 【无变更】 | |
| `accuracyRate` | BigDecimal | 【无变更】 | 正确率百分比 |
| `durationSeconds` / `submittedTime` | — | 【无变更】 | |
| `items[]` | Array | 【无变更】 | 逐题明细，本接口通常为空数组 |

**本接口抛出错误码**：401 / 404

---

#### C3 `GET /writing/papers/{paperId}/parts/{section}/reports/latest`

**用途**：写作板块最近报告状态
**鉴权**：需要登录

入参同 C1。

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "reportId": 7712, "attemptId": 5500, "paperId": 2104193520701620227,
    "section": 1, "evaluationStatus": "READY", "feedbackStatus": "READY",
    "feedbackLanguage": "zh", "completedCount": 1, "totalCount": 1,
    "progressPercent": 100, "etag": "W/\"a1b2c3\"", "updatedTime": 1762773905000,
    "aiUnlocked": true
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| `reportId` / `attemptId` / `paperId` | Long | 【无变更】 | |
| `structureId` | Long | 【删除】 | 改 `section` |
| `section` | Integer | 【新增】 | |
| `evaluationStatus` / `feedbackStatus` / `feedbackLanguage` | String | 【无变更】 | |
| `completedCount` / `totalCount` / `progressPercent` | Integer | 【无变更】 | |
| `etag` | String | 【无变更】 | 与 `If-None-Match` 配合，命中可返 304 |
| `updatedTime` / `aiUnlocked` | — | 【无变更】 | |

**本接口抛出错误码**：401 / 404

---

#### C4 `GET /speaking/papers/{paperId}/parts/{section}/reports/latest`

**用途**：口语板块最近报告状态
**鉴权**：需要登录

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `paperId` | path | Long | 是 | 【新增】**`speaking_exam_paper.id`**，不是 `exam_paper.id` |
| `section` | path | Integer | 是 | 【新增】替代 `structureId`（原值是 `PART_N` 语义） |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "reportId": 8801, "attemptId": 6600, "status": "READY",
    "scoredCount": 1, "unansweredCount": 0, "failedCount": 0,
    "aiUnlocked": true, "failureCode": null, "readyAt": 1762773905000
  }
}
```

**返回字段说明**：`structureId` 【删除】，改 `section`；其余全部【无变更】。

> ⚠️ 口语的 `paper_id` 域与其它三个模块**不重叠**：`speaking_attempt.paper_id` 指向 `speaking_exam_paper.id`。前端不要把听力/阅读的 `paperId` 传进来，会返回 404。

**本接口抛出错误码**：401 / 404

---

### 4.4 运营端板块配置（D 组，2 个新增）

> 仅供后台管理端使用，C 端 App 不调用。**运营只能改 `enabled` / `sort_order`，不能建行、不能删行**——删行等于回到「未配置」，会被兜底逻辑重新放出来（§4.0.4）。

#### D1 `GET /hsk/module-config/parts`

**用途**：按版本 + 等级 + 模块查板块配置（运营页表格）
**鉴权**：需要登录（后台账号）

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `version` | query | String | 是 | `HSK2.0` / `HSK3.0` |
| `level` | query | Integer | 是 | 数值等级，`HSK7-9` 传 `7` |
| `sectionMapping` | query | String | 是 | `SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` / `SEC_TRANSLATION` / `SEC_SPEAK` |

**请求示例**

```http
GET /api/practice/hsk/module-config/parts?version=HSK3.0&level=7&sectionMapping=SEC_TRANSLATION
Authorization: Bearer xxx
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": [
    { "id": 24791, "version": "HSK3.0", "level": 7, "sectionMapping": "SEC_TRANSLATION",
      "section": 1, "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
      "typeCode": "translation_written", "typeName": "笔译",
      "typeNameEn": "Written Translation", "typeNameVi": "Biên dịch viết",
      "standardQuestionCount": 2, "actualQuestionCount": 2,
      "sortOrder": 1, "enabled": 1, "deleted": 0, "updatedTime": 1762773900000 },
    { "id": 24792, "version": "HSK3.0", "level": 7, "sectionMapping": "SEC_TRANSLATION",
      "section": 2, "partName": "第二部分", "partNameEn": "Part 2", "partNameVi": "Phần 2",
      "typeCode": "translation_oral", "typeName": "口译",
      "typeNameEn": "Oral Interpretation", "typeNameVi": "Phiên dịch nói",
      "standardQuestionCount": 2, "actualQuestionCount": 2,
      "sortOrder": 2, "enabled": 1, "deleted": 0, "updatedTime": 1762773900000 }
  ]
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Long | 配置行 ID，`PATCH` 时用 |
| `version` / `level` / `sectionMapping` / `section` | — | 唯一键四元组 |
| `partName` × 3 / `typeName` × 3 | String | 三语名称 |
| `typeCode` | String | 题型编码 |
| `standardQuestionCount` | Integer | 配置的标准题量 |
| `actualQuestionCount` | Integer | **现算的实际题量**（排除 `enabled_prac=0` 与 `example_question`），供运营判断配置是否失真 |
| `sortOrder` | Integer | 展示顺序 |
| `enabled` | Integer | `1` 开放 / `0` 关闭——**运营要改的就是它** |
| `deleted` | Integer | 逻辑删除。正常恒为 `0`，非 `0` 说明是脏数据 |
| `updatedTime` | Long | 最后修改时间（毫秒） |

**关键约定**：本接口**必须返回 `enabled=0` 的行**。若只返回 `enabled=1`，运营将看不到自己关掉的板块，也就无法重新打开。

**服务端内部执行顺序**：登录 → 校验后台权限 → 按四元组查 `practice_module_part_config`（**不带 `enabled` / `deleted` 过滤**，`deleted<>0` 的行标记后返回）→ 现算 `actualQuestionCount` → 按 `sort_order` 排序

**本接口抛出错误码**：400 / 401 / 403

---

#### D2 `PATCH /hsk/module-config/parts/{id}`

**用途**：开关单个板块 / 调整展示顺序
**鉴权**：需要登录（后台账号）

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `id` | path | Long | 是 | 配置行 ID |
| `enabled` | body | Integer | 否 | `0` / `1`。**至少传 `enabled` 或 `sortOrder` 之一** |
| `sortOrder` | body | Integer | 否 | 展示顺序 |

**请求示例**

```json
{ "enabled": 0 }
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "id": 24792, "version": "HSK3.0", "level": 7, "sectionMapping": "SEC_TRANSLATION",
    "section": 2, "partName": "第二部分", "typeCode": "translation_oral",
    "enabled": 0, "sortOrder": 2, "updatedTime": 1762773910000
  }
}
```

**返回字段说明**：与 D1 单行结构一致，至少含 `id` / `enabled` / `sortOrder` / `updatedTime`。

**服务端内部执行顺序**

1. 登录 → 校验后台权限
2. 按 `id` 查行，不存在 → 404
3. 校验 `enabled ∈ {0,1}`，非法 → 400
4. `UPDATE ... SET enabled=?, sort_order=?, updated_time=? WHERE id=?`（**只更新传入的字段**，`deleted` 一律不动）
5. 返回更新后的行

**边界与约束**

- 幂等：重复置同一个值不报错，返回同样结果
- **不提供批量接口**（本期不做批量上下架）
- 关闭板块不影响历史记录：已存在的 `question_ids` 快照仍可回看、出报告
- 关闭后新开练习该板块消失；若该板块题量本就为 0，关闭与开启在目录上都看不到，属正常

**本接口抛出错误码**：400 / 401 / 403 / 404

---

### 4.5 首页聚合（E 组，1 个新增）

#### E1 `GET /hsk/modules`

**用途**：首页一次拿到「版本 → 布局 → 模块卡」，避免前端串行发 5 个请求
**鉴权**：不需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| `version` | query | String | 是 | `HSK2.0` → 4 卡 `GRID_2`；`HSK3.0` → 5 卡 `LIST` |

**请求示例**

```http
GET /api/practice/hsk/modules?version=HSK3.0
Accept-Language: zh
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "version": "HSK3.0",
    "layout": "LIST",
    "header": "专项突破 · 听力/阅读/写作/翻译/口语",
    "modules": [
      { "moduleCode": "LISTENING", "sectionMapping": "SEC_LISTEN",
        "name": "听力", "nameEn": "Listening", "nameVi": "Nghe",
        "sortOrder": 1
     },
      { "moduleCode": "READING", "sectionMapping": "SEC_READ",
        "name": "阅读", "nameEn": "Reading", "nameVi": "Đọc",
        "sortOrder": 2
     },
      { "moduleCode": "WRITING", "sectionMapping": "SEC_WRITE",
        "name": "写作", "nameEn": "Writing", "nameVi": "Viết",
        "sortOrder": 3
     },
      { "moduleCode": "TRANSLATION", "sectionMapping": "SEC_TRANSLATION",
        "name": "翻译", "nameEn": "Translation", "nameVi": "Dịch",
        "sortOrder": 4
     },
      { "moduleCode": "SPEAKING", "sectionMapping": "SEC_SPEAK",
        "name": "口语", "nameEn": "Speaking", "nameVi": "Nói",
        "sortOrder": 5
     }
    ]
  }
}
```

2.0 只有四张卡，`layout` 换成 `GRID_2`（除 `layout` 与卡表外结构完全相同）：

```json
{ "version": "HSK2.0", "layout": "GRID_2", "header": "专项突破 · 听力/阅读/写作/口语",
  "modules": [
    { "moduleCode": "LISTENING",   "sectionMapping": "SEC_LISTEN", "sortOrder": 1 },
    { "moduleCode": "READING",     "sectionMapping": "SEC_READ",   "sortOrder": 2 },
    { "moduleCode": "WRITING",     "sectionMapping": "SEC_WRITE",  "sortOrder": 3 },
    { "moduleCode": "SPEAKING",    "sectionMapping": "SEC_SPEAK",  "sortOrder": 4 }
  ] }
```

**返回字段说明**

| 字段                                     | 类型      | 说明                                                                                              |
| -------------------------------------- | ------- | ----------------------------------------------------------------------------------------------- |
| `version`                              | String  | 回显解析后的版本                                                                                        |
| `layout`                               | String  | `GRID_2`（2.0）/ `LIST`（3.0）。**前端据此切换布局，不写死**（服务端取自 `sys_dict.remark`）                            |
| `header`                               | String  | 首页副标题，按 `Accept-Language` 本地化                                                                   |
| `modules[].moduleCode`                 | String  | `LISTENING` / `READING` / `WRITING` / `TRANSLATION` / `SPEAKING`（← `sys_dict_item.description`） |
| `modules[].sectionMapping`             | String  | `SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` / `SEC_TRANSLATION` / `SEC_SPEAK`（← `item_value`）       |
| `modules[].name` / `nameEn` / `nameVi` | String  | 三语模块名：`name` ← `item_text`，`nameEn`/`nameVi` ← `item_properties`                                |
| `modules[].sortOrder`                  | Integer | 卡片顺序                                                                                            |

**模块卡取自字典表（不写死常量）**

模块清单存在 `sys_dict` / `sys_dict_item`（TEST 已铺 9 项，见 §9.3）：

| 版本 | `dict_code` | 项数 | 布局 |
|---|---|---|---|
| HSK2.0 | `hsk_practice_module_v2` | 4 | `GRID_2` |
| HSK3.0 | `hsk_practice_module_v3` | 5 | `LIST` |

字段映射（**一列一义，不再往 JSON 里塞展示资产**）：

| `sys_dict_item` 列 | 对应响应字段              | 说明                                                               |
| ----------------- | ------------------- | ---------------------------------------------------------------- |
| `item_text`       | `name`              | 中文名（听力 / 阅读 / 写作 / 口语 / 翻译）                                      |
| `item_value`      | `sectionMapping`    | `SEC_xxx`，接口拿它查 `practice_module_level_config` 与内容表              |
| `description`     | `moduleCode`        | `LISTENING` / `READING` / `WRITING` / `SPEAKING` / `TRANSLATION` |
| `sort_order`      | `sortOrder`         | 卡片顺序                                                             |
| `item_properties` | `nameEn` / `nameVi` | JSON，**只有 `nameEn` / `nameVi` 两个键**                              |

**`available` 判定规则**

```
available = 存在 enabled=1 的 level_config 行
            AND 至少一个等级下存在 enabled_prac=1 且题量>0 的卷
```

**服务端内部执行顺序**（SQL ≤ 5 次，与模块数无关）

1. 解析 `version` → 非法 400
2. 取模块元数据（**字典表** `hsk_practice_module_v2` / `_v3`，按 `sort_order` 排序；`layout` 取 `sys_dict.remark`）
3. 批量查 `practice_module_level_config` 得各模块可用等级
4. 批量查 `exam_paper` + `question` 统计 `totalPapers`（题量为 0 的卷剔除）
5. 带 `userId` 时批量查进行中 / 已完成记录
6. 按 `sortOrder` 返回

**降级**：单个模块查询异常 → 该卡 `available=false` + `disabledReason=LOAD_FAILED`，**不要 500 整页**。

**本接口抛出错误码**：400 / 401

---

## 5. 错误码更新

沿用 `BusinessException(code, message)`（`code` 为 HTTP 语义码）。**新增错误码只在新增端点使用，存量端点文案不动**。

| HTTP | code / message | 服务 | 场景 |
|---|---|---|---|
| 400 | `PRACTICE_VERSION_INVALID` | practice-service | `version` 不在白名单【新增】 |
| 400 | `SECTION_MAPPING_MISMATCH` | practice-service | `(paperId, section)` 的实际模块不属于该接口【新增】 |
| 400 | `PART_CONFIG_INVALID` | practice-service | `PATCH` 传的 `enabled` 不是 0/1【新增】 |
| 404 | `TRANSLATION_NOT_IN_VERSION` | practice-service | 2.0 调翻译写链路（**目录接口返回空 papers 不报错**）【新增】 |
| 404 | 沿用各模块文案 | practice-service | `paperId` 的 version 与入参不符 / 卷已下架 / 板块不可练【修改】旧实现部分场景返回 500 |
| 403 | `NO_ADMIN_PERMISSION` | practice-service | 运营端接口非后台账号【新增】 |
| 409 | `ANSWER_VERSION_CONFLICT` | practice-service | 交卷时 `expectedAnswerVersion` 或 `questionSetVersion` 不一致【新增，沿用写作链路】 |
| 409 | `TRANSLATION_NOT_SCORABLE` | practice-service | 翻译交卷但无评分策略。**P0 不报错**，仅 P1 使用 |

> `code: 500` + HTTP 200 的组合是**路由未注册**的典型特征（日志里是 `NoResourceFoundException`），排查方向是新建 `TranslationController` / `HskModuleController` / `ModuleConfigController` 是否已注册到网关路由，而不是业务逻辑。

---

## 6. 前端对接注意事项

### 6.1 破坏性变更（必须同批上线）

| # | 变更 | 影响面 | 前端动作 |
|---|---|---|---|
| 1 | `parts[].structureId` **删除** | 听力/阅读/写作/口语/翻译的 parts 接口 | 全部改用 `parts[].section`；所有作答 start、报告查询的入参同步改 |
| 2 | `questionType` → `typeCode`，`questionTypeName` → `typeName` | 阅读/写作/口语的 parts 与 intro | 字段改名，值不变。建议全局替换后回归一遍 |
| 3 | 报告 latest 路径变更 | 4 个模块 | `/{module}/parts/{structureId}/reports/latest` → `/{module}/papers/{paperId}/parts/{section}/reports/latest` |
| 4 | 所有目录接口必须传 `version` | 全部 | 首页切换版本时清理本地缓存的 `level` / 卷列表 / 滚动位置 |
| **5** | **4 个 `/papers` 端点删除** | 阅读 / 写作 / 口语 / 翻译 | 卷列表改从 `/{mod}/levels` 的 `data.papers` 取。**接口 404，没有兼容层** |
| **6** | **`/levels` 从数组改单对象** | 阅读 / 写作 / 口语 / 翻译 | 原 `data: [ {level…} ]` → `data: { level, levelName, paperCount, papers[] }`。**不再一次返回全部等级**，等级 chip 由前端按版本矩阵渲染（§4.0.6） |
| **7** | **`sections[]` → `parts[]`；`suggestDurationMinutes` → `durationMinutes`** | 阅读 / 写作 / 口语 / 翻译 | 字段改名，值不变 |
| **8** | **卷状态枚举统一小写** | 阅读 / 写作 / 口语 / 翻译 | `NOT_STARTED` → `not_started` 等。全局替换后再全局搜一遍大写残留 |
| **9** | **`/parts` 外层加对象包裹，进度字段收敛** | 全部 5 个模块 | `data: [part…]` → `data: { paperId, paperCode, parts: [...] }`；`draftRecordId`/`draftAttemptId` → `draft.id`；`hasReport`/`latestRecordId`/`latestReportId`/`feedbackStatus`/`reportStatus` → `report.*`；口语 4 个计数 → `stats.*` |
| **10** | **数值等级字段删除** | 阅读 / 写作 / 口语 / 翻译 | `level`（数值）/ `levelCode` / `databaseLevel` / `levelId` 全部不再下发，只用 `level`（**数字串**）+ `levelName`（显示名） |

> 第 5–10 条是**本轮新增的破坏性变更**（三跳对齐），与 1–4 一起构成「前端必须同批上线」的完整清单。**没有灰度通道**：任一条漏改都会导致白屏或空列表。

### 6.2 兼容性说明

1. `partCode` **值域不变**（口语仍是 `PART_1/2/3`，其它仍是 `"1"/"2"`），本地如有按 `partCode` 的分支逻辑不受影响
2. 新增字段（`section`、三语、`sortOrder`、`levelName`）对旧客户端是**增量**，但 `structureId` 的删除、`/papers` 的删除、`/levels` 的数组→对象都是**硬破坏**，不可灰度
3. `questionCount` 改为现算，数值可能与旧的配置值不同（生产库存在 `total_question_count` 与板块求和不一致的情况，差异 E13）。**不要在前端做「进度条 = completedCount / 旧的固定值」的硬编码**
4. **状态枚举已统一为小写**（`not_started` / `in_progress` / `completed`），5 个模块一致，前端不再需要「按模块分别处理」（原文档此处写「本期不统一」，已作废）
5. `paperId` 仍是 `Long`（19 位），JSON 里会有精度风险。`/hsk/modules` 的 `inProgressPaperId` 已改 String，其余接口 P1 再改；**过渡期前端必须用字符串接收或配置 JS 的 bigint 处理**
6. 翻译 P0 交卷后 `report.status = UNAVAILABLE`、`score = null` 是**预期行为**，不是 bug。前端应展示「暂无评分」而不是「生成中」或错误页
7. **`draft` / `report` / `stats` 三块可能为 `null`**，前端按「块是否为 null」判断，不要判内部字段是否为空——因为 `draft.answeredCount = 0` 与「没有草稿」是两件事

### 6.3 渲染约定

| 场景 | 规则 |
|---|---|
| **答题形式** | **只看 `layout`**（题目接口）与 `layouts`（板块接口），原样值不换算。`typeCode` 只用于显示题型名与选择评分策略 |
| 翻译两张卡 | 按 `parts[].layouts` 区分：`["input"]` → 文本输入；`["record"]` → 录音 |
| 三语切换 | `parts[]` 三语同发，前端本地切换无需重新请求；`abilityDescription` / `levelName` / `header` 仍随 `Accept-Language` |
| 模块卡片置灰 | `available=false` 时置灰 + Toast 提示，**不要隐藏卡片**（保持 5 卡/4 卡布局稳定），`disabledReason` 映射文案 |
| 版本切换 | 清空已选 `level`、卷列表、滚动位置、本地「上次练习」。**不要复用旧 `level` 打新版本接口**：2.0 的 `HSK1` 在 3.0 下虽存在但卷集合不同；`HSK7-9` 在 2.0 下返回空结果 |
| 等级切换 | 三跳下「等级 chip」与「卷列表」在同一屏：点 chip 只重拉 `/{mod}/levels?level=`，**不要重拉整页** |
| `questionCount = 0` | 该板块不会下发，前端不需要处理空板块 |
| `layouts` 有多个值 | 说明该板块混了两种交互（TEST 有 2 个板块、PROD 有 48 个）。前端按题渲染即可，**不要在板块层强制选一种** |
| 口语 `stats` | 只有口语的 `parts[].stats` 非 `null`，展示「已录音 x / 已评分 y / 失败 z」 |

---

## 7. 关键业务流程 & 事务边界

### 7.1 板块装配（所有目录接口共用，只读、无事务）

```
解析 version + level
  → 查 level_config（version + section_mapping + enabled=1 + deleted=0）
      └ 空 → 返回空 parts（模块整体关闭，短路，不再往下）
  → 查 part_config（version + level + section_mapping，**不带 enabled 条件**）
      ├ enabled=1 AND deleted=0 → 骨架，按 sort_order 排序
      ├ enabled=0 AND deleted=0 → closedSections（该 section 一律不下发，且不参与兜底）
      └ deleted=1              → 丢弃
  → 现算题量（question：deleted=0 AND enabled_prac=1，排除 example_question）
      ├ 覆盖 standard_question_count
      └ 结果 0 → 该板块不下发（R6）
  → 兜底：question 里出现、但骨架与 closedSections 都没有的 section
      → 命名「第N部分」，视为开放，记 WARN 日志
```

**两条不能反的约束**：

1. **part_config 查询不能带 `enabled=1`**。带上会把「关闭」误判成「未配置」，兜底逻辑又把板块放出来，开关直接失效。
2. **`deleted = 1` 与「行不存在」不是一回事**。前者是模板行删除（丢弃），后者是未配置（兜底开放）。

### 7.2 翻译开始练习（事务边界在写作链路内）

```
POST /translation/attempts/start {paperId, section}
 → 校验登录
 → 【前置】question 里 (paperId, section) 的 section_mapping
     ├ 空集 → 404
     └ ≠ SEC_TRANSLATION → 400 SECTION_MAPPING_MISMATCH
 → 委托 WritingAttemptServiceImpl#start   ← 事务从这里开始
     ├ requirePaper：exam_paper.deleted=0 AND enabled_prac=1 AND exam_type=1 AND level ≥ 3
     ├ validatePart：contentType ∈ {SEC_WRITE, SEC_TRANSLATION} 且 == sectionMapping
     ├ 已有 IN_PROGRESS → 直接返回（restored=true，幂等）
     └ 新建 writing_attempt，快照 section_mapping / section / paperVersion / questionSetVersion
 → 返回 attemptId
```

**唯一侵入存量代码的点**是 `validatePart` 的 `contentType` 白名单：从 `{SEC_WRITE}` 放宽到 `{SEC_WRITE, SEC_TRANSLATION}`。不加这条，翻译**根本开不了练习**。这一处必须和「翻译目录独立」成对评审。

### 7.3 交卷（事务边界）

```
POST /translation/attempts/{attemptId}/submissions
 → 校验登录 + attempt 归属
 → 校验 expectedAnswerVersion == attempt.answerVersion  （不等 → 409）
 → 校验 questionSetVersion                              （不等 → 409）
 → 【事务开始】@Transactional(rollbackFor = Exception.class)
     ├ 写 writing_submission
     ├ 更新 writing_attempt.status = SUBMITTED
     └ 创建 writing_report（status = PENDING）
 → 【事务结束】
 → 查 writing_evaluation_policy
     ├ 有 TRANSLATION_WRITTEN 策略 → 入队评分（P1）
     └ 无 → 直接置 feedbackStatus = UNAVAILABLE，返回（P0 现状）
```

**顺序约束**：报告行必须在事务内创建（保证前端拿到的 `reportId` 一定存在）；评分入队必须在事务**外**（避免评分回调读不到未提交的数据）。

### 7.4 上下架的影响边界（最关键的一条）

| 动作 | 影响新练习 | 影响历史记录 |
|---|---|---|
| 卷下架（`exam_paper.enabled_prac=0`） | 列表消失、详情/开始作答 404 | **不影响**，已有记录仍可打开报告 |
| 板块关闭（`part_config.enabled=0`） | 该板块不下发 | **不影响**，`question_ids` 快照仍可回看（标注「已关闭」） |
| 单题下架（`question.enabled_prac=0`） | 题量现算时不计入 | **不影响**，快照里的题仍在 |

**禁止**把「关闭」实现成删题、改 `question.deleted`、或过滤历史快照——否则历史报告会凭空少题。已开练的 attempt 一律用快照取题，不重新过滤 `enabled_prac`。

---

## 8. 验收测试用例

### 版本隔离

| # | 场景 | 预期结果 |
|---|---|---|
| 1 | 不传 `version` | 按 `HSK2.0` 处理，`/hsk/modules` 返回 `layout=GRID_2`、**4 卡且不含翻译卡**（字典 v2 本就无 `SEC_TRANSLATION` 项） |
| 2 | `version=HSK3.0` | `layout=LIST`、5 卡；翻译在写作与口语之间（`sortOrder=4`）；**响应 `modules[]` 里不存在 `icon` / `theme` / `badge` / `entryLevelCode` 键**（前端按 `moduleCode` 内置） |
| 3 | `hsk3.0`（小写）/ `HSK4.0` | 400 `PRACTICE_VERSION_INVALID`，**不得静默降级** |
| 4 | `/reading/levels?version=HSK3.0&level=7` | **单对象**：`level=7`、`levelName=HSK 7-9`、`paperCount>0`、`papers[]` 非空；2.0 下传 `HSK7-9` → `paperCount=0` + `papers=[]`（**不 404**） |
| 5 | `/reading/levels?level=7&version=HSK3.0` 的 `papers[]` | 能查到卷（验证候选集）。⚠️ TEST 的 `level` 存 `'7'`，验不到 `'7-9'` 那条腿 → **必须补单测**：把 `level` 造为 `'7-9'` 仍能查到（差异 E11，最易漏） |
| 5a | 5 个模块的 `/levels`（带 `version`） | 返回 **`data` 是对象**（`level`/`levelName`/`paperCount`/`papers`），**不是数组**；缺省 `level` 时自动落到该版本最低可用等级 |
| 5b | 4 个已删端点 | `GET /reading/papers`、`/writing/papers`、`/speaking/papers`、`/translation/papers` 全部 404（路由不存在） |

### 破坏性变更

| # | 场景 | 预期结果 |
|---|---|---|
| 6 | 任一 parts 接口 | 响应里**不存在** `structureId`，存在 `section` |
| 6a | 任一 `/papers/{paperId}/parts` | `data` 是对象：`{ paperId, paperCode, parts[] }`，**不是数组**；`paperCode` 非空 |
| 6b | 任一 `parts[]` 元素 | 含 4 个通用进度字段 `status`/`doneCount`/`correctCount`/`wrongCount`，且**必有** `draft`/`report`/`stats` 三个键（无值为 `null`，不能缺键） |
| 6c | 无草稿的板块 | `draft` 为 `null`；`draft.answeredCount=0` 与「无草稿」不得混淆 |
| 7 | 旧路径 `/listening/parts/{structureId}/reports/latest` | 404（路由已删），不是 500 |
| 8 | 新路径 `/listening/papers/{paperId}/parts/{section}/reports/latest` | 200；无报告时 `data=null` |
| 9 | 阅读/写作/口语 parts | 字段为 `typeCode` / `typeName`，**没有** `questionType` / `questionTypeName` |
| 9a | 阅读/写作/口语/翻译的 `/levels` 与 `/intro` | **不存在** `levelCode` / `databaseLevel` / `levelId`；**不存在** `sections`、`suggestDurationMinutes` |
| 9b | 三个带「完成」语义的卷状态 | 5 个模块全部是小写 `not_started` / `in_progress` / `completed`，**没有**大写残留 |
| 10 | `parts[]` 三语 | `partNameEn` / `partNameVi` / `typeNameEn` / `typeNameVi` 全部非空 |
| 10a | 任一 parts 接口 | 每个板块都有 `layouts`，且非空数组 |
| 10b | 阅读 / 翻译取题接口 | 每道题都有 `layout`，值在 7 个规范值内；**阅读系本次新补字段** |
| 10c | 写作取题接口 | `layout` 直取 `question.layout`，**与 `type_id_mapping` 无耦合**：造一条 `type_id_mapping='chart_analysis'` + `layout='input'` 的题，能正常返回（B-04 回归） |
| 10d | 生产对齐后（差异 E6，本期不验） | `SEC_READ` / `SEC_WRITE` 的 `layout` 非空率回到 **100%**（现为 0% / 0%）；本期只验 TEST 的 100% |
| 10e | 混 `layouts` 的板块 | `layouts` 返回 2 个元素；前端逐题渲染不出错（TEST 有 2 个这样的板块） |

### 翻译独立

| # | 场景 | 预期结果 |
|---|---|---|
| 11 | 2.0 调 `/translation/levels` | 200，`paperCount=0` + `papers=[]`，**不 404** |
| 12 | 3.0 调 `/translation/levels?level=7` | `paperCount=1`；`papers[0].paperCode='HSK7-9_1'`、`totalCount=4` |
| 13 | `/translation/papers/{id}/parts` | `data.parts` 2 个板块：`translation_written`（`layouts=["input"]`）/ `translation_oral`（`layouts=["record"]`） |
| 13a | `/translation/papers`（已删） | 404 |
| 14 | 拿写作卷的 section 打翻译 start | 400 `SECTION_MAPPING_MISMATCH` |
| 15 | 拿翻译卷的 section 打写作 start | 404（写作侧不放宽） |
| 16 | 笔译交卷 | `reportId` 立即返回；报告 `feedbackStatus=UNAVAILABLE`、`score=null` |
| 17 | `/writing/papers/{id}/parts` | 不含翻译板块（回归） |
| 18 | 口译板块交卷 | 走 `AUDIO` 答案类型，成功入库 |
| 19 | 同一 `Idempotency-Key` 重复交卷 | 返回同一 `reportId`，不产生第二份报告 |

### 上下架

| # | 场景 | 预期结果 |
|---|---|---|
| 20 | `exam_paper.enabled_prac=0` 的卷 | 列表不出现、详情 404、开始作答 404（**三处都测**） |
| 21 | `question.enabled_prac=0` 的单题 | 目录题量 -1；答题时不出现在题目列表；其它板块不受影响 |
| 22 | 某板块全部题被单题下架 | 该板块因 `questionCount=0` 不下发，**不报错** |
| 23 | 🔴 `enabled_prac=1` + `enabled_exam=0` | **练习侧仍可见**（只关了考试） |
| 24 | 🔴 `enabled_prac=0` + `enabled_exam=1` | 练习侧不可见 |
| 25 | `practice-service` 全仓 grep `enabled_exam` | **零命中**（练习侧不得读考试开关） |

### 板块开关

| # | 场景 | 预期结果 |
|---|---|---|
| 26 | 关 `HSK2.0/L1/SEC_LISTEN/section=2` | 目录只剩其余板块，题量/名称/题型不受影响 |
| 27 | 关闭后新开练习 | 不含 `section=2` 的题；历史记录仍可打开、报告题数不变 |
| 28 | 关整模块 | 整卡消失，不再受板块开关影响（短路顺序） |
| 29 | 🔴 **区分「关闭」与「未配置」** | `enabled=0` → 板块**消失**；物理删行 → 板块**仍出现**且名为 `第N部分`。两条必须分别测 |
| 30 | `deleted=1` 的行 | 视同不存在：既不下发，也不参与兜底排重 |
| 31 | `PATCH` 把 `enabled` 改回 1 | 板块重新出现，名称/题量恢复 |
| 32 | 并发改同模块不同板块 | 两条都生效，无覆盖丢失 |
| 33 | `PATCH` 传 `enabled=2` | 400 `PART_CONFIG_INVALID` |

### 存量回归

| # | 场景 | 预期结果 |
|---|---|---|
| 34 | 2.0 四模块全链路（等级→卷→板块→答题→报告） | 除 §6.1 列明的破坏性变更（`structureId` 删、`/papers` 删、`/levels` 数组→对象、字段改名、状态小写、进度收敛）外，**与改造前逐字段一致** |
| 35 | `/listening/levels?level=1`（TEST） | 不混入 3.0 卷，`totalCount > 0` |
| 36 | TEST `/listening/levels/1/intro` | 不再 500 |
| 37 | `/writing/papers/{HSK7-9 卷}/parts` | 不再 500。⚠️ TEST 的 `level='7'` 走不到 `parseInt('7-9')` 分支，**须单测覆盖 `'7-9'`**（差异 E11） |
| 38 | 存量 `writing_attempt`（TEST 217） | 仍可打开续练（生产 284 条待生产对齐后回归，SDD 附录 D D.3） |
| 39 | 口语 3.0 L4/L5/L6 的 `listen_retell`、L7 的三个新题型 | **都能取到题**（B-19 回归判据） |
| 39a | 2.0 `/speaking/levels?level=3&version=HSK2.0` | `level=3`、`levelName=HSKK 高级`、`paperCount=11`；**不含** `levelCode` / `databaseLevel` |
| 39b | 2.0 `/speaking/levels` 不传 `level` | 缺省落到 `1`（`level_config.level=1`，`levelName=HSKK 初级`） |
| 39c | 3.0 `/speaking/levels?level=7` | 与听力/阅读同构（`level=7`），说明同一套解析在两种编码间不出错 |
| 40 | 源码 `grep -r structure_id` | 零命中；`practice_part_setting` / `practice_paper_structure` 已 drop |

---

## 9. 环境差异与上线事项

### 9.1 环境差异登记（生产 vs TEST）

> **本节只登记差异，不写生产改造方案。** 开发、联调、验收全部在 TEST 上做（TEST 现状见 §9.3）；将来上生产时照这张名单核对。每项的处置约束（例如「回填禁止按值映射」）见 SDD 附录 D。
> 编号与 SDD 附录 D 共用（E1–E15），此处只列**跟接口行为相关**的项。

**A. 结构差异（生产缺列 / 缺表 / 多列）**

| # | 项 | TEST（基线） | 生产 | 对本接口的影响 |
|---|---|---|---|---|
| E1 | `enabled_prac` / `enabled_exam` | 5 张内容表都有，取值全 `1` | **5 表全缺** | **生产部署前必须先加列**，否则启动即 `Unknown column 'enabled_prac'` |
| E2 | `practice_module_part_config` | 132 行，含 `enabled` | **表不存在** | 板块骨架全走兜底 → `partName` 退化成「第 N 部分」、`typeCode` 缺失（口语板块会取不到题） |
| E3 | `practice_module_level_config.parts_config` | 已 drop | 仍在 | 无（接口不再读该列） |
| E4 | 3.0 模块配置行 | 28 行 | **0 行** | 生产 3.0 首页五卡无数据 |
| E5 | `uk_module_part` 唯一键 | 仍缺（B-18） | — | 无（本期 TEST 侧补） |

**B. 数据差异（会改变接口返回值）**

| # | 项 | TEST | 生产 | 影响 |
|---|---|---|---|---|
| E6 | `question.layout` 非空率 | **100%** | **52.3%**（`SEC_READ` / `SEC_WRITE` 全空） | 生产近一半题 `layout = null`，前端判不了交互。只能按 `question.id` 从 TEST 复制，**禁止按值映射**（§4.0.5） |
| E7 | `layout` 值域 | 7 个规范值 | 老 8 值（混 `passageGroup` / `clozeGroup` 题面形态） | 前端会收到契约外的枚举值 |
| E9 | 「有卷但无 setting 行」的活卷 | 0 张 | **16 张**（2.0 L1 ×1 + 3.0 ×15） | 生产加列若用 `DEFAULT 1`，目录从 60 卷涨到 76 卷 → **必须同批置 0** |
| E10 | 3.0 卷上架 | 15/15 | **0/15** | 生产 3.0 目录为空（属运营放量，非缺陷） |
| E11 | `exam_paper.level`（HSK7-9） | `"7"` | `"7-9"` | **代码已兼容**：统一走 `IN ('7','7-9')` 候选集 |
| E13 | `total_question_count` vs 板块求和 | 46/46 一致 | 5/6（L2 听力 `35` ≠ `40`） | 无（`questionCount` 已改为现算） |
| E16 | 模块字典 `hsk_practice_module_v2` / `_v3` | 已建 9 项（1007 / 1008） | **0 项** | **生产不补则 `/hsk/modules` 返回空卡片列表**（不报错、首页空白）。🔴 `item_value` 必须填 `sectionMapping` 而非 `moduleCode`；`description` 才放 `moduleCode` |

> 结论：**接口契约只按 TEST 写**，生产差异不产生第二个分支。唯一进过代码的兼容点是 E11 的等级候选集。

### 9.1.1 TEST 侧待补（本期动作）

```sql
-- 补唯一键（先查重，必须 0 行；实测 132 行无重复）
SELECT version, level, section_mapping, section, COUNT(*) c
FROM practice_module_part_config
GROUP BY version, level, section_mapping, section HAVING c > 1;

ALTER TABLE practice_module_part_config
  ADD UNIQUE KEY `uk_module_part` (`version`,`level`,`section_mapping`,`section`) USING BTREE;
```

- `SEC_SPEAKING` 残留：删 1 行模块配置 + 3 行板块配置，`question` 里 5 条造数题软删（§10 第 6 条）。
- `question.layout`：TEST 已是 100% 填充，**本期不动**。

**任何环境动库都得过五闸门（含 TEST）**

| 闸门 | 动作 |
|---|---|
| G1 | 确认环境：`SELECT @@hostname` —— **测试与生产库名都叫 `xuexitest`，只能靠 hostname 区分** |
| G2 | 确认连接串指向预期的库 |
| G3 | 执行前备份受影响表（备份已存在则跳过，不覆盖） |
| G4 | DRY-RUN 先 `SELECT COUNT(*)` 统计将影响行数，与预期比对后再 `--apply` |
| G5 | 幂等：重复执行不产生脏数据、不重复改行 |

> 3.0 放量口径（运营，非本期）：把该版本 15 张卷的 `enabled_prac` 改回 `1`，**不是新增 setting 行**。

### 9.2 文件级变更清单

| 文件路径（practice-service） | 改动内容 |
|---|---|
| `core/support/PracticeVersion.java` | 新增：version 白名单解析，非法抛 400 |
| `core/support/PracticeLevelCode.java` | 新增：`HSK7-9` ↔ `7` 双向映射 + `dbLevels()` 候选集 |
| `core/support/PracticeModuleCatalog.java` | 新增：**从 `sys_dict` / `sys_dict_item` 载入模块元数据**（`hsk_practice_module_v2` / `_v3`），启动 + 定时刷新；`item_value` 与 `section_mapping` 不匹配时告警，不静默兜底 |
| `core/support/PracticeTypeRegistry.java` | 新增：`typeCode → 题型显示名 / 评分策略` 字典。**不再承担 `answerMode` 判定**——答题形式一律读 `question.layout`（§4.0.5） |
| `core/support/PracticeLayout.java` | 新增：`layout` 值域常量 + `isSubjective(layout)` 等轻量判定（`input` / `shortInput` / `record` 为主观）。**只判语义，不做值换算** |
| `core/support/SharedPaperEligibility.java` | **补判 `enabledPrac == 1`**（B-17，当前缺失 → 下架卷可直达） |
| `core/support/PracticeCatalogBatchLoader.java` | 删 setting 查询；板块骨架改读 `practice_module_part_config` |
| `listening/service/impl/ListeningCatalogServiceImpl.java` | `selectOne` 带 version；板块换源；`HSK7-9` 解析 |
| `reading/service/impl/ReadingCatalogServiceImpl.java` | 常量改参数；`level IN 候选集`；`parseDbLevel` |
| `writing/service/impl/WritingCatalogServiceImpl.java` | 常量改参数；`parseLevel` 扩到 `HSK7-9`；`introSections` 补 7 分支 |
| `speaking/service/impl/SpeakingCatalogServiceImpl.java` | 常量改参数；板块换源；取题改按 `type_code` |
| `speaking/mapper/SpeakingSourceQuestionMapper.xml` | **删 `PartCodeCase` 硬编码 8 题型**，改按 `part_config.type_code` 取题（B-19） |
| `translation/controller/TranslationCatalogController.java` | 新增 4 个目录端点（T1–T4） |
| `translation/controller/TranslationAttemptController.java` | 新增 6 个写链路端点（T5–T10），薄封装 |
| `translation/service/impl/TranslationCatalogServiceImpl.java` | 新增：`SEC_TRANSLATION` 目录装配 |
| `translation/support/TranslationPartGuard.java` | 新增：统一前置归属校验（返回空集 → 404，模块不符 → 400） |
| `writing/service/impl/WritingAttemptServiceImpl.java` | **`validatePart` 放宽 `contentType` 白名单**（唯一侵入点） |
| `writing/content/WritingQuestionNormalizer.java` | **`switch (getTypeIdMapping())` 改为读 `question.layout`**（§4.0.5）。现白名单只有 5 个老题型，3.0 的 `chart_analysis` / `topic_essay` 落 default → 直接挂（B-04） |
| `writing/content/WritingLayoutType.java` | 若保留枚举：补 `CHART_ANALYSIS` / `TOPIC_ESSAY`，并加 `fromLayout(String)`；否则整体退化为直接透传 `layout` 字符串 |
| `reading/dto/ReadingQuestionResponse.java` | **补 `layout` 字段**（直取 `question.getLayout()`）。当前只有 `typeId` / `typeIdMapping`，前端无据可判交互 |
| `speaking/dto/attempt/SpeakingQuestionResponse.java` | 补 `layout`；P0 恒 `record`（`speaking_exam_paper_question` 无该列） |
| `hsk/controller/HskModuleController.java` | 新增：`GET /hsk/modules` |
| `hsk/controller/ModuleConfigController.java` | 新增：`GET` / `PATCH /hsk/module-config/parts` |
| `listening/controller/ListeningReportController.java` | 路径 `parts/{structureId}` → `papers/{paperId}/parts/{section}` |
| `reading/controller/ReadingReportController.java` | 同上 |
| `writing/controller/WritingReportController.java` | 同上 |
| `speaking/controller/SpeakingReportController.java` | 同上 |
| `core/entity/PracticePaperStructure.java` / `PracticePartSetting.java` / `PracticePaperSetting.java` | **整文件删除** |
| `core/mapper/PracticePaperStructureMapper.java` / `PracticePartSettingMapper.java` / `PracticePaperSettingMapper.java` | **整文件删除** |

**其它服务（仅实体加字段，无逻辑改动，已完成）**：`exam-service` 与 `manage` 各 5 个实体加 `enabledPrac` / `enabledExam`。

### 9.3 TEST 现状（开发基线，已就绪）

| 项 | 状态 |
|---|---|
| 5 张内容表 `enabled_prac` / `enabled_exam` | ✅ 已加，取值全 `1` |
| `practice_module_part_config` | ✅ 已建 132 行 + `enabled` 列已加，三语 132/132 填充 |
| `practice_module_level_config.parts_config` | ✅ 已 drop |
| `question.layout` | ✅ 非空率 100%，7 个规范值 |
| **模块字典**（`/hsk/modules` 数据源） | ✅ 已铺 9 项：`hsk_practice_module_v2`（id 1007，4 项）/ `hsk_practice_module_v3`（id 1008，5 项）；`item_value` 全部命中 `practice_module_level_config`；`description` = `moduleCode`；`item_properties` = `{moduleCode,nameEn,nameVi}` |
| 代码侧 `enabled_prac` 过滤 | ✅ 已改完并编译通过 |
| 待补 | `uk_module_part` 唯一键；清 `SEC_SPEAKING` 残留 4 行（§9.1.1） |
| 生产库 | 差异见 §9.1，**本期不处理** |

---

## 10. 待确认事项

| # | 待确认点 | 暂定方案 | 确认人 |
|---|---|---|---|
| 1 | 板块级时长 / 满分 / 提示语是否入库 | 本期**不加列**，走 P1 同表加列；口语的 `suggestedDurationMinutes` 暂时沿用 `level_config` 的模块级时长 | 产品 |
| 2 | `paperId` 何时改 String | P0 保持 `Long`；仅 `/hsk/modules` 的 `inProgressPaperId` 用 String。P1 全量改（涉及所有目录与作答接口） | 前端 + 后端 |
| 3 | 翻译 P0 无评分的用户可见文案 | 报告页展示「暂无评分」，不展示「生成中」，不报错 | 产品 |
| 4 | 模块关闭时是否仍下发板块配置供前端置灰 | 暂定**不下发**（整卡消失）。若产品要「置灰但可点」，需后端在 `level_config.enabled=0` 时仍返回板块骨架 + `available=false` | 产品 |
| 5 | `practice_module_part_config` 唯一键何时补 | **本期补**（§9.1.1）：当前 132 行无重复，补键只防未来 | DBA |
| 6 | `SEC_SPEAKING` 残留配置清理 | 删 TEST 的 1 行模块配置 + 3 行板块配置；`question` 里 5 条造数软删（生产无此差异） | 运营 |
| 7 | `enabled_exam` 何时真正生效 | **当前有列无逻辑**：考试侧所有 SQL 未加 `enabled_exam = 1`。值全 1 时行为不变；要生效需另行接入 exam-service | 产品 + 后端 |
| 8 | 批量上下架是否本期做 | 不做。运营逐条 `PATCH` | 产品 |
| 9 | 生产 `layout` 对齐口径（差异 E6，本期不执行） | 已登记：**只能按 `question.id` 从 TEST 复制**（可覆盖 6439/6469），**禁止按值映射**（`textChoice` 一对多）；剩 30 行生产独有题人工判定（§4.0.5） | DBA + 运营 |
| 10 | 口语要不要补 `layout` 列 | P0 不补，口语恒 `record`，前端按模块写死。若要做「朗读 / 自由说话」差异化录音 UI，再给 `speaking_exam_paper_question` 加列（P1） | 产品 |
| 11 | `layout` 值域是否要收敛到跨模块统一枚举 | **不收敛，原样透传**（沿用 CSCA 既有约定）。7 个值已经是交互形态，换算只会多一层漏配 | 前端 + 后端 |
| 12 | 混 `layouts` 的板块（TEST 2 个 / 生产 48 个）如何处理 | 前端逐题渲染，不做板块级归一。若产品要求「一个板块一种交互」，那是**内容问题**（该板块题填错了 `layout`），回内容侧修，不改接口 | 产品 + 运营 |
| 13 | 老值域 `passageGroup` / `clozeGroup` 的语义（差异 E7） | 它们是**题面形态**不是答题形式（篇章组 / 完形组）。生产对齐时由 TEST 值覆盖；未被覆盖的 30 行若仍是这两个值，需人工判成 `choice` / `choiceGrid` | 运营 |
| 14 | **三跳后「全部等级列表」从哪里来** | P0：等级 chip 由前端按版本矩阵渲染；要显示各级能力描述就逐级调 `/intro`（6–7 个并发，可缓存 1 天）。若产品要求一次拿全，再加 `GET /{mod}/levels/all?version=`（只返 `level`/`levelName`/`abilityDescription×3`/`totalQuestionCount`，不含 `parts`），**不塞进 `/levels`**（否则又回到「单等级概览 vs 全等级列表」分叉） | 产品 + 前端 |
| 15 | **口语 2.0 的 `level` 编码** | 定数字串 `"1"`/`"2"`/`"3"`（= HSKK 初/中/高），与 `level_config.level` 一致；卷侧的 `Beginner/Intermediate/Advanced` 由 `PracticeLevelCode` 换算（§4.0.6）。`levelName` 按「模块 + 版本」取，2.0 显示「HSKK 初级」、3.0 的 `"3"` 显示「HSK 3」 | 产品 + 前端 |
| 16 | **`draft` / `report` / `stats` 三块的命名** | 现定义为 `{draft:{id,answeredCount,currentQuestionId}, report:{id,hasReport,status}, stats:{口语四项}}`。若前端更习惯把 `correctCount`/`wrongCount` 也放进 `report`，可整体调整——但**必须三块一起定**，不要一半平铺一半嵌套 | 前端 |
| 17 | **作答链路（B5–B10）的 `status` 是否也统一小写** | **本期不动**：`writing_attempt.status` / 报告状态仍是 `IN_PROGRESS` / `PENDING` / `READY`（DB 原值）。本次统一范围只到「目录三接口」（`/levels`、`/intro`、`/parts`）。P1 若统一，需要一次 DB 枚举迁移 + 前端全量替换，不建议与目录改造同批 | 后端 + 前端 |
