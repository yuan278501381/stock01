"""
沪深A股全量数据下载工具（专业版）

数据源:
  - BaoStock: 日K线（全字段）、财务数据、行业分类
  - AKShare: 概念板块、地区板块、风格板块

用法:
  python download_data.py --all            # 下载全部数据
  python download_data.py --daily          # 仅下载日K线
  python download_data.py --finance        # 仅下载财务数据
  python download_data.py --boards         # 仅下载板块数据
  python download_data.py --test           # 测试模式（仅5只股票）
  python download_data.py --code sh.600000 # 下载指定股票
"""

import argparse
import os
import sys

# Windows 终端 UTF-8 兼容
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import time
from datetime import datetime, timedelta

import baostock as bs
import pandas as pd


# ============================================================
# 配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DAILY_DIR = os.path.join(DATA_DIR, "daily")
FINANCE_DIR = os.path.join(DATA_DIR, "finance")
BOARDS_DIR = os.path.join(DATA_DIR, "boards")

# 日K线全部字段
DAILY_FIELDS = (
    "date,open,high,low,close,preclose,volume,amount,adjustflag,"
    "turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
)

START_DATE = "2020-01-01"


def ensure_dirs():
    """确保所有目录存在"""
    for d in [DAILY_DIR, FINANCE_DIR, BOARDS_DIR]:
        os.makedirs(d, exist_ok=True)


# ============================================================
# 股票列表
# ============================================================

def get_stock_list():
    """获取沪深所有A股股票列表"""
    rs = bs.query_stock_basic()
    if rs.error_code != "0":
        print(f"[错误] 获取股票列表失败: {rs.error_msg}")
        return []

    stocks = []
    while rs.next():
        row = rs.get_row_data()
        code, name, ipo_date, out_date, stype, status = row[0], row[1], row[2], row[3], row[4], row[5]
        if stype == "1" and status == "1":
            stocks.append({"code": code, "name": name})
    return stocks


# ============================================================
# 日K线下载
# ============================================================

def get_local_latest_date(code):
    """获取本地日K线最新日期"""
    filepath = os.path.join(DAILY_DIR, code.replace(".", "_") + ".csv")
    if not os.path.exists(filepath):
        return None
    try:
        df = pd.read_csv(filepath, nrows=0)
        # 检查字段是否匹配（升级后字段数不同则需要重新下载）
        expected = set(DAILY_FIELDS.split(","))
        if not expected.issubset(set(df.columns)):
            return None  # 字段不兼容，需重新下载
        df = pd.read_csv(filepath, usecols=["date"])
        return df["date"].max() if not df.empty else None
    except Exception:
        return None


def download_daily(code, start_date=None):
    """下载单只股票日K线数据"""
    if start_date is None:
        start_date = START_DATE
    end_date = datetime.now().strftime("%Y-%m-%d")

    rs = bs.query_history_k_data_plus(
        code, DAILY_FIELDS,
        start_date=start_date, end_date=end_date,
        frequency="d", adjustflag="2",
    )
    if rs.error_code != "0":
        return None

    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None

    df = pd.DataFrame(rows, columns=DAILY_FIELDS.split(","))
    numeric_cols = ["open", "high", "low", "close", "preclose", "volume", "amount",
                    "turn", "pctChg", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def save_daily(code, df):
    """保存日K线数据（支持增量追加）"""
    filepath = os.path.join(DAILY_DIR, code.replace(".", "_") + ".csv")
    if os.path.exists(filepath):
        try:
            existing = pd.read_csv(filepath)
            if set(DAILY_FIELDS.split(",")).issubset(set(existing.columns)):
                combined = pd.concat([existing, df], ignore_index=True)
                combined.drop_duplicates(subset=["date"], keep="last", inplace=True)
                combined.sort_values("date", inplace=True)
                combined.to_csv(filepath, index=False)
                return
        except Exception:
            pass
    df.to_csv(filepath, index=False)


def download_all_daily(stock_list, test_mode=False):
    """批量下载日K线"""
    if test_mode:
        stock_list = stock_list[:5]

    total = len(stock_list)
    success = skip = fail = 0
    print(f"\n{'='*60}")
    print(f"  [K线] 开始下载 {total} 只股票的日K线数据 (17字段)")
    print(f"{'='*60}")

    for i, stock in enumerate(stock_list, 1):
        code, name = stock["code"], stock["name"]
        latest = get_local_latest_date(code)
        if latest:
            next_day = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            if next_day >= datetime.now().strftime("%Y-%m-%d"):
                skip += 1
                if test_mode:
                    print(f"  [{i}/{total}] {code} {name} — 已是最新，跳过")
                continue
            start = next_day
        else:
            start = START_DATE

        df = download_daily(code, start)
        if df is not None and not df.empty:
            save_daily(code, df)
            success += 1
            print(f"  [{i}/{total}] {code} {name} — {len(df)} 条 ✓")
        else:
            fail += 1
            if test_mode:
                print(f"  [{i}/{total}] {code} {name} — 无数据 ✗")

        if not test_mode and i % 200 == 0:
            print(f"  ... 已处理 {i}/{total} (成功{success} 跳过{skip} 失败{fail})")

    print(f"\n  日K线下载完毕: 成功 {success} | 跳过 {skip} | 失败 {fail} | 共 {total}")
    print(f"{'='*60}")


# ============================================================
# 财务数据下载
# ============================================================

def get_recent_quarters(n=8):
    """获取最近N个季度的 (year, quarter) 列表"""
    now = datetime.now()
    quarters = []
    y, q = now.year, (now.month - 1) // 3
    if q == 0:
        y -= 1
        q = 4
    for _ in range(n):
        quarters.append((y, q))
        q -= 1
        if q == 0:
            q = 4
            y -= 1
    return quarters


def download_finance_for_stock(code, quarters):
    """下载单只股票的财务数据（盈利+成长）"""
    all_rows = []

    for year, quarter in quarters:
        # 盈利能力
        rs = bs.query_profit_data(code=code, year=year, quarter=quarter)
        if rs.error_code == "0":
            while rs.next():
                row = rs.get_row_data()
                fields = rs.fields
                record = dict(zip(fields, row))
                record["data_type"] = "profit"
                all_rows.append(record)

        # 成长能力
        rs = bs.query_growth_data(code=code, year=year, quarter=quarter)
        if rs.error_code == "0":
            while rs.next():
                row = rs.get_row_data()
                fields = rs.fields
                record = dict(zip(fields, row))
                record["data_type"] = "growth"
                all_rows.append(record)

    return all_rows


def save_finance(code, rows):
    """保存财务数据"""
    if not rows:
        return
    df = pd.DataFrame(rows)
    filepath = os.path.join(FINANCE_DIR, code.replace(".", "_") + ".csv")
    df.to_csv(filepath, index=False)


def download_all_finance(stock_list, test_mode=False):
    """批量下载财务数据"""
    if test_mode:
        stock_list = stock_list[:5]

    quarters = get_recent_quarters(8)
    total = len(stock_list)
    success = fail = 0

    print(f"\n{'='*60}")
    print(f"  [财务] 开始下载 {total} 只股票的财务数据")
    print(f"  季度范围: {quarters[-1][0]}Q{quarters[-1][1]} ~ {quarters[0][0]}Q{quarters[0][1]}")
    print(f"{'='*60}")

    for i, stock in enumerate(stock_list, 1):
        code, name = stock["code"], stock["name"]
        rows = download_finance_for_stock(code, quarters)
        if rows:
            save_finance(code, rows)
            success += 1
            if test_mode:
                print(f"  [{i}/{total}] {code} {name} — {len(rows)} 条财务记录 ✓")
        else:
            fail += 1

        if not test_mode and i % 200 == 0:
            print(f"  ... 已处理 {i}/{total} (成功{success} 失败{fail})")

    print(f"\n  财务数据下载完毕: 成功 {success} | 失败 {fail} | 共 {total}")
    print(f"{'='*60}")


# ============================================================
# 板块数据下载
# ============================================================

def download_industry_boards():
    """下载行业板块分类（BaoStock）"""
    print("\n  [1/2] 下载行业板块（BaoStock 证监会行业分类）...")
    rs = bs.query_stock_industry()
    if rs.error_code != "0":
        print(f"  [错误] {rs.error_msg}")
        return

    rows = []
    while rs.next():
        rows.append(rs.get_row_data())

    if rows:
        df = pd.DataFrame(rows, columns=rs.fields)
        filepath = os.path.join(BOARDS_DIR, "industry.csv")
        df.to_csv(filepath, index=False)
        print(f"  行业板块: {len(df)} 条记录")
    else:
        print("  行业板块: 无数据")


def download_eastmoney_boards():
    """从东方财富 datacenter API 下载全部板块归属（概念/地区/风格）

    API: datacenter.eastmoney.com/securities/api/data/v1/get
    报表: RPT_F10_CORETHEME_BOARDTYPE
    含: 概念板块、地区板块、行业板块（东方财富分类）等全量映射
    """
    print("\n  [2/2] 下载概念/地区/风格板块（东方财富 datacenter API）...")

    import requests as req

    s = req.Session()
    s.trust_env = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://emweb.securities.eastmoney.com/"
    })

    all_records = []
    page = 1
    page_size = 5000
    total_count = None

    while True:
        url = (
            "https://datacenter.eastmoney.com/securities/api/data/v1/get?"
            "reportName=RPT_F10_CORETHEME_BOARDTYPE"
            "&columns=SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,NEW_BOARD_CODE,BOARD_NAME,IS_PRECISE,BOARD_RANK"
            f"&pageNumber={page}&pageSize={page_size}"
            "&sortTypes=1&sortColumns=BOARD_RANK"
            "&source=HSF10&client=PC"
        )

        try:
            r = s.get(url, timeout=30)
            data = r.json()
        except Exception as e:
            print(f"  请求失败 (page={page}): {e}")
            break

        if not data.get("success") or not data.get("result"):
            print(f"  API返回失败 (page={page}): {data.get('message', 'unknown')}")
            break

        result = data["result"]
        items = result.get("data", [])
        if total_count is None:
            total_count = result.get("count", 0)
            print(f"  API返回总记录: {total_count}")

        for item in items:
            secucode = item.get("SECUCODE", "")  # 如 "000636.SZ"
            board_name = item.get("BOARD_NAME", "")
            board_code = item.get("NEW_BOARD_CODE", "")
            stock_name = item.get("SECURITY_NAME_ABBR", "")
            stock_code = item.get("SECURITY_CODE", "")

            if not secucode or not board_name:
                continue

            # 判断板块类型
            if board_code.startswith("BK0") and len(board_code) == 6:
                # BK0xxx 大多是行业/地区/概念
                if "板块" in board_name and any(p in board_name for p in
                    ["北京", "上海", "广东", "浙江", "江苏", "山东", "四川",
                     "福建", "湖南", "湖北", "河南", "河北", "安徽", "辽宁",
                     "重庆", "天津", "陕西", "云南", "贵州", "广西", "吉林",
                     "黑龙江", "内蒙古", "新疆", "甘肃", "海南", "宁夏",
                     "青海", "西藏", "山西", "江西"]):
                    board_type = "region"
                else:
                    board_type = "concept"
            elif board_code.startswith("BK1"):
                board_type = "concept"
            else:
                board_type = "concept"

            all_records.append({
                "board_type": board_type,
                "board_name": board_name,
                "board_code": board_code,
                "code": stock_code,
                "name": stock_name,
            })

        all_records_count = len(all_records)
        print(f"  ... 已获取 {all_records_count}/{total_count} 条 (page={page})")

        if len(items) < page_size:
            break
        page += 1
        time.sleep(0.3)

    if all_records:
        df = pd.DataFrame(all_records)

        # 分开保存概念和地区板块
        concept_df = df[df["board_type"] == "concept"]
        region_df = df[df["board_type"] == "region"]

        concept_df.to_csv(os.path.join(BOARDS_DIR, "concept.csv"), index=False)
        region_df.to_csv(os.path.join(BOARDS_DIR, "region.csv"), index=False)

        # 从日K数据推导风格板块 (大盘/中盘/小盘, 价值/成长)
        _derive_style_boards(df)

        n_concept = len(concept_df)
        n_region = len(region_df)
        n_stocks = df["code"].nunique()
        print(f"  概念板块: {n_concept} 条 | 地区板块: {n_region} 条 | 覆盖 {n_stocks} 只股票")
    else:
        print("  东方财富板块: 无数据")


def _derive_style_boards(boards_df):
    """风格板块暂存为空文件（后续可从评估结果中补充）"""
    filepath = os.path.join(BOARDS_DIR, "style.csv")
    pd.DataFrame(columns=["board_type", "board_name", "board_code", "code", "name"]).to_csv(filepath, index=False)


def download_all_boards():
    """下载全部板块数据"""
    print(f"\n{'='*60}")
    print(f"  [板块] 开始下载板块分类数据")
    print(f"{'='*60}")

    download_industry_boards()
    download_eastmoney_boards()

    print(f"\n  板块数据下载完毕")
    print(f"{'='*60}")


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="沪深A股全量数据下载工具（专业版）")
    parser.add_argument("--all", action="store_true", help="下载全部数据")
    parser.add_argument("--daily", action="store_true", help="下载日K线数据")
    parser.add_argument("--finance", action="store_true", help="下载财务数据")
    parser.add_argument("--boards", action="store_true", help="下载板块分类数据")
    parser.add_argument("--test", action="store_true", help="测试模式（仅5只股票）")
    parser.add_argument("--code", type=str, help="下载指定股票, 如 sh.600000")
    parser.add_argument("--start", type=str, default=START_DATE, help=f"起始日期 (默认: {START_DATE})")
    args = parser.parse_args()

    # 若未指定任何下载类型，默认 --all
    if not any([args.all, args.daily, args.finance, args.boards, args.code]):
        args.all = True

    ensure_dirs()

    # 登录 BaoStock
    lg = bs.login()
    if lg.error_code != "0":
        print(f"[错误] BaoStock 登录失败: {lg.error_msg}")
        sys.exit(1)
    print("[信息] BaoStock 登录成功")

    try:
        if args.code:
            # 下载指定股票
            print(f"[信息] 下载指定股票: {args.code}")
            df = download_daily(args.code, args.start)
            if df is not None and not df.empty:
                save_daily(args.code, df)
                print(f"[信息] 日K线: {len(df)} 条记录")
                print(df.tail())
            else:
                print("[警告] 日K线无数据")

            quarters = get_recent_quarters(8)
            rows = download_finance_for_stock(args.code, quarters)
            if rows:
                save_finance(args.code, rows)
                print(f"[信息] 财务数据: {len(rows)} 条记录")
            else:
                print("[警告] 财务数据无数据")
            return

        # 获取股票列表
        print("[信息] 正在获取沪深A股列表...")
        stock_list = get_stock_list()
        if not stock_list:
            print("[错误] 未获取到股票列表")
            sys.exit(1)
        print(f"[信息] 获取到 {len(stock_list)} 只A股股票")

        # 按类型下载
        if args.all or args.daily:
            download_all_daily(stock_list, test_mode=args.test)

        if args.all or args.finance:
            download_all_finance(stock_list, test_mode=args.test)

        if args.all or args.boards:
            download_all_boards()

    finally:
        bs.logout()
        print("\n[信息] BaoStock 已登出")


if __name__ == "__main__":
    main()
