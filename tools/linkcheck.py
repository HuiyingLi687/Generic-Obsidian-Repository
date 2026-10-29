# -*- coding: utf-8 -*-
"""
Obsidian 仓库链接体检 / 自动修复
用法：
    python linkcheck.py            只检查，出报告
    python linkcheck.py --fix      自动修复「唯一匹配」的断链
"""
import os, re, sys, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'.git', '.obsidian', '.trash', 'node_modules', '__pycache__'}

MD_LINK = re.compile(r'(?<!!)\[([^\]]*)\]\(([^)]*)\)')
WIKI = re.compile(r'\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]')
EXTERNAL = re.compile(r'^(https?:|mailto:|tel:|ftp:|obsidian:|file:|data:|<)', re.I)
# 看起来像「正文里随手打的方括号」，不是真链接
FAKE_HINT = re.compile(r'[\s，。；：、]|^[A-F](-[A-F])?$|^多张$|^固定|^以上$')

def looks_like_file(t):
    if '.' in os.path.basename(t):
        return True
    if '/' in t or '\\' in t:
        return True
    return False

def collect():
    out = []
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn.lower().endswith('.md'):
                out.append(os.path.join(dp, fn))
    return out

def read(p):
    for enc in ('utf-8', 'gbk'):
        try:
            return open(p, encoding=enc).read()
        except UnicodeDecodeError:
            continue
    return open(p, encoding='utf-8', errors='replace').read()

def main():
    do_fix = '--fix' in sys.argv
    files = collect()
    by_name = {}       # 文件名(不含扩展名) -> [绝对路径]
    all_paths = {}     # 相对路径(小写, 正斜杠) -> 绝对路径
    for f in files:
        rel = os.path.relpath(f, ROOT).replace('\\', '/')
        all_paths[rel.lower()] = f
        by_name.setdefault(os.path.splitext(os.path.basename(f))[0], []).append(f)

    ok = ignored = 0
    fixable, dead, fakes = [], [], []
    edits = {}         # 文件 -> [(旧串, 新串)]

    for f in files:
        rel = os.path.relpath(f, ROOT)
        txt = read(f)
        for m in MD_LINK.finditer(txt):
            label, raw = m.group(1), m.group(2).strip()
            if not raw or EXTERNAL.match(raw):
                ignored += 1; continue
            tgt = raw.strip('<>').split('"')[0].strip()
            path_part = urllib.parse.unquote(tgt.split('#')[0]).strip('<>')
            if not path_part:
                ignored += 1; continue
            cand = os.path.normpath(os.path.join(os.path.dirname(f), path_part))
            if os.path.exists(cand):
                ok += 1; continue
            if not looks_like_file(path_part):
                fakes.append((rel, m.group(0), '正文方括号，非链接')); continue
            stem = os.path.splitext(os.path.basename(path_part))[0]
            hits = [h for h in by_name.get(stem, []) if h != f]
            if len(hits) == 1:
                newrel = os.path.relpath(hits[0], os.path.dirname(f)).replace('\\', '/')
                enc = urllib.parse.quote(newrel)
                fixable.append((rel, m.group(0), newrel))
                edits.setdefault(f, []).append((m.group(0), f'[{label}](<{newrel}>)' if ('(' in newrel or ' ' in newrel) else f'[{label}]({newrel})'))
            else:
                dead.append((rel, m.group(0), path_part, hits))

        for m in WIKI.finditer(txt):
            tgt = m.group(1).strip()
            if not tgt:
                ignored += 1; continue
            if tgt in by_name or os.path.exists(os.path.join(ROOT, tgt)) or \
               os.path.splitext(os.path.basename(tgt))[0] in by_name:
                ok += 1; continue
            if not looks_like_file(tgt) and '/' not in tgt and '\\' not in tgt:
                fakes.append((rel, m.group(0), '占位符或正文方括号')); continue
            # wikilink 里写了相对路径 —— 这是常见误用
            base = os.path.basename(tgt.replace('\\', '/'))
            stem = os.path.splitext(base)[0]
            hits = [h for h in by_name.get(stem, []) if h != f]
            if len(hits) == 1:
                fixable.append((rel, m.group(0), f'[[{stem}]]'))
                edits.setdefault(f, []).append((m.group(0), f'[[{stem}]]'))
            else:
                dead.append((rel, m.group(0), tgt, hits))

    print('=' * 74)
    print(f'  md 文件 {len(files)} 个 | 链接正常 {ok} | 已忽略外部/占位 {ignored}')
    print(f'  可自动修复 {len(fixable)} | 真断链 {len(dead)} | 疑似非链接 {len(fakes)}')
    print('=' * 74)

    if fixable:
        print('\n【可自动修复】名字能唯一对上现存文件（多半是改名或移动过）')
        for rel, old, new in fixable:
            print(f'  {rel}')
            print(f'    {old}')
            print(f'    -> {new}\n')
    if dead:
        print('\n【真断链】目标文件已不存在，或同名文件有多个')
        for rel, old, path_part, hits in dead:
            print(f'  {rel}')
            print(f'    {old}')
            if hits:
                print(f'    候选: ' + ' / '.join(os.path.relpath(h, ROOT) for h in hits))
            print()
    if fakes:
        print('\n【疑似非链接】正文里的方括号，可以不管')
        seen = set()
        for rel, txt_, why in fakes:
            k = (rel, txt_)
            if k in seen: continue
            seen.add(k)
            print(f'  {rel}  {txt_}   ({why})')

    if do_fix and edits:
        n = 0
        for f, pairs in edits.items():
            t = read(f)
            for old, new in pairs:
                if old in t:
                    t = t.replace(old, new); n += 1
            open(f, 'w', encoding='utf-8', newline='\n').write(t)
        print(f'\n已修复 {n} 处链接，涉及 {len(edits)} 个文件。')
        print('提示：回 Obsidian 后按 Ctrl+R 刷新生效。')
    elif fixable:
        print('\n加 --fix 参数可自动修复上面这些。')

if __name__ == '__main__':
    main()
