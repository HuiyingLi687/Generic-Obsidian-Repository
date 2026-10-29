# HSK 2.0 题型枚举清单（取自《HSK新旧大纲对比》）

> 配套文档：`HSK题型枚举.md`（HSK 3.0 版）。
> **本文档的题型名一律取自 `HSK新旧大纲对比(1).xlsx` 的「HSK2.0（旧版）」列**（B 列），
> 即大纲口径的细分说法；字符串格式统一为 `模块:题型`（半角冒号，无空格）。

## 一、数据来源与口径

| 项 | 说明 |
|---|---|
| 数据来源 | `C:\workbuddy\HSK3.0\HSK\HSK新旧大纲对比(1).xlsx` → Sheet `HSK新旧大纲对比` → **B 列「HSK2.0（旧版）」** |
| 模块取值 | 同表 **A 列**模块行头（听力 / 阅读 / 写作 / 翻译 / 口语） |
| 涉及级别 | HSK1 – HSK6（HSK（七—九级）是 3.0 才有的，对比表 2.0 列为 `－`，不参与） |
| 字符串格式 | `模块:题型`（半角冒号，无空格） |
| 拆解方式 | 按 B 列每个模块单元格内的 `第X部分：<题型>*<题量>` 逐段解析 |
| 合计 | **3 模块 / 24 题型** |

> HSK 2.0 笔试只有 **听力 / 阅读 / 写作** 三大模块（对比表 2.0 列无「翻译」「口语」；
> HSK1、HSK2 更低级，连「写作」都还没有）。

## 二、总览

| 模块 | 题型数 | 枚举前缀 | code 前缀 | 适用级别 |
|---|---|---|---|---|
| 听力 | 8 | `LISTENING_` | `listening_` | HSK1 – HSK6 |
| 阅读 | 12 | `READING_` | `reading_` | HSK1 – HSK6 |
| 写作 | 4 | `WRITING_` | `writing_` | HSK3 – HSK6 |

> **模块名注意**：对比表把第三模块统一写作「**写作**」（A 列），2.0 原卷则印「**三、书写**」。
> 本文档按你的要求「以对比表为准」，故前缀用 `写作:`；
> 若要与原卷/提取表一致，把这 4 个的 `写作:` 改成 `书写:` 即可（见附录 A 脚注）。

---

## 三、听力模块（8 个）

| 枚举常量 | code | 显示名（入库值） | 出现位置（级别·部分·题量） |
|---|---|---|---|
| `LISTENING_PIC_JUDGE` | `listening_pic_judge` | `听力:看图判断` | HSK1 P1(5)、HSK2 P1(10) |
| `LISTENING_PIC_CHOICE` | `listening_pic_choice` | `听力:看图选择` | HSK1 P2(5) |
| `LISTENING_IMG_MATCH` | `listening_img_match` | `听力:图片匹配` | HSK1 P3(5)、HSK2 P2(10)、HSK3 P1(10) |
| `LISTENING_SHORT_DIALOG_CHOICE` | `listening_short_dialog_choice` | `听力:短对话选择` | HSK2 P3(10)、HSK3 P3(10)、HSK4 P2(15) |
| `LISTENING_LONG_DIALOG_CHOICE` | `listening_long_dialog_choice` | `听力:长对话选择` | HSK2 P4(5)、HSK3 P4(10)、HSK4 P3(20) |
| `LISTENING_DETAIL_JUDGE` | `listening_detail_judge` | `听力:细节判断` | HSK3 P2(10)、HSK4 P1(10) |
| `LISTENING_DETAIL_CHOICE` | `listening_detail_choice` | `听力:细节选择` | HSK1 P4(5)、HSK5 P1(20)、HSK5 P2(25)、HSK6 P1(15)、HSK6 P2(15) |
| `LISTENING_READING_CHOICE` | `listening_reading_choice` | `听力:阅读理解` | HSK6 P3(20) |

```java
// ========== 听力模块 ==========
LISTENING_PIC_JUDGE("listening_pic_judge", "听力:看图判断"),
LISTENING_PIC_CHOICE("listening_pic_choice", "听力:看图选择"),
LISTENING_IMG_MATCH("listening_img_match", "听力:图片匹配"),
LISTENING_SHORT_DIALOG_CHOICE("listening_short_dialog_choice", "听力:短对话选择"),
LISTENING_LONG_DIALOG_CHOICE("listening_long_dialog_choice", "听力:长对话选择"),
LISTENING_DETAIL_JUDGE("listening_detail_judge", "听力:细节判断"),
LISTENING_DETAIL_CHOICE("listening_detail_choice", "听力:细节选择"),
LISTENING_READING_CHOICE("listening_reading_choice", "听力:阅读理解"),
```

---

## 四、阅读模块（12 个）

| 枚举常量 | code | 显示名（入库值） | 出现位置（级别·部分·题量） |
|---|---|---|---|
| `READING_PIC_JUDGE` | `reading_pic_judge` | `阅读:看图判断` | HSK1 P1(5) |
| `READING_IMG_MATCH` | `reading_img_match` | `阅读:图片匹配` | HSK1 P2(5)、HSK2 P1(5) |
| `READING_SENT_MATCH` | `reading_sent_match` | `阅读:句子匹配` | HSK1 P3(5)、HSK2 P4(10)、HSK3 P1(10) |
| `READING_DETAIL_JUDGE` | `reading_detail_judge` | `阅读:细节判断` | HSK2 P3(5) |
| `READING_DETAIL_CHOICE` | `reading_detail_choice` | `阅读:细节选择` | HSK3 P3(10)、HSK4 P3(15)、HSK5 P2(10) |
| `READING_CLOZE` | `reading_cloze` | `阅读:完形填空` | HSK1 P4(5)、HSK2 P2(5)、HSK3 P2(10)、HSK4 P1(10) |
| `READING_ORDER` | `reading_order` | `阅读:排列顺序` | HSK4 P2(5) |
| `READING_WORD_FILL` | `reading_word_fill` | `阅读:选词填空` | HSK6 P2(15) |
| `READING_SENT_FILL` | `reading_sent_fill` | `阅读:选句填空` | HSK6 P3(10) |
| `READING_PASSAGE_FILL` | `reading_passage_fill` | `阅读:阅读填空` | HSK5 P1(15) |
| `READING_WRONG_SENTENCE` | `reading_wrong_sentence` | `阅读:病句选择` | HSK6 P1(10) |
| `READING_PASSAGE_CHOICE` | `reading_passage_choice` | `阅读:文章选择` | HSK5 P3(10)、HSK6 P4(10) |

```java
// ========== 阅读模块 ==========
READING_PIC_JUDGE("reading_pic_judge", "阅读:看图判断"),
READING_IMG_MATCH("reading_img_match", "阅读:图片匹配"),
READING_SENT_MATCH("reading_sent_match", "阅读:句子匹配"),
READING_DETAIL_JUDGE("reading_detail_judge", "阅读:细节判断"),
READING_DETAIL_CHOICE("reading_detail_choice", "阅读:细节选择"),
READING_CLOZE("reading_cloze", "阅读:完形填空"),
READING_ORDER("reading_order", "阅读:排列顺序"),
READING_WORD_FILL("reading_word_fill", "阅读:选词填空"),
READING_SENT_FILL("reading_sent_fill", "阅读:选句填空"),
READING_PASSAGE_FILL("reading_passage_fill", "阅读:阅读填空"),
READING_WRONG_SENTENCE("reading_wrong_sentence", "阅读:病句选择"),
READING_PASSAGE_CHOICE("reading_passage_choice", "阅读:文章选择"),
```

---

## 五、写作模块（4 个）

| 枚举常量 | code | 显示名（入库值） | 出现位置（级别·部分·题量） |
|---|---|---|---|
| `WRITING_WORD_ORDER` | `writing_word_order` | `写作:连词成句` | HSK3 P1(5)、HSK4 P1(10)、HSK5 P1(8)、HSK6 P1(8) |
| `WRITING_CHAR_WRITE` | `writing_char_write` | `写作:汉字书写` | HSK3 P2(5) |
| `WRITING_PIC_SENTENCE` | `writing_pic_sentence` | `写作:看图用词造句` | HSK4 P2(5) |
| `WRITING_SHORT_ESSAY` | `writing_short_essay` | `写作:短文写作` | HSK5 P2(2)、HSK6 P2(2) |

```java
// ========== 写作模块 ==========
WRITING_WORD_ORDER("writing_word_order", "写作:连词成句"),
WRITING_CHAR_WRITE("writing_char_write", "写作:汉字书写"),
WRITING_PIC_SENTENCE("writing_pic_sentence", "写作:看图用词造句"),
WRITING_SHORT_ESSAY("writing_short_essay", "写作:短文写作"),
```

---

## 六、完整枚举（可直接粘贴）

```java
package com.hsk.question.enums;

import java.util.HashMap;
import java.util.Map;

/**
 * HSK 2.0 题型枚举（3 模块 / 24 题型）
 * 数据来源：HSK新旧大纲对比(1).xlsx「HSK2.0（旧版）」列，格式 "模块:题型"
 */
public enum Hsk20QuestionType {

    // ========== 听力模块 ==========
    LISTENING_PIC_JUDGE("listening_pic_judge", "听力:看图判断"),
    LISTENING_PIC_CHOICE("listening_pic_choice", "听力:看图选择"),
    LISTENING_IMG_MATCH("listening_img_match", "听力:图片匹配"),
    LISTENING_SHORT_DIALOG_CHOICE("listening_short_dialog_choice", "听力:短对话选择"),
    LISTENING_LONG_DIALOG_CHOICE("listening_long_dialog_choice", "听力:长对话选择"),
    LISTENING_DETAIL_JUDGE("listening_detail_judge", "听力:细节判断"),
    LISTENING_DETAIL_CHOICE("listening_detail_choice", "听力:细节选择"),
    LISTENING_READING_CHOICE("listening_reading_choice", "听力:阅读理解"),

    // ========== 阅读模块 ==========
    READING_PIC_JUDGE("reading_pic_judge", "阅读:看图判断"),
    READING_IMG_MATCH("reading_img_match", "阅读:图片匹配"),
    READING_SENT_MATCH("reading_sent_match", "阅读:句子匹配"),
    READING_DETAIL_JUDGE("reading_detail_judge", "阅读:细节判断"),
    READING_DETAIL_CHOICE("reading_detail_choice", "阅读:细节选择"),
    READING_CLOZE("reading_cloze", "阅读:完形填空"),
    READING_ORDER("reading_order", "阅读:排列顺序"),
    READING_WORD_FILL("reading_word_fill", "阅读:选词填空"),
    READING_SENT_FILL("reading_sent_fill", "阅读:选句填空"),
    READING_PASSAGE_FILL("reading_passage_fill", "阅读:阅读填空"),
    READING_WRONG_SENTENCE("reading_wrong_sentence", "阅读:病句选择"),
    READING_PASSAGE_CHOICE("reading_passage_choice", "阅读:文章选择"),

    // ========== 写作模块 ==========
    WRITING_WORD_ORDER("writing_word_order", "写作:连词成句"),
    WRITING_CHAR_WRITE("writing_char_write", "写作:汉字书写"),
    WRITING_PIC_SENTENCE("writing_pic_sentence", "写作:看图用词造句"),
    WRITING_SHORT_ESSAY("writing_short_essay", "写作:短文写作"),
    ;

    /** 代码标识，入库/接口传输用 */
    private final String code;
    /** 显示名，格式 "模块:题型" */
    private final String display;

    Hsk20QuestionType(String code, String display) {
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

    /** 题型名（不含模块前缀），如「看图判断」 */
    public String getTypeName() {
        return display.substring(display.indexOf(':') + 1);
    }

    private static final Map<String, Hsk20QuestionType> BY_CODE = new HashMap<>();
    private static final Map<String, Hsk20QuestionType> BY_DISPLAY = new HashMap<>();

    static {
        for (Hsk20QuestionType t : values()) {
            BY_CODE.put(t.code, t);
            BY_DISPLAY.put(t.display, t);
        }
    }

    public static Hsk20QuestionType ofCode(String code) {
        return BY_CODE.get(code);
    }

    public static Hsk20QuestionType ofDisplay(String display) {
        return BY_DISPLAY.get(display);
    }
}
```

---

## 七、注意事项

1. **口径来自对比表，不是实际卷**。本文档的题型名是《HSK新旧大纲对比》里的大纲说法
   （如「短对话选择」「长对话选择」「病句选择」「连词成句」「看图用词造句」）；
   而实际提取表的 `题型*`（C 列）用的是**更粗的口径**（判断 / 单选 / 匹配 / 语病判断 / 完成句子 / 造句…）。
   两者是**同义不同名**，逐条对应见 **附录 A**。入库前请确认按哪套口径统一。

2. **对比表的 2.0 列在 HSK4/5/6 有已知题量错误**（表内自身也与同表「总题量」行矛盾），
   典型如 HSK4 阅读 P2 写 5 实际 10、HSK4 阅读 P3 写 15 实际 20、HSK5 阅读 P3 写 10 实际 20、
   HSK6 阅读 P2 写 15 实际 10、HSK6 阅读 P4 写 10 实际 20、HSK6 写作整部分只 1 题。
   **题型名可用，题量以实际卷为准**（详见附录 A 的 ✗ 标记）。

3. **第三模块名不一致**：对比表写「写作」，2.0 原卷印「书写」。
   本文档按你的要求取对比表口径 → 用 `写作:`；若要与原卷/提取表一致，改回 `书写:` 即可。

4. **同一题型跨级别复用**：枚举是"题型字典"，级别由 `等级*`（P 列）另存，
   第几部分由 `部分标题*`（F 列）另存 —— 不能只靠题型区分级别。

5. **2.0 / 3.0 建议各建一个枚举类**（`Hsk20QuestionType` / `Hsk30QuestionType`）。
   两版有 14 个显示名完全重叠（见附录 B），若要合成一个枚举，务必加 `version` 字段，
   按「version + display」做唯一键。

6. **本文档生成脚本**（可随时重跑核对）：
   - `_parse_cmp_20.py` —— 解析对比表 B 列（HSK2.0 旧版），输出逐级/逐模块题型明细
   - `_cmp_set_20_30.py` —— 对比表 2.0 题型集 vs 3.0 提取表题型集（重叠/各自独有）

---

## 附录 A：对比表「HSK2.0（旧版）」列逐部分原文

（`模块`=对比表 A 列；`对比表 2.0 写法`=B 列原串；「题量 表/实际」中标 ✗ 者表示
对比表题量与实际卷不符，**以实际卷为准**）

| 级别 | 模块 | 部分 | 对比表 2.0 写法 | 本文档显示名 | 题量 表/实际 |
|---|---|---|---|---|---|
| HSK1 | 听力 | P1 | 看图判断题 | `听力:看图判断` | 5 / 5 |
| HSK1 | 听力 | P2 | 看图选择题 | `听力:看图选择` | 5 / 5 |
| HSK1 | 听力 | P3 | 图片匹配题 | `听力:图片匹配` | 5 / 5 |
| HSK1 | 听力 | P4 | 细节选择题 | `听力:细节选择` | 5 / 5 |
| HSK1 | 阅读 | P1 | 看图判断题 | `阅读:看图判断` | 5 / 5 |
| HSK1 | 阅读 | P2 | 图片匹配题 | `阅读:图片匹配` | 5 / 5 |
| HSK1 | 阅读 | P3 | 句子匹配题 | `阅读:句子匹配` | 5 / 5 |
| HSK1 | 阅读 | P4 | 完形填空题 | `阅读:完形填空` | 5 / 5 |
| HSK2 | 听力 | P1 | 看图判断题 | `听力:看图判断` | 10 / 10 |
| HSK2 | 听力 | P2 | 图片匹配题 | `听力:图片匹配` | 10 / 10 |
| HSK2 | 听力 | P3 | 短对话选择题 | `听力:短对话选择` | 10 / 10 |
| HSK2 | 听力 | P4 | 长对话选择题 | `听力:长对话选择` | 5 / 5 |
| HSK2 | 阅读 | P1 | 图片匹配题 | `阅读:图片匹配` | 5 / 5 |
| HSK2 | 阅读 | P2 | 完形填空题 | `阅读:完形填空` | 5 / 5 |
| HSK2 | 阅读 | P3 | 细节判断题 | `阅读:细节判断` | 5 / 5 |
| HSK2 | 阅读 | P4 | 句子匹配题 | `阅读:句子匹配` | 10 / 10 |
| HSK3 | 听力 | P1 | 图片匹配题 | `听力:图片匹配` | 10 / 10 |
| HSK3 | 听力 | P2 | 细节判断题 | `听力:细节判断` | 10 / 10 |
| HSK3 | 听力 | P3 | 短对话选择题 | `听力:短对话选择` | 10 / 10 |
| HSK3 | 听力 | P4 | 长对话选择题 | `听力:长对话选择` | 10 / 10 |
| HSK3 | 阅读 | P1 | 句子匹配题 | `阅读:句子匹配` | 10 / 10 |
| HSK3 | 阅读 | P2 | 完形填空题 | `阅读:完形填空` | 10 / 10 |
| HSK3 | 阅读 | P3 | 细节选择题 | `阅读:细节选择` | 10 / 10 |
| HSK3 | 写作¹ | P1 | 连词成句 | `写作:连词成句` | 5 / 5 |
| HSK3 | 写作¹ | P2 | 汉字书写 | `写作:汉字书写` | 5 / 5 |
| HSK4 | 听力 | P1 | 细节判断题 | `听力:细节判断` | 10 / 10 |
| HSK4 | 听力 | P2 | 短对话选择题 | `听力:短对话选择` | 15 / 15 |
| HSK4 | 听力 | P3 | 长对话选择题 | `听力:长对话选择` | 20 / 20 |
| HSK4 | 阅读 | P1 | 完形填空题 | `阅读:完形填空` | 10 / 10 |
| HSK4 | 阅读 | P2 | 排列顺序题 | `阅读:排列顺序` | **5 / 10 ✗** |
| HSK4 | 阅读 | P3 | 细节选择题 | `阅读:细节选择` | **15 / 20 ✗** |
| HSK4 | 写作¹ | P1 | 连词成句 | `写作:连词成句` | 10 / 10 |
| HSK4 | 写作¹ | P2 | 看图用词造句 | `写作:看图用词造句` | 5 / 5 |
| HSK5 | 听力 | P1 | 细节选择题 | `听力:细节选择` | 20 / 20 |
| HSK5 | 听力 | P2 | 细节选择题 | `听力:细节选择` | 25 / 25 |
| HSK5 | 阅读 | P1 | 阅读填空题 | `阅读:阅读填空` | 15 / 15 |
| HSK5 | 阅读 | P2 | 细节选择题 | `阅读:细节选择` | 10 / 10 |
| HSK5 | 阅读 | P3 | 文章选择题 | `阅读:文章选择` | **10 / 20 ✗** |
| HSK5 | 写作¹ | P1 | 连词成句 | `写作:连词成句` | 8 / 8 |
| HSK5 | 写作¹ | P2 | 短文写作 | `写作:短文写作` | 2 / 2 |
| HSK6 | 听力 | P1 | 细节选择题 | `听力:细节选择` | 15 / 15 |
| HSK6 | 听力 | P2 | 细节选择题 | `听力:细节选择` | 15 / 15 |
| HSK6 | 听力 | P3 | 阅读理解题 | `听力:阅读理解` | 20 / 20 |
| HSK6 | 阅读 | P1 | 病句选择题 | `阅读:病句选择` | 10 / 10 |
| HSK6 | 阅读 | P2 | 选词填空题 | `阅读:选词填空` | **15 / 10 ✗** |
| HSK6 | 阅读 | P3 | 选句填空题 | `阅读:选句填空` | 10 / 10 |
| HSK6 | 阅读 | P4 | 文章选择题 | `阅读:文章选择` | **10 / 20 ✗** |
| HSK6 | 写作¹ | P1 | 连词成句*8 + 短文写作*2 | `写作:连词成句` + `写作:短文写作` | **10 / 1 ✗** |

¹ 对比表把第三模块写作「写作」（A 列），实际提取表与试卷都用「**书写**」。

**题量不符根因**：对比表 2.0 列在 HSK4/HSK5/HSK6 阅读部分与 HSK6 写作部分抄写有误
（且与同表「总题量」行自相矛盾）。以实际卷为准：
HSK4 阅读 10+10+20=40、HSK5 阅读 15+10+20=45、HSK6 阅读 10+10+10+20=50、HSK6 写作 1 题（总 101 题）。

## 附录 B：与 3.0 题型集对照

| 关系 | 数量 | 内容 |
|---|---|---|
| 两者重叠 | 14 | `听力:图片匹配`、`听力:看图选择`、`听力:细节选择`、`听力:阅读理解`、`阅读:句子匹配`、`阅读:图片匹配`、`阅读:完形填空`、`阅读:细节选择`、`阅读:文章选择`、`阅读:选句填空`、`阅读:选词填空`、`阅读:阅读填空`、`写作:看图用词造句`、`写作:短文写作` |
| 仅 2.0 有 | 10 | `听力:看图判断`、`听力:短对话选择`、`听力:长对话选择`、`听力:细节判断`、`阅读:看图判断`、`阅读:细节判断`、`阅读:排列顺序`、`阅读:病句选择`、`写作:汉字书写`、`写作:连词成句` |
| 仅 3.0 有 | 17 | `听力:判断`、`听力:对话选择`、`听力:选择/填空`、`书写:汉字书写`、`书写:汉字部件选择`、`书写:看图用词造句`、`阅读:文章简答`、`阅读:段落排序`、`翻译:笔译`、`翻译:口译`、`口语:应用读说`、`口语:听材料回答问题`、`口语:观点表达`、`写作:图表描述与分析`、`写作:应用文写作`、`写作:看图写作`、`写作:话题作文` |
| 去重合计 | 41 | 24 + 31 − 14 = 41 |

> 注意：`写作:汉字书写`／`写作:看图用词造句`／`写作:短文写作` 在 2.0 属「写作」（对比表口径），
> 在 3.0 里对应的是「书写」或「写作」两个不同模块（3.0 的 HSK2/HSK3 叫「书写」、HSK4 起才叫「写作」），
> 合并枚举时需按 `version + display` 双键区分。

---

*生成时间：2026-09-26 ｜ 数据源：`C:\workbuddy\HSK3.0\HSK\HSK新旧大纲对比(1).xlsx` → Sheet `HSK新旧大纲对比` → B 列「HSK2.0（旧版）」*
