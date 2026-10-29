# HSK 翻译练习 · 独立模块接口方案

> 服务：`practice-service`（网关 `/api/practice`）
> 依据：2026-10-27 三张 UI 截图（模块卡 / 翻译卷列表 / 翻译题型页）+ TEST 库实测
> 文档版本：v1.0 · 2026-10-27
> 前置文档：`docs/HSK练习模块首页-设计方案.md`（本方案推翻其中的 T2「视图层入口」，改为**独立模块**）

---

## 0. 结论（先回答"要不要新写接口"）

**要，但只新写 4 个目录接口；写链路不用重写。**

| 层 | 是否需要新写 | 说明 |
|---|---|---|
| 等级 / 卷 / 板块（4 个 GET） | ✅ **必须新写** | 写作接口返回的是「书写 + 笔译」混合，且口译根本不在目录里，无法靠参数救 |
| 开始练习 / 答题 / 提交 / 报告 | ⭕ **可复用** | 现有 `writing_attempt` 链路**已经能吃 `SEC_TRANSLATION`**（`PracticeSections.isWriting` 含它），`writing_answer.answer_json` 也能存音频 |
| 数据库表 | ❌ **不用新建** | 复用 `writing_*` 7 张表；实测翻译在该 structure 下 `writing_attempt` 为 **0 行**，无历史数据包袱 |

**但真正的拦路虎不是接口，是数据。** TEST 库实测：

- 翻译只有 **1 套卷**（`HSK7-9_1`）、**4 道题**（笔译 2 + 口译 2）；
- **口译 2 题在目录里根本不存在**（被投影器显式排除）；
- 4 题**参考答案全是 `(略)`**、无解析 → 主观题**评不了分**（口译不需要音频，题面就是英文原文）；
- 而 UI 画的是 **4 套卷 × 每卷 20 题**（已确认是假数据，不用管）。

---

## 1. 实测数据（TEST 库，2026-10-27）

### 1.1 目录三张表

| 表 | SEC_TRANSLATION 现状 |
|---|---|
| `practice_module_level_config` | ✅ **已有 1 行**：`HSK3.0 / level=7`，`parts_config` 已写好「第一部分 笔译 2 题 / 第二部分 口译 2 题」，`total_question_count=4`，`suggested_duration_minutes=42`，`enabled=1` |
| `practice_paper_structure` | 1 行：`paper_id=2104188199979532289`（`HSK7-9_1`），`section_name=第3部分`，`question_count=2` |
| `practice_part_setting` | 1 行：`section_code=1`、`type_code=translation_written`、`answer_mode=TEXT` —— **只有笔译** |

> 对比其他模块：LISTEN 446 行 / READ 474 / WRITE 166 / SPEAK 207 / **TRANSLATION 1**。

### 1.2 题库 `question`

| id | section | number | 类型 | 分值 | audio_url | content | passage |
|---|---|---|---|---|---|---|---|
| 2104188202143793154 | 1 | 83 | `translation_written` 笔译 | 25 | ❌ NULL | 空 | 695 字 |
| 2104188202143793155 | 1 | 84 | `translation_written` 笔译 | 25 | ❌ NULL | 空 | 1474 字 |
| 2104188202223484929 | 2 | 85 | `translation_oral` 口译 | 25 | ❌ NULL | 空 | 612 字 |
| 2104188202223484930 | 2 | 86 | `translation_oral` 口译 | 25 | ❌ NULL | 空 | 573 字 |

🔴 **三个数据坑**：
1. `content` 全为空，**正文在 `passage`** → 前端渲染题干必须读 `passage`，否则白屏；
2. `layout` 全为 NULL → 与阅读/听力不同，翻译题**没有版式 JSON**；
3. 口译无 `audio_url` → 口译题**没有可播放的原文音频**，做不了。

### 1.3 历史答题数据

`writing_attempt` 共 214 行，其中 `structure_id=7000178435150355785`（翻译笔译板块）**0 行** → 拆模块不会产生"历史练习无处可去"的问题（PROD 上线前需二次确认）。

---

## 2. 现在的链路是怎么容纳翻译的（关键认知）

```
题库 question(section_mapping=SEC_TRANSLATION)
        │
        ├─ 笔译 section=1 ──► 投影器生成目录行 ──► 写作目录可见（writingMappings 含 SEC_TRANSLATION）
        │                                        └─ WritingAttemptServiceImpl:266 用 isWriting() 校验 → ✅ 能开练习
        │
        └─ 口译 section=2 ──► PracticeCatalogDeriver.isExcluded() 直接丢弃 ──► ❌ 任何模块都看不到
```

三个由此推导出的事实：

- **写作卷的板块列表里现在会多出一个「翻译 第3部分」**（`WritingCatalogServiceImpl.listParts` 按纸卷的 `paper_structure` 遍历，不过滤 `content_type`）；
- **笔译其实已经能做题**，走的就是写作的 attempt/answer/report 链路；
- **口译连目录都没有**，所以 UI 上那行「第二部分：口译」现在点了必然报错。

---

## 3. 三种"分开写"的切法

| | 切法 A：只分读 | 切法 B：读分开 + 写薄封装 | 切法 C：完全独立 |
|---|---|---|---|
| 新增端点 | 4 个目录 | 4 目录 + 约 10 个写接口薄封装 | 14 个端点 + 新表 |
| 前端调用 | 目录走 `/translation/**`，答题走 `/writing/attempts/**` | 全走 `/translation/**` | 全走 `/translation/**` |
| 持久层 | 复用 `writing_*` | 复用 `writing_*` | 新建 `translation_*` 7 张表 |
| 改动量 | 2 天 | 3.5 天 | 10 天+ |
| 主要风险 | 前端要维护两套 basePath，容易被后人误改 | 薄封装里若漏了归属校验会串号 | 评分/报告/统计全部重造，工期最长 |
| 后续成本 | 低 | 低 | 高（两套报表口径） |

**推荐切法 B**：接口层面彻底分开（前端只见 `/translation/**`），实现层委托 `WritingAttemptService` 等既有 Service，不复制表、不复制评分。

> 切法 B 的薄封装写法要点：Controller 里只做「`requireAuthenticatedAppUserId` → 调既有 Service → 返回」，**不要重写业务**；每个封装方法先校验 `structureId` 的 `section_mapping='SEC_TRANSLATION'`，防止有人拿写作的 structureId 打翻译接口。

---

## 4. 接口清单（切法 B）

### 4.1 目录（新增，只读）

#### ① `GET /translation/levels?version=HSK3.0`

返回**数组**（与阅读/写作/口语一致，区别于听力的单对象）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | string | 回显，未传回 `HSK2.0` |
| `level` | int | 7（HSK7-9 存的是 7） |
| `levelCode` | string | **`HSK7-9`** |
| `levelName` | string | 「HSK 七至九级」 |
| `abilityDescription` / `En` / `Vi` | string | 直接取自 `practice_module_level_config` 三语字段 |
| `totalQuestionCount` | int | 4（当前） |
| `suggestedDurationMinutes` | int | 42 |
| `enabled` | boolean | — |
| `sections[]` | array | **`/levels` 返回空数组**，`/intro` 才填（与阅读一致，减少首屏体积） |

⚠️ `version=HSK2.0` → **返回 `[]`**（HSK2.0 无翻译），前端据此把模块卡置灰。

#### ② `GET /translation/levels/{levelCode}/intro?version=HSK3.0`

单对象，`sections[]` 来自 `parts_config`：

```json
{ "partCode": "1", "partName": "第一部分", "questionTypeName": "笔译", "questionCount": 2, "sortOrder": 1 }
{ "partCode": "2", "partName": "第二部分", "questionTypeName": "口译", "questionCount": 2, "sortOrder": 2 }
```

#### ③ `GET /translation/papers?levelCode=HSK7-9&version=HSK3.0`

| 字段 | 说明 |
|---|---|
| `paperId` | **String**（19 位雪花，practice 未开 Long→String，前端必须按字符串接） |
| `paperCode` / `paperName` | 取 `practice_paper.source`（如 `HSK7-9_1`） |
| `totalQuestionCount` | 该卷翻译题总数（笔译 + 口译） |
| `completedQuestionCount` | 已交卷题数 |
| `status` | `NOT_STARTED` / `IN_PROGRESS` / `COMPLETED`（沿用写作的大写风格） |

> 卷清单过滤规则：`practice_paper` 中该等级下、且在 `practice_paper_structure` 里存在 `content_type='SEC_TRANSLATION'` 的卷；`totalQuestionCount=0` 的卷不下发。

#### ④ `GET /translation/papers/{paperId}/parts`

```json
{
  "paperId": "...", "paperCode": "HSK7-9_1",
  "parts": [
    { "structureId": "7000178435150355785", "partCode": "1", "partName": "第一部分",
      "questionTypeName": "笔译", "answerMode": "TEXT", "questionCount": 2,
      "status": "IN_PROGRESS", "answeredCount": 1, "correctCount": null, "wrongCount": null,
      "draftAttemptId": "...", "latestReportId": null, "hasReport": false },
    { "structureId": "...", "partCode": "2", "partName": "第二部分",
      "questionTypeName": "口译", "answerMode": "AUDIO", "questionCount": 2,
      "status": "NOT_STARTED", "answeredCount": 0, "correctCount": 1, "wrongCount": 1,
      "latestReportId": "...", "hasReport": true }
  ]
}
```

🔴 关键：`answerMode` 必须下发（`TEXT` / `AUDIO`），前端据此决定渲染文本框还是录音按钮 —— 这正是 UI 里笔译/口译两张卡长得不一样的原因。

### 4.2 写链路（薄封装，内部委托写作 Service）

| 方法 | 路径 | 委托 |
|---|---|---|
| POST | `/translation/attempts/start` `{paperId, structureId}` | `WritingAttemptService#start` |
| GET | `/translation/attempts/{attemptId}` | 同上 `#get` |
| GET | `/translation/attempts/{attemptId}/questions` | 同上 `#listQuestions` |
| POST | `/translation/attempts/{attemptId}/pause` | 同上 `#pause` |
| PUT | `/translation/attempts/{attemptId}/answers` | `WritingAnswerService#save` |
| GET | `/translation/attempts/{attemptId}/answer-card` | 同上 `#get` |
| POST | `/translation/attempts/{attemptId}/sessions`（+`/heartbeat`、`/end`） | `WritingSessionService` |
| POST | `/translation/attempts/{attemptId}/submit` | `WritingSubmissionService` |
| GET | `/translation/reports/{reportId}`（+`/status`、`/questions/{qid}`） | `WritingReportService` |
| GET | `/translation/parts/{structureId}/reports/latest` | 同上 `getLatest` |

统一前置校验：`partSetting(structureId).section_mapping == 'SEC_TRANSLATION'`，否则 400。

---

## 5. 必须同步改的 4 处存量代码

| # | 位置 | 改什么 | 不改会怎样 |
|---|---|---|---|
| 1 | `PracticeCatalogDeriver.isExcluded()` | 口译（`section=2` / type 含 `oral`）**不再排除**，改为生成目录行 | UI 第二张卡（口译）永远空，点进去 404 |
| 2 | `PracticeSections.writingMappings()` | **只保留 `SEC_WRITE`** | 笔译会同时出现在「写作」和「翻译」两个入口，同一题练两次、进度两份 |
| 3 | `WritingCatalogServiceImpl#listParts / #listPapers` | 显式排除 `SEC_TRANSLATION` | 写作卷的板块里仍会冒出「翻译 第3部分」 |
| 4 | `WritingAttemptServiceImpl:266` 的 `isWriting()` 校验 | **保留**（因为翻译答题复用写作 attempt） | 若跟着第 2 条一起改，翻译题就开不了练习 |

> 🔴 第 2 条和第 4 条是**成对**的：**目录层剥离、写链路保留**。改动时必须一起看，否则要么写作露两次、要么翻译做不了题。
> 🔴 改完必须**重建一次目录**（`PracticeCatalogProjector`），否则 `practice_part_setting` 里不会出现口译行。

---

## 6. 数据缺口清单（比接口重要）

| # | 缺口 | 现状 | 影响 | 归属 |
|---|---|---|---|---|
| 1 | 口译目录行 | 0 行 | 口译入口不可用 | 后端跑重建脚本 |
| 2 | ~~口译音频~~ **不需要** | 口译题面是**英文文字**（`passage`：`According to a survey, in 2020, more than 30%…`），用户看文字、口头译成中文 → **不需要 `audio_url`** | 无 | — |
| 2.1 | 参考答案 | 4 题 `answer` 全部是 **`(略)`**、`analysis` 为空 | 笔译与口译**都没有参考译文**，AI 评分无参照物 | 题库导入 |
| 2.2 | 录音链路 | 无专用接口，但 `system-service` 有 `POST /file/uploadVoice`（MinIO + 音频 MIME 校验） | 前端录音后先传文件拿 URL，再存进 `writing_answer.answer_json` | 前端 + 约定 |
| 3 | 卷数量 | 1 套（UI 要 4 套） | 列表只有 1 张卡 | 题库导入 |
| 4 | 题干位置 | `content` 空、正文在 `passage` | 前端渲染错就白屏 | 前端 + 约定 |
| 5 | 题量口径 | 真实 4 题/卷，UI 写「10/20」 | 进度条对不上 | **产品确认** |
| 6 | 翻译评分 | 笔译靠 `writing_evaluation`（AI 作文评分）；口译需 ASR + 发音评测（`ai-service` 的 `SpeechAssessment` / `SpeakingEvaluation` 已有基础设施，但**未接翻译**） | 口译交卷后没有分数 | 需单独立项 |
| 7 | **评分策略行缺失（P0 阻塞）** | `writing_evaluation_policy` 只有 5 个题型：`WORD_ORDER` / `HANZI_INPUT` / `PICTURE_SENTENCE` / `KEYWORD_ESSAY` / `SUMMARY_WRITING`，**没有 `TRANSLATION_WRITTEN`**（也没有 7-9 的 `CHART_ANALYSIS` / `TOPIC_ESSAY`） | `WritingEvaluationTaskProcessor:115` 查不到 policy 直接抛 `evaluation policy missing` → 任务失败 → 报告卡在「评分中/失败」 | 补 1 行 policy（笔译）；7-9 写作同样缺，属存量问题 |

---

## 6.1 口译的真实形态（已澄清，2026-10-27）

**口译 = 给一段英文文字（`passage`），用户口头翻译成中文。** 题面不需要音频，`audio_url` 为空是正常的。

所以口译 P0 就能做，作答链路是：

```
前端录音 ──► POST /file/uploadVoice?fileType=translation（system-service，MinIO）
         ──► PUT /translation/attempts/{id}/answers
             { questionId, answerType:"AUDIO", answerJson:{ audioUrl, duration } }
         ──► writing_answer.answer_type='AUDIO' + answer_json 存 URL（字段已够用，无需建表）
```

因此口译**不阻塞在"没音频"上，阻塞在"没法评分"上**：

| 问题 | 现状 | 可选处置 |
|---|---|---|
| 参考答案 | `answer='(略)'`、`analysis` 空 | 补参考译文（AI 评分必需）或改人工/抽样评估 |
| 评分策略 | `writing_evaluation_policy` 无 `TRANSLATION_WRITTEN` | 补 1 行 policy |
| 对错口径 | 主观题没有"对/错"，UI 的「1对1错」不成立 | 只出分数 + 反馈，或按阈值折算对错 |

**建议**：P0 口译做成「能录、能存、能复听」，报告显示**待评分**；P1 补齐参考译文 + policy 后再出分。

---

## 7. 分期建议

| 期 | 范围 | 前置 |
|---|---|---|
| **P0** | 4 个目录接口（笔译 + 口译都下发，`answerMode` 区分 TEXT/AUDIO）+ 写作目录剥离翻译 + 口译可**录音存档与复听**（报告显示「待评分」） | ① 放行 `PracticeCatalogDeriver.isExcluded` 的口译排除 + 重建目录；② `writing_evaluation_policy` 补 `TRANSLATION_WRITTEN` 行（笔译出分用） |
| **P1** | 写链路薄封装 `/translation/attempts/**`（URL 全分开）；补参考译文后**笔译/口译出分** | 题库补 `answer`/`analysis` |
| **P2** | 卷补到 4 套；学习报告对齐 UI（主观题不出"对错"） | 题库导入 + ai-service 接翻译评分 |
| **P2** | 口译自动评分（ASR + 评测）；卷补到 4 套；学习报告对齐 UI | ai-service 接入 |

> 若 P0 就要 UI 全量上线，**必须先把口译卡置灰**（用 §4.1 ① 的 `enabled` 或 `answerMode` 判断），不要让用户点进空板块。

---

## 8. 验收用例

1. `version=HSK2.0` 调 `/translation/levels` → `[]`，模块卡置灰。
2. `version=HSK3.0` → 返回 1 个等级 `HSK7-9`，`totalQuestionCount=4`。
3. `/translation/papers?levelCode=HSK7-9` → 1 套卷，`paperId` 为字符串、末位不缺精度。
4. `/translation/papers/{id}/parts` → **2 个 part**，笔译 `answerMode=TEXT`、口译 `answerMode=AUDIO`。
5. 用**写作**的 structureId 打 `/translation/attempts/start` → 400。
6. 笔译开始练习 → 答题 → 提交 → 报告有客观题对错。
7. 写作页的板块列表**不再出现**翻译部分。
8. 已存在的写作练习（历史 214 条）不受影响，仍可打开。
9. 未登录调目录接口 → 200 但 `status` 恒 `NOT_STARTED`（与听力一致）。
10. 口译板块在音频缺失时应返回 `answerMode=AUDIO` 但前端置灰（或后端 `enabled=false`）——二者选一，需产品定。

---

## 9. 待确认

1. **UI 的「已完成 10/20」口径**：翻译真实是 4 题/卷，20 从哪来？
2. 口译是否 P0 就要可点（决定要不要先补音频）。
3. 笔译从写作里剥离后，**写作历史报告**里的题量口径会变小，是否需要公告/兼容？
4. `/translation/**` 是否需要单独网关路由白名单（目前 practice 统一 `/api/practice`，无需新增，确认一下即可）。
