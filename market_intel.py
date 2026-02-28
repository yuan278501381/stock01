"""
市场情报收集与 Gemini 综合分析模块

5层情报: 美股科技龙头 | 宏观政策 | 行业动态 | 个股新闻 | 量化信号
→ 统一喂给 Gemini Flash → 输出候选股消息面评分和操作建议
"""

import sys
import os
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ============================================================
# 配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
_CONFIG = {}
if os.path.exists(_CONFIG_FILE):
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            _CONFIG = json.load(f)
    except Exception:
        pass
GEMINI_API_KEY = _CONFIG.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")

# 美股科技龙头列表
US_TECH_SYMBOLS = {
    "NVDA": "英伟达",
    "GOOGL": "谷歌",
    "MSFT": "微软",
    "META": "Meta",
    "AAPL": "苹果",
    "AMZN": "亚马逊",
}


# ============================================================
# 层1: 美股科技龙头近况
# ============================================================
def fetch_us_tech_signals(days=5):
    """获取美股科技龙头近N日走势摘要"""
    try:
        import akshare as ak
        lines = []
        for symbol, name_cn in US_TECH_SYMBOLS.items():
            try:
                df = ak.stock_us_daily(symbol=symbol, adjust="qfq")
                if df is None or df.empty:
                    continue
                recent = df.tail(days)
                if recent.empty:
                    continue
                latest = recent.iloc[-1]
                first = recent.iloc[0]
                pct = (latest["close"] / first["open"] - 1) * 100
                lines.append(
                    f"  {name_cn}({symbol}): "
                    f"最新${latest['close']:.2f}, "
                    f"{days}日涨跌{pct:+.1f}%, "
                    f"成交量{latest['volume']/1e6:.0f}M"
                )
            except Exception:
                continue
        return "\n".join(lines) if lines else "（美股数据获取失败）"
    except Exception:
        return "（AKShare未安装或不可用）"


# ============================================================
# 层2: 宏观政策/全球财经要闻
# ============================================================
def fetch_macro_news(max_items=20):
    """获取最新全球财经要闻（东方财富）"""
    try:
        import akshare as ak
        df = ak.stock_info_global_em()
        if df is None or df.empty:
            return "（宏观新闻获取失败）"

        lines = []
        for _, row in df.head(max_items).iterrows():
            title = str(row.get("标题", ""))
            summary = str(row.get("摘要", ""))[:80]
            time_str = str(row.get("发布时间", ""))[:16]
            lines.append(f"  [{time_str}] {title}")
            if summary and summary != title:
                lines.append(f"    摘要: {summary}")
        return "\n".join(lines) if lines else "（无宏观新闻）"
    except Exception as e:
        return f"（宏观新闻获取异常: {str(e)[:40]}）"


# ============================================================
# 层3: 行业/板块动态
# ============================================================
def fetch_sector_news(concepts, max_per_concept=5):
    """通过全球财经要闻中筛选行业关键词"""
    try:
        import akshare as ak
        df = ak.stock_info_global_em()
        if df is None or df.empty:
            return "（板块新闻获取失败）"

        # 扩展关键词: 概念名 + 常见关联词
        SECTOR_KEYWORDS = {
            "AI": ["AI", "人工智能", "大模型", "智能体", "GPT", "芯片", "算力",
                   "英伟达", "谷歌", "OpenAI", "DeepSeek", "机器人"],
            "商业航天": ["航天", "火箭", "卫星", "太空", "SpaceX", "星链",
                      "发射", "航空"],
        }
        # 用户传入的 concepts 可能不在预设中,直接作为关键词
        all_keywords = []
        for c in concepts:
            all_keywords.extend(SECTOR_KEYWORDS.get(c, [c]))

        lines = []
        count = 0
        for _, row in df.iterrows():
            if count >= max_per_concept * len(concepts):
                break
            title = str(row.get("标题", ""))
            summary = str(row.get("摘要", ""))
            text = title + summary
            matched = [kw for kw in all_keywords if kw in text]
            if matched:
                time_str = str(row.get("发布时间", ""))[:16]
                lines.append(f"  [{time_str}] {title} (关联:{','.join(matched[:3])})")
                count += 1
        return "\n".join(lines) if lines else "（未找到相关板块新闻）"
    except Exception as e:
        return f"（板块新闻获取异常: {str(e)[:40]}）"


# ============================================================
# 层4: 批量个股新闻
# ============================================================
def fetch_batch_stock_news(stock_list, max_per_stock=5):
    """批量获取个股新闻

    Args:
        stock_list: list of dict, 每个含 code, name
    Returns:
        dict: {code: [title, ...]}
    """
    try:
        import akshare as ak
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=7)
        result = {}

        for item in stock_list:
            code = item["code"]
            name = item.get("name", "")
            pure = code.split(".")[-1] if "." in code else code
            try:
                df = ak.stock_news_em(symbol=pure)
                if df is None or df.empty:
                    continue

                col_title = next((c for c in df.columns if "标题" in c), None)
                col_time = next((c for c in df.columns if "时间" in c), None)
                if not col_title:
                    continue

                titles = []
                for _, row in df.iterrows():
                    title = str(row[col_title])
                    # 仅保留标题含股票名的个股专属新闻
                    if name and name not in title and pure not in title:
                        continue
                    titles.append(title)
                    if len(titles) >= max_per_stock:
                        break

                if titles:
                    result[code] = titles
            except Exception:
                continue

        return result
    except Exception:
        return {}


# ============================================================
# 汇总情报报告
# ============================================================
def build_intel_report(concepts, stock_list):
    """收集5层情报并汇总为结构化文本

    Args:
        concepts: list of str, 概念关键词如 ["AI", "商业航天"]
        stock_list: list of dict, 候选股票(含 code, name, total_score 等)
    Returns:
        str: 完整情报报告文本
    """
    print("[情报] 层1: 获取美股科技龙头近况...")
    us_signals = fetch_us_tech_signals(days=5)

    print("[情报] 层2: 获取全球财经要闻...")
    macro_news = fetch_macro_news(max_items=15)

    print("[情报] 层3: 获取行业板块动态...")
    sector_news = fetch_sector_news(concepts, max_per_concept=8)

    print("[情报] 层4: 获取个股新闻...")
    stock_news = fetch_batch_stock_news(stock_list[:20])

    # 层5: 量化信号（直接从 stock_list 中提取）
    quant_lines = []
    for r in stock_list:
        code = r["code"]
        name = r.get("name", "")[:6]
        quant_lines.append(
            f"  {code} {name} "
            f"总分:{r.get('total_score',0):+d} "
            f"技:{r.get('tech_score',0):+d} "
            f"估:{r.get('val_score',0):+d} "
            f"基:{r.get('fund_score',0):+d} "
            f"风:{r.get('risk_score',0):+d} "
            f"动:{r.get('mom_score',0):+d} "
            f"资:{r.get('flow_score',0):+d} "
            f"热:{r.get('heat_score',0):+d} "
            f"涨跌:{r.get('pctChg',0):+.1f}% "
            f"行业:{r.get('industry','')}"
        )

    # 个股新闻部分
    stock_news_text = ""
    if stock_news:
        for code, titles in stock_news.items():
            name = next((r.get("name", "") for r in stock_list if r["code"] == code), code)
            stock_news_text += f"  {name}({code}):\n"
            for t in titles:
                stock_news_text += f"    - {t}\n"
    else:
        stock_news_text = "  （个股专属新闻较少）"

    report = f"""## 层1: 美股科技龙头走势（近5日）
{us_signals}

## 层2: 全球财经要闻（最新）
{macro_news}

## 层3: 行业板块动态 (关注: {', '.join(concepts)})
{sector_news}

## 层4: 个股新闻
{stock_news_text}

## 层5: 候选股量化评分
{chr(10).join(quant_lines)}"""

    print(f"[情报] 情报收集完成，共 {len(report)} 字符")
    return report


# ============================================================
# Gemini 综合分析
# ============================================================
def gemini_analyze_candidates(intel_report, stock_list, concepts):
    """调用 Gemini Flash 综合分析候选股

    Returns:
        list of dict: [{code, news_score, reason}, ...]
    """
    if not GEMINI_API_KEY:
        print("[警告] GEMINI_API_KEY 未配置，跳过 Gemini 分析")
        return []

    try:
        import time
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        # 候选股列表
        candidates_text = ""
        for r in stock_list:
            candidates_text += (
                f"{r['code']}|{r.get('name','')}|"
                f"总分{r.get('total_score',0):+d}|"
                f"涨跌{r.get('pctChg',0):+.1f}%|"
                f"概念:{r.get('concept','')[:30]}\n"
            )

        prompt = f"""你是A股顶级投资分析师。基于以下市场情报和量化评分，对候选股票做出消息面评估。

# 市场情报
{intel_report}

# 候选股票列表
{candidates_text}

# 分析要求
1. 结合5层情报，给每只候选股一个消息面评分（-15到+15的整数）
2. 重点考虑:
   - 美股科技龙头走势对A股AI/科技概念的映射效应
   - 宏观政策和重大事件对特定行业的影响
   - 个股专属新闻的实质性利好/利空
   - 板块热点和资金流向的联动效应
3. 对每只股票给出1句话理由

# 输出格式
严格输出JSON数组，不要其他文字:
[
  {{"code": "sz.300830", "news_score": 8, "reason": "AI智能体概念核心标的，受益于华为技术发布"}},
  ...
]"""

        # 带重试的 API 调用（处理 429 rate limit）
        max_retries = 3
        retry_delays = [5, 15, 30]
        text = None
        for attempt in range(max_retries + 1):
            try:
                print(f"[Gemini] 提交分析请求...{f' (重试{attempt})' if attempt > 0 else ''}")
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                )
                text = response.text.strip()
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str and attempt < max_retries:
                    wait = retry_delays[attempt]
                    print(f"[Gemini] API 限速，等待 {wait} 秒后重试...")
                    time.sleep(wait)
                else:
                    raise

        if not text:
            return []

        # 解析 JSON
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        results = json.loads(text)
        print(f"[Gemini] 分析完成，返回 {len(results)} 只股票评分")
        return results

    except json.JSONDecodeError as e:
        print(f"[Gemini] JSON解析失败: {str(e)[:60]}")
        print(f"[Gemini] 原始返回: {text[:200] if text else '(无)'}")
        return []
    except Exception as e:
        print(f"[Gemini] 分析失败: {str(e)[:80]}")
        return []


# ============================================================
# 主入口: 对候选股执行完整的情报分析和评分更新
# ============================================================
def enrich_with_intel(results, concepts, top_n=30):
    """对评估结果补充市场情报 + Gemini 消息面分析

    Args:
        results: list of dict, evaluate_single() 的结果列表
        concepts: list of str, 概念关键词
        top_n: 分析多少只候选股

    Effects:
        原地更新 results 中每只股票的 news_score, news_signals, total_score, action
    """
    if not results:
        return

    # 取 top 候选
    results.sort(key=lambda x: x["total_score"], reverse=True)
    candidates = results[:top_n]

    # 收集情报
    intel_report = build_intel_report(concepts, candidates)

    # Gemini 分析
    gemini_results = gemini_analyze_candidates(intel_report, candidates, concepts)

    if not gemini_results:
        print("[情报] Gemini 未返回结果，消息面保持0分")
        return

    # 应用评分
    score_map = {r["code"]: r for r in gemini_results}
    updated = 0
    for r in results:
        gr = score_map.get(r["code"])
        if gr:
            old_news = r.get("news_score", 0)
            new_news = max(-15, min(15, gr.get("news_score", 0)))
            reason = gr.get("reason", "")

            r["total_score"] = r["total_score"] - old_news + new_news
            r["news_score"] = new_news
            r["news_signals"] = [f"[Gemini] {new_news:+d}分 | {reason}"]

            # 重算建议
            total = r["total_score"]
            if total >= 65:
                r["action"] = "** 强烈买入"
            elif total >= 30:
                r["action"] = "*  建议买入"
            elif total <= -45:
                r["action"] = "** 强烈卖出"
            elif total <= -15:
                r["action"] = "*  建议卖出"
            else:
                r["action"] = "-  观望"
            updated += 1

    print(f"[情报] 已更新 {updated} 只股票的消息面评分")

    # 重新排序
    results.sort(key=lambda x: x["total_score"], reverse=True)


# ============================================================
# 独立测试
# ============================================================
if __name__ == "__main__":
    print("=== 市场情报模块独立测试 ===\n")

    # 模拟几只候选股
    mock_stocks = [
        {"code": "sz.300830", "name": "金现代", "total_score": 10,
         "tech_score": 5, "val_score": -19, "fund_score": -13,
         "risk_score": 7, "mom_score": 4, "flow_score": 11, "heat_score": 0,
         "news_score": 0, "pctChg": 20.0, "industry": "软件",
         "concept": "AI应用,AI智能体,信创"},
    ]

    report = build_intel_report(["AI"], mock_stocks)
    print("\n--- 情报报告 ---")
    print(report[:1000])

    if GEMINI_API_KEY:
        print("\n--- Gemini 分析 ---")
        results = gemini_analyze_candidates(report, mock_stocks, ["AI"])
        for r in results:
            print(f"  {r['code']}: {r.get('news_score',0):+d} | {r.get('reason','')}")
