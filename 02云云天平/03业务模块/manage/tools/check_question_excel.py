#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
题库 Excel 上传前自查（只读，不改文件）。

配套文档：../题库Excel上传格式校验规范.md

用法：
    python check_question_excel.py "某批题库.xlsx"
    python check_question_excel.py "某批题库.xlsx" --sheet 0

输出三档：
    BLOCK  上传必然失败或数据必错
    WARN   能上传，但会被改写或静默丢弃
    INFO   统计信息
退出码：有 BLOCK → 1，否则 0。
"""

import argparse
import re
import sys

try:
    import openpyxl
except ImportError:
    sys.exit("缺少 openpyxl：pip install openpyxl")

# 16 列唯一权威清单，顺序固定（源：QuestionExcelEo 的 @ExcelProperty）
COLUMNS = [
    "考试大纲*", "学科类型(HSK非必填)", "题型*", "一级标题*", "一级标题内容*",
    "部分标题*", "题目分组(或者范围)*", "部分标题内容", "题目序号", "题目标题",
    "题目内容", "题目选项", "答案*", "分值*", "来源*", "等级*",
]
COL_IDX = {name: i for i, name in enumerate(COLUMNS)}

# 代码里真正带 @ExcelRequired 的 9 个（"等级*" 表头有星但代码不校验）
REQUIRED = ["考试大纲*", "题型*", "一级标题*", "一级标题内容*",
            "部分标题*", "题目分组(或者范围)*", "答案*", "分值*", "来源*"]

SECTION_TITLES = {"听力", "阅读", "书写"}
GROUP_RE = re.compile(r"^\d+-\d+$")
SCORE_RE = re.compile(r"^[0-9]+(\.[0-9]+)?$")
SCORE_GROUP_RE = re.compile(r"^[0-9]+(\.[0-9]+)?(,[0-9]+(\.[0-9]+)?)*$")
ZH_PUNCT = "，。！？；：、（）【】《》「」『』“”‘’—…·"


class Report:
    def __init__(self):
        self.blocks, self.warns, self.infos = [], [], []

    def block(self, where, msg):
        self.blocks.append(f"[{where}] {msg}")

    def warn(self, where, msg):
        self.warns.append(f"[{where}] {msg}")

    def info(self, msg):
        self.infos.append(msg)

    def dump(self):
        for m in self.blocks:
            print("BLOCK " + m)
        for m in self.warns:
            print("WARN  " + m)
        for m in self.infos:
            print("INFO  " + m)
        print("-" * 60)
        print(f"BLOCK {len(self.blocks)} / WARN {len(self.warns)} / INFO {len(self.infos)}")


def cell(row, name):
    idx = COL_IDX[name]
    if idx >= len(row):
        return ""
    v = row[idx]
    if v is None:
        return ""
    return str(v).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--sheet", default="0", help="sheet 名称或序号，默认第一个")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[int(args.sheet)] if args.sheet.isdigit() else wb[args.sheet]
    except (IndexError, KeyError):
        sys.exit(f"找不到 sheet：{args.sheet}（共 {len(wb.worksheets)} 个：{[s.title for s in wb.worksheets]}）")

    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        sys.exit("空文件")

    r = Report()

    # 1. 列头
    actual = [str(c).strip() if c is not None else "" for c in header]
    if actual[:16] != COLUMNS:
        for i in range(16):
            got = actual[i] if i < len(actual) else "<缺失>"
            if got != COLUMNS[i]:
                r.block("列头", f"第 {i+1} 列应为「{COLUMNS[i]}」，实际「{got}」")
    extra = [(i + 1, c) for i, c in enumerate(actual[16:], start=16) if c]
    if extra:
        r.warn("列头", f"第 17 列及以后有内容会被静默丢弃：{extra[:3]}")

    # 2. 逐行
    package, sources, levels = set(), set(), set()
    numbers, group_spans = set(), []
    module_score, example_cnt = {}, 0
    seen_zh = 0
    total = 0

    for lineno, row in enumerate(rows, start=2):
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        total += 1
        where = f"第{lineno}行"

        # 必填
        for name in REQUIRED:
            if not cell(row, name):
                r.block(where, f"必填「{name}」为空（会导致整批上传失败）")

        # 一致性
        for name, bucket in (("考试大纲*", package), ("来源*", sources), ("等级*", levels)):
            v = cell(row, name)
            if v:
                bucket.add(v)

        # 一级标题必须是整数
        t1 = cell(row, "一级标题*")
        if t1 and not t1.isdigit():
            r.block(where, f"「一级标题」必须是整数，实际「{t1}」→ 解析异常")

        # 一级标题内容枚举
        t1t = cell(row, "一级标题内容*")
        if t1t and t1t not in SECTION_TITLES:
            r.block(where, f"「一级标题内容」只能是 听力/阅读/书写，实际「{t1t}」")

        # 题目分组格式
        grp = cell(row, "题目分组(或者范围)*")
        if grp and not GROUP_RE.match(grp):
            r.block(where, f"「题目分组」必须形如 1-5，实际「{grp}」")

        num = cell(row, "题目序号")
        score = cell(row, "分值*")
        answer = cell(row, "答案*")

        # 分值格式（负数/中文/空格都会在取卷时 500）
        if score:
            if num:
                if not SCORE_RE.match(score):
                    r.block(where, f"「分值」只能是数字，实际「{score}」→ 取卷 500")
            else:
                if not SCORE_GROUP_RE.match(score):
                    r.block(where, f"分组行「分值」只能数字或逗号分隔，实际「{score}」")

        # 答案里的逗号（会和多答案分隔符冲突）；全角逗号上传后同样会被转成半角
        if answer and num and ("," in answer or "，" in answer):
            if not re.match(r"^[A-Za-z]([,，][A-Za-z])*$", answer):
                r.warn(where, f"单题行「答案」含逗号「{answer}」，会被当成多答案拆开")

        # 分组行段数 == 区间长度
        if not num and grp and GROUP_RE.match(grp):
            a, b = (int(x) for x in grp.split("-"))
            span = b - a + 1
            group_spans.append((lineno, a, b))
            if answer:
                n = len([s for s in answer.split(",") if s.strip()])
                if n != span:
                    r.block(where, f"分组 {grp} 展开 {span} 题，但「答案」拆出 {n} 段")
            if score:
                n = len([s for s in score.split(",") if s.strip()])
                if n != span:
                    r.block(where, f"分组 {grp} 展开 {span} 题，但「分值」拆出 {n} 段")
            # 例题
            if score.strip() in ("0", "0.0") or answer.strip() == "0":
                example_cnt += 1
        else:
            if num:
                numbers.add(int(num) if num.isdigit() else num)

        # 题号 0 = 例题
        if num == "0":
            example_cnt += 1
            if score and score.strip() not in ("0", "0.0"):
                r.block(where, f"例题「分值」必须写单个 0，实际「{score}」")

        # 中文标点（链路会转半角）
        joined = "".join(cell(row, c) for c in ("题目标题", "题目内容", "题目选项", "答案*"))
        if any(ch in ZH_PUNCT for ch in joined):
            seen_zh += 1

        # 尖括号高危：〈〉 会变成 < >，破坏 HTML 渲染
        if "〈" in joined or "〉" in joined:
            r.block(where, "含「〈〉」，上传后会变成 < > 被当 HTML 标签，页面内容被吞")

        # 模块分值
        if t1t and score and num and SCORE_RE.match(score) and num != "0":
            module_score[t1t] = module_score.get(t1t, 0.0) + float(score)

    # 3. 汇总判定
    for name, bucket, label in (("考试大纲*", package, "考试大纲"), ("来源*", sources, "来源")):
        if len(bucket) > 1:
            r.block("卷级", f"同一文件「{label}」有多个值 {sorted(bucket)} → 会被拆成多张卷")
    if not levels:
        r.block("卷级", "「等级」整列为空 → 会写出 level=NULL 的卷，之后永远取不到（代码不校验这一列）")
    elif len(levels) > 1:
        r.block("卷级", f"同一文件「等级」有多个值 {sorted(levels)} → 会被拆成多张卷")

    # 题号连续性
    expanded = set(numbers)
    for _, a, b in group_spans:
        expanded.update(range(a, b + 1))
    if expanded:
        lo, hi = min(expanded), max(expanded)
        missing = [n for n in range(lo, hi + 1) if n not in expanded]
        if missing:
            r.block("题号", f"题号不连续，缺 {missing[:10]}{' ...' if len(missing) > 10 else ''}")

    r.info(f"数据行 {total}，例题约 {example_cnt}，题号范围 {min(expanded) if expanded else '-'}~{max(expanded) if expanded else '-'}")
    r.info("各模块分值：" + "，".join(f"{k} {v:g}" for k, v in sorted(module_score.items())))
    if seen_zh:
        r.warn("标点", f"{seen_zh} 行含中文标点，上传后会被强制转半角（详见规范 §2）")

    r.dump()
    print("\n提示：模块/卷分值是否 ≈100 属于入库后验收，见《HSK题库数据-统一检查点与验收标准》§3。")
    return 1 if r.blocks else 0


if __name__ == "__main__":
    sys.exit(main())
