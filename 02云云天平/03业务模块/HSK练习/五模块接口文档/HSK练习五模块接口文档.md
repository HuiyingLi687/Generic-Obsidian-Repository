# HSK 练习 · 五模块全链路接口文档

> **适用服务**：`practice-service`（对外经 `gateway` 暴露）
> **内容版本**：HSK 2.0 / HSK 3.0
> **文档口径**：按 2026-11-17 的代码实测整理，路径、字段名、错误码均与线上实现一致
> **配套文件**：`hsk-practice.http`（Idea HTTP Client 全链路联调脚本，可直接点执行）

---

## 0. 三分钟上手

### 0.1 调用链

五模块共用「目录三跳 → 开练 → 答题 → 交卷 → 看报告」这一条骨架，只有答题和交卷的动作不同。

| 步骤 | 请求 | 拿到什么 |
|---|---|---|
| ① 首页 | `GET /hsk/modules` | 模块卡（免登录） |
| ② 等级概览 | `GET /hsk/levels` | 该等级的卷列表 |
| ③ 备考说明 | `GET /hsk/levels/{level}/intro` | 板块结构（可选，展示用） |
| ④ 卷内板块 | `GET /hsk/papers/{paperId}/parts` | 板块 + 进度（点进去必调） |
| ⑤ 开练 | `POST /{module}/records/start` | `recordId` |
| ⑥ 拉题 | `GET /{module}/records/{recordId}/questions` | 题目列表 |
| ⑦ 答题 | 见各模块 | 逐题或批量存答案 |
| ⑧ 交卷 | `POST /{module}/records/{recordId}/submit` | 判分结果 / 报告状态 |
| ⑨ 报告 | `GET /{module}/records/{recordId}/report` | 轮询直到非 `GRADING` |

> 上表路径省略了网关前缀 `/api/practice`，查询参数也省略；完整写法见 [1.1](#11-地址与网关前缀) 与各模块章节。翻译的交卷是 `/submissions`（复数），见第 7 章。

`{module}` 的取值与第 ⑦ ⑧ 步的差异见 [2. 五模块差异速查](#2-五模块差异速查)。

### 0.2 一个必须知道的坑：`X-Client-Type`

所有需要用户身份的接口，**必须带 `X-Client-Type: APP`**，否则服务端会拿一个内置的模拟用户（`userId=1`）来跑，接口不会报错，但你会看到别人的数据。

```
X-Client-Type: APP
Authorization: Bearer <登录拿到的 token>
```

判断依据：`BaseController.getUserInfo()` 只在 `X-Client-Type=APP` 时才解析 JWT；其他取值一律回落模拟用户。带 `APP` 但 token 缺失/失效时，才会正常返回 `401`。

### 0.3 一个必须知道的坑：业务错误也是 HTTP 200

`GlobalExceptionHandler` 对所有业务异常统一 `ResponseEntity.ok(...)`，所以：

| 你以为 | 实际 |
|---|---|
| `404` / `409` 走 HTTP 状态码 | HTTP 状态码全是 **200**，错误在响应体的 `code` 字段 |
| `if (status === 200) 成功` | 必须 `if (body.code === 200) 成功` |

**前端只能按 `body.code` 判断成败**，`response.ok` 永远为 `true`。唯一的例外是网关层面的错误（服务不可达、鉴权被网关拦截），那才是真的非 200。

---

## 1. 通用约定

### 1.1 地址与网关前缀

服务内路径以 `/hsk`、`/listening`、`/reading`、`/writing`、`/translation`、`/speaking`、`/papers` 开头，经网关后统一加 `/api/practice` 前缀：

```
对外：https://<host>/api/practice/hsk/modules
服务内：                         /hsk/modules
```

网关规则是 `Path=/api/practice/**` + `StripPrefix=2`，`practice` 那一段由网关补，**服务内不要重复写**。

本机直连服务时（不经网关）用 `http://127.0.0.1:8087`，不加 `/api/practice`。

### 1.2 请求头

| 头 | 必填 | 说明 |
|---|---|---|
| `X-Client-Type` | 需要用户数据时必填 | 固定 `APP`。缺失会回落模拟用户 `id=1` |
| `Authorization` | 同上 | `Bearer <token>`；也兼容 `X-Access-Token` 头 |
| `Accept-Language` | 否 | `zh` / `en` / `vi`，缺省 `zh`。带区域后缀（`en-US`）也能识别 |
| `Idempotency-Key` | 否 | 仅交卷接口接受，**服务端已忽略其值**，幂等键由后端按 `{module}-{recordId}-submit` 自拼 |
| `Content-Type` | 有 body 时 | `application/json` |

### 1.3 统一响应结构

```json
{ "code": 200, "message": "操作成功", "data": { } }
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | Integer | `200` 成功；其余为错误码，见 [附录 A](#附录-a-错误码) |
| `message` | String | 成功固定 `操作成功`；失败时可能是错误码字符串（如 `DRAFT_LOCKED`）或中文提示 |
| `data` | Object / Array / null | 业务数据。无返回值的接口为 `null` |

### 1.4 业务错误的表现形式

**HTTP 200 + body.code ≠ 200**。典型的三种：

```json
{ "code": 401, "message": "未登录或Token无效", "data": null }
{ "code": 400, "message": "SECTION_MAPPING_MISMATCH", "data": null }
{ "code": 409, "message": "DRAFT_VERSION_CONFLICT", "data": { "currentVersion": 7, "savedTime": 1789612800000 } }
```

注意 `message` 的两种形态：业务异常抛的是**错误码字符串**（`DRAFT_LOCKED`），参数校验失败给的是**中文描述**（`module: 不能为空`）。前端做提示时不要直接把 `message` 甩给用户，按 `code` 映射文案。

### 1.5 参数约定

- **`module`**：`listening` / `reading` / `writing` / `speaking` / `translation`，**大小写不敏感**（服务端 `toLowerCase`），建议小写。
- **`version`**：`HSK2.0` / `HSK3.0`，缺省 `HSK2.0`；白名单外返回 `400 PRACTICE_VERSION_INVALID`。
- **`level`**：数字字符串 `"1"`–`"7"`，`"7"` 代表 HSK 7-9 整级。
- **`section`**：板块号，各模块统一为数字 `1`、`2`、`3`…；口语同为数字，但**板块编码叫 `PART_1`**（见 1.6）。
- **`recordId`**：练习记录主键。听力/阅读是 `practice_record.id`，写作/翻译/口语是 `practice_subjective_record.id`。**两个模块体系的 ID 不通用**，把听力的 recordId 传给写作必然 403。

### 1.6 三个容易搞混的「板块标识」

| 场景 | 字段名 | 类型 | 示例 | 来源 |
|---|---|---|---|---|
| 首页模块卡 | `moduleCode` | String | `LISTENING`（**大写**） | `GET /hsk/modules` |
| 目录接口入参 | `module` | String | `listening`（小写，大小写不敏感） | 前端固定传 |
| U3 板块列表 | `parts[].section` | **Integer** | `1` | `GET /hsk/papers/{id}/parts` |
| U3 板块列表 | `parts[].partCode` | String | `"1"`；口语是 `PART_1` | 同上 |
| 主观模块开练 | `sectionMapping` | String | `SEC_WRITE` / `SEC_TRANSLATION` / `SEC_SPEAKING` | 前端按模块固定传 |
| 主观模块开练 | `section` | **String** | `"1"` | 取 U3 的 `parts[].section`，`.toString()` |

🔴 **两个类型差异**：U3 的 `section` 是数字，开练接口的 `section` 是字符串，中间要转一次。

### 1.7 模块 ↔ `sectionMapping` 对照

| module | sectionMapping | 记录表 | 交卷路名 |
|---|---|---|---|
| `listening` | `SEC_LISTEN` | `practice_record` | `/listening/records/{id}/submit` |
| `reading` | `SEC_READ` | `practice_record` | `/reading/records/{id}/submit` |
| `writing` | `SEC_WRITE` | `practice_subjective_record` | `/writing/records/{id}/submit` |
| `translation` | `SEC_TRANSLATION` | `practice_subjective_record` | `/translation/records/{id}/submissions`（注意是复数） |
| `speaking` | `SEC_SPEAKING` | `practice_subjective_record` | `/speaking/records/{id}/submit` |

> 口语的 `SEC_SPEAK`（少一个 ING）是历史拼写错误，服务端仍放行，但**响应里返回的一律是 `SEC_SPEAKING`**。新代码请用 `SEC_SPEAKING`。

### 1.8 免登录接口

只有两个：

- `GET /api/practice/hsk/modules`（首页卡片，响应不含任何用户数据）
- `GET /api/practice/csca/catalog`（CSCA 目录，不在本文范围）

其余接口都要求 `X-Client-Type: APP` + 有效 token。`GET /hsk/levels` 等虽然名字像目录，但返回里带用户进度，**属于需登录接口**。

---

## 2. 五模块差异速查

### 2.1 端点对照表

| 动作 | 听力 | 阅读 | 写作 | 翻译 | 口语 |
|---|---|---|---|---|---|
| 开练 | `POST /listening/records/start` | `POST /reading/records/start` | `POST /writing/records/start` | `POST /translation/records/start` | `POST /speaking/records/start` |
| 记录详情 | `GET /listening/records/{id}` | `GET /reading/records/{id}` | `GET /writing/records/{id}` | `GET /translation/records/{id}` | `GET /speaking/records/{id}` |
| 拉题 | `GET …/{id}/questions` | 同 | 同 | 同 | 同 |
| 答题 | `PUT …/{id}/answers/{qid}`<br>`PUT …/{id}/answers`（批） | `PUT …/{id}/answers/{qid}`<br>`PUT …/{id}/answers`（批） | `PUT …/{id}/answers`（批） | `PUT …/{id}/answers`（批） | `POST …/{id}/questions/{qid}/answers`（单题） |
| 草稿 | — | — | `PUT …/{id}/questions/{qid}/draft` | 同 | 同（仅提纲） |
| 暂停 | `POST …/{id}/pause` | `POST …/{id}/pause` | — | — | — |
| 放弃 | — | `POST …/{id}/abandon` | — | — | — |
| 交卷 | `POST /listening/records/{id}/submit` | `POST /reading/records/{id}/submit` | `POST /writing/records/{id}/submit` | `POST /translation/records/{id}/submissions` | `POST /speaking/records/{id}/submit` |
| 报告 | `GET …/{id}/report` | 同 | 同 | 同 | 同 |
| 报告重试 | `POST …/{id}/report/retry` | 同 | 同 | **无此端点** | 同 |
| 单题回顾 | `GET …/{id}/report/questions/{qid}` | 同 | 同 | 同 | 同 |
| 答题卡 | `GET /listening/records/{id}/answer-card` | `/reading/…` | `/writing/…` | `/translation/…` | `/speaking/…` |

表里 `…` 均指 `/records/{recordId}` 之前那段路径。

### 2.2 语义差异

| 维度 | 听力 / 阅读 | 写作 / 翻译 | 口语 |
|---|---|---|---|
| 判分方式 | 交卷即判，报告立刻 `READY` | 客观题即判，主观题走 AI（`GRADING` → `READY`） | 全部 AI 判分 |
| 交卷后能否改 | 否 | 否 | 否 |
| 答案形态 | `selectedOptionId`（A/B/C…）/ `answer` | `answerText` 文本 | `answer` 音频 URL + `durationMs` |
| 进度定位 | `currentQuestionId` + 题号 | 同 | 同 |
| 计时 | `durationSeconds` 客户端上报 | 同 | 同 |
| 答题卡 `answered` | 该题选过 | 该题存过答案 | 录音已上传完成 |

### 2.3 内部接口（前端不要用）

`POST /internal/practice/speaking/configs/{version}/validate` 是运营侧配置校验入口，不在网关白名单，前端无需接入。

---
## 3. 目录三跳（五模块共用）

这一组接口与具体模块无关，靠 `module` 参数区分。三跳都 **必须带 `module`**：HSK 2.0 综合卷上听力第 1 部分和阅读第 1 部分共用同一个 `paperId` 和 `section`，光靠后两者无法定位板块。

### 3.1 E1 首页模块卡

```
GET /hsk/modules?version=HSK3.0
```

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `version` | query | 否 | `HSK2.0` / `HSK3.0`，缺省 `HSK2.0` |

**免登录**，不需要 `X-Client-Type`，响应里没有任何用户数据。

```bash
curl 'https://<host>/api/practice/hsk/modules?version=HSK3.0' \
  -H 'Accept-Language: zh'
```

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "version": "HSK3.0",
    "layout": "LIST",
    "header": "选择要练习的模块",
    "modules": [
      { "moduleCode": "LISTENING",   "sectionMapping": "SEC_LISTEN",      "name": "听力", "nameEn": "Listening",   "nameVi": "Nghe",      "sortOrder": 1 },
      { "moduleCode": "READING",     "sectionMapping": "SEC_READ",        "name": "阅读", "nameEn": "Reading",     "nameVi": "Đọc",       "sortOrder": 2 },
      { "moduleCode": "WRITING",     "sectionMapping": "SEC_WRITE",       "name": "写作", "nameEn": "Writing",     "nameVi": "Viết",      "sortOrder": 3 },
      { "moduleCode": "TRANSLATION", "sectionMapping": "SEC_TRANSLATION", "name": "翻译", "nameEn": "Translation", "nameVi": "Dịch",      "sortOrder": 4 },
      { "moduleCode": "SPEAKING",    "sectionMapping": "SEC_SPEAK",       "name": "口语", "nameEn": "Speaking",    "nameVi": "Nói",       "sortOrder": 5 }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | String | 回显解析后的版本 |
| `layout` | String | `GRID_2`（2.0 四卡）/ `LIST`（3.0 五卡） |
| `header` | String | 副标题，按 `Accept-Language` 本地化 |
| `modules[].moduleCode` | String | **大写**模块码，与后面 `module` 参数（小写）不是同一套 |
| `modules[].sectionMapping` | String | ⚠️ 口语这里是 `SEC_SPEAK`（配置表存量值），开练时传 `SEC_SPEAKING` 或 `SEC_SPEAK` 都能过 |
| `modules[].sortOrder` | Integer | 服务端已排好序，前端照序渲染即可 |

2.0 只有 4 张卡（无翻译），`layout=GRID_2`。模块卡由字典表驱动，增减模块不需要改前端。

### 3.2 U1 等级概览 + 卷列表

```
GET /hsk/levels?module=reading&version=HSK3.0&level=3
```

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `module` | query | **是** | 缺省或非法 → `400 模块编码不合法（PRACTICE_MODULE_INVALID）` |
| `version` | query | 否 | 缺省 `HSK2.0` |
| `level` | query | 否 | 缺省 `"1"` |

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "module": "reading",
    "level": "3",
    "levelName": "HSK 三级",
    "paperCount": 2,
    "papers": [
      { "paperId": 2095405786495315969, "paperCode": "HSK3.0 三级阅读 模拟卷 A", "status": "in_progress", "completedCount": 12, "totalCount": 30 },
      { "paperId": 2095405786495315970, "paperCode": "HSK3.0 三级阅读 模拟卷 B", "status": "not_started", "completedCount": 0,  "totalCount": 30 }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `level` | String | 数字串，`"7"` 表示 HSK 7-9 整级 |
| `levelName` | String | 取配置表 `level_name` 三语列，**服务端不拼接**，直接展示 |
| `papers[].paperId` | Long | 主键，19 位长整数，**JSON 里按字符串传更安全**（见 11.1） |
| `papers[].paperCode` | String | 卷名，来自 `exam_paper.source` / `speaking_exam_paper.source` |
| `papers[].status` | String | `not_started` / `in_progress` / `completed`（**小写**） |
| `papers[].completedCount` | Integer | 已答题数（已提交部分累计；口语 = 已提交的录音题数） |
| `papers[].totalCount` | Integer | 该模块在该卷下的总题数，已排除下架题与示例题 |

模块无内容时（如 2.0 的翻译）返回 `paperCount=0`、`papers=[]`，**不报错**，前端做空态处理即可。

### 3.3 U2 等级备考说明

```
GET /hsk/levels/3/intro?module=reading&version=HSK3.0
```

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `level` | path | 是 | 数字串 |
| `module` | query | **是** | |
| `version` | query | 否 | |

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "module": "reading",
    "level": "3",
    "levelName": "HSK 三级",
    "abilityDescription": "能够阅读中等长度的汉语材料……",
    "abilityDescriptionEn": "Can read medium-length Chinese materials...",
    "abilityDescriptionVi": "...",
    "totalQuestionCount": 30,
    "durationMinutes": 35,
    "parts": [
      {
        "partCode": "1",
        "section": 1,
        "partName": "第一部分",
        "partNameEn": "Part 1",
        "partNameVi": "Phần 1",
        "typeCode": "reading_choice",
        "typeName": "单项选择",
        "typeNameEn": "Multiple choice",
        "typeNameVi": "Trắc nghiệm",
        "questionCount": 10,
        "sortOrder": 1,
        "durationMinutes": null
      }
    ]
  }
}
```

| 字段 | 说明 |
|---|---|
| `parts[].partCode` | 板块编码：口语 `PART_1`，其余模块是数字串 `"1"` |
| `parts[].section` | **Integer**，板块号 1..N |
| `parts[].typeCode` | 题型编码，只表业务语义。**答题交互不看它，只看 `question.layout`** |
| `parts[].questionCount` | 实际题量，现算（已排除下架题与示例题） |
| `parts[].durationMinutes` | 板块级建议时长，**只有口语下发**，其余为 `null` |

这一跳没有进度字段，纯展示。等级未配置或模块关闭时 `parts=[]`。

### 3.4 U3 卷内板块 + 进度

点进一张卷就调这个，是**答题前最关键的一跳**。

```
GET /hsk/papers/2095405786495315969/parts?module=reading&version=HSK3.0
```

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `paperId` | path | 是 | 试卷 ID（口语落 `speaking_exam_paper.id`，其余 `exam_paper.id`） |
| `module` | query | **是** | 缺了无法在综合卷上区分听力和阅读 |
| `version` | query | 否 | 传了且与卷的 version 不符 → 404 |

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "module": "reading",
    "paperId": 2095405786495315969,
    "paperCode": "HSK3.0 三级阅读 模拟卷 A",
    "parts": [
      {
        "partCode": "1",
        "section": 1,
        "partName": "第一部分",
        "partNameEn": "Part 1",
        "partNameVi": "Phần 1",
        "typeCode": "reading_choice",
        "typeName": "单项选择",
        "typeNameEn": "Multiple choice",
        "typeNameVi": "Trắc nghiệm",
        "questionCount": 10,
        "sortOrder": 1,
        "durationMinutes": null,
        "status": "in_progress",
        "doneCount": 4,
        "correctCount": null,
        "wrongCount": null,
        "draft": { "id": 2095405786495315999, "answeredCount": 4, "currentQuestionId": 2095405786495316201 },
        "report": { "id": 2095405786495315999, "hasReport": false, "status": "PENDING" },
        "stats": null
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `parts[].status` | String | `not_started` / `in_progress` / `completed`（小写） |
| `parts[].doneCount` | Integer | 已作答题数（口语 = 已录音题数） |
| `parts[].correctCount` / `wrongCount` | Integer | 仅听力/阅读已提交板块有值，其余为 `null` |
| `parts[].draft` | Object/null | 进行中草稿。**「继续上次位置」用 `draft.currentQuestionId`** |
| `parts[].draft.id` | Long | 草稿记录主键，**不是 recordId**，只是内部标识，前端不用传回去 |
| `parts[].report` | Object/null | 最近一次已出报告，无则 `null` |
| `parts[].report.status` | String | `READY` / `PENDING` / `FAILED` / `UNAVAILABLE`；听力/阅读恒 `READY` |
| `parts[].stats` | Object/null | **只有口语有值**，见下 |

口语的 `stats`：

```json
"stats": { "recordedCount": 3, "scoredCount": 2, "unansweredCount": 5, "failedCount": 1 }
```

> ⚠️ `parts[].section` 是数字，开练接口的 `section` 是字符串，**中间要 `.toString()`**。

### 3.5 CR 板块最近报告

用于「上次成绩」入口。注意路径前缀是 `/papers`，**不带 `/hsk`**：

```
GET /papers/{paperId}/reports/latest?module=reading&section=1&version=HSK3.0
```

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `paperId` | path | 是 | |
| `module` | query | **是** | |
| `section` | query | **是** | 板块号，字符串或数字均可 |
| `version` | query | 否 | 传入时校验卷归属 |

```json
{ "code": 200, "message": "操作成功", "data": { "module": "reading", "data": null } }
```

`data.data` 为 `null` 表示该板块尚无报告。有报告时 `data.data` 的结构随 `module` 而变（四个模块报告形状本来不同，服务端不强行收敛）：

| `module` | `data.data` 结构 |
|---|---|
| `listening` | 听力报告摘要，见 [4.10](#410-报告摘要) |
| `reading` | 阅读报告，见 [5.8](#58-报告) |
| `writing` / `translation` / `speaking` | 主观模块报告，见 [6.8](#68-报告) |

> 翻译也走这个端点，`module=translation` 时返回主观报告结构。

---
## 4. 听力（listening）

主键是 `recordId`（`practice_record.id`），交卷即判分，报告立刻 `READY`。

### 4.1 时序

```
POST /start ──► recordId
   │
   ├─ GET /{recordId}           恢复现场（刷新/杀进程后重进）
   ├─ GET /{recordId}/questions 拉题（含音频、选项、已存答案）
   │
   ├─ PUT  /{recordId}/answers/{questionId}   单题防抖保存（选择即存）
   ├─ PUT  /{recordId}/answers                批量保存（切题/退出/锁屏/提交前）
   ├─ POST /{recordId}/pause                  暂停（存进度 + 草稿答案）
   │
POST /{recordId}/submit ──► 判分 + 报告摘要
   │
   ├─ GET  /{recordId}/report                 报告详情（含题号矩阵）
   ├─ POST /{recordId}/report/retry           报告失败时重试
   └─ GET  /{recordId}/report/questions/{qid} 单题回顾
```

### 4.2 开始 / 恢复练习

```
POST /listening/records/start
```

```json
{ "paperId": 2095405786495315969, "section": "1", "restart": false }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `paperId` | Long | 是 | 试卷 ID |
| `section` | String | 是 | 板块号，取 U3 的 `parts[].section` |
| `restart` | Boolean | 否 | `true` = 放弃已有草稿重新开始；`false`/缺省 = 有草稿就恢复 |

**幂等**：同一卷同一板块已有进行中记录时，直接返回那条记录，不会新建。所以「继续练习」就是再调一次 start，不需要额外接口。

响应 `data` 为记录详情，结构见 4.3。

### 4.3 记录详情

```
GET /listening/records/{recordId}
```

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 2095405786495315999,
    "paperId": 2095405786495315969,
    "section": "1",
    "status": 1,
    "reportStatus": "PENDING",
    "currentQuestionId": 2095405786495316201,
    "currentQuestionNumber": 5,
    "currentPassageItemIndex": 0,
    "durationSeconds": 180,
    "answeredCount": 4,
    "totalQuestions": 10,
    "answers": [
      { "questionId": 2095405786495316201, "answer": "A", "answered": true, "conflict": false, "currentVersion": 7 }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | Integer | `0` 已创建 / `1` 进行中 / `2` 已放弃 / `3` 已提交 |
| `reportStatus` | String | `PENDING` / `GENERATING` / `READY` / `FAILED` |
| `currentQuestionId` | Long | 停在哪道题，用来定位「继续」 |
| `currentQuestionNumber` | Integer | 题号 = 题集下标 + 1 |
| `currentPassageItemIndex` | Integer | `passageGroup` 布局下当前子题索引，其他布局恒 `0` |
| `answers[].currentVersion` | Integer | 云端最新版本号，下次保存时作为 `baseVersion` 传回 |

### 4.4 拉题

```
GET /listening/records/{recordId}/questions
```

响应是**数组**，按题集顺序：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": [
    {
      "questionId": 2095405786495316201,
      "no": 1,
      "layout": "imageChoice",
      "passage": "今天天气很好，我们去公园散步。",
      "variant": null,
      "answered": true,
      "userAnswer": "A",
      "audio_url": "https://cdn.example.com/audio/abc.mp3",
      "option_content": { "A": "图片A", "B": "图片B", "C": "图片C", "D": "图片D" },
      "share_audio_url": null
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `layout` | String | 答题交互的唯一真源，取值见 [9.2](#112-layout-取值) |
| `variant` | String | 细节选择题变体 `short` / `long` / `interview`，仅 `textChoice_shareAudio` / `passageGroup` 有值 |
| `answered` / `userAnswer` | Boolean / String | 已存答案回填 |
| `audio_url` | String | 题目音频。⚠️ **字段名是下划线** |
| `option_content` | Object | 选项映射 `{"A":"...","B":"..."}`，**扁平结构**。⚠️ **字段名是下划线** |
| `share_audio_url` | String | 共享材料音频，仅 `passageGroup` 布局有值。⚠️ **字段名是下划线** |

🔴 **这三个字段是真·下划线命名**（源码里 `@JsonProperty("audio_url")` 显式指定），其余字段都是驼峰。前端别写成 `audioUrl` / `optionContent`，会全部取到 `undefined`。

### 4.5 单题保存（防抖）

```
PUT /listening/records/{recordId}/answers/{questionId}
```

```json
{ "selectedOptionId": "A", "clientSequence": 12, "baseVersion": 7 }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `selectedOptionId` | String | 是 | 稳定选项标识 `A`/`B`/`C`/`D`/`E`/`F`。**判断题也用 A/B 表示，不要传 `true`/`false`** |
| `clientSequence` | Integer | 否 | 客户端序列号，用于乱序检测（小序号不会覆盖大序号已存的值） |
| `baseVersion` | Integer | 否 | 乐观锁基础版本，须与记录当前 `version` 一致；不一致返回冲突摘要 |

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { "questionId": 2095405786495316201, "answer": "A", "answered": true, "conflict": false, "currentVersion": 8 }
}
```

冲突时 `conflict=true`，`answer` / `answered` 返回**云端最新值**，由客户端弹窗让用户选「保留本机 / 用云端」。`currentVersion` 可作为下次重试的 `baseVersion`。

### 4.6 批量保存

```
PUT /listening/records/{recordId}/answers
```

```json
{
  "answers": [
    { "questionId": 2095405786495316201, "selectedOptionId": "A" },
    { "questionId": 2095405786495316202, "selectedOptionId": "C" }
  ],
  "currentQuestionId": 2095405786495316202,
  "durationSeconds": 240,
  "clientSequence": 13,
  "baseVersion": 8
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `answers[]` | Array | 每题 `questionId` + `selectedOptionId`，必填非空 |
| `currentQuestionId` | Long | 当前停留题，服务端据此更新续练位置 |
| `durationSeconds` | Integer | 本次保存累加的有效时长（秒），服务端**按累加**处理 |
| `baseVersion` | Integer | 乐观锁版本 |

响应 `data` 是完整记录（同 4.3），比单题接口多回一次全量，适合切题时刷新本地状态。

### 4.7 暂停

```
POST /listening/records/{recordId}/pause
```

```json
{
  "currentQuestionId": 2095405786495316202,
  "durationSeconds": 300,
  "draftAnswers": [
    { "questionId": 2095405786495316201, "answer": "A", "answered": 1 }
  ],
  "clientSequence": 14,
  "baseVersion": 8
}
```

与批量保存的区别：`draftAnswers` 只落**草稿**，不固化提交快照；`answered` 是 `Integer`（`0` 未答 / `1` 已答），注意与响应里的 Boolean `answered` 不是同一形态。

响应 `data` 为完整记录。

### 4.8 交卷

```
POST /listening/records/{recordId}/submit
```

```json
{
  "durationSeconds": 600,
  "idempotencyKey": "listening-2095405786495315999-submit",
  "finalAnswers": [
    { "questionId": 2095405786495316203, "selectedOptionId": "B" }
  ],
  "baseVersion": 9,
  "clientSequence": 15
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `finalAnswers` | Array | 交卷前最后一批答案，可为空（前面已逐题存过） |
| `idempotencyKey` | String | 相同 key 重复提交直接返回已生成报告。**服务端按 `{module}-{recordId}-submit` 自拼，你传的值会被忽略** |
| `durationSeconds` | Integer | 本次累加时长 |

响应 `data` 为报告摘要：

```json
{
  "recordId": 2095405786495315999,
  "reportId": 2095405786495315999,
  "reportStatus": "READY",
  "totalQuestions": 10,
  "answeredCount": 10,
  "correctCount": 8,
  "wrongCount": 2,
  "accuracyRate": 80,
  "durationSeconds": 600
}
```

听力是客观题，交卷即判，`reportStatus` 直接是 `READY`。`reportId` 与 `recordId` 同值（报告以记录为载体）。

### 4.9 报告详情

```
GET /listening/records/{recordId}/report
```

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "reportId": 2095405786495315999,
    "reportStatus": "READY",
    "accuracyRate": 80,
    "totalQuestions": 10,
    "correctCount": 8,
    "wrongCount": 2,
    "answeredCount": 10,
    "durationSeconds": 600,
    "submittedTime": 1789612800000,
    "rows": [
      {
        "number": 1,
        "questionId": 2095405786495316201,
        "questionType": "imageChoice",
        "layout": "imageChoice",
        "answered": true,
        "isCorrect": true,
        "userAnswer": "A",
        "correctAnswer": "A"
      }
    ]
  }
}
```

🔴 报告接口的 `reportStatus` **值域与记录接口不同**：

| 接口 | 值域 |
|---|---|
| `GET /listening/records/{id}`（记录） | `PENDING` / `GENERATING` / `READY` / `FAILED` |
| `GET /listening/records/{id}/report`（报告） | `PROCESSING` / `READY` / `FAILED_RETRYABLE` / `FAILED_FINAL` |
| `POST …/submit`（交卷） | 同记录接口：`PENDING` / `GENERATING` / `READY` / `FAILED` |

前端做轮询判断时按各自接口的枚举写，别混用一套。

`wrongCount` = `totalQuestions - correctCount`，**未作答计入错误**。

### 4.10 报告摘要

上面 4.8 交卷返回的即报告摘要。`GET /papers/{paperId}/reports/latest?module=listening&section=1` 的 `data.data` 也是这个结构。

### 4.11 报告重试

```
POST /listening/records/{recordId}/report/retry
```

无 body。**仅对 `FAILED_RETRYABLE` 状态生效**，其他状态返回 `2006 REPORT_NOT_RETRYABLE`。响应为最新报告摘要。

### 4.12 单题回顾

```
GET /listening/records/{recordId}/report/questions/{questionId}
```

```json
{
  "questionId": 2095405786495316201,
  "no": 1,
  "layout": "imageChoice",
  "passage": "今天天气很好。",
  "variant": null,
  "answered": true,
  "userAnswer": "A",
  "isCorrect": true,
  "standardAnswer": "A",
  "analysis": "句意表示天气好，选 A。",
  "audio_url": "https://cdn.example.com/audio/abc.mp3",
  "option_content": { "A": "图片A", "B": "图片B" },
  "share_audio_url": null
}
```

全部取自交卷时固化的快照，不拉最新题库。`analysis` 为空时前端展示「暂无解析」。

### 4.13 答题卡

```
GET /listening/records/{recordId}/answer-card?currentQuestionNumber=5
```

`currentQuestionNumber` 可选，缺省取记录里的当前题号。五模块共用同一个响应结构，见 [9. 答题卡](#9-答题卡五模块共用)。

---

## 5. 阅读（reading）

与听力同构，主键同为 `recordId`，交卷即判。**差异只有四处**：

| 差异 | 听力 | 阅读 |
|---|---|---|
| 答题保存 | `selectedOptionId` | `answer`（自由文本/选项标识都走这个字段） |
| 暂停 | `pause` + 草稿答案 | `pause` 只存当前题位置 |
| 放弃草稿 | 无 | `POST /reading/records/{id}/abandon` |
| 题目结构 | 单题 + `share_audio_url` | 单题 + **题组 `group`**（共享材料 + 共享选项） |

### 5.1 端点清单

| 动作 | 端点 | 与听力的差异 |
|---|---|---|
| 开练 | `POST /reading/records/start` | 请求体相同 |
| 记录详情 | `GET /reading/records/{recordId}` | 响应见 5.2 |
| 拉题 | `GET /reading/records/{recordId}/questions` | 响应见 5.3 |
| 单题保存 | `PUT /reading/records/{recordId}/answers/{questionId}` | body 是 `{questionId, answer}` |
| 批量保存 | `PUT /reading/records/{recordId}/answers` | 返回**答案数组**，不是整条记录 |
| 暂停 | `POST /reading/records/{recordId}/pause` | body 只有 `{currentQuestionId}` |
| 放弃 | `POST /reading/records/{recordId}/abandon` | 无 body，返回 `data=null` |
| 交卷 | `POST /reading/records/{recordId}/submit` | 响应见 5.7 |
| 报告 | `GET /reading/records/{recordId}/report` | 结构比听力多 `items[]` 逐题明细 |
| 报告重试 | `POST /reading/records/{recordId}/report/retry` | 同 |
| 单题回顾 | `GET /reading/records/{recordId}/report/questions/{questionId}` | 返回 `ReadingReportItemResponse` |
| 答题卡 | `GET /reading/records/{recordId}/answer-card` | 同 |

### 5.2 记录详情

```json
{
  "recordId": 2095405786495315999,
  "paperId": 2095405786495315969,
  "section": "1",
  "status": 1,
  "reportStatus": "PENDING",
  "currentQuestionId": 2095405786495316201,
  "currentQuestionNumber": 5,
  "answeredCount": 4,
  "totalQuestions": 10,
  "resumeElapsedSeconds": 0,
  "answers": [
    { "questionId": 2095405786495316201, "answer": "B", "answered": true }
  ]
}
```

与听力相比：没有 `currentPassageItemIndex`、没有 `durationSeconds`，多一个 `resumeElapsedSeconds`（本次恢复后重新计时的秒数）。阅读的时长由客户端自己算，服务端不累计。

### 5.3 拉题（含题组）

```json
{
  "code": 200,
  "message": "操作成功",
  "data": [
    {
      "questionId": 2095405786495316201,
      "number": 1,
      "typeId": "reading_choice",
      "typeIdMapping": "reading_choice",
      "content": "根据文章，作者为什么……？",
      "passage": null,
      "optionContent": { "options": { "A": "因为天气", "B": "因为时间", "C": "因为地点" } },
      "audioUrl": null,
      "groupId": 2095405786495316300,
      "group": {
        "groupId": 2095405786495316300,
        "title1Number": 1,
        "title1Text": "第一部分",
        "section": "1",
        "startNumber": 1,
        "endNumber": 5,
        "passage": "这是一段共享的阅读材料……",
        "audioUrl": null,
        "optionContent": { "options": {} }
      },
      "userAnswer": "A",
      "answered": true,
      "optionPoolCode": null,
      "exclusiveSharedOptions": false
    }
  ]
}
```

🔴 **选项结构比听力多一层 `options`**：

| 模块 | 字段 | 形态 |
|---|---|---|
| 听力 | `option_content` | `{"A":"文本","B":"文本"}` 扁平 |
| 阅读 | `optionContent.options` | `{"options":{"A":"文本"}}` 多一层 |

这是两套 DTO 的历史差异（听力用 `Map<String,String>`，阅读用 `PracticeOptionContent`），**不能共用同一段渲染逻辑**。

| 字段 | 说明 |
|---|---|
| `number` | 题号（听力叫 `no`，阅读叫 `number`） |
| `group` | 题组共享内容，`groupId=null` 时该字段恒 `null`。同组题目的 `group` 内容完全相同，前端**只渲染一次** |
| `optionPoolCode` | 共享选项池编码，普通题为 `null`。同池题目共用一套选项，**选项不互斥**（`exclusiveSharedOptions` 恒 `false`，保留兼容） |
| `passage` | 单题材料。题组材料的放在 `group.passage` |

### 5.4 保存答案

单题：

```
PUT /reading/records/{recordId}/answers/{questionId}
```

```json
{ "questionId": 2095405786495316201, "answer": "A" }
```

`answer` 传 `null` 表示**清空该题答案**。

批量：

```
PUT /reading/records/{recordId}/answers
```

```json
{ "answers": [ { "questionId": 1, "answer": "A" }, { "questionId": 2, "answer": "B" } ] }
```

批量接口的响应是**答案数组**，不是整条记录：

```json
{ "code": 200, "message": "操作成功", "data": [ { "questionId": 1, "answer": "A", "answered": true } ] }
```

注意与听力的批量接口（返回整条记录）不一致，前端别照抄。

### 5.5 暂停

```
POST /reading/records/{recordId}/pause
```

```json
{ "currentQuestionId": 2095405786495316201 }
```

只存位置，不存草稿答案。响应为记录详情。

### 5.6 放弃草稿

```
POST /reading/records/{recordId}/abandon
```

无 body，`data` 为 `null`。用于「重新开始」前清掉旧草稿。

### 5.7 交卷

```
POST /reading/records/{recordId}/submit
```

```json
{ "durationSeconds": 600, "idempotencyKey": "reading-2095405786495315999-submit" }
```

阅读的交卷请求里**没有 `finalAnswers`、`baseVersion`、`clientSequence`** —— 答案必须在交卷前已经保存过。响应为完整报告（同 5.8），不是摘要。

### 5.8 报告

```
GET /reading/records/{recordId}/report
```

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "reportId": 2095405786495315999,
    "recordId": 2095405786495315999,
    "paperId": 2095405786495315969,
    "sectionMapping": "SEC_READ",
    "section": "1",
    "status": 3,
    "reportStatus": "READY",
    "totalQuestionCount": 10,
    "answeredCount": 10,
    "correctCount": 8,
    "wrongCount": 2,
    "accuracyRate": 80.00,
    "durationSeconds": 600,
    "submittedTime": 1789612800000,
    "items": [
      {
        "answerId": 2095405786495316400,
        "questionId": 2095405786495316201,
        "questionNumber": 1,
        "typeId": "reading_choice",
        "typeIdMapping": "reading_choice",
        "userAnswer": "A",
        "standardAnswer": "A",
        "answered": true,
        "correct": true,
        "points": 1.00,
        "analysis": "……",
        "questionSnapshot": { },
        "groupSnapshot": null,
        "optionSnapshot": [ ]
      }
    ]
  }
}
```

| 字段 | 说明 |
|---|---|
| `accuracyRate` | **BigDecimal**（听力是 Integer），如 `80.00` |
| `items[]` | 逐题明细，直接返回完整报告，不需要再调单题接口 |
| `questionSnapshot` / `groupSnapshot` / `optionSnapshot` | 交卷时冻结的题目/题组/选项快照。**报告渲染优先用快照**，别再去拉 `/questions`（题库可能已改） |
| `wrongCount` | 错误 + 未作答 |

### 5.9 报告重试

```
POST /reading/records/{recordId}/report/retry
```

无 body，返回完整报告。仅 `FAILED_RETRYABLE` 可重试。

## 6. 写作（writing）

写作、翻译、口语三者**共用同一套记录表和同一套响应结构**（`practice_subjective_*`），只是 `section_mapping` 不同。所以这一节的字段表对三者都适用，第 7 节只写翻译的差异。

与听力/阅读最大的不同：**交卷时主观题只是入队，不是出分**。响应里 `status=COMPLETED` 但 `reportStatus` 可能还是 `GRADING`，需要轮询报告接口。

### 6.1 时序

```
POST /start {paperId, sectionMapping, section} ──► recordId
   │
   ├─ GET /{recordId}            恢复现场
   ├─ GET /{recordId}/questions  拉题（含 layout、promptHint 派生的作答区、已存答案、草稿）
   │
   ├─ PUT /{recordId}/questions/{questionId}/draft   草稿（每 2~5s 防抖，整份覆盖）
   ├─ PUT /{recordId}/answers                        正式保存（切题/离开页面时）
   │
POST /{recordId}/submit ──► 客观题即判，主观题入 AI 队列
   │
   ├─ GET /{recordId}/report                  轮询到 READY / FAILED
   ├─ GET /{recordId}/report/questions/{qid}  单题详情
   └─ POST /{recordId}/report/retry           FAILED 时重试
```

### 6.2 开练（三字段必填）

```
POST /writing/records/start
```

```json
{ "paperId": 2095405786495315969, "sectionMapping": "SEC_WRITE", "section": "1" }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `paperId` | Long | 是 | 试卷 ID |
| `sectionMapping` | String | **是** | 写作 `SEC_WRITE`、翻译 `SEC_TRANSLATION`、口语 `SEC_SPEAKING` |
| `section` | String | **是** | 板块号，取 U3 的 `parts[].section`（**要转成字符串**） |

🔴 **三个字段缺一不可**。只传 `paperId + section` 不够：HSK 3.0 综合卷上同一张卷的 `section=1` 同时存在听力、阅读、写作、翻译、口语五个板块，必须靠 `sectionMapping` 定位。传错 mapping（比如拿写作的 mapping 打翻译入口）返回 `400 SECTION_MAPPING_MISMATCH`。

**幂等**：同一 `(paperId, sectionMapping, section)` 已有进行中记录时直接返回，不新建。

响应 `data` 为记录详情，见 6.3。

### 6.3 记录详情

```
GET /writing/records/{recordId}
```

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 2095405786495315999,
    "paperId": 2095405786495315969,
    "sectionMapping": "SEC_WRITE",
    "section": "1",
    "levelCode": "3",
    "status": "IN_PROGRESS",
    "reportStatus": "NOT_READY",
    "totalQuestions": 2,
    "answeredCount": 1,
    "currentQuestionId": 2095405786495316201,
    "currentQuestionNumber": 1,
    "durationSeconds": 300,
    "objectiveCount": 0,
    "objectiveCorrectCount": 0,
    "aiQuestionCount": 2,
    "aiScoredCount": 0,
    "finalScore": null,
    "totalScore": null
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | String | `IN_PROGRESS` / `COMPLETED` / `DISCARDED`（**大写**；听力阅读那边是 Integer，别混） |
| `reportStatus` | String | `NOT_READY` / `GRADING` / `READY` / `FAILED` |
| `objectiveCount` / `objectiveCorrectCount` | Integer | 客观题数 / 客观题答对数 |
| `aiQuestionCount` / `aiScoredCount` | Integer | AI 题数 / AI 已评出分的题数 |
| `finalScore` / `totalScore` | BigDecimal | 得分 / 满分，评完才有值 |

轮询建议：`status=COMPLETED` 且 `reportStatus=GRADING` 时按 2s → 5s → 10s 退避轮询 `GET /{recordId}`，直到 `READY` 或 `FAILED`。

### 6.4 拉题

```
GET /writing/records/{recordId}/questions
```

```json
{
  "code": 200,
  "message": "操作成功",
  "data": [
    {
      "questionId": 2095405786495316201,
      "order": 1,
      "no": 1,
      "layout": "input",
      "typeName": "命题作文",
      "sectionTitle": "第一部分",
      "content": "<p>请以《我的周末》为题写一篇短文。</p>",
      "passage": null,
      "audioUrl": null,
      "shareAudioUrl": null,
      "optionContent": null,
      "groupContent": null,
      "groupPassage": null,
      "groupOptionContent": null,
      "hasStandardAnswer": 0,
      "answered": false,
      "answerText": null,
      "answer": null,
      "durationMs": null,
      "answerDraft": {
        "text": "我上周去了公园……",
        "graphemeCount": 12,
        "version": 3,
        "savedTime": 1789612800000
      }
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `order` | Integer | 题序 = 题集下标 + 1，**答题卡和报告都用这个序** |
| `no` | Integer | 卷面题号，可能跳号，仅供展示 |
| `layout` | String | `input`（作文、笔译）/ `record`（口译、口语）/ `shortInput` 等，**渲染组件的唯一依据** |
| `content` / `passage` | String | 题干 / 材料，可能是 HTML，**渲染时需白名单过滤** |
| `hasStandardAnswer` | Integer | `1` 客观题（交卷即判）/ `0` 主观题（交 AI） |
| `answered` / `answerText` / `answer` | — | 已存答案回填；`answerText` 是文本，`answer` 是音频 URL |
| `answerDraft` | Object/null | 草稿，`null` 表示从未存过。结构见 6.5 |

> `optionContent` / `groupOptionContent` 是原样透传的对象（`Map<String,Object>`），主观模块用得少；口语与口译常常整块为 `null`。

### 6.5 草稿保存

```
PUT /writing/records/{recordId}/questions/{questionId}/draft
```

```json
{ "text": "我上周去了公园……", "expectedVersion": 3 }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | String | 是 | **整份草稿内容**。`PUT` 语义 = 覆盖，不做按键增量合并。传 `""` 表示清空 |
| `expectedVersion` | Long | 否 | 上次拿到的 `version`。传了就做乐观锁，不传则强制覆盖 |

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { "questionId": 2095405786495316201, "version": 4, "savedTime": 1789612800000, "graphemeCount": 412 }
}
```

**三个必须知道的行为**：

1. **同内容重复保存不增版本、不写库** —— 返回的 `version` 与上次相同，可以放心按 2~5s 防抖调。
2. **草稿不等于答案**。存草稿不置 `answered`、不判分。**交卷前必须再走一次 6.6 批量保存**，把编辑器内容落成正式答案。服务端不拿草稿兜底，只会在交卷响应里回 `draftNotSubmitted` 点名哪些题有草稿但没提交。
3. **字数上限**：写作与笔译 5000 字素（不含空白），超了返回 `400 DRAFT_TOO_LONG`，不会静默截断。口语与口译的草稿（提纲）不限。

失败形态：

| 情况 | code | message | data |
|---|---|---|---|
| 记录已交卷 | `409` | `DRAFT_LOCKED` | `null` |
| 版本冲突 | `409` | `DRAFT_VERSION_CONFLICT` | `{currentVersion, savedTime}` |
| 题不在本次题集 | `2001` | `试题不存在` | `null` |
| 超字数 | `400` | `DRAFT_TOO_LONG` | `null` |

### 6.6 批量保存答案

```
PUT /writing/records/{recordId}/answers
```

```json
{
  "answers": [
    { "questionId": 2095405786495316201, "answerText": "我上周去了公园……", "answerVersion": 2 }
  ],
  "currentQuestionId": 2095405786495316201
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `answers[].answerText` | String | 文本作答：写作正文 / 笔译译文 / 口语转写 |
| `answers[].answer` | String | 音频 URL：口语 / 口译。与 `answerText` 按模块分工，不互斥 |
| `answers[].durationMs` | Long | 录音时长（毫秒），音频作答时填 |
| `answers[].answerVersion` | Long | 客户端持有的答案版本，用于并发冲突检测；**可空，空则不做版本校验** |
| `currentQuestionId` | Long | 当前题，用于续练定位；缺省不更新进度 |

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 2095405786495315999,
    "answeredCount": 1,
    "currentQuestionId": 2095405786495316201,
    "currentQuestionNumber": 1,
    "answers": [ { "questionId": 2095405786495316201, "answerVersion": 3 } ]
  }
}
```

返回里只回「存了哪些题 + 新版本号」，判分结果交卷后才可见。下次保存时把 `answerVersion` 带回来做冲突检测。

### 6.7 交卷

```
POST /writing/records/{recordId}/submit
```

```json
{
  "finalAnswers": [
    { "questionId": 2095405786495316201, "answerText": "我上周去了公园……" }
  ],
  "durationSeconds": 900
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `finalAnswers` | Array | 交卷这一刻的最后一批作答，**可为空**（前面已逐题存过） |
| `durationSeconds` | Integer | 客户端上报的答题秒数；缺省按 `end_time - start_time` 现算 |
| `idempotencyKey` | String | 兼容旧前端的提示字段，**服务端忽略其值**，幂等键自拼为 `writing-{recordId}-submit` |

body 整体可以省略（`@RequestBody(required=false)`）。

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 2095405786495315999,
    "paperId": 2095405786495315969,
    "module": "writing",
    "status": "COMPLETED",
    "reportStatus": "GRADING",
    "totalQuestions": 2,
    "answeredCount": 2,
    "objectiveCount": 0,
    "objectiveCorrectCount": 0,
    "aiQuestionCount": 2,
    "aiScoredCount": 0,
    "finalScore": null,
    "totalScore": null,
    "idempotencyKey": "writing-2095405786495315999-submit",
    "draftNotSubmitted": [2095405786495316202]
  }
}
```

🔴 **两个状态别混**：`status` = 记录状态（交完就是 `COMPLETED`）；`reportStatus` = 出结果进度（AI 还在评就是 `GRADING`）。

🔴 **`draftNotSubmitted`**：数组，列出「有草稿但没提交成答案」的题目 ID。非空时说明用户写了但没保存正式答案 —— 前端应提示，不要静默丢弃。

### 6.8 报告

```
GET /writing/records/{recordId}/report
```

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 2095405786495315999,
    "paperId": 2095405786495315969,
    "module": "writing",
    "sectionMapping": "SEC_WRITE",
    "section": "1",
    "reportStatus": "READY",
    "totalQuestions": 2,
    "answeredCount": 2,
    "objectiveCount": 0,
    "objectiveCorrectCount": 0,
    "aiQuestionCount": 2,
    "aiScoredCount": 2,
    "finalScore": 78.50,
    "totalScore": 100.00,
    "durationSeconds": 900,
    "startTime": 1789612000000,
    "endTime": 1789612900000,
    "questions": [
      {
        "order": 1,
        "questionId": 2095405786495316201,
        "layout": "input",
        "hasStandardAnswer": 0,
        "answered": true,
        "gradingState": 1,
        "points": 39.25,
        "maxScore": 50.00,
        "isFullScore": 0,
        "correct": null
      }
    ]
  }
}
```

| 字段 | 说明 |
|---|---|
| `reportStatus` | `GRADING`（还有题没评完）/ `READY`（全部终态且至少有一题评出分）/ `FAILED`（全部终态但一题都没评出来）/ `NOT_READY`（未交卷） |
| `questions[].gradingState` | `0` 待评 / `1` 已评 / `2` 未作答或评分失败 |
| `questions[].correct` | **仅客观题（`hasStandardAnswer=1`）有值**，主观题恒 `null` —— 主观表没有 `is_correct` 列，客观对错由 `points` 与 `maxScore` 现算 |
| `questions[].isFullScore` | `1` 满分 / `0` 非满分 |
| `startTime` / `endTime` | 毫秒时间戳 |

**没有 `reportId`** —— 报告是 `record + answer` 现拼的，不存在报告表。

### 6.10 单题详情

```
GET /writing/records/{recordId}/report/questions/{questionId}
```

```json
{
  "order": 1,
  "questionId": 2095405786495316201,
  "layout": "input",
  "hasStandardAnswer": 0,
  "answered": true,
  "gradingState": 1,
  "points": 39.25,
  "maxScore": 50.00,
  "isFullScore": 0,
  "correct": null,
  "analysis": "文章结构完整，词汇使用较丰富，但……",
  "standardAnswer": null,
  "answerText": "我上周去了公园……",
  "answer": null,
  "snapshot": { "content": "<p>请以《我的周末》为题……</p>" }
}
```

| 字段 | 说明 |
|---|---|
| `analysis` | 主观题是 AI 点评，客观题是题目解析 |
| `standardAnswer` | 客观题给前端展示「正确答案」，**主观题通常为空** |
| `snapshot` | 交卷时冻结的题目快照（题干/题组/选项），渲染用这个，不要重拉题目 |

### 6.11 报告重试

```
POST /writing/records/{recordId}/report/retry
```

无 body。把 `grading_state=2` 且 `answered=1` 的题重置为待评、评分次数归零，重新入队。响应是**记录详情**（不是报告）：

```json
{ "code": 200, "message": "操作成功", "data": { "recordId": 2095405786495315999, "reportStatus": "GRADING" } }
```

### 6.12 答题卡

```
GET /writing/records/{recordId}/answer-card
```

结构见 [9. 答题卡](#9-答题卡五模块共用)。

---

## 7. 翻译（translation）

**与写作完全同构**，落同一张表，`section_mapping = SEC_TRANSLATION`。只有下面四处差异：

### 7.1 差异清单

| 项 | 写作 | 翻译 |
|---|---|---|
| 开练 `sectionMapping` | `SEC_WRITE` | `SEC_TRANSLATION` |
| 交卷路名 | `POST /{id}/submit` | **`POST /{id}/submissions`**（复数） |
| 报告重试 | 有 | **无此端点** |
| 板块含义 | `section=1` 写作 | `section=1` 笔译（`layout=input`）<br>`section=2` 口译（`layout=record`） |

⚠️ 交卷路名不一致是历史契约（写作 `/submit`、翻译 `/submissions`），**不是笔误**，前端不要统一。

### 7.2 端点清单

| 动作 | 端点 |
|---|---|
| 开练 | `POST /translation/records/start` |
| 记录详情 | `GET /translation/records/{recordId}` |
| 拉题 | `GET /translation/records/{recordId}/questions` |
| 批量保存 | `PUT /translation/records/{recordId}/answers` |
| 草稿 | `PUT /translation/records/{recordId}/questions/{questionId}/draft` |
| 交卷 | `POST /translation/records/{recordId}/submissions` |
| 报告 | `GET /translation/records/{recordId}/report` |
| 单题详情 | `GET /translation/records/{recordId}/report/questions/{questionId}` |
| 答题卡 | `GET /translation/records/{recordId}/answer-card` |

请求/响应体全部同第 6 章。`module` 字段返回 `translation`。

### 7.3 笔译与口译

同一个模块下两套作答形态，靠 `section` 区分：

| section | 形态 | `layout` | 作答字段 |
|---|---|---|---|
| `1` | 笔译 | `input` | `answerText`（译文文本） |
| `2` | 口译 | `record` | `answer`（音频 URL）+ `durationMs` |

口译的录音流程与口语相同，见 8.5。

### 7.4 交卷示例

```
POST /translation/records/{recordId}/submissions
```

```json
{ "finalAnswers": [ { "questionId": 2095405786495316201, "answerText": "译文内容……" } ], "durationSeconds": 600 }
```

响应结构同 6.7，`module` 为 `translation`。

---
## 8. 口语（speaking）

与写作同表同链路，三处不同：

1. **题源双份** —— HSK 7-9 口语题来自 `question` 表，2.0/3.0 口语试卷题来自 `speaking_exam_paper_question`。前端不需要区分，服务端拍平成同一个响应。
2. **作答是音频** —— 落 `answer`（音频 URL）+ `durationMs`，不是文本。
3. **全部 AI 判分** —— 口语试卷题没有标准答案，`hasStandardAnswer` 恒 `0`。

### 8.1 时序

```
POST /start ──► recordId
   │
   ├─ GET /{recordId}            恢复现场
   ├─ GET /{recordId}/questions  拉题（layout 恒 record，音频/题目内容见字段）
   │
   ├─ PUT /{recordId}/questions/{questionId}/draft      提纲草稿（可选，只存文字）
   ├─ POST /{recordId}/questions/{questionId}/answers   录音上传完成后落答案
   │
POST /{recordId}/submit ──► 全部入 AI 队列
   │
   ├─ GET /{recordId}/report                  轮询到 READY / FAILED
   ├─ GET /{recordId}/report/questions/{qid}  单题详情
   └─ POST /{recordId}/report/retry           FAILED 时重试
```

### 8.2 开练

```
POST /speaking/records/start
```

```json
{ "paperId": 2095405786495315969, "sectionMapping": "SEC_SPEAKING", "section": "1" }
```

`sectionMapping` 传 `SEC_SPEAKING`。历史值 `SEC_SPEAK` 服务端仍放行，但**响应里返回的永远是 `SEC_SPEAKING`**，前端按返回值为准。

响应结构同 6.3。

### 8.3 记录详情

`GET /speaking/records/{recordId}`，结构同 6.3，`sectionMapping` 为 `SEC_SPEAKING`，`objectiveCount` 恒 `0`、`aiQuestionCount` = 总题数。

### 8.4 拉题

```
GET /speaking/records/{recordId}/questions
```

```json
{
  "code": 200,
  "message": "操作成功",
  "data": [
    {
      "questionId": 2095405786495316201,
      "order": 1,
      "no": 1,
      "layout": "record",
      "typeName": "朗读",
      "sectionTitle": "第一部分",
      "content": "<p>请朗读下面的短文。</p>",
      "passage": "春天来了，公园里的花都开了……",
      "audioUrl": null,
      "shareAudioUrl": null,
      "optionContent": null,
      "groupContent": null,
      "groupPassage": null,
      "groupOptionContent": null,
      "hasStandardAnswer": 0,
      "answered": false,
      "answerText": null,
      "answer": null,
      "durationMs": null,
      "answerDraft": null
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `layout` | **恒 `record`**。口语试卷题源没有 layout 列，服务端固定下发 `record` |
| `passage` | 朗读/复述的原文本。口语题**常常没有 `content`，题目本体在 `passage`** —— 前端渲染时要兜底，`content` 为空就用 `passage` |
| `audioUrl` | 听力材料音频（如「听一段话然后回答」） |
| `shareAudioUrl` | 共享材料音频 |
| `hasStandardAnswer` | 恒 `0` |
| `sectionTitle` | 板块标题，用于分节展示 |

### 8.5 录音与保存答案

```
POST /speaking/records/{recordId}/questions/{questionId}/answers
```

```json
{ "answer": "https://cdn.example.com/speaking/u123/q456.wav", "durationMs": 45000 }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `answer` | String | 是 | 音频 URL。**路径里的 `questionId` 会自动覆盖 body 里的同名字段**，body 不用传 |
| `durationMs` | Long | 是 | 录音时长（毫秒） |
| `answerText` | String | 否 | 转写文本，一般留空由 AI 转写 |

🔴 **录音预签名端点已停用**（2026-11-13，媒体服务 `speaking_media_object` 下线）：

| 端点 | 状态 |
|---|---|
| `POST /speaking/attempts/{id}/questions/{qid}/recordings/prepare` | ❌ 已注销（404） |
| `POST /speaking/recordings/{id}/confirm` | ❌ 已注销 |
| `POST /speaking/recordings/{id}/retry` | ❌ 已注销 |
| `POST /speaking/recordings/{id}/discard` | ❌ 已注销 |
| `GET /speaking/recordings/{id}/playback-url` | ❌ 已注销 |

现在的流程是**客户端自行录音 → 上传到对象存储拿到 URL → 调上面这个接口把 URL 落库**。服务端只存 URL，不校验可达性、不转码、不托管音频。

> 如果你的客户端还在调 `/recordings/prepare`，会拿到 404 —— 这是预期行为，不是接口挂了。旧的 `/speaking/attempts/**` 系列端点在 2026-11-16 整体退场（决策 24），代码保留但 `@RestController` 已注释。

响应同 6.6 的批量保存响应（只落这一题）。

**重录**：直接再调一次同一接口，`answer` 覆盖为新的 URL，`durationMs` 一起更新，`answered` 保持 `1`。

### 8.6 提纲草稿

```
PUT /speaking/records/{recordId}/questions/{questionId}/draft
```

```json
{ "text": "1. 开头问好 2. 介绍家乡 3. 结尾邀请", "expectedVersion": 2 }
```

- 只存**提纲文字**，不碰音频，不计入答案，不影响判分。
- 不限字数（口语的作答本体是录音，草稿只是辅助记事）。
- 🔴 **不要把提纲写进 `answerText`** —— 那会被 AI 当成转写文本来评分。

响应与失败形态同 6.5。

### 8.7 交卷

```
POST /speaking/records/{recordId}/submit
```

```json
{ "finalAnswers": [ { "questionId": 2095405786495316201, "answer": "https://…", "durationMs": 45000 } ], "durationSeconds": 600 }
```

body 可省略。响应同 6.7，`module` 为 `speaking`，`status=COMPLETED`、`reportStatus=GRADING`。

交卷时**未录音的题**会被标记为未作答（`grading_state=2`），最终报告里计入未得分，不会阻塞其他题的评分。

### 8.8 报告

`GET /speaking/records/{recordId}/report`，结构同 6.8，`module=speaking`。

口语的 `aiQuestionCount` = 全部题数，没有客观题。`questions[].correct` 恒 `null`。

### 8.9 报告重试

`POST /speaking/records/{recordId}/report/retry`，行为同 6.11。

### 8.10 答题卡

`GET /speaking/records/{recordId}/answer-card`，`answered` = **录音已上传完成**。结构见第 9 章。

---

## 9. 答题卡（五模块共用）

五个模块各有一条，路径规律一致：

```
GET /listening/records/{recordId}/answer-card
GET /reading/records/{recordId}/answer-card
GET /writing/records/{recordId}/answer-card
GET /translation/records/{recordId}/answer-card
GET /speaking/records/{recordId}/answer-card
```

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `recordId` | path | 是 | 记录 ID（听/读与写/译/说的 ID 体系不同，见 1.5） |
| `currentQuestionNumber` | query | 否 | 当前题号，缺省取记录里保存的进度 |

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": 2095405786495315999,
    "paperId": 2095405786495315969,
    "section": 1,
    "totalQuestions": 10,
    "answeredCount": 4,
    "unansweredCount": 6,
    "currentQuestionNumber": 5,
    "questions": [
      { "order": 1, "questionId": 2095405786495316201, "answered": true,  "current": false },
      { "order": 2, "questionId": 2095405786495316202, "answered": false, "current": false }
    ]
  }
}
```

| 字段 | 说明 |
|---|---|
| `section` | **Integer**（答题卡这里给数字，与开练的 String 不同） |
| `unansweredCount` | = `totalQuestions - answeredCount` |
| `currentQuestionNumber` | 未开始时为 `null` |
| `questions[].order` | 题序，与报告 `questions[].order` 同源同序 |
| `questions[].current` | 是否当前题，与 `currentQuestionNumber` 同值 |
| `questions[].answered` | 听/读看是否选过；写/译看是否存过答案；口语看录音是否已上传 |

答题卡**只回「答没答」**，不下发对错、不支持标记/收藏/错题筛选。对错只在交卷后的报告接口出现。

---

## 10. 状态机与轮询

### 10.1 记录状态

**听力 / 阅读**（`status` 是 Integer）：

```
0 已创建 ──► 1 进行中 ──► 3 已提交
                └──► 2 已放弃（仅阅读有 abandon）
```

**写作 / 翻译 / 口语**（`status` 是 String）：

```
IN_PROGRESS ──► COMPLETED
      └──► DISCARDED
```

### 10.2 出报告进度（`reportStatus`）

按模块分两套，**前端要分别处理**：

| 模块 | 值域 | 谁产出 |
|---|---|---|
| 听力 / 阅读（记录接口） | `PENDING` / `GENERATING` / `READY` / `FAILED` | 异步任务 |
| 听力 / 阅读（报告接口） | `PROCESSING` / `READY` / `FAILED_RETRYABLE` / `FAILED_FINAL` | 报告服务 |
| 写作 / 翻译 / 口语 | `NOT_READY` / `GRADING` / `READY` / `FAILED` | 按答案表 `grading_state` 现算 |

主观三模块的判定规则：

| 状态 | 条件 |
|---|---|
| `NOT_READY` | 未交卷 |
| `GRADING` | 已交卷，还有题 `grading_state=0`（待评） |
| `READY` | 全部终态，且至少有一题评出分 |
| `FAILED` | 全部终态，但**一题都没评出来** |

### 10.3 轮询建议

| 场景 | 建议 |
|---|---|
| 听力 / 阅读交卷 | 交卷响应已是 `READY`，直接跳报告页，无需轮询 |
| 写 / 译 / 说交卷 | 2s → 5s → 10s → 10s… 退避轮询 `GET /{recordId}`，30s 后转「后台生成中，稍后到报告页查看」 |
| 见到 `FAILED` | 展示「重试」按钮 → `POST /{recordId}/report/retry` |
| 报告页停留 | 每 10s 拉一次 `GET /{recordId}/report`，`READY` 即停 |

服务端 AI 评分的总开关默认**关闭**（`subjective.grading.enabled=false`）：开关关着时交卷照常，主观题停在「待评」，报告一直是 `GRADING`。**联调时如果一直等不到分数，先问后端这个开关开了没**，不是前端的问题。

---

## 11. 通用坑清单

### 11.1 19 位长整数精度丢失

`paperId`、`recordId`、`questionId` 都是 19 位 Long（如 `2095405786495315969`），超过 JavaScript `Number.MAX_SAFE_INTEGER`（`9007199254740991`，16 位）。

```js
JSON.parse('{"paperId":2095405786495315969}').paperId  // 2095405786495316000 ← 尾数被抹平
```

后果：拿这个 ID 去查卷会查不到（返回空或 404），而且**不报错**，非常难查。

三种解法，任选其一：

1. 让后端统一加 `@JsonSerialize(using = ToStringSerializer.class)`，ID 一律以字符串下发（**推荐**，但需要后端改）
2. 前端用 `json-bigint` 之类的库解析
3. 前端自行把 19 位数字当字符串处理，不参与数值运算

发请求时 ID 用字符串也不会报错（Spring 会自动转 Long）。

### 11.2 layout 取值

`layout` 是**答题交互的唯一真源**，不要在客户端按 `typeCode` / `typeName` 去猜该渲染什么组件。

| layout | 交互 | 出现在 |
|---|---|---|
| `imageJudge` | 看图判断（✓/✗） | 听力 |
| `imageChoice` | 看图选图 | 听力 |
| `imageMatch` | 看图连线/匹配 | 听力 |
| `textJudge` | 文字判断（✓/✗） | 听力 |
| `textChoice` | 文字选择 | 听力、阅读 |
| `textChoice_shareAudio` | 文字选择 + 共享音频 | 听力 |
| `passageGroup` | 长材料多子题 | 听力 |
| `input` | 文本输入 | 写作、笔译 |
| `shortInput` | 短文本输入 | 写作 |
| `record` | 录音 | 口语、口译 |

判断题的作答值用 `A`/`B`（表示 ✓/✗），**不要传 `true`/`false`**。

### 11.3 下划线字段

只有听力拉题和听力单题回顾这两个接口有下划线字段：

| 字段 | 出现在 |
|---|---|
| `audio_url` | `ListeningQuestionResponse`、`ListeningQuestionReportResponse` |
| `option_content` | 同上 |
| `share_audio_url` | 同上 |

其余所有接口、所有字段都是驼峰。阅读用的是 `audioUrl` / `optionContent` / `shareAudioUrl`。

### 11.4 选项结构两层不一致

| 模块 | 字段 | 取法 |
|---|---|---|
| 听力 | `option_content` | `data[i].option_content.A` |
| 阅读 | `optionContent` | `data[i].optionContent.options.A` |
| 写/译/说 | `optionContent` | 原样透传，通常为 `null` |

阅读多一层 `options` 包裹，这是 DTO 类型不同导致的，前端不能复用同一段渲染逻辑。

### 11.5 HTML 富文本

`content`、`passage`、`analysis` 里可能是 HTML（`<p>`、`<img>`、`<b>`、上下标等）。渲染时用白名单过滤（`p/br/img/b/i/u/span/div/a/sub/sup/table/...`），**不要用 `<[^>]*>` 一刀切** —— 数学题面里的 `H<0`、`$a<b<0$` 会被整段吞掉。

### 11.6 recordId 不通用

听力/阅读的 `recordId` 来自 `practice_record`，写作/翻译/口语的来自 `practice_subjective_record`。两套 ID 空间独立，拿错了返回 `403 FORBIDDEN`（不是 404）。

---

## 12. 联调 checklist

按顺序过一遍，能覆盖 90% 的问题：

- [ ] 请求带 `X-Client-Type: APP` 且 token 有效（否则会静默用 `userId=1` 的模拟用户）
- [ ] 成功判定用 `body.code === 200`，不是 HTTP 状态码
- [ ] `module` 传小写（大小写不敏感，但别传 `LISTENING` 之外的怪值）
- [ ] U3 的 `parts[].section`（数字）→ 开练的 `section`（字符串），中间转了一次
- [ ] 主观模块开练传全三字段 `paperId + sectionMapping + section`
- [ ] 翻译交卷是 `/submissions`（复数），写作是 `/submit`
- [ ] 听力取 `option_content`，阅读取 `optionContent.options`
- [ ] 听力取 `audio_url`，阅读取 `audioUrl`
- [ ] 19 位 ID 没有在 JS 里被当数字解析
- [ ] 写/译/说交卷后轮询的是 `reportStatus`，不是 `status`
- [ ] 交卷前把草稿落成正式答案（否则 `draftNotSubmitted` 会点名）
- [ ] 口语不再调 `/recordings/prepare`（已 404）

---

## 附录 A 错误码

### A.1 通用

| code | message | 场景 |
|---|---|---|
| `200` | 操作成功 | 成功 |
| `400` | 参数错误 | 参数校验失败，`message` 带字段名与中文说明 |
| `401` | 未登录或Token无效 | 缺 token / token 过期 / 未带 `X-Client-Type: APP` 且接口强制鉴权 |
| `403` | FORBIDDEN | 记录不属于当前用户、或用错模块的 recordId |
| `404` | 试卷不存在 / 板块不存在 | `paperId` 查不到，或该模块在该卷下没有板块（`version` 与卷不符也走这条） |
| `500` | 系统内部错误 | 服务端异常，需带上 traceId 找后端 |

### A.2 练习业务

| code | message | 场景 | 前端处理 |
|---|---|---|---|
| `2001` | 试题不存在 | 题目不在本次题集内 | 刷新题目列表 |
| `2003` | 记录版本冲突，请刷新后重试 | `baseVersion` 与云端不一致 | 重新拉记录，重放本地答案 |
| `2004` | 记录不在进行中，无法保存 | 记录已交卷 / 已放弃 | 跳报告页 |
| `2005` | 记录未提交，无法查看报告 | 未交卷就看报告 | 回答题页 |
| `2006` | 报告状态不允许重试 | 非 `FAILED_RETRYABLE` 调了 retry | 隐藏重试按钮 |

### A.3 目录与开练

| code | message | 场景 |
|---|---|---|
| `400` | `PRACTICE_VERSION_INVALID` | `version` 不是 `HSK2.0` / `HSK3.0` |
| `400` | `模块编码不合法（PRACTICE_MODULE_INVALID）：xxx` | U1/U2/U3 的 `module` 缺失或不在五个取值内 |
| `400` | `SECTION_MAPPING_MISMATCH` | 开练的 `sectionMapping` 与入口模块不符（如拿写作的 mapping 打翻译入口） |
| `400` | `section 不能为空` | `GET /papers/{paperId}/reports/latest` 没传 `section` |

### A.4 草稿

| code | message | 场景 | data |
|---|---|---|---|
| `400` | `DRAFT_TOO_LONG` | 写作/笔译草稿超 5000 字素 | `null` |
| `409` | `DRAFT_LOCKED` | 交卷后再存草稿 | `null` |
| `409` | `DRAFT_VERSION_CONFLICT` | `expectedVersion` 与当前不符 | `{currentVersion, savedTime}` |
| `409` | 请求数据已存在，请勿重复提交 | 并发首存撞唯一键（服务端已自动退化为更新，正常不会出现） | `null` |

> `message` 是**错误码字符串**（如 `DRAFT_LOCKED`）而非中文，前端按 `code` + `message` 组合映射文案，不要把 `message` 直接展示给用户。

---

## 附录 B 端点总表

共 57 个端点（不含内部接口）。

### 目录（5）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/hsk/modules` | 首页模块卡（免登录） |
| GET | `/hsk/levels` | U1 等级概览 + 卷列表 |
| GET | `/hsk/levels/{level}/intro` | U2 备考说明 |
| GET | `/hsk/papers/{paperId}/parts` | U3 卷内板块 + 进度 |
| GET | `/papers/{paperId}/reports/latest` | CR 板块最近报告 |

### 听力（11）

| 方法 | 路径 |
|---|---|
| POST | `/listening/records/start` |
| GET | `/listening/records/{recordId}` |
| GET | `/listening/records/{recordId}/questions` |
| PUT | `/listening/records/{recordId}/answers/{questionId}` |
| PUT | `/listening/records/{recordId}/answers` |
| POST | `/listening/records/{recordId}/pause` |
| POST | `/listening/records/{recordId}/submit` |
| GET | `/listening/records/{recordId}/report` |
| POST | `/listening/records/{recordId}/report/retry` |
| GET | `/listening/records/{recordId}/report/questions/{questionId}` |
| GET | `/listening/records/{recordId}/answer-card` |

### 阅读（12）

| 方法 | 路径 |
|---|---|
| POST | `/reading/records/start` |
| GET | `/reading/records/{recordId}` |
| GET | `/reading/records/{recordId}/questions` |
| PUT | `/reading/records/{recordId}/answers/{questionId}` |
| PUT | `/reading/records/{recordId}/answers` |
| POST | `/reading/records/{recordId}/pause` |
| POST | `/reading/records/{recordId}/abandon` |
| POST | `/reading/records/{recordId}/submit` |
| GET | `/reading/records/{recordId}/report` |
| POST | `/reading/records/{recordId}/report/retry` |
| GET | `/reading/records/{recordId}/report/questions/{questionId}` |
| GET | `/reading/records/{recordId}/answer-card` |

### 写作（9）

| 方法 | 路径 |
|---|---|
| POST | `/writing/records/start` |
| GET | `/writing/records/{recordId}` |
| GET | `/writing/records/{recordId}/questions` |
| PUT | `/writing/records/{recordId}/answers` |
| PUT | `/writing/records/{recordId}/questions/{questionId}/draft` |
| POST | `/writing/records/{recordId}/submit` |
| GET | `/writing/records/{recordId}/report` |
| GET | `/writing/records/{recordId}/report/questions/{questionId}` |
| POST | `/writing/records/{recordId}/report/retry` |
| GET | `/writing/records/{recordId}/answer-card` |

### 翻译（9）

| 方法 | 路径 |
|---|---|
| POST | `/translation/records/start` |
| GET | `/translation/records/{recordId}` |
| GET | `/translation/records/{recordId}/questions` |
| PUT | `/translation/records/{recordId}/answers` |
| PUT | `/translation/records/{recordId}/questions/{questionId}/draft` |
| POST | `/translation/records/{recordId}/submissions` |
| GET | `/translation/records/{recordId}/report` |
| GET | `/translation/records/{recordId}/report/questions/{questionId}` |
| GET | `/translation/records/{recordId}/answer-card` |

### 口语（9）

| 方法 | 路径 |
|---|---|
| POST | `/speaking/records/start` |
| GET | `/speaking/records/{recordId}` |
| GET | `/speaking/records/{recordId}/questions` |
| POST | `/speaking/records/{recordId}/questions/{questionId}/answers` |
| PUT | `/speaking/records/{recordId}/questions/{questionId}/draft` |
| POST | `/speaking/records/{recordId}/submit` |
| GET | `/speaking/records/{recordId}/report` |
| GET | `/speaking/records/{recordId}/report/questions/{questionId}` |
| POST | `/speaking/records/{recordId}/report/retry` |
| GET | `/speaking/records/{recordId}/answer-card` |

小计：目录 5、听力 11、阅读 12、写作 10、翻译 9、口语 10，合计 **57** 个（答题卡已算进各自模块）。
写作、口语有重试端点而翻译没有；阅读多一条 `abandon`，口语与翻译的答题走单题接口。

---

## 附录 C 已退场端点（不要再调）

以下端点在 2026-11-11 ~ 11-16 陆续退场，代码保留但 `@RestController` 已注释，**请求会 404**：

| 端点 | 退场时间 | 替代 |
|---|---|---|
| `/listening/levels`、`/reading/levels`、`/writing/levels` 等 15 个模块内目录 | 2026-11-11 | `GET /hsk/levels`、`GET /hsk/papers/{id}/parts` |
| `/writing/attempts/**` | 2026-11-16 | `/writing/records/**` |
| `/translation/attempts/**` | 2026-11-16 | `/translation/records/**` |
| `/speaking/attempts/**` | 2026-11-16 | `/speaking/records/**` |
| `/writing/reports/**`、`/translation/reports/**`、`/speaking/reports/**` | 2026-11-16 | `/{mod}/records/{recordId}/report` |
| `/speaking/recordings/**`（含 `prepare`） | 2026-11-13 | 客户端自传音频后调 `POST /speaking/records/{id}/questions/{qid}/answers` |
| `/listening/parts/{structureId}/reports/latest` 等 4 条 | 2026-11-11 | `GET /papers/{paperId}/reports/latest` |

没有兼容层，全部直接 404。如果前端代码里还有这些路径，需要同批改掉。
