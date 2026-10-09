"""
三段式 JD 智能匹配与差距分析引擎 (Three-Stage JD Matcher & Gap Analyzer)
对齐 job-agent 架构设计:
1. 阶段一: 规则引擎硬性过滤 (地点/学历/年限/薪资底线，零 Token 消耗、100% 可解释)
2. 阶段二: 技能集合重合与语义召回 (提取关键技术栈，计算交集与覆盖率)
3. 阶段三: 维度加权 Rubric 打分 (技能契合度、业务相关度、成长性) + 差距清单 (Gap List) 与面试建议
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
PROFILE_PATH = BASE_DIR / "profile.json"


def get_profile() -> Dict[str, Any]:
    """读取当前 profile.json"""
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    sample_file = BASE_DIR / "assets" / "sample-profile.student.json"
    if sample_file.exists():
        return json.loads(sample_file.read_text(encoding="utf-8"))
    return {"name": "default", "resume": {}, "preferences": {}}


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


def extract_jd_entities(jd_text: str, default_company: str = "", default_title: str = "") -> Dict[str, Any]:
    """
    结构化抽取岗位要素 (公司、职位、薪资、地点、年限、核心技术)
    """
    company = default_company or "未知企业"
    title = default_title or "AI 研发工程师"
    salary = "薪资面议"
    location = "全国/待定"
    exp_required = "经验不限"
    skills_found = []

    # 1. 识别薪资
    salary_match = re.search(r"(\d+[-~]\d+[kKwW]|\d+[kKwW]·\d+薪|\d+[-~]\d+元/天|\d+元/天)", jd_text)
    if salary_match:
        salary = salary_match.group(1)

    # 2. 识别地点
    for city in ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "远程"]:
        if city in jd_text:
            location = city
            break

    # 3. 识别经验要求
    exp_match = re.search(r"([0-9一两三四五]+年[及以]?[上下的]?经验|应届[生]?|在校[生]?|实习)", jd_text)
    if exp_match:
        exp_required = exp_match.group(1)

    # 4. 识别职位标题
    for t_kw in ["游戏开发", "Unity开发", "Unity客户端", "游戏研发实习生", "游戏客户端开发", "C++游戏开发", "AI应用开发", "AI Agent", "Agent开发", "大模型算法", "后端开发", "Python开发", "算法工程师", "软件开发实习生"]:
        if t_kw in jd_text:
            title = t_kw
            break

    # 5. 提取技能技术词
    jd_lower = jd_text.lower()
    for kw in COMMON_TECH_KEYWORDS:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, jd_lower) or kw.lower() in jd_lower:
            if kw not in skills_found:
                skills_found.append(kw)

    return {
        "company": company,
        "title": title,
        "salary": salary,
        "location": location,
        "exp_required": exp_required,
        "skills_required": skills_found or ["Python", "FastAPI", "Agent"]
    }


def analyze_jd_match(
    jd_text: str,
    company: str = "",
    title: str = "",
    profile: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    执行三段式完整匹配流水线
    """
    if profile is None:
        profile = get_profile()

    resume = profile.get("resume", {})
    basics = resume.get("basics", {})
    candidate_skills = resume.get("skills", [])
    preferences = profile.get("preferences", {})

    extracted = extract_jd_entities(jd_text, company, title)
    comp_name = company or extracted["company"]
    job_title = title or extracted["title"]
    jd_skills = extracted["skills_required"]

    # ----------------------------------------------------
    # 第一段：硬性条件核对 (Rule Engine)
    # ----------------------------------------------------
    hard_filter_pass = True
    hard_filter_reasons = []

    # 1. 城市核对
    pref_cities = preferences.get("期望城市", [])
    if pref_cities and extracted["location"] not in ["全国/待定", "远程"]:
        if not any(c in extracted["location"] for c in pref_cities):
            hard_filter_pass = False
            hard_filter_reasons.append(f"城市【{extracted['location']}】不在期望城市清单中({', '.join(pref_cities)})")
        else:
            hard_filter_reasons.append(f"✔ 城市契合: {extracted['location']}")
    else:
        hard_filter_reasons.append("✔ 城市无硬性冲突")

    # 2. 身份/经验核对
    is_student = "学生" in basics.get("身份", "") or "在校" in basics.get("身份", "") or "202" in basics.get("毕业时间", "")
    if is_student and ("3年" in extracted["exp_required"] or "5年" in extracted["exp_required"]):
        hard_filter_pass = False
        hard_filter_reasons.append(f"岗位要求【{extracted['exp_required']}】，当前在校身份可能不符合硬性年限")
    else:
        hard_filter_reasons.append("✔ 经验/身份要求在合理区间")

    # ----------------------------------------------------
    # 第二段：技能重合计算与 Gap 分析
    # ----------------------------------------------------
    cand_skills_lower = {s.lower(): s for s in candidate_skills}
    matching_skills = []
    gap_skills = []

    for req_s in jd_skills:
        req_l = req_s.lower()
        if req_l in cand_skills_lower:
            matching_skills.append(cand_skills_lower[req_l])
        else:
            # 模糊匹配
            found = False
            for cs_l, cs_raw in cand_skills_lower.items():
                if req_l in cs_l or cs_l in req_l:
                    matching_skills.append(cs_raw)
                    found = True
                    break
            if not found:
                gap_skills.append(req_s)

    # 技能重合得分 (0~100)
    skill_coverage = len(matching_skills) / max(len(jd_skills), 1)
    skill_score = min(100, int(skill_coverage * 100))

    # ----------------------------------------------------
    # 第三段：Rubric 维度量表打分与综合得分
    # ----------------------------------------------------
    # 维度 1: 技能契合度 (1-5 分)
    dim_skill = min(5, max(1, round(skill_coverage * 5)))

    # 维度 2: 业务相关度 (1-5 分)
    dim_business = 3
    if any(k in job_title for k in ["游戏", "Unity", "客户端", "Agent", "AI", "大模型", "Python", "C#", "C++"]):
        dim_business = 5
    elif any(k in job_title for k in ["后端", "研发", "软件"]):
        dim_business = 4

    # 维度 3: 个人加分项 (1-5 分)
    dim_bonus = 4 if any(k in jd_text for k in ["开源", "项目", "架构", "独立开发", "全流程", "评测", "竞赛", "Shader", "物理"]) else 3

    # 加权总分 = 技能45% + 业务35% + 加分20%
    weighted_score = int((dim_skill / 5.0) * 45 + (dim_business / 5.0) * 35 + (dim_bonus / 5.0) * 20)
    if not hard_filter_pass:
        weighted_score = min(weighted_score, 55)

    # 生成突击建议
    # 项目名属于画像数据,从 profile 读:代码里不写死任何具体项目,换画像文案自动跟着变
    focus_projects = []
    for p in resume.get("projects", [])[:2]:
        if isinstance(p, dict) and p.get("名称"):
            # 只取项目名主干,去掉括号里的补充说明,避免句子过长
            focus_projects.append(str(p["名称"]).split("(")[0].split("（")[0].strip())
    focus = "、".join([f for f in focus_projects if f]) or "你的核心实战项目"

    advice = []
    if gap_skills:
        advice.append(f"【技能突击】针对 JD 提及的【{', '.join(gap_skills[:3])}】，建议在面试前了解核心原理并在简历定制版中补充相关技术名词。")
    if matching_skills:
        advice.append(f"【核心优势】你的【{', '.join(matching_skills[:4])}】与该岗位高度对齐，面试时重点围绕{focus}展示闭环能力。")
    if any(k in job_title for k in ["游戏", "Unity", "客户端"]):
        advice.append("【提问预案】建议提前准备好 C#/C++ 语言基础、Unity 生命周期与渲染管线（URP/Shader Graph）、以及 PlayerPrefs 数据持久化和物理碰撞优化以应对深挖。")
    else:
        advice.append("【提问预案】建议提前准备好核心项目的架构选型、性能调优及算法赛事的工程落地实践以应对深挖。")

    return {
        "company": comp_name,
        "title": job_title,
        "salary": extracted["salary"],
        "location": extracted["location"],
        "exp_required": extracted["exp_required"],
        "hard_filter_pass": 1 if hard_filter_pass else 0,
        "hard_filter_reasons": hard_filter_reasons,
        "score": weighted_score,
        "rubric": {
            "skill_match": dim_skill,
            "business_match": dim_business,
            "bonus_match": dim_bonus,
        },
        "matching_skills": matching_skills,
        "gap_list": gap_skills,
        "advice": advice,
        "jd_raw": jd_text,
    }
