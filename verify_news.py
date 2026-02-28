"""验证消息面八维度集成"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from evaluate_stocks import *
from evaluate_stocks import fetch_news, score_news, fetch_capital_flow

CODE = "sz.300830"
print(f"=== 验证 {CODE} 消息面 ===")

boards = get_stock_boards(CODE)
name = boards.get("_name", "") or ""
print(f"股票名称: {name}")

news = fetch_news(CODE, name)
print(f"过滤后个股专属新闻: {len(news)} 条")
for n in news:
    print(f"  [{n['time'][:10]}] w={n['weight']:.1f} {n['title'][:40]}")

news_score, news_signals = score_news(news)
print(f"\n消息面评分: {news_score:+d}")
for s in news_signals:
    print(f"  {s}")

# 完整评估
flow = fetch_capital_flow(CODE)
result = evaluate_single(CODE, flow_data=flow, news_data=news)
if result:
    print(f"\n=== 八维度总览 ===")
    print(f"总分: {result['total_score']:+d}  建议: {result['action']}")
    print(f"技:{result['tech_score']:+d} 估:{result['val_score']:+d} 基:{result['fund_score']:+d} 风:{result['risk_score']:+d}"
          f" 动:{result['mom_score']:+d} 资:{result['flow_score']:+d} 消:{result['news_score']:+d} 热:{result.get('heat_score',0):+d}")
