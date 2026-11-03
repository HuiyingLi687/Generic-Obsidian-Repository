---
tags: [算法, HSK, 取卷]
project: 汉考宝
updated: 2026-11-03
---

# HSK 取卷与判分

> 讲述「用户点开始考试 → 屏幕上有题」这条链路，以及「用户点提交 → 分数怎么来」。
> 全部结论来自 `exam-service` 源码实测，行号以 2026-11-03 的 `ExamRecordServiceImpl` 为准。

## 一、开考：选卷（`startExam`，`ExamRecordServiceImpl:212`）

```
POST /exam/record/start
  ① 校验 version / level / userId 非空
  ② 续考优先：按 user_id + exam_paper.version/level + exam_record.status=0 查
        命中 → 刷新 exam_section_timer.last_answer_time → 直接返回，不重新取题
  ③ 次数校验：level ∈ {1,2} 走免费次数；其余扣点数（hsk_exam = 2 点）
  ④ 选卷：selectUntakenPaper（level 等值 + 排除 user_taken_paper，LIMIT 1）
        没有未考过的卷 → 删掉该用户该等级的全部 user_taken_paper → 随机抽一张
  ⑤ 取题：selectByPaperId（排除例题）
  ⑥ 建 exam_record（status=0、current_question_number=1）
  ⑦ initAnswerCard 给正题逐题插 exam_answer（例题不建行）
  ⑧ 写 user_taken_paper、扣次数/点数
```

🔴 选卷 SQL 用 `a.level = #{level}` **等值比较**，且**不带 `exam_type`**：
- HSK 7-9 的卷侧 level 是 `'7-9'`，前端必须传字符串 `'7-9'`，传 `7` 取不到卷
- 因此 `getLevel()` 不能 `Integer.parseInt`（会抛 `NumberFormatException`）

## 二、取题 SQL

```sql
-- 正题（selectByPaperId）
SELECT * FROM question
WHERE paper_id = ? AND deleted = 0
  AND (type_id_mapping IS NULL OR type_id_mapping != 'example_question')
ORDER BY sort_order ASC, number ASC;

-- 例题（selectExampleQuestionsByPaperId）
SELECT * FROM question
WHERE paper_id = ? AND type_id_mapping = 'example_question' AND deleted = 0
ORDER BY sort_order ASC, number ASC;
```

正题与例题**同表**，只靠 `type_id_mapping` 分开。取正题时漏掉那个 `!=` 条件，例题就会混进答题卡。

## 三、下发整卷：两个接口并存

| 接口 | 方法 | 例题 |
|---|---|---|
| `GET /exam/answer/paper/detail/{paperId}` | `getPaperDetailWithAnswers:2745` | 不返回 |
| `GET /exam/answer/paper/detail/v1/{paperId}` | `getPaperDetailWithAnswersV1:2977` | 挂在 `section.exampleQuestions` |

装配六步（两个接口基本一致）：

1. **分节模板按 `version + hsk_level` 查，不看 `paper_id`** —— 同版本同等级所有卷共用一套节次与时长。
   实测 HSK2.0 一级：8 行结构（4 part × 2 节），每行 `full_score=25`（求和得听力/阅读各 100），
   `duration_minutes` 只写在每节首行（15 / 17 分钟）。
2. **题归哪一节**：`q.section != null` → 比 `section_mapping`；否则 `q.group_id != null` → 看是否落在该节题组；
   **两者都空直接丢弃**（实测 HSK 0 条，但代码无兜底）。
3. **题组覆盖面题**：`audioUrl` / `passage` / `optionContent` 三样，组里有值就覆盖本题值
   （听力整卷音频挂组上，本题侧为空）。
4. `content` 为空时，从 `section_title` 冒号后截一段兜底。
5. 例题（仅 V1）：按 `sectionMapping` 挂到对应节，`beforeNumber` = 该节第一道正题的题号。
6. 汇总 `sectionScore` / `totalScore` / `totalQuestions` 返回，附用户已答内容与标记。

## 四、判分：HSK 是**前端判**，后端只存结果

🔴 这是最容易误解的一点。`ExamAnswerServiceImpl.submit:61`：

```java
examAnswer.setIsCorrect(request.getIsCorrect() != null ? request.getIsCorrect() : 0);
```

`isCorrect` **直接取请求里的值落库**，后端不比对答案。配套证据：

- 下发接口把 `answer` 和 `analysis` 一并塞进 `QuestionWithAnswer`（`:2909`、`:3148`）—— 前端要拿它判分；
- 答题卡 `initAnswerCard` 只建行、不算分；
- 只有 CSCA 侧有 `CscaAnswerGrader` 在后端判分。

> 所以「考试中能拿到标准答案」**不是漏洞，是判分架构的一部分**。
> 想改成后端判分 → 必须先补一条判分链路，才能去掉下发里的 `answer`；单独删 `answer` 会直接把判分打断。

### 4.1 已知的判分口径坑（改判分逻辑前必读）

| 题型 | 坑 |
|---|---|
| 连词成句（`order` 侧 `write_complete_sent`） | 答案句末是**半角点** `.`（468 条里 436 条）；**1 条 `answer` 用 `/` 存了两个都算对的答案**（`2074672640467652630`）→ 比对前先按 `/` 拆、统一标点 |
| 句子排序（`order` 侧 `reading_sort`） | 答案是字母序列 `BAC`，不是句子 |
| 成篇写作 / 笔译 | `answer` 是占位「略/（略）」71 条，**不能当评分依据** → 走独立评价策略 |
| 句池类（`reading_sent_fill`） | 项数 3/4/5/6，通常等于组内题数、一对一**无重复**（仅 2 组 6 选 5）→ 判分别要求唯一性 |
| 分值 | 真源 `question.score`；HSK **每模块恒 100**，不是按题累加 |

## 五、现状的五个已知问题

| # | 问题 | 位置 | 影响 |
|--:|---|---|---|
| 1 | 例题把标准答案当用户答案：`.userAnswer(question.getAnswer())` | `:3234` | 前端若按 `userAnswer` 判「已答」会误判 |
| 2 | `Integer.parseInt(paper.getLevel())` | `:2760`、`:2986`、`:3266` | HSK 7-9（`'7-9'`）开考/取卷**直接崩** |
| 3 | `selectByPaperAndUser` 无 `LIMIT 1`（`WHERE paper_id + user_id + status=0`） | `ExamRecordMapper.xml` | 同一卷存在两条进行中记录 → `TooManyResultsException`；CSCA 已改用 `recordId`，HSK 未改 |
| 4 | 老接口与 V1 并存，前端用哪个不明确 | — | 老接口不返例题 → 例题页空白 |
| 5 | 排序 comparator 里 `try/catch NumberFormatException` 是死代码 | `:2921`、`:3169` | 无功能影响，`number` 是 Integer |

## 六、相关文档

- [[00字段红线索引]] —— 这些字段的类型与陷阱
- [[01CSCA考试关键约束]] —— CSCA 那套完全不同（后端判分、三段事务）
- [[题库-考试布局字段]] —— 下发时该带哪个布局值
