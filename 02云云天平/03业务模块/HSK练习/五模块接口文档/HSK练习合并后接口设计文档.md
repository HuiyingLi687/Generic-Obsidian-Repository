# HSK 练习 · 五模块接口合并（客观族 / 主观族）接口设计文档

> 版本：v2.2｜更新日期：2026-11-18
> 本版变更：删除开练请求的 `restart` 字段（不再提供重开机制）；主观族单题作答与判分重试改为三模块通用，`8120` 随之下线
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

| # | 决策项 | 取值规则 |
|---|---|---|
| 1 | 合并粒度 | 按**响应契约**分组，不按模块：听 + 读合成「客观族」，写 + 译 + 说合成「主观族」 |
| 2 | 路径形态 | 只保留两条前缀 `/hsk/objective/records/**`、`/hsk/subjective/records/**`，模块一律用 `?module=` 指定 |
| 3 | 旧路径 | **不再保留**：`/listening/records/**`、`/reading/records/**`、`/writing/records/**`、`/translation/records/**`、`/speaking/records/**` 全部下线，模块只能由 `?module=` 指定 |
| 4 | 选项结构 | 客观族统一扁平 `{"A":"文本","B":"文本"}`，不再有外层 `options` 包裹 |
| 5 | 题号字段 | 客观族统一 `number`（原听力叫 `no`） |
| 6 | 答案字段 | 客观族统一 `answer`（原听力叫 `selectedOptionId`），值为选项编码 A/B/C/D/E/F |
| 7 | 乐观锁 | `baseVersion` 统一**必传**，取自记录响应的 `version`；听力强校验，阅读接受但不校验 |
| 8 | 报告结构 | 交卷与查报告返回**同一结构**（摘要 + 题号矩阵 `rows` + 单题明细 `items`） |
| 9 | 报告状态 | 收敛为 4 值 `PENDING/GENERATING/READY/FAILED`，可重试性改由布尔 `retryable` 表达 |
| 10 | 口语板块域 | `AnswerCardModule.SPEAKING` 的 `sectionMapping` 由拼写错误的历史值 `SEC_SPEAK` 改为 `SEC_SPEAKING`，校验时仍兼容旧值 |
| 11 | 内部实现 | 客观族保留两套 service（听力回 `question` 表、阅读读 `answer` 快照），门面层只做分派与 DTO 转换 |
| 12 | 开练语义 | `start` 只负责开新的练习：有未提交记录直接返回该记录，已提交后再调用则新建一次练习。不提供重开接口，未提交的继续练习走 `resume` |
| 13 | 模块级端点 | 主观族全部端点三模块通用，不再有「单题作答仅口语」「翻译无判分重试」这类限制，`8120` 随之删除 |

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

### 2.2 枚举更新

| 枚举 | 值 | 含义 |
|---|---|---|
| `ObjectiveModule`【新增】 | `listening` / `reading` | 客观族模块码，`module` 参数取值 |
| `SubjectiveModule` | `writing` / `translation` / `speaking` | 【无变更】主观族模块码，直接作为 `module` 参数取值 |
| `AnswerCardModule.SPEAKING.sectionMapping` | `SEC_SPEAKING`【修改】 | 原值 `SEC_SPEAK`（拼写错误）；校验时仍接受旧值 |

## 3. 接口总览清单

> 目录三跳（`/hsk/modules`、`/hsk/levels`、`/hsk/levels/{level}/intro`、`/hsk/papers/{paperId}/parts`）本次**不动**，不在下表展开。

### 3.1 客观族（听 / 读）

前缀：`/hsk/objective/records`（唯一前缀，旧路径已下线）

| # | Method | Path | 用途 | 接口类型 | 改动简述 |
|---|---|---|---|---|---|
| 1 | POST | `{客观前缀}/start` | 开练 | 改造 | 请求体统一、删除 `restart`；`module` 必传 → §4.2.1 |
| 2 | GET | `{客观前缀}/{recordId}` | 记录详情 | 改造 | 响应加 `module` / `version`；`answers[]` 并集化 → §4.2.2 |
| 3 | POST | `{客观前缀}/{recordId}/pause` | 暂停 | 改造 | 请求体并集化；阅读必须带 `currentQuestionId` → §4.2.3 |
| 4 | POST | `{客观前缀}/{recordId}/resume` | 恢复 | 改造 | 响应同记录详情 → §4.2.4 |
| 5 | GET | `{客观前缀}/{recordId}/questions` | 拉题 | 改造 | 题目响应统一字段名与选项结构 → §4.2.5 |
| 6 | PUT | `{客观前缀}/{recordId}/answers/{questionId}` | 单题保存 | 改造 | 答案字段 `selectedOptionId` → `answer` → §4.2.6 |
| 7 | PUT | `{客观前缀}/{recordId}/answers` | 批量保存 | 改造 | 同上；返回整条记录 → §4.2.7 |
| 8 | POST | `{客观前缀}/{recordId}/submit` | 交卷 | 改造 | 返回完整报告结构（原听力只回摘要）→ §4.2.8 |
| 9 | GET | `{客观前缀}/{recordId}/report` | 报告详情 | 改造 | 统一结构，状态值域收敛 → §4.2.9 |
| 10 | GET | `{客观前缀}/{recordId}/report/questions/{questionId}` | 逐题回顾 | 改造 | 统一为「题目结构 + 判分字段」→ §4.2.10 |
| 11 | POST | `{客观前缀}/{recordId}/report/retry` | 报告重试 | 改造 | 返回完整报告 → §4.2.11 |
| 12 | GET | `{客观前缀}/{recordId}/answer-card` | 答题卡 | 改造 | 五模块同一响应，模块由 `module` 必传指定 → §4.2.12 |

> 答题卡的旧路径（`/listening/records/{id}/answer-card` 等五条）与其余旧路径一并下线。
> 现存两条路径并入同一个方法：`/hsk/objective/records/{id}/answer-card` 与 `/hsk/subjective/records/{id}/answer-card`，靠 `module` 分派，因此主观族不再单列答题卡端点。

### 3.2 主观族（写 / 译 / 说）

前缀：`/hsk/subjective/records`（唯一前缀，旧路径已下线）

| #   | Method | Path                                               | 用途     | 接口类型 | 改动简述                    |
| --- | ------ | -------------------------------------------------- | ------ | ---- | ----------------------- |
| 1   | POST   | `{主观前缀}/start`                                     | 开练     | 改造   | 三个控制器合一，`module` 决定模块   |
| 2   | GET    | `{主观前缀}/{recordId}`                                | 记录详情   | 改造   | 响应体不变                   |
| 3   | POST   | `{主观前缀}/{recordId}/pause`                          | 暂停     | 改造   | 响应体不变                   |
| 4   | POST   | `{主观前缀}/{recordId}/resume`                         | 恢复     | 改造   | 响应体不变                   |
| 5   | GET    | `{主观前缀}/{recordId}/questions`                      | 拉题     | 改造   | 响应体不变                   |
| 6   | PUT    | `{主观前缀}/{recordId}/answers`                        | 批量保存答案 | 改造   | 响应体不变                   |
| 7   | POST   | `{主观前缀}/{recordId}/questions/{questionId}/answers` | 单题作答   | 改造   | 三模块通用；写 / 译填文本，口语填录音地址 |
| 8   | PUT    | `{主观前缀}/{recordId}/questions/{questionId}/draft`   | 保存草稿   | 改造   | 响应体不变                   |
| 9   | POST   | `{主观前缀}/{recordId}/submit`                         | 交卷     | 改造   | 幂等键改为服务端按模块拼            |
| 10  | GET    | `{主观前缀}/{recordId}/report`                         | 报告详情   | 改造   | 响应体不变                   |
| 11  | GET    | `{主观前缀}/{recordId}/report/questions/{questionId}`  | 逐题反馈   | 改造   | 响应体不变                   |
| 12  | POST   | `{主观前缀}/{recordId}/report/retry`                   | 判分重试   | 改造   | 三模块通用                    |

> 主观族响应体（`SubjectiveRecordResponse` / `SubjectiveQuestionResponse` / `SubjectiveReportResponse` 等）本次**不做字段改动** —— 三模块本来就共用一套 DTO，合并只是去掉两份重复的控制器。

## 4. 改动接口详情

### 4.1 模块参数规则（两族通用）

| 路径 | `module` 是否必传 | 取值 |
|---|---|---|
| `/hsk/objective/records/**` | **必传** | `listening` / `reading` |
| `/hsk/subjective/records/**` | **必传** | `writing` / `translation` / `speaking` |

`module` 大小写与首尾空格不敏感。缺失、取值不在白名单 → `8133`。

旧路径（`/listening/records/**`、`/reading/records/**`、`/writing/records/**`、`/translation/records/**`、`/speaking/records/**`）**已不再注册**，访问返回 `404`。

---

### 4.2 客观族端点

客观族有多个端点返回同一条记录（`ObjectiveRecordResponse`），下文统一简称「记录响应」，字段定义见 §4.2.1 的返回字段说明，不再逐段重复。两处共性差异先说明：

- `answers[]` 元素为 `{questionId, answer, answered, conflict, currentVersion}`；`conflict` / `currentVersion` 只有听力会产生，阅读恒为 `false` / `null`
- `currentPassageItemIndex` 只有听力使用（passageGroup 子题位置），阅读恒 `null`

#### 4.2.1 POST `{客观前缀}/start`

**用途**：开练。有未提交记录时直接返回该记录，已提交后再调用则新建一次练习
**鉴权**：需要登录

**入参说明**

| 参数名           | 位置     | 类型      | 必填   | 约束&说明                             |
| ------------- | ------ | ------- | ---- | --------------------------------- |
| module        | query  | String  | 必传 | 【新增】`listening` / `reading` |
| paperId       | body   | Long    | 是    | 【无变更】练习试卷 ID                      |
| section       | body   | String  | 是    | 【无变更】板块号 1..N                     |
| X-Client-Type | header | String  | 否    | 【无变更】                             |

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
    "status": 1,
    "reportStatus": "PENDING",
    "version": 1,
    "currentQuestionId": null,
    "currentQuestionNumber": null,
    "currentPassageItemIndex": 0,
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

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| recordId | Long | 【无变更】 | 练习记录 ID（`practice_record.id`） |
| paperId | Long | 【无变更】 | 试卷 ID |
| section | String | 【无变更】 | 板块号 |
| module | String | 【新增】 | `listening` / `reading` |
| status | Integer | 【无变更】 | 0 已创建、1 进行中、2 已放弃、3 已提交 |
| reportStatus | String | 【无变更】 | `PENDING/GENERATING/READY/FAILED` |
| version | Integer | 【新增】 | 乐观锁版本号，回传给 `baseVersion` |
| currentQuestionId | Long | 【无变更】 | 当前停留题目 ID |
| currentQuestionNumber | Integer | 【无变更】 | 当前停留题号 |
| currentPassageItemIndex | Integer | 【修改】 | 听力 passageGroup 子题位置（原恒 0）；**阅读恒 null** |
| durationSeconds | Integer | 【无变更】 | 在场累计秒数 |
| paused | Boolean | 【无变更】 | 是否已离开（true 时前端不要自动续走计时器） |
| pausedAt | Long | 【无变更】 | 上次离开时刻毫秒；`paused=false` 时为 null |
| answeredCount | Integer | 【无变更】 | 已答题数 |
| totalQuestions | Integer | 【无变更】 | 本次练习总题数 |
| answers | Array | 【修改】 | 元素结构见下（阅读侧 `conflict`/`currentVersion` 恒为 false/null） |
| answers[].questionId | Long | 【无变更】 | 题目 ID |
| answers[].answer | String | 【无变更】 | 用户答案（选项编码） |
| answers[].answered | Boolean | 【无变更】 | 是否已作答 |
| answers[].conflict | Boolean | 【无变更】 | 版本冲突标记；**阅读恒 false** |
| answers[].currentVersion | Integer | 【无变更】 | 云端最新版本；**阅读恒 null** |

**服务端内部执行顺序（重要，后端&测试阅读）**

1. 按 `module` 解析模块，缺失或取值不合法即 `8133`
2. `SELECT ... FOR UPDATE` 查未提交记录，`(userId, paperId, sectionMapping, section)` 定位，仅 `status IN (0,1)`
3. 有未提交记录 → 直接返回该记录（**听力额外校验卷内容与板块配置是否下架**，回 `8141` / `8142`；阅读不校验）；已提交的记录不在查询范围内，继续往下新建一次练习
4. 校验试卷可用性 —— **两模块口径不同，本次未统一**：
   - 听力：卷存在且未删除（`8107`）
   - 阅读：`exam_paper.enabled_prac = 1` 且 `SharedPaperEligibility` 通过（`8166`）
5. 校验板块开关 `practice_module_part_config`（听力 `8138` 语义 → `8107`；阅读 → `8167`）
6. 取题、按题号排序、**冻结 `question_ids`**
7. 插记录 + 逐题插 `practice_answer` 占位行：
   - 听力：占位行带题目快照 + 共享音频解析结果
   - 阅读：占位行带题目 / 题组 / 选项 / 标准答案 / 解析全量快照（后续作答直接读快照）
8. 返回记录

> 约束：同一 `(userId, paperId, sectionMapping, section)` 至多一条 `status IN (0,1)` 的记录。

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

**返回**：记录响应（字段定义见 §4.2.1 返回字段说明）。

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

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 必传 | 模块码 |
| currentQuestionId | body | Long | 条件必填 | 【修改】停留题目 ID；**阅读必传**（要校验该题属于本次记录，缺省回 `8101`），听力可空 |
| draftAnswers | body | Array | 否 | 【新增】元素 `{questionId, answer}`；仅听力生效，阅读传了也不处理、不报错 |
| clientSequence | body | Integer | 否 | 【新增】乱序检测用，仅听力生效 |

**请求示例**

```json
{
  "currentQuestionId": 55121,
  "draftAnswers": [{ "questionId": 55120, "answer": "C" }],
  "clientSequence": 129
}
```

**返回**：记录响应，含结算后的 `durationSeconds`、`paused=true`、`pausedAt`。

**服务端内部执行顺序**

1. 解析模块，`SELECT ... FOR UPDATE` 锁记录并校验归属与进行中状态（`8102` / `8103`；阅读为 `8112` / `8162`）
2. 结算本段时长：段起点取 `max(start_time, paused_time, resumed_time)`，单段上界 1800s
3. 写 `durationSeconds`、`paused_time = now`、停留位置
4. 听力：草稿答案落库（不判分、不固化快照）
5. 返回记录

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

**返回**：记录响应，`paused=false`、`pausedAt=null`，`durationSeconds` 不增加。

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
      "layout": "textChoice_shareAudio",
      "typeId": null,
      "typeIdMapping": null,
      "content": "男：请问洗手间在哪儿？",
      "passage": "男：请问洗手间在哪儿？",
      "variant": "interview",
      "optionContent": { "A": "在二楼", "B": "在一楼", "C": "在三楼" },
      "audioUrl": "https://cdn/xxx.mp3",
      "shareAudioUrl": "https://cdn/share.mp3",
      "groupId": null,
      "group": null,
      "optionPoolCode": null,
      "exclusiveSharedOptions": null,
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
      "variant": null,
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
        "passage": "（文章正文……）",
        "audioUrl": null,
        "optionContent": null
      },
      "optionPoolCode": "GROUP_8801",
      "exclusiveSharedOptions": false,
      "userAnswer": "B",
      "answered": true
    }
  ]
}
```

**返回字段说明**

| 字段                     | 类型      | 改动标记  | 说明                                                      |
| ---------------------- | ------- | ----- | ------------------------------------------------------- |
| questionId             | Long    | 【无变更】 | 题目 ID                                                   |
| number                 | Integer | 【修改】  | 题号；**原听力字段名 `no`**                                      |
| layout                 | String  | 【无变更】 | 布局编码，唯一真源 `question.layout`；**阅读恒 null**（快照未存 layout）   |
| typeId                 | String  | 【新增】  | 原始题型 ID；听力恒 null                                        |
| typeIdMapping          | String  | 【新增】  | 题型映射编码；听力恒 null                                         |
| content                | String  | 【新增】  | 题干；听力等于 `passage`（题库把题干放 passage）                       |
| passage                | String  | 【无变更】 | 文章 / 材料正文                                               |
| variant                | String  | 【修改】  | 细节题变体 short/long/interview；**原听力下划线字段不变，位置不变**；阅读恒 null |
| optionContent          | Object  | 【修改】  | **扁平** `{"A":"文本"}`；阅读原为 `{"options":{...}}`            |
| audioUrl               | String  | 【修改】  | 题目音频；**原听力字段名 `audio_url`**                             |
| shareAudioUrl          | String  | 【修改】  | 共享材料音频；**原听力字段名 `share_audio_url`**；阅读恒 null            |
| groupId                | Long    | 【新增】  | 题组 ID；听力恒 null                                          |
| group                  | Object  | 【新增】  | 题组共享内容（字段见上例）；听力恒 null                                  |
| optionPoolCode         | String  | 【新增】  | 共享选项池编码；听力恒 null                                        |
| exclusiveSharedOptions | Boolean | 【新增】  | 固定 false；听力恒 null                                       |
| userAnswer             | String  | 【无变更】 | 当前答案                                                    |
| answered               | Boolean | 【无变更】 | 是否已作答                                                   |

**服务端内部执行顺序**

1. 解析模块，校验归属与 `status=1`
2. 听力：按 `question_ids` 顺序回 `question` 表取题，按 layout 匹配 `question_shared_audio` 得 `shareAudioUrl` + `variant`
3. 阅读：直接读 `practice_answer` 冻结快照（`questionSnapshot` / `groupSnapshot` / `optionSnapshot`），不查 `question` 表
4. 回填答案与 `answered`
5. 统一转成客观族题目结构

> 约束：题序以记录 `question_ids` 为准；历史记录无 `question_ids` 时听力回落三元组查询、阅读要求快照完整（`8180`）。

**本接口抛出错误码**：8102 / 8103 / 8107 / 8133 / 8165 / 8180

---

#### 4.2.6 PUT `{客观前缀}/{recordId}/answers/{questionId}`

**用途**：单题保存答案（用户点选后防抖同步）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| questionId | path | Long | 是 | 题目 ID |
| module | query | String | 必传 | 【新增】模块码 |
| answer | body | String | 是 | 【修改】选项编码 A/B/C/D/E/F（判断题用 A/B）；原听力字段名 `selectedOptionId` |
| baseVersion | body | Integer | 是 | 【新增】记录 `version`；不一致回 `8104`（听力强校验，阅读不校验） |
| clientSequence | body | Integer | 否 | 【无变更】乱序检测用 |

**请求示例**

```json
{ "answer": "C", "baseVersion": 7, "clientSequence": 128 }
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
    "conflict": false,
    "currentVersion": 8
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| questionId | Long | 【无变更】 | 题目 ID |
| answer | String | 【无变更】 | 保存后的答案 |
| answered | Boolean | 【无变更】 | 是否已作答 |
| conflict | Boolean | 【无变更】 | 冲突标记；阅读恒 false |
| currentVersion | Integer | 【无变更】 | 记录最新版本；阅读恒 null |

**服务端内部执行顺序**

1. 解析模块，锁记录并校验归属与 `status=1`（`8102` / `8103`）
2. 听力：读答案行并写 `answer = 请求answer`、`answered = 1`，重算 `answeredCount`，`lastSavedTime = now`
3. 阅读：写答案；`answer` 传 null 表示清空
4. 返回答案项

**本接口抛出错误码**：8102 / 8103 / 8104 / 8107 / 8133 / 8173

---

#### 4.2.7 PUT `{客观前缀}/{recordId}/answers`（批量）

**用途**：强制保存点一次性提交多题（切题、退出、锁屏、交卷前）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| module | query | String | 必传 | 【新增】模块码 |
| answers | body | Array | 是 | 【修改】元素 `{questionId, answer}`；原听力元素字段名 `selectedOptionId` |
| baseVersion | body | Integer | 是 | 【新增】听力强校验，不一致回 `8104` |
| currentQuestionId | body | Long | 否 | 【无变更】顺带更新停留位置 |
| clientSequence | body | Integer | 否 | 【无变更】 |

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

**返回**：记录响应（字段定义见 §4.2.1），含最新 `version` 与 `answers[]`。

**服务端内部执行顺序**

1. 解析模块，锁记录校验归属与状态
2. 听力：校验 `baseVersion` → 批量 upsert `practice_answer` → 重算 `answeredCount` → 返回记录
3. 阅读：校验答案项属于本次记录（`8173`）、去重（`8169`）→ 批量 upsert → **补一次记录读取**后返回

**本接口抛出错误码**：8102 / 8103 / 8104 / 8133 / 8169 / 8170 / 8171 / 8172 / 8173

---

#### 4.2.8 POST `{客观前缀}/{recordId}/submit`

**用途**：交卷并触发出分 / 报告生成
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| module | query | String | 必传 | 【新增】模块码 |
| baseVersion | body | Integer | 是 | 【新增】不一致回 `8104` |
| finalAnswers | body | Array | 否 | 【修改】元素 `{questionId, answer}` |
| idempotencyKey | body | String | 否 | 【无变更】不传由服务端拼 `{module}-{recordId}-submit` |
| Idempotency-Key | header | String | 否 | 【无变更】body 未带时使用该头 |
| clientSequence | body | Integer | 否 | 【无变更】 |

**请求示例**

```json
{
  "baseVersion": 12,
  "finalAnswers": [{ "questionId": 55120, "answer": "C" }],
  "clientSequence": 204
}
```

**返回完整示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "reportId": 900812,
    "recordId": 900812,
    "paperId": 100231,
    "module": "listening",
    "sectionMapping": "SEC_LISTEN",
    "section": "1",
    "status": 3,
    "reportStatus": "READY",
    "retryable": false,
    "totalQuestions": 20,
    "answeredCount": 20,
    "correctCount": 17,
    "wrongCount": 3,
    "accuracyRate": 85.00,
    "durationSeconds": 1265,
    "submittedTime": 1763452800000,
    "rows": [
      {
        "number": 1,
        "questionId": 55120,
        "questionType": "细节选择",
        "layout": "textChoice_shareAudio",
        "answered": true,
        "isCorrect": true,
        "userAnswer": "C",
        "correctAnswer": "C"
      }
    ],
    "items": [
      {
        "answerId": null,
        "questionId": 55120,
        "number": 1,
        "typeId": null,
        "typeIdMapping": "细节选择",
        "userAnswer": "C",
        "standardAnswer": "C",
        "answered": true,
        "correct": true,
        "points": null,
        "analysis": null,
        "questionSnapshot": null,
        "groupSnapshot": null,
        "optionSnapshot": null
      }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| reportId | Long | 【无变更】 | 与 `recordId` 同值（`practice_report` 表已删） |
| recordId | Long | 【无变更】 | 练习记录 ID |
| paperId | Long | 【新增】 | 试卷 ID |
| module | String | 【新增】 | `listening` / `reading` |
| sectionMapping | String | 【新增】 | `SEC_LISTEN` / `SEC_READ` |
| section | String | 【新增】 | 板块号 |
| status | Integer | 【新增】 | 记录状态 |
| reportStatus | String | 【修改】 | 收敛为 `PENDING/GENERATING/READY/FAILED`；原听力可能回 `PROCESSING` |
| retryable | Boolean | 【新增】 | 失败是否可重试；原听力用 `FAILED_RETRYABLE`/`FAILED_FINAL` 表达 |
| totalQuestions | Integer | 【修改】 | 题目总数；**原阅读字段名 `totalQuestionCount`** |
| answeredCount | Integer | 【无变更】 | 已答题数 |
| correctCount | Integer | 【无变更】 | 答对数 |
| wrongCount | Integer | 【无变更】 | 答错数（未作答计入错误） |
| accuracyRate | BigDecimal | 【无变更】 | 正确率百分比，保留 2 位小数；原听力为 Integer |
| durationSeconds | Integer | 【无变更】 | 用时秒数 |
| submittedTime | Long | 【无变更】 | 提交时间戳毫秒 |
| rows | Array | 【修改】 | 题号矩阵通用化（原听力 `rows` 字段名不变，`number` 取代 `no`） |
| rows[].number | Integer | 【无变更】 | 题号 |
| rows[].questionId | Long | 【无变更】 | 题目 ID |
| rows[].questionType | String | 【无变更】 | 题型名；阅读由 `typeIdMapping` 填充 |
| rows[].layout | String | 【无变更】 | 布局；**阅读恒 null** |
| rows[].answered | Boolean | 【无变更】 | 是否作答 |
| rows[].isCorrect | Boolean | 【无变更】 | 是否正确 |
| rows[].userAnswer | String | 【无变更】 | 用户答案 |
| rows[].correctAnswer | String | 【无变更】 | 正确答案 |
| items | Array | 【修改】 | 单题明细通用化（原阅读 `items` 扩展到听力） |
| items[].answerId | Long | 【无变更】 | 答案行 ID；**听力恒 null** |
| items[].questionId | Long | 【无变更】 | 题目 ID |
| items[].number | Integer | 【修改】 | 题号；**原阅读字段名 `questionNumber`** |
| items[].typeId / typeIdMapping | String | 【无变更】 | 题型；听力 `typeId` 恒 null、`typeIdMapping` 复用 `questionType` |
| items[].userAnswer / standardAnswer | String | 【无变更】 | 用户答案 / 标准答案 |
| items[].answered / correct | Boolean | 【无变更】 | 是否作答 / 是否答对 |
| items[].points | BigDecimal | 【无变更】 | 得分；**听力恒 null** |
| items[].analysis | String | 【无变更】 | 解析；**听力恒 null**（走逐题回顾端点） |
| items[].questionSnapshot / groupSnapshot / optionSnapshot | Object/Array | 【无变更】 | 冻结快照；**听力恒 null** |

**服务端内部执行顺序**

1. 解析模块，锁记录校验归属、状态、`baseVersion`
2. `finalAnswers` 先落库（幂等：`idempotencyKey` 命中直接返回已有结果）
3. 听力：比对标准答案快照逐题判分 → 写 `is_correct` / `points` → 汇总统计 → `reportStatus = READY`；**交卷后立即读一次报告视图**补 `rows` / `items`
4. 阅读：判分 → 生成报告 → 返回完整报告
5. 时长由服务端按在场累计结算（`max(start, paused, resumed)` 为段起点，单段上界 1800s），**不接受客户端上报**

**本接口抛出错误码**：8102 / 8103 / 8104 / 8105 / 8133 / 8164 / 8180 / 8181

---

#### 4.2.9 GET `{客观前缀}/{recordId}/report`

**用途**：查看报告（结构与交卷响应完全一致）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| recordId | path | Long | 是 | 练习记录 ID |
| module | query | String | 必传 | 【新增】模块码 |

**返回**：与 §4.2.8 交卷响应结构完全一致。

**服务端内部执行顺序**

1. 解析模块，校验归属与 `status=3`（未交卷回 `8105` / `8179`）
2. 读 `practice_record` 行作为统计来源（**报告即记录本身**）
3. 听力：按 `practice_answer` 快照组装矩阵；未就绪时 `rows` 为空、统计为 0
4. 阅读：读冻结快照组装明细，再由明细投影出矩阵
5. 统一填 `module` / `retryable` / `rows` / `items`

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
    "answerId": 771201,
    "questionId": 66001,
    "number": 36,
    "layout": null,
    "typeId": "read_choice",
    "typeIdMapping": "readChoice",
    "content": "作者认为最重要的原因是？",
    "passage": "（文章正文……）",
    "variant": null,
    "optionContent": { "A": "气候", "B": "地理", "C": "人口" },
    "audioUrl": null,
    "shareAudioUrl": null,
    "groupId": 8801,
    "group": { "groupId": 8801, "startNumber": 36, "endNumber": 40, "passage": "（文章正文……）", "optionContent": null },
    "optionPoolCode": "GROUP_8801",
    "exclusiveSharedOptions": false,
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

| 字段 | 类型 | 改动标记 | 说明 |
|---|---|---|---|
| answerId | Long | 【新增】 | 答案行 ID；听力恒 null |
| questionId ~ exclusiveSharedOptions | — | 【修改】 | 与拉题响应同名字段完全一致（题号 `number`、选项扁平、`audioUrl` 驼峰） |
| isCorrect | Boolean | 【无变更】 | 是否正确（未作答 false） |
| standardAnswer | String | 【无变更】 | 正确答案；**原阅读同名字段不变** |
| points | BigDecimal | 【新增】 | 本题得分；听力恒 null |
| analysis | String | 【无变更】 | 解析；无解析时阅读回「未录入解析内容」，听力回 null |

**本接口抛出错误码**：8102 / 8105 / 8133 / 8177 / 8181

---

#### 4.2.11 POST `{客观前缀}/{recordId}/report/retry`

**用途**：报告生成失败后重试
**鉴权**：需要登录
**前置条件**：`reportStatus = FAILED` 且 `retryable = true`，否则 `8106`

**返回**：与 §4.2.8 交卷响应结构完全一致（重试后重新读一次报告视图）。

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

> 对错、标记、收藏一律不在此接口 —— 对错只在报告接口。

**本接口抛出错误码**：8102 / 8112 / 8133 / 8161

---

### 4.3 主观族端点

主观族 12 个端点的清单见 §3.2。**请求体与响应体结构本次不变**，改动只有四处。

**路径与 `module` 解析**

```http
POST /practice/hsk/subjective/records/start?module=writing
```

旧的 `POST /practice/writing/records/start` 已下线，新路径必须带 `module`。

**开练语义**

`start` 只负责开新的练习：同一试卷同一板块已有未提交记录时直接返回该记录，不重置进度与计时；已提交后再调用则新建一条记录。服务端不提供重开接口，未提交的练习要继续用 `resume`，想从头再练一遍就在交卷后重新 `start`。

**单题作答与判分重试**

这两个端点三个模块通用，不做模块级放行。单题作答按模块落不同列：写作与翻译填 `answerText`，口语填 `answer`（音频地址）+ `durationMs`。判分重试只挑「已作答、有标准答案之外的 AI 评分题、且评分状态为失败」的行重新入队，三模块判定口径一致。

**幂等键口径**

交卷幂等键由服务端按 `{module}-{recordId}-submit` 拼（`writing-900812-submit`），不再取客户端 `Idempotency-Key` 头作为唯一来源。客户端传了也接受，但同一记录的重复交卷以服务端拼的键去重。

**本族抛出错误码**：8101–8119（通用）、8201+（写作）、8251+（翻译）、8281+（口语）

## 5. 错误码更新

| 错误码 | 服务 | 场景 |
|---|---|---|
| 8133 | practice-service | 【修改】合并路径后承担更多职责：`module` 缺失、取值不在白名单、与路径段冲突 |
| 8141 / 8142 | practice-service | 【无变更】听力续练时卷内容 / 板块配置已下架 |
| 8166 / 8167 / 8168 | practice-service | 【无变更】阅读试卷 / 板块不可练习、板块无题 |
| 8104 | practice-service | 【无变更】`baseVersion` 不一致；本次对阅读也要求传 `baseVersion`（但不校验） |

## 6. 前端对接注意事项

1. **路径一次性切换，没有过渡期**：旧路径（`/listening/records/**`、`/reading/records/**`、`/writing/records/**`、`/translation/records/**`、`/speaking/records/**`，含五条答题卡）已全部下线，请求会返回 `404`。前端必须在同一版本内改完所有调用点，并给每个请求补 `module`。
2. **听力字段名有 4 处改动**，是本次唯一的破坏性变更：`no` → `number`、`audio_url` → `audioUrl`、`option_content` → `optionContent`、`share_audio_url` → `shareAudioUrl`；答案请求字段 `selectedOptionId` → `answer`。
3. **阅读选项结构简化**：`optionContent` 从 `{"options":{"A":"…"}}` 变成 `{"A":"…"}`，取选项少拆一层。
4. **`baseVersion` 改为必传**：从记录响应新增的 `version` 字段取值。阅读侧服务端不校验，但必须带（否则 `400`）。
5. **报告页可以只写一套**：交卷与查报告返回同一结构，`rows` 画题号格子、`items` 画明细。听力 `items` 的 `analysis` / `points` / 快照字段为 null，解析要点进逐题回顾端点取。
6. **报告状态判断收敛**：不再有 `PROCESSING` / `FAILED_RETRYABLE` / `FAILED_FINAL`。用 `reportStatus == FAILED && retryable` 判断是否显示重试按钮。
7. **`currentPassageItemIndex` 阅读恒 null**：阅读侧不要再读这个字段判断翻页。
8. **口语板块域**：新数据用 `SEC_SPEAKING`；若前端有硬编码 `SEC_SPEAK` 的分支，本次要一并改（服务端两种都接受）。

## 7. 关键业务流程&事务边界

### 7.1 合并后的分层

```
Controller（2 族 6 个类）
  ├─ 客观族：ObjectiveRecordController / ObjectiveAnswerController / ObjectiveReportController
  └─ 主观族：SubjectivePracticeController
      ↓ 模块解析（ObjectiveModuleResolver / SubjectiveModuleResolver）
门面层（ObjectivePracticeService；主观族直接复用 SubjectivePracticeService）
      ↓ 分派 + DTO 转换
实现层（听 / 读各一套 service，写 / 译 / 说共用一套）
```

**为什么客观族保留两套实现**：取题口径不同 —— 听力按 `question_ids` 回 `question` 表现查，阅读直接读 `practice_answer` 冻结快照。合并实现会把这条差异变成 `if (module == READING)`，反而更难维护。

### 7.2 事务边界

| 操作 | 事务 | 要点 |
|---|---|---|
| 开练 | `@Transactional` | 行锁查草稿 → 废弃旧草稿 → 插记录 + 逐题占位行，同一事务 |
| 单题 / 批量保存 | `@Transactional` | 锁记录 → 锁答案行 → 写答案 → 重算 `answeredCount`，同一事务 |
| 暂停 / 恢复 | `@Transactional` | 时长结算与位置更新同事务；`resume` 清 `paused_time` 必须走显式 UPDATE 并同时写 `resumed_time` |
| 交卷 | `@Transactional` | 落 finalAnswers → 判分 → 汇总 → 置 `reportStatus`，同一事务；幂等命中直接返回 |
| 报告重试 | `@Transactional` | 置 `GENERATING` → 重算 → 置 `READY` |

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
| 8 | 阅读批量保存传任意 `baseVersion` | 200（服务端不校验） |
| 9 | 听力交卷 | 返回完整报告，`rows` 与 `items` 均有数据 |
| 10 | 阅读交卷 | 返回完整报告，`items` 带快照，`rows` 由明细投影、题号一致 |
| 11 | 报告状态为 `FAILED` | `retryable=true`，重试后回到 `READY` |
| 12 | `POST /hsk/subjective/records/start?module=translation` | 正常开练 |
| 13 | `POST /hsk/subjective/records/{id}/report/retry?module=translation` | 200，失败题重新入队 |
| 14 | `POST /hsk/subjective/records/{id}/questions/1/answers?module=writing` | 200，落 `answer_text` |
| 15 | `POST /hsk/subjective/records/{id}/questions/1/answers?module=speaking` | 200，落 `answer` + `duration_ms` |
| 16 | 同一记录用同一幂等键交卷两次 | 第二次直接返回已有结果，不重复判分 |
| 17 | `/hsk/objective/records/{id}/answer-card?module=reading` | 200，返回阅读答题卡；`/reading/records/{id}/answer-card` 回 `404` |
| 18 | 同一试卷同一板块，未提交时再调 `start` | 返回同一条记录，`recordId` 与进度不变 |
| 19 | 已交卷后调 `start` | 新建一条记录，`recordId` 与上次不同，进度归零 |

## 9. 上线执行事项【P0阻断项】

### 9.1 存量数据补数 SQL

**无**。本次无 DDL、无数据订正。

口语板块域的历史拼写 `SEC_SPEAK` 未订正（服务端两种都接受），如需统一见 §10。

### 9.2 文件级变更清单

| 文件路径 | 改动内容 |
|---|---|
| `hsk/objective/enums/ObjectiveModule.java` | 【新增】客观族模块枚举 |
| `hsk/objective/dto/*.java`（14 个） | 【新增】客观族统一 DTO |
| `hsk/objective/support/ObjectiveModuleResolver.java` | 【新增】模块解析，只认 `module` 参数，缺失 / 非法回 8133 |
| `hsk/objective/support/ObjectiveDtoMapper.java` | 【新增】两套内部 DTO → 统一契约转换 |
| `hsk/objective/service/ObjectivePracticeService.java` + `impl` | 【新增】门面分派 |
| `hsk/objective/controller/*.java`（3 个） | 【新增】客观族 11 个端点（答题卡端点另计，见下方 `AnswerCardController` 行） |
| `hsk/subjective/controller/SubjectivePracticeController.java` | 【新增】写 / 译 / 说 12 个端点合一 |
| `hsk/subjective/support/SubjectiveModuleResolver.java` | 【新增】模块解析，只认 `module` 参数，缺失 / 非法回 8133 |
| `listening/controller/*.java`（3 个） | 【删除】由客观族控制器接管 |
| `reading/controller/*.java`（3 个） | 【删除】同上 |
| `subjective/controller/{Writing,Translation,Speaking}PracticeController.java` | 【删除】由主观族控制器接管 |
| `hsk/answer/enums/AnswerCardModule.java` | `SPEAKING` 板块域改 `SEC_SPEAKING`，新增 `fromCodeOrNull`，`pathSegment` 字段更名 `code` |
| `hsk/answer/controller/AnswerCardController.java` | 【修改】删除五条按模块的旧路径，只保留两条合并路径 |
| `hsk/answer/service/impl/AnswerCardServiceImpl.java` | 注释订正（`SEC_SPEAKING` 为官方值） |
| `listening/dto/ListeningRecordResponse.java`、`reading/dto/ReadingRecordResponse.java` | 新增 `version` 字段 |
| `listening/service/impl/ListeningRecordServiceImpl.java`、`reading/service/impl/ReadingRecordServiceImpl.java` | `toResponse` 回填 `version` |
| `hsk/support/HskPracticeErrorCode.java` | 删除 `MODULE_ENDPOINT_NOT_SUPPORTED(8120)`，模块级端点限制取消后无引用 |
| `csca/controller/CscaFavoriteController.java` | 补回缺失的类闭合大括号（原本导致全模块编译失败） |

### 9.3 环境状态

- 编译：主源 321 文件 + 测试源 46 文件，**0 错误**
- 单测：`374 tests / 374 passed / 0 failed`
- TEST / PROD：未部署（本次仅代码与文档）

## 10. 待确认事项

| # | 待确认点 | 暂定方案 | 确认人 |
|---|---|---|---|
| 1 | 前端切换窗口 | 旧路径已下线，需与后端同版本上线 | 前端 |
| 2 | 阅读是否要真正启用 `baseVersion` 乐观锁 | 暂只要求传、不校验（避免引入新的失败路径） | 后端 |
| 3 | 是否订正 `SEC_SPEAK` 存量配置（24 + 8 行） | 暂不订正，服务端双值兼容 | DBA / 后端 |
| 4 | 听力 `items[].analysis` 是否也要填（当前恒 null） | 暂不填，解析走逐题回顾端点，避免报告响应体过大 | 产品 |
| 5 | 网关白名单登记 | 必须登记 `/hsk/objective/**`、`/hsk/subjective/**`，并确认旧前缀已从白名单移除 | 运维 |
