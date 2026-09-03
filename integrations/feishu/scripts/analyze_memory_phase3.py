# -*- coding: utf-8 -*-
"""
阶段三：记忆策略数据分析（Phase 3 第一轮）
输入：GitHub Pages 导出的 learning-log 记录（历史字段）
分析：旧词回炉率 / 近似轮次正确率 / 间隔效应 / 方向×维度正确率
输出：打印指标（供整理成 docs 报告）
"""
import urllib.request, json, datetime
import pandas as pd

BASE = "https://201650545.github.io/feishu-data-hub/projects/learning-english/tables/learning-log/records-0001.json"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    return json.load(urllib.request.urlopen(req, timeout=30))

recs = fetch(BASE)["records"]
rows = [r["fields"] for r in recs]
df = pd.DataFrame(rows)

# 日期：毫秒时间戳 → 日期
df["日期"] = pd.to_datetime(df["日期"], unit="ms", errors="coerce")
df["word"] = df["关联单词"].fillna("(无)")
df["ok"] = df["结果"] == "✅正确"
df["err"] = df["结果"] == "❌错误"
df["skip"] = df["结果"] == "⏭️跳过"

print("=" * 60)
print(f"总记录: {len(df)} | 有日期: {df['日期'].notna().sum()}")
print(f"日期范围: {df['日期'].min().date()} ~ {df['日期'].max().date()}")
print(f"结果分布: 正确={df['ok'].sum()} 错误={df['err'].sum()} 跳过={df['skip'].sum()}")
print(f"关联单词数(去重): {df['word'].nunique()}")

# ---- 1. 基础：方向×维度 正确率 ----
print("\n" + "=" * 60)
print("【测验方向 × 维度 正确率】")
g = df.groupby(["测验方向", "测验维度"]).agg(
    总数=("ok", "size"), 正确=("ok", "sum")).reset_index()
g["正确率"] = (g["正确"] / g["总数"] * 100).round(1)
print(g.to_string(index=False))

# ---- 2. 近似轮次正确率：同一单词第 N 次测验 ----
print("\n" + "=" * 60)
print("【近似轮次正确率】(按单词内测验次序近似 round)")
df = df.sort_values(["word", "日期"])
df["word_ord"] = df.groupby("word").cumcount() + 1
d2 = df[df["word_ord"] <= 8]
g2 = d2.groupby("word_ord").agg(总数=("ok", "size"), 正确=("ok", "sum")).reset_index()
g2["正确率"] = (g2["正确"] / g2["总数"] * 100).round(1)
print(g2.to_string(index=False))

# ---- 3. 旧词回炉率 ----
print("\n" + "=" * 60)
print("【旧词回炉率】定义：某词曾答对，此后间隔>=3天再测答错 => 回炉")
# 对每个单词：找出"答对过"后的"间隔>=3天的答错"
res = []
for w, sub in df.groupby("word"):
    sub = sub.sort_values("日期")
    # 累计：自上次"答对"后经历的天数
    last_ok_date = None
    for _, r in sub.iterrows():
        d = r["日期"]
        if pd.isna(d):
            continue
        if r["err"] and last_ok_date is not None:
            gap = (d - last_ok_date).days
            if gap >= 3:
                res.append({"word": w, "gap": gap, "date": d})
        if r["ok"]:
            last_ok_date = d
lapse_df = pd.DataFrame(res)
words_with_2plus = df.groupby("word").size()
words_ever_ok = set(df[df["ok"]]["word"])
print(f"有>=2次测验的词: {(words_with_2plus >= 2).sum()}")
print(f"曾答对过的词: {len(words_ever_ok)}")
if len(lapse_df):
    n_lapse_words = lapse_df["word"].nunique()
    eligible = set(lapse_df["word"])  # 直接统计发生过回炉的词
    rate = n_lapse_words / len(words_ever_ok) * 100
    print(f"发生回炉的词数: {n_lapse_words} ({rate:.1f}% of 曾答对词)")
    print(f"回炉事件数: {len(lapse_df)}")
    print("回炉间隔分布:")
    print(lapse_df["gap"].describe().round(1).to_string())
    print("回炉间隔分桶:")
    bins = pd.cut(lapse_df["gap"], [3, 7, 14, 30, 365], labels=["3-7d", "8-14d", "15-30d", ">30d"])
    print(lapse_df.groupby(bins, observed=False).size().to_string())
else:
    print("无回炉事件")

# ---- 4. 间隔效应：相邻两次测验间隔 vs 后一次正确率 ----
print("\n" + "=" * 60)
print("【间隔效应】相邻两次测验间隔天数 vs 第二次正确率")
gaps = []
for w, sub in df.groupby("word"):
    sub = sub.sort_values("日期")
    prev_d = None
    for _, r in sub.iterrows():
        d = r["日期"]
        if pd.isna(d) or pd.isna(prev_d):
            prev_d = d
            continue
        gap = (d - prev_d).days
        if gap >= 0:
            gaps.append({"gap": gap, "next_ok": r["ok"]})
        prev_d = d
gg = pd.DataFrame(gaps)
if len(gg):
    gg["bucket"] = pd.cut(gg["gap"], [-1, 0, 1, 3, 7, 14, 30, 365],
                          labels=["同日", "1d", "2-3d", "4-7d", "8-14d", "15-30d", ">30d"])
    g3 = gg.groupby("bucket", observed=False).agg(样本=("next_ok", "size"), 正确=("next_ok", "sum")).reset_index()
    g3["正确率"] = (g3["正确"] / g3["样本"] * 100).round(1)
    print(g3.to_string(index=False))

# ---- 5. 测验类型分布 ----
print("\n" + "=" * 60)
print("【测验类型分布】")
print(df["测验类型"].value_counts().to_string())

# ---- 6. 回炉最高词 TOP10 ----
if len(lapse_df):
    print("\n" + "=" * 60)
    print("【回炉最多的词 TOP10】")
    top = lapse_df.groupby("word").size().sort_values(ascending=False).head(10)
    for w, c in top.items():
        print(f"  {w}: {c} 次回炉")
