"""
将 job-agent 的画像数据自动导出并同步为 Reactive-Resume 官方标准格式。
用法:
    python scripts/sync_to_rxresume.py
"""

import json
import sys
import uuid
from pathlib import Path

JOB_AGENT_DIR = Path(__file__).resolve().parent.parent
RX_RESUME_DIR = JOB_AGENT_DIR.parent / "reactive-resume"
PROFILE_PATH = JOB_AGENT_DIR / "profile.json"


def uid() -> str:
    return str(uuid.uuid4())[:8]


def convert_profile_to_rxresume(profile: dict) -> dict:
    resume = profile.get("resume", {})
    basics = resume.get("basics", {})
    skills = resume.get("skills", [])
    experiences = resume.get("experiences", [])
    projects = resume.get("projects", [])
    campus = resume.get("campus", {})
    education = resume.get("education", {})
    summary = resume.get("summary_text", "")

    return {
        "basics": {
            "name": basics.get("姓名", ""),
            "headline": basics.get("求职类型") or basics.get("身份", ""),
            "email": basics.get("邮箱", ""),
            "phone": basics.get("电话", ""),
            "location": basics.get("所在地", ""),
            "url": {"label": "GitHub", "href": basics.get("GitHub", "")},
            "customFields": [],
            "picture": {
                "url": "",
                "size": 64,
                "aspectRatio": 1,
                "borderRadius": 0,
                "effects": {"hidden": True, "border": False, "grayscale": False},
            },
        },
        "sections": {
            "summary": {
                "name": "个人综述",
                "columns": 1,
                "separateLinks": True,
                "visible": True,
                "id": "summary",
                "content": f"<p>{summary}</p>" if summary else "",
            },
            "experience": {
                "name": "实习与工作经历",
                "columns": 1,
                "separateLinks": True,
                "visible": True,
                "id": "experience",
                "items": [
                    {
                        "id": uid(),
                        "visible": True,
                        "company": exp.get("公司", ""),
                        "position": exp.get("职位", ""),
                        "location": "",
                        "date": exp.get("时间", ""),
                        "summary": "".join(f"<p>• {b}</p>" for b in exp.get("亮点", []) if b.strip()),
                        "url": {"label": "", "href": ""},
                    }
                    for exp in experiences
                ],
            },
            "education": {
                "name": "教育背景",
                "columns": 1,
                "separateLinks": True,
                "visible": True,
                "id": "education",
                "items": [
                    {
                        "id": uid(),
                        "visible": True,
                        "institution": education.get("学校") or basics.get("学校", ""),
                        "studyType": education.get("学历") or basics.get("最高学历", ""),
                        "area": education.get("专业") or basics.get("专业", ""),
                        "score": "",
                        "date": education.get("时间") or basics.get("毕业时间", ""),
                        "summary": "",
                        "url": {"label": "", "href": ""},
                    }
                ] if (education.get("学校") or basics.get("学校")) else [],
            },
            "projects": {
                "name": "核心项目经历",
                "columns": 1,
                "separateLinks": True,
                "visible": True,
                "id": "projects",
                "items": [
                    {
                        "id": uid(),
                        "visible": True,
                        "name": proj.get("名称", ""),
                        "description": proj.get("角色", ""),
                        "date": proj.get("时间", ""),
                        "summary": "".join(f"<p>• {b}</p>" for b in proj.get("亮点", []) if b.strip()),
                        "keywords": [],
                        "url": {"label": "Repo", "href": proj.get("链接", "")},
                    }
                    for proj in projects
                ],
            },
            "skills": {
                "name": "专业技能",
                "columns": 2,
                "separateLinks": True,
                "visible": True,
                "id": "skills",
                "items": [
                    {
                        "id": uid(),
                        "visible": True,
                        "name": s,
                        "description": "",
                        "level": 4,
                        "keywords": [],
                    }
                    for s in skills
                ],
            },
            "awards": {
                "name": "荣誉与资质",
                "columns": 1,
                "separateLinks": True,
                "visible": True,
                "id": "awards",
                "items": [
                    {"id": uid(), "visible": True, "title": f"{k}: {v}", "awarder": "", "date": "", "summary": "", "url": {"label": "", "href": ""}}
                    for k, v in [("英语", campus.get("英语")), ("竞赛", campus.get("竞赛")), ("奖学金", campus.get("奖学金"))]
                    if v
                ],
            },
            "custom": {},
        },
        "metadata": {
            "template": "onyx",
            "layout": [[["summary", "projects", "experience", "education", "skills", "awards"], []]],
            "css": {"value": "", "visible": False},
            "page": {"margin": 14, "format": "a4", "options": {"breakLine": True, "pageNumbers": False}},
            "theme": {"background": "#ffffff", "text": "#0f172a", "primary": "#1e3a8a"},
            "typography": {
                "font": {"family": "Inter", "subset": "latin", "variants": ["regular", "bold"], "size": 13},
                "lineHeight": 1.45,
                "hideIcons": False,
                "underlineLinks": True,
            },
            "notes": "Generated by Job-Agent Workbench",
        },
    }


def main():
    if not PROFILE_PATH.exists():
        print(f"未找到 {PROFILE_PATH}，请先在 job-agent 中配置画像！")
        sys.exit(1)

    profile_data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    rx_json = convert_profile_to_rxresume(profile_data)

    # 1. 保存到 job-agent/data/
    out1 = JOB_AGENT_DIR / "data" / "rxresume-profile.json"
    out1.parent.mkdir(parents=True, exist_ok=True)
    out1.write_text(json.dumps(rx_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. 保存到 reactive-resume/data/
    if RX_RESUME_DIR.exists():
        out2_dir = RX_RESUME_DIR / "data"
        out2_dir.mkdir(parents=True, exist_ok=True)
        out2 = out2_dir / "profile-for-import.json"
        out2.write_text(json.dumps(rx_json, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] 已同步至 Reactive-Resume 目录: {out2}")

    print(f"[OK] 转换成功！生成 Reactive-Resume 标准文件: {out1}")
    print("\n[使用提示]")
    print("1. 如果你在本地启动了 Reactive-Resume (http://localhost:3000):")
    print("   登录后点击 'Import' -> 上传上述 JSON 文件，即可无缝加载你的全部经历与两个 Agent 项目！")
    print("2. 也可以随时在官方网页端 https://rxresu.me 直接导入该文件。")


if __name__ == "__main__":
    main()
