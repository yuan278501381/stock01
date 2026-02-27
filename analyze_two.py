"""分析 300830 和 300317 为何大涨、模型为何未捕获"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from evaluate_stocks import *
import pandas as pd

for code in ["sz.300830", "sz.300317"]:
    r = evaluate_single(code)
    if not r:
        print(f"=== {code}: 无法评估 ===")
        continue

    print(f"\n{'='*80}")
    print(f"  {code} {r['name']}  板块:{r['board']}")
    print(f"{'='*80}")
    print(f"  收盘: {r['close']:.2f}  涨跌: {r['pctChg']:.2f}%")
    print(f"  总分: {r['total_score']}  技术:{r['tech_score']}  估值:{r['val_score']}  基本:{r['fund_score']}  风险:{r['risk_score']}")
    print(f"\n  技术信号:")
    for s in r['tech_signals']:
        print(f"    {s}")
    print(f"\n  估值信号:")
    for s in r['val_signals']:
        print(f"    {s}")
    print(f"\n  基本面:")
    for s in r['fund_signals']:
        print(f"    {s}")
    print(f"\n  风险:")
    for s in r['risk_signals']:
        print(f"    {s}")
    print(f"\n  概念: {r['concept']}")
    print(f"  行业: {r['industry']}")

    # 近10日K线
    df = load_daily_data(code)
    if df is not None:
        recent = df.tail(10)[["date", "close", "pctChg", "volume", "turn", "peTTM"]].copy()
        print(f"\n  近10日K线:")
        print(recent.to_string(index=False))

        # 近5日涨跌幅
        if len(df) >= 5:
            pct5 = ((df.iloc[-1]["close"] / df.iloc[-5]["close"]) - 1) * 100
            print(f"\n  近5日累计涨跌: {pct5:.2f}%")
        if len(df) >= 20:
            pct20 = ((df.iloc[-1]["close"] / df.iloc[-20]["close"]) - 1) * 100
            print(f"  近20日累计涨跌: {pct20:.2f}%")

        # 量比趋势
        vol_recent = df.tail(5)["volume"].mean()
        vol_prev = df.tail(20).head(15)["volume"].mean()
        if vol_prev > 0:
            print(f"  近5日/前15日均量比: {vol_recent/vol_prev:.2f}")
