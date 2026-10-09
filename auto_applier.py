"""
自动求职投递引擎 (Auto Job Applier & Delivery Engine)
支持核心模式:
1. SMTP 邮件自动投递:
   - 自动挂载 data/uploads/ 中已上传的简历原件 (PDF/DOCX)
   - 自动生成针对岗位的标准化求职信与主题
   - 支持主流邮箱 (QQ, 163, Gmail, Outlook, 企业邮箱)
   - 支持 Dry-Run (试跑预览) 与真实投递
2. 平台专属打招呼话术直投 (Boss/猎聘/脉脉 Cold Message)
3. 状态闭环: 自动将岗位流转至看板的 'applied' (已投递) 状态并落盘投递日志

安全边界(投递不可逆,所以默认最保守):
- 默认 dry_run 模拟,只有显式 dry_run=False 才真正发信;
- 真实批量投递必须再显式 confirm=True;
- 单次批量上限 MAX_BATCH_PER_RUN(默认 5),每日真实投递上限 MAX_REAL_SENDS_PER_DAY(默认 10),
  可用环境变量 JOB_AGENT_MAX_BATCH / JOB_AGENT_MAX_DAILY_SENDS 覆盖。
"""

import json
import os
import re
import smtplib
import sqlite3
from datetime import datetime
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from resume_parser import get_attachment_meta

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SMTP_CONFIG_PATH = DATA_DIR / "smtp_config.json"
PROFILE_PATH = BASE_DIR / "profile.json"
DB_PATH = DATA_DIR / "job.db"


def _env_int(name: str, default: int) -> int:
    """读取正整数环境变量,非法值回退默认"""
    try:
        value = int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# ---- 安全边界(可用环境变量覆盖) ----
# 投递是不可逆的外部副作用:默认只做模拟;批量需要显式确认;每日有熔断上限。
MAX_BATCH_PER_RUN = _env_int("JOB_AGENT_MAX_BATCH", 5)
MAX_REAL_SENDS_PER_DAY = _env_int("JOB_AGENT_MAX_DAILY_SENDS", 10)


def sent_today() -> int:
    """今日已标记为已投递的岗位数(按本地日期统计),用于每日熔断"""
    if not DB_PATH.exists():
        return 0
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM applications "
            "WHERE status = 'applied' AND date(applied_at) = date('now', 'localtime')"
        ).fetchone()
    return int(row[0] or 0) if row else 0


def load_profile() -> Dict[str, Any]:
    """读取当前 profile.json"""
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"name": "default", "resume": {}, "preferences": {}}


def get_smtp_config(mask_password: bool = True) -> Dict[str, Any]:
    """读取 SMTP 投递邮箱配置"""
    config = {
        "smtp_host": "smtp.163.com",
        "smtp_port": 465,
        "smtp_user": "",
        "smtp_pass": "",
        "sender_name": "",
        "is_ssl": True,
        "configured": False,
    }

    if SMTP_CONFIG_PATH.exists():
        try:
            saved = json.loads(SMTP_CONFIG_PATH.read_text(encoding="utf-8"))
            config.update(saved)
            if config.get("smtp_user") and config.get("smtp_pass"):
                config["configured"] = True
        except Exception:
            pass

    # 兜底从环境变量读取
    if not config["configured"]:
        env_user = os.environ.get("SMTP_USER", "")
        env_pass = os.environ.get("SMTP_PASS", "")
        if env_user and env_pass:
            config["smtp_user"] = env_user
            config["smtp_pass"] = env_pass
            config["smtp_host"] = os.environ.get("SMTP_HOST", "smtp.163.com")
            config["smtp_port"] = int(os.environ.get("SMTP_PORT", 465))
            config["configured"] = True

    res = dict(config)
    if mask_password and res.get("smtp_pass"):
        res["smtp_pass"] = "******"
    return res


def save_smtp_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """保存 SMTP 配置"""
    existing = {}
    if SMTP_CONFIG_PATH.exists():
        try:
            existing = json.loads(SMTP_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 如果密码传的是 ****** 则保留原密码
    pass_val = data.get("smtp_pass", "").strip()
    if pass_val == "******" or not pass_val:
        pass_val = existing.get("smtp_pass", "")

    new_cfg = {
        "smtp_host": data.get("smtp_host", "smtp.163.com").strip(),
        "smtp_port": int(data.get("smtp_port", 465)),
        "smtp_user": data.get("smtp_user", "").strip(),
        "smtp_pass": pass_val,
        "sender_name": data.get("sender_name", "").strip(),
        "is_ssl": bool(data.get("is_ssl", True)),
    }

    SMTP_CONFIG_PATH.write_text(json.dumps(new_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    # 授权码是明文落盘(该文件已 gitignore);尽量收紧为仅本人可读写。
    # 更稳的做法是把授权码放环境变量 SMTP_USER/SMTP_PASS,这里只作兜底。
    try:
        os.chmod(SMTP_CONFIG_PATH, 0o600)
    except OSError:
        pass
    return {"status": "success", "message": "SMTP 投递邮箱配置已成功保存！"}


def extract_email_from_jd(jd_text: str) -> Optional[str]:
    """从 JD 文本中自动识别 HR / 招聘邮箱"""
    match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", jd_text)
    if match:
        email = match.group(1).lower()
        # 排除常见非招聘邮箱后缀
        if not any(d in email for d in ["example.com", "w3.org", "sentry.io"]):
            return email
    return None


def generate_email_content(job: Dict[str, Any], profile: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """
    针对目标岗位自动生成标准化邮件标题与求职自荐正文
    """
    if profile is None:
        profile = load_profile()

    resume = profile.get("resume", {})
    basics = resume.get("basics", {})
    skills = resume.get("skills", [])
    candidate_name = basics.get("姓名") or "候选人"
    school = basics.get("学校") or ""
    degree = basics.get("学历") or "本科"
    identity = basics.get("身份") or "在校生"

    company = job.get("company") or "贵司"
    title = job.get("title") or "目标岗位"

    # 1. 规范化邮件主题 (大厂 HR 偏好格式)
    tag_part = f"{school}{degree}" if school else identity
    subject = f"【求职应聘-{title}】{candidate_name}-{tag_part}-附个人简历"

    # 2. 邮件正文
    core_skills_highlight = "、".join(skills[:5]) if skills else "Unity、C#、C++、URP、Shader Graph"
    projects = resume.get("projects", [])
    proj_lines = []
    for p in projects[:2]:
        p_name = p.get("名称", "")
        p_highlights = p.get("亮点", [])
        hl = p_highlights[0] if p_highlights else "负责核心模块研发"
        proj_lines.append(f"• 【{p_name}】：{hl}")
    proj_section = "\n".join(proj_lines) if proj_lines else "• 【项目实践】：具备独立完成游戏玩法设计与全流程落地的实战经验"
    
    body = f"""尊敬的 {company} 招聘负责人 / HR 您好：

我非常关注贵司在游戏与软件研发领域的前沿技术与产品，在招聘平台上看到贵司正在招聘【{title}】岗位，我的专业技术栈（{core_skills_highlight}）与该岗位的核心要求高度契合，特此向您自荐！

一、关于我与核心要求匹配：
1. 【技术栈基础】：掌握 {core_skills_highlight}，具备良好的软件工程素养、代码规范与数据结构算法基础；
2. 【实战项目落地】：
{proj_section}
3. 【工程效率与成长】：熟练运用 Git 版本管理，并善于利用 Claude Code / Cursor 等 AI Agent 辅助编程工具高效攻关，学习能力强，渴望在实战环境中为团队贡献价值。

二、简历附件与联系方式：
我的完整个人简历已随信附上（详见附件），期待能有机会进一步与您沟通交流。
电话：{basics.get('电话', '见附件简历')}
邮箱：{basics.get('邮箱', '见发信地址')}
GitHub：{basics.get('GitHub', '见附件简历')}

非常感谢您在百忙之中查阅我的来信，祝工作顺利，贵司事业蒸蒸日上！

此致
敬礼！

{candidate_name}
{datetime.now().strftime('%Y年%m月%d日')}
"""
    return subject, body


def deliver_job_application(
    job_id: int,
    recipient_email: Optional[str] = None,
    mode: str = "email",  # 'email' 或 'platform'
    dry_run: bool = True  # 默认模拟:真实投递必须由调用方显式要求
) -> Dict[str, Any]:
    """
    执行单个岗位自动投递流水线
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job_row:
            raise ValueError(f"未找到 ID 为 {job_id} 的岗位")
        job = dict(job_row)

    profile = load_profile()
    basics = profile.get("resume", {}).get("basics", {})
    candidate_name = basics.get("姓名") or "候选人"

    # 1. 确定收件邮箱
    target_email = recipient_email or extract_email_from_jd(job.get("jd_raw") or "")

    # 2. 生成邮件内容
    subject, body = generate_email_content(job, profile)

    # 3. 检查是否有附件原件
    attachment_meta = get_attachment_meta()
    has_attachment = False
    attachment_path = None
    attachment_filename = None

    if attachment_meta and attachment_meta.get("file_path"):
        p = Path(attachment_meta["file_path"])
        if p.exists():
            has_attachment = True
            attachment_path = p
            attachment_filename = attachment_meta.get("filename", p.name)

    # 4. 执行投递逻辑
    delivery_log = ""
    success = True

    if mode == "email":
        if not target_email:
            raise ValueError("该岗位 JD 中未检测到 HR 招聘邮箱，请手动输入收件邮箱或选择平台打招呼模式")

        smtp_cfg = get_smtp_config(mask_password=False)
        if not dry_run and not smtp_cfg.get("configured"):
            raise ValueError("尚未配置发件邮箱！请先在【设置】中配置发件 SMTP 邮箱和授权码")

        if dry_run:
            delivery_log = f"[模拟测试] 成功生成投递邮件至 {target_email}，挂载附件: {attachment_filename or '无'}"
        else:
            # 每日熔断:邮件一旦发出无法撤回,先核对今日配额
            already_sent = sent_today()
            if already_sent >= MAX_REAL_SENDS_PER_DAY:
                raise ValueError(
                    f"已达每日真实投递上限({MAX_REAL_SENDS_PER_DAY} 封,今日已投 {already_sent} 封),"
                    "请明天再投,或先用模拟测试预览"
                )
            # 真实通过 SMTP 发送邮件
            try:
                msg = MIMEMultipart()
                sender_display = smtp_cfg.get("sender_name") or candidate_name
                msg["From"] = f"{Header(sender_display, 'utf-8').encode()} <{smtp_cfg['smtp_user']}>"
                msg["To"] = target_email
                msg["Subject"] = Header(subject, "utf-8").encode()
                msg.attach(MIMEText(body, "plain", "utf-8"))

                # 挂载简历附件
                if has_attachment and attachment_path:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment_path.read_bytes())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename=\"{Header(attachment_filename, 'utf-8').encode()}\""
                    )
                    msg.attach(part)

                # 连接 SMTP
                host = smtp_cfg["smtp_host"]
                port = smtp_cfg["smtp_port"]
                if smtp_cfg.get("is_ssl", True):
                    server = smtplib.SMTP_SSL(host, port, timeout=20)
                else:
                    server = smtplib.SMTP(host, port, timeout=20)
                    server.starttls()

                server.login(smtp_cfg["smtp_user"], smtp_cfg["smtp_pass"])
                server.sendmail(smtp_cfg["smtp_user"], [target_email], msg.as_string())
                server.quit()

                delivery_log = f"已通过 SMTP 发送至 {target_email}，附件: {attachment_filename or '无'}"
            except Exception as e:
                success = False
                delivery_log = f"邮件发送失败: {str(e)}"
                raise RuntimeError(delivery_log)

    elif mode == "platform":
        # 平台直投模式
        delivery_log = f"已生成针对 {job.get('company')} 的平台直投推荐信"

    # 5. 更新 SQLite 数据库中的 applications 表 (仅真实投递或平台打招呼确认时标记为 applied)
    if success and not dry_run:
        with sqlite3.connect(DB_PATH) as conn:
            existing = conn.execute("SELECT id FROM applications WHERE job_id = ?", (job_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE applications SET
                        status = 'applied',
                        applied_at = datetime('now', 'localtime'),
                        next_action = '等待HR回复/跟进',
                        notes = ?
                    WHERE job_id = ?
                    """,
                    (delivery_log, job_id)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO applications (job_id, status, applied_at, next_action, notes)
                    VALUES (?, 'applied', datetime('now', 'localtime'), '等待HR回复/跟进', ?)
                    """,
                    (job_id, delivery_log)
                )
            conn.commit()

    return {
        "status": "success",
        "job_id": job_id,
        "company": job.get("company"),
        "title": job.get("title"),
        "mode": mode,
        "dry_run": dry_run,
        "recipient_email": target_email,
        "subject": subject,
        "body": body,
        "has_attachment": has_attachment,
        "attachment_name": attachment_filename,
        "log": delivery_log,
        "applied_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def batch_deliver_pending_applications(
    dry_run: bool = True,
    limit: Optional[int] = None,
    confirm: bool = False,
) -> Dict[str, Any]:
    """
    批量自动投递所有待投递 (pending) 的岗位

    安全边界:
    - dry_run 默认 True:默认只预览收件人与正文,不发送;
    - 真实批量投递必须显式 confirm=True,否则拒绝——批量误发无法撤回;
    - 单次最多 MAX_BATCH_PER_RUN 个,并受每日真实投递上限约束。
    """
    if not dry_run and not confirm:
        raise ValueError(
            "真实批量投递需要 confirm=true 显式确认(邮件发出后无法撤回);"
            "建议先执行 dry_run 预览收件人与正文"
        )

    quota_remaining = max(MAX_REAL_SENDS_PER_DAY - sent_today(), 0)
    requested = MAX_BATCH_PER_RUN if limit is None else int(limit)
    effective_limit = max(1, min(requested, MAX_BATCH_PER_RUN))
    if not dry_run:
        effective_limit = min(effective_limit, quota_remaining)
        if effective_limit <= 0:
            raise ValueError(
                f"今日真实投递配额已用尽({MAX_REAL_SENDS_PER_DAY} 封),请明天再投或用 dry_run 预览"
            )

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        total_pending = int(
            conn.execute("SELECT COUNT(*) FROM applications WHERE status = 'pending'").fetchone()[0] or 0
        )
        rows = conn.execute(
            """
            SELECT a.job_id, j.company, j.title, j.jd_raw
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            WHERE a.status = 'pending'
            ORDER BY a.id
            LIMIT ?
            """,
            (effective_limit,),
        ).fetchall()

    results = []
    skipped = []

    for r in rows:
        job_id = r["job_id"]
        email = extract_email_from_jd(r["jd_raw"] or "")
        if email:
            try:
                res = deliver_job_application(job_id, recipient_email=email, mode="email", dry_run=dry_run)
                results.append(res)
            except Exception as e:
                skipped.append({"job_id": job_id, "company": r["company"], "reason": str(e)})
        else:
            skipped.append({"job_id": job_id, "company": r["company"], "reason": "JD 中无邮箱"})

    return {
        "total_pending": total_pending,
        "processed_count": len(rows),
        "delivered_count": len(results),
        "skipped_count": len(skipped),
        "delivered": results,
        "skipped": skipped,
        "dry_run": dry_run,
        "confirm": confirm,
        "limit_applied": effective_limit,
        "daily_quota": {"limit": MAX_REAL_SENDS_PER_DAY, "remaining": quota_remaining},
    }
