import sys
sys.stdout.reconfigure(encoding="utf-8")
import akshare as ak

df = ak.stock_news_em(symbol="300830")
print("列名:", list(df.columns))
print("行数:", len(df))
print()
for i, row in df.head(15).iterrows():
    cols = df.columns.tolist()
    # 找时间和标题列
    time_col = [c for c in cols if "时间" in c or "日期" in c]
    title_col = [c for c in cols if "标题" in c]
    t = row[time_col[0]] if time_col else ""
    n = row[title_col[0]] if title_col else ""
    print(f"[{str(t)[:16]}] {n}")
