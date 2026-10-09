"""
简历上传与多格式解析引擎 (Resume Parser & Attachment Manager)
支持格式:
- PDF (.pdf) -> 使用 pypdf 提取文本
- Word (.docx) -> 使用 python-docx 提取文本与表格
- Markdown / 文本 (.md, .txt) -> UTF-8 文本解析
- JSON (.json) -> 结构化 profile 直接解析

功能:
1. 物理附件存储至 data/uploads/，保留原件供自动投递时作为邮件简历附件
2. 自动抽取核心要素 (姓名、电话、邮箱、学校、专业、学历、技能标签)
3. 同步更新本地 profile.json 与 SQLite 数据库
"""

import io
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import docx
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
META_PATH = DATA_DIR / "resume_attachment_meta.json"
PROFILE_PATH = BASE_DIR / "profile.json"
DB_PATH = DATA_DIR / "job.db"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

COMMON_TECH_KEYWORDS = [
    "Unity", "C#", "C++", "URP", "Shader Graph", "Shader", "Spine", "Spine 2D", "OpenGL", "DirectX",
    "Unreal", "UE", "3D", "2D", "物理引擎", "Lua", "PlayerPrefs",
    "Python", "FastAPI", "Flask", "Django", "SQL", "MySQL", "PostgreSQL", "SQLite", "Redis",
    "MongoDB", "Docker", "Kubernetes", "Linux", "Git", "pytest", "CI/CD",
    "Agent", "ReAct", "ReWOO", "MCP", "RAG", "LLM", "Prompt", "LangChain", "LlamaIndex",
    "OpenHarness", "Ollama", "PyTorch", "TensorFlow", "Transformer", "BERT", "Embedding",
    "Java", "Spring", "Go", "Golang", "Rust", "Node.js", "TypeScript", "React", "Vue",
    "Claude Code", "Cursor", "Codex"
]


def get_attachment_meta() -> Optional[Dict[str, Any]]:
    """获取当前已上传的简历附件元数据"""
    if META_PATH.exists():
        try:
            return json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def extract_text_from_bytes(filename: str, content: bytes) -> str:
    """从二进制流中提取纯文本"""
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n".join(text_parts).strip()

    elif ext == ".docx":
        doc = docx.Document(io.BytesIO(content))
        text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        text_parts.append(cell.text.strip())
        return "\n".join(text_parts).strip()

    elif ext in [".txt", ".md"]:
        return content.decode("utf-8", errors="ignore").strip()

    elif ext == ".json":
        data = json.loads(content.decode("utf-8", errors="ignore"))
        # 展平成文本
        return json.dumps(data, ensure_ascii=False, indent=2)

    else:
        raise ValueError(f"不支持的文件格式: {ext}，仅支持 .pdf, .docx, .md, .txt, .json")


def extract_entities_from_text(raw_text: str) -> Dict[str, Any]:
    """从简历文本中自动提取关键候选人信息"""
    name = ""
    phone = ""
    email = ""
    school = ""
    major = ""
    degree = ""
    grad_year = ""
    skills = []

    # 1. 电话提取
    phone_match = re.search(r"\b(1[3-9]\d{9})\b", raw_text)
    if phone_match:
        phone = phone_match.group(1)

    # 2. 邮箱提取
    email_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", raw_text)
    if email_match:
        email = email_match.group(1)

    # 3. 毕业时间提取
    grad_match = re.search(r"(202[4-9]\s*[年\.]\s*\d{1,2}|202[4-9]\s*届)", raw_text)
    if grad_match:
        grad_year = grad_match.group(1).replace(" ", "")

    # 4. 学历提取
    for deg in ["博士", "硕士", "本科", "大专"]:
        if deg in raw_text:
            degree = deg
            break

    # 5. 学校提取
    sch_match = re.search(r"([\u4e00-\u9fa5]{2,10}(?:大学|学院|分校))", raw_text)
    if sch_match:
        school = sch_match.group(1)

    # 6. 专业提取
    for maj in ["计算机科学与技术", "软件工程", "人工智能", "自动化", "电子信息", "大数据", "信息安全", "通信工程"]:
        if maj in raw_text:
            major = maj
            break

    # 7. 姓名猜测 (通常在文本最前面的行或带'姓名'标识)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    name_label_match = re.search(r"(?:姓名|Name)[：:\s]+([\u4e00-\u9fa5]{2,4})", raw_text)
    if name_label_match:
        name = name_label_match.group(1)
    elif lines:
        for first_line in lines[:3]:
            # 如果是 2-4 个汉字且不包含常见词汇
            candidate = re.sub(r"[^\u4e00-\u9fa5]", "", first_line)
            if 2 <= len(candidate) <= 4 and not any(kw in candidate for kw in ["简历", "求职", "个人", "电话", "邮箱"]):
                name = candidate
                break

    # 8. 技术栈关键词匹配
    text_lower = raw_text.lower()
    for kw in COMMON_TECH_KEYWORDS:
        if kw.lower() in text_lower and kw not in skills:
            skills.append(kw)

    return {
        "姓名": name or "候选人",
        "电话": phone,
        "邮箱": email,
        "学校": school,
        "专业": major,
        "学历": degree or "本科",
        "毕业时间": grad_year,
        "skills": skills or ["Python", "FastAPI", "Agent"],
    }


def parse_and_save_resume_file(filename: str, content: bytes) -> Dict[str, Any]:
    """
    保存上传的简历原文件，解析内容，并同步至 profile.json 与 SQLite
    """
    ext = Path(filename).suffix.lower()
    clean_stem = re.sub(r"[^\w\-_.]", "_", Path(filename).stem)
    target_filename = f"{clean_stem}{ext}"
    target_path = UPLOADS_DIR / target_filename

    # 1. 保存物理附件原件
    target_path.write_bytes(content)

    # 2. 提取文本与实体
    raw_text = extract_text_from_bytes(filename, content)

    # 如果上传的是 json 格式，直接按结构化合并
    if ext == ".json":
        try:
            parsed_json = json.loads(content.decode("utf-8"))
            resume_data = parsed_json.get("resume", {})
            basics_extracted = resume_data.get("basics", {})
            skills_extracted = resume_data.get("skills", [])
            summary_extracted = resume_data.get("summary_text", "")
            projects_extracted = resume_data.get("projects", [])
            experiences_extracted = resume_data.get("experiences", [])
        except Exception:
            basics_extracted = extract_entities_from_text(raw_text)
            skills_extracted = basics_extracted.pop("skills", [])
            summary_extracted = raw_text[:300]
            projects_extracted = []
            experiences_extracted = []
    else:
        basics_extracted = extract_entities_from_text(raw_text)
        skills_extracted = basics_extracted.pop("skills", [])
        # 提取前 200 字作为综述摘要
        first_lines = [l for l in raw_text.splitlines() if len(l.strip()) > 10]
        summary_extracted = "\n".join(first_lines[:4]) if first_lines else "具备扎实的软件与 AI 工程开发实战能力。"
        projects_extracted = []
        experiences_extracted = []

    # 3. 读取现有的 profile.json 进行增量合并 (保留已有的 issue-pr-agent 和 job-agent 项目)
    existing_profile = {}
    if PROFILE_PATH.exists():
        try:
            existing_profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing_resume = existing_profile.get("resume", {})
    existing_basics = existing_resume.get("basics", {})
    existing_projects = existing_resume.get("projects", [])
    existing_skills = existing_resume.get("skills", [])

    # 合并基本信息 (优先使用提取出的非空信息)
    for k, v in basics_extracted.items():
        if v:
            existing_basics[k] = v

    # 合并技能
    merged_skills = list(dict.fromkeys(existing_skills + skills_extracted))

    # 更新 profile 结构
    updated_profile = {
        "name": existing_profile.get("name", "my_profile"),
        "resume": {
            "basics": existing_basics,
            "skills": merged_skills,
            "experiences": experiences_extracted or existing_resume.get("experiences", []),
            "projects": projects_extracted or existing_projects,
            "campus": existing_resume.get("campus", {}),
            "education": {
                "学校": existing_basics.get("学校", ""),
                "专业": existing_basics.get("专业", ""),
                "学历": existing_basics.get("学历", "本科"),
                "时间": existing_basics.get("毕业时间", "")
            },
            "summary_text": summary_extracted or existing_resume.get("summary_text", "")
        },
        "preferences": existing_profile.get("preferences", {
            "目标岗位": ["AI Agent 研发工程师", "Python 后端开发"],
            "期望城市": ["上海", "杭州", "远程"],
            "薪资底线": "18k",
            "加分项": ["掌握 Agent Harness 架构与 MCP 协议"]
        })
    }

    # 4. 写回 profile.json
    PROFILE_PATH.write_text(json.dumps(updated_profile, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5. 同步写入 SQLite 数据库中的 profile 表
    try:
        from scripts.init_db import init_db
        init_db(DB_PATH)
        with sqlite3.connect(DB_PATH) as conn:
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
                    updated_profile["name"],
                    json.dumps(updated_profile["resume"], ensure_ascii=False),
                    json.dumps(updated_profile["preferences"], ensure_ascii=False)
                )
            )
            conn.commit()
    except Exception as e:
        print(f"写入 SQLite 数据库警告: {e}")

    # 6. 保存附件元数据
    file_size_kb = max(1, round(len(content) / 1024))
    meta = {
        "filename": filename,
        "saved_filename": target_filename,
        "file_path": str(target_path),
        "file_size": f"{file_size_kb} KB",
        "file_type": ext.replace(".", "").upper(),
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "raw_text_preview": raw_text[:500],
        "extracted_basics": existing_basics,
        "extracted_skills": merged_skills[:10]
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return meta
