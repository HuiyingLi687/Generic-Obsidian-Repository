# HSK 练习接口 · 新增字段说明（前端对接稿）

> 服务：`practice-service`（网关前缀 `/api/practice`）>   
> 关联需求：HSK3.0 大纲接入（听力 / 阅读 / 写作 / 口语 四个练习模块支持 `version` 切换）>   
> 代码基线：`83512a49`（听力新增 3.0 版本）→ `10bf2146`（听力目录改造 + 投影器）>   
> 文档版本：v1.0 · 2026-10-19>   
> 影响范围：**4 个模块 / 13 个 GET 接口**（11 个新增入参 `version` + 2 个新增返回字段），新增 **1 个公共入参** + **3 个返回字段**

---

## 0. 三句话结论

1. **所有目录类 GET 接口新增可选入参 `version`**（`HSK2.0` / `HSK3.0`，不传 = `HSK2.0`）。**不传就完全走老逻辑**，存量页面不改也不会崩。
2. **响应体新增 `version` 回显**，另有 3 个字段：听力 `/parts` 的 `section_name_en`、`section_name_vi`，写作 `/parts` 的 `sectionMapping`。
3. ⚠️ **两个坑必须看**：① 新字段里有 2 个是 **snake_case**（其余全是驼峰），别按驼峰取值；② **ID 的序列化类型变了**（Long → String 配置被移除，当前以 number 下发，雪花 ID 有精度风险），详见 §6.1。

---

## 1. 通用约定

### 1.1 地址与返回体

| 项    | 说明                                                                       |
| ---- | ------------------------------------------------------------------------ |
| 网关地址 | `http://{gateway-host}:8080/api/practice/...`（`StripPrefix=2` 后转发到服务根路径） |
| 本地直连 | `http://localhost:8087/...`（调试时网关前缀要去掉）                                  |
| 返回体  | `{ "code": 200, "message": "success", "data": ... }`                     |
| 成功判断 | `code === 200`                                                           |
| 业务异常 | `code` = 404 / 409 等，`message` 为文案或错误码常量                                 |

### 1.2 请求头

| Header            | 必需                                                                                                  | 说明                                                                                                          |
| ----------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `Authorization`   | `/levels`、`/levels/{levelCode}/intro` **可不传**；`/preferences`、`/papers`、`/papers/{id}/parts` **必须传** | `Bearer {token}`                                                                                            |
| `X-Client-Type`   | 建议统一传 `APP`                                                                                         | 听力 `/levels` 只有 `X-Client-Type: APP` 时才带用户进度（否则 `status` 恒 `not_started`）                                   |
| `Accept-Language` | 否                                                                                                   | `zh`（默认）/ `en` / `vi`，决定 `levelName`、`abilityDesc`、`questionTypeName` 等文案语言（**听力板块名 `partName` 不做本地化，恒中文**） |

### 1.3 `version` 入参（本次新增）

| 项        | 说明                                                  |
| -------- | --------------------------------------------------- |
| 取值       | `HSK2.0`、`HSK3.0`                                   |
| 大小写      | 🔴 **大小写敏感**，传 `hsk3.0` 会查不到数据。服务端只做 `trim()`，不做归一化 |
| 不传 / 传空串 | 回落到 **`HSK2.0`**                                    |
| 位置       | 全部为 query 参数，`?version=HSK3.0`                      |

### 1.4 等级编码 `levelCode`

| version  | 可用等级编码                         | 备注                                                  |
| -------- | ------------------------------ | --------------------------------------------------- |
| `HSK2.0` | `HSK1` … `HSK6`                | 编码范围 1–6；**实际开放等级**（如写作只有 3–6）见 §3.1。口语走 HSKK 体系，见下 |
| `HSK3.0` | `HSK1` … `HSK6` + **`HSK7-9`** | 七至九级是**一个等级**，编码固定 `HSK7-9`                         |

> 🔴 **口语两个版本的等级编码完全不同**：
>
> - `version=HSK2.0` → `HSKK_PRIMARY` / `HSKK_INTERMEDIATE` / `HSKK_ADVANCED`（初/中/高级）
> - `version=HSK3.0` → `HSK3` / `HSK4` / `HSK5` / `HSK6` / `HSK7-9`
>
> 切换版本时必须同时切换等级选项的数据源，不能沿用旧的 `levelCode`。

---

## 2. 变更总表（13 个接口）

| #  | 模块 | 方法与路径                                     | 接口说明                | 新增入参      | 新增返回字段                                                         |
| -- | -- | ----------------------------------------- | ------------------- | --------- | -------------------------------------------------------------- |
| 1  | 听力 | `GET /listening/levels`                   | 等级概览（**返回单对象**，非数组） | `version` | `version`                                                      |
| 2  | 听力 | `GET /listening/levels/{levelCode}/intro` | 备考说明 + 题型结构         | `version` | `version`                                                      |
| 3  | 听力 | `GET /listening/papers/{paperId}/parts`   | 试卷板块列表              | —         | 🆕 `parts[].section_name_en`<br />🆕 `parts[].section_name_vi` |
| 4  | 阅读 | `GET /reading/levels`                     | 等级列表                | `version` | `version`                                                      |
| 5  | 阅读 | `GET /reading/levels/{levelCode}/intro`   | 单等级说明               | `version` | `version`                                                      |
| 6  | 阅读 | `GET /reading/papers`                     | 试卷列表                | `version` | `version`                                                      |
| 7  | 写作 | `GET /writing/levels`                     | 等级列表                | `version` | `version`                                                      |
| 8  | 写作 | `GET /writing/levels/{levelCode}/intro`   | 单等级说明               | `version` | `version`                                                      |
| 9  | 写作 | `GET /writing/papers`                     | 试卷列表                | `version` | `version`                                                      |
| 10 | 写作 | `GET /writing/papers/{paperId}/parts`     | 板块列表                | —         | 🆕 `sectionMapping`                                            |
| 11 | 口语 | `GET /speaking/levels`                    | 等级列表                | `version` | `version`                                                      |
| 12 | 口语 | `GET /speaking/levels/{levelCode}/intro`  | 单等级说明               | `version` | `version`                                                      |
| 13 | 口语 | `GET /speaking/papers`                    | 试卷列表                | `version` | `version`                                                      |

**未受影响的接口**（字段无变化）：`/reading|writing|speaking/preferences`（GET/PUT）、`/reading/papers/{id}/parts`、`/speaking/papers/{id}/parts`。  
⚠️ 其中偏好接口**不支持 `version`**，在 HSK3.0 场景下有已知限制，见 §6.5。

---

## 3. `version` 参数的行为差异（重要）

### 3.1 支持矩阵（测试库实际数据）

| 模块 | HSK2.0 可用等级                | HSK3.0 可用等级          |
| -- | -------------------------- | -------------------- |
| 听力 | 1–6                        | 1–6 + 7-9            |
| 阅读 | 1–6                        | 1–6 + 7-9            |
| 写作 | **3–6**（1/2 级 `enabled=0`） | **2–7**（1 级未开放）      |
| 口语 | HSKK 初/中/高                 | **3–7**（3/4/5/6/7-9） |

### 3.2 传了不支持的值会怎样

| 接口                                           | 表现                                                              |
| -------------------------------------------- | --------------------------------------------------------------- |
| 听力 `/levels`                                 | **不报错**，返回 `paperCount: 0`、`papers: []`                         |
| 听力 `/intro`                                  | **不报错**，`data: null`                                            |
| 阅读 `/levels`                                 | **不报错**，返回 `[]`                                                 |
| 阅读 `/intro`、`/papers`                        | ❗ `404` / `"阅读等级不存在"`                                           |
| 写作 `/levels`                                 | 返回 `[]`                                                         |
| 写作 `/intro`、`/papers`                        | ❗ `404` / `"写作等级不存在"`                                           |
| 写作（**等级存在但未开放**：HSK2.0 的 1/2 级、HSK3.0 的 1 级） | `/intro` 正常返回但 `writingAvailable=false`；`/papers` 返回 `[]`       |
| 口语 `/levels`                                 | 返回 `[]`                                                         |
| 口语 `/intro`、`/papers`                        | ❗ `404` / `"SPEAKING_RESOURCE_NOT_FOUND"`（注意这是**错误码常量**，不是中文文案） |

> 前端建议：切版本时先拉 `/levels` 拿可用等级，再让用户选，避免用旧 `levelCode` 直接打 `/papers` 吃 404。

---

## 4. 逐接口字段说明与示例

> 下表只列**结构**，`…` 代表长文本省略。标 🆕 的是本次新增字段。

### 4.1 听力

#### ① `GET /listening/levels?levelCode=HSK3&version=HSK3.0`

| 参数          | 位置    | 必填 | 说明               |
| ----------- | ----- | -- | ---------------- |
| `levelCode` | query | 否  | 不传默认 `HSK1`      |
| `version`   | query | 否  | 🆕 不传默认 `HSK2.0` |

响应 `ListeningLevelOverviewResponse`：

| 字段                        | 类型     | 说明                                                              |
| ------------------------- | ------ | --------------------------------------------------------------- |
| `version`                 | string | 🆕 实际生效的版本（未传时回显 `HSK2.0`）                                      |
| `levelCode`               | string | 回显入参，未传=`HSK1`                                                  |
| `paperCount`              | int    | 该等级试卷数                                                          |
| `papers[].paperId`        | long   | 试卷 ID                                                           |
| `papers[].paperCode`      | string | 试卷编码，如 `HSK3_1`                                                 |
| `papers[].status`         | string | `not_started` / `in_progress` / `completed`（未登录恒 `not_started`） |
| `papers[].completedCount` | int    | 已交卷题数                                                           |
| `papers[].totalCount`     | int    | 总题数                                                             |

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "version": "HSK3.0",
    "levelCode": "HSK3",
    "paperCount": 3,
    "papers": [
      { "paperId": 2104191651581345793, "paperCode": "HSK3_1", "status": "not_started", "completedCount": 0, "totalCount": 30 },
      { "paperId": 2104196034297675777, "paperCode": "HSK3_2", "status": "in_progress",   "completedCount": 10, "totalCount": 30 },
      { "paperId": 2104196669533405186, "paperCode": "HSK3_3", "status": "not_started", "completedCount": 0, "totalCount": 30 }
    ]
  }
}
```

#### ② `GET /listening/levels/{levelCode}/intro?version=HSK3.0`

| 字段                                                                     | 类型     | 说明        |
| ---------------------------------------------------------------------- | ------ | --------- |
| `version`                                                              | string | 🆕 实际生效版本 |
| `abilityDescription` / `abilityDescriptionEn` / `abilityDescriptionVi` | string | 能力说明三语    |
| `totalQuestionCount`                                                   | int    | 总题数       |
| `durationMinutes`                                                      | int    | 建议时长（分钟）  |
| `parts[].partName` / `partNameEn` / `partNameVi`                       | string | 板块名三语     |
| `parts[].typeName` / `typeNameEn` / `typeNameVi`                       | string | 题型名三语     |
| `parts[].questionCount`                                                | int    | 该板块题量     |
| `parts[].sortOrder`                                                    | int    | 排序        |

```json
{
  "code": 200, "message": "success",
  "data": {
    "version": "HSK3.0",
    "abilityDescription": "…", "abilityDescriptionEn": "…", "abilityDescriptionVi": "…",
    "totalQuestionCount": 30,
    "durationMinutes": 35,
    "parts": [
      { "partName": "第一部分", "partNameEn": "Part 1", "partNameVi": "Phần 1",
        "typeName": "图片匹配题", "typeNameEn": "Picture Matching", "typeNameVi": "Ghép hình ảnh",
        "questionCount": 10, "sortOrder": 1 },
      { "partName": "第二部分", "partNameEn": "Part 2", "partNameVi": "Phần 2",
        "typeName": "对话选择题", "typeNameEn": "Dialogue Choice", "typeNameVi": "Lựa chọn hội thoại",
        "questionCount": 10, "sortOrder": 2 },
      { "partName": "第三部分", "partNameEn": "Part 3", "partNameVi": "Phần 3",
        "typeName": "细节选择题", "typeNameEn": "Detail Choice", "typeNameVi": "Lựa chọn chi tiết",
        "questionCount": 10, "sortOrder": 3 }
    ]
  }
}
```

> 该接口**不报错**：`levelCode` 无法识别或该版本无对应配置时返回 `data: null`，前端按空态处理。

#### ③ `GET /listening/papers/{paperId}/parts`

**无新增入参**，`parts[]` 内新增 2 个字段：

| 字段                                          | 类型     | 说明                                              |
| ------------------------------------------- | ------ | ----------------------------------------------- |
| `structureId`                               | long   | 板块结构 ID                                         |
| `partName`                                  | string | 板块名，**听力模块恒为中文**（不做本地化），如 `第1部分`                |
| `section_name_en`                           | string | 🆕 板块英文名，如 `Part 1`（⚠️ **snake_case**）          |
| `section_name_vi`                           | string | 🆕 板块越南语名，如 `Phần 1`（⚠️ **snake_case**）         |
| `typeName`                                  | string | 题型名                                             |
| `questionCount`                             | int    | 板块题数                                            |
| `status`                                    | string | `not_started` / `in_progress` / `completed`     |
| `doneCount` / `correctCount` / `wrongCount` | int    | 进度与正确/错误数（`correctCount`/`wrongCount` 仅已提交板块有值） |
| `sortOrder`                                 | int    | 排序                                              |

```json
{
  "code": 200, "message": "success",
  "data": {
    "paperId": 2104191651581345793,
    "paperCode": "HSK3_1",
    "parts": [
      {
        "structureId": 7000124841053809199,
        "partName": "第1部分",
        "section_name_en": "Part 1",
        "section_name_vi": "Phần 1",
        "typeName": "图片匹配题",
        "questionCount": 10,
        "status": "in_progress",
        "doneCount": 6, "correctCount": null, "wrongCount": null,
        "sortOrder": 1
      }
    ]
  }
}
```

> ✅ **不会为 null**：库中 `section_name_en` / `section_name_vi` 在 **HSK2.0 存量卷约一半为空**（HSK3.0 全有值），后端已做兜底 —— 空值时返回 `"Part " + sortOrder` / `"Phần " + sortOrder`（`sortOrder` 即该模块内的部分序号，如 1/2/3），前端**直接展示即可**。若需要严格的外语名称，以后端补全数据为准。

---

### 4.2 阅读

#### ④ `GET /reading/levels?version=HSK3.0`

#### ⑤ `GET /reading/levels/{levelCode}/intro?version=HSK3.0`

响应 `ReadingLevelResponse`（`/levels` 返回**数组**，`/intro` 返回**单对象**）：

| 字段                       | 类型     | 说明                                                                                                                    |
| ------------------------ | ------ | --------------------------------------------------------------------------------------------------------------------- |
| `levelId`                | long   | 等级配置 ID                                                                                                               |
| `version`                | string | 🆕 版本                                                                                                                 |
| `level`                  | int    | 数值等级（7-9 → `7`）                                                                                                       |
| `levelCode`              | string | `HSK1`…`HSK6`、`HSK7-9`                                                                                                |
| `levelName`              | string | 本地化等级名                                                                                                                |
| `abilityDesc`            | string | 能力说明                                                                                                                  |
| `totalQuestionCount`     | int    | 总题数                                                                                                                   |
| `suggestDurationMinutes` | int    | 建议时长                                                                                                                  |
| `sections[]`             | array  | `/levels` 返回**空数组**；`/intro` 才有内容：`partCode`/`partName`/`questionCount`/`questionType`/`questionTypeName`/`sortOrder` |

```json
{
  "code": 200, "message": "success",
  "data": [
    {
      "levelId": 2205, "version": "HSK3.0", "level": 3, "levelCode": "HSK3",
      "levelName": "HSK（三级）", "abilityDesc": "…",
      "totalQuestionCount": 30, "suggestDurationMinutes": 30,
      "sections": []
    }
  ]
}
```

#### ⑥ `GET /reading/papers?levelCode=HSK3&version=HSK3.0`

| 参数          | 位置    | 必填    | 说明               |
| ----------- | ----- | ----- | ---------------- |
| `levelCode` | query | **是** | —                |
| `version`   | query | 否     | 🆕 不传默认 `HSK2.0` |

| 字段                        | 类型     | 说明                                                                 |
| ------------------------- | ------ | ------------------------------------------------------------------ |
| `paperId`                 | long   | 试卷 ID                                                              |
| `version`                 | string | 🆕 版本                                                              |
| `level`                   | int    | 数值等级                                                               |
| `paperCode` / `paperName` | string | 试卷编码/名称                                                            |
| `totalQuestionCount`      | int    | 阅读题总数                                                              |
| `completedQuestionCount`  | int    | 已完成题数                                                              |
| `status`                  | string | `NOT_STARTED` / `IN_PROGRESS` / `COMPLETED`（⚠️ **阅读是大写下划线**，听力是小写） |

```json
{
  "code": 200, "message": "success",
  "data": [
    {
      "paperId": 2104191651581345793, "version": "HSK3.0", "level": 3,
      "paperCode": "HSK3_1", "paperName": "HSK3_1",
      "totalQuestionCount": 30, "completedQuestionCount": 0,
      "status": "NOT_STARTED"
    }
  ]
}
```


### 4.4 口语

#### ⑪ `GET /speaking/levels?version=HSK3.0`

#### ⑫ `GET /speaking/levels/{levelCode}/intro?version=HSK3.0`

#### ⑬ `GET /speaking/papers?levelCode=HSK3&version=HSK3.0`

`SpeakingLevelResponse`（record，直接用字段名，无驼峰转换）：

| 字段                                                | 类型      | 说明                                                                               |
| ------------------------------------------------- | ------- | -------------------------------------------------------------------------------- |
| `levelId`                                         | long    | —                                                                                |
| `version`                                         | string  | 🆕 版本                                                                            |
| `databaseLevel`                                   | int     | 数据库等级值（HSK2.0 为 1/2/3；HSK3.0 为 3…7）                                              |
| `levelCode`                                       | string  | HSK2.0：`HSKK_PRIMARY`/`HSKK_INTERMEDIATE`/`HSKK_ADVANCED`；HSK3.0：`HSK3`…`HSK7-9` |
| `levelName`                                       | string  | `HSKK 初级`… / `HSK（三级）`…                                                          |
| `abilityDescription`                              | string  | —                                                                                |
| `enabled`                                         | boolean | —                                                                                |
| `totalQuestionCount` / `suggestedDurationMinutes` | int     | —                                                                                |
| `sections[]`                                      | array   | `partCode`/`partName`/`questionType`/`questionTypeName`/`questionCount`          |

`SpeakingPaperResponse`：

| 字段                                                                        | 类型     | 说明    |
| ------------------------------------------------------------------------- | ------ | ----- |
| `paperId`                                                                 | long   | —     |
| `version`                                                                 | string | 🆕 版本 |
| `levelCode` / `paperCode` / `paperName`                                   | string | —     |
| `totalQuestionCount` / `recordedCount` / `scoredCount` / `completedCount` | int    | —     |
| `status`                                                                  | string | —     |

```json
{
  "code": 200, "message": "success",
  "data": [
    { "levelId": 2560, "version": "HSK3.0", "databaseLevel": 3, "levelCode": "HSK3",
      "levelName": "HSK（三级）", "abilityDescription": "…", "enabled": true,
      "totalQuestionCount": 15, "suggestedDurationMinutes": 15, "sections": [] }
  ]
}
```

---

## 5. 新增字段速查

| 字段                        | 出现位置                                    | 类型     | 取值 / 语义                                               |
| ------------------------- | --------------------------------------- | ------ | ----------------------------------------------------- |
| `version`                 | 11 个响应体（列表/单对象顶层）                       | string | `HSK2.0` / `HSK3.0`，为**实际生效**版本（未传时回显 `HSK2.0`）       |
| `parts[].section_name_en` | `GET /listening/papers/{paperId}/parts` | string | `Part 1`、`Part 2`…；**snake_case**；后端已兜底，非 null        |
| `parts[].section_name_vi` | 同上                                      | string | `Phần 1`、`Phần 2`…；**snake_case**；后端已兜底，非 null        |
| `sectionMapping`          | `GET /writing/papers/{paperId}/parts`   | string | `SEC_WRITE` / `SEC_TRANSLATION`；其他模块也有同名概念但**未下发该字段** |

---

## 6. 前端必须注意的 5 个点

### 6.1 🔴 ID 的序列化类型（**待后端确认，目前是 number**）

`practice-service` 原本注册了模块级 `JacksonConfig`（Long → String，防 JS 精度丢失），**该配置在 `10bf2146` 中被删除**，`common` 里的同名配置也是注释状态。按当前代码：

- `paperId` / `structureId` / `levelId` / `draftAttemptId` / `latestReportId` 等**以数字下发**。
- 这些 ID 是**雪花 ID（19 位，如 `2104188199979532289`）**，超过 JS `Number.MAX_SAFE_INTEGER`（2^53）→ `JSON.parse` 后**末位会被改写**（如 …289 变 …288），再回传给后端就查不到数据。

**结论：这条已反馈给后端，倾向于恢复 Long → String（改回去后 ID 全部是字符串，与改造前的老接口表现一致）。**

- **联调前先向后端确认**：`paperId` 返回的是 `2104188199979532289`（number，有精度风险）还是 `"2104188199979532289"`（string）。
- 若仍是 number，前端必须用 `json-bigint` 或在 `axios` 的 `transformResponse` 里先做 ID 转字符串，**不要直接 `JSON.parse` 后拿去当主键**。
- TS 类型建议写 `paperId: string`（后端恢复后即为 string），或先写 `string | number` 过渡。

> 若测试中发现「同一个 paperId 刷新后查不到 / 返回 404」，**优先怀疑这条**。

### 6.2 snake_case 混在驼峰里

`ListeningPartsResponse.Part` 里只有 `section_name_en` / `section_name_vi` 是下划线（因为加了 `@JsonProperty`），同级的 `partName` / `typeName` / `questionCount` 全是驼峰。TS 接口定义时别手滑写成 `sectionNameEn`。

### 6.3 `version` 大小写敏感 + 切版本要重置等级

- 必须传 `HSK3.0`，不能 `hsk3.0`。
- 切到 `HSK3.0` 时，旧的 `HSK3` 可用但对**口语**无效（口语 HSK3.0 从 `HSK3` 起，HSK2.0 是 `HSKK_*`）；建议**版本切换后重新拉 `/levels`，把 `levelCode` 置空让用户重选**。

### 6.4 `status` 枚举大小写在模块间不一致

- 听力 `/levels`：`not_started` / `in_progress` / `completed`（小写）
- 阅读 `/papers`、写作 `/papers`：`NOT_STARTED` / `IN_PROGRESS` / `COMPLETED`（大写）
- 口语：沿用原逻辑

沿用现状即可，跨模块复用状态组件时记得归一化。

### 6.5 偏好接口不认 `version`（已知限制，需产品决策）

`GET /{module}/preferences`、`PUT /{module}/preferences/level` **没有 `version` 参数**，且底层表 `practice_user_preference` **没有 version 列**，因此：

| 现象                  | 说明                                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------ |
| 偏好跨版本共享             | 在 HSK3.0 选了 5 级，切回 HSK2.0 后 `/preferences` 仍返回 `lastLevel=5`；等级数字相同就"看起来正常"，但语义不是同一份大纲                 |
| `PUT` 一律按 HSK2.0 校验 | `updatePreference` 内部用的是默认版本，传 HSK3.0 独有的 `HSK7-9` 会直接 **404**；传 HSK3.0 的 2 级（HSK2.0 下写作未开放）可能 404/409 |

**前端临时规避**：切到 `HSK3.0` 时**不要调用 `/preferences/level` 保存等级**（或只在 `HSK2.0` 下调用），进页面时也不要用 `/preferences` 的返回值直接回填等级下拉框 —— 以本地状态 / URL 参数为准。  
**根治方案**：偏好表加 `version` 列 + 接口加 `version` 入参，需后端另开一轮改造。

---

## 7. 前端改造 Checklist

- [ ] 四个模块的 `/levels`、`/papers` 请求统一带上 `version`（建议放全局 store，默认 `HSK2.0`）
- [ ] 页面加「大纲版本」切换（HSK2.0 / HSK3.0），切换后清空 `levelCode` 与试卷选中态
- [ ] `version=HSK3.0` 时等级列表要包含 **`HSK7-9`**（显示名可用「HSK 七至九级」）
- [ ] 阅读 / 写作 `levelCode` 参数保留；听力 `/levels` 的 `levelCode` 仍是可选
- [ ] TS 类型补 4 个新字段：`version`（11 处）、`section_name_en`、`section_name_vi`、`sectionMapping`
- [ ] ID 类型先与后端确认（见 6.1），暂按 `string` 定义并做兼容
- [ ] 写作板块展示：`sectionMapping === 'SEC_TRANSLATION'` 时可加「翻译」角标，与写作板块视觉区分
- [ ] 听力板块英文/越文名直接用 `section_name_en` / `section_name_vi`（后端已兜底）；中文展示仍用 `partName`（听力不做本地化）
- [ ] 错误码兼容：阅读/写作/口语 `/intro` 传错版本会 404，需给出「该等级暂未开放」提示而非白屏
- [ ] 偏好接口不加 `version`、HSK3.0 下不依赖它保存等级（见 6.5）

---

## 8. 联调信息

| 项    | 值                                                           |
| ---- | ----------------------------------------------------------- |
| 测试环境 | 网关 `http://{gateway-host}:8080`，直连 `practice-service:8087`  |
| 测试数据 | HSK3.0：1–4 级各 3 套卷、5/6 级各 1 套、7-9 级 1 套；HSK2.0：1–6 级各约 20 套 |
| 版本常量 | 只有 `HSK2.0`、`HSK3.0` 两个合法值                                  |

```bash
# 听力（免登录）
curl "http://localhost:8087/listening/levels?levelCode=HSK3&version=HSK3.0" \
  -H "X-Client-Type: APP"

# 写作试卷（需登录）
curl "http://localhost:8087/writing/papers?levelCode=HSK7-9&version=HSK3.0" \
  -H "Authorization: Bearer {token}" -H "X-Client-Type: APP"

# 写作板块（看 sectionMapping / partCode）
curl "http://localhost:8087/writing/papers/{paperId}/parts" \
  -H "Authorization: Bearer {token}" -H "X-Client-Type: APP"
```

---

## 附：变更来源（后端 commit）

| commit                               | 内容                                                                         |
| ------------------------------------ | -------------------------------------------------------------------------- |
| `83512a49`                           | 听力目录新增 3.0 版本                                                              |
| `d805b0d7` / `625d3d81`              | 阅读目录新增 3.0 版本 / 兼容 7-9                                                     |
| `0d92cb42` / `216cce9b`              | 写作目录新增 3.0 版本 / 7-9 翻译题                                                    |
| `e97e6a61` / `02ea5bfd` / `09ef541b` | 口/读/写 `/levels` 新增 `version` 字段                                            |
| `10bf2146`                           | 听力目录改造 + 投影器；删除 `JacksonConfig`（ID 序列化变更）；`/parts` 新增 `section_name_en/vi` |

> 涉及 DTO 共 10 个、新增 33 行，全部为**追加字段**，无字段改名/删除（除 `partCode` 取值语义见 §4.3）。
