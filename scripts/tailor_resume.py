"""简历定制的 headless 入口:以 resume-tailor SKILL.md 为唯一工作流来源。

用法:
    python scripts/tailor_resume.py jd.txt
    echo "JD原文" | python scripts/tailor_resume.py -
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".openharness" / "skills" / "resume-tailor" / "SKILL.md"
OH = Path(r"D:/AI learning/OpenHarness-main/.venv/Scripts/oh.exe")


def load_workflow() -> str:
    text = SKILL.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        text = text[end + 4 :]
    return text.strip()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    jd = sys.stdin.read().strip() if sys.argv[1] == "-" else Path(sys.argv[1]).read_text(encoding="utf-8").strip()
    if not jd:
        print("JD 为空", file=sys.stderr)
        sys.exit(1)
    prompt = (
        f"{load_workflow()}\n\n---\n"
        "现在立即执行以上步骤,不要复述步骤、不要等待确认,你的下一轮输出必须是一次工具调用。\n"
        f"待定制 JD 原文:\n{jd}"
    )
    result = subprocess.run(
        [str(OH), "-p", prompt, "--permission-mode", "auto", "--max-turns", "25"],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
