"""测试东方财富资金流向 API — 寻找批量接口"""
import sys, time, requests
sys.stdout.reconfigure(encoding="utf-8")

session = requests.Session()
session.trust_env = False
session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"

# ---- 方案1: push2 批量排名接口 (一次获取所有股票) ----
print("=== 方案1: push2.eastmoney.com 批量接口 ===")
try:
    r = session.get(
        "https://push2.eastmoney.com/api/qt/clist/get",
        params={
            "pn": 1, "pz": 10,
            "fields": "f2,f3,f12,f14,f62,f184,f66,f69,f72,f75",
            "fid": "f62",
            "fs": "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:81+f:!2",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        },
        timeout=10,
    )
    print(f"  状态: {r.status_code}")
    print(f"  响应: {r.text[:300]}")
except Exception as e:
    print(f"  失败: {e}")

# ---- 方案2: push2his 单股接口 (已验证可用, 测试字段解析) ----
print("\n=== 方案2: push2his.eastmoney.com 单股接口 ===")
try:
    r = session.get(
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
        params={
            "secid": "0.300830",  # 0=深市, 1=沪市
            "fields1": "f1,f2,f3",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "klt": "101",  # 日线
            "lmt": "5",    # 最近5天
        },
        timeout=10,
    )
    data = r.json()
    print(f"  状态: {r.status_code}")
    print(f"  股票: {data['data']['name']}")
    print(f"  字段说明: 日期,主力净流入,超大单净流入,大单净流入,中单净流入,小单净流入,")
    print(f"           主力净流入占比%,超大单占比%,大单占比%,中单占比%,小单占比%,收盘价,涨跌%,x,x")
    print(f"  近5日数据:")
    for kline in data["data"]["klines"]:
        parts = kline.split(",")
        date = parts[0]
        main_net = float(parts[1]) / 10000  # 转为万元
        pct = float(parts[6])  # 主力净流入占比
        price = float(parts[11])
        chg = float(parts[12])
        print(f"    {date}  主力:{main_net:>+10.0f}万  占比:{pct:>+6.2f}%  收盘:{price}  涨跌:{chg:+.2f}%")
except Exception as e:
    print(f"  失败: {e}")

# ---- 方案3: datacenter-web 批量资金流排名 ----
print("\n=== 方案3: datacenter-web.eastmoney.com 资金流排名 ===")
try:
    r = session.get(
        "https://datacenter-web.eastmoney.com/api/data/v1/get",
        params={
            "reportName": "RPT_CAPITALFLOW_RANK",
            "columns": "ALL",
            "sortColumns": "MAIN_NET_INFLOW",
            "sortTypes": "-1",
            "pageNumber": 1,
            "pageSize": 5,
            "source": "WEB",
            "client": "WEB",
        },
        timeout=10,
    )
    print(f"  状态: {r.status_code}")
    print(f"  响应: {r.text[:500]}")
except Exception as e:
    print(f"  失败: {e}")

# ---- 方案4: data.eastmoney.com 资金流向 ----
print("\n=== 方案4: data.eastmoney.com/zjlx/ ===")
try:
    r = session.get(
        "https://data.eastmoney.com/zjlx/detail.html",
        timeout=10,
    )
    print(f"  状态: {r.status_code}")
    print(f"  页面大小: {len(r.text)} 字节")
except Exception as e:
    print(f"  失败: {e}")
