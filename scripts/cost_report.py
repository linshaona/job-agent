"""成本报表:按场景×模型聚合 cost_log,附近 14 天趋势。

已知限制:OpenHarness v0.1.9 不回传 token usage(session 存储为 0),
oh 会话只能按调用次数记账;直连 API 的调用(如 eval)可记录真实 token。

用法:python scripts/cost_report.py
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "job.db"


def main() -> None:
    if not DB.exists():
        sys.exit("数据库不存在,先运行 scripts/init_db.py")
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT scene, model, COUNT(*) AS calls,"
            " SUM(prompt_tokens) AS pt, SUM(completion_tokens) AS ct,"
            " ROUND(SUM(cost_cny), 4) AS cost"
            " FROM cost_log GROUP BY scene, model ORDER BY calls DESC"
        ).fetchall()
        trend = conn.execute(
            "SELECT date(ts) AS day, COUNT(*) AS calls, ROUND(SUM(cost_cny),4) AS cost"
            " FROM cost_log WHERE ts >= datetime('now','-14 day','localtime')"
            " GROUP BY day ORDER BY day DESC"
        ).fetchall()

    if not rows:
        print("cost_log 暂无数据。埋点途径:\n"
              "  1) scripts/match_jd.py 每次运行自动记一条(scene=match)\n"
              "  2) eval 直连 API 调用可记录真实 token\n"
              "  3) OpenHarness v0.1.9 不回传 usage(上游限制),oh 会话按调用次数记账")
        return

    print(f"{'场景':<10} {'模型':<22} {'次数':>4} {'入tokens':>10} {'出tokens':>10} {'成本¥':>8}")
    print("-" * 72)
    for r in rows:
        print(f"{r['scene'] or '-':<10} {r['model'] or '-':<22} {r['calls']:>4} "
              f"{r['pt'] or 0:>10} {r['ct'] or 0:>10} {r['cost'] or 0:>8}")
    total_calls = sum(r["calls"] for r in rows)
    total_cost = sum(r["cost"] or 0 for r in rows)
    print("-" * 72)
    print(f"合计 {total_calls} 次调用,成本 ¥{total_cost}")

    if trend:
        print("\n近 14 天趋势:")
        for t in trend:
            bar = "█" * min(30, t["calls"])
            print(f"  {t['day']}  {t['calls']:>3} 次  ¥{t['cost'] or 0:<7} {bar}")


if __name__ == "__main__":
    main()
