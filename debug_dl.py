import sys; sys.stdout.reconfigure(encoding="utf-8")
import requests

# 测试被删的2只: sh.688981 和 sz.300999
for code in ["sh.688981", "sz.300999"]:
    pure = code.split(".")[-1]
    prefix = "sh" if code.startswith("sh") else "sz"
    symbol = f"{prefix}{pure}"
    s = requests.Session()
    s.trust_env = False
    r = s.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
              params={"param": f"{symbol},day,2020-01-01,2026-03-01,8000,qfq"},
              timeout=15)
    d = r.json()
    data = d.get("data", {}).get(symbol, {})
    if isinstance(data, dict):
        klines = data.get("qfqday") or data.get("day", [])
        print(f"{code}: {len(klines)}条 末:{klines[-1] if klines else 'empty'}")
    else:
        print(f"{code}: 返回异常: {type(data)} {str(data)[:100]}")
