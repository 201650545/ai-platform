import re, json, os, subprocess, sys

NODE = "C:/Users/郭永涛/.workbuddy/binaries/node/versions/22.22.2/node.exe"
RUN_JS = "C:/Users/郭永涛/.workbuddy/binaries/node/versions/22.22.2/node_modules/@larksuite/cli/scripts/run.js"
APP = "StmDbTXQWaujshs9NpIc3UFpnAc"
TID = "tbl79Mb2OWZV1g5T"

ROOT = "D:/ai-resource-hub/docs/资源调研"
FILES = {
    'E': os.path.join(ROOT, '任务E_调研结果_2026-08-25.md'),
    'F': os.path.join(ROOT, '任务F_调研结果_2026-08-25.md'),
    'G': os.path.join(ROOT, '任务G_调研结果_2026-08-25.md'),
    'H': os.path.join(ROOT, '任务H_调研结果_2026-08-25.md'),
    'I': os.path.join(ROOT, '任务I_调研结果_2026-08-25.md'),
}

# task -> 类别(表内选项)
TASK_CAT = {
    'F': 'AI语音',
    'G': 'AI代码模型',
    'H': 'AI Agent自动化',
    'I': 'AI音乐生成',
}

def map_cat(task, raw_cat):
    if task == 'E':
        if '视频' in raw_cat:
            return 'AI视频生成'
        if '生图' in raw_cat:
            return 'AI生图'
        return '多模态API'
    return TASK_CAT[task]

def norm_region(raw):
    r = raw or ''
    if '大陆' in r or '中国' in r or '国内' in r:
        return '大陆'
    return '海外'

def norm_url(raw):
    u = (raw or '').strip()
    if not u or '未确认' in u or u in ('-', '无'):
        return ''
    if not u.startswith('http'):
        if u.startswith('github.com') or u.startswith('www.') or u.startswith('activepieces'):
            u = 'https://' + u
        else:
            # unknown pattern -> best-effort https
            u = 'https://' + u.lstrip('/')
    return u

def clean(v):
    v = (v or '').strip()
    if v in ('-', '无', ''):
        return ''
    return v

rows = []
seen = set()
for task, fp in FILES.items():
    txt = open(fp, encoding='utf-8').read()
    m = re.search(r'## 4\.2 新增资源表(.*?)(?=\n## |\Z)', txt, re.S)
    if not m:
        continue
    sec = m.group(1)
    for line in sec.splitlines():
        if not line.strip().startswith('|'):
            continue
        if '工具名称' in line or set(line.strip()) <= set('|-'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 11:
            continue
        name = cells[0]
        if name in ('无', '-', '---') or not name:
            continue
        raw_cat = cells[1]
        region = cells[2]
        company = cells[3]
        ability = cells[4]
        url = cells[5]
        free_rule = cells[6]
        daily = cells[7]
        validity = cells[8]
        claim = cells[9]
        note = cells[10]
        source = cells[11] if len(cells) > 11 else ''
        if name in seen:
            continue
        seen.add(name)
        cat = map_cat(task, raw_cat)
        reg = norm_region(region)
        u = norm_url(url)
        # 备注: 合并 备注 + 来源
        note_full = clean(note)
        if source and source not in note_full:
            note_full = (note_full + ' | 来源:' + clean(source)).strip(' |')
        rows.append([
            name,                       # 工具名称
            [cat],                      # 类别 (多选)
            reg,                        # 地区
            clean(company),             # 所属公司
            clean(ability),             # 能力
            u,                          # 官网链接 (url)
            clean(free_rule),           # 免费规则
            clean(daily),               # 每日免费额度
            clean(validity),            # 有效期
            clean(claim),               # 领取方式
            note_full,                  # 备注
            '未测', '未测', '未测', '未测', '未测',  # 5个状态列
        ])

fields = ['工具名称', '类别', '地区', '所属公司', '能力', '官网链接', '免费规则',
          '每日免费额度', '有效期', '领取方式', '备注',
          '登录成功', '额度到账', '扣减正确', '生成成功', '总体结论']

payload = {'fields': fields, 'rows': rows}
print('新增资源去重条数 =', len(rows))
from collections import Counter
c = Counter(r[1][0] for r in rows)
for k, v in c.most_common():
    print(' ', k, '=', v)

# 调用 lark-cli 批量建记录
args = [NODE, RUN_JS, 'base', '+record-batch-create',
        '--base-token', APP, '--table-id', TID,
        '--json', json.dumps(payload, ensure_ascii=False)]
if '--dry-run' in sys.argv:
    args.append('--dry-run')
    print('=== DRY-RUN ===')
else:
    print('=== 实际写入 ===')
r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
print('STDOUT:', r.stdout[:2500])
print('STDERR:', r.stderr[:800])

