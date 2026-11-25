# HSK 考试与练习 · 错题本与收藏夹 接口设计文档

> 版本：v1.0｜更新日期：2026-11-24
> 文档模板：接口设计文档模板一（全新模块）
> 影响服务：practice-service（列表读取 + 练习侧写入）、exam-service（考试侧收藏 + 判分后写入）
> 关联文档：《HSK考试、练习错题本和收藏夹业务》《HSK练习合并后接口设计文档》（v2.5）
> 开发：—｜测试：—｜前端：—

## 目录

- 0.全局通用约定
- 1.业务背景与目标
- 2.业务决策/核心公式
- 3.数据模型设计
- 4.接口总览清单
- 5.接口详细定义
- 6.错误码定义
- 7.边界特殊场景说明
- 8.验收测试用例
- 9.上线注意事项
- 10.待确认事项

## 0.全局通用约定

1. 返回统一包装：全部返回 `Result<T>`，HTTP 状态码固定 200，业务看 code

```json
{ "code": 200, "message": "操作成功", "data": {} }
```

2. 鉴权规则

- 本模块接口全部需要登录，未登录返回 `401`
- userId 一律从 token 解析，禁止前端传入
- 请求头：`Authorization: Bearer xxx`、`X-Client-Type: APP`（非 APP 一律 401，与答题链路一致）

3. ID 序列化：雪花 Long ID，响应统一用字符串，避免前端精度丢失；请求体里的 `questionId` / `questionIds[]` 同样用字符串接收，服务端手工解析

4. 时间：全部返回毫秒时间戳

5. 分页：`page` 默认 1，`pageSize` 默认 20，最大 100，越界返回 `8101`；ID 非数字、批量条数越界同样走 `8101`

6. 路径前缀：`/api/practice` 由网关提供（StripPrefix=2），practice-service 内路径写 `/hsk/...`；exam-service 前缀为 `/api/exam`，内路径写 `/answer/...`

7. 兼容性：新增响应字段允许为 `null`，老版本客户端无需升级；老客户端不传筛选参数时按「全部」处理

## 1.业务背景与目标

HSK 考试与练习目前都只产出当轮结果（报告 / 成绩单），用户错过的题和想回看的题，答完一卷就散了。本次为考试与练习建立同一套「错题本」与「收藏夹」：

- 错题本：交卷判分后，把判错的客观题自动收录进来，供用户集中复习；用户可手动移出
- 收藏夹：答题过程中点收藏，答题卡立刻显示已收藏；整轮答完后，被收藏的题进入收藏夹，供长期回看

两条链路的**存储与读取完全共用**（同一库、同一组表），差异只在「哪一侧写入」：

| 场景 | 写入方 | 读取方 |
|---|---|---|
| 练习交卷 | practice-service（`source='prac'`） | practice-service |
| 考试交卷（判分后） | exam-service（`source='exam'`） | practice-service |

解决的问题：原先只有 CSCA 有错题本 / 收藏，HSK 侧没有落点；两侧各写一套会导致「同一道题在练习里错、在考试里也错」时出现两行数据、来源标签互相覆盖。

## 2.业务决策/核心公式

### 2.1 错题本规则

1. 收录时机：**交卷判分完成后**才写，答题过程中不写。练习侧在交卷终结器内写，考试侧在异步判分完成后写
2. 收录条件：`is_correct = 2`（已作答且判错）。**未作答不收**（未答不等于答错）
3. 主观题（写作 / 翻译 / 口语）没有「对错」，**不进错题本**；口语还涉及录音与 AI 评分，一律不收录
4. 只进不出：判对不移出、未评分不动；移出只有用户手动操作
5. 唯一性：一个用户一道题恒一行，唯一键 `uk_user_question(user_id, question_id)`，不含 `deleted` → 软删后可原地复活
6. 重复判错：只刷新 `user_answer` 与 `updated_time`，**不覆盖** `source` / `record_id` / `section`（先练习错、后考试错时，来源标签停在首次收录那一轮）
7. 手动移出：`deleted = 1`，再次判错可由交卷链路复活（`deleted = 0`）

### 2.2 收藏夹规则（两阶段）

收藏不是「点一下就进收藏夹」，而是分两步：

| 阶段 | 时机 | 动作 | 用户可见性 |
|---|---|---|---|
| 暂存 | 答题中点击收藏 | 写 `question_favorite`，`in_book = 0` | 答题卡显示已收藏；收藏夹列表**看不到** |
| 入册 | 整轮交卷 | 本次题集内 `deleted = 0` 的行置 `in_book = 1` | 收藏夹列表可见 |

1. 取消收藏：立即 `deleted = 1`，不区分阶段；答题卡随即变回未收藏
2. 已入册的题在下一轮答题中再收藏：`in_book` **不回退**（仍在收藏夹里），只刷新时间
3. 中途退出未交卷：`in_book` 保持 0，收藏夹不可见，下次进入该轮答题卡仍显示已收藏；交卷后才入册
4. 收藏与「标记」是两件事：标记（`exam_answer.is_tag` / 答题卡 `isTag`）只作用于当前这一轮，不进收藏夹
5. 唯一性同错题本：一用户一题一行，软删复活

### 2.3 快照口径（写库时确定，读库时不再回查）

| 列 | 取值 | 说明 |
|---|---|---|
| `level_code` | `HSK1`–`HSK6`、`HSK7-9`（`exam_paper.level` 为 `'1'`–`'7'`，`'7'` 映射 `HSK7-9`） | HSKK 口语卷取 `speaking_exam_paper.level`，映射 `HSKK PRIMARY` / `HSKK INTERMEDIATE` / `HSKK ADVANCED` |
| `section` | `listening` / `reading` / `writing` / `speaking` / `translation` | 练习取 `practice_record.section_mapping`；考试取**该题**在 `exam_answer.section_mapping`（一场 HSK 考试跨听力 / 阅读 / 写作，不能取卷级） |
| `language_version` | 恒 `chinese` | `exam_paper.language_version` 对 HSK 全为 `NULL`（只有 CSCA 有值），不能取卷表，否则写空 |

### 2.4 写入口径（时机 / 事务 / 失败策略）

1. 错题本与收藏入册都由**交卷链路内部触发**，不额外暴露对 C 端接口，前端不需要调
2. 写入使用**独立事务**（`REQUIRES_NEW`）：错题本 / 收藏夹写失败不能回滚交卷
3. 写入异常只记 error 日志，不抛给前端；交卷成功即视为成功
4. 批量写入必须**单条多值 INSERT**（`ON DUPLICATE KEY UPDATE`），禁止逐条 `executemany`：TEST / PROD 都是公网 MySQL，逐条往返代价高
5. `question_wrong` / `question_favorite` 的 `id` 列无 `AUTO_INCREMENT`（全局 `id-type: auto` 对它无效），必须应用层雪花 ID

### 2.5 核心公式

```
错题条件 = answered = 1 AND is_correct = 2
收藏夹可见 = user_id = ? AND deleted = 0 AND in_book = 1
交卷入册范围 = user_id = ? AND question_id IN (本轮题集) AND deleted = 0 → in_book = 1
错题本角标数 = COUNT(*) WHERE user_id = ? AND deleted = 0（叠加当前筛选）
```

## 3.数据模型设计

### 3.1 涉及数据表

| 表名 | 改动说明 |
|---|---|
| `question_favorite` | **新增列** `in_book`（是否已进收藏夹：0 答题中暂存 / 1 交卷后入册），`tinyint NOT NULL DEFAULT 1`。存量行默认 1（CSCA 现网数据本来就在收藏夹里）。列表查询必须带 `in_book = 1` |
| `question_wrong` | **结构不动**。已有 `level_code` / `section` / `language_version` / `user_answer` / `source` / `record_id` / `deleted` 全部够用 |
| `practice_record` | 只读：取 `paper_id` / `section_mapping`，用于拼快照 |
| `practice_answer` | 只读：取 `is_correct = 2` 的题与 `answer`（写 `user_answer`） |
| `practice_subjective_record` / `practice_subjective_answer` | 只读：判断「本轮是主观模块」时跳过错题写入；收藏按题取板块 |
| `exam_record` | 只读：取 `paper_id`，用于拼快照 |
| `exam_answer` | 只读：取 `is_correct = 2` 的题、`answer`、`section_mapping`（每题板块） |
| `exam_paper` | 只读：取 `level`；`language_version` 对 HSK 为 `NULL`，不用于写入 |
| `speaking_exam_paper` | 只读：HSKK 口语卷取 `level`（`Beginner` / `Intermediate` / `Advanced`） |

唯一键与索引：

- `question_favorite`：`uk_user_question(user_id, question_id)` 保持不变；新增索引 `idx_user_book_time(user_id, in_book, deleted, updated_time)` 覆盖列表查询
- `question_wrong`：`uk_user_question(user_id, question_id)` 保持不变；现有 `idx_user_time(user_id, deleted, updated_time)` 覆盖默认排序，按等级 / 模块筛选的词条数可控，暂不新增索引

DDL（TEST 先行，PROD 上线前同批执行）：

```sql
ALTER TABLE question_favorite
    ADD COLUMN in_book tinyint NOT NULL DEFAULT 1
    COMMENT '是否已进收藏夹：0=答题中暂存，1=交卷后入册' AFTER deleted;

ALTER TABLE question_favorite
    ADD KEY idx_user_book_time (user_id, in_book, deleted, updated_time);
```

> `question_favorite` / `question_wrong` 在 TEST 已建，**PROD 尚未建表**（与 CSCA 错题本同一批遗留）。上线前必须先建表，否则写入会报 `Table doesn't exist`；写入失败已被独立事务 + 异常吞掉，不会阻断交卷，但功能整段不可用。

### 3.2 枚举定义

`source`（来源）：

| 枚举值 | 含义 | `record_id` 指向 |
|---|---|---|
| `prac` | 练习 | `practice_record.id` |
| `exam` | 考试 | `exam_record.id` |

`in_book`（是否已进收藏夹）：

| 枚举值 | 含义 | 备注 |
|---|---|---|
| 0 | 答题中暂存 | 只在答题卡可见；中途退出且不交卷则一直停留在此 |
| 1 | 已入册 | 收藏夹列表可见；存量数据默认此值 |

`level_code`（等级快照）：

| 来源等级 | 写入值 |
|---|---|
| `exam_paper.level = '1'`–`'6'` | `HSK1`–`HSK6` |
| `exam_paper.level = '7'` | `HSK7-9` |
| `speaking_exam_paper.level = Beginner` | `HSKK PRIMARY` |
| `speaking_exam_paper.level = Intermediate` | `HSKK INTERMEDIATE` |
| `speaking_exam_paper.level = Advanced` | `HSKK ADVANCED` |

### 3.3 状态流转

收藏（`question_favorite`）：

```
未收藏 ──答题中收藏──> 暂存(in_book=0, deleted=0) ──交卷──> 已入册(in_book=1, deleted=0)
   ↑                        │                                    │
   └──────取消收藏(deleted=1)┘                                    │
   └──────────────────取消收藏(deleted=1)─────────────────────────┘

已入册 ──下一轮答题中再收藏──> 仍为已入册（in_book 不回退）
```

错题（`question_wrong`）：

```
未收录 ──交卷判错(is_correct=2)──> 在错题本(deleted=0) ──手动移出──> 已移出(deleted=1)
                                        ↑                              │
                                        └────────再次判错（复活）───────┘
```

## 4.接口总览清单

接口类型说明：新增 / 改造 / 复用不改代码

| #   | Method | Path                                                                                             | 用途              | 服务               | 接口类型 |
| --- | ------ | ------------------------------------------------------------------------------------------------ | --------------- | ---------------- | ---- |
| 1   | GET    | `/hsk/wrong-book`                                                                                | 错题本分页列表         | practice-service | 新增   |
| 2   | DELETE | `/hsk/wrong-book/{questionId}`                                                                   | 单题移出错题本         | practice-service | 新增   |
| 3   | POST   | `/hsk/wrong-book/batch-remove`                                                                   | 批量移出错题本         | practice-service | 新增   |
| 4   | GET    | `/hsk/favorites`                                                                                 | 收藏夹分页列表         | practice-service | 新增   |
| 5   | PUT    | `/hsk/favorites/{questionId}`                                                                    | 答题中收藏（练习侧）      | practice-service | 新增   |
| 6   | DELETE | `/hsk/favorites/{questionId}`                                                                    | 取消收藏（练习侧）       | practice-service | 新增   |
| 7   | POST   | `/hsk/favorites/batch-cancel`                                                                    | 批量取消收藏          | practice-service | 新增   |
| 8   | POST   | `/answer/hsk/favorite`                                                                           | 答题中收藏 / 取消（考试侧） | exam-service     | 新增   |
| 9   | GET    | `/hsk/objective/records/{recordId}/answer-card`、`/hsk/subjective/records/{recordId}/answer-card` | 练习答题卡回收藏态       | practice-service | 改造   |
| 10  | GET    | `/answer/card/detail/{paperId}`                                                                  | 考试答题卡回收藏态       | exam-service     | 改造   |

> 交卷时的写入（错题收录 + 收藏入册）不在本清单内：它是交卷链路的内部步骤，无独立端点，详见 §2.4 与 §5.11。

## 5.接口详细定义

### 5.1 GET `/hsk/wrong-book`

**用途**：错题本分页列表（五模块共用，练习与考试合并展示）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| levelCode | query | String | 否 | `HSK1`–`HSK6` / `HSK7-9` / `HSKK PRIMARY` 等；不传为全部 |
| section | query | String | 否 | `listening` / `reading` / `writing` / `speaking` / `translation`，大小写不敏感；不传为全部 |
| source | query | String | 否 | `prac` / `exam`；不传为全部 |
| keyword | query | String | 否 | 题干关键词，模糊匹配题面；空串等同不传 |
| startTime | query | Long | 否 | 错题时间下界（毫秒，闭区间） |
| endTime | query | Long | 否 | 错题时间上界（毫秒，闭区间） |
| order | query | String | 否 | `asc` / `desc`，按错题时间排序，缺省 `desc` |
| page | query | Integer | 否 | 页码，缺省 1 |
| pageSize | query | Integer | 否 | 每页条数，缺省 20，最大 100 |

**请求示例**

```http
GET /practice/hsk/wrong-book?levelCode=HSK3&section=listening&source=prac&order=desc&page=1&pageSize=20
Authorization: Bearer eyJhbGciOi...
X-Client-Type: APP
```

**返回成功示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "total": 37,
    "page": 1,
    "pageSize": 20,
    "wrongQuestions": [
      {
        "questionId": "1234567890123456789",
        "levelCode": "HSK3",
        "section": "listening",
        "layout": "textChoice",
        "typeId": "3",
        "typeIdMapping": "SINGLE",
        "content": "他今天为什么没来上班？",
        "passage": null,
        "optionContent": { "A": "生病了", "B": "出差了", "C": "请假了", "D": "迟到了" },
        "audioUrl": "https://cdn.example.com/audio/1234567890123456789.mp3",
        "shareAudioUrl": null,
        "groupId": null,
        "group": null,
        "standardAnswer": "A",
        "standardAnswerLabels": ["A"],
        "userAnswer": "B",
        "source": "prac",
        "recordId": "1234567890123456790",
        "wrongTime": 1763000000000
      }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| total | Integer | 符合筛选条件的错题总数（不是本页条数）；不带筛选时即「我的」页错题本角标 |
| page / pageSize | Integer | 回显入参（已填缺省） |
| wrongQuestions | Array | 本页错题，按 `wrongTime` 排序 |
| wrongQuestions[].questionId | String | 题目 ID |
| wrongQuestions[].levelCode | String | 等级快照，取收录时的等级（不是题目现在的等级） |
| wrongQuestions[].section | String | 模块码快照（`listening` 等） |
| wrongQuestions[].layout | String | 题面布局，取 `question.layout`，前端按它选渲染形态 |
| wrongQuestions[].typeId / typeIdMapping | String | 题型原始码 / 对外映射码（`SINGLE` / `MULTI` 等） |
| wrongQuestions[].content / passage | String | 题干 / 材料正文，按 `layout` 取值，另一项为 `null` |
| wrongQuestions[].optionContent | Object | 选项扁平映射 `{"A":"文本"}`，无选项为 `null` |
| wrongQuestions[].audioUrl / shareAudioUrl | String | 题目音频 / 共享材料音频 |
| wrongQuestions[].groupId / group | String / Object | 题组 ID / 题组共享内容，非题组题为 `null` |
| wrongQuestions[].standardAnswer | String | 标准答案原文（`question.answer`，原值直传） |
| wrongQuestions[].standardAnswerLabels | Array | 标准答案按 `, ， ; ； / 、 空白` 切分后的标签数组，供前端高亮 |
| wrongQuestions[].userAnswer | String | 最近一次判错时的作答原文（`question_wrong.user_answer`）；历史行可能为 `null` |
| wrongQuestions[].source | String | `prac` / `exam` |
| wrongQuestions[].recordId | String | 来源记录 ID，按 `source` 判定表；可为 `null` |
| wrongQuestions[].wrongTime | Long | 错题时间（`updated_time`，最近一次收录 / 状态变更） |

**服务端内部执行顺序（重要，后端&测试阅读）**

1. 解析 token 取 userId，非 APP 或取不到 → `401`
2. 解析筛选项：`levelCode` / `section` / `source` 走白名单（`source` 只认 `prac` / `exam`，其余 → `8101`）；`order` 只认 `asc` / `desc`
3. 分页参数校验：`page >= 1`、`1 <= pageSize <= 100`，越界 → `8101`
4. 一次 count 查询：`user_id = ? AND deleted = 0` + 筛选条件
5. 一次分页查询：同 where，`ORDER BY updated_time ASC|DESC`，`LIMIT / OFFSET`
6. 按本页 `question_id` 批量查 `question` 表，装配题面（与作答 / 报告同一套字段）
7. 逐行拼装"题面 + 错题快照"，标准答案随行下发；**不下发解析**——解析只在交卷后的报告单题接口（`/report/questions/{questionId}`）里，列表不带
8. 无数据 → `total = 0`、`wrongQuestions = []`，不报错

> 约束重点
>
> 1. 列表只读 `question_wrong` 与 `question` 两张表，**不回查** `practice_answer` / `exam_answer`——错题本状态自持，回查会让「判对后答案变了」影响历史条目
> 2. 不做 N+1：题面必须按本页 ID 批量查，禁止逐题查库
> 3. 本响应带用户维度（私有错题本），不可做公共缓存（CDN / 网关级）

**本接口抛出错误码**：401 / 8101

### 5.2 DELETE `/hsk/wrong-book/{questionId}`

**用途**：把一道题移出错题本（软删，可被再次判错复活）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| questionId | path | String | 是 | 题目 ID（19 位字符串），非数字 → `8101` |

**请求示例**

```http
DELETE /practice/hsk/wrong-book/1234567890123456789
Authorization: Bearer eyJhbGciOi...
X-Client-Type: APP
```

**返回成功示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { "questionId": "1234567890123456789", "removed": true, "wrongBookCount": 36 }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| questionId | String | 被操作的题目 ID |
| removed | Boolean | 操作后是否已移出（`true`） |
| wrongBookCount | Integer | 操作后该用户错题本总数（不带筛选），供角标刷新 |

**服务端内部执行顺序（重要，后端&测试阅读）**

1. 取 userId，非 APP → `401`
2. 手工解析 `questionId`，非数字 → `8101`
3. `UPDATE question_wrong SET deleted = 1, updated_time = now WHERE user_id = ? AND question_id = ? AND deleted = 0`
4. 影响行数为 0 → 说明本就不在错题本：**幂等返回** `removed = true`（不报 404，避免前端重复点击弹错）
5. 查该用户错题本总数，组装回执

> 约束重点
>
> 1. 只按 `user_id + question_id` 更新，禁止按 `id` 单条件更新（防越权移出他人错题）
> 2. 物理删除一律禁止：错题本靠 `deleted` 软删，物理删会丢「曾收录」的语义并让唯一键冲突
> 3. 移出后该题若在本轮再次被判错，交卷链路会把它复活（`deleted = 0`），这是预期行为

**本接口抛出错误码**：401 / 8101

### 5.3 POST `/hsk/wrong-book/batch-remove`

**用途**：批量移出错题本（错题本多选删除）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| questionIds | body | String[] | 是 | 题目 ID 数组，1–100 条；空数组或超 100 条 → `8101` |

**请求示例**

```json
{
  "questionIds": ["1234567890123456789", "1234567890123456790"]
}
```

**返回成功示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { "removedCount": 2, "wrongBookCount": 35 }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| removedCount | Integer | 实际移出条数（本就不在错题本的 ID 不计入） |
| wrongBookCount | Integer | 操作后错题本总数 |

**服务端内部执行顺序（重要，后端&测试阅读）**

1. 取 userId，非 APP → `401`
2. 入参校验：数组非空、长度 ≤ 100、元素全部可解析为数字，否则 `8101`
3. 去重后一条 SQL：`UPDATE ... SET deleted = 1, updated_time = now WHERE user_id = ? AND question_id IN (...) AND deleted = 0`
4. 影响行数为 `removedCount`；不存在的 ID 静默跳过（幂等）
5. 查总数组装回执
6. 全程 `@Transactional`（单条 UPDATE + 一次 count，失败整体回滚）

**本接口抛出错误码**：401 / 8101

### 5.4 GET `/hsk/favorites`

**用途**：收藏夹分页列表（练习与考试合并，只含已入册的收藏）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| levelCode | query | String | 否 | 同错题本 |
| section | query | String | 否 | 同错题本 |
| source | query | String | 否 | `prac` / `exam` |
| keyword | query | String | 否 | 题干关键词 |
| startTime / endTime | query | Long | 否 | 收藏时间区间（毫秒，闭区间，按 `updated_time`） |
| order | query | String | 否 | `asc` / `desc`，缺省 `desc` |
| page / pageSize | query | Integer | 否 | 缺省 1 / 20，最大 100 |

**请求示例**

```http
GET /practice/hsk/favorites?section=reading&source=exam&page=1&pageSize=20
Authorization: Bearer eyJhbGciOi...
X-Client-Type: APP
```

**返回成功示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "total": 12,
    "page": 1,
    "pageSize": 20,
    "questions": [
      {
        "questionId": "1234567890123456791",
        "levelCode": "HSK4",
        "section": "reading",
        "layout": "passageGroup",
        "typeId": "12",
        "typeIdMapping": "SINGLE",
        "content": "根据上文，作者对这件事的态度是：",
        "passage": "……（材料正文）……",
        "optionContent": { "A": "支持", "B": "反对", "C": "中立", "D": "未提及" },
        "audioUrl": null,
        "shareAudioUrl": null,
        "groupId": "1234567890123456792",
        "group": {
          "passage": "……（题组共享材料）……",
          "audioUrl": null
        },
        "standardAnswer": "C",
        "standardAnswerLabels": ["C"],
        "favoriteTime": 1763000000000,
        "source": "exam",
        "recordId": "1234567890123456793"
      }
    ]
  }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| total | Integer | 符合筛选条件的已入册收藏总数（`in_book = 1 AND deleted = 0`） |
| page / pageSize | Integer | 回显入参 |
| questions | Array | 本页收藏，按 `favoriteTime` 排序 |
| questions[].questionId | String | 题目 ID |
| questions[].levelCode / section | String | 等级 / 模块快照（收录时值） |
| questions[].layout 及题面字段 | — | 与作答接口同构：`layout` 决定取 `content` / `passage` / `optionContent` / `group`；主观题多 `sectionTitle` / `picUrl` / `groupContent` 等字段 |
| questions[].standardAnswer | String | 标准答案原文；主观题无标准答案时为 `null` |
| questions[].standardAnswerLabels | Array | 客观题答案标签数组；主观题为空数组 |
| questions[].favoriteTime | Long | 收藏时间（`updated_time`） |
| questions[].source | String | `prac` / `exam` |
| questions[].recordId | String | 来源记录 ID |

**服务端内部执行顺序（重要，后端&测试阅读）**

1. 取 userId，非 APP → `401`
2. 解析筛选项与分页（同 5.1）
3. count：`user_id = ? AND deleted = 0 AND in_book = 1` + 筛选
4. 分页查询：同上 where，`ORDER BY updated_time ASC|DESC`
5. 按 `question_id` 批量装配题面；主观题（`SEC_WRITE` / `SEC_TRANSLATION` / `SEC_SPEAK`）走主观题面字段，客观题走客观题面字段
6. 逐行拼装，标准答案随行下发，**不含解析**（解析走交卷后的报告单题接口）
7. 无数据 → `total = 0`、`questions = []`

> 约束重点
>
> 1. **必须带 `in_book = 1`**：漏掉这个条件会把「答题中暂存」的收藏提前暴露到收藏夹
> 2. 与错题本同：批量装配、不回查作答表、不做公共缓存

**本接口抛出错误码**：401 / 8101

### 5.5 PUT `/hsk/favorites/{questionId}`

**用途**：练习答题过程中收藏（暂存，`in_book = 0`）；也用于已交卷报告的「再收藏」
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| questionId | path | String | 是 | 题目 ID，非数字 → `8101` |
| recordId | body | String | 是 | 练习记录 ID；用于校验归属与取快照 |
| module | body | String | 是 | 模块码 `listening` / `reading` / `writing` / `translation` / `speaking` |

**请求示例**

```json
{
  "recordId": "1234567890123456790",
  "module": "listening"
}
```

**返回成功示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { "questionId": "1234567890123456789", "favorite": true, "inBook": false, "favoriteCount": 13 }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| questionId | String | 题目 ID |
| favorite | Boolean | 是否已收藏（`true`） |
| inBook | Boolean | 是否已在收藏夹（答题中恒 `false`；若该题历史已入册则回 `true`） |
| favoriteCount | Integer | 该用户已入册收藏总数（`in_book = 1 AND deleted = 0`），供「我的」角标 |

**服务端内部执行顺序（重要，后端&测试阅读）**

1. 取 userId，非 APP → `401`
2. 解析 `questionId` / `recordId`；`module` 走白名单，非法 → `8133`
3. 查练习记录（按 module 分表：客观 → `practice_record`，主观 → `practice_subjective_record`），校验 `user_id` 归属、`deleted = 0`；不存在或不属于本人 → `8112`
4. 校验题目在本轮题集内（`question_ids` 快照，主观题查作答行）→ 否则 `8107`
5. 拼快照：`level_code` 取记录 `paper_id` 对应卷的等级映射；`section` 取记录 `section_mapping` 反查模块码（`SEC_LISTEN` → `listening`，`SEC_SPEAKING` / 历史别名 `SEC_SPEAK` 都归 `speaking`）；`language_version` 恒 `chinese`
6. UPSERT：
   - 记录进行中（`practice_record.status = 1`）→ 新行 `in_book = 0`（暂存）
   - 记录已提交（`status = 3`，即报告页复用本接口）→ 新行 `in_book = 1`（直接入册）
   - 命中唯一键时只更新 `deleted = 0` 与 `updated_time`，**不动 `in_book`**（已入册的保持 1，未入册的保持 0）
7. 查该行最终 `in_book` 与已入册收藏总数，组装回执

> 约束重点
>
> 1. UPSERT 的 `ON DUPLICATE KEY UPDATE` 里**禁止写 `in_book = VALUES(in_book)`**，否则「已入册 → 再收藏」会被打回暂存，收藏夹里凭空消失
> 2. 归属校验必须做：不校验会出现「收藏别人练习里的题」
> 3. 不校验记录状态：答题中与已交卷都允许收藏，区别只在 `in_book` 初值（0 / 1），报告页因此可以复用本接口

**本接口抛出错误码**：401 / 8101 / 8133 / 8112 / 8107

### 5.6 DELETE `/hsk/favorites/{questionId}`

**用途**：取消收藏（练习侧），立即从收藏夹消失
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| questionId | path | String | 是 | 题目 ID，非数字 → `8101` |

**请求示例**

```http
DELETE /practice/hsk/favorites/1234567890123456789
Authorization: Bearer eyJhbGciOi...
X-Client-Type: APP
```

**返回成功示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { "questionId": "1234567890123456789", "favorite": false, "favoriteCount": 12 }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| questionId | String | 题目 ID |
| favorite | Boolean | 操作后是否已收藏（`false`） |
| favoriteCount | Integer | 操作后已入册收藏总数 |

**服务端内部执行顺序（重要，后端&测试阅读）**

1. 取 userId，非 APP → `401`
2. 解析 `questionId`，非数字 → `8101`
3. `UPDATE question_favorite SET deleted = 1, updated_time = now WHERE user_id = ? AND question_id = ? AND deleted = 0`
4. 影响行数为 0 → 幂等返回 `favorite = false`，不报错
5. 查已入册总数组装回执

**本接口抛出错误码**：401 / 8101

### 5.7 POST `/hsk/favorites/batch-cancel`

**用途**：批量取消收藏（收藏夹多选删除）
**鉴权**：需要登录

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| questionIds | body | String[] | 是 | 1–100 条，非法同 5.3 |

**请求示例**

```json
{ "questionIds": ["1234567890123456789", "1234567890123456790"] }
```

**返回成功示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { "cancelledCount": 2, "favoriteCount": 10 }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| cancelledCount | Integer | 实际取消条数 |
| favoriteCount | Integer | 操作后已入册收藏总数 |

**服务端内部执行顺序**

1. 取 userId，非 APP → `401`
2. 入参校验同 5.3
3. 一条 UPDATE 软删（`user_id + question_id IN (...) + deleted = 0`）
4. 查已入册总数组装回执

**本接口抛出错误码**：401 / 8101

### 5.8 POST `/answer/hsk/favorite`（exam-service）

**用途**：考试答题过程中收藏 / 取消收藏（暂存，交卷后入册）。与 CSCA 的 `/answer/csca/favorite` 同构
**鉴权**：需要登录，且 `X-Client-Type` 必须为 `APP`（否则 `401`）

**入参说明**

| 参数名 | 位置 | 类型 | 必填 | 约束&说明 |
|---|---|---|---|---|
| questionId | body | String | 是 | 题目 ID（字符串，防精度丢失） |
| examRecordId | body | String | 是 | 考试记录 ID |
| favorite | body | Boolean | 是 | `true` 收藏 / `false` 取消 |

**请求示例**

```json
{
  "questionId": "1234567890123456789",
  "examRecordId": "1234567890123456800",
  "favorite": true
}
```

**返回成功示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { "questionId": "1234567890123456789", "favorite": true, "inBook": false, "favoriteCount": 8 }
}
```

**返回字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| questionId | String | 题目 ID |
| favorite | Boolean | 操作后是否已收藏 |
| inBook | Boolean | 是否已入册（考试进行中 `false`；交卷后调用则 `true`） |
| favoriteCount | Integer | 该用户已入册收藏总数 |

**服务端内部执行顺序（重要，后端&测试阅读）**

1. 校验 `X-Client-Type = APP` 与 userId，任一不满足 → `401`
2. 解析三个字段，缺任一 → `8005`
3. 查 `exam_record`，校验 `user_id` 归属与 `deleted = 0` → 否则 `8107`
4. 校验题目属于本卷（`question.paper_id = record.paper_id`）→ 否则 `8006`
5. 拼快照：`level_code` 取 `exam_paper.level` 映射；`section` 取**该题**在 `exam_answer.section_mapping` 反查模块码（查不到时退 `question.section_mapping`）；`language_version` 恒 `chinese`
6. UPSERT：`deleted = favorite ? 0 : 1`；新行 `in_book = 考试进行中 ? 0 : 1`（交卷后在诊断报告里收藏直接入册）；命中已有行时不动 `in_book`
7. 返回终态与已入册总数

> 约束重点
>
> 1. 不校验 `exam_record.status`：交卷后在诊断报告里也要能收藏，已交卷时 `in_book` 直接置 1
> 2. `section` 不能取 `exam_paper.subject_type_mapping`——那是 CSCA 专用列，HSK 全为 `NULL`；一场 HSK 考试跨听力 / 阅读 / 写作，必须按题取板块
> 3. 与「标记」（`POST /answer/paper/tag`，写 `exam_answer.is_tag`）完全独立，互不影响

**本接口抛出错误码**：400 / 401 / 8005 / 8006 / 8107

### 5.9 练习答题卡：回收藏态（改造）

**用途**：答题卡上显示每题是否已收藏（当前 `AnswerCardResponse` 只回答没答）
**鉴权**：需要登录

**改动点**

1. `AnswerCardQuestion` 新增字段 `favorite`（Boolean）：本次答题卡内该题是否已收藏（读 `question_favorite` 中 `deleted = 0` 的行，**不区分 `in_book`**——暂存也要显示）
2. 路径不变：`GET /hsk/objective/records/{recordId}/answer-card`、`GET /hsk/subjective/records/{recordId}/answer-card`
3. 实现：按本次题集 `question_ids` 批量查收藏，拼进每题项；禁止逐题查库

**返回片段示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "recordId": "1234567890123456790",
    "paperId": "1234567890123456700",
    "section": 1,
    "totalQuestions": 20,
    "answeredCount": 12,
    "unansweredCount": 8,
    "currentQuestionNumber": 13,
    "questions": [
      { "order": 1, "questionId": "1234567890123456789", "answered": true, "current": false, "favorite": true },
      { "order": 2, "questionId": "1234567890123456791", "answered": false, "current": false, "favorite": false }
    ]
  }
}
```

**本接口抛出错误码**：401 / 8133（沿用现有）

### 5.10 考试答题卡：回收藏态（改造）

**用途**：考试答题卡显示每题是否已收藏
**鉴权**：需要登录

**改动点**

1. `AnswerCardDetailDTO.QuestionStatus` 新增 `favorite`（Boolean）
2. 路径不变：`GET /answer/card/detail/{paperId}?currentQuestionNumber=`
3. 实现：按本卷题目 ID 批量查 `question_favorite`（`deleted = 0`），与 `isTag` 并列下发；只查本卷题目，不拉用户全量收藏

**返回片段示例**

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "paperId": "1234567890123456700",
    "currentQuestionNumber": 13,
    "currentSection": "SEC_LISTEN",
    "sections": [
      {
        "section": "SEC_LISTEN",
        "sectionName": "听力",
        "enabled": true,
        "questions": [
          { "questionNumber": 1, "answered": true, "enabled": true, "current": false, "isTag": 0, "favorite": true }
        ]
      }
    ]
  }
}
```

**本接口抛出错误码**：401（沿用现有）

### 5.11 交卷内部写入（无独立端点）

**触发点**

| 场景 | 位置 | 写入内容 |
|---|---|---|
| 练习听力交卷 | `ListeningSubmissionFinalizer.finalize`（判分循环之后） | 错题 `source='prac'` + 收藏入册 |
| 练习阅读交卷 | `ReadingSubmissionFinalizer.finalize` | 同上 |
| 练习主观交卷（写作 / 翻译 / 口语） | `SubjectivePracticeServiceImpl.submit` | 只做收藏入册；**不写错题本** |
| 考试交卷（HSK） | `ExamRecordServiceImpl.submitExam`（记录状态置提交之后） | 只做收藏入册（不等判分，交卷即可见） |
| 考试判分完成 | `AsyncGradingServiceImpl` | 只做错题 `source='exam'` |

**A. 收藏入册（交卷时同步执行，与判分无关）**

1. 交卷主流程完成：记录状态已置已提交、主事务已提交
2. 收集本轮题集 ID：练习取 `practice_record.question_ids` / 主观取作答行；考试取该场 `exam_answer.question_id` 全量
3. 独立事务（`REQUIRES_NEW`）：`UPDATE question_favorite SET in_book = 1, updated_time = now WHERE user_id = ? AND question_id IN (本轮题集) AND deleted = 0`
4. 异常 → error 日志，吞掉

**B. 错题收录（判分完成后执行）**

1. 前置：判分结果已落库（`is_correct` 已写 1 / 2）
2. 收集本轮 `is_correct = 2` 的客观题：`questionId` + `answer` 原文（不归一化）
3. 拼快照：`level_code` / `section` / `language_version`（口径见 §2.3）
4. 独立事务内单条多值 UPSERT `question_wrong`：
   - INSERT：`id`（雪花）、`user_id`、`question_id`、`level_code`、`section`、`language_version`、`user_answer`、`source`、`record_id`、`deleted=0`、`created_time`、`updated_time`
   - ON DUPLICATE：只更新 `user_answer`、`deleted = 0`、`updated_time`；**不覆盖** `source` / `record_id` / `section` / `level_code`
5. 异常 → error 日志，吞掉

> 约束重点
>
> 1. 写入器必须是独立 Bean：`REQUIRES_NEW` 靠 Spring 代理生效，写在同类私有方法上加注解不会开新事务
> 2. 错题本空列表（全对或全未答）直接跳过，不发 SQL
> 3. 收藏入册只扫本轮题集，不要 `WHERE user_id = ?` 全量置 1（会提前放出其他未交卷轮次的暂存收藏）

## 6.错误码定义

| 错误码 | 归属服务 | 触发场景 |
|---|---|---|
| 200 | 两服务 | 成功 |
| 400 | exam-service | 请求体缺失 / 必填字段缺失 |
| 401 | 两服务 | 未登录、token 无效、`X-Client-Type` 非 APP |
| 8005 | exam-service | 考试侧收藏入参缺失（`questionId` / `examRecordId` / `favorite`） |
| 8006 | exam-service | 题目不属于本场考试 |
| 8107 | exam-service | **考试记录**不存在或不属于当前用户 |
| 8101 | practice-service | 参数非法：分页越界、ID 非数字、`source` / `order` 取值非法、批量条数越界、收藏数超上限（detail 写明原因） |
| 8107 | practice-service | **题目**不存在或不属于本次练习（注意与 exam 侧 8107 同码不同义，按服务区分） |
| 8112 | practice-service | 练习记录不存在 |
| 8133 | practice-service | `module` 不在五模块白名单 |

> 本期不新增错误码，全部复用现有 `HskPracticeErrorCode` / exam 侧业务码；`8101` 作为参数类兜底，调用处传 detail 区分具体原因。

## 7.边界特殊场景说明

1. 同一题先练习错、后考试错：唯一键命中，`source` 停在首次的 `prac`，`user_answer` 与 `updated_time` 刷新为考试那次。列表按 `source` 筛会出现「考试错的题在 `prac` 下」——这是刻意的：来源表示「何时第一次进错题本」，不是「最近一次错在哪」
2. 中途退出未交卷：收藏停在 `in_book = 0`，收藏夹看不到；下次进答题卡仍显示已收藏；交卷才入册。错题本轮不写（不交卷不判分）
3. 交卷时收藏已在本轮取消：`deleted = 1`，入册 SQL 的 `deleted = 0` 条件自然跳过，不会复活
4. 已入册收藏在下一轮答题时取消：立即从收藏夹消失；再收藏回来时 `in_book` 仍为 1（唯一键行未删，只翻 `deleted`）
5. 错题本写失败（PROD 未建表 / 死锁 / 超时）：只记 error 日志，交卷照常成功；用户侧表现为「这轮错题没进错题本」，可通过后续同题再错补齐
6. 并发收藏同一题：唯一键保证一行，`ON DUPLICATE KEY UPDATE` 幂等；两次请求最终态一致，`favoriteCount` 可能瞬时偏差，前端以最后一次回执为准
7. 并发交卷 / 重复交卷：交卷幂等键命中直接返回，错题与入册写入**只执行一次**；重试交卷不会重复刷新 `user_answer`
8. 题目被下架（`enabled_prac = 0`）：错题本 / 收藏夹照常展示（历史条目不能凭空消失），题面从 `question` 表实时取，取不到时该条降级为「题目已下架」占位，不整页报错
9. 主观题收藏：可收藏、可在收藏夹查看，但无 `standardAnswerLabels`、不进错题本
10. 空数据：`total = 0` + 空数组，不报 404；前端按空态渲染

## 8.验收测试用例

| # | 测试场景 | 预期结果 |
|---|---|---|
| 1 | 练习听力交卷，20 题错 5 题（含 1 题未作答） | 错题本新增 4 行（未作答不计），`source='prac'`、`level_code`/`section`/`language_version` 正确 |
| 2 | 同一题第二次判错 | 不新增行，只刷新 `user_answer` 与 `wrong_time` |
| 3 | 同一题先练习错、后考试错 | 仍一行，`source` 保持 `prac`，`user_answer` 为考试那次 |
| 4 | 考试交卷（异步判分完成） | 错题本新增判错客观题，`source='exam'`，`record_id` 为 `exam_record.id` |
| 5 | 练习主观题（写作）交卷 | 错题本无新增；收藏正常入册 |
| 6 | 答题中收藏 3 题后查收藏夹 | 收藏夹为空（`in_book = 0`），答题卡显示 3 题已收藏 |
| 7 | 交卷后再查收藏夹 | 3 题出现，`favoriteTime` 为交卷时间 |
| 8 | 已入册的题在下一轮答题中再收藏 | 收藏夹仍有该题，`in_book` 不回退 |
| 9 | 答题中收藏后又取消，再交卷 | 收藏夹无该题（`deleted = 1` 被入册 SQL 跳过） |
| 10 | 中途退出未交卷，次日进入同一轮答题卡 | 收藏仍显示；收藏夹仍不可见 |
| 11 | 移出错题本后再判错 | 错题本重新出现（`deleted` 复活），行数不变 |
| 12 | 批量移出 100 条 | `removedCount = 100`；101 条返回 `8101` |
| 13 | 用他人 recordId 调收藏 | `8112`（记录不存在或不属于当前用户） |
| 14 | 收藏不属于本轮题集的题 | `8107`（题目不存在或不属于本次练习） |
| 15 | 未登录调任一读接口 | `401` |
| 16 | 考试未交卷时调 `/answer/hsk/favorite` | 收藏写入成功，`inBook = false`；交卷后入册 |
| 17 | 练习答题卡 | 每题带 `favorite`，与收藏表一致 |
| 18 | 考试答题卡 | 每题带 `favorite`，与 `isTag` 互不影响 |
| 19 | 按 `levelCode=HSK7-9` 筛选 | 只回 7 级条目（`exam_paper.level = '7'` 写入时映射为 `HSK7-9`） |
| 20 | 错题本 / 收藏夹各 1000 条 | 分页稳定，`pageSize = 100` 时 P95 不劣化（批量装配题面，无 N+1） |

## 9.上线注意事项

1. 数据库 DDL：

```sql
-- TEST 先执行，PROD 上线前同批执行
ALTER TABLE question_favorite
    ADD COLUMN in_book tinyint NOT NULL DEFAULT 1
    COMMENT '是否已进收藏夹：0=答题中暂存，1=交卷后入册' AFTER deleted;

ALTER TABLE question_favorite
    ADD KEY idx_user_book_time (user_id, in_book, deleted, updated_time);
```

2. PROD 建表：`question_favorite` / `question_wrong` 在 PROD **尚未建表**，须与 DDL 同批补建（结构对齐 TEST），否则功能整段不可用（写入被吞异常，用户无感但无数据）
3. 存量数据：`in_book` 默认 1，现有 74 条 CSCA 收藏（TEST 实测）无需回填；HSK 无存量
4. 回归范围：CSCA 收藏 / 错题本接口必须回归（同表共用，新增列与索引不能影响既有列表）；列表查询若漏 `in_book = 1` 会把暂存曝光，必须有测试用例覆盖
5. 收藏数量上限若最终确定数值，需新增专用错误码并同步前端提示文案（暂用 `8101` 带 detail）
6. 回滚方案：接口下线即可；`in_book` 列可保留（默认 1 对旧逻辑无副作用），不建议回滚时删列
7. 监控：错题 / 入册写入失败只记日志，需配 error 日志告警（否则 PROD 未建表期间无人发现）
8. 代码改动范围（供排期）：
   - 实体 / Mapper：`QuestionFavorite` 加 `inBook` 字段；新增 HSK 侧的错题 / 收藏 Mapper（批量 UPSERT、分页查询、软删、批量软删）
   - 写入器：练习客观两个 Finalizer、主观 `SubjectivePracticeServiceImpl`、考试 `ExamRecordServiceImpl` / `AsyncGradingServiceImpl` 各接一次，写入器独立成 Bean
   - DTO：`AnswerCardQuestion`、`AnswerCardDetailDTO.QuestionStatus` 各加 `favorite`
   - 控制器：practice-service 新增 `/hsk/wrong-book`、`/hsk/favorites` 两组端点；exam-service 在 `ExamAnswerController` 加 `/hsk/favorite`
   - CSCA 现有接口不改（同表共用，新增列有默认值）

## 10.待确认事项

| # | 事项 | 暂定方案 | 需要确认人 |
|---|---|---|---|
| 1 | 主观题（写作 / 翻译 / 口语）是否也进错题本 | 暂不进（无「对错」，只有分数） | 产品 |
| 2 | HSKK 口语的 `level_code` 具体写法 | 暂按表注释 `HSKK PRIMARY` / `HSKK INTERMEDIATE` / `HSKK ADVANCED` | 产品 / 前端 |
| 3 | 中途退出未交卷的暂存收藏，是否在「放弃练习」时也转正 | 暂不转正（只认交卷） | 产品 |
| 4 | 收藏数量上限 | 暂定 2000 条，超出暂用 `8101` 带 detail 提示 | 产品 |
| 5 | 是否需要「错题重做」接口（CSCA 有 `POST /csca/wrong-book/{questionId}/answer`） | 本期不做，先只做查看 / 移出 | 产品 |
| 6 | 错题本 / 收藏夹是否需要跨版本（HSK2.0 / HSK3.0）分开筛选 | 暂不区分，`level_code` 已能区分等级；版本不落库 | 产品 |
| 7 | 考试侧错题收录是否包含「考试中未作答」 | 与练习一致：不计入 | 产品 |
