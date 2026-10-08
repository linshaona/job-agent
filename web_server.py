"""
Job-Agent Web 后端服务
提供个人求职画像可视化编辑、导入导出、数据库同步以及系统状态接口。
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from resume_generator import generate_application_package, generate_standard_markdown, get_current_profile_data

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
STATIC_DIR = BASE_DIR / "static"
DB_PATH = DATA_DIR / "job.db"
PROFILE_PATH = BASE_DIR / "profile.json"

app = FastAPI(title="Job-Agent Workbench API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_connection():
    if not DB_PATH.exists():
        from scripts.init_db import init_db
        init_db(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/status")
def get_status():
    """获取系统整体状态与数据库统计"""
    stats = {
        "db_exists": DB_PATH.exists(),
        "has_local_profile": PROFILE_PATH.exists(),
        "jobs_count": 0,
        "matches_count": 0,
        "profiles_count": 0,
        "current_profile_name": None,
    }
    if DB_PATH.exists():
        try:
            with get_db_connection() as conn:
                stats["jobs_count"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                stats["matches_count"] = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
                stats["profiles_count"] = conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0]
                row = conn.execute("SELECT name FROM profile ORDER BY updated_at DESC LIMIT 1").fetchone()
                if row:
                    stats["current_profile_name"] = row["name"]
        except Exception:
            pass

    return {"status": "ok", "stats": stats}


@app.get("/api/profile/template/{tpl_name}")
def get_template(tpl_name: str):
    """读取预设模板 (student 或 default)"""
    file_map = {
        "student": ASSETS_DIR / "sample-profile.student.json",
        "default": ASSETS_DIR / "sample-profile.json",
    }
    target_file = file_map.get(tpl_name)
    if not target_file or not target_file.exists():
        raise HTTPException(status_code=404, detail=f"模板 {tpl_name} 不存在")
    try:
        content = json.loads(target_file.read_text(encoding="utf-8"))
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取模板失败: {str(e)}")


@app.get("/api/profile")
def get_current_profile():
    """
    获取当前画像。
    优先级: 根目录 profile.json -> 数据库最新一条 -> assets/sample-profile.student.json
    """
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 尝试从数据库读取
    try:
        with get_db_connection() as conn:
            row = conn.execute("SELECT name, resume_json, preferences FROM profile ORDER BY updated_at DESC LIMIT 1").fetchone()
            if row:
                return {
                    "name": row["name"],
                    "resume": json.loads(row["resume_json"]),
                    "preferences": json.loads(row["preferences"]) if row["preferences"] else {},
                }
    except Exception:
        pass

    # 兜底返回 student 模板
    student_tpl = ASSETS_DIR / "sample-profile.student.json"
    if student_tpl.exists():
        return json.loads(student_tpl.read_text(encoding="utf-8"))

    return {"name": "default", "resume": {}, "preferences": {}}


@app.post("/api/profile")
def save_profile(data: Dict[str, Any]):
    """
    保存画像：
    1. 落盘到根目录 profile.json (已被 .gitignore 保护)
    2. 同步写入 SQLite 数据库中的 profile 表
    """
    name = data.get("name", "student").strip() or "student"
    resume = data.get("resume", {})
    preferences = data.get("preferences", {})

    payload = {
        "name": name,
        "resume": resume,
        "preferences": preferences,
    }

    # 1. 写文件
    PROFILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. 写 SQLite 数据库
    from scripts.init_db import init_db
    init_db(DB_PATH)

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO profile (name, resume_json, preferences, updated_at)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(name) DO UPDATE SET
                resume_json = excluded.resume_json,
                preferences = excluded.preferences,
                updated_at = datetime('now', 'localtime')
            """,
            (
                name,
                json.dumps(resume, ensure_ascii=False),
                json.dumps(preferences, ensure_ascii=False),
            ),
        )
        conn.commit()

    return {
        "status": "success",
        "message": f"画像 '{name}' 已成功保存并同步至 SQLite 数据库！",
        "file_path": str(PROFILE_PATH),
    }


@app.get("/api/jobs")
def get_jobs_list():
    """获取所有已录入岗位及其匹配情况"""
    try:
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    j.id, j.company, j.title, j.salary, j.fetched_at,
                    m.score, m.hard_filter_pass, m.gap_list,
                    a.status as app_status
                FROM jobs j
                LEFT JOIN matches m ON j.id = m.job_id
                LEFT JOIN applications a ON j.id = a.job_id
                ORDER BY j.id DESC
            """).fetchall()
            
            jobs = []
            for r in rows:
                jobs.append({
                    "id": r["id"],
                    "company": r["company"],
                    "title": r["title"],
                    "salary": r["salary"],
                    "fetched_at": r["fetched_at"],
                    "score": r["score"],
                    "hard_filter_pass": r["hard_filter_pass"],
                    "gap_list": json.loads(r["gap_list"]) if r["gap_list"] else [],
                    "app_status": r["app_status"] or "pending",
                })
            return {"jobs": jobs}
    except Exception as e:
        return {"jobs": [], "error": str(e)}


@app.get("/api/resume/markdown")
def get_resume_markdown():
    """获取当前求职画像生成的标准全量 ATS 简历 Markdown"""
    md = generate_standard_markdown()
    return {"markdown": md}


@app.post("/api/resume/package")
def create_application_package(payload: Dict[str, Any]):
    """
    生成针对特定岗位的投递包 (Application Package):
    包含定制简历 Markdown、HR 打招呼话术 (Cold Message)、以及面试预测
    """
    job_id = payload.get("job_id")
    company = payload.get("company", "目标公司")
    title = payload.get("title", "目标岗位")
    mode = payload.get("mode", "A")

    if job_id:
        with get_db_connection() as conn:
            row = conn.execute("SELECT company, title FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row:
                company = row["company"] or company
                title = row["title"] or title

    package = generate_application_package(
        {"company": company, "title": title},
        mode=mode
    )
    return package


@app.get("/api/applications")
def get_applications():
    """获取投递看板列表（包含关联的岗位信息与匹配分数）"""
    try:
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT 
                    a.id as app_id, a.job_id, a.status, a.applied_at, a.next_action, a.notes,
                    j.company, j.title, j.salary, j.url, j.fetched_at,
                    m.score, m.hard_filter_pass, m.gap_list
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                LEFT JOIN matches m ON j.id = m.job_id
                ORDER BY a.id DESC
            """).fetchall()

            apps = []
            for r in rows:
                apps.append({
                    "app_id": r["app_id"],
                    "job_id": r["job_id"],
                    "status": r["status"] or "pending",
                    "applied_at": r["applied_at"] or "",
                    "next_action": r["next_action"] or "",
                    "notes": r["notes"] or "",
                    "company": r["company"] or "未知公司",
                    "title": r["title"] or "未知岗位",
                    "salary": r["salary"] or "",
                    "url": r["url"] or "",
                    "fetched_at": r["fetched_at"],
                    "score": r["score"],
                    "hard_filter_pass": r["hard_filter_pass"],
                    "gap_list": json.loads(r["gap_list"]) if r["gap_list"] else [],
                })
            return {"applications": apps}
    except Exception as e:
        return {"applications": [], "error": str(e)}


@app.post("/api/applications")
def update_application(payload: Dict[str, Any]):
    """创建或更新投递状态"""
    job_id = payload.get("job_id")
    status = payload.get("status", "pending")
    applied_at = payload.get("applied_at")
    next_action = payload.get("next_action", "")
    notes = payload.get("notes", "")

    if not job_id:
        raise HTTPException(status_code=400, detail="缺少 job_id")

    with get_db_connection() as conn:
        existing = conn.execute("SELECT id FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE applications SET 
                    status = ?, applied_at = COALESCE(?, applied_at), 
                    next_action = ?, notes = ?
                WHERE job_id = ?
                """,
                (status, applied_at, next_action, notes, job_id)
            )
        else:
            conn.execute(
                """
                INSERT INTO applications (job_id, status, applied_at, next_action, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, status, applied_at, next_action, notes)
            )
        conn.commit()

    return {"status": "success", "message": "投递状态更新成功"}


@app.post("/api/applications/create-job")
def create_job_and_apply(payload: Dict[str, Any]):
    """手动快捷添加岗位并加入投递看板"""
    company = payload.get("company", "").strip() or "未命名公司"
    title = payload.get("title", "").strip() or "目标岗位"
    salary = payload.get("salary", "").strip()
    url = payload.get("url", "").strip()
    jd_raw = payload.get("jd_raw", "").strip()
    initial_status = payload.get("status", "pending")

    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO jobs (source, company, title, salary, url, jd_raw)
            VALUES ('manual', ?, ?, ?, ?, ?)
            """,
            (company, title, salary, url, jd_raw)
        )
        job_id = cursor.lastrowid
        
        conn.execute(
            """
            INSERT INTO applications (job_id, status, applied_at, next_action, notes)
            VALUES (?, ?, datetime('now', 'localtime'), '', '')
            """,
            (job_id, initial_status)
        )
        conn.commit()

    return {"status": "success", "job_id": job_id, "message": f"岗位【{company} - {title}】已录入并加入投递看板！"}


@app.delete("/api/applications/{app_id}")
def delete_application(app_id: int):
    """删除投递记录"""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        conn.commit()
    return {"status": "success", "message": "投递记录已删除"}


# 挂载静态目录
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"message": "Job-Agent Web 后端已启动，等待静态页面就绪"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_server:app", host="127.0.0.1", port=8000, reload=True)
