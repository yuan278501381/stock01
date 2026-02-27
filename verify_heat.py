"""验证批量热度评分是否正确注入"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from evaluate_stocks import *
from evaluate_stocks import _apply_sector_heat

codes = get_all_downloaded_codes()
codes = filter_codes_by_board(codes, ["创业板"])
codes = filter_codes_by_concept(codes, ["AI"])
print(f"筛选后: {len(codes)} 只")

results = []
for code in codes[:50]:  # 只评估前50只加速验证
    r = evaluate_single(code)
    if r:
        results.append(r)

print(f"评估完成: {len(results)} 只")
print(f"热度注入前 - 示例总分: {results[0]['total_score']}, 热度: {results[0]['heat_score']}")

_apply_sector_heat(results)

print(f"热度注入后:")
for r in sorted(results, key=lambda x: x['total_score'], reverse=True)[:5]:
    print(f"  {r['code']} {r['name']:<10} 总分:{r['total_score']:>+4}"
          f" 技术:{r['tech_score']:>+3} 估值:{r['val_score']:>+3} 基本:{r['fund_score']:>+3}"
          f" 风险:{r['risk_score']:>+2} 动量:{r['mom_score']:>+3} 资金:{r['flow_score']:>+3}"
          f" 热度:{r['heat_score']:>+3}")
    if r['heat_signals']:
        print(f"         热度信号: {', '.join(r['heat_signals'])}")
    if r['mom_signals']:
        print(f"         动量信号: {', '.join(r['mom_signals'])}")
