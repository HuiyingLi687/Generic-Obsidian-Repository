# HSK 题型清单（数据库实测）

> 数据源：TEST 库 `xuexitest`，`2026-10-27` 实测。
> 统计口径：`question.deleted = 0` 且 `exam_paper.deleted = 0`；HSK 指 `exam_paper.exam_type = 1`。
> 全文题量均为 TEST 环境实测值，PROD 未统计。

---

## 0. 一句话结论

题型编码存在 `question.type_id_mapping`（varchar(30)），**全库 44 个有效取值 + 1 类空值**；字典**不在数据库**里，唯一真源是代码枚举 `common/src/main/java/com/hsktreasure/common/enums/QuestionType.java`（45 个常量，其中 `listening_dialog` 未被任何题目使用）。

空值共 2104 条，**1904 条是 CSCA（正常）**，**200 条是 HSK 6 级阅读真题缺填** —— 后者已于 **2026-10-27 在 TEST 回填完毕（HSK 侧空值归零）**，PROD 100 条待执行，详见 §5.1。

另有一处**编码不规范**（非空值）：HSK2.0 L1 卷 `HSK1_H10902` 第 21–25 题把 `type_id` 写成了编码 `reading_judge`（应为 `阅读:判断`），已 TEST 修复，详见 §5.4。

---

## 1. 字段与关联关系

| 列 | 类型 | 说明 |
|---|---|---|
| `question.type_id` | varchar(32) | 原始题型中文名，来自 Excel「题型」列，如 `听力:单选`、`书写:完成句子` |
| `question.type_id_mapping` | varchar(30) | 枚举编码，如 `listening_single`；**本文统计的对象** |
| `question.section_mapping` | varchar(50) | 模块码：`SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` / `SEC_SPEAKING` / `SEC_TRANSLATION` |
| `question.subject_type_mapping` | varchar(32) | CSCA 专用学科码，HSK 不用 |

**`type_id_mapping → section_mapping` 是一一对应的**（实测 44 个编码无一对多），所以「模块」可以从编码前缀直接推出，不必查库。

---

## 2. 题型字典（按模块分组）

### 2.1 听力 `SEC_LISTEN`（10 个）

| 编码 | 中文名 | 题量 | 出现版本-等级 |
|---|---|---|---|
| `listening_single` | 听力:单选 | 3160 | 2.0 L1–L6 |
| `listening_judge` | 听力:判断 | 720 | 2.0 L1–L4；3.0 L7-9 |
| `listening_img_match` | 听力:图片匹配 | 575 | 2.0 L1–L3；3.0 L1–L3 |
| `listening_passage` | 听力:短文理解 | 420 | 2.0 L4 |
| `listening_detail_choice` | 听力:细节选择 | 177 | 3.0 L1、L3–L6 |
| `listening_dialog_choice` | 听力:对话选择 | 102 | 3.0 L2–L4 |
| `listening_pic_choice` | 听力:看图选择 | 30 | 3.0 L1、L2 |
| `listening_choice_fill` | 听力:选择/填空 | 30 | 3.0 L7-9 |
| `listening_reading_passage` | 听力:阅读理解 | 12 | 3.0 L6 |
| `listening_dialog` | 听力:对话理解 | **0** | **枚举有、库中无** |

> ⚠️ `listening_dialog`（HSK2.0 老口径「对话理解」）是唯一一个**零数据**的编码，删除前需确认没有客户端按它做过分支。

### 2.2 阅读 `SEC_READ`（15 个 + 例题，`example_question` 见 §2.6）

> `SEC_READ` 在库中共 16 个编码，多出的 1 个是跨模块的 `example_question`（402 条），单列在 §2.6。

| 编码 | 中文名 | 题量 | 出现版本-等级 |
|---|---|---|---|
| `reading_single` | 阅读:单选 | 1850 | 2.0 L3–L6 |
| `reading_word_fill` | 阅读:选词填空 | 935 | 2.0 L1–L5；3.0 L6 |
| `reading_match` | 阅读:匹配 | 700 | 2.0 L1–L3 |
| `reading_sort` | 阅读:排列顺序 | 210 | 2.0 L4 |
| `reading_judge` | 阅读:判断 | 200 | 2.0 L1、L2 |
| `reading_wrong_sentence` | 阅读:语病判断 | 200 | 2.0 L6 |
| `reading_detail_choice` | 阅读:细节选择 | 105 | 3.0 L1–L4 |
| `reading_cloze` | 阅读:完形填空 | 90 | 3.0 L1–L4 |
| `reading_sent_match` | 阅读:句子匹配 | 75 | 3.0 L1–L3 |
| `reading_passage_choice` | 阅读:文章选择 | 56 | 3.0 L5–L7-9 |
| `reading_sent_fill` | 阅读:选句填空 | 231 | 2.0 L6；3.0 L4、L6 |
| `reading_img_match` | 阅读:图片匹配 | 30 | 3.0 L1、L2 |
| `reading_para_sort` | 阅读:段落排序 | 15 | 3.0 L5、L7-9 |
| `reading_short_answer` | 阅读:文章简答 | 14 | 3.0 L7-9 |
| `reading_fill` | 阅读:阅读填空 | 10 | 3.0 L5 |

### 2.3 书写 `SEC_WRITE`（14 个）

| 编码 | 中文名 | 题量 | 出现版本-等级 |
|---|---|---|---|
| `write_complete_sent` | 书写:完成句子 | 478 | 2.0 L3–L5 |
| `write_make_sent` | 书写:造句 | 105 | 2.0 L4 |
| `write_character_writing` | 书写:写汉字 | 100 | 2.0 L3 |
| `write_short_essay` | 书写:写短文 | 42 | 2.0 L5 |
| `write_summary` | 书写:缩写 | 20 | 2.0 L6 |
| `handwriting_char_write` | 书写:汉字书写 | 30 | 3.0 L2、L3 |
| `handwriting_comp_choice` | 书写:汉字部件选择 | 15 | 3.0 L2 |
| `handwriting_pic_sentence` | 书写:看图用词造句 | 15 | 3.0 L3 |
| `writing_pic_sentence` | 写作:看图用词造句 | 15 | 3.0 L4 |
| `writing_short_essay` | 写作:短文写作 | 3 | 3.0 L4 |
| `writing_topic_essay` | 写作:话题作文 | 3 | 3.0 L5–L7-9 |
| `writing_pic_write` | 写作:看图写作 | 1 | 3.0 L5 |
| `writing_practical` | 写作:应用文写作 | 1 | 3.0 L6 |
| `writing_chart_analysis` | 写作:图表描述与分析 | 1 | 3.0 L7-9 |

> 🔴 **「书写」与「写作」是两个模块，不要合并**：`handwriting_*` 是 HSK3.0 L2–L3 的「书写」部分，`writing_*` 是 L4 起的「写作」部分。两者 `section_mapping` 都是 `SEC_WRITE`，但题型编码前缀不同。

### 2.4 口语 `SEC_SPEAKING`（3 个）· 仅 HSK3.0 L7-9

| 编码 | 中文名 | 题量 |
|---|---|---|
| `speaking_listen_answer` | 口语:听材料回答问题 | 3 |
| `speaking_read_aloud` | 口语:应用读说 | 1 |
| `speaking_opinion` | 口语:观点表达 | 1 |

### 2.5 翻译 `SEC_TRANSLATION`（2 个）· 仅 HSK3.0 L7-9

| 编码 | 中文名 | 题量 |
|---|---|---|
| `translation_written` | 翻译:笔译 | 2 |
| `translation_oral` | 翻译:口译 | 2 |

### 2.6 例题（1 个，跨模块）

| 编码 | 中文名 | 题量 | 模块分布 |
|---|---|---|---|
| `example_question` | 例题 | 935 | `SEC_LISTEN` 420 / `SEC_READ` 402 / `SEC_WRITE` 113 |

---

## 3. HSK 2.0 题型矩阵

| 题型 | L1 | L2 | L3 | L4 | L5 | L6 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| 例题 `example_question` | 200 | 200 | 220 | 200 | 21 | — |
| 听力:单选 `listening_single` | 200 | 300 | 400 | 300 | 945 | 1000 |
| 听力:判断 `listening_judge` | 100 | 200 | 200 | 200 | — | — |
| 听力:图片匹配 `listening_img_match` | 100 | 200 | 200 | — | — | — |
| 听力:短文理解 `listening_passage` | — | — | — | 400 | — | — |
| 阅读:匹配 `reading_match` | 200 | 300 | 200 | — | — | — |
| 阅读:单选 `reading_single` | — | — | 200 | 400 | 630 | 600 |
| 阅读:选词填空 `reading_word_fill` | 100 | 100 | 200 | 200 | 315 | — |
| 阅读:判断 `reading_judge` | 100 | 100 | — | — | — | — |
| 阅读:排列顺序 `reading_sort` | — | — | — | 200 | — | — |
| 阅读:语病判断 `reading_wrong_sentence` | — | — | — | — | — | 200 |
| 阅读:选句填空 `reading_sent_fill` | — | — | — | — | — | **200** |
| 书写:完成句子 `write_complete_sent` | — | — | 100 | 200 | 168 | — |
| 书写:写汉字 `write_character_writing` | — | — | 100 | — | — | — |
| 书写:造句 `write_make_sent` | — | — | — | 100 | — | — |
| 书写:写短文 `write_short_essay` | — | — | — | — | 42 | — |
| 书写:缩写 `write_summary` | — | — | — | — | — | 20 |

**卷数/题量**：L1–L6 各 20 套卷（L5 为 21 套），每卷 5 个题型组合、约 100–120 题。

---

## 4. HSK 3.0 题型矩阵

| 题型 | L1 | L2 | L3 | L4 | L5 | L6 | L7-9 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 例题 `example_question` | 24 | 27 | 31 | 12 | — | — | — |
| 听力:细节选择 `listening_detail_choice` | 30 | — | 30 | 54 | 35 | 28 | — |
| 听力:图片匹配 `listening_img_match` | 15 | 30 | 30 | — | — | — | — |
| 听力:看图选择 `listening_pic_choice` | 15 | 15 | — | — | — | — | — |
| 听力:对话选择 `listening_dialog_choice` | — | 30 | 30 | 42 | — | — | — |
| 听力:阅读理解 `listening_reading_passage` | — | — | — | — | — | 12 | — |
| 听力:选择/填空 `listening_choice_fill` | — | — | — | — | — | — | 30 |
| 听力:判断 `listening_judge` | — | — | — | — | — | — | 10 |
| 阅读:完形填空 `reading_cloze` | 15 | 15 | 30 | 30 | — | — | — |
| 阅读:细节选择 `reading_detail_choice` | 15 | 15 | 30 | 45 | — | — | — |
| 阅读:图片匹配 `reading_img_match` | 15 | 15 | — | — | — | — | — |
| 阅读:句子匹配 `reading_sent_match` | 15 | 30 | 30 | — | — | — | — |
| 阅读:选句填空 `reading_sent_fill` | — | — | — | 21 | — | 10 | — |
| 阅读:阅读填空 `reading_fill` | — | — | — | — | 10 | — | — |
| 阅读:段落排序 `reading_para_sort` | — | — | — | — | 10 | — | 5 |
| 阅读:文章选择 `reading_passage_choice` | — | — | — | — | 15 | 20 | 21 |
| 阅读:选词填空 `reading_word_fill` | — | — | — | — | — | 10 | — |
| 阅读:文章简答 `reading_short_answer` | — | — | — | — | — | — | 14 |
| 书写:汉字书写 `handwriting_char_write` | — | 15 | 15 | — | — | — | — |
| 书写:汉字部件选择 `handwriting_comp_choice` | — | 15 | — | — | — | — | — |
| 书写:看图用词造句 `handwriting_pic_sentence` | — | — | 15 | — | — | — | — |
| 写作:看图用词造句 `writing_pic_sentence` | — | — | — | 15 | — | — | — |
| 写作:短文写作 `writing_short_essay` | — | — | — | 3 | — | — | — |
| 写作:看图写作 `writing_pic_write` | — | — | — | — | 1 | — | — |
| 写作:话题作文 `writing_topic_essay` | — | — | — | — | 1 | 1 | 1 |
| 写作:应用文写作 `writing_practical` | — | — | — | — | — | 1 | — |
| 写作:图表描述与分析 `writing_chart_analysis` | — | — | — | — | — | — | 1 |
| 口语:听材料回答问题 `speaking_listen_answer` | — | — | — | — | — | — | 3 |
| 口语:应用读说 `speaking_read_aloud` | — | — | — | — | — | — | 1 |
| 口语:观点表达 `speaking_opinion` | — | — | — | — | — | — | 1 |
| 翻译:笔译 `translation_written` | — | — | — | — | — | — | 2 |
| 翻译:口译 `translation_oral` | — | — | — | — | — | — | 2 |


---

## 5. 与代码枚举的核对结果

| 核对项 | 结果 |
|---|---|
| 枚举常量总数 | 45 |
| 库中有效编码 | 44 |
| 库中有、枚举无 | **0**（全部合法） |
| 枚举有、库中无 | **1**：`listening_dialog`（听力:对话理解，0 条） |
| `type_id_mapping → section_mapping` | 44 个编码均为**一对一**，无冲突 |
| `type_id_mapping → type_id`（编码→中文名） | 44 个编码各自**唯一**中文名，无一对多 |

> 枚举第二参数（中文名）是 `HskExcelHandler` 的**映射键**，必须与 Excel 提取表 C 列逐字一致。改名会直接导致导入失败 —— 要改必须同时改枚举和导入模板。

---

## 6. 附：一句话速查

| 想查什么 | 去哪 |
|---|---|
| 编码 ↔ 中文名 | `QuestionType.java`（不是数据库） |
| 某等级需要哪些题型 | 本文 §3 / §4 矩阵 |
| 某题型属于哪个模块 | 编码前缀 + §2 分组（`listening_` / `reading_` / `write|writing|handwriting_` / `speaking_` / `translation_`） |
| 题库够不够 | §4 表格「卷数/题量」，3.0 的 L5/L6/L7-9 各只有 1 套 |
