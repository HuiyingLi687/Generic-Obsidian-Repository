# 真题练习 - 口语模块接口设计

> 基于《真题练习-口语模块.pdf》与现有 `practice-service` 阅读模块架构分析得出。复用 `practice` 核心 13 张实体表（`PracticeRecord`/`PracticeAnswer`/`PracticeReport` 等），口语专属逻辑围绕"录音上传-版本追踪-AI 评分-报告快照"展开。
>
- 模块包路径：`com.hsktreasure.practice.speaking`
- 网关前缀：`/api/practice/speaking`（网关剥离 `/api`，Controller 内部路径为 `/practice/speaking`）
- 三层架构：Controller（参数接收+鉴权） → Service（业务编排） → Mapper（数据访问，复用 `practice.core.mapper`）
- 鉴权约定：所有写操作与个性化查询需 `Authorization: Bearer <APP_JWT>` + `X-Client-Type: APP`，通过 `BaseController.requireAuthenticatedAppUserId(request, clientType)` 解析 `userId`，作为 Service 首参，禁止信任客户端传入的 userId。
- 统一响应：`Result<T>` 包络 `{code, message, data}`；业务错误 HTTP 200 + 非 200 code（`BusinessException(ErrorCode)`）。

---

## 一、模块分层结构

```
com.hsktreasure.practice.speaking
├── controller
│   ├── SpeakingCatalogController   # 目录：等级/试卷/板块/备考说明/偏好
│   ├── SpeakingRecordController    # 作答记录：开始/恢复/暂停/废弃/列表
│   ├── SpeakingAnswerController    # 录音作答：上传/确认/重录/批量保存/答题卡
│   └── SpeakingReportController    # 报告：提交/查询/重试/单题解析
├── dto
│   ├── Speaking*Request / Speaking*Response  # 命名对齐 Reading*
│   └── SpeakingAnswerSaveRequest  # 含 audioUrl + durationSeconds + clientSequence + recordingVersion
├── service
│   ├── SpeakingCatalogService / SpeakingRecordService / SpeakingAnswerService / SpeakingReportService
│   ├── SpeakingScoringService        # 调用 AI 评价服务（异步）
│   ├── SpeakingAudioService          # 录音文件上传/校验/MinIO 落桶
│   └── impl/  + internal/            # 内部包：SpeakingReportGenerator、SpeakingSubmissionFinalizer
└── enums
    └── SpeakingPaperStatus          # 对齐 ReadingPaperStatus
```

**复用核心实体（不新增表）：** `PracticePaper`、`PracticePaperStructure`（板块）、`PracticeQuestionGroup`、`PracticeQuestion`、`PracticeRecord`、`PracticeAnswer`、`PracticeReport`、`PracticePartSetting`、`PracticeModuleLevelConfig`、`PracticeLevelConfig`、`PracticeUserPreference`。

**需补充的元数据：**
- `ExamSection` 枚举新增 `SEC_SPEAK("SEC_SPEAK", "口语")`，作为口语模块的 `sectionMapping`。
- `PracticeQuestion` 通过 `optionContent`（JSON）承载 `picUrl`、`referenceAnswer`、`audioTime`、`waittingTime`、`recordingParams`（`minValidDurationSeconds`/`maxRecordDurationSeconds`/`recommendedDurationSeconds`/`audioFormatProfile`/`allowRerecord`）。
- `PracticeAnswer.answer` 存放已确认的录音 URL；`points`(BigDecimal) 存 AI 评分；`questionSnapshot`/`groupSnapshot`/`optionSnapshot` 在提交时固化快照。
- `PracticeRecord` 复用 `status`(0创建/1进行中/2废弃/3已提交)、`reportStatus`(0待生成/1生成中/2就绪/3失败)、`idempotencyKey`、`version`(乐观锁)。

---

## 二、接口清单总览

| 序号 | 方法 | 路径 | 鉴权 | 说明 | 对应页面 |
|---|---|---|---|---|---|
| 1 | GET | `/practice/speaking/levels` | 否 | HSKK 等级列表 | 试卷选择页 |
| 2 | GET | `/practice/speaking/levels/{levelCode}/intro` | 否 | 备考说明（能力/时间/题量/题型） | 备考说明页 |
| 3 | GET | `/practice/speaking/preferences` | 是 | 用户上次选择等级/试卷 | 试卷选择页 |
| 4 | PUT | `/practice/speaking/preferences/level` | 是 | 更新上次选择等级 | 试卷选择页 |
| 5 | GET | `/practice/speaking/papers?levelCode=HSKK1` | 是 | 试卷列表+进度 | 试卷选择页 |
| 6 | GET | `/practice/speaking/papers/{paperId}/parts` | 是 | 板块（题型）列表+完成进度 | 题型选择页 |
| 7 | POST | `/practice/speaking/records/start` | 是 | 新建/恢复/重开作答记录 | 题型选择页【练习】 |
| 8 | GET | `/practice/speaking/records/{recordId}` | 是 | 获取作答记录状态 | 答题页恢复 |
| 9 | GET | `/practice/speaking/records/{recordId}/questions` | 是 | 题目清单（含素材+录音参数） | 答题页 |
| 10 | POST | `/practice/speaking/records/{recordId}/pause` | 是 | 暂停保存（草稿） | 退出/切后台 |
| 11 | POST | `/practice/speaking/records/{recordId}/abandon` | 是 | 废弃草稿 | 退出确认 |
| 12 | POST | `/practice/speaking/records/{recordId}/answers/{questionId}/audio` | 是 | **录音上传**（临时授权+落桶） | 录音结束 |
| 13 | PUT | `/practice/speaking/records/{recordId}/answers/{questionId}/confirm` | 是 | **录音确认绑定**（版本+幂等+冲突检测） | 上传成功 |
| 14 | PUT | `/practice/speaking/records/{recordId}/answers/{questionId}` | 是 | 单题作答保存（当前题号+草稿） | 切题/防抖 |
| 15 | PUT | `/practice/speaking/records/{recordId}/answers` | 是 | 批量保存草稿 | 强制保存点 |
| 16 | GET | `/practice/speaking/records/{recordId}/answer-card` | 是 | 答题卡（已答/未答/当前题） | 答题卡弹窗 |
| 17 | POST | `/practice/speaking/records/{recordId}/submit` | 是 | **提交事务**（幂等+快照+评分任务） | 提交确认 |
| 18 | GET | `/practice/speaking/records/{recordId}/report` | 是 | 学习报告（含题号矩阵） | 学习报告页 |
| 19 | POST | `/practice/speaking/records/{recordId}/report/retry` | 是 | 重新触发 AI 评分 | 报告失败重试 |
| 20 | GET | `/practice/speaking/parts/{structureId}/reports/latest` | 是 | 板块最近一次报告 | 题型页【学习报告】 |
| 21 | GET | `/practice/speaking/records/{recordId}/report/questions/{questionId}` | 是 | **单题解析**（录音回放+AI 评语） | 单题解析弹窗 |

---

## 三、接口详细设计（三层代码逻辑）

### 1. SpeakingCatalogController（目录）`@RequestMapping("/practice/speaking")`

#### 1.1 GET `/levels` — HSKK 等级列表
- **Controller**：无入参；从 `Accept-Language` 头解析语言（zh/en/vi，默认 zh）；调 `speakingCatalogService.listLevels(lang)` 返回 `Result<List<SpeakingLevelResponse>>`。
- **Service**：查 `PracticeModuleLevelConfig` 中 `sectionMapping='SEC_SPEAK' AND enabled=1` 的记录，按 `sortOrder` 排序；按语言字段映射 `levelName`；空集合时返回空列表（不抛错，前端展示空状态）。
- **Mapper**：`PracticeModuleLevelConfigMapper.selectList(Wrappers.<PracticeModuleLevelConfig>lambdaQuery().eq(...).eq(...).orderByAsc(...))`。

#### 1.2 GET `/levels/{levelCode}/intro` — 备考说明
- **Controller**：路径参 `levelCode`；调 `service.getLevelIntro(levelCode, lang)` 返回 `SpeakingIntroSectionResponse`（能力说明、建议时间、总题量、三题型板块及题量、录音播放说明）。
- **Service**：查 `PracticeLevelConfig` + `PracticeModuleLevelConfig` + `PracticePartSetting`（按 `structureId` 关联 `PracticePaperStructure`），聚合为一段说明；缺失时返回 `null`/空（前端展示"该等级考试说明暂未配置"）。
- **Mapper**：三表联查，使用 `PracticeLevelConfigMapper` + 自定义 XML `selectIntroByLevel`。

#### 1.3 GET `/preferences` — 用户偏好
- **Controller**：`requireAuthenticatedAppUserId`；调 `service.getPreference(userId)`。
- **Service**：查 `PracticeUserPreference` where `userId=? AND sectionMapping='SEC_SPEAK'`；不存在则返回默认等级。
- **Mapper**：`PracticeUserPreferenceMapper.selectOne(...)`。

#### 1.4 PUT `/preferences/level` — 更新偏好
- **Controller**：`@RequestBody @Valid SpeakingPreferenceUpdateRequest{levelCode}`；调 `service.updatePreference(userId, levelCode)`。
- **Service**：upsert `PracticeUserPreference`（`sectionMapping='SEC_SPEAK'`），以 `(userId, sectionMapping)` 唯一约束为准。
- **Mapper**：`PracticeUserPreferenceMapper.insert/updateById`。

#### 1.5 GET `/papers?levelCode=` — 试卷列表+进度
- **Controller**：`requireAuthenticatedAppUserId`；`@RequestParam levelCode`；调 `service.listPapers(userId, levelCode)` 返回 `List<SpeakingPaperResponse>`（含 `paperId, paperName, status, completedCount, totalCount`）。
- **Service**：查 `PracticePaper`（`level=levelCode AND sectionMapping='SEC_SPEAK'`）；对每张试卷，按 `structureId` 聚合用户已提交板块覆盖题数（`PracticeRecord.status=3 AND reportStatus=2`）；`Y` = 试卷总题数（取发布快照），`X` = 已完成板块覆盖题数；空试卷不返回。
- **Mapper**：`PracticePaperMapper.selectList(...)` + `PracticeRecordMapper.selectSubmittedStructures(userId, paperId)`（自定义 XML，按 structureId 汇总已提交题数）。

#### 1.6 GET `/papers/{paperId}/parts` — 板块列表+进度
- **Controller**：`requireAuthenticatedAppUserId`；调 `service.listParts(userId, paperId)` 返回 `List<SpeakingPartResponse>`。
- **Service**：查 `PracticePaperStructure`（`paperId=? AND sectionMapping='SEC_SPEAK'`），按 `sortOrder` 排序；对每个板块，查 `PracticeQuestion` 统计 `totalQuestions`；查 `PracticeRecord` 最新一次已提交记录（`status=3`）以判定是否已完成；查未提交草稿（`status=1`）以判定"已做 X 题"。
- **Mapper**：`PracticePaperStructureMapper.selectList(...)` + `PracticeQuestionMapper.countByStructure(structureId)` + `PracticeRecordMapper.selectLatestSubmitted(...)` / `selectDraft(...)`。

---

### 2. SpeakingRecordController（作答记录）`@RequestMapping("/practice/speaking/records")`

#### 2.1 POST `/start` — 新建/恢复/重开
- **Controller**：`@RequestBody @Valid SpeakingRecordStartRequest{paperId, structureId, restart}`；`requireAuthenticatedAppUserId`；调 `service.start(userId, request)` 返回 `SpeakingRecordResponse`。
- **Service**（核心判定）：
  1. 校验 `paperId`+`structureId` 存在且 `sectionMapping='SEC_SPEAK'`，状态可用（未下架、未封禁）。
  2. 查 `PracticeRecord` 中 `(userId, structureId)` 的草稿（`status IN (0,1)`）。
  3. 若 `restart=true` 或无草稿：新建 `PracticeRecord`（`status=1, reportStatus=0, version=1, idempotencyKey=null`），新建空 `PracticeAnswer` 行（每题一条，`answered=0`）。
  4. 若存在草稿：返回草稿（恢复题号、有效时长、录音状态），**禁止自动新建、禁止覆盖本地录音**。
  5. 草稿版本已下架：沿用历史快照继续作答；被封禁：抛 `BusinessException(ErrorCode.RESOURCE_FORBIDDEN)`。
- **Mapper**：`PracticeRecordMapper.selectInProgressForUpdate(userId, structureId)`（`SELECT ... FOR UPDATE` 行锁防并发）+ `insert` + `PracticeAnswerMapper.insertBatch`。

#### 2.2 GET `/{recordId}` — 获取记录状态
- **Controller**：路径参 `recordId`；调 `service.get(userId, recordId)`。
- **Service**：校验 `recordId` 归属 `userId`（不归属抛 403）；加载 `PracticeRecord` + 全部 `PracticeAnswer`；组装 `SpeakingRecordResponse`（含 `status, reportStatus, currentQuestionId/Number, answeredCount, totalQuestions, resumeElapsedSeconds, List<...AnswerResponse>`）。
- **Mapper**：`PracticeRecordMapper.selectByIdForUpdate(recordId)` + `PracticeAnswerMapper.selectByRecord(recordId)`。

#### 2.3 GET `/{recordId}/questions` — 题目清单
- **Controller**：调 `service.listQuestions(userId, recordId)` 返回 `List<SpeakingQuestionResponse>`。
- **Service**：校验归属；按 `sortOrder` 加载 `PracticeQuestion`（+ 所属 `PracticeQuestionGroup`）；解析 `optionContent` JSON 取出 `picUrl, referenceAnswer, audioTime, waittingTime, recordingParams`；返回题干文本/拼音配对/图片 URL/题干音频 URL。
- **Mapper**：`PracticeQuestionMapper.selectByStructure(structureId)` + `PracticeQuestionGroupMapper.selectByIds(groupIds)`。

#### 2.4 POST `/{recordId}/pause` — 暂停保存
- **Controller**：`@RequestBody SpeakingRecordPauseRequest{currentQuestionId, currentQuestionNumber, durationSeconds, List<SpeakingAnswerSaveRequest> draftAnswers, clientSequence}`；调 `service.pause(...)` 返回 `SpeakingRecordResponse`。
- **Service**：
  1. `SELECT FOR UPDATE` 锁 `PracticeRecord`，校验 `status=1`。
  2. **乐观锁校验** `baseVersion`：`record.version == request.baseVersion`，否则抛 `BusinessException(ErrorCode.RECORD_VERSION_CONFLICT)`（多端冲突，前端提示用户选择版本）。
  3. 更新 `currentQuestionId/Number`、`durationSeconds`（累加）、`lastSavedTime`、`version+1`。
  4. 批量 upsert `PracticeAnswer`（仅草稿，不固化快照），录音 URL 仅在已确认时写入。
- **Mapper**：`PracticeRecordMapper.updateById`（带 `@Version`）+ `PracticeAnswerMapper.batchUpsert`（XML）。

#### 2.5 POST `/{recordId}/abandon` — 废弃草稿
- **Controller**：调 `service.abandon(userId, recordId)`。
- **Service**：校验归属；`UPDATE PracticeRecord SET status=2 WHERE id=? AND status IN(0,1)`；**不删除已上传录音文件**（保留审计），仅在 DB 标记记录废弃。
- **Mapper**：`PracticeRecordMapper.updateStatus(recordId, 2)`。

---

### 3. SpeakingAnswerController（录音作答）`@RequestMapping("/practice/speaking/records")`

#### 3.1 POST `/{recordId}/answers/{questionId}/audio` — 录音上传
> 客户端录音结束后立即上传，不阻塞切题；上传成功后才调 3.2 确认绑定。
- **Controller**：`@RequestParam MultipartFile file`；`requireAuthenticatedAppUserId`；调 `speakingAudioService.uploadAnswerAudio(userId, recordId, questionId, file)` 返回 `Result<SpeakingAudioUploadResponse>{audioUrl, recordingId, expiresAt}`。
- **Service**（`SpeakingAudioService`）：
  1. 校验 `recordId` 归属 + `status=1` + `questionId` 属于该板块。
  2. **MIME 模糊匹配 + 扩展名降级**（复用 `AudioMimeUtil`，已修复 .wav 变体问题）。
  3. 生成路径：`audio/{userId}/hsk-{paperId}/rec/{recordId}/{questionId}-{recordingVersion}-{uuid}.ext`。
  4. 调 `MinIOUtils.uploadFile(bucket, finalName, stream, true, mime)` 落桶。
  5. **生成短期授权 URL**（不暴露永久裸链），返回 `audioUrl + recordingId`（仅元数据，未绑定到 `PracticeAnswer`）。
- **Mapper**：仅查 `PracticeRecord` / `PracticeQuestion`，不写库。

#### 3.2 PUT `/{recordId}/answers/{questionId}/confirm` — 录音确认绑定
> 幂等：同一 `recordingVersion` 重复确认返回原结果。
- **Controller**：`@RequestBody @Valid SpeakingAudioConfirmRequest{audioUrl, recordingId, durationSeconds, fileSize, fileDigest, recordingVersion, clientSequence, baseVersion}`；调 `speakingAnswerService.confirmAudio(userId, recordId, questionId, request)` 返回 `SpeakingAnswerResponse`。
- **Service**（核心）：
  1. `SELECT FOR UPDATE` 锁 `PracticeRecord` + `PracticeAnswer`，校验 `status=1`、`baseVersion` 一致。
  2. 幂等：若 `PracticeAnswer.answer == audioUrl AND recordingVersion` 一致，直接返回。
  3. 校验：`durationSeconds >= minValidDurationSeconds`、`fileDigest` 与上传时一致、MIME 合法。
  4. **重录替换语义**：旧 `answer` 标记为 `replaced`（写入 `optionSnapshot` 的 `replacedAudios` 数组供审计），新 `answer = audioUrl`，`recordingVersion+1`，`answered=1`，`firstAnsweredTime`（首次） / `lastModifiedTime`。
  5. `record.version+1`，`answeredCount` 重算。
- **Mapper**：`PracticeAnswerMapper.selectForUpdate(recordId, questionId)` + `updateById` + `PracticeRecordMapper.updateById`。

#### 3.3 PUT `/{recordId}/answers/{questionId}` — 单题作答草稿保存
- **Controller**：`@RequestBody SpeakingAnswerSaveRequest{audioUrl, durationSeconds, clientSequence, baseVersion, recordingVersion}`（500-1000ms 防抖触发）；调 `service.saveOne(...)` 返回 `SpeakingAnswerResponse`。
- **Service**：与 3.2 类似但允许 `audioUrl=null`（仅更新当前题号/草稿），不做 final 校验；强制保存点（切题/退出/锁屏）调用 3.4 批量接口。
- **Mapper**：`PracticeAnswerMapper.updateById` + `PracticeRecordMapper.updateById`。

#### 3.4 PUT `/{recordId}/answers` — 批量保存
- **Controller**：`@RequestBody @Valid SpeakingAnswerBatchSaveRequest{List<@Valid SpeakingAnswerSaveRequest> answers, currentQuestionId, currentQuestionNumber, durationSeconds, clientSequence, baseVersion}`；调 `service.saveBatch(...)` 返回 `SpeakingRecordResponse`。
- **Service**：事务内批量 upsert `PracticeAnswer` + 更新 `PracticeRecord`（参考阅读模块批量保存逻辑）；乐观锁校验同 2.4。
- **Mapper**：`PracticeAnswerMapper.batchUpsert`（XML）+ `PracticeRecordMapper.updateById`。

#### 3.5 GET `/{recordId}/answer-card` — 答题卡
- **Controller**：调 `service.getAnswerCard(userId, recordId)` 返回 `SpeakingAnswerCardResponse{totalQuestions, answeredCount, List<{questionId, questionNumber, answered, isCurrent}>}`。
- **Service**：聚合 `PracticeAnswer.answered` 字段 + 当前题号；与答题主页实时同步。
- **Mapper**：`PracticeAnswerMapper.selectByRecord(recordId)`。

---

### 4. SpeakingReportController（提交与报告）`@RequestMapping("/practice/speaking")`

#### 4.1 POST `/records/{recordId}/submit` — 提交事务
> 必须幂等：同一 `recordId + idempotencyKey` 重复提交始终返回同一 `reportId`。
- **Controller**：`@RequestBody @Valid SpeakingSubmitRequest{durationSeconds, idempotencyKey, List<SpeakingAnswerSaveRequest> finalAnswers, baseVersion, clientSequence}`；调 `speakingReportService.submit(userId, recordId, request)` 返回 `SpeakingReportResponse`（即使报告还在生成中也返回框架）。
- **Service**（`SpeakingSubmissionFinalizer` 内部组件，原子事务）：
  1. `SELECT FOR UPDATE` 锁 `PracticeRecord` + 全部 `PracticeAnswer`。
  2. **幂等检查**：`record.idempotencyKey == request.idempotencyKey` → 直接返回已生成报告。
  3. 校验：`status=1`、`baseVersion` 一致、归属。
  4. 核验所有"已作答"题：录音上传确认完成、`fileDigest` 匹配、未被标记 `replaced`。
  5. **固化快照**：`PracticeAnswer.questionSnapshot/groupSnapshot/optionSnapshot/standardAnswerSnapshot/analysisSnapshot` 写入提交时点的题目/素材/评分规则版本。
  6. 锁定未作答题清单（`answered=0` 的 questionId 列表）写入 `PracticeReport.unansweredQuestionIds`。
  7. `PracticeRecord.status=3, submittedTime=now, durationSeconds, idempotencyKey`，`version+1`。
  8. 生成 `PracticeReport` 框架（`reportStatus=1 GENERATING, status=PENDING`）。
  9. **异步触发评分**：调 `speakingScoringService.evaluateAsync(recordId, reportId)`，事务提交后才发 MQ/线程池。
- **Mapper**：`PracticeRecordMapper.updateById` + `PracticeAnswerMapper.batchUpdateSnapshot`（XML）+ `PracticeReportMapper.insert`。

#### 4.2 GET `/records/{recordId}/report` — 学习报告
- **Controller**：调 `service.getReport(userId, recordId)` 返回 `SpeakingReportResponse`。
- **Service**：校验归属；加载 `PracticeReport` + `PracticeAnswer`；组装：
  - `reportId, reportStatus`(PENDING/GENERATING/READY/FAILED), `totalQuestions, answeredCount, durationSeconds, submittedTime`
  - `averageScore`（综合得分/题目总数量；未作答 0 分仍计入分母）
  - `completionRate`（已答/总题数）
  - `List<SpeakingReportItemResponse>{questionId, questionNumber, answered, score, questionType, audioUrl, analysisText, status}`
- **Mapper**：`PracticeReportMapper.selectByRecord(recordId)` + `PracticeAnswerMapper.selectByRecord(recordId)`。

#### 4.3 POST `/records/{recordId}/report/retry` — 重试评分
- **Controller**：调 `service.retryReport(userId, recordId)`。
- **Service**：校验 `reportStatus=3 FAILED`；`UPDATE PracticeReport SET reportStatus=1`；重新入队评分任务；**不回滚 Attempt**，已固化的快照不变。
- **Mapper**：`PracticeReportMapper.updateReportStatus(recordId, 1)`。

#### 4.4 GET `/parts/{structureId}/reports/latest` — 板块最近报告
- **Controller**：调 `service.getLatestReport(userId, structureId)` 返回 `SpeakingReportResponse` 或空。
- **Service**：查 `PracticeRecord` 中 `(userId, structureId, status=3, reportStatus=2)` 的最新一条；题型页默认展示此报告。
- **Mapper**：`PracticeRecordMapper.selectLatestSubmitted(userId, structureId)` + `PracticeReportMapper.selectByRecord`。

#### 4.5 GET `/records/{recordId}/report/questions/{questionId}` — 单题解析
- **Controller**：调 `service.getQuestionReport(userId, recordId, questionId)` 返回 `SpeakingQuestionReportResponse`。
- **Service**：校验归属 + 报告已就绪；组装单题：
  - 题目主体快照（题干音频 URL、拼音文本、图片 URL、朗读文章）— 来自 `PracticeAnswer.questionSnapshot` 等快照字段（**严格按提交时点版本，禁止拉取 CMS 实时数据**）。
  - `myRecordingUrl`（用户录音回放，鉴权短期 URL）+ `durationSeconds`。
  - `score`(单题总分) + `analysisText`(AI 评语；未录入则展示"未录入解析内容")。
  - **不返回细分维度得分**（仅服务端快照留存）。
- **Mapper**：`PracticeAnswerMapper.selectByRecordQuestion(recordId, questionId)` + `PracticeReportMapper.selectByRecord`。

---

## 四、AI 评分服务（SpeakingScoringService）

> 完全服务端隔离，客户端无评分逻辑、无提示词、无模型密钥；答题接口全程不返回分数/解析。

- **接口**：`SpeakingScoringService.evaluateAsync(Long recordId, Long reportId)`
- **入参**：考试等级、题型、题目快照、作答录音 URL + 时长 + 摘要、评分规则版本；看图说话额外附带图片快照。
- **流程**：
  1. 核验提交快照、录音资源、评分规则版本无误。
  2. 检测音频：可解码性、时长、静音占比、削波、基础音质。
  3. 按题型执行：语音转写（ASR）→ 文本比对/图文解析/语义理解 → 按评分规则版本计算单题分数 → 生成评语。
  4. 汇总板块总分、平均分、得分率；固化报告快照（`PracticeReport.reportStatus=2 READY`）。
  5. 未作答 0 分不送 AI；音频无有效人声判 0 分并标注；文件损坏不生成虚假 0 分，保持 `FAILED` 可重试。
- **实现方式**：复用 `exam-service` 现有 `AiServiceClient`/`AiChatClient`（Feign），或新增 `SpeakingAiClient`；评分任务通过线程池/MQ 异步执行，幂等键 = `(recordId, reportId, scoringRuleVersion, modelVersion)`。
- **对应 Mapper**：`PracticeReportMapper.updateReportStatus + updateScore`、`PracticeAnswerMapper.updateScoreAndAnalysis`（XML 批量）。

---

## 五、关键约束清单

1. **录音文件路径**：`audio/{userId}/hsk-{paperId}/rec/{recordId}/{questionId}-{recordingVersion}-{uuid}.ext`，与现有 `manage` 上传路径风格一致，增加 `rec/{recordId}` 隔离。
2. **录音 URL 鉴权**：所有返回给客户端的录音 URL 必须是 MinIO 短期授权 URL（建议 1-2 小时），不暴露永久裸链。
3. **幂等约束**：提交接口 `recordId + idempotencyKey` 决定同一 `reportId`；录音确认接口 `recordingVersion` 决定幂等。
4. **乐观锁**：所有写 `PracticeRecord` 的接口校验 `baseVersion`，冲突时返回 `ErrorCode.RECORD_VERSION_CONFLICT`，不自动合并音频，由用户选择版本。
5. **快照闭包**：提交时固化的题目/素材/评分规则版本在报告中不可变；历史报告不随 CMS 更新而变化。
6. **数据最小化**：客户端日志仅含匿名 ID + 状态 + 时长 + 摘要后缀；不返回 ASR 转写、提示词、细分维度得分。
7. **隐私与账号隔离**：登出/切换账号后停止上传、清理授权；上传队列与本地文件按账号隔离。
8. **音频 MIME 校验**：复用 `AudioMimeUtil` 模糊匹配 + 扩展名降级策略，覆盖 .wav 变体。
9. **题库边界**：`practice-service` 仅连 `hsk_practice` 库，不直连 exam 库；口语题目通过 `db/practice_seed.sql` 镜像 `speaking_exam_paper` → `practice_paper/structure/question`（当前 seed 缺口语数据，需补充）。
10. **草稿保留期**：默认 90 天，与其他真题练习模块一致并可配置。

---

## 六、待补充/新增的开发工件

| 工件 | 说明 |
|---|---|
| `ExamSection.SEC_SPEAK` | 枚举新增口语板块标识 |
| `db/practice_seed_speaking.sql` | 口语题库镜像脚本（HSKK 初/中/高级试卷、板块、题目、录音参数） |
| `practice-speaking-openapi.yaml` | OpenAPI 3.0 文档，供 Apifox 导入 |
| `speaking-practice-api.md` | 中文联调文档（对齐 `reading-practice-api.md` 风格） |
| `SpeakingQuestionType` 复用 | 现有枚举 9 值已够用，作为 `PracticeQuestion.typeIdMapping` |
| `PracticePartSetting` 配置 | 口语三题型板块的 `answerMode=SINGLE`、`recordingParams` JSON |
| AI 评分模型对接 | 需与 AI 服务方确定 `audioFormatProfile`（建议 AAC/M4A 单声道）与评分规则版本下发协议 |
