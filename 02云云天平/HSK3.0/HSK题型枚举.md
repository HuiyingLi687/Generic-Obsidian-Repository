# HSK 3.0 题型枚举清单

> 用途：写代码枚举（Java / TypeScript / DB 字典）时直接取用。
> **入库值建议直接用「显示名」列的原串**（形如 `听力:看图选择`），与提取表 `题型*`（C 列）完全一致。

## 一、数据来源与口径

| 项 | 说明 |
|---|---|
| 采样范围 | `C:\workbuddy\HSK3.0` 下全部 **22 份** 17 列提取表（HSK1–HSK7-9 的 `HSKn_样卷.xlsx` + `HSKn_模拟卷n.xlsx`，已跳过 `_backup`） |
| 取值列 | `题型*`（C 列）原始字符串 |
| 字符串格式 | `模块:题型`（半角冒号，无空格） |
| 统计口径 | 按 `题目分组`（G 列）的**题号范围求并集**（一行可能代表多道题） |
| 合计 | **6 个模块 / 31 个题型** |

## 二、总览

| 模块 | 题型数 | 枚举前缀 | code 前缀 | 适用级别 |
|---|---|---|---|---|
| 听力 | 7 | `LISTENING_` | `listening_` | HSK1 – HSK7-9 |
| 阅读 | 10 | `READING_` | `reading_` | HSK1 – HSK7-9 |
| 书写 | 3 | `HANDWRITING_` | `handwriting_` | 仅 HSK2、HSK3 |
| 写作 | 6 | `WRITING_` | `writing_` | HSK4 – HSK7-9 |
| 翻译 | 2 | `TRANSLATION_` | `translation_` | 仅 HSK7-9 |
| 口语 | 3 | `SPEAKING_` | `speaking_` | 仅 HSK7-9 |

> ⚠️ **书写 ≠ 写作**：HSK2/HSK3 的第三模块叫「书写」，HSK4 及以上叫「写作」，是**两个独立模块名**。
> 其中「看图用词造句」在两个模块下都出现，需保留**两个**枚举值。

---

## 三、听力模块（7 个）

| 枚举常量 | code | 显示名（入库值） | 出现位置 | 题号范围 |
|---|---|---|---|---|
| `LISTENING_PIC_CHOICE` | `listening_pic_choice` | `听力:看图选择` | HSK1 P1、HSK2 P1 | 1–5 |
| `LISTENING_DETAIL_CHOICE` | `listening_detail_choice` | `听力:细节选择` | HSK1 P2/P4、HSK3 P3、HSK4 P2、HSK5 P1/P2、HSK6 P1/P2 | 1–35 |
| `LISTENING_IMG_MATCH` | `listening_img_match` | `听力:图片匹配` | HSK1 P3、HSK2 P2、HSK3 P1 | 1–15 |
| `LISTENING_DIALOG_CHOICE` | `listening_dialog_choice` | `听力:对话选择` | HSK2 P3、HSK3 P2、HSK4 P1 | 1–25 |
| `LISTENING_JUDGE` | `listening_judge` | `听力:判断` | HSK7-9 P1 | 1–10 |
| `LISTENING_CHOICE_FILL` | `listening_choice_fill` | `听力:选择/填空` | HSK7-9 P2/P3 | 11–40 |
| `LISTENING_PASSAGE` | `listening_passage` | `听力:阅读理解` | HSK6 P3 | 29–40 |

```java
// ========== 听力模块 ==========
LISTENING_PIC_CHOICE("listening_pic_choice", "听力:看图选择"),
LISTENING_DETAIL_CHOICE("listening_detail_choice", "听力:细节选择"),
LISTENING_IMG_MATCH("listening_img_match", "听力:图片匹配"),
LISTENING_DIALOG_CHOICE("listening_dialog_choice", "听力:对话选择"),
LISTENING_JUDGE("listening_judge", "听力:判断"),
LISTENING_CHOICE_FILL("listening_choice_fill", "听力:选择/填空"),
LISTENING_PASSAGE("listening_passage", "听力:阅读理解"),
```

---

## 四、阅读模块（10 个）

| 枚举常量 | code | 显示名（入库值） | 出现位置 | 题号范围 |
|---|---|---|---|---|
| `READING_IMG_MATCH` | `reading_img_match` | `阅读:图片匹配` | HSK1 P1、HSK2 P1 | 21–30 |
| `READING_SENT_MATCH` | `reading_sent_match` | `阅读:句子匹配` | HSK1 P2、HSK2 P3、HSK3 P1 | 26–45 |
| `READING_CLOZE` | `reading_cloze` | `阅读:完形填空` | HSK1 P3、HSK2 P2、HSK3 P2、HSK4 P1 | 31–50 |
| `READING_DETAIL_CHOICE` | `reading_detail_choice` | `阅读:细节选择` | HSK1 P4、HSK2 P4、HSK3 P3、HSK4 P2 | 36–60 |
| `READING_FILL` | `reading_fill` | `阅读:阅读填空` | HSK5 P1 | 36–45 |
| `READING_SORT` | `reading_sort` | `阅读:段落排序` | HSK5 P2、HSK7-9 P2 | 46–66 |
| `READING_PASSAGE_CHOICE` | `reading_passage_choice` | `阅读:文章选择` | HSK5 P3、HSK6 P3、HSK7-9 P1 | 41–80 |
| `READING_WORD_FILL` | `reading_word_fill` | `阅读:选词填空` | HSK6 P1 | 41–50 |
| `READING_SENT_FILL` | `reading_sent_fill` | `阅读:选句填空` | HSK4 P3、HSK6 P2 | 51–64 |
| `READING_SHORT_ANSWER` | `reading_short_answer` | `阅读:文章简答` | HSK7-9 P3 | 67–80 |

```java
// ========== 阅读模块 ==========
READING_IMG_MATCH("reading_img_match", "阅读:图片匹配"),
READING_SENT_MATCH("reading_sent_match", "阅读:句子匹配"),
READING_CLOZE("reading_cloze", "阅读:完形填空"),
READING_DETAIL_CHOICE("reading_detail_choice", "阅读:细节选择"),
READING_FILL("reading_fill", "阅读:阅读填空"),
READING_SORT("reading_sort", "阅读:段落排序"),
READING_PASSAGE_CHOICE("reading_passage_choice", "阅读:文章选择"),
READING_WORD_FILL("reading_word_fill", "阅读:选词填空"),
READING_SENT_FILL("reading_sent_fill", "阅读:选句填空"),
READING_SHORT_ANSWER("reading_short_answer", "阅读:文章简答"),
```

---

## 五、书写模块（3 个 · 仅 HSK2/HSK3）

| 枚举常量 | code | 显示名（入库值） | 出现位置 | 题号范围 |
|---|---|---|---|---|
| `HANDWRITING_COMP_CHOICE` | `handwriting_comp_choice` | `书写:汉字部件选择` | HSK2 P1 | 51–55 |
| `HANDWRITING_CHAR_WRITE` | `handwriting_char_write` | `书写:汉字书写` | HSK2 P2、HSK3 P1 | 56–65 |
| `HANDWRITING_PIC_SENTENCE` | `handwriting_pic_sentence` | `书写:看图用词造句` | HSK3 P2 | 66–70 |

```java
// ========== 书写模块（仅 HSK2/HSK3）==========
HANDWRITING_COMP_CHOICE("handwriting_comp_choice", "书写:汉字部件选择"),
HANDWRITING_CHAR_WRITE("handwriting_char_write", "书写:汉字书写"),
HANDWRITING_PIC_SENTENCE("handwriting_pic_sentence", "书写:看图用词造句"),
```

---

## 六、写作模块（6 个 · HSK4 起）

| 枚举常量 | code | 显示名（入库值） | 出现位置 | 题号范围 |
|---|---|---|---|---|
| `WRITING_PIC_SENTENCE` | `writing_pic_sentence` | `写作:看图用词造句` | HSK4 P1 | 65–69 |
| `WRITING_SHORT_ESSAY` | `writing_short_essay` | `写作:短文写作` | HSK4 P2 | 70 |
| `WRITING_PIC_WRITE` | `writing_pic_write` | `写作:看图写作` | HSK5 P1 | 71 |
| `WRITING_TOPIC_ESSAY` | `writing_topic_essay` | `写作:话题作文` | HSK5 P2、HSK6 P2、HSK7-9 P2 | 72–82 |
| `WRITING_PRACTICAL` | `writing_practical` | `写作:应用文写作` | HSK6 P1 | 81 |
| `WRITING_CHART_ANALYSIS` | `writing_chart_analysis` | `写作:图表描述与分析` | HSK7-9 P1 | 81 |

```java
// ========== 写作模块 ==========
WRITING_PIC_SENTENCE("writing_pic_sentence", "写作:看图用词造句"),
WRITING_SHORT_ESSAY("writing_short_essay", "写作:短文写作"),
WRITING_PIC_WRITE("writing_pic_write", "写作:看图写作"),
WRITING_TOPIC_ESSAY("writing_topic_essay", "写作:话题作文"),
WRITING_PRACTICAL("writing_practical", "写作:应用文写作"),
WRITING_CHART_ANALYSIS("writing_chart_analysis", "写作:图表描述与分析"),
```

---

## 七、翻译模块（2 个 · 仅 HSK7-9）

| 枚举常量 | code | 显示名（入库值） | 出现位置 | 题号范围 |
|---|---|---|---|---|
| `TRANSLATION_WRITTEN` | `translation_written` | `翻译:笔译` | HSK7-9 P1 | 83–84 |
| `TRANSLATION_ORAL` | `translation_oral` | `翻译:口译` | HSK7-9 P2 | 85–86 |

```java
// ========== 翻译模块（仅 HSK7-9）==========
TRANSLATION_WRITTEN("translation_written", "翻译:笔译"),
TRANSLATION_ORAL("translation_oral", "翻译:口译"),
```

---

## 八、口语模块（3 个 · 仅 HSK7-9）

| 枚举常量 | code | 显示名（入库值） | 出现位置 | 题号范围 |
|---|---|---|---|---|
| `SPEAKING_READ_ALOUD` | `speaking_read_aloud` | `口语:应用读说` | HSK7-9 P1 | 87 |
| `SPEAKING_LISTEN_ANSWER` | `speaking_listen_answer` | `口语:听材料回答问题` | HSK7-9 P2 | 88–90 |
| `SPEAKING_OPINION` | `speaking_opinion` | `口语:观点表达` | HSK7-9 P3 | 91 |

```java
// ========== 口语模块（仅 HSK7-9）==========
SPEAKING_READ_ALOUD("speaking_read_aloud", "口语:应用读说"),
SPEAKING_LISTEN_ANSWER("speaking_listen_answer", "口语:听材料回答问题"),
SPEAKING_OPINION("speaking_opinion", "口语:观点表达"),
```

---

## 九、完整枚举（可直接粘贴）

```java
package com.hsk.question.enums;

import java.util.HashMap;
import java.util.Map;

/**
 * HSK 3.0 题型枚举（6 模块 / 31 题型）
 * 数据来源：HSK3.0 提取表「题型*」列，格式 "模块:题型"
 */
public enum HskQuestionType {

    // ========== 听力模块 ==========
    LISTENING_PIC_CHOICE("listening_pic_choice", "听力:看图选择"),
    LISTENING_DETAIL_CHOICE("listening_detail_choice", "听力:细节选择"),
    LISTENING_IMG_MATCH("listening_img_match", "听力:图片匹配"),
    LISTENING_DIALOG_CHOICE("listening_dialog_choice", "听力:对话选择"),
    LISTENING_JUDGE("listening_judge", "听力:判断"),
    LISTENING_CHOICE_FILL("listening_choice_fill", "听力:选择/填空"),
    LISTENING_PASSAGE("listening_passage", "听力:阅读理解"),

    // ========== 阅读模块 ==========
    READING_IMG_MATCH("reading_img_match", "阅读:图片匹配"),
    READING_SENT_MATCH("reading_sent_match", "阅读:句子匹配"),
    READING_CLOZE("reading_cloze", "阅读:完形填空"),
    READING_DETAIL_CHOICE("reading_detail_choice", "阅读:细节选择"),
    READING_FILL("reading_fill", "阅读:阅读填空"),
    READING_SORT("reading_sort", "阅读:段落排序"),
    READING_PASSAGE_CHOICE("reading_passage_choice", "阅读:文章选择"),
    READING_WORD_FILL("reading_word_fill", "阅读:选词填空"),
    READING_SENT_FILL("reading_sent_fill", "阅读:选句填空"),
    READING_SHORT_ANSWER("reading_short_answer", "阅读:文章简答"),

    // ========== 书写模块（仅 HSK2/HSK3）==========
    HANDWRITING_COMP_CHOICE("handwriting_comp_choice", "书写:汉字部件选择"),
    HANDWRITING_CHAR_WRITE("handwriting_char_write", "书写:汉字书写"),
    HANDWRITING_PIC_SENTENCE("handwriting_pic_sentence", "书写:看图用词造句"),

    // ========== 写作模块（HSK4 起）==========
    WRITING_PIC_SENTENCE("writing_pic_sentence", "写作:看图用词造句"),
    WRITING_SHORT_ESSAY("writing_short_essay", "写作:短文写作"),
    WRITING_PIC_WRITE("writing_pic_write", "写作:看图写作"),
    WRITING_TOPIC_ESSAY("writing_topic_essay", "写作:话题作文"),
    WRITING_PRACTICAL("writing_practical", "写作:应用文写作"),
    WRITING_CHART_ANALYSIS("writing_chart_analysis", "写作:图表描述与分析"),

    // ========== 翻译模块（仅 HSK7-9）==========
    TRANSLATION_WRITTEN("translation_written", "翻译:笔译"),
    TRANSLATION_ORAL("translation_oral", "翻译:口译"),

    // ========== 口语模块（仅 HSK7-9）==========
    SPEAKING_READ_ALOUD("speaking_read_aloud", "口语:应用读说"),
    SPEAKING_LISTEN_ANSWER("speaking_listen_answer", "口语:听材料回答问题"),
    SPEAKING_OPINION("speaking_opinion", "口语:观点表达"),
    ;

    /** 代码标识，入库/接口传输用 */
    private final String code;
    /** 显示名，与提取表「题型*」列原串完全一致 */
    private final String display;

    HskQuestionType(String code, String display) {
        this.code = code;
        this.display = display;
    }

    public String getCode() {
        return code;
    }

    public String getDisplay() {
        return display;
    }

    /** 所属模块名，如「听力」 */
    public String getModule() {
        return display.substring(0, display.indexOf(':'));
    }

    /** 题型名（不含模块前缀），如「看图选择」 */
    public String getTypeName() {
        return display.substring(display.indexOf(':') + 1);
    }

    private static final Map<String, HskQuestionType> BY_CODE = new HashMap<>();
    private static final Map<String, HskQuestionType> BY_DISPLAY = new HashMap<>();

    static {
        for (HskQuestionType t : values()) {
            BY_CODE.put(t.code, t);
            BY_DISPLAY.put(t.display, t);
        }
    }

    public static HskQuestionType ofCode(String code) {
        return BY_CODE.get(code);
    }

    public static HskQuestionType ofDisplay(String display) {
        return BY_DISPLAY.get(display);
    }
}
```

---

## 十、配套：模块枚举（可选）

```java
public enum HskModule {
    LISTENING("听力"),
    READING("阅读"),
    HANDWRITING("书写"),
    WRITING("写作"),
    TRANSLATION("翻译"),
    SPEAKING("口语"),
    ;

    private final String name;

    HskModule(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

---

## 十一、注意事项

1. **「书写」与「写作」不要合并**：这是两个不同模块名（HSK2/HSK3 用「书写」，HSK4 起用「写作」），
   `书写:看图用词造句` 与 `写作:看图用词造句` 必须各占一个枚举值。
2. **入库值直接用「模块:题型」原串**（如 `听力:看图选择`），不要自己拼接或改写顺序，
   否则与提取表的 `题型*` 列对不上。
3. **`听力:选择/填空` 含斜杠**：作为 URL 路径或文件名时要转义；作为 DB 值/枚举 display 没问题，
   其 code 用 `listening_choice_fill`。
4. **同一题型可跨级别复用**：例如 `听力:细节选择` 同时用于 HSK1/3/4/5/6，
   `写作:话题作文` 同时用于 HSK5/6/7-9；枚举是"题型字典"，级别另存字段。
5. **完整表结构参见**：`HSK新旧大纲对比(1).xlsx`（含各级模块×部分的题型与题量，
   注意该表 HSK5 听力/阅读与 HSK2-3 模块名有 3 处与真实样卷不符，以样卷为准）。
6. **本文档的生成/复核脚本**（可随时重跑核对）：
   - `_scan_all_tixing.py` —— 全量扫描出 31 个题型与所属模块
   - `_detail_tixing_locs.py` —— 输出每个题型的「级别-部分」明细

---

*生成时间：2026-09-26 ｜ 数据源：C:\workbuddy\HSK3.0 下 22 份 17 列提取表*
