# 题目「考试布局」字段 — 设计方案

> 版本 **v3.8** · 2026-10-28
> **本版只描述考试侧设计**：字段定义、值域、映射、下发与回填。
> 数据源：TEST 库 `xuexitest` 实测，口径 `question.deleted=0 AND exam_paper.deleted=0`；所有题量为实测值。
---

## 0. 结论速览

| 项 | 结论 |
|---|---|
| 字段 | **新增 `question.exam_layout`** `varchar(32) NULL` |
| 值域 | **8 个枚举值**，覆盖 HSK 44 个题型编码（11,620 题）+ CSCA 8 个题型（1,904 题），零落空 |
| 语义 | **只描述"这道题渲染成什么样"**：一个值 = 一个作答控件 |
| 不包含 | 音频来源（听力整卷一段）、变体（short/long/interview）、材料来源派生字段、作答模式（SINGLE/MATCH/ORDER）、是否计分、**内容是文字还是图片** |
| 改动面 | 1 列 DDL + `exam-service` 实体/DTO/3 处 builder + 一次回填 |

**一句话：它是一个"控件枚举"，与业务题型编码解耦，前端拿到就能选渲染分支，不需要再判断内容特征。**

---

## 1. 字段定义

| 项 | 值 |
|---|---|
| 列名 | **`exam_layout`** |
| 类型 | `varchar(32) NULL`（最长值 `passageChoice` = 13 字符，余量充足） |
| 表 | `question`（题级） |
| 注释 | `考试布局（渲染用）：choice/imageMatch/multiChoice/judge/passageChoice/order/input/record` |

**命名**：`exam_` 前缀标归属（考试域），后缀 `_layout` 标用途（渲染布局）。备选 `render_style` 语义也准，但项目里"布局"已是对外说法，沿用更省沟通成本。

**取值规则（写进代码注释）**：
1. 值必须是 §2 的 8 个之一，落库前校验，**不接受自由文本**；
2. 空值 = 尚未回填，前端按 `typeIdMapping` 走兼容分支；
3. 后端**不根据 `type_id_mapping` 自动派生**，避免两套逻辑各自演化。

---

## 2. 值域（8 个）

### 2.0 先约定：内容存在哪几个字段

下面两张表的 `表.字段` 都是**实际存储位置**（TEST 全量实测，不是推测）。题目内容只会落在这 6 个字段：

| 字段 | 类型 | 装什么 |
|---|---|---|
| `question.content` | text | 题干（CSCA 材料题、部分 HSK 阅读把题干放这里） |
| `question.passage` | text | 主要题面区：判断句、待排项、打散的词、写作材料/图片、外文原文 |
| `question.option_content` | **json** | 本题选项，键为 `A`/`B`/`C`/`D`，值可能是文字或 `<img>` |
| `question.answer` | text | 参考答案（`CAB`、整句、单字；写作类填「略」） |
| `question_group.passage` | text | 题组级材料（阅读长文、段落文字/拼图、带空标记的段落） |
| `question_group.option_content` | **json** | 题组级选项池：`reading_sent_fill` 的句池、`reading_para_sort` 的字母池 |

关联方式：`question.group_id` → `question_group.id`，为空即"本题无题组"。


### 2.1 点选类（5 个）

| 值 | 中文 | 控件 | 题目（表.字段） | 选项（表.字段） | 材料（表.字段） | HSK | CSCA |
|---|---|---|---|---|---|---|---:|
| `choice` | 单选（文字/图片/字母） | 单选按钮（3~7 个按钮选一） | 见下表「`choice` 的 4 种来源形态」 | 同左 | 同左 | 8,330 | 1,759 |
| `imageMatch` | 图片匹配 | 图池取一 | `question.passage`（345/920，其余靠音频） | `question.option_content`（图池） | — | 920 | 0 |
| `multiChoice` | 多选 | 复选框 | `question.passage`（35/35） | `question.option_content`（A-D 文字） | — | 0 | 35 |
| `judge` | 判断（文字/看图） | √ / ×（可 3 项） | `question.passage`（1,150/1,150：判断句或 `<img>`） | `question.option_content`（键数即选项数） | — | 1,150 | 0 |
| `passageChoice` | 材料题 | 单选（分栏版式） | `question.content`（56/68，阅读题干）<br>听力 12 条无文字题面（靠音频） | `question.option_content`（68/68，本题文字选项） | `question_group.passage`（56/68 阅读长文；听力 12 条是音频） | 68 | 110 |

#### `choice` 的 4 种来源形态（一个值，4 处取数位置）

| 形态 | 题量 | 题面在哪 | 选项在哪 |
|---|---:|---|---|
| 普通单选（HSK 8,084 / CSCA 1,609） | 9,693 | `question.passage` 2,672 / `question.content` 977；其余为空（听力题面靠整卷音频） | `question.option_content`（值可能是文字或 `<img>`） |
| 选句填空 `reading_sent_fill` | 231 | **`question_group.passage`** | **`question_group.option_content`** |
| 段落排序 `reading_para_sort` | 15 | **`question_group.passage`** | **`question_group.option_content`** |
| 选词成段（CSCA） | 150 | **`question_group.passage`** | `question.option_content` |


### 2.2 排序与作答（3 个）

| 值 | 中文 | 控件 | 题目（表.字段） | 作答（表.字段） | 材料（表.字段） | HSK 题量 |
|---|---|---|---|---|---|---:|
| `order` | 点选排序（句子/词） | 按序点选 | `question.passage`（749/749）<br>**两种形态**：`<p>A …</p>` 多句待排 220 条／空格分隔的词 529 条 | `question.answer`：句子排序是字母序列（`BAC`）；连词成句是整句（`他学习特别努力.`） | — | 749 |
| `input` | 文本作答（字/句/文/译） | 输入框（单字限 1 字，其余多行） | 见下表「`input` 的 5 种来源形态」 | 同左 | 同左 | 396 |
| `record` | 录音作答（口语/口译） | 录音 + 倒计时 | `question.passage`（7/7）<br>朗读、听后回答、话题作答的题面；口译是外文原文（看文字口头译） | 音频（考试端上传，不落本题表） | — | 7 |

#### `input` 的 5 种来源形态（一个值，5 处取数位置）

| 形态 | 题量 | 题面在哪 | 参考作答 |
|---|---:|---|---|
| 写单字| 130 | `question.passage`，**130/130 全部非空、0 含图**（句子里带拼音提示：`看不见(tài)阳`） | `answer` = **单个汉字**（`太`），恒为单字 |
| 写句子 | 130 | `question.passage`，**130/130 含 `<img>`**（看图写话） | 短句，最长 21 字 |
| 简答 | 14 | `question.content`（问题）；材料在 `question_group.passage` | 5~10 字 |
| 成篇写作 | 71 | `question.passage`（题目要求，部分含图）；`question.content` 20/71 | `answer` **是占位「略」**（69/71），不能用作评分依据 |
| 笔译 | 2 | `question.passage` = 外文原文 | `answer` **是占位「(略)」** |


### 2.3 例题怎么处理

`example_question` **不是布局值，是题型**（935 题，横跨听力/阅读/书写）。它的 `exam_layout` 取**同卷同一题号区间**（例题的 `question_group` 就是区间串，如 `1-5`）内正题的众数，实测 935 条全部可定位（0 条落空），分布：

| `exam_layout` | 题量 |
|---|---:|
| `choice` | 450 |
| `judge` | 240 |
| `imageMatch` | 115 |
| `order` | 81 |
| `input` | 49 |

---

## 3. 全量映射（44 HSK 编码 + 8 CSCA 题型）

### 3.1 HSK

| # | `type_id_mapping` | 题量 | `exam_layout` | 判定依据 |
|--:|---|---:|---|---|
| 1 | `listening_single` | 3,145 | `choice` | 选项文字或图，同一个控件（原文字/图两值已合并） |
| 2 | `listening_judge` | 710 | `judge` | 材料可为文字句或图；2~3 项判断 |
| 3 | `listening_img_match` | 575 | `imageMatch` | 选项全是图（575/575） |
| 4 | `listening_passage` | 400 | `choice` | — |
| 5 | `listening_detail_choice` | 177 | `choice` | — |
| 6 | `listening_dialog_choice` | 102 | `choice` | — |
| 7 | `listening_choice_fill` | 30 | `choice` | — |
| 8 | `listening_pic_choice` | 30 | `choice` | 选项全是图 |
| 9 | `listening_reading_passage` | 12 | `passageChoice` | 材料在题组 |
| 10 | `reading_single` | 1,830 | `choice` | — |
| 11 | `reading_word_fill` | 925 | `choice` | — |
| 12 | `reading_match` | 700 | `choice`（500）/ `imageMatch`（200） | 选项含 `<img>` |
| 13 | `reading_sent_fill` | 231 | `choice` | 选一个句池项，就是单选；题面与句池都在题组 |
| 14 | `reading_wrong_sentence` | 200 | `choice` | 4 句选一 |
| 15 | `reading_sort` | 200 | `order` | 项是句子（`<p>` 包裹），答案是字母序列 |
| 16 | `reading_judge` | 200 | `judge` | 材料可为文字句或图（原文字/图两值已合并） |
| 17 | `reading_detail_choice` | 105 | `choice` | — |
| 18 | `reading_cloze` | 90 | `choice` | 材料随题 |
| 19 | `reading_sent_match` | 75 | `choice` | — |
| 20 | `reading_passage_choice` | 56 | `passageChoice` | 材料在题组 |
| 21 | `reading_img_match` | 30 | `imageMatch` | 选项全是图 |
| 22 | `reading_para_sort` | 15 | `choice` | 逐题选一个字母，就是单选；材料与字母池都在题组 |
| 23 | `reading_short_answer` | 14 | `input` | 无选项，答案自由文本 |
| 24 | `reading_fill` | 10 | `choice` | — |
| 25 | `write_complete_sent` | 468 | `order` | 项是词（空格分隔），答案整句 |
| 26 | `write_make_sent` | 100 | `input` | 看图写句，答案自由文本 |
| 27 | `write_character_writing` | 100 | `input` | 写单字，`answer` 恒为单个汉字（限 1 字输入框） |
| 28 | `write_short_essay` | 42 | `input` | 成篇写作，答案自由文本 |
| 29 | `write_summary` | 20 | `input` | 缩写，答案自由文本 |
| 30 | `handwriting_char_write` | 30 | `input` | 写单字，`answer` 恒为单个汉字（限 1 字输入框） |
| 31 | `handwriting_comp_choice` | 15 | `choice` | 选项是部件图 |
| 32 | `handwriting_pic_sentence` | 15 | `input` | 看图写句 |
| 33 | `writing_pic_sentence` | 15 | `input` | 看图写句 |
| 34 | `writing_topic_essay` | 3 | `input` | 话题作文 |
| 35 | `writing_short_essay` | 3 | `input` | 短文写作 |
| 36 | `writing_practical` | 1 | `input` | 应用文 |
| 37 | `writing_pic_write` | 1 | `input` | 看图写作 |
| 38 | `writing_chart_analysis` | 1 | `input` | 图表分析 |
| 39 | `speaking_read_aloud` | 1 | `record` | — |
| 40 | `speaking_listen_answer` | 3 | `record` | — |
| 41 | `speaking_opinion` | 1 | `record` | — |
| 42 | `translation_written` | 2 | `input` | 外文原文在 `passage`，答案自由文本 |
| 43 | `translation_oral` | 2 | `record` | 口译也是录音提交，控件与口语题一致 |
| 44 | `example_question` | 935 | 见 §2.3（5 个值） | 同卷同题号区间众数 |


### 3.2 CSCA（8 个题型）

| 题型 | 题量 | `exam_layout` | 依据 |
|---|---:|---|---|
| 单选 | 1,069 | `choice`（1,059）/ `passageChoice`（10） | `group_id` 非空 → 材料在组 |
| 补全语句 | 220 | `choice` | 一题一屏 |
| 选词填空 | 150 | `choice` | 一题一屏 |
| 选词成段 | 150 | `choice` | 题面是题组段落（带空标），逐空选一个词 = 单选 |
| 识解汉字 | 100 | `choice` | 一题一屏 |
| 阅读理解 | 100 | `passageChoice` | 材料在题组 |
| 辨析词语 | 80 | `choice` | 一题一屏 |
| 多选 | 35 | `multiChoice` | 答案 `A,D`，选项 4 项 |

按目标值汇总：`choice` **1,759** / `passageChoice` **110** / `multiChoice` **35**，合计 1,904，无漏项。

> CSCA「单选」的 1,069 条里，恰好 10 条有 `group_id`（材料在题组）、1,059 条 `passage` 自带材料，两者互斥、无交集 —— 这条判据可直接写进回填 SQL。


## 附：值域速查

```
点选类（5）  choice / imageMatch / multiChoice / judge / passageChoice
排序与作答（3）  order / input / record
```

> 8 个值 · 覆盖 13,524 题 · 零落空；值只管渲染，不含音频、不含变体、不含计分、不含"文字还是图"。
