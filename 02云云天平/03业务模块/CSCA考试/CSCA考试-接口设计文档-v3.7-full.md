# CSCA 考试 · 接口设计文档

> **所属模块**：`exam-service`（端口 **8084**，网关前缀 `/api/exam/**`，`StripPrefix=2` 后落到服务内路径）
> **业务范围**：CSCA（`exam_paper.exam_type = 2`）**整卷模考** —— 5 个原始科目（文科中文 / 理科中文 / 数学 / 物理 / 化学）× 语言（中文 / English，实测仅中文卷），**一次考试 = 随机抽一张整卷**。与「练习按科目刷单题」是两条独立链路。
> **交互依据**：TAPD wiki《CSCA考试》**v1.3.0**（编写人 梁倩，2026-07-02）+ **10.28 调整**（成绩单预览/下载、免费次数上限 1 + 邀请奖励 2、跳转答题页扣减 1 次且续考不重复扣）+ **11 月调整**（收藏/错题/考试记录同步、免费次数用完可用点数参加）→ 逐条对齐见 [0.8](#08-与需求文档tapd-wiki的对齐)
> **数据依据**：测试库 `xuexitest`（`8.138.185.11`）实测 2026-10-19（31 张 CSCA 卷 / 1904 题 / 136 条 CSCA 考试记录）
> **状态**：**设计稿 v3.7 / 2026-10-22**，🔒 **成绩单改为「前端生成 → 上传 → 后端只存链接」**（`exam_record.report_url` 早已存在，下载端点 302），服务端不再产出任何 CSCA PDF，见 [3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接)；🔒 **开考前资料校验改为真调 auth `GET /api/auth/app/profile/check`**（单一真源，fail-closed），见 [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验)；🔒 **成绩单输出口径已按官方模板锁定** —— `data.schema.json` 是唯一契约，后端只做「填表」不自造字段，见 [3.6.2](#362--get-recordexamrecordidscorereportpreview)，🔬 **已用真实请求核对过 TEST 后端**（见 [4.9 联调实测记录](#49-联调实测记录2026-10-22真调-test-后端)）。🔒 **考试次数方案 = B 方案（每科各 3 次）**，见 [3.2.1](#321--改造-post-answerstartcsca)；🔒 **标记与收藏已拆开**（标记复用 `paper/tag`、收藏新增 `POST /answer/csca/favorite`），见 [3.3.4](#334--新增-post-answercscafavorite--考试内收藏)；🔒 **错题本 = 考试侧只写不读**（交卷时写 `csca_question_wrong`，读/移出/复习走练习模块，零新增端点），见 [3.7](#37-错题本考试侧只写不读)；🔒 **成绩单姓名 = 开考快照**（开考前 `8104` 硬拦 5 项资料、开考写 `real_name`），5 科→4 值「文理中文都印中文」已定；🔒 **`queryExamInProgress` 入参校验按分支拆**（HSK 强制 `version`+`level`、CSCA 两项都不强制，实测 CSCA 传参确实 `500 等级不能为空`），见 [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验)；🔒 **`/answer/batch`、`/answer/statistics` 前端零调用 → 明确不用**；🔒 **`leave` 改判为复用**；**代码尚未改动**，等排期。
> **先读哪一节**：想知道**这批接口到底新增了什么功能** → 直接看 [1.0 功能清单](#10-功能清单这批接口新增了什么)；想知道**某个页面调哪个接口** → [1.2 场景对照](#12-场景--接口对照表)；想知道**实测到底返回什么** → [4.9 联调实测记录](#49-联调实测记录2026-10-22真调-test-后端)。

---

### 本文档 v2 相对 v1 的修正（重要）

v1 把 CSCA 考试设计成**另起 `/csca/**` 命名空间的 15 个全新端点**——这是错的，因为 `exam-service` 里**这些能力大部分已经存在**。v2 改为：

> **「能改不建」**：优先**原地改造现有端点**（URL、返回包装、老前端调用方式全部不变），只有**代码里确实没有的能力才新增端点**。

| | v1（作废） | **v2（本文）** |
|---|---|---|
| 端点总数 | 15 个全新 `/csca/**` | **21 个在用（🔧改 10 / ✅复用 7 / 🆕新增 4）+ 2 个明确不用**（`/answer/batch`、`/answer/statistics`）。<br>🔴 v2.9 据前端实测校正：`leave` 由「⛔停用」改「✅复用」、`batch`/`statistics` 由「改造/复用」改「⛔前端 0 调用」；v3.6 再 +1 新增（`POST /record/{id}/scoreReport` 存成绩单链接） |
| URL | 全部换新 | **现有 URL 一律不动** |
| 老 App | 需等新版本 | **老版本继续可用**（改造是向后兼容的字段新增 + 行为修正） |
| 新增端点 | 15 | **4**：`GET /record/csca/quota`（5 科剩余次数，**接现成的 `user_exam_quota`**）、`GET /record/{examRecordId}/scoreReport/preview`（成绩单 JSON 预览）、`POST /record/{examRecordId}/scoreReport`（**存前端上传的成绩单链接**，v3.6）、`POST /answer/csca/favorite`（考试内收藏） |
| 考试次数限制 | 新造「免费次数 + 会员赠送点数 + 点数包」三级扣减 + `PointAccountClient` | **直接复用 HSK 现成的 `user_exam_quota`**（同一张表、同一套 Mapper），只加 `exam_type='CSCA'` 的行；🔒 **已定 B 方案：`level` = 科目码，5 科各 3 次（一人 5 行）**；点数体系**本期不做**，只留扩展位 |

🔴 **v1 里 3 个"新设计"其实是重复造轮子，v2 已废弃**：

| v1 端点 | 代码里早已存在的等价实现 | v2 处置 |
|---|---|---|
| `GET /csca/records/{recordId}/report` | `GET /record/csca/{examRecordId}/result`（`CscaExamResultDTO` **已含** 成绩卡 + `questionCards[]` 逐题对错 + `avgTimePerQuestionText` + `timeEvaluation`） | 废弃，改造现有端点 |
| `GET /csca/records/{recordId}/questions/{questionId}/analysis` | `GET /record/{paperId}/question/{questionId}?examRecordId=`（`ExamResultDTO.QuestionResult` 已含用户答案/标准答案/解析） | 废弃，改造现有端点 |
| `GET /csca/records` | `GET /record/user/records`（`ExamRecordDetailDTO` **已含** `subjectType` / `languageVersion`） | 废弃，改造现有端点 |

---

> 🔴 **四个必须先拍板的硬缺口**（不解决本功能上不了线，见 [4.3](#43-待确认事项)）：
> ① **点数（权益中心）模块不存在，但「考试次数限制」是现成的** —— HSK / HSKK 早已用 `user_exam_quota` 实现「次数校验 + 扣减」（`hasAvailableQuota` / `decrementQuotaByUser`，见 [3.2.1](#321--改造-post-answerstartcsca)）。CSCA **复用同一张表**，锁 **B 方案**：`level` 存科目码，每科一份；**不新造点数账本**（库中零点数/订单表），点数只留扩展位。
> ② **理科中文（`science_chinese`）当前考不了** —— 枚举没问题（`common/CSCASubjectType` **已含 5 值**），卡在**数据层**：`exam_paper_structure` 只配了 4 个科目（**缺 science_chinese**），取结构必抛「试卷结构不存在」。库里有 5 张卷、400 道题。
> ③ **建会话不扣次数** —— `startCscaExam`（`ExamRecordServiceImpl:269`）**没有一行配额代码**（HSK 的 `startExam:119` 前置校验 + `:235` 扣减）。现在**任何人可无限考**。
> ④ **考试中能直接拿到全部答案** —— `getCscaPaperDetailWithAnswers`（:1809）把 `question.answer` / `question.analysis` 一并下发。

---

## 目录

- [0. 通用约定](#0-通用约定)
- [1. 用户操作流程与接口对照](#1-用户操作流程与接口对照)
- [2. 接口总览](#2-接口总览)
- [3. 接口详细设计](#3-接口详细设计)
- [4. 附录](#4-附录)

---

## 0. 通用约定

### 0.1 返回包装

所有接口统一返回 `com.hsktreasure.common.result.Result<T>`（**只有 `code` / `message` / `data` 三个字段**），**HTTP 状态码恒为 200**，业务结果看 `code`：

```json
{ "code": 200, "message": "操作成功", "data": { } }
```

- `code` = `200` 成功；非 200 见 [0.5 错误码](#05-错误码)
- `data` 为 `null` 时字段仍保留（不省略）
- 异常统一由 `common` 的 `GlobalExceptionHandler` 兜住（`ExamServiceApplication` 的 `@ComponentScan` 已覆盖 `com.hsktreasure.common`）
- ⚠️ **唯一例外是成绩单 PDF**（[3.6.3](#363--改造-get-recordexamrecordidscorereport--csca-改读已上传的-pdf)）：返回 `application/pdf` 二进制流，**不套 `Result`**

### 0.2 鉴权与客户端类型

沿用 `BaseController#getCurrentUserId(request, clientType)`：

| 场景 | 要求 |
|---|---|
| **全部端点**（含 🆕 `GET /record/csca/quota`） | **必须登录**，未登录抛 `BusinessException(401, "未登录或Token无效")` |

- 客户端类型头：`X-Client-Type: APP`（CSCA 考试是 App 端功能）
- Token 顺序：`Authorization: Bearer xxx` → `X-Access-Token` → `?token=`
- **`userId` 一律从 Token 取，绝不由前端传入**（防刷别人的考试、防替人扣次数）
- ✅ **网关 `ignore.whites` 无需新增任何 CSCA 路径**：本模块**没有免登录端点**（原 v2.1 要加 `/api/exam/paper/csca/catalog` 一行，随 `catalog` 撤销一并取消）。科目卡走 `system-service` 的字典接口（它本来就在白名单惯例内），次数接口 `GET /record/csca/quota` **需要登录**

### 0.3 「语言版本」`languageVersion` 与界面文案是两件事

| 概念 | 载体 | 取值 | 作用 |
|---|---|---|---|
| **试卷语言版本** | `exam_paper.language_version`（**业务数据**） | `chinese` / `english` | 决定**抽到哪一批卷** |
| **界面文案** | 前端字典 | 中文 / English / 越语 | 服务端**不管** |

- 🔴 **中文科目只支持中文卷**（需求 2.1）：`arts_chinese` / `science_chinese` 传 `english` → `8102`；前端把 English 开关**置灰**
- ⚠️ **实测 31 张 CSCA 卷 `language_version` 全是 `chinese`**，没有一张英文卷。`languageVersion` 做成**必填参数**，不猜缺省

### 0.4 ID 序列化

🔴 **`exam-service` 当前没有开 `Long → String`**：`common/config/JacksonConfig.java` 的 `ToStringSerializer` **被整段注释掉**（`practice-service` 自己那份是开的）。所以 `/record/*`、`/answer/*` 返回的 id **都是 JSON 数字**。

本版口径（**最小变更**）：

| 端点类别 | id 类型 | 理由 |
|---|---|---|
| **🔧 改造的现有端点** | **保持数字**（`Long`） | 老前端已按数字解析，改成字符串是破坏性变更 |
| **🆕 新增的 2 个端点** | **声明为 `String`** | 新字段无历史包袱，19 位雪花 id 在 JS 端不丢精度 |

> ⚠️ **遗留风险**：同一个 `examRecordId`，在 🆕 `scoreReport/preview` 里是字符串、在 `/record/**` 老端点里是数字。**须前端按端点分别解析**，或后续统一开 `exam-service` 自己的 `JacksonConfig`（会波及 HSK，见 [4.3](#43-待确认事项) 第 16 条）。

### 0.5 错误码

🔴 **本模块新开号段 `8101–8199`**（`CSCA_*` 练习占 8001–8099、`COURSE_*` 占 7001–7099，互不冲突）。通用码复用 `ErrorCode`：

| 业务码 | 值 | 含义 | 触发场景 |
|---|---|---|---|
| `SUCCESS` | 200 | 成功 | — |
| `PARAM_ERROR` | 400 | 参数错误（兜底） | 未细分的参数问题 |
| **`CSCA_EXAM_SUBJECT_INVALID`** | **8101** | 科目码非法 | `subjectTypeMapping` 不在考试 5 科内 |
| **`CSCA_EXAM_LANGUAGE_INVALID`** | **8102** | 语言非法 / 该科目不支持 | 值不在 `CSCALanguageVersion` 内；或中文科目传 `english` |
| **`CSCA_EXAM_PAPER_EMPTY`** | **8103** | 该科目×语言暂无可用试卷 | 无卷；或**卷在但 `exam_paper_structure` 无模板**（理科中文现状） |
| **`CSCA_EXAM_PROFILE_INCOMPLETE`** | **8104** | 个人信息不完整（**开考硬门槛**） | **5 项**：姓名 / 性别 / 国籍 / 出生年月日 / 手机号。🔒 **判定接口 = auth `GET /api/auth/app/profile/check`**（v3.6 起真调，不再本地复刻；**不含邮箱**）；`data.incompleteFields` 直接透传该接口返回的中文名 |
| **`CSCA_EXAM_QUOTA_EXHAUSTED`** | **8105** | **该科目**考试次数不足 | `user_exam_quota(exam_type='CSCA', version='CSCA', level=<科目码>)` 那一行 `remain_quota <= 0`，**或该科目根本没有配额行**（与 HSK `hasAvailableQuota` 语义一致：查不到也算没次数）。⚠️ 只看**当前科目**，不是看总额 |
| ~~`CSCA_EXAM_POINT_CONFIRM_REQUIRED`~~ | ~~8106~~ | ~~需要二次确认扣点~~ | **本期不用**（点数体系不存在）。码位预留给后续「免费次数用完、改用点数参加」的实现 |
| **`CSCA_EXAM_SESSION_NOT_FOUND`** | **8107** | 会话不存在 | `examRecordId` 查不到 / 不是 CSCA 记录。⚠️ **不含归属校验**——报告出口刻意允许非答题者查看（[3.5.1](#351--改造-get-recordcscaexamrecordidresult)） |
| **`CSCA_EXAM_SESSION_NOT_IN_PROGRESS`** | **8108** | 会话已结束 | 已交卷的会话仍保存答案 / 仍取卷 |
| **`CSCA_EXAM_SESSION_EXPIRED`** | **8109** | 会话已超时 | `now > deadline_time`，**已在本请求内自动交卷** |
| **`CSCA_EXAM_QUESTION_NOT_IN_PAPER`** | **8110** | 题目不属于本卷 | `questionId` 不在会话题集内（**跨卷篡改的主要出口**） |
| **`CSCA_EXAM_NOT_SUBMITTED`** | **8111** | 未交卷不能看报告 | `status = 0` 的会话请求报告 / 成绩单 |
| **`CSCA_EXAM_PARAM_OUT_OF_RANGE`** | **8112** | 参数越界 | `pageSize > 100` / 批量 > 200 条 / `answer` 长度 > 64 |
| **`CSCA_EXAM_REPORT_UNAVAILABLE`** | **8113** | 成绩单**数据**不可用 | `preview` 拼装失败：空卷 / 统计不自洽 / 姓名为空 / `score ∉ [0,100]` → **宁可报错，也不要前端白屏**。🔴 v3.6 起**不再表示"PDF 渲染失败"**（服务端已不生成 PDF） |
| **`CSCA_EXAM_REPORT_NOT_READY`** | **8114** | 成绩单尚未生成 | `GET /record/{id}/scoreReport` 时 `exam_record.report_url` 为空（🆕 v3.6，前端应先走 preview → 生成 → 上传 → 保存） |
| **`CSCA_EXAM_REPORT_ALREADY_EXISTS`** | **8115** | 成绩单已存在，不允许覆盖 | `POST /record/{id}/scoreReport` 时 `report_url` 已有值且 `overwrite≠true`（🆕 v3.6） |
| **`CSCA_EXAM_REPORT_URL_INVALID`** | **8116** | 成绩单链接非法 | `reportUrl` host 不在白名单 / 不含 `examRecordId` / 超 1000 字符 / 非 `http(s)`（🆕 v3.6，**防钓鱼外链与串号**） |
| `UNAUTHORIZED` | 401 | 未登录 / Token 无效 | 见 [0.2](#02-鉴权与客户端类型) |
| `FORBIDDEN` | 403 | 无权限 | `X-Client-Type` 非 `APP` |
| `FAILED` | 500 | 服务端错误 | 未预期异常 |

> ✅ **落地位置**：新增 `exam-service/.../exam/csca/support/CscaExamErrorCode`（**模块自有码表，不进 `common` 的 `ErrorCode`**），带 `toException()` / `toException(String detail)`。
> ⚠️ **改造端点保持向后兼容**：老的错误码（如 `BusinessException(500, "考试记录不存在")`）在**不冲突的前提下**逐步替换为新码，但**不得把 500 改成 8107 再让老前端崩**——如需切换，先跟前端约好灰度窗口。

### 0.6 枚举与判定口径

**判定 CSCA 试卷的唯一口径**（三条件同时成立）：

```
exam_paper.exam_type = 2        -- 2 = CSCA（1 = HSK）
exam_paper.version   = 'CSCA'   -- 实测 31 张卷全部为 'CSCA'
exam_paper.deleted   = 0
```

**本模块不设「内容版本号」**：题目、选项、材料**每次实时读题库**；考试**没有题面快照**，交卷后报告按**当前题库**回放（理由见 [4.3](#43-待确认事项) 第 6 条）。

**「答案不进考试内容接口」是一条硬约束**（**没有例外**）：

| 接口产出 | 含标准答案？ | 含解析？ |
|---|---|---|
| 科目目录 / 次数概览 | **否** | 否 |
| 整卷（`GET /answer/paper/csca/detail/{paperId}`） | **否** | **否** |
| 答题卡 | **否** | 否 |
| 交卷结果 | **否**（只回数字） | 否 |
| 诊断报告 / 单题详情 / 成绩单 | **是**（交卷后才允许） | **是** |

> 🔴 **现有 `getCscaPaperDetailWithAnswers` 两个字段都在下发**（`ExamRecordServiceImpl` 内 `.answer(question.getAnswer())` / `.analysis(question.getAnalysis())`），本模块**必须先修的 P0**（[4.4](#44-现状--目标差异清单) 第 3 条）。
> 🔴 **现有 `AnswerSubmitRequest.isCorrect` 由客户端传且直接落库**（`examAnswer.setIsCorrect(request.getIsCorrect())`）—— **CSCA 分支**必须**忽略该字段**并恒置 0（[4.4](#44-现状--目标差异清单) 第 4 条）。
> ⚠️ **`/answer/submit` 是与 HSK 共用的接口，改造必须只对 `exam_type=2` 生效**：HSK 前端靠这个字段做答题中的即时对错反馈，且 HSK 交卷后由 `AsyncGradingServiceImpl:76-101` 异步重判覆盖，最终成绩不依赖它 → **HSK 分支保持原逻辑，一行不改**（[3.3.2](#332--改造-post-answersubmit) 改造点第 2 条的「分支前提」）。

### 0.7 与 HSK 考试链路的差异（为什么不能照抄 `/record/start`）

| # | 维度 | HSK 考试 | CSCA | 后果 |
|---|---|---|---|---|
| 1 | 分类轴 | `exam_paper.level`（1–6 / 7-9）+ `version` | **`level` 全为 `NULL`**；分类轴是 **`subject_type_mapping` + `language_version`** | 抽卷 SQL 必须按科目×语言（`selectByCscaParams` / `selectUntakenPaperCSCA`），**不能**用 `selectUntakenPaper(version, level, …)` |
| 2 | 卷结构 | `exam_paper_structure` 按 `(version, hsk_level)`，多 `content_type` | 按 **`(version, subject_type_mapping)`**，**只有一行 `SEC_READ`**，**没有分部计时** | `exam_section_timer` 对 CSCA **形同虚设**（`question.section_mapping` 为 `NULL`）；计时走**整卷倒计时** |
| 3 | 题型 | 听力/阅读/写作/口语，含主观题 | **全客观选择题**（`type_id`：单选 1069 / 多选 35 / 识解汉字 100 / 选词填空 150 / 辨析词语 80 / 补全语句 220 / 选词成段 150 / 阅读理解 200），**多选答案形如 `A,D`** | 判分必须**集合比较**；异步批阅链路（`AsyncGradingService`）**不参与** |
| 4 | 判分时机 | 交卷后**异步批阅** | **交卷同步判分**，`status` 恒 `0 → 1` | 交卷响应即含全部数字，**不需要** `grading_progress` 轮询 |
| 5 | 抽卷 | 未考过的卷 `LIMIT 1`（顺序取） | **随机抽一张没考过的卷**（`ThreadLocalRandom`）；全考过则**清空 `user_taken_paper` 后重抽** | 天然轮换到不同卷 |
| 6 | 一卷题量 | 25 / 30 / 40 / 45 题不等 | **文/理中文 80 题、数理化 48 题**；满分**均 100.00** | 全卷一次下发（80 题 ≈ 30–35 KB），不做分页 |
| 7 | 计时 | 分部分计时 | **整卷倒计时**（文/理中文 **90**、数理化 **60** 分钟） | 新增 `exam_record.deadline_time`，服务端权威超时 |
| 8 | 报告 | HSK 成绩报告（分段 + `weakness_report`） | **CSCA 官方水平测试报告样式** | 报告 DTO 已有（`CscaExamResultDTO`）；PDF **要新写**（`ScoreReportPdfServiceImpl` 是 HSK 专用） |
| 9 | 考试次数限制 | `user_exam_quota`：`exam_type='HSK'`，`version='HSK2.0'`，`level` 固定 `'1'`；`hasAvailableQuota` 校验 + `decrementQuotaByUser` 扣减（**均不带 `level`**） | **同一张表、同一套 Mapper**，只加 `exam_type='CSCA'`、`version='CSCA'` 的行。🔒 **B 方案**：`level` = 科目码 → 每科一行、各 3 次；🔴 **不能用 `decrementQuotaByUser`**（无 `level`，会 5 行一起扣）→ 用 `getQuota(4参)` 取 id + `decrementQuota(id)`（**都已存在**，只加 2 个薄重载） | 库中 CSCA **0 行**，上线前必须发次数（**每人 5 行**）；点数体系**不做** |

**CSCA 卷结构实测**（`exam_paper_structure where version='CSCA'`，**只有 4 行**）：

| subject_type_mapping | content_type | content_name | duration_minutes | full_score | question_count |
|---|---|---|---|---|---|
| `arts_chinese` | `SEC_READ` | 阅读 | **90** | 100.00 | 80 |
| `math` | `SEC_READ` | 阅读 | **60** | 100.00 | 48 |
| `physics` | `SEC_READ` | 阅读 | **60** | 100.00 | 48 |
| `chemistry` | `SEC_READ` | 阅读 | **60** | 100.00 | 48 |
| ~~`science_chinese`~~ | **缺失** | — | — | — | — |

### 0.8 与需求文档（TAPD wiki）的对齐

**页面结构**（本模块覆盖范围）：

```
CSCA 模块（顶部 考试 / 练习 两个 Tab；本模块只管「考试」，默认进考试 Tab）
 ├─ ① 考试首页：5 个科目卡（默认选中「中文（文科）」）+ 语言开关（中文/English）+【开始模拟考试】
 ├─ ② 答题页：mm:ss 倒计时 ｜ **收藏（★）** ｜ **标记** ｜ 答题卡 ｜ 上一题/下一题（末题变「交卷」）+ 独立交卷按钮
 │     ⚠️ ★ 与「标记」是**两个按钮**：★ 写 `csca_question_favorite`（长期），标记写 `exam_answer.is_tag`（本场）
 ├─ ③ 答题卡弹窗：总题数 / 已答 / 未答 / 标记；网格（红=当前 绿=已答 黄=标记 空=未答）
 ├─ ④ 交卷确认弹窗：总题数 / 已答 / 未答 / 标记题数
 ├─ ⑤ 诊断报告：成绩卡（总分/总题/已答/用时/平均用时）+ 答题概览网格 + 逐题解析弹窗 + 【下载成绩单】【重新考试】
 ├─ ⑥ 成绩单预览：CSCA 官方样式 +【下载 PDF】
 └─ ⑦（我的 → 学习与测试）模考记录 / 收藏夹 / 错题本 —— 记录列表由 [3.6.1](#361--改造-get-recorduserrecords) 提供；
        收藏夹 / 错题本**不在本模块**，走 `practice-service` 的 `/api/practice/csca/favorites`、`/api/practice/csca/wrong-book`（同表、`source='exam'`）
```

**需求 → 本文落点**

| 需求条目 | 本文落点 | 关键口径 |
|---|---|---|
| 1.3 / 4.1 默认选中「中文（文科）」+ 中文 | **`GET /api/system/dict/code/csca_subject`**（现有） | 字典 `sortOrder` 1–5 = 文科中文 → 理科中文 → 数学 → 物理 → 化学；`isDefault=1` 落在 `arts_chinese` → **前端取它作默认**，不硬编码 |
| 2.1 中文科目仅中文 | 前端常量（需求写死）+ 库中 **0 张英文卷** | `arts_chinese` / `science_chinese` 只出中文卷；其余三科虽有 English 开关，但**没有英文卷** → 前端整体置灰，导入后再放开（[4.3](#43-待确认事项) 第 13 条） |
| 2.2 不实时判分 / 4.2 选完只变色不判对错 | [3.3.2](#332--改造-post-answersubmit) | 只落 `answer` + `answered`，**恒不碰 `is_correct` / `points`** |
| 2.3 倒计时切后台不暂停 / 归零自动交卷 | [3.4.1](#341--改造-post-recordpaperidsubmitcsca) | 服务端 `deadline_time` 权威；超时**惰性 + 定时**双兜底 |
| 2.4 每答一题即时保存 / 退出后再进自动恢复 | [3.3.2](#332--改造-post-answersubmit) + [3.2.1](#321--改造-post-answerstartcsca) | 建会话前先查「同 user + 科 + 语言 的 `status=0` 会话」→ 命中即**直接续考、不扣次数** |
| 2.5.1 免费次数：初始 1 + 邀请 2 = 上限 3 | [3.2.1](#321--改造-post-answerstartcsca) 次数校验 | **复用 `user_exam_quota`**：`exam_type='CSCA'` / `version='CSCA'` / `level=<科目码>`（🔒 **B 方案：一人 5 行，每科 3 次**），与 HSK 行**天然隔离**（`exam_type` 不同）；行由**发次数链路**写入（[4.3](#43-待确认事项) 第 3 条），本模块只读 + 扣 |
| 2.5.2 扣减顺序：免费 → 会员赠送点数 → 点数包点数；单次 2 点 | **本期不实现**（[4.3](#43-待确认事项) 第 1 条） | 点数/权益中心**全库未实现**；本期口径 = **剩余次数 `remain_quota <= 0` 即 `8105`**。后续接点数时只需在 `8105` 之前插一段，不动接口形状 |
| 2.5.2 仅「点开始模拟考试且成功建会话」时扣 | [3.2.1](#321--改造-post-answerstartcsca) | 前置查询**只读不扣**；建会话在**同一事务**内扣，**以 UPDATE 影响行数判定成功**（`remain_quota > 0` 条件，天然防并发） |
| 2.5.2 续考不重复扣 | [3.2.1](#321--改造-post-answerstartcsca) 第 2 条 | 幂等键 = `(user, subject, language, status=0)`；命中即**直接返回原会话、不进扣减分支** |
| 2.5.2 扣减记录溯源 | [3.2.1](#321--改造-post-answerstartcsca) 第 6 条 | 次数扣减靠 `user_exam_quota.used_quota` 累计；`exam_record.deduct_type` 记**扣减来源**（本期恒 `1` = 免费次数），`deduct_amount` 恒 `0`（不扣点） |
| 2.5.3 免费/付费会话都支持直接导出成绩单 | [3.6.2](#362--get-recordexamrecordidscorereportpreview) / [3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接) / [3.6.3](#363--改造-get-recordexamrecordidscorereport--csca-改读已上传的-pdf) | 🔒 **读取时不校验 `report_unlocked`**（CSCA 无付费解锁）；**写入时置 `1`** 表示「已有成绩单文件」，供记录列表判断按钮态 |
| 2.5.4 历史报告不受次数变动限制 | [3.5.1](#351--改造-get-recordcscaexamrecordidresult) | 报告只看「会话存在 + 已交卷」，**与余额无关** |
| 2.6 收藏/错题同步到「我的-学习与测试」 | 收藏：🆕 [3.3.4](#334--新增-post-answercscafavorite--考试内收藏)<br>错题：[3.7](#37-错题本考试侧只写不读)（写入在 [3.4.1](#341--改造-post-recordpaperidsubmitcsca) 第 6 步） | 收藏落 `csca_question_favorite`（`source='exam'`，**用户主动**）；错题落 `csca_question_wrong`（`source='exam'`，**判错自动**）；两者读侧都在 practice-service，前端传 `source=exam` |
| 4.1 开始前校验个人信息 **5 项**（含**姓名**） | [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) | 缺项回 `8104` + `incompleteFields`，前端弹窗 + 跳个人中心。🔒 **姓名是硬门槛**：成绩单 `candidate.name` 是模板唯一必填的考生信息 |
| 4.1 次数不足引导（买次数/联系客服），不建会话 | [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) `action=QUOTA_EXHAUSTED` | 建会话侧仍是 `8105`（双保险） |
| 4.2 收藏 / 标记独立于作答 | 🆕 [3.3.4](#334--新增-post-answercscafavorite--考试内收藏) | 收藏**不进 `exam_answer`**、不受 `answered` 影响；**标记仍走** `POST /answer/paper/tag`（写 `is_tag`，不改） |
| 4.3 答题卡颜色四态 | [3.3.5](#335--改造-get-answercscacarddetailpaperid) | 回 `answered` / `isTag` / `favorite` / `current` 四个布尔：**四色由前三个 + 未答算出**（黄=标记），★ 用 `favorite`，两者独立 |
| 4.4 交卷弹窗的四项统计 | [3.3.5](#335--改造-get-answercscacarddetailpaperid) | 第四项「标记题数」= 🆕 `tagCount`（`is_tag=1` 的题数）；⚠️ **不是 `favoriteCount`**（收藏是另一套长期资产） |
| 4.5 诊断报告字段 | [3.5.1](#351--改造-get-recordcscaexamrecordidresult) | `CscaExamResultDTO` **已覆盖**，补 `usedTimeText` / `autoSubmitted` |
| 4.6 成绩单预览 + PDF | [3.6.2](#362--get-recordexamrecordidscorereportpreview) / [3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接) / [3.6.3](#363--改造-get-recordexamrecordidscorereport--csca-改读已上传的-pdf) | 预览给**官方模板 JSON 原样**（前端 `CSCAReport.render` 一行出图）；PDF **前端生成 → 上传 → 回存链接**，下载端点 `302` 到该链接（[4.3](#43-待确认事项) 第 24 条 v3.6 已定案） |
| 5 异常：题库为空 Toast | [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) `paperCheck.available=false` + [3.2.1](#321--改造-post-answerstartcsca) `8103` | 文案由前端出 |
| 5 异常：倒计时以服务器时间为准 | 全篇 | 每个会话接口都回 `remainingSeconds`（服务端算），**不接受客户端报时** |
| 5 异常：交卷失败不丢作答 | [3.3.2](#332--改造-post-answersubmit) | 每题即时落库；交卷可重试（幂等）。🔴 断网补传**不走 `/answer/batch`**（前端未实现、实测 500），改为逐题重发 `/answer/submit` |
| 6 题目唯一 ID = 科目\|语言\|序号 | [3.3.1](#331--改造-get-answerpapercscadetailpaperid) | ⚠️ **不采纳**：对外主键仍是 `question.id`，另回 `number`（卷内题号 1–80） |
| 6 进度存储：题序/作答/收藏/当前题位 | [3.2.1](#321--改造-post-answerstartcsca) | `exam_record.current_question_number`（保存答案时更新）+ `exam_answer` + 收藏表 |

### 0.9 现有代码盘点（基线）

> **本文一切设计从这张表出发**。表中「代码位置」格式为 `Controller#方法 → ServiceImpl:行号`。

**CSCA 相关端点（现有，16 个）**

| # | 端点 | 代码位置 | 现状能力 | v2 处置 |
|---|---|---|---|---|
| 1 | `GET /paper/list/csca?version=&subjectTypeMapping=&languageVersion=` | `ExamPaperMainController:48` → `ExamPaperService#listByCscaParams` | 按科目×语言列卷 | ✅ **复用**（管理端/联调） |
| 2 | `GET /paper/csca/detail?paperId=` | `ExamPaperMainController:63` → `#getCscaPaperDetail` | 卷详情：总题数 / 时长 / 总分 | ✅ **复用** |
| 3 | `GET /paper/structure/version/{version}` | `ExamPaperStructureController:29` | 卷结构模板 | ✅ **复用** |
| 4 | `POST /answer/queryExamInProgress` | `ExamAnswerController:52` → `ExamRecordServiceImpl:241` | 查进行中考试（**只支持 HSK**：`version` + `level` 非空强校验写死在方法头部） | 🔧 **改造**（校验按分支拆：HSK 保持强制 / CSCA 两项都不强制 + 次数/资料校验） |
| 5 | `POST /answer/start/csca` | `ExamAnswerController:70` → `ExamRecordServiceImpl:269` | 抽随机卷 + 建 `exam_record` + `initAnswerCard` + 写 `user_taken_paper` | 🔧 **改造**（参数校验 / 扣次数 / `deadline_time`） |
| 6 | `GET /answer/paper/csca/detail/{paperId}` | `ExamAnswerController:226` → `ExamRecordServiceImpl:1809` | 整卷 + 分组 + 用户答案 | 🔧 **改造**（🔴 剔除答案/解析） |
| 7 | `POST /answer/submit` | `ExamAnswerController:103` → `ExamAnswerService#submit` | 单题保存 | 🔧 **改造**（补 `exam_record_id` / **CSCA 分支**忽略 `isCorrect`） |
| 8 | `POST /answer/batch` | `ExamAnswerController:116` → `#batchSubmit` | 批量保存 | ⛔ **不用**（前端 0 调用；实测传标准 `{paperId,answers[]}` 直接 `500 系统内部错误`） |
| 9 | `POST /answer/paper/tag` | `ExamAnswerController:238` → `#tag` | 标记（写 `exam_answer.is_tag`，HSK 共用） | ✅ **复用**（**语义不变、一行不改**；收藏另开新端点） |
| 10 | `GET /answer/csca/card/detail/{paperId}` | `ExamAnswerController:157` → `#getCSCAAnswerCardDetail` | 答题卡（`is_tag` 当标记，**无收藏态**） | 🔧 **改造**（补 `favorite` / `tagCount` / NPE / `remainingSeconds`） |
| 11 | `GET /answer/statistics/{paperId}` | `ExamAnswerController:171` | 答题统计 | ⛔ **不用**（前端 0 调用；实测 `totalQuestions=25` 而卷是 48 题，数据本身不准） |
| 12 | `GET /answer/checkSubmit/{paperId}` | `ExamAnswerController:184` | 交卷前检查（`canSubmit` / 未答列表） | ✅ **复用**（交卷弹窗数据） |
| 13 | `POST /record/{paperId}/submit/csca` | `ExamRecordController:68` → `ExamRecordServiceImpl:555` | 交卷 + 同步判分 | 🔧 **改造**（🔴 多选判分 / 幂等 / 未答口径 / 错题同步） |
| 14 | `GET /record/csca/{examRecordId}/result` | `ExamRecordController:92` → `ExamRecordServiceImpl:759` | 诊断报告（`CscaExamResultDTO`） | 🔧 **改造**（补 `autoSubmitted` / `id` 置 `null`；**不加 `userId` 校验，by design**） |
| 15 | `GET /record/{paperId}/question/{questionId}?examRecordId=` | `ExamRecordController:104` | 单题详情（答案 + 解析） | 🔧 **改造**（交卷后也能查） |
| 16 | `GET /record/user/records` | `ExamRecordController:127` → `ExamRecordServiceImpl:1111` | 记录列表（分页 + 时间 + 源码/等级筛） | 🔧 **改造**（CSCA 字段 / 全量默认） |
| 17 | `GET /record/{examRecordId}/scoreReport` | `ExamRecordController:177` → `ScoreReportPdfService` | 成绩单 PDF（**HSK 专用版式**） | 🔧 **改造**（按 `exam_type` 分流） |
| 18 | `POST /record/{paperId}/leave` | `ExamRecordController:162` → `#leaveExam` | 暂离（写 `exam_record.leave_at / leave_question_id / leave_question_number / answered_duration_on_leave / leave_section_mapping`，回 `ExamRecordResponse`） | ✅ **复用**（🔴 **v2.9 改判**：前端 `ExamApiProvider#leaveExam` **正在调用**，body `{questionNumber, section, questionId?}`；实测 `200 已暂离考试`。原「⛔ 停用」结论作废 —— 停用它等于把 App 切后台/切题的行为断掉） |
| 19 | `GET /number/examTicket` | `ExamNumberController:33` | 准考证号 | ✅ **复用** |

**代码里完全没有、必须新建的（2 个）**

| # | 新增端点 | 为什么必须有 |
|---|---|---|
| A | `GET /record/csca/quota` | 首页 5 张科目卡要**每科剩余次数**。`user_exam_quota` 在 exam-service 里**没有任何批量出口**——唯一查询端点是口语模块的 `POST /speaking/quota`（单科、返回实体原样），CSCA 不复用它。**纯读现表，不新增存储** |
| B | `GET /record/{examRecordId}/scoreReport/preview` | 需求 4.6 成绩单**预览页**要结构化数据（前端渲染官方样式）；现有只有 PDF 二进制（#17），前端拿不到字段 |
| C | `POST /answer/csca/favorite` | 需求 2.6「收藏同步」要求考试内的 ★ 能进「我的-学习与测试-收藏夹」。现有 `POST /answer/paper/tag` 是**标记**（写 `exam_answer.is_tag`，一场考试一份），**不是收藏**，且 HSK 共用不能改语义 → 只能新增 |

> 📌 **科目清单不需要新端点**：`GET /api/system/dict/code/csca_subject`（**现有**）已给出 5 个科目 + 顺序（`sortOrder` 1–5）+ 默认项（`isDefault=1` 在 `arts_chinese`），前端直调即可 —— 这正是原 `GET /paper/csca/catalog` 被撤销的原因：它想聚合的 6 块数据里，科目来自字典、续考由 `startCscaExam` 自动返回、资料在 [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 校验，只剩下**次数**必须由 exam-service 提供。
> `POST /speaking/quota` 属**口语模块**，**不复用、不改动**（[3.1.3](#313--不复用-post-speakingquota--csca-次数只走-get-recordcscaquota)）——**HSK / HSKK / Proficiency 一行不改**。

**已有的 CSCA 基础设施（不要重造）**

| 已有 | 说明 |
|---|---|
| `CSCAExamRecordRequest` | 建会话入参（`version` / `subjectTypeMapping` / `languageVersion`）—— **已够用**，只需加校验注解 |
| `ExamRecordResponse` | 建会话/交卷返回（含 `status` / `finalScore` / `correctCount` / `duration` / `leave*`）—— **已够用**，本版加 `deadlineTime` / `remainingSeconds` / `deductType` |
| **`user_exam_quota` + `UserExamQuotaService` + `UserExamQuotaMapper`** | **考试次数限制整套现成**（HSK / HSKK 在生产用）。B 方案要用到的件**全部已存在**：<br>· `selectByUserIdAndExamType(userId, examType, version, **level**)` —— **本来就带 level**（`status=1 AND deleted=0`）<br>· `decrementQuota(id, updatedTime)` —— 带 `remain_quota > 0` 守卫 + 刷 `updated_time`，且 Service 已封装成 `decrementQuota(Long quotaId): boolean`<br>🆕 只差 **2 个薄重载**：`getQuota` / `hasAvailableQuota` 各加一个 4 参（带 `level`）版本，实现就是调上面那个**已有的** `selectByUserIdAndExamType`。<br>🔴 **禁用 `decrementQuotaByUser`**（`WHERE` 无 `level` → B 方案下一次扣掉 5 科） |
| `CscaExamResultDTO` | 诊断报告（**已含** `score` / `totalScore` / `questionCards[]` / `avgTimePerQuestionText` / `timeEvaluation`）—— **已覆盖需求 4.5 绝大部分** |
| `ExamRecordDetailDTO` | 记录列表元素（**已含** `subjectType` / `subjectTypeText` / `languageVersion` / `durationText`）—— **已够用** |
| `ExamPaperDetailDTO` | 整卷（**已含** `sections[]` / `groups` / `userAnswers`）—— 改造时删两个字段即可 |
| `AnswerCardDetailDTO` | 答题卡（**已含** `questions[]` 网格态）—— 改造时补 `favorite` / `remainingSeconds` |
| `ExamSubmitCheckDTO` | 交卷前检查（`canSubmit` / `unansweredQuestions[]`）—— **直接复用** |
| `ExamPaperMapper#selectUntakenPaperCSCA` / `selectByCscaParams` | 抽卷 SQL（随机未考卷 + 全考过重抽）—— **已实现** |
| `ExamRecordMapper#selectOngoingCSCAExamByUserIdAndSubjectTypeMapping` | 续考查询—— **已实现** |
| `ExamNumberService` | 准考证号 / 成绩单号自增—— **已实现** |

### 0.10 改造原则

1. **URL 不动**：现有端点的路径、HTTP 方法、返回包装一律保持，只**加字段 / 修行为**。老 App 不受影响。
2. **入参只放宽不收紧**：新增参数一律 `required=false` 且有缺省；现有必填参数**维持必填**（除非它本身是 bug）。
3. **返回只加不减**：现有 DTO 的字段**一个都不删**（老前端在解析）；要"去掉"答案泄漏这种，是**在 Service 层不再 `set`**，DTO 字段本身保留为 `null`。
4. **新逻辑走分支**：所有新增的 CSCA 逻辑判定前置条件为 `exam_paper.exam_type = 2`，**HSK 路径零影响**。
5. **新增端点才用新 DTO 新枚举**：新 DTO 的 id 字段声明 `String`（[0.4](#04-id-序列化)），不动老 DTO。

---

## 1. 用户操作流程与接口对照

### 1.0 功能清单：这批接口新增了什么

> **先看这里**。需求文档（TAPD wiki）讲的是**功能**，本文讲的是**端点**，两者不是一对一。对齐后的结论是：**20 个在用端点里只有 3 个是新增的**（5 科次数 / 成绩单预览 / 考试内收藏），但真正新增的**功能是 8 项**；其余端点的改造目的，是**让这 8 项能安全跑起来**（防答案泄漏、防客户端伪造对错、判分正确、交卷幂等）。另有 2 个端点（`/answer/batch`、`/answer/statistics`）**前端从未调用，本期明确不用**。

**一句话**：需求里真正的功能增量只有四块 —— **次数限制**、**续考与倒计时**、**收藏与错题本**（两个**互不相干**的长期资产：收藏是用户点 ★，错题本是判错自动收录）、**成绩单**。

#### A. 从无到有（5 项）

| # | 新功能 | 涉及端点 | 现状：不做就没有 |
|---|---|---|---|
| **1** | **考试次数限制**（🔒 B 方案：每科 3 次） | 🆕 [`GET /record/csca/quota`](#311--get-recordcscaquota--5-科剩余次数)<br>🔧 [`POST /answer/start/csca`](#321--改造-post-answerstartcsca)<br>🔧 [`POST /answer/queryExamInProgress`](#312--改造-post-answerqueryexaminprogress--前置校验) | `startCscaExam`（`ExamRecordServiceImpl:269`）**一行配额代码都没有**（HSK 在 `:119` 校验 / `:235` 扣减）→ **任何人可无限考**；`user_exam_quota` 中 CSCA **0 行** |
| **2** | **开考前资料完整性拦截**（**含姓名**） | 🔧 `queryExamInProgress` 回 `8104` + `incompleteFields[]`<br>✅ **底层判定已有**：`GET /api/auth/app/profile/check`（5 项） | 需求 4.1 要求"开始前校验"。🔴 **v2.9 校正**：判定逻辑**已经存在**，`auth-service` 实测回 `{completed:true, incompleteFields:[]}`（前端 `ExamApiProvider#checkProfile` 已在用），缺的只是**接进开考链路**；字段名是 **`incompleteFields`** 不是 `missingFields`。<br>🔒 **v3.6：接法是 exam-service 在 `queryExamInProgress` 里真调它**（透传 JWT，fail-closed），不再本地复刻判定逻辑。<br>🔒 **v3.2 定案：这 5 项从「提示」升级为硬门槛** —— 姓名不填就没有成绩单（`candidate.name` 模板唯一必填），所以**不放行**，而不是事后回落 `nickname` |
| **3** | **服务端权威倒计时 + 断点续考** | 🔧 `startCscaExam` 写 `deadline_time`<br>🔧 整卷 / 答题卡返 `remainingSeconds`<br>🔧 `action=RESUME`<br>✅ **复用** `/record/{paperId}/leave`（前端在用） | **无 `deadline_time` 概念**，超时只靠客户端 → 改本地时间 / 关网即可"永久答题"。🔴 v2.9 校正：`leave` **不能停用** —— 前端 `leaveExam` 正在调（暂离/切题都走它），停掉等于断功能，改为原样复用 |
| **4** | **考试内收藏** | 🆕 [`POST /answer/csca/favorite`](#334--新增-post-answercscafavorite--考试内收藏) | exam-service **零收藏代码**（`csca_question_favorite` 全仓零命中）。🔴 **不能拿 `/answer/paper/tag` 顶替**：那是**标记**（写 `exam_answer.is_tag`，HSK 共用），与收藏是两件事 → 必须新增端点 |
| **5** | **错题本（考后自动收录）** | 🔧 [`POST /record/{paperId}/submit/csca`](#341--改造-post-recordpaperidsubmitcsca) 判分后写 `csca_question_wrong`（`source='exam'`）<br>✅ **读 / 移出 / 复习走练习模块**（本模块零新增端点） | 需求 2.6 要求"错题/考试记录同步"，代码**完全未实现**（exam-service 对 `csca_question_wrong` **零引用**）。🔴 两个坑：① 未答题也是 `is_correct=2`，不能单条件筛；② 写入必须与交卷**事务隔离**（PROD 表未建，同事务会让整笔交卷回滚）。完整口径见 [3.7](#37-错题本考试侧只写不读) |

#### B. 已有雏形、补完整（3 项）

| # | 功能 | 涉及端点 | 缺口 |
|---|---|---|---|
| **6** | **成绩单**（预览 → 生成 → 存链接 → 下载） | 🆕 [`GET /record/{examRecordId}/scoreReport/preview`](#362--get-recordexamrecordidscorereportpreview)<br>🆕 [`POST /record/{examRecordId}/scoreReport`](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接)<br>🔧 [`GET /record/{examRecordId}/scoreReport`](#363--改造-get-recordexamrecordidscorereport--csca-改读已上传的-pdf) | 现有只有 PDF，且 `ScoreReportPdfServiceImpl` 是 **HSK 专用版式**（`level + " 成绩报告"`、听说读写分段表）—— CSCA 无 `level`、无分段，直接调会出空白/异常；字体依赖 `C:\Windows\Fonts`，**Linux 容器里必然乱码**。<br>🔒 **v3.6 定案（用户拍板）**：**服务端完全不生成 CSCA 成绩单** —— 前端用官方 A4 模板（`report.css` + `report.js`）渲染并生成 PDF → 上传拿链接 → **回存到 `exam_record.report_url`**（该列早已存在，只是本仓零代码写过）。下载端点改成 `302` 到该链接。**后端零字体依赖、零 Chromium。** |
| **7** | **诊断报告增强** | 🔧 [`GET /record/csca/{examRecordId}/result`](#351--改造-get-recordcscaexamrecordidresult)<br>🔧 [`GET /record/{paperId}/question/{questionId}`](#352--改造-get-recordpaperidquestionquestionid) | 缺 `autoSubmitted`（超时交卷标记）；单题解析依赖 `selectByPaperAndUser`（**只查 `status=0`**）→ **交卷后反而查不到** |
| **8** | **模考记录** | 🔧 [`GET /record/user/records`](#361--改造-get-recorduserrecords) | 不传时间**默认只查最近 30 天**（历史记录"消失"）；`level` 对 CSCA 无意义，`examLevel` 会拼出 `"level null"` |

#### C. 不算新功能，但不改上不了线（P0 修复）

这几项是**安全性与正确性底线**，本身不提供新能力；但只要漏一项，前 8 项要么**形同虚设**（次数被绕过、收藏无处落），要么**带病上线**（判分错、答案泄漏）。

- 🔴 **整卷剔除 `answer` / `analysis`** —— `getCscaPaperDetailWithAnswers:1809` 现在把答案和解析一起下发，**考试中就能看到全部答案**
- 🔴 **单题保存强制写 `exam_record_id` + 忽略客户端 `isCorrect`** —— 前者导致按 `recordId` 判分时**漏题**，后者可被**伪造对错**
- 🔴 **多选改集合比较**（`CscaAnswerNormalizer#equalsSet`）—— 现在用 `equalsIgnoreCase`，**35 道多选题必判错**
- 🔴 **交卷幂等**（`status != 0` 判断 + `UPDATE … WHERE status = 0`）—— 重复 / 并发交卷会**重复判分、重复扣次**
- 未答不计入"答错"、满分口径统一为 `structure.full_score`、答题卡收藏态与 `currentQuestionNumber=null` 的 NPE

#### D. 一个端点都没加的部分

| 需要什么 | 出处 | 说明 |
|---|---|---|
| 5 个科目卡（码 / 名 / 顺序 / 默认项） | ✅ **现有字典** `GET /api/system/dict/code/csca_subject`（system-service） | `sortOrder` 1–5、`isDefault=1` 在 `arts_chinese`，正好覆盖需求 1.3 |
| 按科×语言列卷 / 卷详情 / 卷结构 | ✅ `/paper/list/csca`、`/paper/csca/detail`、`/paper/structure/version/{version}` | — |
| 答题统计 / 交卷前检查 / 准考证号 | ✅ `/answer/checkSubmit`、`/number/examTicket`（**`/answer/statistics` 前端不用**） | 实测 `statistics` 返回 `totalQuestions=25` 而卷是 48 题，数据本身不准 |
| 资料完整度判定 | ✅ **现有** `GET /api/auth/app/profile/check`（auth-service，5 项） | 实测回 `{completed, incompleteFields[]}`。🔒 **v3.6：exam-service 必须调它**（[3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验)）—— 以前是本地拿 `UserResponse` 判空，等于把 auth 的 5 项规则抄了一份，口径会漂；现在判定归 auth、快照取值仍归 `UserClient` |
| 暂离考试 | ✅ **现有** `POST /record/{paperId}/leave` | 前端 `leaveExam` 在用，实测 `200 已暂离考试` |
| **错题本的读 / 移出 / 复习** | ✅ **现有**（CSCA 练习模块）`GET /api/practice/csca/wrong-book`、`DELETE .../{questionId}`、`POST .../{questionId}/answer` | 错题本**一份、跨入口同源**，考试侧只写不读，不重复造读接口（[3.7](#37-错题本考试侧只写不读)）。⚠️ 前端取考试错题必须传 **`source=exam`**，否则练习 + 考试混排 |

> 这也是最终**只新增 3 个端点**的原因：能承接的一律复用（含跨服务的字典、含标记用的 `paper/tag`），只有「5 科次数」「成绩单 JSON」「考试内收藏」在代码里确实没有等价物。

#### E. 上线前置阻塞

🔴 **全仓没有任何 `user_exam_quota` 的发放代码**（auth-service 只在注销重注册时按 `user_cancel_history.quota_snapshot` 写回），而 CSCA 现有 **0 行** → 按本文设计直接上线，**全员一开考就是 `8105`**。方案三选一见 [4.3](#43-待确认事项) 第 3 条 / [4.4](#44-现状--目标差异清单) 的 `1d`。**此项不解决，功能 1 无法验收。**

---

### 1.1 页面流转

```
【考试首页】
  GET /api/system/dict/code/csca_subject   ✅ 5 个科目卡（码 / 名 / 顺序 / 默认项）
  GET /record/csca/quota                   🆕 5 科次数角标（一次拿全）
        │
        ├─ 未登录点【开始模拟考试】 → 401 → 前端弹登录
        │
        └─ 已登录点【开始模拟考试】
             POST /answer/queryExamInProgress   🔧 前置校验（只读、不扣次数）
                  │
                  ├─ action=RESUME             → 直接进答题页（用返回的 recordId/paperId）
                  ├─ action=PROFILE_INCOMPLETE → 弹「去完善资料」+ incompleteFields
                  ├─ action=NO_PAPER           → Toast「该科目暂无试卷」
                  ├─ action=QUOTA_EXHAUSTED    → 弹「次数已用完，联系客服/购买次数」
                  └─ action=CREATE             → 调下一步
                        │
                        POST /answer/start/csca  🔧 建会话 + 扣次数（事务）
                             │
【答题页】                     ▼
  GET /answer/paper/csca/detail/{paperId}   🔧 整卷（无答案）
  POST /answer/submit                       🔧 每题即时保存（字段名 answer + questionNumber 必填）
  POST /record/{paperId}/leave              ✅ 暂离（前端在用，原样复用）
  POST /answer/paper/tag                    ✅ 标记（写 is_tag，HSK 共用，不改）
  POST /answer/csca/favorite                🆕 收藏 / 取消（写 csca_question_favorite）
  GET /answer/csca/card/detail/{paperId}    🔧 答题卡（标记 + 收藏 + remainingSeconds）
  GET /answer/checkSubmit/{paperId}         ✅ 交卷弹窗统计
        │
        └─ 点交卷 / 倒计时归零
             POST /record/{paperId}/submit/csca  🔧 交卷 + 判分 + 错题同步
                  │
【诊断报告】              ▼
  GET /record/csca/{examRecordId}/result              🔧 报告
  GET /record/{paperId}/question/{questionId}?…       🔧 单题解析
        │
        ├─【下载成绩单】→ GET /record/{examRecordId}/scoreReport/preview  🆕 预览（data + reportReady）
        │                    ├─ reportReady=false → 前端 render → 生成 PDF → 上传拿链接
        │                    │                       → POST /record/{id}/scoreReport  🆕 存链接
        │                    └─【下载】→ GET /record/{examRecordId}/scoreReport  🔧 302 到已存链接（无则 8114）
        └─【重新考试】  → 回首页

【我的 → 学习与测试】
  GET /record/user/records                  🔧 模考记录
  收藏夹 / 错题本 → practice-service 的 /api/practice/csca/**（取考试数据传 source=exam）
```

### 1.2 场景 → 接口对照表

| 场景 | 端点 | 处置 | 备注 |
|---|---|---|---|
| 进首页看科目卡 | `GET /api/system/dict/code/csca_subject` | ✅ **复用**（现有） | 5 科 + `sortOrder` 顺序 + `isDefault` 默认项；🔴 `status` 是 **0=正常 / 1=禁用** |
| 查我的剩余次数 | `GET /record/csca/quota` | 🆕 A | 一次拿全 5 科；`POST /speaking/quota` 属口语模块，**不复用**（[3.1.3](#313--不复用-post-speakingquota--csca-次数只走-get-recordcscaquota)） |
| 点开始 → 校验资料/次数 | `POST /answer/queryExamInProgress` | 🔧 | 只读，不扣次数；资料 5 项**由 exam-service 调 auth 现有 `GET /auth/app/profile/check`** 判定（🔒 v3.6 定：判定单一真源，exam 不再自己实现一份） |
| 建会话（扣次数） | `POST /answer/start/csca` | 🔧 | 事务内 `decrementQuota(id)`（**该科目那一行**） |
| 中途退出再进 | `POST /answer/queryExamInProgress` | 🔧 | 命中 `status=0` → `RESUME` |
| 加载整卷 | `GET /answer/paper/csca/detail/{paperId}` | 🔧 | 首次全量加载 |
| 选一个选项 | `POST /answer/submit` | 🔧 | 即时保存，不判分；**字段名 `answer`**（不是 `userAnswer`）+ `questionNumber` 必填 |
| 暂离 / 切后台 | `POST /record/{paperId}/leave` | ✅ **复用** | 写 `leave_*` 字段，实测 `200 已暂离考试` |
| 标记一题（答题卡黄格） | `POST /answer/paper/tag` | ✅ **复用** | 写 `exam_answer.is_tag`，**语义不变**，HSK 共用 |
| 收藏 / 取消收藏（★） | `POST /answer/csca/favorite` | 🆕 | 写 `csca_question_favorite`（`source='exam'`）；与标记**互不影响** |
| 打开答题卡 | `GET /answer/csca/card/detail/{paperId}` | 🔧 | 标记 + 收藏 + 剩余时间 |
| 交卷确认弹窗 | `GET /answer/checkSubmit/{paperId}` | ✅ | 已答/未答统计 |
| 交卷 | `POST /record/{paperId}/submit/csca` | 🔧 | 同步判分 |
| 看诊断报告 | `GET /record/csca/{examRecordId}/result` | 🔧 | `CscaExamResultDTO` |
| 看单题解析 | `GET /record/{paperId}/question/{questionId}` | 🔧 | 用户答案 vs 标准答案 |
| 成绩单预览 | `GET /record/{examRecordId}/scoreReport/preview` | 🆕 | 模板契约 JSON + `reportReady`（**不含链接**，链接走下一行） |
| **生成并上传成绩单** | 前端渲染 → `POST /api/system/file/uploadFile` → `POST /record/{examRecordId}/scoreReport` | 🆕 | 🔴 **先上传拿链接，再回存链接**；按 recordId 幂等，重复生成需 `overwrite:true` |
| 下载成绩单 PDF | `GET /record/{examRecordId}/scoreReport` | 🔧 | CSCA → `302` 到 `report_url`；为空 → `8114`；HSK 仍是 PDFBox 现生成 |
| 模考记录列表 | `GET /record/user/records` | 🔧 | 加 CSCA 筛选 |
| **交卷后错题自动收录** | 无独立调用（交卷内附随） | 🔧 | 写在 `POST /record/{paperId}/submit/csca` 里，`source='exam'`；**未答不进、判对不动**（[3.7](#37-错题本考试侧只写不读)） |
| **看我的错题本** | `GET /api/practice/csca/wrong-book` | ✅ **复用**（练习模块） | 🔴 必传 **`source=exam`**；带标准答案 + 用户答案，不带解析 |
| **移出 / 复习错题** | `DELETE` / `POST /api/practice/csca/wrong-book/{questionId}` | ✅ **复用**（练习模块） | 考试侧不重复造读接口 |

### 1.3 一次完整考试的调用时序

```
T0  进首页        GET  /api/system/dict/code/csca_subject  （5 科 + 顺序 + 默认项）
                  GET  /record/csca/quota                  （5 科次数角标）
T1  点开始        POST /answer/queryExamInProgress          → action=CREATE
                  （CSCA 只传 subjectTypeMapping + languageVersion；version / level 可不传）
T2  建会话        POST /answer/start/csca                   → {recordId, paperId, deadlineTime}
T3  拉整卷        GET  /answer/paper/csca/detail/{paperId}  → 80 题 ≈ 32 KB
T4  …逐题作答      POST /answer/submit × N                  （每题一次，约 100–200 B）
T5  中途看卡      GET  /answer/csca/card/detail/{paperId}   （点答题卡图标）
T6  点交卷        GET  /answer/checkSubmit/{paperId}        → 弹窗统计
T7  确认交卷      POST /record/{paperId}/submit/csca        → 判分摘要
T8  诊断报告      GET  /record/csca/{examRecordId}/result
T9  点某题看解析  GET  /record/{paperId}/question/{questionId}?examRecordId=
T10 打开成绩单    GET  /record/{examRecordId}/scoreReport/preview   → data + reportReady
T11 生成并回存    POST /api/system/file/uploadFile                  → reportUrl（MinIO 直链）
                  POST /record/{examRecordId}/scoreReport {reportUrl} → 写 exam_record.report_url
T12 再下载        GET  /record/{examRecordId}/scoreReport            → 302 到 report_url（无则 8114）
```

**心跳/兜底**：

- 前端倒计时以 `remainingSeconds` 为准，**每次接口响应都回**，不用本地时钟起算；
- 归零 → 前端调 `POST /record/{paperId}/submit/csca`（带 `{auto:true}`）；
- 服务端**惰性兜底**：任何会话相关请求进来先判 `now > deadline_time`，命中即内部自动交卷并回 `8109`；
- 服务端**定时兜底**：`cscaExamTimeoutJob`（XXL-Job，5 分钟一次）扫 `status=0 AND deadline_time < now AND deadline_time IS NOT NULL`。

### 1.4 中断、离线与多端

| 情况 | 服务端口径 | 前端口径 |
|---|---|---|
| App 切后台 / 杀进程 | **倒计时不停**（`deadline_time` 服务端算） | 切走时 `POST /record/{paperId}/leave`（✅ 现有），回来 → `queryExamInProgress` → `RESUME`，`remainingSeconds` 继续算 |
| 断网作答 | 无影响（每题已落库） | 恢复后**逐题重发 `POST /answer/submit`**（🔴 `/answer/batch` 前端**没有实现**，实测也 500，本期不指望它） |
| 交卷失败 | 幂等：`UPDATE … WHERE status=0`，重复调只判一次 | 重试即可，**不会重复判分** |
| 多端同时考同一科 | 建会话幂等键 `(user, subject, language, status=0)` → 第二端**直接续考**同一会话 | 提示「已在其他设备考试」 |
| 本地时钟被改 | 无效：一切以服务端 `remainingSeconds` 为准 | — |
| 倒计时归零时正答题 | 服务端惰性交卷，`8109` → 前端跳报告 | 提交中的答案**先落库再交卷** |

---

## 2. 接口总览

### 2.1 端点总表（17 在用 + 2 不用 + 4 新增）

> 🔴 **v2.9 说明**：19 个现有端点里，`/answer/batch` 与 `/answer/statistics` **前端从未调用** → 列为「⛔ 不用」，不参与本期改造。**在用 = 10 改造 + 7 复用 = 17**，再加 4 个新增 = **21 个**。

| # | 方法 | 端点 | 能力 | 处置 | 鉴权 | 关键改动 |
|---|---|---|---|---|---|---|
| 1 | `GET` | `/paper/list/csca` | 按科×语言列卷 | ✅ 复用 | 否 | — |
| 2 | `GET` | `/paper/csca/detail` | 卷详情（题数/时长/满分） | ✅ 复用 | 否 | — |
| 3 | `GET` | `/paper/structure/version/{version}` | 卷结构模板 | ✅ 复用 | 否 | — |
| **A** | `GET` | **`/record/csca/quota`** | **5 科剩余次数（B 方案）** | 🆕 **新增** | 是 | — |
| 4 | `POST` | `/answer/queryExamInProgress` | 续考查询 + 前置校验 | 🔧 **改造** | 是 | 加 CSCA 分支、`action` 决策字段；`version` / `level` 校验下沉进 HSK 分支 |
| 5 | `POST` | `/answer/start/csca` | 建会话 + 抽卷 + 扣次数 | 🔧 **改造** | 是 | **接 `user_exam_quota`（B 方案按科目）**：`hasAvailableQuota(4参)` + `decrementQuota(id)`、参数校验、`deadline_time` |
| 6 | `GET` | `/answer/paper/csca/detail/{paperId}` | 整卷 | 🔧 **改造** | 是 | 🔴 **剔除答案/解析**、加 `remainingSeconds` |
| 7 | `POST` | `/answer/submit` | 单题保存 | 🔧 **改造** | 是 | `isCorrect` 仅 CSCA 分支忽略（`exam_record_id` **实测已在写**，见 [4.9](#49-联调实测记录2026-10-22真调-test-后端)）；字段名 `answer` + `questionNumber` 必填 |
| 8 | `POST` | `/answer/batch` | 批量保存 | ⛔ **不用** | — | 前端 0 调用 + 实测 `500`；断网补传改用逐题重发 `/answer/submit` |
| 9 | `POST` | `/answer/paper/tag` | **标记**（写 `exam_answer.is_tag`） | ✅ **复用** | 是 | **语义不变、一行不改**（HSK 共用） |
| 10 | `GET` | `/answer/csca/card/detail/{paperId}` | 答题卡（标记 + 收藏） | 🔧 **改造** | 是 | 保留 `isTag`、补 `favorite` / `tagCount`、NPE 修复、加 `remainingSeconds` |
| **C** | `POST` | **`/answer/csca/favorite`** | **考试内收藏（收藏 / 取消）** | 🆕 **新增** | 是 | 写 `csca_question_favorite`（`source='exam'`），软删复活 |
| 11 | `GET` | `/answer/statistics/{paperId}` | 答题统计 | ⛔ **不用** | — | 前端 0 调用；实测 `totalQuestions=25` ≠ 卷 48 题 |
| 12 | `GET` | `/answer/checkSubmit/{paperId}` | 交卷前检查 | ✅ 复用 | 是 | — |
| 13 | `POST` | `/record/{paperId}/submit/csca` | 交卷 + 判分 | 🔧 **改造** | 是 | 🔴 **多选判分**、幂等、未答口径、**错题同步（独立事务，[3.7](#37-错题本考试侧只写不读)）** |
| 14 | `GET` | `/record/csca/{examRecordId}/result` | 诊断报告 | 🔧 **改造** | 是 | 补 `autoSubmitted`、去泄漏 |
| 15 | `GET` | `/record/{paperId}/question/{questionId}` | 单题解析 | 🔧 **改造** | 是 | 交卷后也能查 |
| 16 | `GET` | `/record/user/records` | 模考记录 | 🔧 **改造** | 是 | 加 CSCA 筛选、取消 30 天默认 |
| 17 | `GET` | `/record/{examRecordId}/scoreReport` | 成绩单 PDF | 🔧 **改造** | 是 | 按 `exam_type` 分流到 CSCA 版式 |
| **B** | `GET` | **`/record/{examRecordId}/scoreReport/preview`** | **成绩单 JSON 预览** | 🆕 **新增** | 是 | 加 `reportReady` 字段（v3.6）；v3.7 起**不下发 `reportUrl`** |
| **D** | `POST` | **`/record/{examRecordId}/scoreReport`** | **保存前端上传的成绩单链接** | 🆕 **新增** | 是 | 写 `report_url` + `report_unlocked=1`；host 白名单 + 含 recordId + 本人校验 + 条件更新幂等 |
| 18 | `POST` | `/record/{paperId}/leave` | 暂离 | ✅ **复用** | 是 | **一行不改**（v2.9 改判：前端 `leaveExam` 在用，实测 200） |
| 19 | `GET` | `/number/examTicket` | 准考证号 | ✅ 复用 | 是 | — |

**统计**：🔧 改造 **10** ／ ✅ 复用 **7** ／ 🆕 新增 **4** ／ ⛔ 不用 **2**（`/answer/batch`、`/answer/statistics`）= 在用 **21**，与现有 19 + 新增 4 = 23 条对应。🆕 四个新增 = `GET /record/csca/quota`（5 科次数，**纯读**）+ `GET /record/{examRecordId}/scoreReport/preview`（成绩单 JSON，**纯读**）+ `POST /record/{examRecordId}/scoreReport`（**存成绩单链接**，🆕 v3.6）+ `POST /answer/csca/favorite`（考试内收藏）。**两个写端点**：收藏、存成绩单链接。另：科目卡复用 **system-service 现有的** `GET /api/system/dict/code/csca_subject`，**错题本的读 / 移出 / 复习**复用 **practice-service 的** `/api/practice/csca/wrong-book*`（[3.7](#37-错题本考试侧只写不读)）—— 两者都**不在本服务，不计入上表**。

> ⛔ **两处「造聚合端点」的冲动都已撤销**：
> 1. 原 v2.1 想给 `POST /speaking/quota` 加 `level` —— 那是**口语模块**的端点，CSCA 不该挤进去。
> 2. 原 v2.2 想新增 `GET /paper/csca/catalog` 做「科目目录聚合」—— 砍掉卷量/时长/满分后，它剩下的 6 块数据里 **5 块都有现成出处**（科目=字典、续考=`startCscaExam` 自动返回、资料=[3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 校验），只剩次数需要后端。
>
> ✅ **反过来的第三处必须新增**（v2.7）：`POST /answer/paper/tag` 是**标记**不是收藏，且 HSK 共用不能改语义 → 收藏只能另开端点。**HSK / HSKK / Proficiency 一行不改**。

### 2.2 新增端点清单（4 个，仅这四个需要新建方法）

| 端点 | 归属 Controller | 新增类 |
|---|---|---|
| `GET /record/csca/quota` | `ExamRecordController`（**现有文件加方法**） | `CscaQuotaDTO`（1 个轻量 DTO，无 Service / Mapper / Controller 新类） |
| `GET /record/{examRecordId}/scoreReport/preview` | `ExamRecordController`（新增方法） | `CscaScoreReportDTO` |
| `POST /record/{examRecordId}/scoreReport` | `ExamRecordController`（**现有文件加方法**） | `CscaReportUploadRequest` / `CscaReportUploadResponse`（🆕 v3.6，2 个 DTO） |
| `POST /answer/csca/favorite` | `ExamAnswerController`（**现有文件加方法**） | `CscaFavoriteRequest` / `CscaFavoriteResponse` |

> ⚠️ **其余全部在原 Controller / 原 Service 方法内改**，不新建类、不改 URL。
> 📌 收藏 vs 存成绩单链接：两个都是**新增写端点**，原因不同 —— 收藏是因为 `csca_question_favorite` 在 exam-service **零引用**（`paper/tag` 是标记、不能改语义）；存链接是因为 `exam_record.report_url` 虽早已存在，但**本仓零代码写过**（只有那个外部上传服务在写），CSCA 需要自己的写入口。

### 2.3 端点归属与前缀

| 服务内路径 | 网关路径 |
|---|---|
| `/record/csca/quota`（**CSCA 次数唯一出口**，需登录） | `/api/exam/record/csca/quota` |
| `/answer/csca/favorite`（🆕 **考试内收藏**，强鉴权） | `/api/exam/answer/csca/favorite` |
| `POST /file/uploadFile`（🆕 **PDF 上传通道**，在 `system-service`） | `/api/system/file/uploadFile` |
| `/answer/start/csca` | `/api/exam/answer/start/csca` |
| `/record/{paperId}/submit/csca` | `/api/exam/record/{paperId}/submit/csca` |
| `POST /record/{examRecordId}/scoreReport`（🆕 **存成绩单链接**，强鉴权 + 归属校验） | `/api/exam/record/{examRecordId}/scoreReport` |

### 2.4 量级依据（测试库实测，非估算）

| 项 | 实测值 |
|---|---|
| CSCA 卷 | **31 张**（文科中文 8 / 理科中文 5 / 数学 9 / 物理 5 / 化学 4），全部 `language_version='chinese'` |
| CSCA 题 | **1904 题**（多选 35，其余单选类） |
| 单卷题量 | 文/理中文 **80**、数理化 **48** |
| 满分 / 时长 | 均 **100.00**；文/理中文 **90 min**、数理化 **60 min** |
| 单题分值 | 文/理中文 **1.25**（80 × 1.25 = 100.00）；数理化 **2.00 / 2.50 混合**（40 × 2.00 + 8 × 2.50 = 100.00）→ **每卷 Σ = 100.00，已是百分制**（v3.4 已改；PROD 未改仍 2.08 × 48 = 99.84） |
| 整卷响应体积 | 80 题 ≈ **30–35 KB**（含 passage / option_content） |
| 诊断报告体积 | 80 题 ≈ **12 KB** |
| 现存 CSCA `exam_record` | **136 条**，其中 **42 条卡在 `status=0`**（`deadline_time` 为空） |
| `user_exam_quota` CSCA 行 | **0 行** |

> 📌 上表前几行（卷量 / 题量 / 满分 / 时长）**只用于容量评估与 DDL 校验**，CSCA 没有任何端点会下发它们：卷列表走 `GET /paper/list/csca`、单卷的题数/时长/满分走 `GET /paper/csca/detail?paperId=`。

---

## 3. 接口详细设计

### 3.1 进入考试与前置校验

#### 3.1.1 🆕 GET /record/csca/quota — 5 科剩余次数

**用处**（需求 2.5.1）：考试首页 5 个科目卡上的**次数角标**；「我的 - 考试次数」页刷新。

> 🔒 **本端点只回次数，不做科目目录聚合**。原设计的 `GET /paper/csca/catalog` **已撤销** —— 首页要的 6 块数据里，只有最后一块必须由后端提供：
>
> | 首页要的 | 去哪拿 | 为什么不需要新端点 |
> |---|---|---|
> | 5 个科目（码 / 中文名 / 顺序 / 默认项） | ✅ **`GET /api/system/dict/code/csca_subject`**（**现有接口**） | 字典项恰好全覆盖需求 1.3：`itemValue`=科目码、`itemText`=中文名、`sortOrder`=1–5（文→理→数→物→化）、`isDefault=1` 落在 `arts_chinese`。**前端直调网关即可**，不需要前端写死，也不需要 `exam-service` 中转 |
> | 语言开关（中文 / English） | **前端常量** | 需求 2.1 已写死「中文科目只用中文卷」；数学 / 物理 / 化学虽支持英文，但**库中 0 张英文卷** → 前端整体置灰 English，导入英文卷时前端一起放开（[4.3](#43-待确认事项) 第 13 条） |
> | 该科**能不能考** | **不需要判定** | 唯一不可考的是 `science_chinese`（有 5 套卷、无 `exam_paper_structure` 模板）。补上那一行后 5 科全可考 → `available` 字段失去意义。[4.6](#46-表结构与-ddl-变更) 第 ④ 步已把该行从「建议补」升为**上线阻断项** |
> | 续考会话 | **不用查** | `startCscaExam`（`ExamRecordServiceImpl:269`）**第一步就是**「查进行中考试，命中直接返回」→ 用户点【开始模拟考试】自动续考，首页无需预览。要显式查时走 [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 的 `action=RESUME` |
> | 资料完整度 | **开考时校验** | 需求 4.1 明确是「开始前校验」→ [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 回 `8104` + `incompleteFields[]`，首页不参与 |
> | **5 科剩余次数** | ✅ **本端点** | `user_exam_quota` 在 exam-service 里**没有任何批量出口**：唯一查询端点是口语模块的 `POST /speaking/quota`（单科、返回实体原样），CSCA 不复用它（[3.1.3](#313--不复用-post-speakingquota--csca-次数只走-get-recordcscaquota)） |
>
> 结论：**端点数仍是 2 个**（本端点 + [3.6.2](#362--get-recordexamrecordidscorereportpreview) 成绩单预览），但本端点比原 `catalog` 轻得多 —— `catalog` 还要读 `exam_paper` × `exam_paper_structure` × `exam_record` × `user`（经 `UserClient`）四张表、并新建 Service / DTO / Mapper 三个类；本端点**只读 1 张表、只加 1 个 DTO**。

**科目清单从哪来：`GET /api/system/dict/code/csca_subject`（现有接口，前端直调）**

TEST 库实测（`sys_dict` id=1001，`sys_dict_item` 5 项）：

| `itemValue` | `itemText` | `sortOrder` | `isDefault` | `status` |
|---|---|---|---|---|
| `arts_chinese` | 文科中文 | 1 | **1** | 0 |
| `science_chinese` | 理科中文 | 2 | 0 | 0 |
| `math` | 数学 | 3 | 0 | 0 |
| `physics` | 物理 | 4 | 0 | 0 |
| `chemistry` | 化学 | 5 | 0 | 0 |

与需求 1.3 完全一致：**顺序 = `sortOrder` 升序，默认科目 = `isDefault=1`**。前端按下标渲染 5 张卡、取 `isDefault=1` 作默认选中即可，**既不用硬编码，也不用后端再包一层**。

四条使用注意：

1. 🔴 **`status` 语义是「0-正常 / 1-禁用」**（`SHOW FULL COLUMNS` 注释确认）—— 与项目里多数业务表的 `1=正常` **相反**。全库 `sys_dict` 6 条、`sys_dict_item` 103 条**实测 status 全是 0**。前端过滤必须写 `status === 0`，写成 `=== 1` 会得到空列表。
2. ⚠️ **后端不过滤 `status`**：`SysDictServiceImpl#getDictItemsByDictId:163` 会把禁用项一并返回，**过滤责任在前端**（不要在后端加过滤，那会连带影响管理端页面）。
3. ✅ **跨服务不是问题**：字典在 `system-service`，前端经网关直调 `/api/system/dict/code/csca_subject`。所谓"跨服务"只在**后端聚合**时才需要新建 Feign（`exam-service` 现有 5 个 client 里没有 `SystemClient`）；前端同时调 system / exam 两个服务是常态，**零额外依赖**。
4. ⚠️ **字典数据本身要先修**：`system-service/src/main/resources/sql/csca_subject.sql` 与 TEST 库不一致（文件里 `sort_order` 把数学排第 2、`is_default` 放在数学）→ 详情见 [4.3](#43-待确认事项) 第 19 条，**PROD 上线前必须先修文件**，否则首页默认科目会落到数学。

**落地位置**：`ExamRecordController`（**现有文件，加一个方法**）→ `ExamRecordServiceImpl#getCscaQuota(Long userId)`。**不新建 Controller / Service / Mapper**，只新增 1 个轻量 DTO。

| 层 | 做什么 | 不做什么 |
|---|---|---|
| **Controller** | `@GetMapping("/csca/quota")`，从 Token 取 `userId` | 不收科目 / 语言参数（**恒 5 科一次给全**）；不允许游客 |
| **Service** | 一条查询取回 5 行 → 按 `level` 映射成**固定 5 条** → 缺哪科补 `0 / 0 / 0 / false` | 不扣次数、不建会话、**不读 `exam_paper` / `exam_paper_structure` / `exam_record` / `user`** |
| **Mapper** | 复用 `UserExamQuotaMapper` 现成方法 | 🚫 **一行不改**（`selectByUserIdAndExamTypeAndVersion` 是 `LIMIT 1` 的，本端点不能用它，直接走 MP `selectList`） |

**入参**：无（`userId` 从 Token 取，必填）

**返回 JSON**

```json
{
  "code": 200, "message": "查询成功",
  "data": {
    "quotas": [
      { "subjectType": "arts_chinese",    "subjectTypeText": "文科中文", "totalQuota": 3, "usedQuota": 0, "remainQuota": 3, "hasQuota": true  },
      { "subjectType": "science_chinese", "subjectTypeText": "理科中文", "totalQuota": 3, "usedQuota": 3, "remainQuota": 0, "hasQuota": false },
      { "subjectType": "math",            "subjectTypeText": "数学",     "totalQuota": 3, "usedQuota": 1, "remainQuota": 2, "hasQuota": true  },
      { "subjectType": "physics",         "subjectTypeText": "物理",     "totalQuota": 3, "usedQuota": 0, "remainQuota": 3, "hasQuota": true  },
      { "subjectType": "chemistry",       "subjectTypeText": "化学",     "totalQuota": 3, "usedQuota": 0, "remainQuota": 3, "hasQuota": true  }
    ],
    "totalRemainQuota": 11
  }
}
```

**字段口径**

| 字段 | 口径 |
|---|---|
| `quotas[]` | 🔒 **B 方案按科目回次数**。**固定 5 条、顺序恒为** `arts_chinese` → `science_chinese` → `math` → `physics` → `chemistry`（与前端科目常量同序）。**不是「有才出现」**——前端按下标取数不越界 |
| `hasQuota` | `remainQuota > 0`。与 HSK `hasAvailableQuota` 语义一致：**查不到行 = 没次数**（该条三项全 0） |
| `totalQuota` / `usedQuota` | 原样回 `user_exam_quota` 对应列。⚠️ **`total_quota` 在现网不可信**（实测 `sum(total)=33` vs `sum(remain)=1684`，运营直接改 `remain_quota`）→ **前端判断有无次数只看 `hasQuota` / `remainQuota`，不要用 `totalQuota - usedQuota` 推算** |
| `totalRemainQuota` | 5 科 `remainQuota` 之和，**仅供首页「剩余 N 次」总览**；**不作为任何校验依据**（校验永远按科目，见 [3.2.1](#321--改造-post-answerstartcsca)） |
| 科目中文名 | Service 内硬编码（真源 `common/enums/CSCASubjectType`），**不查 `sys_dict`**、不跨服务 |
| ⚠️ 当前库 CSCA **0 行** | 未初始化时 5 条全 `0 / false`，前端会显示全面「次数用完」。上线前必须执行 [4.6](#46-表结构与-ddl-变更) 第 ④ 步（每人 5 行 / 每科 3 次） |

**业务逻辑**

```java
// ExamRecordServiceImpl#getCscaQuota —— 一次查回，不要循环
List<UserExamQuota> rows = userExamQuotaMapper.selectList(
        new LambdaQueryWrapper<UserExamQuota>()
                .eq(UserExamQuota::getUserId, userId)
                .eq(UserExamQuota::getExamType, "CSCA")
                .eq(UserExamQuota::getVersion, "CSCA")
                .eq(UserExamQuota::getStatus, 1)
                .eq(UserExamQuota::getDeleted, 0)      // 🔴 全仓无 @TableLogic，必须手写
                .in(UserExamQuota::getLevel, CSCA_SUBJECT_CODES));   // 5 个科目码
```

1. **一次查询取回 5 行** → `Map<level, row>` → 按固定科目顺序铺出 5 条，缺失补水。
2. 🔴 **禁止循环调 3 参 `getQuota(userId,"CSCA","CSCA")`**：它走 `selectByUserIdAndExamTypeAndVersion`（**无 `level` + `LIMIT 1`**），B 方案下一人有 5 行 → **5 个角标会显示同一份次数**（[4.4](#44-现状--目标差异清单) 第 1e 条）。
3. **降级**：DB 异常时返回 `quotas` 全 0 + `totalRemainQuota=0`，**不抛 500** —— 首页不能因为配额查询挂了就打不开。
4. **只读**：本端点**绝不扣次数**；扣减只在 [3.2.1](#321--改造-post-answerstartcsca) 建会话成功时发生。

**涉及表**：**`user_exam_quota`（读，现有表，不新增列、不改索引）**

**数据流向**

```
前端 → ExamRecordController(/record/csca/quota) → ExamRecordServiceImpl#getCscaQuota
        └→ UserExamQuotaMapper.selectList (一次查回 5 科)
      → CscaQuotaDTO { quotas[](固定 5 条) , totalRemainQuota } → 前端
```

---

#### 3.1.2 🔧 改造 POST /answer/queryExamInProgress — 前置校验

**现状**（`ExamAnswerController:52` → `ExamRecordServiceImpl:241`）：

```java
// 现有实现：强制 version + level 非空，只查 HSK
if (StringUtils.isBlank(version)) throw new BusinessException(500, "考试大纲版本不能为空");
if (StringUtils.isBlank(level))   throw new BusinessException(500, "等级不能为空");
ExamRecord existing = examRecordMapper.selectOngoingExamByUserIdAndLevel(userId, version, level);
return existing != null ? toResponse(existing) : null;
```

> 🔴 这两行 `isBlank` 校验**写死在方法头部、对所有调用方生效**。CSCA 没有「等级」这个概念（科目走 `subjectTypeMapping`），如果不动它，CSCA 每次调用都被 `"等级不能为空"` 挡在门外。所以**必须先判分支、再校验**。

**改造点**（**URL / 方法签名不变**，只加分支、只加字段）：

1. 🆕 **入参校验按分支拆开**（本次核心）：`version` + `level` 的非空强校验**整体下沉进 HSK 分支**；CSCA 分支**两项都不校验**
   - HSK 分支：**原样保留**两行 `isBlank` → HSK 行为**零变化**
   - CSCA 分支：`level` **直接忽略**（不校验、不参与查询）；`version` 缺省由**服务端**归一为 `'CSCA'`（见下方 🔴）
   - 唯一提到两支外层的只剩 `userId` 非空
2. CSCA 分支改走 `selectOngoingCSCAExamByUserIdAndSubjectTypeMapping(userId, version, subjectTypeMapping, languageVersion)`
3. 新增返回字段 `action` —— **把「校验资料 → 校验次数 → 是否续考」串成单一决策字段**
4. **只读**：本接口**绝不扣任何次数**

**分支判定与校验伪代码**

```java
// 分支判定：任一命中即 CSCA（前端最省时只需传 subjectTypeMapping + languageVersion）
private boolean isCsca(ExamRecordRequest r) {
    return Integer.valueOf(2).equals(r.getExamType())
        || "CSCA".equals(r.getVersion())
        || StringUtils.isNotBlank(r.getSubjectTypeMapping());
}

Long userId = request.getUserId();
if (userId == null) throw new BusinessException(500, "用户ID不能为空");   // ← 唯一提到两支外层的校验

if (!isCsca(request)) {
    // ===== HSK 分支：现有两行校验 + 原 SQL，一行不改 =====
    if (StringUtils.isBlank(version)) throw new BusinessException(500, "考试大纲版本不能为空");
    if (StringUtils.isBlank(level))   throw new BusinessException(500, "等级不能为空");
    existing = examRecordMapper.selectOngoingExamByUserIdAndLevel(userId, version, level);
} else {
    // ===== CSCA 分支：version / level 均不校验 =====
    String subject = requireCscaSubject(request.getSubjectTypeMapping());  // 非 5 值 → 8101
    String lang    = requireCscaLanguage(request.getLanguageVersion());    // 非 chinese/english → 8102
    String ver     = StringUtils.isBlank(version) ? "CSCA" : version;      // 🔴 服务端兜底，见下
    existing = examRecordMapper.selectOngoingCSCAExamByUserIdAndSubjectTypeMapping(
                   userId, ver, subject, lang);
}
```

> 🔴 **`version` 虽然「不强制」，但 CSCA 分支必须由服务端塞默认值 `'CSCA'`**：续考 SQL 是 `WHERE b.version = #{version}`（`ExamRecordMapper.xml:44`），传 `null` 时 `= NULL` **恒不成立**（不是报错、是静默查不到）→ 明明有进行中的会话却回 `null` → 前端走 `CREATE` → 重复开考（还会白扣一次次数）。所以这里的「不强制」= **前端可以不传**，不是「服务端可以不填」。

> 📌 前端传了 `version='HSK2.0'` 但带了 `subjectTypeMapping` 这种自相矛盾的组合时，**以 `examType`/`subjectTypeMapping` 为准**——分支一旦落在 CSCA，`version` 再被归一成 `'CSCA'`，不会拿 HSK 的版本号去查 CSCA 记录。

**入参**

> 🔴 **`ExamRecordRequest`（`exam/dto/ExamRecordRequest.java`）现在只有 `level` / `version` 两个相关字段**（全文 69 行，无 `examType`、无 `subjectTypeMapping`、无 `languageVersion`）。所以本接口要**新增 3 个纯可选字段**（都不加 `@NotBlank`），既有字段一个不动 —— 上面伪代码里的 `getExamType()` / `getSubjectTypeMapping()` / `getLanguageVersion()` 都建立在这一步之上。
>
> 📌 顺带记一句：该 Controller 的参数是 `@RequestBody(required = false)` 且**没有 `@Valid`**，所以 DTO 上那些 `@NotBlank`（连 `paperId` / `userId` 上标着 `@NotBlank` 的 Long 字段）**根本不生效**，校验全靠 Service 手写 —— 这也是为什么 `userId` / `version` / `level` 的非空判断是 `if + throw BusinessException` 而不是注解报错。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `version` | String | **HSK 是 / CSCA 否** | HSK 分支仍强校验非空；CSCA 不传 → 服务端归一 `'CSCA'`（**既有字段**） |
| `level` | String | **HSK 是 / CSCA 否** | HSK 分支仍强校验非空；CSCA **完全忽略**（不校验、不参与查询）（**既有字段**） |
| `subjectTypeMapping` | String | CSCA 时是 | 🆕 `arts_chinese` 等 5 值 → 非法 `8101`；同时也是**分支判定的依据** |
| `languageVersion` | String | CSCA 时是 | 🆕 `chinese` / `english` → 非法 `8102` |
| `examType` | Integer | 否 | 🆕 `2` = CSCA；不传时由 `version` / `subjectTypeMapping` 推断 |

**返回 JSON**（`ExamRecordResponse` **原有字段全部保留**，新增下面这些）

```json
{
  "code": 200, "message": "开始考试成功",
  "data": {
    "action": "CREATE",
    "id": 2101234567890123456,
    "paperId": 2101234567890123457,
    "status": 0,
    "deadlineTime": 1760882400000,
    "remainingSeconds": 2080,
    "deductType": 0,
    "deductAmount": 0.00,
    "profileCheck": { "completed": true, "incompleteFields": [] },
    "paperCheck": { "available": true, "paperCount": 9, "reason": null },
    "quotaCheck": {
      "examType": "CSCA", "version": "CSCA", "level": "math",
      "totalQuota": 3, "usedQuota": 1, "remainQuota": 2,
      "hasQuota": true
    },
    "autoSubmitted": false
  }
}
```

**`action` 五态**（前端唯一分支依据）

| `action` | 含义 | 前端动作 | 服务端已做 |
|---|---|---|---|
| `RESUME` | 有 `status=0` 的会话 | 直接进答题页（用 `id` / `paperId`） | **未扣次数** |
| `PROFILE_INCOMPLETE` | 资料 5 项缺项 | 弹「去完善资料」+ `incompleteFields[]` | **未建会话、未扣次数** |
| `NO_PAPER` | 该科×语言无卷或无结构模板 | Toast「该科目暂无试卷」 | — |
| `QUOTA_EXHAUSTED` | `remain_quota <= 0`（**或无配额行**） | 弹「次数已用完，联系客服 / 购买次数」 | **未建会话** |
| `CREATE` | 全部通过 | 调 [3.2.1](#321--改造-post-answerstartcsca) 建会话 | — |

> 📌 原设计的 `POINT_CONFIRM`（免费次数用完、改用点数）**本期去掉**——点数体系不存在，留着只会让前端多写一个永远进不去的分支。后续接点数时再加，`action` 是新增枚举值，向后兼容。

> ⚠️ `RESUME` 时若会话**已超时**（`now > deadline_time`）→ 先内部自动交卷再回 `CREATE`（`autoSubmitted=true` 在**下一次**建会话里体现）。

**三层逻辑**

| 层 | 做什么 |
|---|---|
| **Controller** | 不变（仍是 `@PostMapping("/queryExamInProgress")`） |
| **Service** | ① **先判分支**（`examType=2` / 带 `subjectTypeMapping` → CSCA，否则 HSK）；② 校验：HSK 两行 `isBlank` 原样保留，CSCA 只校验科目码 + 语言码、`version` 兜底 `'CSCA'`；③ 资料 **5 项**（🔴 **调 auth `GET /app/profile/check`**，透传 `Authorization` + `X-Client-Type`，口径单一真源）；④ 卷可用性；⑤ 次数（🆕 `hasAvailableQuota(userId,"CSCA","CSCA",subject)` **4 参重载**）；⑥ 续考查询（**同科目**）→ 拼 `action` |
| **Mapper** | HSK 分支复用 `selectOngoingExamByUserIdAndLevel`（不改）；CSCA 分支复用 `selectOngoingCSCAExamByUserIdAndSubjectTypeMapping`；新增 `countAvailablePaper` |

**资料校验 5 项（🔒 硬门槛，姓名在内）**

| 项 | 判空字段（`UserResponse`） | 缺失时 `incompleteFields` |
|---|---|---|
| 姓名 | `realName` | `"姓名"` |
| 性别 | `gender` | `"性别"` |
| 国籍 | `nationality` | `"国籍"` |
| 出生年月日 | `birthday` | `"出生年月日"` |
| 手机号 | `phone` | `"手机号"` |

> ✅ **判定口径直接照抄 auth-service**：`AppUserService#checkProfileCompletion` 就是这 5 项（**没有邮箱**），返回 `{completed, incompleteFields[]}`，中文名原样透传 —— 前端已有的「去完善资料」弹窗直接可用，不用新写文案映射。

> 🔴 **为什么姓名必须硬拦、不能事后回落**：官方成绩单模板里 `candidate.name` 是**唯一必填**的考生信息（`report.js#validate` 缺它就抛错，整页空白），而它取的是 `exam_record.real_name` 快照。若允许「先开考、成绩单再回落 `nickname`」，等于把 `user_8613060291168` 这类账号名印到正式成绩单上 —— 所以姓名缺失**在开考前就 `8104` 挡掉**，让用户去补，再回来考。

> 🔒 **v3.6 定案：开考前**必须**真正调一次 `GET /api/auth/app/profile/check`（用户 2026-10-22 拍板）**
>
> v3.2～v3.5 的写法是「exam-service 拿 `UserClient.getUserById` 自己判空、不调 auth」——**判定逻辑重复实现了一份**，auth 侧以后改口径（加字段 / 改中文名 / 加正则）exam 不会跟着变。改为直接调用 auth 的现成端点：
>
> ```java
> // exam-service 新增 AuthProfileClient（与 UserClient 同一套装配，见 config/AiServiceConfig）
> @HttpExchange("/app")
> public interface AuthProfileClient {
>     @GetExchange("/profile/check")
>     Result<ProfileCheckResponse> checkProfile(
>             @RequestHeader("Authorization") String authorization,   // 🔴 必须透传
>             @RequestHeader("X-Client-Type") String clientType);      // 🔴 必须传 "APP"
> }
> ```
>
> | 要点 | 说明 |
> |---|---|
> | **为什么要透传 header** | `AppAuthController#checkProfile` 走 `getCurrentUserId(request, clientType)` → `BaseController#getUserInfo` 只在 `X-Client-Type=APP` 时解析 JWT。**不带 `X-Client-Type` 会回落到 `getDefaultUserInfo()`（userId 恒 1，不是 401）**；不带 `Authorization` 才真的回 `null` → `401 用户未登录`。所以两个 header 缺一不可，且**不能**用 body 里的 `userId` 代替（该端点不收 userId） |
> | **取 token 的方式** | Controller 方法加 `HttpServletRequest`（或 `RequestContextHolder`）取出 `Authorization` 原样转发。`queryExamInProgress` 现在是纯 `@RequestBody`，**要补一个 `HttpServletRequest` 形参**——这是本次唯一的方法签名变化（URL 不变） |
> | **返回值** | `ProfileCheckResponse{completed, incompleteFields[]}`，`incompleteFields` 里已是**中文名**（"姓名" / "性别" …）→ 直接塞进 `8104` 的 `data`，**不做二次映射** |
> | **超时与失败降级** | 连接 + 读取超时 **1.5s**。调不通（超时 / 5xx / `code≠200`）→ **fail-closed**：回 `500`「用户资料校验服务暂不可用，请稍后重试」，🔴 **不得放行**（放行会产出无名成绩单，见下条），也**不得**冒用 `8104`（会让用户白跑一趟个人中心） |
> | **要不要缓存** | **不缓存**。「是否完整」是秒级会变的用户态数据，缓存 5 分钟就可能让刚补完资料的考生仍被拦 |
> | **`UserClient` 还要不要** | **要，但只用于取快照**：[3.2.1](#321--改造-post-answerstartcsca) 建会话时调 `getUserById` 拿 `realName/gender/nationality/birthday` 写 `exam_record`。**判定归 auth、取值归 user**，两个调用各司其职 —— 别再一次调用里既判又取（那就是 v3.2 的做法） |
>
> 📌 **代价**：开考链路多一跳跨服务调用（`exam → auth`，同集群内网，实测 HSK 的 `UserClient` 往返 < 30ms）。换来的是「资料完整口径只有一份」，值得。

**涉及表**：`exam_record`（读）/ `exam_paper`（读）/ `exam_paper_structure`（读）/ `user_exam_quota`（读）/ `user`（读）／ **写：无**

---

#### 3.1.3 ⛔ 不复用 POST /speaking/quota —— CSCA 次数只走 `GET /record/csca/quota`

**结论**：CSCA **不调用** `POST /speaking/quota`（`SpeakingExamController:76`），**也不给它加 `level` 参数**。给 CSCA 用的次数出口**只有一个**：[3.1.1](#311--get-recordcscaquota--5-科剩余次数) 新增的 `GET /record/csca/quota`。

**现状**（一行都不改）：

```java
@PostMapping("/quota")
public Result<UserExamQuota> getQuota(@Valid @RequestBody SpeakingExamQuotaRequest request, ...) {
    Long userId = getCurrentUserId(httpRequest, clientType);
    if (StringUtils.isEmpty(request.getExamType())) request.setExamType("Proficiency");
    UserExamQuota quota = userExamQuotaService.getQuota(userId, request.getExamType(), request.getVersion());
    if (quota == null) return Result.success("查询成功", null);
    quota.setIsInExam(0);
    if ("HSK".equals(request.getExamType())) { /* 顺带查进行中考试 */ }
    return Result.success("查询成功", quota);
}
```

**为什么不拿它给 CSCA 用**

| # | 理由 | 说明 |
|---|---|---|
| 1 | **语义错位** | 路径 `/speaking/quota`、`SpeakingExamController`、`SpeakingExamQuotaRequest` 三层全是**口语模块**的命名。让 CSCA 传 `examType='CSCA'` 进来是硬塞，以后口语侧重构（改路径、改入参、拆 Controller）会顺手把 CSCA 带崩 |
| 2 | **场景根本不存在** | CSCA 需要「刷次数」的地方只有**考完回列表**和**我的次数页**，这两处要的都是**5 科角标**，不是单科。用它反而要发 5 次请求 |
| 3 | **返回体不合用** | 它返回 `UserExamQuota` **实体原样**（`totalQuota` / `usedQuota` / `remainQuota` / `validStartTime` / `validEndTime` + 临时字段 `isInExam`），没有 CSCA 前端要的 `subjectTypeText` / `hasQuota`；`/record/csca/quota` 是加工好的固定 5 条，顺序恒定 |
| 4 | **改动有风险、收益为零** | 加 `level` 要动 `SpeakingExamQuotaRequest` + Controller 分支，而这两处是 HSK / HSKK / Proficiency **三方共用**的老代码。既然场景不需要，就没理由动 |

> 🔻 **因此「给 `/speaking/quota` 加 `level`」这条从改造清单里撤掉**：HSK / HSKK / Proficiency **一行都不用改**，`SpeakingExamQuotaRequest` 也不加字段。

> **单科查询本期不做**：已有 5 科批量端点，前端拿全量后本地按下标取即可（一次请求覆盖所有场景）。若将来真需要单科轻查询，**给 `GET /record/csca/quota` 加一个可选 `subjectType` 参数**即可，**不要**往 `/speaking/**` 里塞 CSCA。

**涉及表**：无（本端点不参与）

---

### 3.2 建会话 / 扣次数（复用 `user_exam_quota`）

#### 3.2.1 🔧 改造 POST /answer/start/csca

**现状**（`ExamAnswerController:70` → `ExamRecordServiceImpl:269`）：

```java
// 已有（保留）
ExamRecord existing = examRecordMapper.selectOngoingCSCAExamByUserIdAndSubjectTypeMapping(...);
if (existing != null) return toResponse(existing);          // ① 续考幂等 ✅ 已有
List<ExamPaper> paperList = examPaperMapper.selectUntakenPaperCSCA(...);  // ② 随机抽未考卷 ✅ 已有
// 全考过 → 清 user_taken_paper 后重抽                                    // ③ ✅ 已有
questionMapper.selectByPaperId(paper.getId());                            // ④ ✅ 已有
examAnswerService.initAnswerCard(paper.getId(), userId, recordId, qs);    // ⑤ ✅ 已有
userTakenPaperMapper.insert(takenPaper);                                  // ⑥ ✅ 已有
// 🔴 缺失：没有任何 userExamQuotaMapper 调用（对比 HSK startExam:235 有 decrementQuotaByUser）
// 🔴 缺失：没有参数非空校验；🔴 缺失：没有 deadline_time
```

**改造点**（**URL / 入参 DTO 不变**：`CSCAExamRecordRequest` 已有 `version` / `subjectTypeMapping` / `languageVersion`）

| # | 改造 | 级别 |
|---|---|---|
| 1 | 三参数**强制非空 + 枚举校验**（`@NotBlank` + `CscaExamSubjects.ofCode`），非法 → `8101` / `8102` | P1 |
| 2 | 抽卷 SQL 补 `exam_type = 2`（现有 `selectUntakenPaperCSCA` **只靠 `version='CSCA'` 兜**） | P2 |
| 3 | **写入 `deadline_time = start_time + duration_minutes × 60000`**（取 `exam_paper_structure.duration_minutes`） | **P0** |
| 4 | **扣次数（🔒 B 方案，按科目）**：`hasAvailableQuota(userId,"CSCA","CSCA",**subject**)` 校验 → `getQuota(4参)` 取该科那一行 → `decrementQuota(q.getId())` 扣减；**与 `exam_record` 插入在同一事务**；`exam_type='CSCA'`、`version='CSCA'`、`level=<科目码>`。🔴 **禁止 `decrementQuotaByUser`**（无 `level`，会一次扣掉 5 科） | **P0** |
| 5 | 修正 `total_score` / `listen_total` 语义（现状 `listen_total=cscaTotalScore`、`total_score=Σquestion.score`）→ 统一 `total_score = structure.full_score`（100.00），`listen_*` 恒 0。✅ **v3.4 起题库已改分**，Σ 也恒 100.00，这条从「纠正 99.84」降级为「防将来再漂」 | P1 |
| 6 | 回 `remainingSeconds` / `deadlineTime` / `deductType` / `deductAmount` / `action` | P1 |
| 7 | 🔴 **写入个人资料快照** `real_name` / `gender` / `nationality` / `birthday`（取自 `UserClient.getUserById`，写法与 HSK `startExam:198-237` 一致）。因为 [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 已在开考前硬拦这 5 项，**快照必非空** → 成绩单 `candidate.name` 不再需要回落 | P1 |

**入参**（`CSCAExamRecordRequest`，**字段不变，只加校验**）

```json
{ "version": "CSCA", "subjectTypeMapping": "math", "languageVersion": "chinese" }
```

| 字段 | 说明 |
|---|---|
| `version` / `subjectTypeMapping` / `languageVersion` | **改为必填**（现状可为 null → `selectByCscaParams(null,…)` 会退化成"版本不限定"，抽到错卷） |
| ~~`confirmPointDeduct`~~ | **本期不加**（点数体系未实现）。后续接点数时再补，加可选字段不破坏兼容 |

**返回 JSON**（`ExamRecordResponse` **原有字段全保留**，新增）

```json
{
  "code": 200, "message": "开始考试成功",
  "data": {
    "id": 2101234567890123456, "paperId": 2101234567890123457,
    "status": 0, "startTime": 1760880320000,
    "deadlineTime": 1760883920000, "remainingSeconds": 3600,
    "durationMinutes": 60, "totalQuestions": 48, "totalScore": 100.00,
    "currentQuestionNumber": 1,
    "deductType": 1, "deductAmount": 0.00,
    "action": "CREATE", "resumed": false, "deducted": true
  }
}
```

**业务逻辑（改造后的完整顺序）**

1. **参数校验**：`version` 非空且 = `CSCA`；`subjectTypeMapping` ∈ 5 值（→ `8101`）；`languageVersion` ∈ 2 值且中文科目不接受 `english`（→ `8102`）
2. **续考优先**：`selectOngoingCSCAExamByUserIdAndSubjectTypeMapping(userId, version, subject, language)`
   - 命中且**未超时** → 直接 `return`（**`deducted=false`、`resumed=true`、不扣任何次数**）—— 需求 2.5.2「续考不重复扣」
   - 命中但**已超时** → 先内部自动交卷（`auto=true`），再走"新建"流程
3. **资料校验（硬门槛）**：5 项缺一 → `8104` + `incompleteFields`（与 `queryExamInProgress` 同一套，见 [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验)）；通过后把 `real_name` / `gender` / `nationality` / `birthday` **写进 `exam_record` 快照**（第 7 条改造点）
4. **卷可用性**：`selectUntakenPaperCSCA` 为空 → 清 `user_taken_paper` 重抽 → 仍空 → `8103`；`exam_paper_structure` 无模板 → `8103`
5. **次数校验 + 扣减**（🔴 **复用 `user_exam_quota`，不新造点数账本**）

🔒 **已定 B 方案：每科各 3 次**（`level` 存科目码，一人 5 行）。下面这段就是最终实现口径，**不再有 A/B 两种选择**。

**① 数据模型**

```
user_exam_quota
  exam_type='CSCA', version='CSCA', level IN ('arts_chinese','science_chinese','math','physics','chemistry')
  每个用户 5 行，每行 total_quota=3 / used_quota=0 / remain_quota=3
  唯一键 uk_user_exam_type_level(user_id, exam_type, version, level, deleted) → 天然防重
```

**② 校验 + 扣减（全部复用现有件，只加 2 个薄重载）**

```java
// ── 校验（只读）────────────────────────────────────────────────
// 🆕 4 参重载，内部就是调已存在的 selectByUserIdAndExamType(userId, examType, version, level)
if (!userExamQuotaService.hasAvailableQuota(userId, "CSCA", "CSCA", subject)) {
    throw new BusinessException(8105, "该科目考试次数已用完");
}

// ── 扣减（事务内）──────────────────────────────────────────────
UserExamQuota q = userExamQuotaService.getQuota(userId, "CSCA", "CSCA", subject);   // 🆕 4 参重载
// ✅ Service 已封装好：返回 false = 没抢到（remain_quota 已是 0）
if (!userExamQuotaService.decrementQuota(q.getId())) {
    throw new BusinessException(8105, "该科目考试次数已用完");   // 并发被抢光 → 整笔回滚
}
// exam_record.deduct_type = 1（免费次数）、deduct_amount = 0.00、deduct_detail = null
```

**③ 🔴 为什么绝对不能用 `decrementQuotaByUser`**

```sql
-- 现有 SQL（HSK 在用）—— WHERE 里没有 level
UPDATE user_exam_quota SET used_quota = used_quota + 1, remain_quota = remain_quota - 1
WHERE user_id = ? AND exam_type = ? AND version = ? AND remain_quota > 0
-- B 方案下一个人有 5 行 CSCA → 这一条 SQL 会把 5 科全扣掉（考数学，物理化学次数也没了）
```

`decrementQuota(id)` 才是 B 方案的正确选择，而且它比 `decrementQuotaByUser` 更严格：

| | `decrementQuota(id)` ✅ 用这个 | `decrementQuotaByUser` ❌ B 方案禁用 |
|---|---|---|
| 定位精度 | 精确到一行（`WHERE id=?`） | `WHERE user_id+exam_type+version` → **5 行一起扣** |
| 防超卖 | `AND remain_quota > 0` | 同样有 |
| 刷 `updated_time` | ✅ 有 | ❌ 没有 |
| 过滤 `status` / `deleted` / 有效期 | 靠前置 `getQuota` 查（`status=1 AND deleted=0`） | ❌ 完全不过滤，禁用行也会被扣 |
| 失败可感知 | ✅ 返回 0 → Service 返 `false` → 判 `8105` | ❌ HSK 侧**从不检查返回值**，扣失败静默放行 |

**④ 需要新增的代码（只此 3 处，其余零改动）**

| # | 位置 | 改什么 |
|---|---|---|
| 1 | `UserExamQuotaService` + `Impl` | 加 `getQuota(Long userId, String examType, String version, String level)` —— 实现一行：`baseMapper.selectByUserIdAndExamType(...)` |
| 2 | 同上 | 加 `hasAvailableQuota(Long userId, String examType, String version, String level)` —— 上面那句 + `remainQuota > 0`（顺带修掉现有 3 参版本日志里打了 `level` 却没有 level 参数的小 bug） |
| 3 | `startCscaExam`（:269） | 上面 ② 那 6 行：校验 → 取行 → 扣减，全在 `@Transactional` 内 |

> 📌 `UserExamQuotaMapper` **一行都不用改**：`selectByUserIdAndExamType(带 level)` 和 `decrementQuota(id)` 都已存在。
>
> 🔴 **CSCA 任何地方都不要调 3 参的 `getQuota` / `hasAvailableQuota`** —— 它们走 `selectByUserIdAndExamTypeAndVersion`（**无 `level` + `LIMIT 1`**），B 方案下会随机命中某一科，等于把 5 科的次数混成一份。

**⑤ 共用口径**

| 项 | 口径 |
|---|---|
| `exam_type` | `'CSCA'`（HSK / HSKK / Proficiency 之外的新值，天然隔离） |
| `version` | `'CSCA'` |
| `level` | **科目码**：`arts_chinese` / `science_chinese` / `math` / `physics` / `chemistry`（`varchar(50)`，够长） |
| 🔴 `level` 不能空 | 列是 `NOT NULL`；唯一键含 `level`，`NULL` 不参与判重 → 会插重复行 |
| `deduct_type` | 扣成功写 `1`（免费次数）；续考复用写 `0` |
| 事务 | 次数扣减 + `exam_record` 插入 + `initAnswerCard` + `user_taken_paper` **同一 `@Transactional`**（同库，不需要幂等键） |
| 无行时 | `getQuota` 返 `null` → `8105`（与 HSK 一致：查不到就当没次数） |
| 续考 | 命中 `status=0` 会话 → **直接返回，不校验、不扣减**（[3.2.1](#321--改造-post-answerstartcsca) 第 2 步） |

> 📌 **点数体系（会员赠送 / 点数包 / 单次 2 点）本期不做** —— 全库无点数表、无账本、无发放链路。`deduct_type` 已按 `0=未扣 / 1=免费次数 / 2=点数` 预留，将来接点数时**只在 `8105` 之前插一段分支**，接口形状不变（[4.3](#43-待确认事项) 第 1 条）。

6. **建会话**：写 `exam_record`（含 `deadline_time` / `deduct_type` / `deduct_amount` / `deduct_detail`）→ `initAnswerCard` → `user_taken_paper`

**涉及表**

| 表 | 操作 |
|---|---|
| `exam_paper` / `exam_paper_structure` | 读 |
| `exam_record` | **INSERT**（🆕 写 `deadline_time` / `deduct_amount` / `deduct_detail`） |
| `exam_answer` | **INSERT × N**（`initAnswerCard`，已有） |
| `user_taken_paper` | **INSERT**（已有） |
| **`user_exam_quota`** | **SELECT 1 行 + UPDATE**（`used_quota` +1 / `remain_quota` -1），走**该科目那一行**：`selectByUserIdAndExamType(…, level=科目码)` + `decrementQuota(id)` |
| `exam_number` | INSERT（准考证号，已有链路） |

**数据流向**

```
POST /answer/start/csca
  → ExamRecordServiceImpl#startCscaExam
      ├─ 参数校验（🆕）
      ├─ selectOngoingCSCAExam…（已有）→ 命中 → return（不扣）
      ├─ 资料校验（🆕）
      ├─ selectUntakenPaperCSCA（已有，🆕补 exam_type=2）
      ├─ 【事务开始】
      │    ├─ 次数校验 + 扣减（🆕 复用 UserExamQuotaService / decrementQuota）
      │    ├─ INSERT exam_record（🆕 deadline_time / deduct_*）
      │    ├─ initAnswerCard（已有）
      │    └─ INSERT user_taken_paper（已有）
      └─【事务提交】→ ExamRecordResponse（🆕 remainingSeconds 等）
```

### 3.3 答题

#### 3.3.1 🔧 改造 GET /answer/paper/csca/detail/{paperId}

**现状**（`ExamAnswerController:226` → `ExamRecordServiceImpl:1809` `getCscaPaperDetailWithAnswers`）：

```java
// 已有：查卷 → 查结构 → 查题 → 查分组 → 查用户答案 → 按 content_type 分组组装
// 🔴 缺陷：ExamPaperDetailDTO 的 QuestionDTO 里
//        .answer(question.getAnswer())       ← 标准答案直接下发
//        .analysis(question.getAnalysis())  ← 解析直接下发
```

**改造点**

| # | 改造 | 级别 |
|---|---|---|
| 1 | 🔴 **Service 层不再 `set` `answer` / `analysis`**（DTO 字段保留为 `null`，老前端不崩） | **P0** |
| 2 | 响应头层加 `remainingSeconds` / `deadlineTime` / `recordId`（整卷 DTO 里新增一个 `examMeta` 段） | P1 |
| 3 | 进接口先判超时：命中即内部自动交卷 → `8109` | P0 |
| 4 | 题目**按 `number` 升序**（现状已按题号排序，保持不变） | — |

**入参**：`paperId`（路径，不变）+ 可选 `?recordId=`（不传则按 `selectByPaperAndUser` 查，保持兼容）

**返回 JSON**（`ExamPaperDetailDTO` **原结构不变**，只说明变化）

```json
{
  "code": 200, "message": "操作成功",
  "data": {
    "examMeta": {
      "recordId": 2101234567890123456,
      "subjectType": "math", "subjectTypeText": "数学",
      "languageVersion": "chinese",
      "durationMinutes": 60, "fullScore": 100.00, "totalQuestions": 48,
      "deadlineTime": 1760883920000, "remainingSeconds": 2080
    },
    "sections": [
      {
        "contentType": "SEC_READ", "contentName": "阅读",
        "durationMinutes": 60, "fullScore": 100.00, "questionCount": 48,
        "questions": [
          {
            "id": 2101234567890123901, "number": 1,
            "typeId": "SINGLE", "typeIdRaw": "单选",
            "content": "已知函数 f(x) = …", "passage": null,
            "options": [ { "key": "A", "value": "…" }, { "key": "B", "value": "…" } ],
            "score": 2.50, "groupId": null,
            "userAnswer": "A", "answered": true, "favorite": false,
            "answer": null,
            "analysis": null
          }
        ]
      }
    ],
    "groups": []
  }
}
```

| 字段 | 口径 |
|---|---|
| `answer` / `analysis` | 🔴 **恒 `null`**（考试中绝不下发）。老前端若判空已处理，未处理也只是显示空白，**不会报错** |
| `typeId` | 对外只两个值：`SINGLE` / `MULTI`（库中 8 种原名**不透出**，`typeIdRaw` 仅供排查） |
| `userAnswer` / `answered` | 从 `exam_answer` 回填（已有逻辑） |
| `favorite` | 🆕 查 `csca_question_favorite`（`source='exam'`、`record_id=recordId`、`deleted=0`） |
| `examMeta.remainingSeconds` | 服务端算：`(deadline_time - now) / 1000`，**不接受客户端报时** |

**业务逻辑**

1. 查 `exam_record`（按 `paperId + userId`，`status=0`）→ 无 → `8107`
2. **超时判定**：`now > deadline_time` → 内部自动交卷 → `8109`
3. 查卷 / 结构 / 题目 / 分组 / 用户答案（**已有逻辑**）+ 🆕 收藏态（`csca_question_favorite`，`user_id + question_id IN 本卷 + deleted=0`，**与答题卡同一口径**）
4. 组装时**跳过** `answer` / `analysis` 两个 setter

**涉及表**：`exam_paper` / `exam_paper_structure` / `question` / `question_group` / `exam_answer` / `exam_record`（读）+ `csca_question_favorite`（🆕 读）

---

#### 3.3.2 🔧 改造 POST /answer/submit

**现状**（`ExamAnswerController:103` → `ExamAnswerService#submit`）：

```java
// 🔴 缺陷 1：新建 exam_answer 行时不写 exam_record_id → 之后按 recordId 查不到该行
// 🔴 缺陷 2：examAnswer.setIsCorrect(request.getIsCorrect()) —— 客户端可伪造对错
// 🔴 缺陷 3：按 question.section_mapping 更新分部分计时（CSCA 为 NULL，白跑一次 SQL）
```

**改造点**

> 🔴 **分支前提（先看这条）**：`/answer/submit` 是 **HSK / CSCA 共用**的（`ExamAnswerController:103`），**没有 CSCA 专用版本**。下列改造**一律只在 `exam_type=2`（CSCA）分支生效**，HSK 走原逻辑。`exam_type` 从 `exam_paper` 或 `exam_record` 取（会话里已有）。
> ⚠️ **为什么不能全局改**：HSK 前端在答题中用 `answer` 本地判分、把 `isCorrect` 传上来做**即时对错反馈**；若全局恒置 0，HSK 答题页会全部显示"错"。而 HSK 的成绩本来就不依赖此值（交卷后 `AsyncGradingServiceImpl:76-101` 用 `question.getAnswer()` 异步重判并覆盖），所以**保留现状对 HSK 无害、改了反而回归**。

| # | 改造 | 生效范围 | 级别 |
|---|---|---|---|
| 1 | 🔴 **新建行必写 `exam_record_id`**（入参新增可选 `examRecordId`；不传则按 `paperId+userId` 反查 `status=0` 的记录） | **两端都改**（HSK 是补全，无行为变化） | **P0** |
| 2 | 🔴 **忽略入参 `isCorrect`**，服务端**恒置 0**（未判分）。`AnswerSubmitRequest.isCorrect` 字段保留但不再使用 | 🔴 **仅 CSCA**；HSK 仍采信客户端值 | **P0** |
| 3 | **不碰 `exam_section_timer`** | **仅 CSCA**（`exam_type=2`） | P1 |
| 4 | 校验 `questionId` 属于本卷（→ `8110`）；校验会话 `status=0`（→ `8108`）；`answer` 长度 ≤ 64（→ `8112`） | 仅 CSCA | P1 |
| 5 | 顺带更新 `exam_record.current_question_number = questionNumber` | 仅 CSCA（HSK 有独立的 `updateProgress`，不要重复写） | P1 |
| 6 | **不判分、不写 `points`**（需求 2.2） | 仅 CSCA | — |

**入参**（`AnswerSubmitRequest`，**字段不变**）

```json
{ "paperId": 2101234567890123457, "questionId": 2101234567890123901, "questionNumber": 1,
  "answer": "A", "section": null, "examRecordId": 2101234567890123456 }
```

| 字段 | 说明 |
|---|---|
| `examRecordId` | 🆕 **可选**。CSCA 场景**强烈建议传**（前端建会话时就拿到了）；不传走兜底反查 |
| `isCorrect` | ⛔ **CSCA 传了也忽略**（恒 0）；HSK 仍按传入值落库（见上方「分支前提」） |

**返回 JSON**（`AnswerResponse`，**结构不变**）

```json
{ "code": 200, "message": "提交成功",
  "data": { "id": 9, "paperId": 2101234567890123457, "questionId": 2101234567890123901,
            "questionNumber": 1, "answer": "A", "answered": 1, "isCorrect": 0,
            "remainingSeconds": 2080 } }
```

**业务逻辑**

1. 会话校验：`exam_record` 存在 + `status=0`（→ `8108`）+ `now <= deadline_time`（超时 → 自动交卷 + `8109`）
2. 题目归属：`questionId` 在该 `paperId` 的题集内（→ `8110`）
3. UPSERT `exam_answer`：`answer` / `answered=1` / **`exam_record_id`** / **`is_correct=0`（仅 CSCA；HSK 用入参值）** / `updated_time`
4. 更新 `exam_record.current_question_number`（仅 CSCA）
5. **不写 `points`、不写 `is_correct`、不动 timer**（仅 CSCA）

> ⚠️ **`answer` 为空串**：视为**取消作答**（`answered=0`、`answer=null`），答题卡回到未答态。

**涉及表**：`exam_answer`（UPSERT）/ `exam_record`（UPDATE `current_question_number`）/ `question`（读）

---

#### 3.3.3 ⛔ 不用 POST /answer/batch —— 前端零调用，实测还 500

**结论（v2.9 据实测改判）**：本期 **CSCA 不走这个端点，也不改它**。

| 证据 | 说明 |
|---|---|
| 前端常量表（`api_constants.dart`，85 个常量全量比对） | **没有 `/answer/batch` 这一项** —— `ExamApiProvider` 里也没有对应方法 |
| 实测 `POST /api/exam/answer/batch`，body `{"paperId":…, "answers":[{"questionId":…,"questionNumber":1,"answer":"A"}]}` | 返回 `{"code":500,"message":"系统内部错误"}`（HSK/CSCA 都走不通） |
| 断网补传的真实做法 | 前端恢复网络后**逐题重发 `POST /answer/submit`**（该端点本身是 UPSERT，重发幂等） |

> 🔻 原 §3.3.3 的「批量上限 200 / 逐条 UPSERT / 返回 `failed[]`」整套设计**整节作废**：既然前端不从这条路走，改造它等于给死代码加功能。若将来 App 要做批量补传，**先修 500 再加需求**。
>
> ⚠️ 顺带记一条：`BatchAnswerRequest` 的字段是 `{paperId, userId, answers[{questionId, questionNumber, answer, section}]}`，**没有 `examRecordId`** —— 这也是 500 的嫌疑点之一（`batchSubmit` 内部按 `paperId+userId` 反查记录，查不到时 `examRecordId=null`，`selectByPaperUserQuestion` 拼 `= NULL` 恒空）。**本期不修**。

---

#### 3.3.4 🆕 新增 POST /answer/csca/favorite — 考试内收藏

**为什么不能拿 `/answer/paper/tag` 当收藏**（2026-10-22 确认）

`POST /answer/paper/tag`（`ExamAnswerController:238`）是**考试标记**，不是收藏 —— 两个不同的东西：

| 维度 | 标记（Mark） | 收藏（Favorite） |
|---|---|---|
| 端点 | ✅ **复用** `POST /answer/paper/tag`（**HSK 共用**） | 🆕 **本端点** |
| 落库 | `exam_answer.is_tag`（`UPDATE … WHERE exam_record_id + question_id`） | `csca_question_favorite`（`user_id + question_id` 唯一） |
| 粒度 | **一场考试 × 一道题** | **一个用户 × 一道题**（跨场次、跨科目长期有效） |
| 语义 | 做题时「这题先记住，回头再看一眼」 | 「这题我想以后再练」 |
| 生命周期 | 随本场考试；交卷后只留在本场答题卡 / 诊断报告 | 永久，进「我的 → 学习与测试 → 收藏夹」 |
| 答题卡表现 | 网格**黄色格** | **★ 角标**（与颜色独立） |
| 谁会用 | HSK + CSCA 都要 | 只有 CSCA（HSK 无收藏夹） |
| 判分影响 | 无 | 无（需求 4.2「收藏标记独立于作答」） |

> 🔴 **`/answer/paper/tag` 一行不改**：它是 HSK 答题页的标记能力，`UPDATE exam_answer SET is_tag` 的语义在 HSK 里是对的，改它 = 改 HSK 行为。
> 答题页上是**两个并列按钮**：★（收藏）→ 本端点；「标记」→ `paper/tag`。
> ⚠️ 现有 `tag()` 实现收了 `userId` 却**没使用**（只按 `exam_record_id + question_id` 定位，不校验归属）—— 属 HSK 链路，本次**不修**。

**现状**：exam-service **零收藏代码** —— `csca_question_favorite` 在全仓 `*.java` / `*.xml` **零命中**。练习侧已有写接口（`feature-20261012-lhy-CSCA练习` 分支的 `PUT /api/practice/csca/favorites/{questionId}`），考试侧没有，**必须新增**。

**端点**

```
POST /api/exam/answer/csca/favorite
```

| 项 | 值 |
|---|---|
| 归属 | `ExamAnswerController`（**现有文件加方法**）→ `ExamAnswerService#favoriteCsca` |
| 鉴权 | **强鉴权**：`userId` 取自 Token（`requireAuthenticatedAppUserId`），未登录 / 非 APP → `401` |
| 新增类 | `CscaFavoriteRequest` / `CscaFavoriteResponse`（**2 个 DTO**，不新建 Controller / Service / Mapper） |

**入参**

```json
{ "questionId": 2101234567890123901, "examRecordId": 2101234567890123456, "favorite": true }
```

| 字段 | 必填 | 口径 |
|---|---|---|
| `questionId` | 是 | 题目 id。**声明为 `String` 后手工解析**（19 位雪花，前端直接传字符串也不炸） |
| `examRecordId` | 是 | 本场考试记录 id（`exam_record.id`）→ 写快照 `record_id`，同时用来取卷的科目 / 语言快照 |
| `favorite` | 是 | **显式最终态**：`true` 收藏 / `false` 取消。**不做「不传就翻转」兜底**（新端点无老客户端；翻转会让重放不幂等） |

> **为什么是一个 `POST` + 显式 `favorite`，而不是练习侧那对 `PUT` / `DELETE`**：
> ① 只新增 **1 个**端点（不是 2 个）；
> ② 形状与现有 `POST /answer/paper/tag`（`questionId` + `examRecordId` + 状态位）一致，前端改动最小；
> ③ 断网补传时只看「最后一次状态」，重放与顺序无关，天然幂等。
> 🔴 与练习侧的**唯一差异是 HTTP 方法**，业务口径（软删复活、回最终态）完全一致，前端可复用同一段处理逻辑。

**返回**

```json
{ "code": 200, "message": "操作成功",
  "data": { "questionId": "2101234567890123901", "favorite": true, "favoriteCount": 12 } }
```

| 字段 | 口径 |
|---|---|
| `questionId` | **字符串**（新增端点按字符串序列化，与练习侧 `CscaFavoriteResponse` 一致） |
| `favorite` | **最终态**：`true` / `false`（不是「本次做了什么」） |
| `favoriteCount` | 该用户**已收藏总题数**（`user_id + deleted = 0`，**不分 `source`**）—— 供「我的收藏」角标。⚠️ 与答题卡的 `favoriteCount`（**本卷内**被收藏题数）是两个口径 |

**业务逻辑**

1. 强鉴权取 `userId`（失败 `401`）
2. 查 `exam_record`：`id = examRecordId AND user_id = userId` → 不存在 / 不属于本人 → `8107`
   - **本端点要校验归属**（与练习侧"`recordId` 只作快照、不校验"不同）：这里必须读这条记录才能拿到卷快照，顺手校验成本为零
   - ⚠️ **不校验 `status`**：交卷后在看诊断报告时也要能收藏
3. 查 `exam_paper`（`examRecord.paperId`）取两个快照：
   - `section` ← `exam_paper.subject_type_mapping`
   - `language_version` ← `exam_paper.language_version`
   - 🔴 **不能用 `question.subject_type_mapping`**：PROD 该列 1904 行**全 `NULL`**
4. 准入校验：该 `questionId` 必须属于本卷 → 否则 `8006`
   ```sql
   SELECT 1 FROM question WHERE id = #{questionId} AND paper_id = #{paperId} AND deleted = 0
   ```
   🔴 **没有 `exam_paper_question` 这张表**（实测 TEST 库不存在，练习文档里的同名说法也不适用）——卷题关联就是 `question.paper_id`。写成 `exam_paper_question` 会直接 `Table doesn't exist`
5. UPSERT `csca_question_favorite`
6. `COUNT(*) WHERE user_id = ? AND deleted = 0` → `favoriteCount`
7. **不碰** `exam_answer`（不写 `is_tag` / `is_correct` / `answered`）、不改 `exam_record`、不判分

**SQL**（与练习侧同一张表、同一套软删复活逻辑）

```sql
-- 收藏与取消共用一条：唯一键 uk_user_question(user_id, question_id)，不含 deleted → 软删可复活
INSERT INTO csca_question_favorite
    (user_id, question_id, section, language_version, source, record_id,
     deleted, created_by, update_by, created_time, updated_time)
VALUES (#{userId}, #{questionId}, #{section}, #{languageVersion}, 'exam', #{examRecordId},
        #{deleted}, #{userId}, #{userId}, #{now}, #{now})
ON DUPLICATE KEY UPDATE deleted = VALUES(deleted), updated_time = VALUES(updated_time);
```

🔴 **`ON DUPLICATE KEY UPDATE` 只更新 `deleted` + `updated_time`**，**不覆盖** `source` / `record_id` / `section` / `language_version`：

- 这题若是**练习时**先收藏的（`source='prac'`），考试里再点 ★ → 命中同一行，`source` 仍是 `prac`
- 这不是 bug：`source` / `record_id` 记的是「**第一次**收藏发生在哪一轮」，后一次收藏不该改写历史
- 反过来，考试里点**取消**会把练习时收藏的那行也软删掉 —— 收藏全局只有一份状态，这是对的

**错误码**

| 码 | 场景 |
|---|---|
| `401` | 未登录 / 非 APP |
| `8005` | `questionId` / `examRecordId` 空或非数字 |
| `8006` | 题目不在本卷（含 HSK 题、题已被移出卷） |
| `8107` | 考试记录不存在，或不属于当前用户 |

**涉及表**：`csca_question_favorite`（UPSERT + COUNT）/ `exam_record`（读）/ `exam_paper`（读）/ `question`（读，准入：`id + paper_id + deleted=0`）

> ⚠️ 这是 exam-service **首次触碰 practice 域的表**（`csca_question_favorite`，与练习侧同库同表）。备选方案（由 practice-service 出内部 Feign 统一写）见 [4.3](#43-待确认事项) 第 14 条，**本期取直写** —— 与错题本同步（[3.4.1](#341--改造-post-recordpaperidsubmitcsca) 第 6 条）保持同一策略。

---

#### 3.3.5 🔧 改造 GET /answer/csca/card/detail/{paperId}

**现状**（`ExamAnswerController:157` → `ExamAnswerService#getCSCAAnswerCardDetail:320`）：

```java
// 🔴 缺陷 1：只有「标记」没有「收藏」—— isTag 取自 exam_answer.is_tag，收藏表零引用
// 🔴 缺陷 2：currentQuestionNumber.equals(...) 无空判断 → 传 null 时 NPE
// 🔴 缺陷 3：section 写死 "CSCA"；无剩余时间
```

**改造点**

| # | 改造 | 生效范围 |
|---|---|---|
| 1 | `isTag` **保持原样**（`exam_answer.is_tag` = 标记）—— 它是需求 4.3 网格四色之一，**不是收藏** | 不动 |
| 2 | 🆕 `favorite` 逐题查 `csca_question_favorite`（`user_id` + `question_id IN 本卷` + `deleted = 0`） | CSCA |
| 3 | 🆕 顶层 `tagCount` / `favoriteCount` 两个计数（交卷弹窗要用的是 `tagCount`，见 [3.3.6](#336--复用-get-answerchecksubmitpaperid)） | CSCA |
| 4 | `current` 用 `Objects.equals(...)`（**修 NPE**） | CSCA |
| 5 | 新增 `remainingSeconds` / `deadlineTime`（服务端算） | CSCA |

> ⚠️ **`favorite` 不能按 `record_id` / `source` 过滤**：同一题可能**练习时就收藏过**，考试答题卡照样要显示 ★。收藏是「用户 × 题」的全局状态，与哪场会话无关。

**返回 JSON**（`AnswerCardDetailDTO` 原字段全保留，新增标 🆕）

```json
{
  "code": 200, "message": "操作成功",
  "data": {
    "paperId": 2101234567890123457, "recordId": 2101234567890123456,
    "totalQuestions": 48, "answeredCount": 30, "unansweredCount": 18,
    "tagCount": 3, "favoriteCount": 2,
    "currentQuestionNumber": 31,
    "deadlineTime": 1760883920000, "remainingSeconds": 2080,
    "questions": [
      { "questionId": 2101234567890123901, "number": 1,  "answered": true,  "isTag": 0, "favorite": false, "current": false },
      { "questionId": 2101234567890123902, "number": 31, "answered": false, "isTag": 1, "favorite": true,  "current": true  }
    ]
  }
}
```

**前端怎么用这两个态（别混）**

| 视觉 | 取自 | 说明 |
|---|---|---|
| 网格**四色**（红=当前 / 绿=已答 / 黄=标记 / 空=未答） | `answered` / `isTag` / `current` | 需求 4.3 的四色说的是**标记**，不是收藏 |
| **★ 角标** | `favorite` | 与颜色**独立**：一个格子可以既是黄格又带 ★ |
| 顶部四项统计 | `totalQuestions` / `answeredCount` / `unansweredCount` / **`tagCount`** | 需求 4.3 |

**业务逻辑**

1. 查 `exam_record`（`paperId + userId`，`status = 0`）→ `8107`
2. 超时判定（同 [3.3.1](#331--改造-get-answerpapercscadetailpaperid)）
3. `exam_answer` 按 `recordId` 查（**已有**）→ `answered` / `isTag` 态
4. `csca_question_favorite` 按 `user_id + question_id IN (本卷题 id)` 查 → `favorite` 态（**不过滤 source / record_id**）
5. 拼网格（**按 `number` 升序**）

**涉及表**：`exam_record`（读）/ `exam_answer`（读）/ `csca_question_favorite`（🆕 读）

---

#### 3.3.6 ✅ 复用 GET /answer/checkSubmit/{paperId}

**现状**（`ExamAnswerController:184`）：返回 `ExamSubmitCheckDTO`（`canSubmit` / `totalQuestions` / `answeredCount` / `unansweredCount` / `unansweredQuestions[]` / `message`）。

**处置**：**直接复用**，交卷确认弹窗（需求 4.4）的四项统计里，**三项由它提供**（总题数 / 已答 / 未答），**第四项「标记题数」取 [3.3.5](#335--改造-get-answercscacarddetailpaperid) 的 `tagCount`（= `exam_answer.is_tag=1` 的题数）**。

> ⚠️ **不是 `favoriteCount`**：需求 4.4 要的是**标记数**（做题时"回头再看"的题），收藏是另一套长期资产（★ 角标），两者不能混算。

**唯一补充**：CSCA 场景**不强制 `canSubmit`**（允许未答完就交卷，需求未要求强制），前端按 `unansweredCount > 0` 提示即可。

---

### 3.4 交卷

#### 3.4.1 🔧 改造 POST /record/{paperId}/submit/csca

**现状**（`ExamRecordController:68` → `ExamRecordServiceImpl:555`）：

```java
// 已有：查 exam_record → 查题目 → 查 exam_answer → 循环判分 → UPDATE exam_record(status=1)
// 🔴 缺陷 1：correctAnswer.equalsIgnoreCase(userAnswerContent) → 多选（35 题）必判错
// 🔴 缺陷 2：无 status!=0 判断、无 UPDATE ... WHERE status=0 → 并发/重复交卷会重复判分
// 🔴 缺陷 3：未答题也计入 wrong_count → 报告"答错 16"其实是"未答 16"
// 🔴 缺陷 4：无超时判定（客户端改本地时间可永久答题）
// 🔴 缺陷 5：不写错题本（需求 2.6）
// 🔴 缺陷 6：不区分手动/自动交卷
```

**改造点**

| # | 改造 | 级别 |
|---|---|---|
| 1 | 🔴 判分改 `CscaAnswerNormalizer#equalsSet`（集合比较，[4.2](#42-答案归一化与判分)） | **P0** |
| 2 | 🔴 **幂等**：`UPDATE exam_record SET status=1 WHERE id=? AND status=0`，返回 0 行 → 直接回已有结果 | **P0** |
| 3 | 🔴 `wrongCount` 只算 `answered=1 AND is_correct=2`；未答单独算 `unansweredCount` | P1 |
| 4 | 🔴 支持 `auto` 参数（超时自动交卷），落 `exam_record`；超时判定以服务端 `deadline_time` 为准 | **P0** |
| 5 | 🔴 交卷时**同步错题本**（`csca_question_wrong`，`source='exam'`）→ 完整口径见 [3.7](#37-错题本考试侧只写不读)；**必须事务隔离**，不得让写错题本失败拖垮交卷 | **P0** |
| 6 | 卷面总分取 `exam_paper_structure.full_score`（100.00）。✅ v3.4 起 `Σquestion.score` 也 = 100.00，两者一致；仍取 `full_score` | P1 |

**入参**（**路径不变**；body 新增可选字段）

```json
{ "auto": true }
```

| 字段 | 说明 |
|---|---|
| `auto` | 🆕 可选。`true` = 超时自动交卷（前端倒计时归零时传）；缺省 `false`。**服务端不信任这个值做超时判定**，只用于标记 `submitSource` |

**返回 JSON**（`ExamRecordResponse`，**结构不变**，说明变化）

```json
{
  "code": 200, "message": "提交成功",
  "data": {
    "id": 2101234567890123456, "paperId": 2101234567890123457, "status": 1,
    "finalScore": 62.40, "totalScore": 100.00, "totalQuestions": 48,
    "answeredCount": 48, "correctCount": 30, "wrongCount": 18, "unansweredCount": 0,
    "accuracyRate": 0.63, "duration": 2080,
    "autoSubmitted": true, "deductType": 1, "deductAmount": 0.00
  }
}
```

**业务逻辑（改造后顺序）**

1. 查 `exam_record`（`paperId + userId`）→ 无 → `8107`
2. **幂等短路**：`status != 0` → 直接回已有结果（**不重复判分**）
3. **超时判定**：`now > deadline_time` → 强制 `auto=true`
4. **条件占位**：`UPDATE exam_record SET status=1, end_time=now WHERE id=? AND status=0` → 影响 0 行说明并发抢先 → 回 409
5. **判分**（逐条 `exam_answer`）：

| 情况 | 处理 |
|---|---|
| `answered=1` 且 `equalsSet(userAnswer, standardAnswer)` | `is_correct=1`、`points=question.score`、`correctCount++` |
| `answered=1` 但不相等 | `is_correct=2`、`points=0`、`wrongCount++`、**写错题本** |
| `answered=0` 或 `answer` 为空 | `is_correct=2`、`points=0`、`unansweredCount++`、**不写错题本**、⚠️ 不刷 `updated_time` |

6. **错题本同步**（只对"判错且已作答"）→ 🔗 **完整设计见 [3.7](#37-错题本考试侧只写不读)**（字段取值 / 三条硬规则 / 事务边界 / 读侧接法）。

   本节只强调两条最易错的：① 过滤条件是 `answered=1 AND is_correct=2`，**不能只用 `is_correct=2`**（未答题也是 2）；② `section` 取 **`exam_paper.subject_type_mapping`**，不是题上的（PROD 全 NULL）。

   🔴 **写错题本失败不得回滚交卷** —— `REQUIRES_NEW` + 外层 try-catch（[3.7.7](#377--事务边界p0上线阻塞)）。

7. **回写 `exam_record`**：`final_score` / `correct_count` / `wrong_count` / `unanswered_count` / `answered_count` / `duration` / `accuracy_rate` / `status=1`
8. **生成成绩单号**：`ExamNumberService#getScoreReportNumber`（已有链路，`leve` 传 `'CSCA'`）

**超时兜底（双保险）**

| 方式 | 位置 | 触发 |
|---|---|---|
| **惰性** | 任何会话请求（取卷 / 保存 / 答题卡 / 交卷）入口 | `now > deadline_time` → 内部调本逻辑 `auto=true`，回 `8109` |
| **定时** | `cscaExamTimeoutJob`（XXL-Job，5 分钟） | `status=0 AND deadline_time < now AND deadline_time IS NOT NULL` |

> 🔴 **Job 必须带 `deadline_time IS NOT NULL`**：现有 **42 条 `status=0` 历史脏数据** `deadline_time` 为空，不加条件会扫出大量 0 分报告（[4.8](#48-上线检查清单) 第 8 条）。

**涉及表**

| 表 | 操作 |
|---|---|
| `exam_record` | **UPDATE**（条件更新 + 幂等） |
| `exam_answer` | **UPDATE × N**（`is_correct` / `points`） |
| `question` | 读（标准答案 + 分值） |
| `csca_question_wrong` | **🆕 INSERT / UPSERT**（**独立事务，失败不回滚交卷**） |
| `exam_number` | INSERT（成绩单号） |

---

### 3.5 诊断报告

#### 3.5.1 🔧 改造 GET /record/csca/{examRecordId}/result

**现状**（`ExamRecordController:92` → `ExamRecordServiceImpl:759`）：返回 `CscaExamResultDTO`，**已包含**需求 4.5 的绝大部分字段：

```java
// 已有字段（不要重造）
recordId / paperId / subjectType / subjectTypeText / languageVersion / languageVersionText
status / score / totalScore / totalQuestions / answeredCount / correctCount / wrongCount
unansweredCount / accuracyRate / duration / durationText / avgTimePerQuestion
avgTimePerQuestionText / timeEvaluation / timeEvaluationType
questionCards[] { questionNumber, status, isTag, content, passage, options, userAnswer, correctAnswer }
```

**改造点**

| # | 改造 | 级别 |
|---|---|---|
| 1 | 补 `usedTimeText`（`durationText` 已有，实为同一值 → **前端直接用 `durationText`**，本条取消） | — |
| 2 | 补 `autoSubmitted`（`end_time` vs `deadline_time` 推断，[4.3](#43-待确认事项) 第 10 条） | P1 |
| 3 | 补 `favoriteCount` / `recordId` 字符串化提示 | P2 |
| 4 | **不做归属校验**（**by design**，见下方说明）——现状 `selectById` 后直接用，本版**保持** | — |
| 5 | `status=0`（未交卷）请求 → `8111` | P1 |
| 6 | `questionCards[]` **不带 `analysis`**（体积控制；点单题走 [3.5.2](#352--改造-get-recordpaperidquestionquestionid)） | P1 |
| 7 | **`userId` 不再下发**（或仅"本人查看"时下发）：报告要能给非答题者看，但不该把答题者的账号 id 一起抛出去 | P1 |

> 📌 **归属校验刻意不做（by design）**：报告需要能**分享给非答题者**查看（老师 / 家长 / 招生官 / 顾问），所以三个报告出口
> —— `GET /record/csca/{examRecordId}/result`、`.../scoreReport/preview`、`.../scoreReport` ——
> **一律只校验"已登录"，不校验 `userId` 是否等于记录归属人**。
>
> 由此产生的三条配套约束：
>
> | # | 约束 | 说明 |
> |---|---|---|
> | 1 | **访问控制 = 「id 即凭证」** | 依赖 `exam_record.id` 是 19 位雪花（不可枚举、不可猜）。⚠️ 若前端把 id 拼进可分享链接，**该链接等同于凭证**，不能放公开可爬的页面 |
> | 2 | **不返回答题者的账号敏感信息** | `CscaExamResultDTO.userId` 置 `null`；成绩单里的姓名/证件等按"报告展示所需"最小化 |
> | 3 | **不泄漏未交卷会话** | `status=0` 仍判 `8111`——分享的只能是**已成型的报告**，不能借 id 探测"某人正在考试" |
>
> ⚠️ **若产品后续要"免登录分享"**（微信转发链接给家长），需要另加**短链 + 有效期 + 水印**，并在链接里带
> `shareToken` 而不是裸 `examRecordId`——列入 [4.3](#43-待确认事项) 第 17 条。

**返回 JSON**（`CscaExamResultDTO`，**原字段全保留**，新增 2 个）

```json
{
  "code": 200, "message": "操作成功",
  "data": {
    "recordId": 2101234567890123456, "paperId": 2101234567890123457,
    "subjectType": "math", "subjectTypeText": "数学",
    "languageVersion": "chinese", "languageVersionText": "中文",
    "status": 1,
    "score": 62.40, "totalScore": 100.00,
    "totalQuestions": 48, "answeredCount": 48, "correctCount": 30,
    "wrongCount": 18, "unansweredCount": 0,
    "accuracyRate": 0.63,
    "duration": 2080, "durationText": "34:40",
    "avgTimePerQuestion": 43, "avgTimePerQuestionText": "43秒",
    "timeEvaluation": "偏快", "timeEvaluationType": "FAST",
    "autoSubmitted": true,
    "questionCards": [
      { "questionNumber": 1, "status": "correct", "isTag": 0, "content": "已知…",
        "passage": null, "options": { "A": "…", "B": "…" },
        "userAnswer": "A", "correctAnswer": "A" }
    ]
  }
}
```

**业务逻辑**

1. `selectById(examRecordId)` → 无 → `8107`
2. **不校验 `userId`**（by design，见上）；但**必须已登录**（`getCurrentUserId` 非空，否则 401）
3. `status=0` → `8111`
4. 组装 `CscaExamResultDTO`（**已有逻辑**）+ 新增字段；`userId` 置 `null`

**涉及表**：`exam_record` / `exam_paper` / `exam_answer` / `question`（读）+ `csca_question_favorite`（读 `isTag`）

---

#### 3.5.2 🔧 改造 GET /record/{paperId}/question/{questionId}

**现状**（`ExamRecordController:104`）：`getQuestionDetail(paperId, userId, questionId, examRecordId)` → 返回 `ExamResultDTO.QuestionResult`（**已含** 用户答案 / 标准答案 / 解析）。

**改造点**

| # | 改造 | 级别 |
|---|---|---|
| 1 | 🔴 **交卷后也能查**：现状 `getQuestionDetail` 内部走 `selectByPaperAndUser`（**只查 `status=0`**）→ 交卷后查不到记录 → **看不了单题解析**。改为按 `examRecordId` 直查 | **P0** |
| 2 | 校验 `questionId` 属于该卷（→ `8110`） | P1 |
| 3 | 未交卷的会话请求 → `8111`（**考试中不能看解析**） | **P0** |

**入参**（**不变**）：`paperId` / `questionId`（路径）+ `?examRecordId=`（**改为必填语义**，不传走兜底？→ 不传直接 `8107`）

**返回**：`ExamResultDTO.QuestionResult`（**结构不变**）

**涉及表**：`exam_record` / `exam_answer` / `question`（读）

---

### 3.6 模考记录与成绩单

> 🔴 **成绩单三个端点各管一段，不重复**（v3.7 补充，回答「`preview` 和 `scoreReport` 不是功能重复了吗」）
>
> | 端点 | 交出什么 | 谁调 | 为什么不能被另一个替代 |
> |---|---|---|---|
> | `GET …/scoreReport/preview` | **JSON 数据**（模板契约 + 统计 + `reportReady`） | 成绩单页首次进入 / 生成 PDF 之前 | 页面要画分数、正确率、48 格题号网格 → 必须有结构化的 48/80 条数据；**PDF 是二进制，渲染不出页面** |
> | `POST …/scoreReport` | 只**写**：存一条链接 | PDF 生成完之后 | 只写不读，与前两者无重叠 |
> | `GET …/scoreReport` | **文件**：CSCA → `302` 到 `report_url`；HSK → PDF 字节 | 点「下载」/ WebView / App 文件下载器 | ① 「给我 PDF」不该顺带拉 48/80 题 JSON（`preview` 是重接口）；② **HSK 也走这条路径** —— 保留它，App 的下载代码才不用按 `exam_type` 分叉；③ 桶将来改私有，只改这里的 302 目标，前端零改动 |
>
> 🔴 **v3.6 那版确实有一处重复，v3.7 已删**：`preview` 曾顺带下发 `reportUrl` → 同一个文件出现**两个出口**（前端可直接开直链、也可走 302），而且字段说明还写着「不要用它拼下载地址」，自相矛盾。现 `preview` **只回 `reportReady` 布尔**，链接**只由 `GET /scoreReport` 交出**。
>
> 📌 **「分享」怎么走**：App 端直接分享下载下来的 PDF 文件；若要「复制链接」，取 `GET` 的 `Location` 响应头（不跟随 302）。真要对外发长期链接属于「分享页」需求，另立接口 —— **不要在 `preview` 里开口子**。

#### 3.6.1 🔧 改造 GET /record/user/records

**现状**（`ExamRecordController:127` → `ExamRecordServiceImpl:1111`）：

```java
// 🔴 缺陷 1：未传时间 → 默认只查最近 30 天 → 模考记录"历史消失"
// 🔴 缺陷 2：level / source 过滤对 CSCA 无意义（CSCA level 恒 NULL）→ examLevel 拼出 "level null"
// ✅ 已有：ExamRecordDetailDTO 已含 subjectType / subjectTypeText / languageVersion / durationText
```

**改造点**

| # | 改造 | 级别 |
|---|---|---|
| 1 | 🔴 **取消 30 天默认**：不传 `startTime` / `endTime` → **查全量** | P1 |
| 2 | 🆕 新增筛选参数 `subjectTypeMapping` / `languageVersion` / `examType` | P1 |
| 3 | `examLevel` 对 CSCA 回 `null`（不要拼 `"level null"`） | P2 |
| 4 | `pageSize` 上限 100（→ `8112`） | P2 |
| 5 | 补 `answeredCount` / `unansweredCount` / `correctCount`（现有 DTO 只有 `listenCorrect` / `readCorrect` 等 HSK 分段字段） | P1 |

**入参**（**原有参数全保留**）

| 参数 | 说明 |
|---|---|
| `level` / `source` / `version` | 保留（HSK 用） |
| 🆕 `subjectTypeMapping` | CSCA 科目筛 |
| 🆕 `languageVersion` | CSCA 语言筛 |
| 🆕 `examType` | `2` = 只要 CSCA（**推荐 CSCA 列表页传这个**） |
| `startTime` / `endTime` | 毫秒；**不传 = 全量** |
| `pageNum` / `pageSize` | 默认 1 / 10，上限 100 |

**返回**：`IPage<ExamRecordDetailDTO>`（**结构不变**）

**涉及表**：`exam_record` / `exam_paper`（读）+ `exam_section_timer`（读，已有批量查）

---

#### 3.6.2 🆕 GET /record/{examRecordId}/scoreReport/preview

**用处**（需求 4.6）：成绩单**预览页**要结构化数据（前端渲染 CSCA 官方样式）。现有只有 PDF 二进制（#17），前端拿不到字段。

**落地位置**：`ExamRecordController#cscaScoreReportPreview` → `CscaScoreReportService#preview`

🔴🔴 **本端点不设计字段，只做「抄」——把官方模板的数据契约逐字段填满。**

模板真源：`D:\UserData\Downloads\CSCA成绩单模板\CSCA\HSK与CSCA模板_清晰Logo与HSK简版\平台接入\`

| 文件 | 作用 |
|---|---|
| `data.schema.json` | **权威契约**（JSON Schema 2020-12），本文的字段表就是它 |
| `report.js` | 渲染器 + 自带校验器（`CSCAReport.render(el, data)` / `validate`） |
| `sample-math.json` | 48 题数学样例（36 对 / 8 错 / 4 未答，得分 75） |
| `report.html` / `report.css` / `assets/` | A4 版式、校名抬头、校徽水印、APP 二维码 |
| `接入说明.md` | 口径与导出规则（满分 100、三态互斥、题量不写死、时区…） |

前端拿到 `data` 后**一行渲染，不做任何字段搬运**：

```js
CSCAReport.render(document.getElementById('report'), res.data);
```

> ⚠️ 模板自带的 `validate()` **不是摆设**：字段不合规会直接 `throw`，整页空白，连错误提示都不给用户。已实测的报错文案见下表。

**返回 JSON**（`data` 内的字段名、层级、类型**以模板为准**；v3.3 只在 `exam` / `result` 上**追加 5 个模板不读的附加字段**，见下方说明，其余不自造）

```json
{
  "code": 200, "message": "操作成功",
  "data": {
    "version": 1,
    "reportId": "CSCA-2113168625743364098",
    "candidate": { "id": "2112787850284290049", "name": "李惠莹" },
    "exam": {
      "attemptId": "2113168625743364098",
      "paperId": "2067119111506894849",
      "paperName": "CSCA_数学题库2026-6-6_03_97-144",
      "subject": "数学",
      "language": "中文",
      "startedAt": "2026-10-22T19:47:16+07:00",
      "submittedAt": "2026-10-22T19:47:19+07:00",
      "timeZone": "Asia/Ho_Chi_Minh",
      "durationSeconds": 3
    },
    "result": {
      "score": 75.0, "fullScore": 100, "questionCount": 48,
      "correctCount": 36, "wrongCount": 8, "unansweredCount": 4, "accuracyRate": 0.75
    },
    "questions": [
      { "questionId": "2105988213198270465", "index": 1, "status": "incorrect",
        "userAnswer": "D", "correctAnswer": "B" },
      { "questionId": "2105988213198270466", "index": 2, "status": "unanswered",
        "userAnswer": null, "correctAnswer": "A" },
      { "questionId": "2105988213198270467", "index": 3, "status": "correct",
        "userAnswer": ["A", "C"], "correctAnswer": ["A", "C"] }
    ],
    "reportReady": false
  }
}
```

> 上面只是**字段形状**示例（`questions` 截了前 3 条），**统计与得分数值取自模板自带 `sample-math.json`**（36 对 / 8 错 / 4 未答，得分 75.0 —— 仅示意；改分后真实值就是 `exam_record.final_score`），ID 沿用 [4.9](#49-联调实测记录2026-10-22真调-test-后端) 的实测记录。真实一次考试是 **48 条（数理化）或 80 条（中文）**，一次返回完，不分页。

**字段映射**（左列 = 模板契约，右列 = 后端必须这么填）

| 模板字段 | 类型 | 取值 |
|---|---|---|
| `version` | int | 恒 `1`（契约版本，写死，别跟文档版本混） |
| `reportId` | string | `"CSCA-" + examRecordId`。🔴 **不要用 `exam_record.score_record_number`** —— 实测 CSCA 记录该列**全 NULL**（`submitCscaExam` 从未生成过），拿它必空、必被前端拒 |
| `candidate.id` | string | `exam_record.user_id`（19 位雪花 → 字符串） |
| `candidate.name` | string | `exam_record.real_name`（**开考快照**）。🔒 已定：开考前 `8104` 硬拦 5 项资料（[3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验)）+ `startCscaExam` 补写快照（[3.2.1](#321--改造-post-answerstartcsca) 第 7 条）→ **新记录必非空**。只有**历史记录**（实测 156 条全 NULL）才回落 `UserClient.getUserById` → `nickname` → `username` |
| `exam.attemptId` | string | `examRecordId` |
| `exam.paperId` | string | `exam_record.paper_id` |
| `exam.paperName` | string | `exam_record.exam_name`（开考时快照的 `exam_paper.source`）。⚠️ `exam_paper` **没有 name 列**；别 JOIN 现取，卷改名会让老成绩单跟着变 |
| `exam.subject` | enum | 🔴 **5 科目码 → 4 值**，见下方映射表；传 5 值原件会被前端拒 |
| `exam.language` | string | `chinese` → `中文`；`english` → `English`（全库目前只有 `chinese`） |
| `exam.startedAt` | string | 🆕 `exam_record.start_time`（毫秒）→ ISO 8601 **带偏移量**：`2026-10-22T19:47:16+07:00`，格式化口径同 `submittedAt`（规则 4）。为 `null` 时前端回落 `submittedAt` |
| `exam.submittedAt` | string | `exam_record.end_time`（毫秒）→ ISO 8601 **带偏移量**：`2026-10-22T19:47:19+07:00` |
| `exam.timeZone` | string | 恒 `Asia/Ho_Chi_Minh`（与上一行的偏移量同值；模板默认值也是它） |
| `exam.durationSeconds` | int | `exam_record.duration`（秒）；null → `0` |
| `result.score` | number | 🔴 **直接取 `exam_record.final_score`，原样下发，不做任何换算**（卷面已是 100 分制）。🔒 **不做 `total_score` 兜底**（已定，规则 1） |
| `result.fullScore` | int | **恒 `100`**（模板 `const`），**不是** `total_score` |
| `result.questionCount` | int | `= questions.length` = 本卷题数（中文 80 / 数理化 48，**不写死**） |
| `result.correctCount` | int | 🆕 **正确总数** = `questions` 里 `status = correct` 的条数（🔴 **从 `exam_answer` 现算**，不抄 `exam_record.correct_count`，见规则 7） |
| `result.wrongCount` | int | 🆕 **错误总数** = `status = incorrect` 的条数，即 `answered=1 AND is_correct=2`。🔴 **不含未答** —— 实测 CSCA 记录 `wrong_count` 把未答也算进去（`answered_count=0` 却 `wrong_count=48`），照抄就错 |
| `result.unansweredCount` | int | 🆕 **未答总数** = `status = unanswered` 的条数 |
| `result.accuracyRate` | number | 🆕 **正确率** = `correctCount ÷ questionCount`，**0–1 小数、保留 2 位**（`0.75` = 75.0%），口径 = `exam_record.accuracy_rate`（`decimal`，实测 0.00 同尺度）。🔴 **不是 0–100**，也**不复用**记录上的旧值（CSCA 记录恒 0.00） |
| `questions[].questionId` | string | `question.id` 字符串 |
| `questions[].index` | int | **排序后的 `1..N`**（见规则 2） |
| `questions[].status` | enum | `correct` / `incorrect` / `unanswered`（见规则 3） |
| `questions[].userAnswer` | string \| string[] \| null | 单选 `"D"`；多选拆数组 `["A","D"]`；未答 `null` |
| `questions[].correctAnswer` | 可选 | `question.answer`，拆分规则同上 |
| `questions[].explanation` | 可选 | 🔴 **本期不下发**（见规则 5） |
| `reportReady` | bool | 🆕 **成绩单 PDF 是否已生成** = `exam_record.report_url` 非空（模板**不读**，前端用来决定「下载」按钮是亮还是走生成流程） |

> 🆕 **v3.3 新增 5 个下发字段**（`exam.startedAt` + `result` 的 4 个统计）：`data.schema.json` **没有 `additionalProperties: false`**，`report.js#validate()` 也只校验它自己列出的字段 → **加字段不会让模板抛错、不影响 `CSCAReport.render()`**（已核对 `report.js` 全文）。
> 但要注意：**模板根本不读这 4 个统计值** —— `statistics(d)` 是拿 `questions[].status` **自己再数一遍**（且它的 `accuracy` 是 **0–100** 一位小数，如 `75.0`）。所以这 4 个字段是**给前端自己用的**（APP 内摘要、记录列表、埋点），一旦与 `questions` 数出来不一致，**报告页显示模板算的、别处显示后端算的**，必然对不上。
> → 后端保证：`correctCount + wrongCount + unansweredCount == questionCount`，且三态判定与 `questions[].status` **同一次循环产出**（不许两套逻辑）。
>
> 🆕 **v3.6 追加 1 个顶层字段 `reportReady`**（模板**不读**，加在 `data` 顶层不影响 `report.js#validate()`，已确认 schema 无 `additionalProperties:false`）。用途：前端进成绩单页先看它 —— `false` 才走「渲染 → 生成 PDF → 上传 → [3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接)」；`true` 就直接亮「下载」按钮。**避免每次进页面都重新生成一遍 PDF。**
> 🔴 **v3.7 起不再下发 `reportUrl`**（v3.6 下发过一版，已删）：链接属于「下载」语义，唯一出口是 [3.6.3](#363--改造-get-recordexamrecordidscorereport--csca-改读已上传的-pdf)，见 [§3.6 开头分工表](#36-模考记录与成绩单)。

**科目映射（5 → 4）**

| `subject_type_mapping` | 卷上中文名（`exam_paper.subject_type`） | → `exam.subject` |
|---|---|---|
| `arts_chinese` | 文科中文 | `中文` |
| `science_chinese` | 理科中文 | `中文` |
| `math` | 数学 | `数学` |
| `physics` | 物理 | `物理` |
| `chemistry` | 化学 | `化学` |

> 🔒 **已定**：文科中文与理科中文**都印「中文」**（模板只有「中文」一个中文科目位，英文名 `Professional Chinese`）。传 5 值原件会被前端拒（已实测）。**报告上分不出文/理是既定代价** —— 由**前端在报告页标题旁补一行小字**（读 `exam_paper.subject_type` 原值），模板不动。要印在纸上必须改模板 `enum` + `names` + Word/PDF 样稿，见 [4.3](#43-待确认事项) 第 22 条。

**模板会直接抛错的 5 种情况**（实测报错原文，照抄自 `report.js#validate`）

| 后端若这样填 | 前端抛什么 |
|---|---|
| `result.fullScore` 填了 `total_score` 而不是字面量 `100`（历史记录 = **99.84**） | `CSCA 单科满分应为 100。` |
| `exam.subject = "文科中文"` / `"理科中文"` | `科目必须是中文、数学、物理或化学。` |
| `result.questionCount ≠ questions.length` | `题目数必须与 questions 中的记录数一致（1–1000 题）。` |
| `status = "unanswered"` 却给了 `userAnswer` | `未答题目的 userAnswer 应为空。` |
| `reportId` / `candidate.id` / `exam.attemptId` / `exam.paperId` 任一为空 | `正式数据必须有 reportId、candidate.id、exam.attemptId、exam.paperId。` |

**七条硬规则**

1. 🔒 **满分归一已彻底取消——试卷本身已是 100 分制，`score` 原样取 `final_score`**（v3.5 定案）。题库单题分值：文/理中文 `1.25 × 80 = 100.00`，数理化 **`2.00 × 40 + 2.50 × 8 = 100.00`**（[§2.4](#24-量级依据测试库实测非估算) 实测 TEST 库 5 科 **每卷 Σ`question.score` 恒为 100.00**）→ 模板 `fullScore` 的 `const 100` 天然满足。

   ```
   score = exam_record.final_score;   // 原样，不乘不除不判断
   fullScore = 100;                   // 恒定字面量，不读 total_score
   ```

   🔴 **明确不做 `total_score` 兼容兜底**（用户 2026-10-22 定：题库后续会统一改到位，不为老数据写分支）。副作用**已知且可接受**：
   - **改分前的历史记录** `total_score` 是快照的 **99.84**（实测 136 条老记录）→ 这类记录若当时满分作答，`final_score` 最多 **99.84**，成绩单就印 99.84，**不会被修正成 100**；
   - **不会报错**：模板只校验 `fullScore === 100` 且 `score ∈ [0,100]`，`99.84 ≤ 100` 合法 → **历史成绩单照常能打开**，只是分数差 0.16。
   - 各环境需在**改分脚本执行后**再开放 CSCA 考试（自查 SQL 见 [§4.8](#48-上线检查清单) 第 20 条）。
2. **`index` 用排序后的序号**，不用 `question.number` 原件。单卷内两者都是 1..48 / 1..80，但模板要求「1 开始连续」，一旦拼卷/跳号就校验不过。
3. 🔴 **三态判定先看 `answered` + 答案是否为空，最后才看 `is_correct`**。实测未答题是 `answer=''`、`answered=0`、`is_correct=2`（= 错）。只按 `is_correct` 判 → 中文 80 题空交会印成 **80 个红叉、0 未答**，和「未答 80」的统计自相矛盾。

   ```
   is_correct = 1                → correct
   answered = 1 且 answer 非空    → incorrect
   其余（answer 空 / answered=0） → unanswered
   ```

   与 [3.5.1](#351--改造-get-recordcscaexamrecordidresult) 的 `questionCards[].status` 同一口径，两个出口不许不一致。
4. 🔴 **时间显式带时区**。`end_time` 是毫秒时间戳，容器时区多为 UTC → 直接格式化得到的是 UTC 时刻，比越南/北京早 7–8 小时，**跨零点就日期差一天**，成绩单日期错了整张就是废单。用 `ZoneId.of("Asia/Ho_Chi_Minh")` 格式化并输出 `+07:00` 偏移，`timeZone` 填同值。
5. **解析（`explanation`）本期不下发**。`question.analysis` 全库已是 HTML 段落（`<p>…</p>` + KaTeX 文本节点），模板用 `esc()` 输出 → 会把 `<p>` 印成字面量。三条路：(a) 不下发，弹窗只有「你的作答 / 参考答案」；(b) 后端剥标签成纯文本（公式退化为 LaTeX 源码）；(c) 模板把那行改 `innerHTML` 再跑 KaTeX（要改模板）。**本版取 (a)**，看解析统一走 [3.5.2](#352--改造-get-recordpaperidquestionquestionid)。→ [4.3](#43-待确认事项) 第 23 条。
6. **姓名只认开考快照，不现查用户表**。`real_name` 在开考时写入 `exam_record`，成绩单直接取该列 —— 用户之后改名，**历史成绩单不该跟着变**（成绩单是正式凭证）。仅在历史记录该列为 `NULL` 时才回落 `UserClient`。
7. 🔴 **统计四项（正确/错误/未答/正确率）一律从 `exam_answer` 现算，禁止抄 `exam_record`**。实测 CSCA 记录（`status=1`）：

   | 字段 | 实测值 | 说明 |
   |---|---|---|
   | `total_questions` | 48 | 可用 |
   | `answered_count` | 0 | 可用（但本端点不需要下发） |
   | `correct_count` | 0 | 可用 |
   | `wrong_count` | **48** | 🔴 **未答被算成错**（`answered_count=0` 却 `wrong_count=48`），照抄 → 报告写「答错 48」，与题号网格的 48 个「—」自相矛盾 |
   | `accuracy_rate` | **0.00** | 🔴 恒 0，CSCA 侧从未正确写入，不可信 |

   → 必须在拼 `questions[]` 的**同一次循环**里累加三个计数器（复用规则 3 的三态判定结果，不许另写一套），再 `accuracyRate = correctCount / questionCount`（2 位 `HALF_UP`）。
   → `accuracyRate` 量纲是 **0–1**（`0.75` = 75%），**与 `exam_record.accuracy_rate` 列、`CscaExamResultDTO.accuracyRate` 一致**；而模板 `statistics().accuracy` 是 **0–100**（`75.0`）→ **两个数不是同一量纲，前端换算时 ×100，别直接塞进模板**。

**取数 SQL**

```sql
-- ① 记录 + 卷（1 行）
SELECT r.id, r.user_id, r.paper_id, r.exam_name, r.real_name,
       r.total_score, r.final_score, r.duration, r.start_time, r.end_time, r.status,
       r.total_questions, r.correct_count, r.wrong_count, r.answered_count, r.accuracy_rate,
       p.subject_type, p.subject_type_mapping, p.language_version
FROM exam_record r JOIN exam_paper p ON p.id = r.paper_id
WHERE r.id = #{examRecordId};

-- ② 逐题（48 / 80 行）—— 一次性拿到三态 + 统计 + 答案
SELECT a.question_id, a.answer, a.answered, a.is_correct,
       q.number, q.answer AS correct_answer
FROM exam_answer a JOIN question q ON q.id = a.question_id
WHERE a.exam_record_id = #{examRecordId} AND a.deleted = 0
ORDER BY q.number, a.question_id;
```

> ① 里的 `correct_count` / `wrong_count` / `answered_count` / `accuracy_rate` **只取来打日志做交叉校验**（三者与 ② 算出来的不一致时 `log.warn` 留痕，用于发现历史脏数据），🔴 **绝不下发给前端**（原因见规则 7）。② 的 `answered` / `is_correct` / `answer` 才是唯一可信源。
> 🔴 `r.total_score` 现在**完全不参与计算**（v3.5 取消归一化），SELECT 里留着只为 `log.warn` 一句「本次卷面 Σ 非 100，请确认改分是否生效」——**不要拿它去乘除任何一个分数**。

> `exam_answer` 开考时由 `initAnswerCard` **预建全量行**（实测 48/48 齐），未答题也有行，**不需要补空行**。
> 姓名正常**直接取记录上的 `real_name` 快照**，不打 auth-service；**仅历史记录该列为 `NULL` 时才回落** `UserClient.getUserById`，且不缓存结果（预览是低频操作，没必要为它建缓存）。

**业务逻辑**

1. `selectById(examRecordId)` → 无 → `8107`
2. **不校验 `userId`**（报告出口 by design，同 [3.5.1](#351--改造-get-recordcscaexamrecordidresult)）→ 但**必须已登录**
3. `status = 0`（未交卷）→ `8111`
4. `name` 为空 → 先回落 `UserClient`，仍空 → `8113`（无名成绩单没有意义）。🔒 **新记录走不到这一步**：开考前已硬拦、开考时已写快照
5. `questions.length == 0`（空卷）→ `8113`
6. 拼 `questions[]` 的**同一次循环**里累加 `correctCount` / `wrongCount` / `unansweredCount`（规则 7），循环后算 `accuracyRate`
7. 组装 → 断言 **`correctCount + wrongCount + unansweredCount == questionCount == questions.length`**、`score ∈ [0, 100]`、`accuracyRate ∈ [0, 1]` → 不符 `8113`（宁可报错，也不要前端白屏 / 报告自相矛盾）

**与诊断报告（3.5.1）的分工**

| | [3.5.1](#351--改造-get-recordcscaexamrecordidresult) 诊断报告 `result` | **3.6.2 成绩单 `preview`** |
|---|---|---|
| 用途 | App 内看题、看解析、看用时评价 | **官方版式**打印 / 分享 |
| 字段集 | 自定义 `CscaExamResultDTO`（含题目内容、选项、时间评价） | **模板契约原样**（含逐题三态网格） |
| 题目内容 | 有 `content` / `passage` / `options` | **无**（只给题号 + 三态 + 答案） |
| 姓名 | 不下发（`userId` 置 `null`） | 🔴 **必须有** `candidate.name` |
| 统计口径 | `correctCount` / `wrongCount` / `unansweredCount` / `accuracyRate`（**0–1 小数**） | **字段名与量纲完全一致**，同一次循环产出（不许各算各的）；模板另算一份 0–100 的 `accuracy` 只用于版面 |

**模板资源与版式**（后端**不出**静态资源，全在前端 build 里）

- 前端只需 `report.html` 的容器 + `report.css` + `report.js` + `assets/`（`header.png` 校名抬头、`watermark.png` 校徽水印、`app-qr.jpg` APP 码）。
- A4 竖版 595×842pt；每页最多 80 格；≤48 题每行 12 格、>48 题每行 16 格（实测中文 80 题 = **1 页 16 格/行**）。本期题量只有 48 / 80 → **恒单页**，续页逻辑用不上。
- 报告上**只印**：姓名、考试日期、科目（中/英）、考试语言、满分 100、成绩、正确/错误/未答/正确率、题号网格、页脚（电子成绩单二维码空位 + APP 码 + 签发单位）。
- 报告上**不印**：准考证号、成绩单号、性别、国籍、出生日期、照片、用时、成绩等级 —— 所以原方案里的 `examTicketNumber` / `scoreRecordNumber` / `gender` / `nationality` / `birthday` / `usedTimeText` / `avgTimePerQuestionText` / `scoreLevel` / `issuer` **全部删掉**（其中 `score_record_number`、`exam_ticket_number` 在 CSCA 记录上实测都是 NULL）。
- ⚠️ **`pdfUrl` 曾以 `reportUrl` 名义保留过一版，v3.7 又删掉了**：它确实不印在纸上（模板不读），但它的语义是「**下载地址**」，属于 `GET /scoreReport`；放进 `preview` 就变成第二个出口。前端判断按钮态只要 `reportReady`。
- 不返回 `template` 字段（那是版式预览专用，正式记录带了就是假数据）；**也不返回 `reportUrl` / `pdfUrl`**（🔒 v3.7 定，理由同上条）。前端「下载」一律调 `GET /record/{id}/scoreReport` 由它 `302` 过去 —— 前端**不需要知道文件存在哪**，桶改私有也无需前端改动。

**涉及表**：`exam_record` / `exam_paper` / `exam_answer` / `question`（读）+ `user`（读，经 `UserClient`，**仅历史记录姓名为空时**）

---

#### 3.6.3 🔧 改造 GET /record/{examRecordId}/scoreReport — CSCA 改读「已上传的 PDF」

**现状**（`ExamRecordController:177`）：`scoreReportPdfService.generateScoreReport(examRecordId)` → **HSK 专用版式**（`level + " 成绩报告"`、听/读/写分段表），CSCA 直接调会出空白/异常。

🔒 **v3.6 方案定案（用户 2026-10-22）**：**服务端不再生成任何 CSCA 成绩单 PDF**。PDF 由**前端用官方模板生成**，上传后把链接存回后端（[3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接)），本端点只负责**把存好的链接交出去**。

**改造点**

| # | 改造 | 级别 |
|---|---|---|
| 1 | 🔴 **按 `exam_type` 分流**：`exam_paper.exam_type = 2` → 走 CSCA 分支（下表）；否则走原 HSK 逻辑（`ScoreReportPdfServiceImpl` 那 684 行 PDFBox 手绘**一行不改**） | **P0** |
| 2 | CSCA 分支：`exam_record.report_url` **有值** → **`302` 重定向**到该地址（`response.sendRedirect`），**不套 `Result`** | **P0** |
| 3 | CSCA 分支：`report_url` **为空** → `8114`（成绩单尚未生成，前端应先走 [3.6.2](#362--get-recordexamrecordidscorereportpreview) → 生成 → [3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接)） | **P0** |
| 4 | `status = 0`（未交卷）→ `8111`，**在分流之前判**（HSK / CSCA 都适用） | P1 |
| 5 | 记录不存在 / `exam_type=2` 但卷查不到 → `8107` | P1 |
| 6 | **不做 `userId` 归属校验**（同 [3.5.1](#351--改造-get-recordcscaexamrecordidresult)：成绩单要能给老师 / 家长看） | — |
| 7 | ⛔ **删除**原「CSCA 版式 = PDFBox 重画」「服务端 headless Chromium 渲染」两条路（[4.3](#43-待确认事项) 第 24 条 v3.6 已改判） | — |

**为什么用 `302` 而不是后端代理下载**

| 方案 | 优点 | 缺点 | 取舍 |
|---|---|---|---|
| **`302` 重定向**（本版） | exam-service **零新依赖**（不用引 MinIO / 不用拉 400KB 流）；前端 / WebView / 微信浏览器天然支持；MinIO 自带 `Range` 与缓存 | URL 会短暂出现在地址栏；桶若私有则 302 失效 | ✅ **取这个** |
| 后端代理（`InputStream` → `response`） | 可自定义文件名、可加二次鉴权、桶可私有 | exam-service 要引 MinIO 客户端、要处理大对象流与超时，**为一个低频操作不值得** | 备选 |
| 返回 JSON `{url}` 让前端自己跳 | 后端最简单 | 前端多写一次跳转；`Content-Disposition` / 文件名失控 | 不要（本端点语义就是"给我 PDF"） |

> 🔴 **若将来桶改私有**：只需把第 2 条的跳转目标换成**预签名 URL**（`getPresignedObjectUrl` 有效期 5 分钟）——**仍然是 `302`，前端一行不改**。这也是选 302 的原因：升级路径最短。

**入参**：`examRecordId`（路径，不变）

**返回**：`302 Found` + `Location: <exam_record.report_url>`（🔴 **不套 `Result`、不返回 JSON**）

**错误返回**（这两种才套 `Result`）

```json
// report_url 为空
{ "code": 8114, "message": "成绩单尚未生成，请先导出", "data": null }

// 未交卷
{ "code": 8111, "message": "未交卷不能查看成绩单", "data": null }
```

**数据流向**

```
GET /record/{id}/scoreReport
  → ExamRecordController（URL 不变）
       ├─ status=0                        → 8111
       ├─ exam_type=1 → 原 HSK 渲染       → PDFBox 手绘（684 行零改动）→ 直接写 response
       └─ exam_type=2
            ├─ report_url 为空            → 8114
            └─ 302 Location: report_url   ← 前端上传时存进去的那个 MinIO 直链
```

**涉及表**：`exam_record`（读 `report_url` / `status`）/ `exam_paper`（读 `exam_type`）。🔴 CSCA 分支**只读这两列**，不再读 `question` / `exam_answer` —— 内容已在 PDF 里，服务端不需要重算。

---

#### 3.6.4 🆕 POST /record/{examRecordId}/scoreReport — 保存前端生成的成绩单链接

**用处**：CSCA 成绩单 PDF 由**前端用官方模板生成**（`CSCAReport.render()` → 「导出 PDF」），上传到对象存储后，把链接**回存到考试记录**上。这样「我的记录」列表、分享页、二次下载都不用再渲染一遍，也不需要服务端跑 Chromium。

**整条链路**（三段，前端主导）

```
① 取数据    GET  /record/{id}/scoreReport/preview      → data（模板契约 JSON）
② 渲染+上传  CSCAReport.render(el, data) → window.print()/jsPDF → PDF 文件
              POST /api/system/file/uploadFile          → reportUrl（MinIO 直链）
③ 回存链接   POST /record/{id}/scoreReport  {reportUrl} → 写入 exam_record.report_url
```

> 🔴 **②的上传通道**：`system-service` 现有 `POST /file/uploadImage` / `uploadVoice` **只收 image / audio**（`ImageMimeUtil` / `AudioMimeUtil` 白名单），PDF 传不上去。二选一：
>
> | 方案 | 做法 | 评价 |
> |---|---|---|
> | **(a) 新增 `POST /api/system/file/uploadFile`**（推荐） | 通用上传：`folder="pdf"`、MIME 白名单 `application/pdf`、**≤ 10 MB**、路径 `pdf/{userId}/csca_report/csca-report-{examRecordId}-{uuid}.pdf`；返回直链 | 与现有 `image/` `audio/` 同一套 `MinIOUtils`，**改 30 行**；顺带能修下面那个 bug |
> | (b) 前端直传（预签名 PUT） | 后端出预签名，前端 PUT 完回调 | 要多写两个端点（prepare / confirm），本期不值 |
>
> 🔴🔴 **`FileController` 有个必须先修的 bug**：`system-service/.../controller/FileController.java:97` 写的是 `Long userId = 3232344L;`（**硬编码**，不是当前用户）。后果：所有上传都落到 `pdf/3232344/` 下，**所有人的成绩单混在一个目录里**，且 URL 里看不出归属。→ CSCA 上线前必须改成从 JWT 取真实 `userId`（这也是 MinIO 里为什么有一堆 `pdf/3232344/...` 的原因，见 [4.9](#49-联调实测记录2026-10-22真调-test-后端) 备注）。
>
> 📌 路径命名建议对齐 MinIO 里**已存在**的存量目录（`pdf/{uid}/hsk_report/hsk-report-{recordId}-{uuid}.pdf`）：CSCA 用 `pdf/{uid}/csca_report/csca-report-{recordId}-{uuid}.pdf`。

**落地位置**：`ExamRecordController#saveCscaScoreReport` → `ExamRecordServiceImpl#saveCscaScoreReport`（**现有文件加方法**，不新建 Service）

**入参**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `reportUrl` | String | **是** | PDF 直链，长度 **≤ 1000**（`exam_record.report_url` 是 `varchar(1000)`，超长会被 MySQL 截断或报错） |
| `overwrite` | Boolean | 否 | 默认 `false`。`true` 时允许覆盖已有链接（前端「重新生成」） |

```json
{ "reportUrl": "http://www.hkbvvtb.com:9000/hsk/pdf/2112787850284290049/csca_report/csca-report-2113168625743364098-9c6ce2c4.pdf",
  "overwrite": false }
```

**返回 JSON**

```json
{ "code": 200, "message": "保存成功",
  "data": { "examRecordId": "2113168625743364098",
            "reportReady": true, "saved": true, "overwritten": false } }
```

> `saved=false` + `overwritten=false` = **本来就是这条链接**（幂等重复提交），仍回 `200`。

**校验链（🔴 顺序不能乱，先便宜后昂贵）**

| # | 校验 | 不通过 |
|---|---|---|
| 1 | `reportUrl` 非空、`trim` 后长度 ≤ **1000**、`http://` 或 `https://` 前缀 | `400` 参数错误 |
| 2 | 🔴 **host 必须命中白名单**（配置项 `csca.report.allowed-hosts`，值 = MinIO 公网域名，如 `www.hkbvvtb.com`）—— 防「存一个钓鱼域名让家长点开」、防 SSRF | `8116` |
| 3 | 🔴 **`reportUrl` 必须包含本记录的 `examRecordId`**（路径或文件名任一处）—— 防「把 A 的成绩单挂到 B 的记录上」 | `8116` |
| 4 | 🔴 **记录必须属于当前登录用户**（`exam_record.user_id == 当前 userId`） | `403` |
| 5 | 记录存在、`deleted=0` | `8107` |
| 6 | `status = 1`（必须已交卷） | `8111` |
| 7 | 卷 `exam_type = 2`（HSK 不许走这个口） | `8107` |
| 8 | 已有 `report_url` 且 `≠ 本次值` 且 `overwrite=false` | `8115` |
| 9 | （P1 建议）对 `reportUrl` 发一次 `HEAD`：`Content-Type` 含 `application/pdf`、`Content-Length` ≥ 10 KB | `8116` |

> 🔴 **第 4 条与读出口相反，别抄错**：**读**成绩单**不校验归属**（[3.5.1](#351--改造-get-recordcscaexamrecordidresult) / 3.6.2 / 3.6.3，报告要给老师家长看）；**写**成绩单**必须校验归属**（只有本人能给自己的记录挂文件）。这两条同时成立，不矛盾。
>
> ⚠️ **第 9 条是可选加固**：因为 host 已在白名单内（只打自己的 MinIO），SSRF 面很小。不做也不影响主流程，但做了能挡「链接拼错 404」——否则用户点了下载才发现是坏链。

**写库（一条 SQL，天然幂等 + 防并发）**

```sql
UPDATE exam_record
SET report_url     = #{reportUrl},
    report_unlocked = 1,
    updated_time    = #{now}
WHERE id = #{examRecordId}
  AND deleted = 0
  AND (report_url IS NULL OR report_url = '' OR #{reportUrl} = report_url OR #{overwrite} = 1);
```

> - 影响行数 **1** → 成功（`overwritten` = 原来非空）
> - 影响行数 **0** → 说明「已有链接且不允许覆盖」→ **回 `8115`**（`UPDATE` 的 `WHERE` 自带并发保护，不需要先 SELECT 后 UPDATE）
> - 🔴 **不要用 `UPDATE … WHERE report_url = 旧值` 做乐观锁**：`report_url` 可能为 `NULL`，`= NULL` 恒不成立（同 [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 踩过的坑）。

**`report_unlocked` 怎么处理**

`exam_record.report_unlocked`（现有列，注释「成绩单导出解锁：0=未解锁，1=已解锁」）—— CSCA 本期**无付费解锁概念**（需求 2.5.3：免费 / 付费会话都支持直接导出），所以：

- **读取时不校验它**（[3.6.2](#362--get-recordexamrecordidscorereportpreview) / 3.6.3 都不看）
- **写入时置 `1`**：语义从"已付费解锁"放宽为「**该记录已有成绩单文件**」，供记录列表判断要不要显示「下载」按钮
- ⚠️ 本仓**零代码引用**这两列（全仓 grep 0 命中），所以置 1 不影响 HSK 任何逻辑；但若**别的服务**（如那个写 `pdf/3232344/` 的上传服务）也读它，需知会一声

**错误码**

| 码 | 含义 | 前端动作 |
|---|---|---|
| `8114` | 成绩单尚未生成 | 先走 3.6.2 → 生成 → 上传 → 再调本接口 |
| `8115` | 成绩单已存在，不允许覆盖 | 提示「成绩单已生成」；确实要重生成 → 带 `overwrite:true` |
| `8116` | 成绩单链接非法（host 不在白名单 / 不含 recordId / 超长 / 非 http(s)） | **前端 bug**，查上传返回值是否被改写 |
| `8107` / `8111` / `403` | 记录不存在或非 CSCA / 未交卷 / 非本人 | 按语义提示 |

**风险（后端无法消除，必须写下来）**

| 风险 | 说明 | 缓解 |
|---|---|---|
| 🔴 **PDF 内容不可校验** | PDF 是前端渲染上传的，后端**只看链接、不开文件**。理论上用户可以上传一张改过分的 PDF | ① 只有本人能写；② URL 必须含 recordId；③ 成绩单页脚二维码**指向 `preview` 接口**（模板自带二维码位）→ 扫码能核到官方数据，这是唯一能证伪的通道；④ 需要强校验时改为服务端渲染（本期不做） |
| 🔴 **直链是公开可读的** | 当前 MinIO 桶 `hsk` 匿名可读（实测 `curl` 直出 200 + `application/pdf`），拿到链接的人都能下载 | 与「报告要给老师家长看」的产品意图一致；但**链接一旦外泄等于成绩单外泄**。治理路径：桶改私有 + `302` 目标换预签名（3.6.3 已预留），**前端无感** |
| **重复提交** | 前端重试 / 双击 | `WHERE` 条件更新 + 同值幂等（`saved=false`） |
| **链接失效** | 对象被清理 / bucket 迁移 | `302` 后前端拿到 404 无法感知；建议前端在「下载」失败时回退到「重新生成」流程（3.6.2 重新拉数据） |

**涉及表**：`exam_record`（**读写** `report_url` / `report_unlocked` / `updated_time`）+ `exam_paper`（读 `exam_type`）／ **`user` 不查**（姓名快照早在开考时写好）

---

### 3.7 错题本（考试侧只写，不读）

**一句话**：错题本是**练习 + 考试共用的长期资产**。考试侧**只在交卷判分时写入**；读取 / 移出 / 复习三个动作全在 `practice-service`（`/api/practice/csca/wrong-book*`）。**本模块零新增端点**。

#### 3.7.1 三者定位：标记 / 收藏 / 错题本

| 能力 | 谁触发 | 落库 | 生命周期 | 考试中可见 | 跨考试 |
|---|---|---|---|---|---|
| **标记** | 用户点「标记」 | `exam_answer.is_tag` | 本场 | ✅ 答题卡黄格 | ❌ |
| **收藏** | 用户点 ★ | `csca_question_favorite` | 长期 | ✅ 答题卡 ★ 角标 | ✅ |
| **错题本** | **系统自动**（判错才写） | `csca_question_wrong` | 长期 | ❌ **看不到** | ✅ |

> 这张表解释了**为什么答题页没有"错题本"按钮**：它不是一个用户动作，是**判分的附产物** —— 与收藏（用户主动 ★）本质不同。需求 2.6 说的"错题同步"，指的就是这件事。

#### 3.7.2 唯一写入点

**只有一处**：`POST /record/{paperId}/submit/csca` 的判分之后（[3.4.1](#341--改造-post-recordpaperidsubmitcsca) 第 6 步）。

- **答题过程中不写** —— 需求 2.2 明确"不实时判分"，此刻根本没有对错
- **超时自动交卷也写** —— Job / 惰性兜底走的是同一段判分逻辑，天然覆盖
- **重复交卷不重复写** —— 幂等短路（`status != 0` 直接返回）发生在判分之前

#### 3.7.3 字段取值（🔴 每一列都有坑）

| 列 | 取值 | 为什么不能取别的 |
|---|---|---|
| `user_id` | 交卷请求的 token 用户 | — |
| `question_id` | `exam_answer.question_id` | — |
| **`section`** | **`exam_paper.subject_type_mapping`** | 实测 31 张 CSCA 卷该列全有值（`math` / `arts_chinese` …）。🔴 **不能取 `question.subject_type_mapping`**：PROD 该列 1904 行**全 NULL** → 写进去也是 NULL → **错题本按科目筛选全失效** |
| **`language_version`** | **`exam_paper.language_version`** | 题目表没有可靠的语言来源；卷上有（实测全 `chinese`） |
| **`user_answer`** | `exam_answer.answer` **原文** | **不做归一化** —— 复习页要还原用户当时写的 `DA`，而不是 `A,D` |
| `source` | 常量 `'exam'` | 与练习的 `'prac'` 区分 |
| **`record_id`** | **`exam_record.id`** | 与 `practice_record.id` **共用一列、两个命名空间** → 前端必须按 `source` 判断跳转 |
| `deleted` | `0`（软删复活） | 唯一键 `uk_user_question(user_id, question_id)` **不含 `deleted`** |
| `created_time` | 首次收录（毫秒） | 只写一次 |
| `updated_time` | 每次覆盖（毫秒） | 列表按它倒序 |

#### 3.7.4 SQL（与练习侧同一张表、同一套软删复活）

```sql
-- 同一唯一键 uk_user_question(user_id, question_id)，不含 deleted → 移出后再次判错可复活
INSERT INTO csca_question_wrong
    (user_id, question_id, section, language_version, user_answer,
     source, record_id, deleted, created_by, update_by, created_time, updated_time)
VALUES (#{userId}, #{questionId}, #{section}, #{languageVersion}, #{userAnswer},
        'exam', #{examRecordId}, 0, #{userId}, #{userId}, #{now}, #{now})
ON DUPLICATE KEY UPDATE
    user_answer  = VALUES(user_answer),
    deleted      = 0,
    updated_time = VALUES(updated_time);
```

🔴 **`ON DUPLICATE KEY UPDATE` 只收敛 `user_answer` / `deleted` / `updated_time`** —— 不覆盖 `source` / `record_id` / `section` / `language_version`（理由见下面第 1 条硬规则，与收藏同一套）。

#### 3.7.5 三条硬规则

| # | 规则 | 不这么做会怎样 |
|---|---|---|
| **1** | **只收敛 `user_answer` / `deleted` / `updated_time`**，不覆盖 `source` / `record_id` / `section` | 同一题先**练习**错（`source='prac'`）再**考试**错 → 来源标签被改写成 `exam`，历史被抹。练习侧口径是"首次落值不覆盖"，考试侧必须一致 |
| **2** | **只进不出**：判**对**不动（**不自动移出**），移出只能手动 `DELETE` | 考一次试把用户正在复习的错题**批量清空**。这是练习侧 2026-10-19 回归原型后定的口径（`CscaWrongBookService#syncAfterGrade`：判错收录 / 判对与未评分不动） |
| **3** | **未答题不写**：`answered=0` 的即使 `is_correct=2` 也不写 | 48 题的卷只做了 20 题 → **28 条空答案**灌进错题本，用户打开全是空白题 |

#### 3.7.6 取数过滤（🔴 最容易写错的一行）

```java
List<CscaWrongBookSyncItem> items = answers.stream()
    .filter(a -> Integer.valueOf(1).equals(a.getAnswered()))    // 🔴 未答不写
    .filter(a -> Integer.valueOf(2).equals(a.getIsCorrect()))   // 只收录判错
    .map(a -> new CscaWrongBookSyncItem(
            a.getQuestionId(),
            a.getAnswer(),
            paper.getSubjectTypeMapping(),   // ← 卷上的科目码，不是题上的
            paper.getLanguageVersion()))
    .toList();

if (!items.isEmpty()) {
    wrongBookWriter.sync(userId, items, examRecord.getId());
}
```

> 🔴 **不能只用 `is_correct=2` 一个条件筛**：交卷三态里**未答题也是 `is_correct=2`**（[4.1](#41-枚举速查) 的作答状态表），必须叠加 `answered=1`。这两个 `filter` 少写一个不报错，只会静默把未答题塞进错题本。

#### 3.7.7 🔴 事务边界（P0，上线阻塞）

`csca_question_wrong` **PROD 未建表**（[4.8](#48-上线检查清单) 第 12 条）。若与交卷同事务：

```
交卷 → 判分 OK → 写错题本 → Table doesn't exist → 整笔回滚
→ 用户做完 48 题，交不上去，分数也没了
```

**必须隔离**，二选一：

| 方案 | 做法 | 评价 |
|---|---|---|
| **A（推荐）** | 错题同步方法挂 `@Transactional(propagation = Propagation.REQUIRES_NEW)`，外层 `try-catch` 只 `log.error` + 告警，**交卷照常返回** | 表没建时只是错题本空，考试功能不残 |
| **B** | 交卷事务**提交后**再同步调用（同进程即可，不必上 MQ） | 少一层代理，但调用位置要放在 `TransactionSynchronization#afterCommit` |

> 交卷返回体**不含任何错题字段** —— 错题本是后台沉淀，不是交卷结果。别在前端等它。
>
> ⚠️ `REQUIRES_NEW` **只在跨 Bean 代理调用时生效** —— 所以 `CscaWrongBookWriter` 必须是独立 Bean，**不能写成 `ExamRecordServiceImpl` 的私有方法**（自调用不走代理，会沿用外层事务，等于没隔离）。

#### 3.7.8 读取侧（不在本模块，但前端必须这么接）

| 动作 | 端点 | 归属 | 关键参数 |
|---|---|---|---|
| **我的错题本** | `GET /api/practice/csca/wrong-book` | practice-service | 🔴 **`source=exam`**（不传则练习 + 考试混排）/ `section` / `languageVersion` / `startTime` / `endTime` / `order` / 分页 |
| **移出错题本** | `DELETE /api/practice/csca/wrong-book/{questionId}` | practice-service | — |
| **错题复习作答** | `POST /api/practice/csca/wrong-book/{questionId}/answer` | practice-service | 只判分 + 同步错题本，**不落作答表** |

- 列表**带 `standardAnswer` / `standardAnswerLabels` / `userAnswer`**，**不带 `analysis`**（解析仍走 `/solution`）
- 排序**恒由后端**（`updated_time` + `id` 兜底同向），`order` 只切方向不切列
- **无作答态**（错题本状态自持，不读作答表）

> ⚠️ 这三个端点属 **CSCA 练习模块**（`practice-service` 的 `CscaWrongBookController`），与收藏夹同一批交付。**考试侧不重复造读接口** —— 错题本只有一份，跨入口必须同源。

#### 3.7.9 依赖与风险

| # | 风险 | 后果 | 处置 |
|---|---|---|---|
| 1 | `csca_question_wrong` **PROD 未建** | 交卷 500 / 回滚 | 建表 + **事务隔离**（[3.7.7](#377--事务边界p0上线阻塞)） |
| 2 | 错题本读接口属**练习模块** | 练习模块不上线 → 考试错题写进去了但**用户看不到**（收藏不同：收藏在考试内有 ★ 态兜底） | 排期对齐，考试侧不自己造 |
| 3 | `section` 取自 `question.subject_type_mapping` | PROD 全 NULL → 错题本科目筛选失效、科目标签空白 | 只取 `exam_paper.subject_type_mapping` |
| 4 | 与收藏共用 `record_id` 列 | 前端不按 `source` 区分 → 从错题本点回考试/练习跳错 | 前端按 `source` 分流（`exam` → 诊断报告，`prac` → 练习记录） |

**涉及表**：`csca_question_wrong`（**UPSERT × N**）/ `exam_answer`（读）/ `exam_paper`（读）

---

## 4. 附录

### 4.1 枚举速查

**科目（`CscaExamSubjects`，5 个原始值）**

| code | 中文名 | 支持语言 | 卷数 | 单卷题量 | 时长 | 满分 | 当前可用 |
|---|---|---|---|---|---|---|---|
| `arts_chinese` | 文科中文 | `chinese` | 8 | 80 | 90 min | 100.00 | ✅ |
| `science_chinese` | 理科中文 | `chinese` | 5 | 80 | — | — | ❌ **结构模板缺失** |
| `math` | 数学 | `chinese` / `english` | 9 | 48 | 60 min | 100.00 | ✅（仅中文） |
| `physics` | 物理 | `chinese` / `english` | 5 | 48 | 60 min | 100.00 | ✅（仅中文） |
| `chemistry` | 化学 | `chinese` / `english` | 4 | 48 | 60 min | 100.00 | ✅（仅中文） |

> ✅ `common/enums/CSCASubjectType` **已含 5 个值**（`CHEMISTRY` / `PHYSICS` / `MATH` / `ARTS_CHINESE` / **`SCIENCE_CHINESE`**），**不用再补枚举**。
> ⚠️ 缺的只在**数据层**：`exam_paper_structure` 只有 4 行（无 `science_chinese`）→ 理科中文仍不可考，见 [4.3](#43-待确认事项) 第 2 条。

**语言（`CSCALanguageVersion`）**：`chinese` / `english`。实测**只有 chinese 有卷**。

**题型映射（对外只两个值）**

| 库中 `type_id` | 题数 | 对外 `typeId` |
|---|---|---|
| `多选` | 35 | **`MULTI`** |
| `单选` / `识解汉字` / `选词填空` / `辨析词语` / `补全语句` / `选词成段` / `阅读理解` / 空 | 1869 | **`SINGLE`** |

**考试记录状态（`exam_record.status`）**

| 值 | 含义 | CSCA 会不会出现 |
|---|---|---|
| `0` | 进行中 | ✅ |
| `1` | 已结束（= 已交卷 + 已判分） | ✅ |
| `2` | 已提交（HSK 异步批阅完成后） | ❌ **CSCA 永不出现** |

**作答状态（报告 / 答题卡的三态）**

| 值 | 判定 | 说明 |
|---|---|---|
| `correct` | `answered=1 AND is_correct=1` | 答对 |
| `wrong` | `answered=1 AND is_correct=2` | 答错 |
| `unanswered` | `answered=0` | 未答（**仍写 `is_correct=2` 但不得分**） |

**扣减类型（`exam_record.deduct_type`）**

| 值 | 含义 | `deduct_amount` | 本期是否出现 |
|---|---|---|---|
| `0` | 未扣（续考复用旧会话 / 历史存量记录） | `0.00` | ✅ |
| `1` | **免费次数**（`user_exam_quota` 扣 1 次） | `0.00`（次数不折钱） | ✅ **唯一实际取值** |
| `2` | 点数（会员赠送 / 点数包） | `2.00` | ❌ 预留，点数体系未实现 |

> 📌 只记**扣减来源**，不记金额到分。真要对账，看 `user_exam_quota.used_quota` 的累计增量。

**收藏 / 错题来源（`source`）**

| 值 | 谁写 | `record_id` 指向 |
|---|---|---|
| `prac` | `practice-service`（CSCA 练习） | `practice_record.id` |
| `exam` | `exam-service`（本模块） | `exam_record.id` |

**核心表**

| 表 | 角色 | 本模块操作 |
|---|---|---|
| `exam_paper` | CSCA 卷（`exam_type=2`、`version='CSCA'`） | 读 |
| `exam_paper_structure` | 每科时长/满分模板（**4 行**） | 读 |
| `question` / `question_group` | 题目 / 共用材料 | 读 |
| `exam_record` | 考试会话 | **写**（建/交卷/超时） |
| `exam_answer` | 逐题作答（建会话时整卷初始化） | **写** |
| `user_taken_paper` | 已考卷（抽卷去重） | **写/删** |
| **`user_exam_quota`** | 考试次数（`exam_type='CSCA'`、`version='CSCA'`、`level=<科目码>`，**一人 5 行**）| **已是通用表**（HSK / HSKK / Proficiency 在用）→ 本模块 **SELECT 1 行 + UPDATE**，走 `decrementQuota(id)`（🔒 B 方案，**禁止 `decrementQuotaByUser`**） |
| `exam_number` | 准考证号 / 成绩单号自增 | **写** |
| `csca_question_favorite` | 收藏（与练习共用） | 🆕 **写（`source='exam'`）** |
| `csca_question_wrong` | 错题本（与练习共用） | 🆕 **写（`source='exam'`）** |

### 4.2 答案归一化与判分

**问题**：库中多选答案形如 **`A,D`**（逗号分隔、升序，35 题），用户提交可能被前端序列化成 `DA` / `A, D` / `a,d` / `A、D`。现有 `submitCscaExam` 用 `equalsIgnoreCase` 会把**做对的题判错**。

**归一化规则**（`CscaAnswerNormalizer#equalsSet`，与练习侧同一套）：

```
① trim → 全角转半角（，、；／ → , ; /）
② 去空白
③ 大写
④ 按 [,;/\s] 切分 → 去空串 → 去重
⑤ 排序后拼回（用 ',' 连接）
⑥ 与标准答案做同规则归一化后比较字符串相等
```

| 用户答案 | 标准答案 | 归一化后 | 判 |
|---|---|---|---|
| `DA` | `A,D` | `A,D` vs `A,D` | ✅ 对 |
| `a, d` | `A,D` | `A,D` vs `A,D` | ✅ 对 |
| `A、D` | `A,D` | `A,D` vs `A,D` | ✅ 对 |
| `A,D,B` | `A,D` | `A,B,D` vs `A,D` | ❌ 错（**多选必须完全一致，不给部分分**） |
| `A` | `A,D` | `A` vs `A,D` | ❌ 错 |
| `""` | `A,D` | —（未答，不比较） | — `unanswered` |

**判分口径（务必与练习侧一致）**

- **单选题**：归一化后字符串相等即对；
- **多选题**：**集合完全相等**才对（多选一个/少选一个都算错，**不给部分分**）；
- **未答**：`is_correct=2`、`points=0`，但报告归 `unanswered`；
- **单题得分**：`question.score`（文/理中文 1.25；数理化 **2.00 / 2.50 混合**），答对才加；
- **卷面总分**：`exam_paper_structure.full_score`（100.00）。✅ **v3.4 起 `SUM(question.score)` 也恒等于 100.00**（题库已改分：数理化 40×2.00 + 8×2.50）→ 两者一致；仍建议取 `full_score`，避免将来再调分值又漂；
- **正确率**：`correctCount / totalQuestions`，**0–1 小数、保留 2 位**（`HALF_UP`，`0.63` = 62.5%），与 `exam_record.accuracy_rate` 列同尺度（🔴 **不是 0–100**；v3.4 修正，原写 ×100 与代码 `AsyncGradingServiceImpl:195` 的 `divide(total,2)` 不符）。

### 4.3 待确认事项

| # | 事项 | 现状 | 建议 / 影响 |
|---|---|---|---|
| **1** | **「免费次数用完可用点数参加」本期不做** | 全库无点数/订单表/账本；`user_exam_quota` 只有 HSK / HSKK / Proficiency 三种 `exam_type`；`feature-20260917-订单支付功能` 分支未合入。**但「考试次数限制」本身 HSK 已经跑通了**，CSCA 直接复用 | 本期口径 = **只认 `user_exam_quota` 的免费次数**，用完即 `8105`。点数体系作为**后续迭代**（`deduct_type=2` 已预留位）。**须产品确认**：上线版本是否接受"次数用完不能考" |
| **2** | **`science_chinese` 数据结构缺失** | ✅ `common/CSCASubjectType` **已有 5 值**（含 `SCIENCE_CHINESE`，不用补枚举）；❌ `exam_paper_structure` 无该科目（5 卷 400 题在库）；练习侧 `CscaSubjects` 待核 | 只补数据：① `exam_paper_structure` 插 1 行（80 题 / 90 分钟 / 100 分）；② 练习侧 `CscaSubjects` 同步。**不补则理科中文永远"暂无可用试卷"**。~~原「补 `CSCASubjectType` 枚举」一项已由代码完成~~ |
| **3** | **CSCA 次数怎么发（最大缺口）** | `user_exam_quota` **CSCA 0 行**；且**全仓没有任何"发放"代码** —— auth-service 只在**注销重注册**时按 `user_cancel_history.quota_snapshot` 写回，注册/邀请**都不写 `user_exam_quota`**（HSK 的行是后台/人工维护的，实测 `sum(total)=33` 但 `sum(remain)=1684`，明显被手工改过） | 三选一，**须拍板**：<br>① **沿用现状**：运营后台/SQL 手工发（最省事，但要运维配合，且新用户注册后立刻考试会 `8105`）；<br>② **auth-service 注册时按 5 科目各插一行**（`CSCA/CSCA/<科目>/1/0/1`）+ 邀请奖励 `+2` 加到哪科待定（`UserInvitationBinding.rewardQuota` 已有字段可扩，见第 18 条）；<br>③ **exam-service 首次考试时"按需发"**（`getQuota` 查不到就插默认 1 次）——最省改，但违背"次数该由运营掌控"的语义，**不推荐** |
| **4** | **次数是「全局一份」还是「每科一份」** | 🔒 **已定：B 方案（每科一份）** | `level` = 科目码，**一人 5 行、每科 3 次**。实现见 [3.2.1](#321--改造-post-answerstartcsca)：加 2 个带 `level` 的薄重载 + `decrementQuota(id)`。<br>🔴 **禁用 `decrementQuotaByUser`**（`WHERE` 无 level → 5 行一起扣）；🔴 **禁用 3 参 `getQuota` / `hasAvailableQuota`**（`selectByUserIdAndExamTypeAndVersion` 无 level + `LIMIT 1` → 随机命中一科） |
| **5** | **未答题是否进错题本** | 需求未写；本文取"**不进**"（`user_answer` 为空、没有复习价值）—— 口径已落到 [3.7.5](#375-三条硬规则) 第 3 条：过滤条件是 `answered=1 AND is_correct=2`，🔴 **未答题的 `is_correct` 也是 2**，少写 `answered` 条件就会把整张卷的空题灌进错题本 | 若产品要"未答也算错题"，改 1 行。**须拍板** |
| **6** | **考试是否要题面快照** | 练习侧冻结题面；考试侧本文**不冻结**（`exam_answer` 无快照列） | 若要求"报告必须还原考试当时题目"，需在 `exam_answer` 加 snapshot 列。**建议 v1 不冻结**，报告页注明"以当前题库为准" |
| **7** | **超时是否退次数** | 需求未写 | 本文取"**不退**"（考试已消费）。**须拍板** |
| **8** | **超时但用户没打开的会话** | 42 条历史脏数据（`status=0`、`deadline_time` 为空） | 上线时**先清理**，再开 Job；否则 Job 会扫出大量"0 分报告" |
| **9** | **答题卡颜色优先级** | 需求 4.3 列了四色但没给优先级 | 本文取 **当前 > 已答 > 标记**（三个布尔 + 未答算四色）；**收藏不参与配色**，只用 ★ 角标表示 |
| **10** | **`autoSubmitted` 怎么判** | `exam_record` 无"是否自动交卷"列 | 本文用 `end_time - deadline_time ∈ [-5s, +5s]` 推断；**建议加 `submit_source` 列**（推断法在边界不可靠） |
| **11** | ~~**成绩单要不要"合格/不合格"**~~ ✅ **本项作废**（2026-10-22） | 官方成绩单模板 `data.schema.json` **没有任何分级 / 合格字段**，报告上只印成绩（0–100） | 不再需要产品给线：成绩单只显示分数。原 `CscaScoreReportDTO.scoreLevel` 已删（见 [3.6.2](#362--get-recordexamrecordidscorereportpreview)） |
| **12** | **准考证号 / 成绩单号印在成绩单上吗** | ✅ **已定：不印**。官方模板只有姓名 / 考试日期 / 科目 / 语言 / 满分 / 成绩 / 三态网格，**没有这两个号的栏位**；且 CSCA 记录 `score_record_number`、`exam_ticket_number` 实测**全 NULL** | `ExamNumberService` 的 `leve='CSCA'` 用法**取消**（不再生成 CSCA 成绩单号）；`GET /number/examTicket` 仍可复用（[2.1](#21-端点总表17-在用--2-不用--4-新增) 第 19 行），只是与成绩单无关 |
| **13** | **英文卷何时导入** | 库中 0 张英文卷 | **后端接口全部不用改**：导入后 `GET /paper/list/csca?languageVersion=english` 自然能取到卷。唯一要动的是**前端**——把 English 开关从「置灰」放开（需求 2.1 下中文两科仍恒只中文） |
| **14** | **收藏/错题"跨考试与练习共享"的一致性** | 两服务**同库同表**（`csca_question_favorite` / `csca_question_wrong`）；exam-service 目前对这两张表**零引用**，且**没有 PracticeClient** | 本文取"exam-service **直写**同库两张表"（收藏见 [3.3.4](#334--新增-post-answercscafavorite--考试内收藏)，错题见 [3.4.1](#341--改造-post-recordpaperidsubmitcsca)）：① 同库，零 RPC；② 与错题本保持同一策略，不会出现"一个直写一个 Feign"的双口径。**备选**：由 practice-service 出内部接口 + 新建 `PracticeClient` 统一写（更干净，但要多一次跨服务调用、且要跨分支协调接口形状）。**须拍板** |
| **15** | ~~**`POST /answer/paper/tag` 的兼容策略**~~ ✅ **本项作废**（2026-10-22） | 原先想把它改造成收藏，才需要考虑"翻转兼容" | **改为不动它**：`paper/tag` 保留**标记**语义（`is_tag`），收藏走新增的 `POST /answer/csca/favorite`（[3.3.4](#334--新增-post-answercscafavorite--考试内收藏)）。没有兼容问题，也没有"翻转兜底"这种模糊语义 |
| **16** | **是否给 exam-service 开全局 Long→String** | `common/config/JacksonConfig` 被注释；`practice-service` 自己那份是开的 | 本文取"**新增端点用 String、改造端点保持数字**"。若前端愿统一迁移，可加 `exam-service` 自己的 `JacksonConfig`（**会波及 HSK 全部接口**）。**须拍板** |
| **18** | 🔴 **B 方案下「3 次」的口径要重新确认** | 需求 2.5.1 写的是「初始 1 + 邀请 2 = 上限 3」，原文是按**整场考试**写的；B 方案下变成 **5 科 × 3 次 = 上限 15 次/人**，跟需求字面数量不符 | 本文按「**每科各 3 次**」落（已确认）。仍需定 **邀请奖励 `+2` 加到哪一科**：<br>① 用户自选科目（要加选择交互）；② 固定加到「文科中文」（默认第一科，最简单）；③ **5 科各 +2**（= 送 10 次，成本最高）<br>—— 这条只影响**发次数链路**，不影响考试侧代码 |
| **17** | **报告分享的边界** | 已确认「报告要给非答题者看」→ 三个报告出口**不校验归属**（[3.5.1](#351--改造-get-recordcscaexamrecordidresult)） | 本版取「**只要求登录 + id 即凭证**」。**须拍板三件事**：① 是否要**免登录**分享（要则加 `shareToken` + 有效期，不能用裸 `recordId`）；② 成绩单是否**脱敏**（姓名/证件打码）；③ 是否加**查看水印**（防截图外传） |
| **19** | 🔴 **`csca_subject` 字典：SQL 文件与 TEST 库已不一致** | 文件 `system-service/src/main/resources/sql/csca_subject.sql` 写的是 `arts=1 / math=2 / physics=3 / chemistry=4 / science=5`、`is_default=1` 在 **math**（10002）；**TEST 库实测**是 `arts=1 / science=2 / math=3 / physics=4 / chemistry=5`、`is_default=1` 在 **arts**（10001） | 需求 1.3 要求顺序 **文→理→数→物→化**、默认第一科 = 文科中文 → **TEST 库是对的，SQL 文件是旧的**。PROD 若照文件执行，管理端下拉顺序错、**考生端首页默认科目也会落到数学**。**上线前先修文件再执行**（或确认 PROD 已是正确数据）。⚠️ 字典现在就是**首页科目卡的唯一数据源**（[3.1.1](#311--get-recordcscaquota--5-科剩余次数)），这一条从「管理端体验」升级为**考生端可见缺陷** |
| **20** | ~~**是否保留 `GET /paper/csca/catalog`**~~ | ✅ **已撤销**（2026-10-21）：科目清单改用**现有字典** `GET /api/system/dict/code/csca_subject`（`sortOrder` 1–5 + `isDefault` 恰好覆盖需求 1.3）；可考性靠**补 `exam_paper_structure` 数据**解决；续考由 `startCscaExam` 自动返回；资料在 [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 校验 | 次数改为**单一小端点** `GET /record/csca/quota`（[3.1.1](#311--get-recordcscaquota--5-科剩余次数)）。**端点数仍为 2 个**（quota 顶替 catalog），但新增类从 3 个降为 1 个、读取表从 5 张降为 1 张。原先担心的「前端首屏 7–12 次请求」不再成立：前端只需**字典 1 次 + 次数 1 次**，共 2 次 |
| **21** | 🔴 **错题本「写在本服务、读在练习服务」的交付依赖** | `csca_question_wrong` **TEST 已建 / PROD 未建**；读/移出/复习三端点（`/api/practice/csca/wrong-book*`）属 **CSCA 练习模块**，与考试侧**不同分支** | 风险：练习模块不同批上线 → 考试错题**写进去了但用户看不到**（收藏不至此：收藏本身有考试内 ★ 态兜底，错题本没有）。**须排期对齐**。<br>⚠️ 另需核对：练习侧 `syncAfterGrade` 传的 `section` 若取自 `question.subject_type_mapping`，**PROD 该列全 NULL** → 练习来的错题科目为空（考试侧取 `exam_paper` 不受影响）。错题本列表按科目筛选时会出现"有记录但筛不出" |
| **22** | ✅ **文科中文 / 理科中文的成绩单都印「中文」**（已定） | 模板 `exam.subject` 只有 4 个合法值（中文 / 数学 / 物理 / 化学），`names` 里「中文」= `Professional Chinese`；而 CSCA 有 **5 科** | **已定：两科都映射 `中文`**（传 5 值原件前端必抛 `科目必须是中文、数学、物理或化学。`，已实测）。🔴 **代价固定**：报告上分不出文/理 → 由**前端在报告页标题旁补一行小字**（读 `exam_paper.subject_type` 原值，如「文科中文」），模板本身不动。将来若必须印在纸上，再改模板 `enum` + `names` + Word/PDF 样稿 |
| **23** | **成绩单弹窗里要不要显示解析** | `question.analysis` 全库已是 HTML 段落（`<p>…</p>` + KaTeX），而模板用 `esc()` 输出 → 标签会被印成字面量 | 本文取「**不下发 `explanation`**」（[3.6.2](#362--get-recordexamrecordidscorereportpreview) 规则 5），弹窗只有「你的作答 / 参考答案」。要显示解析需三选一：后端剥标签（公式退化成 LaTeX 源码）/ 模板改 `innerHTML` 再跑 KaTeX / 干脆不做。**须拍板** |
| **24** | ✅ **成绩单 PDF 由谁生成（v3.6 已定案）** | 现状 `ScoreReportPdfServiceImpl` 是 **684 行 PDFBox 手绘 HSK 版式**，且依赖 `C:\Windows\Fonts`（Linux 容器必乱码）；`exam_record.report_url`（varchar(1000)）与 `report_unlocked` **两列早已存在**，本仓零代码写过，TEST 库已有 **11 行**有值（全是被外部上传服务写进去的） | 🔒 **定案：前端生成 → 上传 → 回存链接**（[3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接)）。<br>① 前端用官方模板 `CSCAReport.render()` 渲染 → 导出 PDF；<br>② `POST /api/system/file/uploadFile` 上传（需新增，现有 upload 只收 image/audio）；<br>③ `POST /record/{id}/scoreReport` 回存链接 → 写 `exam_record.report_url`；<br>④ `GET /record/{id}/scoreReport` 改 **302** 到该链接（不再服务端渲染）。<br>**放弃的两条路**：~~(a) 服务端 PDFBox 重画 CSCA 版式~~（要重写 684 行 + 打包中文字体）、~~(b) headless Chromium~~（多运行时依赖，容器还要装字体）。**已知代价**：PDF 内容后端无法校验（见 3.6.4 风险表），靠「只有本人能写 + URL 含 recordId + 页脚二维码指向 preview」缓解 |

### 4.4 现状 → 目标差异清单

> **编码前必须过一遍**。左列是**当前代码/库的真实行为**（2026-10-19 实测）。**标 P0 的不改就上不了线**。

| # | 现状（代码/库实测） | 影响 | 本文处置 | 级别 |
|---|---|---|---|---|
| **1** | `startCscaExam`（:269）**完全不做次数校验与扣减**（HSK `startExam:119` 有 `hasAvailableQuota`、`:235` 有 `decrementQuotaByUser`，CSCA 分支一条都没有） | 考试次数形同虚设，**任何人可无限考** | [3.2.1](#321--改造-post-answerstartcsca)：**B 方案** —— 加 2 个带 `level` 的薄重载 + 事务内 `decrementQuota(id)`，返回 `false` 判 `8105` | **P0** |
| **2** | `submitCscaExam`（:593）判分用 `correctAnswer.equalsIgnoreCase(userAnswerContent)` | **多选（35 题）必判错** | 改 `CscaAnswerNormalizer#equalsSet`（[4.2](#42-答案归一化与判分)） | **P0** |
| **3** | `getCscaPaperDetailWithAnswers`（:1809）把 `answer` / `analysis` **一起下发** | **考试中就能看到全部答案** | Service 层不再 `set`（[3.3.1](#331--改造-get-answerpapercscadetailpaperid)） | **P0** |
| **4** | `/answer/submit` ①新建 `exam_answer` 时**不写 `exam_record_id`**；②接受客户端 `isCorrect` 并落库；③按 `section_mapping` 更新计时（CSCA 为 NULL，白跑）。🔴 **该接口与 HSK 共用** | ①按 `recordId` 查不到该行 → 判分漏题；②**客户端可伪造对错**。⚠️ 但 HSK 的成绩不依赖此值（交卷后 `AsyncGradingServiceImpl:76-101` 异步重判覆盖），所以**全局改会把 HSK 的即时反馈打成"全错"** | 强制写 `exam_record_id`（两端）；**`isCorrect` 置 0 / 不碰 timer / current_question_number 只在 `exam_type=2` 分支生效**（[3.3.2](#332--改造-post-answersubmit)） | **P0** |
| **5** | `getCscaExamResult`（:759）**不校验 `userId`** | ✅ **不是缺陷，是刻意设计**（报告要能给非答题者看） | **保持不校验**；三个报告出口（`result` / `scoreReport/preview` / `scoreReport`）口径一致，附三条配套约束（[3.5.1](#351--改造-get-recordcscaexamrecordidresult) 说明块） | ✅ 已确认 |
| **6** | `getQuestionDetail` 依赖 `selectByPaperAndUser`（**只查 `status=0`**） | **交卷后查不到记录 → 看不了单题解析** | 按 `examRecordId` 直查（[3.5.2](#352--改造-get-recordpaperidquestionquestionid)） | **P0** |
| **7** | `submitCscaExam` 无 `status!=0` 判断、无 `UPDATE … WHERE status=0` | 重复/并发交卷会**重复判分** | 幂等 + 条件更新（[3.4.1](#341--改造-post-recordpaperidsubmitcsca)） | **P0** |
| **8** | 无 `deadline_time` 概念，超时只能靠客户端 | 改本地时间/关网即可"永久答题" | 服务端权威截止（[3.4.1](#341--改造-post-recordpaperidsubmitcsca) 第 3/7 条） | **P0** |
| **9** | `ScoreReportPdfServiceImpl` 是 HSK 专用（`level + " 成绩报告"`、听/读/写分段表） | CSCA 无 `level`、无分段，直接调会出空白/异常 | 按 `exam_type` 分流到 `CscaScoreReportPdfService`（[3.6.3](#363--改造-get-recordexamrecordidscorereport--csca-改读已上传的-pdf)） | **P0** |
| **10** | `startCscaExam` 无参数校验（`version` / `subjectTypeMapping` / `languageVersion` 可为 null）；`selectByCscaParams(null,…)` 会退化成"版本不限定" | 传空可抽到别的版本的卷 | 三参数强制非空 + 枚举校验（[3.2.1](#321--改造-post-answerstartcsca)） | P1 |
| **11** | `startCscaExam` 写 `listen_total = cscaTotalScore`、`total_score = Σquestion.score` | 改分前 `48×2.08=99.84` 时"满分"显示 99.84；**v3.4 题库已改分（Σ=100.00）后该现象消失** | 仍统一 `total_score = structure.full_score`（防再漂），`listen_*` 恒 0 | P1 |
| **12b** | `startCscaExam`（:269）**不写个人资料快照**（`real_name/gender/nationality/birthday` 全空；HSK `startExam:198-237` 有写） | CSCA 记录 `real_name` 实测 **156/156 全 NULL** → 成绩单姓名空白 | 开考前 `8104` 硬拦 + 开考写快照（[3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) / [3.2.1](#321--改造-post-answerstartcsca) 第 7 条）；历史记录才回落 `UserClient` | P1 |
| **12** | `submitCscaExam` 把未答计入 `wrong_count` | 报告"答错 16"实际是"未答 16" | `wrongCount` 只算 `answered=1 AND is_correct=2` | P1 |
| **13** | `/record/user/records`（:1111）不传时间**默认只查最近 30 天**；`level` / `source` 对 CSCA 无意义 | 模考记录"历史消失"；`examLevel` 拼出 `"level null"` | 取消默认、加 `subjectTypeMapping` / `examType` 筛（[3.6.1](#361--改造-get-recorduserrecords)） | P1 |
| **14** | `getCSCAAnswerCardDetail` **只有标记没有收藏**（`is_tag` 取自 `exam_answer`，`csca_question_favorite` 零引用）；`currentQuestionNumber.equals(...)` 无空判断；`section` 写死 `"CSCA"` | 答题页 ★ 与答题卡 ★ 无从显示；`currentQuestionNumber=null` 时 **NPE** | `isTag` **保留**、补 `favorite` / `tagCount` / `favoriteCount`、`Objects.equals`、加 `remainingSeconds`（[3.3.5](#335--改造-get-answercscacarddetailpaperid)） | P1 |
| **15** | `startCscaExam` 不写错题本 | 需求 2.6「错题同步」落空 | 交卷时同步 `csca_question_wrong`（[3.4.1](#341--改造-post-recordpaperidsubmitcsca) 第 6 条） | P1 |
| **16** | exam-service **无任何收藏代码**（`csca_question_favorite` 全仓零命中）；`/answer/paper/tag` 只写 `is_tag`，且它是 **HSK 共用的标记** | 考试里的收藏无处可落（需求 2.6 要求考试收藏进「我的-学习与测试-收藏夹」） | **新增** `POST /answer/csca/favorite` 写 `csca_question_favorite`（[3.3.4](#334--新增-post-answercscafavorite--考试内收藏)）；`paper/tag` **一行不改** | **P1** |
| **17** | 库里 `exam_record` 已有 `deduct_type` / `report_unlocked` / `report_url` 三列但**代码零引用** | 列"悬空" | `deduct_type` 接上（`0` 未扣 / `1` 免费次数 / `2` 点数预留）；`report_unlocked` / `report_url` **本版不用**（保留不删） | P1 |
| **1b** | `decrementQuotaByUser`（HSK 在用）**无 `level` 维度**、**不过滤 `status` / `deleted` / 有效期**、**不刷 `updated_time`**；返回行数**调用方从不检查** | 🔴 **B 方案下会一次扣掉 5 科**（考数学，物理化学的次数也没了） | CSCA **禁用**，改 `decrementQuota(id)`（带 `remain_quota > 0` + 刷 `updated_time`，返回 0 判 `8105`）。HSK 侧**本版不动**，另记技术债 | **P0**（B 方案前提） |
| **1e** | 3 参 `getQuota` / `hasAvailableQuota` 走 `selectByUserIdAndExamTypeAndVersion`（**无 `level` + `LIMIT 1`**） | B 方案下一人 5 行 → **随机返回某一科**，5 科次数混成一份 | CSCA **一律用 4 参重载**（开考校验/扣减）+ MP `in(level, 5科)` 批量查（[3.1.1](#311--get-recordcscaquota--5-科剩余次数)）；**不调** `POST /speaking/quota`（口语模块，[3.1.3](#313--不复用-post-speakingquota--csca-次数只走-get-recordcscaquota)） | **P0**（B 方案前提） |
| **1f** | **HSK 的 quota 事实模型 = 一人一行**（TEST 库实测：HSK 22 行 / 22 个用户、HSKK 22 / 22、Proficiency 7 / 7；**`level` 一律是 `'1'`**、`version` 一律 `HSK2.0`） | 所以 HSK 那套「不带 level 的校验 + `decrementQuotaByUser`」**能跑** —— 一个用户只有 1 行，`WHERE` 少 `level` 也只命中 1 行。**`level` 列在 HSK 侧根本没参与业务**，是占位值 | 🔴 **别把 HSK 的调用方式当模板照抄**：CSCA B 方案一人 5 行，必须带 `level`（[3.2.1](#321--改造-post-answerstartcsca)） | 认知前提 |
| **1g** | 🔴 HSK 校验写死 `hasAvailableQuota(userId, "HSK", "**HSK2.0**")`（`:119`），扣减却用**请求的 `version`**（`:235`）；而 `user_exam_quota` 里**没有任何 `HSK3.0` 行** | 学生考 **HSK3.0** 时：校验查 HSK2.0 的行 → 通过；扣减 `WHERE version='HSK3.0'` → **命中 0 行**（返回行数没人检查，静默）→ **HSK3.0 考试完全不消耗次数** | CSCA **不复制这个写法**：校验与扣减必须用**同一组参数**（`examType` / `version` / `level`）。HSK 侧本版只记录不改 | **P0**（HSK 现网缺陷） |
| **1h** | `decrementQuota(id)`（带 `remain_quota > 0` 守卫 + 刷 `updated_time`）**全仓零调用**，一直是死代码 | 未被任何场景验证过 | CSCA 是它**第一个真实使用方** → 必须补单测（并发两笔只能成 1 笔）+ 覆盖返回 `0` 时的 `8105` 分支 | P1 |
| **1i** | `queryExamInProgress`（:241）**方法头部两行 `isBlank` 强校验 `version` + `level`**，对所有调用方生效，且只查 HSK（`selectOngoingExamByUserIdAndLevel`） | CSCA 没有「等级」→ **每次调用都被 500「等级不能为空」挡回**（2026-10-22 实测确认）；只删校验不改 SQL 则仍查不到 CSCA 记录 | 校验**下沉进 HSK 分支**（HSK 行为零变化）；CSCA 分支两项都不校验，`version` 由服务端兜底 `'CSCA'` 再走 `selectOngoingCSCAExamByUserIdAndSubjectTypeMapping`（[3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验)） | **P0** |
| **1j** | 🔴 **`/answer/batch` 与 `/answer/statistics` 前端从未调用**（前端 85 个 API 常量里都没有；`ExamApiProvider` 19 个方法里也没有）。实测：`batch` → `500 系统内部错误`；`statistics` → `totalQuestions=25` 而该卷 48 题 | 本文原把它们列成「🔧改造 / ✅复用」→ **白做工**，还误导人以为断网补传有批量通道 | 双改判 **⛔ 不用、也不改**（[3.3.3](#333--不用-post-answerbatch--前端零调用实测还-500) / [4.9](#49-联调实测记录2026-10-22真调-test-后端)）；断网补传改为**逐题重发 `/answer/submit`** | 认知修正 |
| **1k** | `POST /record/{paperId}/leave` **前端 `ExamApiProvider#leaveExam` 正在调用**（body `{questionNumber, section, questionId?}`），实测 `200 已暂离考试` 并回写 `leave_*` 五个字段 | 原「⛔ CSCA 停用」若照做 → **App 切后台 / 切题的行为直接断掉**（前端会 404/500 且无兜底） | 改判 **✅ 复用、一行不改**（[2.1](#21-端点总表17-在用--2-不用--4-新增) 第 18 行） | **P0**（改错就断功能） |
| **1l** | `/answer/submit` 的答**字段名是 `answer`**（不是 `userAnswer`），且 `paperId` / `questionId` / `questionNumber` 三个 `@NotNull` 生效；传错名字**静默丢答案**（`200` + `answer:null`） | 前端若按「`userAnswer`」写 → 每题都保存成功但答案为空，交卷全 0 分且无报错 | 文档入参示例与字段表统一写 **`answer`**，并标注「`questionNumber` 必填」 | P1（联调陷阱） |
| **1c** | `UserExamQuota.isInExam` 字段**没有 `@TableField(exist=false)`**，而表里**没有 `is_in_exam` 列** | 一旦用 `save` / `updateById` 会 `Unknown column 'is_in_exam'`；现在没炸只因全走 XML | 补 `@TableField(exist = false)`（1 行）；否则 CSCA 发次数时会踩 | P1 |
| **1d** | 全仓**没有 `user_exam_quota` 的写入/发放代码**（auth-service 只在注销重注册时按快照写回） | CSCA 上线后**全员 0 次** | 见 [4.3](#43-待确认事项) 第 3 条（三选一） | **P0**（阻塞） |
| **18** | PDF 字体依赖 `resources/fonts/` + 系统路径回退（`C:\Windows\Fonts\...`） | **Linux 容器里没有 Windows 字体**，回退失败即乱码 | ⛔ **CSCA 侧本项彻底消失**：v3.6 起服务端**完全不生成** CSCA 成绩单（前端渲染上传、后端只存链接）；HSK 仍走原 PDFBox 路径，字体问题维持现状不动（[4.3](#43-待确认事项) 第 24 条） | P1 |
| **19** | `selectUntakenPaperCSCA` **没有 `exam_type=2` 条件**（只靠 `version='CSCA'` 兜） | 将来有别的考试也用 `CSCA` 版本号 → 抽到错卷 | 补 `exam_type=2` | P2 |
| **20** | 42 条 `status=0` 历史记录（`deadline_time` 为空） | 新 Job 会误扫/误交 | Job 条件加 `deadline_time IS NOT NULL`；上线前清理 | **P0**（上线动作） |

### 4.5 需求页面元素 → 接口映射（元素级）

| 页面 | 需求里的元素 / 输入 | 输出（本文对应字段） |
|---|---|---|
| **4.1 考试首页** | 科目卡（5 个）+ 默认选中 | `GET /api/system/dict/code/csca_subject` → `items[]`：`itemValue` = 科目码、`itemText` = 名称、`sortOrder` = 顺序、`isDefault=1` = 默认选中（🔴 按 **`status === 0`** 过滤，0 才是正常） |
| | 每张卡上的**次数角标** | `GET /record/csca/quota` → `quotas[i].remainQuota` / `hasQuota`（**固定 5 条，顺序与字典 `sortOrder` 一致**） |
| | 科目卡上的「N 套卷 / 90 分钟 / 100 分」 | 🔻 **首页不展示**：卷列表走 `GET /paper/list/csca`、单卷的题数/时长/满分走 `GET /paper/csca/detail?paperId=` |
| | 语言开关（中文 / English） | 前端常量：需求 2.1 定死中文两科只出中文卷；**库中 0 张英文卷** → 其余三科的 English 开关一并置灰 |
| | 切科目 / 切语言 | 前端本地状态（字典 + 次数各 1 次已拿全，**切 tab 无需再请求**） |
| | 点【开始模拟考试】 | `queryExamInProgress.action` 五选一 |
| | 试卷为空 Toast | `paperCheck.available=false` / `action=NO_PAPER` |
| | 资料缺失弹窗（**5 项**，含姓名） | `profileCheck.incompleteFields[]`（中文名，直接展示；有姓名项时提示「成绩单需要真实姓名」） |
| | 次数不足弹窗 | `action=QUOTA_EXHAUSTED` + `quotaCheck.remainQuota` |
| | ~~扣费确认弹窗~~ | **本期无**（点数体系未实现） |
| | 中途退出 → 恢复 | `action=RESUME`（`startCscaExam` 本身也会先查进行中会话并直接返回） |
| **4.2 答题页** | 选选项 → 实时保存 + 答题卡变绿 | `POST /answer/submit` → `answered=1` |
| | 收藏 / 取消（★） | 🆕 `POST /answer/csca/favorite` → `favorite`（`true`/`false`）+ `favoriteCount` |
| | 标记（黄格） | ✅ `POST /answer/paper/tag` → `isTag`（**语义不变**，与收藏互不影响） |
| | 上一题 / 下一题 | 前端本地（整卷已加载）+ `currentQuestionNumber` |
| | 答题卡图标 | `GET /answer/csca/card/detail/{paperId}` |
| | 交卷按钮 / 末题变交卷 | `POST /record/{paperId}/submit/csca`（确认弹窗数据来自 `card/detail` + `checkSubmit`） |
| | mm:ss 倒计时 | `remainingSeconds`（每次接口都回） |
| **4.3 答题卡弹窗** | 总题数 / 已答 / 未答 | `totalQuestions` / `answeredCount` / `unansweredCount` |
| | 网格四色 | `questions[].answered` / `isTag` / `current`（第四个态 = 全 false）；★ 角标另看 `favorite` |
| | 点题号跳转 | 前端（`number` 定位） |
| **4.4 交卷弹窗** | 四项统计 | `card/detail` 的 **`tagCount`** + `checkSubmit` 的三项（⚠️ 不是 `favoriteCount`） |
| **4.5 诊断报告** | 成绩卡 | `CscaExamResultDTO` 的 `score` / `totalQuestions` / `answeredCount` / `durationText` / `avgTimePerQuestionText` |
| | 答题概览网格 | `questionCards[].status` |
| | 单题解析弹窗 | `GET /record/{paperId}/question/{questionId}` |
| | 【重新考试】 | 回首页 → `queryExamInProgress` → `start/csca` |
| | 【下载成绩单】 | 跳 `scoreReport/preview` |
| **4.6 成绩单预览** | 完整成绩单 | `GET /record/{id}/scoreReport/preview` |
| | 下载按钮 → PDF | `GET /record/{id}/scoreReport` |
| **2.6 数据同步** | 收藏 / 错题 / 记录 | 收藏：[3.3.4](#334--新增-post-answercscafavorite--考试内收藏)；错题：[3.4.1](#341--改造-post-recordpaperidsubmitcsca)；记录：[3.6.1](#361--改造-get-recorduserrecords) |

### 4.6 表结构与 DDL 变更

**结论：只动 `exam_record` 一张表**（3 个新列 + 1 个索引 + 1 个列注释），其余全部复用。

```sql
-- ① 新增 3 列
ALTER TABLE exam_record
  ADD COLUMN deadline_time BIGINT NULL COMMENT '交卷截止时间(毫秒)=start_time+duration_minutes*60000，NULL=无计时(历史数据)' AFTER duration,
  ADD COLUMN deduct_amount DECIMAL(5,2) NOT NULL DEFAULT 0.00 COMMENT '本次实扣点数(免费次数=0.00，本期恒0)' AFTER deduct_type,
  ADD COLUMN deduct_detail VARCHAR(200) NULL COMMENT '扣减明细JSON，如[{"bucket":"POINT_PACK","points":2.00}]' AFTER deduct_amount;

-- ② deduct_type 语义扩为 3 值（原注释只写了 0/1）
ALTER TABLE exam_record
  MODIFY COLUMN deduct_type TINYINT NULL DEFAULT 0 COMMENT '扣减来源：0=未扣/存量 1=免费次数(user_exam_quota) 2=点数(预留)';

-- ③ 超时扫描索引（Job：status=0 AND deadline_time < now）
ALTER TABLE exam_record
  ADD INDEX idx_status_deadline (status, deadline_time);

-- ④ 考试次数初始行（🔒 B 方案：每用户 × 5 科目 = 5 行，level = 科目码）
--    ⚠️ 表里没有 is_in_exam 列，别照抄实体字段，否则 Unknown column
--    ⚠️ 影响行数 = 用户数 × 5，先 DRY-RUN，别直接 --apply
INSERT INTO user_exam_quota
  (user_id, exam_type, version, level, total_quota, used_quota, remain_quota,
   valid_start_time, valid_end_time, status, deleted, created_by, update_by, created_time, updated_time)
SELECT u.id, 'CSCA', 'CSCA', subj.code, 3, 0, 3, NULL, NULL, 1, 0, u.id, u.id,
       UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000
FROM user u
CROSS JOIN (
              SELECT 'arts_chinese' AS code
    UNION ALL SELECT 'science_chinese'
    UNION ALL SELECT 'math'
    UNION ALL SELECT 'physics'
    UNION ALL SELECT 'chemistry'
) subj
WHERE u.deleted = 0
  AND NOT EXISTS (
    SELECT 1 FROM user_exam_quota q
    WHERE q.user_id = u.id AND q.exam_type = 'CSCA' AND q.version = 'CSCA'
      AND q.level = subj.code AND q.deleted = 0
  );
```

**不改表的部分（明确写下来，避免有人"顺手加列"）**

| 需求 | 为什么不用改表 |
|---|---|
| 收藏 / 错题 | `csca_question_favorite`（12 列）/ `csca_question_wrong`（13 列）**已建**，`source` + `record_id` 已能承载 `exam` |
| 剩余时长 | 由 `deadline_time - now` 计算，不落"剩余"列 |
| 当前题号 | `exam_record.current_question_number` 已存在 |
| 成绩单 | `exam_record.report_url` / `report_unlocked` **两列早已存在**（`varchar(1000)` + `tinyint`），v3.6 起直接复用，**不需要新增列**。⚠️ 只需确认 PROD 也有这两列（TEST 已确认） |
| 次数对账 | 唯一真源 = `user_exam_quota.used_quota` 累计；`exam_record.deduct_*` 只标来源 |
| 整卷题目 | `exam_answer` 由 `initAnswerCard` 初始化（已有） |

> ⚠️ **DDL 执行守住"五闸门"**：① `DATABASE()` 断言；② `@@hostname` 断言；③ 先备份结构 + 回滚 SQL；④ 事务内回读 `SHOW FULL COLUMNS` 核对；⑤ 幂等（`information_schema` 判存在再 ALTER）。**`ALTER` 是隐式提交，`rollback()` 不保护**，异常分支必须显式补偿。
> ⚠️ **`user_exam_quota` 的 `INSERT … SELECT` 必须先 DRY-RUN 出影响行数**，再 `--apply`。

### 4.7 改造清单（工时分块）

> v2 相对 v1 的本质变化：**没有"另起一套"，全部是"就地改造 + 4 个新增"**（2 个**纯读**：次数查询、成绩单预览；2 个**写**：考试内收藏、存成绩单链接）；考试次数限制也**直接复用 HSK 的 `user_exam_quota`**，不新造点数账本；科目清单**复用现有字典**，不新造目录接口。

**需要新建的代码（仅此）**

| 类 | 作用 |
|---|---|
| `csca/CscaQuotaDTO` | 5 科次数返回体（🆕 A）。**只有这 1 个 DTO** —— 方法挂在 `ExamRecordServiceImpl#getCscaQuota`，**不新建 Controller / Service / Mapper** |
| `csca/CscaScoreReportService` + `CscaScoreReportDTO` | 成绩单预览（🆕 B）。🔴 **字段集 = 模板 `data.schema.json` 原样**（`version/reportId/candidate/exam/result/questions[]`），不自造字段，见 [3.6.2](#362--get-recordexamrecordidscorereportpreview)。v3.3 另加 **5 个下发字段**（模板不读、不影响校验）：`exam.startedAt` + `result` 的 `correctCount` / `wrongCount` / `unansweredCount` / `accuracyRate`（`accuracyRate` 用 **0–1 小数**，与 `CscaExamResultDTO` 一致） |
| `exam/dto/CscaFavoriteRequest` + `CscaFavoriteResponse` | 考试内收藏入参 / 回执（🆕 C）。方法挂在现有 `ExamAnswerController` / `ExamAnswerServiceImpl` |
| `csca/CscaReportUploadRequest` + `CscaReportUploadResponse` | 🆕 **存成绩单链接**（[3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接)）。方法挂在 `ExamRecordController` / `ExamRecordServiceImpl`，**不新建 Service** |
| `exam/client/AuthProfileClient` | 🆕 **资料完整性判定**（[3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验)）：`GET /app/profile/check`，透传 `Authorization` + `X-Client-Type`。装配进 `config/AiServiceConfig`（与 `UserClient` 同一套 `HttpServiceProxyFactory`，`baseUrl=http://auth-service`） |
| ~~`csca/CscaScoreReportPdfService` + `CscaPdfFontLoader`~~ | ⛔ **本版不建**：服务端**完全不生成** CSCA 成绩单 PDF —— 前端渲染上传、后端只存链接（[4.3](#43-待确认事项) 第 24 条 v3.6 定案） |
| `csca/CscaAnswerNormalizer` | 答案归一化判分 |
| `csca/CscaExamErrorCode` | 8101–8113 码表 |
| `csca/CscaFavoriteWriter` / `CscaWrongBookWriter` | 直写两张姊妹表。🔴 后者必须 `@Transactional(propagation = Propagation.REQUIRES_NEW)` + 外层 try-catch，**写失败不得回滚交卷**（[3.7.7](#377--事务边界p0上线阻塞)） |
| `csca/CscaExamTimeoutJob` | 超时兜底 |

**需要改造的方法（均在原文件内，不新建类）**

| 文件 | 方法 | 改动 |
|---|---|---|
| `ExamRecordServiceImpl` | `startCscaExam` (:269) | 参数校验 + **次数校验/扣减（B 方案按科目：`hasAvailableQuota(4参)` + `decrementQuota(id)`）** + `deadline_time` + `total_score` 修正 |
| `ExamRecordServiceImpl` | `submitCscaExam` (:555) | 判分归一 + 幂等 + 未答口径 + **错题同步（委托 `CscaWrongBookWriter`，独立事务）** + 超时 |
| `ExamRecordServiceImpl` | `getCscaPaperDetailWithAnswers` (:1809) | 去掉 `answer` / `analysis` |
| `ExamRecordServiceImpl` | `getCscaExamResult` (:759) | **不做 `userId` 校验（by design，报告要给老师/家长看）** + `autoSubmitted` + `userId` 字段置 `null` |
| `ExamRecordServiceImpl` | `getQuestionDetail` | 按 `examRecordId` 直查（去 `status=0` 限制） |
| `ExamRecordServiceImpl` | `getUserRecordsWithDetail` (:1111) | 取消 30 天默认 + CSCA 筛选 |
| `ExamRecordServiceImpl` | `queryExamInProgress` (:241) | **`version` / `level` 非空校验下沉进 HSK 分支** + CSCA 分支（不校验这两项、`version` 兜底 `'CSCA'`） + `action` 决策 |
| **`exam/dto/ExamRecordRequest`** | 🆕 新增 3 个**纯可选**字段 `subjectTypeMapping` / `languageVersion` / `examType` | 既有字段不动、不加注解 —— 分支判定与 CSCA 入参都靠它们 |
| `ExamAnswerServiceImpl` | `submit` | 忽略 `isCorrect`（**仅 `exam_type=2`**，HSK 不变）。`exam_record_id` **实测已在写**，回归确认即可 |
| ~~`ExamAnswerServiceImpl`~~ | ~~`tag`~~ | ✅ **不动** —— 保留**标记**语义（写 `exam_answer.is_tag`），HSK 共用。收藏走下面新增的 `favoriteCsca` |
| `ExamAnswerServiceImpl` | `getCSCAAnswerCardDetail` | 保留 `isTag`、补 `favorite` / `tagCount` / `favoriteCount` + `Objects.equals` 修 NPE + `remainingSeconds` |
| `ExamAnswerController` / `ExamAnswerServiceImpl` | 🆕 `favoriteCsca`（`POST /answer/csca/favorite`） | 校验归属 + 卷快照 + `question.paper_id` 准入 + UPSERT `csca_question_favorite` + 回最终态 |
| `ScoreReportPdfServiceImpl` | `generateScoreReport` | CSCA **不再进这个方法**：`ExamRecordController` 先按 `exam_type` 分流，`exam_type=2` 直接 `302` 到 `report_url`（为空则 `8114`），HSK 才调它 |
| **`UserExamQuotaService` / `Impl`** | 🆕 加 2 个 4 参重载 `getQuota` / `hasAvailableQuota`（带 `level`） | 实现只调**已存在的** `selectByUserIdAndExamType`；`UserExamQuotaMapper` **一行不改** |
| ~~`SpeakingExamController` / `SpeakingExamQuotaRequest`~~ | ~~`POST /speaking/quota` 加可选 `level`~~ | ⛔ **已撤销** —— 那是口语模块的端点，CSCA 不复用（[3.1.3](#313--不复用-post-speakingquota--csca-次数只走-get-recordcscaquota)）。**这两个文件一行不改** |
| `ExamRecordController` / `ExamRecordServiceImpl` | 🆕 `getCscaQuota`（`GET /record/csca/quota`） | 一条 MP 查询取 5 行 → 固定 5 条输出；**只读** |
| `ExamRecordController` / `ExamRecordServiceImpl` | 🆕 `saveCscaScoreReport`（`POST /record/{examRecordId}/scoreReport`） | 🆕 v3.6：校验链 8 条 + 条件 `UPDATE` 写 `report_url` / `report_unlocked=1`；影响行数 0 → `8115` |
| `ExamRecordController#cscaScoreReportPreview` | `GET /record/{id}/scoreReport/preview` | 补 `reportReady` 字段（v3.7：**只此一个**，链接不由这里下发） |
| `system-service/FileController` | 🆕 `uploadFile`（通用 PDF 上传）+ 🔴 **修 `:97` 硬编码 `userId=3232344L`** | 成绩单上传通道（[3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接)）；不修就会把所有成绩单堆进 `pdf/3232344/` |
| `UserExamQuota`（entity） | 补 `@TableField(exist = false)` 到 `isInExam` | 否则 `save` / `updateById` 会 `Unknown column 'is_in_exam'` |

**完全不动的（7 个复用端点 + HSK 全链路）**：`/paper/list/csca`、`/paper/csca/detail`、`/paper/structure/version/{v}`、**`/answer/paper/tag`（标记）**、**`/record/{paperId}/leave`（暂离）**、`/answer/checkSubmit/{paperId}`、`/number/examTicket`，以及所有 HSK 路径。

**明确不用、也不改的（2 个）**：`/answer/batch`（前端 0 调用 + 实测 500）、`/answer/statistics/{paperId}`（前端 0 调用 + 题数算错）。

### 4.8 上线检查清单

| # | 项 | 责任方 | 不做的后果 |
|---|---|---|---|
| 1 | ~~`CSCASubjectType` 补 `science_chinese`~~ ✅ **代码已有 5 值，本项作废** | 后端 `common` | — |
| 2 | `exam_paper_structure` 补 `science_chinese`（80 题 / 90 分钟 / 100 分） | 数据 | `8103` |
| 3 | **`user_exam_quota` CSCA 行怎么来**（§4.3 第 3 条三选一：手工发 / auth 注册发 / 首次按需发）。🔒 B 方案 = **每人 5 行**（5 科目 × 1 次；邀请再 +2/科） | 产品 + 后端 | 不解决 → **全员 0 次，开局就 `8105`**，功能等于上不了线 |
| 4 | 若选「auth 注册发」：注册时**按 5 科目各插一行** `CSCA/CSCA/<科目>/1/0/1`；邀请奖励 `+2` 加到哪科先按 §4.3 第 18 条定 | 后端 auth | 新用户无法考试 / 邀请奖励拿不到 |
| 5 | `UserExamQuota.isInExam` 补 `@TableField(exist=false)` | 后端 exam | 发次数走 `save` 时 `Unknown column 'is_in_exam'` |
| 7 | ~~网关白名单加 `/api/exam/paper/csca/catalog`~~ ✅ **本项作废**（本模块无免登录端点；`/record/csca/quota` 需登录） | 运维 | — |
| 8 | 清理 42 条 `status=0` 脏记录 | 数据 | Job 扫出大量 0 分报告 |
| 9 | 注册 `cscaExamTimeoutJob`（XXL-Job，5 分钟） | 运维 | 关机后会话永远"进行中" |
| 10 | ✅ **本项作废（v3.6）**：服务端不再生成 CSCA 成绩单 PDF，**不需要往镜像里塞中文字体**。若将来改回服务端渲染才需重启此条（[4.3](#43-待确认事项) 第 24 条） | 运维 | —（当前无风险） |
| 11 | `exam_record` DDL（3 列 + 1 索引）双环境执行 | DBA | 建会话写 `deadline_time` 报错 |
| 12 | 收藏/错题表在 **PROD** 已建（`csca_question_favorite` / `csca_question_wrong`） | DBA | 收藏报 `Table doesn't exist`（只是少个 ★）；**错题表未建且未做隔离 → 整笔交卷回滚，用户分数丢失** |
| 12b | 🔴 **错题本同步必须与交卷事务隔离**（`REQUIRES_NEW` + 外层 try-catch），交卷返回体不含错题字段 | 后端 | 表缺失/写失败时用户做完 48 题交不上去（[3.7.7](#377--事务边界p0上线阻塞)） |
| 12c | 错题 `section` 取 **`exam_paper.subject_type_mapping`**（不是 `question.subject_type_mapping`，PROD 全 NULL） | 后端 | 错题本科目筛选全失效、科目标签空白 |
| 13 | 前端确认：新增端点的 id 按**字符串**解析，改造端点按**数字**解析 | 前端 | 19 位 id 精度丢失 |
| 14 | 前端倒计时以 `remainingSeconds` 为准，不用本地 `Date.now()` 起算 | 前端 | 改本地时间可"延长考试" |
| 15 | 🆕 `POST /answer/csca/favorite` 前后端联调：① ★ 走新端点、标记走 `paper/tag`，**两个按钮别接错**；② 答题卡同时显示黄格（`isTag`）与 ★（`favorite`）；③ 交卷弹窗第四项取 `tagCount` | 前端 + 后端 | ★ 点了不生效 / 收藏进了"标记"统计 |
| 16 | 修 `system-service/src/main/resources/sql/csca_subject.sql`：`sort_order` 改成 **文1→理2→数3→物4→化5**、`is_default` 挪到 `arts_chinese`，再对 PROD 执行 | 后端 | **考生端首页顺序错、默认科目落在数学**（字典已是首页唯一数据源，不再是"管理端体验"问题。详见 [4.3](#43-待确认事项) 第 19 条） |
| 17 | 🔬 **改动后必须按 [4.9](#49-联调实测记录2026-10-22真调-test-后端) 回归**，重点 5 条：① 整卷不再下发 `answer` / `analysis`；② 伪造 `isCorrect=1` 不再落库；③ CSCA 传参调 `queryExamInProgress` 不再 `500 等级不能为空`；④ `POST /record/{paperId}/leave` 仍 `200`；⑤ `/paper/list/csca` 前端展示名仍从 `source` 取 | 后端 | P0 改了但没验证 = 没改 |
| 18 | 前端确认：`paper/list/csca` 的元素 `paperName` 为 `null`，**卷名要读 `source`**；`/answer/submit` 答**字段名是 `answer`** | 前端 | 卷名空白 / 答案静默丢失（`200` 但不报错） |
| 19 | **成绩单模板资源进前端 build**：`report.html` 容器 + `report.css` + `report.js` + `assets/`（`header.png` 校名抬头、`watermark.png` 校徽水印、`app-qr.jpg` APP 码）。后端**不出**静态资源，也**不生成** PDF（v3.6） | 前端 | 成绩单页白屏 / 抬头、水印、二维码全缺 / 生成不出 PDF |
| 20 | 🔴 **满分口径自查（v3.4 已改分，仍须验一遍）**：① 跑 `SELECT p.subject_type_mapping, SUM(q.score) FROM question q JOIN exam_paper p ON p.id=q.paper_id WHERE p.exam_type=2 AND q.deleted=0 GROUP BY 1`，5 科必须都是 **100.00**（TEST 已过；**PROD 实测仍是 99.84，改分脚本未执行**）；② `preview` 里**没有任何换算代码**（`score = final_score`、`fullScore = 100` 两个字面量赋值），`total_score` 不参与计算；③ 改分脚本**必须在开考功能上线前**在目标环境跑完 | 后端 | ① 漏改 → 新卷满分作答只显示 99.8（不报错，静默偏差）；② 若有人「好心」加回换算 → 与题库口径打架（[3.6.2](#362--get-recordexamrecordidscorereportpreview) 规则 1） |
| 21 | 🔴 **姓名：开考前硬拦 + 开考写快照**（已定）。① [3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 用 `8104` 挡下 5 项资料（**含姓名**），前端弹窗跳个人中心；② [3.2.1](#321--改造-post-answerstartcsca) 第 7 条把 `realName/gender/nationality/birthday` 写进 `exam_record`（对齐 HSK `startExam`）；③ 成绩单只读快照，仅历史 156 条 NULL 记录才回落 `UserClient` | 后端 | 成绩单姓名空白（`candidate.name` 是模板唯一必填的考生信息） |
| 22 | ✅ **已确认**：文理中文都印「中文」（[4.3](#43-待确认事项) 第 22 条）；前端在报告页标题旁用 `exam_paper.subject_type` 补一行小字区分文/理 | 前端 | 报告上看不出文科还是理科中文 |
| 23 | 🔴 **资料硬门槛回归（新增）**：找一个 `real_name` 为空的账号（TEST 库 27 个用户里 **10 个**为空）→ `queryExamInProgress` 必须回 `8104` + `incompleteFields:["姓名"]` 且**不建会话**；补全资料后再考 → `exam_record.real_name` **有值**、成绩单姓名正常。另验证 HSK 不受影响（HSK 分支不做此项拦截） | 后端 | 拦不住 = 成绩单姓名仍是空的；拦过头 = 把 HSK 一起挡了 |
| 24 | 🔴 **统计四项不许抄 `exam_record`（v3.3 新增）**：`preview` 的 `correctCount` / `wrongCount` / `unansweredCount` / `accuracyRate` 必须与 `questions[].status` 由**同一次循环**产出，且三者和 == `questionCount`。实测 CSCA 记录 `wrong_count` **把未答算成错**（`answered_count=0` 却 `wrong_count=48`）、`accuracy_rate` 恒 `0.00`，照抄 → 报告「答错 48」与题号网格 48 个「—」自相矛盾 | 后端 | 统计与网格打架（[3.6.2](#362--get-recordexamrecordidscorereportpreview) 硬规则 7） |
| 25 | 🔴 **PDF 上传通道（v3.6 必做）**：① `system-service` 新增 `POST /file/uploadFile`（`folder="pdf"`、只收 `application/pdf`、≤ 10 MB）；② **修 `FileController:97` 的 `Long userId = 3232344L;`** → 改成从 JWT 取真实 userId；③ 路径统一 `pdf/{userId}/csca_report/csca-report-{examRecordId}-{uuid}.pdf` | 后端（system-service） | ① 不新增 → PDF 传不上去（现有 upload 只收 image/audio）；② 不修硬编码 → **所有考生的成绩单堆进 `pdf/3232344/`**，无法按人清理、也看不出归属 |
| 26 | 🔴 **`report_url` / `report_unlocked` 两列环境确认（v3.6）**：TEST 已确认存在（`varchar(1000)` / `tinyint`，且已有 11 行有值）；**PROD 必查**（`SHOW FULL COLUMNS FROM exam_record LIKE 'report%'`）。另验证 `POST /record/{id}/scoreReport` 写入后 `GET` 能 302 出去（`curl -I` 看 `Location` + 跟随后 `200 application/pdf`） | 后端 | 列不存在 → `Unknown column 'report_url'`（整个交卷后链路报错）；`302` 到坏链 → 用户点下载拿到 404 而页面不报错 |
| 27 | 🔴 **资料校验改造回归（v3.6）**：① 缺姓名的账号调 `queryExamInProgress` → `8104` + `incompleteFields:["姓名"]`；② **故意不带 `X-Client-Type`** 调 auth `profile/check` → 会回 `userId=1` 的数据（**不是 401**）→ 确认 exam 侧转发时两个 header 都带上了；③ 停掉 auth-service → 必须**快速失败**（`500 用户资料校验服务暂不可用`），**不能卡住 30 秒**、**不能放行** | 后端 | ② 漏 header → 拿别人的资料判定，全员「资料完整」；③ 无超时 → 点开始转圈；fail-open → 无名成绩单 |
| 28 | 🔴 **成绩单「唯一出口」自查（v3.7）**：① 全仓搜 `report_url`，除 `GET /scoreReport` 的 302 与 `POST` 的写入外，**只允许**再出现一次（`preview` 里算 `reportReady` 的判空）；② 打开 `CscaScoreReportDTO`，字段清单里**不得有** `reportUrl` / `pdfUrl`；③ 实际调 `preview` 抓响应，`grep -c "http" ` 应为 **0**（`data` 里不该出现任何 URL） | 后端 | `preview` 又下发链接 → 前端直接开直链，桶改私有后全部失效，还绕过了 302 这个唯一维护点（[§3.6 分工表](#36-模考记录与成绩单)） |

---

### 4.9 联调实测记录（2026-10-22，真调 TEST 后端）

> 本节是**唯一有真实请求/响应支撑的一节**。前面各章的结论绝大多数来自读代码，本节是对「App 实际怎么调」的核对 —— 也修正了几条读代码得出的错误结论。

**环境**

| 项 | 值 |
|---|---|
| 前端 | `http://10.45.1.201:8080`（Flutter Web，**DDC debug 构建**，`version.json` = `app_name:hbk / 1.2.0+4`） |
| 后端 baseUrl | 🔴 **`http://8.138.185.11`**（前端 `AppConfig._defaultBaseUrl` 硬编码，**就是 TEST 服务器**，不是前端机器） |
| 公共头 | `X-Client-Type: APP`（缺 → `400 缺少 X-Client-Type 请求头`）+ `Authorization: Bearer <jwt>` |
| 网关鉴权链 | 验签（HS512，secret = `gateway/application.yml` 默认值）→ 按 claim `userId` 调 `auth-service /validate/app/{id}`（**查库存在性/禁用/删除**）→ 放行 |
| Mock | `AppConfig._defaultUseMock = false`（真调后端）；`_defaultSkipFaceCapture = false` |
| 实测身份 | TEST 库真实用户 `2112787850284290049`（自签 token，未改任何人密码、未改业务数据） |

**前端 85 个 API 常量里，与考试直接相关的只有这些**（`core/values/api_constants.dart`，逐项比对）

```
认证   login smsLogin zaloLogin facebookLogin facebookBindLogin register smsRegister logout
       deleteAccount updateProfile sendCode sendBindEmailCode sendSmsCode  profileCheck ★
HSK    hskLevelList speakingExamLevelList speaking{Structure,Start,SubmitAnswer,SubmitExam,
       ExamResult,QuestionDetail,RecordList,Quota} examPaperDetail paperStructureVersion
       paperListByVersion paperDetailV1 examTicketNumber startExam updateSectionTimerStatus
共用   queryExamInProgress answerCardDetail submitSingleAnswer tagQuestion checkSubmit
       userExamRecords examRecordBase
CSCA   cscaPaperList cscaPaperDetail cscaStartExam cscaCardDetail cscaAnswerPaperDetail cscaRecordResult
```

> 🔴 **`/answer/batch` 和 `/answer/statistics` 不在这个列表里** —— 前端从来没有调用过它们（`ExamApiProvider` 的 19 个方法里也没有）。这是本文 v2.9 把这两个端点改判为「⛔ 不用」的唯一依据。

**逐端点实测结果**

| # | 实测请求 | 实测响应 | 与本文原结论的差异 |
|---|---|---|---|
| 1 | `GET /paper/list/csca?version=CSCA&subjectTypeMapping=math&languageVersion=chinese` | `200`，5 张数学卷。🔴 **`paperName` 全是 `null`，卷名在 `source` 字段**（「数学模拟试卷5」…） | 补：前端展示名要取 `source`，不是 `paperName` |
| 2 | `GET /paper/csca/detail?paperId=` | `200` `{paperId, paperName, description, totalQuestionCount:48, totalDurationMinutes:60, fullScore:100.00}` | ✅ 一致 |
| 3 | `POST /answer/start/csca` `{version:"CSCA", subjectTypeMapping:"math", languageVersion:"chinese"}` | `200`，32 个字段。🔴 **没有任何 `deadlineTime` / `remainingSeconds`**（只有 `startTime`、`endTime:0`）；`totalScore:99.84`（=48×2.08，**改分前的实测值；v3.4 题库已改分，新卷应为 100.00**）、`listenTotal:100.00`；**不扣次数**（`user_exam_quota` CSCA 仍 0 行）。再调一次 → **原样返回同一条记录**（续考） | ✅ 「不扣次数 / 无 deadline / totalScore 错 / listenTotal 错 / 内置续考」全部成立。入参确认**不需要 userId** |
| 4 | `POST /answer/queryExamInProgress` `{version:"CSCA", level:"1"}` | `200` `data:null`（落到 HSK SQL，查不到） | — |
| 4b | 同上，`{version, subjectTypeMapping, languageVersion}`（**无 level**） | 🔴 `500 等级不能为空` | ✅ **铁证**，[3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 的分支拆分必需 |
| 5 | `GET /answer/paper/csca/detail/{paperId}` | `200`，43 KB / 48 题。🔴 **`answer` 与 `analysis` 都在**（含完整解析 HTML）。结构：`sections[0].questions[]`；题干在 **`passage`**（`content:null`）；`optionContent = {questions:null, options:{A,B,C,D}}`；`section.contentName="阅读"`、`contentType="SEC_READ"`（**数学卷的 section 也叫「阅读」**） | ✅ P0 答案泄漏成立。补：解析结构要给前端讲清，字段不是 `content` 而是 `passage` |
| 6 | `GET /answer/csca/card/detail/{paperId}` | `200` `{paperId, currentQuestionNumber, currentSection:"CSCA", sections:[{section:"CSCA", sectionName:"CSCA考试", questions:[{questionNumber, answered, enabled:null, current, isTag}]}]}`。🔴 **无 `remainingSeconds`、无 `favorite` / `favoriteCount`** | ✅ 「要补 favorite/tagCount/remainingSeconds」成立 |
| 7 | `GET /answer/checkSubmit/{paperId}` | `200` `{canSubmit:true, totalQuestions:48, answeredCount, unansweredCount, unansweredQuestions:[{questionId, questionNumber, **section:"1"**, groupTitle:null}]}` | 补：`unansweredQuestions[].section` 存的是**题号字符串**，不是 section 码 |
| 8 | `POST /answer/submit` `{paperId, questionId, questionNumber, **answer**:"D", isCorrect:1}` | `200`。库里落成 `answer='D'` / `is_correct=**1**` / `answered=1` —— **标准答案是 C，我答 D，伪造 `isCorrect=1` 成功** | 🔴 ✅ P0「客户端可伪造对错」**实测复现** |
| 8b | 同上但字段写成 `userAnswer` | `200`，`answer:null`、库 `answer=''`、`answered=0` —— **字段名错就静默丢答案**，不报错 | 🔴 新发现：字段名必须是 **`answer`**；缺 `questionNumber` 直接 `400 题号不能为空` |
| 9 | `POST /record/{paperId}/submit/csca`（**无请求体**） | `200`，`wrongCount:**48**`、`answeredCount:0` —— 未答全部计成「答错」。重复调用仍 `200`，无状态判断 | ✅ 「未答计入 wrongCount」「无幂等判断」成立。补：**该端点不收 body**，只认 path 上的 `paperId` + token |
| 10 | `GET /record/csca/{examRecordId}/result` | `200` 12–14 KB。字段：`recordId/paperId/subjectType:"math"/subjectTypeText:"数学"/languageVersion:"chinese"/languageVersionText:"中文"/**userId**/status/score/totalScore/totalQuestions/answeredCount/correctCount/wrongCount/unansweredCount/accuracyRate/duration/durationText/avgTimePerQuestion/avgTimePerQuestionText/timeEvaluation/timeEvaluationType/**questionCards[]**`。🔴 **`userId` 真的下发了**、**无 `autoSubmitted`**；`questionCards[].correctAnswer`（不是 `standardAnswer`） | ✅ 「补 autoSubmitted / userId 置 null」成立 |
| 11 | `POST /record/{paperId}/leave` `{questionNumber:1, section:"CSCA", questionId:…}` | `200` `已暂离考试`，回 `ExamRecordResponse`（含 `leaveAt` / `leaveQuestionId` / `leaveQuestionNumber` / `answeredDurationOnLeave` / `leaveSectionMapping`） | 🔴 **v2.9 改判：原写「⛔ CSCA 停用」是错的** —— 前端 `leaveExam` 正在用 |
| 12 | `GET /answer/statistics/{paperId}` | `200` 但 `totalQuestions:**25**`（该卷实际 48 题）、`listenAnswered/readAnswered/writeAnswered` 全 0 | 🔴 数据本身不准 + 前端零调用 → 改判「不用」 |
| 13 | `POST /answer/batch` `{paperId, answers:[{questionId, questionNumber, answer}]}` | 🔴 `500 系统内部错误` | 🔴 改判「不用」（详见 [3.3.3](#333--不用-post-answerbatch--前端零调用实测还-500)） |
| 14 | `POST /answer/paper/tag` `{examRecordId, questionId, isTag:1}` | `200` `data:true`，库 `exam_answer.is_tag=1` | ✅ 「它是标记不是收藏」成立 |
| 15 | `GET /auth/app/profile/check` | `200` `{completed:true, **incompleteFields**:[]}` | 🔴 **原写「代码里没有任何校验入口」是错的**：auth-service 早有这个端点、前端也在调；字段名是 `incompleteFields` 不是 `missingFields` |
| 16 | `GET /record/user/records?pageNum=1&pageSize=3` | `200`，元素里**已有** `subjectType` / `subjectTypeText` / `languageVersion` / `languageVersionText` / `examType` | 补：CSCA 字段**大部分已存在**，改造重点在「取消 30 天默认 + 筛选参数」 |
| 17 | 本文新增的端点（`/record/csca/quota`、`/answer/csca/favorite`、`/record/{id}/scoreReport/preview`、`/record/{id}/scoreReport`） | 全部 `500 系统内部错误`（Controller 无此映射） | ✅ 确认「尚未实现」，不是路径写错 |
| 18 | 直连 TEST 库 `user_exam_quota` | `exam_type='CSCA'` → **0 行**；该用户 HSK / HSKK 各 1 行且 `remain_quota=0` | ✅ 「上线即全员 8105」成立 |
| 19 | 直连 TEST 库 `exam_answer` | `exam_record_id IS NULL` → **全库 0 行**；本次 `/answer/submit` 新建的行也**带正确 `exam_record_id`** | 🔴 **原写「新建行不写 exam_record_id」与现网不符** —— 已写入（机制是 `submit` 先按 `paperId+userId` 取到 record，写入时带上；本地代码 `builder()` 没显式 `.examRecordId()`，但实测有值，**部署版本与本地代码可能不完全一致**）→ 该 P0 降为「已修复，回归测试确认即可」 |
| 20 | 直连 TEST 库 `exam_record.report_url` | TEST **11 行非空**（10 条 `hsk_report` + 1 条 `csca_report`），全部形如 `http://www.hkbvvtb.com:9000/hsk/pdf/**3232344**/{hsk\|csca}_report/{hsk\|csca}-report-{examRecordId}-{uuid}.pdf`；`report_unlocked=1` 共 9 行；**PROD 全空（0 行）** | ✅ 证明「前端生成→上传→存链接」这条路**已有别的服务在跑**，缺的只是 CSCA 自己的写入口（[3.6.4](#364--post-recordexamrecordidscorereport--保存前端生成的成绩单链接)）。🔴 同时解开了 `3232344` 之谜：**`system-service/FileController.java:97` 把 `userId` 硬编码成 `3232344L`**，不是用户 id（两库 `user` / `sys_user` 都查无此号） |

**从实测反推的真实调用顺序**（前端 DDC 代码 + 上面的响应共同确认）

```
进 CSCA 页   GET  /paper/list/csca                          （按科目×语言列卷）
             GET  /auth/app/profile/check                   （completed / incompleteFields）
             GET  /record/user/records                      （历史记录）
点开始       POST /answer/queryExamInProgress                （★ 目前不带 subjectTypeMapping → 500）
             POST /answer/start/csca                        （{version,subjectTypeMapping,languageVersion}）
拉卷         GET  /answer/paper/csca/detail/{paperId}        （含 answer/analysis ← P0）
答题         POST /answer/submit                             （{paperId,questionId,questionNumber,answer,section,isCorrect}）
             POST /answer/paper/tag                          （标记）
切后台       POST /record/{paperId}/leave                    （暂离）
答题卡       GET  /answer/csca/card/detail/{paperId}
交卷         GET  /answer/checkSubmit/{paperId}
             POST /record/{paperId}/submit/csca              （无 body）
报告         GET  /record/csca/{examRecordId}/result
             GET  /record/{paperId}/question/{questionId}    （单题解析）
```

---

> **文档版本**：v3.7 / 2026-10-22 / 依据 TAPD wiki《CSCA考试》v1.3.0 + 10.28 & 11 月调整 + 测试库 `xuexitest` 实测 + `exam-service` 现有代码盘点 + **官方成绩单模板 `平台接入/data.schema.json`** + **前端 Flutter Web 构建产物与 TEST 后端真实请求实测**（[4.9](#49-联调实测记录2026-10-22真调-test-后端)）。
> **v2.1 变更**：考试次数方案锁定 **B 方案（每科各 3 次，`level` = 科目码，一人 5 行）**；`catalog` 的 `quota` 对象改为 `quotas[]` 数组；`POST /speaking/quota` 的 `level` 从"可选优化"升为"必改项"（**v2.4 已撤销**）；新增 §4.4 的 1e 与 §4.3 的第 18 条。**代码尚未改动。**
> **v2.2 变更**：§3.1.1 补「为什么不用 `sys_dict/csca_subject` 字典」（含跨服务 / 可考性 / 顺序契约三条硬约束）；§4.3 新增第 19 条（字典 SQL 文件与 TEST 库顺序不一致，实测证据）与第 20 条（`catalog` 保留结论）；§4.8 新增第 16 项。**（v2.5 已推翻"不用字典"的结论，见下）** 代码尚未改动。
> **v2.3 变更**：按需求确认，`GET /paper/csca/catalog` **删掉卷量 / 题量 / 时长 / 满分**（`paperCount` / `questionsPerPaper` / `durationMinutes` / `fullScore` / `languages[]` 五组字段），首页卡片只留「科目 + 可考性 + 语言可用性 + 次数 + 续考」；新增 `availableLanguages`（查库得来，替代原 `languages[]` 承担 English 置灰）；Mapper 由 `COUNT(*)` 降为两条 `SELECT DISTINCT`。§2.1 / §2.4 / §4.3 第 13·20 条 / §4.5 同步。**（v2.5 整节撤销）** 代码尚未改动。
> **v2.4 变更**：⛔ **撤销「给 `POST /speaking/quota` 加 `level`」**——那是**口语模块**的端点（`SpeakingExamController` / `SpeakingExamQuotaRequest`），CSCA 不复用。§3.1.3 从「✅ 复用」改写为「⛔ 不复用」并给出四条理由。**HSK / HSKK / Proficiency 一行不改。** 代码尚未改动。
> **v2.5 变更**：⛔ **撤销新增 `GET /paper/csca/catalog`**。砍掉卷量/时长/满分后，它剩下的数据里 **科目清单由现有字典 `GET /api/system/dict/code/csca_subject` 承接**（实测 `sortOrder` 1–5 = 文→理→数→物→化、`isDefault=1` 在 `arts_chinese`，正好覆盖需求 1.3）、**续考**由 `startCscaExam` 第一步自动返回、**资料**在 `queryExamInProgress` 校验 —— 只有**次数**必须新端点，改为 `GET /record/csca/quota`（§3.1.1 整节重写）。**端点数不变（仍 2 个），但 `catalog` 换成了 `quota`**：新增类从 3 个降为 1 个、读取表从 5 张降为 1 张，网关白名单也不用加。§0.2 / §0.4 / §1.1 / §1.2 / §1.3 / §1.4 / §2.1 / §2.2 / §2.3 / §2.4 / §3.1.3 / §4.3 第 13·19·20 条 / §4.4 1e / §4.5 / §4.7 / §4.8 同步。**代码尚未改动。**
> **v2.6 变更**：新增 **[1.0 功能清单](#10-功能清单这批接口新增了什么)** —— 按「功能」而非「端点」重组全文：A 从无到有 5 项（次数限制 / 资料拦截 / 倒计时+续考 / 收藏 / 错题本）、B 补完雏形 3 项（成绩单 / 诊断报告 / 模考记录）、C 不算功能但 P0 的修复（答案泄漏 / 伪造 isCorrect / 多选判分 / 交卷幂等）、D 一个端点都没加的部分（字典 + 6 个复用）、E 上线前置阻塞（发次数代码缺失）。同时修正头部两处过期表述：状态版本号 `v2.1 → v2.6`、v2 对比表里「新增端点 = 科目目录聚合」改为 `quota`（`catalog` 已于 v2.5 撤销）。**代码尚未改动。**
> **v2.7 变更（2026-10-22）**：🔴 **「标记」与「收藏」拆开** —— 原设计把 `POST /answer/paper/tag` 改造成收藏，**是错的**：它是**考试标记**（写 `exam_answer.is_tag`，答题卡黄格），且 **HSK 共用**，改语义 = 动 HSK。现改为：**`paper/tag` 一行不改**（✅ 复用，「处置」由改造改为复用），**新增 `POST /answer/csca/favorite`** 写 `csca_question_favorite`（`source='exam'`，软删复活，回最终态）。连带修正：答题卡 `isTag` **保留**（标记）+ 🆕 `favorite`（收藏）+ `tagCount` / `favoriteCount` 两个计数；**交卷弹窗第四项「标记题数」改取 `tagCount`**（原文档错写成 `favoriteCount`）；答题卡四色 = 当前/已答/**标记**/未答，收藏只用 ★ 角标。计数同步：🔧改造 **12→11** ／ ✅复用 **6→7** ／ 🆕新增 **2→3**（共 22 个端点）。§0.8 / §0.9 / §1.0 / §1.1 / §1.2 / §2.1 / §2.2 / §2.3 / §3.3.4（整节重写）/ §3.3.5 / §3.3.6 / §4.3 第 9·14·15 条（**第 15 条作废**）/ §4.4 第 14·16 条 / §4.5 / §4.7 / §4.8 第 15 项 同步。**代码尚未改动。**
> **v2.8 变更（2026-10-22）**：🔴 **`queryExamInProgress` 的入参校验按分支拆开** —— 原设计只放宽了 `level`，仍把 `version` 定为必填；实际那两行 `isBlank` 是**写在方法头部、对所有调用方生效**的死门槛，CSCA 没有「等级」，只要不挪就被 `"等级不能为空"` 挡回。现改为：**两行强校验整体下沉进 HSK 分支**（HSK 行为**零变化**），**CSCA 分支 `version` / `level` 两项都不校验** —— `level` 完全不参与查询，`version` 由**服务端兜底 `'CSCA'`**（🔴 不能真留 null：续考 SQL 是 `b.version = #{version}`，`= NULL` 恒不成立 → 静默查不到 → 重复开考白扣次数）。同时给出**分支判定伪代码**（`userId` 是唯一提到两支出外的校验）与「自相矛盾入参以 `examType`/`subjectTypeMapping` 为准」的兜底口径。§1.3 T1 / §2.1 第 4 行 / §3.1.2（现状注释 + 改造点 + 伪代码 + 入参表 + 三层逻辑）/ §4.4 新增 1i / §4.7 `queryExamInProgress` 行同步。**代码尚未改动。**
> **v2.9 变更（2026-10-22）**：🔬 **首次用真实请求核对 App 实际调用**（前端 `10.45.1.201:8080` 的 Flutter Web DDC 构建 → 后端 `8.138.185.11`），新增 **[4.9 联调实测记录](#49-联调实测记录2026-10-22真调-test-后端)**（19 条逐端点实测 + 真实调用顺序 + 前端 85 个 API 常量比对）。据此**改判 4 处**：① 🔴 **`/answer/batch`、`/answer/statistics` 前端从未调用**（`api_constants.dart` 里根本没有这两项，`ExamApiProvider` 19 个方法也没有）→ 由「🔧改造 / ✅复用」改为 **⛔ 不用、也不改**（`batch` 实测还 `500`、`statistics` 的 `totalQuestions` 算成 25 而卷是 48）；② 🔴 **`/record/{paperId}/leave` 由「⛔ 停用」改为「✅ 复用」** —— 前端 `leaveExam` 正在调，停用它等于切断「切后台/切题」；③ 🔴 **资料校验不是「没有入口」** —— auth-service 早有 `GET /auth/app/profile/check`，实测回 `{completed, **incompleteFields**}`，字段名不是 `missingFields`；④ 🔴 **`/answer/submit` 实测已写 `exam_record_id`**（全库 0 行 NULL），该 P0 降为「回归确认」。**计数同步**：19 现有端点 → **20 个在用（🔧改 10 / ✅复用 7 / 🆕新增 3）+ 2 个不用**。另补 3 条坑：卷名取 `source` 不取 `paperName`、`submit` 字段名必须是 **`answer`**（写 `userAnswer` 会静默丢答案）、整卷题干在 **`passage`**、`submit/csca` **不收 body**。§1.0 / §1.1 / §1.2 / §1.4 / §2.1 / §2.2 / §2.3 / §3.1.2 / §3.3.3（整节重写为「⛔ 不用」）/ §3.3.2 / §4.4 新增 1j–1l / §4.7 / §4.8 同步。**代码尚未改动。**
> **v3.0 变更（2026-10-22）**：🆕 **补上「错题本」这一整块功能设计 —— §3.7（7 小节）**。原文档只在交卷改造里塞了一条"同步错题本"的 SQL，**没有把它写成一个功能**：读在哪、怎么筛选、字段从哪取、和收藏/标记怎么区分、失败会不会拖垮交卷，全都没有。补齐的要点：① **考试侧只写不读**（写 = 交卷判分后 UPSERT `csca_question_wrong`；读/移出/复习三端点属练习模块 `GET /api/practice/csca/wrong-book`，**零新增端点**）；② 🔴 **`section` 必须取 `exam_paper.subject_type_mapping`**（实测 31 卷全有值），不能取 `question.subject_type_mapping`（PROD 1904 行全 NULL → 错题本科目筛选失效）；③ 🔴 **未答题也是 `is_correct=2`**，过滤必须叠加 `answered=1`，否则一张没做完的卷会把所有未答题灌进错题本；④ 🔴 **写错题本不得回滚交卷**（`csca_question_wrong` PROD 未建表 → 同事务会让整笔交卷失败，用户 48 题白做），必须 `REQUIRES_NEW` + 外层 try-catch；⑤ **只进不出**（判对不自动移出）、**不覆盖 `source`/`record_id`**（与练习侧"首次落值"一致）。同时**修掉一处硬错误**：`exam_paper_question` **这张表根本不存在**（实测 TEST 库无此表，卷题关联就是 `question.paper_id`）—— §3.3.4 收藏端点的准入校验与 §4.7 改造清单已改正，照原文实现会直接 `Table doesn't exist`。§1.0 A 类第 5 项（「错题本同步」→「错题本（考后自动收录）」）/ §1.0 D 类 / §1.2 / §3.4.1 / §4.7 / §4.8 第 12·12b·12c 项同步。**代码尚未改动。**
> **v3.7 变更（2026-10-22）**：🧹 **拆掉 v3.6 里真正的重复出口**（用户问「`preview` 和 `scoreReport` 不是功能重复了吗」）。
> **两个端点本身不重复**：一个交 **JSON 数据**（页面渲染 / 生成 PDF 要用），一个交 **PDF 文件**（`302` 到已存链接）—— 成绩单页必须拿数据才画得出分数与 48 格题号网格，而「下载」不该顺带拉 48/80 题的 JSON；且 **HSK 也走同一个 `GET`**，保留它 App 的下载代码才不用按 `exam_type` 分叉。
> **但 v3.6 造出了一处真重复**：让 `preview` 顺带下发 `reportUrl`，于是同一个文件有了**两个出口**（前端可直接开直链、也可走 302），字段说明里还写着「不要用它拼下载地址」，自相矛盾。
> → **v3.7 定：`preview` 只回 `reportReady` 布尔，链接只由 `GET /scoreReport` 交出**（出口唯一；桶改私有只改这一处，前端零改动）。
> → 新增 **§3.6 开头「三个端点分工表」**，把「谁交什么、谁调、为什么不能被替代」写死，避免下次又有人往 `preview` 里塞 URL。
> → `POST /record/{id}/scoreReport` 的响应**去掉 `reportUrl` 回显**（只回 `examRecordId` / `reportReady` / `saved` / `overwritten`），不留第二个入口。
> → 同步：`preview` 示例 JSON（删 `reportUrl` 键）、字段表（2 行并 1 行）、§1.2、§1.3 T12、§2.1、§4.7、§4.8 新增第 28 条自查。**「分享」另行处理**：App 分享 PDF 文件本身，要链接就取 302 的 `Location`，长期外链属「分享页」需求、另立接口。
> **v3.6 变更（2026-10-22）**：两条都由用户拍板，**方向都变了，所以要把理由写清楚**。
> **① `GET /auth/app/profile/check` 正式接进开考校验**。v3.2～v3.5 的写法是「exam-service 用 `UserClient.getUserById` 自己判空、不调 auth」，等于把 auth 的 5 项规则**在 exam 里抄了一份**，auth 改口径 exam 不会跟着变。现改为 exam `queryExamInProgress` **真调**该端点：新增 `AuthProfileClient`（`@HttpExchange("/app")` + `/profile/check`），**必须透传 `Authorization` + `X-Client-Type: APP`**（缺后者会回落到 `getDefaultUserInfo()`，userId 恒 1，**不是 401**），超时 1.5s、**fail-closed**（`500`，不放行、也不冒用 `8104`）。判定归 auth、**快照取值仍归 `UserClient`**（建会话时写 `real_name` 等 4 列）。
> **② 成绩单 PDF 改为「前端生成 → 上传 → 后端存链接」**。这是对 [4.3](#43-待确认事项) 第 24 条的**改判**：原方案 (a) 前端 `window.print()` 后**不留档**、每次下载都要重新渲染；(b) 服务端 headless Chromium 要装中文字体。新方案用上 `exam_record` 里**早已存在但本仓零代码写过**的 `report_url`（varchar(1000)）与 `report_unlocked`——实测 TEST 已有 **11 行**有值（外部上传服务写的），PROD 0 行。
> → 新增 **§3.6.4 `POST /record/{examRecordId}/scoreReport`**（第 4 个新增端点，写 `report_url`；host 白名单 + URL 必须含 recordId + 本人校验 + 条件 `UPDATE` 幂等，超 1000 字符/钓鱼外链/串号一律 `8116`）；**§3.6.3 改为 `302` 重定向**到已存链接（为空 `8114`，HSK 分支一行不改）；**§3.6.2 补 `reportReady` / `reportUrl`**（撤销「不返回 pdfUrl」的旧结论）。
> → 错误码新增 **8114 / 8115 / 8116**，8113 语义从「PDF 渲染失败」改为「成绩单**数据**不可用」。端点统计：17 在用 + 2 不用 + **4 新增** = **21**。
> → 🔴 顺带查出 `system-service/FileController.java:97` **硬编码 `Long userId = 3232344L`** —— 这就是 MinIO 里那堆 `pdf/3232344/...` 的来源，也是「3232344 查不到用户」之谜的答案。**CSCA 上线前必须修**，否则全员成绩单堆进同一个目录。
> → **已知代价（已写进 3.6.4 风险表）**：PDF 内容后端**无法校验**（只看链接不开文件）；直链**公开可读**（桶匿名）；缓解 = 只有本人能写 + URL 必须含 recordId + 页脚二维码指向 preview。将来桶改私有，只需把 302 目标换预签名，**前端无感**。
> **v3.5 变更（2026-10-22）**：🔒 **撤销 v3.4 的「`total_score` 兜底」，成绩单彻底零换算**（用户定：题库后续会统一改到位，不为老数据写分支）。[3.6.2](#362--get-recordexamrecordidscorereportpreview) 规则 1 改为纯字面量：`score = exam_record.final_score`（不乘不除不判断）、`fullScore = 100`；字段映射表 `result.score` 同步删掉兜底说明；§4.8 第 20 条改为「`preview` 里不得有任何换算代码 + 改分脚本必须先于开考功能上线」。**已知副作用（可接受，已写进文档）**：改分前的历史记录 `total_score` 快照是 99.84，其 `final_score` 最高就是 99.84 → 成绩单印 99.84，**不会被修正成 100**；但**不会报错**（模板只校验 `fullScore===100` 且 `score∈[0,100]`，99.84 合法），老成绩单照常能打开。PROD 卷仍需先跑改分（实测仍 `2.08×48=99.84`）。
> **v3.4 变更（2026-10-22）**：✅ **试卷分值已归一，成绩单不再做满分换算**（用户 2026-10-22 完成改分）。题库单题分值调整后：文/理中文 `1.25 × 80 = 100.00`、数理化 **`2.00 × 40 + 2.50 × 8 = 100.00`**（TEST 库实测 5 科每卷 Σ 恒为 100.00）→ [3.6.2](#362--get-recordexamrecordidscorereportpreview) **规则 1 反转**：`score` **直接取 `final_score`**（原为 `final_score ÷ total_score × 100`），`fullScore` 恒 `100`；**仅保留一行兜底**（`total_score ≠ 100` 时才换算），因为库里还有两类非 100 数据：**改分前的历史记录 `total_score = 99.84`**（实测 136 条 CSCA 记录的老记录）与 **PROD 卷尚未改分**（直连 PROD 实测仍是 `2.08 × 48 = 99.84`）。连带修正：§2.4 单题分值行、§4.2 判分口径（单题得分 + 卷面总分）、§3.x 改造点第 5/6 条、§4.4 第 11 条、§4.8 **第 20 条改为「满分口径自查」**（给了 `SUM(question.score) = 100.00` 的校验 SQL，并明确 **PROD 漏改** 的后果）、§4.9 第 3 条实测值加注「改分前」、整卷示例 `score: 2.08 → 2.50`。另 🔴 **正确率量纲统一为 0–1**（`0.63` = 62.5%）：§4.2 原写 `× 100` 与代码 `AsyncGradingServiceImpl:195` 的 `divide(total,2)`、`exam_record.accuracy_rate` 列、[3.6.2](#362--get-recordexamrecordidscorereportpreview) 的 `accuracyRate` 都不一致，本次一并纠正（§3.5.1 两处示例 `62.50 → 0.63`）。
> **v3.3 变更（2026-10-22）**：📊 **成绩单 `preview` 补统计与考试时间**（[3.6.2](#362--get-recordexamrecordidscorereportpreview)）。`result` 新增 **`correctCount`（正确总数）/ `wrongCount`（错误总数）/ `unansweredCount`（未答总数）/ `accuracyRate`（正确率）**，`exam` 新增 **`startedAt`（开考时间）**；并新增**硬规则 7**：这四项**一律从 `exam_answer` 现算，禁止抄 `exam_record`** —— 实测 CSCA 记录 `answered_count=0` 却 `wrong_count=48`（未答被算成错）、`accuracy_rate` 恒 `0.00`，照抄会让报告「答错 48」与题号网格的 48 个「—」自相矛盾。量纲固定：`accuracyRate` **0–1 两位小数**（`0.75`），与 `CscaExamResultDTO` / `exam_record.accuracy_rate` 同尺度；模板 `statistics().accuracy` 是 **0–100**，**不是同一量纲**。另核对 `report.js`：`validate()` 不校验多余字段、`schema` 无 `additionalProperties:false` → **加这 5 个字段不会让模板抛错**，但**模板也不读这 4 个统计值**（它自己从 `questions[].status` 再数一遍），故两端必须同源同值。
> **v3.2 变更（2026-10-22）**：两条拍板落地。① **5 科目 → 4 值定为「文科中文 / 理科中文都印『中文』」**（[4.3](#43-待确认事项) 第 22 条从「须拍板」改「已定」）：模板 `exam.subject` 只认 4 值，前端传 5 值原件必被拒（已实测），故两科统一映射 `中文`；**报告分不出文/理的代价固定下来**，由前端在标题旁用 `exam_paper.subject_type` 补一行小字，模板不动。② 🔴 **`real_name` 改为开考前强制校验**（原方案是「成绩单预览时回落 `nickname` → `username`」，等于把 `user_8613060291168` 这种账号名印上正式成绩单）：[3.1.2](#312--改造-post-answerqueryexaminprogress--前置校验) 把资料完整性从「提示」升为**硬门槛**，缺项回 `8104` + `incompleteFields`（**5 项：姓名/性别/国籍/出生年月日/手机号，不含邮箱**，与 auth `checkProfileCompletion` 完全一致）；判定**不再额外调 `GET /auth/app/profile/check`** —— `UserClient.getUserById` 返回的 `UserResponse` 已含这 5 个字段，一次调用既判空又留快照值；[3.2.1](#321--改造-post-answerstartcsca) 新增第 7 条改造点，把 `realName/gender/nationality/birthday` 写进 `exam_record`（对齐 HSK `startExam:198-237`）；[3.6.2](#362--get-recordexamrecordidscorereportpreview) 姓名改为「只认开考快照」（新增硬规则 6），仅历史 156 条 `NULL` 记录才回落。连带修正：`missingFields` → **`incompleteFields`**（8 处）、「6 项」→ **5 项**（含 §0.8 / §1.0 / §1.1 / §1.2 / §3.1.2 / §3.2.1 / §3.6.2）、§4.4 新增 **12b**、§4.8 第 21/22 条改写 + 新增第 23 条（资料硬门槛回归）。

> **v3.1 变更（2026-10-22）**：📄 **成绩单 `preview` 按官方模板重写** —— 原来那份 DTO 是我按 HSK 报告卡的习惯自己拼的（准考证号 / 成绩单号 / 性别 / 国籍 / 生日 / 用时 / 平均用时 / 成绩等级 / pdfUrl），**跟官方 A4 模板一个字段都对不上**。现以 `CSCA成绩单模板/CSCA/…/平台接入/data.schema.json` 为**唯一契约**：`data` 里出现的就是 `version / reportId / candidate{id,name} / exam{attemptId,paperId,paperName,subject,language,submittedAt,timeZone,durationSeconds} / result{score,fullScore,questionCount} / questions[]{questionId,index,status,userAnswer,correctAnswer,explanation}`，前端 `CSCAReport.render(el, res.data)` 一行直接出图。**实测定下的四条硬约束**：① 🔴 **满分归一** —— 数理化卷每题 2.08 × 48 = `total_score` **99.84**，模板 `fullScore` 是 `const 100`，照抄直接被前端抛「CSCA 单科满分应为 100」；② 🔴 **5 科目 → 4 值** —— 模板只认 中文/数学/物理/化学，传「文科中文」「理科中文」原件必抛错，须映射成「中文」（代价：报告分不出文/理）；③ 🔴 **三态判定先看 `answered`** —— 未答题 `is_correct` 也是 **2**（= 错），只按 `is_correct` 判会把空题全印成红叉；④ 🔴 **姓名取不到快照** —— CSCA 记录 `real_name` 实测 **156/156 全 NULL**，须走 `UserClient` 回落。连带修正：`result` 的 `questionCards[].status` 与本端点同口径；PDF 出口由「新建 684 行 PDFBox 手绘」改为「前端打印」（[3.6.3](#363--改造-get-recordexamrecordidscorereport--csca-改读已上传的-pdf)）；[4.3](#43-待确认事项) 第 11/12 条作废、新增第 22–24 条；[4.8](#48-上线检查清单) 补第 19–22 条。
> **关联文档**：[`CSCA练习-接口设计文档.md`](../CSCA练习/CSCA练习-接口设计文档.md)（收藏/错题/科目口径以它为准）。
