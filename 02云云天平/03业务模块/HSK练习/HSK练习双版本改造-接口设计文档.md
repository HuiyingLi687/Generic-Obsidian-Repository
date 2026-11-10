# HSK 练习双版本（2.0 / 3.0）与翻译模块拆分 · 接口设计文档

> 版本：v1.0｜更新日期：2026-11-10
> 影响服务：practice-service（改造 + 新增）；exam-service / manage 仅实体加字段
> 关联文档：[HSK练习双版本与翻译模块拆分-SDD](HSK练习双版本与翻译模块拆分-SDD.md)
> 开发：待填｜测试：待填｜前端：待填

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
| 5 | 板块字段来源 | `parts[]` 全部字段直取 `practice_module_part_config` 同名列，三语同发；**不下发 `answerMode`**（主客观由前端按 `typeCode` 判断） |
| 6 | 报告 latest 路径 | 旧 `/parts/{structureId}/reports/latest` **直接删除**，换 `/papers/{paperId}/parts/{section}/reports/latest`，不保留兼容 |
| 7 | 上下架口径 | 练习侧只读 `enabled_prac = 1`；`enabled`（板块）/ `exam_paper.enabled_prac`（卷）/ `question.enabled_prac`（题）三级独立，详见 SDD §3.4 |
| 8 | 板块开关 | `practice_module_part_config.enabled`：`1` 开放 / `0` 关闭。`deleted` 回到纯逻辑删除，不作开关 |
| 9 | 翻译版本门槛 | 翻译仅 `HSK3.0` 有数据。2.0 调目录接口返回**空数组 / 空对象**，不报 404 |
| 10 | 翻译作答复用写作链路 | 6 个写链路端点薄封装委托 `Writing*Service`，唯一侵入点是 `validatePart` 放宽 `contentType` 白名单 |

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
| `exam_paper` | 【新增】`enabled_prac tinyint NOT NULL DEFAULT 1`（练习侧上下架）、`enabled_exam tinyint NOT NULL DEFAULT 1`（考试侧）。原名 `deleted_prac`，**PROD 从未有过该列** |
| `question` | 【新增】同上两列。`question.enabled_prac` 为**题级上下架** |
| `question_group` | 【新增】同上两列（练习侧不单独判，材料随题走） |
| `speaking_exam_paper` | 【新增】同上两列 |
| `speaking_exam_paper_question` | 【新增】同上两列 |
| `practice_module_part_config` | 【新增】`enabled tinyint NOT NULL DEFAULT 1`（板块开关），位置在 `sort_order` 之后、`deleted` 之前。**仍缺唯一键** `uk_module_part (version, level, section_mapping, section)` |
| `practice_module_level_config` | 【删除】`parts_config` 列（板块配置已拉平成行式表）。TEST 已删，PROD 仍在 |
| `practice_paper_setting` | 【删除】整表 drop（卷级上下架由 `exam_paper.enabled_prac` 替代） |
| `practice_paper_structure` | 【删除】整表 drop |
| `practice_part_setting` | 【删除】整表 drop |
| `practice_record` | 【删除】`structure_id`、`practice_name`；【启用】`question_ids` 快照 |
| `practice_report` | 【删除】`structure_id` |
| `writing_attempt` | 【新增】`section_mapping`、`section` 两列（回填后删 `structure_id`） |
| `speaking_attempt` | 【新增】同上两列（`section_code` 是 `PART_1/2/3`，回填取 `SUBSTRING(section_code, 6)`） |

### 2.2 枚举与取值域更新

| 字段 | 值 | 含义 |
|---|---|---|
| `version` | `HSK2.0` / `HSK3.0` | 【修改】由代码常量改为请求参数，缺省 `HSK2.0` |
| `levelCode` | `HSK1`…`HSK6`、`HSK7-9` | 【修改】`HSK7-9` 是**一个**等级，数值 `7`；禁止 `HSK7` |
| `exam_paper.level`（DB） | TEST `"7"` / PROD `"7-9"` | 【无变更】查询必须用候选集 `IN ('7','7-9')` |
| `section` | `1`…`N` | 【新增】板块号，替代 `structureId` |
| `partCode` | `"1"`/`"2"`… 或 `PART_1`/`PART_2`/`PART_3` | 【无变更】口语带 `PART_` 前缀，其余纯数字串 |
| `enabled` / `enabled_prac` | `0` / `1` | 【新增】`1` 启用，`0` 关闭。正向布尔，不再是 `deleted_*` |
| `typeCode` | 见 SDD §3.2.2 | 【新增】`question.type_id_mapping` 稳定编码，如 `translation_written` / `translation_oral` |

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

| # | Method | Path | 用途 | 接口类型 | 改动简述 |
|---|---|---|---|---|---|
| A1 | GET | `/listening/levels` | 听力等级概览 + 卷列表 | 改造 | 加 `version`、补 `exam_type=1`、走 `enabled_prac` 判定 |
| A2 | GET | `/listening/levels/{levelCode}/intro` | 听力等级备考说明 | 改造 | `selectOne` 带 `version` + `deleted=0`；`parts[]` 三语 + `typeCode` |
| A3 | GET | `/listening/papers/{paperId}/parts` | 听力卷板块列表 | 改造 | 加 `version`；板块换源配置表；`structureId` → `section` |
| A4 | GET | `/reading/levels` | 阅读等级列表 | 改造 | 常量改 `version` 参数 |
| A5 | GET | `/reading/levels/{levelCode}/intro` | 阅读等级备考说明 | 改造 | `version` + `PracticeLevelCode` 解析；`sections[]` 三语 + `typeCode` |
| A6 | GET | `/reading/papers` | 阅读卷列表 | 改造 | `version` + `level IN (候选集)` |
| A7 | GET | `/reading/papers/{paperId}/parts` | 阅读卷板块列表 | 改造 | 卷 `version` 与入参不符 → 404；`structureId` → `section` |
| A8 | GET | `/reading/preferences` | 阅读偏好 | 无变更 | P0 不动（表无 `version` 列） |
| A9 | PUT | `/reading/preferences/level` | 更新阅读偏好 | 无变更 | P0 仅 2.0 可写 |
| A10 | GET | `/writing/levels` | 写作等级列表 | 改造 | 常量改参数；补 `HSK7-9` 分支 |
| A11 | GET | `/writing/levels/{levelCode}/intro` | 写作等级备考说明 | 改造 | `parseLevel` 正则扩到 `HSK7-9`；`sections[]` 三语 |
| A12 | GET | `/writing/papers` | 写作卷列表 | 改造 | 常量改参数 |
| A13 | GET | `/writing/papers/{paperId}/parts` | 写作卷板块列表 | 改造 | `parseDbLevel` 替代裸 `parseInt`；`structureId` → `section` |
| A14 | GET | `/speaking/levels` | 口语等级列表 | 改造 | 常量改参数 |
| A15 | GET | `/speaking/papers` | 口语卷列表 | 改造 | 常量改参数；2.0 / 3.0 都读 `speaking_exam_paper` |
| A16 | GET | `/speaking/papers/{paperId}/parts` | 口语卷板块列表 | 改造 | 板块换源配置表；`structureId` → `section` |
| B1 | GET | `/translation/levels` | 翻译等级列表 | 新增 | 2.0 → `[]` |
| B2 | GET | `/translation/levels/{levelCode}/intro` | 翻译等级备考说明 | 新增 | `sections[]` 来自板块配置 |
| B3 | GET | `/translation/papers` | 翻译卷列表 | 新增 | 过滤 `totalQuestionCount=0` |
| B4 | GET | `/translation/papers/{paperId}/parts` | 翻译卷板块列表 | 新增 | 2 个板块：笔译 / 口译 |
| B5 | POST | `/translation/attempts/start` | 开始翻译练习 | 新增 | 委托 `WritingAttemptService#start` |
| B6 | GET | `/translation/attempts/{attemptId}` | 练习详情 | 新增 | 委托 `#get` |
| B7 | GET | `/translation/attempts/{attemptId}/questions` | 题目列表 | 新增 | 委托 `#listQuestions` |
| B8 | PUT | `/translation/attempts/{attemptId}/answers` | 批量保存答案 | 新增 | 委托 `WritingAnswerService#save` |
| B9 | POST | `/translation/attempts/{attemptId}/submissions` | 交卷 | 新增 | 委托 `WritingSubmissionService#submit` |
| B10 | GET | `/translation/reports/{reportId}` | 报告详情 | 新增 | 委托 `WritingReportService#get` |
| C1 | GET | `/listening/papers/{paperId}/parts/{section}/reports/latest` | 听力板块最近报告 | 改造 | 路径 `structureId` → `paperId + section` |
| C2 | GET | `/reading/papers/{paperId}/parts/{section}/reports/latest` | 阅读板块最近报告 | 改造 | 同上 |
| C3 | GET | `/writing/papers/{paperId}/parts/{section}/reports/latest` | 写作板块最近报告 | 改造 | 同上 |
| C4 | GET | `/speaking/papers/{paperId}/parts/{section}/reports/latest` | 口语板块最近报告 | 改造 | 同上 |
| D1 | GET | `/hsk/module-config/parts` | 运营：查板块配置 | 新增 | 按 `version + level + sectionMapping` 查，**含 `enabled=0` 行** |
| D2 | PATCH | `/hsk/module-config/parts/{id}` | 运营：开关板块 | 新增 | 只改 `enabled`（可选 `sort_order`），不建行不删行 |
| E1 | GET | `/hsk/modules` | 首页模块卡聚合 | 新增 | 一次返回布局 + 卡片 + 可用性 + 进度 |

**统计**：改造 21（16 目录 + 4 报告路径 + 1 preferences 无变更计入清单不展开）、新增 12。

---
