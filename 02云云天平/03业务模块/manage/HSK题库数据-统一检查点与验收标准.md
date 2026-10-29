# HSK 题库数据 — 统一检查点与验收标准

> 适用范围：HSK 全等级（HSK2.0 一级~六级、HSK3.0 一级~六级、七~九级）题库数据的
> **Excel 交付件**与**入库结果**。不含 CSCA（另见 `CSCA题库数据-统一检查点与验收标准.md`）。
>
> 本文是**规范**，不是某批数据的核查记录。任何人拿到一批 HSK Excel，按本文逐条判定即可得出
> 可放行 / 不可放行的结论。
>
> 配套可执行实现：`tmp/hsk_audit.py`（只读，一条命令出验收报告）。

---

## 0. 一句话结论

HSK 数据有**三层**必须分开看，只查一层必然漏：

| 层 | 载体 | 谁决定这一层 | 典型缺陷 |
|---|---|---|---|
| L0 输入层 | Excel（16 列有效） | 出题/整理人员 | 分卷键写错、分组区间写错、题型不在枚举、分值不满 100 |
| L1 转换层 | `HskExcelHandler` + `QuestionExcelTemplate` | **代码，Excel 改不动** | 全角标点被转半角、第 17 列丢弃、不写 layout、非枚举题型丢 mapping |
| L2 结果层 | `question` / `question_group` / `exam_paper` | 前两层叠加结果 | 分组区间与实际题数不符、例题计分、选项为空 |

> 🔴 **验收只能验 L2**。L0 全对不代表 L2 对（L1 会破坏数据）；L2 全对也不代表 L0 好（可能被 L1 掩盖）。
> 正确顺序是：先验 L0 → 再验 L2 → 最后跑 L1 的三项后处理。

---

## 1. HSK 与 CSCA 的六处硬差异（不可混用标准）

两份标准看着像，规则不同。混用会直接判错。

| 维度 | HSK | CSCA |
|---|---|---|
| 列数 | **16 列**（有「等级*」，无「版本」） | 15 列（有「版本」「解析」，无「等级」） |
| 分卷键 | `source + version + level` | `source + version + languageVersion + subjectType` |
| **分值规则** | **每个模块满分恒 100**，卷面 = 100 × 模块数 | 整卷满分 100（40×2 + 8×2.5 / 80×1.25） |
| 分组机制 | **题目序号为空 = 一行展开 N 题**，用 `,` 和 `---` 拆 | 无此机制，一题一行 |
| 题型编码 | 中文名（`听力:单选`）→ 枚举 18 种 | 中文名（`单选`）→ 枚举 8 种 |
| 解析 `analysis` | **允许全空**（题库无解析是常态） | 必须 HTML 段落化 |

> 🔴 最容易错的两条：**分值按模块算而不是按整卷算**；**「题目序号」为空不是漏填，是分组题**。
> 把分组行当缺陷判掉，会把整个阅读/听力大题全部误报。

---

## 2. 数据契约

### 2.1 列定义（16 列，顺序固定）

Excel 模板类 `QuestionExcelEo` 上 16 个 `@ExcelProperty`，这就是**唯一权威列清单**：

| # | 列头 | EO 字段 | 必填 | 落库 | 说明 |
|---|---|---|---|---|---|
| 1 | `考试大纲*` | `version` | ✅ | `exam_paper.version` | `HSK2.0` / `HSK3.0` |
| 2 | `学科类型(HSK非必填)` | `subjectType` | ✕ | `exam_paper.subject_type` | **HSK 必须留空** |
| 3 | `题型*` | `typeId` | ✅ | `question.type_id` | 中文名，见 2.4 |
| 4 | `一级标题*` | `title1Number` | ✅ | `question.title1_number` | 模块序号 1/2/3…（整数） |
| 5 | `一级标题内容*` | `title1Text` | ✅ | → `section_mapping` | 只能 `听力`/`阅读`/`书写` |
| 6 | `部分标题*` | `section` | ✅ | `question.section` | 模块内第几部分，1..N |
| 7 | `题目分组(或者范围)*` | `questionGroup` | ✅ | `question.question_group` | **必须 `起-止`** |
| 8 | `部分标题内容` | `sectionTitle` | ✕ | `question.section_title` | 该部分的指导语 |
| 9 | `题目序号` | `number` | ✕ | `question.number` | **空 = 分组行** |
| 10 | `题目标题` | `content` | ✕ | `question.content` | 小题干；分组行用 `---` 拆 |
| 11 | `题目内容` | `passage` | ✕ | `question.passage` | 材料正文；分组行用 `---` 拆 |
| 12 | `题目选项` | `optionContent` | ✕ | `question.option_content` | `A:..,B:..` → JSON 对象 |
| 13 | `答案*` | `answer` | ✅ | `question.answer` | 选择题为选项键；分组行用 `,` 拆 |
| 14 | `分值*` | `score` | ✅ | `question.score` | varchar；分组行用 `,` 拆 |
| 15 | `来源*` | `source` | ✅ | `exam_paper.source` | 卷唯一标识，≤40 字符 |
| 16 | `等级*` | `level` | ✅ | `exam_paper.level` | `1`~`6` 或 `7-9` |

> 🔴 **陷阱 1（第 17 列静默丢弃）**：实际交付件常带第 17 列「图片名称」。EO 只映射前 16 列，
> **该列的值一个都不会入数据库**。图片必须已用 `<img>` 内联在 `题目内容` / `题目选项` 里。
>
> 🔴 **陷阱 2（字段语义反直觉）**：`题目标题` → `content`，`题目内容` → `passage`。
> 命名与字段名相反，核对字段映射时不要按字面猜。
>
> 🔴 **陷阱 3（学科类型不是 HSK 字段）**：该列表头写着「HSK非必填」，HSK 数据应整列为空。
> 若填了值，会被当作 `subject_type` 存入卷，影响后续按学科筛选。

### 2.2 分卷键

```
paperKey = source + "_" + version + "_" + level
```

同一个键 → 同一张 `exam_paper`；**任一不同就新建一张卷**。

推论（验收时必查）：

- 一个 Excel 文件对应**一卷**，文件内 `来源` / `考试大纲` / `等级` 三列必须**全表一致**。
- 若同表内 `等级` 混填（前 40 行写 `6`、后 10 行写 `HSK6`），会被拆成两张卷，题量各缺一半。
- 跨文件若 `source + version + level` 完全相同，会被**合并到同一张卷**，导致题号冲突。

### 2.3 字段填充矩阵（题干落点）

题目序号为空（分组行）与有题号（单题行）走**两套完全不同的落库路径**：

| 行类型 | 判断 | `content` | `passage` | `option_content` | `answer` / `score` |
|---|---|---|---|---|---|
| 单题行 | 题目序号非空 | 常空 | 材料/题干 | 本题选项（JSON 对象） | 单值 |
| 分组行 | **题目序号为空** | 各行小题干，`---` 拆 | 材料正文（整段共用） | 各行选项，`---` 拆 | **`,` 拆，个数 = 区间长度** |

> 🔴 **分组行展开规则**：`题目分组 = 71-75` 的一行，会生成 **5 个 `question`**（题号 71~75）
> 外加 **1 条 `question_group`**。
>
> - `question_group.start_number` / `end_number` 取自区间字面值；
> - 子题 `question.number` = 区间内逐个赋值；
> - 子题 `answer` / `score` = 按位置取逗号分列的第 k 个。
>
> 🔴 **选项是否上提到分组**：若 `题目选项` 只有 1 段（不含 `---`），则整组共用，选项存在
> `question_group.option_content`，**子题 `option_content` 为空** —— 这是正常的，不是缺选项。

### 2.4 题型取值域

`题型*` 列写**中文名**，代码用 `QuestionType.getCodeByName()` 映射成 `type_id_mapping`。
**名字必须与枚举逐字一致（含全角/半角冒号）**，否则 mapping 为 `null`，该题在按题型筛选时不可见。

| 模块 | 中文名 | `type_id_mapping` |
|---|---|---|
| 听力 | `听力:判断` | `listening_judge` |
| 听力 | `听力:单选` | `listening_single` |
| 听力 | `听力:图片匹配` | `listening_img_match` |
| 听力 | `听力:对话理解` | `listening_dialog` |
| 听力 | `听力:短文理解` | `listening_passage` |
| 阅读 | `阅读:判断` | `reading_judge` |
| 阅读 | `阅读:单选` | `reading_single` |
| 阅读 | `阅读:匹配` | `reading_match` |
| 阅读 | `阅读:选词填空` | `reading_word_fill` |
| 阅读 | `阅读:排列顺序` | `reading_sort` |
| 阅读 | `阅读:完形填空` | `reading_cloze` |
| 阅读 | `阅读:语病判断` | `reading_wrong_sentence` |
| 书写 | `书写:完成句子` | `write_complete_sent` |
| 书写 | `书写:造句` | `write_make_sent` |
| 书写 | `书写:写汉字` | `write_character_writing` |
| 书写 | `书写:写短文` | `write_short_essay` |
| 书写 | `书写:缩写` | `write_summary` |
| 通用 | `例题` | `example_question` |

> 🔴 **枚举缺口（已知）**：HSK3.0 新增题型（如 `阅读:选句填空`、`听力:细节选择`、
> `阅读:段落排序`、`书写:汉字部件选择`、`口语:*`、`翻译:*`、`写作:*`、`handwriting_*`）
> **不在 `QuestionType` 枚举里**。这类题型入库后 `type_id_mapping` 为 `null`。
>
> 处置二选一：① 扩充 `QuestionType` 枚举后重新导入；② 导入后用映射表 SQL 回填。
> **在枚举补齐前，含未登记题型的卷不能判为「通过」。**

### 2.5 考试部分（一级标题内容 → `section_mapping`）

| `一级标题内容*` | `section_mapping` | 是否在 `ExamSection` 枚举 |
|---|---|---|
| `听力` | `SEC_LISTEN` | ✅ |
| `阅读` | `SEC_READ` | ✅ |
| `书写` | `SEC_WRITE` | ✅ |
| （无） | `SEC_SPEAKING` | ❌ 仅 HSK3.0 七~九级，靠后处理写入 |
| （无） | `SEC_TRANSLATION` | ❌ 仅 HSK3.0 七~九级，靠后处理写入 |

> 🔴🔴 **`SEC_SPEAK` 与 `SEC_SPEAKING` 不是同一个东西**：
> - `SEC_SPEAK` = **HSKK 口语等级**（初/中/高 → level 1/2/3），出现在
>   `practice_module_level_config` 与口语卷侧；
> - `SEC_SPEAKING` = **HSK3.0 七~九级口语部分**，出现在 `question.section_mapping`。
>
> 两者混填会导致口语模块取不到题 / 取到错题，且不会报错，只会「页面空了」。
>
> 🔴 `ExamSection.fromDescription()` 只认三个中文名。写「写作」而不是「书写」、
> 写「听」而不是「听力」，都会返回 `null`，随后 `.getCode()` 直接 NPE，整份 Excel 导入失败。

### 2.6 分值规则（HSK 核心）

> **每个考试部分（模块）满分恒为 100 分，模块内按计分题数均分。**
> 卷面满分 = 100 × 该卷模块数。

| 大纲 | 等级 | 模块构成 | 卷面满分 |
|---|---|---|---|
| HSK2.0 | 1、2 | 听力 + 阅读 | **200** |
| HSK2.0 | 3、4、5、6 | 听力 + 阅读 + 书写 | **300** |
| HSK3.0 | 1 | 听力 + 阅读 | **200** |
| HSK3.0 | 2、3、4、5、6 | 听力 + 阅读 + 书写 | **300** |
| HSK3.0 | 7-9 | 听力 + 阅读 + 书写 + 翻译 + 口语 | **500** |

单题分值算法：

```
模块内计分题数 n（不含例题）
单题分值 = 100 / n
```

**除不尽时的唯一合规做法**：保留足够小数位（≥4 位），或在模块内按题序分配余数，
使该模块 `SUM(score)` **精确等于 100.00**。允许的舍入容差见 6.1（A 级 >1.0 阻断，B 级 0.01~1.0 提示）。

> 🔴 **禁止算法**：卷面满分 ÷ 总题数。这样算会让模块合计偏离 100，且不同模块题分相同，
> 丧失「模块各 100 分」的分数体系含义。
>
> 🔴 **例题不计分**：`type_id = 例题` 的行 `score` 必须为 `0`，不得参与任何合计。
> 例题题号固定为 `0`（多道例题共用 0 号，因此题号唯一性检查必须排除例题）。

### 2.7 官方题量（不含例题）

| 大纲 | L1 | L2 | L3 | L4 | L5 | L6 | 7-9 |
|---|---|---|---|---|---|---|---|
| HSK2.0 | 40 | 60 | 80 | 100 | 100 | 101 | — |
| HSK3.0 | 40 | 60 | 70 | 70 | 72 | 82 | 91 |

> 同等级可能有多套卷，但**题量必须一致**（差异即说明有题漏录或重复）。

### 2.8 `layout` 取值域

导入链路**不写** `layout`，必须由后处理按题型回填。HSK 的合法取值与 CSCA 不同：

| `type_id_mapping` | `layout` |
|---|---|
| 一般选择题（`*_single`、`*_judge`） | `textChoice` / `textJudge` |
| 听力共用音频 | `textChoice_shareAudio` |
| 图片匹配 | `imageMatch` |
| 图片判断 / 图片选择 | `imageJudge` / `imageChoice` |
| 材料类（阅读理解、短文理解、完形填空） | `passageGroup` |

---

## 3. 检查点（共 45 项，分五层编号）

每个检查点给出：**检查内容 / 检查方法 / 合格判据 / 级别 / 脚本**。
「脚本」列：`E` = `--dir` 在 Excel 侧自动判定；`D` = `--env` 在库侧自动判定；
`—` = 需人工或专项脚本。

### 3.1 L1 卷级（V-01 ~ V-13，13 项）

| 编号 | 检查内容 | 检查方法 | 合格判据 | 级别 | 脚本 |
|---|---|---|---|---|---|
| **V-01** | Excel 列定义 | 读第 1 行，比对 2.1 的 16 列 | 列名字面量与顺序完全一致 | A | E |
| **V-02** | 分卷键唯一 | `GROUP BY source,version,level HAVING COUNT(*)>1` | 无重复 | A | D |
| **V-03** | `version` 合法 | 枚举比对 | ∈ {`HSK2.0`,`HSK3.0`} | A | E+D |
| **V-04** | `level` 合法 | 枚举比对 | ∈ {`1`…`6`,`7-9`}，`7-9` 写成一个整体 | A | E+D |
| **V-05** | 学科类型留空 | `subject_type` 非空计数 | HSK 全为空 | B | D |
| **V-06** | `source` 无污染 | 长度 + 后缀匹配 | ≤40 字符，无 `-无图片名称列` / `_中文` / `_英文` 后缀 | A | D |
| **V-07** | 卷面合计 = 100 × 模块数 | 按卷 `SUM(score)` 与 2.6 满分表比对 | 差 ≤ 1.0 | A | E+D |
| **V-08** | 模块合计 = 100 | 按 `(卷, 模块)` 求和 | 差 ≤ 1.0（>0.01 记 B 级） | A | E+D |
| **V-09** | 卷内题号唯一且连续 | 题号集合 = 有题号行 ∪ 分组行展开区间 | 无重号、无缺号 | A | E+D |
| **V-10** | 分组区间 = 实际挂题数 | `end-start+1` 与 `COUNT(question)` 比对 | 相等 | A | D |
| **V-11** | `section_mapping` 在枚举内 | 见 2.5 | 五值之内 | A | E+D |
| **V-12** | 一卷一来源 | 同卷内 `source` 去重 | 仅 1 个值 | B | E+D |
| **V-13** | 题量 = 官方题量 | 见 2.7 | 相符（不含例题） | B | E |

> 🔴 **V-09 的题号集合必须包含分组行展开的区间**。分组行本身没有题号，但它的区间**占用了题号**；
> 只统计有题号的行，会判出大量「缺号」假阳性 —— 这是本篇最容易写错的一条。
>
> 🔴 **V-10 是最容易出真问题的一项**。分组行的 `题目分组` 若把「整个大题区间」写成第一组的区间
> （如第一部分 1-15 题，第一组也写 `1-15`，实际只挂 1-5 题），区间与挂载数就对不上。
> 后果：题卡分组展示错乱、按区间计算的进度条跳变。

### 3.2 L2 题级（Q-01 ~ Q-14，13 项）

| 编号 | 检查内容 | 检查方法 | 合格判据 | 级别 | 脚本 |
|---|---|---|---|---|---|
| **Q-01** | 必填列非空 | 10 个必填列逐行判空 | 无空值 | A | E |
| **Q-02** | 题型命中枚举 | 逐行比对 2.4 的 18 个中文名 | 全部命中 | A | E |
| **Q-03** | `type_id_mapping` 已回填 | `mapping IS NULL` 计数 | 0 条 | A | D |
| **Q-04** | `type_id` 与 mapping 一一对应 | 按 `type_id` 统计 mapping 去重数 | 同名题型只有一个 mapping | A | D |
| **Q-05** | `option_content` 是合法 JSON | `JSON_VALID()=0` 计数 | 0 条 | A | D |
| **Q-06** | 客观题选项数 ∈ 2~6 | 按客观题型统计 `JSON_LENGTH` | 全部落区间 | B | D |
| **Q-07** | 选择题答案命中选项键 | Excel 侧比对选项键；库侧 `JSON_CONTAINS_PATH` | 全部命中 | A | E+D |
| **Q-08** | 选项键连续 | 键序列 = `A,B,C…` | 连续无跳号 | A | E |
| **Q-09** | 答案格式合法 | 选择题全字母且无重复键；书写题为文本 | 相符 | A | E |
| **Q-10** | 题干非空 | 按 `layout` 取 `content`/`passage`/`section_title` | 至少一个非空 | A | D |
| **Q-11** | 听力题已挂分组 | 听力 5 种题型 `group_id` 非空 | 全部非空 | A | D |
| **Q-12** | 子题题号落在分组区间内 | `number` 与 `start_number`/`end_number` 比对 | 全部落区间 | A | D |
| **Q-13** | 例题题号为 `0` 且分值 `0` | 例题行逐条比对 | 全部为 0 | B | E+D |
| **Q-14** | 非例题分值 > 0 | `score+0 <= 0` 计数 | 0 条 | A | D |

> 🔴 **Q-06 / Q-07 必须限定客观题型**。书写题与例题本来就没有选项，`{}` 是正常值；
> 把书写题纳入选项检查会一次误报上千条。
>
> 🔴 **Q-11 的判定依赖题型枚举**。若 `type_id_mapping` 为 `null`（Q-03 不合格），
> 该题不会被听力分组逻辑捕获，Q-11 也因此无法判定 —— **两个检查点有依赖关系，Q-03 必须先过**。
>
> ⚠️ **听力子题的 `answer`/`score` 现状是「保留」而不是「清空」**。
> 代码里 `HskExcelHandler.handleQuestions()` 对听力 5 种题型执行 `setScore(null)` / `setAnswer(null)`，
> 但随后的 `updateBatchById` 默认忽略 null 字段，**清空并未落库**。
> 因此「听力子题答案为空」不能作为合格判据，本表也不设此项。

### 3.3 L3 分组级（G-01 ~ G-05，5 项｜HSK 独有）

| 编号 | 检查内容 | 检查方法 | 合格判据 | 级别 | 脚本 |
|---|---|---|---|---|---|
| **G-01** | 分组区间格式 | 正则 `^\d+\s*[-~—]\s*\d+$` | 全部匹配 | A | E |
| **G-02** | 分组行 `答案` 个数 | 逗号拆分后计数 | = 区间长度 | A | E |
| **G-03** | 分组行 `分值` 个数 | 逗号拆分后计数 | = 区间长度 | A | E |
| **G-04** | 分组行 `---` 段数 | 按列拆段后计数 | 段数 = 1（整组共用）或 = 区间长度 | A | E |
| **G-05** | 分组区间无重叠 | 同卷内区间两两比较 | 不重叠 | A | E |

> 🔴 **G-01 对听力题是强制的**。`uploadHskListening` 里 `questionGroupKey.split("-")` 后
> 直接取 `number[1]`，**只写 `1`、不写区间会数组越界，整份导入失败**。
> 即：听力题**即使有题号**，`题目分组` 也必须写成 `起-止`。
>
> 🔴 **G-04 的判据是「1 或区间长度」**，不是「必须等于区间长度」。
> 单段表示整组共用（材料/选项上提到 `question_group`），多段表示逐题不同。

### 3.4 L4 文本级（T-01 ~ T-09，9 项）

| 编号 | 检查内容 | 检查方法 | 合格判据 | 级别 | 脚本 |
|---|---|---|---|---|---|
| **T-01** | `layout` 已回填 | 非空计数 | 全部非空 | C | D |
| **T-02** | `layout` 取值合法 | 见 2.8 | 7 值之内 | B | D |
| **T-03** | 公式可渲染 | 导出 `$…$` → KaTeX `strict:'error'` 真渲染 | 全部渲染成功 | B | — |
| **T-04** | 全角标点已还原 | 中文后紧跟 `,` `.` `?` `!` `;` 计数 | 0 条（或已登记整改） | B | E+D |
| **T-05** | HTML 标签闭合 | `<p>`/`<u>`/`<img>` 配对 | 全部闭合 | B | — |
| **T-06** | 音频引用可达 | `shareAudio` 题的分组有音频字段 | 全部非空 | A | — |
| **T-07** | 无占位符残留 | 检索 `TODO`/`待补`/`xxx`/`待定` | 0 条 | B | D |
| **T-08** | 编码无异常 | 检索替换字符 `U+FFFD` | 0 条 | A | D |
| **T-09** | 图片已内联 | `<img` 出现在 `passage`/`option_content` | 有图即内联；第 17 列存在时提示 | A | E |

> 🔴 **T-03 必须用 KaTeX 真渲染，不能用正则白名单**。命令名白名单会把 `\mid`、`\boldsymbol`、
> `\begin` 等合法命令误判为非法，同时放过真正的语法残缺。
>
> 🔴 **`analysis` 不设检查点**。HSK 题库不要求解析（与 CSCA 相反），全空是正常状态。
>
> 🔴 **T-04 看到「中文正文里全是英文标点」不要回去改 Excel** —— 源头在导入链路（§4 第 1 条）。
> 正确判定是「待还原」，不是「Excel 不合格」。

### 3.5 L5 一致性（C-01 ~ C-05，5 项）

| 编号 | 检查内容 | 检查方法 | 合格判据 | 级别 | 脚本 |
|---|---|---|---|---|---|
| **C-01** | 行数守恒 | Excel 计分题数 vs 库内题数 | 相等（例题另计） | A | E+D |
| **C-02** | 卷数守恒 | Excel 文件数 vs 新建卷数 | 相等 | A | — |
| **C-03** | 分值守恒 | Excel 模块合计 vs 库内模块合计 | 相等 | A | — |
| **C-04** | 分组守恒 | Excel 分组行数 vs `question_group` 行数 | 相等 | A | — |
| **C-05** | 双环境一致 | TEST 与 PROD 逐卷比对题数、模块合计 | 相等 | B | — |

> 🔴 **C-01~C-05 必须在同一批次导入前后各采集一次**，且必须两侧数据同时在场。
> 脚本输出两侧基线（`[Excel] 文件 n / 计分题 n` 与 `C-01 卷 n / 题 n`），据此人工核对。
>
> 🔴 **C-05 必须两个环境都查**。HSK 的 TEST / PROD 曾出现同卷题量不同、
> `section_mapping` 取值不同的情况，只查一个环境会得出相反结论。

## 4. 导入链路的六处有损行为（Excel 侧无解）

以下六条发生在「Excel 读取之后、落库之前」，**改 Excel 无法规避**，只能导入后处理或改代码。

| # | 行为 | 代码位置 | 后果 | 处置 |
|---|---|---|---|---|
| 1 | **全角标点强制转半角** | `QuestionExcelTemplate:77` → `PunctuationConvertUtil.convertObject()` | `，`→`,`、`。`→`.`、`…`→`.`、`—`→`-`、`“”`→`"`，中文正文全部英文化 | 导入后按字段还原 |
| 2 | 第 17 列「图片名称」丢弃 | `QuestionExcelEo` 只有 16 个 `@ExcelProperty` | 图片必须内联，否则丢失 | 出题时内联 |
| 3 | 不写 `layout` | `HskExcelHandler` 无 layout 赋值 | 前端按 layout 渲染的页面全空 | 后处理回填 |
| 4 | 选项解析只认半角 `:` `,` | `OptionParseUtil.KV_REGEX` | 用全角冒号写选项 → 解析为空对象 | 前置校验 + 修正 Excel |
| 5 | 非枚举题型 mapping 为 null | `QuestionType.getCodeByName()` 返回 null | 题型筛选、练习取题不可见 | 扩枚举或后处理回填 |
| 6 | 听力题 `score`/`answer` 置 null | `HskExcelHandler.handleQuestions()` | 听力题本身无分值无答案 | 按设计接受，计分走分组 |

> 🔴 **第 1 条是最容易被误判为「Excel 写错了」的一条**。看到中文正文里全是英文标点，
> 不要回去改 Excel —— 源头在导入链路。判定口径：Excel 里有全角标点 → 直接判 **T-04 待还原**，
> 而不是判 Excel 不合格。

---

## 5. 判定方法（Excel 侧）

脚本逐文件判定，等价于 `tmp/hsk_audit.py` 的 `check_excel()`：

| 步骤 | 判定内容 |
|---|---|
| 1 | 读第 1 个 sheet 第 1 行，列头须等于 2.1 的 16 列（顺序、字面量完全一致） |
| 2 | 若存在第 17 列「图片名称」→ 记 B 级提示（该列不入库） |
| 3 | 10 个必填列逐行判空 |
| 4 | `一级标题内容` 逐行比对 `听力/阅读/书写` |
| 5 | `题型` 逐行比对 2.4 的 18 个中文名 |
| 6 | 听力行与「题目序号为空」的行，`题目分组` 必须匹配 `起-止` 正则 |
| 7 | 分组行的 `答案`/`分值`（逗号拆）与 `区间长度` 比对；`题目内容`/`题目选项`/`题目标题`（`---` 拆）段数比对 |
| 8 | 题号集合 = 有题号的行 ∪ 每个分组行展开的区间；判连续、判重 |
| 9 | 单题行的选项键须为 `A,B,C…` 连续；选择题答案须命中选项键 |
| 10 | 按 `一级标题内容` 分组累加 `分值`（例题排除），每模块须 ≈100 |
| 11 | 卷合计须 = 100 × 模块数（按 2.6 满分表核对 `version+level`） |
| 12 | 例题 `分值` 须为 `0` |

> 🔴 **第 8 步是本题最容易写错的地方**：分组行本身没有题号，但它的区间**占用了题号**。
> 只统计有题号的行，会判出大量「缺号」假阳性。
>
> 🔴 **第 10 步必须按模块分组**，不是整卷求和。整卷求和只能验证「卷面 = 100×模块数」，
> 查不出「听力 90 + 阅读 110」这种内部错配。

---

## 6. 验收标准

### 6.1 级别定义与放行条件

| 级别 | 含义 | 处理要求 |
|---|---|---|
| **A 阻断** | 数据错误或结构错误，导入即产生脏数据 | **任一不合格即禁止导入**，无豁免 |
| **B 质量** | 可用但有质量缺陷（舍入、痕迹、提示） | 须登记责任人与修复期限；可先导入后补 |
| **C 后处理** | 导入链路必然造成，只能在导入后补 | 导入后必须执行后处理脚本，否则视为未完成 |

**放行判定：**

```
A 级全部 PASS 且 B 级全部 PASS  → 通过
A 级全部 PASS 且 B 级有不合格    → 有条件通过（须附整改计划）
A 级任一 FAIL                    → 不通过（禁止导入）
```

> 🔴 **不允许「A 级有 FAIL 但先导入再修」**。A 级问题在库内表现为结构错误（分卷错、题号冲突、
> 分组错位），事后修复需要重建卷，代价远高于改 Excel。

### 6.2 强制后处理项（导入后必做）

| 编号 | 内容 | 不做会怎样 |
|---|---|---|
| **PP-01** | 全角标点还原（至少 `passage`/`content`/`option_content`/`section_title`/`answer`） | 中文正文全是英文标点，阅读体验崩坏 |
| **PP-02** | 按题型回填 `layout` | 前端按 layout 渲染的组件全部降级/空白 |
| **PP-03** | 非枚举题型的 `type_id_mapping` 回填 | 题型筛选、练习取题取不到 |
| **PP-04** | 例题 `score` 归零 | 卷面总分被例题污染 |
| **PP-05** | HSK3.0 七~九级 `SEC_SPEAKING`/`SEC_TRANSLATION` 落位 | 口语/翻译模块空 |

### 6.3 验收数据留存

验收报告须包含以下四项，缺一不可：

1. 检查点总数与 A/B/C 各级不合格数；
2. 逐项明细（编号、结果、说明、样例）；
3. 待处理项清单（优先级、责任动作）；
4. 执行环境（检查时间、目录、数据库 hostname 与库名）。

> 🔴 **必须记录 `@@hostname`**。TEST 库名与 PROD 库名都叫 `xuexitest`，
> 只记录库名无法区分环境，历史上因此误判过。

---

## 7. 一键验收 SQL（只读，可直接执行）

以下 SQL 均以 `exam_type = 1` 圈定 HSK，`deleted = 0` 排除软删。
**不加 `exam_type` 条件会把 CSCA 卷混进来。**

```sql
-- V-06 卷面合计 ≠ 100 × 模块数
SELECT p.id, p.version, p.level, p.source, ROUND(SUM(q.score+0),2) total,
       COUNT(DISTINCT q.section_mapping) mods
FROM exam_paper p JOIN question q ON q.paper_id = p.id
WHERE p.exam_type = 1 AND p.deleted = 0 AND q.deleted = 0 AND q.type_id <> '例题'
GROUP BY p.id, p.version, p.level, p.source
HAVING ABS(SUM(q.score+0) - 100 * COUNT(DISTINCT q.section_mapping)) > 1.0;

-- V-07 模块合计 ≠ 100
SELECT p.id, p.source, q.section_mapping, ROUND(SUM(q.score+0),2) s
FROM exam_paper p JOIN question q ON q.paper_id = p.id
WHERE p.exam_type = 1 AND p.deleted = 0 AND q.deleted = 0 AND q.type_id <> '例题'
GROUP BY p.id, p.source, q.section_mapping
HAVING ABS(SUM(q.score+0) - 100) > 1.0;

-- V-08 卷内重号（例题按 0 号占位，必须排除）
SELECT q.paper_id, q.number, COUNT(*) c
FROM question q
WHERE q.deleted = 0
  AND q.paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 1 AND deleted = 0)
  AND q.type_id <> '例题'
GROUP BY q.paper_id, q.number HAVING c > 1;

-- V-09 分组区间与实际挂题数不符
SELECT g.id, g.paper_id, g.start_number, g.end_number, COUNT(q.id) c
FROM question_group g LEFT JOIN question q ON q.group_id = g.id AND q.deleted = 0
WHERE g.deleted = 0
  AND g.paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 1 AND deleted = 0)
GROUP BY g.id, g.paper_id, g.start_number, g.end_number
HAVING c <> (g.end_number - g.start_number + 1);

-- Q-02 例题分了值
SELECT q.paper_id, q.number, q.score
FROM question q
WHERE q.deleted = 0 AND q.type_id = '例题' AND q.score + 0 <> 0
  AND q.paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 1 AND deleted = 0);

-- Q-03 题型 mapping 未回填
SELECT q.type_id, COUNT(*) c FROM question q
WHERE q.deleted = 0
  AND q.paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 1 AND deleted = 0)
  AND (q.type_id_mapping IS NULL OR TRIM(q.type_id_mapping) = '')
GROUP BY q.type_id ORDER BY c DESC;

-- Q-07 选择题答案不在选项键里 / 选项为空
SELECT q.type_id, COUNT(*) c FROM question q
WHERE q.deleted = 0
  AND q.paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 1 AND deleted = 0)
  AND q.type_id_mapping IN ('listening_single','reading_single','listening_judge',
        'reading_judge','listening_img_match','reading_match','reading_word_fill',
        'reading_sort','reading_cloze','reading_wrong_sentence','reading_sent_fill')
  AND (q.option_content IS NULL
       OR JSON_VALID(q.option_content) = 0
       OR JSON_LENGTH(q.option_content) = 0
       OR JSON_CONTAINS_PATH(q.option_content,'one',CONCAT('$.',UPPER(q.answer))) = 0)
GROUP BY q.type_id ORDER BY c DESC;

-- T-01 layout 未回填（C 级）
SELECT IFNULL(q.layout,'(NULL)') lv, COUNT(*) c FROM question q
WHERE q.deleted = 0
  AND q.paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 1 AND deleted = 0)
GROUP BY q.layout;

-- T-04 全角句号被转成半角的痕迹
SELECT COUNT(*) FROM question q
WHERE q.deleted = 0
  AND q.paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 1 AND deleted = 0)
  AND (q.passage REGEXP '[一-龥]\\.' OR q.passage REGEXP '[一-龥][,?!;]');
```

> 🔴 **`layout <> 'xxx'` 这种写法不能用**：`layout` 未回填时是 `NULL`，
> `NULL <> 'x'` 求值为 `NULL`，该行会被静默过滤，整卷漏报。要排除某类题请改用 `type_id`。

---

## 8. 验收报告模板

```markdown
# HSK 题库数据验收报告

| 项 | 值 |
|---|---|
| 检查时间 | YYYY-MM-DD HH:MM:SS |
| Excel 目录 | <路径 或 —> |
| 数据库环境 | TEST / PROD（hostname / 库名） |
| 检查点总数 | 44（PASS n / FAIL n / SKIP n） |

## 一、结论

A 阻断：n 项不合格
B 质量：n 项不合格
C 后处理：n 项未完成

验收结论：通过 / 有条件通过 / 不通过

## 二、逐项明细

| 编号 | 检查点 | 级别 | 结果 | 说明 |
|---|---|---|---|---|

## 三、待处理项

| 优先级 | 编号 | 问题 | 处理建议 |
|---|---|---|---|
```

---

## 附录 A 复现方式

```bash
# Excel 侧
python tmp/hsk_audit.py --dir "<HSK Excel 目录>"

# 数据库侧
python tmp/hsk_audit.py --env TEST
python tmp/hsk_audit.py --env PROD

# 两侧 + 落盘
python tmp/hsk_audit.py --dir "<目录>" --env TEST --out report.md
```

工具只读，不修改任何 Excel 或数据库数据。判定逻辑与本文章节一一对应，
`RESULTS` 中的编号即本文检查点编号。

## 附录 B 术语

| 术语 | 含义 |
|---|---|
| 单题行 | `题目序号` 非空的行，落库为 1 道题 |
| 分组行 | `题目序号` 为空的行，落库为 N 道题 + 1 条 `question_group` |
| 模块 | `一级标题内容`（听力/阅读/书写…），**每模块满分恒 100** |
| 例题 | `type_id = 例题`，题号 `0`，分值 `0`，不计分 |
| 计分题 | 除例题外的所有题 |
| 分卷键 | `source + version + level` |
| `SEC_SPEAK` | HSKK 口语等级（初/中/高） |
| `SEC_SPEAKING` | HSK3.0 七~九级口语部分 —— **与上一条无关** |
