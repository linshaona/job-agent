"""每日晨报:汇总最近 24h 的新职位与匹配分,推送到飞书/Telegram;未配置推送时落盘。

设计:纯 SQL + 模板,不调 LLM——cron 场景下要快、要稳,LLM 摘要是后续增强。

用法:
    python scripts/daily_brief.py             # 生成并推送今天的晨报
    python scripts/daily_brief.py --demo      # 用内置假数据走一遍(测试用,不读库)
    python scripts/daily_brief.py --register  # 注册 Windows 计划任务(每日 08:30)

环境变量(.env):FEISHU_WEBHOOK / TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID,都没配则只落盘。
"""

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIEFS = ROOT / "data" / "briefs"
PY = sys.executable

DEMO_ROWS = [
    {"id": 1, "title": "AI应用开发实习生", "company": "某大模型应用公司", "salary": "250元/天",
     "score": 94, "gap_list": ["缺生产级 LangChain 经验", "Kafka 未接触"]},
    {"id": 2, "title": "Python后端实习生", "company": "某SaaS公司", "salary": "220元/天",
     "score": 88, "gap_list": ["无"]},
    {"id": 3, "title": "LLM应用开发实习生", "company": "某Agent平台公司", "salary": "300元/天",
     "score": 85, "gap_list": ["MCP 协议了解尚浅"]},
]

QUERY = """
SELECT j.id, j.title, j.company, j.salary, m.score, m.gap_list
FROM jobs j
JOIN matches m ON m.job_id = j.id
WHERE m.id IN (SELECT MAX(id) FROM matches GROUP BY job_id)
  AND j.fetched_at >= datetime('now', '-1 day', 'localtime')
ORDER BY m.score DESC
"""

TODO_QUERY = """
SELECT a.next_action, j.title, j.company
FROM applications a JOIN jobs j ON j.id = a.job_id
WHERE a.status NOT IN ('offer', 'rejected') AND a.next_action != ''
"""


def fetch_rows() -> list[dict]:
    with sqlite3.connect(ROOT / "data" / "job.db") as conn:
        conn.row_factory = sqlite3.Row
        jobs = [dict(r) for r in conn.execute(QUERY)]
        todos = [dict(r) for r in conn.execute(TODO_QUERY)]
    for j in jobs:
        try:
            j["gap_list"] = json.loads(j["gap_list"] or "[]")
        except json.JSONDecodeError:
            j["gap_list"] = []
    return {"jobs": jobs, "todos": todos}


def build_brief(data: dict) -> str:
    today = datetime.now().strftime("%m-%d %a")
    jobs = data["jobs"]
    lines = [f"📮 求职晨报 {today}"]
    if not jobs:
        lines.append("过去 24h 无新职位。保持节奏,别忘了跟进在手流程。")
    for j in jobs:
        score = j.get("score")
        head = f"· [{score:.0f}分] {j['title']} | {j['company']}"
        if j.get("salary"):
            head += f" | {j['salary']}"
        lines.append(head)
        for gap in (j.get("gap_list") or [])[:2]:
            lines.append(f"    - 差距:{gap}")
    if data.get("todos"):
        lines.append("")
        lines.append("⏰ 待跟进:")
        lines.extend(f"· {t['next_action']} —— {t['title']}({t['company']})" for t in data["todos"])
    return "\n".join(lines)


def push_feishu(text: str, webhook: str) -> bool:
    import httpx
    resp = httpx.post(webhook, json={"msg_type": "text", "content": {"text": text}}, timeout=30)
    return resp.status_code == 200


def push_telegram(text: str, token: str, chat_id: str) -> bool:
    import httpx
    resp = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text}, timeout=30,
    )
    return resp.status_code == 200


def deliver(text: str, env: dict) -> str:
    """按可用通道推送,返回通道说明;一个都没配则落盘。"""
    BRIEFS.mkdir(exist_ok=True)
    out = BRIEFS / f"brief-{datetime.now():%Y%m%d}.md"
    out.write_text(text, encoding="utf-8")
    channels = []
    if env.get("FEISHU_WEBHOOK"):
        if push_feishu(text, env["FEISHU_WEBHOOK"]):
            channels.append("飞书")
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        if push_telegram(text, env["TELEGRAM_BOT_TOKEN"], env["TELEGRAM_CHAT_ID"]):
            channels.append("Telegram")
    if not channels:
        return f"未配置推送通道,晨报已存 {out}"
    return f"已推送:{'/'.join(channels)};备份 {out}"


def register_task() -> None:
    task = "job-agent-daily-brief"
    tr = f'"{PY}" "{Path(__file__).resolve()}"'
    cmd = ["schtasks", "/Create", "/F", "/TN", task, "/SC", "DAILY", "/ST", "08:30", "/TR", tr]
    subprocess.run(cmd, check=True)
    print(f"已注册计划任务 {task}(每日 08:30);删除:schtasks /Delete /TN {task} /F")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="用内置假数据走一遍")
    ap.add_argument("--register", action="store_true", help="注册每日 08:30 计划任务")
    args = ap.parse_args()

    if args.register:
        register_task()
        return

    env = {}
    dot = ROOT / ".env"
    if dot.exists():
        for line in dot.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()

    data = {"jobs": DEMO_ROWS, "todos": []} if args.demo else fetch_rows()
    brief = build_brief(data)
    print(brief)
    print("\n---")
    print(deliver(brief, env))


if __name__ == "__main__":
    main()
