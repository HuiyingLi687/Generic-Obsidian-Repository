# CSCA 练习 · 接口设计文档

> **所属模块**：`practice-service`（端口 **8087**，网关前缀 `/api/practice/**`，经 `StripPrefix=2` 后落到服务内路径，对照见 [2.2](#22-端点归属)）
> **业务范围**：CSCA（`exam_paper.exam_type = 2`）**按科目刷单题** —— 库中 **5 个原始科目**（文科中文 / 理科中文 / 数学 / 物理 / 化学；客户端可把文/理中文并为「中文」展示）× 语言（中文 / English），见 [0.8 与互动原型的对齐](#08-与互动原型的对齐v13)
> **设计约束**（用户已定，2026-10-11；2026-10-12 一处例外）：**不改题库**（`question.section_mapping` / `question.type_id_mapping` 保持 `NULL` 不动 —— ⚠️ **唯一例外**：同表的 `question.subject_type_mapping` 已于 10-12 补齐，用于科目统计与筛选，见 [4.4](#44-文档与实现的差异) 第 1 条）、**不做整卷与分节**，练习粒度为「科目 → 单题」；**业务表新增两张** —— `csca_question_favorite`（收藏）+ `csca_question_wrong`（错题本），均 2026-10-13 拍板**落库**、2026-10-19 **加 `csca_` 前缀**（原名 `question_favorite` / `question_wrong`）+ **各加 `language_version` 语言快照列** + **删 `section_mapping` 恒值列**（见 [4.3](#43-待确认事项) 第 10 / 15 条、[3.6.1](#361-收藏favorite) / [3.6.2](#362-错题本wrong-book)）；应用表只给 `practice_record` 加一列 `question_ids`（专存 CSCA 本次题集，2026-10-13 定，见 [4.4](#44-文档与实现的差异) 第 26 条）
> **交互依据**：`CSCA练习原型_v1.3`（手机端 H5，驾考宝典式刷题）—— 本文的**科目口径、语言切换、科目卡统计、答题页（答题/背题模式 + 收藏 + 答题卡）、完成页**均以该原型为准；**「我的」页（收藏夹 / 错题本 / 练习记录）以 `CSCA练习+错题本+收藏本` 原型为准**（2026-10-13 新增错题本）
> **数据依据**：测试库 `xuexitest`（`8.138.185.11`）实测侦察，2026-10-12；涉及 `exam_paper` / `question` / `question_group` / `exam_paper_structure` / `practice_record` / `practice_answer` / `practice_report`
> **状态**：设计稿 + **部分已编码**（2026-10-13）。`practice-service/.../practice/csca/` 包**已创建**，已实现 [3.1.1 `GET /csca/catalog`](#311-get-cscacatalog) / [3.2.1 `POST /csca/records`](#321-post-cscarecords)（建轮：幂等 + 进行中行锁 + 题集一次算定落 `question_ids`）/ [3.2.2 `GET /csca/questions`](#322-get-cscaquestions)（含 `layout` 下发）/ [3.2.3 `GET /csca/questions/{questionId}`](#323-get-cscaquestionsquestionid)（单题详情，与列表共用装配）/ [3.3.1 `PUT /csca/records/{recordId}/answers/{questionId}`](#331-put-cscarecordsrecordidanswersquestionid)（逐题作答：upsert + **写齐 5 个快照列** + 独立判分，`immediate=true` 回判分结果与 `standardAnswerLabels`）/ [3.3.2 `POST /csca/records/{recordId}/answers/batch`](#332-post-cscarecordsrecordidanswersbatch)（离线批量补传：批内去重 + **冲突合并** + 一条 SQL 批量 upsert，`skippedItems[].reason` 逐条说明）/ [3.3.3 `GET /csca/questions/{questionId}/solution`](#333-get-cscaquestionsquestionidsolution)（**答案出口**：标准答案 + 解析，**原值直传、不做归一化**，只需登录、**不要求已作答**）/ [3.4.1 `GET /csca/records/{recordId}`](#341-get-cscarecordsrecordid)（记录详情）/ [3.4.2 `GET /csca/records/{recordId}/answer-card`](#342-get-cscarecordsrecordidanswer-card)（答题卡：逐题格 + 按题型分组，`favorite` 段查 `csca_question_favorite`）/ [3.5.1 `POST /csca/records/{recordId}/submit`](#351-post-cscarecordsrecordidsubmit)（**交卷**：`status=3` 幂等 + 快照基准全量重判 + 只回写变化行 + 写记录汇总列 + `upsertReport`） / [3.6.1 `PUT` / `DELETE /csca/favorites/{questionId}`](#361-收藏favorite)（**收藏 / 取消收藏**：幂等 `INSERT … ON DUPLICATE KEY UPDATE` + `source` / 轮次快照只在首次插入写） / [3.6.1 `GET /csca/favorites`](#361-收藏favorite)（**我的收藏**：分页 + 科目 / 来源 / 语言三筛选 + 收藏时间区间 + 排序方向 + 作答态，题面与取题列表**同源同构**、**不含答案**） / [3.6.2 `GET /csca/wrong-book`](#362-错题本wrong-book)（**我的错题本**：分页 + 科目 / 来源 / 语言三筛选 + 错题时间区间 + 排序方向；**无作答态**，状态自持**不读作答表**） / [3.6.2 `DELETE` / `POST /csca/wrong-book/{questionId}`](#362-错题本wrong-book)（**移出 / 复习作答**：与收藏同一套幂等 upsert；复习作答只判分 + 同步、**不落作答表**）—— **本组 3 个端点全落地**；✅ ~~其余端点（`wrong-book` 组的 `DELETE` / `POST .../answer`）尚未编码~~ **2026-10-14 全部编码**（[4.4](#44-文档与实现的差异) 第 61 条）—— **本模块 16 个端点至此全部落地**；其中 `favorites*` / `wrong-book*` 的支撑表 `csca_question_favorite` / `csca_question_wrong` **TEST 已建表（2026-10-14 11:01、2026-10-19 重构）、⚠️ PROD 未建**（见文末「附 5」「附 6」）；3.3.1 第 7 条 / 3.3.2 第 6 条 / 3.5.1 第 8 条「同步错题本」**已接线**（`CscaWrongBookService#syncAfterGrade`：判错收录 / **判对与未评分不动**，错题本「只进不出」，2026-10-19 口径见 [4.4](#44-文档与实现的差异) 第 62 条）；`practice_record.question_ids` 加列 **TEST 已建（2026-10-13）、PROD 未建**（见 [4.4](#44-文档与实现的差异) 第 26 条 / 文末「附 4」）。本文仍是编码依据，**文档与实现不一致处以 [4.4](#44-文档与实现的差异) 为准**。

> ⚠️ **原型与题库存在三处口径差**（先读 [0.8](#08-与互动原型的对齐v13) 与 [4.5](#45-原型-v13-对照表)）：① 原型科目「中文」在库里是「文科中文 + 理科中文」两科（本模块**不合并** —— 按 5 个原始科目各给一张卡）；② 原型有「English」语言开关，但**库里没有任何 `english` 卷**；③ 原型练习页多出一张「**教学**」卡，**实为原型自身的错误**（库中不存在该科目），本模块**不实现**。以上均须在编码前拍板（见 [4.3](#43-待确认事项)）。

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

所有接口统一返回 `com.hsktreasure.common.result.Result<T>`，**HTTP 状态码恒为 200**，业务结果看 `code`：

```json
{ "code": 200, "message": "操作成功", "data": { } }
```

- `code` = `200` 成功；非 200 见 [0.5 错误码](#05-错误码)
- `data` 为 `null` 时字段仍保留（不省略），前端判 `code` 即可
- 异常统一由 `GlobalExceptionHandler` 兜住（`PracticeServiceApplication` 已 `@Import`），业务异常也返回 HTTP 200 + 错误 `code`

### 0.2 鉴权与客户端类型

沿用 `practice-service` 现状（`BaseController` + `X-Client-Type` 头 + JWT）：

| 场景 | 要求 |
|---|---|
| **目录接口**（`/csca/catalog`） | **免登录可读**（带 Token 则附用户统计）。目录是公共聚合数据，与用户无关 |
| **题目接口**（`/csca/questions*`：取题 / 单题详情 / 答案） | **必须登录**（2026-10-13 口径）。原因：取题要**按本人的练习记录取题集**（`recordId` 必填 + 归属校验，见 [3.2.2](#322-get-cscaquestions)），单题详情与答案同属一个内容出口，一并强鉴权。未登录抛 `BusinessException(401, "未登录或Token无效")` |
| **作答 / 离线补传 / 收藏 / 错题本类接口**（`/csca/records/**`、`/csca/favorites*`、`/csca/wrong-book*`） | **必须登录**。走 `requireAuthenticatedAppUserId(request, clientType)`，未登录抛 `BusinessException(401, "未登录或Token无效")` |

- 客户端类型头：`X-Client-Type: APP`（CSCA 练习是 App 端功能，非 `APP` 一律按未登录处理）
- Token 顺序：`Authorization: Bearer xxx` → `X-Access-Token` → `?token=`
- **`userId` 一律从 Token 取，绝不由前端传入**（防止刷别人的进度）
- ⚠️ 与 HSK 目录接口的差异：阅读 / 写作 / 口语目录是**强鉴权**、听力目录**允许游客**。CSCA 的**目录**允许游客（与听力同向），但**题目类接口一律强鉴权**（2026-10-13 定，见上表）—— 这意味着**未登录不能刷题**，是「**按练习记录取题 / 题集归属校验**」的必然结果（题集挂在 `recordId` 上，必须先知道「你是谁」）。
- ⚠️ **强鉴权带来两条工程约束**：① `/csca/questions` 的响应**带用户维度**（同一 URL 不同用户 / 不同 `recordId` 结果不同）→ **不可做公共缓存**（CDN / 网关级缓存），见 [0.6](#06-枚举与版本号)；② 网关或 CDN 若按「GET 可缓存」统一配置，需把 `/csca/questions*` 排除在外。

### 0.3 「语言版本」`languageVersion` 与界面文案是两件事

这是 CSCA 与 HSK 最容易混淆的一点，**先分清再读全文**：

| 概念 | 载体 | 取值 | 作用 |
|---|---|---|---|
| **考试语言版本** | `exam_paper.language_version`（**业务数据**） | `chinese` / `english` | 决定**用哪一批卷/题**。CSCA 是给留学生考「用中文出的数学/物理/化学卷」，中文卷与英文卷是**两套不同的题** |

- 接口入参里的 `languageVersion` **只指考试语言版本**（业务维度）。
- 🔴 **服务端不处理界面文案**（2026-10-12 定）：本模块**不解析** `Accept-Language`、也不回 `*_en` / `*_vi` 译文；`subjectType`（科目名）回**库中中文原名**。界面文案（中文 / English / 越语）**由前端字典自行处理**（见 [4.3](#43-待确认事项) 第 5 条）。
- 🔴 **`typeId` 是「映射值」，不是库中题型原名**（2026-10-12 定）：对外只有**两个值** —— `MULTI`（库中 `type_id='多选'`）/ `SINGLE`（**其余一切**题型名：`识解汉字` / `选词填空` / `辨析词语` / `选词成段` / `补全语句` / `阅读理解` / 空值）。库中 8 种原名**一律不透出**；**数据库里的 `type_id` 一个字符都不改**，映射只发生在服务端出口（[4.1](#41-枚举速查) `CscaQuestionTypes`，细则见 [3.2.2](#322-get-cscaquestions) 第 13 条）。
- ⚠️ **实测：当前全库 31 张 CSCA 卷的 `language_version` 全是 `chinese`，没有一张 `english` 卷**（TEST 与 PROD 一致）。英文卷是**未来导入**，接口必须提前把 `languageVersion` 做成参数。🔴 **2026-10-13 口径收口：`/csca/questions` 与 `POST /csca/records` 两个接口的 `languageVersion` 均为「必填、无缺省」**（未传 → `400` / `CSCA_LANGUAGE_INVALID`）—— 取题与建轮都必须明确指定用哪一批卷，不猜缺省（见 [4.4](#44-文档与实现的差异) 第 35 / 39 条）。

### 0.4 ID 序列化（**与写字课文档相反：本文 id 一律是字符串**）

**结论：本模块所有 id 在响应里一律是 JSON 字符串**（`"recordId": "2096765985265061890"`）。

依据：`practice-service` 自己那份 `config/JacksonConfig.java`（**有效、已 `@Import` 进 `PracticeServiceApplication`**）注册了 `ToStringSerializer`，把 `Long` / `long` 全局序列化为字符串：

```java
// practice/config/JacksonConfig.java
module.addSerializer(Long.class, ToStringSerializer.instance);
module.addSerializer(Long.TYPE, ToStringSerializer.instance);
```

- 本模块确实存在**雪花 ID**：`question.id`、`exam_paper.id`、`practice_record.id` 都是 19 位（如 `2096765985265061890`），**超过 JS `Number.MAX_SAFE_INTEGER`（2^53 ≈ 9.007e15）**，不字符串化前端会丢精度。
- ⚠️ **不要照抄写字课的结论**。写字课（`course-service`）得出"id 用数字"是因为**它响应里没有超 2^53 的数**；`practice-service` 恰恰相反，且是全局配置。**两处别互相"对齐"。**
- 请求参数传字符串或数字都能被 Spring 转回 `Long`（`/csca/questions/2096765985525108738` 与 `?questionId=2096765985525108738` 等价），**响应一律字符串**。

### 0.5 错误码

🔴 **2026-10-13 拍板：本模块补一组 `CSCA_*` 业务码**（原方案「直接用字面量」已废弃）—— 取号段 **8001–8099**（7001–7099 已归写字课 / 拼音课的 `COURSE_*`，两模块互不冲突）。通用码（200 / 401 / 403 / 500）与 409 仍**复用 `ErrorCode`**：

| 业务码 | 值 | HTTP | 含义 | 触发场景 |
|---|---|---|---|---|
| `SUCCESS` | 200 | 200 | 成功 | — |
| `PARAM_ERROR` | 400 | 400 | 参数错误（兜底） | 未细分的参数问题 |
| `CSCA_SUBJECT_INVALID` | **8001** | 400 | 科目码非法 | `subjectTypeMapping` 不在 5 个原始值内（**含已取消的 `chinese`**，见 [3.2.2](#322-get-cscaquestions)） |
| `CSCA_LANGUAGE_INVALID` | **8002** | 400 | 语言版本非法 | `languageVersion` **未传（现为必填）** 或不在 `CSCALanguageVersion` 的 2 值内（`/csca/questions` 与 `POST /csca/records` 同口径） |
| `CSCA_TYPE_ID_INVALID` | **8003** | 400 | 题型码非法 | 🔵 **保留码**：题型自 2026-10-13 起**不再是** `/csca/questions` 的入参（不做按题型筛选，见 [4.4](#44-文档与实现的差异) 第 35 条），**当前无触发点**；号段预留给将来若重新开放题型入参 |
| `CSCA_SHUFFLE_SEED_REQUIRED` | **8004** | 400 | 乱序缺种子 | `shuffle=true` 但 `seed` 为空（本模块只有确定性乱序） |
| `CSCA_PARAM_OUT_OF_RANGE` | **8005** | 400 | 参数越界 | ① 分页越界（`pageSize > 100`、`page < 1`）；② `seed` 长度 > 64；③ **路径变量不是数字**（`/csca/questions/abc`） |
| `CSCA_QUESTION_NOT_FOUND` | **8006** | 404 | 题目不存在 | `questionId` 库中查不到，或不属于 CSCA（`exam_type≠2`）；HSK 的题被拿来从 CSCA 收藏也走这个 |
| `CSCA_RECORD_NOT_FOUND` | **8007** | 404 | 练习记录不存在 | `recordId` **未传（现为必填）** / 查不到 / 不属于当前用户 / 不是 CSCA 记录（**含 [3.2.2](#322-get-cscaquestions) 的题集参数 `recordId`**）。⚠️ 前端遇此码应走「重新建轮」分支 |
| `CSCA_NO_QUESTION_AVAILABLE` | **8008** | 404 | 该科目暂无未练题目 | 建轮时剩余未练 = 0 且未要求 `restart`（[3.2.1](#321-post-cscarecords) 第 3 条） |
| `UNAUTHORIZED` | 401 | 401 | 未登录 / Token 无效 | 题目类（`/csca/questions*`）/ 作答 / 收藏类接口未带或 Token 无效（**复用 `ErrorCode`**） |
| `FORBIDDEN` | 403 | 403 | 无权限 | `X-Client-Type` 非 `APP`（**复用 `ErrorCode`**） |
| `FAILED` | 500 | 500 | 服务端错误 | 未预期异常（**复用 `ErrorCode`**） |
| `RECORD_NOT_IN_PROGRESS` | 2004 | 409 | 记录不在进行中 | 非进行中记录仍保存答案（**复用**已有码） |
| `RECORD_VERSION_CONFLICT` | 2003 | 409 | 乐观锁冲突 | 记录版本冲突，请刷新后重试（**复用**已有码） |

> 🔴 **号段（2026-10-13 定）**：`CSCA_*` 占 **8001–8099**；`COURSE_*`（写字课 / 拼音课）占 7001–7099 —— 两模块**互不冲突**。
> ⚠️ **不再写裸字面量**：本文其余各处出现的 `400` / `404`（[3.2.2](#322-get-cscaquestions) / [3.3.3](#333-get-cscaquestionsquestionidsolution) / [3.6.1](#361-收藏favorite) / [3.2](#32-开始练习) 起各节 的业务逻辑）**一律按本表替换为对应 `CSCA_*` 码**；原用 `QUESTION_NOT_FOUND(2001)` 的写法也改走 `CSCA_QUESTION_NOT_FOUND(8006)`（[4.4](#44-文档与实现的差异) 第 4 条）。
> ⚠️ **响应体口径不变**：HTTP 状态码恒 `200`、业务码在 `code` 字段（同全站约定）；上表「HTTP」列只是**同时回写的状态码**，供网关 / 前端按 HTTP 语义兜底。
> ⚠️ **路径没匹配到任何接口**（Spring 兜底 404）**不属本模块业务码**，仍由全局兜底回固定文案「请求的资源不存在」。
> ✅ **代码已同步（2026-10-13）**：8 个 `CSCA_*` 枚举（8001–8008）**定义在 `practice-service` 的 `com.hsktreasure.practice.csca.support.CscaErrorCode`**（模块自有码表，**不放进 common 的 `ErrorCode`**，避免污染全站共用码；`ErrorCode` 内留指路注释），并带 `toException()` / `toException(String detail)` 便捷方法；`practice-service` 的 `csca` 包内各处 `BusinessException` 已改抛该枚举（仍由 `GlobalExceptionHandler` 统一处理）。见 [4.4](#44-文档与实现的差异) 第 30 条。

### 0.6 枚举与版本号

**判定 CSCA 试卷的唯一口径**（三个条件同时成立）：

```
exam_paper.exam_type = 2        -- 2 = CSCA（1 = HSK）
exam_paper.version   = 'CSCA'   -- 大纲版本，实测 31 张卷全部为 'CSCA'
exam_paper.deleted   = 0
```

> ⚠️ **`SharedPaperEligibility.isEligible` 现在只认 `exam_type = 1`**，CSCA 走它会被判"不合格"。CSCA **不修改**该类（它被 HSK 四条链路共用），而是新增 `csca/support/CscaPaperEligibility`，判据为 `deleted = 0 && exam_type = 2`。

**本模块不设「内容版本号」**（与课程 / 写字课不同）：

- 练习内容**每次实时读题库**：目录与题面都由 `exam_paper` / `question` 现场聚合，**服务端不下发 `dataVersion` 之类的版本号**，客户端也无需据此做缓存失效。⚠️ **唯一例外是"已答过的题"**：CSCA 在作答时**冻结题面快照**（见 [3](#3-接口详细设计) 开头），**已答过的题一律回快照**、不随题库改动而变
- ⚠️ `dataVersion` 是**课程 / 写字课**的口径（`course.data_version`）——**练习模块不需要**，本文所有接口的响应里都**没有该字段**
- 若客户端仍要缓存题面，**自行定失效策略**（短 TTL / 每次进页面重拉均可）

**「答案不进内容接口」是一条硬约束**（贯穿全文；🟡 **唯一例外 = 收藏 / 错题本两个复习类列表**，理由见下表下注）：

| 接口产出 | 含答案？ | 可缓存？ |
|---|---|---|
| 科目目录（`/csca/catalog`） | **否** | ✅ 客户端可自缓存（公共数据；服务端**不下发版本号**，失效策略自定） |
| 题面内容（`/csca/questions/{id}` / `/csca/questions` 里的题目对象） | **否** | ⚠️ **题面本身与用户无关、可按 `questionId` 缓存**；但 `/csca/questions` 的**列表响应是用户维度**（按 `recordId` 的题集切片），**不可做公共缓存**（CDN / 网关级），只能缓存在本机 ⚠️ 见下 |
| 单题答案与解析（`/questions/{id}/solution`） | **是** | ⚠️ 谨慎（见下） |
| **我的收藏 / 我的错题本列表**（`/csca/favorites` / `/csca/wrong-book`） | **是**（🟡 2026-10-19 起：带 `standardAnswer` / `standardAnswerLabels`，错题本再带 `userAnswer`；**仍不含 `analysis`**） | ❌ **不可缓存**：用户私有数据，且已带答案（[4.4](#44-文档与实现的差异) 第 68 条） |
| 作答 / 判分 / 进度 | **是**（用户相关） | ❌ 不可缓存，每次现拉 |

> 🟡 **2026-10-19 对上面这条硬约束开了一个口子**：「我的收藏 / 我的错题本」是**复习场景**，用户点进去就是要对答案——再让他逐个调 `/solution` 拉解析，等于把 N+1 次请求甩给客户端。故这两个**列表**改为直接带 `standardAnswer` / `standardAnswerLabels`（错题本另带 `userAnswer`）。**边界很硬**：① 只这两个列表，`/csca/questions*` 与 `/csca/catalog` **一个字段都没变**；② **不带 `analysis`**（解析体积大、仍是 `/solution` 的独家出口）；③ 这两个接口本来就是**强鉴权 + 不可缓存**的用户私有数据，不存在「公开缓存泄漏答案」的风险。

> ⚠️ **`/csca/questions*` 三个接口都需登录、且响应带用户维度**（[0.2](#02-鉴权与客户端类型)）：同一 URL 不同用户 / 不同 `recordId` 结果不同 → **服务端不得做公共缓存**；客户端能缓存的是**题面本身**（与用户无关），**不要**把「这一页有哪些题」当成可跨用户复用的缓存。
> ⚠️ `/questions/{id}/solution` 会带标准答案。**它现在也是强鉴权接口**（2026-10-13 起，见 [0.2](#02-鉴权与客户端类型)），**但仍不能被客户端当作"可长期缓存的内容"**：建议客户端**只缓存已作答过的题的解析**，或干脆不缓存。

### 0.7 与 HSK 练习链路的差异（为什么要单开一条链路）

CSCA 复用了 `practice-service` 的基础设施（`Result` / `BaseController` / `GlobalExceptionHandler` / `JacksonConfig`），但**不能套用 HSK 的目录链路**，原因逐条列在这里，避免后来人"照着 reading 抄"：

| # | 维度 | HSK 阅读 / 写作 / 口语 | CSCA | 后果 |
|---|---|---|---|---|
| 1 | 等级轴 | `level` 1–6 / 7-9 | **`level` 全为 `NULL`** | 无等级可筛；`practice_module_level_config.level` 是 `NOT NULL INT`，**CSCA 塞不进去** |
| 2 | 分类轴 | 无（等级即分类） | **科目码**（`question.subject_type_mapping`）+ **语言版本** | 目录要按「科目 × 语言」组织；科目归属在**题**上，不在卷上 |
| 3 | 目录配置 | `practice_paper_setting` / `practice_paper_structure` / `practice_part_setting` 四层 | **一行都没有**（实测：CSCA 的 `practice_paper_structure` = 0 行、`practice_paper_setting` = 0 行） | 目录**改为实时聚合** `exam_paper` + `question`，**不补配置行** |
| 4 | 题库标签 | `question.section_mapping` = `SEC_READ` / `SEC_LISTEN`…、`type_id_mapping` 有值 | **这两列全为 `NULL`**（1904 行）；⚠️ 但**同表的 `subject_type_mapping` 已补齐**（1904 行全有值，5 个科目码） | **不能用 `selectByPart(paperId, 'SEC_READ', sectionCode)`**，要新增按 `paper_id + section` 的取题 SQL；科目筛选则**直接用 `q.subject_type_mapping`**，不必再 join `exam_paper` |
| 5 | 题型 | 有稳定枚举（`QuestionType`） | `type_id` 是**中文原名**（`单选` / `多选` / `识解汉字`…**8 种**），`QuestionType` 里**没有这些值** | 新增 CSCA 局部题型映射 `CscaQuestionTypes`，**不动 `common` 的 `QuestionType`**；对外**只回映射值 `SINGLE` / `MULTI`**（**英文枚举码**；除库中原名「多选」外一律 `SINGLE`），库中 8 种原名不透出 |
| 6 | 例题 | 必须排除（`type_id_mapping='example_question'`） | **实测 0 行**（`number=0` 与 `section_title='例题'` 都为 0） | 仍保留防御性排除条件，但正常不触发 |
| 7 | 练习粒度 | 卷 → 部分 → 整部分作答 | **科目 → 单题**（不切部分、不整卷） | 少一层结构，`practice_part_setting` 完全不参与 |
| 8 | 题面布局 | `question.layout` 是**听力专用**（7 种值：`imageJudge` / `textJudge` / `imageChoice` / `imageMatch` / `textChoice` / `textChoice_shareAudio` / `passageGroup`） | CSCA **同一列另有 3 种值**（`textChoice` / `passageGroup` / `clozeGroup`，2026-10-12 补全 1904 行；其中 `textChoice` / `passageGroup` 沿用旧名） | 服务端**原样透传**（与听力一致，不做 `enum`）；**但 CSCA 不能套用听力那 7 种值的语义** —— 听力的 `passageGroup` 材料走 `question_shared_audio`，CSCA 的走 `question_group.passage`，不是同一套载体 |

---

### 0.8 与互动原型的对齐（v1.3）

**交互依据**：`CSCA练习原型_v1.3.html`（手机端 H5，驾考宝典式刷题）；**2026-10-13 起另有 `CSCA练习+错题本+收藏本.html`**（新增「我的」页：收藏夹 / 错题本 / 练习记录）。下面把「原型定了什么」→「本文怎么落」逐条对齐；**本节之外的一切，以原型为准**。

**原型页面结构**（已实现交互的部分）：

```
CSCA（顶部 考试 / 练习 两个 Tab，本模块只管「练习」）
 └─【练习 Tab】
     ① 选择科目：4 张卡 —— 中文 / 数学 / 物理 / 化学（与「考试」Tab 同 4 科）
          每卡展示「总题数 · 已练习 · 正确率」（未练显示 "-"）
     ② 练习语言：中文 / English（「中文」科目仅支持中文，English 置灰）
     ③ 开始练习
          └─【答题页】
               · 顶栏：返回 ｜ 答题模式·背题模式 ｜ 收藏 ｜ 答题卡
               · 题型徽标 + 会话内题号 + 题干
               · 选项列表（选中蓝 / 答对绿 / 答错红，答后锁定不可改）
               · 结果条（答案：X ／ 您选择：Y）
               · 试题详解 → 题目解析（原型已去掉「速记口诀」）
               · 底部：上一题 / 下一题（最后一题变「交卷」）
               · 答题卡抽屉：总题数 / 答对 / 答错 / 未答 + 6 列网格（对绿 / 错红 / ★收藏 / 当前）
          └─【完成页】正确率圆环 + 答对 / 答错 / 未答 + 退出练习 / 再来一轮

【我的】Tab（原型 v1.4 新增；本模块涉及「学习与测试」区）
     ├─ 收藏夹   ── 收藏列表（[3.6.1](#361-收藏favorite)）
     ├─ 错题本   ── 答错自动收录、可手动移出、可进复习页（[3.6.2](#362-错题本wrong-book)）
     ├─ 练习记录 ── 逐题作答明细；本模块不另设接口（由 [3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card) + [3.3.3 solution](#333-get-cscaquestionsquestionidsolution) 组合，统计看 [3.1.1 catalog](#311-get-cscacatalog)）
     └─ 模考记录 ── 属考试链路，本模块不涉及
```

**原型 → 本文的落点**

| 原型元素 | 本文落点 | 关键口径 |
|---|---|---|
| 4 个科目卡 | [3.1.1 `GET /csca/catalog`](#311-get-cscacatalog) 的 `subjects[]` | 科目以服务端清单为准（库中 5 个原始科目）；原型名「中文」= 库里「文科中文 + 理科中文」，**服务端不合并、两科各一张卡**（2026-10-13 定） |
| 科目卡「总题数 / 已练习 / 正确率」 | [3.1.1](#311-get-cscacatalog) 的 `subjects[]` 合计 / `languageStats[]` | 已练习按 **`question.id` 去重**（**只在同一语言内**去重；中 / 英卷是两套不同的题、**各记一次、不跨语言合并**，见 [4.3](#43-待确认事项) 第 12 条）、正确率 = 答对 ÷ 已练；**进度只算该科目「最新一轮」**（起新一轮即归零，见 [3.1.1](#311-get-cscacatalog) 业务逻辑第 3 条） |
| 练习语言 中文 / English | [3.1.1](#311-get-cscacatalog) 的 `languages` + `languageStats[]` | 数据驱动；**当前全库无 `english` 卷**，英文开关实际不可用（该语言题数为 0） |
| 开始练习（**整科**） | [3.2.1 `POST /csca/records`](#321-post-cscarecords) | 原型不选题量，默认练**整科**；🔴 **接口也不接收题量**（2026-10-13 收口，§4.4 第 39 条）；题序由 [3.2.2](#322-get-cscaquestions) 的 `shuffle` 开关控制（缺省自然序，可开乱序；**开则须带 `seed` 冻结题序**） |
| 答题 / 背题模式 | [3.3.3 solution](#333-get-cscaquestionsquestionidsolution) | **背题模式 = 未作答也能取答案** → solution **登录即可读**（2026-10-13 起随题目类接口强鉴权，但**不要求已作答**） |
| 收藏（★） | [3.6.1 收藏](#361-收藏favorite) | ✅ **落库**（2026-10-13 定）：新增 `csca_question_favorite`（2026-10-19 加 `csca_` 前缀），跨设备可取回；同错题本一样带 `source`（练习 / 考试）、`language_version`（语言快照）维度 —— [4.3](#43-待确认事项) 第 10 条 |
| **错题本**（答错自动收录 / 可移出 / 可复习） | [3.6.2 错题本](#362-错题本wrong-book) | ✅ **落库**（2026-10-13 定）：新增 `csca_question_wrong`（2026-10-19 加 `csca_` 前缀）；**答错收录、答对不自动移出**（2026-10-19 回归原型口径 —— 错题本「只进不出」，见 [4.4](#44-文档与实现的差异) 第 62 条）；带 `source`（练习 / 考试）、`language_version`（语言快照）维度 —— [4.3](#43-待确认事项) 第 15 条 |
| 答题卡抽屉 | [3.4.2 `GET …/answer-card`](#342-get-cscarecordsrecordidanswer-card) | 补 `unansweredCount` 与逐题 `favorite` |
| 交卷 / 完成页 | [3.5.1 `POST …/submit`](#351-post-cscarecordsrecordidsubmit) | 补 `unansweredCount`；正确率 = 答对 ÷ **已作答** |
| 再来一轮 | [3.2.1](#321-post-cscarecords) 的 `restart=true` | 作废本轮（`status→2`）、作答**一行不删**；新轮成为「最新一轮」→ **科目进度归零后重新累计**（[3.1.1](#311-get-cscacatalog) 业务逻辑第 3 条） |

> ⚠️ 原型里的**总题数（中文 320 / 数学 480 / 物理 360 / 化学 420）是演示规划值**，**不是库中真实题量**。真实题量见 [4.1](#41-枚举速查)（中文 1040 / 数学 432 / 物理 240 / 化学 192）。服务端一律回**实测题量**。
> ⚠️ 原型练习页多出的第 5 张卡「**教学**」是**原型自身的错误**（库中无此科目），本模块**不实现**，练习科目与「考试」Tab 一致为 4 科。

---

## 1. 用户操作流程与接口对照

### 1.1 页面流转

**与原型 v1.3 一致**：主流程是「选科目 → 选语言 → 开始练习」，**没有科目简介页、没有卷来源筛选**（本模块**不提供**这两个接口）。

```
CSCA（顶部 Tab：考试 | 练习；本模块只管「练习」）
 └─[练习] CSCA 练习
     ├─ 科目网格 + 每科分语言统计（进练习区一次取全）        ── GET /api/practice/csca/catalog
     │     每格：总题数 · 已练习 · 正确率（未练显示 "-"，按语言分项）
     ├─ 练习语言（中文 / English；由 languages 决定开关可用） （本地状态，服务端回 languages + languageStats）
     │
     └─ 点「开始练习」                                      ── POST /api/practice/csca/records
         ├─ 拉取本次题集（题面三字段 + 选项 + layout，无答案；题集由 recordId 定、建轮时已排除做过的）── GET  /api/practice/csca/questions?subjectTypeMapping=math&recordId={id}&page=1
         ├─ 逐题作答（答后即锁、即时回对错与解析）            ── PUT  /api/practice/csca/records/{id}/answers/{questionId}?immediate=true
         │     └─ 背题模式：不判分，直接取答案与解析          ── GET  /api/practice/csca/questions/{id}/solution
         ├─ 收藏 / 取消收藏                                 ── PUT/DELETE /api/practice/csca/favorites/{questionId}
         ├─ 答题卡（总/对/错/未答 + 逐题状态 + ★收藏）        ── GET  /api/practice/csca/records/{id}/answer-card
         ├─ 交卷 / 完成页（正确率 + 答对/答错/未答）          ── POST /api/practice/csca/records/{id}/submit
         │     └─ 再来一轮                                  ── POST /api/practice/csca/records  { restart: true }
         └─ 科目卡进度刷新（跨设备 / 下拉刷新）               ── GET  /api/practice/csca/catalog
```

> 📌 **两个参数口径**：① 原型前端的科目键是 `wk/sx/wl/hx`，本文对外用**可读科目码** —— **5 个原始值** `arts_chinese/science_chinese/math/physics/chemistry`（**不提供合并别名 `chinese`**，见 [4.1](#41-枚举速查)）；② 原型语言键是 `zh/en`，本文对外用 `chinese/english`（见 [0.3](#03-语言版本languageversion-与界面文案是两件事)）。前端做一对一映射即可。

> 📌 **「我的」页（原型 v1.4）**：**收藏夹**（[3.6.1](#361-收藏favorite)）/ **错题本**（[3.6.2](#362-错题本wrong-book)）/ **练习记录**三块。本模块提供前两组接口；**「练习记录」不另设接口**（逐题作答明细由 [3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card) + [3.3.3 solution](#333-get-cscaquestionsquestionidsolution) 组合，统计看 [3.1.1 catalog](#311-get-cscacatalog)）。


### 1.2 场景 → 接口对照表

| # | 原型里的位置 | 用户动作 | 接口 | 登录 | 可缓存 |
|---|---|---|---|---|---|
| 1 | （App 练习区）CSCA 入口卡片 + **5 个科目**（每科**按语言分项**）的总题数/已练习/正确率 | 进入练习区 / 下拉刷新 / **换设备打开** | `GET /csca/catalog` | 否（有 Token 才带统计） | ⚠️ 含用户统计 |
| 2 | 题集（题面三字段 `passage` / `content` / `group.passage` + 选项 + `layout`，**无答案**；**题集由 `recordId` 定**、建轮时已排除做过的） | 点「开始练习」/ 翻页 | `GET /csca/questions?subjectTypeMapping=math&recordId=…` | **是** | ❌（用户维度） |
| 3 | 单题详情（深链 / 重试） | 深链进入 | `GET /csca/questions/{questionId}` | **是** | ✅（内容本身） |
| 4 | 点「开始练习」 | 建会话 | `POST /csca/records` | **是** | — |
| 5 | **答题模式**：选完选项立即看到对错 + 解析 | 选选项 | `PUT /csca/records/{recordId}/answers/{questionId}?immediate=true` | **是** | — |
| 6 | **背题模式**：不判分，直接看答案 + 解析 | 切到背题模式 | `GET /csca/questions/{questionId}/solution` | **是** | ⚠️ 见 [0.6](#06-枚举与版本号) |
| 7 | 右上角 **★ 收藏 / 取消收藏** | 点星标 | `PUT` / `DELETE /csca/favorites/{questionId}` | **是** | — |
| 8 | **答题卡抽屉**（总/对/错/未答、★、当前） | 中途查看 | `GET /csca/records/{recordId}/answer-card` | **是** | ❌ |
| 9 | 最后一题点 **交卷** / 完成页 | 交卷 | `POST /csca/records/{recordId}/submit` | **是** | — |
| 10 | 完成页 **再来一轮** | 重练 | `POST /csca/records` `{restart:true}` | **是** | — |
| 11 | 错题回顾 / 看解析 | 点「查看解析」 | `GET /csca/questions/{questionId}/solution` | **是** | ⚠️ 见 [0.6](#06-枚举与版本号) |
| 12 | 断网期间作答、联网补传 | 网络恢复 | `POST /csca/records/{recordId}/answers/batch`（批量） | **是** | — |
| 13 | 我的 → **错题本**（科目 / 来源 / 错题时间筛选 / 时间升序降序） | 打开错题本 | `GET /csca/wrong-book` | **是** | ❌（用户维度） |
| 14 | 错题卡片右上「**移出**」 | 移出 | `DELETE /csca/wrong-book/{questionId}` | **是** | — |
| 15 | **错题复习页**选选项 | 复习作答 | `POST /csca/wrong-book/{questionId}/answer` | **是** | — |
| 16 | 答错**自动收录**（答对**不**自动移出） | （随作答自动） | 附随 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) / [3.3.2](#332-post-cscarecordsrecordidanswersbatch) / 复习作答 | **是** | — |

### 1.3 一次完整会话的调用时序

以「进入练习页 → 选数学 → 开始练习（整科）→ 答若干题 → 收藏 1 题 → 答题卡 → 交卷」为例：

```
①  GET /api/practice/csca/catalog                    → 入口卡片：languages + 5 科目（每科按语言分项的总题数/已练习/正确率）
    ②  写入 IndexedDB（key: csca-catalog）
③  POST /api/practice/csca/records                   → {subjectTypeMapping:"math", languageVersion:"chinese"}
                                                     → recordId=…, totalQuestions=432, status=1
④  GET /api/practice/csca/questions?subjectTypeMapping=math&languageVersion=chinese&recordId={recordId}&page=1&pageSize=20[&shuffle=true&seed={recordId}]
                                                     → 20 道题的题干 + 选项（不含 answer / analysis）
    ⑤  写入 IndexedDB（key: csca-questions-math-chinese-1）
⑥  PUT /api/practice/csca/records/{recordId}/answers/{questionId}?immediate=true
                                                     → {answered:1, isCorrect:1, standardAnswer:"B", analysis:"…"}
    ⑦  每题一次；答后该题锁定（前端不再允许改选）；离线则先落本地队列，联网后 ⑧ 补传
⑧  POST /api/practice/csca/records/{recordId}/answers/batch  → 批量幂等补传（离线场景）
⑨  PUT /api/practice/csca/favorites/{questionId}     → 收藏 1 题（答题卡出现 ★）
⑩  GET /api/practice/csca/records/{recordId}/answer-card  → 总 432 / 对 X / 错 Y / 未答 Z + 逐题状态
⑪  POST /api/practice/csca/records/{recordId}/submit  → 判分 + 生成报告 + 完成页数据（得分 / 正确率 / 答对 / 答错 / 未答）
```

**第二次进入**：重发 ① 拿最新目录（服务端每次实时聚合，**没有版本号可比**），进度走服务端。**点「再来一轮」**则重发 ③ 并带 `restart: true`。

> ⚠️ **开了乱序必须带 `seed`**：`shuffle=true` 时 `seed` **必填**，服务端用 `ORDER BY CRC32(CONCAT(q.id, seed))` 做**确定性乱序**，保证"同一会话多次翻页题序一致"。`seed` **建议直接用 `recordId`**（见 [3.2.1](#321-post-cscarecords)）。**缺 `seed` 直接 `400`** —— 本模块**不提供**"无种子的 `ORDER BY RAND()`"那种每次真随机的形态（它无法复现顺序，翻页会重复或漏题）。缺省关（自然序）时无需种子、天然一致。

### 1.4 离线与跨设备

| 场景 | 行为 |
|---|---|
| **离线进练习页 / 科目卡** | 命中 IndexedDB，**科目目录与已缓存的题面**可用（答案本就不在内容接口里，**离线时判分由「已缓存的解析」或联网后补判**）。⚠️ **「取题」必须联网**：`/csca/questions` 需登录且**必须带 `recordId`**（题集来自练习记录），离线取不到新题集，只能用本地已缓存的题面 |
| **离线刷题** | 作答写本地队列，**界面按已缓存解析自行标色**（或统一灰色、联网后回填对错）；联网后批量 `POST /csca/records/{recordId}/answers/batch` |
| **离线收藏** | ✅ **收藏落库**（2026-10-13 定）：离线可正常星标，联网后**排队补传** `PUT /csca/favorites/{questionId}`（幂等，见 [3.6.1](#361-收藏favorite)）。收藏**不参与判分**，补传失败不影响作答结果 |
| **多设备冲突** | 服务端按「`answer` 取最后写入（`last_modified_time` 最新）」合并，**先写的不丢**（同 HSK 阅读口径，见 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid)） |
| **内容更新后** | 服务端实时读题库，**未作答的题**每次取到即最新；**已答过的题回快照**、保持作答当时的版本（见 [3](#3-接口详细设计)）；客户端若自缓存，需**自定失效策略**（服务端不下发版本号） |
| **作答进度跨设备** | 服务端在 `practice_record` / `practice_answer`，由 [3.1.1 `GET /csca/catalog`](#311-get-cscacatalog) 的 `subjects[]` 汇总下发（原 `GET /csca/progress` 已裁撤，2026-10-13） |

---

## 2. 接口总览

### 2.1 端点清单

| # | 方法 | 路径（对外，含 `/api/practice` 前缀） | 用处 | 登录 | 缓存 | 响应量级（实测/估算） |
|---|---|---|---|---|---|---|
| 1 | `GET` | `/api/practice/csca/catalog` | 内容目录：**languages** + **5 科目**（每科按语言分项统计） | 否 | ⚠️ | < 3 KB |
| 2 | `GET` | `/api/practice/csca/questions` | 按科目取单题（分页；**乱序开关 `shuffle`**；**`recordId` 必填**、取该记录的固定题集） | **是** | ❌ | 20 题约 **7–9 KB** |
| 3 | `GET` | `/api/practice/csca/questions/{questionId}` | 单题详情（无答案） | **是** | ✅ | < 1 KB |
| 4 | `GET` | `/api/practice/csca/questions/{questionId}/solution` | 答案与解析（**背题模式 / 错题回顾**） | **是** | ⚠️ | < 2 KB |
| 5 | `POST` | `/api/practice/csca/records` | 开始一次练习（`restart` 即「再来一轮」） | **是** | — | < 1 KB |
| 6 | `GET` | `/api/practice/csca/records/{recordId}` | 练习态 | **是** | ❌ | < 1 KB |
| 7 | `PUT` | `/api/practice/csca/records/{recordId}/answers/{questionId}` | 作答（幂等，可即时判分） | **是** | — | < 1 KB |
| 8 | `GET` | `/api/practice/csca/records/{recordId}/answer-card` | 答题卡（总/对/错/未答 + ★） | **是** | ❌ | 432 题约 **30 KB** |
| 9 | `POST` | `/api/practice/csca/records/{recordId}/submit` | 交卷判分（含完成页全部数字） | **是** | — | < 1 KB |
| 10 | `POST` | `/api/practice/csca/records/{recordId}/answers/batch` | 批量上报作答（离线补传） | **是** | — | 200 条上限约 12 KB |
| **11** | `PUT` | `/api/practice/csca/favorites/{questionId}` | **收藏一题**（幂等） | **是** | — | < 1 KB |
| **12** | `DELETE` | `/api/practice/csca/favorites/{questionId}` | **取消收藏**（幂等） | **是** | — | < 1 KB |
| **13** | `GET` | `/api/practice/csca/favorites` | **收藏列表**（我的收藏；科目 / 来源 / 语言 / **收藏时间**筛选） | **是** | ❌ | 20 题约 **7–9 KB** |
| **14** | `GET` | `/api/practice/csca/wrong-book` | **错题本列表**（我的错题） | **是** | ❌ | 20 题约 **7–9 KB** |
| **15** | `DELETE` | `/api/practice/csca/wrong-book/{questionId}` | **移出错题本**（幂等） | **是** | — | < 1 KB |
| **16** | `POST` | `/api/practice/csca/wrong-book/{questionId}/answer` | **错题复习作答**（判分 + 同步错题本） | **是** | — | < 2 KB |

> 📌 **11–13 是收藏接口**、**14–16 是错题本接口**（均 2026-10-13 定）。两组支撑表是**并列姊妹表**：`csca_question_favorite` / `csca_question_wrong`（均为本模块**新增的业务表**，2026-10-19 加 `csca_` 前缀，DDL 见 [3.6.1](#361-收藏favorite) 业务逻辑第 5 条 / [3.6.2](#362-错题本wrong-book) 业务逻辑第 9 条）。⚠️ 别与 `practice_record.question_ids` 混淆：那是**加列**、不是新表。

> 📌 **「缓存」列口径**：✅ = 内容本身（**不含答案**），客户端**可自行缓存**；⚠️ = 含答案或需谨慎；❌ = **用户相关数据**（同一 URL 不同用户结果不同），**不可缓存**（含公共缓存）。**服务端不下发版本号**（见 [0.6](#06-枚举与版本号)），缓存失效策略由客户端自定。

> **量级依据（测试库实测，非估算）**
>
> | 项 | 实测值 |
> |---|---|
> | CSCA 卷总数 | **31**（TEST 与 PROD 一致） |
> | CSCA 题目总数 | **1904** |
> | 单题 `passage`（题干）字符数 | 平均 **16.7–36.3**（理科中文最短、数学最长），**最大 188** |
> | 单题 `option_content`（JSON）字符数 | 平均 **56.2–115.1**，**最大 318** |
> | 选项个数分布 | **4 个 1603 题 / 5 个 150 题 / 6 个 150 题 / 3 个 1 题**（⚠️ 选项数**不固定**） |
> | `analysis`（解析） | **1904 题全部非空**，平均 **88.7** 字符、**最大 1088** |
> | `question_group.passage`（共材料段，75 行） | 平均 **202** 字符、**最大 548** |
> | 单卷题量 | 数学 / 物理 / 化学 **48** 题；文科中文 / 理科中文 **80** 题 |
> | 单卷满分 | 数学 / 物理 / 化学 **99.84**（48 × 2.08）；文科 / 理科中文 **100.00**（80 × 1.25） |
> | 科目题量（库中原始口径） | 数学 **432** / 文科中文 **640** / 理科中文 **400** / 物理 **240** / 化学 **192** |
> | 科目题量（**若把文/理中文并为「中文」**） | 中文 **1040**（=文科中文 640 + 理科中文 400）/ 数学 432 / 物理 240 / 化学 192（合计 **1904**） |
>
> **据此估算响应体量**（按"题干 + 选项 + 字段名 + 19 位 id"约 350–450 B/题）：
> 20 题约 **7–9 KB**；数学一科 432 题全量约 **170 KB**、中文一科 1040 题约 **400 KB**。
> ⚠️ 因此 `/csca/questions` **必须分页**（默认 `pageSize=20`，上限 100），**不允许 `pageSize=0`（全量）**。

### 2.2 端点归属

| 服务内路径前缀 | 对外路径 | Controller | 归属包 | 说明 |
|---|---|---|---|---|
| `/csca/catalog*` | `/api/practice/csca/catalog*` | `CscaCatalogController` | `csca` | 进入与目录 |
| `/csca/questions*` | `/api/practice/csca/questions*` | `CscaCatalogController` | `csca` | 开始练习（取题） |
| `/csca/records*` | `/api/practice/csca/records*` | `CscaRecordController` | `csca` | 开始练习 / 逐题作答 / 练习态与答题卡 / 交卷（含**离线批量补传** `/answers/batch`，2026-10-13 并入；原 `/csca/progress/report` 已迁走） |
| `/csca/favorites*` | `/api/practice/csca/favorites*` | `CscaFavoriteController` | `csca` | 收藏与错题本（见 [3.6.1](#361-收藏favorite)） |
| `/csca/wrong-book*` | `/api/practice/csca/wrong-book*` | `CscaWrongBookController` | `csca` | 收藏与错题本（见 [3.6.2](#362-错题本wrong-book)） |

> **为什么服务内路径不带 `/api/practice`**：网关 `application-{env}.yml` 里 `practice-service` 路由配了 `Path=/api/practice/**` + **`StripPrefix=2`**，`/api/practice/csca/questions` 到服务内就是 `/csca/questions`。写 Controller 时按**服务内路径**写 `@RequestMapping("/csca/questions")`。

---

## 3. 接口详细设计

> 每节固定七段：**接口用处 / 入参 / 返回 JSON / 业务逻辑 / 三层逻辑 / 涉及表 / 数据流向**。
> 返回示例均为**测试库 `xuexitest` 真实数据**（`exam_paper.exam_type = 2`）。

> **落库策略（本模块的核心设计决策）**：**作答链路不新增业务表**，复用 `practice_record` / `practice_answer` / `practice_report`；⚠️ **「改表」只有一次** = 给 `practice_record` 加一列 `question_ids`（本次题集，2026-10-13 定，见 [3.2.1](#321-post-cscarecords) 第 4 条）。
> 📌 **另有新增的两张业务表**（**与作答链路无关**）：收藏 `csca_question_favorite`（[3.6.1](#361-收藏favorite)）/ 错题本 `csca_question_wrong`（[3.6.2](#362-错题本wrong-book)）—— 两者是**并列姊妹表**（2026-10-19 加 `csca_` 前缀），DDL 见各自「业务逻辑」末条。
> 因为这三张表是为"卷 × 部分（structure）"设计的，而 CSCA 是"科目 × 单题"，所以约定：
>
> | 字段 | HSK 语义 | **CSCA 约定** |
> |---|---|---|
> | `practice_record.paper_id` | 真实卷 id | **`0`（哨兵）** —— CSCA 一次练习可跨多卷，单值表达不了，用 0 表示"不分卷" |
> | `practice_record.structure_id` | `practice_paper_structure.id`（真实行） | **由 `(科目, 语言版本)` 计算的稳定 ID**（号段 `6e18`），**库里没有对应的 structure 行**。计算式见 [4.1](#41-枚举速查) |
> | `practice_record.section_mapping` | `SEC_READ` / `SEC_LISTEN`… | **恒为 `'SEC_CSCA'`**（需在 `PracticeSections` 里新增常量） |
> | `practice_record.section` | 部分编码 | **科目码**（`math` / `physics` / …） |
> | 🆕 **`practice_record.question_ids`** | **无此列**（HSK 用 `practice_paper_structure` 固定题集） | **本次题集**：自然序 `question.id` 数组（JSON）—— 建轮时**一次算定**，之后**固定不变**（[3.2.1](#321-post-cscarecords) 第 4 条）。⚠️ **新增列**，HSK 行为 `NULL` |
> | `practice_answer.section_mapping` | 同上 | 恒为 `'SEC_CSCA'` |
> | **`practice_answer.question_snapshot` 等 5 个快照列** | 冻结题面 | ✅ **全写**（与 HSK 听力 / 阅读同口径）—— `question_snapshot` / `group_snapshot` / `option_snapshot` / `standard_answer_snapshot` / `analysis_snapshot`，见下 |
>
> **冻结策略选择：CSCA 冻题面（与 HSK 听力 / 阅读同口径）。** ⚠️ **2026-10-13 由「不冻结」改为「冻结」**（登记见 [4.4](#44-文档与实现的差异) 第 25 条）：
> ① **作答时**把**题面 / 材料 / 选项 / 标准答案 / 解析**一起写进 `practice_answer` 的 5 个快照列（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 3 条）—— 这 5 列**早已存在**（HSK 在用），**不改表**；
> ② **读时「已答过的题一律回快照」**：同一道题答过之后，复习 / 回顾取到的题面、选项、材料都是**作答当时那一版**，题库后来怎么改都不影响（口径见 [3.2.2](#322-get-cscaquestions) 业务逻辑第 5 条）；
> ③ **没做过的题仍实时读 `question`** —— 进行中的新题永远是题库最新版，题库勘误（[4.2](#42-答案归一化cscaanswernormalizer)）对**没做过的题**依然即时生效；
> ④ **唯一例外：[3.3.3 `GET /csca/questions/{id}/solution`](#333-get-cscaquestionsquestionidsolution) 不读快照**（它没有 `recordId` 上下文）—— 要看「作答当时」的标准答案 / 解析，用 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 的 `immediate=true` 返回（走快照）。
> **代价**：① `practice_answer` 行变大（多 5 列；单题题面 < 1 KB，实测可接受）；② **题库纠错不追溯已答过题的判分** —— 判分基准（`standard_answer_snapshot`）随题面一起冻结，见 [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 2 条。

---

### 3.1 进入与目录

> 📌 **科目进度统计已并入 [3.1.1 `GET /csca/catalog`](#311-get-cscacatalog)**：原 `GET /csca/progress`（科目进度明细）与目录接口的科目卡**功能重复**，已于 2026-10-13 **裁撤**（见 [4.4](#44-文档与实现的差异) 第 23 条）—— 本模块**不另设科目进度接口**。作答 / 答题卡 / 交卷见 [3.3](#33-逐题作答) / [3.4](#34-练习态与答题卡) / [3.5](#35-交卷)，离线补传见 [3.3.2](#332-post-cscarecordsrecordidanswersbatch)。

#### 3.1.1 GET /csca/catalog

##### 接口用处

CSCA 练习的**首页入口卡片**，同时也是**唯一的内容目录接口**（本模块不另设科目目录接口）。一次带回三层信息：

1. **顶层 `languages`**：库中实际存在的 `language_version` 列表（前端「中文 / English」开关的数据源，**也是 `/csca/questions` 取题时 `languageVersion` 的合法取值**）。
2. **`subjects[]`**：按库中原始科目铺开的卡片，每科带**合计**题量与进度（**进度 = 该科目「最新一轮」练习**，起新一轮即归零 —— 见业务逻辑第 3 条）。
3. **每科的 `languageStats[]`**：把该科的**中文题、英文题分开统计**（各自的总题数 / 已练习数 / 正确率 / 末次练习时间），供卡片内语言开关切换后直接读取。前端据此在入口处就能铺开"各科目练到哪了"，不必再为每个科目单独发请求。

> 📌 **不返回 `moduleCode` / `moduleName`**：模块标识与模块名是**前端静态文案**（App 里写死的「CSCA 练习」），与用户数据无关，服务端不必下发、也无从多语言化。
> 📌 **本模块不另设「科目目录」接口**：科目、题量、语言、进度全在这里一次给全，故原 `GET /csca/subjects` **已裁撤**（功能与本接口重复）。


##### 入参

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `X-Client-Type` / Token | Header | String | 否 | 带了才回**练习统计**（`subjects[]` 的合计与 `languageStats[]` 的分语言：`practicedQuestions` / `correctCount` / `accuracyRate` / `lastPracticedTime`）；不带则这些字段为 `0` / `null`（`languages` / `subjects` / `languageStats` 的**结构仍在** —— 题数是公共数据，未登录也要看得到） |

##### 返回 JSON

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "version": "CSCA",
    "languages": ["chinese", "english"],
    "subjectCount": 5,
    "paperCount": 31,
    "questionCount": 1904,
    "subjects": [
      {
        "subjectTypeMapping": "arts_chinese",
        "subjectType": "文科中文",
        "paperCount": 8,
        "questionCount": 640,
        "practicedQuestions": 96,
        "correctCount": 78,
        "accuracyRate": 81.25,
        "lastPracticedTime": "1785394374000",
        "languageStats": [
          { "languageVersion": "chinese", "paperCount": 8, "questionCount": 640, "practicedQuestions": 96, "correctCount": 78, "accuracyRate": 81.25, "lastPracticedTime": "1785394374000" },
          { "languageVersion": "english", "paperCount": 0, "questionCount": 0, "practicedQuestions": 0, "correctCount": 0, "accuracyRate": 0, "lastPracticedTime": null }
        ]
      },
      {
        "subjectTypeMapping": "science_chinese",
        "subjectType": "理科中文",
        "paperCount": 5,
        "questionCount": 400,
        "practicedQuestions": 32,
        "correctCount": 26,
        "accuracyRate": 81.25,
        "lastPracticedTime": "1785394100000",
        "languageStats": [
          { "languageVersion": "chinese", "paperCount": 5, "questionCount": 400, "practicedQuestions": 32, "correctCount": 26, "accuracyRate": 81.25, "lastPracticedTime": "1785394100000" },
          { "languageVersion": "english", "paperCount": 0, "questionCount": 0, "practicedQuestions": 0, "correctCount": 0, "accuracyRate": 0, "lastPracticedTime": null }
        ]
      },
      {
        "subjectTypeMapping": "math",
        "subjectType": "数学",
        "paperCount": 9,
        "questionCount": 432,
        "practicedQuestions": 0,
        "correctCount": 0,
        "accuracyRate": 0,
        "lastPracticedTime": null,
        "languageStats": [
          { "languageVersion": "chinese", "paperCount": 9, "questionCount": 432, "practicedQuestions": 0, "correctCount": 0, "accuracyRate": 0, "lastPracticedTime": null },
          { "languageVersion": "english", "paperCount": 0, "questionCount": 0, "practicedQuestions": 0, "correctCount": 0, "accuracyRate": 0, "lastPracticedTime": null }
        ]
      },
      {
        "subjectTypeMapping": "physics",
        "subjectType": "物理",
        "paperCount": 5,
        "questionCount": 240,
        "practicedQuestions": 0,
        "correctCount": 0,
        "accuracyRate": 0,
        "lastPracticedTime": null,
        "languageStats": [
          { "languageVersion": "chinese", "paperCount": 5, "questionCount": 240, "practicedQuestions": 0, "correctCount": 0, "accuracyRate": 0, "lastPracticedTime": null },
          { "languageVersion": "english", "paperCount": 0, "questionCount": 0, "practicedQuestions": 0, "correctCount": 0, "accuracyRate": 0, "lastPracticedTime": null }
        ]
      },
      {
        "subjectTypeMapping": "chemistry",
        "subjectType": "化学",
        "paperCount": 4,
        "questionCount": 192,
        "practicedQuestions": 0,
        "correctCount": 0,
        "accuracyRate": 0,
        "lastPracticedTime": null,
        "languageStats": [
          { "languageVersion": "chinese", "paperCount": 4, "questionCount": 192, "practicedQuestions": 0, "correctCount": 0, "accuracyRate": 0, "lastPracticedTime": null },
          { "languageVersion": "english", "paperCount": 0, "questionCount": 0, "practicedQuestions": 0, "correctCount": 0, "accuracyRate": 0, "lastPracticedTime": null }
        ]
      }
    ]
  }
}
```

- `languages`（**顶层**，`string[]`）：库中 CSCA 卷出现过的 `language_version` 去重列表，**顺序 `chinese` 在前**。它是前端「中文 / English」开关的数据源，**也是 [3.2.2 `/csca/questions`](#322-get-cscaquestions) 取题参数 `languageVersion` 的合法取值集合**。⚠️ **实测当前库中只有中文卷，实际只会返回 `["chinese"]`**——示例里的 `english` 仅演示英文卷导入后的形态（见 [4.3](#43-待确认事项) 第 9 条）。
- `subjects` **恒为 5 项**（库中原始科目，见业务逻辑第 1 条），**顺序固定**：文科中文 → 理科中文 → 数学 → 物理 → 化学（由 `CscaSubjects` 定义，不随题量变化）。
- 每个科目的**顶层统计字段**（`paperCount` / `questionCount` / `practicedQuestions` / `correctCount` / `accuracyRate` / `lastPracticedTime`）= 该科目**各语言合计**；**`languageStats[]`** 才是**中文题、英文题分开**的口径，**与顶层 `languages` 一一对齐**（顶层列几种语言，每科的 `languageStats` 就有几条；某语言无题则整条补 `0` / `null`）。
- 未登录 / 零练习时：`practicedQuestions` / `correctCount` / `accuracyRate` 为 `0`、`lastPracticedTime` 为 `null`（前端显示 `-`）；**`paperCount` / `questionCount` 照常返回**。⚠️ **该科目尚无任何记录、或最新一轮刚开还没作答时，同样是这一组 `0` / `null`** —— 进度只算「最新一轮」（业务逻辑第 3 条）。
- `accuracyRate` = `correctCount / practicedQuestions × 100`，保留 2 位；`practicedQuestions = 0` 时回 `0`（**分母是"已练去重题数"，不是全部题数**；去重键 = `question.id`，**跨语言不合并** —— 中 / 英是两套卷）。

##### 业务逻辑

1. **科目维度 = 库中 5 个原始科目**（`question.subject_type_mapping` 原样，**不做文理归并**）：`arts_chinese`（文科中文）/ `science_chinese`（理科中文）/ `math` / `physics` / `chemistry`。`subjectCount` = 聚合结果行数（**实测 5**，不写死枚举大小）。
2. **语言维度 = `exam_paper.language_version`**：
   - 顶层 `languages` = 本模块卷出现过的 `language_version` **去重列表**（顺序 `chinese` 在前），实测 `["chinese"]`。前端据此决定「中文 / English」开关是否可用。
   - 每科的 `languageStats[]` **按顶层 `languages` 逐项铺开**（不是"有才出现"）：某语言无题则整条补 `0` / `null`，保证前端按 `languages[i]` 取数不越界。**这就是"每个科目的中文题和英文题分开"的落点。**
   - 科目**顶层**统计字段 = `languageStats` 各语言的**合计**（求和的求和）。
3. **两次聚合、两次对齐（科目 × 语言）**：
   - **题数（分母）**：`question ⋈ exam_paper` 按 **`subject_type_mapping` + `language_version`** 双键分组，`COUNT(q.id)` / `COUNT(DISTINCT q.paper_id)`；科目内按语言求和得合计，顶层再对 5 科求和。
   - **进度（分子）**：`practice_answer`（`section_mapping='SEC_CSCA'`、`user_id=?`）**每题取最后一次作答**再按 `question_id` 去重计数（🔴 **去重只在同一 `language_version` 内**：中文卷与英文卷是**两套不同的题**（不同 `question.id`），**同一考点在中 / 英各算一次、不合并** —— 2026-10-13 定，见 [4.3](#43-待确认事项) 第 12 条）；**语言维度由 `question_id` 回连 `question → exam_paper.language_version` 取得**（作答表本身无语言列）。🔴 **统计范围只含该科目「最新一轮」记录**：先由 `practice_record` 按 `section` 分组取 `MAX(id)`（雪花 id 单调 = 最后开的那一轮），再只统计**归属该记录**的作答行 —— 起新一轮即自动归零，无需删任何历史数据。
   - 两个结果都按 **科目码 + 语言** 左连接（题数为骨架）：还没人练的科目/语言补 `0` —— **不因"没练过"就从 `subjects` / `languageStats` 里消失**。
   > ⚠️ **进度分语言要回连一张表**：`practice_answer` 只存 `section_mapping + section + question_id`，**没有语言列**，所以 `languageStats[].practicedQuestions` 需 `JOIN question ON question_id` 再 `JOIN exam_paper` 取 `language_version`。当前只有中文卷时它与科目合计恒等；若嫌这次 join 重，可先只给科目级进度、`languageStats` 内的进度复用合计（**仅中文卷下结果一致**），导入英文卷前必须补上回连。
4. `subjectType`（中文名）**不查库**：由 `csca/support/CscaSubjects` 按 mapping 反查（code ↔ 中文名的唯一真源）；**服务端只回中文原名**，界面文案多语言由前端处理（本模块不解析 `Accept-Language`，见 [4.3](#43-待确认事项) 第 5 条）。
5. **题数为 0 时**：`questionCount = 0`，前端据此隐藏卡片（**不报 404** —— 目录接口"没有内容"是正常状态，与 `id 查不到` 不同）。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaCatalogController#catalog(HttpServletRequest request, String clientType)` | 尝试取（非强制）userId；调 Service（**不解析 `Accept-Language`**） |
| Service | `CscaCatalogService#catalog(Long userId)` | 题数聚合（科目 × 语言）+ 进度聚合 + 科目/语言两层对齐 + 语言列表 + 概要求和 |
| Mapper | `csca/mapper/CscaQuestionMapper#selectSubjectStats` / `CscaAnswerMapper#selectProgressBySubject` | 题数 / 进度两个聚合（**均按 科目 × 语言**） |
| 支撑 | `csca/support/CscaSubjects` | 库中 5 科目（mapping ↔ 中文名 + 固定顺序）+ 语言排序（`chinese` 在前） |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `question` | SELECT（聚合） | `id` / `subject_type_mapping` / `paper_id` / `deleted` |
| `exam_paper` | SELECT | `id` / `exam_type` / `version` / **`language_version`** / `deleted`（限定范围 + **语言分组维度**） |
| `practice_answer` | SELECT（聚合） | `user_id` / `section_mapping` / `section` / `question_id` / `is_correct` / `last_modified_time` / **`practice_record_id`**（**只统计「最新一轮」**，见业务逻辑第 3 条；语言由 `question_id` 回连取得） |
| `practice_record` | SELECT（子查询） | `id` / `user_id` / `section_mapping` / `section` / `deleted` —— 按 `section` 分组取 `MAX(id)` = 该科目「最新一轮」的记录 id |

##### 数据流向

**① 入参 → ② 查库 → ③ 加工 → ④ 组装**

```
① 入参    可选 Token ──→ userId（本模块不解析 Accept-Language）

② 查库    question ⋈ exam_paper(exam_type=2, version='CSCA')
            ──GROUP BY q.subject_type_mapping, p.language_version──→ 科目×语言的 paperCount / questionCount
          practice_record(user_id=?, section_mapping='SEC_CSCA', deleted=0)
            ──GROUP BY section 取 MAX(id)──→ 各科「最新一轮」的记录 id
          practice_answer(section_mapping='SEC_CSCA', practice_record_id ∈ 最新一轮)（有 userId 时）
            ⋈ question ⋈ exam_paper（取 language_version）
            ──GROUP BY section, language_version（每题先取末次作答）──→ 各科×各语言 已练 / 答对 / 末次时间

③ 加工    languages = 步骤②题数结果里的 language_version 去重（chinese 在前）
          两结果按 科目×语言 左连接（题数为骨架，未练补 0）；科目内按语言求和得合计
          subjectCount = 科目条数（5）；顶层 paperCount / questionCount = 各科求和
          subjectType 中文名由 CscaSubjects 反查（不查库）

④ 组装    CscaCatalogResponse { version, languages[], subjectCount, paperCount, questionCount, subjects[] }
```

**关键 SQL**

```sql
-- ① 题数 + 卷数：按「科目 × 语言」双键分组（语言来自卷，科目来自题）
SELECT q.subject_type_mapping     AS subject_type_mapping,
       p.language_version         AS language_version,
       COUNT(DISTINCT q.paper_id) AS paper_count,
       COUNT(q.id)                AS question_count
FROM question q
JOIN exam_paper p ON p.id = q.paper_id AND p.deleted = 0
WHERE q.deleted = 0
  AND p.exam_type = 2
  AND p.version = 'CSCA'
GROUP BY q.subject_type_mapping, p.language_version;

-- ② 进度：先定位各科「最新一轮」，再每题取最后一次作答；语言由 question_id 回连 exam_paper 取得
-- latest = 该用户每个科目「最后开的那一轮」（雪花 id 单调递增 → MAX(id) 即最新）
WITH latest AS (
    SELECT r.section, MAX(r.id) AS record_id
    FROM practice_record r
    WHERE r.user_id = ? AND r.section_mapping = 'SEC_CSCA' AND r.deleted = 0
    GROUP BY r.section
)
SELECT t.section                  AS subject_code,
       p.language_version         AS language_version,
       COUNT(*)                   AS practiced_questions,
       SUM(t.is_correct = 1)      AS correct_count,
       MAX(t.last_modified_time)  AS last_practiced_time
FROM (
    SELECT a.id, a.section, a.question_id, a.is_correct, a.last_modified_time,
           ROW_NUMBER() OVER (PARTITION BY a.section, a.question_id
                              ORDER BY a.last_modified_time DESC, a.id DESC) AS rn
    FROM practice_answer a
    JOIN latest l ON l.record_id = a.practice_record_id   -- 只算「最新一轮」
    WHERE a.user_id = ? AND a.section_mapping = 'SEC_CSCA' AND a.deleted = 0
) t
JOIN question q   ON q.id = t.question_id
JOIN exam_paper p ON p.id = q.paper_id
WHERE t.rn = 1
GROUP BY t.section, p.language_version;
```

> ⚠️ **主分组键 = 题上的 `question.subject_type_mapping` + 卷上的 `exam_paper.language_version`**：科目列已补齐（CSCA **1904 行全部有值**，共 5 个值）→ **科目归属落在题上**；语言归属只能在卷上 → 故仍需 join `exam_paper`（既限定 CSCA 范围，也提供语言）。中文名 `subjectType` 由 `CscaSubjects` 反查。
> ⚠️ **`subjectCount` 取聚合结果行数（实测 5）、`languages` 取语言去重结果（实测 `["chinese"]`），两者都不要写死**：将来新增科目/语言应能自动长出卡片；导入英文卷后 `languageStats[]` 要按新的 `languages` 补齐条目。
> ⚠️ **`practice_answer` 必须带 `section_mapping = 'SEC_CSCA'`**：该表混着 HSK 的 6300+ 行，只按 `user_id` 查会把 HSK 的进度算进 CSCA。
> ⚠️ **`accuracyRate` 的分母是"已练去重题数"**（不是答案行数、也不是科目总题数），`practicedQuestions = 0` 时回 `0` —— 原 `GET /csca/progress`（2026-10-13 已裁撤）与本接口**完全同一套口径**，科目进度统一由本接口下发。
> 🔴 **进度是「最新一轮」口径（2026-10-13 定）**：只统计该科目**最后开的那一轮**记录下的作答。**由此「重做一轮」天然等价于「进度清零后重新累计」**（[3.2.1](#321-post-cscarecords) 的 `restart=true` 建新轮 → 新轮 id 最大 → 旧轮立即退出统计），**全程不删任何 `practice_answer`**。
> 🔴 **分母恒为科目总题数（2026-10-13 拍板）**：卡片进度 = `practicedQuestions / questionCount`，`questionCount` 是**题库维度**（按 `subject_type_mapping` + `language_version` 现算），**与轮次无关** —— 建轮即练整科（2026-10-13 起入参 `questionCount` 已删，§4.4 第 39 条），所以「练完一轮 = 练完整科 = 进度 100%」（进度条算法同业务逻辑第 3 条）。

---

### 3.2 开始练习

#### 3.2.1 POST /csca/records

##### 接口用处

**开始一次 CSCA 练习**（对应原型「开始练习」按钮），创建 `practice_record`，确定本次的**题目范围**，返回记录摘要（前端可拿 `recordId` 当 [3.2.2](#322-get-cscaquestions) 乱序的 `seed`）。`restart=true` 即原型完成页的**「再来一轮」**：旧轮作废但**作答一行不删**；新轮成为该科目「**最新一轮**」→ **科目进度归零、随新一轮重新累计**（进度口径见 [3.1.1](#311-get-cscacatalog) 业务逻辑第 3 条）。

> 📌 **原型的「开始练习」不选题量**——它默认**练整个科目**。本接口也**不接收题量**（🔴 2026-10-13 收口：入参 `questionCount` **已删除**，见 [4.4](#44-文档与实现的差异) 第 39 条）—— 题集由服务端**一次算定**（剩余未练 / `restart=true` 时全量），客户端看到的就是全部。**本接口不管题序**：乱序与否由 [3.2.2](#322-get-cscaquestions) 的 `shuffle` 开关决定。
> ⚠️ **「整科」不等于"全科题都出"**：本次题集**默认已排除该用户练过的题**（去重口径见本文业务逻辑第 3 条），所以 `totalQuestions` 是**剩余未练题数**，不一定是该科目的总题量。

##### 入参

```json
{
  "subjectTypeMapping": "math",
  "languageVersion": "chinese",
  "restart": false,
  "idempotencyKey": "app-4f2c…-1712"
}
```

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `subjectTypeMapping` | Body | String | **是** | 科目码，5 个原始值 `arts_chinese` / `science_chinese` / `math` / `physics` / `chemistry`（**只有这 5 个值**，无合并别名）；非法 → `400` / `CSCA_SUBJECT_INVALID` |
| `languageVersion` | Body | String | **是** | **必填、无缺省**（🔴 2026-10-13 收口，§4.4 第 39 条；与 [3.2.2](#322-get-cscaquestions) **同口径**）；只认 `CSCALanguageVersion` 的 2 值（`chinese` / `english`），**未传 / 非法值 → `400` / `CSCA_LANGUAGE_INVALID`** |
| `restart` | Body | Boolean | 否 | `false`（缺省）：有进行中的记录**直接返回该记录**；`true`（= **再来一轮**）：弃旧另起。⚠️ 它只管「**要不要弃旧**」，与响应里的 `reused`（服务端**实际有没有复用**已有记录）**不是互反关系**—— 四种组合见下方返回说明的真值表 |
| `idempotencyKey` | Body | String | 否 | 客户端生成，防重复建记录（断网重试场景）；长度 ≤ 128（超长 → `400` / `CSCA_PARAM_OUT_OF_RANGE`） |

> 🔴 **原入参 `questionCount` 已删除**（2026-10-13，§4.4 第 39 条）：建轮**不接收题量**，题集恒为「该科目剩余未练（`restart=true` 时全量）」的**全部**。原「`1–200` 取前 N 题」的口子一并取消 —— 一个诉求一个入口，避免"建出来的题集"与"客户端以为的题量"两处口径。

##### 返回 JSON

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": "2097000000000000001",
    "subjectCode": "math",
    "languageVersion": "chinese",
    "practiceName": "CSCA · 数学",
    "status": 1,
    "totalQuestions": 432,
    "answeredCount": 0,
    "reused": false,
    "startTime": "1785394374000"
  }
}
```

- `reused` 回答的是「**服务端这次有没有把一条已存在的记录直接还给你**」，而入参 `restart` 回答的是「**你要不要弃掉旧记录、另开一条**」——两者是**两个不同的轴**，**不是互反关系**（`reused ≠ !restart`）。组合见下表：

| `restart`（入参） | 场景 | 服务端行为 | `reused`（响应） |
|---|---|---|---|
| `false`（缺省） | **首次开始** | 无进行中记录 → 新建 | `false` |
| `false`（缺省） | **继续练习** | 命中进行中记录 → 直接返回它 | `true` |
| `true` | **再来一轮** | 旧轮 `status → 2`、另起新轮 | `false` |
| `true` | **断网重试**（同 `idempotencyKey`） | 幂等命中 → 返回首次已建的那条 | `true` |
| `false` | **断网重试**（同 `idempotencyKey`） | 幂等命中 → 返回首次已建的那条 | `true` |

> ⚠️ **`reused=true` 有两条来源，别只盯第一条**：
> ① **幂等命中**（业务逻辑第 1 条）——传了 `idempotencyKey` 且已有同 key 记录时直接返回，**优先级最高**，在「查进行中记录」之前就返回；
> ② **命中进行中记录**（业务逻辑第 2 条）——`restart=false` 时的正常路径。
> 所以 **`restart=true` 也可能收到 `reused=true`**（重试场景）—— 那条 key 属于「首次调用时已新建的记录」，幂等返回它正是**预期行为**，不是矛盾。

##### 业务逻辑

1. **幂等**：传了 `idempotencyKey` 且已存在同 key 的记录 → 直接返回（`reused=true`）。
2. **查进行中记录**：`practice_record` where `user_id=? AND section_mapping='SEC_CSCA' AND section=科目码 AND status IN (0,1)`，加行锁（`FOR UPDATE`）；命中且 `restart=false` → 直接返回。
3. **计算题目范围（题集），建轮时一次算定**（**缺省排除该用户已练过的题**；⚠️ 这就是本模块「去重」的**唯一落点** —— 取题接口 [3.2.2](#322-get-cscaquestions) 自 2026-10-13 起**不再做去重**、只读这里算定的 `question_ids`）：
   - **`restart=true`（「再来一轮」）** → 题集 = 该科目**全部题**（自然序）—— 「重做一轮」就是**从头重练**，不受"已练过"影响
   - **首次建轮（`restart` 缺省、无进行中记录）** → 题集 = 该科目**剩余未练**的题（自然序）
   - 🔴 **题集不截断**（2026-10-13 收口）：入参 `questionCount` **已删除**（§4.4 第 39 条），上面算出的题集**全部**写进 `question_ids` —— 「练整个科目」就是字面意思，没有"只练前 N 题"的口子。
   - 🔴 **剩余为 0**（该科目已全部练完、且 `restart=false`）→ `404 "该科目暂无未练题目"` —— **此时走「重做一轮」**（`restart=true` 题集取全量、不再 `404`），新轮成为「最新一轮」→ 科目进度自动归零后重新累计（[4.3](#43-待确认事项) 第 14 条已定口径）
   - 🔴 **「想整科全量复习」的唯一出口 = 起新轮**：调 `POST /csca/records {restart:true}` —— **新轮题集直接取科目全量**（[3.2.1](#321-post-cscarecords) 第 3/4 条），此后取题照旧读题集。⚠️ **原「带 `includeAnswered=true` 忽略题集取全量」这条已删除**（2026-10-13 第 36 条）—— 它会让"切背题模式"变成换整套题单。⚠️ **`recordId` 为必填**，故任何取题**至少要有一条属于自己、且 `section_mapping='SEC_CSCA'` 的记录**；全新用户「直接浏览全科」的正常路径就是先建轮（首次建轮题集 = 剩余未练 = 全量）。
4. **题集落库：`question_ids`**（🆕 **新增列**，2026-10-13 定，见 [4.4](#44-文档与实现的差异) 第 26 条）：第 3 条算出的题集写进 `practice_record.question_ids`（**自然序** `question.id` 数组，JSON）。此后**本次练习的题集固定不变** —— `/csca/questions?recordId=<本记录>` 只在这批 id 里分页，**两次打开永远是同一批题**（[4.3](#43-待确认事项) 第 2 条已定）。
   - **题序**：`question_ids` 存**自然序**；要乱序仍走 [3.2.2](#322-get-cscaquestions) 的 `shuffle=true` + `seed`（`seed` 建议直接传 `recordId`）—— 对**固定题集**做确定性排序，同一条记录内多次翻页题序一致、不重不漏。
   - **题量不可选**：题集**不截断** —— 建轮即练整科（该科目剩余未练 / `restart=true` 时全量）。原「`questionCount > 0` 只取前 N 题截断」**已随该入参删除**（2026-10-13，§4.4 第 39 条）。
   - ⚠️ **题集只在建轮时写一次**，后续作答 / 交卷 / 补传**都不更新**它。
   - ⚠️ **HSK 记录该列为 `NULL`**（HSK 用 `practice_paper_structure` 固定题集）—— CSCA 的取题逻辑必须只认 `section_mapping='SEC_CSCA'` 的记录、并判空。

5. **弃旧记录**（`restart=true` 时）：旧记录 `status → 2（已放弃）`，**保留其 `practice_answer`** —— 历史作答**一行都不删**。⚠️ 但 **科目进度是「只算最新一轮」**（[3.1.1](#311-get-cscacatalog) 业务逻辑第 3 条）：新轮一建立就成为「最新一轮」，**旧轮立刻退出进度统计** → 科目卡归零、随新轮作答重新累加。**这就是「重做一轮」的实现，不需要任何删除或重置接口。**
6. 建记录：`paper_id=0`、`structure_id=科目稳定ID`、`section_mapping='SEC_CSCA'`、`section=科目码`、`practice_name='CSCA · 数学'`、`status=1`、`total_questions=N`（**= 题集大小**）、🆕 **`question_ids=<第 3 条算出的题集>`**、`start_time=now`。
7. **不预建 `practice_answer` 行**：作答时按题 upsert（见 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid)），避免"一开练就预写整科 N 行"。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaRecordController#start(@RequestBody CscaRecordStartRequest, HttpServletRequest)` | 强鉴权 + 参数校验 |
| Service | `CscaRecordService#start(Long userId, CscaRecordStartRequest)` | 幂等 → 查进行中（锁）→ 建记录 |
| Mapper | `CscaRecordMapper` / `CscaAnswerMapper` | 记录 CRUD |
| 支撑 | `csca/support/CscaStructureIds#of(subjectCode, lang)` | `structure_id` 稳定 ID 计算 |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `exam_paper` / `question` / `practice_answer` | SELECT | **剩余未练题量**（该科目题 − 该用户已答）+ **题集 id 列表**（自然序）/ 是否存在（校验科目非空） |
| `practice_record` | SELECT（FOR UPDATE）+ INSERT + UPDATE | 全部建记录所需列 + 🆕 **`question_ids`（写题集）** |

##### 数据流向

```
① 入参    subjectTypeMapping（5 值）/ languageVersion（必填）… ──校验──→ 非法 400
② 查库    question ⋈ exam_paper ──剩余未练题数 N0（= 该科目题 − 该用户已答；为 0 则 404 "该科目暂无未练题目"）
          practice_record(FOR UPDATE, section_mapping='SEC_CSCA', section=科目, status IN(0,1))
③ 加工    structure_id = CscaStructureIds.of(subject, lang)
          题集 = 该科目（剩余未练 | restart 时全量）的自然序 id 列表（整科全取，不截断）
          restart → 旧记录 ABANDONED
④ 组装    INSERT practice_record（含 question_ids）→ CscaRecordStartResponse
```

> ⚠️ **`paper_id = 0` 是哨兵值，不是真卷**。任何"按 `paper_id` join `exam_paper`"的既有 SQL 都会把 CSCA 记录当成"卷 0"——新增的 CSCA 查询必须**显式带 `section_mapping='SEC_CSCA'`**，绝不能只按 `user_id` 查。这条要在 Mapper 上写注释。
> ⚠️ **`structure_id` 是计算值、库里无对应行**，所以**任何 join `practice_paper_structure` 的查询都会把 CSCA 记录查丢**。CSCA 的进度查询**只用 `section_mapping + section`**，不 join 结构表。

---

#### 3.2.2 GET /csca/questions

##### 接口用处

**CSCA 练习的核心取题接口**：按**科目 + 语言**返回单题（题干 + 选项，**不含答案 / 解析**）。支持分页、**乱序开关**；**必须登录**。**`subjectTypeMapping` / `languageVersion` / `recordId` 三参必填**（2026-10-13 收口）—— **题集恒取该 `recordId` 的固定题集**（两次打开同一批题、**不随任何开关改变**）。题序缺省为自然序，可用 `shuffle=true` 打乱（**须同时传 `seed`**，见下）。⚠️ **题型不再是入参**（本接口不做按题型筛选，`typeId` 只作出参）。⚠️ **原 `includeAnswered` 入参已删除**（§4.4 第 36 条）：背题模式**不改题集**，只是对当前题调 [`GET /csca/questions/{id}/solution`](#333-get-cscaquestionsquestionidsolution) 把答案亮出来；「整科全量」走 [`POST /csca/records {restart:true}`](#321-post-cscarecords) 起新一轮。

每道题带 **`layout`（题面布局三态）**：`textChoice` / `passageGroup` / `clozeGroup`。CSCA 题的题面**不全在 `passage` 里** —— 题面 / 材料共**三个下发字段**（`passage` / `content` / `group.passage`，逐个由 `layout` 决定取哪个），有 150 题的题面只存在于分组材料（`group.passage`），所以**前端必须按 `layout` 分流渲染**，见 [业务逻辑第 8 条](#322-get-cscaquestions) 与 [4.1 `CscaLayout`](#41-枚举速查)。

> 📌 **原型「开始练习」是练整个科目、并整体乱序**；但「整个科目」在**跨天**场景下会重复出题（第一天做过的第二天又出现），所以本模块把「**只回还没做过的题**」**前移到建轮**：[3.2.1 `POST /csca/records`](#321-post-cscarecords) 建轮时把**剩余未练**的题算定并落库（`practice_record.question_ids`），取题**一律带 `recordId`**（**必填**）读这份固定题集 —— 跨天反复打开也不会换题、也不会重复。本模块把乱序做成**开关**：`shuffle` 缺省 `false`（自然序 `paper_id, section, number, sort_order, id`），传 `true` 才打乱，且**此时 `seed` 必填**（同一 `seed` 多次翻页题序一致、不重不漏）；`shuffle=true` 不带 `seed` → `400`。**本模块没有"无种子的每次随机"形态。**

##### 入参

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| Token | Header | String | **是** | 题目接口统一强鉴权（`Authorization: Bearer` / `X-Access-Token` / `?token=`，见 [0.2](#02-鉴权与客户端类型)）；`userId` 从 Token 取，**前端不得传** |
| `subjectTypeMapping` | Query | String | **是** | 科目码，**5 个原始值** `arts_chinese` / `science_chinese` / `math` / `physics` / `chemistry`（与 [3.1.1](#311-get-cscacatalog) 返回的 `subjectTypeMapping` 一致）；**只有这 5 个值**（**不提供合并别名 `chinese`** —— 文 / 理中文各成一科，2026-10-13 定）；非法 → `400` |
| `languageVersion` | Query | String | **是** | **必填、无缺省**（2026-10-13 收口）；**只认 `CSCALanguageVersion` 的 2 值**（`chinese` / `english`），**未传 / 非法值 → `400`（`CSCA_LANGUAGE_INVALID`）** |
| `recordId` | Query | Long | **是** | 本次练习记录 id（[3.2.1](#321-post-cscarecords) 建的那条；`restart=false` 幂等取回草稿也回它），**题集来源**：取**该记录的 `question_ids` 题集**（建轮时算定、**固定不变**，两次打开永远是同一批题）。**未传 / 不存在 / 不属于当前用户 / 非 CSCA 记录 → `404`（`CSCA_RECORD_NOT_FOUND`）**。⚠️ **题集唯一来源**：本接口**不再有**「忽略题集、按科目全量取」这条支路（原 `includeAnswered` 已删，§4.4 第 36 条）。⚠️ **由可选改必填的理由**：题集必须有落点（「只回没做过的题」已前移到建轮，见业务逻辑第 5 条），且缺记录时前端统一走「重新建轮」分支 |
| `shuffle` | Query | Boolean | 否 | **乱序开关**：`false`（**缺省**）= 自然序；`true` = 打乱题序，**此时 `seed` 必填**（未传 → `400`） |
| `seed` | Query | String | **仅 `shuffle=true` 时必填** | **乱序种子**（≤ 64 字符）。服务端用它做**确定性乱序**（`ORDER BY CRC32(CONCAT(q.id, seed))`，同一 `seed` 多次请求题序一致、翻页不重不漏）；**缺省关时忽略**；**`shuffle=true` 未传 → `400`**（**无** `ORDER BY RAND()` 形态） |
| `page` | Query | Integer | 否 | 缺省 `1`，`< 1` → `400` |
| `pageSize` | Query | Integer | 否 | 缺省 `20`，范围 `1–100`，越界 → `400` |

##### 返回 JSON

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "subjectCode": "arts_chinese",
    "languageVersion": "chinese",
    "availableCount": 640,
    "page": 1,
    "pageSize": 20,
    "questions": [
      {
        "questionId": "2095483421313331202",
        "paperId": "2095483421053284353",
        "paperSource": "文科中文模拟试卷1",
        "number": 1,
        "section": "1",
        "typeId": "SINGLE",
        "layout": "textChoice",
        "passage": "请选出\"着\"字读音不同的一项.",
        "content": null,
        "options": [
          { "label": "A", "content": "别<u>着</u>急" },
          { "label": "B", "content": "睡<u>着</u>了" },
          { "label": "C", "content": "躺<u>着</u>看书" },
          { "label": "D", "content": "找<u>着</u>了吗" }
        ],
        "score": "1.25",
        "group": null
      },
      {
        "questionId": "2095483438635806735",
        "paperId": "2095483421053284353",
        "paperSource": "文科中文模拟试卷1",
        "number": 71,
        "section": "6",
        "typeId": "SINGLE",
        "layout": "passageGroup",
        "passage": null,
        "content": "根据这段话,很多人做了学习计划后:\n",
        "options": [
          { "label": "A", "content": "要复习考试" },
          { "label": "B", "content": "去参加运动" },
          { "label": "C", "content": "从来不放弃" },
          { "label": "D", "content": "却没有完成" }
        ],
        "score": "1.25",
        "group": {
          "startNumber": 71,
          "endNumber": 72,
          "passage": "<p>不知道你是否有过这样的经历:下定决心去做一件事情,还没有开始做,却已经放弃了.例如:你打算健身,可是每次到了该锻炼的时候又不想运动了;你打算学习新知识,可是刚开始学就因为觉得太难而放弃了.我们做了很多决定,可是真正能够完成的却非常少.所以,不要把今天的事情留到明天.做好计划后,就赶快行动吧.</p>"
        }
      },
      {
        "questionId": "2095483438577086465",
        "paperId": "2095483421053284353",
        "paperSource": "文科中文模拟试卷1",
        "number": 34,
        "section": "4",
        "typeId": "SINGLE",
        "layout": "clozeGroup",
        "passage": null,
        "content": null,
        "options": [
          { "label": "A", "content": "农业" },
          { "label": "B", "content": "发明" },
          { "label": "C", "content": "历史" },
          { "label": "D", "content": "记载" },
          { "label": "E", "content": "构成" }
        ],
        "score": "1.25",
        "group": {
          "startNumber": 34,
          "endNumber": 38,
          "passage": "筒车是一种用水流做动力取水浇田的工具,也叫\"水转筒车\".据史料__34__,筒车是隋朝人__35__的,从唐代开始广泛应用于__36__,距今已有1000多年的__37__.这种靠水力自动运行的古老筒车是中国古代劳动人民的伟大创造,在全国各地的山涧.溪流间__38__了一幅幅古老的田园春光图."
        }
      }
    ]
  }
}
```

- **`answer` / `analysis` 绝不出现**（硬约束，见 [0.6](#06-枚举与版本号)）
- `layout` 是**题面布局**，三态之一（本模块新增定义，见 [4.1 `CscaLayout`](#41-枚举速查)）；**下面示例的三条题正好各占一态**：`textChoice`（单题自足，题面在 **`passage`**）/ `passageGroup`（材料与题面**分列**：题面 **`content`** + 材料 **`group.passage`**）/ `clozeGroup`（**材料即题面**：题面在 **`group.passage`**，`passage` / `content` **均为 `null`**）
- `group` 只在**共材料题**（`question_group` 命中）时非 `null` —— 共 **260 题**：阅读理解 `passageGroup` **110** + 选词成段 `clozeGroup` **150**。形如示例第 2 / 3 条：`{ "startNumber": 71, "endNumber": 72, "passage": "…" }`；`startNumber` / `endNumber` 是该组覆盖的**题号区间**（示例第 3 条的组为 **34–38**，5 道题**共用一段材料与同一个词池**）
- **题面 / 材料是三个字段，全部取库中原值、服务端不做合成、`stem` 已取消**：

  | 下发字段 | 库中来源 | 何时有值 | 用途 |
  |---|---|---|---|
  | `passage` | `question.passage` | `textChoice`（**1644 题**） | 单题自足的**题面**原文 |
  | `content` | `question.content` | `passageGroup`（**110 题**） | 与材料**分列**的**题面**原文 |
  | `group.passage` | `question_group.passage` | 有分组时（**260 题**） | **组级材料**；`clozeGroup` 时**它就是题面**（含 `__N__` 空位） |

  取哪个**完全由 `layout` 决定**：`textChoice` → `passage`；`passageGroup` → 题面 `content` + 材料 `group.passage`；`clozeGroup` → 只看 `group.passage`。三者**互斥**（同一道题最多一个「题面源」），前端**不必猜字段名**。
- 🔴 **`availableCount` = 「本次可取的题数」，恒等于该记录题集的大小**（`JSON_LENGTH(question_ids)`，**建轮时算定、固定不变**，读记录即可、不必再查库）。**它不随任何开关变化** —— 原「不传 `recordId` 时的去重后剩余题数」（已移到建轮）与「`includeAnswered=true` 时的科目总量」两个中间语义**均已取消**（§4.4 第 36 条）。`availableCount = 0` 表示**该记录题集为空**（此时走「重做一轮」，见 [4.3](#43-待确认事项) 第 14 条）。取舍逻辑见入参表与业务逻辑第 5 条。
- ✅ **三个键在每道题里恒出现**：没有值就填 `null`（**不省略键**）—— 全项目未配 `NON_NULL` 序列化策略，`passage` / `content` / `group` 会原样序列化，前端可写死 schema、不必判 `hasOwnProperty`。
- ⚠️ **示例取材说明（防误读）**：上面三条题取自**同一张卷「文科中文模拟试卷1」**、覆盖三种 `layout`，值**全部是库中真实数据**（三条 `paperId` 相同，便于横向对照三种形态的字段差异）。**别拿数学题去对照共材料形态** —— 数学 / 物理 / 化学卷**结构上全是 `textChoice`**（这三科在 `question_group` 里**一行都没有**），共材料题**只存在于文科中文 / 理科中文卷**（`arts_chinese` 505 + 60 + 75 / `science_chinese` 275 + 50 + 75，见 [4.1](#41-枚举速查)）。⚠️ 示例**只摘三条**（为横向对照三态，**不是**一页的真实长度）：真实响应里 `questions` 最多 `pageSize`（≤ 20）条、按题序连续切片。
- ⚠️ **题面 / 材料 / 选项都是库中的「原样字符串」**：示例里的 `<u>着</u>`、`<p>…</p>` 并非笔误，而是**库中真实存在的 HTML 片段**（实测 `question.passage` **158 行**、`option_content` **55 行**、`question_group.passage` **40/75 组**含标签）；`content` 还带**首尾换行**（示例第 2 条尾部的 `\n`）。前端按**富文本**渲染（与 LaTeX 同理，见 [4.4](#44-文档与实现的差异) 第 2 条）——**不要做 HTML 转义**（会显示成源码），**也不要把「看起来像标签」的题面当脏数据丢掉**。
- ⚠️ **本响应已取消 `stem` 字段**：旧实现把 `passage`（空白则回退 `content`）合成一个 `stem` 下发，与上面三字段**信息重复**且会误导（`clozeGroup` 时它恒为 `null`）—— 见 [4.4](#44-文档与实现的差异) 第 15 条。前端**不要**用「题面字段是否为空」猜形态，形态**只认 `layout`**。
- **`typeId` 只有 `SINGLE` / `MULTI` 两个值**（**映射值**、**英文枚举码**，不是库中题型原名）：库里 `type_id='多选'` 的 **33 题**回 `MULTI`，其余 **1871 题**（含库中原名 `单选` / `识解汉字` / `选词填空` / `辨析词语` / `选词成段` / `补全语句` / `阅读理解`）**一律回 `SINGLE`**。它管的是**作答值域（单值作答 / 多值作答）**，**不管题面怎么画** —— `MULTI` = 答案可有多个标签、`SINGLE` = 单标签作答；**渲染形态（材料怎么摆、题面取自哪个字段）一律看 `layout`**（见上一条），`typeId` 不参与形态判定。**不必认识库中那 8 种中文原名**（规则见 [4.1](#41-枚举速查) 与业务逻辑第 13 条）。⚠️ **`answerMode` 字段已取消** —— 它当年的取值（`SINGLE` / `MULTI`）**就是现在 `typeId` 的这两个值**，信息完全重复，留一个就够。

##### 业务逻辑

1. **参数校验**：`subjectTypeMapping` 命中 5 个原始值（**合并别名 `chinese` 已取消**，传它 → `400` / `CSCA_SUBJECT_INVALID`）；**`languageVersion` 必填**（未传 / 非法 → `400` / `CSCA_LANGUAGE_INVALID`）；**`recordId` 必填**，且必须属于当前用户、是 CSCA 记录（**未传 / 查不到 / 非本人 → `404` / `CSCA_RECORD_NOT_FOUND`**）；`pageSize ∈ [1,100]`；`page ≥ 1`；`seed` 长度 ≤ 64（超长 → `400`）；**`shuffle=true` 且 `seed` 为空 → `400`**（乱序必须带种子）。⚠️ **题型不再是入参**（2026-10-13 删除 `typeId` 入参，`CSCA_TYPE_ID_INVALID` 转为**保留码**、无触发点，见 [4.4](#44-文档与实现的差异) 第 35 条）。
2. **科目筛选直接打在题上**：`question.subject_type_mapping` 已补齐（CSCA **1904 行全有值**），5 个原始码**各为单值**（`q.subject_type_mapping = ?`）—— ⚠️ **不再有「`chinese` 展开成 IN 两值」这条**（2026-10-13 取消合并别名，[4.3](#43-待确认事项) 第 11 条）。**join `exam_paper` 不再用于换科目**，只为限定 CSCA 范围与 `language_version`。
3. **⚠️ 不能用 `PracticeQuestionMapper.selectByPart`**：那条 SQL 依赖 `question.section_mapping`（CSCA 全为 `NULL`，见 [0.7](#07-与-hsk-练习链路的差异为什么要单开一条链路) 第 4 条）。本接口用新增的 `CscaQuestionMapper#selectBySubject`。
4. **例题防御性排除**：`AND (q.type_id_mapping IS NULL OR q.type_id_mapping <> 'example_question')`。实测 CSCA 无例题行，但条件保留（成本为零，防未来）。
5. **题集只有一处来源 + 已答过的题回快照（2026-10-13 收口，§4.4 第 36 条）**：

   | 取哪些题 | 稳定性 |
   |---|---|
   | **恒取该 `recordId` 的 `practice_record.question_ids`**（建轮时算定，[3.2.1](#321-post-cscarecords) 第 4 条） | ✅ **固定**，两次打开同一批题；**不随任何入参变化** |

   - 🔴 **原「题集两态」已取消**（2026-10-13，用户口径）：`includeAnswered` 入参**已删除**，`selectBySubject` / `countBySubject` 两条 SQL **一并删除**。理由 —— 它实现的是**换结果集**（不是换显示），切过去之后：**同一 `page` 取到另一批题**（分页坐标从"题集内 offset"变成"科目内 offset"）、**`availableCount` 从题集大小跳到科目总量**（进度条跳变）、**同一 `seed` 的乱序结果整体重算**、**本轮已答题的题面从"快照"退回"实时"** —— 用户在答题过程中切一次「背题模式」，题目、题序、进度、题面**四处全变**，属设计冲突。
   - 🔴 **背题模式与本接口无关**：原型里它是答题页顶栏的一个开关（`答题模式·背题模式`），只做「不判分、直接亮答案+解析」，走 [`GET /csca/questions/{id}/solution`](#333-get-cscaquestionsquestionidsolution)。**切背题模式不重拉列表、不换题集**。
   - 🔴 **「想整科全量复习」的正规出口 = `restart:true`**：[3.2.1 `POST /csca/records {restart:true}`](#321-post-cscarecords) 起新一轮，**新轮题集即科目全量**（[4.3](#43-待确认事项) 第 14 条）。一个诉求一个入口，不再有第二套题单。
   - 🔴 **题集必须有落点 → `recordId` 必填（2026-10-13 收口）**：原「**不传 `recordId`**（`includeAnswered=false`）→ 按科目实时取 + `NOT EXISTS` 排除该用户**已答过的题**」这条**已删除** —— 「只回没做过的题」**前移到建轮**（建轮时题集 = 剩余未练），取题侧**不再做任何去重**。附带好处：原「边答边翻页会漂移、只适合一次性拉完」的坑**随之消失**（题集是死的，翻页永远稳定）。
   - ⚠️ **固定题集里不要再按"排除已答"过滤**：题集是死的，「本轮已答的题」必须**继续留在题集里**（否则答完第 1 页后第 2 页的 `OFFSET` 整体前移 → 重复出题）。已答过的题靠**回快照**展示（见下条），**不是**从题集里消失。
   - 🔴 **去重键 = `question_id`，跨语言不去重**（2026-10-13 定）：中文卷与英文卷是**两套不同的卷子**（不同 `question.id`），故**同一考点在中 / 英各记一次、各自独立进出题集** —— **不要**把中 / 英两道题当成"同一题"合并（[4.3](#43-待确认事项) 第 12 条）。
   - 🔴 **已答过的题回快照**（冻结题面，见 [3](#3-接口详细设计)）：对本页题目**再过一道 `practice_answer`**（`practice_record_id = ? AND answered = 1 AND deleted = 0 AND question_id IN (本页 id)`，**每页 1 次查询**）——
     - **命中**（这一轮已经答过）→ 题面 / 选项 / 材料**改从快照读**：`question_snapshot`（`passage` / `content` / `layout` / 题型原名）、`option_snapshot`、`group_snapshot`；
     - **未命中**（还没做过）→ 保持实时读 `question` / `question_group`。
     - ⚠️ 快照**只覆盖题面相关字段**；`paperSource` / `number` / `section` / `score` 这些"身份字段"仍实时取（改卷名不该让旧记录显示旧卷名）。
     - ⚠️ 这一步**恒执行**（题集固定，所以"本轮已答"的上下文永远存在）—— 原「`includeAnswered=true` 时不做快照」的分支已随该入参删除。
6. **选项解析**：`question.option_content` 是 **JSON 对象** `{"A":"…","B":"…"}`，键即选项标签，**必须保序**（A→B→C→D→E→F）。实测选项数**不固定**（有 5 选项、6 选项的题：全库 `answer` 出现 `E` 54 次、`F` 28 次）。
7. **`group` 组装**：库里 `question_group` 是"共材料大题"（带 `start_number` / `end_number` / `passage`）。实测 **260 道 CSCA 题有 `question.group_id`**（= 阅读理解类 110 题 + 选词成段 150 题；集中在**文科中文 / 理科中文**卷，数学 / 物理 / 化学**没有分组**）。
   - **取组不是 SQL join，而是「一次批量取 + 内存索引」**：先由本页题目收集 `paper_id` 去重集合，用 `practice/core/mapper/PracticeQuestionGroupMapper#selectList` 查 `paper_id IN (...) AND deleted = 0`（**每页 1 次查询**，不是每题一查），在内存里建两张索引：`group_id → 组`、`paper_id → 组列表`。
   - **主路径**：用 `question.group_id` 直接命中内存索引（HSK 阅读取组同思路）。
   - **兜底路径**：`group_id` 为空（或索引未命中）时，按 `number ∈ [start_number, end_number]` 在**本卷**组列表里顺序扫描命中——防将来导入的卷只填了区间没填 `group_id`（HSK 听力取 `question_shared_audio` 同手法）。
   - 命中则把整组的 `startNumber` / `endNumber` / `passage` 一起下发（约 200 字符），避免前端为每道题重复请求材料。**组材料只在 `group.passage` 里** —— 顶层 `passage` 是**题级**字段（`question.passage`），两者**不再互为冗余**（2026-10-12 口径变更，见 [4.4](#44-文档与实现的差异) 第 15 条）。
8. **`layout` 直接透传、不做推算**：`question.layout` 已按**字段判定规则**补全（2026-10-12 落库，**1904 行全覆盖**；判定规则与统计见 [4.1 `CscaLayout`](#41-枚举速查)），服务端**原样下发**（与 HSK 听力同一个用法：**不做 `enum` 换算、不参与业务分支**）—— ✅ **已实现**（`CscaQuestionRow` / `CscaQuestionResponse` / `CscaQuestionMapper.xml` 的 SELECT / Service 直传，见 [4.4](#44-文档与实现的差异) 第 13 条）：
   - `textChoice`（**1644 题**）—— `group_id` 为空，**单题自足**，题面在 **`passage`**；
   - `passageGroup`（**110 题 / 45 组**）—— `group_id` 非空**且** `content` 非空，材料（**`group.passage`**）与题面（**`content`**）**分列**；
   - `clozeGroup`（**150 题 / 30 组**）—— `group_id` 非空**且** `content` 为空，**材料即题面**（**`group.passage`** 内含 `__34__` 空位，5 个选项是**组内共享词池**），此时 **`passage` / `content` 均为 `null`**。
   > 🔴 **前端必须按 `layout` 分流，不能按「题面字段是否为空」去猜**：`clozeGroup` 的这 150 题 `passage` 与 `content` **两列皆空**（下发的两个字段都是 `null`）—— 若代码写成"`passage` 为空就跳过 / 隐藏这道题"，**这 150 题会整体丢失**。这类题应把 `group.passage` 当题面渲染，`__N__` 视作输入位。
   > ⚠️ **`layout` 不能由 `type_id` 推算**：`单选` 跨两种形态（1061 题扁平 + **10 题带材料**，后者与「阅读理解」同形态却标了另一个题型名）。判定只能看 `group_id` 与 `content` 两列 —— 这正是它**独立成列、而不是运行时用 `CASE` 现算**的原因（现算会让 `paper_id` 上的筛选与排序复杂化，且无法走索引）。
9. **题序（由 `shuffle` 开关决定）**：
   - `shuffle` 缺省 / `false` → **自然序**：`ORDER BY q.paper_id ASC, q.section ASC, q.number ASC, q.sort_order ASC, q.id ASC`；
   - `shuffle=true`（**此时 `seed` 必填，已校验非空**）→ **确定性乱序**：`ORDER BY CRC32(CONCAT(q.id, seed)) ASC, q.id ASC`（同一 `seed` 题序一致，**翻页不重不漏**）。
   - ⚠️ **没有第三种形态**：`shuffle=true` 无 `seed` 已在步骤 1 被 `400` 拦下，**不存在** `ORDER BY RAND()` 分支。
   - ⚠️ 乱序只作用于**本次的结果集**（恒为那份**固定题集**）；同一 (`userId`, `recordId`, `seed`) 三元组下题序完全一致（因此 `seed` 建议直接传 `recordId`）。⚠️ **切「背题模式」不要换 `seed`、也不要重拉列表** —— 题序就不会动。
10. **`availableCount` 直接取自记录**（= `JSON_LENGTH(question_ids)`，**不必再发 COUNT SQL**）；**题集为空时短路**、直接回空数组（不再发取题 SQL）。🔴 **`availableCount` 语义（2026-10-13 第 36 条收口）**：**恒等于该记录题集的大小**（`JSON_LENGTH(question_ids)`，**固定**、**不随任何开关变化**）。`availableCount = 0` 表示**该记录题集为空**（走「重做一轮」）。⚠️ 原「`includeAnswered=true` 时为科目总量」这一态**已随该入参删除**；「去重后剩余题数」这个中间语义**只存在于建轮**（[3.2.1](#321-post-cscarecords) 第 3 条），取题侧不再出现。
11. 分页采用 `LIMIT/OFFSET`（`page` × `pageSize`）。
12. **选项数可变（对原型的提醒）**：原型演示里每题都是 4 个选项（A–D），但**库中选项数不固定**（4 / 5 / 6）。前端布局必须按 `options.length` 自适应，**不要硬编码 4 项**。
13. **`typeId` 映射（对外只出两值）**：响应里的 `typeId` **不是** `question.type_id` 原名，而是**映射值**（`CscaQuestionTypes#display`）：
    - `question.type_id = '多选'` → 回 **`MULTI`**（**33 题**）；
    - **其余一切**（`单选` / `识解汉字` / `选词填空` / `辨析词语` / `选词成段` / `补全语句` / `阅读理解` / 空值 / 未登记的新原名）→ 回 **`SINGLE`**（**1871 题**）。
    - 映射**只看 `type_id` 列、不看标准答案**（取题 SQL **已不取 `answer`**）。
    - ⚠️ **题型已不是入参（2026-10-13）**：本接口**不做**按题型筛选 —— 传 `typeId` 一律**被忽略**（不校验、不再回 `8003`），`CSCA_TYPE_ID_INVALID` 转为**保留码**（[0.5](#05-错误码) / [4.4](#44-文档与实现的差异) 第 35 条）。原「筛选与显示严格同源」的说法**随之作废**（筛选侧已不存在，只剩出参映射）。若将来要恢复按题型筛，需重新加回入参 + `q.type_id` 过滤。
    - ⚠️ **与库中原名解耦**：`识解汉字` / `选词填空`… 这些名字**不再下发**。产品若要按细粒度题型展示或筛选，得另加字段（**本次不做**，见 [4.3](#43-待确认事项) 第 5 条）。
    - ⚠️ **已知代价（数据问题，非逻辑问题）**：实测有 2 题 `type_id='单选'` 但标准答案是 `B,D` / `A,C`，按本规则它们回 `SINGLE` → 前端渲染**单选框**，用户选一个就会判错。**建议题库侧修正这 3 行的 `type_id`**（[4.4](#44-文档与实现的差异) 第 9 条）；**判分不受影响** —— 判分一律按**答案标签集合**比较、**不按 `type_id` 分支**（[4.2](#42-答案归一化cscaanswernormalizer)）。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaCatalogController#questions(CscaQuestionQuery query, HttpServletRequest request, @RequestHeader X-Client-Type)` | 强鉴权：`requireAuthenticatedAppUserId` 取 `userId`（未登录 → `401`）→ 调 Service |
| Service | `csca/service/impl/CscaQuestionQueryServiceImpl#query(Long userId, CscaQuestionQuery query)` | **全部校验在这里**（含 `languageVersion` / `recordId` **必填** + `recordId` 归属校验）+ 计数 + 分页取题 + 共材料装配 + 选项解析 + 剥离答案 |
| Mapper | `csca/mapper/CscaQuestionMapper#selectByQuestionIds`（固定题集，**唯一取题 SQL**） | 取题（拼 `<sql id="cscaQuestionValid">` / `<sql id="cscaPaperScope">` / `<sql id="cscaOrderBy">`）。⚠️ `#selectBySubject` / `#countBySubject` / `<sql id="cscaSubjectScope">` **已随 `includeAnswered` 一并删除**（§4.4 第 36 条） |
| Mapper（共材料） | `practice/core/mapper/PracticeQuestionGroupMapper#selectList`（MyBatis-Plus 条件构造器） | 按本页 `paper_id IN (...) AND deleted = 0` 一次取回全卷分组，**不是** SQL join |
| 支撑 | `csca/support/CscaQuestionTypes`（`type_id` 原名 → 映射值 `SINGLE` / `MULTI`，**仅出参**）/ `csca/support/CscaSubjects`（科目码单值校验 + 中文名反查） | 题型映射 / 科目校验 |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `exam_paper` | SELECT | `id` / `exam_type` / `version` / `language_version` / **`source`**（下发为 `paperSource`）/ `deleted`（限定范围 + 语言） |
| `question` | SELECT | `id` / `paper_id` / **`subject_type_mapping`** / `number` / `section` / **`type_id`**（只用于映射 `typeId`，原名不透出）/ `type_id_mapping` / **`layout`** / `content` / `passage` / `option_content` / `score` / `group_id` / `sort_order` / ⚠️ **不取 `answer`**（映射不看答案；答案只在 [3.3.3](#333-get-cscaquestionsquestionidsolution) 出口）/ `deleted` |
| `question_group` | SELECT | `id` / `paper_id` / `start_number` / `end_number` / `passage` / `deleted`（**按 `paper_id IN` 一次取回**，无 `section_mapping` 参与） |
| `practice_answer` | SELECT | 本页题的快照列（`question_snapshot` / `group_snapshot` / `option_snapshot`）—— 用于**已答过的题回快照**（**恒执行**；⚠️ 取题侧**不用**它做「排除已答」的去重） |
| `practice_record` | SELECT | `id` / `user_id` / `section_mapping`（**校验 `recordId` 归属**）+ 🆕 **`question_ids`（读固定题集）** |

##### 数据流向

```
① 入参    token.userId / subjectTypeMapping / languageVersion / recordId / shuffle / seed / page / pageSize
          （前 3 参必填；无 typeId —— 题型不再是入参；无 includeAnswered —— 已删除，§4.4 第 36 条）
          ──校验──→ 未登录 401 / 缺参·非法 400（8001 / 8002）/ 记录缺失·非本人 404（8007）

② 查库    题集唯一来源（业务逻辑第 5 条；recordId 必填）：
            读 practice_record.question_ids（固定题集，建轮时算定；题集为空 → 短路回空数组）
          question(id IN 题集, deleted=0, 排除例题)
            ⋈ exam_paper(exam_type=2, version='CSCA', language_version=?, deleted=0)
          ──ORDER BY paper_id, section, number, sort_order, id；shuffle=true 时改 CRC32(CONCAT(id, seed))──→ 分页切片
          question_group(按本页 paper_id IN 一次取回 → 内存索引；主命中 group_id，为空时按 number ∈ [start,end] 兜底) ──→ 共材料
          practice_answer(本页已答过的题取快照列 → 题面 / 选项 / 材料回快照)

③ 加工    option_content JSON → 保序选项数组（A→B→…→F）[已答过的题改用 option_snapshot]
          layout 原样透传（textChoice / passageGroup / clozeGroup，不推算）[已答过的题改用 question_snapshot.layout]
          题面 / 材料三字段原样透传（passage / content 取自题，group.passage 取自组；不做合成，已无 stem）[已答过的题取自 question_snapshot / group_snapshot]
          typeId = CscaQuestionTypes.display(type_id)（库中 '多选' → MULTI；其余一切 → SINGLE；不看答案）
          剥离 answer / analysis（只留题面）

④ 组装    CscaQuestionsResponse { availableCount, page, pageSize, questions[] }
```

**映射对照**

| 响应字段 | 来自 | 取法 |
|---|---|---|
| `subjectCode` | `csca/support/CscaSubjects` | 回显入参科目码（**5 个原始值之一**）。⚠️ **不再下发科目中文名**（原 `subjectName` 字段已删，见 [4.4](#44-文档与实现的差异) 第 16 条） |
| `languageVersion` | 入参（**必填**，无缺省） | 回显**规范化后**的语言码 |
| `questionId` / `paperId` | `question.id` / `question.paper_id` | 直取（字符串） |
| `paperSource` | `exam_paper.source` | join 取 |
| `number` / `section` | `question.number` / `question.section` | 直取（`section` 是数字字符串） |
| `typeId` | `CscaQuestionTypes#display` | **映射值（英文枚举码），只出两值**：`question.type_id = '多选'` → `MULTI`；**其余一切 → `SINGLE`**（`识解汉字` / `选词填空` / `辨析词语` / `选词成段` / `补全语句` / `阅读理解` / 空值 / 未登记）。**库中原名不透出**；映射**不看答案**（取题 SQL 已不取 `answer`）。⚠️ **该字段是纯出参** —— 题型**已不是入参**（2026-10-13，不再支持按题型筛选，见第 13 条） |
| `layout` | `question.layout` | 直取，**原样透传**（`textChoice` / `passageGroup` / `clozeGroup`）；前端据此分流题面渲染（[4.1](#41-枚举速查)） |
| `passage` | `question.passage` | 直取（**题级**，`textChoice` 的题面；`clozeGroup` 为 `null`）。**不做兜底合成**（见下 ⚠️） |
| `content` | `question.content` | 直取（**题级**，`passageGroup` 的题面；其余形态实测为 `null`）。与 `passage` **二者互斥** |
| `group.passage` | `question_group.passage` | 组级材料（`passageGroup` 的材料 / `clozeGroup` 的题面，含 `__N__`）；无分组时 `group` 整体为 `null` |
| `options` | `question.option_content` | JSON 对象 → 保序数组 |
| `score` | `question.score` | 直取（`2.08` / `1.25`） |
| `group` | `question_group` | 取组：按本页 `paper_id IN` 一次取回后建**内存索引**；主：命中 `question.group_id`；兜底：`number ∈ [start_number, end_number]` |
| `answer` / `analysis` | — | **本接口不返回** |
| `availableCount` | `practice_record.question_ids` | **恒等于该记录题集大小**（`JSON_LENGTH(question_ids)`，读记录即可）。⚠️ **2026-10-13 由 `total` 改名**（原名与 `totalQuestions` 撞脸）——它与 `/csca/favorites` 的 `total`（收藏总数）、`/csca/records/{id}` 的 `byType[].total`（该题型题数）**三者名字相近但语义各不相同**（[4.4](#44-文档与实现的差异) 第 20 条）；⚠️ 原「`includeAnswered=true` → 科目总量」这一态**已删**（第 36 条） |

**关键 SQL**

```sql
-- 唯一取题 SQL：只在这份固定题集里分页（题集来自 practice_record.question_ids，建轮时算定）
-- 列清单：type_id 只为映射出参 typeId（MULTI / SINGLE），原名不透出；不取 answer（映射不看答案）；p.source 下发为 paperSource
SELECT q.id, q.paper_id, p.source AS paper_source, q.number, q.section,
       q.type_id, q.type_id_mapping, q.layout, q.content, q.passage, q.option_content,
       q.score, q.group_id, q.sort_order
FROM question q
JOIN exam_paper p ON p.id = q.paper_id
WHERE q.id IN (:questionIds)          -- ← 本记录的题集（≤ 640 个 id，一次 IN）
  AND p.deleted = 0
  AND p.exam_type = 2
  AND p.version = 'CSCA'
  AND p.language_version = ?
  AND q.deleted = 0
  AND (q.type_id_mapping IS NULL OR q.type_id_mapping <> 'example_question')
  -- ⚠️ 无题型筛选（题型已不是入参）；无「排除已答」——已答的题要留在题集里（靠回快照展示）
  -- ⚠️ 也没有第二条「按科目全量取」的路径 —— 原 selectBySubject / countBySubject / cscaSubjectScope
  --    已随 includeAnswered 入参一并删除（§4.4 第 36 条）：它会随"切背题模式"换掉整套题单
-- 题序二态（由 shuffle 开关决定；shuffle=true 时 seed 必填，已校验非空）：
--   ① shuffle=false（缺省）：下面这行自然序
--   ② shuffle=true： ORDER BY CRC32(CONCAT(q.id, ?)) ASC, q.id ASC   -- 对固定题集确定性乱序，翻页稳定
--   （不存在"无 seed 的 RAND()"形态）
ORDER BY q.paper_id ASC, q.section ASC, q.number ASC, q.sort_order ASC, q.id ASC
LIMIT ? OFFSET ?;

-- 已答过的题回快照（冻结题面；每页 1 次，恒执行）
SELECT pa.question_id, pa.question_snapshot, pa.group_snapshot, pa.option_snapshot
FROM practice_answer pa
WHERE pa.practice_record_id = ? AND pa.deleted = 0 AND pa.answered = 1
  AND pa.question_id IN (:pageQuestionIds);

-- 计数（availableCount）：恒为 JSON_LENGTH(practice_record.question_ids)，读记录即可、
--   "不发 COUNT SQL"（原「includeAnswered=true → 科目总量」那条 COUNT 已删，§4.4 第 36 条）。
```

> ⚠️ **题干字段用的是 `question.passage` 不是 `content`**：实测 `数学模拟试卷1` 的题，`content` 全为 `NULL`、`passage` 才是题干（`下列结论正确的是( )．`）；**文科中文的题也一样**（`content` 为 `NULL`、题干同样在 `passage`）。**所以 `passage` 与 `content` 两个字段都要下发**（服务端**不做合成**，前端按 `layout` 决定取哪个）——见 [4.4](#44-文档与实现的差异) 第 15 条（`stem` 合成字段已取消）。**别想当然只取 `content`。**
> 🔴 **但 `clozeGroup` 的 150 题是例外**：这 150 题 `passage` 与 `content` **两列皆空**（下发的两个字段都是 `null`）—— 这**不是 bug**，这类题的题面本就在 `group.passage`（含 `__34__` 空位）。前端按 `layout='clozeGroup'` 取 `group.passage` 当题面；**服务端不要为了"让题面字段非空"去回填**，否则同一段材料会在题面区与材料区各出现一次。
> ⚠️ **乱序分页必须配稳定种子 —— 所以本模块把种子做成必填**：`ORDER BY RAND() LIMIT/OFFSET` 会让**同一页在两次请求间不重复但整体有重**（MySQL 每次 `RAND()` 都不同），前端翻页会看到重复题。因此本模块**只保留确定性乱序**：`shuffle=true` 时 `seed` **必填**（`ORDER BY CRC32(CONCAT(q.id, seed))`），服务端无状态也能保证同一会话题序一致；**`shuffle=true` 未传 `seed` 一律 `400`**，不提供 `RAND()` 这条"翻页会重复"的路径。

---

#### 3.2.3 GET /csca/questions/{questionId}

##### 接口用处

**单题详情**（题干 + 选项，**无答案**）。用于深链进入、缓存损坏时单点重试。**需登录**（题目接口统一强鉴权，见 [0.2](#02-鉴权与客户端类型)）。

##### 入参

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| Token | Header | String | **是** | 题目接口统一强鉴权（见 [0.2](#02-鉴权与客户端类型)）；未登录 → `401` |
| `questionId` | Path | Long | **是** | 不是数字 → `400`；查不到 / 不属于 CSCA → `404` |

##### 返回 JSON

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "questionId": "2096765985525108738",
    "paperId": "2096765985265061890",
    "paperSource": "数学模拟试卷1",
    "subjectCode": "math",
    "languageVersion": "chinese",
    "number": 1,
    "section": "1",
    "typeId": "SINGLE",
    "layout": "textChoice",
    "passage": "下列结论正确的是( )．",
    "content": null,
    "options": [
      { "label": "A", "content": "$-1\\in\\mathbb{N}$" },
      { "label": "B", "content": "$\\frac{3}{2}\\notin\\mathbb{N}$" },
      { "label": "C", "content": "$\\sqrt{2}\\in\\mathbb{Q}$" },
      { "label": "D", "content": "$0\\in\\mathbb{N}$" }
    ],
    "score": "2.08",
    "group": null
  }
}
```

- 题目对象与 [3.2.2](#322-get-cscaquestions) **同构**：`layout` + **三字段**（`passage` / `content` / `group`）恒出现、无值填 `null`。本例是**数学卷的 `textChoice`** 形态（数学卷没有共材料题）；`group` 非 `null` 的形态见 [3.2.2](#322-get-cscaquestions) 示例第 2 / 3 条。

##### 业务逻辑

1. `questionId` 非数字 → `400` / `CSCA_PARAM_OUT_OF_RANGE(8005)`（[0.5](#05-错误码) 表里「**路径变量不是数字**」就是这一条）。⚠️ **实现口径（2026-10-13）**：路径变量在 Controller 里声明为 `String` 后**手工解析**，**不是** `@PathVariable Long` —— 项目里 common 的 `GlobalExceptionHandler` **没有** `MethodArgumentTypeMismatchException` 处理器，若声明成 `Long`，非数字会落到兜底分支回 `SYSTEM_ERROR(500)`，与本条 / [0.5](#05-错误码) 冲突（见 [4.4](#44-文档与实现的差异) 第 40 条）。
2. **准入校验**：题目所属卷必须 `exam_type=2 AND version='CSCA' AND deleted=0`，否则 `404 "题目不存在"`（**HSK 的题不能从 CSCA 接口查到**）。
3. **绝不返回 `answer` / `analysis`**（与 [3.2.2](#322-get-cscaquestions) 同一条硬约束）。
4. 解析同上（选项保序、`group` 区间命中、**`layout` 原样透传**）。⚠️ 与 [3.2.2](#322-get-cscaquestions) 同一条：`clozeGroup` 的题 **`passage` / `content` 均为 `null`**，题面在 `group.passage`，前端按 `layout` 分流。
5. **需登录**（题目接口统一强鉴权）：未登录 → `401`。**本接口不涉及题集 / 去重** —— 去重的唯一落点是 [3.2.1](#321-post-cscarecords) **建轮**（按 `questionId` 直取没有「重复出题」的概念）。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaCatalogController#question(String questionId, HttpServletRequest request, @RequestHeader X-Client-Type)` | 路径绑定（**`String` + 手工解析**，非数字 → `8005`）+ 强鉴权；与 [3.2.2](#322-get-cscaquestions) 同一 Controller |
| Service | `CscaQuestionQueryService#detail(Long questionId)` | 准入（慢 SQL 查不到 → `8006`）+ 装配（**与列表共用 `toResponse`**，但 `answered` 恒 `null` → 不读快照） |
| Mapper | `CscaQuestionMapper#selectDetail(questionId)` | 主键直取 1 行，join `exam_paper`（卷侧只 include `<sql id="cscaPaperBase">`，**不含语言**） |
| DTO | `csca/dto/CscaQuestionDetailResponse#of(question, subjectCode, languageVersion)` | 与列表元素**同构** + 两个回读标识（静态工厂逐项搬运，不加工） |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `question` / `exam_paper` / `question_group` | SELECT | 同 [3.2.2](#322-get-cscaquestions) |

##### 数据流向

```
① 入参    questionId（+ token）──非数字则 400；未登录 401
② 查库    question ⋈ exam_paper ──exam_type=2 准入──→ 1 行 / 否则 404
③ 加工    选项解析 + group 装配 + 剥离 answer
④ 组装    CscaQuestionResponse
```

> ⚠️ 与 [0.5](#05-错误码) / [4.4](#44-文档与实现的差异) 第 4 条一致：**"题目不存在"用 `CSCA_QUESTION_NOT_FOUND(8006)`**（HTTP 回 `404`），不再用 `ErrorCode.QUESTION_NOT_FOUND(2001)`，也不写裸字面量 —— 本模块改用自有的 `CSCA_*` 业务码（2026-10-13 定）。
>
> ✅ **已实现（2026-10-13）**：① Controller `#question`（强鉴权 + **手工解析**路径变量）；② Service `#detail`（**与列表共用 `toResponse`**，`answered` 恒 `null` → 不读快照）；③ Mapper `#selectDetail`(+`.xml`)（卷侧只 include 新拆出的 `<sql id="cscaPaperBase">`，**不按语言筛**、**不取 `q.answer`**）；④ DTO `CscaQuestionDetailResponse`（与列表元素**同构** + `subjectCode` / `languageVersion` 两个回读标识）。单测 `CscaQuestionDetailMapperXmlContractTest` 已加（主键绑定 / CSCA 范围 / 不按语言筛 / 不取 `answer`）；文档与实现的细部差异见 [4.4](#44-文档与实现的差异) 第 40 条。

---

### 3.3 逐题作答

#### 3.3.1 PUT /csca/records/{recordId}/answers/{questionId}

##### 接口用处

**作答（一次一题）**。幂等 upsert；`immediate=true` 时**顺手返回判分结果**（对错 + 正确答案 + 解析），支持"刷题即时反馈"。离线场景由客户端排队，联网后走 [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 批量补传。

##### 入参

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `recordId` | Path | Long | **是** | 必须属于当前用户 |
| `questionId` | Path | Long | **是** | 必须属于本次记录的科目 |
| `immediate` | Query | Boolean | 否 | `true` 时响应带 `isCorrect / points / standardAnswer / standardAnswerLabels / analysis`；缺省 `false` |
| Body | Body | Object | **是** | `{ "answer": "B", "clientTime": "1785394500000" }` |

多选作答时 `answer = "A,D"`（**与题库同格式**，逗号分隔、升序）。

##### 返回 JSON（`immediate=false`）

```json
{ "code": 200, "message": "操作成功", "data": { "questionId": "2096765985525108738", "answered": 1, "answeredCount": 13, "lastSavedTime": "1785394500000" } }
```

##### 返回 JSON（`immediate=true`）

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "questionId": "2096765985525108738",
    "answered": 1,
    "userAnswer": "B",
    "isCorrect": 1,
    "points": "2.08",
    "standardAnswer": "B",
    "standardAnswerLabels": ["B"],
    "analysis": "(A) $\\mathbb{N}$ 是自然数集, $\\mathbb{N}=\\{0,1,2,3,\\cdots\\}$, $-1\\notin\\mathbb{N}$…",
    "answeredCount": 13,
    "lastSavedTime": "1785394500000"
  }
}
```

##### 业务逻辑

1. **归属 + 状态校验**：记录属于当前用户、`status IN (0,1)`；已提交（`status=3`）→ `409 RECORD_NOT_IN_PROGRESS(2004)`。
2. **题目归属校验**：`questionId` 必须属于本次记录的**科目范围**（比对 `question.subject_type_mapping` 与记录的 `section` 科目码，join `exam_paper` 校验 `language_version` 一致），否则 `404`。
   - ⚠️ **实现口径（2026-10-13）**：编码只做**科目一致**校验 —— 文档里那句「join `exam_paper` 校验 `language_version` 一致」**落不了地**：`practice_record` **没有语言列**（语言挂在卷上，见 [3.2.1](#321-post-cscarecords)），记录的「语言」无从反查。语言一致性由**建轮时的题集**保证（题集按「科目 × 语言」一次算定）。
   - ⚠️ **未按题集做成员校验**：文档只要求「属于科目范围」，故 `questionId ∈ question_ids` 这一层<u>没有</u>强制（同科目但不在本轮题集里的题仍可作答）。如需更严（不在题集内一律 `404`），说一声即可加（见 [4.4](#44-文档与实现的差异) 第 41 条）。
3. **upsert `practice_answer`**：唯一键 `uk_record_question(practice_record_id, question_id)` 保证了"一题一行"。
   - 写入：`paper_id`（题所属卷 id）、`practice_record_id`、`user_id`、`question_id`、`question_number`（`q.number`）、`section`（`q.section`）、`section_mapping='SEC_CSCA'`、`answer`、`answered=1`、`first_answered_time`（首次写入时）、`last_modified_time=now`
   - **同时写 5 个快照列**（**冻结题面**，2026-10-13 定，见 [3](#3-接口详细设计) 开头；这 5 列早已存在，**不改表**）：

     | 快照列 | 写什么 |
     |---|---|
     | `question_snapshot` | `{ questionId, number, section, layout, typeId, passage, content, score }` —— **题面字段原值**；`typeId` 存**库中题型原名**，回放时再走映射 |
     | `group_snapshot` | `{ startNumber, endNumber, passage }`；**无分组题写 `null`** |
     | `option_snapshot` | `question.option_content` 的解析结果，**与 HSK 同构**（`List<Map<String,Object>>`，单元素，键为选项标签 `A` / `B` / …，**保序**） |
     | `standard_answer_snapshot` | `question.answer` **原值**（与第 4 条判分取的是同一份） |
     | `analysis_snapshot` | `question.analysis` **原值** |

   - ⚠️ **快照只在「首次作答」时写**：`ON DUPLICATE KEY UPDATE` 里**刻意不更新这 5 列** —— 改答案不该改题面（见下方「关键 SQL」）。
4. **判分（`is_correct` / `points` / `standard_answer_snapshot`）**——**先归一化双方答案**（见 [4.2](#42-答案归一化cscaanswernormalizer)），再按**标签集合**比较，**不按 `type_id` 分支**：
   - 集合相等（含单选单标签、多选多标签；`{A,D}` vs `{D,A}` 视为相同）→ `1` + `score`
   - 集合不等（错选 / 漏选 / 多选）→ `2` + `0`
   - **`无` 标准答案 / `answer` 为空** → `is_correct=0`（未评分）、`points=null` —— 🟡 **防御性兜底，当前题库已无此值**（两库实测 0 行，见 [4.2](#42-答案归一化cscaanswernormalizer)）
   - > ⚠️ 判分必须**只看标签集合**，不要写成"单选走 `equals`、多选走集合"——因为实测有 2 题被标成「单选」但答案是 `B,D`（见 [4.1](#41-枚举速查)），按 `type_id` 分支会把它们永远判错。
   - **本次是否写入**取决于 `immediate`：`immediate=false` 时**也写** `is_correct`（避免交卷时再算一遍），只有在**未作答**时才不写
5. **`immediate=true` 时的返回**：`standardAnswer` / `analysis` **取刚写入的快照**（`standard_answer_snapshot` / `analysis_snapshot` = 作答那一刻的标准答案与解析）—— ⚠️ **不做归一化、原值直传**（2026-10-13 定，与 [3.3.3](#333-get-cscaquestionsquestionidsolution) 第 1 条**同口径**；`无` / `NULL` 同样特判为 `null`）。**这个字段是"答案出口"，仅本接口与 [3.3.3](#333-get-cscaquestionsquestionidsolution) 允许返回答案。**
   - 🆕 **`standardAnswerLabels`**（2026-10-13 新增）：与 [3.3.3](#333-get-cscaquestionsquestionidsolution) 的同名字段**完全同口径** —— 由 `standardAnswer` **原值切分**（按 `,` / `，` / `;` / `；` / `/` / `、` / 空白切 → 丢空串 → **保序**；**不** trim 单标签、**不**转大写、**不**去「答案」、**不**去重、**不**排序），供前端高亮 / 比对；`无` / `NULL` / 空白 → **空数组**（与 `standardAnswer` 一起特判）。⚠️ 前端**别拿它当「判分标准」** —— 判分一律以 `isCorrect` 为准（按标签集合、多选全对才算对）。
   - ⚠️ **两个键的出现规则**（本响应带 `@JsonInclude(NON_NULL)`，两种"没有值"的语义不同）：`immediate=false`（不在判分形态）→ `standardAnswer` / `standardAnswerLabels` **均缺席**；`immediate=true` 但该题**无标准答案** → `standardAnswer` **缺席**、`standardAnswerLabels = []`。
6. **乐观锁**：`practice_record.version` 每次保存 +1；冲突 → `409`。
7. **同步错题本**（2026-10-13 定，2026-10-19 修订）：按本次判分结果**附随更新** `csca_question_wrong` —— 判**错** → 收录（`deleted=0`）；判**对** → **不动**（🔴 2026-10-19 起取消「自动移出」，错题本「只进不出」，见 [4.4](#44-文档与实现的差异) 第 62 条）；**未评分（`is_correct=0`）不动**。⚠️ 这是判分的**附随动作**，**不改本接口返回体**；规则见 [3.6.2](#362-错题本wrong-book) 第 1 条。🆕 **携带轮次 + 语言快照**：写表时一并写 `practice_record_id` = 本接口路径上的 `recordId`、`language_version` = `question.getLanguageVersion()`（均沿用「首次落值、不覆盖」口径，[3.6.2](#362-错题本wrong-book) 第 11 / 14 条）。
   - ✅ **已实现（2026-10-14，2026-10-19 调整）**：调用 `CscaWrongBookService#syncAfterGrade(userId, List.of(new CscaWrongBookSyncItem(questionId, grade.isCorrect(), question.getSubjectTypeMapping(), question.getLanguageVersion(), userAnswer)), record.getId())` —— 判错收录 / **判对与未评分均不动**（[3.6.2](#362-错题本wrong-book) 第 1 条；判对自动移出已于 2026-10-19 取消，见 [4.4](#44-文档与实现的差异) 第 62 条）。🟡 **2026-10-19 起第 5 位带用户答案**（写 `user_answer` 快照），且**单题便捷重载已删除**（第 69 条）—— 逐题 / 批量 / 交卷统一走「传 `List` 的一入口」。⚠️ 支撑表 `csca_question_wrong` **TEST 已建表（2026-10-14、2026-10-19 改名 + 加列）**、⚠️ **PROD 未建**（文末「附 6」）→ PROD 上线前补建，否则本步会报 `Table doesn't exist`。见 [4.4](#44-文档与实现的差异) 第 41 / 61 / 62 / 66 / 69 条。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaRecordController#saveAnswer(String recordId, String questionId, Boolean immediate, CscaAnswerSaveRequest, HttpServletRequest, @RequestHeader X-Client-Type)` | 路径绑定（**`String` + 手工解析**，非数字 → `8005`，同 [3.2.3](#323-get-cscaquestionsquestionid)）+ 强鉴权 |
| Service | `CscaAnswerService#save(Long userId, Long recordId, Long questionId, CscaAnswerSaveRequest, boolean immediate)` | 校验 + upsert + 判分 + 记录进度 |
| Service | `csca/service/CscaGradingService#grade(String standardAnswer, String userAnswer, String score)` | 判分（**入参是标准答案字符串**，非题目实体：可传 `question.answer` 或 `standard_answer_snapshot`；返回 `GradeResult{isCorrect, points}`） |
| Mapper | `csca/mapper/CscaAnswerMapper#upsertAnswer` / `#selectAnsweredCount` | 作答 upsert（**写齐 5 个快照列**）/ 已答题数统计 |
| Mapper | `csca/mapper/CscaQuestionMapper#selectForAnswer(questionId)` | 作答用取题（**唯一**会读 `q.answer` / `q.analysis` 的查询；一次带出组材料三列） |
| Mapper | `PracticeRecordMapper#selectByIdForUpdate` / `#updateById` | 记录行锁 + 归属 + 状态；`answered_count` / `version`（**复用共享实体上的 `@Version` 乐观锁**，与 HSK 听力 / 阅读同一机制） |
| 支撑 | `csca/support/CscaAnswerNormalizer` | 归一化 + 标签集合比较（**判分专用**）；答案出口只用 `splitRaw` |
| 支撑 | `csca/support/CscaSnapshotWriter` | 5 个快照列的**写侧**（与读侧 `CscaSnapshotSupport` 键名严格配对） |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `practice_record` | SELECT + UPDATE | `status` / `version`（乐观锁 +1）/ `answered_count`（实时重算）/ `last_saved_time` / `current_question_id` / `current_question_number` |
| `practice_answer` | **INSERT … ON DUPLICATE KEY UPDATE** | 见第 3 条 |
| `question` / `exam_paper` / `question_group` | SELECT | `answer` / `analysis` / `score` / `number` / `section` / `layout` / `type_id` / 科目校验 / 组材料 |
| `csca_question_wrong`（新增） | INSERT … ON DUPLICATE KEY UPDATE | 按判分结果收录（[3.6.2](#362-错题本wrong-book) 第 1 条）—— ✅ **已接线（2026-10-14）**：判错走 `upsertWrongs`；判对**不写**（2026-10-19 取消自动移出，原 `markRemoved` 已删除，[4.4](#44-文档与实现的差异) 第 62 条）（⚠️ 表 PROD 未建，见第 7 条） |

##### 数据流向

```
① 入参    recordId / questionId / answer / immediate
② 查库    practice_record(user_id=?, status IN(0,1))  ──不满足则 404 / 409
          question ⋈ exam_paper  ──科目归属校验──→ 题行（含 answer / score）
③ 加工    CscaGradingService.grade() ──→ isCorrect, points
          CscaAnswerNormalizer.normalize(userAnswer) 与 normalize(standardAnswer) 集合比较
④ 组装    upsert practice_answer → 更新 record.version → Response
```

**关键 SQL**

```sql
INSERT INTO practice_answer
  (id, paper_id, practice_record_id, user_id, question_id, question_number, section,
   section_mapping, answer, answered, is_correct, points,
   question_snapshot, group_snapshot, option_snapshot, standard_answer_snapshot, analysis_snapshot,
   first_answered_time, last_modified_time, deleted, created_time, updated_time)
VALUES
  (?, ?, ?, ?, ?, ?, ?, 'SEC_CSCA', ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
ON DUPLICATE KEY UPDATE
  answer               = VALUES(answer),
  answered             = 1,
  is_correct           = VALUES(is_correct),
  points               = VALUES(points),
  last_modified_time   = VALUES(last_modified_time);
-- ⚠️ 5 个快照列刻意不出现在 UPDATE 子句里：题面以「首次作答」为准，改答案不改题面
```

> ⚠️ **多选题必须按"集合相等"判分，不能字符串比较**。`exam-service` 现有 `submitCscaExam` 用的是 `correctAnswer.equalsIgnoreCase(userAnswerContent)`（`ExamRecordServiceImpl:589`），**多选题只要是这个比对方式就永远判错**（题库里多选答案是 `A,D` 这种）。本模块要**独立实现正确判分**，不要去复用那段逻辑。这是本次设计发现的一处**存量缺陷**（见 [4.4](#44-文档与实现的差异) 第 3 条）。
> ⚠️ `uk_record_question(practice_record_id, question_id)` 是**唯一键**，所以 upsert 必须用 `ON DUPLICATE KEY UPDATE` 或先查后写；**不要**直接 `INSERT`（重复作答会 1062）。
> ⚠️ `practice_answer.section` 存 `q.section`（数字字符串 `"1"`–`"6"`），`section_mapping` 存常量 `'SEC_CSCA'`。**两个都必填**（`section_mapping` NOT NULL）。
> ⚠️ `practice_answer.paper_id` / `question_number` **NOT NULL**：`paper_id` 取**题所属卷的真实 id**（`question.paper_id`，**不是**记录上的哨兵 `0`），`question_number` 取 `q.number`。

> ✅ **已实现（2026-10-13）**：① Controller `CscaRecordController#saveAnswer`（强鉴权 + **手工解析**两个路径变量）；② Service `CscaAnswerService#save`（记录行锁 + 归属/状态 → 题目归属 → 判分 → upsert → 进度 → 组装）；③ **判分独立实现**：`csca/service/CscaGradingService`(+`impl`) + `csca/support/CscaAnswerNormalizer`（§4.2 七步；`normalize` / `labels` / `sameLabels` 供判分，`splitRaw` 供答案出口；**不复用** `exam-service` 的 `equalsIgnoreCase`）；④ **快照写侧** `csca/support/CscaSnapshotWriter`（与读侧 `CscaSnapshotSupport` **键名严格配对**，改一个必须改另一个）；⑤ Mapper `CscaAnswerMapper#upsertAnswer` / `#selectAnsweredCount`、`CscaQuestionMapper#selectForAnswer`（**唯一**读 `q.answer` / `q.analysis` 的查询，一次带出组材料）；⑥ 单测 `CscaAnswerNormalizerTest` / `CscaGradingServiceImplTest` / `CscaAnswerMapperXmlContractTest`（钉住「快照只写一次」「答案不进内容接口」「统计必带 `SEC_CSCA`」）。⚠️ 与文档的细部差异（**错题本同步未实现**、快照 `option_snapshot` 键名、`;` 也作分隔符、记录更新走共享 Mapper）见 [4.4](#44-文档与实现的差异) 第 41 条。

---

#### 3.3.2 POST /csca/records/{recordId}/answers/batch

##### 接口用处

**批量上报作答**（离线补传，幂等）。前端断网期间把作答写本地队列，联网后一次性补传，服务端逐条 upsert + 判分。

##### 入参

**`recordId` 走 Path**（`/csca/records/{recordId}/answers/batch`），Body 只带 `items[]`：

```json
{
  "items": [
    { "questionId": "2096765985525108738", "answer": "B", "clientTime": "1785394500000" },
    { "questionId": "2096765985525108739", "answer": "C", "clientTime": "1785394510000" },
    { "questionId": "2097000000000000009", "answer": "A,D", "clientTime": "1785394520000" }
  ]
}
```

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `recordId` | **Path** | Long | **是** | 目标记录（必须属于当前用户、未提交）；从 URL 取，**不写在 Body** |
| `items[]` | Body | Array | **是** | 上限 **200** 条；超限 → `400` |
| `items[].questionId` | Body | Long | **是** | 不属于该记录科目 → 该条**跳过并 warn**（不整批打回） |
| `items[].answer` | Body | String | **是** | 与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 同格式 |
| `items[].clientTime` | Body | Long | 否 | 客户端作答时间（毫秒），用于 `first_answered_time` |

##### 返回 JSON

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": "2097000000000000001",
    "accepted": 2,
    "skipped": 1,
    "answeredCount": 15,
    "lastSavedTime": "1785394520000",
    "skippedItems": [ { "questionId": "2097000000000000009", "reason": "NOT_IN_SUBJECT" } ]
  }
}
```

##### 业务逻辑

1. **单事务批量 upsert**：`ON DUPLICATE KEY UPDATE`（同 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid)）；**同样写 5 个快照列**（冻结题面）—— 离线补传的题面以**服务端当前读到的那一版**为准（客户端离线队列里不存题面）。
2. **个别非法项跳过 + warn，不整批打回**（与写字课 `ids` 口径一致）：`questionId` 不在本次科目范围 → 跳过，计入 `skippedItems`。
3. **判分**：与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 同一套 `CscaGradingService`。
4. **冲突合并**：同题已有答案时，按 **`last_modified_time` 新的胜出**（离线补传的 `clientTime` 早于服务端已有答案 → 保留服务端值，**先写的不丢**）。**不用 `clientTime` 直接覆盖**服务端时间戳（客户端时钟不可信）；`clientTime` 只用于 `first_answered_time` 的兜底。
5. 记录已提交（`status=3`）→ `409`。
6. **同步错题本**：与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条同一套规则（逐条按判分结果：**判错收录，判对与未评分不动** —— 2026-10-19 取消自动移出，[4.4](#44-文档与实现的差异) 第 62 条）。🆕 同样**携带轮次快照** `record_id` = 本接口路径上的 `recordId`（[3.6.2](#362-错题本wrong-book) 第 11 条）。✅ **已实现（2026-10-14）**：第 ⑨ 步对**真正写入的 winners** 调 `syncAfterGrade`（被跳过的条目没改判分，不动错题本）。🟡 2026-10-19 起同一项还带**用户答案**（= 该条补传的 `answer`，写 `user_answer` 快照，[4.4](#44-文档与实现的差异) 第 69 条）。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaRecordController#batchAnswers(String recordId, CscaBatchAnswerRequest, HttpServletRequest, @RequestHeader X-Client-Type)` | 路径绑定（**`String` + 手工解析**，非数字 → `8005`，同 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid)）+ 强鉴权；`@RequestBody(required=false)` —— 缺 Body 交给 Service 回 `8005`（不落成 common 的「请求体格式错误」） |
| Service | `CscaAnswerService#batchReport(Long userId, Long recordId, CscaBatchAnswerRequest)` | 条数校验 → 记录行锁 → 批内去重 → 逐条字段/科目校验（跳过 + warn）→ **冲突合并** → 判分 → 批量 upsert → 记录进度 |
| Mapper | `CscaAnswerMapper#batchUpsertAnswers` / `#selectAnswerTimes` | **一条 SQL** 多值 `ON DUPLICATE KEY UPDATE`（同 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 的 5 快照列口径）/ 取「服务端已有作答的最后修改时间」（冲突合并用） |
| Mapper | `CscaQuestionMapper#selectForAnswerBatch` | 批量取题：**与 `selectForAnswer` 共用同一份列 / join / 准入**（否则批量补传写出的 `group_snapshot` 会静默为空） |
| Mapper | `PracticeRecordMapper#selectByIdForUpdate` / `#updateById` | 记录行锁 + 归属 + 状态；`answered_count` / `version`（**复用共享实体上的 `@Version` 乐观锁**） |
| 支撑 | `csca/support/CscaBatchAnswerPlanner` | **纯函数**：条数上限 / 批内去重 / 冲突合并判定（只在批量接口成立的三条口径，便于单测钉死） |
| 支撑 | `csca/support/CscaBatchSkipReason` | 跳过原因枚举（`skippedItems[].reason` 的取值域，见第 2 条 / 文末 ✅ 段） |
| 支撑 | `csca/service/CscaGradingService` | 判分（与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) **同一个**，不另起一套） |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `practice_answer` | INSERT … ON DUPLICATE KEY UPDATE | 同 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) |
| `question` / `exam_paper` | SELECT | 答案 / 科目归属 |
| `practice_record` | UPDATE | `version` / `answered_count` |
| `csca_question_wrong`（新增） | INSERT … ON DUPLICATE KEY UPDATE | 逐条按判分结果收录（判对不动，见第 6 条）—— ✅ **已接线（2026-10-14）** |

##### 数据流向

```
① 入参    Path recordId + Body items[]（≤200）
② 查库    practice_record（归属 + 未提交，FOR UPDATE 行锁）
          question ⋈ exam_paper（一次 SQL 批量取题 + 科目校验）
          practice_answer（这批题「已有作答的最后修改时间」—— 冲突合并用）
③ 加工    批内去重 → 逐条字段/科目校验（非法项 skip+warn）→ 冲突合并（服务端更新则 skip）
          → 逐条 normalize + grade → 一条 SQL 批量 upsert
④ 组装    CscaBatchAnswerResponse { accepted, skipped, skippedItems[] }（accepted + skipped == items.length）
```

> ⚠️ **批量 upsert 必须走单条 SQL + `CASE WHEN` / `ON DUPLICATE KEY UPDATE`，不要用 `executemany` 逐条写**（本仓库踩过"批量写库产生僵尸事务持锁 → 1205"的坑）。200 条一次 SQL 即可。
> ⚠️ 与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 的分工：**在线逐题走 [3.3.1]，离线补传走本接口**。两者写的是同一张表、走同一个判分器，**不要各自实现一套判分**。

> ✅ **已实现（2026-10-13）**：① Controller `CscaRecordController#batchAnswers`（强鉴权 + 手工解析路径变量 + `@RequestBody(required=false)`）；② Service `CscaAnswerService#batchReport`：条数校验 → `selectByIdForUpdate` 行锁 + 归属 + `status IN (0,1)`（否则 `409 RECORD_NOT_IN_PROGRESS`）→ 批内去重 → 逐条字段 / 科目校验（**跳过 + warn，不整批打回**）→ **冲突合并** → 判分 → **一条 SQL** 批量 upsert → `answered_count` 重算 + `@Version`（冲突 `409 RECORD_VERSION_CONFLICT`）；③ **与 3.3.1 共用四段**（`loadInProgressRecord` / `requireSameSubject` / `buildAnswerRow` / `CscaGradingService`）—— 快照 5 列、判分、行锁、乐观锁**只有一份实现**；④ Mapper：`CscaAnswerMapper#batchUpsertAnswers`（foreach 单条多值 INSERT）+ `#selectAnswerTimes`（冲突合并，带 `SEC_CSCA`）、`CscaQuestionMapper#selectForAnswerBatch`（与 `selectForAnswer` 共用 `<sql>` 片段）；⑤ 纯函数 `csca/support/CscaBatchAnswerPlanner`（上限 / 去重 / 冲突判定）+ 枚举 `csca/support/CscaBatchSkipReason`；⑥ 单测 `CscaBatchAnswerPlannerTest`(6) / `CscaBatchAnswerMapperXmlContractTest`(5) / `CscaBatchAnswerServiceImplTest`(9)（Mockito，钉住 `accepted + skipped == items.length` 与「服务端更新不被冲掉」）。⚠️ 与文档的细部差异（**跳过原因扩充为 5 类**、`current_question_id` 不更新、冲突合并用 `clientTime` 比对、全跳过不写记录）见 [4.4](#44-文档与实现的差异) 第 42 条。

---

#### 3.3.3 GET /csca/questions/{questionId}/solution

##### 接口用处

**标准答案 + 解析**。用途：**背题模式**——**不判分、直接揭示答案与解析**（对应原型左上角的「背题模式」开关）；回答过的题目展示答案。

> 📌 **背题模式能成立，是因为本接口只要求"登录"、不要求"已作答"**（2026-10-13 起本接口随题目类接口一并改为强鉴权，但**不校验是否答过**）。若产品进一步要求"必须先作答才能看答案"，背题模式就会失效——见 [4.3](#43-待确认事项) 第 3 条。
> 🔴 **背题模式不换题集**：它只是答题页顶栏的一个开关，**题目列表、题序、`availableCount` 全都不变**（列表仍来自 [3.2.2](#322-get-cscaquestions) 的那份固定题集），切换时**不要重拉列表**，只对当前题调本接口即可。原「带 `includeAnswered=true` 忽略题集取科目全量」的做法**已删除**（§4.4 第 36 条）—— 它会让切模式变成换整套题单。

##### 入参

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| Token | Header | String | **是** | 题目接口统一强鉴权（见 [0.2](#02-鉴权与客户端类型)）；未登录 → `401` |
| `questionId` | Path | Long | **是** | 同 [3.2.3](#323-get-cscaquestionsquestionid) |

##### 返回 JSON

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "questionId": "2096765985525108738",
    "typeId": "SINGLE",
    "standardAnswer": "B",
    "standardAnswerLabels": ["B"],
    "analysis": "(A) $\\mathbb{N}$ 是自然数集, $\\mathbb{N}=\\{0,1,2,3,\\cdots\\}$, $-1\\notin\\mathbb{N}$\n(B) $\\mathbb{Z}$ 是整数集…",
    "score": "2.08"
  }
}
```

`MULTI` 示例（`CSCA_化学题库2026-6-4_03_97-144` 第 2 题）：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "questionId": "2067118969118662658",
    "typeId": "MULTI",
    "standardAnswer": "A,D",
    "standardAnswerLabels": ["A", "D"],
    "analysis": "侯氏制碱法的发明者是侯德榜，A 正确；「碱」指纯碱（$Na_2CO_3$）而非氢氧化钠，B 错误…",
    "score": "2.08"
  }
}
```

##### 业务逻辑

1. 🔴 **本接口不做答案归一化（2026-10-13 定）**：`standardAnswer` = `question.answer` **原文直传** —— 不 trim、不去尾标点、不去「答案」二字、不转大写、不排序、不重新拼接。
   - 归一化（[4.2](#42-答案归一化cscaanswernormalizer)）**只服务判分**，不作用于任何「答案出口」。
   - 因此库里的脏值会**原样**下发：实测 `"D\n答案"` 1 行、`"D."` 1 行 —— 前端若要做高亮 / 比对，请自行容错（属题库数据问题，见 [4.4](#44-文档与实现的差异) 第 9 条）。
   - `standardAnswerLabels` **仍下发**，但**只按分隔符切分、不做任何其他加工**：按 `,` / `，` / `/` / `、` / 空白 切 → **丢弃空串** → **保序**（**不** trim 单个标签、**不**转大写、**不**去「答案」、**不**去重、**不**排序）。
   - 例：`"A,D"` → `["A","D"]`；`"D\n答案"` → `["D","答案"]`（脏值原样呈现）。
2. **`standardAnswerLabels`** 是**按原文切分**的标签数组（前端高亮 / 比对用），`standardAnswer` 是**库中原值**（见第 1 条），二者**同源**。⚠️ 前端**别拿 labels 当「判分标准」** —— 判分一律以服务端 `is_correct` 为准（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 4 条）。
3. **`analysis` 实测全部非空**（1904/1904，平均 88.7 字符、最大 1088），可直接下发。**但要注意两件事**：
   - 解析里同样是 **LaTeX 原文**（`$\because A=\{x\in\mathbb{Z}|...\}$`），与题干一样需要客户端渲染；
   - 文科/理科中文的解析里有 **OCR 残留的拼音插空格**（如 `"着"读作zh á o`、`读y ī ng`），**属数据质量问题**，服务端**不做清洗**（清洗会改原文，见 [4.4](#44-文档与实现的差异) 第 2 条）。
   仍保留"`analysis` 可为 `null`"的容错（若将来导入的卷缺解析）。
4. **异常答案值**：`answer` 为 `无` 或 `NULL` 时（🟡 **防御性特判，当前两库实测 0 行**）视为**无标准答案** → `standardAnswer = null`、`standardAnswerLabels = []`，且**该题判分时置"未评分"而不是判错**（见 [3.5.1](#351-post-cscarecordsrecordidsubmit)）。⚠️ 这是「原值直传」口径下**唯一的特判**（其余脏值一律原样透出）。**保留纯为兜底** —— 两库 CSCA 1904 题实测 `answer` 全为 `A`–`F` 单/多标签、`无` / 空 = 0 行（[4.2](#42-答案归一化cscaanswernormalizer)）。
5. **本接口必须登录**（2026-10-13 起题目接口统一强鉴权，见 [0.2](#02-鉴权与客户端类型)）：未登录 → `401`。**但只校验"登录"、不校验"是否已作答"** —— 这是背题模式成立的前提。缓存风险见 [0.6](#06-枚举与版本号)。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaCatalogController#solution(String questionId, HttpServletRequest request, @RequestHeader X-Client-Type)` | 路径绑定（**声明 String 后手工解析**）+ 强鉴权 |
| Service | `CscaQuestionQueryService#solution(Long questionId)` | 准入 + 组装（**原值直传，不归一化**） |
| Mapper | `CscaQuestionMapper#selectSolution(questionId)` | 只取 `answer` / `analysis` / `score` / `type_id` |
| 支撑 | `csca/support/CscaAnswerNormalizer#splitRaw` | **只按分隔符切分**（供答案出口）；`normalize` / 集合比较**仅供判分**（[4.2](#42-答案归一化cscaanswernormalizer)） |
| DTO | `dto/CscaSolutionResponse#of(CscaSolutionRow)` | 组装出口（**原值直传** + 「无标准答案」唯一特判） |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `question` / `exam_paper` | SELECT | `answer` / `analysis` / `score` / `type_id` / `exam_type` |

##### 数据流向

```
① 入参    questionId（+ token）──未登录 401
② 查库    question ⋈ exam_paper ──准入 exam_type=2──→ answer / analysis / score / type_id
③ 加工    原值直传（不做归一化）：standardAnswer = answer 原文；standardAnswerLabels = splitRaw(answer)
          answer = '无' / NULL → { null, [] }
④ 组装    CscaSolutionResponse
```

> ✅ **已实现（2026-10-13）**：`CscaCatalogController#solution`（强鉴权 + **手工解析路径变量**，非数字 → `8005`）/ `CscaQuestionQueryService#solution`（准入 `null` → `8006`）/ `CscaSolutionResponse#of`（**原值直传** + 唯一特判）/ `CscaQuestionMapper#selectSolution`(+`.xml`，只取 4 列，include `cscaPaperBase` + `cscaQuestionValid`，**不按语言筛**、**不带题面**)/ `dto/CscaSolutionRow`;
> 单测 `CscaSolutionResponseTest`（原值直传 / labels 保序不去重 / 脏值原样 / 无答案特判）+ `CscaSolutionMapperXmlContractTest`（主键绑定 / 读答案 / 不带题面 / CSCA 准入 + 不按语言筛）→ **Tests run: 11, Failures: 0**；文档与实现的细部差异见 [4.4](#44-文档与实现的差异) 第 43 条。

> ⚠️ **这个接口是"答案出口"，必须与内容接口严格分开**：如果把 `answer` 塞进 `/csca/questions` 的响应，整个内容缓存（IndexedDB）就变成"带答案的题库"，等于把答案发给所有人。**这是本模块最容易被后来人"顺手加个字段"破坏的地方**，编码时请在 `CscaQuestionResponse` 上留注释。

---

### 3.4 练习态与答题卡

#### 3.4.1 GET /csca/records/{recordId}

##### 接口用处

**练习态**：返回当前记录的进度（已答/未答/对错/正确率）、上次停在哪、是否是草稿。用于"继续练习"与断点恢复。

> 📌 **本接口给的是「这一轮」的进度**（按 `recordId` 统计）；[3.1.1](#311-get-cscacatalog) 的科目卡进度是「**最新一轮**」的进度。**当 `recordId` 恰是最新那一轮时两者相等**；查历史轮次时，本接口给的是那一轮当时的数（科目卡不会跟着变）。

##### 入参

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `recordId` | Path | Long | **是** | 查不到 / 非当前用户 → `404` |

##### 返回 JSON

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": "2097000000000000001",
    "subjectCode": "math",
    "practiceName": "CSCA · 数学",
    "status": 1,
    "totalQuestions": 432,
    "answeredCount": 20,
    "correctCount": 17,
    "wrongCount": 3,
    "unGradedCount": 0,
    "accuracyRate": 85.00,
    "currentQuestionId": "2096765985525108742",
    "currentQuestionNumber": 5,
    "startTime": "1785394374000",
    "lastSavedTime": "1785394500000",
    "durationSeconds": 726
  }
}
```

##### 业务逻辑

1. **归属校验**：`record.section_mapping = 'SEC_CSCA' AND record.user_id = token.userId`，否则 `404`（**不返回 403**，避免暴露"记录存在但不属于你"）。
2. `answeredCount` / `correctCount` / `wrongCount` 由 `practice_answer` **实时 count**（记录未提交时 `record.correct_count` 还是 0，只有提交后才回填缓存列）。
3. `unGradedCount` = `is_correct = 0` 的已答行数（`无` 标准答案的题）—— 🟡 **防御性字段，当前恒为 `0`**：两库 CSCA 1904 题实测已无 `无` / 空标准答案（见 [4.2](#42-答案归一化cscaanswernormalizer) 判分表下方注记）；保留只为防题库回潮时把脏值判成「错题」。
4. `accuracyRate` = `correctCount / answeredCount × 100`（**分母是"已作答"**，与 [3.1.1](#311-get-cscacatalog) 同一定义；未评分题计入分母），保留 2 位。
5. `durationSeconds` = `now - start_time`（记录未提交时）；提交后取 `record.duration_seconds`（冻结值）。
   - ⚠️ **实现口径（2026-10-14）**：已提交但 `duration_seconds` 为 `null`（老数据 / 提交链路早期写入的行）时**回落实时计算**（`now - start_time`），而不是回 `null` / `0` —— 保证前端拿到的恒是一个有意义的数；`start_time` 缺失、或时钟回拨（`now < start_time`）→ `0`（**不回负数**）。✅ 提交链路 [3.5.1](#351-post-cscarecordsrecordidsubmit) **已编码（2026-10-14）**，新交卷的记录 `duration_seconds` 会被写实，此回落只为兜住历史行。
   - ⚠️ **不限制记录状态**：已放弃（`2`）/ 已提交（`3`）的轮次**同样可查**（本接口是只读的「这一轮」进度，看历史轮次靠它）；与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid)（作答链路要求 `status IN (0,1)`）**不是一回事**。
6. `totalQuestions` = **该记录题集的大小**（`question_ids` 的长度 = 建轮时算定的剩余未练 / `restart=true` 时的科目全量，**不截断**），与 [3.2.2](#322-get-cscaquestions) 的 `availableCount`（传 `recordId` 时）**同源同值**。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaRecordController#detail(Long recordId, HttpServletRequest)` | 强鉴权 |
| Service | `CscaRecordService#detail(Long userId, Long recordId)` | 归属校验 + 实时统计 |
| Mapper | `CscaRecordMapper` / `CscaAnswerMapper#countByRecord` | 记录 + 统计 |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `practice_record` | SELECT | 记录列 |
| `practice_answer` | SELECT（聚合） | `practice_record_id` / `answered` / `is_correct` |

##### 数据流向

```
① 入参    recordId + token.userId
② 查库    practice_record(section_mapping='SEC_CSCA', user_id=?, id=?) ──→ 1 行 / 否则 404
          practice_answer ──COUNT / SUM(is_correct)──→ 统计
③ 加工    accuracyRate = correct / (correct+wrong)
④ 组装    CscaRecordResponse
```

---

#### 3.4.2 GET /csca/records/{recordId}/answer-card

##### 接口用处

**答题卡**：对应原型右上角「答题卡」抽屉——一次性给出**顶部四个统计**（总题数 / 答对 / 答错 / 未答）+ **逐题状态**（答没答、对没对、是否收藏、题号、题型），用于练习中的进度条、交卷前检查、错题与收藏跳转。

##### 入参

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `recordId` | Path | Long | **是** | 归属校验 |
| `withGroup` | Query | Boolean | 否 | `true` 时附带"按题型汇总"（缺省 `true`） |

##### 返回 JSON

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": "2097000000000000001",
    "subjectCode": "math",
    "totalQuestions": 432,
    "answeredCount": 20,
    "correctCount": 17,
    "wrongCount": 3,
    "unansweredCount": 412,
    "unGradedCount": 0,
    "favoriteCount": 2,
    "cards": [
      { "questionId": "2096765985525108738", "seq": 1, "number": 1, "typeId": "SINGLE", "answered": 1, "isCorrect": 1, "favorite": true },
      { "questionId": "2096765985525108739", "seq": 2, "number": 2, "typeId": "SINGLE", "answered": 1, "isCorrect": 2, "favorite": false },
      { "questionId": "2096765985525108740", "seq": 3, "number": 3, "typeId": "SINGLE", "answered": 0, "isCorrect": 0, "favorite": false }
    ],
    "byType": [
      { "typeId": "SINGLE", "total": 432, "answered": 20, "correct": 17, "accuracyRate": 85.00 }
    ]
  }
}
```

- `seq` = **会话内序号**（= 前端显示的题号，原型 `idx+1`）；`number` = 题库内原题号。**开了乱序（`shuffle=true`）时二者不同**，`seq` 按本次题集顺序（`shuffle` + `seed`）在 Java 侧递增编号；答题卡网格请用 `seq`。缺省自然序时 `seq` 与 `number` 同序。
- `unansweredCount` = `totalQuestions - answeredCount`（对应原型「未答」）
- `favorite` = 该题是否被当前用户收藏（[3.6.1](#361-收藏favorite)）—— ✅ **收藏已落库（2026-10-13），本字段恒下发**（前端不再用本地态兜）
- 前端配色（对齐原型）：`isCorrect=1` → 绿、`=2` → 红、未答 → 灰、`favorite=true` → ★、当前题 → 描边

##### 业务逻辑

1. **本题集从哪来**：直接取 **`practice_record.question_ids`**（**建轮时算定的固定题集**，[3.2.1](#321-post-cscarecords) 第 4 条），因此 `cards` 由 **"该题集" LEFT JOIN `practice_answer`** 得到：
   - ⚠️ **不要再"按规则重算题集"**（旧写法）：题集已落库，重算会与建轮时那份漂移（题库改动 / 期间作答都会影响结果）。**本次已答的题本来就在题集内**，答题卡不会越刷越短，`totalQuestions` 恒等于建记录时算的值。
   - `LEFT JOIN practice_answer ON practice_answer.practice_record_id = ? AND practice_answer.question_id = q.id`
   - 未作答的题 `answered=0 / isCorrect=0`
   - `seq` 按题集顺序（自然序；或 `shuffle` + `seed` 的乱序）在 Java 侧递增编号
     - ⚠️ **实现口径（2026-10-14，已编码）**：本接口**没有** `shuffle` / `seed` 入参，`practice_record` 也**不落库**乱序参数 → 可实现的只有 **`seq` = 题集自然序下标 + 1**（建轮写入 `question_ids` 的顺序）。**后果**：练习若以 `shuffle=true` 开始，答题卡的 `seq` 与答题页题序**不一致**（题集内容仍一致、`totalQuestions` 不变）。**要修需二选一**：① 答题卡补 `shuffle` / `seed` 入参（推荐，零改表）；② 把乱序参数落库到 `practice_record`（**要改表**）。见 [4.4](#44-文档与实现的差异) 第 46 条
2. **`byType`**：按 **`typeId` 映射值**（`SINGLE` / `MULTI`）聚合，**在 Java 侧分组**，不用 `GROUP BY`（题集是**动态 id 集合**，SQL 里不好聚合）。⚠️ 映射只有两值 → `byType` **最多 2 行**：文科 / 理科中文的题全映射为 `SINGLE`（只有 1 行），只有物理 / 化学会出现 `MULTI` 行（见 [4.1](#41-枚举速查)）。
3. `isCorrect` **一律读 `practice_answer` 的冻结值**（作答时就已判分并落库，见 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 4 条）—— **无"实时重算"分支**（2026-10-13 冻结题面后，判分结果随快照一起冻结）。
4. `totalQuestions` 取 `record.total_questions`（= **建轮时算定的题集大小**，与 `JSON_LENGTH(question_ids)` 相等；[3.2.1](#321-post-cscarecords) 第 4 条）—— 题集固定后**不存在"重算题集"**，不再需要 `MIN(...)` 兜底。
5. `unansweredCount` = `totalQuestions - answeredCount`（**不等于 `unGradedCount`**：未评分是"已答但无标准答案"，未答是"没作答"）。
   - ⚠️ **实现口径（2026-10-14，已编码）**：`answeredCount` / `correctCount` / `wrongCount` / `unGradedCount` **四个数一律由 `cards[]` 现场汇总**（= 题集 ⋈ 作答），**不是**按 `recordId` 对 `practice_answer` 全量 `COUNT`（那是 [3.4.1](#341-get-cscarecordsrecordid) 的 `countByRecord`）—— 这样才能保证**顶部统计与网格同源同值**、且 `unansweredCount` **恒非负**。代价：记录里若存在「不属于本记录题集」的作答行（作答链路只校验科目、**不校验题集成员**），本接口的数会比 [3.4.1](#341-get-cscarecordsrecordid) **少那几行** —— 见 [4.4](#44-文档与实现的差异) 第 46 条。
6. `favorite` / `favoriteCount`：**批量查 `csca_question_favorite`** —— `WHERE user_id=? AND deleted=0 AND question_id IN (本页题集 id)`（每页 1 次查询；2026-10-13 起收藏落库，**不再"整段省略"**）。
   - ⚠️ `favoriteCount` 只统计**本次题集内**的收藏（用户在别处收藏、不属于本次题集的题**不计入**）。
   - ✅ **前置条件已满足（TEST，2026-10-14 建表）**：该表 **TEST 已建**（文末「附 5」）→ TEST 可直接调用；⚠️ **PROD 未建**，上线前必须补，否则生产调本接口会在这一步失败（`Table doesn't exist`）。读侧 SQL 已按本节口径编码（`CscaFavoriteMapper#selectFavoritedQuestionIds`，[3.6.1](#361-收藏favorite) 编码时复用同一 Mapper）。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaRecordController#answerCard(Long recordId, Boolean withGroup, HttpServletRequest)` | 强鉴权（`withGroup` 缺省 `true`） |
| Service | `CscaAnswerService#answerCard(Long userId, Long recordId, boolean withGroup)` | 读记录题集（`question_ids`）+ join 答案 + 收藏 + 汇总 / 分组 |
| Mapper | `CscaQuestionMapper#selectCardQuestions` / `CscaAnswerMapper#selectByRecord` / `CscaFavoriteMapper#selectFavoritedQuestionIds` | 题号 + 题型 / 答案状态明细 / 收藏（**各 1 次查询**） |

> ⚠️ **取题不是 `selectByQuestionIds`**：那个要 `languageVersion`（本接口**无**语言入参）且带分页 / 排序 / `shuffle`。答题卡用 `selectCardQuestions` —— **不分页、不排序、不限语言**（题集在建轮时已是「科目 × 语言」内的题），只回 `id` / `number` / `type_id`；**顺序由 Service 按题集原序还原**（`seq` 才有意义），SQL 里的顺序会被丢掉。

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `practice_record` / `practice_answer` / `question` / `exam_paper` | SELECT | 见数据流向（题集来自 `practice_record.question_ids`；`practice_answer` 只做**答案 join**，**不再参与去重**） |

##### 数据流向

```
① 入参    recordId
② 查库    practice_record ──→ 科目 / 语言 / 数量 / 题集（question_ids）
          question(id IN practice_record.question_ids（本次固定题集，[3.2.1](#321-post-cscarecords) 第 4 条）) ⋈ exam_paper（限 CSCA + 语言）──→ 题集
          practice_answer(practice_record_id=?, section_mapping='SEC_CSCA')  ──→ 答案映射
③ 加工    题集 LEFT JOIN 答案 → cards[]；按 typeId 映射值（SINGLE / MULTI）分组成 byType[]
④ 组装    CscaAnswerCardResponse
```

---

### 3.5 交卷

#### 3.5.1 POST /csca/records/{recordId}/submit

##### 接口用处

**交卷**（对应原型最后一题的「交卷」按钮）：对整条记录做一次全量判分汇总，写 `practice_record` 汇总列 + 生成 `practice_report`（**同步生成，无 AI、无需异步**）。返回体即原型**完成页**所需的全部数字（正确率 + 答对 / 答错 / 未答）。

> 📌 **本模块不单设「练习报告」查询接口**：报告汇总（得分 / 正确率 / 对错数）随本接口一次性返回，**重复调用即幂等返回既有结果**（见下第 1 条），完成页退出后再回来仍能拿到。更深维度也不必新增接口——「按题型统计 + 逐题对错」由 [3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card) 提供，错题解析走 [3.3.3 `/questions/{id}/solution`](#333-get-cscaquestionsquestionidsolution)。

##### 入参

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `recordId` | Path | Long | **是** | 归属校验 |
| Body | Body | Object | 否 | `{ "idempotencyKey": "…" }` |

##### 返回 JSON

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": "2097000000000000001",
    "status": 3,
    "reportId": "2097000000000000002",
    "totalQuestions": 432,
    "answeredCount": 20,
    "correctCount": 17,
    "wrongCount": 3,
    "unansweredCount": 412,
    "unGradedCount": 0,
    "score": "35.36",
    "fullScore": "41.60",
    "accuracyRate": 85.00,
    "durationSeconds": 726,
    "submittedTime": "1785395100000"
  }
}
```

- `accuracyRate` = `correctCount / answeredCount × 100`（**分母为"已作答"**，含未评分题；与 [3.1.1](#311-get-cscacatalog) 同一定义）——与原型完成页「正确率 = 答对 ÷ 已练习」一致
- `unansweredCount` = `totalQuestions - answeredCount`（原型完成页的「未答」）

##### 业务逻辑

1. **幂等**：记录已 `status=3` → 直接返回既有报告（`idempotencyKey` 命中同理）。
   - ✅ **实现口径（2026-10-14 编码）**：幂等闸门**只有 `status`** —— 已提交即**直接回既有结果**（**不重判、不写库、不涨 `version`、不发任何 `UPDATE`**）；重放的四个统计取**记录上冻结的缓存列**，而 `score` / `fullScore` 仍从 `practice_answer` **现算**（两表都没有得分列，见第 5 条）。
   - 🔴 **Body 里的 `idempotencyKey` 不落库**：`practice_record.idempotency_key` **已被建轮占用**（防重复建轮），交卷的键**没有落点**；写进去会把建轮的幂等重放搞坏（重发建轮请求找不到记录 → 又建一轮）→ 本实现**只做长度校验（`>128` → `8005`）+ 打日志**。**"命中同理"的实现方式就是这一次 `status=3` 判定**。
2. **全量重判**（**关键**）：遍历该记录**全部** `practice_answer` 行，用**该行自己的快照基准**重新比对：
   - 🔴 **判分基准 = `standard_answer_snapshot`（作答那一刻的标准答案），不是实时 `question.answer`** —— 题面与答案一起冻结，**题库后来纠错不改写已答过题的判分**（2026-10-13 冻结策略，见 [3](#3-接口详细设计) 开头）；⚠️ 快照为空（老数据 / 异常行）时**回落到 `question.answer`**
   - 为什么重判：`immediate=false` 的作答、以及离线批量补传的行，`is_correct` 可能还是 0
   - 判分走同一个 `CscaGradingService`，**单选/多选分别处理**（见 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 4 条）
   - ✅ **实现口径（2026-10-14）**：① 一次 `SELECT` 取回该记录**全部**作答行（含 5 个快照列）；② 快照为空时的回落**复用**作答链路的批量取题 `CscaQuestionMapper#selectForAnswerBatch`（本模块已允许读 `q.answer` 的三个查询之一），**不新增**读答案的 SQL，且**只在真的缺快照时才发这条查询**（常规交卷一次兜底查询都不发）；③ **只回写与库中值不同的行**（单条 `CASE id WHEN … THEN …` SQL）—— 重判是确定性的，常规交卷（作答时已判分）变化行数为 **0**，此时**一次 `UPDATE` 都不发**。
3. **未作答的题**：`answered=0` → 计入 `totalQuestions`，`is_correct` 保持 `0`（**不算错**，与 HSK 阅读口径一致），`points=null`；`unansweredCount = totalQuestions - answeredCount`。
4. **写 `practice_record`**：`status=3`、`submitted_time`、`duration_seconds`、`total_questions`、`answered_count`、`correct_count`、`wrong_count`、`accuracy_rate`。
5. **生成 `practice_report`**：唯一键 `uk_report_record(practice_record_id)` → upsert。字段 `paper_id=0`、`structure_id=科目稳定ID`、`total_questions/answered_count/correct_count/wrong_count/accuracy_rate/duration_seconds/generated_time`。
   - **`practice_report` 没有"得分"列**：得分只能由响应**现算**（`SUM(practice_answer.points)`），或写进 `practice_record`（该表也没得分列）。**本文的做法：得分每次从 `practice_answer.points` 现算**（见 [4.3](#43-待确认事项) 第 4 条）。
6. **`score` 满分的口径**：`fullScore` = 本次题集**已作答题**的分值之和（**取快照 `question_snapshot.score`**，与作答当时一致；不是整卷满分）。**`answered` 之外的题不计入满分**，避免"没作答也算进满分"导致正确率失真。
7. **「再来一轮」不在本接口**：原型完成页的「再来一轮」= 重发 [3.2.1 `POST /csca/records`](#321-post-cscarecords) 并带 `restart: true` —— 仅作废本轮的 `practice_record`（`status → 2`），**作答数据一行不删**；新轮成为「最新一轮」，**科目进度随之归零后重新累计**（[3.1.1](#311-get-cscacatalog) 业务逻辑第 3 条）。
8. **同步错题本**：第 2 条的全量重判若**翻转**了某题的 `is_correct`（正常路径不会，仅老数据 / 异常行），**同期同步** `csca_question_wrong`（与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条同一套规则：**只把「翻成错」的题收录，翻成对不动** —— 2026-10-19 取消自动移出，[4.4](#44-文档与实现的差异) 第 62 条）、并**携带轮次快照** `record_id` = 本轮 `recordId`、**语言快照** `language_version` = `null`（交卷路径取不到语言，[4.4](#44-文档与实现的差异) 第 66 条）（[3.6.2](#362-错题本wrong-book) 第 11 条）。✅ **已实现（2026-10-14，2026-10-19 调整）**：重判时收集「判分三态发生变化」的已答行（`RegradeSummary.flips`），第 ⑧ 步**只挑其中 `isCorrect = 2`（翻成错）的**调 `syncAfterGrade`；没有翻成错时一次同步都不发。⚠️ **科目 / 语言快照传 `null`**（作答行不落这两列）—— 见 [4.4](#44-文档与实现的差异) 第 61 条 c 项；🟡 但**用户答案照传**（`GradeFlip` 带出 `practice_answer.answer`）—— 这一路取得到，别传 `null`（第 69 条）。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaRecordController#submit(String recordId, CscaSubmitRequest, HttpServletRequest, @RequestHeader X-Client-Type)` | 路径手工解析（非数字 → `8005`，同 [3.2.3](#323-get-cscaquestionsquestionid)）+ 强鉴权 |
| Service | `CscaSubmissionService#submit(Long userId, Long recordId, CscaSubmitRequest)` | 幂等 → 全量重判 → 回写作答 → 写记录 → upsert 报告 → 组装 |
| Service | `csca/service/CscaGradingService#grade(standardAnswer, userAnswer, score)` | 逐题判分（**唯一**判分入口；无标准答案 → 未评分，**绝不判错**） |
| Mapper | `csca/mapper/CscaAnswerMapper#selectForSubmit` / `#updateGradesAfterSubmit` | 取**全部**作答行（含 5 快照列）/ **单条 SQL** 批量回写 `is_correct` + `points` |
| Mapper | `csca/mapper/CscaReportMapper#selectIdByRecord` / `#upsertReport` | 取已有报告 id（幂等重放）/ `uk_report_record` upsert |
| Mapper | `PracticeRecordMapper#selectByIdForUpdate` / `#updateById` | 记录行锁 + 归属；汇总列（**复用共享实体上的 `@Version` 乐观锁**） |
| Mapper | `csca/mapper/CscaQuestionMapper#selectForAnswerBatch` | **仅**快照为空时回落取实时 `question.answer` 作判分基准 |
| Mapper | `csca/mapper/CscaRecordMapper#selectRecord` | **仅** `total_questions` 为空（异常）时回落读 `question_ids` 长度 |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `practice_record` | UPDATE | 汇总列 |
| `practice_answer` | SELECT + UPDATE | `is_correct` / `points` |
| `practice_report` | **INSERT … ON DUPLICATE KEY UPDATE** | 全列（`paper_id=0`、`structure_id=科目稳定ID`） |
| `question` / `exam_paper` | SELECT | 科目校验；**判分基准优先用 `standard_answer_snapshot`**（仅快照为空时回落 `answer`） |
| `csca_question_wrong`（新增） | INSERT … ON DUPLICATE KEY UPDATE | 重判**翻成错**时同步收录（翻成对不动，见第 8 条）—— ✅ **已接线（2026-10-14）**：判错走 `upsertWrongs`（2026-10-19 起「翻成对」不再移出，`markRemoved` 已删除） |

##### 数据流向

```
① 入参    recordId ──幂等：已提交（status=3）则直接返回既有结果（零写入）
② 查库    practice_answer(record_id=?)（含 5 个快照列；判分基准 = standard_answer_snapshot）
③ 加工    逐题 CscaGradingService.grade() → is_correct / points（只回写变化的行）
          SUM(points) = score；SUM(score of answered) = fullScore
④ 组装    UPDATE practice_record + UPSERT practice_report → Response
```

> ⚠️ **"无标准答案"的题（`answer='无'`；🟡 **当前两库已无此值，纯兜底**）在交卷时必须保持 `is_correct=0`（未评分），不能因重判被改成"错误"**。否则题库的脏值会直接变成用户扣分，属于数据问题转嫁用户。见 [4.2](#42-答案归一化cscaanswernormalizer) 第 3 条。
> ⚠️ **不要复用 `exam-service` 的 `submitCscaExam`**：它把 CSCA 全按单选处理（`ExamRecordServiceImpl:589` 注释原文「CSCA只有一种题型（选择题），不分类型统计」），**这个前提在当前题库里不成立**（有 33 道多选 + 5 选项/6 选项题）。

---

### 3.6 收藏与错题本

#### 3.6.1 收藏（favorite）

> **本组接口是原型 v1.3 新增需求**（答题页右上角 ★ 收藏、答题卡里的 ★ 标记）。原型把收藏**存在本地**（`PROG[key].fav`）；✅ **2026-10-13 拍板：落库**（跨设备可取回），支撑表 `csca_question_favorite`（2026-10-19 加 `csca_` 前缀，原名 `question_favorite`；本模块**新增的业务表之一** —— 另一张是错题本 `csca_question_wrong`，见 [3.6.2](#362-错题本wrong-book)；DDL 见业务逻辑第 5 条）。<br>⚠️ 原型的「仅本地」方案**已废弃** —— 本组 3 个接口**全部落库实现**（[4.3](#43-待确认事项) 第 10 条）。<br>📌 **编码进度（2026-10-14）**：`PUT /csca/favorites/{questionId}` ✅ **已编码**（[4.4](#44-文档与实现的差异) 第 56 条）、`DELETE /csca/favorites/{questionId}` ✅ **已编码**（[4.4](#44-文档与实现的差异) 第 57 条 —— 与 `PUT` **共用同一条 upsert**，只差 `deleted` 传 0 / 1）、`GET /csca/favorites` ✅ **已编码**（[4.4](#44-文档与实现的差异) 第 59 条）—— 🔴 **本组 3 个端点已全部落地**。

##### 接口用处

| 接口 | 作用 | 对应原型 |
|---|---|---|
| `PUT /csca/favorites/{questionId}` | 收藏一题（**幂等**） | 点 ★「收藏本题」 |
| `DELETE /csca/favorites/{questionId}` | 取消收藏（**幂等**） | 点 ★「已取消收藏」 |
| `GET /csca/favorites` | 收藏列表（"我的收藏"，分页） | 原型只有星标、**暂无收藏列表页**，此接口为**预留** |

##### 入参

**PUT / DELETE `/csca/favorites/{questionId}`**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `questionId` | Path | Long | **是** | 必须属于 CSCA（`exam_type=2`），否则 `404` |
| `recordId` | Query | Long | **是** | **当前练习轮次**（`practice_record.id`）→ 写快照列 `record_id`（第 8 条；该列与 `source` 成对，第 70 条）。⚠️ 🔴 **由可选改必填**（2026-10-14 用户口径「recordId改为必填」，[4.4](#44-文档与实现的差异) 第 58 条）—— 收藏动作**总是发生在某一轮练习里**（答题页 ★ / 答题卡 ★ 都在某条记录的上下文）；**未传 / 空串 / 非数字 → `CSCA_PARAM_OUT_OF_RANGE(8005)`**（与路径变量同口径）。⚠️ **只在首次插入时写**，重复收藏不覆盖 |
| Token | Header | String | **是** | 收藏是用户数据，强鉴权 |

**GET /csca/favorites**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `subjectTypeMapping` | Query | String | 否 | 只查某科目；不传 = 全部 |
| `source` | Query | String | 否 | `prac`（练习）/ `exam`（考试）；不传 = 全部（[4.1](#41-枚举速查) `source`） |
| `languageVersion` | Query | String | 否 | **不传 = 全部语言**（`CSCALanguageVersion` 的 2 值之一：`chinese` / `english`；非法 → `CSCA_LANGUAGE_INVALID(8002)`）。✅ 2026-10-19 起收藏表**自带语言快照列** `language_version`，筛选**直接命中该列、免 join**（业务逻辑第 6 条） |
| `startTime` / `endTime` | Query | Long | 否 | 🆕 **收藏时间区间**（2026-10-19 加，[4.4](#44-文档与实现的差异) 第 64 条）：**毫秒时间戳、闭区间** `[startTime, endTime]`，命中 `csca_question_favorite.updated_time`（= 排序键 = 响应体 `favoriteTime`）。🔴 **只做自定义区间**，`三天内 / 一周内 / 一个月内` 由前端算好时间戳传过来（与 [3.6.2](#362-错题本wrong-book) 第 12 条同一套口径）。单边传也合法；`startTime > endTime` → `CSCA_PARAM_OUT_OF_RANGE(8005)` |
| `order` | Query | String | 否 | 🆕 **排序方向**（2026-10-19 加，[4.4](#44-文档与实现的差异) 第 65 条）：`asc`（最早在前）/ `desc`（**缺省**，最近在前），**忽略大小写**；非法 → `CSCA_PARAM_OUT_OF_RANGE(8005)`。🔴 **只切方向、不切列**（排序键恒为 `updated_time`，与 `favoriteTime`、时间筛同一列）；**排序只能由后端做**（分页列表前端排不了跨页）。见业务逻辑第 10 条 |
| `withAnswerState` | Query | Boolean | 否 | `true` 时附带该用户对每题的上次对错（缺省 `true`） |
| `page` / `pageSize` | Query | Integer | 否 | 缺省 `1` / `20`，`pageSize ∈ [1,100]` |

##### 返回 JSON

**PUT / DELETE**（两者一致，返回"最终态"）：

```json
{ "code": 200, "message": "操作成功", "data": { "questionId": "2096765985525108738", "favorite": true, "favoriteCount": 37 } }
```

**GET /csca/favorites**：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "total": 37,
    "page": 1,
    "pageSize": 20,
    "questions": [
      {
        "questionId": "2096765985525108738",
        "subjectCode": "math",
        "typeId": "SINGLE",
        "layout": "textChoice",
        "passage": "下列结论正确的是( )．",
        "content": null,
        "options": [ { "label": "A", "content": "$-1\\in\\mathbb{N}$" } ],
        "group": null,
        "standardAnswer": "C",
        "standardAnswerLabels": ["C"],
        "source": "prac",
        "recordId": "3026191612601000448",
        "favoriteTime": "1785395100000",
        "answered": 1,
        "isCorrect": 2
      }
    ]
  }
}
```

- 列表元素与 [3.2.2](#322-get-cscaquestions) 的题目对象**同构**：`layout` + **三字段**（`passage` / `content` / `group`）恒出现、无值填 `null`，另附 **`standardAnswer` / `standardAnswerLabels`（🟡 2026-10-19 新增）** + `source` / `recordId` / 收藏态 / 作答态字段。（本例为 `textChoice`；收藏到共材料题时 `group` 会非 `null`，形态同 [3.2.2](#322-get-cscaquestions) 示例第 2 / 3 条。）
- 🟡 **答案口径与 [3.3.3](#333-get-cscaquestionsquestionidsolution) 完全一致**：`standardAnswer` 原值直传（不归一化），`无` / `NULL` / 空白 → `standardAnswer = null` 且 `standardAnswerLabels = []`。**不带 `analysis`**（解析仍走 `/solution`）。

##### 业务逻辑

1. **幂等（`PUT` / `DELETE` 同一套写法）**：`PUT` 已收藏 → 直接返回 `favorite=true`（不报错、不重复插入）；`DELETE` 未收藏 → 返回 `favorite=false`。**都走 `INSERT … ON DUPLICATE KEY UPDATE`**，唯一键 `uk_user_question(user_id, question_id)`：
   - `PUT`：`INSERT …(…, source='prac', record_id=?, deleted=0…) ON DUPLICATE KEY UPDATE deleted=0, updated_time=VALUES(updated_time)`
   - `DELETE`：`INSERT …(…, source='prac', record_id=?, deleted=1…) ON DUPLICATE KEY UPDATE deleted=1, updated_time=VALUES(updated_time)`
   - ⚠️ **`source` / `record_id` 只在 INSERT 时写**（`source` 恒 `'prac'`），`ON DUPLICATE KEY UPDATE` 里**不含**它们 —— 保留**首次收藏的来源与轮次**（与错题本同口径，第 7 / 8 条）。
   - 🔴 **软删 + 复活，不物理删**：取消收藏置 `deleted=1`（行保留），再收藏**复活同一行**（`deleted` 回 `0`）→ 唯一键恒成立、不会撞键。⚠️ **唯一键里不要带 `deleted`**（带上去重收藏会插出第二行）。
2. **准入校验**：`questionId` 所属卷必须 `exam_type=2 AND version='CSCA'`，否则 `CSCA_QUESTION_NOT_FOUND(8006)`（回 HTTP `404`）—— HSK 的题不能从 CSCA 收藏（[0.5](#05-错误码)）。
3. **`GET` 列表返回 `standardAnswer` / `standardAnswerLabels`，但<u>不返回</u> `analysis`**（🟡 **2026-10-19 口径变更**：[4.4](#44-文档与实现的差异) 第 68 条）。原口径「收藏列表也不带答案」已废止 —— 「我的收藏」是复习入口，用户点进去就要看正解，逐个再调 `/solution` 会让列表页发出 N+1 次请求。边界：答案**只**在 `selectFavoritePage` 这条查询里补 `q.answer`，**不往 `cscaQuestionColumns` 共享片段里加**（否则 `GET /csca/questions` 也会带出答案）；解析仍走 [3.3.3](#333-get-cscaquestionsquestionidsolution)。
4. **跨设备**：收藏与 `user_id` 绑定，换设备登录后由 `GET /csca/favorites` 取回。**收藏独立于作答**——不进 [3.1.1](#311-get-cscacatalog) 科目卡的题数/正确率统计。
5. **落库表 `csca_question_favorite`**（🆕 **本模块新增的业务表之一** —— 与错题本 `csca_question_wrong` 并列，见 [3.6.2](#362-错题本wrong-book)；2026-10-13 拍板；🔴 **2026-10-19 表名加 `csca_` 前缀**（原 `question_favorite`），见 [4.4](#44-文档与实现的差异) 第 66 条；⚠️ 别与 `practice_record.question_ids` 混淆 —— 那是**加列**、不是新表，[4.4](#44-文档与实现的差异) 第 26 条）：
   ```sql
   CREATE TABLE csca_question_favorite (
     id                 BIGINT       NOT NULL COMMENT '收藏ID（雪花）',
     user_id            BIGINT       NOT NULL COMMENT '用户ID',
     question_id        BIGINT       NOT NULL COMMENT '题目ID（question.id）',
     section            VARCHAR(50)  DEFAULT NULL COMMENT '科目码快照（= question.subject_type_mapping）',
     language_version   VARCHAR(20)  DEFAULT NULL COMMENT '语言版本快照（= exam_paper.language_version）',
     source             VARCHAR(20)  NOT NULL DEFAULT 'prac' COMMENT '来源快照：prac 练习 / exam 考试',
     record_id          BIGINT       DEFAULT NULL COMMENT '来源记录ID（按 source 判定：prac→practice_record.id / exam→exam_record.id）',
     deleted            INT          NOT NULL DEFAULT 0 COMMENT '逻辑删除：0 已收藏，1 已取消',
     created_by         BIGINT       DEFAULT NULL COMMENT '创建人（FieldFill.INSERT 自动填充）',
     update_by          BIGINT       DEFAULT NULL COMMENT '更新人（FieldFill.INSERT_UPDATE 自动填充）',
     created_time       BIGINT       DEFAULT NULL COMMENT '首次收藏时间（毫秒时间戳）',
     updated_time       BIGINT       DEFAULT NULL COMMENT '最近一次收藏/取消时间（列表按它倒序）',
     PRIMARY KEY (id),
     UNIQUE KEY uk_user_question (user_id, question_id),
     KEY idx_user_time (user_id, deleted, updated_time)
   ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='题目收藏表';
   ```
   - **列风格对齐本库既有 `practice_*` 表**（`practice_record` / `practice_answer` 实测）：雪花 `BIGINT` 主键、`deleted INT`（0/1）、时间列是**毫秒 `BIGINT`**（不是 `datetime`）、`utf8mb4_0900_ai_ci` + `ROW_FORMAT=DYNAMIC`。
   - 🆕 **末 5 列与 `practice_answer` / `practice_report` 逐列同序**（2026-10-14 补）：`deleted` → `created_by` → `update_by` → `created_time` → `updated_time`。其中新增的 **`created_by` / `update_by`（审计列）**由实体基类 [`BaseEntity`](file:///d:/code/hsk_treasure/common/src/main/java/com/hsktreasure/common/entity/BaseEntity.java) + 自动填充器 [`DBMetaObjectHandler`](file:///d:/code/hsk_treasure/common/src/main/java/com/hsktreasure/common/handler/DBMetaObjectHandler.java) 写入（`FieldFill.INSERT` / `INSERT_UPDATE`，取当前登录用户 `id`；无登录态时不填）。
   - 🔴 **表里必须有这两列**：本库所有业务实体都 `extends BaseEntity`，MyBatis-Plus 的 `insertFill` 会**无条件向 `created_by` / `update_by` 写值** —— 缺列时 `INSERT` 直接报 `Unknown column 'created_by'`。⚠️ 本组接口用**手写 `INSERT … ON DUPLICATE KEY UPDATE`**（不走 MP 的 `saveOrUpdate`），故这两列**需在 SQL 里显式带入**（`created_by` / `update_by` / `created_time` / `updated_time` 一并），别指望自动填充。
   - 🆕 **`language_version` 是语言快照列**（2026-10-19 加，[4.4](#44-文档与实现的差异) 第 66 条）：写侧从**同一次准入查询**带回（`CscaQuestionMapper#selectFavoriteAdmission` 已 join `exam_paper`，多取一列零成本）；读侧按语言筛**直接命中该列**，不再 `JOIN question → exam_paper`（第 6 条）。取值 `VARCHAR(20) NULL`，与 `exam_paper.language_version` **同类型同宽**。
   - `section` / `language_version` / `source` / `record_id` 都是**快照列**（便于免 join 筛选、不参与任何鉴权）：`section` = 科目码、`language_version` = 卷的考试语言版本、`source` = **收藏那一刻来自哪条链路**（`prac` / `exam`，第 7 条）、`record_id` = **来自哪一轮练习 / 考试**（第 8 条，🟡 2026-10-19 由两列合一）。
   - 🔴 **原 `section_mapping` 列已删**（2026-10-19 用户口径「两个表的 section_mapping 不要了」，[4.4](#44-文档与实现的差异) 第 67 条）：该列恒为 `'SEC_CSCA'`、无任何查询使用（模块归属已由**表名前缀**表达）。⚠️ 别与 `practice_record.section_mapping` / `practice_answer.section_mapping` 混淆 —— 那两张表**混着 HSK 行**、该列必须保留。
   - 🟡 **正确答案不落本表**（2026-10-19）：列表要显示的 `standardAnswer` 在查询时**现场读 `q.answer`**（与 `/solution` 同源，题库纠错能立刻反映到下发的答案上）。收藏行只存**用户行为产生的快照**（科目 / 语言 / 来源 / 轮次 / 时间），**不存题的属性** —— 否则同一道题被 100 个人收藏就存 100 份答案，且题库一改错就要批量修。
   - 🟡 **`record_id` 一列承载「来源记录」**（2026-10-19 由 `practice_record_id` + `exam_record_id` 两列合一，[4.4](#44-文档与实现的差异) 第 70 条）：**具体是哪张表的 id 由 `source` 决定** —— `source='prac'` → `practice_record.id`；`source='exam'` → `exam_record.id`。原两列**按 source 互斥**（恒有一个为 `NULL`），拆成两列后读侧必须自己 `COALESCE` 才能还原，而 `source` 早已存着这条信息。🔴 **本模块只写 `prac` 来源** → 写入值恒为 `practice_record.id`。
   - 索引分工（**只留 2 个二级索引**，2026-10-14 精简）：
     - `uk_user_question` → **幂等 upsert**（`INSERT … ON DUPLICATE KEY UPDATE` 的唯一依据、**不可去**）+ 答题卡 `question_id IN` 查询
     - `idx_user_time` → 列表**倒序分页**（`WHERE user_id=? AND deleted=0 ORDER BY updated_time DESC`；唯一能免 filesort 的索引）
   - 🔴 **原 `idx_user_section (user_id, section_mapping, section, deleted)` 已删**（2026-10-14 用户口径「可以删掉吗」→ 精简，[4.4](#44-文档与实现的差异) 第 47 条）：它只服务「按科目筛收藏」（`… AND section=?`），而列表**主路径不传科目**、本就走 `idx_user_time`；带科目筛时用 `idx_user_time` 的 `user_id` 前缀命中后**回表逐行 filter `section`** 即可 —— 收藏是**用户私有数据**（单个用户几十~几百行），代价可忽略。另：原索引含的那个恒值列现已随列一起删除。⚠️ **`section` 列保留**（仍是免 join 的快照列），只是不再为它单建索引。
   - 📌 **列表排序用 `updated_time`**：响应里的 `favoriteTime` 取它（= **最近一次收藏**的时间；取消后再收藏会刷新）。
6. **按语言筛收藏（`GET /csca/favorites?languageVersion=…`）**：✅ **2026-10-19 起免 join** —— 直接 `AND f.language_version = ?`（命中第 5 条的快照列）；`language_version IS NULL` 的历史行**不会被任何语言筛命中**（CSCA 存量行已于建列时全量回填，NULL 0 行）。**不传 = 全部语言**（含历史 NULL 行）；英文卷导入后该筛选才有区分度。
7. **来源维度（`source` 快照列，2026-10-14 加）**：与 [3.6.2](#362-错题本wrong-book) 第 6 条**同列同义** —— `prac` = 本模块练习链路写入（收藏动作发生在答题页 ★ / 答题卡 ★）；`exam` = **考试链路写入** —— ⚠️ **本模块只写 `prac`，`exam` 待考试侧接入**（超出本模块范围）。`GET /csca/favorites?source=…` 即按此列过滤、**免 join**（这是把它存成快照列的原因）。
8. **来源记录（`record_id` 快照列，2026-10-14 加、🟡 2026-10-19 两列合一）**：与 [3.6.2](#362-错题本wrong-book) 第 11 条**同列同义** —— 记下**这条收藏是在哪一轮练习 / 考试里产生的**（收藏动作本身没有轮次，这是「来源记录」快照）。① **是哪张表的 id 由 `source` 决定**：`source='prac'` → `record_id` = 入参 `recordId`（[3.2.1](#321-post-cscarecords) 建的轮）；`source='exam'` → `exam_record.id`（[4.4](#44-文档与实现的差异) 第 70 条）；② ⚠️ **本模块只写 `prac`**，故该列恒为 `practice_record.id`；③ 🔴 **只在 INSERT 写、重复收藏不覆盖**（与 `source` 同口径，第 1 条）→ 保留**首次收藏时的轮次**；④ 🔴 **`recordId` 必填**（2026-10-14 口径，[4.4](#44-文档与实现的差异) 第 58 条）→ 本模块**恒写非空值**；**原「复习页收藏无轮次上下文 → 留 `NULL`」的形态已取消**（复习页收藏同样必须交代轮次，否则 `8005`）；⑤ **只存快照**：不做归属 / 存在性校验，**不参与任何查询条件与鉴权**（列表也不按它筛）。
9. 🆕 **按收藏时间筛（`GET /csca/favorites?startTime=…&endTime=…`，2026-10-19 加，[4.4](#44-文档与实现的差异) 第 64 条）**：与 [3.6.2](#362-错题本wrong-book) 第 12 条**同一套口径**。
   - **命中列 = `csca_question_favorite.updated_time`**（= `favoriteTime` = `ORDER BY` 的列）—— 筛的 / 排的 / 显示的是**同一个时间**，不会「按区间筛出来却显示成区间外时间」；走 `idx_user_time(user_id, deleted, updated_time)` 第三列，**不新建索引**。
   - **闭区间**、**毫秒时间戳**；`startTime` / `endTime` 各自可选（单边 = 该时刻之后 / 之前）；`startTime > endTime` → `8005`。
   - 🔴 **不提供 `三天内 / 一周内 / 一个月内` 枚举**：那是前端的快捷按钮，由前端按**用户本地时区**算出 `startTime = now - N×86400000`、`endTime = now` 传过来 —— ① 时区只有客户端知道；② 新增档位不必改后端、不必发版；③ 快捷按钮与「自定义起止日期」走同一条链路。
   - ⚠️ 本区间**与 `withAnswerState` 无关**：作答态取「最近一次作答」，其时间可能落在区间之外（那是另一维度的信息，不参与筛选）。
   - ⚠️ 误传 10 位**秒级**时间戳**不报错、只筛出空结果**（后端不猜单位）。
10. 🆕 **排序方向（`GET /csca/favorites?order=asc|desc`，2026-10-19 加，[4.4](#44-文档与实现的差异) 第 65 条）**：与 [3.6.2](#362-错题本wrong-book) 第 13 条**同一套口径**。
   - 🔴 **排序必须在后端**：列表带 `LIMIT / OFFSET` 分页，前端只能排「已下发的那一页」，翻到第 2 页整体顺序即错 —— 跨页排序只有 SQL 能做。前端**只传方向**。
   - **只切方向、不切列**：排序键恒为 `updated_time`（= `favoriteTime` = 时间筛命中列）。不开放「按科目 / 按题号排」，因为 `idx_user_time(user_id, deleted, updated_time)` 只覆盖这一列，每多一种排序列就要多一个索引。
   - **取值**：`asc` / `desc`，**忽略大小写**（`order` 是控制字，不是库里的数据值，与 `source` 的大小写敏感刻意不同）；不传 / 空白 = `desc`；**非法 → `8005`，不静默退回缺省**（否则前端会以为自己传的排序生效了）。
   - 🔴 **`id` 兜底必须与 `updated_time` 同向**：`ASC` 配 `id ASC`、`DESC` 配 `id DESC`。写成 `updated_time ASC, id DESC` 这种混合方向时 MySQL 用不上索引的有序性，会退化成 filesort。
   - **实现**：入参收敛成布尔（`CscaListParams#resolveAscending`）→ XML 用两个**写死方向**的 `<choose>` 分支，**不用 `${}` 拼串**（注入面为零）。**计数不吃这个参数**（排序不影响条数）。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaFavoriteController#add` / `#remove` / `#list`（✅ **三个全部已编码**） | 强鉴权 |
| Service | `CscaFavoriteService#add` / `#remove`（共用私有 `upsertState`） / `#list`（✅ **已编码**） | 幂等收藏 / 取消 / 列表装配 |
| Mapper | `csca/mapper/CscaFavoriteMapper`（`upsertFavorite`（**PUT / DELETE 共用**） / `countFavorites` / `selectFavoritePage` / `countFavoritePage`；读侧 `selectFavoritedQuestionIds` 已服务答题卡）（✅ **已编码**；列表**五个筛选项**（科目 / 来源 / 语言 / 起 / 止）全走 `favoriteListFilters` 一份片段（5 个 `<if>`）；`selectFavoritePage` 另带 `ascending`，`countFavoritePage` 不带；🟡 `selectFavoritePage` 还取 `q.answer`（收藏列表带标准答案，[4.4](#44-文档与实现的差异) 第 68 条）） | upsert / 软删 / 分页查 |
| 题面装配 | `support/CscaQuestionAssembler`（✅ **已编码**；与 `GET /csca/questions` **共用同一份**） | 三字段直传 + 选项保序 + 共材料兜底 + `typeId` 映射 |
| 作答态 | `CscaAnswerMapper#selectLatestByQuestionIds`（✅ **已编码**） | `withAnswerState=true` 时的上次对错（**跨轮次**取最近一次） |

> 📌 **编码进度（2026-10-14）**：`PUT /csca/favorites/{questionId}` **已实现**（见 [4.4](#44-文档与实现的差异) 第 56 条）—— 写侧走 `CscaFavoriteMapper#upsertFavorite`（幂等 upsert）+ `CscaFavoriteMapper#countFavorites`（回执计数），准入复用 `CscaQuestionMapper#selectFavoriteAdmission`（`cscaPaperBase` + `cscaQuestionValid`）；`source` / `record_id` / `section` / 首次时间**只在 INSERT 写**。✅ **`DELETE /csca/favorites/{questionId}` 已实现**（第 57 条）：与 `PUT` **共用同一条 upsert**（`deleted` 传 1）、**准入同样校验**、回执 `favorite = false`。✅ **`GET /csca/favorites` 已实现**（第 59 条）：`selectFavoritePage` 一条 SQL 把**题面 + 收藏字段**一起 join 回来，`countFavoritePage` **复用同一份筛选片段**（口径不会漂）；题面交给 `CscaQuestionAssembler`（与取题列表同源），**恒不传题面快照**；🔴 **本组 3 个端点全部落地**。

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `csca_question_favorite`（**新增**，2026-10-13 定，2026-10-19 加 `csca_` 前缀） | INSERT / UPDATE / SELECT | 见上 |
| `question` / `exam_paper` | SELECT | 准入校验、题面装配 |
| `practice_answer` | SELECT | `withAnswerState=true` 时的上次对错 |

##### 数据流向

**写（`PUT` / `DELETE /csca/favorites/{questionId}`）**

```
① 入参    questionId + recordId(+ token.userId)
② 查库    question ⋈ exam_paper ──准入 exam_type=2──→ 命中 / 否则 404
③ 加工    UPSERT csca_question_favorite（幂等；`section` + `language_version` 同时落快照）
④ 组装    { questionId, favorite, favoriteCount }
```

**读（`GET /csca/favorites`）**

```
① 入参    subjectTypeMapping? + source? + languageVersion? + startTime?/endTime? + order? + withAnswerState? + page/pageSize(+ token.userId)
② 计数    COUNT(*) csca_question_favorite ⋈ question ──同一套筛选（含语言快照列 + 收藏时间闭区间；不吃 order）──→ total
③ 取页    selectFavoritePage（同 join、ORDER BY updated_time asc|desc + id 同向兜底、LIMIT/OFFSET）
          → 收藏行（题面在同一条 SQL 里带回来；🟡 2026-10-19 起另带 q.answer）
④ 索引    question_group（本页各卷）→ 共材料分组
⑤ 作答态  withAnswerState=true → practice_answer 按【用户】分区取每题最近一次（answered / is_correct）
⑥ 装配    { questionId, subjectCode, typeId, layout, passage, content, options, group,
            standardAnswer, standardAnswerLabels, source, recordId, favoriteTime,
            answered, isCorrect }
          ⚠️ 答案口径 = CscaSolutionResponse 同一套（原值直传；`无`/NULL → null + []）；不含 analysis
```

> 📌 **`favoriteCount` 的口径**：本组写接口（`PUT` / `DELETE`）**没有题集上下文**，回的是「**当前用户已收藏总数**」（`user_id + deleted = 0`）—— ⚠️ 与 [3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card) 的同名计数（**本次题集内**）**不是一回事**，别混用（[4.4](#44-文档与实现的差异) 第 56 条）。

> ⚠️ **收藏不等于作答**：`csca_question_favorite` 与 `practice_answer` **是两张表**，收藏不写 `practice_answer`、也不进判分与报告。答题卡里的 ★ 与 对/错 是两个独立标记。

---

#### 3.6.2 错题本（wrong-book）

> **本组接口是原型 v1.4 新增需求**（「我的 → 错题本」列表 + 错题复习页）。✅ **2026-10-13 拍板：落库**，支撑表 `csca_question_wrong`（2026-10-19 加 `csca_` 前缀，原 `question_wrong`）—— 与 [3.6.1 收藏](#361-收藏favorite) 的 `csca_question_favorite` **并列的姊妹表**（DDL 见业务逻辑第 9 条）。<br>🔴 与收藏的**口径**：**两张表都「只进不出」**（2026-10-19 起取消「答对自动移出」，错题本与收藏都是只增不减；移出错题本只有用户手动 `DELETE` 一条路径，见 [4.4](#44-文档与实现的差异) 第 62 条）—— 其余（软删复活 / 唯一键 / 索引集合 / **`source` 来源列** / **`language_version` 语言快照列** / **无 `section_mapping`**）与 [3.6.1](#361-收藏favorite) **完全一致**（2026-10-19 两表同批加语言列、删 `section_mapping` 后两表互为镜像）。<br>📌 **编码进度（2026-10-14）**：`GET /csca/wrong-book` ✅ **已编码**（[4.4](#44-文档与实现的差异) 第 60 条 —— 列表读侧落地，含新增的共用支撑 `support/CscaListParams` / `support/CscaRequestParams`）；`DELETE /csca/wrong-book/{questionId}`（手动移出）与 `POST /csca/wrong-book/{questionId}/answer`（复习作答）✅ **已编码（[4.4](#44-文档与实现的差异) 第 61 条）** —— 本组**写侧**（幂等 upsert / 软删 / 判分同步）与**判错自动收录的接线**（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条 / [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 第 6 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条）**均已落地** —— 🔴 **本模块 16 个端点至此全部编码**。

##### 接口用处

| 接口 | 作用 | 对应原型 |
|---|---|---|
| `GET /csca/wrong-book` | 错题列表（"我的错题本"，分页 + 科目筛选 + 来源筛选 + **语言筛选** + **错题时间筛选** + **排序方向**） | 「我的 → 错题本」列表 |
| `DELETE /csca/wrong-book/{questionId}` | 手动移出错题本（**幂等**） | 错题卡片右上「移出」 |
| `POST /csca/wrong-book/{questionId}/answer` | 复习作答（**判分 + 同步错题本**） | 错题复习页选选项 |

> 📌 **判错自动收录没有独立接口**：它是**判分的附随动作** —— 判**错** → 收录；🔴 判**对** → **不动**（2026-10-19 取消自动移出）；写 `practice_answer.is_correct` 的每一处都会顺带同步（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条 / [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 第 6 条）。

##### 入参

**GET /csca/wrong-book**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `subjectTypeMapping` | Query | String | 否 | 5 个原始值之一（[4.1](#41-枚举速查)）；不传 = 全部 |
| `source` | Query | String | 否 | `prac`（练习）/ `exam`（考试）；不传 = 全部（[4.1](#41-枚举速查) `source`） |
| `languageVersion` | Query | String | 否 | 🆕 **语言筛选**（2026-10-19 加，[4.4](#44-文档与实现的差异) 第 66 条）：`chinese` / `english`（`CSCALanguageVersion` 的 2 值，**非法 → `CSCA_LANGUAGE_INVALID(8002)`**）；**不传 = 全部语言**。✅ 命中**语言快照列** `csca_question_wrong.language_version`、**免 join**（业务逻辑第 14 条） |
| `startTime` | Query | Long | 否 | **错题时间下界**，**毫秒时间戳、闭区间**（含）；不传 = 不限。命中 `csca_question_wrong.updated_time` |
| `endTime` | Query | Long | 否 | **错题时间上界**，**毫秒时间戳、闭区间**（含）；不传 = 不限。`startTime > endTime` → `8005` |
| `order` | Query | String | 否 | 🆕 **排序方向**（2026-10-19 加，[4.4](#44-文档与实现的差异) 第 65 条）：`asc`（最早在前）/ `desc`（**缺省**，最近在前），**忽略大小写**；非法 → `8005`。🔴 **只切方向、不切列**（排序键恒为 `updated_time`，与 `wrongTime`、时间筛同一列）；**排序只能由后端做**。见业务逻辑第 13 条 |
| `page` / `pageSize` | Query | Integer | 否 | 缺省 `1` / `20`，`pageSize ∈ [1,100]` |
| Token | Header | String | **是** | 错题本是用户数据，强鉴权（[0.2](#02-鉴权与客户端类型)） |

> 🔴 **时间筛选只提供「自定义区间」，不提供 `timeRange=3d/7d/30d` 这类枚举**（2026-10-19 定，见业务逻辑第 12 条）：
> 「三天内 / 一周内 / 一个月内」只是**前端的快捷按钮**，点选后由前端按**用户本地时区**算出
> `endTime = 当前毫秒`、`startTime = endTime - N × 86400000` 再传进来 —— 与「自定义起止日期」**同一条链路**，后端不区分。
>
> 三个理由：① **时区**只有客户端知道，服务器按 UTC 算「三天前」在跨时区用户那里会偏几小时；
> ② 新增档位（如「半年内」）**不必改后端**、不必发版；③ 前端不必为快捷按钮和自定义日期写两套请求。
>
> ⚠️ 两个参数**单边也合法**：只传 `startTime` = 该时刻之后；只传 `endTime` = 该时刻之前。
> ⚠️ 约定就是**毫秒**（与库里 `updated_time` 的存储单位一致）；误传 10 位秒级值**不会报错、只会筛出空结果**。

**DELETE /csca/wrong-book/{questionId}**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `questionId` | Path | Long | **是** | 必须属于 CSCA（`exam_type=2`），否则 `CSCA_QUESTION_NOT_FOUND(8006)` |
| Token | Header | String | **是** | 强鉴权 |

**POST /csca/wrong-book/{questionId}/answer**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `questionId` | Path | Long | **是** | 必须属于 CSCA，否则 `CSCA_QUESTION_NOT_FOUND(8006)` |
| Body | Body | Object | **是** | `{ "answer": "B" }` —— **与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 同格式**（多选 `"A,D"`，逗号分隔、升序） |
| Token | Header | String | **是** | 强鉴权 |

##### 返回 JSON

**GET /csca/wrong-book**：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "total": 12,
    "page": 1,
    "pageSize": 20,
    "wrongQuestions": [
      {
        "questionId": "2096765985525108738",
        "subjectCode": "math",
        "typeId": "SINGLE",
        "layout": "textChoice",
        "passage": "下列结论正确的是( )．",
        "content": null,
        "options": [ { "label": "A", "content": "$-1\\in\\mathbb{N}$" } ],
        "group": null,
        "standardAnswer": "C",
        "standardAnswerLabels": ["C"],
        "userAnswer": "B",
        "source": "prac",
        "recordId": "3026191612601000448",
        "wrongTime": "1785395100000"
      }
    ]
  }
}
```

- 列表元素与 [3.2.2](#322-get-cscaquestions) 的题目对象**同构**：`layout` + **三字段**（`passage` / `content` / `group`）恒出现、无值填 `null`，另附 **`standardAnswer` / `standardAnswerLabels` / `userAnswer`（🟡 2026-10-19 新增）** + `source` / `recordId` / `wrongTime`。（本例为 `textChoice`；错题落在共材料题时 `group` 会非 `null`，形态同 [3.2.2](#322-get-cscaquestions) 示例第 2 / 3 条。）
- 🟡 **三个答案字段的口径**：
  - `standardAnswer` / `standardAnswerLabels`：与 [3.3.3](#333-get-cscaquestionsquestionidsolution) **完全一致**（原值直传；`无` / `NULL` → `null` + `[]`）；
  - `userAnswer` = **最近一次判错**的作答原文（错题表快照列 `user_answer`）——<b>不是首次收录的那一次</b>；重复收录会刷新，与 `wrongTime` 同频；**手动移出不覆盖**（`COALESCE` 兜底）。2026-10-19 之前收录、且无法从作答表回填的历史行为 `null`，前端要能容忍缺席；
  - **不带 `analysis`**：解析仍走 [3.3.3](#333-get-cscaquestionsquestionidsolution)。
- `total` = 该用户错题本**当前**条数（= 「我的」页错题本**角标数**）；`wrongTime` 取 `updated_time`（最近一次收录 / 状态变更时间，列表按它倒序）。

**DELETE /csca/wrong-book/{questionId}**：

```json
{ "code": 200, "message": "操作成功", "data": { "questionId": "2096765985525108738", "inWrongBook": false, "wrongCount": 11 } }
```

**POST /csca/wrong-book/{questionId}/answer**（判分结果）：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "questionId": "2096765985525108738",
    "userAnswer": "B",
    "isCorrect": 1,
    "standardAnswer": "B",
    "standardAnswerLabels": ["B"],
    "analysis": "(A) $\\mathbb{N}$ 是自然数集, $\\mathbb{N}=\\{0,1,2,3,\\cdots\\}$, $-1\\notin\\mathbb{N}$…",
    "inWrongBook": false,
    "wrongCount": 11
  }
}
```

- 与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) `immediate=true` 的响应**完全同构**（`userAnswer` / `isCorrect` / `standardAnswer` / `standardAnswerLabels` / `analysis`），另加 `inWrongBook` / `wrongCount`。（`standardAnswerLabels` 于 2026-10-13 已并入 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid)，两边同一口径，见 [4.4](#44-文档与实现的差异) 第 44 条。）
- `inWrongBook` = 本次作答**之后**该题是否仍在错题本：**答错 → `true`**（已收录 / 复活）；🔴 **答对 → 维持原状**（2026-10-19 起不再自动移出，回查当前态）；未评分 → 同样维持原状。⚠️ 上例 `isCorrect=1` 且 `inWrongBook=false` 表示「该题**原本就不在**错题本，复习答对后仍不在册」；若该题在册，判对后 `inWrongBook` 仍为 `true`（[4.4](#44-文档与实现的差异) 第 62 条）。

##### 业务逻辑

1. **收录 / 移出规则（本组核心）** —— 🔴 **只进不出**（2026-10-19 口径，[4.4](#44-文档与实现的差异) 第 62 条）：
   - **收录**：某次作答判为**错** → `INSERT … ON DUPLICATE KEY UPDATE deleted=0, updated_time=now`（行不存在时同时写 `created_time` / `section` / `source`）。
   - **判对**：**不动** —— 🔴 2026-10-19 起**取消「自动移出」**：经核对，原型与大多数错题本产品都是「答对不移出」，且自动移出会让用户复习时答对一次就丢掉这道错题。**不写库、不刷 `updated_time`**（`wrongTime` 语义仍是「最近一次收录 / 手动移出」的时间）。~~原口径：判对 → `deleted=1, updated_time=now`~~。
   - **手动移出**：`DELETE` → `deleted=1, updated_time=now`（软删）—— 🔴 **这是移出错题本的<u>唯一</u>路径**。
   - ⚠️ **判分为「未评分」（`is_correct=0`，[4.2](#42-答案归一化cscaanswernormalizer) 第三态）时不动** —— 既不移出、也不收录。
   - ⚠️ **手动移出不是"永久拉黑"**：该题**后续再被判错**会重新收录（`deleted` 1→0）。这是"状态由**最近一次判错**驱动"的必然结果；若产品要"永久不再收录"，需再加一列，**本次不做**。
2. **幂等**：`DELETE` 未收录 / 已移出 → 直接返回 `inWrongBook=false`；`POST .../answer` 重复提交同选项 → 结果一致。`DELETE` 也走 `INSERT … ON DUPLICATE KEY UPDATE`（唯一键 `uk_user_question(user_id, question_id)`），**未收录时插入一行 `deleted=1`**（保持幂等、不写"删不存在的行"分支）。
3. **准入校验**：`questionId` 所属卷必须 `exam_type=2 AND version='CSCA'`，否则 `CSCA_QUESTION_NOT_FOUND(8006)`（同 [3.6.1](#361-收藏favorite) 第 2 条）。⚠️ **复习作答不校验"该题是否在错题本内"**（宽松）：答错会把新题**收进来**，答对则是无操作。
4. **`GET` 列表返回 `standardAnswer` / `standardAnswerLabels` / `userAnswer`，但<u>不返回</u> `analysis`**（🟡 **2026-10-19 口径变更**：[4.4](#44-文档与实现的差异) 第 68 条）。原口径「错题本列表也不带答案」已废止 —— 错题本本身就是复习场景，必须能同屏看到「正解 + 我错在哪」。边界：正确答案**现场读 `q.answer`**（与 `/solution` 同源、题库纠错立刻反映），用户答案**读本表快照列 `user_answer`**（🔴 不 join `practice_answer`：复习作答根本不写作答表，事后也查不回那一刻的值 —— 这是「状态自持」约束的唯一延伸）；解析仍走 [3.3.3](#333-get-cscaquestionsquestionidsolution)。
5. **跨轮次、用户维度**：错题本**全局一份**，**不受「再来一轮」影响**（[3.2.1](#321-post-cscarecords) / [0.8](#08-与互动原型的对齐v13)）。⚠️ 与科目进度（[3.1.1](#311-get-cscacatalog) 只算**最新一轮**）**不是一回事** —— 🔴 **唯一键不含轮次**（`uk_user_question(user_id, question_id)`，2026-10-14 定）：同一题无论跨多少轮，**始终只有一行**。🆕 表里另有 `record_id` 一列（第 11 条，2026-10-19 由两列合一），但它**只作「来源记录」快照、不进唯一键** —— 「再来一轮」不会让错题本分裂成多行。
6. **来源维度（`source` 快照列）**：与 [3.6.1](#361-收藏favorite) 第 7 条**同列同义** —— `prac` = 本模块练习链路写入；`exam` = **考试链路（`exam-service`）写入** —— ⚠️ **本模块只写 `prac`；`exam` 待考试侧接入**（超出本模块范围，登记 [4.4](#44-文档与实现的差异) 第 32 条）。列表 `source` 筛选即按此列过滤、**免 join**（这是把它存成快照列的原因）。
7. **判分（复习作答）**：与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 4 条**同一套** `CscaGradingService`（归一化 + 标签集合相等；多选全对才算对）。⚠️ **复习作答无 `recordId` 上下文** → 判分基准取**实时 `question.answer`**（**不读快照**），与 [3.3.3](#333-get-cscaquestionsquestionidsolution) 同口径；`无` / 空 → `is_correct=0`（未评分，兜底）。
8. **复习作答不落 `practice_answer`**（2026-10-13 定）：只判分 + 同步错题本，**不进练习统计 / 不进报告 / 不写任何作答记录**。要"正式再练一次"仍走 [3.2.1](#321-post-cscarecords) 建轮 + [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 作答。
9. **落库表 `csca_question_wrong`**（🆕 与 `csca_question_favorite` 并列的姊妹表；🔴 **2026-10-19 表名加 `csca_` 前缀**（原 `question_wrong`）、加 `language_version` 与 **`user_answer`**、删 `section_mapping`，[4.4](#44-文档与实现的差异) 第 66 / 67 / 69 条）：
   ```sql
   CREATE TABLE csca_question_wrong (
     id                 BIGINT       NOT NULL COMMENT '错题记录ID（雪花）',
     user_id            BIGINT       NOT NULL COMMENT '用户ID',
     question_id        BIGINT       NOT NULL COMMENT '题目ID（question.id）',
     section            VARCHAR(50)  DEFAULT NULL COMMENT '科目码快照（= question.subject_type_mapping）',
     language_version   VARCHAR(20)  DEFAULT NULL COMMENT '语言版本快照（= exam_paper.language_version）',
     user_answer        TEXT         DEFAULT NULL COMMENT '用户答案快照（最近一次判错时的作答原文）',
     source             VARCHAR(20)  NOT NULL DEFAULT 'prac' COMMENT '来源快照：prac 练习 / exam 考试',
     record_id          BIGINT       DEFAULT NULL COMMENT '来源记录ID（按 source 判定：prac→practice_record.id / exam→exam_record.id）',
     deleted            INT          NOT NULL DEFAULT 0 COMMENT '逻辑删除：0 在错题本，1 已移出',
     created_by         BIGINT       DEFAULT NULL COMMENT '创建人（FieldFill.INSERT 自动填充）',
     update_by          BIGINT       DEFAULT NULL COMMENT '更新人（FieldFill.INSERT_UPDATE 自动填充）',
     created_time       BIGINT       DEFAULT NULL COMMENT '首次收录时间（毫秒时间戳）',
     updated_time       BIGINT       DEFAULT NULL COMMENT '最近一次状态变更（收录 / 移出；列表按它倒序）',
     PRIMARY KEY (id),
     UNIQUE KEY uk_user_question (user_id, question_id),
     KEY idx_user_time (user_id, deleted, updated_time)
   ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='错题本';
   ```
   - **与 [3.6.1](#361-收藏favorite) 的 `csca_question_favorite` 互为镜像**（雪花 `BIGINT` 主键 / `deleted INT` / 毫秒 `BIGINT` 时间列 / 同字符集与行格式 / **同含审计列 `created_by` / `update_by`**），**索引集合完全一致**（`uk_user_question` + `idx_user_time`）—— 2026-10-14 收藏表补加 `source`、两表同批补审计列与「来源记录」列（原地是 `practice_record_id` / `exam_record_id` 两列，2026-10-19 已合并为 `record_id`，第 70 条）后两表**再无结构差异**（[4.4](#44-文档与实现的差异) 第 48 / 49 / 50 条）；🆕 **2026-10-19 两表同批加 `language_version`、同批删 `section_mapping`**。🔴 **唯一列差异 = 本表的 `user_answer`（本表 13 列 / 收藏 12 列）**（2026-10-19，[4.4](#44-文档与实现的差异) 第 69 条）：收藏侧不需要「我答了什么」，故**不跟着加**。
   - 🟡 **`user_answer` 是用户答案快照**（2026-10-19 加，`TEXT NULL`，紧随 `language_version`）：
     - **语义 = 最近一次判错的作答原文**（不是首次收录的）—— 与 `updated_time`（= 响应体 `wrongTime`）**同频**，否则会出现「时间是最新的、答案却是几个月前的」错位；
     - **写入口径**：`INSERT … ON DUPLICATE KEY UPDATE user_answer = COALESCE(VALUES(user_answer), user_answer)` —— 判错时**覆盖**、**手动移出（传 `null`）时保留原值**（绝不能把用户答案抹掉）；四条写链路（逐题 / 批量 / 交卷 / 复习作答）都能带上原文；
     - 🔴 **为什么不 join `practice_answer`**：① 复习作答**根本不写作答表**（第 8 条），事后查不回那一刻的值；② 这会让本组「状态自持、列表不读作答表」的约束破功；③ 「收录时」是历史事实，必须冻结成快照；
     - ⚠️ **历史行可能为 `null`**：2026-10-19 建列时从 `practice_answer`（`is_correct = 2` 的最近一次）回填，TEST 7 行 100% 回填成功；**PROD 建表时无历史行**，天然无此问题。
   - 🔴 **正确答案不落本表**：列表读 `q.answer` **现场取**（与 `/solution` 同源，题库纠错立刻反映）；只有「用户答案」才是必须冻结的历史事实。
   - 🔴 **审计列 `created_by` / `update_by` 同 [3.6.1](#361-收藏favorite)**：由 `BaseEntity` + `DBMetaObjectHandler` 自动填充；本组 upsert 是**手写 SQL** → 需显式带入。
   - 🔴 **索引同样精简（2026-10-14）**：不建 `idx_user_section`（科目筛选）与 `idx_user_source`（来源筛选）—— 两者都是**低选择性筛选列**，列表主路径（不传筛选）走 `idx_user_time` 倒序分页；带筛选时用其 `user_id` 前缀命中 + 回表逐行 filter。`section` / `language_version` / `source` **列保留**（免 join 的筛选快照列），只是不为它们单建索引（[4.4](#44-文档与实现的差异) 第 47 条）。
   - 🆕 **`language_version` 是语言快照列**（2026-10-19 加，与收藏同口径）：写侧从 `CscaAnswerQuestionRow#languageVersion`（`answerQuestionColumns` 已带 `p.language_version`）取；**交卷路径取不到 → 传 `null`**（与 `section` 同一取舍，[4.4](#44-文档与实现的差异) 第 61 条 c）。读侧语言筛**直接命中该列、免 join**（第 14 条）。
   - 🔴 **原 `section_mapping` 列已删**（2026-10-19 用户口径「两个表的 section_mapping 不要了」，[4.4](#44-文档与实现的差异) 第 67 条）：恒值 `'SEC_CSCA'`、无查询使用，模块归属改由**表名前缀**表达。
   - 🔴 **唯一键里不带 `deleted`**（同收藏：带上会插出第二行）。
   - `section` / `language_version` / `source` / `record_id` 都是**快照列**（便于免 join 筛选、不参与鉴权）；`source` 记"收录那一刻来自哪条链路"、`record_id` 记"**首次**收录时来自哪一轮"（第 11 条，🟡 两列已于 2026-10-19 合一）。
   - 🟡 **`record_id` 一列承载「来源记录」**（2026-10-19 由两列合一，[4.4](#44-文档与实现的差异) 第 70 条）：收录由作答链路驱动 → 恒写 `record_id`（= 当前轮的 `recordId`，`source='prac'`）。⚠️ **复习作答 / 手动移出（均无轮次上下文）保留原值**：不覆盖、不置空。
10. **计数**：`GET /csca/wrong-book` 的顶层 `total` 即「我的」页错题本角标数（`deleted=0` 行数）；`DELETE` / 复习作答响应里的 `wrongCount` 同义（便于前端**免二次请求**刷新角标）。
11. **来源记录（`record_id` 快照列，2026-10-14 加、🟡 2026-10-19 两列合一）**：与 [3.6.1](#361-收藏favorite) 第 8 条**同列同义** —— 记下**这条错题是在哪一轮练习 / 考试里被判错的**。① **是哪张表的 id 由 `source` 决定**：`source='prac'` → `practice_record.id`，`source='exam'` → `exam_record.id`（[4.4](#44-文档与实现的差异) 第 70 条）；② ⚠️ **本模块只写 `prac`**（收录由作答链路驱动，恒有 `recordId`）；③ 🔴 **只在收录（INSERT）时写、重复收录不覆盖**（与 `source` 同口径，第 6 条）→ 保留**首次收录时的轮次**；④ 🔴 **复习作答**（`POST /csca/wrong-book/{questionId}/answer`）与**手动移出**（`DELETE`）**均无轮次上下文** → 既不写也不清空，**保留原值**（答错复活时该列仍是首次收录那轮）；⑤ **只存快照**：不参与唯一键、不参与任何查询条件与鉴权（列表不按它筛）。
12. **错题时间筛选（`startTime` / `endTime`，2026-10-19 加）** —— 🔴 **只做「自定义区间」，不做 `三天内 / 一周内 / 一个月内` 枚举**：
    - **入参**：`startTime` / `endTime`，**毫秒时间戳**（与库里 `updated_time` 同单位），**闭区间** `[startTime, endTime]`（`>=` / `<=`）；两个都可选、单边合法；`startTime > endTime` → `CSCA_PARAM_OUT_OF_RANGE(8005)`；非数字同样 `8005`。
    - **命中列** = `csca_question_wrong.updated_time` —— 与**列表排序**（`ORDER BY w.updated_time DESC`）、**响应体 `wrongTime`** <u>同一列</u>：筛的、排的、显示的是同一个时间，不会出现「按三天内筛出来、却显示成一个月前」的错位。
    - 🔴 **为什么不给枚举**：「三天内 / 一周内 / 一个月内」本质是**前端的快捷按钮**，点选后由前端按**用户本地时区**算出 `endTime = 当前毫秒`、`startTime = endTime − N × 86400000` 传进来 —— 与「自定义起止日期」**同一条链路**。三个理由：① **时区**只有客户端知道，服务器按 UTC 算「三天前」在跨时区用户那里会偏几小时；② 新增档位（「半年内」/「本年度」）**不必改后端**、不必发版；③ 前端不必为快捷按钮和自定义日期写两套请求。
    - ⚠️ **索引**：落在 `idx_user_time(user_id, deleted, updated_time)` 上 —— `user_id` / `deleted` 等值 + `updated_time` 范围，正是该索引的第三列，**不额外建索引**。
    - ⚠️ **前端注意**：误传 **10 位秒级**时间戳**不会报错**、只会筛出空结果（约束是「毫秒」，后端不猜单位）。
    - 📌 **收藏列表（[3.6.1](#361-收藏favorite) 第 9 条）同日也加上了同一套时间筛**（2026-10-19，[4.4](#44-文档与实现的差异) 第 64 条）：两表 `updated_time` 语义相同（排序键 = 展示时间 = 筛选列），后端复用同一份 `CscaListParams#resolveTimeRange`。
13. 🆕 **排序方向（`order`，2026-10-19 加，[4.4](#44-文档与实现的差异) 第 65 条）**：与 [3.6.1](#361-收藏favorite) 第 10 条**同一套口径**。
    - 🔴 **排序必须在后端**：列表带 `LIMIT / OFFSET` 分页 —— 前端排序只能排到「本次下发的那一页」，翻到第 2 页整体顺序即错。前端**只传方向**，排序由 SQL 做。
    - **只切方向、不切列**：排序键恒为 `updated_time`（= `wrongTime` = 时间筛命中列）。不开放按科目 / 按题号排 —— `idx_user_time(user_id, deleted, updated_time)` 只覆盖这一列，多一种排序列就多一个索引。
    - **取值**：`asc` / `desc`，**忽略大小写**；不传 / 空白 = `desc`（最近错的最前）；**非法 → `8005`，不静默退回缺省**。
    - 🔴 **`id` 兜底必须与 `updated_time` 同向**：`ASC` 配 `id ASC`、`DESC` 配 `id DESC`。混合方向（如 `updated_time ASC, id DESC`）用不上索引有序性 → filesort。
    - **实现**：入参收敛成布尔（`CscaListParams#resolveAscending`）→ XML 两个**写死方向**的 `<choose>` 分支，**不用 `${}` 拼串**；**`countWrongBook` 不吃这个参数**（排序不影响条数）。
14. 🆕 **语言筛选（`languageVersion`，2026-10-19 加，[4.4](#44-文档与实现的差异) 第 66 条）**：与 [3.6.1](#361-收藏favorite) 第 6 条**同一套口径**（用户口径「**错题本也要这个字段**」）。
    - **命中列 = `csca_question_wrong.language_version`**（快照列，`VARCHAR(20)`，与 `exam_paper.language_version` 同类型同宽）→ 🔴 **免 join**：不再 `JOIN question → exam_paper`，一条 SQL 直接筛。
    - **取值校验**：`CscaListParams#resolveOptionalLanguage` → `CSCALanguageVersion.ofCode` → **回写规范码**；空 / 空白 = `null` = **不过滤**（全部语言）；**非法 → `CSCA_LANGUAGE_INVALID(8002)`**（与 `/csca/questions` 的 `languageVersion` 同错误码）。
    - ⚠️ **不传 ≠ 传 `chinese`**：不传是**不过滤**（含 `language_version IS NULL` 的历史行）；传 `chinese` 只命中中文卷。⚠️ 与 [3.6.1](#361-收藏favorite) 入参表原「缺省 `chinese`」的描述**刻意不同** —— 两处统一按「**不传 = 全量**」执行（[4.3](#43-待确认事项) 第 6 条）。
    - **与 `subjectTypeMapping` / `source` / `startTime` / `endTime` 并列**：五个 `<if>` 同处 `wrongBookListFilters` 一份片段，`countWrongBook` 与 `selectWrongPage` **共用** → 计数与列表口径恒一致。
    - ⚠️ **写侧语言快照可能为 `NULL`**：交卷路径（[3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条）取不到语言 → 传 `null`；这类行**不会被任何语言筛命中**。逐题 / 批量作答路径均能取到语言，正常落库。

##### 三层逻辑

| 层 | 类 / 方法 | 职责 |
|---|---|---|
| Controller | `CscaWrongBookController#list` / `#remove` / `#reviewAnswer(...)`（✅ **三个端点全已编码**） | 强鉴权 |
| Service | `CscaWrongBookService#list` / `#remove` / `#reviewAnswer`（✅ **已编码**）+ `#syncAfterGrade(...)`（✅ **已编码**，判分附随同步） | 列表装配 / 移出 / 复习判分 + 同步 / **判错自动收录**（判对不动） |
| Service | `csca/service/CscaGradingService#grade(CscaQuestion, String userAnswer)` | 复习作答判分（**与练习共用**） |
| 题面装配 | `support/CscaQuestionAssembler`（✅ **已编码**；与 `GET /csca/questions` **共用同一份**） | 三字段直传 + 选项保序 + 共材料兜底 + `typeId` 映射 |
| 列表入参解析 | `support/CscaListParams`（✅ **已编码**；与 [3.6.1](#361-收藏favorite) **共用同一份**；语言 `resolveOptionalLanguage` / 时间区间 `resolveTimeRange` / 排序方向 `resolveAscending` **两边共用**） | 科目 / 来源 / **语言** / **时间区间** / **排序方向** / 分页的校验与缺省（两表镜像口径的唯一真源） |
| Mapper | `csca/mapper/CscaWrongBookMapper`（`selectWrongPage` / `countWrongBook` / `upsertWrongs` / `countWrong` / `existsInWrongBook` ✅ **全已编码**；列表**五个筛选项**（科目 / 来源 / 语言 / 起 / 止）全走 `wrongBookListFilters` 一份片段（5 个 `<if>`）；`selectWrongPage` 另带 `ascending`，`countWrongBook` 不带；🟡 `selectWrongPage` 还取 `q.answer` + `w.user_answer`，`upsertWrongs` 写 `user_answer`（`COALESCE` 覆盖）） | 分页查 / 计数 / 幂等 upsert（收录 + 手动移出） |

##### 涉及表

| 表 | 操作 | 用到的列 |
|---|---|---|
| `csca_question_wrong`（**新增**，2026-10-13 定，2026-10-19 加 `csca_` 前缀） | INSERT / UPDATE / SELECT | 见上 |
| `question` / `exam_paper` | SELECT | 准入校验、题面装配、复习判分取 `answer` / `analysis` |

> ⚠️ 本组**不读 `practice_answer`**：错题本状态**自持**（不靠 join 作答表推导）—— 列表页因此**不需要**任何"最近一次作答"查询。

##### 数据流向

```
① 入参    subjectTypeMapping / source / languageVersion / startTime / endTime / order / page(+ token.userId)     ✅ 已实现（CscaListParams，与收藏共用）
② 查库    csca_question_wrong(user_id=?, deleted=0[, section=?][, source=?][, language_version=?][, updated_time BETWEEN ? AND ?]) ──按 updated_time 排序（asc/desc，id 同向兜底）──→ 题 id + user_answer
          question ⋈ exam_paper ──装配题面三字段 + 选项 + layout + q.answer──→ 列表元素
③ 组装    { total, page, pageSize, wrongQuestions[] }
          ⚠️ 元素另带 standardAnswer / standardAnswerLabels（读 q.answer）+ userAnswer（读本表快照列）

── 写侧（2026-10-14 起；2026-10-19 改为「只进不出」）──
④ 判分    三态分流 → 判错 upsertWrongs(deleted=0, user_answer=本次作答) / 判对【不写】 / 未评分不动
⑤ 移出    DELETE → upsertWrongs(deleted=1)（未收录时插一行，保幂等；与收藏镜像）—— 唯一的移出路径
⑥ 复习    POST .../answer → 实时 question.answer 判分（不读快照）→ 同步 → 回 { userAnswer, isCorrect, standardAnswer*, analysis, inWrongBook, wrongCount }
```

> ✅ **已编码（2026-10-14）**：读侧三步**逐条落地**（[4.4](#44-文档与实现的差异) 第 60 条）—— ② 的两次查询（`countWrongBook` / `selectWrongPage`，**共用同一份筛选片段**）与 ③ 的装配（`CscaQuestionAssembler`，**与取题列表同源同构**）已在 `CscaWrongBookServiceImpl#list` 中串联；写侧 ④⑤⑥ 与三处作答链路的自动收录见 [4.4](#44-文档与实现的差异) 第 61 条；🔴 **④ 的「判对」分支已于 2026-10-19 取消**（不再移出），见第 62 条。
> ⚠️ **本图不含「作答态」那一步**（与 [3.6.1](#361-收藏favorite) 的数据流向不同）—— 错题本**状态自持**（本表即「最近一次判分」的物化结果），故**不查 `practice_answer`**、列表元素也**没有** `answered` / `isCorrect` 字段。

---

## 4. 附录

### 4.1 枚举速查

**科目枚举（本模块新增，`csca/support/CscaSubjects`）** —— **目录接口 [3.1.1 `/csca/catalog`](#311-get-cscacatalog) 按库中 5 个原始科目原样返回**（**不做归并、不提供合并别名 `chinese`**，2026-10-13 定）：

| 对外 `code` | 名称 | 库中 `subject_type_mapping`（题级） | 库中 `subject_type`（卷上原始名） | 测试库卷数 / 题数 |
|---|---|---|---|---|
| `arts_chinese` | 文科中文 | `arts_chinese` | `文科中文` | 8 / 640 |
| `science_chinese` | 理科中文 | `science_chinese` | `理科中文` | 5 / 400 |
| `math` | 数学 | `math` | `数学` | 9 / 432 |
| `physics` | 物理 | `physics` | `物理` | 5 / 240 |
| `chemistry` | 化学 | `chemistry` | `化学` | 4 / 192 |

> 🔴 **2026-10-13 拍板：不合并，就给 5 个科目** —— 文科中文 / 理科中文**各一张卡**，服务端**不提供合并别名 `chinese`**（`CscaSubjects` 的别名已删；传 `chinese` → `400`），见 [4.3](#43-待确认事项) 第 11 条。
> ✅ **`question.subject_type_mapping` 已补齐**（2026-10-12 落库，五闸门 G4 通过）：CSCA **1904 行全有值**，5 个码 ↔ 5 个中文名一一对应；`exam_paper.subject_type_mapping` 的 `理科中文` 空值也一并补成 `science_chinese`。**HSK 行未触碰**（全库该列非空行数恰为 1904）。
> ⚠️ **代码/字典侧仍缺 `science_chinese`，入库后务必同步**：① `common/enums/CSCASubjectType`（exam-service 侧，**仅 4 值** `chemistry`/`physics`/`math`/`arts_chinese`，**无** `science_chinese`）；② 线上 `sys_dict_item`（`dict_id=1001` `csca_subject`，**同样只有 4 项**，管理端科目下拉读它）。本模块不复用该枚举，练习侧一律用 `CscaSubjects`；但**考试侧若按 `subject_type_mapping` 精确匹配，会漏掉「理科中文」**——见 [4.4](#44-文档与实现的差异) 第 1 条、[4.3](#43-待确认事项) 第 8 条。
> ⚠️ 原型里的「**教学**」科目**库里不存在**（`exam_type=2` 的 `subject_type` 实测仅上述 5 种），属**原型错误**，**不定义、不实现**（见 [4.5](#45-原型-v13-对照表)）。

**`CSCALanguageVersion`（`common/enums/CSCALanguageVersion.java`，2 值）**

| code | 中文 | 测试库卷数 |
|---|---|---|
| `chinese` | 中文 | 31（**全部**） |
| `english` | 英文 | **0**（待导入） |

**`CscaQuestionTypes`（本模块新增，`csca/support/CscaQuestionTypes`）** —— `question.type_id` 是中文原名（**8 种**），`QuestionType` 枚举里**没有**这些值，故本模块自建一张**映射表** —— 对外**只出 `SINGLE` / `MULTI` 两个值**（**英文枚举码**，用户口径 2026-10-12：「换成英文的不要中文」）：

| `type_id`（库中原名） | 对外 `typeId`（**映射值**，英文枚举码） | 测试库题数 | 出现科目 |
|---|---|---|---|
| `单选` | `SINGLE` | 1071 | 数学 / 物理 / 化学 / 中文 |
| `多选` | **`MULTI`** | 33 | 物理 / 化学 |
| `识解汉字` | `SINGLE` | 100 | 中文 |
| `选词填空` | `SINGLE` | 150 | 中文 |
| `辨析词语` | `SINGLE` | 80 | 中文 |
| `选词成段` | `SINGLE` | 150 | 中文 |
| `补全语句` | `SINGLE` | 220 | 中文 |
| `阅读理解` | `SINGLE` | 100 | 中文 |
| **合计** | `SINGLE` **1871** / `MULTI` **33** | **1904** | — |

> **映射规则（唯一真源）**：`type_id = '多选'` → `MULTI`；**其余一切 → `SINGLE`**。对外**只有两个值**（**英文枚举码**），库中 8 种原名**一律不透出**，而**数据库里的 `type_id` 不做任何改动** —— 用户口径（2026-10-12）：「给前端的是映射值，但是数据库里的不改」。
> 响应字段 **`answerMode` 已取消**：它当初的取值（`SINGLE` / `MULTI`）**就是现在 `typeId` 的这两个值**，信息**完全等价**，留一个就够（见 [4.3](#43-待确认事项) 第 7 条）。
> ⚠️ **`type_id` 与答案格式有 3 行对不上**（实测）：2 题 `type_id='单选'` 但答案是 `B,D` / `A,C`（多答案），1 题 `type_id='多选'` 但答案是 `D`（单答案）。
> 🔴 **题型映射按 `type_id`、不再按答案兜底**（2026-10-12 定）：映射只认 `question.type_id` 这一列。⚠️ **2026-10-13 起「按题型筛选」已不再是接口入参**（[3.2.2](#322-get-cscaquestions) 第 13 条），`typeId` 仅作**出参**供前端定作答控件；原「与筛选口径同源」的理由随之作废，但「**不按答案兜底**」这条**仍成立**。**代价**：上面那 2 题会回 `SINGLE`、前端渲染**单选框**，用户选一个即判错 —— 属**题库数据问题**，**建议题库侧把这 3 行的 `type_id` 改对**（[4.4](#44-文档与实现的差异) 第 9 条）。**判分不受影响**：判分一律按**答案标签集合**比较、**不按 `type_id` 分支**（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 4 条）。

**`CscaLayout`（`question.layout`，题面布局三态）** —— 本模块**新增定义**（该列原为 HSK 听力专用、CSCA 全为 `NULL`；**2026-10-12 已按下方规则补全 1904 行**）：

| `layout` | 语义 | 判定规则（唯一真源） | 题数 / 组数 | 题面落点 | 涉及题型（**库中原名**） |
|---|---|---|---:|---|---|
| `textChoice` | 单题自足 | `group_id IS NULL`（或 `= 0`） | **1644** / — | 题面 `question.passage` → 响应 **`passage`** | 单选 1061 / 补全语句 220 / 选词填空 150 / 识解汉字 100 / 辨析词语 80 / 多选 33 |
| `passageGroup` | 材料与题面**分列** | `group_id` 非空 **且** `question.content` 非空 | **110** / 45 | 题面 `question.content` → 响应 **`content`**；材料 `question_group.passage` → 响应 **`group.passage`** | 阅读理解 100 / 单选 10 |
| `clozeGroup` | **材料即题面**（组内共享词池） | `group_id` 非空 **且** `question.content` 为空 | **150** / 30 | **题面即** `question_group.passage`（含 `__N__` 空位）→ 响应 **`group.passage`**；**`passage` / `content` 均为 `null`** | 选词成段 150 |

> ⚠️ **布局必须按字段判定，不能按 `type_id` 映射**：`单选` **跨两种形态** —— 1061 题扁平（`textChoice`）+ **10 题带材料**（`passageGroup`，`CSCA_文科中文题库2026-6-6_03_161-240` 第 6 节，5 组 × 2 题）；后者与「**阅读理解**」是同一形态，却标了不同题型名。**只按 `type_id` 判 layout 会把这 10 题判错。**
> ⚠️ **命名口径**：`layout` 全库原有 **7 种值、清一色 HSK 听力**（见 [0.7](#07-与-hsk-练习链路的差异为什么要单开一条链路) 第 8 条）；其中 **`textChoice` 与 `passageGroup` 沿用旧名**（语义一致：单题自足 / 共材料分组），**`clozeGroup` 为本模块新增**。服务端**不做 `enum`、原样透传**（与听力一致）——所以 `clozeGroup` 是"约定值"，**不是枚举常量**。
> ⚠️ **`question_group` 没有 `layout` 列**（实测）：layout **只落在题上**。`clozeGroup` 的 150 题**每题都标**，前端任取组内一道即可判定该组形态。
> ⚠️ **三个下发字段与三态的对应（前端渲染唯一依据）**：`passage`（题级 `question.passage`）/ `content`（题级 `question.content`）/ `group.passage`（组级 `question_group.passage`）—— `textChoice` 取 `passage`，`passageGroup` 取题面 `content` + 材料 `group.passage`，`clozeGroup` 取 `group.passage` 当题面；**已无合成字段 `stem`**（见 [4.4](#44-文档与实现的差异) 第 15 条）。
> ⚠️ **`question_group.content` / `option_content` 基本是死列**（见 [4.4](#44-文档与实现的差异) 第 12 条）：CSCA 取组只读 `passage`。判定规则里的 `question.content` 指的**始终是题级** `question.content`，不是组级。

**`CscaSection`（`question.section`，数字字符串）**：`"1"`–`"6"`，**仅内部使用，不透出**（练习粒度为单题，不对客户端暴露"部分"）。

**`PracticeSections`（`practice/core/support/PracticeSections.java`）** —— 需**新增**常量：

| 常量 | 值 | 用途 |
|---|---|---|
| `CSCA` | `"SEC_CSCA"` | CSCA 练习记录的 `section_mapping`（题库里**没有**这个值，只用于记录表） |

**`source`（收藏 / 错题本共用来源列，`csca_question_favorite.source` / `csca_question_wrong.source`，2 值）** —— 两张姊妹表**各有一份同名列**（[3.6.1](#361-收藏favorite) 第 7 条 / [3.6.2](#362-错题本wrong-book) 第 6 条）：

| 取值 | 含义 | 谁写入 |
|---|---|---|
| `prac` | 练习来源 | ✅ 本模块（`practice-service` 作答 / 收藏链路） |
| `exam` | 考试来源 | ⚠️ **考试链路 `exam-service`（待接入）** —— 本模块只写 `prac`；`exam` 要等考试侧同步写入才有数据 |

**`PracticeRecordStatus` / `PracticeReportStatus`**（复用，不新增）：记录 `0 创建中 / 1 作答中 / 2 已放弃 / 3 已提交`；报告 `0 待生成 / 1 生成中 / 2 已生成 / 3 生成失败`。CSCA **同步生成报告**，正常不会停在 `0/1`。

**稳定 ID 号段**（`csca/support/CscaStructureIds`）

| 号段 | 归属 | 生成式 |
|---|---|---|
| `2e18` | 雪花（Excel 导入） | — |
| `7e18` | practice stableId | `7e18 + int(sha256('structure\|<paper_id>\|<module>\|<section>')[:12],16) % 1e18` |
| `8e18` | 口语目录 | — |
| **`6e18`** | **CSCA 科目稳定 ID（本模块新增）** | `6e18 + int(sha256('csca\|<subjectCode>\|<languageVersion>')[:12],16) % 1e18` |

> ⚠️ **不要复用 `7e18`**：那是"卷内某节"的稳定 ID，CSCA 的"科目"是另一个语义层次，混用号段会让排查时无法靠前两位判断 id 类型。

### 4.2 答案归一化（`CscaAnswerNormalizer`）

> 🔴 **适用范围（2026-10-13 定）：归一化只用于「判分」** —— 即 [3.3.1 保存作答](#331-put-cscarecordsrecordidanswersquestionid) 第 4 条与 [3.5.1 交卷](#351-post-cscarecordsrecordidsubmit) 第 4 条（含 `standard_answer_snapshot`）。
> **所有「答案出口」一律原值直传、不做归一化**：[3.3.3 solution](#333-get-cscaquestionsquestionidsolution) 的 `standardAnswer`、交卷响应（`immediate=true`）里的 `standardAnswer`（口径见 [3.3.3](#333-get-cscaquestionsquestionidsolution) 第 1 条）。下方规则表**只在判分链路适用**。

| 步骤 | 规则 |
|---|---|
| 1 | `trim()` 去首尾空白 |
| 2 | 去尾部标点：`.` `。` `,` `，` `;` `；`（**只去尾部**，不删中间） |
| 3 | 去误粘的中文串：删除结尾的 `答案` 二字 |
| 4 | 全角字母 → 半角（`Ａ`→`A`）、转大写 |
| 5 | 多选拆分：按 `,` `，` `/` `、` 空白 切成标签 |
| 6 | 去空标签 → 去重 → **升序排序** |
| 7 | 重新拼接（单选 = 单标签；多选 = `A,D`） |

**判分规则**

| 场景（**一律按归一化后的标签集合比较，不按 `type_id`**） | `is_correct` | `points` |
|---|---|---|
| 集合相等（单选单标签 / 多选多标签；`{A,D}` vs `{D,A}` 视为相同） | `1` | `question.score` |
| 集合不等（错选 / 漏选 / 多选） | `2` | `0` |
| **标准答案为 `无` 或空** | **`0`（未评分）** | `null` |
| 用户未作答（`answered=0`） | `0` | `null` |

> 🟡 **「标准答案为 `无` 或空」这一行是防御性兜底，正常恒不触发（2026-10-13 实测）**：
> TEST / PROD 两库 CSCA **各 1904 题**，`answer` **全部匹配 `^[A-F](,[A-F])*$`** —— **NULL / 空串 / `无` 均为 0 行**（题库侧曾有的 4 行脏值：2 行 `无` + 1 行 `D\n答案` + 1 行 `D.`，**两库均已修正、现已一致**）。
> **为什么保留**：一旦题库回潮再导入 `无` / 空，没有这条兜底就会退回「按标签集合比较」→ 这类题**全部判错**，把题库的数据问题**转嫁成用户扣分**（[3.5.1](#351-post-cscarecordsrecordidsubmit) 注记明确禁止）。
> 同理，[3.4.1](#341-get-cscarecordsrecordid) / [3.4.2](#342-get-cscarecordsrecordidanswer-card) / [3.5.1](#351-post-cscarecordsrecordidsubmit) 三个接口都下发的 **`unGradedCount` 当前恒为 `0`** —— 它**只为兜住这种情况而存在**，不是常规统计字段。

> ✅ **多选题「全对才给分」、无部分给分（2026-10-13 拍板定稿）**：判分**只有「集合相等 / 不等」两态**（见上表），**不按选对几个给比例分**（选对 1 个但漏选 = `2` + `0` 分）。与 `exam-service` 既有口径一致；用户口径：「多选无部分给分，这个要全对才算对」。**将来若要部分分**，只改 `CscaGradingService` 一处（[4.3](#43-待确认事项) 第 4 条）。

### 4.3 待确认事项

| # | 事项 | 影响 | 建议 |
|---|---|---|---|
| 1 | ~~**不冻结题面**~~ ✅ **已定（2026-10-13）：改为「冻结题面」**（[3](#3-接口详细设计) 开头）—— 作答时写 `practice_answer` 的 5 个快照列，**已答过的题一律回快照** | 已答过的题**不再**随题库改动而变（回顾 = 作答当时那一版）；**未作答**的题仍实时读 `question` | 与 HSK 听力 / 阅读同口径。代价：`practice_answer` 行变大（+5 列）；**题库纠错不追溯已答过题的判分**（判分基准也冻结，见 [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 2 条）。**不改表**（5 列早已存在）。见 [4.4](#44-文档与实现的差异) 第 25 条 |
| 2 | ~~**无"本次题集"落点**~~ ✅ **已定（2026-10-13）：给 `practice_record` 加一列 `question_ids`**（JSON，[3.2.1](#321-post-cscarecords) 第 4 条） | 题集**建轮时一次算定并落库** → 两次打开永远是同一批题；`questionCount` **不再是软上限** | 本模块**唯一一次「改表」**（**加列、不新增表**；可空，**HSK 行为 `NULL`**、对既有链路零影响）。DDL 与改库闸门见 [4.4](#44-文档与实现的差异) 第 26 条 / 文末「附 4」 |
| 3 | **`/questions/{id}/solution` 的鉴权** ✅ **半条已定（2026-10-13）**：题目类接口（`/csca/questions*`）**全部改为强鉴权**（[0.2](#02-鉴权与客户端类型)） | 未登录不能看答案（**已收紧**）；但**仍不校验"是否已作答"** | 已采纳「强鉴权」这半条（登录即可，背题模式保留）。**另一半仍待定**：是否进一步要求"必须先作答才能看答案" —— 若要做，只需在本接口加一次 `practice_answer` 存在性校验，代价是背题模式与离线看解析失效 |
| 4 | ~~多选无部分给分~~ ✅ **已定（2026-10-13）：无部分给分、全对才算对**（[4.2](#42-答案归一化cscaanswernormalizer)）。**余下未定**：报告无"得分"持久列（[3.5.1](#351-post-cscarecordsrecordidsubmit) 第 5 条） | 判分**只有「集合相等 / 不等」两态**，得分每次现算；多选**全对才得分**、**不按比例给分** | ① 无部分给分 —— **零代码动作**（当前实现即此口径，[4.4](#44-文档与实现的差异) 第 29 条）；② 得分若要落库，需给 `practice_report` 加 `score` / `full_score` 两列（**要改表**；与本模块已有的一次「加列」同性质，见 [4.4](#44-文档与实现的差异) 第 26 条） |
| 5 | **科目名 / 题型名多语言** ✅ **已定（2026-10-12）**：`CscaSubjects` 只有中文；`typeId` 只出映射值 | 无 —— **服务端不解析 `Accept-Language`**、也不加 `*_en` / `*_vi` 字段：`subjectType` 回**库中中文原名**，`typeId` 回**映射值**（`SINGLE` / `MULTI`，**英文枚举码**） | **界面文案多语言由前端字典处理**（用户口径：前端自己弄语言）。⚠️ 细粒度题型名（`识解汉字` / `选词填空`…）**本次不下发**；若产品要按它展示或筛选，需另加字段（**本次不做**） |
| 6 | ~~是否补 `CSCA_*` 业务码~~ ✅ **已定（2026-10-13）：补**（清单见 [0.5](#05-错误码)） | 号段 **8001–8099**（7001–7099 已归 `COURSE_*`）；8 个码覆盖原 `400` / `404` 字面量场景 | 用户口径「可以补上」。⚠️ **号段与写字课 / 拼音课不冲突**（CSCA 从 8001 起）。<br>✅ **代码已同步（2026-10-13）**：码表落在 `practice-service` 的 `csca/support/CscaErrorCode`（**不写进 common `ErrorCode`**）；`csca` 包各处 `BusinessException` 已改抛新码（[4.4](#44-文档与实现的差异) 第 30 条） |
| 7 | ~~`answer_mode = 'MULTI'` 是新值~~ ✅ **已消解（2026-10-12）**：`practice_part_setting.answer_mode` 的枚举是 `SINGLE` / `MATCH` / `ORDER`，**没有 `MULTI`** | 已**不需要**该值 —— 响应字段 `answerMode`（`SINGLE` / `MULTI`）**已取消**，题型只回映射值 `SINGLE` / `MULTI`（英文码，与 `practice_part_setting` 毫无关系；本模块也不用该表）<br>⚠️ **别与 `practice_part_setting.answer_mode` 混为一谈**：改英文码后两边都出现 `SINGLE`，但**纯属字母巧合** —— `answer_mode` 是"部分配置表"的作答交互类型（`SINGLE` / `MATCH` / `ORDER`，本模块不读），本模块的 `typeId` 是"**从 `question.type_id` 现场映射**"的题型码，**判分与取题都不碰 `answer_mode`** | 无需动作。将来若真要把「多选」写进 `practice_part_setting`，再同步扩该列的枚举注释 |
| 8 | ~~`理科中文` 的 `subject_type_mapping` 为 `NULL`~~ ✅ **已解决**（2026-10-12 补数据，G4 通过） | 按 `subject_type_mapping` 精确匹配会漏掉理科中文 | 已补 `exam_paper` 5 行 + `question` 1904 行（值 `science_chinese`）。**遗留半条**：`CSCASubjectType` 枚举与 `sys_dict_item` 仍缺该值 → 考试侧若按 mapping 匹配仍会漏，需同步补（[4.4](#44-文档与实现的差异) 第 1 条） |
| 9 | **没有 `english` 卷**（[0.3](#03-语言版本languageversion-与界面文案是两件事)） | 英文 CSCA 不可用 | 接口已预留 `languageVersion`，导入英文卷后**无需改协议** |
| **10** | ~~收藏是否落库~~ ✅ **已定（2026-10-13）：落库，并新建 `csca_question_favorite`**（原名 `question_favorite`，2026-10-19 加 `csca_` 前缀；设计见 [3.6.1](#361-收藏favorite) 业务逻辑第 5 条） | 本模块**新增的业务表之一**（另一张是错题本 `csca_question_wrong`，⚠️ 均区别于 `practice_record.question_ids` 的「加列」）；**✅ TEST 已建表（2026-10-14、2026-10-19 重构）**、⚠️ **PROD 待建** | 用户口径「收藏要落库，把 question_favorite 设计一下」。换设备可取回、支持「我的收藏」列表；[第 11–13 号接口](#21-端点清单)**全部实现**。<br>🔴 **待办**：① ~~TEST 建表~~ ✅ 已建；**PROD 待建**（见文末「附 5」）；② `CscaFavoriteController` / `CscaFavoriteService` / `CscaFavoriteMapper`(+`.xml`) 编码（[4.4](#44-文档与实现的差异) 第 31 条） |
| **11** | ~~「中文」是否合并文/理科~~ ✅ **已定（2026-10-13）：不合并，就给 5 个科目**（[3.1.1](#311-get-cscacatalog) 的科目口径） | **科目列表恒为 5 条**：文科中文 640 / 理科中文 400 / 数学 432 / 物理 240 / 化学 192；**`chinese` 合并别名取消** | 用户口径「不合并，就给五个科目」。<br>🔴 **代码待同步**：`csca/support/CscaSubjects` 删 `RESOLUTION` 的 `"chinese"` 行 + `ALIAS_NAMES`（别名随之失效）—— 否则传 `chinese` 仍命中两科、与本文不符（[4.4](#44-文档与实现的差异) 第 27 条） |
| **12** | ~~跨语言同题去重~~ ✅ **已定（2026-10-13）：不去重、分开记**（[3.1.1](#311-get-cscacatalog) 业务逻辑第 3 条 / [3.2.2](#322-get-cscaquestions) 第 5 条） | **这正是要的**：中 / 英卷是**两套不同的卷子**（不同 `question.id`），同一考点在中文卷与英文卷**各记一次** | 用户口径「中文和英语是两套不同卷子，就是要分开记、不能去重」。故**去重键恒为 `question.id`**（`COUNT(DISTINCT question_id)` 原样保留），**不需要**任何"题目组"标识或序号归一（[4.4](#44-文档与实现的差异) 第 28 条） |
| **13** | **乱序做成开关** ✅ **已定（2026-10-12）**（[3.2.2](#322-get-cscaquestions)） | 原型「开始练习」是整体乱序；本模块提供 `shuffle` 开关（**缺省 `false` = 自然序**），`true` 时乱序，且 **`seed` 必填** | 默认**关闭**、不影响任何既有调用方；要乱序时 `shuffle=true&seed=xxx`（`seed` 建议传 `recordId`）。**`shuffle=true` 未传 `seed` → `400`**；**不提供**无种子的 `RAND()` 形态（翻页会重复） |
| **14** | **「全部练完」之后怎么办** ✅ **已定（2026-10-13）**（[3.2.1](#321-post-cscarecords) 第 3/5 条 / [3.2.2](#322-get-cscaquestions) 第 5 条 / [3.1.1](#311-get-cscacatalog) 业务逻辑第 3 条） | 去重后 `availableCount` 可能为 0；此时 [3.2.1](#321-post-cscarecords) 会 `404`（该科目暂无未练题目） | **两个出口，都不删数据**：① **「重做一轮」** = `POST /csca/records {restart:true}` 起新轮 —— **新轮题集直接取全量**（不再 `404`），新轮成为「最新一轮」，**科目进度自动归零后重新累计**；② ~~**只复习、不清进度** = 不起新轮，取题带 `includeAnswered=true` 取全量~~ **已取消（2026-10-13 第 36 条）** —— `includeAnswered` 入参已删；**复习不换题集**：切「背题模式」仍用当前 `recordId` 的题集，只是对当前题调 [`/csca/questions/{id}/solution`](#333-get-cscaquestionsquestionidsolution) 把答案亮出来；要看**整科**则走 ①（`restart:true`，新轮题集即全量）。用户口径：「进度清零然后重新算最新的进度」+「按最新一轮重算」（[4.4](#44-文档与实现的差异) 第 18 条） |
| **15** | ~~错题本是否落库~~ ✅ **已定（2026-10-13）：落库，并新建 `csca_question_wrong`**（原名 `question_wrong`，2026-10-19 加 `csca_` 前缀；设计见 [3.6.2](#362-错题本wrong-book)） | 与收藏并列的**第二张新增业务表**（⚠️ 仍区别于 `practice_record.question_ids` 的「加列」）；**✅ TEST 已建表（2026-10-14、2026-10-19 重构）**、⚠️ **PROD 待建** | 用户口径：「现在原型新增了错题本，你设计错题本的接口」。⚠️ **两条与原型不同**：① ~~**答对自动移出**（原型是「答对不自动移除」，按用户口径改 —— [4.4](#44-文档与实现的差异) 第 32 条）~~ 🔴 **2026-10-19 已回退为「答对不移出」**（错题本只进不出，见 [4.4](#44-文档与实现的差异) 第 62 条）；② **带 `source` 来源维度**（`prac` / `exam`）。<br>🔴 **待办**：① ~~TEST 建表~~ ✅ 已建；**PROD 待建**（见文末「附 6」）；② `CscaWrongBookController` / `CscaWrongBookService` / `CscaWrongBookMapper`(+`.xml`) 编码；③ **作答链路同步写入**（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) / [3.5.1](#351-post-cscarecordsrecordidsubmit) / [3.3.2](#332-post-cscarecordsrecordidanswersbatch)）；④ **考试侧 `source=exam` 待接入**（超本模块范围） |
| **16** | 🔵 **收藏列表是否跨 HSK**（拟加 `examCategory`（`CSCA` / `HSK`）类别入参 + HSK `level` 等级入参） ✅ **已定（2026-10-14）：不跨，维持 CSCA 单类别** | 本模块收藏接口**不加** `examCategory` / `level` 入参 —— 入参面保持 [3.6.1](#361-收藏favorite) 现状（`subjectTypeMapping` / `source` / `languageVersion` / `startTime` / `endTime` / `order` / `withAnswerState` / `page` / `pageSize`）；`csca_question_favorite` **只承载 CSCA**（模块归属由表名前缀表达，2026-10-19 起**已无 `section_mapping` 列**） | 用户口径：「不写HSK的，写CSCA科目入参筛选」→ 追问后明确「**就是现有那个，不用改**」（[3.6.1](#361-收藏favorite) 入参表的 `subjectTypeMapping`，**可选**、不传 = 全部科目、命中快照列 `f.section`、非法 → `8001`）。<br>⚠️ **为什么当初会讨论**：表结构当初预留了 HSK（旧 §3.6.1 第 5 条的恒值 `section_mapping` 列），且 `exam_paper.exam_type`（1 = HSK / 2 = CSCA）+ `exam_paper.level`（HSK `1`–`6` / `7-9`、CSCA 恒 `NULL`）现成可筛 —— 但**本轮不做**。<br>🔴 **2026-10-19 口径收紧**：`section_mapping` 已随 [4.4](#44-文档与实现的差异) 第 67 条删除、表名也已 `csca_` 前缀化 → 「零改表并入 HSK」的**原前提不再成立**；真要做需**重新评估**（新增 `exam_category` 列 + 改表名/建同构 HSK 表二选一）。<br>🔴 **另一条遗留前提**：HSK 侧**本就没有收藏写入链路**（`PUT` / `DELETE` 准入 `exam_type = 2 AND version = 'CSCA'`，HSK 题回 `8006`），故即便加了类别入参，`examCategory=HSK` 也只会是空结果。将来若要把 HSK 收藏并入，须连**写侧准入**一起另立议题 |

### 4.4 文档与实现的差异

编码前建议一并处理（**未确认不动数据**，此处只登记）：

| # | 位置 | 差异 | 建议 |
|---|---|---|---|
| 1 | `exam_paper` / `question` 的 `subject_type_mapping` | ✅ **已于 2026-10-12 补齐**（走五闸门、G4 回读核对通过）：`exam_paper` 理科中文 5 行 `NULL → 'science_chinese'`；`question` CSCA 1904 行按所属卷继承（`arts_chinese` 640 / `math` 432 / `science_chinese` 400 / `physics` 240 / `chemistry` 192）；**HSK 行未触碰**。**但代码与字典侧仍缺该值**：`common/enums/CSCASubjectType` 只有 4 值、线上 `sys_dict_item`（`csca_subject`）只有 4 项 | **练习侧现在可直接依赖该列**（统计与取题都按 `q.subject_type_mapping`，不必 join `exam_paper` 换科目）。**待办（不在本次范围）**：① `CSCASubjectType` 加 `SCIENCE_CHINESE("science_chinese", "理科中文")`；② `sys_dict_item` 补一项（`dict_id=1001` / `item_text='理科中文'` / `item_value='science_chinese'` / `sort_order` 顺延）——否则**考试侧按 mapping 匹配会漏「理科中文」、管理端科目下拉也选不到它** |
| 2 | `question.passage` / `content` / `analysis` | 实测数学卷题干在 `passage`、`content` 为 `NULL`；题干、选项、**解析**都含 **LaTeX 原文**（`$A=\{x\in\mathbb{Z}\|...\}$`、`\frac`、上标）；**文科/理科中文的解析有 OCR 残留拼音插空格**（`zh á o` / `y ī ng`） | ① 服务端**不做合成**：`passage` / `content` / `group.passage` 三字段原样透传，题面按 `layout` 取（[3.2.2](#322-get-cscaquestions)）；② **客户端必须渲染 LaTeX**（题干/选项/解析里就是未转义原文，不渲染会看到一片源码），若用 KaTeX 注意 `$` 与 `\$` 转义；③ OCR 空格**由题库侧修**，接口原样透传；④ 题面 / 材料 / 选项里还有 **HTML 片段**（`<u>着</u>` / `<p>…</p>`，实测 `passage` 158 行、`option_content` 55 行、`question_group.passage` 40 行含标签），前端须按**富文本**渲染（与 LaTeX 同处理，别转义） |
| 3 | `exam-service` 的 `submitCscaExam` | **按单选判 CSCA 所有题**（`ExamRecordServiceImpl:589`），而题库实有 **34 题是多答案** → 这些题在**考试侧必然判错** | **本模块不复用该逻辑**，独立实现 `CscaGradingService`（标签集合相等）。**考试侧是否需要同步修**见 [4.3](#43-待确认事项) —— 属 exam-service 范围，本文只登记 |
| 4 | `ErrorCode` | 无 `404` 项；`QUESTION_NOT_FOUND(2001)` 语义相近 | ✅ **已定（2026-10-13）**：本模块**不再写裸字面量**，改用新增的 `CSCA_*` 业务码（**8001–8099** 段，清单见 [0.5](#05-错误码)）；`409` 仍复用既有 `RECORD_NOT_IN_PROGRESS(2004)` / `RECORD_VERSION_CONFLICT(2003)`。✅ **代码已同步（2026-10-13）**，见第 30 条 |
| 5 | `exam_paper_structure` | **`version='CSCA'` 只有 4 行**（`id` 309–312，`paper_id=1` 占位卷，`section_name` 统一"第一部分"，`subject_type_mapping` = `arts_chinese` / `chemistry` / `physics` / `math`，**缺理科中文**），且**不指向任何真实 CSCA 卷** | 这 4 行是 `exam-service` 的 `getCscaPaperDetail` 用的"模板行"。**本模块不用它**（CSCA 无逐卷结构）；但如果有人按它推导"CSCA 有结构"，会被误导——建议在这 4 行或文档里标注"exam 侧模板，非练习结构" |
| 6 | `question.section_mapping` / `type_id_mapping` | CSCA 1904 行**全为 `NULL`**（⚠️ 同表的 `subject_type_mapping` **不在此列** —— 它已补齐，见第 1 条） | **本次不改**（用户已定）。因此 `PracticeQuestionMapper.selectByPart` / `selectCountsByParts` **对 CSCA 全部不可用**，必须用 `CscaQuestionMapper` 的新 SQL |
| 7 | `question_group` | CSCA 有 **75 行 / 11 卷**；`question.group_id` **有值的是 260 题**（文科中文 / 理科中文的阅读理解类），数学 / 物理 / 化学**无分组** | 按 `group_id` join 为主、`number ∈ [start_number, end_number]` 为兜底。若将来统一回填 `group_id`，可去掉兜底分支 |
| 8 | `CSCA` 卷的 `level` | 31 卷 `level` **全为 `NULL`** | 不要在代码里 `Integer.parseInt(paper.getLevel())`（会 `NPE`）。CSCA 链路**完全不读 `level`** |
| 9 | `question.type_id` 与 `question.answer` 不一致 | 3 行对不上：2 题 `type_id='单选'` 但答案为 `B,D` / `A,C`；1 题 `type_id='多选'` 但答案为 `D`（题 id：`2067118915733561367` / `2067119004204015620` / `2067119686520807435`） | ① **判分**：本模块按**答案标签集合**比较，不受影响（[4.2](#42-答案归一化cscaanswernormalizer)）；② **题型映射**：`typeId` 按 `type_id` 原名映射、**不做答案兜底**（[4.1](#41-枚举速查)），故这 2 题会回 `SINGLE`、前端渲染单选框 —— **建议题库侧把这 3 行的 `type_id` 改对**（改完映射与题面作答控件即自洽，服务端无需改码） |
| **10** | **本文旧口径 vs 实现**（2026-10-12 同步） | 文档原定 `/csca/questions` 用 `order` / `seed` 做乱序、且按 `Accept-Language` 回多语言文案 | **最终形态**：乱序改为**开关 `shuffle`（缺省关）+ `seed`（开关打开时必填）**，只有确定性乱序一种（[3.2.2](#322-get-cscaquestions)）；**服务端不解析 `Accept-Language`**（`subjectType` 回库中中文原名，`typeId` 回映射值 `SINGLE` / `MULTI`）（[0.3](#03-语言版本languageversion-与界面文案是两件事) / [4.3](#43-待确认事项) 第 5 条） |
| **11** | **`/csca/questions`「文档 vs 实现」复核**（2026-10-12） | 文档原写：共材料 Mapper 是 `CscaQuestionGroupMapper#selectByRanges`（**该类/方法不存在**）、"按 `group_id` 批量 join"、Controller 带 `HttpServletRequest`、题干 `content` 回退是"将来"之事 | **已按代码改正**（[3.2.2](#322-get-cscaquestions)）：共材料 = `practice/core/mapper/PracticeQuestionGroupMapper#selectList`（按本页 `paper_id IN` 一次取回 + **内存索引**，`group_id` 空时按区间兜底）；Controller 为 `questions(CscaQuestionQuery)`（**免登录、不读 Token**）⚠️ **已被第 17 条推翻**（现为强鉴权 + 带 `HttpServletRequest` / `userId`）；`content` 回退当年已实现，**现整体取消**（改为直传原始三字段，见第 15 条）；~~`answerMode` 增加**答案标签数兜底**~~ ⚠️ **已被后续决策推翻**：题型改为回映射值 `SINGLE` / `MULTI`、`answerMode` 字段取消（见第 14 条）；顶层 `passage` 原系 `group.passage` 冗余 —— ⚠️ **已被第 15 条推翻**：现为**题级** `question.passage`，组材料只看 `group.passage` |
| **12** | `question_group.content` / `question_group.option_content` | **基本是死列**（实测全库 `question_group` 1036 行）：`content` 仅 51 行非空，且这 51 行的 `JSON_LENGTH` **全为 0**（值就是 `[]`）；`option_content` 全库仅 48 行有值、**CSCA 为 0** | **CSCA 零使用** —— 取组一律走 `question_group.passage`（现有 `CscaQuestionQueryServiceImpl` 也只读它，**无需改**）。**别照着列名想当然去读 `question_group.content`** |
| **13** | `clozeGroup` 题（150 题）的题面字段与 `layout` 下发 ✅ **已闭环（2026-10-12）** | 这 150 题 `question.passage` 与 `question.content` **两列皆空**（下发的 `passage` / `content` 两个字段都是 `null`，**实现行为本身正确**），题面只在 `question_group.passage`；~~既有实现尚未在响应里下发 `layout`~~ → **已补上下发** | **代码已改**：① `CscaQuestionRow` 加 `layout`；② `CscaQuestionResponse` 加 `layout`（置于 `typeId` 之后，与 [3.2.2](#322-get-cscaquestions) 返回示例同序）；③ `CscaQuestionMapper.xml` 的 SELECT 加 `q.layout`；④ `CscaQuestionQueryServiceImpl` 用 `.layout(row.getLayout())` **直传库值**（不推算、不换算）。前端对 `layout='clozeGroup'` 用 `group.passage` 作题面、`__N__` 作输入位；`layout='passageGroup'` 材料与题面分列。**⚠️ 前端不得用「题面字段为空就跳过」代替 `layout` 分流**，否则这 150 题会被整段吞掉。题面字段本身的口径变更见第 15 条 |
| **14** | **题型口径改「映射值」**（2026-10-12 用户口径：「给前端的是映射值，但是数据库里的不改」） | 原口径：`typeId` 直回 `question.type_id` 中文原名（8 种），另设 `answerMode`（`SINGLE` / `MULTI`） | **已按新口径改**（[4.1](#41-枚举速查) / [3.2.2](#322-get-cscaquestions) 第 13 条）：① `typeId` 改回**映射值** —— `MULTI` 仅 `type_id='多选'`，**其余一律 `SINGLE`**，**库中 `type_id` 一个字符都不动**；② **删除**响应字段 `answerMode`（与 `typeId` 信息重复）；③ 入参 `typeId` 同步只认映射值 `SINGLE` / `MULTI`（其它 → `400`），筛选与显示同源；④ 取题 SQL **不再取 `q.answer`**（映射不看答案）；⑤ **映射值改用英文枚举码 `SINGLE` / `MULTI`**（追加口径：「**换成英文的不要中文**」）—— 库中 `type_id` 的中文原名仍**一字不改**，筛选入参同步只认这两个英文码；`.xml` 的 `<choose>` 判据改比 `'MULTI'`、**落 SQL 仍比中文 `'多选'`**，`CscaQuestionTypes` 新增常量 `DB_TYPE_MULTI = "多选"` 专供判定（**别把「对外取值」与「库中原名」混用**）。**代码同步**：`csca/support/CscaQuestionTypes`（`display` / `isMulti` 改判 `DB_TYPE_MULTI`）/ `CscaQuestionResponse`（去 `answerMode`）/ `CscaQuestionQuery` / `CscaQuestionRow` / `CscaQuestionQueryServiceImpl`（`resolveTypeId` 只放行两码）/ `CscaQuestionMapper`（+`.xml`） |
| **15** | **题面字段：合成 `stem` → 下发「题目材料」原始三字段** ✅ **已闭环（2026-10-13）**（2026-10-12 用户口径：「修改文档为下发题目材料判断 layout 的那三个字段」+「不要 `stem` 了」） | 原设计：服务端把 `question.passage`（空白则回退 `question.content`）**合成一个 `stem`** 下发，并把 `group.passage` 冗余到**顶层 `passage`** | **文档已改 + 代码已同步**（[3.2.2](#322-get-cscaquestions) / [4.1](#41-枚举速查)）：① **取消 `stem`**；② 顶层 `passage` 改为**题级** `question.passage`（不再冗余组材料，组材料只看 `group.passage`）；③ **新增 `content`**（题级 `question.content`）；④ 三字段与 `layout` 三态一一对应 —— `textChoice`→`passage`、`passageGroup`→题面 `content` + 材料 `group.passage`、`clozeGroup`→题面 `group.passage`；⑤ 顺带把 `typeId` 的职责收口为**作答值域（单值 / 多值作答）**，修掉与「按 `layout` 分流」自相矛盾的那句；⑥ **三字段恒出现、无值填 `null`**（收藏列表 / 单题详情 / 题集三处示例同构）。<br>✅ **代码已同步（2026-10-13）**：`CscaQuestionResponse` **删 `stem`**、**加 `content`**、`passage` 改为题级语义（字段序 `… typeId / layout / passage / content / options / score / group`，与返回示例同序）；`CscaQuestionQueryServiceImpl` **删 `stemOf`**、装配改为 `passage` / `content` / `group.passage` 三者直传（**不做「空白回退」合成**）；`CscaQuestionMapper.xml` 的 SELECT 本就取 `q.passage` / `q.content`（**无需改**） |
| **16** | **删除响应字段 `subjectName`** ✅ **已闭环（2026-10-13）**（2026-10-12 用户口径：「`"subjectName": "数学"` 这个字段删掉」） | 原设计：`/csca/questions` 顶层、`/csca/records*`、`/csca/progress` 的 `subjects[]`、`/csca/favorites` 列表元素**都下发了科目中文名** | **文档已删 + 代码已同步**（示例 6 处 + 映射对照表）：科目中文名改由**前端按 `subjectCode` 自行映射**（`subjectCode` 仍回显，**5 个原始值之一**；[0.3](#03-语言版本languageversion-与界面文案是两件事) 的口径不变——服务端不做文案多语言）。✅ **代码已同步（2026-10-13）**：`CscaQuestionsResponse` 删 `subjectName`、`CscaQuestionQueryServiceImpl` 去掉 `.subjectName(...)`；`CscaSubjects#nameOf` **保留**（`/csca/catalog` 的 `subjectType` 仍用它） |
| **17** | **取题口径改造：去 `paperId` + 题目接口强鉴权 + 按用户去重**（2026-10-13 用户口径：「文档不要根据 paperId 取题，要根据 subject_type_mapping 和 languageVersion 来取，并且[做过的]不重复出现」+「带用户维度，有 token 才能访问题目」+「全部题目接口」+「按记录去重」+「`totalQuestions` 改成剩余未练题数」） | 原口径：`/csca/questions` **免登录**、可按 `paperId` 取某张卷的题；`POST /csca/records` 有 `paperId` 且与 `questionCount` 互斥；**无任何"已练去重"** | **已按新口径改文档**：① `/csca/questions` **删 `paperId`**，改按 `subjectTypeMapping` + `languageVersion` 取题；② **新增 `recordId`**（去重基准）与 **`includeAnswered`**（重做开关，缺省 `false`）；③ `/csca/questions*` **三个接口全部强鉴权**（未登录 `401`）；④ 默认**排除该用户在「其它记录」里已答过的题**（`NOT EXISTS` 子查询，见 [3.2.2](#322-get-cscaquestions) 第 5 条），顶层 `total` **改名 `availableCount`**（语义仍是"剩余题数"）；⑤ `POST /csca/records` **删 `paperId`**、`totalQuestions` 改"剩余未练题数"、剩余 0 → `404`；⑥ **`/csca/questions` 不可公共缓存**（用户维度）。<br>✅ **取题侧代码已同步（2026-10-13）**：`CscaQuestionQuery` **删 `paperId`**、**加 `recordId` / `includeAnswered`**；`CscaQuestionMapper`(+`.xml`) **删 `paperId` 分支**、改 `selectBySubject`/`countBySubject` 收 `excludeAnsweredUserId`（`NOT EXISTS` 去重）+ 新增 `selectByQuestionIds`（固定题集）；`CscaQuestionQueryServiceImpl#query(Long userId, CscaQuestionQuery)` **加 `userId` 与 `recordId` 归属校验**、实现题集三态；`CscaCatalogController#questions` **加 `HttpServletRequest` + 强鉴权**（`requireAuthenticatedAppUserId`，未登录 → `401`）；网关白名单**去掉** `/api/practice/csca/questions*`。<br>✅ **建轮（records）侧已同步（2026-10-13，见第 38 条）**：`CscaRecordStartRequest` **无 `paperId`**（Body 只有 科目 / 语言 / 题量 / `restart` / 幂等键）；`CscaRecordService#start` 题量按「剩余未练」算、剩余 0 → `CSCA_NO_QUESTION_AVAILABLE(8008)` |
| **18** | **科目进度改「最新一轮」口径：重做一轮 = 进度清零重算**（2026-10-13 用户口径：「我想要的是进度清零然后重新算最新的进度」+「按最新一轮重算」） | 原口径：[3.1.1](#311-get-cscacatalog) 的进度按 `user_id + section_mapping` **历次累计**（SQL 里没有轮次维度）→ `restart=true` 弃旧轮后**科目卡数字一点都不变**，且去重把旧轮全排除 → 新轮题集为 0、直接撞 `404` | **已按新口径改文档**（[3.1.1](#311-get-cscacatalog) 业务逻辑第 3 条 + 关键 SQL② / [3.2.1](#321-post-cscarecords) 第 5 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 7 条 / [3.4.1](#341-get-cscarecordsrecordid) 区分注记 / [0.8](#08-与互动原型的对齐v13) / [1.2](#12-场景--接口对照表)）：① 进度**只统计该科目最后开的那一轮**（`practice_record` 按 `section` 取 `MAX(id)`，雪花 id 单调）；② **零写操作** —— 不删、不改任何 `practice_answer`，旧轮仅退出统计；③ 分母 `questionCount` / `totalQuestions` 仍是**科目总题数**（题库维度，与轮次无关）；④ `restart=true` 因此天然就是「进度清零 + 重新累计」，不需要新增删除/重置接口。<br>🔴 **代码待同步**：`CscaAnswerMapper#selectProgressBySubject`（`.xml`）与 `CscaQuestionMapper#selectSubjectStats` 的进度段都要加 `WITH latest (section, MAX(id))` + `JOIN practice_record`；`CscaProgressService` / `CscaCatalogService` 签名不用改（`userId` 已有），但要核对 `.xml` 里 `practice_answer` 的过滤是否漏了 `practice_record_id` |
| **19** | **进度条分母口径拍板：分母取「科目总题数」**（2026-10-13 用户口径：「① 分母取科目总题数」） | 上一版把两条路并列写着（科目总量 / 本轮题数）**却未定默认**，实现时无从下手 | **已钉死**（[3.1.1](#311-get-cscacatalog) 注记 + 业务逻辑第 3 条）：① 科目卡与进度页的进度 = `practicedQuestions / questionCount`，**分母 `questionCount` / `totalQuestions` 恒为科目总题数**（按 `subject_type_mapping` + `language_version` 现算，题库维度，**与轮次无关、与 `questionCount` 本次练多少题无关**）；② **已知后果（接受）**：`questionCount:N` 只练前 N 题时，练完进度条仍只到 `N / 科目总量`，**只有练完整科才 100%**；③ 若将来要「本轮进度条」（分母 = 本轮题数），**不改科目卡**，用 [3.4.1](#341-get-cscarecordsrecordid) / [3.4.2](#342-get-cscarecordsrecordidanswer-card) 的 `totalQuestions`（`record.total_questions`）另算 |
| **20** | **`/csca/questions` 顶层 `total` 改名 `availableCount`**（2026-10-13 用户口径：「total 字段改一下名字，因为这样太容易混淆了」） | 原名 `total` 与 `totalQuestions`（科目总量 / 本轮题数）**撞脸**，读文档时极易混；同一文档里还有另外两个 `total`，三者语义各异 | **已改文档**（只动这一处，[3.2.2](#322-get-cscaquestions)：返回示例 + 返回说明 + 业务逻辑第 10 条 + 字段对照表）：顶层 `total` → **`availableCount`**，语义不变（= 去重后剩余题数；`includeAnswered=true` 时为科目总量）。<br>⚠️ **另两处 `total` 按用户口径保留不动**：`/csca/favorites` 顶层 `total`（收藏总数，标准分页语义）、`/csca/records/{id}` 的 `byType[].total`（该题型在本次题集里的题数）。<br>✅ **代码已同步（2026-10-13）**：`CscaQuestionsResponse#total` → **`availableCount`**（字段 + 装配处 `.availableCount(...)`） |
| **21** | **答案出口取消归一化：`standardAnswer` 原值直传**（2026-10-13 用户口径：「GET /csca/questions/{questionId}/solution …… **不做答案归一化**」+「原值直传，留 labels」+「两个出口一起改」+「`无` / NULL 保持特判为 `null`」） | 原口径：solution 与交卷响应的 `standardAnswer` 都**先归一化再下发** —— 同一题的答案在「出口」与「库里」长得不一样（脏值 `"D\n答案"` 被洗成 `D`、`"D."` 洗成 `D`），前端高亮 / 比对时对不上原文 | **已改文档**：① [3.3.3](#333-get-cscaquestionsquestionidsolution) 第 1 条改为**原值直传**（`standardAnswer` = `question.answer` 原文）；② `standardAnswerLabels` **保留但只按分隔符切分**（切 → 丢空串 → **保序**；不 trim 单标签 / 不转大写 / 不去「答案」/ 不去重 / 不排序），例 `"D\n答案"` → `["D","答案"]`；③ `无` / `NULL` **仍是唯一特判** → `null` + `[]`；④ **两个出口一起改**（[3.5.1](#351-post-cscarecordsrecordidsubmit) 第 5 条）；⑤ [4.2](#42-答案归一化cscaanswernormalizer) 明确**归一化只服务判分**（含 `standard_answer_snapshot`），答案出口一律不用。<br>🔴 **代码待同步**：`CscaQuestionQueryServiceImpl#solution` 去掉 `normalize(...)`、改直传 + `splitRaw(...)`；`CscaAnswerService` 的 `immediate=true` 分支同改；`CscaAnswerNormalizer` 拆出 `splitRaw`（或让 `normalize` 只被判分链路调用） |
| **22** | **「无/空标准答案」与 `unGradedCount` 定为「防御性兜底」**（2026-10-13 用户口径：「现在没有标准答案为 无 或空的情况了」→ 经确认**保留为防御性兜底**，不删规则、不删字段） | 题库侧已把 CSCA 答案全部修干净，原「`无` → 未评分」规则与 3 个接口的 `unGradedCount` 成了**永不触发的死代码**；但直接删掉有风险 —— 脏值一旦回潮会被判成「错」，等于把题库问题转嫁成用户扣分 | **已改文档（保留 + 加注，未删任何规则）**：① [4.2](#42-答案归一化cscaanswernormalizer) 判分表下方新增实测注记；② [3.4.1](#341-get-cscarecordsrecordid) 第 3 条 / [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 4 条 / [3.3.3](#333-get-cscaquestionsquestionidsolution) 第 4 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 注记各加「当前已无此值、纯兜底」。<br>**实测（2026-10-13 复核）：TEST + PROD 两库 CSCA 各 1904 题，`answer` 全部匹配 `^[A-F](,[A-F])*$`，NULL / 空串 / `无` = 0 行**（曾有的 4 行脏值 —— 2 行 `无`、1 行 `D\n答案`、1 行 `D.` —— **两库均已修正且一致**）。<br>⚠️ **不产生新的代码待同步项**：兜底与字段本就要实现，只是平时恒不触发 |
| **23** | **裁撤 `GET /csca/progress`（与目录接口功能重复）**（2026-10-13 用户口径：「GET /csca/progress 和 GET /csca/catalog 功能重复了，不要」） | 原设计：`GET /csca/progress` 给「科目进度明细」（已练 / 对错 / 正确率 / 末次时间 / `draftRecordId`），与 [3.1.1 `GET /csca/catalog`](#311-get-cscacatalog) 的 `subjects[]`（已练 / 答对 / 正确率 / 末次时间）**大面积重复**，同一套口径要维护两处 | **已裁撤（只改文档，代码待同步）**：① 删除原 §3.3.6 `GET /csca/progress` 整节，原 §3.3.7 `POST /csca/progress/report` 顺延为 **§3.3.6**（**路径不变**）；② progress 独有的 `wrongCount` / `unGradedCount` / `draftRecordId` **直接删掉、不并入 catalog**（科目卡原型的三个数就是 总题数 / 已练习 / 正确率；错题数看 [3.4.2](#342-get-cscarecordsrecordidanswer-card)，草稿改由 [3.2.1](#321-post-cscarecords) `restart=false` **幂等取回**，见其业务逻辑第 2 条）；③ **端点总数 14 → 13**（[2.1](#21-端点清单) / [1.2](#12-场景--接口对照表) 已同步重编号）；④ §3.3 层名 `作答与进度层` → `作答层（含离线补传）`；⑤ 全文档指向 `#336-get-cscaprogress` 的 20 处引用改指 [3.1.1](#311-get-cscacatalog)。<br>**代码待同步**：`CscaProgressController` / `CscaProgressService#progress` **从未实现**（`csca` 包现有仅 catalog + questions 两个接口）→ **本项无代码删除量**；既有 `dto/CscaProgressRow.java` 仍被 catalog 的进度聚合复用，**保留** |
| **24** | **批量补传改路径：`POST /csca/progress/report` → `POST /csca/records/{recordId}/answers/batch`**（2026-10-13 用户口径：「修改一下路径吧，放在 `PUT /csca/records/{recordId}/answers/{questionId}` 差不多的路径下吧，都是提交作答」） | 原路径把「批量作答」挂在 `/csca/progress*` 下（历史遗留自被裁撤的「进度层」），与「提交作答」的资源语义不符 —— 同一件事（写 `practice_answer`）被拆在两个不同前缀下 | **已改（只改文档，代码待同步）**：① 路径改 `POST /csca/records/{recordId}/answers/batch`，**`recordId` 从 Body 提到 Path**（Body 只剩 `items[]`）；② 方法仍为 `POST`（路径自带 `batch` 后缀，不占用单题的 `PUT /answers/{questionId}`）；③ Controller `CscaProgressController` → **并入 `CscaRecordController`**（`/csca/records*` 本就归它），DTO 更名 `CscaProgressReportRequest` / `Response` → `CscaBatchAnswerRequest` / `Response`；④ §0.2 鉴权表删掉 `/csca/progress*` 前缀（已被 `/csca/records/**` 覆盖）、§2.2 端点归属表删掉 `/csca/progress/report` 行；⑤ 端点总数仍 **13**（只改路径、不增删端点）。<br>**代码待同步**：该端点**从未实现** → 直接按新路径新建即可、**无删除量**；若已建 `CscaProgressController` 骨架，把方法并入 `CscaRecordController` |
| **25** | **题面冻结策略：由「不冻结」改为「冻结题面」**（2026-10-13 用户口径：「① 多写 5 个字段」；涉及 [3](#3-接口详细设计) 开头「冻结策略选择」段 + 落库策略表 + [3.2.2](#322-get-cscaquestions) 业务逻辑） | 原口径：CSCA 走「听力式」**不冻结题面**、**不写** `practice_answer` 的 `question_snapshot` / `group_snapshot` / `option_snapshot`（只写 `standard_answer_snapshot` 用于判分），理由是无法让题库勘误即时生效 | **已按新口径改文档**：① 作答（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) / [3.3.2](#332-post-cscarecordsrecordidanswersbatch)）**写齐 5 个快照列**（`question_snapshot` / `group_snapshot` / `option_snapshot` / `standard_answer_snapshot` / `analysis_snapshot`），与 HSK 听力 / 阅读一致；② **读时「已答过的题一律回快照」**（[3.2.2](#322-get-cscaquestions) 业务逻辑第 5 条，传 `recordId` 时每页 1 次 `practice_answer` 查询）；③ **未作答的题仍实时读** `question`；④ [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 2 条**判分基准改用 `standard_answer_snapshot`**（题库改答案不追溯已答过题的判分）；⑤ [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 5 条 `immediate=true` 的答案 / 解析**改取快照**；⑥ 例外：`/csca/questions/{id}/solution` **不读快照**（无 `recordId` 上下文）。<br>⚠️ **不改表**：5 列早已存在、HSK 在用（TEST 库 `practice_answer` 已有 4528 行非空快照）。<br>✅ **取题读侧代码已同步（2026-10-13）**：`CscaQuestionQueryServiceImpl` 在传了 `recordId` 时每页 1 次查 `practice_answer`（`PracticeAnswerMapper#selectByRecordId`）并对「本轮已答（`answered=1`）」的题**回快照**；新增 `csca/support/CscaSnapshotSupport`（**读取侧契约**：`question_snapshot` 的 `typeId`(原名)/`layout`/`passage`/`content`、`option_snapshot` 的 `scope=QUESTION` 项按 `sortOrder` 保序、`group_snapshot` 的 `startNumber`/`endNumber`/`passage`；键缺失一律回落 `null`/空集合）。<br>🔴 **作答写侧仍待编码**：`CscaAnswerService#save` / `#batchReport` 补写 5 个快照列（参考 `reading/service/internal/ReadingSnapshotSupport`，**须按上面的契约键名写**）；`CscaSubmissionService` 判分基准改 `standard_answer_snapshot`；`CscaGradingService` 入参由 `question.answer` 改为"传入的标准答案字符串" |
| **26** | **题集落库：新增列 `practice_record.question_ids`**（2026-10-13 用户口径：「② 加一列」；涉及 [3.2.1](#321-post-cscarecords) 第 4 条 / [3.2.2](#322-get-cscaquestions) 第 5 条 / [3](#3-接口详细设计) 落库策略表） | 原口径：「**题序不落库，靠规则重算**」—— `practice_record` 没有题集列，`record` 只记"科目 + 语言 + 数量"，题集与题序每次取题时重算 → `questionCount` 只是**软上限**，且**保证不了"两次打开是同一批题"** | **已按新口径改文档**：① 新增列 `practice_record.question_ids`（**自然序** `question.id` 数组，JSON）；② **建轮时一次算定**（`restart=true` → 科目**全量**；首次建轮 → **剩余未练**；再按 `questionCount` 截断）并写入；③ [3.2.2](#322-get-cscaquestions) 取题**三态**：传 `recordId` → `question_ids` 固定题集；不传 → 按科目实时算（`NOT EXISTS` 去重）；`includeAnswered=true` → 忽略题集取全量；④ `availableCount` / `totalQuestions` 在传 `recordId` 时 = 题集大小；⑤ **`restart=true` 不再撞 `404`**（题集取全量，「全部练完」的出口更顺）。<br>⚠️ **本模块唯一一次「改表」**（**加列、非新表**）：DDL = `ALTER TABLE practice_record ADD COLUMN question_ids JSON NULL COMMENT '本次练习题集（自然序 question.id 数组；仅 CSCA 使用，HSK 为 NULL）' AFTER total_questions;` —— **可空**，HSK 全部既有行保持 `NULL`、既有链路零影响。改库走五闸门，见文末「附 4」。<br>✅ **取题读侧代码已同步（2026-10-13）**：`CscaQuestionMapper#selectByQuestionIds`（`q.id IN (题集)` 分页，**不追加排除已答**）+ 新增 `csca/mapper/CscaRecordMapper#selectRecord` 读 `question_ids`；`availableCount` 传 `recordId` 时 = 题集大小（Java 侧读列表长度）。<br>⚠️ **实现取舍**：**未改动共享实体 `PracticeRecord`**（`question_ids` 列 **TEST 已建（2026-10-13 16:10）、PROD 未建**，加进共享实体会让 HSK 四条链路的 `selectById` 一起报 `Unknown column`）；题集读取走 csca 包内独立 SQL，`question_ids` 以 JSON 原文取出、由 Service 显式解析为 `List<Long>`（避免 `JacksonTypeHandler` 按原始 `List` 类型把雪花 id 反序列化成 `Integer`）。<br>🔴 **records 写侧待编码**：`CscaRecordService#start` 算题集并写 `question_ids`；`CscaRecordStartRequest` 的 `restart` 分支题集取全量；建列脚本见文末「附 4」（✅ **TEST 已执行 2026-10-13 16:10**、⚠️ **PROD 未执行**） |
| **27** | **科目不合并：「中文」别名删除**（2026-10-13 用户口径：「这个不合并，就给五个科目」；涉及 [4.1](#41-枚举速查) 科目枚举表 + [3.1.1](#311-get-cscacatalog) / [3.2.2](#322-get-cscaquestions) / [3.2.1](#321-post-cscarecords) 的入参口径） | 原口径：`CscaSubjects` 有别名 `chinese`（展开为 `arts_chinese` + `science_chinese`），[4.1](#41-枚举速查) 表首行是 4 科目合并卡「中文 1040」 | **已改文档**：科目**恒为 5 条**（[4.1](#41-枚举速查) 表由 4 行改 5 行）、删除全部「别名 `chinese`」表述（[0.8](#08-与互动原型的对齐v13) / [1.1](#11-页面流转) / [3.2.2](#322-get-cscaquestions) 入参 + 校验 + 筛选 + SQL / [3.2.1](#321-post-cscarecords) 入参 / [4.3](#43-待确认事项) 第 11 条 / [4.5](#45-原型-v13-对照表)）。<br>✅ **代码已同步（2026-10-13）**：`csca/support/CscaSubjects` **删 `RESOLUTION` 表与 `ALIAS_NAMES` 常量**，`resolveMappings(String)` 收窄为 **`resolveMapping(String)` 单值**（只认 5 个原始码，传 `chinese` → `null` → 调用方回 `CSCA_SUBJECT_INVALID`）；`nameOf` 去掉别名兜底分支。 |
| **28** | **跨语言同题不去重（分开记）**（2026-10-13 用户口径：「这个就是要分开记的不能去重，中文和英语是两套不同卷子」） | 原口径：列为待确认（中 / 英是不同 `question.id`，`COUNT(DISTINCT question_id)` 会让同一考点中 / 英各计一次，被当成"问题"） | **口径确认、零代码**：去重键**恒为 `question.id`**（[3.1.1](#311-get-cscacatalog) 业务逻辑第 3 条 / [3.2.2](#322-get-cscaquestions) 第 5 条 / [4.3](#43-待确认事项) 第 12 条）；**不做**跨语言合并、**不需要**"题目组"标识。 |
| **29** | **多选无部分给分（全对才算对）**（2026-10-13 用户口径：「多选无部分给分，这个要全对才算对」） | 原口径：列为待确认（[4.3](#43-待确认事项) 第 4 条） | **口径确认、零代码**：判分只有「集合相等 / 不等」两态（[4.2](#42-答案归一化cscaanswernormalizer)），**无按比例给分**；与既有 `CscaGradingService` 实现一致。 |
| **30** | **补 `CSCA_*` 业务码（8001–8099）**（2026-10-13 用户口径：「这个可以补上」） | 原口径：`400` / `404` 直接写字面量；`ErrorCode` 无 404 项 | **已改文档**：[0.5](#05-错误码) 给出 8 个 `CSCA_*` 码（8001–8008）+ 号段划分（`COURSE_*` 占 7001–7099）。<br>✅ **代码已同步（2026-10-13）**：8 个枚举（8001–8008）**落在 `practice-service` 的 `com.hsktreasure.practice.csca.support.CscaErrorCode`**（⚠️ **不放进 common 的 `ErrorCode`** —— 用户口径「写在 practice-service 下」，模块自有码表不污染全站共用码；`ErrorCode` 内留一行指路注释、**不重复定义**），并带 `toException()` / `toException(String detail)` 便捷方法；`csca` 取题链路的 `BusinessException` **已由字面量改抛新码**（场景 → 码的对照见 [0.5](#05-错误码) 表：科目 `8001` / 语言 `8002` / 题型 `8003` / 乱序缺种子 `8004` / 参数越界 `8005` / 记录不存在 `8007`）。🔴 其余端点（solution / favorites / records / wrong-book）尚未编码，编码时同样按 [0.5](#05-错误码) 表取码。 |
| **31** | **收藏落库 + 新表 `question_favorite`**（2026-10-13 用户口径：「收藏要落库，把 question_favorite 设计一下」；涉及 [3.6.1](#361-收藏favorite) / [2.1](#21-端点清单) 第 11–13 号） | 原口径：收藏**只存本地**、表不存在（[4.3](#43-待确认事项) 第 10 条） | **已设计 DDL**（[3.6.1](#361-收藏favorite) 业务逻辑第 5 条）：雪花主键 / `uk_user_question(user_id, question_id)` + **软删复活** / **不存语言列**（靠 `question_id` 天然分中英）/ 两个二级索引 / **`source` 来源快照列**（2026-10-14 补加，与错题本对称，见第 48 条）/ **审计列 `created_by` / `update_by`**（10-14 补，末 5 列与 `practice_answer` 同序，见第 49 条）/ **「来源轮次」两列 `practice_record_id` / `exam_record_id`**（10-14 补，见第 50 条，共 13 列）。<br>🔴 **待办**：① **建表**（TEST → PROD，见文末「附 5」）；② `CscaFavoriteController` / `CscaFavoriteService` / `CscaFavoriteMapper`(+`.xml`) 编码；③ [3.4.2](#342-get-cscarecordsrecordidanswer-card) 答题卡的 `favorite` 段改查该表。 |
| **32** | **错题本落库 + 新表 `question_wrong` + 3 个接口**（2026-10-13 用户口径：「现在原型新增了错题本，你设计错题本的接口」；涉及 [3.6.2](#362-错题本wrong-book) / [2.1](#21-端点清单) 第 14–16 号） | 原口径：**无错题本**（原型把错题存 `localStorage` 的 `WRONG_BOOK`） | **已设计 DDL + 3 个接口**（[3.6.2](#362-错题本wrong-book)）：与 `question_favorite` **互为镜像**（**列定义与索引集合完全一致、13 列** —— 2026-10-14 收藏表补加 `source`（第 48 条）、两表同批补审计列（第 49 条）后再次对齐；索引同经精简、不建 `idx_user_source`，见第 47 条）；**答错收录 / 答对自动移出 / 手动移出软删复活**（🔴 2026-10-19 「答对自动移出」已取消，见第 62 条）。<br>⚠️ **与原型的两条差异**：① ~~原型「答对不自动移除」→ **改为答对自动移出**（用户口径）~~ 🔴 **2026-10-19 已回退（即与原型一致）**，见第 62 条；② 原型有「全部来源 / 练习 / 考试」筛选 → 本模块**保留 `source` 列与筛选**，但**只写 `prac`**、`exam` 待考试侧接入（第 33 条）。<br>🔴 **待办**：① 建表（见文末「附 6」）；② `CscaWrongBookController` / `Service` / `Mapper` 编码；③ 作答链路同步（第 33 条）。 |
| **33** | **作答链路同步错题本**（2026-10-13 定） | 原口径：无。新增要求：**判分结果驱动错题本状态** | **已改文档**（[3.6.2](#362-错题本wrong-book) 第 1 条 / [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条 / [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 第 6 条）：写入 `practice_answer.is_correct` 的每一处**附随**更新 `question_wrong`（判错收录 / 判对移出 / 未评分不动；🔴 其中「判对移出」已于 2026-10-19 取消，见第 62 条）。<br>🔴 **代码待同步**：`CscaAnswerService#save` / `#batchReport` / `CscaSubmissionService#submit` 判分后调用 `CscaWrongBookService#syncAfterGrade(userId, questionId, isCorrect, source)`。 |

| **34** | **`GET /csca/questions` 代码同步（本轮，2026-10-13）** | 文档在 2026-10-13 已把取题口径改到位（第 17 / 20 / 25 / 26 / 27 / 30 条），但**代码整体滞后**：仍按卷（`paperId`）取题、免登录、无去重、无固定题集、无快照回放、顶层仍叫 `total`、`CSCA_*` 未落、科目仍有 `chinese` 别名 | ✅ **本轮已把 `GET /csca/questions` 全量对齐**：① `CscaQuestionQuery` 删 `paperId`、加 `recordId` / `includeAnswered`；② **强鉴权**（`requireAuthenticatedAppUserId`，未登录 `401`）+ 网关白名单**移除** `/api/practice/csca/questions*`；③ **题集三态**（`recordId` → `CscaQuestionMapper#selectByQuestionIds`；不传 → `selectBySubject`/`countBySubject` + `NOT EXISTS` 排除已答；`includeAnswered=true` → 科目全量）；④ 顶层 `total` → **`availableCount`**；⑤ 已答之题**回快照**（`csca/support/CscaSnapshotSupport`）；⑥ **8001–8008** 落到 `csca/support/CscaErrorCode`（模块自有码表，**非** common `ErrorCode`）并改抛；⑦ `CscaSubjects` 删 `chinese` 别名。**未动**：records / solution / favorites / wrong-book 端点（未编码）、`practice_record.question_ids` 建列脚本（附 4，✅ **TEST 已执行 2026-10-13**、⚠️ PROD 未执行——故传 `recordId` 的路径**在 TEST 已可用、PROD 待建列**） |
| **35** | **取题入参收口：`languageVersion` / `recordId` 改必填、`typeId` 取消入参**（2026-10-13 用户口径：「languageVersion 和 recordId 必填，typeId 不做入参」） | 上一版：`languageVersion` **可选**（缺省 `chinese`）、`recordId` **可选**（不传就「按科目实时取 + `NOT EXISTS` 排除已答」，边答边翻页会漂移）、`typeId` **可选**（`SINGLE` / `MULTI` 筛选） | **已按新口径改文档 + 同步代码**：<br>① **`languageVersion` 必填、无缺省**（未传 / 非法 → `400` / `CSCA_LANGUAGE_INVALID`）—— 取题必须明确指定用哪一批卷，不猜缺省（[0.3](#03-语言版本languageversion-与界面文案是两件事)）；<br>② **`recordId` 必填**（未传 / 查不到 / 非本人 / 非 CSCA → `404` / `CSCA_RECORD_NOT_FOUND`）—— 题集必须有落点，前端遇 `8007` 统一走「重新建轮」；**题集三态收窄为两态**（`includeAnswered=false` → 固定题集；`=true` → 科目全量）；<br>③ **原第三条路「不传 `recordId` → 按科目实时取 + `NOT EXISTS` 排除已答」整条删除** —— 「只回没做过的题」**唯一落点前移到建轮**（[3.2.1](#321-post-cscarecords) 第 3 条），取题侧**不再做任何去重**；连带好处：原「边答边翻页会漂移、只适合一次性拉完」的坑消失（题集是死的）；<br>④ **`typeId` 取消入参**（传了**忽略**、不校验）—— 本接口**不做按题型筛选**，`typeId` 仅作**出参**（`SINGLE` / `MULTI`）；`CSCA_TYPE_ID_INVALID(8003)` 转为**保留码**、**当前无触发点**；原「筛选与显示严格同源」的说法作废；<br>⑤ `availableCount` 语义随之简化：`includeAnswered=false` = **题集大小**（固定），`=true` = **科目总量**（不再有「去重后剩余题数」这一中间态）；<br>⑥ **范围仅限 `/csca/questions`**：`/csca/favorites`（`languageVersion` 缺省 `chinese`）与 `POST /csca/records` Body（`languageVersion` 缺省 `chinese`）**本次不动**（两者均未编码，如要一并改必填请另行确认）。<br>✅ **代码已同步（2026-10-13）**：`CscaQuestionQuery` **删 `typeId` 字段**、`languageVersion` / `recordId` javadoc 标必填；`CscaQuestionQueryServiceImpl` **删 `resolveTypeId` 与 `DEFAULT_LANGUAGE`**、`resolveLanguage` 改必填、`recordId` 加未传校验、题集判定改 `useQuestionSet = !includeAnswered`；`CscaQuestionMapper`(+`.xml`) **删 `typeId` 参数与 `<sql id="cscaTypeFilter">`**、**删 `excludeAnsweredUserId` 与 `NOT EXISTS` 段**（`selectBySubject` / `countBySubject` 只剩科目单值 + 例题排除）；`CscaCatalogController#questions` 日志去 `typeId`；`CscaErrorCode` 的 `8003` / `8007` 注释同步。编译通过（`mvn -pl practice-service -am compile`）。<br>⚠️ **连带影响（已在文档注明）**：[3.3.3 `solution`](#333-get-cscaquestionsquestionidsolution) 不受影响（无 `recordId` 上下文）；「只复习、不清进度」现在也**必须有 `recordId`**（[3.2.1](#321-post-cscarecords) 第 3 条注记）；[3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card) 的数据流向已改写为「读 `question_ids` + join 答案」（`practice_answer` **不再参与去重**） |

| **36** | **删除 `includeAnswered` 入参：题集改为「唯一来源」**（2026-10-13 用户口径：「这样不会导致我在答题的时候切换背题模式造成题目不一样吗？」） | 上一版（第 34 / 35 条）：题集**两态** —— `includeAnswered=false`（缺省）→ 该 `recordId` 的固定题集；`=true` → **忽略题集**、按**科目全量**实时取（复习模式） | **已按新口径改文档 + 同步代码**：<br>① 🔴 **根因**：`includeAnswered` 换的是**结果集**而不是**显示** —— 切过去之后 **同一 `page` 取到另一批题**（分页坐标由"题集内 offset"变成"科目内 offset"）、**`availableCount` 从题集大小跳到科目总量**（进度条跳变）、**同一 `seed` 的乱序结果整体重算**、**本轮已答题的题面从"快照"退回"实时"** → 用户在答题过程中切一次「背题模式」，**题目 / 题序 / 进度 / 题面四处全变**，属设计冲突；<br>② **题集唯一来源** = `practice_record.question_ids`（[3.2.2](#322-get-cscaquestions) 第 5 条的「两态表」→ **单行表**；入口描述 / 入参表 / 业务逻辑 / 三层逻辑表 / 涉及表 / 数据流向 / 映射对照 / **关键 SQL** 全同步）；<br>③ **背题模式与本接口解耦**：它只是答题页顶栏的一个开关，对**当前题**调 [`GET /csca/questions/{id}/solution`](#333-get-cscaquestionsquestionidsolution) 把答案亮出来，**切模式不重拉列表、不换题集、不换 `seed`**；<br>④ **「想整科全量」唯一出口 = `POST /csca/records {restart:true}`**（新轮题集即全量）—— [4.3](#43-待确认事项) 第 14 条的**「出口 ② 只复习、不清进度」作废**，[3.2.1](#321-post-cscarecords) 对应注记同改；<br>⑤ `availableCount` **回归单值**（恒 = 题集大小 `JSON_LENGTH(question_ids)`，**不发 COUNT SQL**）；「不传 recordId 的去重剩余题数」与「includeAnswered=true 的科目总量」两个中间语义**均已取消**；<br>⑥ **代码同步**：`dto/CscaQuestionQuery` **删 `includeAnswered` 字段**；`CscaQuestionQueryServiceImpl` **删两态分支**（题集路径恒定、快照回放**恒执行**、删 `useQuestionSet` / `includeAnswered` 变量）；`mapper/CscaQuestionMapper` **删 `selectBySubject` / `countBySubject`**、`CscaQuestionMapper.xml` **删 `<sql id="cscaSubjectScope">` 与两条 SQL**；`CscaCatalogController#questions` 日志与 javadoc 同步；`dto/CscaQuestionsResponse#availableCount` 与 `dto/CscaQuestionRow` 注释同步。⚠️ **`subjectTypeMapping` 保留必填**（现仅用于**校验与 `subjectCode` 回显** —— 取题范围由题集决定）。<br>⚠️ **本条取代**第 17 / 20 / 26 / 34 / 35 条中所有 `includeAnswered` 相关口径（旧条目按历史记录保留，**不回改**）。<br>✅ **编译通过**：`mvn -pl practice-service -am compile -DskipTests` → **BUILD SUCCESS**（58.4s，JDK17）。 |

| **37** | **§3 接口排序改「按用户流程」+ 分组改名**（2026-10-13 用户口径：「文档的接口设计部分按照流程来排序接口」） | 原结构按「层」分：`3.1 入口层` / `3.2 内容层（单题 / 答案 / 收藏）` / `3.3 作答层（含离线补传）`，顺序与 [1.1](#11-页面流转) / [1.3](#13-一次完整会话的调用时序) 定义的流程**不一致** —— 最明显是 `POST /csca/records`（建轮）排在取题 `GET /csca/questions` **之后**，而流程上**必须先建轮拿到 `recordId` 才能取题**（题集由 `recordId` 定） | **已按流程重排（只改文档、代码零影响、端点仍 13 个）**：<br>① **新分组** = **3.1 进入与目录** / **3.2 开始练习** / **3.3 逐题作答** / **3.4 练习态与答题卡** / **3.5 交卷** / **3.6 收藏与错题本**；<br>② 段内顺序：3.2 = `POST records` → `GET questions` → `GET questions/{id}`；3.3 = `PUT answers/{id}` → `POST answers/batch` → `GET solution`；3.4 = `GET records/{id}` → `GET answer-card`；3.6 = 收藏 → 错题本；<br>③ **章节编号全变** `3.2.x` / `3.3.x` → 新号，文档内 **242 处锚点引用按映射整体改写**（含 `[3.x.y]` 半引用、`](#anchor)` 完整锚点、`#### 3.x.y` 标题）；<br>④ 原 `3.3` 层引言的两块 📌 **上提**：「落库策略 / 冻结策略 / 表映射」→ §3 章节开头（全模块级说明）；「科目进度已并入 catalog」→ [3.1](#31-进入与目录) 节前；<br>⑤ **§2.2 归属表「说明」列**层名同步为流程阶段名；<br>⑥ **§2.1 端点清单顺序不动**（用户口径：只重排 §3）；[1.2](#12-场景--接口对照表) 亦不动；<br>⑦ **顺带修正一处口径矛盾**：§3 开头的「不新增业务表」改为「**作答链路**不新增业务表」＋注明另有两张姊妹新表（收藏 / 错题本）—— 原措辞与 [4.4](#44-文档与实现的差异) 第 31 / 32 条已矛盾。 |

| **38** | **新建 `POST /csca/records` 建轮接口**（2026-10-13 用户口径：「根据文档写 POST /csca/records 接口」） | 该端点此前**未编码**（[3.2.1](#321-post-cscarecords) 只有设计）；第 17 / 35 条已把 records 侧口径改到位（删 `paperId`、题量按剩余算、剩余 0 → `8008`），但**无实现** | ✅ **已按 [3.2.1](#321-post-cscarecords) 实现**：<br>① **新增** `csca/controller/CscaRecordController`（`POST /records`，**强鉴权**）、`csca/service/CscaRecordService`(+`impl`)、`dto/CscaRecordStartRequest` / `CscaRecordStartResponse` / `CscaRecordInsertRow`、`csca/support/CscaStructureIds`（`6e18` 稳定 ID）、`csca/support/CscaQuestionIds`（题集 JSON 编解码，**与取题侧共用**）；<br>② **流程**：参数校验 → **幂等命中**（`user_id + idempotency_key`，优先级最高）→ **查进行中记录**（`status IN (0,1)`，`FOR UPDATE` **行锁**；`restart=false` 则复用）→ **算题集**（`restart=true` → `selectAllQuestionIds` 全量；否则 `selectUnansweredQuestionIds` 剩余未练）→ `questionCount` 自然序截断 → **弃旧轮**（只改 `status=2`、作答**一行不删**）→ **建记录**（独立 INSERT，含 `question_ids`）；<br>③ **不碰共享实体 `PracticeRecord`**：`question_ids` 是本模块新增列，建轮走 `CscaRecordInsertRow` 的**独立 INSERT**（否则 HSK 四条链路 `selectById` 会一起报 `Unknown column`）；<br>④ **Mapper 新增**：`CscaRecordMapper#selectRecordDetail` / `#selectIdByIdempotencyKey` / `#selectInProgressIdForUpdate` / `#insertRecord` / `#abandonRecord`，`CscaQuestionMapper#selectAllQuestionIds` / `#selectUnansweredQuestionIds` —— 全部**显式带 `section_mapping='SEC_CSCA'`**（CSCA 记录 `paper_id=0` 是哨兵、`structure_id` 无对应结构行，只按 `user_id` 查会串到 HSK），排除已答用 `NOT EXISTS` 且只认 CSCA 作答；<br>⑤ **`CscaStructureIds#of` 严格按 §4.1 公式**（`6e18 + int(sha256('csca\|&lt;科目&gt;\|&lt;语言&gt;')[:12],16) % 1e18`），单测钉死值：理科中文 `6000086914499189309` / 文科中文 `6000222343388004333`；<br>⑥ **单测**：`CscaStructureIdsTest`（公式 / `6e18` 号段 / 不撞车）+ `CscaRecordMapperXmlContractTest`（SQL 契约：CSCA 范围、`FOR UPDATE`、`question_ids` 写入、弃旧只改状态、`NOT EXISTS` 只认 CSCA）→ `Tests run: 10, Failures: 0`；`mvn -pl practice-service -am compile` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **两处实现细化（文档未明写，按"更合理"落地，如需回改请说）**：<br>　**a. `restart=true` 但该科目<b>题库为空</b>**（不是"已练完"）→ **仍回 `8008`**（文案区分：「该科目题库为空，暂无可练题目」）。文档只写了「剩余为 0 且 `restart=false` → `404`」；建一条空轮无意义，故把「科目本身无题」一并归到 `8008`。<br>　**b. 记录表没有语言列** → 复用路径（幂等命中 / 命中进行中）的 `languageVersion` **回显本次请求值**，且进行中查询**不带语言维度** ⇒ **同一科目下的中 / 英不分别建轮**（先开中文轮、再请求英文会复用中文那轮）。若要「分语言建轮」，需给 `practice_record` 再加一列（`question_ids` 之外的第二处改表）—— 当前按文档「只用 `section_mapping + section` 定位记录」实现。<br>⚠️ **未动**：`records/{recordId}` 详情、`answer-card`、`submit`、`answers*` 补传（均未编码）。<br>⚠️ **网关**：`/api/practice/csca/records*` **不在白名单**（gateway 配置已有注释「作答类，必须登录」），无需改动。 |

| **39** | **建轮入参收口：删 `questionCount`、`languageVersion` 改必填**（2026-10-13 用户口径：「questionCount 传参不要、languageVersion 必传」） | 上一版：`POST /csca/records` 有 `questionCount`（`0` 缺省 = 全部；`1–200` = 按自然序取前 N 题，**建轮时就截断题集**）、`languageVersion` **可选**（缺省 `chinese`，与 `/csca/questions` 的必填口径**不一致**） | **已按新口径改文档 + 同步代码**：<br>① **删入参 `questionCount`** —— 建轮**不接收题量**，题集恒为「该科目**剩余未练**（`restart=true` 时**全量**）」的**全部**、**不截断**（原「只练前 N 题」的口子一并取消，避免"建出的题集"与"客户端以为的题量"两处口径）；<br>② **`languageVersion` 必填、无缺省**（未传 / 非法 → `400` / `CSCA_LANGUAGE_INVALID`）—— 与 [3.2.2 `/csca/questions`](#322-get-cscaquestions) **同口径**（原「建轮默认中文」缺省删除）；<br>③ `totalQuestions`（响应）语义随之简化 = **题集大小**（= 剩余未练 / 全量，不再有"已按 `questionCount` 截断"的中间态）；<br>④ `8005` 在建轮侧只剩 `idempotencyKey` 超长（原 `questionCount` 越界校验删除）。<br>✅ **代码已同步（2026-10-13）**：`CscaRecordStartRequest` **删 `questionCount` 字段**、`languageVersion` javadoc 改必填；`CscaRecordServiceImpl` **删 `MAX_QUESTION_COUNT` 常量 / 题量校验 / 截断段**（连带删 `ArrayList` import）、`resolveLanguage` 改**必填**（未传 → `8002`）；`CscaRecordController` 日志去 `questionCount`；`CscaRecordStartResponse#totalQuestions` 注释同步；`CscaErrorCode` 的 `8002` / `8005` 注释同步。编译：`mvn -pl practice-service -am compile` → **BUILD SUCCESS**（JDK17）；单测 `CscaStructureIdsTest` + `CscaRecordMapperXmlContractTest` → **Tests run: 10, Failures: 0**（入参改动不影响这两组契约测试）。<br>⚠️ **取代关系**：第 38 条②中「`questionCount` 自然序截断」一句**已失效**；第 19 条②「`questionCount:N` 只练前 N 题 → 进度条只到 `N/科目总量`」与第 26 条②「再按 `questionCount` 截断」所述的**已知后果随之消失**（旧条目按历史保留、不回改）。<br>⚠️ **未动**：`/csca/favorites` 的 `languageVersion`（仍缺省 `chinese`，该端点**未编码**）—— 如需一并改必填请另行确认。 |

| **40** | **新建 `GET /csca/questions/{questionId}` 单题详情**（2026-10-13 用户口径：「根据文档写 GET /csca/questions/{questionId}」） | 该端点此前**未编码**（[3.2.3](#323-get-cscaquestionsquestionid) 只有设计）；[0.2](#02-鉴权与客户端类型) / [1.2](#12-场景--接口对照表) 第 3 条 / [2.1](#21-端点清单) 第 3 号早已把它定为「**强鉴权** + 内容本身**可缓存**」 | ✅ **已按 [3.2.3](#323-get-cscaquestionsquestionid) 实现**：<br>① **新增** `dto/CscaQuestionDetailResponse` —— 题目对象与列表元素（`CscaQuestionResponse`）**同构**（`… typeId / layout / passage / content / options / score / group` 恒出现）**只多两个回读标识** `subjectCode`（题级 `question.subject_type_mapping`）/ `languageVersion`（卷级 `exam_paper.language_version`）+ 静态工厂 `of(question, subjectCode, languageVersion)`。⚠️ **没有**直接给 `CscaQuestionResponse` 加这两个字段 —— 列表接口的科目 / 语言在**响应顶层**（`CscaQuestionsResponse`），塞进元素里会让列表每道题多出两个恒 `null` 的键（§4.4 第 16 条「顶层回显、元素里不放」的同一思路）；<br>② **Mapper** `CscaQuestionMapper#selectDetail`(+`.xml`)：`q.id = #{questionId}` **主键直取 1 行**，卷侧只 include 新拆出的 `<sql id="cscaPaperBase">`（`p.deleted=0 AND p.exam_type=2 AND p.version='CSCA'`，**不含语言**）→ **HSK 的题查不到**（回 `8006`）；原 `<sql id="cscaPaperScope">` 改为 `cscaPaperBase` + `p.language_version = ?`（**列表 SQL 行为一字不变**，只是把「范围」与「语言」两层拆开复用）；额外取回 `q.subject_type_mapping` / `p.language_version` 供回显；<br>③ **不取 `q.answer`**：「答案不进内容接口」硬约束（答案出口只有 [`/questions/{id}/solution`](#333-get-cscaquestionsquestionidsolution)），已由单测钉死；<br>④ **Service** `CscaQuestionQueryService#detail(Long)`：把列表装配循环体抽成私有 `toResponse(row, answered, groups)`，**列表与详情共用同一份装配**（选项保序 / `group` 区间命中 / `layout` 原样透传 / `typeId` 映射只有一处）；详情 = `toResponse(row, null, loadGroups(List.of(row)))` —— **无 `recordId` → 不读题面快照**（本接口是"看题目本身"，没有"作答当时"这回事）；查不到 / 非 CSCA → `CSCA_QUESTION_NOT_FOUND(8006)`；<br>⑤ **Controller** `CscaCatalogController#question`：强鉴权（`requireAuthenticatedAppUserId`，未登录 / 非 APP → `401`）；**无语言入参**，语言与科目码由卷 / 题回读；<br>⑥ **实现细化（文档未明写，如需回改请说）**：非数字 `questionId` 走**手工解析**（路径变量声明为 `String`，解析失败 → `CSCA_PARAM_OUT_OF_RANGE(8005)`）。⚠️ 文档 3.2.3 第 1 条原写「框架 `MethodArgumentTypeMismatchException`，由 `GlobalExceptionHandler` 兜住」，但 **common 的 `GlobalExceptionHandler` 并没有这个处理器** → 声明成 `@PathVariable Long` 时非数字会落到兜底分支回 `SYSTEM_ERROR(500)`，与 [0.5](#05-错误码) 的「路径变量不是数字 = `8005`」冲突；手工解析可在**不动 common** 的前提下满足文档（[3.2.3](#323-get-cscaquestionsquestionid) 第 1 条已按实现改写）；<br>⑦ **单测**：`CscaQuestionDetailMapperXmlContractTest`（4 例：主键绑定 / CSCA 范围 / **不按语言筛**（详情无语言入参，改成按语言筛即绑不上值）/ **不取 `q.answer`**）→ **Tests run: 4, Failures: 0**；`mvn -pl practice-service -am compile` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **未做**：DB 实跑联调（连库审批受限）；`/csca/questions/{id}/solution` 仍未编码（答案出口）。 |

| **41** | **新建 `PUT /csca/records/{recordId}/answers/{questionId}` 逐题作答**（2026-10-13 用户口径：「根据文档写 PUT /csca/records/{recordId}/answers/{questionId}」） | 该端点此前**未编码**（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 只有设计）；[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条（同步错题本）依赖第 32 条那张**尚未建表**的 `question_wrong` | ✅ **已按 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 实现**：<br>① **新增** `controller`（端点）、`service/CscaAnswerService`(+`impl`)、`service/CscaGradingService`(+`impl`)、`support/CscaAnswerNormalizer`（§4.2 七步；**判分**用 `normalize` / `labels` / `sameLabels`，**答案出口**用 `splitRaw`）、`support/CscaSnapshotWriter`（5 快照列的**写侧**，与读侧 `CscaSnapshotSupport` 键名严格配对）、`dto/CscaAnswerSaveRequest` / `CscaAnswerSaveResponse` / `CscaAnswerQuestionRow`；<br>② **流程**：`answer` 必填校验 → 记录 `selectByIdForUpdate` **行锁** + 归属 + `status IN (0,1)`（否则 `409 RECORD_NOT_IN_PROGRESS`）→ 题目归属（`selectForAnswer` 带上 `exam_type=2` + **科目一致**）→ `CscaGradingService#grade` → `upsertAnswer`（**写齐 5 个快照列**）→ `selectAnsweredCount` 重算 + `updateById`（`@Version` 乐观锁 +1，冲突 → `409 RECORD_VERSION_CONFLICT`）→ 组装；<br>③ **判分独立实现**（不复用 `exam-service` 的 `equalsIgnoreCase`）：归一化后按**标签集合**相等，多选**全对才算对**；`无` / NULL 或用户未作答 → **未评分**（`0` + `points=null`），**不判错**；<br>④ **题面冻结只写一次**：`ON DUPLICATE KEY UPDATE` 里**刻意不含** 5 个快照列（改答案不改题面），`first_answered_time` 走 `IFNULL` 保首次值 —— 两条都由 `CscaAnswerMapperXmlContractTest` 钉死；<br>⑤ **答案唯一出口**：`immediate=true` 才回 `standardAnswer` / `analysis`，且取**刚写入的快照**、**原值直传、不归一化**（`无` / NULL → 缺席）；内容查询**永不取** `q.answer`（逐条点名断言，唯一例外是 `selectForAnswer`）；<br>⑥ **单测**：`CscaAnswerNormalizerTest`(7) + `CscaGradingServiceImplTest`(7) + `CscaAnswerMapperXmlContractTest`(5)，与既有 3 组共 **33 绿**；`mvn -pl practice-service -am compile -DskipTests` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **三处实现细化 / 差异（文档未明写或落不了地，如需回改请说）**：<br>　**a. 🔴 第 7 条「同步错题本」<u>未实现</u>**：支撑表 `question_wrong` 尚未建表（[4.3](#43-待确认事项) 第 15 条），此刻写入会 SQL 报错并把整次作答连事务打回。已在 `CscaAnswerServiceImpl#save` 第 ⑦ 步留可执行落点（注释里写明要调 `CscaWrongBookService#syncAfterGrade(userId, questionId, isCorrect, "prac")`），**待建表后补调用**。<br>　**b. `option_snapshot` 键名**：文档 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 3 条写「与 HSK 同构（… 键为选项标签 `A` / `B`）」，**但读侧** `CscaSnapshotSupport` 认的键是 `{scope, optionCode, optionText, sortOrder}`（HSK 真实格式）。写侧**按读侧契约写**（否则「已答快照回放」会静默变成空选项）；文档那句的措辞待改。<br>　**c. `records` 更新走共享 `PracticeRecordMapper`**：文档三层逻辑里写的是 `CscaRecordMapper` 更新记录，实际复用共享实体 / Mapper（`selectByIdForUpdate` + `updateById`，`@Version` 自动 +1），与 HSK 听力 / 阅读同一机制 —— **不碰共享实体新增列**这条底线仍然守住（`question_ids` 仍走 `CscaRecordInsertRow` 独立 INSERT）。<br>　**附**：`;` / `；` 也作判分分隔符（§4.2 第 5 条只列 `, ， / 、 空白`，但第 2 条把它们当标点；与既有 `CscaQuestionTypes#answerLabels` 一致 —— 该 helper 已删，解析口径收口到 `CscaAnswerNormalizer`）；顺带**顺手更正**：脚本化断言「内容查询不取 `q.answer`」改为**逐条点名**（原先按整文件断言，加入作答查询后必然误报）。  <br>⚠️ **就近更新（2026-10-14）**：支撑表 **TEST 已建表**（见第 52 条）—— 本条 a 项「未接线」仍成立（表已就绪，只差代码落点）。|
| **42** | **新建 `POST /csca/records/{recordId}/answers/batch` 离线批量补传**（2026-10-13 用户口径：「POST /csca/records/{recordId}/answers/batch根据文档写这个接口」） | 该端点此前**未编码**（[3.3.2](#332-post-cscarecordsrecordidanswersbatch) 只有设计；其路径在第 24 条才从 `POST /csca/progress/report` 改过来、Controller 也从 `CscaProgressController` 并回 `CscaRecordController`）；§3.3.2 第 6 条（同步错题本）依赖第 32 条那张**尚未建表**的 `question_wrong` | ✅ **已按 [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 实现**：<br>① **新增** `dto/CscaBatchAnswerRequest`（`items[]`，嵌套 `Item{questionId,answer,clientTime}`）、`dto/CscaBatchAnswerResponse`（`{recordId, accepted, skipped, answeredCount, lastSavedTime, skippedItems[]}`）、`dto/CscaAnswerTimeRow`（冲突合并只需两列）、`support/CscaBatchSkipReason`（跳过原因枚举）、`support/CscaBatchAnswerPlanner`（**纯函数**：`MAX_ITEMS=200` / `dedupe` / `serverIsNewer`）；<br>② **流程**：条数校验（空 / 超 200 → `8005`）→ 记录 `selectByIdForUpdate` **行锁** + 归属 + `status IN (0,1)`（否则 `409 RECORD_NOT_IN_PROGRESS`）→ **批内去重**（同题保留 `clientTime` 最新）→ 逐条字段校验 → **一次 SQL** 批量取题（`selectForAnswerBatch`）+ 科目归属校验 → **冲突合并**（`selectAnswerTimes`）→ 判分 → **一条 SQL** `batchUpsertAnswers` → `answered_count` 重算 + `@Version` 乐观锁 → 组装；<br>③ **与 3.3.1 共用四段**：把 `save` 里的「记录行锁 + 归属 + 状态」「题目科目校验」「组装作答行（5 快照列）」「判分」抽成 `loadInProgressRecord` / `requireSameSubject` / `buildAnswerRow` / `CscaGradingService` —— 判分、快照、行锁、乐观锁**只有一份实现**（落实 §3.3.2 注记「不要各自实现一套判分」）；<br>④ **一条 SQL 写整批**：`<foreach>` 拼多值 `INSERT … ON DUPLICATE KEY UPDATE`（**不是**循环单条、也不是 MyBatis BATCH executor —— 避开本仓库「批量写库僵尸事务持锁 → 1205」的坑）；UPDATE 子句同样**不含** 5 个快照列、`IFNULL` 保 `first_answered_time`；批量取题与单题取题**共用 `<sql>` 片段**（`answerQuestionColumns` / `answerQuestionFromJoin` / `cscaPaperBase` / `cscaQuestionValid`），只换 `WHERE`、去掉 `LIMIT 1`（共材料的多行由 `ORDER BY q.id ASC, 精确命中优先` + Service 侧 `putIfAbsent` 取首行解决）；<br>⑤ **单测**：`CscaBatchAnswerPlannerTest`(6) + `CscaBatchAnswerMapperXmlContractTest`(5) + `CscaBatchAnswerServiceImplTest`(9，Mockito) → 与既有 6 组共 **53 绿**；`mvn -pl practice-service -am compile -DskipTests` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **四处实现细化 / 差异（文档未明写或需补齐，如需回改请说）**：<br>　**a. 跳过原因扩充为 5 类**：文档只点名 `NOT_IN_SUBJECT`；实现补齐 `QUESTION_ID_REQUIRED`（缺题 id）/ `ANSWER_REQUIRED`（缺答案 —— **跳过该条**而非整批 `400`，一条脏数据不该废掉 199 条）/ `DUPLICATE_IN_BATCH`（批内同题）/ `SERVER_NEWER`（服务端已有更新值）。**对外不变式**：`accepted + skipped == items.length`（被去重的那条也计入 skipped）—— 前端据此决定能否清空离线队列。<br>　**b. 冲突合并用 `clientTime` 比对、不写 `clientTime`**：判据 = 本条 `clientTime` < 服务端已有 `last_modified_time` → 跳过。⚠️ 若改用**服务端 now** 比对，后到的补传永远"更新"、会把联网后的新作答冲掉（这正是本条要防的）；写入侧仍**只写服务端 now**（`clientTime` 不落 `last_modified_time`），符合 §3.3.2 第 4 条「不用 `clientTime` 覆盖服务端时间戳」。<br>　**c. `current_question_id` / `current_question_number` 不更新**：离线补传是「回填历史」，不代表「当前断点」（文档「涉及表」也只列了 `version` / `answered_count`），故只写 `lastSavedTime`；断点仍由在线逐题作答（3.3.1 第 6 条）维护。<br>　**d. 一条都没写进去时不动记录**：全跳过时不 `updateById`（白涨一次 `version` 没意义），响应 `answeredCount` 取行锁读到的记录值。<br>　**附**：`@RequestBody(required=false)` + 缺 Body → `8005`（文档只写 `items[]` 必填；用默认必填时，缺 Body 会先被 common 的 `HttpMessageNotReadableException` 兜成「请求体格式错误」，与 [0.5](#05-错误码) 的「参数越界 = 8005」不一致）。**顺带修正两处措辞 / 断言**：① 「唯一读 `q.answer` 的查询」改为「唯二」（新增批量孪生）——`CscaQuestionMapper` 注释已同步；② `CscaAnswerMapperXmlContractTest#onlyTheAnswerQueryReadsTheStandardAnswer` 原先断言 `selectForAnswer` 语句里**字面**出现 `q.answer`，作答列抽成共用片段后该断言必然误报（本轮首次跑测试即红）→ 改为断言**共用片段**含 `q.answer` / `q.analysis`、且两条作答查询都 `include` 该片段。  <br>⚠️ **就近更新（2026-10-14）**：支撑表 **TEST 已建表**（见第 52 条）；「同步错题本」**仍未接线**。|

| **43** | **新建 `GET /csca/questions/{questionId}/solution` 答案出口**（2026-10-13 用户口径：「GET /csca/questions/{questionId}/solution根据文档写这个接口」） | 该端点此前**未编码**（[3.3.3](#333-get-cscaquestionsquestionidsolution) 只有设计）；它是模块内**唯一把 `question.answer` 直接下发**的内容出口（另一个是 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 的 `immediate=true`，走快照） | ✅ **已按 [3.3.3](#333-get-cscaquestionsquestionidsolution) 实现**：<br>① **新增** `dto/CscaSolutionRow`（库内行：`id / typeId / answer / analysis / score`）、`dto/CscaSolutionResponse`（+ 静态工厂 `of(row)` 承载组装口径）；<br>② **Mapper** `CscaQuestionMapper#selectSolution`(+`.xml`)：`q.id = #{questionId}` **主键直取**、**只取 4 列**（`type_id` / `answer` / `analysis` / `score`），include `cscaPaperBase` + `cscaQuestionValid`（**与 [3.2.3](#323-get-cscaquestionsquestionid) 同一份准入** → HSK 的题查不到 = `8006`）；**不按语言筛**（无该入参）；**不带题面**（`passage` / `content` / `option_content` / `layout` 一律不取）；<br>③ **Service** `CscaQuestionQueryService#solution`：准入为 `null` → `CSCA_QUESTION_NOT_FOUND(8006)`；组装交 `CscaSolutionResponse#of`。**不读快照**、**不校验是否已作答**（背题模式成立的前提，§3.3.3 第 5 条 —— 要看"作答当时"的答案走 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 的 `immediate=true`）；<br>④ **答案出口三口径**：`standardAnswer` = `question.answer` **原文**（不归一化）；`standardAnswerLabels` = `CscaAnswerNormalizer#splitRaw`（**只切分**、丢空串、**保序**，不 trim / 不转大写 / 不去「答案」/ 不去重 / 不排序）；`typeId` 走 `CscaQuestionTypes#display`（`SINGLE` / `MULTI`）；<br>⑤ **Controller** `CscaCatalogController#solution`：强鉴权（`requireAuthenticatedAppUserId`，未登录 / 非 APP → `401`）；路径变量**手工解析**（复用详情接口抽出的 `parseQuestionId`，非数字 → `8005`）；<br>⑥ **单测**：`CscaSolutionResponseTest`(7) + `CscaSolutionMapperXmlContractTest`(4) → 与既有 8 组共 **64 绿**；`mvn -pl practice-service -am compile -DskipTests` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **一处实现细化（文档把 `standardAnswer` / `standardAnswerLabels` 并列，未点明 labels 也走特判；按第 1 条口径推导，如需回改请说）**：**`无` / `NULL` / 空白 → `standardAnswer = null` 且 `standardAnswerLabels = []`（两者一起特判）**。若只特判 `standardAnswer` 而让 labels 走 `splitRaw("无")`，会切出 `["无"]` → 前端高亮会亮出一个不存在的选项；故把特判同时作用于 labels。⚠️ 另：响应**刻意不加 `@JsonInclude(NON_NULL)`** —— `standardAnswer` / `analysis` 的 `null` 是有语义的（"这题没答案 / 没解析"），键须恒出现。<br>⚠️ **顺带更正三处测试注释口径**（无逻辑改动）：`CscaQuestionDetailMapperXmlContractTest` / `CscaAnswerMapperXmlContractTest` 里「唯一例外是 `selectForAnswer`」的措辞改为「例外 = 作答链路 `selectForAnswer` / `selectForAnswerBatch` + 答案出口 `selectSolution`」——本轮新增了合法的答案读取者，旧措辞已不准确；并新增 `CscaSolutionMapperXmlContractTest` 钉住「`selectSolution` <b>必须</b>读 `q.answer`」（防止有人"顺手清理"成不取答案、导致接口静默返回空）。 |
| **44** | **作答响应新增 `standardAnswerLabels`**（2026-10-13 用户口径：「PUT /csca/records/{recordId}/answers/{questionId}的返回 JSON（`immediate=true`）新增"standardAnswerLabels"字段」） | [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 的 `immediate=true` 原先只回 `standardAnswer` **原文**，前端要高亮选项得自己按分隔符切（各端各写一套、脏值处理不一致）；而 [3.3.3](#333-get-cscaquestionsquestionidsolution) 早已下发 `standardAnswerLabels`，[3.6.2](#362-错题本wrong-book) 的复习作答响应也标着「与 3.3.1 同构**另加** `standardAnswerLabels`」 —— 三处本该同构，却差这一个字段 | ✅ **已实现**：<br>① **新增字段** `CscaAnswerSaveResponse#standardAnswerLabels`（`List<String>`），**只在 `immediate=true` 时装配**，与 `standardAnswer` **同源**（都取刚写入的 `standard_answer_snapshot` 原值）；<br>② **口径收口**：抽出 `CscaAnswerNormalizer#outputLabels(String)`（`无` / NULL / 空白 → **`[]`**，否则 `splitRaw`）作为**两个答案出口共用的唯一入口**，`CscaSolutionResponse#of` 一并改调它（**行为不变**）—— 防止日后只改一处、让 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 与 [3.3.3](#333-get-cscaquestionsquestionidsolution) 的同名字段漂移；<br>③ **`@JsonInclude(NON_NULL)` 下的键出现规则**（文档已补注，前端需按语义区分）：`immediate=false` → 键**缺席**；`immediate=true` 但该题**无标准答案** → `standardAnswer` **缺席**、`standardAnswerLabels` 为 **`[]`**（空数组本身有语义，不能省）；<br>④ **文档同步**：[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 返回 JSON 示例加该字段、入参表 `immediate` 说明更新（**顺带更正**：原写「响应带 `correct / …`」，实际字段是 `isCorrect`）、业务逻辑第 5 条补 labels 口径与键出现规则；[3.6.2](#362-错题本wrong-book) 那句措辞由「同构……**另加** `standardAnswerLabels`」改为「**完全同构**」；<br>⑤ **单测**：`dto/CscaAnswerSaveResponseTest`（**新增 4 例**，Jackson **序列化层面**钉住「`immediate=false` 键缺席 / 原值保序不去重 / 无答案 → `[]` 且 `standardAnswer` 缺席 / 脏值 `D\n答案` 不清洗」）+ `CscaAnswerNormalizerTest` 补 2 例 `outputLabels` → 与既有 9 组共 **70 绿**；`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS**（JDK17）。 |

| **45** | **新建 `GET /csca/records/{recordId}` 练习态**（2026-10-14 用户口径：「根据文档写/csca/records/{recordId}接口」） | 该端点此前**未编码**（[3.4.1](#341-get-cscarecordsrecordid) 只有设计）；它是前端「继续练习 / 断点恢复」的唯一数据源，也是「**这一轮**」进度的唯一出口（[3.1.1](#311-get-cscacatalog) 的科目卡给的是「最新一轮」） | ✅ **已按 [3.4.1](#341-get-cscarecordsrecordid) 实现**：<br>① **新增** `dto/CscaRecordDetailResponse`（15 字段，`recordId` / `currentQuestionId` 走全站 Long→字符串口径）+ `dto/CscaRecordStatRow`（四项统计聚合行）；<br>② **`CscaRecordMapper#selectRecordDetail` 扩展 4 列**（`last_saved_time` / `current_question_id` / `current_question_number` / `duration_seconds`）—— 与建轮复用路径（[3.2.1](#321-post-cscarecords)）**共用同一 SQL**，扩展列对前者零影响；**刻意不取** `correct_count` / `wrong_count`（记录未提交时它们还是 0，§3.4.1 第 2 条 —— 已由契约测试钉死「详情不得读缓存列」）；<br>③ **新增 `CscaAnswerMapper#countByRecord`**：一条 SQL 取齐 `answeredCount` / `correctCount` / `wrongCount` / `unGradedCount`（`COUNT(*)` 无 `GROUP BY` → 恒 1 行），显式带 `section_mapping='SEC_CSCA'` + `deleted=0` + `answered=1`，`SUM` 用 `IFNULL(...,0)` 兜 0。⚠️ **与 `selectAnsweredCount` 并存、不合并**：后者是作答链路的写侧统计（语义单一、被 `save` / `batchReport` 复用），本方法是读侧四项聚合；<br>④ **Service** `CscaRecordService#detail`：归属校验（本人 + CSCA，否则 `8007`，**不返回 403**）→ 实时统计 → 组装（`accuracyRate` 分母是**已作答**、保留 2 位、未作答回 `0`，与 [3.1.1](#311-get-cscacatalog) **同一定义** —— 两处都不拿 `total_questions` 当分母）；`totalQuestions` 取记录缓存列，为空回落 `question_ids` 长度（**与 [3.2.2](#322-get-cscaquestions) `availableCount` 同源**）；<br>⑤ **Controller** `CscaRecordController#detail`：强鉴权（`requireAuthenticatedAppUserId`）+ 路径变量**手工解析**（复用 `parseId`，非数字 → `8005`，理由同第 40 条 —— common 无 `MethodArgumentTypeMismatchException` 处理器）；网关白名单**无需改动**（`/csca/records*` 本就不在白名单）；<br>⑥ **单测**：`CscaRecordDetailServiceImplTest`（10，Mockito：实时统计 / 未评分计入分母 / `durationSeconds` 双来源 / 三处 8007 / 题集兜底）+ `CscaRecordDetailMapperXmlContractTest`（4，SQL 契约）→ 与既有 10 组共 **80 绿**；`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **两处实现细化（文档未明写 / 已补注 §3.4.1 第 5 条，如需回改请说）**：<br>　**a.** `durationSeconds` 在**已提交但 `duration_seconds` 为 `null`**（提交链路 [3.5.1](#351-post-cscarecordsrecordidsubmit) 尚未接线）时**回落实时计算**（`now - start_time`），而非回 `null` / `0`；`start_time` 缺失 / 时钟回拨 → `0`（不回负数）。<br>　**b.** **不限制记录状态**：已放弃（`2`）/ 已提交（`3`）的轮次同样可查 —— 与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid)（作答链路要求 `status IN (0,1)`）刻意不同。<br>🔁 **顺带更正第 44 条**：其中 `dto/CscaAnswerSaveResponseTest`（4 例）已于同日按测试策略口径**删除**（用户口径「和接口无关就删」）—— practice-service **无接口级测试**（31 个测试类零 MockMvc / `@SpringBootTest`，测试只有「纯函数单测 / XML 契约测试 / Mockito Service 单测」三型），该测试只测 DTO 注解 + 字段、够不上「和接口有关」；**同层的 `CscaSolutionResponseTest` 保留**（它测 `CscaSolutionResponse#of` 这个**有逻辑的组装工厂**）。代价：`@JsonInclude(NON_NULL)` 的「键缺席 vs `[]`」此后**无测试覆盖**（只靠注解 + §3.3.1 第 5 条注记约束）。CSCA 组当时由 70 → **66 绿**，本轮再 +14 → **80 绿**。<br>⚠️ **未做**：DB 实跑联调（连库审批受限）；`answer-card`([3.4.2](#342-get-cscarecordsrecordidanswer-card)) / `submit`([3.5.1](#351-post-cscarecordsrecordidsubmit)) / `favorites*`([3.6.1](#361-收藏favorite)) / `wrong-book*`([3.6.2](#362-错题本wrong-book)) 仍未编码（端点总数仍 13，本接口是第 **6** 个已编码端点）。 |

| **46** | **新建 `GET /csca/records/{recordId}/answer-card` 答题卡**（2026-10-14 用户口径：「GET /csca/records/{recordId}/answer-card根据文档写这个接口」） | 该端点此前**未编码**（[3.4.2](#342-get-cscarecordsrecordidanswer-card) 只有设计）；它对外承诺的 `favorite` / `favoriteCount` 依赖第 31 条那张**尚未建表**的 `question_favorite` | ✅ **已按 [3.4.2](#342-get-cscarecordsrecordidanswer-card) 实现**：<br>① **新增** `dto/CscaAnswerCardResponse`（顶部 7 个统计 + `cards[]` + `byType[]`；`byType` 带 `@JsonInclude(NON_NULL)` —— `withGroup=false` 时**键缺席**，不是空数组）、`dto/CscaAnswerCardItem`（逐题格 `questionId / seq / number / typeId / answered / isCorrect / favorite`，其中 `answered` / `isCorrect` 是**数字** `0/1/2`）、`dto/CscaAnswerTypeStat`（`typeId / total / answered / correct / accuracyRate`）、`dto/CscaCardQuestionRow`（`id / number / type_id`）、`dto/CscaAnswerStateRow`（`questionId / answered / isCorrect`）；<br>② **Mapper 三查询**：`CscaQuestionMapper#selectCardQuestions`（`q.id IN 题集`，**只取 3 列**、不分页不排序不限语言，include `cscaPaperBase` + `cscaQuestionValid`）、`CscaAnswerMapper#selectByRecord`（答案状态**明细**，带 `section_mapping='SEC_CSCA'` + `deleted=0` + `answered=1`）、**新建** `csca/mapper/CscaFavoriteMapper`(+`.xml`) 的 `selectFavoritedQuestionIds`（`user_id` + `deleted=0` + `question_id IN 题集`；[3.6.1](#361-收藏favorite) 的三个收藏端点将复用该类）；<br>③ **Service** `CscaAnswerService#answerCard`（按 三层逻辑表 落位）：归属校验（本人 + CSCA → 否则 `8007`，**不返回 403**）→ 读**固定题集**（`question_ids`，**不重算**）→ 三份原料各 1 次查询 → 按题集原序拼 `cards[]`（`seq` 递增）→ **由 `cards` 现场汇总**四个统计 + `favoriteCount` → 按映射值分组出 `byType`（固定 `SINGLE` → `MULTI`）；<br>④ **Controller** `CscaRecordController#answerCard`：强鉴权（`requireAuthenticatedAppUserId`）+ 路径变量**手工解析**（复用 `parseId`，非数字 → `8005`）+ `withGroup` **缺省 `true`**（用 `Boolean` 而非 `boolean`，才能区分"没传"与显式 `false`）；<br>⑤ **单测**：`CscaAnswerCardServiceImplTest`（10，Mockito：`seq`≠`number` / 未评分不当答错 / 两行 `byType` 与 2 位正确率 / `withGroup=false` 时 `byType` 为 `null` / 题被删仍占一格 / 收藏范围限题集 / 空题集零卡不查库 / 三处 `8007`）+ `CscaAnswerCardMapperXmlContractTest`（5，SQL 契约：只取 3 列 / 回明细不回 `COUNT` / 限 CSCA / 收藏只认 `deleted=0`）→ 与既有 11 组共 **95 绿**；`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **四处实现细化 / 差异（文档未明写或落不了地，已同步补注 §3.4.2 第 1 / 5 / 6 条与 三层逻辑，如需回改请说）**：<br>　**a.** 🔴 **`seq` 只能是「题集自然序下标 + 1」**：本接口**无** `shuffle` / `seed` 入参、`practice_record` 也**不落库**乱序参数 → 练习若以 `shuffle=true` 开始，答题卡 `seq` 与**答题页题序不一致**（题集内容 / `totalQuestions` 仍一致）。**要修二选一**：① 答题卡补 `shuffle` / `seed` 入参（推荐，**零改表**）；② 乱序参数落库（**要改表**）。当前按"自然序"实现。<br>　**b.** **四个统计由 `cards` 汇总，而不是 `countByRecord` 全量 `COUNT`**：保证顶部统计与网格**同源同值**、`unansweredCount` **恒非负**（另有 `Math.max(0, …)` 防御）。代价是与 [3.4.1](#341-get-cscarecordsrecordid) 在「记录里存在不属于题集的作答行」时会不同 —— 而**作答链路只校验科目、不校验题集成员**（§3.3.1 第 2 条），这种行理论上可被写出来。<br>　**c.** 🔴 **`favorite` 段的前置条件**：`question_favorite` **TEST / PROD 均尚未建表** → **建表前调本接口会在这条 SQL 上失败**。**建表脚本已落盘**：`tmp/_ddl_question_favorite.py`（五闸门、默认 DRY-RUN；G4 核对 8 列类型/可空性 + 3 个索引 + `InnoDB` + `utf8mb4_0900_ai_ci` + `DYNAMIC`；DRY-RUN 已跑通）—— 确认后 `--apply` 即可（**附 5** 已同步）。<br>　**d.** **题集内的题被逻辑删时仍占一格**（`number` / `typeId` 为 `null`、`seq` 连续），保证 `cards` 长度**恒等于** `totalQuestions`；该格**不进任何题型分组** → `byType[].total` 之和会**略小于** `totalQuestions`。  <br>⚠️ **就近更新（2026-10-14）**：支撑表 **TEST 已建表**（见第 52 条）→ 答题卡的 `favorite` / `favoriteCount` 在 TEST 已可直接调用。|

| **47** | **收藏 / 错题本两张新表的索引精简：删 `idx_user_section`（收藏 + 错题本）与 `idx_user_source`（错题本）**（2026-10-14 用户口径：「question_favorite 的 `UNIQUE KEY uk_user_question …` / `KEY idx_user_section …` / `KEY idx_user_time …` 可以删掉吗」） | 三组索引逐个核对：**`uk_user_question` 不可删** —— 它是唯一键，既是 `INSERT … ON DUPLICATE KEY UPDATE`（幂等收藏 / 取消 + 软删复活）的**唯一依据**，也是答题卡 `question_id IN` 查询的索引；**`idx_user_time` 保留** —— 列表倒序分页**唯一免 filesort** 的索引；**`idx_user_section` / `idx_user_source` 是最冗余的两个** —— 低选择性筛选列、主路径（不传筛选）不经过，且原 `idx_user_section` 里 `section_mapping` 恒 `SEC_CSCA` 是常量列占位。⚠️ 两张表 **TEST / PROD 均未建表** → 改动**零成本**，不需 ALTER 既有表 | ✅ **已改**（**只改文档 + `tmp/_ddl_question_favorite.py`，未建表、未改任何 .java**）：<br>① [3.6.1](#361-收藏favorite) 第 5 条 DDL 删 `idx_user_section`，同条「索引分工」重写为「只留 2 个二级索引」+ 记录删除理由；<br>② [3.6.2](#362-错题本wrong-book) 第 9 条 DDL 删 `idx_user_section` / `idx_user_source`，第 9 条注改为「索引集合与收藏表完全一致」；<br>③ 文末 **附 5 / 附 6** 索引列举 4 → 2，G4 回读核对「4 个索引名」→ **3 个**（含 `PRIMARY`）；[4.4](#44-文档与实现的差异) 第 46 条 c 项同步；<br>④ `tmp/_ddl_question_favorite.py` 同步：DDL 删该行、`EXPECTED_INDEXES` 收为 `{PRIMARY, uk_user_question, idx_user_time}`、G4 打印文案与 docstring 同步；<br>⑤ **未改**：`section` / `source` 列**保留**（免 join 快照列），两张表的列定义、`uk_user_question` 唯一键、`deleted` 软删复活口径**零变更**。  <br>⚠️ **就近更新（2026-10-14）**：两表 **TEST 已建表**（见第 52 条），且**建的就是本条精简后的「3 索引」版本** → 无需 ALTER；⚠️ PROD 仍未建，按本条口径建即可。|
| **48** | **收藏表补 `source` 列：与错题本表完全对称**（2026-10-14 用户口径：「question_favorite 加一个 source 字段」） | 收藏表原本**没有来源维度**，而姊妹表错题本有 `source`（`prac` / `exam`）—— 文档里因此多处写着「错题本比收藏表**多出的一个维度**」（[4.1](#41-枚举速查)）、「两处口径差异」「只多一个 `source` 列」（[3.6.2](#362-错题本wrong-book) 开头 / 第 9 条），两张表**结构不对称**；将来考试侧要收藏（`exam`）时**无处落列** | ✅ **已改（只改文档 + `tmp/_ddl_question_favorite.py`，未建表、未改任何 .java）**：<br>① [3.6.1](#361-收藏favorite) 第 5 条 DDL 加 **`source VARCHAR(20) NOT NULL DEFAULT 'prac'`**（列位置与错题本一致：`section` 之后、`created_time` 之前）；<br>② **完全对称**：`GET /csca/favorites` 加 **`source` 筛选入参**（`prac` / `exam`，不传 = 全部）+ **列表元素下发 `source`**；<br>③ 业务逻辑新增 **第 7 条「来源维度」**（与 [3.6.2](#362-错题本wrong-book) 第 6 条同列同义 —— 本模块只写 `prac`、`exam` 待考试侧接入）；第 1 条 upsert 补 `source` 写入口径（**只在 INSERT 写、`ON DUPLICATE` 不含**，保留首次收藏来源）；<br>④ [3.6.2](#362-错题本wrong-book) 开头「两处口径差异」→ **唯一差异 = 答对自动移出**（🔴 该差异已于 2026-10-19 取消，两表口径现完全一致，见第 62 条）；第 9 条「只多一个 `source` 列」→ **两表互为镜像、列定义与索引完全一致**；<br>⑤ [4.1](#41-枚举速查) `source` 标题由「错题本来源……比收藏表多出的一个维度」→「**收藏 / 错题本共用来源列**」；<br>⑥ 文末 **附 5** 列清单补 `source`（8 列 → **9 列**）；`tmp/_ddl_question_favorite.py` 同步（DDL 加列、`EXPECTED_COLUMNS` 加 `source`、G4 文案 8 → 9 列）。<br>⚠️ **取代关系**：第 31 / 32 条原「错题本比收藏表多一个 `source` 列 / 多一个维度」的表述**已作废**（旧条目按历史保留，摘要已就近更正）。 |
| **49** | **收藏 / 错题本两张新表补审计列 `created_by` / `update_by`，末 5 列与既有 `practice_*` 表同序**（2026-10-14 用户口径：贴出 `BaseEntity` 与 `ExamRecord extends BaseEntity` 两张截图 →「补上这些字段」） | 两张新表原只有 `deleted` / `created_time` / `updated_time`，**缺 `created_by` / `update_by`**；而本库**所有业务实体都 `extends BaseEntity`**（`common/entity/BaseEntity.java`），MyBatis-Plus 的 [DBMetaObjectHandler](file:///d:/code/hsk_treasure/common/src/main/java/com/hsktreasure/common/handler/DBMetaObjectHandler.java) 在 `insertFill` 里对这两个字段做 `FieldFill` 自动填充 → **表缺列时实体 `INSERT` 报 `Unknown column 'created_by'`** | ✅ **已改（只改文档 + `tmp/_ddl_question_favorite.py`，未建表、未改任何 .java）**：<br>① [3.6.1](#361-收藏favorite) 第 5 条与 [3.6.2](#362-错题本wrong-book) 第 9 条 DDL 各加 **`created_by BIGINT DEFAULT NULL`** / **`update_by BIGINT DEFAULT NULL`**，并把 **`deleted` 前移** → 末 5 列 = `deleted` → `created_by` → `update_by` → `created_time` → `updated_time`（**与 TEST 库 `practice_answer` / `practice_report` 实测顺序逐列一致**；两列均可空，同既有表）；<br>② 两表「列风格 / 互为镜像」bullet 补审计列说明 —— ⚠️ 本组是**手写 `INSERT … ON DUPLICATE KEY UPDATE`**（不走 MP 的 `saveOrUpdate`），**自动填充不生效，需在 SQL 里显式带入**这 4 列；<br>③ 文末**附 5 / 附 6** 列清单 9 列 → **11 列**、G4 回读文案同步；`tmp/_ddl_question_favorite.py` 同步（DDL、`EXPECTED_COLUMNS` +2、G4 文案 9 → 11 列）；<br>④ 顺带把姊妹表脚本 **`tmp/_ddl_question_wrong.py`** 一并落盘（此前一直缺，附 6 只写「待生成」），DDL 与收藏表**逐字对齐**（当时 11 列 + 同 2 索引；2026-10-14 又同批加「来源轮次」两列 → 13 列，见第 50 条），DRY-RUN 同样通过。<br>⚠️ 两表仍**互为镜像**（11 列 + 同 2 个索引），差异仍只有「答对自动移出」一条。 |
| **50** | **收藏 / 错题本两张新表加「来源轮次」两列：`practice_record_id` + `exam_record_id`**（2026-10-14 用户口径：「加上练习的recordid」→「考试的recordid也加上」） | 两张表原本只记「哪条链路」（`source`）、**不记「哪一轮」** —— 无法把一条收藏 / 错题**回溯到产生它的那次练习或考试** | ✅ **已改（只改文档 + 两个 DDL 脚本，未建表、未改任何 .java）**：<br>① 两张表 DDL 各加 **`practice_record_id BIGINT DEFAULT NULL`**（= `practice_record.id`）与 **`exam_record_id BIGINT DEFAULT NULL`**（= `exam_record.id`），位于 `source` 之后 → 两表 **13 列**、仍**完全镜像**；<br>② 🔴 **两列不进唯一键**（`uk_user_question(user_id, question_id)` 不变）→ 收藏 / 错题本**仍是一题一行**，「再来一轮」**不会分裂成多行**（[3.6.2](#362-错题本wrong-book) 第 5 条同步改写）；<br>③ 🔴 **只在 INSERT 写、`ON DUPLICATE KEY UPDATE` 不含**（与 `source` 同口径）→ 保留**首次收藏 / 收录时的轮次**；<br>④ 写入点：[3.6.1](#361-收藏favorite) 收藏入参新增 **`recordId`**（Query，可选）；错题本收录由作答链路驱动 —— [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条 / [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 第 6 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条**一并携带 `practice_record_id`**；<br>⑤ **复习作答**（[3.6.2](#362-错题本wrong-book) 第 11 条 ④）**无轮次上下文 → 保留原值**（不覆盖、不置空）；<br>⑥ 新增业务逻辑条目 [3.6.1](#361-收藏favorite) 第 8 条 / [3.6.2](#362-错题本wrong-book) 第 11 条；两列表响应元素各加 `practiceRecordId` / `examRecordId`。<br>⚠️ **本模块只写 `practice_record_id`**（`exam_record_id` 恒 `NULL`，待考试侧接入）；两列**只存快照** —— 不参与唯一键 / 查询条件 / 鉴权。⚠️ **2026-10-19 已被第 70 条合并为 `record_id`**（本节保留原口径，仅作沿革）。 |
| **51** | **两张新表「`user_id` 与 `created_by` / `update_by` 是否重复」的裁定：三者都保留、结构与列零变更**（2026-10-14 用户口径：「user_id 不是和 created_by、update_by…」→ 拍板「保持现状，三列都留」） | 两张表同时有 `user_id` 与审计列 `created_by` / `update_by`，且在本组写入口径下**取值恒等**（手写 `INSERT … ON DUPLICATE KEY UPDATE` 显式传同一个登录用户 `id`），**容易被误读为冗余**，有「删列」的诱惑 | ✅ **已裁定（结构零变更 —— DDL、两个建表脚本、.java 均未改；本节仅作登记）**：<br>① 🔴 **`user_id` 删不得** —— 它是**业务归属列**（`NOT NULL`），同时是唯一键成员 `uk_user_question(user_id, question_id)`、索引 `idx_user_time` 的首列、以及列表 / 答题卡**全部查询的过滤条件**；<br>② 🔴 **`created_by` / `update_by` 也删不得** —— 本库 86 张表中 **81 张带这两列**，其中 **39 张「三者齐全」**（含 `practice_answer` / `practice_record` / `practice_report` / `exam_record` / `exam_answer`…）；删掉后这两张表会退出该惯例，且实体 `extends BaseEntity` 后一旦走 MP 的 `insert` 直写即报 `Unknown column 'created_by'`；<br>③ 🔴 **实测反证：审计列承担不了归属职责** —— [`DBMetaObjectHandler#insertFill`](file:///d:/code/hsk_treasure/common/src/main/java/com/hsktreasure/common/handler/DBMetaObjectHandler.java) 只在 `userInfo != null`（有登录态）时才填充，**TEST 库 `practice_record` 884 / 887 行 `created_by` 为 NULL**（脚本 / 无登录态写入所致）；而**唯一键列一旦可为 NULL，MySQL 允许多行 NULL → 约束直接失效**；<br>④ **分工维持**：`user_id` 记**归属**、`created_by` / `update_by` 记**审计**；两表列定义、索引、写入口径**零变更**（见 [3.6.1](#361-收藏favorite) 第 5 条与 [3.6.2](#362-错题本wrong-book) 第 9 条，后者已写明「手写 upsert 需显式带入这 4 列」）。 |
| **52** | **两张新表 TEST 已建（2026-10-14 11:01）—— 收藏 / 错题本支撑表由「设计」进入「可用」**（2026-10-14 用户口径：「新建表在数据库」→ 拍板**只建 TEST**） | 两张表的 DDL 自 2026-10-13 起一直停在文档与脚本里（第 31 / 32 / 47 / 48 / 49 / 50 / 51 条反复打磨结构），**TEST / PROD 库中始终没有** → [3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card) 的 `favorite` / `favoriteCount`（**已编码**，第 46 条）在 TEST 一调即 `Table doesn't exist` | ✅ **TEST 已建表**（`python tmp/_ddl_question_favorite.py --apply` + `tmp/_ddl_question_wrong.py --apply`）：<br>① **G1** `xuexitest` / **G2** `787e3b0c860c` 通过；**G3** 落盘 `tmp/_backup_practice_{favorite,wrong}_tables_20261014_1101*.json` + `tmp/_rollback_question_{favorite,wrong}_20261014_1101*.sql`（回滚 = `DROP TABLE`）；**G4** 回读：**13 列**类型 / 可空性逐列一致、**3 个索引**（`PRIMARY` / `uk_user_question` / `idx_user_time`）、`InnoDB` + `utf8mb4_0900_ai_ci` + `Dynamic`、**0 行** → `COMMIT`；<br>② 建表后 **TEST 表总数 86 → 88**（`practice_*` 9 → **11 张**），两表**互为镜像**（结构逐列一致）；<br>③ 🆕 **只读复核脚本 `tmp/_verify_ddl_question_tables.py`**（`--prod` 可切库）—— 独立于建表脚本做同源核对，防「脚本自证」；<br>④ 🔴 **首跑踩坑（脚本已修）**：G4 原断言 `ROW_FORMAT == "DYNAMIC"`，而 `information_schema` 实回 **`Dynamic`** → 断言失败；且 **MySQL DDL 隐式提交 —— `conn.rollback()` 对 `CREATE TABLE` 无效**（当时表其实已落库，靠 G5 幂等挡住二次执行）。已改 `.upper()` 比较 + `except` 分支补**显式 `DROP TABLE` 补偿**（能进该分支 = G5 已判表原不存在，DROP 安全）；<br>⑤ 🔴 **PROD 未建**（按用户决定本轮只建 TEST）→ **上线前必须补跑 `--prod --apply`**，否则生产的收藏 / 错题本接口直接报 `Table doesn't exist` |

| **53** | **新建两张新表的实体类**（2026-10-14 用户口径：「收藏表和错题表是新表，在代码中新建实体类」） | 第 52 条两张表已建于 TEST，但**代码侧只有 Mapper、没有实体映射** —— 表的存在没被数据模型表达；[3.6.1](#361-收藏favorite) / [3.6.2](#362-错题本wrong-book)「三层逻辑」表也只列到 Mapper | ✅ **已建**（**只新增 2 个 .java，未改任何既有文件**）：<br>① **新增** `csca/entity/PracticeQuestionFavorite`（映射 `question_favorite`）/ `csca/entity/PracticeQuestionWrong`（映射 `question_wrong`）—— 均 `@Data` + `@EqualsAndHashCode(callSuper = true)` + `@SuperBuilder` + `@NoArgsConstructor` + `@AllArgsConstructor` + `@TableName`，**`extends BaseEntity`**（与 [4.4](#44-文档与实现的差异) 第 49 条「本库业务实体都 extends BaseEntity」一致）；<br>② **字段**：自有 8 列（`id` / `user_id` / `question_id` / `section_mapping` / `section` / `source` / `practice_record_id` / `exam_record_id`，`@TableId` 用 `IdType.ASSIGN_ID` = 雪花）+ **末 5 列由 `BaseEntity` 继承**（`deleted` / `created_by` / `update_by` / `created_time` / `updated_time`）→ **与库表 13 列逐列同序**；<br>③ **验证**：只读连库逐列比对 `SHOW FULL COLUMNS`（TEST `787e3b0c860c`）→ 两表各 **13 列与实体声明顺序完全一致**（含类型）；`mvn -pl practice-service -am compile -DskipTests` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **四处实现说明（文档未明写，如需回改请说）**：<br>　**a.** 包选 **`csca/entity`**（不是 `core/entity`）：两表当前**唯一消费者是 CSCA**（`section_mapping` 恒 `SEC_CSCA`）、对应 Mapper 也叫 `CscaFavoriteMapper` —— 放 `core/entity` 会把 CSCA 专属表混进共享包；**类名按本库惯例 = 表名 PascalCase**（同 `PracticeQuestionOptionPool` ← `practice_question_option_pool`）。将来 HSK 侧真复用同表时，再上移 `core/entity`（零调用方，移动成本极低）。<br>　**b.** 🔴 **两个实体暂未被任何代码调用**：按第 49 条口径，两张表的读写**全是手写 SQL** —— 实体先落位，**待 [3.6.1](#361-收藏favorite) / [3.6.2](#362-错题本wrong-book) 端点编码时接入**（若要直接用 MP 查询，需让 `CscaFavoriteMapper` / 新建的 `CscaWrongBookMapper` `extends BaseMapper<…>`）。<br>　**c.** **不引入 `@TableLogic`**：本库 `BaseEntity.deleted` **没有**逻辑删注解、配置里也没有 `logic-delete-field`，「软删复活」由**手写 SQL 显式表达**（`INSERT … ON DUPLICATE KEY UPDATE deleted = 0/1`、查询显式 `deleted = 0`）；给子类加 `@TableLogic` 需要在子类重声明与父类同名的 `deleted` 字段，既无必要也有风险 —— 保持零 `@TableLogic`。<br>　**d.** **不新增测试**：按本模块既有取舍（纯注解 / 字段、无组装逻辑的类不写测试，见第 44 条删除记录），实体的正确性由「逐列连库核对 + 编译」覆盖，不建测试类。 |
| **54** | **两张新表去 `practice_` 前缀：`practice_question_favorite` → `question_favorite`、`practice_question_wrong` → `question_wrong`（库 + 代码 + 文档一体改名）**（2026-10-14 用户口径：「practice_不带这个前缀，数据库里的也改了」） | 两张表的表名自设计起就带 `practice_` —— 但本库 `practice_*` 是**「练习链路」表族**（`practice_record` / `practice_answer` / `practice_report` / `practice_paper_structure`…，靠 `practice_record` 串起一次练习）；两张新表**不属于该族**（收藏 / 错题本**独立于某一轮练习**，读取不 join `practice_record`，`practice_record_id` 只是可选快照列）；库中另有 `question` / `question_group` / `question_shared_audio` 一族，**收藏 / 错题本天然属于「题目」族** | ✅ **已改（库 + 实体 + 代码 + 文档 + 可复用脚本，全链路一致）**：<br>① 🔴 **DB（TEST `xuexitest`）已改名**：`python tmp/_rename_question_tables.py --apply` → **G1** `xuexitest` / **G2** `787e3b0c860c` 通过；**G3** 落盘 `tmp/_rename_question_tables_before_*.json` + `tmp/_rollback_rename_question_tables_*.sql`（回滚 = 改回旧名）；**G4** 回读：**表总数 88 张不变**、两张新名表**13 列 / 3 索引 / `InnoDB` / `utf8mb4_0900_ai_ci` / `Dynamic` 逐项与改前一致**、改前表名逐个已消失 → `COMMIT`；<br>② **实体类重命名**：`csca/entity/PracticeQuestionFavorite` → **`QuestionFavorite`**、`PracticeQuestionWrong` → **`QuestionWrong`**（`@TableName` 同步为 `question_favorite` / `question_wrong`）；旧文件与其 `target` 残留 class 已删；<br>③ **代码引用同步**：`CscaFavoriteMapper`(+xml) 的表名与注释、`CscaAnswerCardItem` / `CscaRecordController` / `CscaAnswerServiceImpl` 注释、契约测试断言（`CscaAnswerCardMapperXmlContractTest`）；<br>④ **文档全文改新名**（共 **63 处**）—— ⚠️ 含 §4.4 第 48 / 53 条**引文中的表名**（引文按新表名同步改写，非另存原名）；<br>⑤ **可复用脚本同步**：`tmp/_verify_ddl_question_tables.py`（`TABLES` 清单 + docstring）、`tmp/_probe_favorite_table.py`（docstring）；<br>⑥ 🔴 **刻意不改的文件**（改写 = 伪造历史）：`tmp/_rename_question_tables.py`（它**必须**保留旧名，是改名映射的真源）、`tmp/_backup_ddl_*.py`（G3 备份快照）、`tmp/_doc_*.py` / `tmp/_notes_*.py`（**已执行过的补丁载荷**，记录当时文档原文）、`tmp/_verify_{5items,audit_cols,recordid,wrongbook}.py`（过去某轮的一次性终验脚本）。<br>⚠️ **命名理由**：与库中既有 `question` / `question_group` / `question_shared_audio` **同族**；且去前缀后**仍不与 `practice_question_option_pool`（真·练习链路表）混淆**。<br>🔴 **踩坑（脚本已修）**：首跑 G4 断言写成「拿**改名后**的表集合去比**改名前**的表集合」→ 必然失败；因 **MySQL DDL 隐式提交、`ROLLBACK` 对 `RENAME TABLE` 无效**，靠 `except` 分支**显式反向 `RENAME`** 把库改了回去（本次改名**可逆**，与 `CREATE TABLE` 不同——那张是只能 `DROP`）；断言改为「**旧名逐个不存在 + 新名逐个存在 + 表总数不变 + 13 列/3 索引逐项一致**」后重跑通过。<br>⚠️ **PROD 未同步**（两张表 PROD 本来就未建，**直接按新名建表即可**，无需改名）。<br>✅ 回归：`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS，95 绿**。 |
| **55** | **新建 `POST /csca/records/{recordId}/submit` 交卷**（2026-10-14 用户口径：「根据文档写POST /csca/records/{recordId}/submit接口」） | 该端点此前**未编码**（[3.5.1](#351-post-cscarecordsrecordidsubmit) 只有设计）；它是「练习闭环」的落点 —— 交卷后 `practice_record` 定态、`practice_report` 落报告，也是后续**错题本**与**成绩统计**的唯一入口；`reportId` 依赖第 32 条那张 `practice_report` 主表（**主表早已存在于 TEST，非新表**） | ✅ **已按 [3.5.1](#351-post-cscarecordsrecordidsubmit) 实现**：<br>① **新增** `dto/CscaSubmitRequest`（**只有 `idempotencyKey`**：仅做长度校验，**不落库**）、`dto/CscaSubmitResponse`（15 字段：`recordId / status / reportId / totalQuestions / answeredCount / correctCount / wrongCount / unansweredCount / unGradedCount / score / fullScore / accuracyRate / durationSeconds / submittedTime`；`score` / `fullScore` 为**定标 2 位字符串**）、`mapper/CscaReportMapper`(+`csca/CscaReportMapper.xml`) 的 `selectIdByRecord`（带 `deleted=0`）与 `upsertReport`（`ON DUPLICATE KEY UPDATE` **只刷新统计列**、`user_id` / `paper_id` / `structure_id` **保留首次值**、`deleted=0` 复活）、`service/CscaSubmissionService`(+`impl/CscaSubmissionServiceImpl`)；<br>② **流程**（八步）：`idempotencyKey` 长度校验（超长 → `8005`）→ `selectByIdForUpdate` **行锁** + 归属校验（非本人 / 非 CSCA → `8007`）→ **幂等闸门**（`status` 已交卷 → 直接读 `existingResult` 组装，**零写入**、不报错）→ `selectForSubmit` 取全量作答行 + **重判** → **只回写「判分结果发生变化」的行**（`updateGradesAfterSubmit`）→ 写 `practice_record` 汇总列（`status=3` 等，`@Version` 乐观锁，冲突 → `409 / RECORD_VERSION_CONFLICT`）→ `upsertReport` 落 `practice_report` → 组装响应；<br>③ **重判基准 = `standard_answer_snapshot`**（**作答那一刻冻结的值**），**不是**实时 `question.answer` —— 题库事后被改不影响历史卷的判分（§3.5.1 第 4 条）；<br>④ **「无标准答案 → 未评分不判错」**：快照缺失 / 答案为 `无` / NULL / 用户未作答 → `unGradedCount`，**既不进 `correctCount` 也不进 `wrongCount`**；**满分只累加「已作答题」**，故 `score / fullScore` 与 `accuracyRate` 同分母；<br>⑤ **单条 `CASE id WHEN … THEN …` 批量回写**（**不是**循环单条 `update`，规避本仓库「循环写库 → 僵尸事务持锁 `1205`」的坑），且**只回写判分有变化的行**（绝大多数行判分不变 → 一次 SQL 写入极少行）；<br>⑥ **单测**：`CscaSubmitServiceImplTest`（20，Mockito：`@Mock` 5 个 Mapper + 真实 `CscaGradingServiceImpl`；覆盖幂等零写入 / 未评分不当错 / 只回写变化行 / `8005` / `8007` / 版本冲突 / 快照兜底 / 时长计算等）+ `CscaSubmitMapperXmlContractTest`（5，SQL 契约：`selectForSubmit` 取全列不限 `answered=1` / `updateGradesAfterSubmit` 单条 `CASE` / `upsertReport` 保留身份列 + `deleted=0`）→ 与既有 13 组共 **120 绿**；`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **四处实现细化 / 差异（文档未明写或落不了地，已同步补注 [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 1 / 2 条与三层逻辑表、数据流向，如需回改请说）**：<br>　**a. 🔴 幂等键 `idempotencyKey` <u>不落库</u>**：[3.5.1](#351-post-cscarecordsrecordidsubmit) 原设想把幂等键写库防重，但 `practice_record.idempotency_key` 列**已被「建轮」链路占用**（复用同一列会冲掉开卷幂等语义）→ 交卷**改用 `status` 天然幂等**：一旦 `status=3`（已交卷），重复提交一律走「读已有结果 + 零写入」分支。`idempotencyKey` 入参**只保留**（长度校验 + 契约兼容），**不参与落库 / 去重**。<br>　**b. 交卷不是「重判全表」而是「只刷新变化行」**：`selectForSubmit` 取全量作答行**不限定 `answered=1`**（未作答行也要进 `unGradedCount` 统计），但 `updateGradesAfterSubmit` 只对**判分值发生了变化**的行发 UPDATE —— 保证二次交卷 / 幂等分支下**零副作用**、不无谓刷新 `updated_time`。<br>　**c. 报告 `upsertReport` 的身份列保留首次值**：`ON DUPLICATE KEY UPDATE` 只刷新统计列（得分 / 题数 / 正确率 / 时长），`user_id` / `paper_id` / `structure_id` **不覆盖**（唯一键 `uk_report_record(practice_record_id)`）—— 一张记录只有一份报告，重交卷只更新统计。<br>　**d. 🔴 错题本同步<u>仍未接线</u>**：[3.5.1](#351-post-cscarecordsrecordidsubmit) 要求交卷后把错题写入 `question_wrong`；表 **TEST 已建**（第 52 条）、实体已建（第 53 条、第 54 条改名），但 `CscaWrongBookService` **尚未编码** → 交卷 Service 第 ⑧ 步留了可执行落点（注释），**待该服务落地后补调用**（与 [4.4](#44-文档与实现的差异) 第 41 条 a 项、第 42 条「同步错题本」同源）。<br>　**附**：`@RequestBody(required = false)` —— **交卷无必填 body**（幂等键可缺省），故不能设为必填（否则前端不传 body 会被 common 的 `HttpMessageNotReadableException` 兜成「请求体格式错误」）；路径变量 `recordId` **手工解析**（非数字 → `8005`，同既有两个记录端点，因 common 的 `GlobalExceptionHandler` **无** `MethodArgumentTypeMismatchException` 处理器）。 |

| **56** | **新建 `PUT /csca/favorites/{questionId}` 收藏**（2026-10-14 用户口径：「PUT /csca/favorites/{questionId}按文档写接口」） | 该端点此前**未编码**（[3.6.1](#361-收藏favorite) 只有设计；同日早前一轮曾完整写出又被用户「回退，先不写收藏接口」整体撤销）；它是原型答题页右上角 ★ / 答题卡 ★ 的落库点，也是「跨设备取回收藏」的唯一写入口；支撑表 `question_favorite` **TEST 已建**（第 52 条）、实体已建（第 53 / 54 条）| ✅ **已按 [3.6.1](#361-收藏favorite) 实现**：<br>① **新增** `dto/CscaFavoriteResponse`（`questionId` / `favorite` / `favoriteCount` —— 前两个 `Long`→字符串序列化、`favoriteCount` 用 **`Integer` 走数字**，与 §3.6.1 示例一致）、`dto/CscaFavoriteAdmissionRow`（准入行：`id` + `subjectTypeMapping`）、`service/CscaFavoriteService`(+`impl/CscaFavoriteServiceImpl`)、`controller/CscaFavoriteController`；<br>② **写侧**：`CscaFavoriteMapper#upsertFavorite(QuestionFavorite)` —— 一条 `INSERT INTO question_favorite … ON DUPLICATE KEY UPDATE deleted = VALUES(deleted), update_by = VALUES(update_by), updated_time = VALUES(updated_time)`。唯一键 `uk_user_question(user_id, question_id)` 是**幂等的唯一依据**；🔴 **`UPDATE` 子句刻意不含** `source` / `practice_record_id` / `exam_record_id` / `section` / `section_mapping` / `created_by` / `created_time` → **保留首次收藏的来源、轮次、科目与首次时间**（§3.6.1 第 1 / 7 / 8 条）；软删行被再次收藏即**复活同一行**；<br>③ **读侧**：`CscaFavoriteMapper#countFavorites(userId)`（`user_id + deleted = 0` 计数）—— 与既有 `selectFavoritedQuestionIds`（答题卡的「**本次题集内**」计数）**口径不同、刻意并存**；<br>④ **准入**：新增 `CscaQuestionMapper#selectFavoriteAdmission(questionId)`，**复用** `cscaPaperBase` + `cscaQuestionValid`（与 `selectDetail` / `selectSolution` **同一份准入**）、**不按语言筛**、**不取 `q.answer` / `q.analysis`** —— 查不到 → `CSCA_QUESTION_NOT_FOUND(8006)`；<br>⑤ **Controller**：强鉴权（`requireAuthenticatedAppUserId`）+ 路径变量**手工解析**（非数字 → `8005`，理由同第 40 条）+ `recordId`（Query，可选）**亦手工解析**（`?recordId=abc` 同样回 `8005` 而不是 500；空串 / 纯空白按"没传"处理）；<br>⑥ **单测**：`CscaFavoriteServiceImplTest`（5，Mockito：快照列写死 / 重复收藏不覆盖来源与轮次 / 非 CSCA 题**零写入** + `8006` / `count` 为 `null` 兜 `0` / 不打扰记录侧）+ `CscaFavoriteMapperXmlContractTest`（5，SQL 契约：`ON DUPLICATE` 必须存在且**不含** `source` / `practice_record_id` / `exam_record_id` / `section` / `created_*`、`deleted = VALUES(deleted)` 软删复活、INSERT 列清单 13 列一个不少、`countFavorites` 限用户 + `deleted=0`、准入复用 CSCA 范围且不限语言）→ 与既有 14 组共 **130 绿**；`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **五处实现细化 / 差异（文档未明写或落不了地，已同步补注 [3.6.1](#361-收藏favorite) 三层逻辑 + 数据流向，如需回改请说）**：<br>　**a. 🔴 `favoriteCount` 的口径 = 「当前用户已收藏总数」**：文档只给了字段名与示例值（`37`），**未定义范围**。本接口**无题集上下文**，故取 `user_id + deleted = 0` 的**全量计数**（供「我的收藏」角标）；⚠️ 与 [3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card) 的同名字段（**本次题集内**计数）**语义不同** —— 已在 [3.6.1](#361-收藏favorite) 数据流向补注。<br>　**b. `recordId` 只作快照、不做任何校验**：按 §3.6.1 第 8 条第 ⑤ 点「只存快照：不做归属 / 存在性校验」，本实现**不查 `practice_record`**（连"这轮是不是你的"都不查）—— 传别人的轮次 id 也只影响快照值真假，不影响鉴权与结果；**未传 → `practice_record_id` 存 `NULL`**。<br>　**c. `upsertFavorite` 用实体作入参、`deleted` 由实体承载**：[3.6.1](#361-收藏favorite) 第 1 条把 `PUT` / `DELETE` 描述为「**同一套写法**」（只差 `deleted = 0` / `1`），故 mapper 方法写成**一个** `upsertFavorite(QuestionFavorite)`、`deleted` 由 Service 塞入 —— `DELETE` 端点落地时**只需把 `deleted=1` 传进来**，SQL 零改动。<br>　**d. 幂等**：写接口**无 `idempotencyKey` 入参**（文档也未要求）—— 幂等性由唯一键 `uk_user_question` **天然提供**：重复 `PUT` 走 `UPDATE` 分支、结果恒等，离线队列重放安全。<br>　**e. ⚠️ 本组其余两个端点仍未编码**：`DELETE /csca/favorites/{questionId}`（取消收藏）与 `GET /csca/favorites`（收藏列表，含 `subjectTypeMapping` / `source` / `languageVersion` / `withAnswerState` / 分页）**尚未实现** —— 后者要 join `question` / `exam_paper`（表不存语言列）并按 `updated_time` 倒序分页。 |

| **57** | **新建 `DELETE /csca/favorites/{questionId}` 取消收藏**（2026-10-14 用户口径：「根据文档写DELETE /csca/favorites/{questionId}接口」） | 该端点此前**未编码**（[3.6.1](#361-收藏favorite) 只有设计）；同日 `PUT` 刚落（第 56 条），其 c 项已预留「`deleted` 由实体承载 → `DELETE` 落地只需传 1、**SQL 零改动**」；它是答题页 ★「已取消收藏」/ 答题卡 ★ 的落库点 | ✅ **已按 [3.6.1](#361-收藏favorite) 实现**：<br>① **改动仅 3 处 .java**（**Mapper / XML / DTO 零改动**）：`service/CscaFavoriteService` 加 `remove(userId, questionId, recordId)`；`service/impl/CscaFavoriteServiceImpl` 抽出私有 **`upsertState(userId, questionId, recordId, deleted)`**，`add` 传 `0`、`remove` 传 `1`；`controller/CscaFavoriteController` 加 `@DeleteMapping("/favorites/{questionId}")`；<br>② 🔴 **写侧复用 `CscaFavoriteMapper#upsertFavorite`**（第 56 条已写成 `deleted = VALUES(deleted)`）—— 一条 `INSERT … ON DUPLICATE KEY UPDATE` **同服 PUT / DELETE**：`ON DUPLICATE` 仍**只刷** `deleted` / `update_by` / `updated_time`，**不含** `source` / `practice_record_id` / `exam_record_id` / `section` / `section_mapping` / `created_*` → **取消不覆盖首次收藏的来源、轮次、科目与首次时间**；<br>③ 🔴 **软删 + 复活**：`deleted` 置 1（**行保留、不物理删**），再次 `PUT` 即复活同一行 → 唯一键恒成立；<br>④ **准入同样校验**：`selectFavoriteAdmission` 查不到 → `CSCA_QUESTION_NOT_FOUND(8006)`（**取消也不写非 CSCA 的脏行**）；<br>⑤ **回执**：`favorite = false`（最终态）+ `favoriteCount`（同 `PUT` 口径 = 当前用户全量 `deleted = 0` 计数）；Controller 侧强鉴权 + 路径变量 / `recordId` **手工解析**（同 `PUT`，非数字 → `8005`）；<br>⑥ **单测**：`CscaFavoriteServiceImplTest` 由 5 扩到 **9**（补 4 例：取消写 `deleted=1` / `favorite=false` 且快照列与 PUT 一致、非 CSCA 题**零写入** + `8006`、未收藏直接取消**仍幂等**（补一行 `deleted=1` 而非插第二行 / 无操作）、`count` 为 `null` 兜 `0`）→ 与既有 14 组共 **134 绿**；`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **两处实现细化 / 差异（文档未明写，已同步补注 [3.6.1](#361-收藏favorite) 编码进度与三层逻辑表，如需回改请说）**：<br>　**a. 🔴 取消收藏也发 `INSERT`（而非纯 `UPDATE`）**：[3.6.1](#361-收藏favorite) 第 1 条明写「`PUT` / `DELETE` **同一套写法**、都走 `INSERT … ON DUPLICATE KEY UPDATE`」，故「**未收藏直接取消**」会**补一行 `deleted=1`**（不是无操作）—— 与文档「`DELETE` 未收藏 → 返回 `favorite=false`」一致；若希望「未收藏取消**不落任何行**」需改成先查后写（多一次往返、并发下反而不如现在安全），**当前按文档**。<br>　**b. ⚠️ 准入校验的副作用**：题若事后被**软删 / 移出 CSCA**，则对该题 `DELETE` 会回 `8006`（**用户将无法取消这条历史收藏**）。这是 [3.6.1](#361-收藏favorite) 业务逻辑第 2 条（`PUT` / `DELETE` 共用段落）的直接后果 —— 若产品上要求「已收藏的题即使下架也能取消」，可把准入**仅保留在 `PUT`**（`DELETE` 直接 upsert）；**当前按文档**（准入对两者都生效）。<br>　**c. 剩余**：本组 `GET /csca/favorites`（收藏列表：`subjectTypeMapping` / `source` / `languageVersion` / `withAnswerState` + 分页，要 join `question` / `exam_paper`）**仍未编码**。 |

| **58** | **收藏接口 `recordId` 由可选改必填**（2026-10-14 用户口径：「recordId改为必填」） | [3.6.1](#361-收藏favorite) 的 `recordId` 原设计为 **Query 可选**（第 50 条 ④：「练习中收藏**建议带上**；复习页 / 无轮次上下文**可不传**」），故 `practice_record_id` 允许 `NULL`；但收藏动作**事实上总是发生在某一轮练习的上下文里**（答题页 ★ / 答题卡 ★ 都挂在某条 `practice_record` 上），可选参数让前端多一条「传不传都行」的分支、也让快照列出现 `NULL` 空洞 | ✅ **已改（文档 + 代码 + 测试一体）**：<br>① **文档**：[3.6.1](#361-收藏favorite) 入参表 `recordId` 必填列 `否 → **是**`、说明整体改写；业务逻辑第 8 条 ④「复习页收藏（无轮次上下文）→ 留 `NULL`」改为「🔴 **必填 → 恒写** `practice_record_id`，原无轮次形态取消」；数据流向 ① 补 `recordId`；<br>② **代码**：`CscaFavoriteController` 的 `add` / `remove` 由 `parseOptionalId(recordId, …)` 改为 **`parseId(recordId, …)`**；`parseId` 增加 **判空分支**（`null` / 纯空白 → `CSCA_PARAM_OUT_OF_RANGE(8005)`，文案「不能为空」）；**删除 `parseOptionalId`**（已无调用方）；`CscaFavoriteService` 的 `add` / `remove` javadoc 标必填；<br>③ **测试**：`CscaFavoriteServiceImplTest` 的 4 个「传 `null` 轮次」用例（`keepsFirstSourceAndRecordWhenAlreadyFavorited` / `treatsNullCountAsZero` / `removeOnNeverFavoritedQuestionIsStillIdempotent` / `removeTreatsNullCountAsZero`）**统一改传 `RECORD_ID`**，删掉两处「快照留 null」断言 → 用例数不变、仍 **134 绿**；<br>④ **失败口径**：`recordId` 缺失 / 空串 / 非数字 → **`8005`**（**与路径变量同一处理**）—— ⚠️ **刻意不用 `@RequestParam(required = true)`**：common 的 `MissingServletRequestParameterException` 处理器回的是**通用** `PARAM_ERROR`（且 HTTP `200`），**不是**文档要求的 `CSCA_*` 码（§0.5）；故两处参数都保留 `required = false` + 手工解析。<br>⚠️ **三处已知影响**：<br>　**a. 🔴 接口签名变严（破坏性变更）**：老前端若在「复习页 / 无轮次上下文」调 `PUT` / `DELETE` 收藏而不带 `recordId`，升级后将收 `8005`（**必须补 `recordId`**）。本组接口**尚未对外联调**（无生产调用方），当前变更无损。<br>　**b. 快照列 `practice_record_id` 仍可空（DB / 实体 / Mapper 零改动）**：只收紧了**接口入参** —— 因为 `source='exam'` 链路将来写 `exam_record_id`、`practice_record_id` 仍须可空（第 50 条 ④⑤「按 `source` 二选一」）。<br>　**c.** `recordId` 仍是**纯快照、不做归属 / 存在性校验**（第 56 条 b 项）—— 必填只约束「必须有值」，**不改变**「不查 `practice_record`」的口径（传别人的轮次 id 也只影响快照真假）。 |

| **59** | **新建 `GET /csca/favorites` 我的收藏列表**（2026-10-14 用户口径：「GET /csca/favorite按照文档写这个接口」—— 用户写的单数 `favorite`，文档实为复数 `favorites`，按文档实现） | 该端点此前**未编码**（[3.6.1](#361-收藏favorite) 只有设计，第 56 / 57 条只落了 `PUT` / `DELETE`）；它是「换设备登录后把 ★ 取回」的唯一读入口（§3.6.1 业务逻辑第 4 条），也是原型「我的收藏」页的**预留**落点；它把本组从「能收藏但看不见」补成闭环 | ✅ **已按 [3.6.1](#361-收藏favorite) 实现**：<br>① **新增 DTO 4 个**：`dto/CscaFavoriteQuery`（六个入参全可选）、`dto/CscaFavoriteListRow extends CscaQuestionRow`（**题面字段 + 收藏 5 列**一次承载）、`dto/CscaFavoriteItem`（列表元素；静态工厂 `of(question, favorite, answered, isCorrect)` 是唯一的字段映射点）、`dto/CscaFavoritesResponse`（`total` / `page` / `pageSize` / `questions`）；<br>② 🔴 **抽出 `support/CscaQuestionAssembler`（`@Component`）**：把 `CscaQuestionQueryServiceImpl` 的私有 `toResponse` / `loadGroups` / `resolveGroup` / `optionsOf` / `Groups` **整体上移**为公共组件 —— 取题列表 / 单题详情 / **收藏列表**三处**共用同一份题面装配**（`layout` 直传 + 三字段 + 选项保序 + 共材料兜底 + `typeId` 映射），避免「同构」要求被三份实现慢慢写歪。**这是本轮唯一的既有代码重构**（`CscaQuestionQueryServiceImpl` 删 5 个私有成员、改 2 处调用，**行为不变**）；<br>③ **读侧 SQL 一条拿全**：`CscaFavoriteMapper#selectFavoritePage` 用 `question_favorite ⋈ question ⋈ exam_paper` 三表 join，**题面与收藏字段一次取回**（不必「先查收藏、再按 id 批量补题面」）；列清单**跨 namespace 复用** `CscaQuestionMapper.cscaQuestionColumns`（`<include refid="com.hsktreasure.practice.csca.mapper.CscaQuestionMapper.cscaQuestionColumns"/>`）→ 与取题接口读的是同一批列；⚠️ `f.section AS favorite_section` **必须起别名**（它与 `q.section`（题的部分号）同名不同义，撞名会映射错字段）；<br>④ 🔴 **计数与分页复用同一份筛选片段** `<sql id="favoriteListFilters">`（`f.user_id` + `f.deleted = 0` + 三个 `<if>` 可选项，**含语言那个 join**）—— 两处 where 一旦分家，`total` 与「实际能翻到的条数」就会对不上（多算 → 末页回空数组；少算 → 末页被截断）；<br>⑤ **排序** `ORDER BY f.updated_time DESC, f.id DESC`（走 `idx_user_time`；加 `f.id` 兜底保证同一毫秒的两条顺序稳定 → 翻页**不重不漏**）；<br>⑥ **作答态**：新增 `CscaAnswerMapper#selectLatestByQuestionIds` —— `ROW_NUMBER() OVER (PARTITION BY a.question_id ORDER BY a.last_modified_time DESC, a.id DESC)` 取每题**最近一次**作答；🔴 **按 `user_id` 查（跨轮次）而不是按 `practice_record_id`**（收藏不属于任何一轮练习）；<br>⑦ **Controller**：`@GetMapping("/favorites")`（强鉴权）；`page` / `pageSize` / `withAnswerState` **手工解析**（`?page=abc` → `8005` 而不是 `500`，理由同第 40 条）；`withAnswerState` **只认 `true` / `false`**（不用 `Boolean.valueOf`——它会把 `abc` 静默当 `false`）；<br>⑧ **单测**：`CscaFavoriteServiceImplTest` **9 → 19**（补 10 例：计数与分页同筛选 / `offset = (page-1)*pageSize` / 快照列映射 / **恒不传题面快照** / `total=0` 时零查询 / 作答态缺省附带 / 未作答当 `0` 不当错 / `withAnswerState=false` 整段缺席 / 四个非法入参各回各的码 / 空白筛选按没传）+ `CscaFavoriteMapperXmlContractTest` **5 → 10**（补 5 例：三表 join 且不含 `q.answer` / **不 join `practice_answer`** / 排序与 tie-breaker / 分页与计数**共用筛选片段** / 三个 `<if>` 可选且命中快照列 / 不过滤 `q.deleted` / 列表计数 ≠ 写端点计数）+ `CscaAnswerMapperXmlContractTest` **5 → 6**（补 1 例：作答态按用户而非记录 + 分区去重 + `rn = 1` + 限 `SEC_CSCA`）→ CSCA 组共 **150 绿**；`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **七处实现细化 / 差异（文档未明写或自相矛盾，已同步补注 [3.6.1](#361-收藏favorite) 编码进度 / 三层逻辑表 / 数据流向，如需回改请说）**：<br>　**a. 🔴 `languageVersion` 不传 = <u>不过滤</u>（而非「缺省 `chinese`」）**：文档**入参表**写「缺省 `chinese`」，而同节**业务逻辑第 6 条**写「不传即全量」—— 两者自相矛盾（当前只有中文卷时等效）。本实现取**后者**：过滤条件**只在传了才加**。理由：将来英文卷导入后，「不传参数反而静默丢掉英文收藏」比「多回几条」危险得多。**若产品要「缺省只回中文」，改一行即可**（`resolveOptionalLanguage` 的 `null` 分支回 `chinese` 而不是 `null`）。<br>　**b. 🔴 `total` 与分页**同源**（含语言那个 join）**：`total` **不是**「用户全量收藏数」，而是「**符合筛选条件且 join 命中**」的条数；⚠️ 与写端点回执的 `favoriteCount`（`countFavorites`：单表、**不带**筛选、**不 join**）**刻意不同** —— 两者在「传了筛选」或「有题被物理删」时会给出不同的数（已在 XML 与 javadoc 里双向标注「不是同一件事」）。<br>　**c. ⚠️ 题被<u>物理</u>删 → 该收藏从列表消失；被<u>逻辑</u>删则照常显示**：SQL **刻意不过滤** `q.deleted` / 卷侧 `exam_type` —— 收藏是用户自己的历史记录，题事后下架不该让这条收藏凭空消失（与 [3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card)「题被删仍占一格」同一精神）。代价是 inner join 兜不住「行没了」这种情况（那一条会静默消失、且不再计入 `total`，二者一致）。<br>　**d. 三个快照列的口径**：`favoriteTime` 取 **`updated_time`**（最近一次收藏，取消后再收藏会刷新，§3.6.1 第 5 条）；`subjectCode` 取**收藏表的快照列** `f.section`（**不取** `q.subject_type_mapping` 实时值 —— 题若被改科目，历史条目仍显示当初收藏的那一科）；`source` / 两个 `*_record_id` 同理取快照列。<br>　**e. 作答态的口径**：**未作答 → `answered = 0` / `isCorrect = 0`**（与 [3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card) **同口径**：不是 `null`、更不是「答错」）；`withAnswerState = false` 时两字段**整段缺席**（`null`）。<br>　**f. 列表<u>不做</u>逐题准入校验**：写的时候已校验过（第 56 条 ④），且题可能事后下架 —— 列表是「我已经收藏了什么」的真相，不重跑准入。（与 `PUT` / `DELETE` 都要准入形成有意对比。）<br>　**g. 重构既有代码**：`CscaQuestionAssembler` 的抽取动了 `CscaQuestionQueryServiceImpl`（该文件**此前无单测**）—— 属**纯搬移**（方法体逐字未改），靠 `CscaAnswerMapperXmlContractTest#onlyTheAnswerQueriesReadTheStandardAnswer` 等 SQL 契约 + 150 绿兜底。若后续要给「题面装配」补单测，落点就是这个新组件。 |

| **60** | **新建 `GET /csca/wrong-book` 我的错题本列表**（2026-10-14 用户口径：「GET /csca/wrong-book根据文档写这个接口」） | 该端点此前**未编码**（[3.6.2](#362-错题本wrong-book) 只有设计，第 52 条只把支撑表 `question_wrong` 建到 TEST）；它是「我的 → 错题本」列表页与**角标数**的唯一数据源（业务逻辑第 10 条），也是 [3.6.2](#362-错题本wrong-book) 三端点里唯一**只读**的一个 —— 写侧（手动移出 / 复习作答）依赖它先把「怎么读」定死 | ✅ **已按 [3.6.2](#362-错题本wrong-book) 实现**：<br>① **新增 DTO 4 个**：`dto/CscaWrongBookQuery`（**四个入参全可选**：`subjectTypeMapping` / `source` / `page` / `pageSize`）、`dto/CscaWrongBookListRow extends CscaQuestionRow`（**题面字段 + 错题 5 列**一次承载）、`dto/CscaWrongBookItem`（列表元素；静态工厂 `of(question, wrong)` 是唯一的字段映射点）、`dto/CscaWrongBookResponse`（`total` / `page` / `pageSize` / **`wrongQuestions`** —— 字段名与收藏的 `questions` 刻意不同，与文档返回 JSON 一致）；<br>② 🔴 **抽出两个共用支撑类**（本轮**仅有的既有代码重构**）：<br>　**a.** `support/CscaListParams` —— 把 `CscaFavoriteServiceImpl` 的私有 `resolveOptionalSubject` / `resolveOptionalSource` / 分页缺省与边界（+ `SOURCE_PRAC` / `SOURCE_EXAM` / `DEFAULT_PAGE` / `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE` 五个常量）**整体上移**；两表镜像（§3.6.2 开头）要求筛选口径完全一致，各写一份必然漂移（「只认 5 个原始科目码」改一边忘一边）。⚠️ `resolveOptionalLanguage`（语言筛）**留在收藏侧** —— 错题本没有这一项；<br>　**b.** `support/CscaRequestParams` —— 把 `CscaFavoriteController` 的私有 `parseId` / `parseInteger` / `parseBoolean` 上移（`parseId` 更名 `parseRequiredId`）。两者都是**纯搬移**，唯一差别是 `CscaListParams` 多一层「分页缺省与边界」的封装；<br>③ **读侧 SQL 一条拿全**：`CscaWrongBookMapper#selectWrongPage` 用 `question_wrong ⋈ question ⋈ exam_paper` 三表 join，**题面与错题字段一次取回**；列清单**跨 namespace 复用** `CscaQuestionMapper.cscaQuestionColumns`（`<include refid="com.hsktreasure.practice.csca.mapper.CscaQuestionMapper.cscaQuestionColumns"/>`）→ 与取题接口读的是同一批列；⚠️ `w.section AS wrong_section` **必须起别名**（它与 `q.section`（题的部分号）同名不同义，撞名会映射错字段）；⚠️ `exam_paper` 的 join **不可省**（列清单含 `p.source AS paper_source`），尽管本组**无语言筛**；<br>④ 🔴 **计数与分页复用同一份筛选片段** `<sql id="wrongBookListFilters">`（`w.user_id` + `w.deleted = 0` + **两个** `<if>` 可选项）—— 两处 where 一旦分家，`total` 与「实际能翻到的条数」就会对不上（多算 → 末页回空数组；少算 → 末页被截断）；<br>⑤ **排序** `ORDER BY w.updated_time DESC, w.id DESC`（走 `idx_user_time`；加 `w.id` 兜底保证同一毫秒的两条顺序稳定 → 翻页**不重不漏**）；<br>⑥ 🔴 **不读 `practice_answer`**（与 [3.6.1](#361-收藏favorite) 收藏列表**最大的结构差异**）：错题本**状态自持** —— 本表即「该用户对该题最近一次判分结果」的物化结果，列表**不需要**任何「最近一次作答」查询。故 `CscaWrongBookServiceImpl` **只注入 2 个依赖**（`CscaWrongBookMapper` + `CscaQuestionAssembler`）、**根本没有** `CscaAnswerMapper`；列表元素**没有** `answered` / `isCorrect` 两个字段；<br>⑦ **Controller**：`@GetMapping("/wrong-book")`（强鉴权）；`page` / `pageSize` 复用 `CscaRequestParams#parseOptionalInteger` **手工解析**（`?page=abc` → `8005` 而不是 `500`，理由同第 40 条）；网关白名单**无需改动**（`/csca/wrong-book` 本就不在白名单）；<br>⑧ **单测**：`CscaWrongBookServiceImplTest`（**7**，Mockito：计数与分页同筛选 / `offset = (page-1)*pageSize` / 快照列映射 / **恒不传题面快照** / `total=0` 时零查询 / 四个非法入参各回各的码 / 空白筛选按没传）+ `CscaWrongBookMapperXmlContractTest`（**5**，SQL 契约：三表 join 且不含 `q.answer` / **不 join `practice_answer`** / 排序与 tie-breaker / 分页与计数**共用筛选片段** / **只有两个 `<if>` 且无语言筛** / 不过滤 `q.deleted`）+ `CscaListParamsTest`（**7**）+ `CscaRequestParamsTest`（**3**）→ CSCA 组 **150 → 172 绿**（新增 22 例）；`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **六处实现细化 / 差异（文档未明写或落不了地，已同步补注 [3.6.2](#362-错题本wrong-book) 编码进度 / 三层逻辑表 / 数据流向，如需回改请说）**：<br>　**a. `total` 与分页**同源**（含 join）**：`total` **不是**「用户全量错题数」，而是「**符合筛选条件且 join 命中**」的条数 —— 与 [3.6.1](#361-收藏favorite) 第 59 条 b 项**完全同口径**。⚠️ **不传筛选时它才等于「我的」页错题本角标数**（业务逻辑第 10 条）；⚠️ 与写端点回执的 `wrongCount`（`DELETE` / 复习作答响应：单表、**不带**筛选、**不 join**）**刻意不同** —— 待写端点落地时另加查询方法，**不要与本方法合并**（已在 `CscaWrongBookMapper#countWrongBook` javadoc 里标注）。<br>　**b. ⚠️ 题被<u>物理</u>删 → 该错题从列表消失；被<u>逻辑</u>删则照常显示**：SQL **刻意不过滤** `q.deleted` / 卷侧 `exam_type` —— 错题本是用户自己的历史记录，题事后下架不该让这条错题凭空消失（与收藏列表同一精神）。代价是 inner join 兜不住「行没了」这种情况（那一条静默消失、且不再计入 `total`，二者一致）。<br>　**c. 两个快照列的口径**：`wrongTime` 取 **`updated_time`**（「最近一次收录 / 状态变更时间」，列表按它倒序 —— 与收藏的 `favoriteTime` 同一取法）；`subjectCode` 取**错题表的快照列** `w.section`（**不取** `q.subject_type_mapping` 实时值）；`source` / 两个 `*_record_id` 同理取快照列。⚠️ 因本组**尚无写侧**，TEST 库 `question_wrong` 为空表 → 当前只能验证「空列表」路径（`total = 0`）。<br>　**d. 🔴 只有两个筛选项（<u>没有</u>语言筛）**：与 [3.6.1](#361-收藏favorite) 的 `favoriteListFilters`（三个 `<if>`）刻意不同 —— 错题表同收藏**不存语言列**，且原型错题本只有「科目 + 来源」两个筛选（第 9 条）；`CscaWrongBookMapperXmlContractTest` 用「`<if>` 计数恰为 2」+「筛选片段不含 `language_version`」把这一点钉死，防止后人「顺手对齐收藏」补上语言筛。<br>　**e. 列表<u>不做</u>逐题准入校验**：与收藏列表同口径（收录时已校验过；列表是「我已经错在哪」的真相，不重跑准入）。<br>　**f. 🔴 重构既有代码**：`CscaListParams` / `CscaRequestParams` 的抽取动了**收藏侧已定稿**的两个文件（`CscaFavoriteServiceImpl` 删 3 个私有方法 + 3 个常量、`CscaFavoriteController` 删 3 个私有方法）—— 属**纯搬移**（方法体逐字未改），靠既有 `CscaFavoriteServiceImplTest`（19 例，黑盒回调）**零改动通过** + 172 绿兜底验证。⚠️ `CscaFavoriteController` 是**无单测**的（项目无接口级测试）；`CscaRequestParamsTest`（3 例）正是为补上这层覆盖而新增。<br>　**g. 剩余**：本组 `DELETE /csca/wrong-book/{questionId}`（手动移出，幂等）与 `POST /csca/wrong-book/{questionId}/answer`（复习作答：判分 + 同步错题本）**仍未编码** —— ① 写侧 upsert 可直接复用收藏的写法（`INSERT … ON DUPLICATE KEY UPDATE`，`deleted` 传 1）；② 复习作答的响应 `inWrongBook` / `wrongCount` 与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) `immediate=true` **同构**（第 44 条）；③ 三处「同步错题本」的载荷点（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条 / [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 第 6 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条）**仍待接线**（表已就绪，只差代码落点）。 |

| **61** | **新建 `DELETE` / `POST /csca/wrong-book/{questionId}`，并接线「答错自动收录 / 答对自动移出」**（2026-10-14 用户口径：「我发现答题错了不会自动加入错题本，在错题本答对后可以自动移出错题本」；⚠️ 其中「答对自动移出」已被 2026-10-19 的**第 62 条取消**） | 本组写侧此前**未编码**（[3.6.2](#362-错题本wrong-book) 只有设计）；三处作答链路（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条 / [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 第 6 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条）**只留了注释落点**—— 于是「判错了却不进错题本、错题本永远为空」，而这正是错题本的**唯一写入来源**（除手动移出外）。补上后：**本模块 16 个端点全部编码** | ✅ **已按 [3.6.2](#362-错题本wrong-book) 实现**：<br>① **新增 DTO 4 个**：`dto/CscaWrongBookRemoveResponse`（`questionId` / `inWrongBook` / `wrongCount`）、`dto/CscaWrongBookAnswerRequest`（`{answer}`，与 [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 同格式）、`dto/CscaWrongBookAnswerResponse`（与 3.3.1 `immediate=true` **同构**的 5 个判分字段 + `inWrongBook` / `wrongCount`；🔴 **不含** `points` / `answeredCount` / `lastSavedTime` —— 复习作答不落作答表，与「记录」相关的字段一个都不出现）、`dto/CscaWrongBookSyncItem`（**内部传参** record：`questionId` / `isCorrect` 三态 / `section`，不出现在任何 JSON 里）；<br>② **`CscaWrongBookMapper` 扩 4 个方法**（+`.xml`）：`upsertWrongs`（批量幂等 upsert，判错收录 / 手动移出共用；`ON DUPLICATE` **刻意只刷** `deleted` / `update_by` / `updated_time`）、`markRemoved`（批量软删**在册**行）、`countWrong`（**单表**在册总数）、`existsInWrongBook`（单题在册判定）；<br>③ **Service 加 3 个入口**：`remove`（手动移出）+ `reviewAnswer`（复习作答）+ `syncAfterGrade`（**自动收录 / 自动移出**，含单题便捷重载）；<br>④ **Controller 加 2 个端点**：`@DeleteMapping("/wrong-book/{questionId}")` + `@PostMapping("/wrong-book/{questionId}/answer")`（均强鉴权；路径变量走 `CscaRequestParams#parseRequiredId`；Body 用 `required=false` 接、由 Service 判 `answer` 必填）；<br>⑤ 🔴 **三处作答链路接线**：`CscaAnswerServiceImpl#save` 第 ⑦ 步（单题，带 `record.getId()` 作轮次快照）、`CscaAnswerServiceImpl#batchReport` 第 ⑨ 步（**只对真正写入的 winners**）、`CscaSubmissionServiceImpl#submit` 第 ⑧ 步（新增 `RegradeSummary.flips` 收集「判分三态发生变化的已答行」，**不翻转时一次同步都不发**）；<br>⑥ **单测**：`CscaWrongBookServiceImplTest` **7 → 17**（补 10 例：移出准入 8006 / 移出写 `deleted=1` + 回执 / 复习作答必填 8005 / 判错收录 + 实时答案 + 无轮次 / 判对移出且不回查 / 未评分维持原状 / 复习作答准入 8006 / 混合批一次收录一次移出 / 空与全未评分不碰库 / 单题重载委托批量）+ `CscaWrongBookMapperXmlContractTest` **5 → 9**（补 4 例：upsert 冻结首次快照 / `markRemoved` 只 UPDATE 不插入 / `countWrong` 单表 / `existsInWrongBook` 作用域）+ 新建 `CscaSaveAnswerServiceImplTest`（2 例：逐题作答同步带本轮 recordId / 参数非法不碰库）+ `CscaBatchAnswerServiceImplTest` 补 1 例（只同步写入项）+ `CscaSubmitServiceImplTest` 补 2 例（翻转才同步 / 不翻转不同步）→ CSCA 组 **172 → 191 绿**（新增 19 例）；`mvn -pl practice-service -am test -Dtest='Csca*Test'` → **BUILD SUCCESS**（JDK17）。<br>⚠️ **实现细化 / 差异（文档未明写，已同步补注 [3.6.2](#362-错题本wrong-book) 编码进度 / 三层逻辑表 / 数据流向与三处同步条目，如需回改请说）**：<br>　**a. 🔴 判对「自动移出」<u>只 UPDATE、不插新行</u>**（`markRemoved`），而**手动移出**走 `upsertWrongs`（未收录时插一行 `deleted = 1`，保幂等，第 2 条）—— 两者**刻意不同**：手动移出是低频用户动作，自动移出是**高频**判分附随动作；若自动移出也用 upsert，「练对了但从没答错」的题会在表里堆满 `deleted = 1` 的空行（用户答对的题远多于答错的）。本方法的语义因此是「**确保它不在错题本里**」，本来就没收录的题 0 行受影响 —— 正是「答对无操作」。<br>　**b. 🔴 `syncAfterGrade` 是三处链路的<u>唯一同步出口</u>**，输出与接口返回体<b>无关</b>（附随动作）；未评分（`is_correct = 0`）**既不移出也不收录**（第 1 条），这一分流只在 Service 内实现一次，避免三处各写一套。<br>　**c. ⚠️ 交卷兜底路径的科目快照传 `null`**：作答行（`practice_answer`）不落科目列，其 `question_snapshot.section` 是「卷内部分号」**不是**科目码 —— 为一行罕见兜底（重判翻转）再查一次题库不值当。仅影响「**从未收录过 + 交卷重判才翻转成错**」这一极罕见组合，且只影响该条在「按科目筛选」时的可见性（`section` 只在 INSERT 写、重复收录不覆盖，故已收录过的题不受影响）。<br>　**d. 复习作答的判分基准 = 实时 `question.answer`**（第 7 条），故复用**作答链路**的 `selectForAnswer`（准入条件相同 + 一次拿齐标准答案 / 解析 / 分值），**不**复用只取两列的 `selectFavoriteAdmission`（那个留给收藏与手动移出）。<br>　**e. ⚠️ 计时 / 统计一律不涉及**：复习作答**不落 `practice_answer`**（第 8 条）—— `CscaWrongBookServiceImpl` 因此**不注入** `PracticeRecordMapper` / `CscaAnswerMapper`，与列表读侧「不读作答表」的口径一脉相承。<br>　**f. 手动移出仍要过准入**（`exam_type=2 AND version='CSCA'`，否则 `8006`）—— 与收藏 `DELETE` 同一口径：既挡住「HSK 的题不该出现在 CSCA 错题本」，也挡住「移出时往表里写脏行」。另：手动移出**不是永久拉黑**，该题后续再被判错会复活（第 1 条）。<br>　**g. 本题组仍无 DB 实跑**：`question_wrong` **TEST 已建、⚠️ PROD 未建**（文末「附 6」），故接口层联调（含三处自动同步的落库效果）**尚未在 TEST 库跑过**；PROD 上线前必须先建表，否则所有写路径报 `Table doesn't exist`。 |
| **62** | **取消「答对自动移出」，错题本改为「只进不出」**（2026-10-19 用户口径：「我的意思是把错题本改成答对了不自动移出错题本」） | 第 61 条落地的是「判错收录 / **判对自动移出**」—— 与原型（「答对不自动移除」）相反：用户在错题复习页**答对一次就把这道错题弄丢了**，等于错题本无法用来「反复练直到记住」。且判对是高频事件，每次都要多跑一轮 UPDATE。 | ✅ **已改（代码 + 文档）**：<br>① **`CscaWrongBookServiceImpl#syncAfterGrade`**：删除 `CORRECT` 分支 → 「判错 → `upsertWrongs(deleted=0)`；**判对 / 未评分 → 不动**（不写库、不刷 `updated_time`）」；它仍是三处作答链路的**唯一同步出口**；<br>② **删除 `CscaWrongBookMapper#markRemoved`**（接口 + XML + 契约用例）—— 它唯一的调用方就是「判对自动移出」；新增 XML 契约守卫 `xmlHasNoAutomaticRemovalStatement` 防回归；<br>③ **`resolveInWrongBook`**：判对不再直接回 `false`（那会让前端以为题已移出），改为**回查 `existsInWrongBook`** —— 与「未评分」同一处理；判错仍直接回 `true`（必然收录，省一次查询）；<br>④ **交卷路径**（`CscaSubmissionServiceImpl` 第 ⑧ 步）：`RegradeSummary.flips` 保留（仍是「判分三态翻转」的完整集合），但**只挑 `isCorrect = 2`（翻成错）的**调同步 —— 全判对时一次同步都不发；<br>⑤ **测试口径翻转**：`reviewAnswerMovesOutWhenCorrect` → `reviewAnswerKeepsTheQuestionInBookWhenCorrect`（断言 `inWrongBook = true` + **零写入**）、`syncAfterGradeCollectsWrongAndRemovesCorrectInOneShot` → `syncAfterGradeOnlyCollectsWrongAndLeavesCorrectAlone`、`CscaSubmitServiceImplTest` 拆成「翻成错才同步」+「翻成对不同步」两例 → CSCA 组 **191 → 192 绿**，`BUILD SUCCESS`；<br>⑥ **文档**：状态行 / [2.1](#21-端点清单) 第 16 号 / [3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条 / [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 第 6 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条（+ 各自涉及表）/ [3.6.2](#362-错题本wrong-book) 引子 + 第 1 条 + 三层逻辑 + 数据流向，均已改为新口径；[4.3](#43-待确认事项) 第 15 条与 [4.4](#44-文档与实现的差异) 第 32 / 48 / 61 条的旧表述已就近标注「被第 62 条取代」。<br>⚠️ **行为差异（须知）**：<br>　**a. 错题本从此只增不减**（除用户手动 `DELETE`）—— 一道题一旦被判错收录，就会一直留在列表里，直到用户自己移出。这是「反复练同一道错题」的产品语义，但也意味着**错题本可能越用越长**（无自动清理机制）。<br>　**b. `wrongTime` 语义微变**：它是 `updated_time`，此前「答对」也会刷新它；现在只有**首次收录 / 手动移出 / 移出后再收录**会刷新 → 列表排序更稳定（不会因复习答对把老错题顶到最前）。<br>　**c. 复习作答回执的 `inWrongBook`** 现在对「答对」也要多查一次库（`existsInWrongBook`）—— 单题一次 `COUNT(*)`（走 `uk_user_question`），可忽略。<br>　**d. ⚠️ 历史数据不回补**：2026-10-14 ~ 10-19 期间因「判对自动移出」而被软删（`deleted = 1`）的行**保持原样**、不会自动复活（它们与「用户手动移出」的行在库里完全一样，无法区分）。如需回补需人工按 `updated_time` 区间评估，**本次不做**。<br>　**e. 考试侧 `source=exam` 仍待接入**（第 32 条），与本条无关。 |

| **63** | **错题本列表新增「错题时间」筛选**（2026-10-19 用户口径：「/csca/wrong-book 新增时间段查询筛选条件，三天内、一周内、一个月内、自定义时间，是不是可以直接做一个自定义的，其他选项让前端固定字段」） | 第 60 条落地时列表只有 **科目 / 来源** 两个筛选，没有时间维度 —— 错题攒多之后无法只看「最近错的」。 | ✅ **按用户判断落地：只做自定义区间**（`startTime` / `endTime`），三天内 / 一周内 / 一个月内交给前端算（用户原话「其他选项让前端固定字段」）。<br>① **入参**：`GET /csca/wrong-book` 新增 `startTime` / `endTime` 两个**可选** Query 参数，**毫秒时间戳、闭区间** `[start, end]`（`>=` / `<=`）；单边合法；`start > end` → `8005`；非数字 → `8005`（`CscaRequestParams#parseOptionalLong`，**不能复用 `Integer` 版** —— 13 位毫秒必抛 `NumberFormatException`）；<br>② **命中列** `question_wrong.updated_time` —— 与**排序**、响应体 **`wrongTime`** 同一列（筛的 / 排的 / 显示的是同一个时间）；走 `idx_user_time(user_id, deleted, updated_time)`，**不新建索引**；<br>③ 🔴 **不加 `timeRange=3d/7d/30d` 枚举**：那只是前端快捷按钮，由前端按**用户本地时区**算 `endTime = now`、`startTime = endTime − N × 86400000`，与「自定义起止日期」**同一条链路**。理由：**时区**只有客户端知道（服务器按 UTC 算「三天前」会偏几小时）、新增档位不必改后端发版、前端不必写两套请求；<br>④ **代码**：`CscaWrongBookQuery` +2 字段；`CscaListParams#resolveTimeRange` 新增（返回 `TimeRange(startTime, endTime)`，**只有这一份校验**）；`CscaRequestParams#parseOptionalLong` 新增；`CscaWrongBookMapper#selectWrongPage` / `#countWrongBook` 各 +2 参数（**两个查询必须收同一份区间**，否则 `total` 与可翻页数对不上）；XML `wrongBookListFilters` +2 个 `<if>`（`&gt;=` / `&lt;=`，**不得出现 `NOW()` / `INTERVAL`** 这类服务器侧相对时间）；`CscaWrongBookController#list` +2 入参；<br>⑤ **测试**：`CscaListParamsTest` +2（区间可选 / 反序 `8005`）、`CscaRequestParamsTest` +1（`parseOptionalLong` 钉住「13 位毫秒不能走 Integer」）、`CscaWrongBookMapperXmlContractTest` +1（闭区间 + 禁相对时间；`<if>` 计数 2 → 4）、`CscaWrongBookServiceImplTest` +3（同一区间传给计数与分页 / 单边合法 / 反序不碰库）→ CSCA 组 **192 → 199 绿**，`BUILD SUCCESS`（49.3s）；<br>⑥ **文档**：[3.6.2](#362-错题本wrong-book) 接口用处 / 入参表（+ 取舍说明）/ 新增业务逻辑**第 12 条** / 三层逻辑 / 数据流向。<br>⚠️ **前端须知**：约定单位是**毫秒**；误传 **10 位秒级**值**不报错、只筛出空结果**（后端不猜单位）。<br>📌 **收藏列表当时未加**（用户只提错题本）—— **同日已由第 64 条补上**，两表复用同一份 `CscaListParams#resolveTimeRange`。 |

| **64** | **收藏列表同步加上「收藏时间」筛选**（2026-10-19 用户口径：「收藏也加上」） | 第 63 条只给错题本加了时间筛，收藏列表仍只有科目 / 来源 / 语言三个筛选 —— 收藏攒多之后同样无法只看「最近收藏的」；两表 `updated_time` 语义相同（排序键 = 展示时间），没有不加的理由。 | ✅ **完全复用第 63 条的口径，不新增任何设计**：<br>① **入参**：`GET /csca/favorites` 新增 `startTime` / `endTime`（**可选、毫秒、闭区间**）；单边合法；`start > end` → `8005`；非数字 → `8005`（同走 `CscaRequestParams#parseOptionalLong`）；<br>② **命中列** `question_favorite.updated_time` —— 与 `ORDER BY f.updated_time DESC`、响应体 **`favoriteTime`** 同一列；走 `idx_user_time(user_id, deleted, updated_time)` 第三列，**不新建索引**；<br>③ 🔴 **仍然不加 `3d/7d/30d` 枚举**：理由与第 63 条同（时区只有客户端知道 / 新增档位不发版 / 快捷按钮与自定义区间同一条链路）；<br>④ **代码**：`CscaFavoriteQuery` +2 字段；`CscaFavoriteMapper#selectFavoritePage` / `#countFavoritePage` 各 +2 参数（**同一份区间**）；XML `favoriteListFilters` +2 个 `<if>`（`&gt;=` / `&lt;=`，禁 `NOW()` / `INTERVAL`，`<if>` 计数 3 → 5）；`CscaFavoriteServiceImpl#list` 解析并透传；`CscaFavoriteController#list` +2 入参；`CscaListParams` 的 `resolveTimeRange` / `TimeRange` 由「错题本专用」改为**两边共用**（注释同步）；<br>⑤ **测试**：`CscaFavoriteServiceImplTest` +3（同一区间传给计数与分页 / 单边合法 / 反序 `8005` 且不碰库）、`CscaFavoriteMapperXmlContractTest` +1（闭区间 + 禁相对时间 + 与排序 / 展示同列；`<if>` 3 → 5）→ CSCA 组 **199 → 203 绿**，`BUILD SUCCESS`（48.6s）；<br>⑥ **文档**：[3.6.1](#361-收藏favorite) 入参表 / 新增业务逻辑**第 9 条** / 三层逻辑 Mapper 行 / 数据流向 ①②、§2.1 第 13 号。<br>⚠️ **与 `withAnswerState` 无关**：作答态取「最近一次作答」，其时间可能落在区间之外（另一维度，不参与筛选）。<br>⚠️ **前端须知**同第 63 条：单位是**毫秒**，误传 10 位秒级值只筛出空结果、不报错。 |

| **65** | **收藏 / 错题本列表新增「排序方向」**（2026-10-19 用户口径：「那按时间升序降序是后端实现还是前端实现？」→「加上吧」） | 第 60 / 59 条落地时两个列表的排序都是**硬编码 `updated_time DESC, id DESC`**，前端无法选「最早在前」。回答用户的问题：**排序只能在后端** —— 列表带 `LIMIT / OFFSET` 分页，前端排序只能排到「本次下发的那一页」，翻到第 2 页整体顺序即错（跨页排序只有 SQL 能做）；且前端拿不到全量数据（错题本可能上千条）。 | ✅ **两端点同口径落地**：<br>① **入参**：`GET /csca/favorites` 与 `GET /csca/wrong-book` 各新增 `order`（**可选**），只认 `asc` / `desc`（**忽略大小写**），**不传 / 空白 = `desc`**（保持原行为）；**非法 → `8005`，不静默退回缺省**（否则前端会以为自己传的排序生效了）；<br>② 🔴 **只切方向、不切列**：排序键恒为 `updated_time`（= 响应体 `favoriteTime` / `wrongTime` = 时间筛命中列）。**不开放「按科目 / 按题号排」** —— `idx_user_time(user_id, deleted, updated_time)` 只覆盖这一列，每多一种排序列就多一个索引；<br>③ 🔴 **`id` 兜底必须与 `updated_time` 同向**（`ASC` 配 `id ASC`、`DESC` 配 `id DESC`）：混合方向（`updated_time ASC, id DESC`）会让 MySQL 用不上索引有序性 → 退化成 filesort。这条由 XML 契约测试挡住；<br>④ **实现**：`CscaListParams#resolveAscending(String)` 把入参**收敛成 `boolean`**（缺省 `false` = 降序）→ XML 用两个**写死方向**的 `<choose>` 分支，**不用 `${}` 拼串**（`ORDER BY` 后面不能走 `#{}`，而 `${}` 有注入面）；<br>⑤ **`count` 不吃这个参数**（`countFavoritePage` / `countWrongBook` 签名不变）：排序不影响条数，多传一个参数只是多一处两方偏离的机会；<br>⑥ **代码**：`CscaFavoriteQuery` / `CscaWrongBookQuery` 各 +`String order`；两个 Mapper 的 `selectXxxPage` 各 +`@Param("ascending") boolean`（放在 `endTime` 之后、`limit` 之前）；两个 XML 的 `ORDER BY` 改为 `<choose>`；两个 Controller 各 +1 个 `@RequestParam`（**保持原文、不在 Controller 校验** —— `order` 是控制字不是数据值，与 `source` 的大小写敏感刻意不同）；两个 Service 的 `list` 解析并透传；<br>⑦ **测试**：`CscaListParamsTest` +2（缺省 / 双向 / 忽略大小写；非法值 5 种全 `8005`）、`CscaWrongBookServiceImplTest` +3（缺省降序 / 升序透传且计数不吃 / 非法不碰库）、`CscaFavoriteServiceImplTest` +3（同三项，含 `"ASC"` 收敛成 `true`）、两个 XML 契约测试各 +1（两个分支方向 + `id` 同向 + 禁 `${}`）→ CSCA 组 **203 → 213 绿**，`BUILD SUCCESS`（41.0s）；<br>⑧ **文档**：[3.6.1](#361-收藏favorite) 入参表 + 新增业务逻辑**第 10 条**、[3.6.2](#362-错题本wrong-book) 入参表 + 新增业务逻辑**第 13 条**、两处三层逻辑表 / 数据流向。<br>⚠️ **前端须知**：默认就是 `desc`（最近在前），**不传即可**；只有「想看最早的」才传 `order=asc`。⚠️ 时间筛与排序方向**互相独立**（可以「筛三天内 + 升序」）。 |

| **66** | **两张姊妹表加 `language_version` 语言快照列 + 表名加 `csca_` 前缀**（2026-10-19 用户口径：「回滚，要留下这个字段，并且**错题本也要这个字段**，**在表中也加上这字段**，**表名加上前缀 csca_**」） | 此前口径是「**两表都不存语言列**」（[3.6.1](#361-收藏favorite) 旧第 5 条注 / [3.6.2](#362-错题本wrong-book) 旧第 9 条注）：理由是「中 / 英是不同 `question.id`、天然各一行」，故收藏的语言筛要 `JOIN question → exam_paper`，而**错题本连语言筛都没有**。问题：① 每页列表都要为语言多 join 两张表；② 错题本无法按语言筛（导入英文卷后即为缺陷）；③ 表名 `question_favorite` / `question_wrong` 缺模块前缀，与库内其它 `csca` 语义的资产（`exam_type=2`、`6e18` 学科 ID）不成体系。 | ✅ **已落库 + 已编码 + 已改文档**：<br>① **DDL（TEST 已 `--apply`，2026-10-19 12:57）**：`RENAME TABLE question_favorite → csca_question_favorite`、`question_wrong → csca_question_wrong`；每表 `ADD COLUMN language_version VARCHAR(20) NULL COMMENT '语言版本快照（= exam_paper.language_version）' AFTER section`；从 `question → exam_paper` **回填**（两表各 4 行，回填后 NULL 0 行）；<br>② **写入链路打通**：收藏侧用 `CscaFavoriteAdmissionRow#languageVersion`（`selectFavoriteAdmission` 的 SELECT 加 `p.language_version`，**准入一次查询白白带回**）；错题本侧用 `CscaAnswerQuestionRow#languageVersion`（`answerQuestionColumns` 加 `p.language_version`）；`CscaWrongBookSyncItem` 加语言位 → 单题重载同步加一个 `languageVersion` 形参（⚠️ 该重载已于同日**连同「用户答案」一起收敛掉**，见第 69 条）；三处作答链路（[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条 / [3.3.2](#332-post-cscarecordsrecordidanswersbatch) 第 6 条 / [3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条）全部传值；**交卷兜底路径取不到 → 传 `null`**（与 `section` 同一取舍）；<br>③ **读侧改为免 join**：`favoriteListFilters` 的 `<if>` 由 `p.language_version` 改为 `f.language_version`；`wrongBookListFilters` **新增** `w.language_version` 筛（`<if>` 4 → 5）；两个列表**均不传 = 全部语言**（不传 ≠ `chinese`）；<br>④ **共用支撑**：`CscaListParams#resolveOptionalLanguage`（`CSCALanguageVersion.ofCode` + 规范码回写 + 非法 `8002`）—— 两表**唯一一份**语言校验；<br>⑤ **测试**：`CscaWrongBookServiceImplTest` +2（语言透传给计数与分页 / 非法语言 `8002` 且不碰库）、两个 XML 契约测试改为断言 `f.|w. language_version` 且**不得**出现 `p.language_version`（收藏侧）→ CSCA 组 **213 → 215 绿**，`BUILD SUCCESS`（41.8s）；<br>⑥ **文档**：[3.6.1](#361-收藏favorite) 入参表 / 第 5 条 DDL / 第 6 条、[3.6.2](#362-错题本wrong-book) 入参表 / 第 9 条 DDL / **新增第 14 条**、两处涉及表与数据流向、附 5 / 附 6、[4.3](#43-待确认事项) 第 10 / 15 条。<br>⚠️ **PROD 未建表** → 生产上线时**直接按新表名 + 新 DDL 建表**（无需改名），且 `language_version` 列**必须一起建**（否则 `Unknown column`）。<br>⚠️ **历史行**：TEST 两表存量行已全量回填（`chinese`）；PROD 因为是全新表，写侧自动带值，无回填问题。<br>⚠️ **交卷路径写入的 `language_version` 为 `NULL`** → 这类行**不被任何语言筛命中**（不传筛仍可见），口径登记于第 61 条 c。 |
| **67** | **两张姊妹表删除 `section_mapping` 列**（2026-10-19 用户口径：「两个表的 `section_mapping` 不要了」） | 该列在两表里**恒为 `'SEC_CSCA'`**（建表时按 `practice_answer` 的口径抄过来，为「将来复用同表做 HSK」预留），但：① **没有任何查询用它**（列表筛选走 `section` = 科目码、归属由 `user_id` 决定）；② 唯一键 / 索引都不含它（原 `idx_user_section` 已删，[4.4](#44-文档与实现的差异) 第 47 条）；③ 模块归属现在由**表名前缀 `csca_`** 表达（第 66 条）—— 一个恒值列纯占位。 | ✅ **已落库 + 已编码 + 已改文档**：<br>① **DDL**：两表 `DROP COLUMN section_mapping`（与改名 / 加列**同一批事务**执行，G4 断言「13 列逐列同序、无 `section_mapping`」通过）；<br>② **代码**：删 `CscaFavoriteServiceImpl#SECTION_CSCA` 常量（错题本侧同名常量一并删）→ 写库 builder 改为 `.section(admission.getSubjectTypeMapping()).languageVersion(admission.getLanguageVersion())`；`CscaFavoriteMapper.xml` / `CscaWrongBookMapper.xml` 的 INSERT 列清单去掉 `section_mapping`；两个实体删 `sectionMapping` 字段、加 `languageVersion` 字段；<br>③ **测试**：XML 契约测试的 INSERT 列清单断言改为「含 `language_version`、**不含** `section_mapping`」；`ON DUPLICATE KEY UPDATE` 的「冻结列」断言由 `section_mapping` 改为 `section` + `language_version`；<br>④ **文档**：两处 DDL / 列说明 / 附 5 附 6 全部去掉该列，并加一条警示：「别与 `practice_record.section_mapping` / `practice_answer.section_mapping` 混淆 —— **那两张表混着 HSK 行、该列必须保留**」。<br>⚠️ **回滚代价**：`tmp/_rollback_csca_tables_lang_20261019_125733.sql` 会用**恒值 `'SEC_CSCA'`** 把列加回来（原行的取值就是它，无信息损失）。<br>⚠️ **不要顺手删 `practice_*` 的同名列**：`practice_answer` / `practice_record` 的 `section_mapping` 是**多模块共用列**（HSK 6300+ 行靠它区分），删了会把 HSK 进度算进 CSCA。 |
| **68** | **收藏列表 / 错题本列表返回正确答案（`standardAnswer` / `standardAnswerLabels`）**（2026-10-19 用户口径：「CSCA收藏本需要展示正确答案……」） | 此前 [3.6.1](#361-收藏favorite) 第 3 条 / [3.6.2](#362-错题本wrong-book) 第 4 条把这两个列表也归入「内容接口」，**绝不带答案**。实际使用中它们是**复习入口**：用户点「我的收藏 / 我的错题本」就是要对答案，若每个元素再调一次 `/solution`，一页 20 条 = 20 次请求（N+1）。 | ✅ **已编码 + 已改文档**：<br>① **取法**：只在 `selectFavoritePage` / `selectWrongPage` 两条查询里补 `q.answer AS answer`，**不往 `cscaQuestionColumns` 共享片段里加** —— `GET /csca/questions`（取题列表）**一个字段都没变**，仍不带答案（XML 契约测试新增守卫断言钉住）；<br>② **口径**：与 [3.3.3](#333-get-cscaquestionsquestionidsolution) 完全一致 —— `standardAnswer` 原值直传（不归一化）、`无` / `NULL` / 空白 → `standardAnswer = null` 且 `standardAnswerLabels = []`（复用 `CscaAnswerNormalizer`，不另写一套）；<br>③ **不含 `analysis`**：解析体积大（LaTeX 长文本），仍是 `/solution` 的独家出口；<br>④ **缓存**：[0.6](#06-缓存口径) 的硬约束表加例外行 —— 这两个接口是**强鉴权 + 用户私有数据**，本来就不许缓存，故不存在「公开缓存泄漏答案」的风险；<br>⑤ **测试**：`CscaFavoriteServiceImplTest` / `CscaWrongBookServiceImplTest` 的列表装配用例补 `standardAnswer` / `standardAnswerLabels` 断言，两个 XML 契约测试改为「必须取 `q.answer`、仍不得取 `q.analysis`」。<br>⚠️ 若将来 HSK 侧也要「我的收藏」，**不要**直接把答案塞进 HSK 的内容接口 —— 口径是「**复习类列表可以带答案**」，不是「内容接口可以带答案」。 |
| **69** | **错题本列表返回用户答案快照：`csca_question_wrong` 加 `user_answer` 列**（2026-10-19 用户口径：「……错题本需要展示正确答案和**用户错题收录时的错误答案**」） | 「我错在哪」是错题本的核心信息，但表里**完全没有存**：`practice_answer.answer` 有用户答案，可是 ① 复习作答（[3.6.2](#362-错题本wrong-book) 第 8 条）**根本不写作答表**；② 列表一旦 join `practice_answer`，本组「状态自持、列表不读作答表」的约束就破功；③ 「收录时」是**历史事实**，题库纠错 / 用户重答都不该改写它 → 必须**独立冻结成快照**。 | ✅ **已落库 + 已编码 + 已改文档**：<br>① **DDL（TEST 已 `--apply`，2026-10-19 15:17）**：`ADD COLUMN user_answer TEXT NULL COMMENT '用户答案快照（最近一次判错时的作答原文）' AFTER language_version` → 本表 **14 列**（与收藏表唯一列差异）；回填从 `practice_answer`（`is_correct = 2` 的最近一次，按 `last_modified_time` 取）**7 行 100% 命中**；<br>② **语义**：**最近一次判错**的作答原文（不是首次收录）—— 与 `updated_time`（= 响应体 `wrongTime`）**同频**，否则「时间最新、答案却是几个月前」；<br>③ **写入口径**：`ON DUPLICATE KEY UPDATE user_answer = COALESCE(VALUES(user_answer), user_answer)` —— 判错时**覆盖**、**手动移出（传 `null`）时保留原值**（绝不能把用户答案抹掉）；四条写链路全部带值：[3.3.1](#331-put-cscarecordsrecordidanswersquestionid) 第 7 条（`request.answer`）、[3.3.2](#332-post-cscarecordsrecordidanswersbatch) 第 6 条（`item.answer`）、[3.5.1](#351-post-cscarecordsrecordidsubmit) 第 8 条（`practice_answer.answer`，经 `GradeFlip` 带出）、复习作答（`request.answer`）；<br>④ **代码**：`QuestionWrong` 加 `userAnswer`；`CscaWrongBookSyncItem` 加 `userAnswer` 位（**并删除单题便捷重载** —— 6 个参数（`userId, questionId, isCorrect, section, languageVersion, recordId`）的旧签名已无存在必要，逐题作答改传 `List.of(item)`，与批量 / 交卷同一入口）；`CscaWrongBookListRow` / `CscaWrongBookItem` 加 `userAnswer`；XML 的 `selectWrongPage` 取 `w.user_answer`、`upsertWrongs` 写该列；<br>⑤ **测试**：`CscaWrongBookMapperXmlContractTest` 补「INSERT 含 `user_answer`」+「`ON DUPLICATE` 用 `COALESCE`」两条断言（并盯住其余快照列仍**不得**被覆盖）；四个 Service 测试分别断言「用户答案跟着落库 / 跟着同步」→ CSCA 组 **214 绿**，`BUILD SUCCESS`（49.6s）。<br>⚠️ **历史行可能为 `null`**（2026-10-19 之前收录、且作答表里查不到的行）→ 前端要能容忍缺席；TEST 实测 7/7 全部回填成功。<br>⚠️ **PROD 建表时直接带该列**，无需跑回填脚本。 |
| **70** | **两张姊妹表的 `practice_record_id` + `exam_record_id` 合并为 `record_id`**（2026-10-19 用户口径：「我突然发现好像不需要 practiceRecordId、examRecordId 因为可以根据 source 判断，那直接合成一个 recordId 字段吧，数据库也改」） | 两列本来就**按 `source` 互斥**（`prac` → 只有 `practice_record_id`、`exam` → 只有 `exam_record_id`，恒有一个为 `NULL`），读侧要还原「来源记录」必须自己 `COALESCE`，而 `source` 早已存着这条信息 —— 两列并存等于把同一概念拆成两列、再让每个读点重新拼一遍。（改前实测：TEST 收藏 5 行 / 错题本 7 行，`exam_record_id` **全部为 NULL**） | ✅ **已落库 + 已编码 + 已改文档**：<br>① **DDL（TEST 已 `--apply`，2026-10-19 15:44，两表同批）**：每表 `ADD COLUMN record_id BIGINT NULL COMMENT '来源记录ID（按 source 判定：prac→practice_record.id / exam→exam_record.id）' AFTER source` → `UPDATE … SET record_id = practice_record_id` → `DROP exam_record_id` → `DROP practice_record_id`；删列**前**先断言「`record_id` 与 `practice_record_id` 全行 NULL 安全相等」且「`exam_record_id` 非空行 = 0」，不满足就**拒绝删列**（不赌数据）；收藏表 **13 → 12 列**、错题本 **14 → 13 列**；<br>② **代码**：两个实体（`QuestionFavorite` / `QuestionWrong`）删两字段加 `recordId`；四个 DTO（`CscaFavoriteListRow` / `CscaFavoriteItem` / `CscaWrongBookListRow` / `CscaWrongBookItem`）同步；两个 XML 的 **INSERT 列清单 + SELECT 列清单**同步；三个写点改为 `.recordId(...)`（收藏 upsert 传入参 `recordId`、错题收录传本轮 `recordId`、手动移出传 `null` 保留原值）；<br>③ **测试**：两个 XML 契约测试的「冻结列 / INSERT 必带列」改为 `record_id`，并新增守卫断言「INSERT **不得再出现** `practice_record_id` / `exam_record_id`」；四个 Service 测试改 `getRecordId()` → CSCA 组 **214 绿**，`BUILD SUCCESS`（39.9s）；<br>④ **文档**：[3.6.1](#361-收藏favorite) 入参表 / 返回 JSON / 第 5 条 DDL / 第 8 条、[3.6.2](#362-错题本wrong-book) 返回 JSON / 第 9 条 DDL / 第 11 条、附 5 / 附 6。<br>⚠️ **API 破坏性变更**：列表元素不再有 `practiceRecordId` / `examRecordId`，改为单个 `recordId`（`source='prac'` 时即 `practice_record.id`）—— 前端要同步改字段名。<br>⚠️ **PROD 两表仍未建** → 建表时**直接按 `record_id` 建**，无需跑本合并脚本。<br>⚠️ 与前两轮的口径关系：本条**只动「来源记录」这两列**，`section` / `language_version` / `user_answer` 一概不变。 |

### 4.5 原型 v1.3 对照表
> 原型**交互与落点**的逐条对照见 [0.8](#08-与互动原型的对齐v13)；本节只对比**数据**（原型演示值 ↔ 真实题库）。

| 原型 | 真实库（TEST `xuexitest`） | 处置 |
|---|---|---|
| 科目「**教学**」 | **不存在** | **不实现** |
| 中文 = 单卡 | 文科中文 640 + 理科中文 400 | 服务端按 5 科**原样**给，**客户端也不合并**（2026-10-13 定）—— 原型这张「中文」卡落到前端就是**两张卡**（文科中文 / 理科中文） |
| 总题数 320 / 480 / 360 / 420 | 1040 / 432 / 240 / 192 | 服务端回**实测值**，前端不写死 |
| 每题 4 选项 | 4 / 5 / 6 三种 | 前端自适应 |
| 题型只有「单选题」 | 库中题型名有 **8 种**（单选 / 多选 / 识解汉字 / 选词填空 / 辨析词语 / 选词成段 / 补全语句 / 阅读理解），但**只有「多选」是真多选** | 服务端**映射为 2 值**下发（`SINGLE` 1871 / `MULTI` 33，[4.1](#41-枚举速查) `CscaQuestionTypes`）—— 原型「只有单选题」的演示因此与 `typeId` 口径自洽；前端**按 `layout` 分流渲染题面**、按 `typeId` 决定**单值 / 多值作答** |
| 题面一律"题干 + 选项"（无材料型） | **260 题是共材料题**：110 题「材料与题面分列」+ 150 题「材料即题面（组内共享词池）」 | 服务端下发 **`layout` 三态**（`textChoice` / `passageGroup` / `clozeGroup`，[4.1](#41-枚举速查)），前端**必须按 layout 分流**渲染；`clozeGroup` 的题 **`passage` / `content` 均为 `null`**，题面即 `group.passage` |
| 有 English 题库（`BANK.hx.en`） | **无 `english` 卷** | 语言接口**预留**，数据待导 |
| 答案用下标 `a:1`（0-based） | 库中 `answer` 是 `"B"` / `"A,D"` / 脏值 | 答案出口**原值直传**（labels 只按分隔符切分）；**归一化只用于判分**，见 [4.2](#42-答案归一化cscaanswernormalizer) |
| 收藏存 `localStorage` | **无收藏表** | ✅ **已定**：服务端**新建 `csca_question_favorite` 落库**（2026-10-13，2026-10-19 加 `csca_` 前缀），不再只存本地 —— 见 [4.3](#43-待确认事项) 第 10 条 |
| 错题本存 `localStorage`（`WRONG_BOOK`） | **无错题表** | ✅ **已定**：服务端**新建 `csca_question_wrong` 落库**（2026-10-13，2026-10-19 加 `csca_` 前缀）；✅ 原型「答对不自动移除」**保持不变**（2026-10-19 回退了 10-14 的「答对自动移出」，见 [4.4](#44-文档与实现的差异) 第 62 条）—— 见 [4.3](#43-待确认事项) 第 15 条 |

---

> **附 1：本次侦察脚本**（只读，带 G1 `DATABASE()` / G2 `@@hostname` 闸门）
> `tmp/_recon_csca_all.py`、`tmp/_recon_csca_detail.py`、`tmp/_recon_csca_detail2.py`、`tmp/_recon_csca_tables.py`、`tmp/_recon_csca_fav.py`（科目取值 / 收藏表 / 语言版本）、`tmp/_probe_subject.py`（subject 列取值）、`tmp/_probe_favorite_table.py`（2026-10-14 复核：`question_favorite` / `question_wrong` **均不存在**、`practice_record.question_ids` 列存在）
> 复跑可验证本文所有"实测"数字。
>
> **附 2：`subject_type_mapping` 补数据脚本**（**写库**，2026-10-12 已执行）
> `tmp/_fill_subject_mapping.py` —— 默认 DRY-RUN，加 `--apply` 才写。五闸门齐备：G1 `DATABASE()` / G2 `@@hostname` / G3 改前快照 JSON + 回滚 SQL 先落盘 / G4 事务内回读核对（`CSCA 题 NULL 数 = 0`、`全库非空行数 = 1904`，防误伤 HSK）通过才 `COMMIT` / G5 幂等（重复跑影响 **0 行**）。
> 回滚：`UPDATE exam_paper SET subject_type_mapping=NULL WHERE exam_type=2 AND subject_type='理科中文';` + 对 1904 个 `question.id` 置 `NULL`（具体 id 清单见同目录 `_backup_subject_mapping_*.json` / `_rollback_subject_mapping_*.sql`）。
>
> **附 3：CSCA `layout` 补数据脚本**（**写库**，2026-10-12 已执行，⚠️ **只填了测试库**）
> `tmp/_fill_csca_layout.py`（判定规则不变量验证：`tmp/_verify_layout_rule.py`，**只读**）—— 默认 DRY-RUN，加 `--apply` 才写。五闸门齐备：G1 `DATABASE()` / G2 `@@hostname` / G3 备份 JSON + 回滚 SQL 先落盘 / G4 事务内回读核对（`无 NULL 残留` + `textChoice 1644` / `passageGroup 110` / `clozeGroup 150` + `总数 1904` + **`HSK(exam_type=1) 非空仍 5181`**，防误伤）通过才 `COMMIT` / G5 幂等（重跑待改 **0 行**）。
> 回滚：`tmp/_rollback_csca_layout_*.sql`（对 1904 个 `question.id` 置 `NULL`；**改动前该列原值全部为 `NULL`**，故回滚即"清空 CSCA 的 layout"）。
> ⚠️ **只填了 TEST `8.138.185.11`，PROD `43.99.57.11` 未执行** —— 生产需另行评审后再跑（脚本自身带 `--apply` 开关，直接 `python _fill_csca_layout.py --apply` 即可，但**必须先确认 `HOST` 指向生产**）。
>
> **附 4：`practice_record.question_ids` 加列脚本**（**改表**，2026-10-13 定，✅ **TEST 已执行（2026-10-13 16:10）**、⚠️ **PROD 未执行**）
> `tmp/_ddl_question_ids.py` —— 默认 DRY-RUN，加 `--apply` 才执行。五闸门齐备：G1 `DATABASE()` / G2 `@@hostname` / G3 改前 `SHOW FULL COLUMNS` 快照 + 回滚 SQL 先落盘 / G4 执行后回读核对（列存在 + `COLUMN_TYPE=json` + `IS_NULLABLE=YES` + **HSK 记录不受影响**）通过才 `COMMIT` / G5 幂等（先判列是否已存在，存在则跳过）。
> ```sql
> ALTER TABLE practice_record
>   ADD COLUMN question_ids JSON NULL COMMENT '本次练习题集（自然序 question.id 数组；仅 CSCA 使用，HSK 为 NULL）' AFTER total_questions;
> ```
> 回滚：`ALTER TABLE practice_record DROP COLUMN question_ids;`（⚠️ 回滚会丢掉已写题集，CSCA 记录退回"每次重算题集"的老行为）。
> ⚠️ 该列**可空**，HSK 全部既有行保持 `NULL` → **对 HSK 四条链路零影响**（HSK 取题不读此列）。
>
> ✅ **TEST 执行记录（2026-10-13 16:10）**：`python tmp/_ddl_question_ids.py --apply` 执行通过 —— G1 `xuexitest` / G2 `787e3b0c860c` 通过；G5 幂等判定列不存在；**G3** 改前列快照 `tmp/_backup_practice_record_cols_20261013_161007.json`、回滚 SQL `tmp/_rollback_question_ids_20261013_161007.sql` 已落盘；**G4** 回读：列存在 / `COLUMN_TYPE=json` / `IS_NULLABLE=YES` / 列位置第 17（紧接 `total_questions`）/ 表行数 **882 不变** / 非空行 **0** → `COMMIT`。复核脚本 `tmp/_verify_question_ids_col.py`（只读）同源确认。
>
> **附 5：`csca_question_favorite` 建表**（🆕 **新建表**，2026-10-13 定；✅ **TEST 已建（2026-10-14 11:01）**；🔴 **2026-10-19 改名 + 加 `language_version` + 删 `section_mapping`**、🟡 **15:44 两列合一为 `record_id`**（[4.4](#44-文档与实现的差异) 第 66 / 67 / 70 条）；⚠️ **PROD 未建**）
> DDL 见 [3.6.1 业务逻辑第 5 条](#361-收藏favorite)（**12 列**：`id` / `user_id` / `question_id` / `section` / `language_version` / `source` / `record_id` / `deleted` / `created_by` / `update_by` / `created_time` / `updated_time` + `uk_user_question` / `idx_user_time`；🔴 **无 `section_mapping`**；🟡 **`record_id` 与 `source` 成对**，原 `practice_record_id` / `exam_record_id` 已于 15:44 合并）。
> 建表时**照本模块既有做法配五闸门脚本**（默认 DRY-RUN、加 `--apply` 才执行；✅ **脚本 `tmp/_ddl_question_favorite.py`，TEST 已执行（`python tmp/_ddl_question_favorite.py --apply`）**）：G1 `DATABASE()` / G2 `@@hostname` / G3 改前 `SHOW TABLES` 快照 + 回滚 SQL（`DROP TABLE`）先落盘 / G4 执行后回读核对（表存在 + 13 列类型与可空性 + 3 个索引名（含 `PRIMARY`）+ 引擎 `InnoDB` + 字符集 `utf8mb4_0900_ai_ci` + 行格式 `DYNAMIC` + 空表）通过才 `COMMIT` / G5 幂等（先判表是否已存在，存在则跳过）。
> 🔴 **为什么现在就需要它**：[3.4.2 答题卡](#342-get-cscarecordsrecordidanswer-card) 的 `favorite` / `favoriteCount` **已编码**（[4.4](#44-文档与实现的差异) 第 46 条），建表前该接口会在这条 SQL 上失败（TEST 已于 2026-10-14 补建，见 [4.4](#44-文档与实现的差异) 第 52 条）。
> 回滚：`DROP TABLE csca_question_favorite;`（新表，回滚即整表删除、**收藏数据全部丢失**）。
> ✅ **TEST 执行记录（2026-10-14 11:01）**：G1 `xuexitest` / G2 `787e3b0c860c` 通过；G3 落盘 `tmp/_backup_practice_favorite_tables_20261014_110105.json` + `tmp/_rollback_question_favorite_20261014_110105.sql`；G4 回读：**13 列**类型/可空性逐列一致、**3 个索引**（`PRIMARY` / `uk_user_question(user_id, question_id)` / `idx_user_time(user_id, deleted, updated_time)`）、`InnoDB` + `utf8mb4_0900_ai_ci` + `Dynamic`、**0 行** → `COMMIT`。只读复核脚本 `tmp/_verify_ddl_question_tables.py` 独立确认（并与 `question_wrong` 逐列比对一致）。
> ⚠️ **首跑踩坑（脚本已修）**：G4 原断言 `ROW_FORMAT == "DYNAMIC"`，而 `information_schema.TABLES` 实回 **`Dynamic`** → 断言失败；且 **MySQL DDL 隐式提交 —— `conn.rollback()` 对 `CREATE TABLE` 无效**（表当时其实已落库，靠 G5 幂等挡住二次执行）。已改为 `.upper()` 比较，并给两个脚本的 `except` 分支补上**显式 `DROP TABLE` 补偿**（能进入该分支说明 G5 已判定表原不存在，DROP 安全）。
> 🔴 **TEST 重构执行记录（2026-10-19 12:57）**：`python tmp/_ddl_csca_tables_lang.py --apply` —— **改名 + 加列 + 回填 + 删列合并一次事务**：`question_favorite` → `csca_question_favorite`；`ADD COLUMN language_version VARCHAR(20) NULL AFTER section`；从 `question → exam_paper` **回填 4 行**（NULL 0 行、语言分布 `chinese` 4 行）；`DROP COLUMN section_mapping`。G4 回读：**13 列**逐列同序（语言列在 `section` 之后、无 `section_mapping`）/ **3 个索引** / `InnoDB` / **4 行**（与改前一致）→ `COMMIT`。G3 落盘 `tmp/_csca_tables_lang_before_20261019_125733.json` + `tmp/_rollback_csca_tables_lang_20261019_125733.sql`。⚠️ 该脚本 `--prod` 模式可复用于生产（当前 **PROD 两表尚未建**，生产上应直接按新 DDL 建表）。
> 🟡 **TEST 合并 record 列执行记录（2026-10-19 15:44，两表同批）**：`python tmp/_ddl_csca_record_id.py --apply` —— 每表 `ADD COLUMN record_id BIGINT NULL COMMENT '来源记录ID（按 source 判定…）' AFTER source` → `UPDATE … SET record_id = practice_record_id`（收藏 **5 行** / 错题本 **7 行**）→ `DROP exam_record_id` → `DROP practice_record_id`。删列**前**先断言「`record_id` 与 `practice_record_id` 全行 NULL 安全相等」且「`exam_record_id` 非空行 = 0」，不满足就拒绝删列。G4 回读：收藏 **12 列** / 错题本 **13 列**逐列同序、3 索引、`InnoDB`、行数不变（5 / 7）、`record_id` NULL **0 行** → `COMMIT`。G3 备份 `tmp/_csca_record_id_before_20261019_154457.json` + 回滚 `tmp/_rollback_csca_record_id_20261019_154457.sql`（重建两旧列 + 从 `record_id` 回灌 `practice_record_id` + 删 `record_id`）。
>
> **附 6：`csca_question_wrong` 建表**（🆕 **新建表**，2026-10-13 定；✅ **TEST 已建（2026-10-14 11:01）**；🔴 **2026-10-19 改名 + 加 `language_version` / `user_answer` + 删 `section_mapping`**、🟡 **15:44 两列合一为 `record_id`**（[4.4](#44-文档与实现的差异) 第 66 / 67 / 69 / 70 条）；⚠️ **PROD 未建**）
> DDL 见 [3.6.2 业务逻辑第 9 条](#362-错题本wrong-book)（**13 列**：`id` / `user_id` / `question_id` / `section` / `language_version` / **`user_answer`** / `source` / `record_id` / `deleted` / `created_by` / `update_by` / `created_time` / `updated_time` + `uk_user_question` / `idx_user_time`；🔴 **无 `section_mapping`**；🟡 **`record_id` 与 `source` 成对**，原 `practice_record_id` / `exam_record_id` 已于 15:44 合并）。
> 建表时**照本模块既有做法配五闸门脚本**（默认 DRY-RUN、加 `--apply` 才执行；✅ **脚本 `tmp/_ddl_question_wrong.py`，TEST 已执行（`python tmp/_ddl_question_wrong.py --apply`）**）：G1 `DATABASE()` / G2 `@@hostname` / G3 改前 `SHOW TABLES` 快照 + 回滚 SQL（`DROP TABLE`）先落盘 / G4 执行后回读核对（表存在 + 13 列类型与可空性 + 3 个索引名 + 引擎 `InnoDB` + 字符集 `utf8mb4_0900_ai_ci` + 行格式 `DYNAMIC` + 空表）通过才 `COMMIT` / G5 幂等（先判表是否已存在，存在则跳过）。
> 回滚：`DROP TABLE csca_question_wrong;`（新表，回滚即整表删除、**错题本数据全部丢失**）。
> ⚠️ 本表**只服务 CSCA 错题本接口**，与 HSK 四条链路**零耦合**（HSK 不读此表）。
> ✅ **TEST 执行记录（2026-10-14 11:01）**：G1 `xuexitest` / G2 `787e3b0c860c` 通过；G3 落盘 `tmp/_backup_practice_wrong_tables_20261014_110129.json` + `tmp/_rollback_question_wrong_20261014_110129.sql`；G4 回读：**13 列**逐列一致、**3 个索引**齐全、`InnoDB` + `utf8mb4_0900_ai_ci` + `Dynamic`、**0 行** → `COMMIT`。
> 🔴 **TEST 重构执行记录（2026-10-19 12:57）**：同批脚本 `tmp/_ddl_csca_tables_lang.py --apply` —— `question_wrong` → `csca_question_wrong`；加 `language_version`（AFTER `section`）并**回填 4 行**（NULL 0 行、`chinese` 4 行）；删 `section_mapping`。G4：**13 列**逐列同序 / **3 个索引** / `InnoDB` / **4 行**不变 → `COMMIT`。
> 🟡 **TEST 加 `user_answer` 执行记录（2026-10-19 15:17）**：`python tmp/_ddl_csca_wrong_user_answer.py --apply` —— `ADD COLUMN user_answer TEXT NULL AFTER language_version` + **从 `practice_answer`（`is_correct = 2` 最近一次）回填 7 行**（NULL 0 行，分布 `A` 2 / `B` 5）。G4：**14 列**逐列同序 / **3 个索引** / `InnoDB` / **7 行**不变 → `COMMIT`。G3 备份 `tmp/_csca_wrong_user_answer_before_20261019_151753.json`、回滚 `tmp/_rollback_csca_wrong_user_answer_20261019_151753.sql`（`DROP COLUMN`）。⚠️ **PROD 建表时直接带上该列**，无需跑回填。
> 🟡 **同批合并 `record_id`（2026-10-19 15:44）**：与收藏表**同一次脚本**执行，见附 5 的执行记录 —— 本表 **14 → 13 列**、7 行不变、`record_id` NULL 0 行。
> 📊 **建表后 TEST 表总数 86 → 88**（`practice_*` 由 9 张增至 **11 张**：`…favorite` / `…wrong` 两张到位）；⚠️ **PROD 未建**（本轮按口径只建 TEST）→ 上线前须补 `--prod --apply`。
