# 板块功能 — 数据获取、排查与使用指南

> 记录时间: 2026-02-27

---

## 一、需求背景

评估系统需要获取每只股票的**四类板块归属**信息：

| 板块类型 | 说明 | 示例 |
|----------|------|------|
| 行业板块 | 证监会行业分类 | C39计算机、通信和其他电子设备制造业 |
| 概念板块 | 市场热点题材 | 机器人概念、华为概念、5G概念 |
| 地区板块 | 注册地/上市地 | 广东板块、上海板块 |
| 风格板块 | 市值/估值风格 | 大盘股、价值股 |

---

## 二、初始方案与失败

### 方案设计

- **行业板块**: BaoStock `query_stock_industry()` — 证监会行业分类
- **概念板块**: AKShare `stock_board_concept_name_em()` + `stock_board_concept_cons_em()` — 东方财富概念板块
- **地区板块**: AKShare `stock_zh_a_spot_em()` — 从代码推断交易所
- **风格板块**: AKShare `stock_zh_a_spot_em()` — 从市值/PE推导

### 遇到的问题

行业板块（BaoStock）下载正常，但**概念/地区/风格板块全部失败**，报错：

```
HTTPSConnectionPool(host='82.push2.eastmoney.com', ...)
RemoteDisconnected('Remote end closed connection without response')
```

AKShare 底层调用的是东方财富的 `push2.eastmoney.com` API，该端点在当前网络环境下无法连接。

---

## 三、排查过程

### 第1步：判断是代理还是反爬虫

最初怀疑是东方财富的反爬虫机制。通过错误信息中的 `ProxyError` 关键字，推测可能是**代理问题**。

### 第2步：尝试绕过代理

尝试了多种绕过代理的方法，均无效：

| 方法 | 代码 | 结果 |
|------|------|------|
| PowerShell 环境变量 | `$env:NO_PROXY='*'; $env:HTTP_PROXY=''` | 失败 |
| Python 环境变量 | `os.environ['NO_PROXY'] = '*'` | 失败 |
| requests trust_env | `session.trust_env = False` | 失败 |

### 第3步：检查系统代理配置

```python
import urllib.request
print(urllib.request.getproxies())
# 输出: {'no': '*'}
```

系统已设置 `NO_PROXY=*`，但 requests 库仍然走了代理路径。即使用 `trust_env=False` 完全禁用系统代理后，连接仍然失败。

### 第4步：确认是网络层面问题

```python
session.trust_env = False
session.get('https://82.push2.eastmoney.com/...')  # 失败
```

**结论**：不是代理问题，而是**网络层面**（防火墙/路由器/ISP）直接封锁了 `push2.eastmoney.com` 的连接。

### 第5步：探测可用端点

对东方财富的多个子域名逐一测试：

| 端点 | 状态 | 用途 |
|------|------|------|
| `push2.eastmoney.com` | ❌ ConnectionError | AKShare 使用的 API |
| `82.push2.eastmoney.com` | ❌ ConnectionError | 同上 |
| `push2ex.eastmoney.com` | ❌ 404 | 另一个 push 端点 |
| `datacenter-web.eastmoney.com` | ✅ 200 | 数据中心（Web版） |
| `data.eastmoney.com` | ✅ 200 | 东方财富数据主站 |
| `quote.eastmoney.com` | ✅ 200 | 行情中心 |
| `datacenter.eastmoney.com` | ✅ 200 | **数据中心（证券版）** |

**发现**：只有 `push2` 系列被封，其他端点均可正常访问。

### 第6步：寻找替代 API

在可用端点上尝试了多种 API 路径：

| 尝试 | 结果 |
|------|------|
| `datacenter-web` 的 RPT_BOARD_CONCEPT 报表 | 报表不存在 |
| `datacenter-web` 的 RPT_F10_CORETHEME_BOARDTYPE | 参数错误 |
| `data.eastmoney.com/bkzj/gn.html` 页面解析 | 获取到625个概念板块名称，但无成分股 |
| `emweb.securities.eastmoney.com` F10 核心题材 | 返回JS渲染的空壳HTML |
| 同花顺 `q.10jqka.com.cn` | 超时 |
| 新浪财经 | 返回空内容 |

### 第7步：浏览器抓包（关键突破）

使用浏览器工具加载东方财富 F10 核心题材页面，通过**网络请求监控**捕获到页面实际发出的 API 请求。

**关键发现**：页面使用的是 `datacenter.eastmoney.com`（注意：没有 `-web` 后缀），路径为 `/securities/api/data/v1/get`，与之前测试的 `datacenter-web.eastmoney.com` 是**不同的子域名**。

捕获到的完整 API URL：

```
https://datacenter.eastmoney.com/securities/api/data/v1/get
  ?reportName=RPT_F10_CORETHEME_BOARDTYPE
  &columns=SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,NEW_BOARD_CODE,BOARD_NAME,IS_PRECISE,BOARD_RANK
  &filter=(SECUCODE="000636.SZ")
  &pageNumber=1&pageSize=50
  &sortTypes=1&sortColumns=BOARD_RANK
  &source=HSF10&client=PC
```

### 第8步：验证 API 可用性

```python
# 单股查询 — 000636.SZ 的全部板块归属
r = session.get(url, params={...filter: '(SECUCODE="000636.SZ")'...})
# 成功! 返回 21 条板块记录（含行业/概念/地区）

# 全量无过滤查询
r = session.get(url, params={...无filter...})
# 成功! 总记录 81198 条（所有股票的板块映射）
```

**API 完全打通**。且支持分页全量获取，无需逐只股票查询。

---

## 四、最终解决方案

### 数据源对比

| 项目 | 旧方案 (AKShare) | 新方案 (datacenter API) |
|------|-------------------|--------------------------|
| 端点 | push2.eastmoney.com | datacenter.eastmoney.com |
| 方式 | 逐个概念板块获取成分股 | 全量分页获取所有映射 |
| 请求数 | 数百次 | 约17次 (81198/5000) |
| 耗时 | 很长 + 可能被封 | 约10秒 |
| 网络兼容性 | 依赖 push2 可达 | 使用主站可达端点 |

### API 参数说明

```
报表名: RPT_F10_CORETHEME_BOARDTYPE
字段:
  - SECUCODE: 证券代码 (如 "000636.SZ")
  - SECURITY_CODE: 纯数字代码 (如 "000636")
  - SECURITY_NAME_ABBR: 股票简称
  - NEW_BOARD_CODE: 板块代码 (如 "BK0574")
  - BOARD_NAME: 板块名称 (如 "锂电池")
  - BOARD_RANK: 排序权重

必要请求头:
  - User-Agent: 标准浏览器UA
  - Referer: https://emweb.securities.eastmoney.com/
  - trust_env=False (绕过系统代理)
```

### 板块类型判别逻辑

API 返回的数据不区分概念/地区，需要自行判别：

```python
# 含省份名 + "板块" 后缀 → 地区板块
if "板块" in board_name and any(province in board_name for province in PROVINCES):
    board_type = "region"
else:
    board_type = "concept"
```

### 代码实现

核心代码在 [download_data.py](file:///f:/PycharmProjects/Stock/download_data.py) 的 `download_eastmoney_boards()` 函数，板块加载在 [evaluate_stocks.py](file:///f:/PycharmProjects/Stock/evaluate_stocks.py) 的 `load_boards()` 函数。

---

## 五、验证结果

**sz.000636 (风华高科)**：

```
行业: C39计算机、通信和其他电子设备制造业    ← BaoStock
概念: 电子, 元件, 被动元件, 最近多板, 东方财富热股  ← datacenter API
地区: 广东板块                                ← datacenter API
风格: -                                       ← 暂空
```

**板块数据量统计**：

| 类型 | 记录数 | 覆盖股票数 |
|------|--------|-----------|
| 行业 | 5,506 | 5,506 |
| 概念 | 75,697 | 5,439 |
| 地区 | 5,501 | 3,248 |
| API总量 | 81,198 | — |

---

## 六、经验总结

1. **东方财富有多个子域名**，`push2` 和 `datacenter`/`datacenter-web`/`data` 是完全不同的服务，可达性可能不一致
2. **AKShare 严重依赖 push2 端点**，网络环境不兼容时无法使用其东方财富相关接口
3. **浏览器抓包是找到可用 API 的最有效方法**，JS渲染页面的真实数据接口只能通过网络监控发现
4. **全量获取 vs 逐条查询**：datacenter API 支持无 filter 全量分页，效率远高于逐只股票/逐个板块请求
5. **代码格式差异需注意**：BaoStock 用 `sh.600000`，东方财富用 `600000` 或 `600000.SH`，评估模块需做统一转换

---

## 七、筛选功能参考

### 全参数速查

```bash
python evaluate_stocks.py [选项]
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `--code CODE` | 评估单只股票（详细报告） | `--code sh.600000` |
| `--board B [B...]` | 按板块筛选 | `--board 创业板` |
| `--concept K [K...]` | 按概念/行业关键词筛选 | `--concept AI 机器人` |
| `--top N` | 显示前 N 只（默认 30） | `--top 50` |
| `--list-concepts` | 列出所有可用概念关键词 | |

---

### 7.1 板块筛选 `--board`

根据股票代码前缀自动判断板块：

| 板块 | 代码前缀 | `--board` 参数值 |
|------|----------|-----------------|
| 沪市主板 | `sh.60xxxx` | `沪主板` |
| 深市主板 | `sz.000xxx` / `sz.001xxx` | `深主板` |
| 中小板 | `sz.002xxx` / `sz.003xxx` | `中小板` |
| 创业板 | `sz.300xxx` / `sz.301xxx` | `创业板` |
| 科创板 | `sh.688xxx` / `sh.689xxx` | `科创板` |

**快捷键**：`主板` = 沪主板+深主板+中小板 | `沪市` = 沪主板+科创板 | `深市` = 深主板+中小板+创业板

---

### 7.2 概念/行业筛选 `--concept`

通过关键词模糊匹配股票的概念板块和行业分类，支持多关键词（OR 匹配 + 多概念叠加加分）。

评分策略（alpha = 基础四维分 + 加成）：

| 加成项 | 规则 | 分值 |
|--------|------|------|
| 多概念叠加 | 同时匹配多个关键词 | +8/个 |
| 成长板偏好 | 创业板/科创板 | +5 |
| 概念密度 | 总概念数多（热门龙头） | +2/5个, 上限+6 |
| 产品端优先 | 行业名直接匹配关键词 | +3 |
| 大盘价值降权 | 银行/保险/证券等 | -10 |

```bash
# 查看所有可用概念关键词
python evaluate_stocks.py --list-concepts

# 单概念筛选
python evaluate_stocks.py --concept AI

# 多概念筛选（多概念叠加加分）
python evaluate_stocks.py --concept AI 机器人 芯片

# 板块 + 概念组合
python evaluate_stocks.py --board 创业板 --concept AI --top 20
```

---

### 7.3 筛选流水线

参数可组合使用，执行顺序如下（**先筛选后计算，减少计算量**）：

```
全量股票 (5190)
  │
  ├── --board 创业板  →  按代码前缀过滤  → 1392 只
  │
  ├── --concept AI   →  按板块数据预筛选 → ~500 只
  │
  └── 四维度评估（仅计算筛选后的股票）
       │
       ├── 有 --concept → alpha 排名输出
       └── 无 --concept → 买入推荐 + 卖出警示
```

> **设计决策**：概念预筛选只依赖板块数据（`load_boards()`），不依赖评估结果，因此可在评估前执行，无负面影响。

---

### 7.4 用法示例汇总

```bash
# === 板块筛选 ===
python evaluate_stocks.py --board 创业板              # 主攻创业板
python evaluate_stocks.py --board 科创板 --top 10     # 科创板 TOP 10
python evaluate_stocks.py --board 创业板 科创板        # 创业板 + 科创板
python evaluate_stocks.py --board 沪市                 # 快捷键: 沪主板 + 科创板

# === 概念筛选 ===
python evaluate_stocks.py --concept AI                # AI 概念
python evaluate_stocks.py --concept AI 机器人 芯片     # 多概念叠加
python evaluate_stocks.py --list-concepts              # 列出所有概念

# === 组合筛选 ===
python evaluate_stocks.py --board 创业板 --concept AI --top 20

# === 单只股票详细报告 ===
python evaluate_stocks.py --code sz.300285             # 国瓷材料

# === 不加筛选，全量评估 ===
python evaluate_stocks.py --top 30
```

### 核心代码

筛选逻辑在 [evaluate_stocks.py](file:///f:/PycharmProjects/Stock/evaluate_stocks.py) 中：

- `get_board_name(code)` — 根据代码前缀返回板块名
- `filter_codes_by_board(codes, board_args)` — 按板块过滤
- `filter_codes_by_concept(codes, keywords)` — 按概念/行业预筛选
- `BOARD_SHORTCUTS` — 板块快捷键映射
- `_run_concept_filter(results, keywords, top_n)` — 概念 alpha 排名

---

## VIII. 增强版：七维度综合评分架构 (最新)

最初的模型依赖前四个静态维度（技术面、估值面、基本面、风险面）。在遇到某些股票（如300830/300317）在启动时毫无征兆甚至负分的情况后，新增了三个动态维度以捕捉短期资金和市场情绪的异动。

### 8.1 维度说明与满分结构

目前的综合评估（`total_score`）由以下七个维度构成：

1. **技术面 (±40分)**：MACD, RSI, KDJ, WR, CCI等传统指标综合。
2. **估值面 (±25分)**：PE/PB/PS。
3. **基本面 (±25分)**：ROE、营收、净利润、毛利率等。
4. **风险面 (0~10分)**：主要作为减分项（ST、停牌、高波动率减分）。
5. **动量面 (±15分) [新增]**：
   - 捕捉短期异动：5/20日涨跌幅（针对深跌反弹和暴涨追高）。
   - 捕捉连跌情绪：连续下跌天数（5天/3天）反向加分。
   - 价格占位：当前价格距离20日低点/高点的位置（越靠近低点得分越高）。
6. **资金面 (±15分) [新增/升级]**：
   - **核心升级**：接入东方财富 `push2his.eastmoney.com` API 获取真实主力资金数据。
   - 大额净流入加分（近N日主力净流入>5000万得+6分）。
   - 连续流入天数加分，连续流出减分。
   - 每日主力净流入占比判断强度（>15%得+5分）。
   - **退化机制**：当评估数量>500只时，退化为通过量价代理解析（放量上涨天数、缩量企稳信号、换手率加速、天量天价风险评估）。
7. **热度面 (±10分) [新增]**：
   - 后处理阶段执行（`_apply_sector_heat`）。
   - 取评估池所有股票当天的 `pctChg`，按概念板块分组计算均值即为“板块热度”。
   - 根据股票归属的最热板块的涨跌幅赋分（最热板块上涨>3%得+6分，下跌<-3%扣6分）。
   - 当一支股票属于多个当前热门上升的概念板块时附带额外加分。

### 8.2 资金流向接口细节

使用东方财富内部 API 获取按个股的主力资金明细：
- **接口:** `https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get`
- **特点:** 免登录，不受批量拉取限流干扰（仅对少量股票筛选后拉取）。
- **展示:** 详细评估报告 (`--code sz.xxx`) 自动列显带有以下字段的明细大表：
  - 日期、主力净流入、超大单净流入、大单净流入
  - 主力占比（流入额/总成交额）
  - 合计近3日、近5日、近10日的资金流入/流出/净额。
