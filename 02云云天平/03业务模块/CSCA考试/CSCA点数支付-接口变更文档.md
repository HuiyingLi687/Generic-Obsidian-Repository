# CSCA 点数支付 · 接口变更文档

> 版本：v1.0｜更新日期：2026-11-09
> 影响服务：**exam-service（改造）**、**pay-service（改造：枚举 / 文案 / 配置行）**、auth-service（不改）
> 关联文档：《CSCA 考试 · 接口设计文档》（错误码 8101–8199）、《CSCA 邀请与次数 · 接口变更文档》、《HSK 取卷与判分》
> 开发：待填｜测试：待填｜前端：待填

---

## 改动标记约定

- 【新增】：本次迭代新增字段 / 业务逻辑
- 【修改】：原有字段，修改约束、含义、逻辑
- 【无变更】：原有内容，本次迭代不做任何改动

---

## 0. 变更决策记录

| # | 决策项 | 取值规则 |
|---|---|---|
| 1 | 免费与点数的优先级 | `remain_quota > 0` **一律走免费次数**，不碰点数；`remain_quota = 0`（或查不到配额行）才走点数 |
| 2 | 点数场景编码 | 5 个科目**共用** `csca_exam` 一个场景；按科目差异化定价不做（后续配置表加行可扩展，无需改代码） |
| 3 | 点数单价 | 由 `point_price_config` 配置，初值 **4 点 / 科 / 次**（对齐 HSKK 档位），**上线前必须插入**，见 §9.1 |
| 4 | 混合扣减 | **不做**「免费 + 点数」混扣。一笔 `exam_record` 的 `deduct_type` 在建会话时一次写定：`0`=纯免费，`1`=纯点数 |
| 5 | 扣点时机 | 在 T2 开考事务内、**所有落库动作之后、提交之前**执行；扣点失败 → 整个 T2 回滚，不产生「扣了点没卷」 |
| 6 | 续考 | `RESUME` 分支在扣减之前返回，**不扣点数、不校验余额**（沿用现有分支顺序） |
| 7 | 提交失败兜底 | pay-service 扣成功但 T2 提交失败（极小概率）→ **不自动退点**，按 `biz_id = exam_record.id` 人工/对账补，见 §7.3 |
| 8 | 配额行是否记账 | 付费场次**不动** `user_exam_quota`（不改 `used_quota`），避免破坏 `remain = total − used` 的展示口径 |
| 9 | 错误码口径 | 余额不足统一抛 **8105**（扩展 `data`），**不把 pay-service 的 4001 透传**给 CSCA 客户端，避免前端处理两套码 |

---

## 1. 现状问题列表（本次要修的问题）

| # | 问题描述 | 带来的后果 |
|---|---|---|
| 1 | `startCscaExam` 只认 `remain_quota > 0`，为 0 直接抛 `8105`，**没有点数通道** | 用户免费次数用完即彻底无法考试；HSK/HSKK 已支持点数，CSCA 口径不一致，商业闭环缺一角 |
| 2 | `createCscaSession` 恒写 `deductType = CSCA_DEDUCT_TYPE_FREE`、`deductAmount = 0.00` | 即使接了扣点，场次也无法区分免费/付费，无法对账、无法统计付费转化 |
| 3 | `PointScene` 无 CSCA 场景；`point_price_config` 无 `csca_exam` 行 | 现在直接调 `deductExam` 必然 500「未配置场景点数价格」 |
| 4 | `GET /record/csca/quota` 只回免费次数，不回点数余额与单价 | 前端只能在开考报错后才知道点数不够，科目卡无法提前提示「N 点/次」 |
| 5 | `remain = 0` 时 T2 的 `FOR UPDATE` 锁不到任何 `exam_record` 行 | 极端并发下同一用户同科目可能建两场、扣两次点（见 §7.4 的补救） |

---

## 2. 数据模型变更

> 只写改动部分，不变的表不用写。

### 2.1 数据表改动

| 表名 | 改动内容 |
|---|---|
| `point_price_config` | **无结构变更**；新增 1 行 `scene_code='csca_exam'`（见 §9.1，P0 阻断项） |
| `exam_record` | **无结构变更**；`deduct_type` 由恒 0 变为可能出现 `1`（点数付费）。表里**没有** `deduct_amount` 列，扣点金额只走响应值 |
| `user_exam_quota` | **无结构变更、无补数**。付费场次不写 `used_quota`，不建新行 |
| `user_benefit_record` | **无结构变更**；`scene` / `source_type` 新增取值 `csca_exam`；对账键为 `biz_id = exam_record.id` |

**新增价格行（结构参照现有 4 行）**

| scene_code | point_amount | description | status |
|---|---|---|---|
| `csca_exam` | 4（待产品确认） | CSCA 考试单科单次消耗 | 1 |

### 2.2 枚举更新

| 表列 | 值 | 含义 |
|---|---|---|
| `point_price_config.scene_code` / `PointScene.code` | `csca_exam`【新增】 | CSCA 考试扣减（5 科共用） |
| `exam_record.deduct_type` | 0 | 免费次数（【无变更】原值） |
| `exam_record.deduct_type` | 1 | 点数付费（编码原本就有，**CSCA 本次首次真的写入**） |
| `user_benefit_record.scene` | `csca_exam`【新增】 | 权益流水展示文案「CSCA 考试扣减」 |

> `PointScene` 与 `BenefitI18n.SCENE` 要**同时**加，漏掉 i18n 时流水页场景列会渲染成空白。

---

## 3. 接口总览清单

> 接口类型说明：新增 / 改造 / 复用不改代码

| # | Method | Path | 用途 | 接口类型 | 改动简述 |
|---|---|---|---|---|---|
| 1 | POST | `/api/exam/answer/start/csca` | CSCA 开考（唯一入口） | 改造 | `remain=0` 时改走点数：先锁配额行 → 判余额 → 扣点 → 建会话；响应新增 `deductPoints` |
| 2 | GET | `/api/exam/record/csca/quota` | CSCA 5 科次数 | 改造 | 每科新增 `requiredPoints` / `canStartWithPoints` / `canStart`；顶层新增 `pointBalance` |
| 3 | POST | `/api/pay/benefit/deductExam` | 按场景扣点（内部） | 复用不改代码 | `sceneCode` 传 `csca_exam`，实扣数由价格表决定 |
| 4 | GET | `/api/pay/benefit/price` | 查场景单价（内部） | 复用不改代码 | `sceneCode=csca_exam` |
| 5 | GET | `/api/pay/benefit/examPoints` | 查点数余额（内部） | 复用不改代码 | 会员点数 + 永久点数 |
| 6 | GET | `/api/exam/quota` | HSK / HSKK 通用次数查询 | 复用不改代码 | **CSCA 不走这个入口**（它按 `level` 维度，CSCA 一个用户 5 行会命中随机一科） |

---

## 4. 改动接口详情

> 复用不改代码的接口不在此处展开，仅在上方清单记录。

### 4.1 POST /api/exam/answer/start/csca

**用途**：CSCA 开考：续考判定 → 资料 / 试卷 / 次数校验 → 建会话并扣减（免费次数或点数）
**鉴权**：需要登录，且 `X-Client-Type: APP`（非 APP 一律 403，与现状一致）

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| subjectTypeMapping | body | String | 是 | 【无变更】5 个科目码之一，非法 → 8101 |
| languageVersion | body | String | 是 | 【无变更】`chinese` / `english`，非法或中文科目传 english → 8102 |
| version | body | String | 否 | 【无变更】一律归一为 `CSCA`，传其它值只打 warn，不生效 |
| X-Client-Type | header | String | 是 | 【无变更】必须 `APP` |
| Authorization | header | String | 是 | 【无变更】透传给 auth-service 做资料校验，缺 → 401 |

**请求示例**

```http
POST /api/exam/answer/start/csca
Authorization: Bearer xxx
X-Client-Type: APP
Content-Type: application/json
```

```json
{
  "subjectTypeMapping": "math",
  "languageVersion": "chinese"
}
```

**返回完整示例（CREATE，免费次数已用完 → 本次扣点）**

```json
{
  "code": 200,
  "message": "开始考试成功",
  "data": {
    "action": "CREATE",
    "recordId": 2087777000000000001,
    "paperId": 1201,
    "status": 0,
    "startTime": 1792990000000,
    "deadlineTime": 1792995400000,
    "remainingSeconds": 5400,
    "durationMinutes": 90,
    "totalQuestions": 40,
    "totalScore": 100.00,
    "currentQuestionNumber": 1,
    "deductType": 1,
    "deductAmount": 0.00,
    "deductPoints": 4,
    "resumed": false,
    "deducted": true,
    "profileCheck": { "completed": true, "incompleteFields": [] },
    "paperCheck": { "available": true, "paperCount": 3, "reason": null },
    "quotaCheck": {
      "version": "CSCA",
      "totalQuota": 1,
      "usedQuota": 1,
      "remainQuota": 0,
      "hasQuota": false,
      "requiredPoints": 4,
      "pointBalance": 12,
      "sceneCode": "csca_exam"
    },
    "autoSubmitted": false
  }
}
```

**返回字段说明（仅列变动项）**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| action | String | 【无变更】 | `CREATE` / `RESUME` |
| recordId | Long | 【无变更】 | 会话题集定位唯一键 |
| deductType | Integer | 【修改】 | 以前 CSCA 恒 `0`；现在 `0`=免费次数、`1`=点数付费 |
| deductAmount | BigDecimal | 【无变更】 | 恒 `0.00`（表里无金额列，仅占位，保持老字段不消失） |
| deductPoints | Integer | 【新增】 | 本次**实际扣减的点数**；免费场次 / RESUME 恒 `0` |
| deducted | Boolean | 【无变更】 | RESUME 恒 `false` |
| quotaCheck.requiredPoints | Integer | 【新增】 | 该科目单次点数单价；价格未配置时为 `null` |
| quotaCheck.pointBalance | Integer | 【新增】 | 扣减后的点数总余额（会员 + 永久）；免费场次为当前余额 |
| quotaCheck.sceneCode | String | 【新增】 | 固定 `csca_exam`，便于前端埋点与文案 |
| 其余字段 | — | 【无变更】 | `paperCheck` / `profileCheck` / `autoSubmitted` 语义不变，RESUME 时 profileCheck/paperCheck 仍恒 `null` |

**服务端内部执行顺序（重要，后端&测试阅读）**

```
① 鉴权：非 APP → 403；无 userId / 无 Authorization → 401
② 归一 version='CSCA'；校验科目（8101）、语言（8102）；加载试卷结构（无模板在 CREATE 时报 8103）
③ 续考判定（🔴 无锁只读，必须在任何事务之外）
     命中且未超时 → 直接 RESUME 返回：不扣次数、不扣点、不查余额
     命中但已超时 → T1（REQUIRES_NEW）闭卷，继续往下
④ T2（REQUIRES_NEW）createCscaSession：
   4.1 exam_record 进行中行 FOR UPDATE，命中转 RESUME（并发双开防护）
   4.2 资料完整性（8104）→ 试卷可用性（8103）
   4.3 🆕 按 (user_id, 'CSCA', 'CSCA', 科目) 对 user_exam_quota 行加 FOR UPDATE
         · 目的：同科目开考串行化，避免 remain=0 时无人可锁 → 并发重复扣点
         · 行不存在时锁不到，属已知边界（见 §7.4）
   4.4 🆕 判定通道：
         remain_quota > 0  → deductType = 0（免费），继续
         否则              → 查单价（失败 → 8117）→ 查余额（不足 → 8105）→ deductType = 1
   4.5 选卷 → 建 exam_record（按 4.4 写 deduct_type）→ 建答题卡 → 写 user_taken_paper
   4.6 扣减（顺序不可颠倒）：
         免费 → decrementQuota(quotaId)（remain_quota > 0 守卫，返回 0 → 8105）
         付费 → 🆕 本步骤是 T2 的**最后一步**：deductExam(sceneCode='csca_exam', bizId=recordId)
                 · success=false → 抛 8105（带 requiredPoints / pointBalance），整个 T2 回滚
                 · 远程异常 / 超时 → 抛 8117，整个 T2 回滚
   4.7 返回 CREATE
```

> 🔴 **扣点必须是 T2 的最后一步**。放在建会话之前，一旦后续选卷/建卡失败，用户就会「扣了点、没卷、也没次数退回」。
> 🔴 **禁止在 T1 阶段或续考判定之前扣点**：超时闭卷是独立事务，扣了不会跟着回滚。

**本接口抛出错误码**：400 / 401 / 403 / 8101 / 8102 / 8103 / 8104 / 8105 / 8117

---

### 4.2 GET /api/exam/record/csca/quota

**用途**：首页 5 个科目卡次数角标 + 「剩余 N 次」总览；本次起同时给出点数单价与余额
**鉴权**：需要登录

**入参说明**：无业务入参（仅 `X-Client-Type`）。与现状一致，**不收科目 / 语言参数**，恒 5 科一次给全。

**请求示例**

```http
GET /api/exam/record/csca/quota
Authorization: Bearer xxx
X-Client-Type: APP
```

**返回完整示例（3 科用完免费次数、点数余额 12）**

```json
{
  "code": 200,
  "message": "查询成功",
  "data": {
    "quotas": [
      {
        "subjectType": "arts_chinese",
        "subjectTypeText": "文科中文",
        "totalQuota": 1,
        "usedQuota": 1,
        "remainQuota": 0,
        "hasQuota": false,
        "inProgress": false,
        "inProgressRecordId": null,
        "remainingSeconds": null,
        "requiredPoints": 4,
        "canStartWithPoints": true,
        "canStart": true
      },
      {
        "subjectType": "science_chinese",
        "subjectTypeText": "理科中文",
        "totalQuota": 1,
        "usedQuota": 0,
        "remainQuota": 1,
        "hasQuota": true,
        "inProgress": false,
        "inProgressRecordId": null,
        "remainingSeconds": null,
        "requiredPoints": 4,
        "canStartWithPoints": true,
        "canStart": true
      },
      {
        "subjectType": "math",
        "subjectTypeText": "数学",
        "totalQuota": 1,
        "usedQuota": 1,
        "remainQuota": 0,
        "hasQuota": false,
        "inProgress": false,
        "inProgressRecordId": null,
        "remainingSeconds": null,
        "requiredPoints": 4,
        "canStartWithPoints": true,
        "canStart": true
      },
      {
        "subjectType": "physics",
        "subjectTypeText": "物理",
        "totalQuota": 1,
        "usedQuota": 1,
        "remainQuota": 0,
        "hasQuota": false,
        "inProgress": false,
        "inProgressRecordId": null,
        "remainingSeconds": null,
        "requiredPoints": 4,
        "canStartWithPoints": true,
        "canStart": true
      },
      {
        "subjectType": "chemistry",
        "subjectTypeText": "化学",
        "totalQuota": 1,
        "usedQuota": 0,
        "remainQuota": 1,
        "hasQuota": true,
        "inProgress": false,
        "inProgressRecordId": null,
        "remainingSeconds": null,
        "requiredPoints": 4,
        "canStartWithPoints": true,
        "canStart": true
      }
    ],
    "totalRemainQuota": 2,
    "pointBalance": 12,
    "sceneCode": "csca_exam"
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| quotas[].subjectType / subjectTypeText | String | 【无变更】 | 固定 5 条，顺序 arts → science → math → physics → chemistry |
| quotas[].totalQuota / usedQuota / remainQuota | Integer | 【无变更】 | 原样回 `user_exam_quota`，缺行补 0 |
| quotas[].hasQuota | Boolean | 【无变更】 | `remainQuota > 0` |
| quotas[].inProgress / inProgressRecordId / remainingSeconds | — | 【无变更】 | 未交卷且未超时才为 true；`hasQuota=false` 但 `inProgress=true` 时仍可进考场 |
| quotas[].requiredPoints | Integer | 【新增】 | 该科目单次点数单价；价格未配置时为 `null` |
| quotas[].canStartWithPoints | Boolean | 【新增】 | `requiredPoints != null && pointBalance >= requiredPoints` |
| quotas[].canStart | Boolean | 【新增】 | `hasQuota \|\| inProgress \|\| canStartWithPoints` —— **前端按钮可点性改用这个字段** |
| totalRemainQuota | Integer | 【无变更】 | 5 科免费次数之和，仅总览用，**不参与任何校验** |
| pointBalance | Integer | 【新增】 | 点数总余额（会员 + 永久），来自 pay-service |
| sceneCode | String | 【新增】 | 固定 `csca_exam` |

**降级策略（首页不能因为支付服务抖动打不开）**

1. `payBenefitClient.getExamPointBalance` 异常 → `pointBalance = 0`、所有 `canStartWithPoints=false`、`canStart = hasQuota || inProgress`，只打 `warn` 日志，接口仍返回 200
2. `payBenefitClient.getExamPrice` 异常 → `requiredPoints = null`（**不兜底成写死的 4**，避免前后端价格口径分叉），同上降级
3. 次数查询本身异常 → 沿用现有「5 科全 0 + 保留 inProgress」降级，不新增抛错

> 🔴 新增字段允许为 `null`，老 App 忽略即可。但 `canStart` 只有在 `requiredPoints` 与 `pointBalance` 都拿到时才可信。

**本接口抛出错误码**：401（不新增）

---

### 4.3 复用接口（不改代码，仅约定调用方式）

| 接口 | CSCA 的调用约定 |
|---|---|
| `POST /api/pay/benefit/deductExam` | `sceneCode='csca_exam'`、`bizId=exam_record.id`、`remark='CSCA考试扣费'`；返回 `DeductResult`，**实扣数由 pay-service 查价格表**，调用方不得传金额 |
| `GET /api/pay/benefit/price?sceneCode=csca_exam` | 价格未配置时 pay-service 抛 500，CSCA 侧捕获后按 §4.1 的 8117 处理，不透传 500 |
| `GET /api/pay/benefit/examPoints?userId=xxx` | 用于 §4.2 的 `pointBalance`；`totalPoints` 即会员 + 永久之和 |

---

## 5. 错误码更新

| 错误码 | 服务 | 场景 |
|---|---|---|
| 8105 | exam-service | 【修改】触发条件从「免费次数不足」扩为「**免费次数=0 且点数不足以支付本次单价**」，`data` 增加 `requiredPoints` / `pointBalance` / `sceneCode`；扣点被 pay-service 判定余额不足时也归一为 8105 |
| 8117 | exam-service | 【新增】点数通道不可用：`point_price_config` 缺 `csca_exam` 行 / `status=0`，或 pay-service 调用异常、超时（fail-closed，不建会话、不扣任何东西） |
| 4001 | pay-service | 【无变更】HSK/HSKK 仍在用；**CSCA 不透传**，统一折成 8105 |
| 8101–8104 / 8107–8116 | exam-service | 【无变更】 |

> 8105 的 `data` 结构由 `QuotaCheckDTO` 承载，本次给它加 3 个可空字段，不新建 DTO——否则前端要按两种错误结构解析。

---

## 6. 前端对接注意事项

| # | 事项 | 说明 |
|---|---|---|
| 1 | 科目卡按钮 | 由 `hasQuota` 改为 `canStart`；置灰逻辑别再写 `remainQuota > 0`，否则「次数用完但有点数」的用户被锁在门外 |
| 2 | 点数不足引导 | 收到 8105 时读 `data.requiredPoints` / `data.pointBalance`，文案「当前 %d 点，本次需要 %d 点」，按钮跳权益中心 |
| 3 | 价格展示 | 科目卡副标题用 `requiredPoints` 拼「免费次数已用完，消耗 N 点开始考试」；`requiredPoints=null` 时不展示点数文案（视为通道未开） |
| 4 | 开考成功分流 | `deductType=1` 可埋点「点考场次」；`deductPoints` 用于 toast「已扣 4 点」；两者都不要当成金额 |
| 5 | 续考 | `action=RESUME` 时 `deducted=false`、`deductPoints=0`，**不要弹支付/扣点提示** |
| 6 | 老版本兼容 | 不读新字段仍可用，但 8105 文案会永远是「次数不足」。建议随版本一起更新文案，不强制升级 |
| 7 | 权益流水 | 场景文案已加「CSCA 考试扣减」中/英/越三语，直接展示 `sceneText` 即可 |
| 8 | 不要本地算价 | 单价只认接口返回值；客户端写死价格一旦调价就会提示错误金额 |

---

## 7. 关键业务流程 & 事务边界

### 7.1 通道选择（一次开考只走一条路）

```
remain_quota > 0 ?
 ├─ 是 → 免费通道：decrementQuota(quotaId)，deductType=0，deductPoints=0
 └─ 否 → 点数通道：
          查单价（csca_exam）── 失败/停用 → 8117（不建会话）
          查余额 ────────────── 不足 → 8105（不建会话）
          建会话 → 扣点 ─────── 失败 → 8105（回滚整个 T2）
                              成功 → deductType=1，deductPoints=单价
```

### 7.2 事务边界（必须按此实现）

| 阶段 | 事务 | 允许的写操作 |
|---|---|---|
| 续考判定（无锁只读） | **无** | 无 |
| T1 超时闭卷 | `REQUIRES_NEW` | 只改旧会话 `status` / 分数，**不扣不补** |
| T2 开考 | `REQUIRES_NEW`（`TransactionTemplate`） | 配额行锁、`exam_record`、`exam_answer`、`user_taken_paper`、远程扣点 |

**三条硬约束**

1. **配额行 `FOR UPDATE` 只能在 T2 内加**。T1 之前加锁会与外层事务叠成死锁（报 `1205`），这是现有 CSCA 三段事务的既定红线。
2. **远程扣点只能在 T2 的最后一步**。远程调用不可回滚，放前面就是「事务回滚、点数已扣」。
3. **`RESUME` 分支不得出现任何扣减代码**，包括余额校验；续考是纯读路径。

### 7.3 扣点成功但提交失败的兜底（P1）

`deductExam` 成功 → T2 提交时 DB 故障 → 会话不存在但点数已扣。

- **识别口径**：`user_benefit_record` 存在 `scene='csca_exam'` 的记录，但其 `biz_id` 在 `exam_record` 中查不到。
- **处理**：人工按 `biz_id` 补一次免费场次或手动加点（当前**无退点接口**，见 §10）。
- **概率**：仅提交阶段失败才触发；业务失败（8105/8117）发生在扣点之前，不会留下孤儿流水。

### 7.4 并发与重复扣点

- **正常路径**：T2 内 `user_exam_quota` 行 `FOR UPDATE` → 同科目开考串行化；第二个并发请求要么看到 `remain` 变化走点数，要么在 4.1 的 `exam_record` 锁上转 `RESUME`。
- **客户端重试**：第一次已提交 → 第二次必命中 `status=0` 进行中会话 → `RESUME`，不会二次扣点。
- **残余风险**：`user_exam_quota` 无行（存量未补数）+ 双端同时首开 → 锁不到行，理论上可扣两次。缓解：上线前跑一次《CSCA 邀请与次数》§8 的补数脚本（该脚本已存在，无需新增）。

### 7.5 与 HSK 的差异（别照抄）

| 维度 | HSK 笔试 | CSCA |
|---|---|---|
| 次数维度 | `user_id + version + level` | `user_id + 'CSCA' + 'CSCA' + 科目`（5 行，必须 4 参重载） |
| 免费判定 | `level ∈ {1,2}` 才有免费次数 | 5 科都有免费次数（注册 1 + 邀请最多 +2） |
| 扣减调用 | `decrementQuotaByUser`（无 level） | 🔴 **必须** `decrementQuota(id)`，用 `decrementQuotaByUser` 会一次扣光 5 行 |
| 事务 | 单事务 | 三段（T1 闭卷 / T2 开考），扣点位置受限 |
| 失败码 | 4001 | 8105 / 8117（不透传 4001） |

---

## 8. 验收测试用例

| # | 场景 | 预期结果 |
|---|---|---|
| 1 | 新用户（5 科各剩 1 次）开考数学 | `deductType=0`、`deductPoints=0`、`deducted=true`；`remain_quota` 1 → 0；无点数流水 |
| 2 | 数学免费次数已用完，点数余额 12 | 开考成功，`deductType=1`、`deductPoints=4`；`user_benefit_record` 新增 `scene=csca_exam`、`biz_id=recordId`；余额 12 → 8 |
| 3 | 数学免费次数用完，点数余额 3（< 4） | `8105`，`data.requiredPoints=4`、`data.pointBalance=3`；**无** `exam_record`、**无**点数流水 |
| 4 | 点数余额 0，且从未有过配额行 | 同上 `8105`（`pointBalance=0`），不报 `8105` 以外的码 |
| 5 | 价格表无 `csca_exam` 行 | `8117`，不建会话、不扣任何东西；日志含「未配置场景点数价格」 |
| 6 | pay-service 停机 | `8117`，`exam_record` 无新行；恢复后重试可正常开考 |
| 7 | 开考中途（选卷后）人为抛异常 | T2 整体回滚：无 `exam_record`、无 `exam_answer`、无 `user_taken_paper`、**无点数流水** |
| 8 | 已开考未交卷，再次开考同科目 | `action=RESUME`，`deducted=false`、`deductPoints=0`，`deductType` 回原场次值 |
| 9 | 上一场已超时，再次开考 | 先自动交卷（`autoSubmitted=true`），再按 §8-#2 规则重新扣减 |
| 10 | 免费场次开考，余额足够 | 不走点数，余额不变 |
| 11 | `GET /csca/quota`（余额 12、3 科用完免费） | 3 科 `canStartWithPoints=true`、`canStart=true`；`pointBalance=12` |
| 12 | `GET /csca/quota`（余额 2） | 所有科目 `canStartWithPoints=false`；`hasQuota=true` 的科目 `canStart` 仍为 true |
| 13 | pay-service 超时调 `/csca/quota` | 200 返回，`pointBalance=0`、`requiredPoints=null`、`canStart` 退回 `hasQuota \|\| inProgress` |
| 14 | 5 科并发开考（同用户不同科目） | 各扣各的：免费科目不扣点，付费科目各扣 4 点，互不影响（4 参重载不串科） |
| 15 | 同科目并发两次开考（点数通道） | 只产生 1 个 `exam_record`、只扣 1 次点；另一请求返回 `RESUME` |

---

## 9. 上线执行事项【P0 阻断项】

### 9.1 配置数据 SQL（无表结构变更、无存量补数）

```sql
-- ① 环境确认（G1/G2）：SELECT DATABASE(), @@hostname;
SELECT DATABASE(), @@hostname;

-- ② 执行前先看现状（G4 dry-run）：确认 csca_exam 是否已存在
SELECT id, scene_code, point_amount, description, status
FROM point_price_config
WHERE deleted = 0
ORDER BY id;

-- ③ 幂等插入（G5）
INSERT INTO point_price_config
  (scene_code, point_amount, description, status, deleted, created_time, updated_time)
VALUES
  ('csca_exam', 4, 'CSCA 考试单科单次消耗', 1, 0,
   UNIX_TIMESTAMP() * 1000, UNIX_TIMESTAMP() * 1000)
ON DUPLICATE KEY UPDATE point_price_config.id = point_price_config.id;   -- 已存在则不动（防覆盖运营改过的价）

-- ④ 回读校验
SELECT scene_code, point_amount, status FROM point_price_config WHERE scene_code = 'csca_exam';
```

执行闸门：

| 闸门 | 要求 |
|---|---|
| G1 / G2 | 打印 `DATABASE()` / `@@hostname` 确认环境（TEST `787e3b0c860c` / PROD `4a4fc6ac22b0`） |
| G3 | 只需备份 `point_price_config`（单表、只增一行；不必备份 `user_exam_quota`，本次不动配额数据） |
| G4 | 先跑 ② 的 `SELECT`，确认无 `csca_exam` 行 |
| G5 | `ON DUPLICATE KEY UPDATE point_price_config.id = point_price_config.id`，重跑 0 行变更 |

> 🔴 **`id = id` 必须带表名**（`point_price_config.id`），本仓已有 `INSERT ... SELECT` 裸写导致 `1052 ambiguous` 的前车之鉴。
> 🔴 不补 `user_exam_quota`：点数不依赖配额行；若存量用户缺 5 行，走《CSCA 邀请与次数》§8 的既有脚本，**不要在本期重复跑**。

**调价说明**：后续改价只需 `UPDATE point_price_config SET point_amount = ? WHERE scene_code='csca_exam'`，**不用发版**——扣点数由 pay-service 每次实时查表。

### 9.2 文件级变更清单

| 服务 | 文件路径 | 改动内容 |
|---|---|---|
| pay-service | `enums/PointScene.java` | 新增 `CSCA_EXAM("csca_exam", "CSCA考试扣减")` |
| pay-service | `i18n/BenefitI18n.java` | `SCENE` 增加 `csca_exam` 中/英/越文案；`REMARK` 增加 `CSCA考试扣费` |
| pay-service | 数据库 | `point_price_config` 插入 `csca_exam` 行（§9.1） |
| exam-service | `service/impl/ExamRecordServiceImpl.java` | `createCscaSession`：新增配额行 `FOR UPDATE`、通道判定、付费分支扣点（T2 末尾）、按通道写 `deduct_type`、组装 `deductPoints`；新增常量 `CSCA_SCENE_CODE = "csca_exam"` |
| exam-service | `service/impl/ExamRecordServiceImpl.java`（`getCscaQuota`） | 每科补 `requiredPoints` / `canStartWithPoints` / `canStart`；顶层补 `pointBalance` / `sceneCode`；pay 调用异常降级 |
| exam-service | `service/UserExamQuotaService.java`(+Impl) | 新增 `getQuotaForUpdate(userId, examType, version, level)` |
| exam-service | `mapper/UserExamQuotaMapper.java`(+`.xml`) | 新增 `selectByUserIdAndExamTypeForUpdate`（4 参 + `FOR UPDATE`） |
| exam-service | `mapper/ExamRecordMapper.java`(+`.xml`) | 新增 `selectSubjectQuotaForUpdate`（按用户 + 科目锁配额行，与上一行二选一实现即可） |
| exam-service | `dto/CscaStartResponse.java` | 新增 `deductPoints`（Integer） |
| exam-service | `dto/CscaQuotaDTO.java` | `SubjectQuota` 补 3 字段；顶层补 2 字段 |
| exam-service | `dto/QuotaCheckDTO.java` | 补 `requiredPoints` / `pointBalance` / `sceneCode`（均可空） |
| exam-service | `csca/support/CscaExamErrorCode.java` | 新增 `POINT_SCENE_UNAVAILABLE = 8117` |
| auth-service | — | **不改** |

### 9.3 环境状态

- TEST：未执行（配置行未插入 → 现在调用必 8117）
- PROD：未执行，上线前必须操作（§9.1 ③，P0 阻断）

---

## 10. 待确认事项

| # | 待确认点 | 暂定方案 | 确认人 |
|---|---|---|---|
| 1 | 单科单价取几点 | 暂定 **4 点**（对齐 HSKK）；HSK=2、HSKK=4，CSCA 单科 90 分钟同档 | 产品 |
| 2 | 是否按科目差异化定价 | 本期不做；后续在价格表加 `csca_exam_math` 等行并加一层 fallback 即可，不改表结构 | 产品 |
| 3 | 是否需要「扣错退点」接口 | 本期不做，走 §7.3 人工对账；若上线后孤儿流水 > 3 例，建议 pay-service 补 `refundExam` | 产品 / 后端 |
| 4 | 免费次数用完后的单日/单科次数上限 | 本期不做（点数即门槛）；如需防刷另开需求 | 产品 |
| 5 | 点数通道是否对全量用户开放 | 默认全开；如需灰度，建议用 `point_price_config.status=0` 作总开关（无需发版） | 运营 |
| 6 | `GET /exam/quota` 是否也要支持 `examType=CSCA` | 不支持。该接口按 `level` 定位，CSCA 无 level 概念，误用会返回随机一科次数 | 前端 |
