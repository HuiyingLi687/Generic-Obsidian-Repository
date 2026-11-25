# HSK 练习 · 五模块接口合并（客观族 / 主观族）接口设计文档

> 版本：v2.5｜更新日期：2026-11-23
> 本版变更：§4.4 纳入首页模块卡 `GET /hsk/modules`（新增 §4.4.1，进目录前的入口，不算一跳），原小节顺移为 §4.4.2–§4.4.6；上版新增的第一跳 `GET /hsk/modules/{module}/levels` 现为 §4.4.2
> 上版变更（v2.4）：新增 `GET /hsk/modules/{module}/levels` 作为目录第一跳（模块 → 等级清单），原 `levels` / `parts` 顺移为第二、第三跳；`intro` 仍随目录展示，不算一跳
> 上版变更（v2.3）：删除开练请求的 `restart` 字段（不再提供重开机制）；主观族单题作答与判分重试改为三模块通用，`8120` 随之下线；客观报告结构收敛为「摘要 + 题号矩阵 `rows`」，不再下发 `items` / `reportStatus` / `retryable`；`baseVersion` 听读两模块都强校验；新增 §4.4 目录三跳与最近报告 4 个端点
> 影响服务：practice-service（改造，无 DDL 变更）
> 关联文档：《HSK练习五模块接口文档》（v1.x，按模块拆路径的旧版）
> 配套文件：`hsk-practice.http`（需按本文档同步路径与字段）
> 开发：—｜测试：—｜前端：—

## 改动标记约定

- 【新增】：本次迭代新增字段 / 端点 / 业务逻辑
- 【修改】：原有字段，修改命名、结构或约束
- 【无变更】：原有内容，本次迭代不做任何改动
- 【删除】：原有端点或字段，本次不再提供

## 0. 变更决策记录

| #   | 决策项  | 取值规则                                                                                                                                                   |
| --- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | 合并粒度 | 按**响应契约**分组，不按模块：听 + 读合成「客观族」，写 + 译 + 说合成「主观族」                                                                                                         |
| 2   | 路径形态 | 只保留两条前缀 `/hsk/objective/records/**`、`/hsk/subjective/records/**`，模块一律用 `?module=` 指定                                                                   |
| 3   | 旧路径  | **不再保留**：`/listening/records/**`、`/reading/records/**`、`/writing/records/**`、`/translation/records/**`、`/speaking/records/**` 全部下线，模块只能由 `?module=` 指定 |
| 4   | 选项结构 | 客观族统一扁平 `{"A":"文本","B":"文本"}`，不再有外层 `options` 包裹                                                                                                       |
| 5   | 题号字段 | 客观族统一 `number`（原听力叫 `no`）                                                                                                                              |
| 6   | 答案字段 | 客观族统一 `answer`（原听力叫 `selectedOptionId`），值为选项编码 A/B/C/D/E/F                                                                                             |
| 7   | 乐观锁  | `baseVersion` 统一**必传**，取自记录响应的 `version`；听读两个模块都强校验，不一致回 `8104`                                                                                        |
| 8   | 报告结构 | 交卷、查报告、重试返回**同一结构**：顶部摘要 + 题号矩阵 `rows`。`items` 不再下发，逐题明细走逐题回顾端点 |
| 9 | 报告状态 | 客观族不再返回 `reportStatus` / `retryable`：报告能不能看只取决于 `status = SUBMITTED` 与 `rows` 是否有值；重试前置条件是 `status = SUBMITTED` 且 `idempotency_key` 非空，否则 `8106` |
| 10 | 口语板块域 | `AnswerCardModule.SPEAKING` 的 `sectionMapping` 由拼写错误的历史值 `SEC_SPEAK` 改为 `SEC_SPEAKING`，校验时仍兼容旧值 |
| 11 | 内部实现 | 客观族保留两套 service（听力回 `question` 表、阅读读 `answer` 快照），门面层只做分派与 DTO 转换 |
| 12 | 开练语义 | `start` 只负责开新的练习：有未提交记录直接返回该记录，已提交后再调用则新建一次练习。不提供重开接口，未提交的继续练习走 `resume` |
| 13 | 模块级端点 | 主观族全部端点三模块通用，不再有「单题作答仅口语」「翻译无判分重试」这类限制，`8120` 随之删除 |
| 14 | 付费时机 | 交卷与评分都**不扣费**，改为用户在报告页主动解锁时按卷扣一次；顺序仍是免费次数 → AI 解析次数 → 考试点数，扣到一级即停 |
| 15 | 报告遮蔽 | 后端**不遮蔽**内容，报告与单题反馈统一返回 `aiUnlocked` 布尔标志，解析是否显示由前端控制 |
| 16 | 解锁落表 | 仍是 `practice_subjective_record` 单表：`ai_deduct_state`（`0` 未解锁 / `1` 已解锁 / `3` 无需解锁）+ `deduct_type` + `ai_deduct_time` |
| 17 | 解锁失败 | 扣减失败直接抛 `8118` 并回滚，本地不写解锁状态，用户付费后重试即可 |
| 18 | 答题卡 | 五模块同一响应：`questions[]` 只给 `order` / `questionId` / `answered` / `current`，不下发对错，也不做标记 / 收藏 / 错题筛选 |
| 19 | 首页、目录与最近报告 | 首页模块卡 `modules` 字典驱动、一次下发卡片；目录三跳（`modules/{module}/levels` / `levels` / `parts`）免登录、五模块同构；`modules` 是首页入口、`intro` 是目录内展示的等级说明，都不是一跳；最近报告需登录，`data` 按模块分形状，无报告回 `null` 不报 404 |

## 1. 现状问题列表（本次要修复的 bug）

| # | 问题描述 | 带来的后果 |
|---|---|---|
| 1 | 五模块链路骨架完全一致，但拆成 8 个控制器（听 3 / 读 3 / 写 1 / 译 1 / 说 1），其中写译说三份代码逐字相同、只有模块常量不同 | 同一段逻辑三处维护，改一处漏两处 |
| 2 | 听读两套 DTO 表达同一语义却字段名不同：题号 `no` / `number`，答案 `selectedOptionId` / `answer`，音频 `audio_url` / `audioUrl` | 前端要写两套解析器，字段名靠记忆区分 |
| 3 | 阅读选项下发 `{"options":{"A":"文本"}}`，听力下发 `{"A":"文本"}` | 同一个选项组件要兼容两种形状 |
| 4 | 听力交卷只回摘要、查报告才回矩阵；阅读两边都回完整明细 | 前端两套报告页渲染逻辑 |
| 5 | 听力报告状态是 `PROCESSING/FAILED_RETRYABLE/FAILED_FINAL`，阅读是 `PENDING/GENERATING/READY/FAILED` | 状态判断无法复用，`FAILED_FINAL` 前端从未处理过 |
| 6 | `AnswerCardModule.SPEAKING` 的板块域写成 `SEC_SPEAK`（拼写错误），与 `SubjectiveModule` 的 `SEC_SPEAKING` 不一致 | 两套枚举对同一模块给出不同值，合并前必须先收敛 |
| 7 | 记录响应不返回 `version` | 统一后的 `baseVersion` 没有取值来源 |
| 8 | `CscaFavoriteController` 类体缺少闭合大括号 | 全模块编译失败（本次已修复） |

## 2. 数据模型变更

### 2.1 数据表改动

**无 DDL 变更**。本次只改接口契约与服务端分派，数据表、快照字段、`section_mapping` 取值全部不动。

唯一涉及的取值口径修正：口语板块域的新写入统一为 `SEC_SPEAKING`，`SEC_SPEAK` 仅作为历史值被兼容读取（`practice_module_part_config` 存量 24 行、`practice_module_level_config` 存量 8 行未做数据订正，见 §10）。

**`ai_deduct_state` 取值口径**（列已存在，本次不新增列，只改写入时机）：

| 值 | 含义 | 写入时机 |
|---|---|---|
| `0` | 未解锁 | 创建记录时的默认值；卷内有 AI 题且用户还没付费 |
| `1` | 已解锁 | 用户调 `POST /{recordId}/unlock` 扣减成功 |
| `2` | 欠费 | 历史值，旧链路扣费失败留下的记录，读时按已解锁处理；当前链路不再写入 |
| `3` | 无需解锁 | 交卷时判定卷内没有可评分的 AI 题 |

`deduct_type` 与 `ai_deduct_time` 只在 `ai_deduct_state=1` 时有意义，分别为实际走通的扣减级别（`0` 免费次数 / `1` AI 解析次数 / `2` 考试点数）与解锁时间。

### 2.2 枚举更新

| 枚举 | 值 | 含义 |
|---|---|---|
| `ObjectiveModule`【新增】 | `listening` / `reading` | 客观族模块码，`module` 参数取值 |
| `SubjectiveModule` | `writing` / `translation` / `speaking` | 【无变更】主观族模块码，直接作为 `module` 参数取值 |
| `AnswerCardModule.SPEAKING.sectionMapping` | `SEC_SPEAKING`【修改】 | 原值 `SEC_SPEAK`（拼写错误）；校验时仍接受旧值 |
| `AiUnlockState`【新增】 | `LOCKED(0)` / `UNLOCKED(1)` / `OWED(2)` / `NOT_REQUIRED(3)` | 主观题 AI 解析的解锁状态，对应 `ai_deduct_state` |
| 记录状态【修改】 | `CREATED(0)` / `IN_PROGRESS(1)` / `ABANDONED(2)` / `SUBMITTED(3)` | 客观记录与主观记录共用这一套码值，落 `practice_record.status`、`practice_subjective_record.status`。库里存数字，出参返回枚举名 |
| 目录 / 板块进度【修改】 | `NOT_STARTED` / `IN_PROGRESS` / `COMPLETED` | 只有 `papers[].status` 与 `parts[].status` 用这一套，按草稿与报告现算，库里没有对应列 |

**记录状态码值（两族一致）**

| 状态 | 码值 | 客观记录 `practice_record.status` | 主观记录 `practice_subjective_record.status` |
|---|---|---|---|
| `CREATED` 创建中 | `0` | 记录已建、尚未作答 | 不出现（建记录即作答中） |
| `IN_PROGRESS` 作答中 | `1` | 有作答未交卷 | 建记录即此态 |
| `ABANDONED` 已放弃 | `2` | 超时、换卷、数据清理 | 同左 |
| `SUBMITTED` 已提交 | `3` | 已交卷 | 已交卷 |

> 两张记录表的码值完全相同，服务端判库按数字比较，只在拼装响应时换成枚举名。目录与板块进度是另一套三态，只出现在 §4.4.3 的 `papers[].status` 与 §4.4.5 的 `parts[].status`。

## 3. 接口总览清单

> 目录三跳（`/hsk/modules/{module}/levels`、`/hsk/levels`、`/hsk/papers/{paperId}/parts`）与随目录展示的等级说明 `/hsk/levels/{level}/intro`，以及首页模块卡 `/hsk/modules`，都不属于两族作答链路，见 §3.3 与 §4.4。

### 3.1 客观族（听 / 读）

前缀：`/hsk/objective/records`（唯一前缀，旧路径已下线）

| # | Method | Path | 用途 | 接口类型 | 改动简述 |
|---|---|---|---|---|---|
| 1 | POST | `{客观前缀}/start` | 开练 | 改造 | 请求体统一、删除 `restart`；`module` 必传 → §4.2.1 |
| 2 | GET | `{客观前缀}/{recordId}` | 记录详情 | 改造 | 响应加 `module` / `version`；`answers[]` 并集化 → §4.2.2 |
| 3 | POST | `{客观前缀}/{recordId}/pause` | 暂停 | 改造 | 请求体只留 `currentQuestionId`，两个模块都必传 → §4.2.3 |
| 4 | POST | `{客观前缀}/{recordId}/resume` | 恢复 | 改造 | 响应同记录详情 → §4.2.4 |
| 5 | GET | `{客观前缀}/{recordId}/questions` | 拉题 | 改造 | 题目响应统一字段名与选项结构 → §4.2.5 |
| 6 | PUT | `{客观前缀}/{recordId}/answers/{questionId}` | 单题保存 | 改造 | 答案字段 `selectedOptionId` → `answer`；`baseVersion` 必传并强校验 → §4.2.6 |
| 7 | PUT | `{客观前缀}/{recordId}/answers` | 批量保存 | 改造 | 同上；返回整条记录 → §4.2.7 |
| 8 | POST | `{客观前缀}/{recordId}/submit` | 交卷 | 改造 | 返回摘要 + 题号矩阵 `rows`，`items` 不再下发 → §4.2.8 |
| 9 | GET | `{客观前缀}/{recordId}/report` | 报告详情 | 改造 | 与交卷同一结构：摘要 + `rows` → §4.2.9 |
| 10 | GET | `{客观前缀}/{recordId}/report/questions/{questionId}` | 逐题回顾 | 改造 | 统一为「题目结构 + 判分字段」→ §4.2.10 |
| 11 | POST | `{客观前缀}/{recordId}/report/retry` | 报告重试 | 改造 | 前置 `status = SUBMITTED` 且幂等键非空（否则 `8106`）；返回摘要 + `rows` → §4.2.11 |
| 12 | GET | `{客观前缀}/{recordId}/answer-card` | 答题卡 | 改造 | 五模块同一响应，模块由 `module` 必传指定 → §4.2.12 |

> 答题卡的旧路径（`/listening/records/{id}/answer-card` 等五条）与其余旧路径一并下线。
> 现存两条路径并入同一个方法：`/hsk/objective/records/{id}/answer-card` 与 `/hsk/subjective/records/{id}/answer-card`，靠 `module` 分派，因此主观族不再单列答题卡端点。

### 3.2 主观族（写 / 译 / 说）

前缀：`/hsk/subjective/records`（唯一前缀，旧路径已下线）

| # | Method | Path | 用途 | 接口类型 | 改动简述 |
|---|---|---|---|---|---|
| 1 | POST | `{主观前缀}/start` | 开练 | 改造 | 三个控制器合一，`module` 决定模块 → §4.3.1 |
| 2 | GET | `{主观前缀}/{recordId}` | 记录详情 | 改造 | 响应体不变 → §4.3.2 |
| 3 | POST | `{主观前缀}/{recordId}/pause` | 暂停 | 改造 | 响应体不变；请求无时长 → §4.3.3 |
| 4 | POST | `{主观前缀}/{recordId}/resume` | 恢复 | 改造 | 响应体不变 → §4.3.4 |
| 5 | GET | `{主观前缀}/{recordId}/questions` | 拉题 | 改造 | 响应体不变 → §4.3.5 |
| 6 | PUT | `{主观前缀}/{recordId}/answers` | 批量保存答案 | 改造 | 响应体不变 → §4.3.6 |
| 7 | POST | `{主观前缀}/{recordId}/questions/{questionId}/answers` | 单题作答 | 改造 | 三模块通用；写 / 译填文本，口语填录音地址 → §4.3.7 |
| 8 | PUT | `{主观前缀}/{recordId}/questions/{questionId}/draft` | 保存草稿 | 改造 | 响应体不变 → §4.3.8 |
| 9 | POST | `{主观前缀}/{recordId}/submit` | 交卷 | 改造 | 幂等键改为服务端按模块拼 → §4.3.9 |
| 10 | GET | `{主观前缀}/{recordId}/report` | 报告详情 | 改造 | 新增 `aiUnlocked` → §4.3.10 |
| 11 | GET | `{主观前缀}/{recordId}/report/questions/{questionId}` | 逐题反馈 | 改造 | 新增 `aiUnlocked` → §4.3.11 |
| 12 | POST | `{主观前缀}/{recordId}/report/retry` | 判分重试 | 改造 | 三模块通用 → §4.3.12 |
| 13 | GET | `{主观前缀}/{recordId}/unlock/precheck` | 解锁预检 | 新增 | 返回三级余额、单价与弹窗文案 → §4.3.13 |
| 14 | POST | `{主观前缀}/{recordId}/unlock` | 执行解锁 | 新增 | 按卷扣一次权益，失败抛 8118，限流 5 次/秒 → §4.3.14 |

> 主观族响应体只有一处字段变更：`SubjectiveReportResponse` 与 `SubjectiveQuestionReportResponse` 新增布尔字段 `aiUnlocked`，其余结构不变。报告内容不因未解锁而清空。

### 3.3 首页模块卡、目录三跳与最近报告（五模块共用）

这一组接口不区分客观族 / 主观族，靠 `module` 区分模块，只读、不写库。首页模块卡、目录三跳与等级说明免登录，最近报告需要登录；三跳的响应结构五模块同构，最近报告的 `data` 按模块分形状。首页模块卡是进目录前的入口，等级说明只是目录页里展示的内容，两者都不是一跳。

下表序号与 §4.4 小节号一一对应；`modules` 与 `intro` 都不是跳次，前者是首页入口，后者是目录页里展示的说明。

| # | Method | Path | 用途 | 接口类型 | 改动简述 |
|---|---|---|---|---|---|
| 1 | GET | `/hsk/modules` | 首页模块卡（进目录前的入口，不是一跳） | 【无变更】 | 按 `version` 下发布局 + 副标题 + 卡片清单，字典驱动，免登录 → §4.4.1 |
| 2 | GET | `/hsk/modules/{module}/levels` | 目录第一跳：模块下的等级清单 | 【新增】 | 按 `practice_module_level_config` 下发可用等级，`module` 走路径段，免登录 → §4.4.2 |
| 3 | GET | `/hsk/levels` | 目录第二跳：等级概览 + 卷列表 + 进度 | 【无变更】 | `module` / `version` / `level` 全走 query，免登录 → §4.4.3 |
| 4 | GET | `/hsk/levels/{level}/intro` | 等级备考说明（目录内展示，不是一跳） | 【无变更】 | 能力描述三语 + 板块结构，无进度字段 → §4.4.4 |
| 5 | GET | `/hsk/papers/{paperId}/parts` | 目录第三跳：卷内板块 + 每块进度 | 【无变更】 | 板块统一 `parts[]`，进度含 `draft` / `report` / 口语 `stats` → §4.4.5 |
| 6 | GET | `/papers/{paperId}/reports/latest` | 板块最近一次已出报告 | 【新增】 | 替代原四条 `/{{mod}}/parts/{{structureId}}/reports/latest`，模块与板块号走 query → §4.4.6 |

> 目录三跳与等级说明的旧模块内路径（`/listening/levels`、`/reading/levels` 等 15 条）已整块下线，返回 `404`。
> 首页模块卡 `GET /hsk/modules` 与第一跳 `/hsk/modules/{module}/levels` 是同前缀下的两个并列路径，Spring 按段数精确匹配，互不冲突。

## 4. 改动接口详情

### 4.1 模块参数规则（两族通用）

| 路径 | `module` 是否必传 | 取值 |
|---|---|---|
| `/hsk/objective/records/**` | **必传** | `listening` / `reading` |
| `/hsk/subjective/records/**` | **必传** | `writing` / `translation` / `speaking` |
| `/hsk/modules` | 不涉及 | 无 `module` 参数，只按 `version` 下发卡片清单，免登录 |
| `/hsk/modules/{module}/levels` | **必传**（路径段） | 五个模块码全收，免登录 |
| `/hsk/levels`、`/hsk/levels/{level}/intro`、`/hsk/papers/{paperId}/parts` | **必传** | 五个模块码全收（`listening` / `reading` / `writing` / `speaking` / `translation`），免登录 |
| `/papers/{paperId}/reports/latest` | **必传** | 五个模块码全收，另需 `section` |

`module` 大小写与首尾空格不敏感。缺失、取值不在白名单 → `8133`。

旧路径（`/listening/records/**`、`/reading/records/**`、`/writing/records/**`、`/translation/records/**`、`/speaking/records/**`）**已不再注册**，访问返回 `404`。

---

### 4.2 客观族端点

#### 4.2.1 POST `{客观前缀}/start`

**用途**：开练。有未提交记录时直接返回该记录，已提交后再调用则新建一次练习
**鉴权**：需要登录

**入参说明**

| 参数名            | 位置     | 类型     | 必填  | 约束&说明                                       |
| -------------- | ------ | ------ | --- | ------------------------------------------- |
| module         | query  | String | 必传  | 【新增】`listening` / `reading`                 |
| paperId        | body   | Long   | 是   | 【无变更】练习试卷 ID                                |
| section        | body   | String | 是   | 【无变更】板块号 1..N                               |
| X-Client-Type  | header | String | 否   | 【无变更】                                       |

**请求示例**

```http
POST /practice/hsk/objective/records/start?module=listening
Authorization: Bearer xxx
X-Client-Type: APP
Content-Type: application/json

{ "paperId": 100231, "section": "1" }
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 900812,
    "paperId": 100231,
    "section": "1",
    "module": "listening",
    "status": "IN_PROGRESS",
    "version": 1,
    "currentQuestionId": null,
    "currentQuestionNumber": null,
    "durationSeconds": 0,
    "paused": false,
    "pausedAt": null,
    "answeredCount": 0,
    "totalQuestions": 20,
    "answers": []
  }
}
```

**返回字段说明**

| 字段                    | 类型      | 改动标记  | 说明                              |
| --------------------- | ------- | ----- | ------------------------------- |
| recordId              | Long    | 【无变更】 | 练习记录 ID（`practice_record.id`）   |
| paperId               | Long    | 【无变更】 | 试卷 ID                           |
| section               | String  | 【无变更】 | 板块号                             |
| module                | String  | 【新增】  | `listening` / `reading`         |
| status                | String  | 【修改】  | 状态枚举 `CREATED` 创建中 / `IN_PROGRESS` 作答中 / `ABANDONED` 已放弃 / `SUBMITTED` 已提交；库中存 0/1/2/3 |
| version               | Integer | 【新增】  | 乐观锁版本号，回传给 `baseVersion`        |
| currentQuestionId     | Long    | 【无变更】 | 当前停留题目 ID；刚开练为 null             |
| currentQuestionNumber | Integer | 【无变更】 | 当前停留题号；刚开练为 null                |
| durationSeconds       | Integer | 【无变更】 | 在场累计秒数                          |
| paused                | Boolean | 【无变更】 | 是否已离开（true 时前端不要自动续走计时器）        |
| pausedAt              | Long    | 【无变更】 | 上次离开时刻毫秒；`paused=false` 时为 null |
| answeredCount         | Integer | 【无变更】 | 已答题数                            |
| totalQuestions        | Integer | 【无变更】 | 本次练习总题数                         |
| answers               | Array   | 【修改】  | 元素结构见下                          |
| answers[].questionId  | Long    | 【无变更】 | 题目 ID                           |
| answers[].answer      | String  | 【无变更】 | 用户答案（选项编码）；未作答为 null            |
| answers[].answered    | Boolean | 【无变更】 | 是否已作答                           |



**服务端内部执行顺序（重要，后端&测试阅读）**

1. 按 `module` 解析模块，缺失或取值不合法即 `8133`
2. `SELECT ... FOR UPDATE` 查未提交记录，`(userId, paperId, sectionMapping, section)` 定位，仅 `status IN (0, 1)`（`CREATED` / `IN_PROGRESS`）
3. 有未提交记录 → 直接返回该记录（不校验）；已提交的记录不在查询范围内，继续往下新建一次练习
4. 校验试卷可用性 `exam_paper.enabled_prac = 1` 
5. 取题、按题号排序、**冻结 `question_ids`**
6. 插记录 + 逐题插 `practice_answer` 占位行：
   - 占位行带题目 / 题组 / 选项 / 标准答案 / 解析全量快照
7. 返回记录

> 约束：同一 `(userId, paperId, sectionMapping, section)` 至多一条 `status IN (0, 1)`（`CREATED` / `IN_PROGRESS`）的记录。

**本接口抛出错误码**：8107 / 8133 / 8141 / 8142 / 8166 / 8167 / 8168

---

#### 4.2.2 GET `{客观前缀}/{recordId}`

**用途**：查询练习记录当前进度
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 必传 | 模块码 |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 900812,
    "paperId": 100231,
    "section": "1",
    "module": "listening",
    "status": "IN_PROGRESS",
    "version": 7,
    "currentQuestionId": 55121,
    "currentQuestionNumber": 2,
    "durationSeconds": 186,
    "paused": false,
    "pausedAt": null,
    "answeredCount": 2,
    "totalQuestions": 20,
    "answers": [
      {
        "questionId": 55120,
        "answer": "C",
        "answered": true
      }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| recordId | Long | 练习记录 ID（`practice_record.id`） |
| paperId | Long | 试卷 ID |
| section | String | 板块号 |
| module | String | `listening` / `reading` |
| status | String | 枚举 `CREATED` / `IN_PROGRESS` / `ABANDONED` / `SUBMITTED`（库中存 0/1/2/3） |
| version | Integer | 乐观锁版本号，回传给 `baseVersion` |
| currentQuestionId | Long | 当前停留题目 ID；未开始为 null |
| currentQuestionNumber | Integer | 当前停留题号；未开始为 null |
| durationSeconds | Integer | 在场累计秒数 |
| paused | Boolean | 是否已离开 |
| pausedAt | Long | 上次离开时刻毫秒；`paused=false` 时为 null |
| answeredCount | Integer | 已答题数 |
| totalQuestions | Integer | 本次练习总题数 |
| answers | Array | 已保存答案项，元素见下 |
| answers[].questionId | Long | 题目 ID |
| answers[].answer | String | 用户答案（选项编码）；未作答为 null |
| answers[].answered | Boolean | 是否已作答 |

**服务端内部执行顺序**

1. 解析模块，按 `recordId` 查记录并校验归属（`8112` / `8102`）
2. 汇总 `answeredCount` / `totalQuestions`
3. 转换成记录响应

**本接口抛出错误码**：8102 / 8112 / 8133

---

#### 4.2.3 POST `{客观前缀}/{recordId}/pause`

**用途**：暂停作答，结算本段在场时长并记录停留位置
**鉴权**：需要登录

**入参说明**

| 参数名               | 位置    | 类型     | 必填   | 约束&说明                                            |
| ----------------- | ----- | ------ | ---- | ------------------------------------------------ |
| recordId          | path  | Long   | 是    | 练习记录 ID                                          |
| module            | query | String | 必传   | 模块码                                              |
| currentQuestionId | body  | Long   | 条件必填 | 【修改】停留题目 ID；**必传**（要校验该题属于本次记录，缺省回 `8101`）       |



**请求示例**

```json
{
  "currentQuestionId": 55121
}
```

**返回字段说明**（记录响应，暂停后 `paused=true`、`pausedAt` 有值、`durationSeconds` 已结算）

| 字段                    | 类型      | 说明                       |
| --------------------- | ------- | ------------------------ |
| recordId              | Long    | 练习记录 ID                  |
| paperId               | Long    | 试卷 ID                    |
| section               | String  | 板块号                      |
| module                | String  | `listening` / `reading`  |
| status                | String  | 枚举 `CREATED` / `IN_PROGRESS` / `ABANDONED` / `SUBMITTED`（库中存 0/1/2/3）  |
| version               | Integer | 乐观锁版本号，回传给 `baseVersion` |
| currentQuestionId     | Long    | 当前停留题目 ID；请求体未带则保持原值     |
| currentQuestionNumber | Integer | 当前停留题号                   |
| durationSeconds       | Integer | 本次结算后的累计在场秒数             |
| paused                | Boolean | 本次调用后为 `true`            |
| pausedAt              | Long    | 本次离开时刻毫秒                 |
| answeredCount         | Integer | 已答题数                     |
| totalQuestions        | Integer | 本次练习总题数                  |
| answers               | Array   | 已保存答案项                   |
| answers[].questionId  | Long    | 题目 ID                    |
| answers[].answer      | String  | 用户答案（选项编码）；未作答为 null     |
| answers[].answered    | Boolean | 是否已作答                    |

**服务端内部执行顺序**

1. 解析模块，`SELECT ... FOR UPDATE` 锁记录并校验归属与进行中状态（`8102` / `8103`；阅读为 `8112` / `8162`）
2. 结算本段时长：段起点取 `max(start_time, paused_time, resumed_time)`，单段上界 1800s
3. 写 `durationSeconds`、`paused_time = now`、停留位置
4. 返回记录

> 请求体没有 `durationSeconds`：时长一律服务端自算，客户端上报值忽略。
> 前端建议每 5–10 分钟与页面隐藏时各调一次，回来调 `resume`。

**本接口抛出错误码**：8101 / 8102 / 8103 / 8112 / 8133 / 8162

---

#### 4.2.4 POST `{客观前缀}/{recordId}/resume`

**用途**：恢复作答，开启新的在场计时段
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 必传 | 模块码 |

无请求体。

**返回字段说明**（记录响应，恢复后 `paused=false`、`pausedAt=null`，`durationSeconds` 不增加）

| 字段 | 类型 | 说明 |
|---|---|---|
| recordId | Long | 练习记录 ID |
| paperId | Long | 试卷 ID |
| section | String | 板块号 |
| module | String | `listening` / `reading` |
| status | String | 枚举 `CREATED` / `IN_PROGRESS` / `ABANDONED` / `SUBMITTED`（库中存 0/1/2/3） |
| version | Integer | 乐观锁版本号，回传给 `baseVersion` |
| currentQuestionId | Long | 当前停留题目 ID |
| currentQuestionNumber | Integer | 当前停留题号 |
| durationSeconds | Integer | 累计在场秒数，本次调用不增加 |
| paused | Boolean | 本次调用后为 `false` |
| pausedAt | Long | 恒 null |
| answeredCount | Integer | 已答题数 |
| totalQuestions | Integer | 本次练习总题数 |
| answers | Array | 已保存答案项 |
| answers[].questionId | Long | 题目 ID |
| answers[].answer | String | 用户答案（选项编码）；未作答为 null |
| answers[].answered | Boolean | 是否已作答 |

**服务端内部执行顺序**

1. 解析模块，锁记录并校验归属与进行中状态
2. 置 `paused_time = NULL`、`resumed_time = now`（新段起点，否则会重复计时）
3. 幂等：本来就在场时直接返回，不写库

> `resume` 只推进段起点，不累加时长；累计只发生在 `pause` 与 `submit`。

**本接口抛出错误码**：8102 / 8103 / 8112 / 8133 / 8162

---

#### 4.2.5 GET `{客观前缀}/{recordId}/questions`

**用途**：拉取本次练习冻结的题集
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 必传 | 【新增】模块码 |

**返回完整示例（听力）**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": [
    {
      "questionId": 55120,
      "number": 1,
      "layout": "choice",
      "typeId": "听力:细节判断",
      "typeIdMapping": "reading_detail_choice",
      "content": "男：请问洗手间在哪儿？",
      "passage": "男：请问洗手间在哪儿？",
      "optionContent": { "A": "在二楼", "B": "在一楼", "C": "在三楼" },
      "audioUrl": "https://cdn/xxx.mp3",
      "shareAudioUrl": "https://cdn/share.mp3",
      "groupId": null,
      "group": null,
      "userAnswer": null,
      "answered": false
    }
  ]
}
```

**返回完整示例（阅读）**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": [
    {
      "questionId": 66001,
      "number": 36,
      "layout": null,
      "typeId": "read_choice",
      "typeIdMapping": "readChoice",
      "content": "作者认为最重要的原因是？",
      "passage": "（文章正文……）",
      "optionContent": { "A": "气候", "B": "地理", "C": "人口" },
      "audioUrl": null,
      "shareAudioUrl": null,
      "groupId": 8801,
      "group": {
        "groupId": 8801,
        "title1Number": 1,
        "title1Text": "第一部分",
        "section": "2",
        "startNumber": 36,
        "endNumber": 40,
        "content":null,
        "passage": "（文章正文……）",
        "audioUrl": null,
        "optionContent": null
      },
      "userAnswer": "B",
      "answered": true
    }
  ]
}
```

**返回字段说明**

| 字段                  | 类型      | 改动标记  | 说明                                                    |
| ------------------- | ------- | ----- | ----------------------------------------------------- |
| questionId          | Long    | 【无变更】 | 题目 ID                                                 |
| number              | Integer | 【修改】  | 题号；**原听力字段名 `no`**                                    |
| layout              | String  | 【无变更】 | 布局编码，唯一真源 `question.layout`；**阅读恒 null**（快照未存 layout） |
| typeId              | String  | 【新增】  | 原始题型 ID；听力恒 null                                      |
| typeIdMapping       | String  | 【新增】  | 题型映射编码；听力恒 null                                       |
| content             | String  | 【新增】  | 题干；听力等于 `passage`（题库把题干放 passage）                     |
| passage             | String  | 【无变更】 | 文章 / 材料正文                                             |
| optionContent       | Object  | 【修改】  | **扁平** `{"A":"文本"}`；阅读原为 `{"options":{...}}`          |
| audioUrl            | String  | 【修改】  | 题目音频；**原听力字段名 `audio_url`**                           |
| shareAudioUrl       | String  | 【修改】  | 共享材料音频；**原听力字段名 `share_audio_url`**；阅读恒 null          |
| groupId             | Long    | 【新增】  | 题组 ID；听力恒 null                                        |
| group               | Object  | 【新增】  | 题组共享内容；听力恒 null；子字段见下                                 |
| group.groupId       | Long    | 【新增】  | 题组 ID                                                 |
| group.title1Number  | Integer | 【新增】  | 一级标题序号                                                |
| group.title1Text    | String  | 【新增】  | 一级标题文本                                                |
| group.section       | String  | 【新增】  | 题组所属板块号                                               |
| group.startNumber   | Integer | 【新增】  | 题组起始题号                                                |
| group.endNumber     | Integer | 【新增】  | 题组结束题号                                                |
| group.passage       | String  | 【新增】  | 题组共用文章 / 材料                                           |
| group.audioUrl      | String  | 【新增】  | 题组音频地址                                                |
| group.optionContent | Object  | 【新增】  | 题组共用选项，扁平 `{"A":"文本"}`                                |
| userAnswer          | String  | 【无变更】 | 当前答案                                                  |
| answered            | Boolean | 【无变更】 | 是否已作答                                                 |

**服务端内部执行顺序**

1. 解析模块，校验归属与 `status = IN_PROGRESS`
2. 听力：按 `question_ids` 顺序回 `question` 表取题，拿 `paper_id` 和`group_id`回 `question_shared_audio` 表取 `audio_url`得 `shareAudioUrl` 字段值
3. 阅读：按 `question_ids` 顺序回 `question` 表取题
4. 回填答案与 `answered`
5. 统一转成客观族题目结构

> 约束：题序以记录 `question_ids` 为准；历史记录无 `question_ids` 时听力回落三元组查询、阅读要求快照完整（`8180`）。

**本接口抛出错误码**：8102 / 8103 / 8107 / 8133 / 8165 / 8180

---

#### 4.2.6 PUT `{客观前缀}/{recordId}/answers/{questionId}`

**用途**：单题保存答案（用户点选后防抖同步）
**鉴权**：需要登录

**入参说明**

| 参数名         | 位置    | 类型      | 必填  | 约束&说明                                      |
| ----------- | ----- | ------- | --- | ------------------------------------------ |
| recordId    | path  | Long    | 是   | 练习记录 ID                                    |
| questionId  | path  | Long    | 是   | 题目 ID                                      |
| module      | query | String  | 必传  | 【新增】模块码                                    |
| answer      | body  | String  | 是   | 【修改】选项编码 A/B/C/D/E/F（判断题用 A/B）；传 null 表示清空 |
| baseVersion | body  | Integer | 是   | 【新增】记录 `version`；不一致回 `8104`（强校验）          |


**请求示例**

```json
{ "answer": "C", "baseVersion": 7, }
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "questionId": 55120,
    "answer": "C",
    "answered": true,
    "currentVersion": 8
  }
}
```

**返回字段说明**

| 字段             | 类型      | 改动标记  | 说明              |
| -------------- | ------- | ----- | --------------- |
| questionId     | Long    | 【无变更】 | 题目 ID           |
| answer         | String  | 【无变更】 | 保存后的答案          |
| answered       | Boolean | 【无变更】 | 是否已作答           |
| currentVersion | Integer | 【无变更】 | 记录最新版本；阅读恒 null |

**服务端内部执行顺序**

1. 解析模块，锁记录并校验归属与 `status = IN_PROGRESS`（`8102` / `8103`）
2. 写答案行 `answer = 请求answer`、`answered = 1`，重算 `answeredCount`，`lastSavedTime = now`
3. 返回答案项

**本接口抛出错误码**：8102 / 8103 / 8104 / 8107 / 8133 / 8173

---

#### 4.2.7 PUT `{客观前缀}/{recordId}/answers`（批量）

**用途**：强制保存点一次性提交多题（切题、退出、锁屏、交卷前）
**鉴权**：需要登录

**入参说明**

| 参数名               | 位置    | 类型      | 必填  | 约束&说明                           |
| ----------------- | ----- | ------- | --- | ------------------------------- |
| module            | query | String  | 必传  | 【新增】模块码                         |
| answers           | body  | Array   | 是   | 【修改】元素 `{questionId, answer}`；` |
| baseVersion       | body  | Integer | 是   | 【新增】两个模块都强校验                    |
| currentQuestionId | body  | Long    | 否   | 【无变更】顺带更新停留位置                   |



**请求示例**

```json
{
  "answers": [
    { "questionId": 55120, "answer": "C" },
    { "questionId": 55121, "answer": "A" }
  ],
  "currentQuestionId": 55121,
  "baseVersion": 8
}
```

**返回字段说明**（保存后的整条记录，`version` 与 `answers[]` 均为最新值）

| 字段 | 类型 | 说明 |
|---|---|---|
| recordId | Long | 练习记录 ID |
| paperId | Long | 试卷 ID |
| section | String | 板块号 |
| module | String | `listening` / `reading` |
| status | String | 枚举 `CREATED` / `IN_PROGRESS` / `ABANDONED` / `SUBMITTED`（库中存 0/1/2/3） |
| version | Integer | 本次写入后的记录版本号，回传给 `baseVersion` |
| currentQuestionId | Long | 当前停留题目 ID；请求体未带则保持原值 |
| currentQuestionNumber | Integer | 当前停留题号 |
| durationSeconds | Integer | 累计在场秒数 |
| paused | Boolean | 是否已离开 |
| pausedAt | Long | 上次离开时刻毫秒；`paused=false` 时为 null |
| answeredCount | Integer | 重算后的已答题数 |
| totalQuestions | Integer | 本次练习总题数 |
| answers | Array | 全卷答案项（不只本次提交的题） |
| answers[].questionId | Long | 题目 ID |
| answers[].answer | String | 用户答案（选项编码）；未作答为 null |
| answers[].answered | Boolean | 是否已作答 |

**服务端内部执行顺序**

1. 解析模块，锁记录校验归属与状态
2. 校验 `baseVersion` → 批量 upsert `practice_answer` → 重算 `answeredCount` → 返回记录

**本接口抛出错误码**：8102 / 8103 / 8104 / 8133 / 8169 / 8170 / 8171 / 8172 / 8173

---

#### 4.2.8 POST `{客观前缀}/{recordId}/submit`

**用途**：交卷并触发出分
**鉴权**：需要登录

**入参说明**

| 参数名             | 位置     | 类型      | 必填  | 约束&说明                                     |
| --------------- | ------ | ------- | --- | ----------------------------------------- |
| module          | query  | String  | 必传  | 【新增】模块码                                   |
| baseVersion     | body   | Integer | 是   | 【新增】不一致回 `8104`                           |
| finalAnswers    | body   | Array   | 否   | 【修改】元素 `{questionId, answer}`             |
| idempotencyKey  | body   | String  | 否   | 【无变更】不传由服务端拼 `{module}-{recordId}-submit` |
| Idempotency-Key | header | String  | 否   | 【无变更】body 未带时使用该头                         |


**请求示例**

```json
{
  "baseVersion": 12,
  "finalAnswers": [{ "questionId": 55120, "answer": "C" }]
}
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 900812,
    "paperId": 100231,
    "module": "listening",
    "sectionMapping": "SEC_LISTEN",
    "section": "1",
    "status": "SUBMITTED",
    "totalQuestions": 20,
    "answeredCount": 20,
    "correctCount": 17,
    "wrongCount": 3,
    "accuracyRate": 85.00,
    "durationSeconds": 1265,
    "submittedTime": 1763452800000
  }
}
```

**返回字段说明**

| 字段              | 类型         | 改动标记  | 说明                           |
| --------------- | ---------- | ----- | ---------------------------- |
| recordId        | Long       | 【无变更】 | 练习记录 ID                      |
| paperId         | Long       | 【新增】  | 试卷 ID                        |
| module          | String     | 【新增】  | `listening` / `reading`      |
| sectionMapping  | String     | 【新增】  | `SEC_LISTEN` / `SEC_READ`    |
| section         | String     | 【新增】  | 板块号                          |
| status          | String     | 【修改】  | 恒 `SUBMITTED`；状态枚举                  |
| totalQuestions  | Integer    | 【修改】  | 题目总数；                        |
| answeredCount   | Integer    | 【无变更】 | 已答题数                         |
| correctCount    | Integer    | 【无变更】 | 答对数                          |
| wrongCount      | Integer    | 【无变更】 | 答错数（未作答计入错误）                 |
| accuracyRate    | BigDecimal | 【无变更】 | 正确率百分比，保留 2 位小数；原听力为 Integer |
| durationSeconds | Integer    | 【无变更】 | 用时秒数                         |
| submittedTime   | Long       | 【无变更】 | 提交时间戳毫秒                      |


**服务端内部执行顺序**

1. 解析模块，锁记录校验归属、状态、`baseVersion`
2. `finalAnswers` 先落库（幂等：`idempotencyKey` 命中直接返回已有结果）
3. 比对标准答案快照逐题判分 → 写 `is_correct` / `points` → 汇总统计 
4. 时长由服务端按在场累计结算（`max(start, paused, resumed)` 为段起点，单段上界 1800s），**不接受客户端上报**

**本接口抛出错误码**：8102 / 8103 / 8104 / 8105 / 8133 / 8164 / 8180 / 8181

---

#### 4.2.9 GET `{客观前缀}/{recordId}/report`

**用途**：查看报告
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 必传 | 【新增】模块码 |

**返回字段说明**（统计取自 `practice_record`，`rows` 由快照组装）

| 字段                | 类型         | 说明                                    |
| ----------------- | ---------- | ------------------------------------- |
| recordId          | Long       | 练习记录 ID                               |
| paperId           | Long       | 试卷 ID                                 |
| module            | String     | `listening` / `reading`               |
| sectionMapping    | String     | `SEC_LISTEN` / `SEC_READ`             |
| section           | String     | 板块号                                   |
| status            | String     | 状态枚举，报告场景恒 `SUBMITTED`                |
| totalQuestions    | Integer    | 题目总数                                  |
| answeredCount     | Integer    | 已答题数                                  |
| correctCount      | Integer    | 答对数                                   |
| wrongCount        | Integer    | 答错数（未作答计入错误）                          |
| accuracyRate      | BigDecimal | 正确率百分比，保留 2 位小数                       |
| durationSeconds   | Integer    | 用时秒数                                  |
| submittedTime     | Long       | 提交时间戳毫秒                               |
| rows              | Array      | 题号矩阵，元素见下                             |
| rows[].number     | Integer    | 题号，practice_record.question_ids数组下标+1 |
| rows[].questionId | Long       | 题目 ID                                 |
| rows[].answered   | Boolean    | 是否作答                                  |
| rows[].isCorrect  | Boolean    | 是否正确                                  |


**服务端内部执行顺序**

1. 解析模块，校验归属与 `status = SUBMITTED`（未交卷回 `8105` / `8179`）
2. 读 `practice_record` 行作为统计来源（**报告即记录本身**）
3. 按 `practice_answer` 快照组装矩阵；未就绪时 `rows` 为空、统计为 0
4. 统一填 `module`  / `rows` 

**本接口抛出错误码**：8102 / 8105 / 8133 / 8176 / 8179 / 8181 / 8182

---

#### 4.2.10 GET `{客观前缀}/{recordId}/report/questions/{questionId}`

**用途**：逐题回顾（题目结构 + 判分 + 解析）
**鉴权**：需要登录

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "questionId": 66001,
    "number": 36,
    "layout": "choice",
    "typeId": null,
    "typeIdMapping": null,
    "content": "作者认为最重要的原因是？",
    "passage": "（文章正文……）",
    "optionContent": { "A": "气候", "B": "地理", "C": "人口" },
    "audioUrl": null,
    "shareAudioUrl": null,
    "groupId": 8801,
    "group": { "groupId": 8801, "startNumber": 36, "endNumber": 40, "passage": "（文章正文……）", "optionContent": null },
    "answered": true,
    "userAnswer": "B",
    "isCorrect": false,
    "standardAnswer": "A",
    "points": 0,
    "analysis": "（解析文本）"
  }
}
```

**返回字段说明**

| 字段                  | 类型         | 改动标记  | 说明                |
| ------------------- | ---------- | ----- | ----------------- |
| questionId          | Long       | 【修改】  | 题目 ID             |
| number              | Integer    | 【修改】  | 题号；               |
| layout              | String     | 【无变更】 | 布局编码；             |
| typeId              | String     | 【新增】  | 原始题型 ID；          |
| typeIdMapping       | String     | 【新增】  | 题型映射编码；           |
| content             | String     | 【新增】  | 题干；听力等于 `passage` |
| passage             | String     | 【无变更】 | 文章 / 材料正文         |
| optionContent       | Object     | 【修改】  | 扁平 `{"A":"文本"}`   |
| audioUrl            | String     | 【修改】  | 题目音频地址；           |
| shareAudioUrl       | String     | 【修改】  | 共享材料音频地址；阅读恒 null |
| groupId             | Long       | 【新增】  | 题组 ID；听力恒 null    |
| group               | Object     | 【新增】  | 题组共享内容；听力恒 null   |
| group.groupId       | Long       | 【新增】  | 题组 ID             |
| group.title1Number  | Integer    | 【新增】  | 一级标题序号            |
| group.title1Text    | String     | 【新增】  | 一级标题文本            |
| group.section       | String     | 【新增】  | 题组所属板块号           |
| group.startNumber   | Integer    | 【新增】  | 题组起始题号            |
| group.endNumber     | Integer    | 【新增】  | 题组结束题号            |
| group.passage       | String     | 【新增】  | 题组共用文章 / 材料       |
| group.audioUrl      | String     | 【新增】  | 题组音频地址            |
| group.optionContent | Object     | 【新增】  | 题组共用选项，扁平结构       |
| answered            | Boolean    | 【无变更】 | 是否已作答             |
| userAnswer          | String     | 【无变更】 | 用户答案；未作答为 null    |
| isCorrect           | Boolean    | 【无变更】 | 是否正确（未作答 false）   |
| standardAnswer      | String     | 【无变更】 | 正确答案；             |
| points              | BigDecimal | 【新增】  | 本题得分；             |
| analysis            | String     | 【无变更】 | 解析；               |

**本接口抛出错误码**：8102 / 8105 / 8133 / 8177 / 8181

---

#### 4.2.11 POST `{客观前缀}/{recordId}/report/retry`

**用途**：报告生成失败后重试
**鉴权**：需要登录
**前置条件**：`practice_record.status = 3`（`SUBMITTED`），`practice_record.idempotency_key NOT NULL`否则 `8106`

**返回字段说明**

| 字段                       | 类型         | 说明                                    |
| ------------------------ | ---------- | ------------------------------------- |
| recordId                 | Long       | 练习记录 ID                               |
| paperId                  | Long       | 试卷 ID                                 |
| module                   | String     | `listening` / `reading`               |
| sectionMapping           | String     | `SEC_LISTEN` / `SEC_READ`             |
| section                  | String     | 板块号                                   |
| status                   | String     | 状态枚举，报告场景恒 `SUBMITTED`               |
| totalQuestions           | Integer    | 题目总数                                  |
| answeredCount            | Integer    | 已答题数                                  |
| correctCount             | Integer    | 答对数                                   |
| wrongCount               | Integer    | 答错数（未作答计入错误）                          |
| accuracyRate             | BigDecimal | 正确率百分比，保留 2 位小数                       |
| durationSeconds          | Integer    | 用时秒数                                  |
| submittedTime            | Long       | 提交时间戳毫秒                               |
| rows                     | Array      | 题号矩阵，元素见下                             |
| rows[].number            | Integer    | 题号，practice_record.question_ids数组下标+1 |
| rows[].questionId        | Long       | 题目 ID                                 |
| rows[].answered          | Boolean    | 是否作答                                  |
| rows[].isCorrect         | Boolean    | 是否正确                                  |


**本接口抛出错误码**：8102 / 8105 / 8106 / 8133

---

#### 4.2.12 GET `{客观前缀}/{recordId}/answer-card`

**用途**：答题卡（五模块共用同一响应结构）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | 【新增】`listening`/`reading`/`writing`/`translation`/`speaking` |
| currentQuestionNumber | query | Integer | 否 | 当前题号，缺省取记录进度 |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 900812,
    "paperId": 100231,
    "section": 1,
    "totalQuestions": 20,
    "answeredCount": 3,
    "unansweredCount": 17,
    "currentQuestionNumber": 4,
    "questions": [
      { "order": 1, "questionId": 55120, "answered": true, "current": false },
      { "order": 2, "questionId": 55121, "answered": true, "current": false },
      { "order": 3, "questionId": 55122, "answered": true, "current": false },
      { "order": 4, "questionId": 55123, "answered": false, "current": true }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| recordId | Long | 练习记录 ID |
| paperId | Long | 试卷 ID |
| section | Integer | 板块号 |
| totalQuestions | Integer | 总题数 |
| answeredCount | Integer | 已答题数 |
| unansweredCount | Integer | 未答题数 |
| currentQuestionNumber | Integer | 当前题号；入参传了就用传入值，否则取记录进度 |
| questions[].order | Integer | 题号（作答顺序） |
| questions[].questionId | Long | 题目 ID |
| questions[].answered | Boolean | 是否已作答（只表态不判对错） |
| questions[].current | Boolean | 是否当前停留题 |


**本接口抛出错误码**：8102 / 8112 / 8133 / 8161

---

### 4.3 主观族端点

主观族 14 个端点（含 2 个解锁端点），全部挂在 `/hsk/subjective/records` 下。写 / 译 / 说三模块共用同一套端点，`module` 必传，端点本身不做模块级放行。旧的 `/writing/records/**`、`/translation/records/**`、`/speaking/records/**` 已下线。

**两条通用规则**

- `module` 缺失或取值不认识 → `8133`；与记录实际板块不匹配 → `8102`。用 `8102` 而非 404，避免被拿来探测他人记录是否存在
- 记录级端点统一按 `(recordId, userId)` 校验归属，`deleted = 1` 的记录同样回 `8102`

**响应体复用**

下表的「共用」只表示这几个端点返回同一套字段，具体字段在每个端点小节内都已完整列出，不需要跳读。

| 响应体 | 使用端点 | 完整字段所在小节 |
|---|---|---|
| `SubjectiveRecordResponse` | start / get / pause / resume / retry | §4.3.1、§4.3.2、§4.3.3、§4.3.4、§4.3.12 各自列全 |
| `SubjectiveQuestionResponse` | questions | §4.3.5 |
| `SubjectiveReportResponse` | report | §4.3.10 |
| `SubjectiveQuestionReportResponse` | report/questions/{questionId} | §4.3.11 |

---

#### 4.3.1 POST `{主观前缀}/start`

**用途**：开练。同一试卷同一板块已有未提交记录时直接返回该记录；已提交后再调用则新建一次练习
**鉴权**：需要登录
**幂等**：按 `(userId, paperId, sectionMapping, section)` 命中 `status = IN_PROGRESS`（1）的记录即返回，不重复建记录、不重置进度与计时

**入参说明**

| 参数名            | 位置     | 类型     | 必填  | 约束&说明                                                             |
| -------------- | ------ | ------ | --- | ----------------------------------------------------------------- |
| module         | query  | String | 是   | `writing` / `translation` / `speaking`                            |
| paperId        | body   | Long   | 是   | 练习试卷 ID                                                           |
| sectionMapping | body   | String | 是   | `SEC_WRITE` / `SEC_TRANSLATION` / `SEC_SPEAKING`，必须与 `module` 一致； |
| section        | body   | String | 是   | 板块号，服务端 `trim` 后使用                                                |
| X-Client-Type  | header | String | 否   | 客户端类型                                                             |

**请求示例**

```http
POST /practice/hsk/subjective/records/start?module=writing
Authorization: Bearer xxx
X-Client-Type: APP
Content-Type: application/json

{
  "paperId": 100231,
  "sectionMapping": "SEC_WRITE",
  "section": "1"
}
```

**返回字段说明**（`SubjectiveRecordResponse`，start / get / pause / resume / retry 共用）

| 字段                    | 类型         | 说明                                       |
| --------------------- | ---------- | ---------------------------------------- |
| recordId              | Long       | 练习记录 ID（`practice_subjective_record.id`） |
| paperId               | Long       | 试卷 ID                                    |
| sectionMapping        | String     | 板块域，库里原值                                 |
| section               | String     | 板块号                                      |
| levelCode             | String     | HSK 等级码                                  |
| status                | String     | 枚举 `CREATED` 创建中 / `IN_PROGRESS` 作答中 / `ABANDONED` 已放弃 / `SUBMITTED` 已提交；库中存 0/1/2/3                           |
| totalQuestions        | Integer    | 本次练习总题数（开练时冻结）                           |
| answeredCount         | Integer    | 已作答题目数                                   |
| currentQuestionId     | Long       | 当前停留题目 ID                                |
| currentQuestionNumber | Integer    | 当前停留题序（`question_ids` 下标 + 1）            |
| durationSeconds       | Integer    | 累计在场秒数，退出期间不计                            |
| paused                | Boolean    | 是否处于「已离开」状态；为 true 时前端不要自动续走计时器          |
| pausedAt              | Long       | 上次离开时刻（毫秒）；`paused=false` 时为 null        |
| objectiveCount        | Integer    | 客观题数（`has_standard_answer = 1`）          |
| objectiveCorrectCount | Integer    | 客观题答对数                                   |
| aiQuestionCount       | Integer    | 需 AI 评分的题数（已排除满分 0 的流程题）                 |
| aiScoredCount         | Integer    | AI 已评出分的题数                               |
| finalScore            | BigDecimal | 当前已得总分；AI 未评完时只有客观分                      |
| totalScore            | BigDecimal | 本卷满分                                     |

**服务端内部执行顺序**

1. 校验 `sectionMapping` 与 `module` 一致，不一致回 `8108`
2. `section` 去空白
3. 查未提交记录 `(userId, paperId, sectionMapping, section)`，条件只有 `status = IN_PROGRESS`（1）：命中直接返回，**不再校验卷与板块配置**
4. 校验试卷存在，不存在回 `8107`
5. 按三元组 `(paperId, sectionMapping, section)` 现取题、按题号排序，**冻结 `question_ids`**；之后拉题与交卷只认这份冻结顺序
6. 统计客观题数，算出 `totalQuestions` / `totalScore` / `objectiveCount` / `aiQuestionCount`
7. 插记录：`status = IN_PROGRESS`、`start_time = now`、`duration = 0`、`ai_deduct_state = 0`（未解锁）
8. 返回记录。此时逐题作答行还没有，首次保存作答时才建

> 服务端不提供重开接口：未提交要继续练走 `resume`，想从头再来就在交卷后重新 `start`。
> 记录按 `userId` 查，不可能命中他人记录，因此本端点不会抛 `8102`。

**本接口抛出错误码**：8107 / 8108 / 8133

---

#### 4.3.2 GET `{主观前缀}/{recordId}`

**用途**：查询记录详情，续练时用来恢复进度
**鉴权**：需要登录
**前置条件**：记录存在、属于当前用户、板块与 `module` 匹配，否则 `8102`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| X-Client-Type | header | String | 否 | 客户端类型 |

**返回字段说明**（记录响应，与 start 同一结构）

| 字段                    | 类型         | 说明                                       |
| --------------------- | ---------- | ---------------------------------------- |
| recordId              | Long       | 练习记录 ID（`practice_subjective_record.id`） |
| paperId               | Long       | 试卷 ID                                    |
| sectionMapping        | String     | 板块域，库里原值                                 |
| section               | String     | 板块号                                      |
| levelCode             | String     | HSK 等级码                                  |
| status                | String     | 枚举 `CREATED` 创建中 / `IN_PROGRESS` 作答中 / `ABANDONED` 已放弃 / `SUBMITTED` 已提交；库中存 0/1/2/3                           |
| totalQuestions        | Integer    | 本次练习总题数（开练时冻结）                           |
| answeredCount         | Integer    | 已作答题目数                                   |
| currentQuestionId     | Long       | 当前停留题目 ID；未开始为 null                      |
| currentQuestionNumber | Integer    | 当前停留题序（`question_ids` 下标 + 1）            |
| durationSeconds       | Integer    | 累计在场秒数，退出期间不计                            |
| paused                | Boolean    | 是否处于「已离开」状态                              |
| pausedAt              | Long       | 上次离开时刻（毫秒）；`paused=false` 时为 null        |
| objectiveCount        | Integer    | 客观题数（`has_standard_answer = 1`）          |
| objectiveCorrectCount | Integer    | 客观题答对数                                   |
| aiQuestionCount       | Integer    | 需 AI 评分的题数（已排除满分 0 的流程题）                 |
| aiScoredCount         | Integer    | AI 已评出分的题数                               |
| finalScore            | BigDecimal | 当前已得总分；AI 未评完时只有客观分                      |
| totalScore            | BigDecimal | 本卷满分                                     |

**服务端内部执行顺序**

1. 按 `recordId` 查记录（不加锁）
2. 校验归属、板块、`deleted`，任一不符回 `8102`
3. 返回

> 只读接口，不加行锁。已交卷的记录也能查，用于报告页回看。

**本接口抛出错误码**：8102 / 8133

---

#### 4.3.3 POST `{主观前缀}/{recordId}/pause`

**用途**：暂停。结算本段在场时长并记录当前停留位置，供切后台、锁屏与定时存档调用
**鉴权**：需要登录
**前置条件**：记录进行中，已交卷回 `8103`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| currentQuestionId | body | Long | 否 | 当前停留题目 ID；不传则不改进度位置 |
| X-Client-Type | header | String | 否 | 客户端类型 |

> 请求体整体可省略（`visibilitychange` 触发时没有位置上下文）。**请求体不含时长**，时长由服务端算。

**请求示例**

```http
POST /practice/hsk/subjective/records/900812/pause?module=writing
Authorization: Bearer xxx
Content-Type: application/json

{ "currentQuestionId": 55120331 }
```

**返回字段说明**（记录响应，暂停后 `paused = true`、`pausedAt` 有值、`durationSeconds` 已结算）

| 字段                    | 类型         | 说明                    |
| --------------------- | ---------- | --------------------- |
| recordId              | Long       | 练习记录 ID               |
| paperId               | Long       | 试卷 ID                 |
| sectionMapping        | String     | 板块域                   |
| section               | String     | 板块号                   |
| levelCode             | String     | HSK 等级码               |
| status                | String     | 枚举 `CREATED` 创建中 / `IN_PROGRESS` 作答中 / `ABANDONED` 已放弃 / `SUBMITTED` 已提交；库中存 0/1/2/3        |
| totalQuestions        | Integer    | 本次练习总题数               |
| answeredCount         | Integer    | 已作答题目数                |
| currentQuestionId     | Long       | 当前停留题目 ID；请求体未带则保持原值  |
| currentQuestionNumber | Integer    | 当前停留题序；题目不在冻结题集内时保持原值 |
| durationSeconds       | Integer    | 本次结算后的累计在场秒数          |
| paused                | Boolean    | 本次调用后为 `true`         |
| pausedAt              | Long       | 本次离开时刻（毫秒）            |
| objectiveCount        | Integer    | 客观题数                  |
| objectiveCorrectCount | Integer    | 客观题答对数                |
| aiQuestionCount       | Integer    | 需 AI 评分的题数            |
| aiScoredCount         | Integer    | AI 已评出分的题数            |
| finalScore            | BigDecimal | 当前已得总分                |
| totalScore            | BigDecimal | 本卷满分                  |

**服务端内部执行顺序**

1. `SELECT ... FOR UPDATE` 查记录并校验归属（`8102`）
2. 非进行中状态回 `8103`
3. 结算本段时长：`now − max(start_time, paused_time, resumed_time)`，累加到 `duration`，单段上界 1800 秒
4. `currentQuestionId` 在冻结题集内时，同时更新 `current_question_number`（下标 + 1）；不在题集内则忽略，不报错
5. `paused_time = now`，写回记录
6. 返回记录

> 重复调用 `pause` 是安全的：结算基点是 `max(...)`，没有新起一段时该段结算结果趋近 0。

**本接口抛出错误码**：8102 / 8103 / 8133

---

#### 4.3.4 POST `{主观前缀}/{recordId}/resume`

**用途**：恢复。结束停表状态，计时器从已累计时长继续累加
**鉴权**：需要登录
**前置条件**：记录进行中，已交卷回 `8103`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| X-Client-Type | header | String | 否 | 客户端类型 |

**返回字段说明**（记录响应，恢复后 `paused = false`、`pausedAt = null`、`durationSeconds` 不变）

| 字段                    | 类型         | 说明             |
| --------------------- | ---------- | -------------- |
| recordId              | Long       | 练习记录 ID        |
| paperId               | Long       | 试卷 ID          |
| sectionMapping        | String     | 板块域            |
| section               | String     | 板块号            |
| levelCode             | String     | HSK 等级码        |
| status                | String     | 枚举 `CREATED` 创建中 / `IN_PROGRESS` 作答中 / `ABANDONED` 已放弃 / `SUBMITTED` 已提交；库中存 0/1/2/3 |
| totalQuestions        | Integer    | 本次练习总题数        |
| answeredCount         | Integer    | 已作答题目数         |
| currentQuestionId     | Long       | 当前停留题目 ID      |
| currentQuestionNumber | Integer    | 当前停留题序         |
| durationSeconds       | Integer    | 累计在场秒数，本次调用不增加 |
| paused                | Boolean    | 本次调用后为 `false` |
| pausedAt              | Long       | 恒 null         |
| objectiveCount        | Integer    | 客观题数           |
| objectiveCorrectCount | Integer    | 客观题答对数         |
| aiQuestionCount       | Integer    | 需 AI 评分的题数     |
| aiScoredCount         | Integer    | AI 已评出分的题数     |
| finalScore            | BigDecimal | 当前已得总分         |
| totalScore            | BigDecimal | 本卷满分           |

**服务端内部执行顺序**

1. `SELECT ... FOR UPDATE` 查记录并校验归属（`8102`）
2. 非进行中状态回 `8103`
3. `paused_time` 非空时执行一条显式 UPDATE：`paused_time = NULL` + `resumed_time = now`
4. 回查记录并返回

> 时间列清零必须走显式 UPDATE：MyBatis-Plus 的 `updateById` 默认忽略 null 字段，用它会清不掉 `paused_time`。
> `resume` 只推进新段起点，**不做任何累加**；累加只发生在 `pause` 与 `submit`。因此重复调用 `resume` 是幂等的。

**本接口抛出错误码**：8102 / 8103 / 8133

---

#### 4.3.5 GET `{主观前缀}/{recordId}/questions`

**用途**：拉取本次练习的题目，按开练时冻结的顺序下发，逐题带作答形式与已存草稿
**鉴权**：需要登录
**前置条件**：记录存在且属于当前用户，否则 `8102`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| X-Client-Type | header | String | 否 | 客户端类型 |

**返回字段说明**（`SubjectiveQuestionResponse`，数组，按题序）

| 字段                        | 类型      | 说明                                                            |
| ------------------------- | ------- | ------------------------------------------------------------- |
| questionId                | Long    | 题目 ID                                                         |
| order                     | Integer | 题序 = `question_ids` 下标 + 1，**前端翻页/定位以此为准**                    |
| no                        | Integer | 卷面题号（`question.number`），可能跳号，只用于展示                            |
| layout                    | String  | 题面形态，`question.layout` 原值：`input` / `record` / `shortInput` 等 |
| typeName                  | String  | 题型名                                                           |
| sectionTitle              | String  | 板块标题                                                          |
| content                   | String  | 题干                                                            |
| passage                   | String  | 题级材料                                                          |
| audioUrl                  | String  | 题目音频地址                                                        |
| shareAudioUrl             | String  | 共享材料音频地址                                                      |
| optionContent             | Object  | 选项，扁平结构 `{"A":"文本","B":"文本"}`                                 |
| groupContent              | String  | 题组题干                                                          |
| groupPassage              | String  | 题组共用材料                                                        |
| groupOptionContent        | Object  | 题组共用选项，结构同上                                                   |
| hasStandardAnswer         | Integer | `1` 客观题（交卷即判）、`0` 主观题（交 AI）                                   |
| answered                  | Boolean | 是否已保存正式作答（草稿不算）                                               |
| answerText                | String  | 已保存的文本作答：写作正文 / 笔译译文 (无需将用户录音转为文字，口语为NULL)                    |
| answer                    | String  | 已保存的音频 URL：口语 / 口译                                            |
| durationMs                | Long    | 录音时长（毫秒）                                                      |
| answerDraft               | Object  | 草稿块；从未存过为 `null`，子字段见下                                        |
| answerDraft.text          | String  | 草稿正文；空串表示用户清空后存过                                              |
| answerDraft.graphemeCount | Integer | 不含空白字符的字素数                                                    |
| answerDraft.version       | Long    | 草稿版本，保存时回传做乐观锁                                                |
| answerDraft.savedTime     | Long    | 最后保存时刻（毫秒）                                                    |

**服务端内部执行顺序**

1. 查记录并校验归属（`8102`），不加锁
2. 按 `question_ids` 冻结顺序加载题目行
3. 一次查出该记录全部作答行，按 `questionId` 建索引
4. 逐题组装：`order = i + 1`、`no = 卷面题号`、作答字段取自作答行
5. 返回数组

> 草稿块的 `null` 与空串含义不同：`answerDraft = null` 表示从没存过草稿；`answerDraft.text = ""` 表示用户清空后保存过。前端靠 `savedTime` 区分「恢复了一个空草稿」与「压根没草稿」。
> 题目全部从冻结的 `question_ids` 取，**不重新按板块查题**，所以中途改题库配置不会影响进行中的练习。
> 冻结题集里的题若在题库中已被删除，服务端**静默跳过、只打 warn**，本接口不报错，返回的数组会比 `totalQuestions` 少。前端不要假设数组长度等于总题数。

**本接口抛出错误码**：8102 / 8133

---

#### 4.3.6 PUT `{主观前缀}/{recordId}/answers`（批量保存）

**用途**：批量保存正式作答，仅保存不评分。写作与笔译一次提交整段文字，口语与口译提交录音地址
**鉴权**：需要登录
**前置条件**：记录进行中，已交卷回 `8103`

**入参说明**

| 参数名                     | 位置     | 类型     | 必填  | 约束&说明                                  |
| ----------------------- | ------ | ------ | --- | -------------------------------------- |
| recordId                | path   | Long   | 是   | 练习记录 ID                                |
| module                  | query  | String | 是   | `writing` / `translation` / `speaking` |
| answers                 | body   | Array  | 是   | 作答列表，元素见下                              |
| answers[].questionId    | body   | Long   | 是   | 题目 ID，必须在冻结题集内，否则 `8107`               |
| answers[].answerText    | body   | String | 否   | 文本作答：写作正文 / 笔译译文 (无需将用户录音转为文字，口语为NULL) |
| answers[].answer        | body   | String | 否   | 音频 URL：口语 / 口译                         |
| answers[].durationMs    | body   | Long   | 否   | 录音时长（毫秒）                               |
| answers[].answerVersion | body   | Long   | 否   | 客户端持有的版本，**当前不参与校验**（见下）               |
| currentQuestionId       | body   | Long   | 否   | 当前题，用于更新进度位置；不传则不改进度                   |
| X-Client-Type           | header | String | 否   | 客户端类型                                  |

**请求示例**

```http
PUT /practice/hsk/subjective/records/900812/answers?module=writing
Authorization: Bearer xxx
Content-Type: application/json

{
  "answers": [
    { "questionId": 55120331, "answerText": "我最近看了一部很有意思的电影……" }
  ],
  "currentQuestionId": 55120331
}
```

**返回字段说明**（`SubjectiveAnswerSaveResponse`）

| 字段 | 类型 | 说明 |
|---|---|---|
| recordId | Long | 练习记录 ID |
| answeredCount | Integer | 保存后全卷已作答题目数 |
| currentQuestionId | Long | 当前停留题目 ID |
| currentQuestionNumber | Integer | 当前停留题序 |
| answers | Array | 本次保存涉及的题目 |
| answers[].questionId | Long | 题目 ID |
| answers[].answerVersion | Long | 保存后的行版本号，供下次带回 |

**服务端内部执行顺序**

1. `SELECT ... FOR UPDATE` 查记录并校验归属（`8102`）
2. 非进行中状态回 `8103`
3. 一次加载冻结题集，建 `questionId → 题目行` 索引
4. 逐条处理作答项：
   - 题目不在题集内 → `8107`（防串记录、防塞脏题）
   - 按模块决定落哪一列：**口语**落 `answer` + `durationMs`，**写作与翻译（除口译外）**落 `answerText` 并清空音频列
   - 重算 `answered`：文本非空白或音频非空即为已作答
   - 行版本 `answerVersion + 1`，首次作答时补 `first_answered_time`
5. `currentQuestionId` 非空时同步更新 `current_question_number`
6. 重算 `answeredCount`，写回记录
7. 返回

> `answerVersion` 这个字段请求与响应都有，但服务端**只自增、不比对**：目前没有"版本不一致就拒绝"的逻辑，多端同时改是最后写入者生效。想做强校验需要在此处补一次 `WHERE answer_version = ?`，会影响客户端契约，暂时不做。

**本接口抛出错误码**：8102 / 8103 / 8107 / 8133

---

#### 4.3.7 POST `{主观前缀}/{recordId}/questions/{questionId}/answers`

**用途**：单题作答，仅保存不评分。题目 ID 走路径，请求体可省略
**鉴权**：需要登录
**前置条件**：同 §4.3.6

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| questionId | path | Long | 是 | 题目 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| answerText | body | String | 否 | 文本作答：写作 / 笔译 / 口语转写 |
| answer | body | String | 否 | 音频 URL：口语 / 口译 |
| durationMs | body | Long | 否 | 录音时长（毫秒） |
| X-Client-Type | header | String | 否 | 客户端类型 |

**返回字段说明**（与批量保存同一结构，`answers` 只含本题一项）

| 字段 | 类型 | 说明 |
|---|---|---|
| recordId | Long | 练习记录 ID |
| answeredCount | Integer | 保存后全卷已作答题目数 |
| currentQuestionId | Long | 当前停留题目 ID，本端点恒等于路径里的 `questionId` |
| currentQuestionNumber | Integer | 当前停留题序 |
| answers | Array | 本次保存涉及的题目，本端点固定 1 个元素 |
| answers[].questionId | Long | 题目 ID |
| answers[].answerVersion | Long | 保存后的行版本号，供下次带回 |

**服务端内部执行顺序**

1. 把请求体包装成只含一个元素的作答列表，`currentQuestionId` 置为路径里的 `questionId`
2. 直接复用 §4.3.6 的批量保存链路，行为与返回完全一致

> **请求体可省略**：不传或传空对象时，该题的两个作答字段都为空，结果等于「清空这道题的作答」——`answered` 置 0、旧分作废。前端要做"清除作答"可以直接利用这个语义。
> 该端点写、译、说三模块通用，不做模块级放行。落列规则与批量保存一致。

**本接口抛出错误码**：8102 / 8103 / 8107 / 8133

---

#### 4.3.8 PUT `{主观前缀}/{recordId}/questions/{questionId}/draft`

**用途**：保存题目级草稿。PUT 语义整份覆盖，只写草稿列
**鉴权**：需要登录
**前置条件**：记录进行中，已交卷回 `8109`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| questionId | path | Long | 是 | 题目 ID，必须在冻结题集内，否则 `8107` |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| text | body | String | 是 | 草稿全文；清空请传空串（`null` 由校验拦下） |
| expectedVersion | body | Long | 否 | 期望的草稿版本；传了就必须与库里一致，否则 `8111` |
| X-Client-Type | header | String | 否 | 客户端类型 |

**请求示例**

```http
PUT /practice/hsk/subjective/records/900812/questions/55120331/draft?module=writing
Authorization: Bearer xxx
Content-Type: application/json

{ "text": "我最近看了一部很有意思的电影……", "expectedVersion": 3 }
```

**返回字段说明**（`SubjectiveDraftResponse`）

| 字段 | 类型 | 说明 |
|---|---|---|
| questionId | Long | 题目 ID |
| version | Long | 保存后的草稿版本，首次保存为 1；同文本重复保存不增 |
| savedTime | Long | 服务端保存时刻（毫秒） |
| graphemeCount | Integer | 不含空白字符的字素数 |

**服务端内部执行顺序**

1. 查记录并校验归属（`8102`），不加锁
2. 非进行中状态回 `8109`（草稿冻结只读，保留供回看）
3. 校验题目在冻结题集内，否则 `8107`
4. 数字素数，超上限回 `8110`：写作与笔译 5000 字，**口语与口译（翻译 `section = 2`）不限**
5. 库里还没有该题作答行 → 插入一行「空答案 + 草稿」：
   - `answered = 0`、`grading_state = 未答`，答题卡仍显示未答
   - `expectedVersion` 传了非 0 值 → 说明客户端拿到了脏版本，回 `8111`
   - 并发首存撞唯一键 → 退化成更新，不让用户白写
6. 已有行 → 版本比对：`expectedVersion` 与库里不一致回 `8111`；文本完全相同就直接返回现值不增版本（避免每次失焦重写几 KB）
7. 条件更新，命中 0 行说明期间被别的请求改了版本 → 回 `8111`
8. 返回新版本号与保存时刻

> 草稿**不是作答**：不写 `answer_text`、不置 `answered`、不动 `grading_state` 与 `points`。
> 交卷时服务端不会拿草稿兜底变答案，只在交卷响应里回 `draftNotSubmitted` 提示哪几题只有草稿。所以交卷前必须调一次 §4.3.6 把编辑器内容落成正式答案。

**本接口抛出错误码**：8102 / 8107 / 8109 / 8110 / 8111 / 8133

---

#### 4.3.9 POST `{主观前缀}/{recordId}/submit`

**用途**：交卷。冻结题目与答案快照，客观题当次判分，主观题转入 AI 评分队列
**鉴权**：需要登录
**前置条件**：记录存在且属于当前用户，否则 `8102`；未交卷且非进行中回 `8103`
**幂等**：服务端按 `{module}-{recordId}-submit` 拼幂等键写入记录，重复交卷直接返回当前结果

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| finalAnswers | body | Array | 否 | 交卷这一刻的最后一批作答，元素结构同 §4.3.6 |
| idempotencyKey | body | String | 否 | 兼容旧前端的字段，**服务端忽略其值** |
| Idempotency-Key | header | String | 否 | 同上，仅打日志，不参与去重 |
| X-Client-Type | header | String | 否 | 客户端类型 |

> 请求体整体可省略。若前端在交卷前才把编辑器内容提交，可以放进 `finalAnswers` 一起落库，省一次往返。

**返回字段说明**（`SubjectiveSubmitResponse`）

| 字段                    | 类型            | 说明                     |
| --------------------- | ------------- | ---------------------- |
| recordId              | Long          | 练习记录 ID                |
| paperId               | Long          | 试卷 ID                  |
| module                | String        | 模块码                    |
| status                | String        | 枚举 `CREATED` 创建中 / `IN_PROGRESS` 作答中 / `ABANDONED` 已放弃 / `SUBMITTED` 已提交；库中存 0/1/2/3         |
| totalQuestions        | Integer       | 总题数                    |
| answeredCount         | Integer       | 已作答题目数                 |
| objectiveCount        | Integer       | 客观题数                   |
| objectiveCorrectCount | Integer       | 客观题答对数                 |
| aiQuestionCount       | Integer       | 需 AI 评分的题数             |
| aiScoredCount         | Integer       | 已评出分的 AI 题数（交卷瞬间通常为 0） |
| finalScore            | BigDecimal    | 当前总分（交卷瞬间只有客观分）        |
| totalScore            | BigDecimal    | 本卷满分                   |
| idempotencyKey        | String        | 服务端拼的交卷幂等键，重复交卷返回同一个   |
| draftNotSubmitted     | Array\<Long\> | 只有草稿、没落正式答案的题目 ID 列表   |

**服务端内部执行顺序**

1. `SELECT ... FOR UPDATE` 查记录并校验归属（`8102`）
2. 幂等判断：已交卷，或记录的幂等键已等于服务端拼的键 → **直接返回当前口径，不做任何写入**
3. 未交卷且非进行中 → `8103`
4. `finalAnswers` 落库（复用 §4.3.6 的 upsert，并额外冻结快照）
5. 逐题冻结快照 + 分流：
   - 题集里有、但一行答案都没有的题 → 补一条占位行，`grading_state = 未答`，报告才能逐题列出
   - 客观题（`has_standard_answer = 1`）：已作答则当次比对判分、写 `points` 与对错、置已评；未作答则 0 分、置未答
   - 主观题且满分 > 0：已作答置**待评**并收集 `answer_id`；未作答置未答
1. 写回记录：`status = SUBMITTED`（3）、`end_time`、结算在场时长、全量统计、`idempotency_key`
2. **本卷没有可评的 AI 题**时直接把 `ai_deduct_state` 置为 `3 无需解锁`；有 AI 题则停在 `0 未解锁`，等用户在报告页主动解锁
3. 事务提交后再把待评作答投进评分线程池（`afterCommit`），不拖慢交卷响应
4. 返回

> 交卷**不做任何权益校验与扣减**，余额不够也能交卷、也能看到分数，只是解析要等解锁。
> AI 投递放在事务提交之后：评分线程读不到未提交数据，交卷也不会被 AI 调用阻塞。

**本接口抛出错误码**：8102 / 8103 / 8107 / 8133

---

#### 4.3.10 GET `{主观前缀}/{recordId}/report`

**用途**：查询报告，含总分、逐题摘要、评分状态与解锁标志
**鉴权**：需要登录
**前置条件**：记录存在且属于当前用户，否则 `8102`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| X-Client-Type | header | String | 否 | 客户端类型 |

**返回字段说明**（`SubjectiveReportResponse`）

| 字段                            | 类型         | 改动标记  | 说明                                                     |
| ----------------------------- | ---------- | ----- | ------------------------------------------------------ |
| recordId                      | Long       | 【无变更】 | 练习记录 ID                                                |
| paperId                       | Long       | 【无变更】 | 试卷 ID                                                  |
| module                        | String     | 【新增】  | 模块码                                                    |
| sectionMapping                | String     | 【无变更】 | 板块域                                                    |
| section                       | String     | 【无变更】 | 板块号                                                    |
| status                        | String     | 【修改】  | 枚举 `CREATED` / `IN_PROGRESS` / `ABANDONED` / `SUBMITTED`；库中存 0/1/2/3 |
| totalQuestions                | Integer    | 【无变更】 | 总题数                                                    |
| answeredCount                 | Integer    | 【无变更】 | 已作答题目数                                                 |
| objectiveCount                | Integer    | 【无变更】 | 客观题数                                                   |
| objectiveCorrectCount         | Integer    | 【无变更】 | 客观题答对数                                                 |
| aiQuestionCount               | Integer    | 【无变更】 | AI 题数                                                  |
| aiScoredCount                 | Integer    | 【无变更】 | AI 已评出分的题数                                             |
| finalScore                    | BigDecimal | 【无变更】 | 当前总分                                                   |
| totalScore                    | BigDecimal | 【无变更】 | 本卷满分                                                   |
| durationSeconds               | Integer    | 【无变更】 | 累计在场秒数                                                 |
| startTime                     | Long       | 【无变更】 | 开练时刻（毫秒）                                               |
| endTime                       | Long       | 【无变更】 | 交卷时刻（毫秒）                                               |
| aiUnlocked                    | Boolean    | 【新增】  | 解析是否已解锁；内容不因未解锁而清空                                     |
| questions                     | Array      | 【无变更】 | 逐题摘要，元素见下                                              |
| questions[].order             | Integer    | 【无变更】 | 题序 = 冻结下标 + 1                                          |
| questions[].questionId        | Long       | 【无变更】 | 题目 ID                                                  |
| questions[].hasStandardAnswer | Integer    | 【无变更】 | 1 客观 / 0 主观                                            |
| questions[].answered          | Boolean    | 【无变更】 | 是否已作答                                                  |
| questions[].gradingState      | Integer    | 【无变更】 | 0 待评 / 1 已评 / 2 未答或失败                                  |
| questions[].points            | BigDecimal | 【无变更】 | 得分；待评时为 null                                           |
| questions[].maxScore          | BigDecimal | 【无变更】 | 单题满分                                                   |
| questions[].isFullScore       | Integer    | 【无变更】 | 1 满分 / 0 非满分；待评时为 null                                 |
| questions[].correct           | Boolean    | 【无变更】 | 客观题对错；主观题恒 null                                        |


**服务端内部执行顺序**

1. 查记录并校验归属（`8102`），不加锁
2. 按冻结顺序加载题目行，一次查出全部作答行
3. 逐题组装摘要：`correct` 只在客观题且已评时给值，主观题一律 `null`
4. `aiUnlocked = ai_deduct_state ∈ {1, 2, 3}`（`2` 是历史欠费，读时按已解锁处理）
5. 返回

> **不遮蔽内容**：报告本身不带解析正文，逐题解析在 §4.3.11 里，同样全文返回。是否展示由前端按 `aiUnlocked` 决定，后端不做付费墙。

**本接口抛出错误码**：8102 / 8133

---

#### 4.3.11 GET `{主观前缀}/{recordId}/report/questions/{questionId}`

**用途**：查询单题反馈，含用户作答、参考答案、得分、AI 点评与题目快照
**鉴权**：需要登录
**前置条件**：记录属于当前用户，否则 `8102`；该题没有作答行或不在冻结题集内，回 `8107`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| questionId | path | Long | 是 | 题目 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| X-Client-Type | header | String | 否 | 客户端类型 |

**返回字段说明**（`SubjectiveQuestionReportResponse`）

| 字段                | 类型         | 改动标记  | 说明                               |
| ----------------- | ---------- | ----- | -------------------------------- |
| order             | Integer    | 【无变更】 | 题序 = 冻结下标 + 1                    |
| questionId        | Long       | 【无变更】 | 题目 ID                            |
| layout            | String     | 【无变更】 | 题面形态                             |
| hasStandardAnswer | Integer    | 【无变更】 | 1 客观 / 0 主观                      |
| answered          | Boolean    | 【无变更】 | 是否已作答                            |
| gradingState      | Integer    | 【无变更】 | 0 待评 / 1 已评 / 2 未答或失败            |
| points            | BigDecimal | 【无变更】 | 得分；待评时为 null                     |
| maxScore          | BigDecimal | 【无变更】 | 单题满分                             |
| isFullScore       | Integer    | 【无变更】 | 1 满分 / 0 非满分                     |
| correct           | Boolean    | 【无变更】 | 客观题对错；主观题恒 null                  |
| analysis          | String     | 【无变更】 | 主观题是 AI 点评，客观题是题目解析；优先取作答行上冻结的评语 |
| standardAnswer    | String     | 【无变更】 | 标准答案；主观题通常为空                     |
| answerText        | String     | 【无变更】 | 用户文本作答                           |
| answer            | String     | 【无变更】 | 用户音频 URL                         |
| snapshot          | Object     | 【无变更】 | 交卷时冻结的题目快照（题干 / 题组 / 选项）         |
| aiUnlocked        | Boolean    | 【新增】  | 解析是否已解锁；内容不因未解锁而清空               |

**服务端内部执行顺序**

1. 查记录并校验归属（`8102`），不加锁
2. 查该题作答行，没有回 `8107`
3. 按冻结题集加载这一题，没有回 `8107`
4. 组装：`order` 用冻结下标、`analysis` 优先取作答行上冻结的 AI 评语，为空再回退到题目解析
5. 返回

> 交卷后 AI 还没评完时，`hasStandardAnswer = 0` 、`gradingState = 0`、`points` 为 `null`、`analysis` 可能为空，前端应按"评分中"展示而不是"无解析"。

**本接口抛出错误码**：8102 / 8107 / 8133

---

#### 4.3.12 POST `{主观前缀}/{recordId}/report/retry`

**用途**：判分重试。把已作答但评分失败的题重新置为待评并再次投递
**鉴权**：需要登录
**前置条件**：记录存在且属于当前用户，否则 `8102`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| X-Client-Type | header | String | 否 | 客户端类型 |

**返回字段说明**（记录响应，可据 `status` 判断是否已重新进入 ）

| 字段                    | 类型         | 说明                                |
| --------------------- | ---------- | --------------------------------- |
| recordId              | Long       | 练习记录 ID                           |
| paperId               | Long       | 试卷 ID                             |
| sectionMapping        | String     | 板块域                               |
| section               | String     | 板块号                               |
| levelCode             | String     | HSK 等级码                           |
| status                | String     | 枚举 `CREATED` 创建中 / `IN_PROGRESS` 作答中 / `ABANDONED` 已放弃 / `SUBMITTED` 已提交；库中存 0/1/2/3                    |
| totalQuestions        | Integer    | 本次练习总题数                           |
| answeredCount         | Integer    | 已作答题目数                            |
| currentQuestionId     | Long       | 当前停留题目 ID                         |
| currentQuestionNumber | Integer    | 当前停留题序                            |
| durationSeconds       | Integer    | 累计在场秒数                            |
| paused                | Boolean    | 是否处于「已离开」状态                       |
| pausedAt              | Long       | 上次离开时刻（毫秒）；`paused=false` 时为 null |
| objectiveCount        | Integer    | 客观题数                              |
| objectiveCorrectCount | Integer    | 客观题答对数                            |
| aiQuestionCount       | Integer    | 需 AI 评分的题数                        |
| aiScoredCount         | Integer    | AI 已评出分的题数                        |
| finalScore            | BigDecimal | 当前已得总分                            |
| totalScore            | BigDecimal | 本卷满分                              |

**服务端内部执行顺序**

1. `SELECT ... FOR UPDATE` 查记录并校验归属（`8102`）
2. 加载冻结题集，建 `questionId → 是否客观题` 索引
3. 遍历该记录全部作答行，同时满足四条才入选：
   - `grading_state = 2`（未答或评分失败）
   - 主观题（非客观题）
   - 单题满分 > 0（满分 0 的流程题不进 AI 队列）
   - 已作答
4. 用**一条 SQL** 批量重置入选行的评分字段（`grading_state = 0`、清 `grading_next_time` 与 `grading_error`、重排租约）
5. `grading_attempts + 1`，写回记录
6. 事务提交后把入选的作答 ID 投进评分线程池，用户不用等下一轮兜底扫描
7. 返回记录

> 三模块口径完全一致，不做模块级放行。
> 用一条 SQL 重置而不是逐行 `updateById`：MyBatis-Plus 默认忽略 null 字段，`grading_next_time` / `grading_error` 清不掉的话，重试的题会一直卡在退避里。
> 该端点不校验"是否已交卷"：未交卷时已答题是待评、未答题是未答，都不满足入选条件，因此不会误重排；但 `grading_attempts` 仍会 +1。

**本接口抛出错误码**：8102 / 8133

---

**AI 解析解锁口径**

交卷与评分都不涉及扣费，扣费只发生在用户主动解锁时。打开报告页先看 `aiUnlocked`：

未解锁时报告与单题反馈的 `analysis`、`standardAnswer` 字段**照常返回全文**，是否展示完全由前端按 `aiUnlocked` 控制。后端不做内容遮蔽，也不返回「锁定占位文案」。

扣减顺序：免费次数（场景 `report_unlock`，新用户默认 3 次）→ AI 解析次数（场景 `ai_analysis`）→ 考试点数（场景 `report_unlock`），扣到一级即停，走过的级别写入 `deduct_type`。

---

#### 4.3.13 GET `{主观前缀}/{recordId}/unlock/precheck`

**用途**：解锁预检，供弹窗直接渲染
**鉴权**：需要登录
**前置条件**：记录已交卷，否则 `8105`；记录不属于当前用户或模块不匹配，`8102`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |
| language | header | String | 否 | 弹窗文案语言，`zh` / `en` / `vi`，缺省中文；不识别时回退中文 |

**返回字段说明**

| 字段                | 类型      | 说明                                          |
| ----------------- | ------- | ------------------------------------------- |
| recordId          | Long    | 练习记录 ID                                     |
| alreadyUnlocked   | Boolean | 已解锁或卷内无可评分 AI 题时为 `true`，此时只看文案、不再引导支付      |
| price             | Integer | 本次消耗数量，来自权益中心的场景单价；已解锁时为 null               |
| vip               | Boolean | 会员赠送的 AI 次数大于 0 即为 `true`                   |
| freeCount         | Integer | 剩余免费解锁次数                                    |
| aiQuotaTotal      | Integer | AI 解析次数总余额（会员 + 永久）                         |
| examPointTotal    | Integer | 考试点数总余额（会员 + 永久）                            |
| recommendedMethod | String  | `free` / `ai_quota` / `exam_point` / `none` |
| content           | String  | 弹窗正文，已按语言填好数量                               |
| buttonLabel       | String  | 确认按钮文案                                      |
| bottomLabel       | String  | 底部余额栏名称；已解锁时为 null                          |
| bottomValue       | Integer | 底部余额栏数值；已解锁时为 null                          |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 900812,
    "alreadyUnlocked": false,
    "price": 1,
    "vip": false,
    "freeCount": 2,
    "aiQuotaTotal": 0,
    "examPointTotal": 0,
    "recommendedMethod": "free",
    "content": "新用户可免费解锁 2 次，本次将使用 1 次免费解锁，解锁后可查看本次练习的全部题目自然解析。",
    "buttonLabel": "免费解锁",
    "bottomLabel": "当前免费解锁次数",
    "bottomValue": 2
  }
}
```

`recommendedMethod` 的判定顺序与扣减顺序一致：`freeCount > 0` 取 `free`，否则看 `aiQuotaTotal > 0` 取 `ai_quota`，再看 `examPointTotal > 0` 取 `exam_point`，都为 0 取 `none`。

**本接口抛出错误码**：8102 / 8105 / 8133

---

#### 4.3.14 POST `{主观前缀}/{recordId}/unlock`

**用途**：执行解锁，扣减一次权益并把记录置为已解锁
**鉴权**：需要登录
**限流**：5 次/秒
**前置条件**：记录已交卷，否则 `8105`

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 是 | `writing` / `translation` / `speaking` |

无请求体。

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| recordId | Long | 练习记录 ID |
| aiUnlocked | Boolean | 恒为 `true` |
| deductType | Integer | 实际扣减方式：`0` 免费次数 / `1` AI 解析次数 / `2` 考试点数；扣费开关关闭时为 null |
| remainingFreeCount | Integer | 扣减后剩余免费次数，查询失败为 null |
| remainingAiQuota | Integer | 扣减后 AI 解析次数总余额，查询失败为 null |
| remainingExamPoint | Integer | 扣减后考试点数总余额，查询失败为 null |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 900812,
    "aiUnlocked": true,
    "deductType": 0,
    "remainingFreeCount": 1,
    "remainingAiQuota": 0,
    "remainingExamPoint": 0
  }
}
```

**幂等**：已解锁的记录重复调用直接返回成功，`deductType` 取库里已有的值，不再扣减任何权益。并发请求在行锁下串行执行，第二个请求进来时状态已是已解锁。

**失败处理**：三级权益都扣不到时抛 `8118`，本地不写解锁状态，用户可以购买后重试。解锁过程先扣减后写库，远程扣减成功而本地写库失败仍会多扣一次，这是接入外部计费服务的固有代价。

**本接口抛出错误码**：8102 / 8105 / 8118 / 8119 / 8133

---

**本族抛出错误码**：8101–8119（通用）、8201+（写作）、8251+（翻译）、8281+（口语）

### 4.4 首页模块卡、目录三跳与最近报告

本节 6 个端点服务首页与「模块 → 等级 → 卷列表 → 卷内板块」这条只读链路，以及板块卡片上的「上次成绩」入口。首页模块卡（§4.4.1）是进目录前的入口，等级备考说明（§4.4.4）是目录页内展示的内容，两者都不算一跳。它们与作答链路解耦：只读、不写库、不参与任何扣费与判分。

**通用规则**

- `module` 取值 `listening` / `reading` / `writing` / `speaking` / `translation`，大小写不敏感；缺失或不在白名单 → `8133`。§4.4.2 走路径段，其余走 query；§4.4.1 没有 `module` 参数
- `version` 缺省 `HSK2.0`，只认 `HSK2.0` / `HSK3.0`，其余 → `8131`
- 首页模块卡、目录三跳与等级说明（§4.4.1–§4.4.5）**免登录**：不带 token 时进度一律为未开始、`draft` 与 `report` 为 `null`；带有效 token 才回真实进度
- §4.4.6 需要登录，只查本人报告
- 对外路径与作答端点不同：首页模块卡、目录三跳与等级说明都是 `/hsk/...`，最近报告是 `/papers/...`（`/api/practice` 前缀由网关提供）

---

#### 4.4.1 GET `/hsk/modules`

**用途**：首页模块卡（进入目录前的一次性拉取）。按 `version` 返回布局、副标题与模块卡清单，前端照序渲染首页；点某张卡后再调 §4.4.2 拉该模块的等级
**鉴权**：免登录（响应里没有任何用户数据，不解析 token，也不需要 `X-Client-Type`）

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| version | query | String | 否 | `HSK2.0` / `HSK3.0`，缺省 `HSK2.0`；其余 → `8131` |
| Accept-Language | header | String | 否 | `zh` / `en` / `vi`，决定 `header` 与卡片名的取列 |

**请求示例**

```http
GET /practice/hsk/modules?version=HSK3.0
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
      { "moduleCode": "LISTENING", "sectionMapping": "SEC_LISTEN", "name": "听力", "nameEn": "Listening", "nameVi": "Nghe", "sortOrder": 1 },
      { "moduleCode": "READING", "sectionMapping": "SEC_READ", "name": "阅读", "nameEn": "Reading", "nameVi": "Đọc", "sortOrder": 2 },
      { "moduleCode": "WRITING", "sectionMapping": "SEC_WRITE", "name": "写作", "nameEn": "Writing", "nameVi": "Viết", "sortOrder": 3 },
      { "moduleCode": "TRANSLATION", "sectionMapping": "SEC_TRANSLATION", "name": "翻译", "nameEn": "Translation", "nameVi": "Dịch", "sortOrder": 4 },
      { "moduleCode": "SPEAKING", "sectionMapping": "SEC_SPEAK", "name": "口语", "nameEn": "Speaking", "nameVi": "Nói", "sortOrder": 5 }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| version | String | 解析后的版本，回显 |
| layout | String | `GRID_2`（2.0 两列卡片）/ `LIST`（3.0 单列列表），取字典里配置的布局 |
| header | String | 首页副标题：语言前缀 + ` · ` + 各卡片名按序用 `/` 拼接；卡片为空时只有前缀 |
| modules | Array | 模块卡，已按 `sortOrder` 升序，前端照序渲染；空数组表示该版本没有可用卡片 |
| modules[].moduleCode | String | 模块编码 `LISTENING` / `READING` / `WRITING` / `TRANSLATION` / `SPEAKING`，直接作为 §4.4.2 的 `module` 入参（服务端大小写不敏感） |
| modules[].sectionMapping | String | 板块归属 `SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` / `SEC_TRANSLATION` / `SEC_SPEAK` |
| modules[].name | String | 中文名 |
| modules[].nameEn | String | 英文名 |
| modules[].nameVi | String | 越南语名 |
| modules[].sortOrder | Integer | 卡片顺序 |

**下发口径**

- 三语名一并下发，前端按当前语言取一列；`header` 已由服务端按同一语言拼好，直接用，不要自己再拼
- 卡片清单由字典驱动：HSK2.0 为 `hsk_practice_module_v2` 四项（听力 / 阅读 / 写作 / 口语，无翻译），HSK3.0 为 `hsk_practice_module_v3` 五项（多翻译）。运营改字典的 `sort_order` 即改顺序，前端不要写死模块数量与排列
- 只下发「有哪些模块、叫什么、什么顺序」。可用性、卷数、进度一概不发——那三样要按模块再查等级开关、卷数、作答表，会让一个纯展示接口多打 6 次库，且与 §4.4.2 / §4.4.5 形成两套口径。前端点进模块后再取
- 不下发 `icon` / `theme` / `badge` / `entryLevelCode`：前端按 `moduleCode` 内置
- 字典查得到但为空（生产未灌数据）→ `modules = []` + 服务端 WARN，不报错；字典查询本身失败 → `500`

**服务端内部执行顺序**

1. 解析 `version`（缺省 `HSK2.0`，白名单外 → `8131`）
2. 按版本选字典码：`HSK3.0` → `hsk_practice_module_v3`，其余 → `hsk_practice_module_v2`
3. 一条查询取字典：`sys_dict` ⨝ `sys_dict_item`（`dict_code` 命中、两表 `deleted = 0`），按 `sort_order` 升序、`id` 次之
4. 逐行映射：`description` → `moduleCode`、`item_value` → `sectionMapping`、`item_text` → `name`、`item_properties.nameEn/nameVi` → 英文名 / 越南语名、`sort_order` → `sortOrder`（缺失按行号补）
5. 取布局：读 `sys_dict.remark` 里的 `layout` 键（库里存的是 JSON），取不到按版本缺省（2.0 `GRID_2` / 3.0 `LIST`）
6. 拼 `header`：语言前缀（`专项突破` / `Targeted Practice` / `Luyện chuyên sâu`）+ 卡片名
7. 无字典行 → `modules = []`，不报错

> 前端约定：首页只调本接口一次即可画完，不必按模块逐个请求。点卡片时把 `moduleCode` 原样传给 §4.4.2；`modules = []` 时显示空态，不要再调目录。

**本接口抛出错误码**：8131

---

#### 4.4.2 GET `/hsk/modules/{module}/levels`

**用途**：模块下的可用等级清单（目录第一跳）。点模块卡进入后按 `levels` 生成等级切换条，用户选中某一级再拉 §4.4.3 的卷列表
**鉴权**：免登录

**入参说明**

| 参数名             | 位置     | 类型     | 必填  | 约束&说明                                                                                  |
| --------------- | ------ | ------ | --- | -------------------------------------------------------------------------------------- |
| module          | path   | String | 是   | `listening` / `reading` / `writing` / `speaking` / `translation`，大小写不敏感；缺失或非法 → `8133` |
| version         | query  | String | 否   | `HSK2.0` / `HSK3.0`，缺省 `HSK2.0`；其余 → `8131`                                            |
| Accept-Language | header | String | 否   | `zh` / `en` / `vi`，决定 `levelName` 取哪一列                                                 |

**请求示例**

```http
GET /practice/hsk/modules/reading/levels?version=HSK3.0
Accept-Language: zh
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "module": "reading",
    "version": "HSK3.0",
    "levels": [
      { "level": "1", "levelName": "HSK1", "totalQuestionCount": 20, "durationMinutes": 17 },
      { "level": "2", "levelName": "HSK2", "totalQuestionCount": 25, "durationMinutes": 22 },
      { "level": "3", "levelName": "HSK3", "totalQuestionCount": 30, "durationMinutes": 30 },
      { "level": "4", "levelName": "HSK4", "totalQuestionCount": 32, "durationMinutes": 40 },
      { "level": "5", "levelName": "HSK5", "totalQuestionCount": 35, "durationMinutes": 45 },
      { "level": "6", "levelName": "HSK6", "totalQuestionCount": 40, "durationMinutes": 50 },
      { "level": "7", "levelName": "HSK7-9", "totalQuestionCount": 40, "durationMinutes": 50 }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| module | String | 模块编码，回显入参 |
| version | String | 解析后的版本，回显 |
| levels | Array | 可用等级，已按配置顺序排好，前端照序渲染；空数组表示该模块在该版本下没有可用等级 |
| levels[].level | String | 等级数字串 `1`–`7`，直接作为 §4.4.3 的 `level` 入参；`7` 表示 HSK7-9 整级 |
| levels[].levelName | String | 等级显示名，取 `practice_module_level_config` 的 `level_name` / `level_name_en` / `level_name_vi` 按 `Accept-Language` 三选一，不拼接、不换算 |
| levels[].totalQuestionCount | Integer | 该等级该模块的标准总题量（`total_question_count`），可用于 tab 副标题或级别介绍 |
| levels[].durationMinutes | Integer | 该等级建议时长，分钟（`suggested_duration_minutes`） |

**下发口径**

- 只下发 `enabled = 1` 的等级。
- `level` 不连续是正常现象：HSK3.0 口语从 `level = 3` 起配，只配到 `7`；HSK2.0 翻译没有配置，返回空数组。前端不要按 `1..N` 自造 tab
- `levelName` 必须取库列，不能按 `"HSK" + level` 拼：HSK2.0 口语三级配的是 `HSKK 初级` / `HSKK 中级` / `HSKK 高级`
- 不下发卷数。卷数要按等级逐级现算题量才准（7 个等级 7 次查卷），而选中等级的准确卷数由 §4.4.3 的 `paperCount` 给出
- 不重复下发模块名与图标：模块名、英文名、卡片顺序取首页 `GET /hsk/modules`，图标与横幅文案由前端内置，本接口只负责等级维度

**服务端内部执行顺序**

1. 解析 `module`（缺失或不在五模块白名单 → `8133`）、`version`（不在 `HSK2.0` / `HSK3.0` → `8131`）
2. 由 `module` 推 `section_mapping`（口语取 `SEC_SPEAK`，不兼容新值 `SEC_SPEAKING`，SEC_SPEAKING是脏值）
3. 查 `practice_module_level_config`：`version` + `section_mapping` + `deleted = 0` + `enabled = 1`，按 `sort_order` 升序、`level` 次之
4. 逐行映射 `level` 数字串、`levelName`（三语选一）、`totalQuestionCount`、`durationMinutes`
5. 无匹配行 → `levels = []`，不报错

> 前端约定：取 `levels[0].level` 作为默认选中等级；`levels` 为空时整页按「该模块暂无内容」处理，不要再调 §4.4.3。选中等级后，卷列表（§4.4.3）与该等级备考说明（§4.4.4，页面顶部介绍与「备考说明」弹窗的内容）并行拉取，说明接口不产生页面跳转。

**本接口抛出错误码**：8131 / 8133

---

#### 4.4.3 GET `/hsk/levels`

**用途**：等级概览 + 该等级全部卷及作答进度（目录第二跳，点等级 tab 即进入）
**鉴权**：免登录

**入参说明**

| 参数名             | 位置     | 类型     | 必填  | 约束&说明                                                            |
| --------------- | ------ | ------ | --- | ---------------------------------------------------------------- |
| module          | query  | String | 必传  | `listening` / `reading` / `writing` / `speaking` / `translation` |
| version         | query  | String | 否   | `HSK2.0` / `HSK3.0`，缺省 `HSK2.0`                                  |
| level           | query  | String | 否   | 等级数字串 `1`–`7`（`7` = HSK7-9 整级），缺省 `1`                            |
| Accept-Language | header | String | 否   | `zh` / `en` / `vi`，决定 `levelName` 取哪一列                           |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "module": "listening",
    "level": "3",
    "levelName": "HSK 三级",
    "paperCount": 2,
    "papers": [
      {
        "paperId": 100231,
        "paperCode": "HSK3.0 模拟卷一",
        "status": "IN_PROGRESS",
        "completedCount": 6,
        "totalCount": 40
      }
    ]
  }
}
```

**返回字段说明**

| 字段                      | 类型      | 说明                                                             |
| ----------------------- | ------- | -------------------------------------------------------------- |
| module                  | String  | 模块编码，回显入参                                                      |
| level                   | String  | 等级数字串，回显解析后的值                                                  |
| levelName               | String  | 等级显示名，取 `practice_module_level_config` 三列并按语言选一，不拼接、不换算        |
| paperCount              | Integer | 该等级卷数 = `papers` 长度；模块无内容时为 0                                  |
| papers                  | Array   | 该等级全部卷，元素见下                                                    |
| papers[].paperId        | Long    | 试卷 ID（口语为 `speaking_exam_paper.id`，其余为 `exam_paper.id`）        |
| papers[].paperCode      | String  | 试卷名称                                                           |
| papers[].status         | String  | `NOT_STARTED` / `IN_PROGRESS` / `COMPLETED`，未登录恒 `NOT_STARTED` |
| papers[].completedCount | Integer | 已作答题数（口语 = 已提交录音题数）；未登录恒 0                                     |
| papers[].totalCount     | Integer | 该模块在该卷下的总题数（已排除 `enabled_prac=0` 与示例题）                         |

**服务端内部执行顺序**

1. 解析 `module` / `version` / `level`，缺失或非法分别回 `8133` / `8131` / `8132`
2. 读 `practice_module_level_config`：等级未配置，或模块在该等级 `enabled=0` → 返回空目录（`paperCount=0`、`papers=[]`），不报错
3. 按版本 + 等级候选集取启用卷（`enabled_prac=1`、`exam_type=1`、`deleted=0`；口语走口语卷表），`7` 不要展开成 `('7','7-9')`只要 `7`
4. 逐卷现算该模块题量，题量为 0 的卷不进目录
5. 登录态下逐卷算进度；`userId == null` 时进度走 EMPTY 兜底，不查作答表
6. 组装并返回

**本接口抛出错误码**：8131 / 8132 / 8133

---

#### 4.4.4 GET `/hsk/levels/{level}/intro`

**用途**：等级备考说明（能力描述 + 板块结构），纯内容，无进度字段；在目录页内展示，不是一跳
**鉴权**：免登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| level | path | String | 是 | 等级数字串 `1`–`7` |
| module | query | String | 必传 | 五个模块码之一 |
| version | query | String | 否 | 缺省 `HSK2.0` |
| Accept-Language | header | String | 否 | `zh` / `en` / `vi` |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "module": "reading",
    "level": "3",
    "levelName": "HSK 三级",
    "abilityDescription": "能读懂日常生活中的简短材料……",
    "abilityDescriptionEn": "Can read short texts from daily life...",
    "abilityDescriptionVi": "Có thể đọc các văn bản ngắn...",
    "totalQuestionCount": 40,
    "durationMinutes": 30,
    "parts": [
      {
        "section": 1,
        "partName": "第一部分",
        "partNameEn": "Part 1",
        "partNameVi": "Phần 1",
        "typeCode": "read_choice",
        "typeName": "单项选择",
        "typeNameEn": "Multiple choice",
        "typeNameVi": "Chọn một đáp án",
        "questionCount": 10,
        "sortOrder": 1
      }
    ]
  }
}
```

**返回字段说明**

| 字段                      | 类型      | 说明                                    |
| ----------------------- | ------- | ------------------------------------- |
| module                  | String  | 模块编码，回显入参                             |
| level                   | String  | 等级数字串                                 |
| levelName               | String  | 等级显示名，按语言从配置表三列取一                     |
| abilityDescription      | String  | 能力描述（中文）                              |
| abilityDescriptionEn    | String  | 能力描述（英文）                              |
| abilityDescriptionVi    | String  | 能力描述（越南语）                             |
| totalQuestionCount      | Integer | 模块标准总题量                               |
| durationMinutes         | Integer | 建议总时长（分钟）                             |
| parts                   | Array   | 板块列表，无进度；等级未配置或模块关闭时为空数组              |
| parts[].section         | Integer | 板块号 1..N，后续作答与报告用它定位板块                |
| parts[].partName        | String  | 部分名（中文）                               |
| parts[].partNameEn      | String  | 部分名（英文）                               |
| parts[].partNameVi      | String  | 部分名（越南语）                              |
| parts[].typeCode        | String  | 题型编码（业务语义，不决定答题交互）                    |
| parts[].typeName        | String  | 题型名（中文）                               |
| parts[].typeNameEn      | String  | 题型名（英文）                               |
| parts[].typeNameVi      | String  | 题型名（越南语）                              |
| parts[].questionCount   | Integer | 该板块实际题量（现算，已排除 `enabled_prac=0` 与示例题） |
| parts[].sortOrder       | Integer | 排序号                                   |
| parts[].durationMinutes | Integer | 板块级建议时长（分钟）；只有口语下发，其余模块该键不出现          |


**服务端内部执行顺序**

1. 解析 `module` / `version` / `level`，非法分别回 `8133` / `8131` / `8132`
2. 读等级配置：未配置 → 只回 `module` / `level` / `parts=[]`；模块关闭 → 再补 `levelName`，`parts` 仍为空
3. 取该等级全部卷，按板块现算题量，同板块取各卷最大值；全空时回退 `standard_question_count`
4. 组装 `parts` 与三语文本后返回

**本接口抛出错误码**：8131 / 8132 / 8133

---

#### 4.4.5 GET `/hsk/papers/{paperId}/parts`

**用途**：卷内该模块的板块列表 + 每块进度（目录第三跳，点板块即开练）
**鉴权**：免登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| paperId | path | Long | 是 | 试卷 ID（口语为口语卷 ID，其余为 `exam_paper.id`） |
| module | query | String | 必传 | 五个模块码之一 |
| version | query | String | 否 | 传了就必须与该卷版本一致，否则 `8135` |

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "module": "speaking",
    "paperId": 200077,
    "paperCode": "HSK3.0 口语卷",
    "parts": [
      {
        "section": 1,
        "partName": "第一部分",
        "partNameEn": "Part 1",
        "partNameVi": "Phần 1",
        "typeCode": "speak_repeat",
        "typeName": "听后重复",
        "typeNameEn": "Repeat after listening",
        "typeNameVi": "Nhắc lại sau khi nghe",
        "questionCount": 10,
        "sortOrder": 1,
        "durationMinutes": 5,
        "status": "IN_PROGRESS",
        "doneCount": 4,
        "correctCount": null,
        "wrongCount": null,
        "report": { "id": 771201, "hasReport": false, "status": "GRADING" },
        "stats": { "recordedCount": 4, "scoredCount": 2, "unansweredCount": 6, "failedCount": 0 }
      }
    ]
  }
}
```

**返回字段说明**

| 字段                            | 类型      | 说明                                                             |
| ----------------------------- | ------- | -------------------------------------------------------------- |
| module                        | String  | 模块编码，回显入参                                                      |
| paperId                       | Long    | 试卷 ID                                                          |
| paperCode                     | String  | 试卷名称                                                           |
| parts                         | Array   | 板块列表，元素见下                                                      |
| parts[].section               | Integer | 板块号 1..N                                                       |
| parts[].partName              | String  | 部分名（中文）                                                        |
| parts[].partNameEn            | String  | 部分名（英文）                                                        |
| parts[].partNameVi            | String  | 部分名（越南语）                                                       |
| parts[].typeCode              | String  | 题型编码                                                           |
| parts[].typeName              | String  | 题型名（中文）                                                        |
| parts[].typeNameEn            | String  | 题型名（英文）                                                        |
| parts[].typeNameVi            | String  | 题型名（越南语）                                                       |
| parts[].questionCount         | Integer | 板块实际题量（现算）                                                     |
| parts[].sortOrder             | Integer | 排序号                                                            |
| parts[].durationMinutes       | Integer | 板块级建议时长（分钟），仅口语有值                                              |
| parts[].status                | String  | `NOT_STARTED` / `IN_PROGRESS` / `COMPLETED`，未登录恒 `NOT_STARTED` |
| parts[].doneCount             | Integer | 已作答题数（口语 = 已录音题数），未登录为 0                                       |
| parts[].correctCount          | Integer | 正确数；只在听力 / 阅读的已提交板块有值，写 / 译 / 说恒 `null`                        |
| parts[].wrongCount            | Integer | 错误数，规则同上                                                       |
| parts[].report                | Object  | 最近一次已出报告块，无则 `null`；子字段见下                                      |
| parts[].report.id             | Long    | 报告主键（听 / 读恒等于记录 ID）                                            |
| parts[].report.hasReport      | Boolean | 是否已有可看报告                                                       |
| parts[].report.status         | String  | `READY` / `GRADING` / `FAILED` / `UNAVAILABLE`；听 / 读恒 `READY`  |
| parts[].stats                 | Object  | 口语专属计数块，其余模块恒 `null`；子字段见下                                     |
| parts[].stats.recordedCount   | Integer | 已录音题数                                                          |
| parts[].stats.scoredCount     | Integer | 已评分题数                                                          |
| parts[].stats.unansweredCount | Integer | 未录音题数                                                          |
| parts[].stats.failedCount     | Integer | 录音或评分失败题数                                                      |

**服务端内部执行顺序**

1. 解析 `module` / `version`（`8133` / `8131`）
2. 定位卷：口语先查口语卷表，查不到回落 `exam_paper`（HSK7-9 口语走公共卷）；不存在、未启用、版本不符 → `8135`
3. 读该卷该模块的等级配置与板块行；等级配置缺失、模块关闭或板块为空 → `8138`
4. 逐板块现算题量
5. 登录态下逐板块算进度、草稿、最近报告；口语额外算 `stats`
6. 组装返回；`draft` / `report` / `stats` 无值时输出 `null`，不省略键

**本接口抛出错误码**：8131 / 8133 / 8135 / 8138

---

#### 4.4.6 GET `/papers/{paperId}/reports/latest`

**用途**：查某卷某板块最近一次已出报告，供板块卡片的「上次成绩」入口
**鉴权**：需要登录
**前置条件**：`module` 与 `section` 都必传，缺 `section` 回 `8137`；卷不存在回 `8140`；`version` 与卷不符回 `8136`

**入参说明**

| 参数名     | 位置    | 类型     | 必填  | 约束&说明                                                            |
| ------- | ----- | ------ | --- | ---------------------------------------------------------------- |
| paperId | path  | Long   | 是   | 试卷 ID                                                            |
| module  | query | String | 必传  | `listening` / `reading` / `writing` / `speaking` / `translation` |
| section | query | String | 必传  | 板块号，五个模块统一为数字：`1` / `2` / `3`…                                   |
| version | query | String | 否   | 传了就校验卷归属，不符回 `8136`                                              |

**返回字段说明（外层）**

| 字段 | 类型 | 说明 |
|---|---|---|
| module | String | 模块编码，回显入参，前端据此决定 `data` 用哪套字段 |
| data | Object | 该板块最近一份报告；该板块尚无报告时为 `null`，不报 404 |

`data` 的形状按 `module` 分四种，字段各自列全：

**`data`（listening、reading：报告摘要  §4.2.9 报告同结构）**

| 字段                | 类型         | 说明                                    |
| ----------------- | ---------- | ------------------------------------- |
| recordId          | Long       | 练习记录 ID                               |
| paperId           | Long       | 试卷 ID                                 |
| module            | String     | `listening` / `reading`               |
| sectionMapping    | String     | `SEC_LISTEN` / `SEC_READ`             |
| section           | String     | 板块号                                   |
| status            | String     | 状态枚举，报告场景恒 `SUBMITTED`                |
| totalQuestions    | Integer    | 题目总数                                  |
| answeredCount     | Integer    | 已答题数                                  |
| correctCount      | Integer    | 答对数                                   |
| wrongCount        | Integer    | 答错数（未作答计入错误）                          |
| accuracyRate      | BigDecimal | 正确率百分比，保留 2 位小数                       |
| durationSeconds   | Integer    | 用时秒数                                  |
| submittedTime     | Long       | 提交时间戳毫秒                               |
| rows              | Array      | 题号矩阵，元素见下                             |
| rows[].number     | Integer    | 题号，practice_record.question_ids数组下标+1 |
| rows[].questionId | Long       | 题目 ID                                 |
| rows[].answered   | Boolean    | 是否作答                                  |
| rows[].isCorrect  | Boolean    | 是否正确                                  |


**`data`（writing / translation / speaking：与 §4.3.10 报告同结构）**

| 字段                            | 类型         | 说明                                                                   |
| ----------------------------- | ---------- | -------------------------------------------------------------------- |
| recordId                      | Long       | 练习记录 ID                                                              |
| paperId                       | Long       | 试卷 ID                                                                |
| module                        | String     | `writing` / `translation` / `speaking`                               |
| sectionMapping                | String     | `SEC_WRITE` / `SEC_TRANSLATION` / `SEC_SPEAKING`                     |
| section                       | String     | 板块号                                                                  |
| status                        | String     | 枚举 `CREATED` / `IN_PROGRESS` / `ABANDONED` / `SUBMITTED`；库中存 0/1/2/3 |
| totalQuestions                | Integer    | 总题数                                                                  |
| answeredCount                 | Integer    | 已作答题目数                                                               |
| objectiveCount                | Integer    | 客观题数                                                                 |
| objectiveCorrectCount         | Integer    | 客观题答对数                                                               |
| aiQuestionCount               | Integer    | 需 AI 评分的题数                                                           |
| aiScoredCount                 | Integer    | AI 已评出分的题数                                                           |
| finalScore                    | BigDecimal | 当前总分                                                                 |
| totalScore                    | BigDecimal | 本卷满分                                                                 |
| durationSeconds               | Integer    | 累计在场秒数                                                               |
| startTime                     | Long       | 开练时刻（毫秒）                                                             |
| endTime                       | Long       | 交卷时刻（毫秒）；未交卷为 `null`                                                 |
| aiUnlocked                    | Boolean    | 解析是否已解锁                                                              |
| questions                     | Array      | 逐题摘要，元素见下                                                            |
| questions[].order             | Integer    | 题序 = 冻结下标 + 1                                                        |
| questions[].questionId        | Long       | 题目 ID                                                                |
| questions[].hasStandardAnswer | Integer    | 1 客观 / 0 主观                                                          |
| questions[].answered          | Boolean    | 是否已作答                                                                |
| questions[].gradingState      | Integer    | 0 待评 / 1 已评 / 2 未答或失败                                                |
| questions[].points            | BigDecimal | 得分；待评时为 `null`                                                       |
| questions[].maxScore          | BigDecimal | 单题满分                                                                 |
| questions[].isFullScore       | Integer    | 1 满分 / 0 非满分                                                         |
| questions[].correct           | Boolean    | 客观题对错；主观题恒 `null`                                                    |

**服务端内部执行顺序**

1. 解析 `module`（`8133`）与 `section`（`8137`）
2. 卷归属校验：`module = speaking` 先查口语卷表，查不到回落 `exam_paper`；两表都查不到 → `8140`；`version` 不符 → `8136`
3. **不校验 `enabled_prac`**：卷下架后历史报告仍要能看
4. 按三元组 `(paperId, section_mapping, section)` 直查该模块最近一条已提交记录／报告
5. 无报告时把各模块原有的「报告不存在」异常统一降级为 `data = null`，不报错
6. 返回 `{module, data}`

> `section` 必须和 `module` 一起传：HSK2.0 是综合卷，听力第 1 部分与阅读第 1 部分共用同一个 `paperId` 和 `section`，只用后两者无法定位唯一板块。

**本接口抛出错误码**：8133 / 8136 / 8137 / 8140

## 5. 错误码更新

| 错误码                | 服务               | 场景                                                                                                    |
| ------------------ | ---------------- | ----------------------------------------------------------------------------------------------------- |
| 8104               | practice-service | 【修改】`baseVersion` 与库里 `version` 不一致；本次对听读两个模块都强校验（原阅读只要求传、不校验）                                        |
| 8105               | practice-service | 【修改】客观报告未交卷、主观解锁预检与执行解锁要求记录已交卷，都回该码                                                                   |
| 8106               | practice-service | 【新增到本文档】客观报告重试前置不满足：`status ≠ 3` 或 `idempotency_key` 为空                                                        |
| 8131               | practice-service | 【新增到本文档】首页模块卡、目录三跳、等级说明与最近报告的 `version` 不在 `HSK2.0` / `HSK3.0` 之内                                              |
| 8132               | practice-service | 【新增到本文档】目录 `level` 不在 `1`–`7` 之内                                                                   |
| 8133               | practice-service | 【修改】合并路径后承担更多职责：`module` 缺失、取值不在白名单（作答端点按族区分白名单，目录与最近报告五个模块码全收）                                       |
| 8134 / 8137        | practice-service | 【新增到本文档】`paperId` 为空（服务层兜底，路径参数场景不会触发）/ 最近报告缺 `section`                                            |
| 8135 / 8138        | practice-service | 【新增到本文档】目录第三跳：卷不存在或未启用（8135）、该模块在该卷下没有板块（8138）                                                    |
| 8136               | practice-service | 【新增到本文档】最近报告的 `version` 与卷实际版本不符                                                                    |
| 8140               | practice-service | 【新增到本文档】最近报告查不到卷（`exam_paper` 与口语卷表都没有）                                                            |
| 8141 / 8142        | practice-service | 【无变更】听力续练时卷内容 / 板块配置已下架                                                                               |
| 8166 / 8167 / 8168 | practice-service | 【无变更】阅读试卷 / 板块不可练习、板块无题                                                                               |
| 8118               | practice-service | 【新增】解锁时免费次数、AI 解析次数、考试点数三级都不足                                                                         |
| 8119               | practice-service | 【新增】解锁状态写回冲突：扣减已完成但状态位被行锁之外的写操作改过                                                                     |

## 6. 前端对接注意事项

1. **路径一次性切换，没有过渡期**：旧路径（`/listening/records/**`、`/reading/records/**`、`/writing/records/**`、`/translation/records/**`、`/speaking/records/**`，含五条答题卡）已全部下线，请求会返回 `404`。前端必须在同一版本内改完所有调用点，并给每个请求补 `module`。
2. **听力字段名有 4 处改动**，是本次唯一的破坏性变更：`no` → `number`、`audio_url` → `audioUrl`、`option_content` → `optionContent`、`share_audio_url` → `shareAudioUrl`；答案请求字段 `selectedOptionId` → `answer`。
3. **阅读选项结构简化**：`optionContent` 从 `{"options":{"A":"…"}}` 变成 `{"A":"…"}`，取选项少拆一层。
4. **`baseVersion` 必传且两个模块都校验**：取自记录响应的 `version`。听读任一模块传旧版本都回 `8104`，前端应就地刷新记录后重发，不要静默吞掉。
5. **报告页只写一套**：交卷、查报告、报告重试返回同一结构 = 顶部摘要 + 题号矩阵 `rows`。`items` 已不再下发，单题明细与解析走逐题回顾端点，不要按旧字段取值。
6. **客观报告不再有 `reportStatus` / `retryable`**：报告能不能看只取决于 `status = SUBMITTED` 与 `rows` 是否有值；重试按钮的前置条件与后端一致（未交卷不给重试），重试后重新拉一次报告即可。
7. **答题卡只表态不判对错**：`questions[]` 只有 `order` / `questionId` / `answered` / `current`，当前题用响应里的 `currentQuestionNumber`，也可用 query 传入覆盖。
8. **口语板块域**：新数据用 `SEC_SPEAKING`；若前端有硬编码 `SEC_SPEAK` 的分支，本次要一并改（服务端两种都接受）。
9. **主观题报告多了一个解锁步骤**：报告与单题反馈新增 `aiUnlocked`，为 `false` 时解析需要用户主动解锁。后端不再替你遮挡内容，`analysis` 字段有值但**不应直接渲染**，必须先判 `aiUnlocked`，否则付费墙形同虚设。
10. **解锁弹窗文案由后端下发**：`content` / `buttonLabel` / `bottomLabel` / `bottomValue` 直接渲染即可，不要在客户端拼「将消耗 N 次」这类句子，服务端已按 `language` 头和实际余额填好。`recommendedMethod = none` 时按钮应跳权益中心而不是调 unlock。
11. **交卷不再因余额不足被拦**：旧版交卷前会校验权益，现在交卷只看作答与判分，未解锁只影响报告页的解析展示。
12. **目录三跳与等级说明都免登录，别用 401 拦自己**：不带 token 也能拉 `modules/{module}/levels` / `levels` / `intro` / `parts`，此时进度字段为未开始、`draft` 与 `report` 为 `null`；带有效 token 自动带进度。`parts[].draft.id` 就是 `recordId`，直接拿去调 `resume` 继续练习。
13. **首页只调 `GET /hsk/modules` 一次**：布局、副标题、卡片名与顺序都由它给出，2.0 是四张卡（无翻译）、3.0 是五张（多翻译），按 `modules` 原序渲染并直接用 `moduleCode` 进 §4.4.2。不要在前端写死五张卡，也不要在首页逐个模块查等级。
14. **等级 tab 由第一跳决定，不要写死**：进入模块先拉 `GET /hsk/modules/{module}/levels`，按 `levels` 原序渲染并默认选中第一项。HSK3.0 口语从 HSK3 起配、HSK2.0 口语是 `HSKK 初级/中级/高级`、HSK2.0 翻译没有等级，按 `HSK1`–`HSK6` 写死会漏项或点进空页；`levels = []` 时直接显示「暂无内容」，不要再调第二跳。
15. **最近报告的 `data` 按模块分形状**：先看 `module` 再取值，并且必须判 `data == null`（该板块还没报告，服务端不报 404）。

## 7. 关键业务流程&事务边界

### 7.1 合并后的分层

```
Controller（2 族 6 个类 + 4 个跨族只读类）
  ├─ 客观族：ObjectiveRecordController / ObjectiveAnswerController / ObjectiveReportController
  ├─ 主观族：SubjectivePracticeController
  └─ 跨族只读：PracticeHomeController（首页模块卡）/ PracticeCatalogController（目录三跳 + 等级说明）
               PracticeReportController（最近报告）/ AnswerCardController（五模块答题卡）
      ↓ 模块解析（ObjectiveModuleResolver / SubjectiveModuleResolver）
门面层（ObjectivePracticeService；主观族直接复用 SubjectivePracticeService）
      ↓ 分派 + DTO 转换
实现层（听 / 读各一套 service，写 / 译 / 说共用一套）
```

**为什么客观族保留两套实现**：取题口径不同 —— 听力按 `question_ids` 回 `question` 表现查，阅读直接读 `practice_answer` 冻结快照。合并实现会把这条差异变成 `if (module == READING)`，反而更难维护。

### 7.2 事务边界

| 操作 | 事务 | 要点 |
|---|---|---|
| 开练（客观） | `@Transactional` | 行锁查未提交记录 → 校验卷与板块配置 → 取题冻结 → 插记录 + **逐题插作答占位行** |
| 开练（主观） | `@Transactional` | 按 `userId` 查进行中记录（不加锁）→ 校验卷 → 冻结题集 → 插记录；**不建占位行**，占位行在首次保存作答或交卷时补 |
| 保存草稿（主观） | `@Transactional` | 不锁记录 → 校验题在冻结题集内 → 版本比对 → 只写草稿三列，不碰 `answered` / `grading_state` / `points` |
| 单题 / 批量保存（客观） | `@Transactional` | 锁记录 → 锁答案行 → 写答案 → 重算 `answeredCount`，同一事务 |
| 单题 / 批量保存（主观） | `@Transactional` | 行锁记录 → 逐条 upsert 作答 → 按模块落列（口语 `answer`，写作与翻译 `answerText`）→ 重算 `answeredCount` 与进度 |
| 暂停 / 恢复（两族） | `@Transactional` | 时长结算与位置更新同事务；`resume` 清 `paused_time` 必须走显式 UPDATE 并同时写 `resumed_time` |
| 交卷（客观） | `@Transactional` | 落 `finalAnswers` → 比对标准答案判分 → 写对错与 `points` → 汇总统计 → 置 `status = 3`（`SUBMITTED`）、`end_time`、结算在场时长，同一事务；幂等命中直接返回 |
| 交卷（主观） | `@Transactional` | 落 finalAnswers → 冻结快照 → 客观题即判、主观题置待评 → 写统计与 `idempotency_key` → `afterCommit` 投递 AI。**报告状态不落库**（表里没有该列），读时按逐题 `grading_state` 现算 |
| 报告重试（客观） | `@Transactional` | 前置 `status = 3`（`SUBMITTED`）且 `idempotency_key` 非空（否则 `8106`）→ 按冻结快照重算统计与矩阵；不改记录状态 |
| 判分重试（主观） | `@Transactional` | 一条 SQL 重置入选行的 `grading_state` 与退避字段 → `grading_attempts + 1` → `afterCommit` 重新投递；不改报告状态（现算） |
| 解锁（主观） | `@Transactional` | 行锁查记录 → 校验已交卷与归属 → 三级扣减（远程，不参与本地事务）→ 写 `ai_deduct_state=1` + `deduct_type` + `ai_deduct_time`。先扣后写，扣失败抛 8118 回滚，行锁串行化并发请求 |
| 详情 / 拉题 / 报告读取（两族） | 无事务 | 只读、不加锁；`aiUnlocked` 在读时按 `ai_deduct_state` 现算 |
| 首页模块卡、目录三跳、等级说明 / 最近报告（§4.4） | 无事务 | 只读、不加锁、不写库；未登录走 EMPTY 进度兜底；最近报告把各模块「无报告」异常统一降级为 `data = null` |

### 7.3 时长口径（未变，重申）

- 结算点只有 `pause` 与 `submit`；`resume` 只推进段起点、不累加
- 段起点 = `max(start_time, paused_time, resumed_time)`
- 单段上界 1800s，只防崩溃，不防作弊以外的场景
- `pause` / `submit` 请求体一律无 `durationSeconds`

## 8. 验收测试用例

| # | 场景 | 预期结果 |
|---|---|---|
| 1 | `POST /hsk/objective/records/start?module=listening` | 返回 `module=listening`、`version=1` |
| 2 | `POST /listening/records/start`（旧路径） | `404`，路径已下线 |
| 3 | `POST /hsk/objective/records/start`（不带 module） | `8133` |
| 4 | `POST /hsk/objective/records/start?module=writing` | `8133`（不在客观族白名单） |
| 5 | 听力拉题 | `number` / `optionContent` 扁平 / `audioUrl` 驼峰；`group` 为 null |
| 6 | 阅读拉题 | `group` 与 `optionContent`（扁平）都有；`layout` 为 null |
| 7 | 听力批量保存传错 `baseVersion` | `8104` |
| 8 | 阅读批量保存传旧 `baseVersion` | `8104`（两个模块都强校验） |
| 9 | 听力交卷 | 返回摘要 + `rows`，逐题带 `answered` / `isCorrect`，响应里没有 `items` |
| 10 | 阅读交卷 | 同上：摘要 + `rows`，题号为 `question_ids` 下标 + 1 |
| 11 | 未交卷时调客观报告重试 | `8106`；已交卷且幂等键非空 → 200，重算后 `rows` 完整 |
| 12 | `POST /hsk/subjective/records/start?module=translation` | 正常开练 |
| 13 | `POST /hsk/subjective/records/{id}/report/retry?module=translation` | 200，失败题重新入队 |
| 14 | `POST /hsk/subjective/records/{id}/questions/1/answers?module=writing` | 200，落 `answer_text` |
| 15 | `POST /hsk/subjective/records/{id}/questions/1/answers?module=speaking` | 200，落 `answer` + `duration_ms` |
| 16 | 同一记录用同一幂等键交卷两次 | 第二次直接返回已有结果，不重复判分 |
| 17 | `/hsk/objective/records/{id}/answer-card?module=reading` | 200，返回阅读答题卡；`/reading/records/{id}/answer-card` 回 `404` |
| 18 | 同一试卷同一板块，未提交时再调 `start` | 返回同一条记录，`recordId` 与进度不变 |
| 19 | 已交卷后调 `start` | 新建一条记录，`recordId` 与上次不同，进度归零 |
| 20 | 主观题交卷后查报告（未解锁） | `aiUnlocked=false`，`analysis` 与 `standardAnswer` 仍有值，不返回锁定占位文案 |
| 21 | 未解锁时调 `GET /{recordId}/unlock/precheck?module=writing` | 200，`recommendedMethod` 按「免费 → AI 次数 → 点数」顺序取第一个有余额的 |
| 22 | 有免费次数时调 `POST /{recordId}/unlock` | 200，`deductType=0`，`ai_deduct_state` 置 `1`，再查报告 `aiUnlocked=true` |
| 23 | 三级权益都为 0 时调 `POST /{recordId}/unlock` | `8118`，`ai_deduct_state` 仍为 `0`，报告 `aiUnlocked` 仍为 `false` |
| 24 | 已解锁后再调一次 `POST /{recordId}/unlock` | 200，`deductType` 与首次一致，余额不再减少 |
| 25 | 卷内全客观题交卷后查报告 | `aiUnlocked=true`（`ai_deduct_state=3`），不需要解锁 |
| 26 | `GET /hsk/levels?module=listening&level=3`（不带 token） | 200，`papers[].status` 全为 `NOT_STARTED`、`completedCount` 全 0 |
| 27 | `GET /hsk/levels?module=writing&version=HSK4.0` | `8131` |
| 28 | `GET /hsk/papers/{paperId}/parts?module=speaking`（不带 token） | 200，`parts[].draft` 与 `report` 为 `null`，`stats` 按口语口径有值 |
| 29 | `GET /hsk/papers/{paperId}/parts?module=reading`，该卷无阅读板块 | `8138` |
| 30 | `GET /papers/{paperId}/reports/latest?module=listening&section=1`，该板块从未练过 | 200，`module=listening`、`data=null` |
| 31 | 同一端点缺 `section` | `8137` |
| 32 | 最近报告：`module=writing` 且有已交卷记录 | 200，`data` 按主观报告形状返回，含 `aiUnlocked` |
| 33 | `GET /hsk/modules/reading/levels?version=HSK3.0`（不带 token） | 200，`levels` 共 7 项，依次 `1`–`6` + `7`（`HSK7-9`） |
| 34 | `GET /hsk/modules/writing/levels?version=HSK3.0` | 200，6 项：HSK1 那行 `enabled=0`，不出现 |
| 35 | `GET /hsk/modules/speaking/levels?version=HSK2.0` | 200，3 个等级，`levelName` 为 `HSKK 初级` / `HSKK 中级` / `HSKK 高级`（不是 `HSK1`–`HSK3`） |
| 36 | `GET /hsk/modules/translation/levels`（缺省 HSK2.0） | 200，`levels=[]`，不报 404 |
| 37 | `GET /hsk/modules/reading/levels?version=HSK4.0` / `GET /hsk/modules/xxx/levels` | `8131` / `8133` |
| 38 | `GET /hsk/modules?version=HSK2.0`（不带 token） | 200，`layout=GRID_2`，`modules` 共 4 项，顺序为听力 / 阅读 / 写作 / 口语，无 `TRANSLATION` |
| 39 | `GET /hsk/modules?version=HSK3.0`，`Accept-Language: en` | 200，`layout=LIST`，`modules` 共 5 项，`header` 为 `Targeted Practice · Listening/Reading/Writing/Translation/Speaking` |
| 40 | `GET /hsk/modules`（不带 `version` 与 `Accept-Language`） | 200，`version=HSK2.0`，`header` 为 `专项突破 · 听力/阅读/写作/口语` |
| 41 | `GET /hsk/modules?version=hsk3.0`（小写） | `8131`（版本白名单大小写敏感，不静默降级） |

## 9. 上线执行事项【P0阻断项】

### 9.1 存量数据补数 SQL

**无**。本次无 DDL、无数据订正。

口语板块域的历史拼写 `SEC_SPEAK` 未订正（服务端两种都接受），如需统一见 §10。

### 9.2 文件级变更清单

| 文件路径 | 改动内容 |
|---|---|
| `hsk/objective/api/enums/ObjectiveModule.java` | 【新增】客观族模块枚举 |
| `hsk/objective/api/dto/*.java`（14 个） | 【新增】客观族统一 DTO |
| `hsk/objective/api/support/ObjectiveModuleResolver.java` | 【新增】模块解析，只认 `module` 参数，缺失 / 非法回 8133 |
| `hsk/objective/api/support/ObjectiveDtoMapper.java` | 【新增】两套内部 DTO → 统一契约转换 |
| `hsk/objective/api/service/ObjectivePracticeService.java` + `impl` | 【新增】门面分派 |
| `hsk/objective/api/controller/*.java`（3 个） | 【新增】客观族 11 个端点（答题卡端点另计，见下方 `AnswerCardController` 行） |
| `hsk/subjective/api/controller/SubjectivePracticeController.java` | 【新增】写 / 译 / 说 12 个端点合一 |
| `hsk/subjective/api/support/SubjectiveModuleResolver.java` | 【新增】模块解析，只认 `module` 参数，缺失 / 非法回 8133 |
| `listening/controller/*.java`（3 个） | 【删除】由客观族控制器接管 |
| `reading/controller/*.java`（3 个） | 【删除】同上 |
| `subjective/controller/{Writing,Translation,Speaking}PracticeController.java` | 【删除】由主观族控制器接管 |
| `hsk/answer/enums/AnswerCardModule.java` | `SPEAKING` 板块域改 `SEC_SPEAKING`，新增 `fromCodeOrNull`，`pathSegment` 字段更名 `code` |
| `hsk/answer/controller/AnswerCardController.java` | 【修改】删除五条按模块的旧路径，只保留两条合并路径 |
| `hsk/answer/service/impl/AnswerCardServiceImpl.java` | 注释订正（`SEC_SPEAKING` 为官方值） |
| `listening/dto/ListeningRecordResponse.java`、`reading/dto/ReadingRecordResponse.java` | 新增 `version` 字段 |
| `listening/service/impl/ListeningRecordServiceImpl.java`、`reading/service/impl/ReadingRecordServiceImpl.java` | `toResponse` 回填 `version` |
| `hsk/support/HskPracticeErrorCode.java` | 删除 `MODULE_ENDPOINT_NOT_SUPPORTED(8120)`，模块级端点限制取消后无引用 |
| `hsk/subjective/api/enums/AiUnlockState.java` | 【新增】解锁状态枚举，含 `isUnlocked` / `needsUnlock` 判定 |
| `hsk/subjective/api/dto/SubjectiveUnlockPrecheckResponse.java` | 【新增】解锁预检响应 |
| `hsk/subjective/api/dto/SubjectiveUnlockResponse.java` | 【新增】解锁结果响应 |
| `hsk/subjective/api/config/SubjectiveUnlockProperties.java` | 【新增】解锁扣费开关 `subjective.unlock.deduct-enabled` |
| `hsk/subjective/api/service/SubjectiveUnlockService.java` + `impl` | 【新增】预检与解锁，含三级扣减链 |
| `hsk/subjective/api/controller/SubjectivePracticeController.java` | 【修改】新增 `unlock/precheck` 与 `unlock` 两个端点 |
| `hsk/subjective/api/service/impl/SubjectivePracticeServiceImpl.java` | 交卷去掉权益预检；报告与单题反馈回填 `aiUnlocked` |
| `hsk/subjective/grading/SubjectiveGradingService.java` | 评分完成后不再触发扣费，只重算统计 |
| `hsk/subjective/grading/SubjectiveAiDeductService.java` | 【删除】由 `SubjectiveUnlockService` 接管 |
| `common/mapper/PracticeSubjectiveRecordMapper.java` + XML | `casAiDeductState` / `markAiDeductType` 合并为 `markAiUnlocked` |
| `hsk/report/controller/PracticeReportController.java` | 【新增】板块最近报告统一端点 `GET /papers/{paperId}/reports/latest`，替代原四条按模块的 `/{{mod}}/parts/{structureId}/reports/latest` |
| `hsk/report/service/PracticeReportQueryService.java` + `impl` | 【新增】`module` + `section` 必传，按三元组直查各模块报告；「无报告」统一降级为 `data = null` |
| `hsk/report/dto/LatestReportResponse.java` | 【新增】外层 `{module, data}`，`data` 按模块分形状 |
| `hsk/catalog/controller/PracticeCatalogController.java` | 【新增】`GET /hsk/modules/{module}/levels` 第一跳端点；`/hsk/modules`（无路径变量）仍归 `PracticeHomeController`，两者为并列路径 |
| `hsk/catalog/service/PracticeCatalogService.java` + `impl` | 【新增】`moduleLevels`：按 `version` + `section_mapping` + `deleted = 0` + `enabled = 1` 读等级配置，不发额外查询 |
| `hsk/catalog/dto/PracticeModuleLevelsResponse.java`、`PracticeModuleLevelItem.java` | 【新增】第一跳响应与等级行（`level` / `levelName` / `totalQuestionCount` / `durationMinutes`） |
| `hsk/catalog/controller/PracticeHomeController.java` | 【无变更】首页模块卡 `GET /hsk/modules`，本次只补进文档，代码与响应结构不动 |
| `hsk/catalog/service/PracticeHomeService.java` + `impl`、`mapper/PracticeHomeMapper.java` + XML、`dto/PracticeHomeResponse.java`、`PracticeModuleCard.java`、`PracticeModuleDictRow.java` | 【无变更】字典驱动的一次查询，`layout` 取 `sys_dict.remark`，空白字典降级为空卡片 |
| `hsk/catalog/**`（其余目录端点控制器 / 服务 / DTO） | 【无变更】路径与响应结构不动 |
| `csca/controller/CscaFavoriteController.java` | 补回缺失的类闭合大括号（原本导致全模块编译失败） |

### 9.3 环境状态

- 编译：主源 349 文件 + 测试源 46 文件，**0 错误**
- 单测：`374 tests / 374 passed / 0 failed`
- TEST / PROD：未部署（本次仅代码与文档）

## 10. 待确认事项

| # | 待确认点 | 暂定方案 | 确认人 |
|---|---|---|---|
| 1 | 前端切换窗口 | 旧路径已下线，需与后端同版本上线 | 前端 |
| 2 | 阅读 `baseVersion` | 已拍定：两个模块都强校验，不一致回 `8104` | 后端 |
| 3 | 是否订正 `SEC_SPEAK` 存量配置（24 + 8 行） | 暂不订正，服务端双值兼容 | DBA / 后端 |
| 4 | 客观报告是否还需要 `items` | 已拍定：不再下发，单题明细走逐题回顾端点 | 产品 |
| 5 | 网关白名单登记 | 必须登记 `/hsk/objective/**`、`/hsk/subjective/**`、`/hsk/modules`、`/hsk/modules/*/levels`、`/hsk/levels`、`/hsk/papers/**`、`/papers/**`，并确认旧前缀已从白名单移除；首页模块卡、目录三跳与等级说明免登录放行 | 运维 |
| 6 | 最近报告路径缺 `/hsk` 段 | 现为 `/papers/{paperId}/reports/latest`（对外 `/api/practice/papers/...`），与目录三跳的 `/hsk/...` 不齐；是否统一成 `/hsk/papers/{paperId}/reports/latest` 待定 | 前后端 |
| 7 | 最近报告的板块域取值 | 口语报告按 `SEC_SPEAK` 直查；若新记录按决策 10 写 `SEC_SPEAKING`，会出现查不到，候选集是否改为 `IN ('SEC_SPEAK','SEC_SPEAKING')` 待定 | 后端 / DBA |
| 8 | 阅读最近报告是否也砍掉 `items` | 最近报告复用阅读原有模型（带 `items`），与 §4.2.9 收敛后的结构不一致；暂按现状双口径，是否统一待定 | 产品 / 前端 |
