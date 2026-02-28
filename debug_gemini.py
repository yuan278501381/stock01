"""调试：验证 GEMINI_API_KEY 读取 + Gemini 调用"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

# 检查 API key 读取
from evaluate_stocks import GEMINI_API_KEY, fetch_news, analyze_news_with_gemini, get_stock_boards

print(f"GEMINI_API_KEY 长度: {len(GEMINI_API_KEY)} ({'已配置' if GEMINI_API_KEY else '未配置'})")
print(f"前8位: {GEMINI_API_KEY[:8]}...")

code = "sz.300830"
boards = get_stock_boards(code)
name = boards.get("_name", "") or ""
industry = boards.get("industry", "") or ""
print(f"股票: {name}, 行业: {industry}")

news = fetch_news(code, name)
print(f"个股专属新闻: {len(news)} 条")
for n in news:
    print(f"  [{n['time'][:10]}] {n['title']}")

if news:
    print("\n--- 调用 Gemini 分析 ---")
    score, reason = analyze_news_with_gemini(name, code, industry, news)
    print(f"Gemini 返回分数: {score}")
    print(f"Gemini 分析理由: {reason}")
