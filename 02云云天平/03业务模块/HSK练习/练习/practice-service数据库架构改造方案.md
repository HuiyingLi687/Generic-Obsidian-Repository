# practice-service 数据库架构问题分析与改造方案

## 一、现状分析

### 1.1 数据库拆分情况

当前项目存在**两个独立数据库**，分别服务于考试模块和练习模块：

| 数据库名 | 服务模块 | 核心数据表 |
|---|---|---|
| `xuexitest` | manage / exam-service | `exam_paper`、`question`、`question_group` 等题目主数据 |
| `hsk_practice` | practice-service | `practice_paper`、`practice_question`、`practice_question_group` 等镜像表 + 练习业务表 |

### 1.2 practice-service 数据库表清单

从 [practice-service 实体包](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity) 可见，共 13 张表：

| 表名 | 实体类 | 类型 | 对应主库表 | 说明 |
|---|---|---|---|---|
| `practice_paper` | [PracticePaper.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticePaper.java) | **镜像表** | `exam_paper` | 试卷主数据，字段完全一致 |
| `practice_question` | [PracticeQuestion.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticeQuestion.java) | **镜像表** | `question` | 题目主数据，字段基本一致，类型不同 |
| `practice_question_group` | [PracticeQuestionGroup.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticeQuestionGroup.java) | **镜像表** | `question_group` | 题组主数据，字段基本一致，类型不同 |
| `practice_answer` | [PracticeAnswer.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticeAnswer.java) | 练习业务表 | — | 用户答案（含题目快照） |
| `practice_record` | [PracticeRecord.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticeRecord.java) | 练习业务表 | — | 练习过程记录 |
| `practice_report` | [PracticeReport.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticeReport.java) | 练习业务表 | — | 练习报告汇总 |
| `practice_paper_setting` | [PracticePaperSetting.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticePaperSetting.java) | 练习配置表 | — | 试卷展示设置（是否启用/可见/排序） |
| `practice_paper_structure` | [PracticePaperStructure.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticePaperStructure.java) | 练习配置表 | — | 试卷结构（多语言支持） |
| `practice_part_setting` | PracticePartSetting.java | 练习配置表 | — | Part 级配置 |
| `practice_question_option_pool` | [PracticeQuestionOptionPool.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticeQuestionOptionPool.java) | 练习配置表 | — | 题目选项池映射 |
| `practice_user_preference` | PracticeUserPreference.java | 用户数据表 | — | 用户练习偏好 |
| `practice_level_config` | [PracticeLevelConfig.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/core/entity/PracticeLevelConfig.java) | 练习配置表 | — | 等级基础配置（多语言） |
| `practice_module_level_config` | PracticeModuleLevelConfig.java | 练习配置表 | — | 模块-等级配置 |

---

## 二、核心架构问题

### 问题1：题目数据双写，一致性无法保证

**表现**：`practice_paper`、`practice_question`、`practice_question_group` 三张表与主库 `exam_paper`、`question`、`question_group` 存储的是**完全相同的业务数据**。

**风险**：
- manage 模块在 `xuexitest` 修改题目后，`hsk_practice` 不会自动同步
- 练习模块用户看到的题目可能是旧数据
- 同一道题在考试和练习中的答案、选项不一致
- 需要人工维护两套数据，操作成本高且容易遗漏

**代码佐证**：
- [ReadingCatalogServiceImpl.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/reading/service/impl/ReadingCatalogServiceImpl.java#L82) 中 `paperMapper` 查询的是 `practice_paper` 表
- [ReadingRecordServiceImpl.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/reading/service/impl/ReadingRecordServiceImpl.java#L56) 中 `questionMapper` 查询的是 `practice_question` 表
- 这意味着题目数据完全独立于主库，互不干扰

### 问题2：字段类型不一致，埋下数据转换隐患

**`number` 字段类型差异**：

| 表 | 字段名 | Java类型 | 数据库类型 |
|---|---|---|---|
| `question`（主库） | `number` | `String` | `varchar` |
| `practice_question`（镜像） | `number` | `Integer` | `int` |

**影响范围**：
- [ReadingRecordServiceImpl.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/reading/service/impl/ReadingRecordServiceImpl.java#L299-L302) 中排序用 `Integer::compareTo`
- [ReadingSubmissionFinalizer.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/reading/service/internal/ReadingSubmissionFinalizer.java#L443-L445) 中排序同样用 `Integer::compareTo`
- 如果未来统一数据源，`Integer` 转 `String` 或反之需要修改大量代码

**`option_content` 字段类型差异**：

| 表 | Java类型 | 处理器 |
|---|---|---|
| `question`（主库） | `String`（存 JSON 字符串） | 无 |
| `practice_question`（镜像） | `PracticeOptionContent`（对象） | `JacksonTypeHandler` |

虽然 MyBatis 的 `JacksonTypeHandler` 可以自动处理 JSON 字段，但两个模块对同一字段的认知不同，后续维护容易出错。

### 问题3：代码重复，维护成本翻倍

**重复实体类**（3个）：
- `PracticePaper` ↔ `ExamPaper`
- `PracticeQuestion` ↔ `Question`
- `PracticeQuestionGroup` ↔ `QuestionGroup`

**重复 Mapper 接口**（3个）：
- `PracticePaperMapper` ↔ `ExamPaperMapper`
- `PracticeQuestionMapper` ↔ `QuestionMapper`
- `PracticeQuestionGroupMapper` ↔ `QuestionGroupMapper`

**重复 Service 逻辑**：
- 题目查询逻辑在两个模块各自实现
- 题组查询逻辑在两个模块各自实现
- 试卷查询逻辑在两个模块各自实现

统计：17 个文件中出现 153 处 `PracticeQuestion/PracticeQuestionGroup/PracticePaper/PracticePaperStructure` 引用，修改字段时需要同步修改两套代码。

### 问题4：数据库连接资源浪费

- practice-service 维护一套独立的 Druid 数据库连接池
- 两个数据库需要分别备份、分别监控、分别调优
- 跨库查询无法用 JOIN，只能通过应用层聚合

### 问题5：ID 主键独立生成，存在冲突风险

- 主库 `question.id` 和镜像库 `practice_question.id` 都使用雪花算法独立生成
- 如果未来做数据合并或迁移，ID 可能冲突
- 练习业务表（`practice_answer.question_id`）引用的是镜像库题目 ID，与主库题目 ID 不对应

**代码佐证**：
- [ReadingSubmissionFinalizer.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/reading/service/internal/ReadingSubmissionFinalizer.java#L208) 中 `PracticeAnswer.questionId` 存的是 `practice_question.id`
- 如果切换到主库 `question.id`，所有历史答案的 `question_id` 都无法对应

### 问题6：配置表与主数据耦合，难以独立管理

`practice_paper_structure`、`practice_paper_setting` 等配置表以 `paper_id` 关联 `practice_paper`，而不是主库的 `exam_paper`：

- 试卷新增/删除时，需要同时维护两套表的关联关系
- `paper_id` 是雪花 ID，两套库的同一试卷 ID 不同，无法直接关联

**代码佐证**：
- [ReadingCatalogServiceImpl.java](file:///c:/Users/l/code/hsk_treasure/practice-service/src/main/java/com/hsktreasure/practice/reading/service/impl/ReadingCatalogServiceImpl.java#L93) 中 `paperMapper.selectById(paperId)` 查询的是镜像库 ID

---

## 三、改造方案（统一数据源）

### 3.1 改造目标

```
改造前：
┌─────────────────────┐    ┌─────────────────────┐
│   xuexitest (主库)   │    │  hsk_practice (镜像库)│
│                     │    │                     │
│  exam_paper         │    │  practice_paper      │ ← 重复
│  question_group     │    │  practice_question_  │ ← 重复
│  question           │    │    group             │
│  ...                │    │  practice_question   │ ← 重复
│                     │    │  practice_answer     │ ← 练习专属
│                     │    │  practice_record     │ ← 练习专属
│                     │    │  practice_report     │ ← 练习专属
│                     │    │  ...其他练习配置表    │
└─────────────────────┘    └─────────────────────┘
        ↑                           ↑
   manage/exam-service        practice-service

改造后：
┌─────────────────────────────────────────────────┐
│              xuexitest (统一主库)                 │
│                                                 │
│  exam_paper          ← 题目数据（唯一来源）       │
│  question_group      ← 题目数据（唯一来源）       │
│  question            ← 题目数据（唯一来源）       │
│  practice_answer     ← 练习业务（迁移）           │
│  practice_record     ← 练习业务（迁移）           │
│  practice_report     ← 练习业务（迁移）           │
│  practice_paper_...  ← 练习配置（迁移，重命名）   │
│  ...其他练习表       ← 练习业务（迁移）           │
└─────────────────────────────────────────────────┘
        ↑                           ↑
   manage/exam-service        practice-service
   （管理题目主数据）         （管理练习业务数据）
```

### 3.2 表归属划分

| 表 | 迁移后位置 | 处理方式 | 说明 |
|---|---|---|---|
| `exam_paper` | xuexitest | **保留** | 主库已有，作为唯一来源 |
| `question` | xuexitest | **保留** | 主库已有，作为唯一来源 |
| `question_group` | xuexitest | **保留** | 主库已有，作为唯一来源 |
| `practice_paper` | — | **删除** | 镜像表，直接用 `exam_paper` |
| `practice_question` | — | **删除** | 镜像表，直接用 `question` |
| `practice_question_group` | — | **删除** | 镜像表，直接用 `question_group` |
| `practice_answer` | xuexitest | **迁移 + 重命名** | 练习业务表，`question_id` 需重新关联主库题目 |
| `practice_record` | xuexitest | **迁移** | 练习业务表 |
| `practice_report` | xuexitest | **迁移** | 练习业务表 |
| `practice_paper_setting` | xuexitest | **迁移** | 练习配置表，`paper_id` 改为关联 `exam_paper.id` |
| `practice_paper_structure` | xuexitest | **迁移** | 练习配置表，`paper_id` 改为关联 `exam_paper.id` |
| `practice_part_setting` | xuexitest | **迁移** | 练习配置表 |
| `practice_question_option_pool` | xuexitest | **迁移 + 重命名** | 练习配置表，`question_id` 需重新关联主库题目 |
| `practice_user_preference` | xuexitest | **迁移** | 用户数据表 |
| `practice_level_config` | xuexitest | **迁移** | 配置表 |
| `practice_module_level_config` | xuexitest | **迁移** | 配置表 |

### 3.3 实体类改造方案

推荐**方式B：修改 Practice 实体的 @TableName（改动最小）**

保留 practice-service 现有的 `PracticeQuestion`、`PracticeQuestionGroup`、`PracticePaper` 实体类名和包路径不变，仅修改 `@TableName` 注解指向主库表，并修复字段类型与主库一致。

```
practice-service/
  └── src/main/java/com/hsktreasure/practice/core/entity/
        ├── PracticeQuestion.java         ← 保留类名
        │     @TableName("question")      ← 原 "practice_question"，改为 "question"
        │     number: String              ← 原 Integer，改为 String（与主库一致）
        │     optionContent: PracticeOptionContent + JacksonTypeHandler（保持不变）
        ├── PracticeQuestionGroup.java    ← 保留类名
        │     @TableName("question_group") ← 原 "practice_question_group"，改为 "question_group"
        └── PracticePaper.java            ← 保留类名
              @TableName("exam_paper")    ← 原 "practice_paper"，改为 "exam_paper"
```

**改造要点**：

1. **仅修改 @TableName 注解**：三个实体类的 `@TableName` 分别指向主库的 `question`、`question_group`、`exam_paper`
2. **保留实体类名**：`PracticeQuestion` 等类名不变，避免大批量修改 import 和类型引用（17 个文件、约 153 处引用）
3. **保留包路径**：继续放在 `com.hsktreasure.practice.core.entity` 包下
4. **修复字段类型**：仅 `PracticeQuestion.number` 需要从 `Integer` 改为 `String`（与主库 `Question.number` 类型一致）
5. **保留 JacksonTypeHandler**：`option_content` 字段继续使用 `PracticeOptionContent` 对象 + `JacksonTypeHandler`，无需改为 String

**优点**：
- 改动最小，只修改 3 个 `@TableName` 注解 + 1 个字段类型
- 不涉及模块依赖关系调整
- 不影响 manage / exam-service 模块
- 17 个文件、约 153 处引用的代码全部无需改动
- 改造风险低、回滚容易

**缺点**：
- 实体类仍然重复（`PracticeQuestion` 与 `Question` 共存）
- 后续新增字段需要同时修改两套实体类
- 类型不一致的隐患仅部分消除（`number` 已统一，但 `option_content` 仍是不同类型）

**适用场景**：
- 希望快速完成数据库统一，降低改造风险
- 暂时不想调整模块依赖关系
- 后续可以再逐步重构到方式A（抽取公共实体）

---

## 四、分阶段改造路线

### 第一阶段：准备工作（低风险）

1. **数据对比**：对比 `xuexitest.question` 与 `hsk_practice.practice_question` 的数据一致性
2. **ID 映射关系建立**：建立 `practice_question.id` ↔ `question.id` 的映射（通过 `paper_id + number` 唯一匹配）

### 第二阶段：代码适配（中风险）

1. **修改 practice-service 数据库配置**：指向 `xuexitest`
2. **修改实体类 @TableName**：
   - `PracticeQuestion` → 修改 `@TableName("question")`
   - `PracticeQuestionGroup` → 修改 `@TableName("question_group")`
   - `PracticePaper` → 修改 `@TableName("exam_paper")`
3. **修复字段类型**：`PracticeQuestion.number` 从 `Integer` 改为 `String`，修改所有引用处的排序/比较逻辑
4. **option_content 处理**：保持现状，继续使用 `PracticeOptionContent` + `JacksonTypeHandler`

### 第三阶段：数据迁移（高风险）

1. **迁移练习业务表到主库**：
   - `practice_answer`、`practice_record`、`practice_report`
   - `practice_paper_setting`、`practice_paper_structure`、`practice_part_setting`
   - `practice_question_option_pool`、`practice_user_preference`
   - `practice_level_config`、`practice_module_level_config`
2. **修复关联 ID**：
   - `practice_answer.question_id`、`practice_answer.paper_id` → 用映射表转换为主库 ID
   - `practice_record.paper_id`、`practice_record.structure_id` → 用映射表转换
   - 所有 `paper_id` 关联字段重新指向 `exam_paper.id`
3. **验证数据完整性**：检查所有外键关联是否正确

### 第四阶段：清理收尾（低风险）

1. **保留 Practice 实体类**：`PracticeQuestion`、`PracticeQuestionGroup`、`PracticePaper` 类名和包路径不变，仅 `@TableName` 指向主库表
2. **删除镜像库**：`DROP DATABASE hsk_practice`（先备份）
3. **更新文档**：更新数据库设计文档、接口文档
4. **（可选）后续重构**：如需进一步消除代码重复，可后续逐步重构到方式A（抽取公共实体到 common 模块）

---

## 五、风险与应对

| 风险 | 等级 | 应对措施 |
|---|---|---|
| 数据迁移后 ID 不对应 | 高 | 迁移前用 `paper_id + number` 建立完整映射表，逐条验证 |
| `number` 类型转换错误 | 中 | 全局搜索 `getNumber()` 的 Integer 用法，逐一修改，编写单元测试验证排序 |
| 迁移期间数据不一致 | 中 | 选择低峰期迁移，迁移期间暂停练习模块写入，迁移完成后双写验证 |
| 回滚困难 | 高 | 迁移前完整备份 `hsk_practice`，出问题可快速回滚 |
| 配置表关联失效 | 中 | 迁移后检查 `practice_paper_setting`、`practice_paper_structure` 的 `paper_id` 能否正确关联 `exam_paper` |

---

## 六、改造收益

| 指标 | 改造前 | 改造后 | 收益 |
|---|---|---|---|
| 数据库数量 | 2 个 | 1 个 | 减少运维成本 |
| 题目表数量 | 6 张（3主+3镜像） | 3 张 | 减少 50% |
| 重复实体类 | 6 个 | 3 个 | 减少 50% |
| 重复 Mapper | 6 个 | 3 个 | 减少 50% |
| 数据一致性 | 需要人工同步 | 天然一致 | 消除数据不一致风险 |
| 字段类型 | 两套（String vs Integer） | 一套（统一 String） | 消除类型转换隐患 |
| 新字段开发成本 | 修改两套代码 | 修改一套代码 | 效率提升 50% |

---

## 七、当前代码引用统计

以下是 practice-service 中对镜像表相关类的引用情况（供改造工作量评估）：

| 类名 | 引用文件数 | 出现次数 | 主要使用位置 |
|---|---|---|---|
| `PracticeQuestion` | 7 | — | ReadingRecordServiceImpl、ReadingAnswerServiceImpl、ReadingSubmissionFinalizer |
| `PracticeQuestionGroup` | 4 | — | ReadingRecordServiceImpl、ReadingSubmissionFinalizer |
| `PracticePaper` | 5 | — | ReadingCatalogServiceImpl、ReadingRecordServiceImpl |
| `PracticePaperStructure` | 5 | — | ReadingCatalogServiceImpl、ReadingRecordServiceImpl |
| 合计 | 17 文件 | 约 153 处 | — |

> 数据来源：`practice-service` 代码库全文检索
