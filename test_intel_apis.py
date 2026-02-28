"""探测 AKShare 可用的美股/宏观/板块新闻接口"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import akshare as ak

# === 1. 美股科技龙头走势 ===
print("=== 1. 美股日K (NVDA) ===")
try:
    df = ak.stock_us_daily(symbol="NVDA", adjust="qfq")
    print(f"  行数: {len(df)}, 列: {list(df.columns)}")
    print(df.tail(3).to_string())
except Exception as e:
    print(f"  失败: {e}")

# === 2. 财经要闻/宏观新闻 ===
print("\n=== 2. 东方财富财经要闻 ===")
try:
    df2 = ak.stock_info_global_em()
    print(f"  行数: {len(df2)}, 列: {list(df2.columns)}")
    for _, r in df2.head(5).iterrows():
        t_col = [c for c in df2.columns if "时间" in c or "日期" in c]
        n_col = [c for c in df2.columns if "标题" in c or "内容" in c or "摘要" in c]
        t = str(r[t_col[0]])[:16] if t_col else ""
        n = str(r[n_col[0]])[:60] if n_col else str(r.iloc[0])[:60]
        print(f"  [{t}] {n}")
except Exception as e:
    print(f"  stock_info_global_em 失败: {e}")
    try:
        df2 = ak.news_cctv(date="20260227")
        print(f"  news_cctv 行数: {len(df2)}, 列: {list(df2.columns)}")
        for _, r in df2.head(3).iterrows():
            print(f"  {r.iloc[0]}: {str(r.iloc[1])[:60]}")
    except Exception as e2:
        print(f"  news_cctv 也失败: {e2}")

# === 3. 板块新闻 ===
print("\n=== 3. 东方财富概念板块资讯 ===")
try:
    df3 = ak.stock_board_concept_info_ths(symbol="AI")
    print(f"  行数: {len(df3)}, 列: {list(df3.columns)}")
except Exception as e:
    print(f"  concept_info_ths 失败: {e}")

# === 4. 全球财经快讯 ===
print("\n=== 4. 金十快讯 ===")
try:
    df4 = ak.js_news(timestamp="20260228")
    print(f"  行数: {len(df4)}, 列: {list(df4.columns)}")
    for _, r in df4.head(5).iterrows():
        print(f"  {str(r.iloc[0])[:80]}")
except Exception as e:
    print(f"  js_news 失败: {e}")

print("\n=== 完成 ===")
