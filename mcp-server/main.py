"""job-agent 数据 MCP server。

设计原则:确定性计算(SQL 读写、embedding 相似度)收在 Python 里,
模型只负责判断(rubric 打分、差距分析)。所有数据落在本地 SQLite。
"""

import json
import math
import os
import sqlite3
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("JOB_AGENT_DB", ROOT / "data" / "job.db"))
EMBED_URL = os.environ.get("EMBED_BASE_URL", "http://10.102.170.214:11434/v1")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")

mcp = MCPServer("job-agent-data")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _resume_text(resume: dict) -> str:
    """把结构化画像压成一段供 embedding 的文本(工作/实习、项目、校园经历都覆盖)。"""
    parts = []
    basics = resume.get("basics") or {}
    parts.append(" ".join(str(v) for v in basics.values() if v))
    parts.extend(resume.get("skills") or [])
    for exp in resume.get("experiences") or []:
        parts.append(" ".join(str(v) for v in exp.values() if v))
    for proj in resume.get("projects") or []:
        parts.append(" ".join(str(v) for v in proj.values() if v))
    campus = resume.get("campus") or {}
    if campus:
        parts.append(" ".join(str(v) for v in campus.values() if v))
    parts.append(resume.get("summary_text") or "")
    return " ".join(p for p in parts if p)[:4000]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


@mcp.tool()
def save_job(
    source: str,
    company: str,
    title: str,
    jd_raw: str,
    salary: str = "",
    url: str = "",
    jd_structured: dict | None = None,
) -> dict:
    """保存一份职位描述并返回 job_id。source 取值:manual/email/rss。"""
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (source, company, title, jd_raw, salary, url, jd_structured)"
            " VALUES (?,?,?,?,?,?,?)",
            (source, company, title, jd_raw, salary, url,
             json.dumps(jd_structured, ensure_ascii=False) if jd_structured else None),
        )
        return {"job_id": cur.lastrowid}


@mcp.tool()
def get_profile(profile_name: str = "default") -> dict:
    """读取简历画像与求职偏好(期望城市/薪资底线/经验底线等)。"""
    with db() as conn:
        row = conn.execute(
            "SELECT name, resume_json, preferences FROM profile WHERE name = ?",
            (profile_name,),
        ).fetchone()
        if row is None:
            # 单用户工具:名字对不上但库里只有一个画像时,直接返回它
            only = conn.execute("SELECT name, resume_json, preferences FROM profile").fetchall()
            if len(only) == 1:
                row = only[0]
    if row is None:
        with db() as conn:
            names = [r["name"] for r in conn.execute("SELECT name FROM profile")]
        return {
            "error": f"profile '{profile_name}' 不存在",
            "available": names,
            "hint": "用 available 列表中的名字重试,或运行 scripts/seed_profile.py 导入",
        }
    return {
        "name": row["name"],
        "resume": json.loads(row["resume_json"]),
        "preferences": json.loads(row["preferences"]) if row["preferences"] else {},
    }


@mcp.tool()
def semantic_score(jd_text: str, profile_name: str = "default") -> dict:
    """计算简历画像与 JD 的语义相似度(0-100)。embedding 在服务端完成,模型无需自己算。"""
    with db() as conn:
        row = conn.execute(
            "SELECT resume_json FROM profile WHERE name = ?", (profile_name,)
        ).fetchone()
    if row is None:
        return {"error": f"profile '{profile_name}' 不存在"}
    resume = json.loads(row["resume_json"])
    resp = httpx.post(
        f"{EMBED_URL}/embeddings",
        json={"model": EMBED_MODEL, "input": [_resume_text(resume), jd_text[:4000]]},
        timeout=60,
    )
    resp.raise_for_status()
    vectors = [item["embedding"] for item in resp.json()["data"]]
    return {"similarity": round(_cosine(vectors[0], vectors[1]) * 100, 1)}


def _as_float(v: float | str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_bool(v: bool | int | str | None) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "pass", "通过")
    return bool(v)


def _as_obj(v: dict | list | str | None) -> dict | list | None:
    """模型经常把数组/对象传成 JSON 字符串,统一在服务端收敛。"""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return None
    return v


@mcp.tool()
def save_match(
    job_id: int,
    score: float | str,
    hard_filter_pass: bool | int | str,
    semantic: float | str | None = None,
    dimensions: dict | str | None = None,
    gap_list: list | str | None = None,
) -> dict:
    """写入匹配结果。dimensions 形如 {"技能重叠":4,"业务相关性":3,"成长性":4};gap_list 为差距清单数组。参数可传原生类型或 JSON 字符串,服务端自动转换。"""
    dims = _as_obj(dimensions)
    gaps = _as_obj(gap_list)
    detail = json.dumps(
        {"semantic": _as_float(semantic), "dimensions": dims}, ensure_ascii=False
    )
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO matches (job_id, score, hard_filter_pass, detail, gap_list)"
            " VALUES (?,?,?,?,?)",
            (job_id, _as_float(score) or 0.0, int(_as_bool(hard_filter_pass)), detail,
             json.dumps(gaps, ensure_ascii=False) if gaps else None),
        )
        return {"match_id": cur.lastrowid}


@mcp.tool()
def track_application(
    job_id: int, status: str = "pending", next_action: str = "", notes: str = ""
) -> dict:
    """记录/更新投递状态。status 取值:pending/applied/interview/offer/rejected。"""
    with db() as conn:
        open_row = conn.execute(
            "SELECT id FROM applications WHERE job_id = ? AND status NOT IN ('offer','rejected')",
            (job_id,),
        ).fetchone()
        if open_row:
            conn.execute(
                "UPDATE applications SET status=?, next_action=?, notes=? WHERE id=?",
                (status, next_action, notes, open_row["id"]),
            )
            return {"application_id": open_row["id"], "updated": True}
        cur = conn.execute(
            "INSERT INTO applications (job_id, status, next_action, notes) VALUES (?,?,?,?)",
            (job_id, status, next_action, notes),
        )
        return {"application_id": cur.lastrowid, "updated": False}


@mcp.tool()
def log_cost(
    scene: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_cny: float = 0.0,
    model: str = "",
) -> dict:
    """记录一次调用的成本(scene: match/brief/interview/tailor;本地模型 cost_cny=0)。"""
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO cost_log (scene, model, prompt_tokens, completion_tokens, cost_cny)"
            " VALUES (?,?,?,?,?)",
            (scene, model, prompt_tokens, completion_tokens, cost_cny),
        )
        return {"cost_id": cur.lastrowid}


@mcp.tool()
def list_jobs(limit: int = 20) -> list:
    """列出最近的职位及其最高匹配分。"""
    with db() as conn:
        rows = conn.execute(
            "SELECT j.id, j.company, j.title, j.salary, j.source,"
            " MAX(m.score) AS best_score"
            " FROM jobs j LEFT JOIN matches m ON m.job_id = j.id"
            " GROUP BY j.id ORDER BY j.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    mcp.run()
