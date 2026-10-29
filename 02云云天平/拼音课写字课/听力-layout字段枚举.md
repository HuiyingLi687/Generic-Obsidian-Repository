# 听力 `layout` 字段枚举说明（测试库实测）

> **2026-09-28 编制** · 数据源：测试库 `8.138.185.11:3306` / `xuexitest` / 表 `question`
> 口径来源：库内 DDL 注释 + `practice-service` listening 模块代码 + 实测数据统计

---

## 一、字段定位

| 项 | 内容 |
| --- | --- |
| 所在表 | `question`（公共题库） |
| 列名 | `layout` |
| 类型 | `varchar(32)`，允许 NULL |
| 库内注释（原文） | `题型\r\n听力：(imageJudge/textJudge/imageChoice/imageMatch/textChoice/textChoice_shareAudio/passageGroup)` |
| 语义 | **客户端布局编码**，决定答题页怎样渲染 |
| 服务端行为 | 不按 `layout` 拆分结构，**原样透传**（见 `ListeningQuestionResponse` 类注释） |

使用方（`practice-service` listening 模块）：

- `ListeningQuestionResponse#layout` — 练习答题页逐题下发
- `ListeningQuestionReportResponse#layout` — 单题回顾
- `ListeningReportRow#layout` — 报告题号矩阵（提交时已固化进 `practice_answer.question_snapshot`）

**结论：目前全库只有听力模块使用该字段。** 实测 4725 条非空 `layout` 全部落在 `section_mapping = 'SEC_LISTEN'`。

---

## 二、枚举取值总表（核心）

| # | `layout` | 派生题型名 | 渲染形态 | 需共享音频 | 实测条数 | 占非空比 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `imageJudge` | 看图判断题 | 图片 + `√`/`×` | 否 | 295 | 6.24% |
| 2 | `textJudge` | 文字判断题 | 文本陈述 + `√`/`×` | 否 | 400 | 8.47% |
| 3 | `imageChoice` | 看图选择题 | 图片选项，单选 | 否 | 95 | 2.01% |
| 4 | `imageMatch` | 图片匹配题 | 图片与音频匹配 | 否 | 295 | 6.24% |
| 5 | `textChoice` | 细节选择题 | 文本选项，单选 | 否 | 2425 | 51.32% |
| 6 | `textChoice_shareAudio` | 细节选择题 | 文本选项，单选；**音频由题组共享** | **是** | 815 | 17.25% |
| 7 | `passageGroup` | 听短文选择 | 短文题组，整组共用一段材料音频 | **是** | 400 | 8.47% |
| | **合计** | | | | **4725** | **100%** |

> 注意两点易错处：
> 1. **`textChoice` 与 `textChoice_shareAudio` 的题型名相同**（都是"细节选择题"），差别只在音频来源是不是题组共享。
> 2. `ListeningReportRow` 的字段注释只列了 6 个值，**漏了 `textChoice_shareAudio`**，以代码 `switch` 为准。

---

## 三、`layout` → `questionType` 固定映射

两处实现完全对称，修改时必须同步（否则报告与答题页题型名会不一致）：

- `ListeningSubmissionFinalizer#deriveQuestionType`（提交时固化）
- `ListeningReportServiceImpl#deriveQuestionType`（旧快照兜底）

```java
switch (layout) {
    case "imageJudge"           -> "看图判断题";
    case "textJudge"            -> "文字判断题";
    case "imageChoice"          -> "看图选择题";
    case "imageMatch"           -> "图片匹配题";
    case "textChoice"           -> "细节选择题";
    case "textChoice_shareAudio"-> "细节选择题";
    case "passageGroup"         -> "听短文选择";
    default                     -> null;      // 含 NULL
}
```

---

## 四、`variant` 派生规则（库内无此列）

`question` 表**没有** `variant` 列，`variant` 是运行期派生的，且两条路径口径不同：

| 路径 | 来源 | 规则 |
| --- | --- | --- |
| 提交固化（`ListeningSubmissionFinalizer#deriveVariant`） | `hsk_level` + `parts_config` | 仅 `textChoice` / `textChoice_shareAudio` / `passageGroup` 有值；`hskLevel ≤ 3` → `short`，`≤ 5` → `long`，part 3 → `interview`，否则 `long` |
| 答题页下发（`ListeningRecordServiceImpl`） | 命中的 `question_shared_audio.material_code` | 直接取素材码 |

`question_shared_audio.material_code` 实测取值：`PASSAGE`(148)、`INTERVIEW`(27)、`LONG_DIALOGUE`(9)、空串(5)。

> **口径风险**：同一道题的 `variant` 在「答题页」与「报告」可能一个是 `LONG_DIALOGUE`、一个是 `long`。如需统一，需明确以哪一侧为准。

---

## 五、与其他字段的关系（实测）

### 5.1 `layout` 与 `type_id_mapping` 是**多对多**，不能互推

| `type_id_mapping` | 对应 `layout` |
| --- | --- |
| `listening_judge`（听力:判断） | `imageJudge`(295) / `textJudge`(400) |
| `listening_single`（听力:单选） | `textChoice`(2025) / `textChoice_shareAudio`(615) / `passageGroup`(400) / `imageChoice`(95) |
| `listening_img_match`（听力:图片匹配） | `imageMatch`(295) / `textChoice`(200) |
| `listening_passage`（听力:短文理解） | `textChoice`(200) / `textChoice_shareAudio`(200) |

**同一个 `listening_single` 会映射出 4 种 `layout`**——判断渲染方式只能读 `layout`，不要从 `type_id_mapping` 反推。

### 5.2 选项内容形态（`option_content`）

| `layout` | 选项值样例 |
| --- | --- |
| `imageJudge` / `textJudge` | `{"A": "√", "B": "×"}` |
| `imageChoice` / `imageMatch` | `{"A": "<img src=\"http://.../xxx.jpeg\" style=\"max-width:100%;\">", ...}` |
| `textChoice` | `{"A": "<p>tā de</p><p>他的</p>", ...}`（拼音 + 汉字双行）或纯文本 |
| `textChoice_shareAudio` | `{"A": "考试", "B": "写作业", "C": "踢足球", "D": "看球赛"}` |
| `passageGroup` | `{"A": "国王", "B": "商人", "C": "大臣", "D": "珠宝匠"}` |

### 5.3 音频字段

| 下发字段 | 来源 | 说明 |
| --- | --- | --- |
| `audio_url` | `question.audio_url` | 逐题音频 |
| `share_audio_url` | `question_shared_audio.audio_url` | 仅 `textChoice_shareAudio` / `passageGroup`，按 `group_id` + 题号区间（`start_number`~`end_number`）命中 |

实测听力行 **约 50% 的 `audio_url` 为空**，按等级看各等级接近一半，属于题组共享音频的正常形态，不是数据缺陷。

---

## 六、`layout` × HSK 等级（结构关系）

> ⚠️ 绝对条数不可直接用：`practice_paper_structure` 对同一份试卷按「部分」拆成多行，`join` 会放大计数。下表只反映**哪些等级会出现哪些布局**。

| HSK 等级 | 出现的 `layout` |
| --- | --- |
| HSK1 | `imageJudge`、`imageChoice`、`imageMatch`、`textChoice` |
| HSK2 | `imageJudge`、`textChoice` |
| HSK3 | `imageMatch`、`textJudge`、`textChoice` |
| HSK4 | `textJudge`、`textChoice`、`textChoice_shareAudio` |
| HSK5 | `textChoice`、`textChoice_shareAudio` |
| HSK6 | `textChoice`、`textChoice_shareAudio`、`passageGroup` |

规律：低等级偏图片类布局（`image*`），高等级偏文本 + 共享音频（`textChoice_shareAudio` / `passageGroup`）。

---

## 七、`layout` 为 NULL 的行（921 条，占听力行 16.3%）

| `type_id_mapping` | 条数 | 说明 |
| --- | --- | --- |
| `example_question` | 330 | 例题行（`number='0'`），按设计不带布局 |
| `listening_detail_choice` | 190 | 未回填 |
| `listening_dialog_choice` | 114 | 未回填 |
| `listening_img_match` | 99 | 未回填 |
| `listening_single` | 45 | 未回填 |
| `listening_judge` | 45 | 未回填 |
| `listening_pic_choice` | 36 | 未回填 |
| `listening_choice_fill` | 30 | 未回填 |
| `listening_passage` | 20 | 未回填 |
| `listening_reading_passage` | 12 | 未回填 |

除例题外，其余 591 条集中在 HSK1 的部分题型上，属**待回填**状态。

---

## 八、基数总览

| 指标 | 数值 |
| --- | --- |
| `question` 全表行数（`deleted=0`） | 13624 |
| 其中 `layout` 非空 | 4725（全部为听力） |
| 听力行（`section_mapping='SEC_LISTEN'`） | 5646 |
| 含听力题目的试卷数 | 137 |

---

## 九、核对用 SQL（DBeaver 可直接执行）

```sql
-- 1. 字段注释（权威枚举来源）
SHOW FULL COLUMNS FROM question LIKE 'layout';

-- 2. 听力 layout 分布
SELECT layout, COUNT(*) AS cnt
FROM question
WHERE deleted = 0 AND section_mapping = 'SEC_LISTEN'
GROUP BY layout
ORDER BY cnt DESC;

-- 3. layout × type_id_mapping（验证不可互推）
SELECT layout, type_id_mapping, type_id, COUNT(*)
FROM question
WHERE deleted = 0 AND section_mapping = 'SEC_LISTEN'
GROUP BY layout, type_id_mapping, type_id
ORDER BY 1, 4 DESC;

-- 4. layout × HSK 等级（注意 join 会按"部分"放大）
SELECT s.hsk_level, q.layout, COUNT(DISTINCT q.id) AS cnt
FROM question q
JOIN practice_paper_structure s ON s.paper_id = q.paper_id
WHERE q.deleted = 0 AND s.deleted = 0
  AND q.section_mapping = 'SEC_LISTEN' AND q.layout IS NOT NULL
GROUP BY s.hsk_level, q.layout
ORDER BY 1, cnt DESC;

-- 5. 共享音频素材码
SELECT material_code, COUNT(*), MIN(start_number), MAX(end_number)
FROM question_shared_audio
WHERE deleted = 0
GROUP BY material_code ORDER BY 2 DESC;
```

---

## 十、维护提示

1. 新增听力布局时，**三处必须同步**：DDL 注释、`ListeningSubmissionFinalizer` 与 `ListeningReportServiceImpl` 的 `switch`、本表。
2. `needsSharedAudioByLayout()` 里 `textChoice_shareAudio` / `passageGroup` 是**硬编码字符串**，新增共享音频布局需改该方法（`ListeningSubmissionFinalizer` 与 `ListeningRecordServiceImpl` 各一份）。
3. 报告中 `layout` 取自提交时固化的快照，**改历史题目的 `layout` 不会影响已提交报告**。
