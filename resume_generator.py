"""
简历生成引擎与投递包生成器 (Resume & Application Package Generator)
参考开源优秀设计:
- srbhr/Resume-Matcher: ATS 友好度、关键词对齐与格式标准化
- sharzoy/auto-job-apply: 投递包概念 (针对性定制简历 + HR破冰开场白 + 面试预测预案)
- Reactive-Resume: 优雅排版与印刷级 Markdown/HTML 渲染
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).resolve().parent
PROFILE_PATH = BASE_DIR / "profile.json"
ASSETS_DIR = BASE_DIR / "assets"


def get_current_profile_data() -> Dict[str, Any]:
    """读取当前 profile.json，若不存在则回退至学生样本"""
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    sample_file = ASSETS_DIR / "sample-profile.student.json"
    if sample_file.exists():
        return json.loads(sample_file.read_text(encoding="utf-8"))
    return {"name": "default", "resume": {}, "preferences": {}}


def generate_standard_markdown(profile: Optional[Dict[str, Any]] = None) -> str:
    """
    生成标准全量简历 (ATS 友好排版 Markdown)
    """
    if profile is None:
        profile = get_current_profile_data()

    resume = profile.get("resume", {})
    basics = resume.get("basics", {})
    skills = resume.get("skills", [])
    experiences = resume.get("experiences", [])
    projects = resume.get("projects", [])
    campus = resume.get("campus", {})
    education = resume.get("education", {})
    summary = resume.get("summary_text", "")

    lines = []

    # 1. 姓名与个人抬头
    name = basics.get("姓名") or "个人简历"
    lines.append(f"# {name}")

    contact_parts = []
    if basics.get("身份"):
        contact_parts.append(basics["身份"])
    if basics.get("求职类型"):
        contact_parts.append(f"求职类型: {basics['求职类型']}")
    if basics.get("毕业时间"):
        contact_parts.append(f"毕业时间: {basics['毕业时间']}")
    if basics.get("学校"):
        contact_parts.append(f"{basics['学校']} · {basics.get('专业', '')}")

    if contact_parts:
        lines.append(f"**{' | '.join(contact_parts)}**\n")

    # 2. 个人总结
    if summary:
        lines.append("## 个人综述 / Summary")
        lines.append(f"{summary}\n")

    # 3. 掌握技能
    if skills:
        lines.append("## 专业技能 / Technical Skills")
        lines.append(f"- **核心技术栈**: {', '.join(skills)}\n")

    # 4. 核心项目经历
    if projects:
        lines.append("## 核心项目经历 / Key Projects")
        for proj in projects:
            p_name = proj.get("名称", "项目")
            p_role = proj.get("角色", "核心开发")
            lines.append(f"### {p_name} （{p_role}）")
            for bullet in proj.get("亮点", []):
                if bullet.strip():
                    lines.append(f"- {bullet.strip()}")
            lines.append("")

    # 5. 实习 / 工作经历
    if experiences:
        lines.append("## 实习与工作经历 / Experience")
        for exp in experiences:
            c_name = exp.get("公司", "公司")
            c_pos = exp.get("职位", "岗位")
            c_time = exp.get("时间", "")
            lines.append(f"### {c_name} — {c_pos} ({c_time})")
            for bullet in exp.get("亮点", []):
                if bullet.strip():
                    lines.append(f"- {bullet.strip()}")
            lines.append("")

    # 6. 教育背景
    if education and (education.get("学校") or basics.get("学校")):
        lines.append("## 教育背景 / Education")
        sch = education.get("学校") or basics.get("学校") or ""
        maj = education.get("专业") or basics.get("专业") or ""
        deg = education.get("学历") or basics.get("最高学历") or ""
        time_span = education.get("时间") or basics.get("毕业时间") or ""
        lines.append(f"- **{sch}** | {maj} | {deg} | {time_span}\n")

    # 7. 荣誉与资质
    campus_parts = []
    if campus.get("英语"):
        campus_parts.append(f"英语: {campus['英语']}")
    if campus.get("竞赛"):
        campus_parts.append(f"竞赛: {campus['竞赛']}")
    if campus.get("奖学金"):
        campus_parts.append(f"荣誉/奖学金: {campus['奖学金']}")
    if campus_parts:
        lines.append("## 荣誉资质 / Honors")
        for cp in campus_parts:
            lines.append(f"- {cp}")
        lines.append("")

    return "\n".join(lines)


def generate_application_package(
    job_info: Dict[str, Any], 
    profile: Optional[Dict[str, Any]] = None,
    mode: str = "A"
) -> Dict[str, Any]:
    """
    生成针对目标岗位的完整“投递包” (Application Package):
    1. 定制版简历 Markdown (A版保真 / B版进取对齐)
    2. HR破冰/打招呼开场白 (Cold Message，Boss/邮件直接可用)
    3. 岗位高频面试问题预测与应答建议 (Interview Prep)
    """
    if profile is None:
        profile = get_current_profile_data()

    resume = profile.get("resume", {})
    basics = resume.get("basics", {})
    skills = resume.get("skills", [])
    projects = resume.get("projects", [])
    
    company = job_info.get("company", "贵公司")
    title = job_info.get("title", "目标岗位")
    user_name = basics.get("姓名") or "候选人"
    user_identity = basics.get("身份") or "AI / 后端开发者"

    # 1. 生成 HR 打招呼开场白 (参考 auto-job-apply)
    core_skills_highlight = "、".join(skills[:5]) if skills else "Python、AI Agent 与分布式系统"
    
    cold_message = f"""您好！看到贵司正在招聘【{title}】，我的背景与该岗位的核心要求高度吻合，特向您自荐：

1. 【核心技术栈】：熟练掌握 {core_skills_highlight}，具备完整项目工程落地经验；
2. 【项目实战沉淀】：主导研发了自主 Issue-to-PR 编码智能体（已完成真实 GitHub 自动化闭环）与基于 OpenHarness 的本地求职 Agent 工作台；
3. 【工程与评测素养】：深入理解 Agent 规划（ReWOO/ReAct）、确定性安全防御栈与评测驱动开发（Eval-Driven）。

我的完整简历已为您附上，非常期待能与您进一步沟通交流！
祝好！
{user_name}"""

    # 2. 定制简历 (基于模式 A/B)
    tailored_markdown = generate_standard_markdown(profile)
    tailored_header = f"> **[针对性定制简历 - { 'A版·保真版' if mode == 'A' else 'B版·进取对齐版' }]** 目标岗位: {company} · {title}\n\n"
    tailored_markdown = tailored_header + tailored_markdown

    # 3. 面试高频预测与回答策略
    interview_prep = [
        {
            "question": f"谈谈你为什么对【{company}】的【{title}】岗位感兴趣？",
            "strategy": f"强调贵司在业务场景上的技术挑战，结合自身在 Agent 架构设计与本地模型工程化落地的经验，说明可以快速上手并产生业务价值。"
        },
        {
            "question": "你在项目中实现的 ReWOO 规划流相比传统 ReAct 有什么区别和优势？",
            "strategy": "从 Token 成本、模型在环往返次数（Round trips）、以及通过参数动态物化（Materialization）避免幻觉级联错误的角度展开，结合 MODEL_CARD 真实测试数据回答。"
        },
        {
            "question": "如何保证 Agent 工具调用时的安全性和防注入能力？",
            "strategy": "回答四层确定性安全防御栈：权限策略熔断（PermissionPolicy）、Canary 诱饵探针防越权、工具白名单与必须通过 exit=0 的验证门禁（Verify Gate）。"
        }
    ]

    return {
        "company": company,
        "title": title,
        "mode": mode,
        "cold_message": cold_message,
        "tailored_resume_markdown": tailored_markdown,
        "interview_prep": interview_prep
    }
