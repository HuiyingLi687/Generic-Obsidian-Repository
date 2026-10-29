# CSCA 考试 · 接口设计文档（精简版）

> **状态**：v4.3 / 2026-10-24　**范围**：CSCA 考试主流程接口契约（入参 / 返回 / 错误码 / 约束）
> **依据**：TAPD wiki《CSCA考试》v1.3.0；格式对齐《CSCA练习-接口设计文档》
> **完整版**（设计论证、现状盘点、实测记录、改造清单、上线检查项）：`archive/CSCA考试-接口设计文档-v3.7-full.md`

**服务**：`exam-service`（`/api/exam/**`），前缀由网关转发。**科目字典**在 `system-service`，**错题本读写**在 `practice-service`。

---

## 0. 通用约定

### 0.1 返回包装

统一 `Result<T>`，**只有 `code` / `message` / `data`**，HTTP 状态码恒 `200`，业务结果看 `code`：

```json
{ "code": 200, "message": "操作成功", "data": { } }
```

- `data` 为 `null` 时字段仍保留
- **无例外**：本模块所有端点都套 `Result<T>`，**不返回文件流、不返回 `302`**

### 0.2 鉴权

| 项 | 要求 |
|---|---|
| 登录 | **全部端点必须登录**，未登录 → `401` |
| 客户端类型 | 必须带 `X-Client-Type: APP`（缺省会回落到默认用户，见下） |
| Token | `Authorization: Bearer xxx` → `X-Access-Token` → `?token=` |
| `userId` | **一律从 Token 取，不接受前端传入** |

> 🔴 **内部调用 auth 时（如资料校验）必须同时透传 `Authorization` 与 `X-Client-Type: APP`**：缺 `X-Client-Type` 不会 401，而是回落到 `getDefaultUserInfo()`（`userId` 恒 1），等于拿别人的资料做判定。

### 0.3 ID 序列化

`exam-service` **没有开 `Long → String`**：

| 端点类别 | id 类型 |
|---|---|
| 🔧 改造的现有端点 | **数字**（`Long`），保持老前端兼容 |
| 🆕 新增端点 | **`String`**（19 位雪花 id 前端不丢精度） |

> ⚠️ 同一个 `examRecordId`，在 CSCA 单题解析（§2.12）里是**字符串**、在 `/record/csca/{id}/result` 与 HSK 的 `/record/{paperId}/question/{questionId}` 里是**数字**，**前端按端点分别解析**。

### 0.4 错误码

本模块新开号段 **8101–8199**（`CSCA_*` 练习占 8001–8099，互不冲突）。

| 值 | 含义 | 触发 |
|---|---|---|
| 200 | 成功 | — |
| 400 | 参数错误 | 未细分的参数问题 |
| 401 | 未登录 / Token 无效 | — |
| 403 | 无权限 | `X-Client-Type` 非 `APP`；往非本人会话提交答案 |
| **8101** | 科目码非法 | `subjectTypeMapping` 不在考试 5 科内 |
| **8102** | 语言非法 / 该科目不支持 | 不在 `chinese`/`english`；中文科目传 `english` |
| **8103** | 该科目×语言暂无可用试卷 | 无卷；或卷在但 `exam_paper_structure` 无模板 |
| **8104** | 个人信息不完整 | 5 项：姓名 / 性别 / 国籍 / 出生年月日 / 手机号（不含邮箱）；`data.incompleteFields` 回中文名 |
| **8105** | 该科目次数不足 | `user_exam_quota(exam_type='CSCA', version='CSCA', level=<科目码>)` 该行 `remain_quota<=0`，或该科目没有配额行 |
| 8106 | （预留）需要扣点确认 | 本期不用 |
| **8107** | 会话不存在 | `examRecordId` 查不到 / 不是 CSCA 记录（**不含归属校验**） |
| **8108** | 会话已结束 | 已交卷的会话仍存答案 / 仍取卷 |
| **8109** | 会话已超时 | `now > start_time + duration*60000`（表无 `deadline_time` 列，须现算），本请求内已自动交卷 |
| **8110** | 题目不属于本卷 | `questionId` 不在会话题集内 |
| **8111** | 未交卷不能看报告 | `status=0` 请求报告 / 单题解析 |
| **8112** | 参数越界 | `pageSize>100` / `answer` 长度 `>64` |
| 500 | 服务端错误 | 未预期异常 |

> `8113`–`8116` 原分配给成绩单端点（已移除），**号段保留不复用**。

码表落地：`exam-service/.../exam/csca/support/CscaExamErrorCode`（模块自有，不进 `common`）。

---

## 1. 主流程

### 1.1 一次完整考试

```
T0  进首页        GET  /api/system/dict/code/csca_subject       5 科 + 顺序 + 默认项
                  GET  /record/csca/quota                      5 科次数角标
T1  点开始        POST /answer/start/csca                      → action=CREATE | RESUME
                  （内部：续考判定 → 资料/试卷/次数校验 → 建会话扣次数）
T2  拉整卷        GET  /answer/paper/csca/detail/{paperId}      → 48 或 80 题（不含答案/解析）
T3  逐题作答      POST /answer/submit/csca  ×N                  每题一次；带 examRecordId，服务端判对错且不回传
T4  收藏          POST /answer/csca/favorite                    可选
T5  看答题卡      GET  /answer/csca/card/detail/{paperId}       标记 + 收藏 + 剩余时间
T6  切后台        POST /record/{paperId}/leave                  暂离
T7  交卷确认      GET  /answer/checkSubmit/{paperId}            已答/未答
T8  交卷          POST /record/{recordId}/submit/csca            判分 + 错题本写入
T9  诊断报告      GET  /record/csca/{examRecordId}/result
T10 单题解析      GET  /record/csca/{examRecordId}/question/{questionId}   → 用户答案 / 标准答案 / 解析
```

### 1.2 端点总表（在用 16 + 不用 4）

记号：🔧 改造现端点 / ✅ 直接复用 / 🆕 新增 / ⛔ 本期不用 / ⚠️ 契约待实现（文档先定，代码未补）。

| # | 方法 | 路径 | 用途 | 处置 |
|---|---|---|---|---|
| 1 | GET | `/api/system/dict/code/csca_subject` | 科目卡（5 科 + 顺序 + 默认） | ✅ 复用（system） |
| 2 | GET | `/record/csca/quota` | 5 科剩余次数 | 🆕 |
| 3 | GET | `/api/auth/app/profile/check` | 资料完整性 5 项（开考硬门槛） | ✅ 复用（auth） |
| 4 | POST | `/answer/start/csca` | **开考唯一入口**：续考判定 + 校验 + 建会话扣次数 | 🔧 |
| 5 | GET | `/answer/paper/csca/detail/{paperId}` | 整卷 | 🔧 |
| 6 | POST | `/answer/submit/csca` | 逐题保存 + 服务端判对错 | 🆕 |
| 7 | POST | `/answer/csca/favorite` | 考试内收藏 | 🆕 |
| 8 | GET | `/answer/csca/card/detail/{paperId}` | 答题卡 | 🔧 |
| 9 | GET | `/answer/checkSubmit/{paperId}` | 交卷弹窗统计 | ✅ 复用 |
| 10 | POST | `/record/{paperId}/leave` | 暂离 | ✅ 复用 |
| 11 | POST | `/record/{recordId}/submit/csca` | 交卷 + 判分 + 错题本 | 🔧 |
| 12 | GET | `/record/csca/{examRecordId}/result` | 诊断报告 | 🔧 |
| 13 | GET | `/record/csca/{examRecordId}/question/{questionId}` | 单题解析（按会话，不按 paperId） | 🆕 |
| 14 | GET | `/record/user/records` | 模考记录列表（HSK/CSCA 共用） | ✅ 复用 |
| 15 | GET | `/api/practice/csca/wrong-book?source=exam` | 错题本（读） | ✅ 复用（practice） |
| 16 | DELETE | `/api/practice/csca/wrong-book/{questionId}` | 移出错题本 | ✅ 复用（practice） |
| ⛔ | POST | `/answer/submit` | 逐题保存（**HSK 专用**） | **CSCA 不用**：无归属/状态/超时校验，也不判分 |
| ⛔ | GET | `/record/{paperId}/question/{questionId}` | 单题解析（**HSK 专用**） | **CSCA 不用**：走 `paperId` 且 SQL 带 `user_id`，改走 #13 |
| ⛔ | POST | `/answer/batch` | 批量保存 | **不用**（前端零调用，实测 500） |
| ⛔ | POST | `/answer/statistics` | 答题统计 | **不用**（前端零调用） |

**科目目录与次数不新造接口**：科目走 `system-service` 字典，次数走现有的 `user_exam_quota`。

---

## 2. 接口详情

### 2.1 GET /record/csca/quota 🆕

**用途**：首页 5 科剩余次数角标。

**入参**：无（`userId` 从 Token 取）。

**返回**

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

**约束**

- 一次 `selectList` 取该用户全部 CSCA 配额行（`exam_type='CSCA'`），**固定按 文科中文 → 理科中文 → 数学 → 物理 → 化学 顺序**输出 5 条，缺行补 `0/0/0/false`。
- 顺序**必须自建常量列表**，不能依赖枚举声明顺序。
- 查不到任何行 → 5 条全 0，回 `200`（**不报 8105**）。
- 纯只读。

**错误码**：`401`。

---

### 2.2 GET /api/auth/app/profile/check — 资料完整性 ✅ 复用（auth-service）

**用途**：判断开考必需的 **5 项个人资料**是否齐全。`POST /answer/start/csca` **在内部调用它**（前端也可直接调，用于进个人中心前预判）。

**入参**：无（`userId` 从 Token 取）。

**请求头**

| 头 | 值 | 说明 |
|---|---|---|
| `Authorization` | 当前用户 Token | 内部调用**透传**，不换发 |
| `X-Client-Type` | `APP` | 🔴 必须带，见 §0.2 |

**返回**

```json
{
  "code": 200, "message": "操作成功",
  "data": { "completed": false, "incompleteFields": ["姓名", "手机号"] }
}
```

**5 项判定**（auth `AppUserService#checkProfileCompletion`，**不含邮箱**）：姓名 / 性别 / 国籍 / 出生年月日 / 手机号。`incompleteFields` 里已是**中文名**，前端直接展示，**不做二次映射**。

**约束**

- `completed=false` → 开考链路回 `8104`，`data.incompleteFields` 带同一份数组；**未建会话、未扣次数**。
- 超时 **1.5s**（连接 + 读取）；超时 / 5xx / `code≠200` → **fail-closed**：`500 用户资料校验服务暂不可用，请稍后重试`，**不放行**，也不冒用 `8104`。
- **不缓存**：「是否完整」秒级可变，缓存会让刚补完资料的考生仍被拦。
- 判定归 auth、**快照取值仍归 `UserClient`**（建会话时写 `real_name` / `gender` / `nationality` / `birthday`），两边不重复实现规则。
- HSK 分支不做此项拦截。

**错误码**：`401` / `500`。

---

### 2.3 POST /answer/start/csca 🔧

**用途**：**CSCA 开考唯一入口** —— 判定续考 / 建会话扣次数，并在此前完成资料、试卷、次数校验。原 `POST /answer/queryExamInProgress` **已废弃不用**，其续考判定并入本接口，CSCA 侧不存在「先查再开」两步调用。

**入参**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `userId` | Long | 是 | 由 Controller 从 Token 注入，**不接受前端传入** |
| `subjectTypeMapping` | String | 是 | `arts_chinese` / `science_chinese` / `math` / `physics` / `chemistry` |
| `languageVersion` | String | 是 | `chinese` / `english` |
| `version` | String | 否 | 缺省按 `CSCA` 归一；🔴 传字面 `null` 会让续考查询恒不成立 → 静默查不到 → 双开会话白扣次数 |

> CSCA 侧**没有** `level` / `examType` 入参，前端不要传：等级概念只属 HSK；CSCA 与 HSK 的区分只靠 `version=CSCA`，`exam_record` 表本身也没有 `exam_type` 列。

```json
{ "subjectTypeMapping": "math", "languageVersion": "chinese" }
```

**返回（CREATE · 新开会话）**

```json
{
  "code": 200, "message": "开始考试成功",
  "data": {
    "action": "CREATE",
    "recordId": 2101234567890123456, "paperId": 2101234567890123457,
    "status": 0, "startTime": 1760880320000,
    "deadlineTime": 1760883920000, "remainingSeconds": 3600,
    "durationMinutes": 60, "totalQuestions": 48, "totalScore": 100.00,
    "currentQuestionNumber": 1,
    "deductType": 0, "deductAmount": 0.00,
    "resumed": false, "deducted": true,
    "profileCheck": { "completed": true, "incompleteFields": [] },
    "paperCheck": { "available": true, "paperCount": 9, "reason": null },
    "quotaCheck": {
      "version": "CSCA",
      "totalQuota": 3, "usedQuota": 1, "remainQuota": 2, "hasQuota": true
    },
    "autoSubmitted": false
  }
}
```

**返回（RESUME · 续考）**

```json
{
  "code": 200, "message": "继续考试",
  "data": {
    "action": "RESUME",
    "recordId": 2101234567890123456, "paperId": 2101234567890123457,
    "status": 0, "startTime": 1760880320000,
    "deadlineTime": 1760883920000, "remainingSeconds": 812,
    "durationMinutes": 60, "totalQuestions": 48, "totalScore": 100.00,
    "currentQuestionNumber": 17,
    "deductType": 0, "deductAmount": 0.00,
    "resumed": true, "deducted": false,
    "profileCheck": null,
    "paperCheck": null,
    "quotaCheck": {
      "version": "CSCA",
      "totalQuota": 3, "usedQuota": 1, "remainQuota": 2, "hasQuota": true
    },
    "autoSubmitted": false
  }
}
```

`action`：`CREATE`（无进行中会话，本次已扣次数）/ `RESUME`（回原会话，`deducted=false`，`deductType`/`startTime`/`deadlineTime` 均为原值）。

🔴 **RESUME 时 `profileCheck` / `paperCheck` 恒为 `null`** —— 续考**不执行**资料与试卷校验，不能返回「已完成」的假状态；`quotaCheck` 仍是实时只读值，供角标显示。

`quotaCheck` 只回 `version` + 三档次数 + `hasQuota`，**不回 `examType` / `level`**（`examType` 恒为 CSCA、无信息量；科目前端入参已带）。

**服务端执行顺序（不可乱）**

| # | 步骤 | 结果 |
|---|---|---|
| 1 | 必填校验：`subjectTypeMapping` / `languageVersion` 非空（本接口 **CSCA 专用**，不判 HSK 分支） | `400` |
| 2 | 归一 `version='CSCA'`；校验科目码 / 语言码 | `8101` / `8102` |
| 3 | **续考查询**（🔴 **无锁只读**，事务外）：`user_id` + `status=0` + `deleted=0`，再按 `exam_paper` 的 `version='CSCA'` + `subject_type_mapping=<科目>` 匹配（`exam_record` 无 `exam_type` / `level` 列，不能按它们筛） | 命中且**未超时** → 直接回 `RESUME`（不走第 4–6 步） |
| 4 | 命中的会话**已超时** → **T1 独立事务**自动交卷（`status=1` + 判分 + 写错题本 + **提交即落地**），再继续 | `autoSubmitted=true` |
| 5 | **T2 独立事务**开始：先 `FOR UPDATE` 再加锁确认一次（双开防护）→ 资料 5 项（`GET /api/auth/app/profile/check`，契约见 §2.2）→ 试卷可用性 → 该科目次数 | 命中进行中 → 转 `RESUME`；否则 `8104`（附 `incompleteFields`）/ `8103` / `8105` |
| 6 | T2 内扣次数 + 建 `exam_record` + 写资料快照 + 答题卡 + 已考卷记录 | `CREATE`，`deducted=true` |

**约束**

- 🔴 **RESUME 必须跳过资料校验与扣次数**：`start/csca` 若对续考也校验，考生把资料改空、或次数被后台清零后，**已开的会话就永久进不去**（一开就 `8104`/`8105`，又不给重考）。
- 🔴🔴 **三段事务边界（T1 与 T2 必须独立提交）**：
  - 外层编排**不开事务**，只做校验 + 只读续考判定，`RESUME` 纯读直接返回；
  - **T1（`REQUIRES_NEW`）= 超时闭卷**，提交即落地，**不随后续 `8103`/`8104`/`8105`/500 回滚**；
  - **T2（`REQUIRES_NEW`）= 开考**，失败只回滚新会话，不影响已闭卷的旧会话。
  - 反面教材：把这两段放进同一个事务，超时会话的 `status=1` + 判分会被后续异常一起撤销 → 会话永久卡在「进行中」、成绩永久丢失，且每天点一次「开始」就是一次 8105/8104 死循环（job 只扫当天，跨天再也不修）。
- 🔴🔴 **续考判定分两次，锁只在第二次加**：外层用**无锁**查询（`selectOngoingCsca`），T2 内用 `FOR UPDATE`（`selectOngoingCscaForUpdate`）再确认。
  - 原因：T1 用 `REQUIRES_NEW` 开的是**新连接**；若外层事务已用 `FOR UPDATE` 锁住本人进行中行，T1 的 `update` 同一行会与外层互相等待 → 死锁 / `1205 Lock wait timeout`。
  - 防双开靠 T2 那次加锁：并发时后到者命中先到者刚建好的会话 → 直接转 `RESUME`，不重复扣次数。
- 🔴 **`exam_record` 当前没有 `deadline_time` 列**（实测 46 列）→ 超时判定按 `start_time + duration*60000` 现算，**不要写 `WHERE deadline_time > NOW()`**；日后补了该列再切。
- 🔴 次数查询必须用**带科目（4 参）的重载**：3 参版不带 `level` 且 `LIMIT 1` → 随机命中一科（B 方案一人 5 行）。
- T2 内扣次数用 **`decrementQuota(id)`**（`WHERE id=? AND remain_quota>0`），返回 0 → `8105`，只回滚 T2。
- 🔴 **禁用 `decrementQuotaByUser`**：该方法 `WHERE` 不含 `level`，一人 5 行会被一次全扣（考数学把物理化学次数也扣了）。
- 建会话时写**用户资料快照**：`real_name` / `gender` / `nationality` / `birthday`（§2.2 已在开考前硬拦，故新记录必非空；快照用于报告与历史留档，不随资料变更而变）。
- `deadline_time = start_time + duration*60000`；`total_score` 取 `exam_paper_structure.full_score`（100.00）；`listen_total` 等 HSK 字段恒 `0`。
- `deduct_type`：`0` 免费次数 / `1` 点数付费（🔴 与 HSK 同一套编码）；CSCA 新建会话恒 `0`，`deduct_amount = 0.00`。
- `currentQuestionNumber`：新建为 `1`，续考回 `exam_record.current_question_number` 里的上次位置（该列由 §2.5 逐题保存回写；未作答过则为 `1`）。

**错误码**：`400` / `8101` / `8102` / `8103` / `8104`（附 `incompleteFields`）/ `8105` / `500`。

---

### 2.4 GET /answer/paper/csca/detail/{paperId} 🔧

**用途**：加载整卷（首次全量）。

**入参**：`paperId`（路径）+ `recordId`（query，**必传**）。

> 🔴 `recordId` 必传，前端从 §2.3 `POST /answer/start/csca` 的响应里拿。**不允许**只凭 `paperId` 定位会话 —— 同一张卷可以有多场会话（含历史已交卷场次），只按 paperId 取会取错场次、串出上一场的答案。

**返回**

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

**约束**

- 🔴 **`answer` / `analysis` 必须 `null`**（现有实现整卷下发，属 P0 缺陷）。答案只能在交卷后的报告/解析接口出现。
- `typeId` 对外只两个值：`SINGLE` / `MULTI`（库中 `多选` → `MULTI`，其余 7 种题型 + 空 → `SINGLE`）；`typeIdRaw` 回原始中文名。
- 题干一般落在 `passage` 列（实测），前端两列都要渲染。
- `options` 是 `{key,value}` 数组，不是 map。
- `score` 单题分值：文/理中文 `1.25`；数理化 `2.00` 或 `2.50`（全卷 Σ = `100.00`）。
- 题量：中文 `80`，数理化 `48`。
- 🔴 **`recordId` 必传**：缺参直接 `400`（`缺少必要参数: recordId`），不做「按 paperId 兜底猜一场」的降级 —— 兜底 SQL 无论怎么排序（`status ASC, id DESC`）都可能在同卷多会话时取错场次，且 `selectByPaperAndUser` 无 `LIMIT`，多条 `status=0` 会抛 `TooManyResultsException`。
- 🔴 **归属不符按 `8107` 处理**（不回 `403`）：避免用错误码差异暴露「别人的会话是否存在」；`recordId` 与 `paperId` 不匹配同样是 `8107`。
- `remainingSeconds` 已过期返回 `0`（不返负数）；是否还能交卷由 §2.5 的 `8109` 判定，本接口不做拦截。

**错误码**：`8107` / `8108`（另：`400` `paperId`/`recordId` 缺失 / `401` 未登录 / `8103` 结构模板或题目缺失）。

---

### 2.5 POST /answer/submit/csca 🆕

**用途**：逐题保存 CSCA 答案，**服务端判对错**（不接受客户端 `isCorrect`）。CSCA **不再调用** `/answer/submit`。

**入参**

```json
{
  "examRecordId": "2113168625743364098",
  "paperId": "2101234567890123457",
  "questionId": "2101234567890123901",
  "questionNumber": 1,
  "answer": "A"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `examRecordId` | 是 | 会话 ID（**字符串**：雪花号超 2^53，数字会丢精度）；用它锁定「哪一次考试」 |
| `paperId` | 是 | 卷 ID；须等于 `exam_record.paper_id`，不等 → `8110` |
| `questionId` | 是 | 题 ID |
| `questionNumber` | 是 | 题号，缺失会答错位 |
| `answer` | 否 | 🔴 字段名就是 `answer`；多选 `"A,D"`（字母序不限）；≤ 64 字符；**空串 = 清空该题** |

🔴 **没有 `section` 入参**：答题行的 `section` 由开考时 `initAnswerCard` 按 `question.section` 预建，本接口不覆盖 —— 放开覆盖等于允许客户端伪造分节，把答案挪进别的小节统计。

**返回**

```json
{
  "code": 200, "message": "保存成功",
  "data": {
    "examRecordId": "2113168625743364098",
    "questionId": "2101234567890123901",
    "questionNumber": 1,
    "answered": 1,
    "remainingSeconds": 2080
  }
}
```

🔴 **不回 `isCorrect` / `points`**：逐题回对错等于给考生一个「改到对为止」的探测器。对错只落库，交卷后才由 §2.11 出结果。

**执行顺序**

| # | 步骤 | 失败 |
|---|---|---|
| 1 | 4 个 ID 非空、`answer` ≤ 64 字符 | `400` / `8112` |
| 2 | `selectById(examRecordId)`；`version != 'CSCA'` | `8107` |
| 3 | 🔴 **归属校验**：`record.user_id != 当前 userId` | `403` |
| 4 | `record.paper_id != paperId` | `8110` |
| 5 | `status != 0`（已交卷） | `8108` |
| 6 | `now > start_time + duration*60000` → 先自动交卷再拒 | `8109` |
| 7 | `questionId` 不属于本卷（`question.paper_id != paperId` 或 `deleted=1`） | `8110` |
| 8 | **服务端判对错** → 写 `is_correct` / `points` | — |
| 9 | 按 `(exam_record_id, question_id)` update | — |
| 10 | 🔴 **回写作答进度** `exam_record.current_question_number = questionNumber`（单列 update） | 越界/相同值则跳过，不影响保存结果 |

**判分口径**（归一化实现见 §3.6，逐题与交卷两处共用同一份）

- 单选：归一化后相等 → `is_correct=1`、`points = question.score`；否则 `2` / `0`。
- 多选（35 题）：**集合完全相等**才给满分，不给部分分、不倒扣。答案样本：`"A,D"` / `"A,B,C"` / `"A,B,C,D"`。
- 空答案：`answered=0`、`is_correct=2`、`points=0`，统计归 `unanswered`（§3.6）。🔴 虽然 `is_correct=2`，但 §4 按 `answered=0` 跳过，**不会进错题本**。
- 🔴 **不能直接 `equalsIgnoreCase`**：`"D,A"` / `"a, d"` / `"A、D"` 与 `"A,D"` 等价；`submitCscaExam:620` 现在的写法会把 35 道多选全判错。

**约束**

- **幂等覆盖**：同一 `(examRecordId, questionId)` 重复提交以最后一次为准。
- 🔴 **回写进度是续考落点的唯一来源**：保存成功后把 `exam_record.current_question_number` 置为本次 `questionNumber`（`LambdaUpdateWrapper` 单列 `set`，**不能整对象 `updateById`** —— 会拿旧快照覆盖并发的 `answered_count` / `leave_*`）。§2.3 的 `RESUME` 与 §2.7 的「当前题」都读这一列。越界题号（`<1` 或 `> total_questions`）与相同值不写。
- 🔴 **只 update、不 insert**：开考 `initAnswerCard` 已按整卷预建 `exam_answer`，本接口直接改行。🔴 `exam_answer` **无 (paper_id, user_id, question_id) 唯一键**，一旦误走 insert 就会产生重复行，判分和答题卡都会错。**答题行缺失时回 `400`「答题卡缺少该题记录，请重新进入考试」**，不补插。
- 🔴 **超时分支不加事务**：`now > deadline` 时先 `closeCscaRecord` 自动交卷落库、再抛 `8109`。若把整个方法包进一个事务，`8109` 回滚会把「自动交卷」一起撤销，考生会永远卡在「超时但未交卷」，所以本接口不开事务（单条 update 自身即事务）。
- 🔴 **判分归一化只有一份实现**：`com.hsktreasure.exam.csca.support.CscaAnswerGrader`（`normalize` / `matches`）。逐题保存与 §2.10 交卷必须都调它，`equalsIgnoreCase` 一类写法一律不许再出现。
- `is_correct` 由服务端写，**客户端传了也不采纳**（DTO 不含该字段）。
- 交卷时 `submitCscaExam` 仍按 `question.answer` 重算一遍全卷，本接口的判分结果会被覆盖 —— 两处**必须调用同一份归一化实现（§3.6）**，否则口径打架。

**错误码**：`400` / `403` / `8107` / `8108` / `8109` / `8110` / `8112`。

---

### 2.6 POST /answer/csca/favorite 🆕

**用途**：考试内收藏 / 取消收藏（与「标记」互相独立）。

**入参**

```json
{ "questionId": "2101234567890123901", "examRecordId": "2113168625743364098", "favorite": true }
```

**返回**

```json
{ "code": 200, "message": "操作成功",
  "data": { "questionId": "2101234567890123901", "favorite": true, "favoriteCount": 12 } }
```

**约束**

- `favorite` 是**显式最终态**（`true` 收藏 / `false` 取消），不是开关。
- 幂等写：`ON DUPLICATE KEY UPDATE` **只改 `deleted` + `updated_time`**，`source` / `record_id` / `section` 是首次收藏快照，不覆盖。
- 🔴 `csca_question_favorite.id` **无 `AUTO_INCREMENT`**（全局 `id-type: auto`）→ 必须应用层 `IdUtil.getSnowflakeNextId()`。
- 准入：会话对应卷 `exam_type = 2`（HSK 题不允许进 CSCA 收藏）。
- 表：`csca_question_favorite`（12 列），唯一键 `uk_user_question(user_id, question_id)`（不含 `deleted` → 软删可复活）。

**错误码**：`8107` / `8110`。

---

### 2.7 GET /answer/csca/card/detail/{paperId} 🔧

**用途**：答题卡（已答/未答、标记、收藏、剩余时间）。

**入参**：`paperId`（路径）+ `?recordId=`（**必传**）+ 可选 `?currentQuestionNumber=`。

| 字段 | 必填 | 说明 |
|---|---|---|
| `paperId` | 是 | 路径参数；须是 `version='CSCA'` 的卷 |
| `recordId` | **是** | 会话 ID；同卷可有多场会话（含历史已交卷场次），只凭 `paperId` 无法确定看哪一场。缺失 → `400 缺少必要参数: recordId` |
| `currentQuestionNumber` | 否 | 不传时取会话进度 `exam_record.current_question_number`（由 §2.5 逐题保存回写），再缺省 `1` |

**返回**

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

**约束**：`isTag` 来自 `exam_answer.is_tag`（HSK 共用，语义不变）；`favorite` 由 `csca_question_favorite` 左连（`source='exam'`）。**本接口不下发答案**。

- 🔴 **`recordId` 必传，不做「按卷兜底」**：同一卷可有多场会话，任何排序兜底都可能取错场次；缺参直接 `400`，不猜。
- `answered` 判定要**双条件**：`exam_answer.answered=1` **且** `answer` 非空（历史脏数据里有 `answered=1` 但 `answer=''` 的行）。
- `favoriteCount` 是**本卷内**已收藏题数（`favoriteId ∩ 本卷 questionId`），不是用户全量收藏数。
- `deadlineTime` 现算 `start_time + durationMinutes*60000`（`exam_record` 无 `deadline_time` 列）；`remainingSeconds` 过期回 `0`。
- `totalQuestions` 取答题行数（开考时整卷预建，等于全卷题数），行缺失时退回 `exam_record.total_questions`。

**错误码**：`8107`（卷非 CSCA / 会话不存在 / 归属或卷不匹配）（另：`400` 缺参 / `401` 未登录）。

---

### 2.8 GET /answer/checkSubmit/{paperId} ✅ 复用

**用途**：交卷确认弹窗的已答/未答统计。

**约束**：结构不变，直接复用；`section` 参数是**题号字符串**（实测），不要传科目码。

---

### 2.9 POST /record/{paperId}/leave ✅ 复用

**用途**：切后台 / 暂离，写 `leave_*` 字段。

**返回**：`{"code":200,"message":"已暂离考试"}`（现有实现，不改）。

---

### 2.10 POST /record/{recordId}/submit/csca 🔧

**用途**：交卷 + 同步判分 + 错题本写入（见 §4）。

> 🔴 路径参数是 **`recordId`（会话 ID，必传）**，不是 `paperId`。一场考试由 `recordId` 唯一确定，`paperId` 由会话反查（`exam_record.paper_id`）；同卷可以有多场记录，按卷反查会取错场次 —— 这就是把 `paperId` 换成 `recordId` 的原因。

**入参**

| 位置 | 参数 | 必填 | 说明 |
|---|---|---|---|
| path | `recordId` | 是 | 会话 ID（§2.3 的 `recordId` / §2.5 交卷响应里的 `id`）；服务端校验归属，不属于当前用户一律按 8107 处理 |
| body | `auto` | 否 | `true` = 客户端本地倒计时到点自动交卷；**整个 body 可省略** |

```json
{ "auto": true }
```

> `auto` **不参与判分**，只决定 `autoSubmitted` 回显。服务端自己也会判：`now > start_time + duration*60000` 时同样置 `true`，所以不传也不会漏标。

**返回**

```json
{
  "code": 200, "message": "提交成功",
  "data": {
    "id": 2101234567890123456, "paperId": 2101234567890123457, "status": 1,
    "finalScore": 62.40, "totalScore": 100.00, "totalQuestions": 48,
    "answeredCount": 48, "correctCount": 30, "wrongCount": 18, "unansweredCount": 0,
    "accuracyRate": 0.63, "duration": 2080,
    "autoSubmitted": true, "deductType": 0, "deductAmount": 0.00
  }
}
```

> 🔴 字段名是 `id`（沿用老 `ExamRecordResponse`），**不是** §2.3 的 `recordId` —— 同一个值、两个名字。前端把这里的 `id` 直接当 `examRecordId` 传给 §2.11 / §2.12。

**约束**

- 判分：单选归一化后相等；**多选集合完全相等**（不给部分分）；未答 `is_correct=2`、不得分，统计归 `unanswered`。归一化规则见 §3.6。
- 🔴 **未答不计入 `wrongCount`**：`unansweredCount = totalQuestions - answeredCount`，`wrongCount` 只数 `answered=1 AND is_correct=2`；错题本也只收这一类（§4 硬规则 3）。
- `final_score` = Σ 答对题 `question.score`；`total_score` 取 `exam_paper_structure.full_score`（缺模板时保留开考值、再兜 `100.00`）；`accuracy_rate` = `correctCount / totalQuestions`，**0–1 两位小数**（`HALF_UP`）。
- 写库：`exam_answer.is_correct` / `points`、`exam_record(status=1, final_score, total_score, correct_count, wrong_count, answered_count, accuracy_rate, duration, end_time)`；🔴 `exam_answer.exam_record_id` 必须落。
- 🔴 **幂等**：入口先判 `status=1`，命中直接回上次结果（不再判分、不再累加统计）；此时 `autoSubmitted` 只能回显本次请求的 `auto`（表里没这一列），前端不要依赖重复交卷的该字段。
- 错题本写入走**独立事务**（独立 Bean + `REQUIRES_NEW`）+ 外层 `try-catch` 吞异常，失败不回滚交卷（见 §4）。
- 🔴 **`csca_question_wrong` PROD 尚未建表**：写失败只打 ERROR 日志，交卷照常成功 —— 上线前必须先建表，否则错题本永远为空。

**错误码**：`8107`（会话不存在 / 归属不符 / 会话指向的卷非 CSCA）（另：`400` `recordId` 缺失 / `401` 未登录）。`8108` 在本接口**不出现** —— 重复交卷按幂等处理，不报错。

---

### 2.11 GET /record/csca/{examRecordId}/result 🔧

**用途**：诊断报告（成绩卡 + 题号卡）。

**返回**

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
    "avgTimePerQuestion": 43, "avgTimePerQuestionText": "43s",
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

**约束**

- `status=0` → `8111`。
- 🔴 **不做 `userId` 归属校验**（报告要给老师/家长看），`8107` 只表示「记录不存在 / 不是 CSCA」。
- 🔴 **答题行只按 `exam_record_id` 查，SQL 里不能带 `user_id`**：带了会让老师/家长打开时一行都查不到、题卡全空（与 §2.12 同一条硬规则）。交卷时 `closeCscaRecord` 已把 `exam_answer.exam_record_id` 全量回填，按会话查是完整的。
- 三态判定先看 `answered`（未答 `is_correct` 也是 `2`）：`answered=0` → `unanswered`；`answered=1 AND is_correct=1` → `correct`；`answered=1 AND is_correct=2` → `wrong`。
- `wrongCount` **不含未答**；`unansweredCount = totalQuestions - answeredCount`（下限 0）。四个计数以 `exam_record` 上的交卷统计为准，字段为空时才按答题行现算。
- `autoSubmitted`：`exam_record` 无该列，按「`end_time - start_time ≥ duration*60000`」现算，与 §2.10 的 `timeout` 同口径。
- `durationText` 是 `mm:ss`（如 `34:40`）；`avgTimePerQuestion = duration / answeredCount`（已答为 0 时取 0），文本 `"43s"`。
- `timeEvaluation` / `timeEvaluationType`：每题平均 `<30s` → `偏快` / `FAST`，`>60s` → `偏慢` / `SLOW`，其余 → `用时合理` / `REASONABLE`（`duration<=0` 也归合理）。
- `passage`：取 `question.passage`，为空时回退 `question_group.passage`（只查本卷涉及的分组）；`options` 是 `question.option_content`（JSON 列）反序列化后的对象。
- 点某一题看解析 → §2.12。

**错误码**：`8107` / `8111`（另：`400` `examRecordId` 缺失）。

---

### 2.12 GET /record/csca/{examRecordId}/question/{questionId} 🆕

**用途**：单题解析 —— 从诊断报告（§2.11）点某一题进来，回用户答案 / 标准答案 / 题库解析。

**入参**

| 位置 | 参数 | 类型 | 说明 |
|---|---|---|---|
| path | `examRecordId` | String | 会话 id（19 位雪花，**字符串**，见 §0.3） |
| path | `questionId` | String | 题目 id（同上） |

> 🔴 **不再传 `paperId`**：由 `exam_record.paper_id` 反查，前端不用记两个 id，也免掉「`paperId` 与 `examRecordId` 不一致」的校验分支。

**返回**

```json
{
  "code": 200, "message": "操作成功",
  "data": {
    "examRecordId": "2113168625743364098",
    "paperId": "2101234567890123457",
    "questionId": "2101234567890123901",
    "questionNumber": 12,
    "sectionMapping": "SEC_READ",
    "status": "wrong",
    "isTag": 0,
    "content": "若 $x^2-5x+6=0$，则 $x$ 的值为（　）",
    "passage": null,
    "options": { "A": "2 或 3", "B": "1 或 6", "C": "-2 或 -3", "D": "0 或 6" },
    "userAnswer": "A,B",
    "correctAnswer": "A",
    "points": 0.00,
    "totalPoints": 2.50,
    "analysis": "<p>由 $x^2-5x+6=(x-2)(x-3)=0$ 得 $x=2$ 或 $x=3$。</p><p>故选 A。</p>"
  }
}
```

**字段口径**

| 字段 | 取值 |
|---|---|
| `status` | `correct` / `wrong` / `unanswered`，与 §2.11 `questionCards[].status` **同一判定**：先看 `exam_answer.answered`（未答时 `is_correct` 也是 `2`），`answered=0` → `unanswered` |
| `userAnswer` | `exam_answer.answer` 原样；多选形如 `"A,D"`；未答 `null` |
| `correctAnswer` | `question.answer` 原样（多选同样是 `"A,D"`，**前端展示时按集合处理，别当字符串比**） |
| `points` / `totalPoints` | `exam_answer.points` / `question.score`（🔴 `question.score` 库里是 `varchar(30)`、实体是 `BigDecimal`，非数字串会转换失败） |
| `analysis` | 🔴 **取 `question.analysis`**（题库标准解析，已是 `<p>` 段落 + LaTeX 的 HTML，前端**按 HTML 渲染**并遍历文本节点跑 KaTeX）。**不是** `exam_answer.analysis` —— 那是写作题 AI 批改结果，CSCA 恒空 |
| `options` | `question.option_content`（**JSON 列**，反序列化成对象，不是字符串） |
| `passage` | `question.passage`，为空回退 `question_group.passage` |
| `isTag` | `exam_answer.is_tag`（考试中标记，0/1） |

**约束**

- `examRecordId` 查不到 / 不是 CSCA 记录（`exam_paper.version <> 'CSCA'`）→ `8107`。
- 🔴 **`status=0`（未交卷）→ `8111`**：解析里带标准答案，交卷前绝不能下发。
- `questionId` 不属于本卷 → `8110`：按 `exam_record.paper_id` 校验，**不信客户端传的 paperId**。
- 🔴 **归属校验与 §2.11 同口径：不校验 `userId`** —— 报告要能给老师 / 家长看，点进单题解析不能断。因此查答题行**只按 `exam_record_id + question_id`**，🔴 **不要带 `user_id`**。
- 只在交卷后开放，`is_correct` 已是终值，本端点只读、不改任何表。
- 答题行缺失（题目在卷内、但本会话没有对应答题行）→ 按 `unanswered` 下发，`userAnswer=null`、`points=0`，**不报错**：`8110` 只表示「题目不属于本卷」。
- ✅ 已实现：`ExamAnswerMapper#selectByExamRecordIdAndQuestionId`（`WHERE exam_record_id=? AND question_id=? LIMIT 1`，**不带 `user_id`**）；不再使用带 `user_id` 的 `selectByPaperUserQuestion`。

**错误码**：`8107` / `8110` / `8111`。

---

### 2.13 GET /record/user/records ✅ 复用

**用途**：模考记录列表，HSK / CSCA 共用。**CSCA 无需新增字段或参数**。

**入参**

| 参数 | 说明 |
|---|---|
| `version` | **筛 CSCA 就传 `CSCA`**（SQL 走 `exam_paper.version`）；HSK 传 `HSK2.0` / `HSK3.0` |
| `level` / `source` | HSK 用；🔴 CSCA 卷 `level` 全为 `NULL`，**CSCA 不要传 `level`** |
| `startTime` / `endTime` | 毫秒；🔴 **不传会被强制改成「最近 30 天」**（`ExamRecordServiceImpl:1204-1209`），要全量必须显式传足够早的 `startTime` |
| `pageNum` / `pageSize` | 默认 1 / 10，上限 100（超限 `8112`） |

**返回**：`IPage<ExamRecordDetailDTO>`，结构不变。CSCA 记录里 `subjectType` / `subjectTypeText` / `languageVersion` / `languageVersionText` **后端已解析并翻译好**（`resolveSubjectTypeCode` + `CSCASubjectType.translateName`）。

**约束**

- `examLevel` 对 CSCA 记录返回 `null`（卷 `level IS NULL`，代码是三元判断，**不会拼出 `"level null"`**）。
- 🔴 **`exam_record` 没有 `exam_type` 列** → 无法按 `examType=2` 筛；区分 CSCA 只能用 `version=CSCA`。
- 要按 5 科筛：先用 `version=CSCA` 取再按 `subjectType` 前端过滤 —— ⚠️ **分页在前端过滤会导致每页条数不齐**；产品若要「按科目 tab」，才需后端加 `subjectTypeMapping` 参数与 SQL 条件（可选增强，非上线必需）。
- `listenCorrect` 对 CSCA 塞的是 `record.correct_count`（总正确数），列表页展示「答对 x / `totalQuestions`」直接用。
- SQL 现状**未带 `deleted=0`** —— 实测全库 `deleted=1` 为 0 行，暂无影响，不阻塞。

---

### 2.14 科目字典 ✅ 复用（system-service）

`GET /api/system/dict/code/csca_subject` → 5 科 + `sortOrder` 顺序 + `isDefault` 默认项。

- ⚠️ `status` 是 **`0 = 正常` / `1 = 禁用`**（与其他字典反向，别写反）。

---

### 2.15 错题本读取 ✅ 复用（practice-service）

| 端点 | 说明 |
|---|---|
| `GET /api/practice/csca/wrong-book?source=exam` | 🔴 必传 `source=exam`；带标准答案 + 用户答案，**不带解析** |
| `DELETE /api/practice/csca/wrong-book/{questionId}` | 移出错题本（唯一的移出方式） |
| `POST /api/practice/csca/wrong-book/{questionId}` | 复习 |

考试侧**不重复造读接口**。

---

## 3. 枚举与判分口径

### 3.1 科目（5 个值）

| code | 中文名 | 语言 | 题量 | 时长 | 满分 | 备注 |
|---|---|---|---|---|---|---|
| `arts_chinese` | 文科中文 | `chinese` | 80 | 90 min | 100.00 | ✅ |
| `science_chinese` | 理科中文 | `chinese` | 80 | — | — | ❌ `exam_paper_structure` 缺模板 |
| `math` | 数学 | `chinese` / `english` | 48 | 60 min | 100.00 | ✅（仅中文有卷） |
| `physics` | 物理 | `chinese` / `english` | 48 | 60 min | 100.00 | ✅（仅中文有卷） |
| `chemistry` | 化学 | `chinese` / `english` | 48 | 60 min | 100.00 | ✅（仅中文有卷） |

### 3.2 CSCA 试卷判定

```
exam_paper.exam_type = 2   -- 2 = CSCA，1 = HSK
exam_paper.version   = 'CSCA'
exam_paper.deleted   = 0
```

### 3.3 题型（对外两个值）

| 库中 `type_id` | 对外 `typeId` |
|---|---|
| `多选`（35 题） | `MULTI` |
| `单选` / `识解汉字` / `选词填空` / `辨析词语` / `补全语句` / `选词成段` / `阅读理解` / 空 | `SINGLE` |

### 3.4 记录状态（`exam_record.status`）

| 值 | 含义 | CSCA |
|---|---|---|
| `0` | 进行中 | ✅ |
| `1` | 已结束（已交卷 + 已判分） | ✅ |
| `2` | 已提交（HSK 异步批阅后） | ❌ 不出现 |

### 3.5 作答三态

| `status` | 判定 |
|---|---|
| `correct` | `answered=1 AND is_correct=1` |
| `wrong` / `incorrect` | `answered=1 AND is_correct=2` |
| `unanswered` | `answered=0`（仍写 `is_correct=2`，但不得分） |

> 判定**必须先看 `answered`**，否则未答会被算成答错。

### 3.6 答案归一化与判分

```
① trim → 全角转半角（，、；／ → , ; /）
② 去空白
③ 大写
④ 按 [,;/\s] 切分 → 去空串 → 去重
⑤ 排序后拼回（',' 连接）
⑥ 与标准答案同规则归一化后比较
```

| 用户答案 | 标准答案 | 判定 |
|---|---|---|
| `DA` / `a, d` / `A、D` | `A,D` | ✅ |
| `A,D,B` | `A,D` | ❌（多选必须完全一致） |
| `A` | `A,D` | ❌ |
| `""` | `A,D` | `unanswered` |

- 单选：归一化后字符串相等。
- 多选：**集合完全相等**，不给部分分。
- 未答：`is_correct=2`、`points=0`，统计归 `unanswered`。
- 单题得分：`question.score`（中文 `1.25`；数理化 `2.00` / `2.50`）。
- 卷面总分：`exam_paper_structure.full_score` = `100.00`。
- 正确率：`correctCount / totalQuestions`，**0–1 两位小数**（`0.63` = 62.5%）。

---

## 4. 错题本写入（随交卷，不单独调用）

**触发**：`POST /record/{recordId}/submit/csca` 判分完成后，对每道 `answered=1 AND is_correct=2` 的题写 `csca_question_wrong`。

**字段取值**

| 列 | 取值 |
|---|---|
| `user_id` | Token 用户 |
| `question_id` | `exam_answer.question_id` |
| `section` | **`exam_paper.subject_type_mapping`**（科目码快照；不能取 `question.subject_type_mapping`，PROD 该列全 NULL） |
| `language_version` | `exam_paper.language_version` |
| `user_answer` | `exam_answer.answer` **原文**（不归一化） |
| `source` | 常量 `'exam'` |
| `record_id` | `exam_record.id`（与 `practice_record.id` 共用一列，前端按 `source` 区分） |
| `deleted` | `0`（软删复活） |

```sql
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

**三条硬规则**

1. **只收敛 `user_answer` / `deleted` / `updated_time`**，不覆盖 `source` / `record_id` / `section`（先练习错、后考试错时，来源标签不被改写）。
2. **只进不出**：判对不动、未评分不动；移出只能手动 `DELETE`。
3. **未答题不写**：`answered=0` 的即使 `is_correct=2` 也跳过。

**事务边界**：错题本写入放在**独立 Bean + `REQUIRES_NEW`**，外层 `try-catch` 吞异常 —— 否则 `csca_question_wrong` 写入失败会把整笔交卷回滚。
