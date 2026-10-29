# CSCA 题库数据 · 统一检查点与验收标准

> **文档定位**：定义「CSCA 试卷数据合规」的**唯一判定依据**，适用于**任何来源**的 CSCA 试卷 Excel 与已落库数据。
> 本文不针对某一批文件、某一套卷，只定义标准。任何一批数据交来，都按本文件检查、按本文件验收。
>
> | 项 | 内容 |
> |---|---|
> | 版本 | v1.0 |
> | 适用对象 | CSCA（`exam_paper.exam_type = 2`）全部试卷与题目 |
> | 依据 | 代码 `QuestionExcelCSCAEo` / `CscaExcelHandler` / `PunctuationConvertUtil` / `OptionParseUtil`；DDL `exam_paper`、`question`、`exam_paper_structure` |
> | 检查分层 | L1 卷级 · L2 题级 · L3 文本级 · L4 一致性 |
> | 验收分级 | A 阻断级 · B 质量级 · C 后处理级 |
> | 执行方式 | 全部检查点均可用 SQL 或脚本自动化，不依赖人工目测 |

---

## 1. 数据模型（规范的锚点）

规范不是凭空定的，全部锚定在**代码与表结构**上。这一章是唯一真源，凡与之冲突的，以本章为准。

### 1.1 三层结构

```
Excel 输入层  →  导入转换层  →  数据库结果层
（15 列固定）    （有损，必须补偿）  （字段类型/取值域受 DDL 约束）
```

三层各有各的规范。**判定合规必须三层都查** —— 只查 Excel 不查库，查不出转换期损失；只查库不查 Excel，查不出源头缺陷。

### 1.2 Excel 输入层：15 列固定模板

依据 `manage/.../dto/excel/QuestionExcelCSCAEo.java`。**只有 15 个 `@ExcelProperty`，第 16 列「图片名称」不被识别**。

| # | Excel 列名（须精确匹配） | 必填 | EO 字段 | 落库位置 |
|---|---|---|---|---|
| 1 | `考试大纲*` | ✅ | `version` | `exam_paper.version` |
| 2 | `学科类型(HSK非必填)` | ✅ | `subjectType` | `exam_paper.subject_type` |
| 3 | `题型*` | ✅ | `typeId` | `question.type_id` |
| 4 | `部分标题*` | ✅ | `section` | `question.section` |
| 5 | `题目分组(或者范围)*` | ✅ | `questionGroup` | `question.question_group` |
| 6 | `部分标题内容` | — | `sectionTitle` | `question.section_title` |
| 7 | `题目序号` | — | `number` | `question.number`（int） |
| 8 | `题目标题` | — | `content` | `question.content` |
| 9 | `题目内容` | — | `passage` | `question.passage` |
| 10 | `题目选项` | — | `optionContent` | `question.option_content`（JSON） |
| 11 | `答案*` | ✅ | `answer` | `question.answer` |
| 12 | `分值*` | ✅ | `score` | `question.score`（varchar） |
| 13 | `来源*` | ✅ | `source` | `exam_paper.source` |
| 14 | `解析` | — | `analysis` | `question.analysis` |
| 15 | `版本` | ✅ | `languageVersion` | `exam_paper.language_version` |

> 🔴 **陷阱 1（字段互换）**：EO 中 `content` 对应「**题目标题**」、`passage` 对应「**题目内容**」。两者语义与命名相反，检查字段映射时不可按字面直觉判断。
>
> 🔴 **陷阱 2（第 16 列静默丢弃）**：任何放在「图片名称」列的值**不会**进入数据库。图片必须以 `<img>` 内联在 `passage` / `option_content` / `analysis` 中。
>
> 🔴 **陷阱 3（题干落点随 layout 变化）**：题干**不是**固定存在某一列。规范见下表，这是判定「题干是否入错列」的唯一依据。

### 1.2.1 字段填充矩阵

| `type_id` | `layout` | `content`（题目标题） | `passage`（题目内容） | `section_title` |
|---|---|---|---|---|
| `单选` | `textChoice` | 空 | **题干** | 部分标题（可选） |
| `多选` | `textChoice` | 空 | **题干** | 部分标题（可选） |
| `识解汉字` | `textChoice` | 空 | **题干** | 部分标题 |
| `选词填空` | `textChoice` | 空 | **题干** | 部分标题 |
| `辨析词语` | `textChoice` | 空 | **题干** | 部分标题 |
| `补全语句` | `textChoice` | 空 | **题干** | 部分标题 |
| `阅读理解` | `passageGroup` | **题干/材料标题** | 空 | 部分标题 |
| `单选`（材料题） | `passageGroup` | **题干** | 空 | 部分标题 |
| `选词成段` | `clozeGroup` | 空 | 空 | **整段材料** |

归纳为三条硬规则：

1. `textChoice` → 题干写「题目内容」列（→ `passage`），「题目标题」列**必须留空**。
2. `passageGroup` → 题干写「题目标题」列（→ `content`），「题目内容」列**必须留空**。
3. `clozeGroup` → 整段材料写「部分标题内容」列（→ `section_title`），前两列**都留空**。

> 换言之：`content` 与 `passage` **互斥**，任一题只能有一个非空。两者同时为空（且非 `clozeGroup`）或同时非空，均判定为字段错列。

### 1.3 分卷键

依据 `CscaExcelHandler.getGroupKey()`：

```
groupKey = source + "_" + version + "_" + languageVersion + "_" + subjectType
```

- 四元组**任一不同** → 新建一张 `exam_paper`。
- 因此**同一套卷的多语言版本**必须靠 `版本` 列区分（`chinese` / `english`），不能靠文件名。
- 因此**同一套卷**的 `来源*` 列必须**完全一致**；若因文件名后缀（如 `-无图片名称列`、`_中文`）写进 `来源*`，会被拆成多张卷。

### 1.4 数据库结果层：类型与长度上限

| 表.字段 | 类型 | 上限 | 说明 |
|---|---|---|---|
| `exam_paper.source` | varchar(40) | **40 字符** | 卷唯一标识，超长静默截断 |
| `exam_paper.version` | varchar(30) | 30 | 恒 `CSCA` |
| `exam_paper.language_version` | varchar(20) | 20 | `chinese` / `english` |
| `exam_paper.subject_type` | varchar(32) | 32 | 5 种枚举 |
| `question.type_id` | varchar(32) | 32 | 8 种枚举 |
| `question.section` | varchar(50) | 50 | 数字字符串 |
| `question.question_group` | varchar(100) | 100 | `N-M` 区间 |
| `question.section_title` | varchar(200) | 200 | 部分标题内容 |
| `question.number` | **int** | — | Excel 传 String，MySQL 隐式转换 |
| `question.score` | **varchar(30)** | 30 | 分值唯一真源 |
| `question.layout` | varchar(32) | 32 | `textChoice` / `passageGroup` / `clozeGroup` |
| `question.option_content` | **json** | — | JSON 对象 `{"A":".."}`，非数组 |
| `question.content` / `passage` / `answer` / `analysis` | text | 64KB | 富文本/公式 |

### 1.5 取值域（枚举）

| 字段 | 允许值 |
|---|---|
| `version` | `CSCA`（唯一值） |
| `language_version` | `chinese`、`english` |
| `subject_type` | `文科中文`、`理科中文`、`数学`、`物理`、`化学` |
| `type_id` | `单选`、`多选`、`选词填空`、`选词成段`、`识解汉字`、`辨析词语`、`补全语句`、`阅读理解` |
| `section` | 阿拉伯数字字符串 `1` … `6` |
| `layout` | `textChoice`、`passageGroup`、`clozeGroup` |

> 🔴 **禁止值**：`subject_type` 不得写 `语文`（历史遗留写法，会导致学科筛选、练习分科全部失效）。

### 1.6 layout 映射规则

依据 `CscaExcelHandler`。导入链路**不写** `layout`，必须由后处理按此表回填：

| `type_id` | `layout` | 说明 |
|---|---|---|
| `单选` | `textChoice` | 常规单选题 |
| `单选` + 共用材料 | `passageGroup` | 一材多问，题干在 `content` |
| `多选` | `textChoice` | — |
| `选词填空` | `textChoice` | — |
| `识解汉字` | `textChoice` | — |
| `辨析词语` | `textChoice` | — |
| `补全语句` | `textChoice` | — |
| `阅读理解` | `passageGroup` | 短文后多问 |
| `选词成段` | `clozeGroup` | 一段多空，共用词池 |

### 1.7 分值规则（唯一算法）

`question.score` 是分值的**唯一真源**；卷面总分 = `SUM(question.score)`，无冗余字段。

| 题型组合 | 题量 | 分值分布 | 合计 |
|---|---|---|---|
| 客观题卷（化学/数学/物理） | 48 | 第 **1–40 题 = 2.00**，第 **41–48 题 = 2.50** | **100.00** |
| 语言类卷（文科中文/理科中文） | 80 | 每题 **1.25** | **100.00** |

> 🔴 **反面教材**：若按 `100 ÷ 48 = 2.0833` 四舍五入为每题 **2.08**，则 `2.08 × 48 = 99.84`，卷面总分不足 100。**该写法禁止使用**。

### 1.8 导入转换层：三项有损行为（必须后处理补偿）

| # | 行为 | 代码位置 | 后果 |
|---|---|---|---|
| 1 | **强制全角标点转半角** | `QuestionExcelTemplate.java:77` → `PunctuationConvertUtil.convertObject()` | `……`→`..`、`·`→`.`、`。`→`.`、`—`→`-`、`，：（）“”` 全部转换 |
| 2 | **不写 `layout`** | `CscaExcelHandler` | `layout` 恒为 NULL，前端渲染退化 |
| 3 | **不做 `analysis` HTML 化** | `CscaExcelHandler` | 解析为纯文本，无段落结构 |

> 🔴 这三项**改 Excel 无解**，因为损失发生在读取之后、落库之前。唯一解法是导入完成后跑后处理脚本还原。

---

## 2. 检查点

共 **41 个检查点**，分四层。每个检查点给出：检查方法、合格判据、级别。

级别定义：
- **A（阻断）**：不满足禁止导入。
- **B（质量）**：不满足须整改，但可先导入后修。
- **C（后处理）**：导入链路必然违反，须在导入后由脚本补偿。

### 2.1 L1 卷级检查点（V-01 ~ V-12）

| 编号 | 检查点 | 检查方法 | 合格判据 | 级别 |
|---|---|---|---|---|
| **V-01** | 卷身份四元组完整 | 分组统计 `source`/`version`/`language_version`/`subject_type` | 四项均非空、无 `null`、无空串 | A |
| **V-02** | `version` 取值 | `SELECT DISTINCT version` | 仅 `CSCA` | A |
| **V-03** | `language_version` 取值 | `SELECT DISTINCT language_version` | ∈ {`chinese`,`english`} | A |
| **V-04** | `subject_type` 取值 | `SELECT DISTINCT subject_type` | ∈ 5 种枚举，**无 `语文`** | A |
| **V-05** | `source` 长度与纯净度 | `CHAR_LENGTH(source)`；正则筛后缀 | ≤ 40；不含 `-无图片名称列`/`_中文`/`_英文` 等文件名残留 | A |
| **V-06** | 分卷键唯一性 | 按 `getGroupKey()` 模拟分组 | 同一套卷只产生 **1 个** groupKey | A |
| **V-07** | 卷面总分 | `SUM(score+0) GROUP BY paper_id` | = **100.00 ± 0.01** | A |
| **V-08** | 卷内题量 | `COUNT(*) GROUP BY paper_id` | ∈ {48, 80} | A |
| **V-09** | 结构表配套 | `exam_paper_structure` 按 `paper_id` 计数 | 每卷有对应结构行（新卷必须补） | A |
| **V-10** | 卷内题号唯一 | `COUNT(DISTINCT section,number)` vs `COUNT(*)` | 两者相等 | A |
| **V-11** | 卷内题目内容唯一 | 按 `题干 + option_content + answer` 算指纹，**排除 `选词成段`** | 指纹去重后数量 = 总题数（**无副本**） | A |
| **V-12** | 无空题干 | 按 layout 取题干字段，统计空值 | 每题题干非空（`textChoice`→`passage`，`passageGroup`→`content`，`clozeGroup`→`section_title`） | A |

> **V-11 判定细节（易错）**：
> - 题干需按 layout 取：`COALESCE(NULLIF(TRIM(content),''), passage)` —— `content` 与 `passage` 互斥，可直接 coalesce。
> - **必须排除选词成段**：一段材料含 5 个空，5 题共用同一材料与同一词池，`option_content` 天然相同，不排除会产生假阳性。
> - **排除时用 `type_id`，不要用 `layout`**：`layout` 在未做后处理的库中全为 NULL，`layout <> 'clozeGroup'` 对 NULL 求值为 NULL 会被静默过滤，导致**整卷漏报**。
> - **不得只用 `content` 判重**：`textChoice` 的 `content` 全为空，用它判重等于全部碰撞。
>
> V-06 与 V-11 一起，能拦住「同一套卷的多个衍生态文件被重复导入」。

### 2.2 L2 题级检查点（Q-01 ~ Q-14）

| 编号 | 检查点 | 检查方法 | 合格判据 | 级别 |
|---|---|---|---|---|
| **Q-01** | 列头精确匹配 | 读第 1 行，与 1.2 表逐字比对 | 15 列名称、顺序完全一致；无第 16 列依赖 | A |
| **Q-02** | 必填项非空 | 逐列统计空值 | 8 个必填列空值率 **0%** | A |
| **Q-03** | 题号连续 | 按 `section` 排序取 `number` 序列 | 整数、卷内 **1..N 连续无缺号** | A |
| **Q-04** | `type_id` 合法 | `SELECT DISTINCT type_id` | ∈ 8 种枚举 | A |
| **Q-05** | `section` 格式 | 正则 `^\d+$` | **阿拉伯数字字符串**（禁中文数字「一、二」） | B |
| **Q-06** | `question_group` 格式 | 正则 `^\d+-\d+$` | **区间格式** `N-M`（禁逗号罗列 `1,2,3`） | B |
| **Q-07** | 选项格式 | 正则 `^[A-Za-z]+[:：]` 切分 | 半角 `A:xxx,B:xxx`；字母从 A 连续 | A |
| **Q-08** | 客观题选项数 | 按 `,X:` 计数 | ∈ {4, 5, 6}；**禁 7 个及以上** | B |
| **Q-09** | 答案合法性（单选） | `answer` 是否存在于选项键中 | 单字母、∈ 选项键集合 | A |
| **Q-10** | 答案合法性（多选） | 同上 | 多字母、无重复、均为合法选项键 | A |
| **Q-11** | `layout` 正确 | 与 1.6 映射表比对 | 完全符合映射表 | C |
| **Q-12** | 分值符合规则 | 与 1.7 规则比对 | 48 题卷 1–40=2、41–48=2.5；80 题卷全 1.25 | A |
| **Q-13** | `section_title` 配套 | 按 `section` 分组查空值 | 中文卷（文科/理科）每 section 均非空 | B |
| **Q-14** | 题干落点正确 | 对照 1.2.1 填充矩阵 | `content`/`passage` 互斥；三者不同时空；与 layout 匹配 | A |

### 2.3 L3 文本级检查点（T-01 ~ T-09）

| 编号 | 检查点 | 检查方法 | 合格判据 | 级别 |
|---|---|---|---|---|
| **T-01** | KaTeX 严格可渲染 | `katex.renderToString(m,{throwOnError:true,strict:'error'})` | 失败数 **0** | A |
| **T-02** | `$` 成对 | 按**字段粒度**（每个 `content`/`passage`/每个选项/`analysis`）计 `$` 个数 | 每字段 `$` 数为偶数 | A |
| **T-03** | 数学模式无裸中文 | 由 T-01 的 `unicodeTextInMathMode` 分类兜住 | 中文一律包在 `\text{}` 内 | A |
| **T-04** | `analysis` 已 HTML 段落化 | 正则 `<p>` 是否存在 | 含 `<p>` 标签；`∵/∴` 已转 `\because`/`\therefore` | C |
| **T-05** | 公式外裸 `<` 转义 | 找公式外的 `<` 字符 | 全部转为 `&lt;`（避免被当标签吞掉） | B |
| **T-06** | 中文标点保留 | 查 `..`（连续两点）出现 | **无 `..` 退化**；中文语境省略号应为 `……` | C |
| **T-07** | 图片可解析 | 提取 `<img src>`，HEAD 请求 | 全部返回 200，无 404 | B |
| **T-08** | HTML 闭合 | 标签配对检查 | `<p>`/`<img>`/`<span>` 均闭合或自闭合 | B |
| **T-09** | 音译间隔号 | 查中西文混排人名 | 用 `·`（U+00B7），非半角 `.` | B |

> 🔴 **T-01 的判定方式**：必须用 KaTeX **真渲染**，禁止用正则白名单判断命令是否合法。
> 正则法会把 `\mid`、`\boldsymbol`、`\begin`、`\complement`、`\xrightarrow`、`\underset`、`\overset`、`\not`、`\rightleftharpoons` 等合法命令误判为非法，产生大量假阳性。

### 2.4 L4 一致性检查点（C-01 ~ C-06）

| 编号 | 检查点 | 检查方法 | 合格判据 | 级别 |
|---|---|---|---|---|
| **C-01** | 行数一致 | Excel 有效行数 vs 落库题数 | 完全相等 | A |
| **C-02** | 字段值一致 | 逐题逐字段比对 Excel 与 DB | 除 1.8 三项有损外，逐字段相同 | A |
| **C-03** | `option_content` 结构 | 解析 JSON | 为**对象** `{"A":"..","B":".."}`，键为大写单字母 | A |
| **C-04** | 题号重编号 | 对照源卷题号 | 卷内重编号为 1..N | A |
| **C-05** | 快照一致 | `practice_answer` 三份快照 vs `question` | 已有人作答的卷，快照与题目一致 | B |
| **C-06** | 双环境一致 | TEST 与 PROD 同卷结构/分值/题数比对 | 除已知差异外一致 | B |

> 🔴 **C-05 说明**：答题/复习页读的是 `practice_answer` 的 `question_snapshot`/`option_snapshot`/`analysis_snapshot`，不是 `question`。「改完题目没生效」先查这里。

---

## 3. 验收标准

### 3.1 放行条件

| 结论 | 条件 |
|---|---|
| **通过** | A 级检查点 **全部合格**，B 级不合格项 ≤ 0 |
| **有条件通过** | A 级全部合格，B 级存在不合格项，但已登记整改责任人与截止时间 |
| **不通过** | 任一 A 级不合格 |

> **A 级不设豁免**。C 级不进放行判定，但必须随导入计划提交后处理脚本，否则视为未完成。

### 3.2 A 级验收清单（阻断项，逐项签字）

| 序 | 检查点 | 判据 | 结论 |
|---|---|---|---|
| A-1 | V-01~V-06 卷身份 | 四元组完整、取值合法、source 纯净且 ≤40、分卷键唯一 | ☐ |
| A-2 | V-07~V-10 卷结构 | 总分 100.00、题量 48/80、结构表配套、题号唯一 | ☐ |
| A-3 | V-11/V-12 无副本无空题干 | 卷内题目指纹去重 = 总题数；题干非空 | ☐ |
| A-4 | Q-01/Q-02 列与必填 | 15 列精确匹配、8 个必填列零空值 | ☐ |
| A-5 | Q-03/Q-04 题号与题型 | 1..N 连续、8 种枚举内 | ☐ |
| A-6 | Q-07/Q-09/Q-10 选项与答案 | 半角分隔、答案 ∈ 选项键 | ☐ |
| A-7 | Q-12 分值规则 | 40×2 + 8×2.5 / 80×1.25 | ☐ |
| A-8 | T-01~T-03 公式 | KaTeX 严格模式 0 失败、`$` 成对、无裸中文 | ☐ |
| A-9 | C-01~C-04 落库一致 | 行数、字段、JSON 结构、重编号全部一致 | ☐ |

### 3.3 B 级验收清单（质量项）

| 序 | 检查点 | 判据 | 结论 |
|---|---|---|---|
| B-1 | Q-05 section 格式 | 阿拉伯数字 | ☐ |
| B-2 | Q-06 question_group 格式 | `N-M` 区间 | ☐ |
| B-3 | Q-08 选项数 | 4/5/6 | ☐ |
| B-4 | Q-13 section_title 配套 | 中文卷各 section 非空 | ☐ |
| B-5 | T-05 裸 `<` 转义 | 全部 `&lt;` | ☐ |
| B-6 | T-07 图片可解析 | 无 404 | ☐ |
| B-7 | T-08 HTML 闭合 | 标签配对 | ☐ |
| B-8 | T-09 间隔号 | 用 `·` | ☐ |
| B-9 | C-05 快照一致 | 已作答卷快照 = 题目 | ☐ |
| B-10 | C-06 双环境一致 | TEST/PROD 一致（已知差异除外） | ☐ |

### 3.4 C 级（后处理项，必须在导入后执行）

| 序 | 检查点 | 补偿动作 | 判据 |
|---|---|---|---|
| C-1 | Q-11 `layout` | 按 1.6 映射表 UPDATE | 全部非空且符合映射 |
| C-2 | T-04 `analysis` HTML 化 | 段落化 + `∵/∴` 转义 | 100% 含 `<p>` |
| C-3 | T-06 中文标点还原 | 按语义还原 `..` → `……`、`.` → `·` | 无退化残留 |

---

## 4. 一键验收（可直接执行）

### 4.1 数据库侧（SQL，MySQL 8.0，只读）

限定 CSCA：`p.exam_type = 2 AND p.deleted = 0`。**不加此条件会混入 HSK 卷，导致误报。**

> 🔴 **两个写 SQL 时必须避开的坑**：
> 1. **NULL 比较会静默漏报**。`layout <> '选词成段'` 在 `layout` 为 NULL 时求值为 NULL，该行直接被过滤。凡涉及可能为空的列，用 `COALESCE(col,'')` 或改用不依赖该列的字段判断。
> 2. **中文正则 `[一-龥]` 会跨公式对匹配**。把两个公式之间的中文误判为「公式内裸中文」。此项**不要用 SQL 查**，改用 KaTeX 脚本（见 4.2）。

```sql
-- A-2 卷面总分不等于 100
SELECT p.id, p.source, p.language_version, SUM(q.score+0) AS total
FROM exam_paper p JOIN question q ON q.paper_id = p.id
WHERE p.exam_type = 2 AND p.deleted = 0 AND q.deleted = 0
GROUP BY p.id, p.source, p.language_version
HAVING ABS(SUM(q.score+0) - 100) > 0.01;

-- A-2 卷内题量不在 48/80
SELECT p.id, p.source, COUNT(*) AS cnt
FROM exam_paper p JOIN question q ON q.paper_id = p.id
WHERE p.exam_type = 2 AND p.deleted = 0 AND q.deleted = 0
GROUP BY p.id, p.source
HAVING cnt NOT IN (48, 80);

-- A-2 卷内 (section, number) 重复
SELECT paper_id, section, number, COUNT(*) c
FROM question q
WHERE deleted = 0 AND paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 2 AND deleted = 0)
GROUP BY paper_id, section, number
HAVING c > 1;

-- A-1 学科类型越界（含历史遗留「语文」）
SELECT DISTINCT subject_type FROM exam_paper
WHERE exam_type = 2 AND deleted = 0
  AND subject_type NOT IN ('文科中文','理科中文','数学','物理','化学');

-- A-1 source 超长或含文件名残留
SELECT id, source, CHAR_LENGTH(source) len FROM exam_paper
WHERE exam_type = 2 AND deleted = 0
  AND (CHAR_LENGTH(source) > 40
       OR source LIKE '%-无图片名称列%'
       OR source LIKE '%\_中文' ESCAPE '\\'
       OR source LIKE '%\_英文' ESCAPE '\\');

-- A-5 题型越界
SELECT DISTINCT q.type_id FROM question q JOIN exam_paper p ON p.id = q.paper_id
WHERE p.exam_type = 2 AND p.deleted = 0 AND q.deleted = 0
  AND q.type_id NOT IN ('单选','多选','选词填空','选词成段','识解汉字','辨析词语','补全语句','阅读理解');

-- A-3 卷内题目重复（题干按 layout 取；用 type_id 排除选词成段，不用 layout）
SELECT q.paper_id, p.source,
       MIN(q.number) n1, MAX(q.number) n2, COUNT(*) c, MIN(q.type_id) t
FROM question q JOIN exam_paper p ON p.id = q.paper_id
WHERE q.deleted = 0 AND p.exam_type = 2 AND p.deleted = 0
  AND q.type_id <> '选词成段'
GROUP BY q.paper_id, p.source,
         MD5(CONCAT_WS('#', COALESCE(NULLIF(TRIM(q.content),''), q.passage),
                       q.option_content, q.answer))
HAVING c > 1;

-- A-5 空题干（题干按 layout 落在不同字段）
SELECT q.layout, COUNT(*) cnt FROM question q
JOIN exam_paper p ON p.id = q.paper_id
WHERE p.exam_type = 2 AND p.deleted = 0 AND q.deleted = 0
  AND COALESCE(NULLIF(TRIM(q.content),''), NULLIF(TRIM(q.passage),''),
               NULLIF(TRIM(q.section_title),'')) IS NULL
GROUP BY q.layout;

-- A-4 字段错列（content 与 passage 同时非空，或同为空且非 clozeGroup）
SELECT q.layout, COUNT(*) cnt FROM question q
JOIN exam_paper p ON p.id = q.paper_id
WHERE p.exam_type = 2 AND p.deleted = 0 AND q.deleted = 0
  AND ( (TRIM(IFNULL(q.content,'')) <> '' AND TRIM(IFNULL(q.passage,'')) <> '')
     OR (TRIM(IFNULL(q.content,'')) =  '' AND TRIM(IFNULL(q.passage,'')) = '' AND q.layout <> 'clozeGroup') )
GROUP BY q.layout;

-- C-1 layout 为空或不合法
SELECT layout, COUNT(*) FROM question q
WHERE deleted = 0 AND paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 2 AND deleted = 0)
GROUP BY layout;

-- C-2 analysis 未 HTML 化
SELECT COUNT(*) FROM question q
WHERE deleted = 0 AND paper_id IN (SELECT id FROM exam_paper WHERE exam_type = 2 AND deleted = 0)
  AND (q.analysis IS NULL OR q.analysis NOT LIKE '%<p>%');
```

### 4.2 Excel 侧（脚本检查）

| 检查项 | 方法 |
|---|---|
| Q-01 列头 | 读第 1 行，`list(header) == 15 列清单` |
| Q-02 必填 | 8 个必填列 `isnull().sum() == 0` |
| Q-03 题号 | 满足其一：整卷 `1..N` 连续；或每个 `section` 内 `1..M` 连续 |
| Q-07/Q-08 选项 | 正则 `,([A-Z]):` 切分，键连续 |
| Q-12 分值 | 按 1.7 规则逐题比对 |
| T-01 公式 | 导出所有 `$...$` / `$$...$$` → KaTeX 严格渲染 → 收集失败明细 |
| T-02 `$` 配对 | **按字段**计 `$` 个数，为偶数 |

> 🔴 **`$` 配对检查必须按「单字段」粒度**。整单元格/整行计数会把「两个相邻公式各缺一半」抵消成偶数，漏掉真缺陷。
>
> 🔴 **题号连续性有两种合法模式**：考试卷为整卷 `1..N`；冲刺卷/模拟卷按 `section` 内独立编号 `1..M`。只按 `section` 判会把整卷连续的卷误判为缺号，只按整卷判会把分节编号的卷误判为重复。

**可执行实现**：`tmp/csca_audit.py`，一条命令输出完整验收报告。

```bash
# 只查 Excel
python tmp/csca_audit.py --dir "<Excel 根目录>"

# 只查数据库
python tmp/csca_audit.py --env TEST

# 两侧同查并落盘报告
python tmp/csca_audit.py --dir "<目录>" --env TEST --out report.md
```

报告结构固定为「结论汇总（A/B/C 三级计数 + 验收结论）→ 逐项明细（编号/检查点/级别/结果/说明）→ 待处理项」。工具只读，不修改任何 Excel 或数据库数据。

### 4.3 KaTeX 校验基准配置

```javascript
katex.renderToString(tex, {
  throwOnError: true,
  strict: 'error',        // 关键：不是 'warn'，否则中文进数学模式不报错
  displayMode: false
});
```

失败分类与对应修复：

| KaTeX 报错 | 含义 | 修复 |
|---|---|---|
| `unicodeTextInMathMode` | 中文裸进数学模式 | 包 `\text{中文}` |
| `Undefined control sequence` | 未定义命令 | 改为合法命令（如 `\le`→`\leq`） |
| `Expected ...` | 语法残缺 | 补 `}` 或缺参数 |
| `Extra \}` | 多余括号 | 删多余 `}` |
| `$` 数不成对 | 字段级 `$` 未闭合 | 补 `$` |

---

## 5. 验收报告模板

> 每批数据提交验收时，按此模板填写。不得只给结论，必须附数值与证据路径。

```
──────────────────────────────────────────────────────────
CSCA 题库数据验收报告
──────────────────────────────────────────────────────────
批次标识    ：
数据来源    ：（目录 / 系统 / 交接方）
提交时间    ：
验收环境    ：☐ TEST   ☐ PROD（圈选）
验收人      ：
──────────────────────────────────────────────────────────
一、数据规模
  Excel 文件数        ：
  有效数据行          ：
  模拟分卷数          ：
  落库后卷数          ：
  落库后题数          ：
  冗余副本数          ：（内容指纹重复条数）

二、A 级（阻断）检查结果
  A-1 卷身份          ：□通过 □不通过   证据：
  A-2 卷结构          ：□通过 □不通过   证据：
  A-3 无副本          ：□通过 □不通过   证据：
  A-4 列与必填        ：□通过 □不通过   证据：
  A-5 题号与题型      ：□通过 □不通过   证据：
  A-6 选项与答案      ：□通过 □不通过   证据：
  A-7 分值规则        ：□通过 □不通过   证据：
  A-8 公式            ：□通过 □不通过   失败数：
  A-9 落库一致        ：□通过 □不通过   证据：

三、B 级（质量）检查结果
  B-1 ~ B-10          ：不合格项数 =     明细见附件
  整改责任人          ：
  整改截止            ：

四、C 级（后处理）执行情况
  C-1 layout 回填     ：□已执行 影响行数：
  C-2 analysis HTML 化：□已执行 影响行数：
  C-3 标点还原        ：□已执行 影响行数：

五、验收结论
  □ 通过      □ 有条件通过      □ 不通过
  阻断原因（若不通过）：
  签字：                    日期：
──────────────────────────────────────────────────────────
```

## 附录 A 检查点总表（速查）

| 层 | 编号区间 | 数量 | A 级 | B 级 | C 级 |
|---|---|---|---|---|---|
| L1 卷级 | V-01 ~ V-12 | 12 | 12 | 0 | 0 |
| L2 题级 | Q-01 ~ Q-14 | 14 | 9 | 4 | 1 |
| L3 文本级 | T-01 ~ T-09 | 9 | 3 | 4 | 2 |
| L4 一致性 | C-01 ~ C-06 | 6 | 4 | 2 | 0 |
| **合计** | — | **41** | **28** | **10** | **3** |

## 附录 B 术语

| 术语 | 含义 |
|---|---|
| 分卷键 | `source`+`version`+`languageVersion`+`subjectType`，决定是否新建一张卷 |
| 衍生态 | 同一套卷的多个交付变体（带/不带图片列、中文/英文），**不得全部导入** |
| 内容指纹 | 题干（按 layout 取 `content`/`passage`/`section_title`）+ `option_content` + `answer` 的 MD5，用于判重；对「选词成段」不适用 |
| 阻断项 | A 级检查点，不满足即禁止导入，无豁免 |
| 后处理 | 导入链路无法完成、必须在落库后跑脚本补偿的动作（layout/HTML/标点） |
| 快照 | `practice_answer` 中的题目副本，是答题/复习页的真实数据源 |

## 附录 C 代码与表结构依据索引

| 依赖 | 路径 |
|---|---|
| Excel 模板定义 | `manage/src/main/java/com/hsktreasure/manage/dto/excel/QuestionExcelCSCAEo.java` |
| 分卷与解析 | `manage/.../service/handler/impl/CscaExcelHandler.java` |
| 标点强制转换 | `manage/.../check/excel/QuestionExcelTemplate.java:77` |
| 全角半角映射表 | `common/.../util/PunctuationConvertUtil.java` |
| 选项解析 | `manage/.../util/OptionParseUtil.java` |
| 表结构 | `exam_paper`(14 列) / `question`(28 列) / `exam_paper_structure`(23 列) |
