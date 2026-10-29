# practice_paper_structure 补卷逻辑说明

> 目标：把「`exam_paper` 里存在、但 `practice_paper_structure` 里一张结构记录都没有」的 HSK 卷子，
> 按其等级固定的 Part 模板，补生成结构记录。
>
> **实现方式已从「纯 SQL」改为「应用层一次性批量方法」**（用户要求走 `IdWorker.getId()` 生成雪花主键）。
> 核心逻辑（判定口径、Part 模板、字段映射）与本文档一致，仅 id 生成方式从 SQL 的 `ROW_NUMBER` 改为 `IdWorker.getId()`。

## 一、核心口径

| 项 | 结论 |
|---|---|
| practice 端试卷表 | `PracticePaper` 直接 `@TableName("exam_paper")`，即练习端复用考试卷表 |
| `practice_paper_structure.paper_id` | 直接等于 `exam_paper.id` |
| 「一张卷子」判定 | `exam_paper.id`（业务键 `source` 是试卷编号如 `HSK1_H10901`） |
| 「缺结构」判定 | `exam_paper.exam_type=1 AND deleted=0`，且 `practice_paper_structure` 中无任何 `deleted=0` 的同 `paper_id` 记录 |
| 补充范围 | 仅 HSK（`exam_type=1`）。CSCA（`exam_type=2`）不参与（见 `SharedPaperEligibility`：`exam_type==1` 才算有资格发布） |

## 二、当前数据差距

- `exam_paper`：HSK 每等级 20 张（HSK5 为 21 张）。
- `practice_paper_structure`：每等级仅发布了 **10 张**卷子的结构。
- **缺 61 张**：HSK1~4、6 各 10 张，HSK5 缺 11 张。

## 三、每等级 Part 固定模板（由现有数据反推）

一张卷子在 `practice_paper_structure` 里是「多个 Part」记录，按 `sort_order` 全局递增。
字段取值规律：

- `content_name`：SEC_LISTEN=听力，SEC_READ=阅读，SEC_WRITE=**书写**（注意不是「写作」）。
- `section_name`：听力/书写用「第N部分」，阅读用中文「第一部分~第四部分」。
- `duration_minutes`：仅每个模块**第一个 part** 有值（= 该模块总时长），其余为 0。
- `full_score`：听力/书写为 NULL；阅读按题量分配。
- `sort_order`：听力从 1 起 → 阅读接续 → 书写固定从 21 起（中间留空）。

完整模板（`content_type | section_name | question_count | duration_minutes | sort_order | full_score`）：

| 等级 | 模板 Part 序列 |
|---|---|
| HSK1 | 听力 第1~4部分(各5题) → 阅读 第一~四部分(各5题,25分，第一部分时长17) |
| HSK2 | 听力 第1~3部分(10题)+第4部分(5题) → 阅读 第一~三部分(5题,20分)+第四部分(10题,40分，第一部分时长22) |
| HSK3 | 听力 第1~4部分(各10题) → 阅读 第一~三部分(各10题,33.33/33.33/33.34分，第一部分时长30) → 书写 第1~2部分(各5题) |
| HSK4 | 听力 第1(10)+第2(15)+第3(20) → 阅读 第一(10,25分)+第二(10,25分)+第三(20,50分，第一部分时长40) → 书写 第1(10)+第2(5) |
| HSK5 | 听力 第1(20)+第2(25) → 阅读 第一(15,33.33)+第二(10,22.22)+第三(20,44.45，第一部分时长45) → 书写 第1(8)+第2(2) |
| HSK6 | 听力 第1(15)+第2(15)+第3(20) → 阅读 第一~三部分(各10,20分)+第四部分(20,40分，第一部分时长50) → 书写 第1(1) |

## 四、字段映射（生成 INSERT 的取值来源）

| practice_paper_structure 字段 | 取值 |
|---|---|
| `id` | 雪花主键（见第五节） |
| `paper_id` | `exam_paper.id` |
| `version` | `exam_paper.version`（如 `HSK2.0`） |
| `hsk_level` | `exam_paper.level` |
| `paper_name` | `exam_paper.source`（如 `HSK3_H31001`） |
| `content_type` / `content_name` / `section_name` | 模板固定值 |
| `question_count` / `duration_minutes` / `sort_order` / `full_score` | 模板固定值 |
| `description` | NULL |
| `subject_type_mapping` | NULL（HSK 不用） |
| `created_time` / `updated_time` | 执行时 `UNIX_TIMESTAMP()` |
| `deleted` | 0 |
| `created_by` / `update_by` | NULL（或沿用系统管理员 id `2057361044495556609`） |

## 五、ID 生成策略（已改为应用层雪花）

`practice_paper_structure.id` 是雪花 ID，应用层 `IdType.ASSIGN_ID`（`IdWorker`）生成，
**数据库没有默认值**。最终采用应用层一次性批量方法：

- 核心类：`PracticePaperStructureBackfillService`（`practice-service` 的 `core/support` 包）。
- id 用 `com.baomidou.mybatisplus.core.toolkit.IdWorker.getId()` 生成（标准雪花，与全项目其他实体一致）。
- 通过 `PracticePaperStructureMapper.insert(...)` 逐条插入，走 MyBatis-Plus 的 `FieldFill` 审计字段填充。
- 触发入口：`PaperStructureBackfillController`（`POST /backfill/paper-structure`），跑完核对后可整体删除。

> 注：本方法为一次性修复用途，不建议接入正常业务链路。审计字段 `created_by`/`update_by` 在无请求上下文时
> `ThreadLocal` 为 null，故方法内已显式写死为 `1L`（系统管理员），`created_time`/`updated_time` 用当前时间戳。

## 六、幂等性

`INSERT ... SELECT` 带 `NOT EXISTS (SELECT 1 FROM practice_paper_structure s WHERE s.paper_id=p.id AND s.deleted=0)`，
只对「尚无结构记录」的卷子生成，重复执行不会产生重复数据。

## 七、执行前校验（建议）

1. 先跑 SQL 顶部注释里的 `SELECT COUNT(*)` 预览，确认预计新增条数 = 61 张卷 × 各等级 part 数。
   各等级 part 数：HSK1=8、HSK2=8、HSK3=9、HSK4=8、HSK5=7、HSK6=8。
   预计总数 = 10×8 + 10×8 + 10×9 + 10×8 + 11×7 + 10×8 = 80+80+90+80+77+80 = **487 条**。
2. 执行后校验：`practice_paper_structure` 的 distinct `paper_id` 数应从 93 增至 154（+61）。
