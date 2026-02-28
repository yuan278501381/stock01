"""
沪深A股专业级技术分析与买卖评估工具

分析维度:
  - 技术面 (±40): MA, MACD, RSI, KDJ, 布林带, 量比, DMI/ADX, WR, CCI, OBV, ATR, VWAP
  - 估值面 (±25): PE/PB/PS 水平判断
  - 基本面 (±25): ROE, 营收增长, 净利润增长, 负债率
  - 风险面 (0~10): ST, 停牌, 波动率异常
  - 动量面 (±15): 近5/20日涨跌幅, 连续下跌, 距高低点位置
  - 资金面 (±15): 放量上涨天数, 缩量企稳, 换手率加速, 天量天价风险
  - 热度面 (±10): 板块联动热度, 多热门概念叠加

用法:
  python evaluate_stocks.py                  # 评估所有已下载的股票
  python evaluate_stocks.py --code sh.600000 # 评估指定股票（详细报告）
  python evaluate_stocks.py --top 50         # 显示前50只推荐
  python evaluate_stocks.py --board 创业板   # 只评估创业板股票
  python evaluate_stocks.py --board 创业板 科创板 --concept AI  # 板块+概念组合筛选
"""

import argparse
import os
import sys

# Windows 终端 UTF-8 兼容
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import requests
import pandas as pd


# ============================================================
# 配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DAILY_DIR = os.path.join(BASE_DIR, "data", "daily")
FINANCE_DIR = os.path.join(BASE_DIR, "data", "finance")
BOARDS_DIR = os.path.join(BASE_DIR, "data", "boards")

# 加载外部配置（API Key 等）
import json as _json
_CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
_CONFIG = {}
if os.path.exists(_CONFIG_FILE):
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as _f:
            _CONFIG = _json.load(_f)
    except Exception:
        pass
GEMINI_API_KEY = _CONFIG.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")


MIN_ROWS = 60  # 最少数据行数

# ============================================================
# 消息面 — 金融情感词典
# ============================================================
# 重大利好：标题匹配即得高分
NEWS_MAJOR_POS = [
    "中标", "大合同", "战略合作协议", "股权激励", "回购",
    "增持", "高送转", "并购", "重组", "业绩超预期",
    "首次盈利", "扭亏", "获批", "上市许可", "垄断企业",
    "获得专利", "技术突破", "战略投资", "入股",
]
# 普通正面新闻
NEWS_MINOR_POS = [
    "合作", "签约", "中选", "新客户", "扩产", "新订单",
    "业绩增长", "净利润增长", "营收增长", "新产品",
    "降本增效", "份额提升", "加大投入",
    "龙虎榜", "涨停", "大幅上涨", "主力资金流入", "获机构重点关注",
    "创近期新高",
]
# 重大利空：标题匹配即扣高分
NEWS_MAJOR_NEG = [
    "亏损预告", "业绩大幅下滑", "行政处罚", "被调查", "立案",
    "违规", "诉讼", "仲裁", "财务造假", "强制退市",
    "债务违约", "股权冻结", "大规模裁员", "停产",
    "退市风险", "被ST", "欺诈发行",
]
# 普通负面新闻
NEWS_MINOR_NEG = [
    "减持", "解禁", "下调评级", "业绩下滑", "竞争加剧",
    "产能过剩", "客户流失", "亏损", "计提减值", "商誉减值",
]




# ============================================================
# 技术指标计算 (12种)
# ============================================================

def calc_ma(df, periods=(5, 10, 20, 60)):
    for p in periods:
        df[f"MA{p}"] = df["close"].rolling(window=p).mean()
    return df


def calc_macd(df, fast=12, slow=26, signal=9):
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["DIF"] = ema_fast - ema_slow
    df["DEA"] = df["DIF"].ewm(span=signal, adjust=False).mean()
    df["MACD"] = 2 * (df["DIF"] - df["DEA"])
    return df


def calc_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def calc_kdj(df, n=9, m1=3, m2=3):
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n) * 100
    rsv = rsv.fillna(50)
    df["K"] = rsv.ewm(com=m1 - 1, adjust=False).mean()
    df["D"] = df["K"].ewm(com=m2 - 1, adjust=False).mean()
    df["J"] = 3 * df["K"] - 2 * df["D"]
    return df


def calc_boll(df, period=20, num_std=2):
    df["BOLL_MID"] = df["close"].rolling(window=period).mean()
    std = df["close"].rolling(window=period).std()
    df["BOLL_UP"] = df["BOLL_MID"] + num_std * std
    df["BOLL_DN"] = df["BOLL_MID"] - num_std * std
    return df


def calc_volume_indicators(df):
    df["VOL_MA5"] = df["volume"].rolling(window=5).mean()
    df["VOL_MA10"] = df["volume"].rolling(window=10).mean()
    df["VOL_RATIO"] = df["volume"] / df["VOL_MA5"]
    return df


def calc_dmi_adx(df, period=14):
    """DMI/ADX 趋势强度指标"""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["ADX"] = dx.ewm(span=period, adjust=False).mean()
    df["PLUS_DI"] = plus_di
    df["MINUS_DI"] = minus_di
    return df


def calc_wr(df, period=14):
    """WR 威廉指标"""
    high_n = df["high"].rolling(window=period).max()
    low_n = df["low"].rolling(window=period).min()
    df["WR"] = -100 * (high_n - df["close"]) / (high_n - low_n)
    return df


def calc_cci(df, period=14):
    """CCI 顺势指标"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma_tp = tp.rolling(window=period).mean()
    md = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    df["CCI"] = (tp - ma_tp) / (0.015 * md)
    return df


def calc_obv(df):
    """OBV 能量潮"""
    direction = np.sign(df["close"].diff())
    df["OBV"] = (direction * df["volume"]).cumsum()
    df["OBV_MA5"] = df["OBV"].rolling(window=5).mean()
    return df


def calc_atr(df, period=14):
    """ATR 真实波幅"""
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift()).abs()
    tr3 = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(span=period, adjust=False).mean()
    df["ATR_PCT"] = df["ATR"] / df["close"] * 100  # ATR占比
    return df


def calc_vwap(df):
    """VWAP 成交量加权平均价（滚动20日）"""
    cumvol = df["volume"].rolling(window=20).sum()
    cumtp = (df["close"] * df["volume"]).rolling(window=20).sum()
    df["VWAP"] = cumtp / cumvol
    return df


def calc_all_indicators(df):
    """计算全部12种技术指标"""
    df = calc_ma(df)
    df = calc_macd(df)
    df = calc_rsi(df)
    df = calc_kdj(df)
    df = calc_boll(df)
    df = calc_volume_indicators(df)
    df = calc_dmi_adx(df)
    df = calc_wr(df)
    df = calc_cci(df)
    df = calc_obv(df)
    df = calc_atr(df)
    df = calc_vwap(df)
    return df


# ============================================================
# 四维度评估
# ============================================================

def score_technical(df):
    """技术面评分 (满分 ±40)"""
    if len(df) < MIN_ROWS:
        return 0, []

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0
    signals = []

    # --- MA 均线 (±8) ---
    mas = [latest.get(f"MA{p}") for p in [5, 10, 20, 60]]
    if all(pd.notna(v) for v in mas):
        ma5, ma10, ma20, ma60 = mas
        if ma5 > ma10 > ma20 > ma60:
            score += 8;  signals.append("均线多头排列(+8)")
        elif ma5 < ma10 < ma20 < ma60:
            score -= 8;  signals.append("均线空头排列(-8)")
        else:
            p5, p10 = prev.get("MA5"), prev.get("MA10")
            if pd.notna(p5) and pd.notna(p10):
                if p5 <= p10 and ma5 > ma10:
                    score += 5;  signals.append("MA5/10金叉(+5)")
                elif p5 >= p10 and ma5 < ma10:
                    score -= 5;  signals.append("MA5/10死叉(-5)")

    # --- MACD (±7) ---
    vals = [latest.get("DIF"), latest.get("DEA"), prev.get("DIF"), prev.get("DEA")]
    if all(pd.notna(v) for v in vals):
        if prev["DIF"] <= prev["DEA"] and latest["DIF"] > latest["DEA"]:
            score += 6;  signals.append("MACD金叉(+6)")
        elif prev["DIF"] >= prev["DEA"] and latest["DIF"] < latest["DEA"]:
            score -= 6;  signals.append("MACD死叉(-6)")
        if latest["MACD"] > 0 and latest["MACD"] > prev["MACD"]:
            score += 1;  signals.append("MACD柱放大(+1)")
        elif latest["MACD"] < 0 and latest["MACD"] < prev["MACD"]:
            score -= 1;  signals.append("MACD柱缩小(-1)")

    # --- RSI (±5) ---
    if pd.notna(latest.get("RSI")):
        rsi = latest["RSI"]
        if rsi < 30:
            score += 5;  signals.append(f"RSI超卖{rsi:.0f}(+5)")
        elif rsi < 40:
            score += 2;  signals.append(f"RSI偏低{rsi:.0f}(+2)")
        elif rsi > 70:
            score -= 5;  signals.append(f"RSI超买{rsi:.0f}(-5)")
        elif rsi > 60:
            score -= 2;  signals.append(f"RSI偏高{rsi:.0f}(-2)")

    # --- KDJ (±5) ---
    vals = [latest.get("K"), latest.get("D"), latest.get("J")]
    if all(pd.notna(v) for v in vals):
        j = latest["J"]
        if j < 20:
            score += 3;  signals.append(f"KDJ超卖J={j:.0f}(+3)")
        elif j > 80:
            score -= 3;  signals.append(f"KDJ超买J={j:.0f}(-3)")
        pk, pd_ = prev.get("K"), prev.get("D")
        if pd.notna(pk) and pd.notna(pd_):
            if pk <= pd_ and latest["K"] > latest["D"]:
                score += 2;  signals.append("KDJ金叉(+2)")
            elif pk >= pd_ and latest["K"] < latest["D"]:
                score -= 2;  signals.append("KDJ死叉(-2)")

    # --- BOLL (±3) ---
    vals = [latest.get("BOLL_UP"), latest.get("BOLL_DN")]
    if all(pd.notna(v) for v in vals):
        if latest["close"] <= latest["BOLL_DN"]:
            score += 3;  signals.append("触及布林下轨(+3)")
        elif latest["close"] >= latest["BOLL_UP"]:
            score -= 3;  signals.append("触及布林上轨(-3)")

    # --- 量比 (±3) ---
    if pd.notna(latest.get("VOL_RATIO")):
        vr = latest["VOL_RATIO"]
        if vr > 2.0 and latest["close"] > prev["close"]:
            score += 3;  signals.append(f"放量上涨{vr:.1f}(+3)")
        elif vr > 2.0 and latest["close"] < prev["close"]:
            score -= 3;  signals.append(f"放量下跌{vr:.1f}(-3)")

    # --- DMI/ADX (±3) ---
    vals = [latest.get("ADX"), latest.get("PLUS_DI"), latest.get("MINUS_DI")]
    if all(pd.notna(v) for v in vals):
        if latest["ADX"] > 25 and latest["PLUS_DI"] > latest["MINUS_DI"]:
            score += 3;  signals.append(f"ADX强势上升{latest['ADX']:.0f}(+3)")
        elif latest["ADX"] > 25 and latest["PLUS_DI"] < latest["MINUS_DI"]:
            score -= 3;  signals.append(f"ADX强势下跌{latest['ADX']:.0f}(-3)")

    # --- WR (±2) ---
    if pd.notna(latest.get("WR")):
        wr = latest["WR"]
        if wr < -80:
            score += 2;  signals.append(f"WR超卖{wr:.0f}(+2)")
        elif wr > -20:
            score -= 2;  signals.append(f"WR超买{wr:.0f}(-2)")

    # --- CCI (±2) ---
    if pd.notna(latest.get("CCI")):
        cci = latest["CCI"]
        if cci < -100:
            score += 2;  signals.append(f"CCI超卖{cci:.0f}(+2)")
        elif cci > 100:
            score -= 2;  signals.append(f"CCI超买{cci:.0f}(-2)")

    # --- OBV (±1) ---
    vals = [latest.get("OBV"), latest.get("OBV_MA5")]
    if all(pd.notna(v) for v in vals):
        if latest["OBV"] > latest["OBV_MA5"] and latest["close"] > prev["close"]:
            score += 1;  signals.append("OBV量价齐升(+1)")
        elif latest["OBV"] < latest["OBV_MA5"] and latest["close"] < prev["close"]:
            score -= 1;  signals.append("OBV量价齐跌(-1)")

    # --- ATR波动 (±1) ---
    if pd.notna(latest.get("ATR_PCT")):
        atr_pct = latest["ATR_PCT"]
        if atr_pct < 2.0:
            score += 1;  signals.append(f"低波动{atr_pct:.1f}%(+1)")

    return max(-40, min(40, score)), signals


def score_valuation(latest):
    """估值面评分 (满分 ±25)"""
    score = 0
    signals = []

    # PE 评分 (±10)
    pe = latest.get("peTTM")
    if pd.notna(pe) and pe > 0:
        if pe <= 15:
            score += 10;  signals.append(f"PE低估{pe:.1f}(+10)")
        elif pe <= 25:
            score += 5;   signals.append(f"PE合理{pe:.1f}(+5)")
        elif pe <= 50:
            score -= 3;   signals.append(f"PE偏高{pe:.1f}(-3)")
        else:
            score -= 10;  signals.append(f"PE高估{pe:.1f}(-10)")
    elif pd.notna(pe) and pe < 0:
        score -= 10;  signals.append("PE为负(亏损)(-10)")

    # PB 评分 (±8)
    pb = latest.get("pbMRQ")
    if pd.notna(pb) and pb > 0:
        if pb <= 1.0:
            score += 8;   signals.append(f"PB破净{pb:.2f}(+8)")
        elif pb <= 2.0:
            score += 4;   signals.append(f"PB低估{pb:.2f}(+4)")
        elif pb <= 5.0:
            score -= 2;   signals.append(f"PB偏高{pb:.2f}(-2)")
        else:
            score -= 8;   signals.append(f"PB高估{pb:.2f}(-8)")

    # PS 评分 (±7)
    ps = latest.get("psTTM")
    if pd.notna(ps) and ps > 0:
        if ps <= 2.0:
            score += 7;   signals.append(f"PS低估{ps:.2f}(+7)")
        elif ps <= 5.0:
            score += 3;   signals.append(f"PS合理{ps:.2f}(+3)")
        elif ps > 10:
            score -= 7;   signals.append(f"PS高估{ps:.2f}(-7)")

    return max(-25, min(25, score)), signals


def load_finance_data(code):
    """加载财务数据"""
    filepath = os.path.join(FINANCE_DIR, code.replace(".", "_") + ".csv")
    if not os.path.exists(filepath):
        return None
    try:
        return pd.read_csv(filepath)
    except Exception:
        return None


def score_fundamental(code):
    """基本面评分 (满分 ±25)"""
    fin = load_finance_data(code)
    if fin is None or fin.empty:
        return 0, []

    score = 0
    signals = []

    # 取最新一期盈利数据
    profit = fin[fin["data_type"] == "profit"].sort_values("statDate", ascending=False)
    growth = fin[fin["data_type"] == "growth"].sort_values("statDate", ascending=False)

    # ROE (±8)
    if not profit.empty and "roeAvg" in profit.columns:
        roe = pd.to_numeric(profit.iloc[0].get("roeAvg"), errors="coerce")
        if pd.notna(roe):
            if roe >= 15:
                score += 8;   signals.append(f"ROE优秀{roe:.1f}%(+8)")
            elif roe >= 10:
                score += 4;   signals.append(f"ROE良好{roe:.1f}%(+4)")
            elif roe >= 0:
                score += 0
            else:
                score -= 8;   signals.append(f"ROE为负{roe:.1f}%(-8)")

    # 营收增长 (±7)
    if not growth.empty and "YOYEquity" in growth.columns:
        rev_growth = pd.to_numeric(growth.iloc[0].get("YOYEquity"), errors="coerce")
        if pd.notna(rev_growth):
            if rev_growth >= 30:
                score += 7;   signals.append(f"营收高增长{rev_growth:.1f}%(+7)")
            elif rev_growth >= 10:
                score += 3;   signals.append(f"营收稳增长{rev_growth:.1f}%(+3)")
            elif rev_growth < -10:
                score -= 7;   signals.append(f"营收下滑{rev_growth:.1f}%(-7)")

    # 净利润增长 (±5)
    if not growth.empty and "YOYNI" in growth.columns:
        np_growth = pd.to_numeric(growth.iloc[0].get("YOYNI"), errors="coerce")
        if pd.notna(np_growth):
            if np_growth >= 30:
                score += 5;   signals.append(f"净利高增长{np_growth:.1f}%(+5)")
            elif np_growth >= 10:
                score += 2;   signals.append(f"净利稳增长{np_growth:.1f}%(+2)")
            elif np_growth < -20:
                score -= 5;   signals.append(f"净利大幅下滑{np_growth:.1f}%(-5)")

    # 毛利率 (±5)
    if not profit.empty and "gpMargin" in profit.columns:
        gpm = pd.to_numeric(profit.iloc[0].get("gpMargin"), errors="coerce")
        if pd.notna(gpm):
            if gpm >= 50:
                score += 5;   signals.append(f"高毛利率{gpm:.1f}%(+5)")
            elif gpm >= 30:
                score += 2;   signals.append(f"毛利率良好{gpm:.1f}%(+2)")
            elif gpm < 10:
                score -= 5;   signals.append(f"毛利率过低{gpm:.1f}%(-5)")

    return max(-25, min(25, score)), signals


def score_risk(latest):
    """风险面评分 (满分 ±10, 主要是减分项)"""
    score = 10  # 基础分
    signals = []

    # ST风险 (-10)
    is_st = latest.get("isST")
    if str(is_st) == "1":
        score -= 10;  signals.append("ST股票(-10)")

    # 停牌 (-5)
    trade_status = latest.get("tradestatus")
    if str(trade_status) == "0":
        score -= 5;   signals.append("停牌中(-5)")

    # 高波动率 (-3)
    atr_pct = latest.get("ATR_PCT")
    if pd.notna(atr_pct) and atr_pct > 5.0:
        score -= 3;   signals.append(f"高波动{atr_pct:.1f}%(-3)")

    # 极低成交量（流动性风险）(-2)
    vol_ratio = latest.get("VOL_RATIO")
    if pd.notna(vol_ratio) and vol_ratio < 0.3:
        score -= 2;   signals.append(f"极低量比{vol_ratio:.2f}(-2)")

    return max(0, min(10, score)), signals


def score_momentum(df):
    """动量面评分 (满分 ±15) — 超跌反弹 / 追高风险"""
    if len(df) < 20:
        return 0, []

    score = 0
    signals = []
    closes = df["close"].values
    pct_changes = df["pctChg"].values if "pctChg" in df.columns else np.diff(closes) / closes[:-1] * 100

    # --- 近5日涨跌幅 (±5) ---
    if len(closes) >= 6:
        ret5 = (closes[-1] / closes[-6] - 1) * 100
        if ret5 < -15:
            score += 5;  signals.append(f"5日深跌{ret5:.1f}%反弹机会(+5)")
        elif ret5 < -5:
            score += 2;  signals.append(f"5日回调{ret5:.1f}%(+2)")
        elif 5 <= ret5 <= 15:
            score += 3;  signals.append(f"5日上涨动量{ret5:+.1f}%(+3)")
        elif ret5 > 15:
            score -= 5;  signals.append(f"5日暴涨{ret5:+.1f}%追高风险(-5)")

    # --- 近20日涨跌幅 (±3) ---
    if len(closes) >= 21:
        ret20 = (closes[-1] / closes[-21] - 1) * 100
        if ret20 < -20:
            score += 3;  signals.append(f"20日深跌{ret20:.1f}%(+3)")
        elif ret20 > 30:
            score -= 3;  signals.append(f"20日大涨{ret20:+.1f}%(-3)")

    # --- 连续下跌天数 (0~+3) ---
    consec_down = 0
    for i in range(len(pct_changes) - 1, -1, -1):
        if pct_changes[i] < 0:
            consec_down += 1
        else:
            break
    if consec_down >= 5:
        score += 3;  signals.append(f"连跌{consec_down}天(+3)")
    elif consec_down >= 3:
        score += 1;  signals.append(f"连跌{consec_down}天(+1)")

    # --- 距20日低/高点 (±2) ---
    recent20 = closes[-20:]
    low20 = recent20.min()
    high20 = recent20.max()
    cur = closes[-1]
    if high20 > low20:
        pos = (cur - low20) / (high20 - low20)
        if pos < 0.1:
            score += 2;  signals.append(f"接近20日低点(+2)")
        elif pos > 0.9:
            score -= 2;  signals.append(f"接近20日高点(-2)")

    return max(-15, min(15, score)), signals


def fetch_capital_flow(code, days=10):
    """从东方财富 push2his API 获取个股主力资金流向 (近N天)"""
    pure = code.split(".")[-1] if "." in code else code
    market = "1" if code.startswith("sh") or pure.startswith("6") else "0"
    try:
        s = requests.Session()
        s.trust_env = False
        s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
        r = s.get(
            "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
            params={
                "secid": f"{market}.{pure}",
                "fields1": "f1,f2,f3",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                "klt": "101", "lmt": str(days),
            },
            timeout=5,
        )
        data = r.json()
        klines = data.get("data", {}).get("klines", [])
        rows = []
        for line in klines:
            p = line.split(",")
            rows.append({
                "date": p[0],
                "main_net": float(p[1]),       # 主力净流入(元)
                "main_pct": float(p[6]),       # 主力净流入占比%
                "super_net": float(p[2]),      # 超大单净流入
                "big_net": float(p[3]),        # 大单净流入
            })
        return rows
    except Exception:
        return None


def score_flow(df, flow_data=None):
    """资金面评分 (满分 ±15) — 优先用真实主力资金数据, 兆底用量价代理"""
    if len(df) < 20:
        return 0, []

    score = 0
    signals = []

    # ============ 真实资金流向数据 ============
    if flow_data and len(flow_data) >= 3:
        # --- 近N日主力累计净流入 (±6) ---
        total_main = sum(r["main_net"] for r in flow_data)
        total_main_wan = total_main / 10000  # 转万元
        if total_main_wan > 5000:
            score += 6;  signals.append(f"主力累计流入{total_main_wan:+.0f}万(+6)")
        elif total_main_wan > 1000:
            score += 3;  signals.append(f"主力累计流入{total_main_wan:+.0f}万(+3)")
        elif total_main_wan < -5000:
            score -= 6;  signals.append(f"主力累计流出{total_main_wan:+.0f}万(-6)")
        elif total_main_wan < -1000:
            score -= 3;  signals.append(f"主力累计流出{total_main_wan:+.0f}万(-3)")

        # --- 连续主力流入天数 (±4) ---
        consec_in = 0
        for r in reversed(flow_data):
            if r["main_net"] > 0:
                consec_in += 1
            else:
                break
        if consec_in >= 3:
            score += 4;  signals.append(f"主力连续流入{consec_in}天(+4)")
        elif consec_in >= 2:
            score += 2;  signals.append(f"主力连续流入{consec_in}天(+2)")

        consec_out = 0
        for r in reversed(flow_data):
            if r["main_net"] < 0:
                consec_out += 1
            else:
                break
        if consec_out >= 3:
            score -= 4;  signals.append(f"主力连续流出{consec_out}天(-4)")

        # --- 最新一日主力占比 (±5) ---
        latest_pct = flow_data[-1]["main_pct"]
        if latest_pct > 15:
            score += 5;  signals.append(f"今日主力占比{latest_pct:+.1f}%(+5)")
        elif latest_pct > 5:
            score += 3;  signals.append(f"今日主力占比{latest_pct:+.1f}%(+3)")
        elif latest_pct < -15:
            score -= 5;  signals.append(f"今日主力占比{latest_pct:+.1f}%(-5)")
        elif latest_pct < -5:
            score -= 3;  signals.append(f"今日主力占比{latest_pct:+.1f}%(-3)")

        # --- 汇总展示: 近3/5/10日 ---
        for period in [3, 5, 10]:
            subset = flow_data[-period:] if len(flow_data) >= period else flow_data
            if len(subset) < period:
                continue
            p_in = sum(r["main_net"] for r in subset if r["main_net"] > 0) / 10000
            p_out = sum(r["main_net"] for r in subset if r["main_net"] < 0) / 10000
            p_net = (p_in + p_out)
            signals.append(f"近{period}日 流入{p_in:+.0f}万 流出{p_out:+.0f}万 净额{p_net:+.0f}万")

        return max(-15, min(15, score)), signals

    # ============ 兆底: 量价行为代理 ============
    recent5 = df.tail(5)
    recent20 = df.tail(20)
    vol_ma20 = recent20["volume"].mean()

    if vol_ma20 <= 0:
        return 0, []

    # --- 近5日放量上涨天数 (+5) ---
    vol_up_days = 0
    for _, row in recent5.iterrows():
        if row["volume"] > vol_ma20 * 1.5 and row.get("pctChg", 0) > 0:
            vol_up_days += 1
    if vol_up_days >= 3:
        score += 5;  signals.append(f"5日内{vol_up_days}天放量上涨(+5)")
    elif vol_up_days >= 2:
        score += 3;  signals.append(f"5日内{vol_up_days}天放量上涨(+3)")

    # --- 缩量企稳 (+3) ---
    last3 = df.tail(3)
    if len(last3) == 3:
        pcts = last3["pctChg"].values if "pctChg" in last3.columns else [0, 0, 0]
        vols = last3["volume"].values
        prev5_pct = df.tail(8).head(5)["pctChg"].mean() if len(df) >= 8 else 0
        vol_shrink = all(v < vol_ma20 * 0.8 for v in vols)
        pct_stabilize = abs(pcts[-1]) < 2 and (pcts[-1] > pcts[0] or pcts[-1] > 0)
        if prev5_pct < -1 and vol_shrink and pct_stabilize:
            score += 3;  signals.append("缩量企稳(+3)")

    # --- 换手率加速 (±4) ---
    if "turn" in df.columns:
        turn5 = recent5["turn"].mean()
        prev15 = recent20.head(15)["turn"].mean()
        if prev15 > 0:
            turn_ratio = turn5 / prev15
            if turn_ratio > 2.0:
                score += 4;  signals.append(f"换手加速{turn_ratio:.1f}x(+4)")
            elif turn_ratio > 1.5:
                score += 2;  signals.append(f"换手升温{turn_ratio:.1f}x(+2)")

    # --- 天量天价风险 (-5) ---
    last = df.iloc[-1]
    if last["volume"] > vol_ma20 * 3 and last.get("pctChg", 0) > 5:
        score -= 5;  signals.append("天量天价风险(-5)")

    # --- 持续缩量下跌 (-3) ---
    if vol_up_days == 0:
        down_days = sum(1 for _, r in recent5.iterrows() if r.get("pctChg", 0) < 0)
        if down_days >= 4:
            score -= 3;  signals.append("持续缩量下跌(-3)")


    return max(-15, min(15, score)), signals


def fetch_news(code, name, days=7):
    """获取个股近N天的专属新闻（含时间衰减权重）

    Returns: list of dict {title, time, weight}
    """
    try:
        import akshare as ak
        from datetime import datetime, timedelta
        pure = code.split(".")[-1] if "." in code else code
        df = ak.stock_news_em(symbol=pure)
        if df is None or df.empty:
            return []

        # 字段标准化
        col_time = next((c for c in df.columns if "时间" in c or "日期" in c), None)
        col_title = next((c for c in df.columns if "标题" in c), None)
        col_content = next((c for c in df.columns if "内容" in c), None)
        if not col_time or not col_title:
            return []

        cutoff = datetime.now() - timedelta(days=days)
        items = []
        for _, row in df.iterrows():
            t_str = str(row[col_time])[:16]
            try:
                t = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
            except Exception:
                try:
                    t = datetime.strptime(t_str[:10], "%Y-%m-%d")
                except Exception:
                    continue
            if t < cutoff:
                continue

            title = str(row[col_title])
            col_source = next((c for c in df.columns if "来源" in c), None)
            source = str(row.get(col_source, "")) if col_source else ""

            # 严格过滤：标题必须含股票名或代码，或者来源是公司公告
            is_company_ann = any(x in source for x in ["公告", "披露", "交易所"])
            if name and name not in title and pure not in title and not is_company_ann:
                continue

            # 时间衰减权重
            age_days = (datetime.now() - t).total_seconds() / 86400
            if age_days < 1:
                weight = 1.0
            elif age_days < 2:
                weight = 0.8
            elif age_days < 3:
                weight = 0.6
            elif age_days < 5:
                weight = 0.4
            else:
                weight = 0.2

            items.append({"title": title, "time": t_str, "weight": weight})

        return items
    except Exception:
        return []


def analyze_news_with_gemini(stock_name, stock_code, industry, news_items):
    """将全量新闻发给 Gemini 做语义情感分析，返回 (score: int, reasoning: str)

    score 范围: -15 ~ +15
    考虑因素: 新闻实质内容、行业关联事件、时间衰减（越新越重要）
    """
    if not GEMINI_API_KEY or not news_items:
        return None, ""
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        # 构建新闻列表文本，按时间倒序（越新越靠前）
        news_text = ""
        for item in sorted(news_items, key=lambda x: x["time"], reverse=True):
            decay_label = {1.0: "今日", 0.8: "昨日", 0.6: "2天前", 0.4: "3-4天前"}.get(
                item["weight"], "更早"
            )
            news_text += f"[{decay_label} {item['time'][:10]}] {item['title']}\n"

        prompt = f"""你是A股专业投资分析师。请分析以下关于"{stock_name}"({stock_code}, 行业:{industry})的近期新闻，\
评估其对该股票**短期（1-5个交易日）**股价的影响。

## 新闻列表（越靠前越新，权重越高）
{news_text}

## 评分规则
- 分析每条新闻对该公司的**实质性**影响
- 考虑行业关联事件（如供应链伙伴、竞争对手、政策变化对该行业的影响）
- 越新的消息影响越大
- 综合给出 -15 到 +15 的整数评分，格式如下：

SCORE: <整数>
REASON: <1-2句中文说明，重点讲最有影响力的1-2条新闻>"""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()

        # 解析分数
        score = 0
        reason = ""
        for line in text.splitlines():
            if line.startswith("SCORE:"):
                try:
                    score = int(line.replace("SCORE:", "").strip())
                    score = max(-15, min(15, score))
                except Exception:
                    pass
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        return score, reason
    except Exception as e:
        return None, str(e)[:60]


def score_news(news_items, stock_name="", stock_code="", industry=""):
    """消息面评分 (±15)

    优先路径: Gemini 全量语义分析（有 API key 时）
    退化路径: 金融关键词词典 + 时间衰减
    """
    if not news_items:
        return 0, []

    signals = []

    # ============ 路径 A: Gemini 语义分析 ============
    if GEMINI_API_KEY:
        gemini_score, reason = analyze_news_with_gemini(
            stock_name, stock_code, industry, news_items
        )
        if gemini_score is not None:
            final = gemini_score
            tag = "Gemini分析"
            if final > 0:
                signals.append(f"[{tag}] 消息面正面 {final:+d}分 | {reason}")
            elif final < 0:
                signals.append(f"[{tag}] 消息面负面 {final:+d}分 | {reason}")
            else:
                signals.append(f"[{tag}] 消息面中性 0分 | {reason}")
            # 附最新3条标题
            for item in sorted(news_items, key=lambda x: x["time"], reverse=True)[:3]:
                t = item["time"][:10]
                signals.append(f"  [{t}] {item['title'][:40]}")
            return final, signals

    # ============ 路径 B: 关键词词典（兜底）============
    score = 0.0
    matched_titles = []

    for item in news_items:
        title = item["title"]
        w = item["weight"]
        t = item["time"]

        for kw in NEWS_MAJOR_POS:
            if kw in title:
                score += 8 * w
                signals.append(f"【利好】{kw}: {title[:25]}... (权重{w:.1f})")
                matched_titles.append(f"↑ {t[:10]} {title[:35]}")
                break

        for kw in NEWS_MAJOR_NEG:
            if kw in title:
                score -= 8 * w
                signals.append(f"【利空】{kw}: {title[:25]}... (权重{w:.1f})")
                matched_titles.append(f"↓ {t[:10]} {title[:35]}")
                break

        for kw in NEWS_MINOR_POS:
            if kw in title:
                score += 3 * w
                matched_titles.append(f"+ {t[:10]} {title[:35]}")
                break

        for kw in NEWS_MINOR_NEG:
            if kw in title:
                score -= 3 * w
                matched_titles.append(f"- {t[:10]} {title[:35]}")
                break

    final = int(max(-15, min(15, score)))
    if final > 0:
        signals.append(f"[词典] 消息面正面 {final:+d}分，{len(news_items)}条新闻")
    elif final < 0:
        signals.append(f"[词典] 消息面负面 {final:+d}分，{len(news_items)}条新闻")
    else:
        signals.append(f"[词典] 消息面中性 0分，{len(news_items)}条新闻")
    for t in matched_titles[:3]:
        signals.append(f"  {t}")

    return final, signals



# 板块信息
# ============================================================

_boards_cache = {}


def _normalize_code(raw_code):
    """将各种代码格式统一为 sh.600000 / sz.000636 格式"""
    raw_code = str(raw_code).strip()
    # 已经是 sh.600000 格式
    if "." in raw_code and len(raw_code) == 9:
        return raw_code
    # 纯6位数字
    if len(raw_code) == 6 and raw_code.isdigit():
        prefix = "sh" if raw_code.startswith("6") else "sz"
        return f"{prefix}.{raw_code}"
    return raw_code


def get_board_name(code):
    """根据代码前缀判断板块: 沪主板/深主板/中小板/创业板/科创板"""
    pure = code.split(".")[-1] if "." in code else code
    if pure.startswith(("688", "689")):
        return "科创板"
    if pure.startswith("60"):
        return "沪主板"
    if pure.startswith(("000", "001")):
        return "深主板"
    if pure.startswith(("002", "003")):
        return "中小板"
    if pure.startswith("30"):
        return "创业板"
    return "其他"


# 板块快捷键映射
BOARD_SHORTCUTS = {
    "主板": ["沪主板", "深主板", "中小板"],
    "沪市": ["沪主板", "科创板"],
    "深市": ["深主板", "中小板", "创业板"],
}


def filter_codes_by_board(codes, board_args):
    """按板块参数过滤代码列表, 支持快捷键展开"""
    target_boards = set()
    for b in board_args:
        if b in BOARD_SHORTCUTS:
            target_boards.update(BOARD_SHORTCUTS[b])
        else:
            target_boards.add(b)
    return [c for c in codes if get_board_name(c) in target_boards]


def filter_codes_by_concept(codes, keywords):
    """用板块数据预筛选匹配概念/行业关键词的股票代码, 在评估前调用以减少计算量"""
    boards = load_boards()
    matched = []
    for code in codes:
        info = boards.get(code, {})
        text = (" ".join(info.get("concept", [])) + " " + " ".join(info.get("industry", []))).lower()
        if any(kw.lower() in text for kw in keywords):
            matched.append(code)
    return matched


def load_boards():
    """加载板块分类数据"""
    global _boards_cache
    if _boards_cache:
        return _boards_cache

    mapping = {}  # code -> {industry: [], concept: [], region: [], style: []}

    for board_type in ["industry", "concept", "region", "style"]:
        filepath = os.path.join(BOARDS_DIR, f"{board_type}.csv")
        if not os.path.exists(filepath):
            continue
        try:
            df = pd.read_csv(filepath, dtype=str)
            for _, row in df.iterrows():
                # 获取代码
                code = _normalize_code(row.get("code", ""))
                # 获取板块名称
                if board_type == "industry":
                    board_name = row.get("industry", row.get("board_name", ""))
                else:
                    board_name = row.get("board_name", "")

                if code and board_name:
                    if code not in mapping:
                        mapping[code] = {"industry": [], "concept": [], "region": [], "style": [], "_name": ""}
                    if board_name not in mapping[code][board_type]:
                        mapping[code][board_type].append(board_name)
                    # 记录股票名称
                    stock_name = row.get("code_name", row.get("name", ""))
                    if stock_name and not mapping[code]["_name"]:
                        mapping[code]["_name"] = stock_name
        except Exception:
            pass

    _boards_cache = mapping
    return mapping


def get_stock_boards(code):
    """获取股票的板块信息"""
    boards = load_boards()
    info = boards.get(code, {})
    return {
        "_name": info.get("_name", ""),
        "industry": ", ".join(info.get("industry", [])) or "-",
        "concept": ", ".join(info.get("concept", [])) or "-",
        "region": ", ".join(info.get("region", [])) or "-",
        "style": ", ".join(info.get("style", [])) or "-",
    }


def _print_stock_list(tag, title, stock_list, top_n):
    """打印荐1股列表（含名称和板块信息）"""
    print(f"\n{'='*120}")
    print(f"  [{tag}] {title} TOP {top_n} (八维度综合评分)")
    print(f"{'='*130}")
    print(f"  {'#':<3} {'代码':<12} {'名称':<10} {'收盘':>8} {'涨跌%':>7}"
          f" {'总分':>5} {'技术':>5} {'估值':>5} {'基本':>5} {'风险':>5}"
          f" {'动量':>5} {'资金':>5} {'消息':>5} {'热度':>5} {'建议'}")
    print(f"  {'-'*125}")
    for i, r in enumerate(stock_list, 1):
        name = r.get('name', '')[:8]
        print(f"  {i:<3} {r['code']:<12} {name:<10} {r['close']:>8.2f} {r['pctChg']:>6.2f}%"
              f" {r['total_score']:>+5} {r['tech_score']:>+5} {r['val_score']:>+5}"
              f" {r['fund_score']:>+5} {r['risk_score']:>5}"
              f" {r['mom_score']:>+5} {r['flow_score']:>+5} {r.get('news_score',0):>+5} {r.get('heat_score',0):>+5} {r['action']}")
        print(f"      [{r.get('board','?')}] 行业:{r.get('industry','-')}"
              f"  概念:{r.get('concept','-')}"
              f"  地区:{r.get('region','-')}")
        # 资金流向摘要
        flow_sigs = r.get('flow_signals', [])
        flow_summary = [s for s in flow_sigs if s.startswith("近")]
        if flow_summary:
            print(f"      资金: {' | '.join(flow_summary)}")
        if i < len(stock_list):
            print(f"  {'.'*115}")

# ============================================================
# 综合评估
# ============================================================

def load_daily_data(code):
    """加载日K线数据"""
    filepath = os.path.join(DAILY_DIR, code.replace(".", "_") + ".csv")
    if not os.path.exists(filepath):
        return None
    try:
        df = pd.read_csv(filepath)
        numeric_cols = ["open", "high", "low", "close", "preclose", "volume", "amount",
                        "turn", "pctChg", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return None


def get_all_downloaded_codes():
    """获取所有已下载的股票代码"""
    if not os.path.exists(DAILY_DIR):
        return []
    codes = []
    for f in os.listdir(DAILY_DIR):
        if f.endswith(".csv"):
            code = f.replace(".csv", "").replace("_", ".", 1)
            codes.append(code)
    return sorted(codes)


def evaluate_single(code, verbose=False, flow_data=None, news_data=None):
    """八维度综合评估单只股票"""
    df = load_daily_data(code)
    if df is None or len(df) < MIN_ROWS:
        return None

    df = calc_all_indicators(df)
    latest = df.iloc[-1]

    # 八维度评分
    tech_score, tech_signals = score_technical(df)
    val_score, val_signals = score_valuation(latest)
    fund_score, fund_signals = score_fundamental(code)
    risk_score, risk_signals = score_risk(latest)
    mom_score, mom_signals = score_momentum(df)
    flow_score, flow_signals = score_flow(df, flow_data=flow_data)

    # 板块信息（先加载，供消息面分析使用）
    boards = get_stock_boards(code)
    _name = boards.get("_name", "") or code
    _industry = boards.get("industry", "") or ""
    news_score, news_signals = score_news(
        news_data or [],
        stock_name=_name,
        stock_code=code,
        industry=_industry,
    )

    total = tech_score + val_score + fund_score + risk_score + mom_score + flow_score + news_score
    # heat_score 在 main() 批量评估后注入

    if total >= 65:
        action = "** 强烈买入"
    elif total >= 30:
        action = "*  建议买入"
    elif total <= -45:
        action = "** 强烈卖出"
    elif total <= -15:
        action = "*  建议卖出"
    else:
        action = "-  观望"

    result = {
        "code": code,
        "name": boards.get("_name", "") or code,
        "board": get_board_name(code),
        "date": latest["date"],
        "close": latest["close"],
        "pctChg": latest.get("pctChg", 0) or 0,
        "total_score": total,
        "tech_score": tech_score,
        "val_score": val_score,
        "fund_score": fund_score,
        "risk_score": risk_score,
        "mom_score": mom_score,
        "flow_score": flow_score,
        "news_score": news_score,
        "heat_score": 0,
        "action": action,
        "tech_signals": tech_signals,
        "val_signals": val_signals,
        "fund_signals": fund_signals,
        "risk_signals": risk_signals,
        "mom_signals": mom_signals,
        "flow_signals": flow_signals,
        "news_signals": news_signals,
        "heat_signals": [],
        "industry": boards["industry"],
        "concept": boards["concept"],
        "region": boards["region"],
        "style": boards["style"],
    }

    return result


def print_detail_report(result):
    """打印单只股票的详细评估报告"""
    boards = get_stock_boards(result["code"])

    print(f"\n{'='*80}")
    print(f"  [详细] 股票评估报告")
    print(f"{'='*80}")
    print(f"  代码: {result['code']}   名称: {result.get('name', '')}")
    print(f"  日期: {result['date']}")
    print(f"  收盘价: {result['close']:.2f}   涨跌幅: {result['pctChg']:.2f}%")
    print(f"  {'-'*76}")
    print(f"  [板块] 板块归属: {get_board_name(result['code'])}")
    print(f"    行业: {boards['industry']}")
    print(f"    概念: {boards['concept']}")
    print(f"    地区: {boards['region']}")
    print(f"    风格: {boards['style']}")
    print(f"  {'-'*76}")
    print(f"  [评分] 综合评分: {result['total_score']}   操作建议: {result['action']}")
    print(f"  {'-'*76}")
    print(f"  技术面: {result['tech_score']:>+4}/40  |  估值面: {result['val_score']:>+4}/25  |"
          f"  基本面: {result['fund_score']:>+4}/25  |  风险面: {result['risk_score']:>+3}/10")
    print(f"  动量面: {result['mom_score']:>+4}/15  |  资金面: {result['flow_score']:>+4}/15  |"
          f"  消息面: {result.get('news_score',0):>+4}/15  |  热度面: {result['heat_score']:>+4}/10  |")
    print(f"  {'-'*76}")

    for label, key in [("技术面", "tech_signals"), ("估值面", "val_signals"),
                       ("基本面", "fund_signals"), ("风险面", "risk_signals"),
                       ("动量面", "mom_signals"), ("资金面", "flow_signals"),
                       ("消息面", "news_signals"), ("热度面", "heat_signals")]:
        sigs = result[key]
        if sigs:
            print(f"  {label}:")
            for s in sigs:
                print(f"    - {s}")

    print(f"{'='*80}")

    # 资金流向明细
    flow_detail = result.get("_flow_detail")
    if flow_detail:
        print(f"\n  [资金流向] 近{len(flow_detail)}日主力资金明细")
        print(f"  {'-'*76}")
        print(f"  {'日期':<12} {'主力净流入':>12} {'超大单':>12} {'大单':>12} {'主力占比':>8}")
        print(f"  {'-'*76}")
        for r in flow_detail:
            main_wan = r['main_net'] / 10000
            super_wan = r['super_net'] / 10000
            big_wan = r['big_net'] / 10000
            tag = " ↑" if r['main_net'] > 0 else " ↓"
            print(f"  {r['date']:<12} {main_wan:>+11.0f}万 {super_wan:>+11.0f}万 {big_wan:>+11.0f}万 {r['main_pct']:>+7.2f}%{tag}")
        total_wan = sum(r['main_net'] for r in flow_detail) / 10000
        print(f"  {'-'*76}")
        print(f"  {'合计':<12} {total_wan:>+11.0f}万")


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="沪深A股专业级技术分析与买卖评估工具")
    parser.add_argument("--code", type=str, help="评估指定股票, 如 sh.600000")
    parser.add_argument("--top", type=int, default=30, help="显示前N只推荐 (默认: 30)")
    parser.add_argument("--board", nargs="+", type=str,
                        help="按板块筛选: 创业板 科创板 沪主板 深主板 中小板 (快捷键: 主板 沪市 深市)")
    parser.add_argument("--concept", nargs="+", type=str,
                        help="按概念/行业筛选, 如 --concept AI 电力 商业航天")
    parser.add_argument("--list-concepts", action="store_true",
                        help="列出所有可用的概念板块关键词")
    args = parser.parse_args()

    # 列出所有概念
    if args.list_concepts:
        _list_all_concepts()
        return

    if args.code:
        flow = fetch_capital_flow(args.code)
        _tmp = get_stock_boards(args.code)
        _name = _tmp.get("_name", "") or ""
        news = fetch_news(args.code, _name)
        result = evaluate_single(args.code, verbose=True, flow_data=flow, news_data=news)
        if result:
            result["_flow_detail"] = flow
            print_detail_report(result)
        else:
            print(f"[信息] 无法评估 {args.code}（数据不足或不存在）")
        return

    # 批量评估
    codes = get_all_downloaded_codes()
    if not codes:
        print("[错误] 未找到已下载的股票数据，请先运行 download_data.py")
        sys.exit(1)

    if args.board:
        total_before = len(codes)
        codes = filter_codes_by_board(codes, args.board)
        board_label = " ".join(args.board)
        print(f"[信息] 板块筛选: {board_label} → {len(codes)}/{total_before} 只")
        if not codes:
            print("[错误] 筛选后无匹配股票，请检查板块名称")
            sys.exit(1)

    # 概念预筛选: 先用板块数据过滤, 再评估, 大幅减少计算量
    if args.concept:
        total_before = len(codes)
        codes = filter_codes_by_concept(codes, args.concept)
        concept_label = " ".join(args.concept)
        print(f"[信息] 概念预筛选: {concept_label} → {len(codes)}/{total_before} 只")
        if not codes:
            print("[错误] 未找到匹配概念的股票")
            sys.exit(1)

    # 资金流向数据获取: 筛选后≤500只实时获取, >500只用量价代理
    flow_cache = {}  # code -> flow_data
    if len(codes) <= 500:
        print(f"[信息] 获取 {len(codes)} 只股票的主力资金流向...")
        for i, code in enumerate(codes, 1):
            flow_cache[code] = fetch_capital_flow(code)
            if i % 100 == 0:
                print(f"  已获取 {i}/{len(codes)} ...")
    else:
        print(f"[信息] 股票数 {len(codes)} 超过500, 资金面使用量价代理")

    print(f"[信息] 开始七维度综合评估...")

    results = []
    for i, code in enumerate(codes, 1):
        result = evaluate_single(code, flow_data=flow_cache.get(code))
        if result:
            results.append(result)
        if i % 500 == 0:
            print(f"  已评估 {i}/{len(codes)} ...")

    if not results:
        print("[信息] 无有效评估结果")
        return

    # ---- 板块热度后处理 ----
    _apply_sector_heat(results)

    # ---- Gemini 综合情报分析（取代逐股分析） ----
    active_concepts = args.concept or []
    if active_concepts:
        from market_intel import enrich_with_intel
        enrich_with_intel(results, active_concepts, top_n=args.top)

    # 概念筛选模式: 对已预筛选的结果做 alpha 排名
    if args.concept:
        _run_concept_filter(results, args.concept, args.top)
        return

    # 常规模式: 买入推荐 + 卖出警示
    results.sort(key=lambda x: x["total_score"], reverse=True)

    buy_list = [r for r in results if r["total_score"] >= 25][:args.top]
    _print_stock_list("买入", "买入推荐", buy_list, args.top)

    sell_list = [r for r in results if r["total_score"] <= -15]
    sell_list.sort(key=lambda x: x["total_score"])
    sell_list = sell_list[:args.top]
    _print_stock_list("卖出", "卖出警示", sell_list, args.top)

    total_buy = len([r for r in results if r["total_score"] >= 25])
    total_sell = len([r for r in results if r["total_score"] <= -15])
    print(f"\n[统计] 评估 {len(results)} 只 | 买入推荐 {total_buy} | 卖出警示 {total_sell}")
    print(f"[日期] 数据截至: {results[0]['date']}")


def _apply_sector_heat(results):
    """板块热度后处理: 用评估结果的 pctChg 按概念分组算均涨跌幅, 注入热度评分"""
    boards_data = load_boards()

    # 第一步: 按概念聚合所有股票的 pctChg
    concept_pcts = {}  # {concept_name: [pctChg, ...]}
    for r in results:
        code = r["code"]
        pct = r["pctChg"]
        if pd.isna(pct):
            continue
        info = boards_data.get(code, {})
        for c in info.get("concept", []):
            concept_pcts.setdefault(c, []).append(pct)

    # 第二步: 计算每个概念的平均涨跌幅
    concept_heat = {c: np.mean(v) for c, v in concept_pcts.items() if len(v) >= 3}

    # 第三步: 为每只股票计算热度分
    for r in results:
        code = r["code"]
        info = boards_data.get(code, {})
        concepts = info.get("concept", [])
        if not concepts:
            continue

        # 取所属概念中最热的板块
        heats = [concept_heat.get(c, 0) for c in concepts]
        max_heat = max(heats) if heats else 0
        hot_count = sum(1 for h in heats if h > 1.0)

        heat_score = 0
        heat_signals = []

        if max_heat > 3:
            heat_score += 6;  heat_signals.append(f"热门板块{max_heat:+.1f}%(+6)")
        elif max_heat > 1:
            heat_score += 3;  heat_signals.append(f"板块活跃{max_heat:+.1f}%(+3)")
        elif max_heat > 0.5:
            heat_score += 1;  heat_signals.append(f"板块偏暖{max_heat:+.1f}%(+1)")
        elif max_heat < -3:
            heat_score -= 6;  heat_signals.append(f"板块暗淡{max_heat:+.1f}%(-6)")
        elif max_heat < -1:
            heat_score -= 3;  heat_signals.append(f"板块偏冷{max_heat:+.1f}%(-3)")

        # 多热门概念叠加
        if hot_count >= 3:
            heat_score += 4;  heat_signals.append(f"{hot_count}个热门概念叠加(+4)")
        elif hot_count >= 2:
            heat_score += 2;  heat_signals.append(f"{hot_count}个热门概念叠加(+2)")

        heat_score = max(-10, min(10, heat_score))
        r["heat_score"] = heat_score
        r["heat_signals"] = heat_signals
        r["total_score"] += heat_score

        # 重新计算建议
        total = r["total_score"]
        if total >= 60:
            r["action"] = "** 强烈买入"
        elif total >= 30:
            r["action"] = "*  建议买入"
        elif total <= -40:
            r["action"] = "** 强烈卖出"
        elif total <= -15:
            r["action"] = "*  建议卖出"
        else:
            r["action"] = "-  观望"


def _match_concept(result, keywords):
    """检查股票是否匹配任一关键词（模糊匹配概念+行业）"""
    text = (result.get("concept", "") + " " + result.get("industry", "")).lower()
    matched = [kw for kw in keywords if kw.lower() in text]
    return matched


def _run_concept_filter(results, keywords, top_n):
    """按概念关键词筛选 — 龙头优选、成长偏好、多概念叠加"""

    # 大盘价值行业关键词（降权）
    VALUE_SECTORS = ["银行", "保险", "货币金融", "证券", "信托", "电力、热力"]

    # ---- 第一步: 匹配并计算alpha ----
    boards_data = load_boards()
    keyword_stocks = {kw: [] for kw in keywords}
    all_matched = {}

    for r in results:
        matched = _match_concept(r, keywords)
        if not matched:
            continue

        code = r["code"]
        pure_code = code.split(".")[-1] if "." in code else code

        # --- alpha_score 计算 ---
        alpha = r["total_score"]

        # (1) 多概念叠加: 每多匹配一个关键词 +8
        overlap_bonus = (len(matched) - 1) * 8
        alpha += overlap_bonus

        # (2) 成长板偏好
        board_bonus = 0
        if pure_code.startswith("300"):       # 创业板
            board_bonus = +5
        elif pure_code.startswith("688"):     # 科创板
            board_bonus = +5
        # 大盘价值行业降权
        industry_text = r.get("industry", "")
        if any(vs in industry_text for vs in VALUE_SECTORS):
            board_bonus = -10
        alpha += board_bonus

        # (3) 概念密度 — 总概念数多 = 热门龙头
        info = boards_data.get(code, {})
        total_concepts = len(info.get("concept", []))
        density_bonus = min(total_concepts // 5, 3) * 2  # 每5个+2, 上限+6
        alpha += density_bonus

        # (4) 产品端优先 — 行业名直接匹配搜索关键词
        product_bonus = 0
        for kw in matched:
            if kw.lower() in industry_text.lower():
                product_bonus = 3
                break
        alpha += product_bonus

        # 记录
        r["_matched"] = ", ".join(matched)
        r["_overlap"] = len(matched)
        r["_alpha"] = alpha
        r["_bonus_detail"] = (f"叠加{overlap_bonus:+d} "
                              f"板{board_bonus:+d} "
                              f"密{density_bonus:+d} "
                              f"产{product_bonus:+d}")
        all_matched[code] = r
        for kw in matched:
            keyword_stocks[kw].append(r)

    matched_list = sorted(all_matched.values(), key=lambda x: x["_alpha"], reverse=True)

    # ---- 第二步: 输出 ----
    print(f"\n{'='*105}")
    print(f"  [龙头优选] 概念筛选: {', '.join(keywords)}")
    print(f"{'='*105}")
    print(f"  评分策略: 四维基础分 + 多概念叠加(+8/个) + 成长板(+5) + 概念密度 + 产品端(+3) - 大盘价值(-10)")

    if not matched_list:
        print(f"\n  未找到匹配的股票")
        return

    # 统计摘要
    print(f"\n  概念匹配统计:")
    for kw in keywords:
        stocks = keyword_stocks.get(kw, [])
        if stocks:
            avg = sum(s["_alpha"] for s in stocks) / len(stocks)
            best = max(stocks, key=lambda x: x["_alpha"])
            print(f"    [{kw}] {len(stocks)} 只, alpha均值 {avg:.1f},"
                  f" 最优 {best.get('name','')}({best['_alpha']:+d})")
        else:
            print(f"    [{kw}] 未匹配到股票")

    # 排名表
    print(f"\n  {'='*100}")
    print(f"  龙头排名 (共 {len(matched_list)} 只, 按alpha评分)")
    print(f"  {'='*100}")
    print(f"  {'#':<3} {'代码':<12} {'名称':<10} {'收盘':>8} {'涨跌%':>7}"
          f" {'alpha':>6} {'基础':>5} {'加成':>5} {'建议'}")
    print(f"  {'-'*100}")

    show_list = matched_list[:top_n]
    for i, r in enumerate(show_list, 1):
        name = r.get("name", "")[:8]
        base = r["total_score"]
        bonus = r["_alpha"] - base
        print(f"  {i:<3} {r['code']:<12} {name:<10} {r['close']:>8.2f} {r['pctChg']:>6.2f}%"
              f" {r['_alpha']:>+6} {base:>+5} {bonus:>+5} {r['action']}")
        overlap_tag = f"[x{r['_overlap']}]" if r["_overlap"] > 1 else ""
        print(f"      匹配:{r.get('_matched','')}{overlap_tag}"
              f"  ({r['_bonus_detail']})")
        print(f"      行业:{r.get('industry','-')}"
              f"  概念:{r.get('concept','-')}")
        if i < len(show_list):
            print(f"  {'.'*100}")

    if len(matched_list) > top_n:
        print(f"\n  ... 共 {len(matched_list)} 只, 仅显示前 {top_n} 只 (--top N 调整)")

    print(f"\n[统计] 匹配 {len(matched_list)} 只 | alpha>=20: "
          f"{sum(1 for r in matched_list if r['_alpha'] >= 20)} 只")
    print(f"[日期] 数据截至: {matched_list[0]['date']}")


def _list_all_concepts():
    """列出所有可用的概念板块"""
    boards = load_boards()
    concept_count = {}
    for code, info in boards.items():
        for c in info.get("concept", []):
            concept_count[c] = concept_count.get(c, 0) + 1

    sorted_concepts = sorted(concept_count.items(), key=lambda x: x[1], reverse=True)
    print(f"\n[信息] 共 {len(sorted_concepts)} 个概念板块 (按成分股数量排序)\n")
    for i, (name, count) in enumerate(sorted_concepts, 1):
        print(f"  {i:>4}. {name:<20} ({count} 只)")


if __name__ == "__main__":
    main()

