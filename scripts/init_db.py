"""初始化 SQLite 数据库(job-agent 全部本地数据)。

幂等:CREATE TABLE IF NOT EXISTS,可重复执行。
用法:python scripts/init_db.py [db_path]
"""

import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "job.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL DEFAULT 'manual',   -- manual / email / rss
    company       TEXT,
    title         TEXT,
    jd_raw        TEXT,                             -- JD 原文
    jd_structured TEXT,                             -- 两阶段解析后的结构化 JSON
    salary        TEXT,
    url           TEXT,
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS profile (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,               -- 简历画像版本名
    resume_json TEXT NOT NULL,                      -- 结构化画像(经历/技能/偏好)
    preferences TEXT,                               -- 求职偏好 JSON(地点/薪资底线/方向)
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS matches (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           INTEGER NOT NULL REFERENCES jobs(id),
    score            REAL,                          -- 最终匹配分 0-100
    hard_filter_pass INTEGER,                       -- 硬性过滤 1/0
    detail           TEXT,                          -- 三段式各段得分明细 JSON
    gap_list         TEXT,                          -- 差距清单 JSON
    eval_label       INTEGER,                       -- 人工标注相关度 1-5(评测用,平时顺手标)
    created_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_matches_job ON matches(job_id);

CREATE TABLE IF NOT EXISTS applications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id),
    status     TEXT NOT NULL DEFAULT 'pending',     -- pending/applied/interview/offer/rejected
    applied_at TEXT,
    next_action TEXT,
    notes      TEXT
);
CREATE INDEX IF NOT EXISTS idx_apps_job ON applications(job_id);

CREATE TABLE IF NOT EXISTS cost_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    scene             TEXT NOT NULL,                -- match / brief / interview / tailor
    model             TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cost_cny          REAL                          -- 本地模型记 0
);

CREATE TABLE IF NOT EXISTS interview_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER REFERENCES jobs(id),
    transcript  TEXT,                               -- 多轮对话 JSON
    rubric_score TEXT,                              -- 复盘评分 JSON
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


def init_db(db_path: Path = DEFAULT_DB) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    print(f"db ready: {db_path}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    init_db(path)
