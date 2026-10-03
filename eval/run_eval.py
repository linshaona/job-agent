"""P3 评测基线(组件级):抽取准确率 / 语义召回区分度 / 精排 Top-K 命中率。

对齐 job-agent 三段式设计:硬性过滤是纯规则(Python 实现,不测模型),
这里评测三个依赖模型的环节——抽取、召回、rubric 精排。

数据集 eval/jd_dataset.jsonl 每行一个用例:
    {"id": "...", "jd_raw": "...",
     "label": {"relevant": 1-5},                 # 人工标注:5=高度匹配 1=完全不匹配
     "gt": {"title": "...", "company": "...", "location": "...", "salary": "...",
            "experience_required": "...", "skills_required": [...]}}

用法:
    python eval/run_eval.py all|extract|recall|rubric [--profile student]

注意:样例画像 + 样例标注跑出的数字仅用于验证脚手架;
换真实画像、重新标注后重跑,才是可写进简历的基线。
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server"))

DATASET = Path(__file__).resolve().parent / "jd_dataset.jsonl"
REPORTS = Path(__file__).resolve().parent / "reports"


def load_env() -> dict:
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


ENV = load_env()
LLM_URL = ENV.get("LLM_BASE_URL", "http://10.102.170.214:11434/v1").rstrip("/")
LLM_KEY = ENV.get("LLM_API_KEY", "ollama")
LLM_MODEL = ENV.get("LLM_MODEL", "qwen3.5-4b-agent")
EMBED_URL = ENV.get("EMBED_BASE_URL", LLM_URL).rstrip("/")
EMBED_MODEL = ENV.get("EMBED_MODEL", "nomic-embed-text")


def load_dataset() -> list[dict]:
    cases = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def load_profile(name: str) -> dict:
    with sqlite3.connect(ROOT / "data" / "job.db") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT name, resume_json, preferences FROM profile WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            rows = conn.execute(
                "SELECT name, resume_json, preferences FROM profile"
            ).fetchall()
            row = rows[0] if len(rows) == 1 else None
    if row is None:
        sys.exit(f"profile '{name}' 不存在,先运行 scripts/seed_profile.py")
    return {
        "name": row["name"],
        "resume": json.loads(row["resume_json"]),
        "preferences": json.loads(row["preferences"] or "{}"),
    }


def chat(prompt: str, temperature: float = 0.2) -> str:
    resp = httpx.post(
        f"{LLM_URL}/chat/completions",
        headers={"Authorization": f"Bearer {LLM_KEY}"},
        json={
            "model": LLM_MODEL,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


def parse_json(text: str):
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").lstrip()
        t = t[t.find("\n") + 1 :] if "\n" in t else t
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if not starts:
        return None
    start = min(starts)
    end = max(t.rfind("}"), t.rfind("]"))
    if end <= start:
        return None
    try:
        return json.loads(t[start : end + 1])
    except json.JSONDecodeError:
        return None


def embed(texts: list[str]) -> list[list[float]]:
    resp = httpx.post(
        f"{EMBED_URL}/embeddings",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=120,
    )
    resp.raise_for_status()
    return [item["embedding"] for item in resp.json()["data"]]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _norm(s) -> str:
    # 去掉全部空白再比对,避免 "200-300 元/天" vs "200-300元/天" 这类假阴性
    return "".join(str(s or "").split()).lower()


def _field_hit(gt: str, pred: str) -> bool:
    g, p = _norm(gt), _norm(pred)
    return bool(g) and bool(p) and (g in p or p in g)


def _skill_coverage(gt: list, pred: list) -> float | None:
    if not gt:
        return None
    gset, pset = {_norm(x) for x in gt}, {_norm(x) for x in (pred or [])}
    hits = sum(1 for g in gset if any(g in p or p in g for p in pset))
    return hits / len(gset)


def hard_filter(preferences: dict, location: str | None) -> tuple[bool, str]:
    """与线上一致:硬性过滤是纯规则。脚手架先做城市规则,薪资规则留待真实画像定口径。"""
    expected = preferences.get("期望城市") or []
    if not expected:
        return True, "无城市偏好"
    loc = _norm(location)
    for city in expected:
        c = _norm(city)
        if c and (c in loc or loc in c):
            return True, f"城市命中:{city}"
    return False, f"城市不匹配(期望 {'/'.join(expected)})"


# ---------- 阶段 1:抽取 ----------

EXTRACT_PROMPT_HEAD = (
    "从下面的职位描述(JD)中抽取结构化字段,只输出 JSON,不要输出其他内容:\n"
    '{"title": "职位名", "company": "公司名", "location": "城市", "salary": "薪资原文",\n'
    ' "experience_required": "经验要求原文", "skills_required": ["技能", ...]}\n'
    "JD 中没有的信息填 null 或空数组,禁止编造。\n\nJD:\n"
)


def run_extract(cases: list[dict], lines: list[str], stamp: str = "") -> dict:
    lines.append("## 1. 抽取字段准确率\n")
    stats = {"title": 0, "company": 0, "location": 0, "salary": 0, "experience_required": 0}
    skill_covs, rows, n, preds = [], [], 0, []
    for c in cases:
        n += 1
        gt = c["gt"]
        try:
            pred = parse_json(chat(EXTRACT_PROMPT_HEAD + c["jd_raw"])) or {}
            preds.append({"id": c["id"], "pred": pred, "gt": gt})
        except Exception as exc:
            pred, err = {}, str(exc)[:60]
            rows.append(f"| {c['id']} | 调用失败:{err} | - |")
            continue
        per = {}
        for field in stats:
            ok = _field_hit(gt.get(field), pred.get(field))
            stats[field] += int(ok)
            per[field] = "√" if ok else "×"
        cov = _skill_coverage(gt.get("skills_required"), pred.get("skills_required"))
        if cov is not None:
            skill_covs.append(cov)
        rows.append(
            f"| {c['id']} | {' '.join(f'{k}:{v}' for k, v in per.items())} "
            f"| 技能覆盖 {cov:.0%} |"
        )
    lines.append("| 用例 | 字段判定 | 技能覆盖 |")
    lines.append("|---|---|---|")
    lines.extend(rows)
    lines.append("")
    lines.append("**字段准确率**: " + " / ".join(
        f"{k} {v}/{n}" for k, v in stats.items()
    ))
    acc = sum(stats.values()) / (len(stats) * n)
    mean_cov = sum(skill_covs) / len(skill_covs) if skill_covs else 0
    lines.append(f"\n**总字段准确率 {acc:.0%} · 技能平均覆盖 {mean_cov:.0%}**(目标:字段 >90%)\n")
    if stamp:
        (REPORTS / f"predictions-{stamp}-extract.jsonl").write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in preds), encoding="utf-8"
        )
    return {"field_acc": acc, "skill_cov": mean_cov}


# ---------- 阶段 2:召回 ----------

def run_recall(cases: list[dict], profile: dict, lines: list[str]) -> dict:
    lines.append("## 2. 语义召回区分度\n")
    from main import _resume_text
    pvec = embed([_resume_text(profile["resume"])])[0]
    rows, scores = [], []
    for c in cases:
        v = embed([c["jd_raw"]])[0]
        s = round(cosine(pvec, v) * 100, 1)
        scores.append((c["id"], c["label"]["relevant"], s))
        rows.append((s, c))
    pos = [s for _, rel, s in scores if rel >= 3]
    neg = [s for _, rel, s in scores if rel <= 2]
    rows.sort(key=lambda x: -x[0])
    lines.append("| 排名 | 用例 | 标注相关度 | 语义分 |")
    lines.append("|---|---|---|---|")
    lines.extend(f"| {i+1} | {c['id']} | {c['label']['relevant']} | {s} |" for i, (s, c) in enumerate(rows))
    thr = (sum(pos) / len(pos) + sum(neg) / len(neg)) / 2 if pos and neg else 0
    correct = sum(1 for _, rel, s in scores if (s >= thr) == (rel >= 3))
    lines.append(
        f"\n**相关(≥3)均值 {sum(pos)/len(pos):.1f} · 不相关(≤2)均值 {sum(neg)/len(neg):.1f}"
        f" · 区分间隔 {sum(pos)/len(pos) - sum(neg)/len(neg):.1f}**\n"
        f"建议阈值 {thr:.1f},二分类准确率 {correct}/{len(scores)}\n"
    )
    return {"pos_mean": sum(pos) / len(pos) if pos else 0,
            "neg_mean": sum(neg) / len(neg) if neg else 0,
            "threshold": round(thr, 1)}


# ---------- 阶段 3:精排 ----------

RUBRIC_PROMPT_HEAD = (
    "你是招聘评估助手。根据候选人画像与 JD,输出 JSON 打分(整数 1-5):\n"
    '{"技能重叠": n, "业务相关性": n, "成长性": n}\n'
    "技能重叠=JD 技能与候选人技能/项目重合度;业务相关性=JD 业务与候选人目标岗位吻合度;"
    "成长性=岗位对候选人的成长价值。只输出 JSON。\n\n候选人画像:\n"
)


def run_rubric(cases: list[dict], profile: dict, lines: list[str]) -> dict:
    lines.append("## 3. 精排与 Top-5 命中率\n")
    from main import _resume_text
    profile_text = _resume_text(profile["resume"])
    finals = []
    for c in cases:
        try:
            dims = parse_json(chat(RUBRIC_PROMPT_HEAD + profile_text + "\n\nJD:\n" + c["jd_raw"])) or {}
        except Exception:
            dims = {}
        d = {k: int(dims.get(k) or 3) for k in ("技能重叠", "业务相关性", "成长性")}
        semantic = None
        try:
            v = embed([c["jd_raw"]])[0]
            pvec = embed([profile_text])[0]
            semantic = round(cosine(pvec, v) * 100, 1)
        except Exception:
            pass
        ok, reason = hard_filter(profile["preferences"], c["gt"].get("location"))
        final = 0 if not ok else round(
            (semantic or 0) * 0.3 + sum(d.values()) / 15 * 70
        )
        finals.append((final, c, semantic, d, ok, reason))
    finals.sort(key=lambda x: -x[0])
    lines.append("| 排名 | 用例 | 标注 | 硬过滤 | 语义分 | 三维度 | 总分 |")
    lines.append("|---|---|---|---|---|---|---|")
    lines.extend(
        f"| {i+1} | {c['id']} | {c['label']['relevant']} | {'过' if ok else '拦:'+reason} "
        f"| {semantic} | {d['技能重叠']}/{d['业务相关性']}/{d['成长性']} | {final} |"
        for i, (final, c, semantic, d, ok, reason) in enumerate(finals)
    )
    top5 = [c for final, c, *_ in finals[:5]]
    p5 = sum(1 for c in top5 if c["label"]["relevant"] >= 3) / min(5, len(top5))
    lines.append(f"\n**Top-5 命中率 {p5:.0%}**(目标 ≥80%)\n")
    return {"top5": p5}


# ---------- 主流程 ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["all", "extract", "recall", "rubric"], nargs="?", default="all")
    ap.add_argument("--profile", default="student")
    args = ap.parse_args()

    cases = load_dataset()
    profile = load_profile(args.profile)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    lines = [
        f"# 评测报告 {stamp}",
        f"- 画像:{profile['name']}(注意:样例画像的结果仅验证脚手架,不可写进简历)",
        f"- 模型:{LLM_MODEL} @ {LLM_URL}",
        f"- 数据集:{DATASET.name}({len(cases)} 条)\n",
    ]
    t0 = time.time()
    if args.stage in ("all", "extract"):
        run_extract(cases, lines, stamp)
    if args.stage in ("all", "recall"):
        run_recall(cases, profile, lines)
    if args.stage in ("all", "rubric"):
        run_rubric(cases, profile, lines)
    lines.append(f"\n---\n耗时 {time.time()-t0:.0f}s · 本地模型,成本 ¥0")
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"report-{stamp}-{args.stage}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
