# HSK 练习 · 共用题库方案（目录与结构全部由题库推导）

> **目标形态**：练习的目录（等级 → 卷 → 节）与结构**不再读任何练习专用配置表**，全部由题库 `question` 实时推导；题库（`exam_paper` / `question`）考试与练习**物理同一份**。
> **改动边界**：只改 `practice-service`（"只修改练习的接口"）；`exam-service` 一行不动；题库表一行不动。
> **交付**：本文档为方案，**本次不动代码、不动数据库**。
>
> 数据基线：TEST 库 `xuexitest`（`8.138.185.11`），只读侦察，带 G1 `DATABASE()` / G2 `@@hostname` 闸门。

---

## 目录

- [0. 摘要](#0-摘要)
- [1. 现状盘点（实测）](#1-现状盘点实测)
- [2. 目标形态：题库即目录](#2-目标形态题库即目录)
- [3. 逐模块可行性](#3-逐模块可行性)
- [4. 缺口与替代方案](#4-缺口与替代方案)
- [5. 迁移与兼容](#5-迁移与兼容)
- [6. 改动面（只改练习侧）](#6-改动面只改练习侧)
- [7. 风险登记](#7-风险登记)
- [8. 实施步骤](#8-实施步骤)
- [附录 A：实测数据表](#附录-a实测数据表)
- [附录 B：侦察脚本](#附录-b侦察脚本)

---

## 0. 摘要

### 一句话

**HSK 的题库早就是共用的了 —— 真正重复的是「卷结构」这一层**：练习侧为每张卷单独建了 1201 行结构配置，而考试侧只有"每等级一套"的模板。本方案把练习的结构层**整体删掉**，改为按 `question` 表实时推导，从而让"题库 = 目录"。

### 结论速览

| 问题 | 结论 | 证据 |
|---|---|---|
| 题库共用吗 | **已经共用**：两侧读同一批 `exam_paper` / `question` 行 | 见 [1.1](#11-已经在共用的) |
| 什么在重复 | **卷结构**：`practice_paper_structure` 1201 行 vs `exam_paper_structure` 每版本 48 行 | 两张表**列定义完全相同（23 列逐列一致）** |
| 节能从题库推出来吗 | **能**。`section_title` 自带节标题（"第1-10题:判断对错."）、`title1_text` 自带模块名（"听力"）、`type_id_mapping` 自带题型码 | [2.2](#22-节名与题型名的来源) |
| `answer_mode` 呢 | **能**。`type_id_mapping` → `answer_mode` 是 **1:1**（实测一对多为 0 个 type_code） | [4.1](#41-answer_mode可推导) |
| 共享选项池呢 | **能替代**。同 `pool_code` 的题本就各自带着同一份 `option_content` | [4.3](#43-共享选项池-option_pool) |
| 会断链吗 | **不会**。`practice_record` / `practice_answer` **自带 `paper_id` + `section_mapping` + `section`**，`structure_id` 只是冗余键 | [5.1](#51-structure_id-不变量) |
| 改动面 | 100% 在 `practice-service`；端点路径与出入参**不变** | [6](#6-改动面只改练习侧) |

---

## 1. 现状盘点（实测）

### 1.1 已经在共用的

| 资源 | 考试侧 | 练习侧 | 共用 |
|---|---|---|---|
| `exam_paper`（`exam_type=1`） | 136 卷（HSK2.0 **121** + HSK3.0 **15**） | **同一批行**（`SharedPaperEligibility` 也认 `exam_type=1`） | ✅ |
| `question` | HSK2.0 **10561** 题 + HSK3.0 **1059** 题 = **11620** 题 | **同一批行** | ✅ |
| `question_group`（1036 行） | 共材料大题 | 同一批行 | ✅ |
| `question_shared_audio`（237 行） | — | 听力共同材料音频 | ✅ |
| `exam_type=2`（CSCA 31 卷） | 考试 | **不参与**（`SharedPaperEligibility` 要求 `exam_type=1`） | ❌ 正确隔离 |
| `question.section_mapping` 填充率 | — | HSK2.0 **100%**（10561/10561）、HSK3.0 **100%**（1059/1059） | ✅ 标签齐全 |

> **所以"题目"这一层没有任何重复**：练习的 `PracticeQuestionMapper.selectByPart(paperId, sectionMapping, sectionCode)` 与考试的 `QuestionMapper.selectByPaperId(paperId)` 读的是**同一张 `question`**，只是投影与过滤不同。

### 1.2 重复维护的：结构层

这是本方案要消除的核心对象。

| 维度 | `exam_paper_structure`（考试） | `practice_paper_structure`（练习） |
|---|---|---|
| 粒度 | **按 `(version, hsk_level)` 一套模板** | **按真实 `paper_id` 逐卷一套** |
| 行数 | HSK2.0 **48** 行 + HSK3.0 **48** 行 | **1201** 行（`deleted=0`） |
| `paper_id` | 占位值（2–7，不对应真实卷） | 真实卷 id（雪花） |
| 覆盖 | 每等级仅"第一套" | 全部 136 卷（听力/阅读）/93 卷（写作）/38 卷（口语） |
| 列定义 | 23 列 | **23 列，逐列相同** |

**两张表的列定义逐列一致**（`id / paper_id / version / hsk_level / paper_name / content_type / content_name / section_name / content_name_en / content_name_vi / section_name_en / section_name_vi / question_count / duration_minutes / sort_order / description / created_time / updated_time / deleted / created_by / update_by / subject_type_mapping / full_score`）。

**含义**：练习侧是在**用一张同构的表，把考试侧的模板逐卷抄了一份**。每导入一张新卷，就要补一套结构行 —— 这就是"共同题库"没做到的最后一公里。

### 1.3 练习独有的配置层清单

| 表 | 行数 | 角色 | 本方案去留 |
|---|---|---|---|
| `practice_paper_setting` | 174（`enabled=1 & visible=1 & deleted=0`） | 卷的上下架 / 可见性 | **由"是否有题"替代** + 保留黑名单 |
| `practice_paper_structure` | **1201** | 逐卷的"节" | **删除依赖**，改由 `question` 推导 |
| `practice_part_setting` | 逐卷 | 节的题型码 / 答题模式 / 多语言名 | **删除依赖**，改由题型字典推导 |
| `practice_module_level_config` | 49 | 等级开关 + 听力 `parts_config` | **删除依赖**，等级由 `exam_paper` 推导；`parts_config` 由 `question` 推导 |
| `practice_question_option_pool` | 2505（306 structure） | MATCH 题型的共享选项池 | **可替代**（见 [4.3](#43-共享选项池-option_pool)） |
| `practice_user_preference` | 16 | "最近选的等级/卷" | **保留**（用户态，不属于题库） |
| `hsk_level_config` | 13 | 等级名（多语言） | **保留**（等级字典，非练习专属） |

### 1.4 顺带发现的脏数据

| # | 现象 | 影响 | 建议 |
|---|---|---|---|
| 1 | `practice_paper_structure` 里有 **215 行**指向**已删除的卷**（`deleted=1` 101 行 + 卷已删 114 行） | 逐卷维护必然积累垃圾 | 本方案上线后自然消失 |
| 2 | 有 **33 张卷**"有结构行但 0 题"（`exam_paper` 行已删） | 目录靠 `.filter(total > 0)` 兜住，但结构表本身不可信 | 同上 |
| 3 | `practice_paper_structure.id` **只有约 56%** 能用稳定 ID 公式复现 | 见 [5.1](#51-structure_id-不变量)（**结论：不影响**） | 无需修复 |

---

## 2. 目标形态：题库即目录

### 2.1 三级目录的推导式

**共同约定**：所有推导都以 `exam_paper.deleted=0 AND exam_paper.exam_type=1` 为根，且排除例题（`type_id_mapping = 'example_question'`）。

#### ① 等级（levels）

不再读 `practice_module_level_config`。**"有题的等级"才存在**：

```sql
SELECT p.version,
       p.level,
       COUNT(DISTINCT p.id) AS paper_count,
       COUNT(q.id)          AS question_count
FROM exam_paper p
JOIN question q ON q.paper_id = p.id
               AND q.deleted = 0
               AND q.section_mapping = #{sectionMapping}          -- 'SEC_READ' / 'SEC_LISTEN' / ...
               AND (q.type_id_mapping IS NULL OR q.type_id_mapping <> 'example_question')
WHERE p.deleted = 0 AND p.exam_type = 1 AND p.version = #{version}
GROUP BY p.version, p.level
HAVING question_count > 0
ORDER BY p.level;
```

- 等级名：`hsk_level_config`（保留）或 `PracticeLevels` 枚举。
- **等级开关的语义变化**：原 `enabled=0` 表示"该等级不可练"→ 新语义为"无题即不可练"；若仍需人工关闭，见 [4.4](#44-人工上下架)。

#### ② 卷（papers）

不再读 `practice_paper_setting`。**"有题的卷"才存在**：

```sql
SELECT p.id AS paper_id, p.source, p.level
FROM exam_paper p
WHERE p.deleted = 0 AND p.exam_type = 1
  AND p.version = #{version} AND p.level = #{level}
  AND EXISTS (
        SELECT 1 FROM question q
        WHERE q.paper_id = p.id AND q.deleted = 0
          AND q.section_mapping = #{sectionMapping}
          AND (q.type_id_mapping IS NULL OR q.type_id_mapping <> 'example_question'))
ORDER BY p.source;
```

> **这一条直接消灭了"空壳卷"问题**：实测那 33 张"有结构无题"的卷，在推导口径下**自动不出现在目录里**，不再依赖 `.filter(total > 0)` 事后兜。

#### ③ 节（parts）

不再读 `practice_paper_structure` / `practice_part_setting`。**节 = `(section_mapping, section)` 分组**：

```sql
SELECT q.section_mapping,
       CAST(q.section AS UNSIGNED)      AS section_code,
       COUNT(*)                          AS question_count,
       MIN(q.section_title)              AS section_title,      -- 天然节标题
       MIN(q.title1_text)                AS module_name,        -- '听力' / '阅读'
       GROUP_CONCAT(DISTINCT q.type_id_mapping) AS type_codes   -- 题型稳定码
FROM question q
WHERE q.paper_id = #{paperId} AND q.deleted = 0
  AND q.section_mapping = #{sectionMapping}
  AND (q.type_id_mapping IS NULL OR q.type_id_mapping <> 'example_question')
GROUP BY q.section_mapping, q.section
ORDER BY section_code;
```

- **节的顺序** = `section` 的数字顺序（不再需要 `sort_order`）。实测 `practice_part_setting.section_code` 与 `question.section` **完全一致**（都是 `1/2/3/4`），说明两者本来就是同一个东西，只是练习侧抄了一份。
- **节名** = `section_title`（见 [2.2](#22-节名与题型名的来源)）。

### 2.2 节名与题型名的来源

这是本方案成立的**关键证据**。实测 `question` 表本身就带着目录所需的全部文本：

| 所需信息 | 题库字段 | 实测取值（HSK2.0 四级第一卷） |
|---|---|---|
| 模块名 | `title1_text` | `听力` / `阅读` |
| **节标题** | `section_title` | `第1-10题:判断对错.`、`第11-25题:请选出正确答案.` |
| 例题标记 | `section_title` = `例题` 且 `number = 0` | 与既有判据一致 |
| 题型（稳定码） | `type_id_mapping` | `listening_judge` / `listening_single` / `reading_word_fill` ... |
| 题型（中文名） | `type_id` | `听力:判断` / `阅读:选词填空` ... |
| 部分号 | `section` | `1` / `2` / `3` / `4` |

> **含义**：`section_title` 本来就是"第 X-Y 题：题型说明"这种**直接可做节标题的文本**，而 `type_id_mapping` 与练习配置里的 `type_code` **取值完全一致**（`listening_judge` / `reading_word_fill` / `write_complete_sent` …）。所以"节名 + 题型名"不需要人工配置。

### 2.3 题数与版本探测

- **题数**：本来就来自 `question`（`selectCountsByParts`），保持不变。
- **版本探测（`dataVersion`）**：

```sql
SELECT GREATEST(
         COALESCE(MAX(updated_time), 0),           -- 由 exam_paper
         0
       ) FROM exam_paper WHERE deleted = 0 AND exam_type = 1
UNION ALL
SELECT COALESCE(MAX(updated_time), 0) FROM question WHERE deleted = 0;
-- 取三轮（exam_paper / question / question_group）的 MAX 再取最大值
```

题库一改 → `dataVersion` 变 → 前端缓存失效。**这是"共用题库"的免费收益**：考试侧导入新卷，练习侧立即跟随，无需任何同步动作。

### 2.4 取题 SQL 的变化

**几乎不变**。现有 `selectByPart` 已经是"按 `paper_id + section_mapping + section` 取题"：

```sql
-- 现状（保留）
SELECT * FROM question
WHERE paper_id = #{paperId} AND section_mapping = #{sectionMapping}
  AND section = #{sectionCode} AND deleted = 0
  AND (type_id_mapping IS NULL OR type_id_mapping <> 'example_question')
ORDER BY number ASC, sort_order ASC, id ASC
```

**唯一的变化是 `sectionCode` 的来源**：以前来自 `practice_part_setting.section_code`（人工配置），现在来自 `GROUP BY question.section`（实时推导）。**SQL 本身不动**。

---

## 3. 逐模块可行性

| 模块 | 题库来源 | 结构能否推导 | 结论 |
|---|---|---|---|
| **阅读** | `question`（`SEC_READ`） | ✅ 节 = `section` 分组，节名 = `section_title` | **可全推导** |
| **听力** | `question`（`SEC_LISTEN`）+ `question_group` + `question_shared_audio` | ✅ 同上；材料音频按 `group_id` 取（`question_shared_audio` 已有 `start_number`/`end_number`） | **可全推导**，但需处理现有 `parts_config` 依赖（见 [4.5](#45-听力-parts_config)） |
| **写作** | `question`（`SEC_WRITE`） | ✅ 节 = `section` 分组；`question_count` 硬校验可改为"以实际题数为准" | **可全推导** |
| **翻译** | `question`（`SEC_TRANSLATION`） | ✅ 同上（当前仅 1 节 / 1 卷） | **可全推导** |
| **口语** | **`speaking_exam_paper_question`**（**不在 `question` 表**） | ❌ 题库不共用 | **除外**：口语仍走 `speaking_exam_paper` + 副本表（另有同步器议题） |

> ⚠️ **口语不适用本方案**。实测 `practice_paper_structure` 里 `SEC_SPEAK` 有 114 行 / 38 卷，但它们对应的题在 `speaking_exam_paper_question`，**`question` 表中只有 5 行 `SEC_SPEAKING`**（HSK7-9 一卷）。口语的"共用题库"是另一件事（需要同步器或改读主表），本文不覆盖。

---

## 4. 缺口与替代方案

"全部由题库推导"会丢掉 5 样东西。逐项给出替代，**全部可解**：

### 4.1 `answer_mode`（可推导）

**现状**：`practice_part_setting.answer_mode` ∈ `SINGLE` / `MATCH` / `ORDER`。

**实测**：按 `type_code` 分组，**`answer_mode` 一对多的 `type_code` 数量 = 0** —— 即 `type_code` → `answer_mode` 是**严格 1:1** 映射。

**替代**：由 `question.type_id_mapping`（= 原 `type_code`）查**题型字典**得出。字典可从现有 `practice_part_setting` 一次性导出（去重后**仅数十行**），以枚举或小字典表承载。

### 4.2 多语言节名 / 题型名

**现状**：`practice_paper_structure.section_name_en/vi`、`practice_part_setting.type_name_en/vi`。

**缺口**：`question` 表**没有**英文/越南文。

**替代（三选一）**：
1. **题型字典表**（推荐）：`practice_question_type_dict(type_code PK, name_zh, name_en, name_vi, answer_mode)` —— 数十行，一次建好长期复用，同时解决 [4.1](#41-answer_mode可推导)；
2. **前端字典**：服务端只回 `type_id_mapping`，多语言交给客户端；
3. **回落到中文**：`Accept-Language=en/vi` 时仍回中文（与现有 `CSCASubjectType` 同款降级）。

> **节标题的多语言**：现有 `parts_config` 里的 `partNameEn/Vi`（"Part 1"/"Phần 1"）本身是**可机械生成**的（"第N部分" → "Part N" / "Phần N"），不需要逐卷配置。

### 4.3 共享选项池 `option_pool`

**现状**：`practice_question_option_pool` 2505 行 / 306 structure，`pool_code` 形如 `SEC_LISTEN_<structureId>_<hash>`。

**实测语义**：同一 `pool_code` 下的题**共享同一组选项**，且这些题**各自带着完全相同的 `option_content`**（示例：`number` 11–15 五题，`group_id` 同为 `2095337767580557313`，`option_content` 逐字相同）。

**替代**：两种都可行 ——
1. 直接用**题自带的 `option_content`**（前端本来就要用它渲染；同一池的题拿到的就是同一份）；
2. 或按 `group_id` 分组，取组内任一题的 `option_content` 作为共享池。

> `pool_code` 中的 hash 段（`b1b4447f...`）可从 `(structure_id, group_id)` 确定性生成，**不承载额外信息**。

### 4.4 人工上下架

**现状**：`practice_paper_setting.enabled` / `visible`（实测 174 行全开；仅 2 行 `enabled=0`，且均已 `deleted=1`）。

**缺口**：题库里没有"这张卷不许练"的表达。

**替代**：
- **默认全开**："有题即可练"（当前无一卷需要人工关闭）；
- 若确需关闭，保留一张**极小的黑名单表**（`practice_hidden_paper(paper_id, reason)`，预计 0–5 行），或复用 `exam_paper` 的既有 `deleted` 语义（**注意**：这会影响考试侧，**不建议**）。

### 4.5 听力 `parts_config`

**现状**：`practice_module_level_config.parts_config`（JSON）**只有 `SEC_LISTEN` 有**（HSK2.0 6 个等级 + HSK3.0 7 个等级）。

其结构为 `[{partName, typeName, sortOrder, partNameEn/Vi, typeNameEn/Vi, questionCount}, ...]`，且**与 `practice_paper_structure` 按序号对齐**（既有"按序号对齐脆弱"的坑）。

**替代**：
- `partName` → `第N部分`（由 `section` 生成）
- `typeName` → 题型字典（[4.2](#42-多语言节名--题型名)）
- `sortOrder` → `section`
- `questionCount` → `COUNT(*)`
- `partNameEn/Vi` / `typeNameEn/Vi` → 机械生成 / 题型字典

> **收益**：顺带消除"`parts_config` 与 structure 按序号对齐"这个**已知脆弱点**（顺序错位就串名）。

---

## 5. 迁移与兼容

### 5.1 `structure_id` 不变量

**这是方案能否零迁移的关键。**

`practice_record.structure_id` 是 `NOT NULL`。现状它指向 `practice_paper_structure.id`。若练习结构不再落表，`structure_id` 必须能**现算**。

**实测稳定 ID 公式**（`SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` 全部命中）：

```
structure_id = 7e18 + int( sha256('structure|<paper_id>|<SEC_XXX>|<section数字>')[:12], 16 ) % 1e18
```

| 验证项 | 结果 |
|---|---|
| 结构表内命中率 | **608 / 1087**（有效且卷存活的结构行）= 约 **56%** |
| **存量 `practice_record` 可复现率** | **98.2%**（859 / 875 条） |
| 不可复现的 16 条 | 均落在"新导入、无人练过"的结构行上 |

> **为什么 56% 也不影响**：不可复现的那 479 行结构，大多是**新导入但还没有任何练习记录**的卷（所以存量记录受影响仅 16 条）。

### 5.2 真正的保险：记录表自带三元组

**决定性事实** —— `practice_record` 与 `practice_answer` **自己就存了**：

| 表 | 关键列 |
|---|---|
| `practice_record` | `paper_id`（NOT NULL）、`section_mapping`（NOT NULL）、`section`（NULL 允许） |
| `practice_answer` | `paper_id`（NOT NULL）、`section_mapping`（NOT NULL）、`section`（NULL 允许） |

也就是说，**`structure_id` 只是一个冗余关联键**：

- **存量记录**：`structure_id` 保持原值，**不回填、不改动**；后续读取时优先用记录自带的 `paper_id + section_mapping + section` 定位节。
- **新记录**：`structure_id` 按 [5.1](#51-structure_id-不变量) 公式现算写入（或从 `paper_id + section_mapping + section` 反算）。
- **断链风险**：**0**。即使某条老记录的 `structure_id` 无法用公式复现，它仍能靠自带三元组正常工作。

> ⚠️ 唯一需要留意的是**阅读**：`practice_answer` 有 5 个快照列（`question_snapshot` / `group_snapshot` / `option_snapshot` / `standard_answer_snapshot` / `analysis_snapshot`），其**完整性硬校验**（行数 == `record.total_questions`）必须保留 —— 本方案不动冻结机制。

### 5.3 灰度与回滚

| 阶段 | 做法 |
|---|---|
| **影子模式** | 新推导逻辑与旧配置逻辑**并行跑**，比对"等级/卷/节/题数"是否一致，只记日志不生效 |
| **按模块灰度** | 先切**阅读**（最简单）→ 再**听力**（含 `parts_config`）→ 再**写作** |
| **回滚** | 配置表**不删**，只停用读取路径；`practice_paper_structure` / `practice_part_setting` 保留为只读备份，随时可切回 |

---

## 6. 改动面（只改练习侧）

### 6.1 会动的

| # | 对象 | 改动 |
|---|---|---|
| 1 | `practice/core/support/PracticeCatalogBatchLoader.java` | 新增"题库推导"路径，替代四层配置装配 |
| 2 | `practice/reading|catalog/...CatalogServiceImpl` | 目录改为调用推导 |
| 3 | `practice/reading|listening|writing/service/...RecordServiceImpl` | `start` 时节的校验改为"按题库存在性" |
| 4 | `practice/listening/...ListeningCatalogServiceImpl` | 去掉 `parts_config` 依赖 |
| 5 | `practice/core/mapper/PracticeQuestionMapper`（+XML） | **新增**一个 `selectPartsByPaper` 分组查询（现有 `selectByPart` 保留） |
| 6 | 新增 `practice/core/support/QuestionTypeDict`（题型字典） | 承载 `type_code → 多语言名 + answer_mode` |
| 7 | 新增 `practice/core/support/QuestionDerivedStructureIds` | `structure_id` 派生（若采用现算） |

### 6.2 一行不动的

| 对象 | 说明 |
|---|---|
| `exam-service/**` | 全部不动 |
| `exam_paper` / `question` / `question_group` / `question_shared_audio` | **题库表只读**，不改一行 |
| `exam_paper_structure` | 考试模板，练习**不读也不用**（避免耦合考试侧结构） |
| `practice_record` / `practice_answer` / `practice_report` | 表结构不动、存量数据不动 |
| `speaking-exam-*` 全链路 | 口语除外 |
| 网关路由 | `/api/practice/**` 已存在 |
| **端点路径与出入参** | **不变**（只改内部实现；节名来源变化见 [4.2](#42-多语言节名--题型名)） |

### 6.3 可以"停读"的表

`practice_paper_setting` / `practice_paper_structure` / `practice_part_setting` / `practice_module_level_config` / `practice_question_option_pool` —— **停读但保留**（回滚保险），观察若干版本后再决定是否物理清理。

---

## 7. 风险登记

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| 1 | 推导结果与现配置**不一致**（节数/节名/题数） | 高 | 影子模式全量比对后再切；差异逐条归因 |
| 2 | 丢失人工上下架能力 | 中 | 默认"有题即上架"；必要时留黑名单表 |
| 3 | 多语言题型名退化 | 中 | 题型字典（[4.2](#42-多语言节名--题型名)） |
| 4 | 听力 `parts_config` 语义丢失（如"含准备时间"等真实业务字段） | 中 | 上线前逐条比对 `parts_config` 字段，确认可机械生成 |
| 5 | 节名依赖 `section_title` 的**数据质量** | 中 | 影子比对；异常回退到"第N部分" |
| 6 | `question` 表被 exam/manage 改结构导致练习取题异常 | 低 | 只 SELECT 白名单列，禁 `SELECT *`；对新增列不敏感 |
| 7 | 写作 `question_count` 硬校验失效 | 低 | 改为"以实际题数为准"，去掉硬校验 |
| 8 | 口语被误纳入 | 低 | 口语**明确排除**（[3](#3-逐模块可行性)） |

---

## 8. 实施步骤

| 阶段 | 内容 | 完成判据 |
|---|---|---|
| **S0** | 导出题型字典（从 `practice_part_setting` 去重 `type_code → type_name*, answer_mode`） | 字典行数 = 去重 `type_code` 数；`answer_mode` 1:1 校验通过 |
| **S1** | 实现推导查询（`selectPartsByPaper`）+ 影子模式开关 | 影子日志可比对 |
| **S2** | 影子比对（全量 136 卷 × 3 模块） | 节数/节名/题型/题数差异清单 = 空（或逐条已归因） |
| **S3** | 阅读切流 | 阅读目录与现网一致；练习/交卷主流程回归通过 |
| **S4** | 听力切流（去 `parts_config` + 材料音频按 `group_id`） | 听力共同材料音频正常；节名/题型与现网一致 |
| **S5** | 写作切流 | 写作冻结快照链路不变；`question_count` 校验改造完成 |
| **S6** | 观察期 + 决定配置表去留 | 无回滚需求后，评估物理清理 |

---

## 附录 A：实测数据表

> 全部来自 TEST 库 `xuexitest`（`8.138.185.11`），只读侦察，G1 `DATABASE()` / G2 `@@hostname` 通过。

| 项 | 实测值 |
|---|---|
| `exam_paper`（`exam_type=1`） | **136** 卷（HSK2.0 **121** + HSK3.0 **15**） |
| `exam_paper`（`exam_type=2`） | 31 卷（CSCA，**不在本文范围**） |
| `question`（HSK） | HSK2.0 **10561** + HSK3.0 **1059** = **11620** 题 |
| `question.section_mapping` 填充率 | HSK2.0 **100%** / HSK3.0 **100%** |
| `question.section_mapping` 取值 | `SEC_LISTEN` / `SEC_READ` / `SEC_WRITE` / `SEC_SPEAKING`(5) / `SEC_TRANSLATION`(4) |
| `exam_paper_structure` | HSK2.0 **48** 行 / HSK3.0 **48** 行（每版本 6 个等级各一套） |
| `practice_paper_structure`（`deleted=0`） | **1201** 行：`SEC_LISTEN` 446/136卷、`SEC_READ` 474/136卷、`SEC_WRITE` 166/93卷、`SEC_SPEAK` 114/38卷、`SEC_TRANSLATION` 1/1卷 |
| `practice_paper_setting` | **174**（`enabled=1 & visible=1 & deleted=0`） |
| `practice_question_option_pool` | **2505** 行 / **306** structure / 覆盖 **2505** 题（所属卷总题 13624） |
| `practice_module_level_config` | **49** 行；`parts_config` **仅 `SEC_LISTEN`** 有 |
| `hsk_level_config` | 13 行 |
| `question_group` / `question_shared_audio` | 1036 / 237 行 |
| `practice_record` / `practice_answer` / `practice_report` | 875 / 6359 / 471 行 |
| ID 公式命中（结构表） | 608 / 1087（约 56%） |
| ID 公式命中（存量 `practice_record`） | **859 / 875 = 98.2%** |
| `type_code → answer_mode` 一对多数量 | **0**（严格 1:1） |

---

## 附录 B：侦察脚本

位于 `D:\code\hsk_treasure\tmp\`（全部只读，带 G1/G2 闸门，可随时复跑）：

| 脚本 | 用途 |
|---|---|
| `_recon_hsk_shared_bank.py` | 卷/题总量、`section_mapping` 填充率、配置覆盖度 |
| `_recon_hsk_shared_bank2.py` | `exam_paper` 分布、两张结构表列定义、`section_mapping` 取值分布 |
| `_recon_hsk_shared_bank3.py` | 考试模板 vs 练习逐卷对比、`practice_part_setting` 粒度 |
| `_recon_hsk_derive.py` | ID 公式验证、`section_title`/`title1_text` 取值、配置覆盖面、逐卷节数对拍 |
| `_recon_hsk_derive2.py` | ID 公式精确定位、ID 命中率、`option_pool` 语义、空壳卷、上下架行 |

复跑命令：

```bash
C:/Users/l/.workbuddy/binaries/python/envs/default/Scripts/python.exe \
    D:/code/hsk_treasure/tmp/_recon_hsk_derive.py
```

---

> **一句话总结**：题库早已共用，重复的是结构层；把结构从"逐卷人工配置"改成"由 `question` 实时推导"，节名（`section_title`）、题型（`type_id_mapping`）、题数（`COUNT(*)`）全都在题库里现成，`answer_mode` 与多语言名靠一张数十行的题型字典补齐，存量记录因自带三元组而**零断链**。改动面 100% 落在 `practice-service`。
