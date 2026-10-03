"""JD 匹配的 headless 入口:以 SKILL.md 为唯一工作流来源,拼提示词调 oh。

绕开 print 模式下斜杠命令参数展开不稳定的上游问题;交互式仍可用 /jd-match。

用法:
    python scripts/match_jd.py jd.txt          # JD 文本文件
    echo "JD原文" | python scripts/match_jd.py -
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".openharness" / "skills" / "jd-match" / "SKILL.md"
OH = Path(r"D:/AI learning/OpenHarness-main/.venv/Scripts/oh.exe")


def load_workflow() -> str:
    text = SKILL.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        text = text[end + 4:]
    return text.strip()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "-":
        jd = sys.stdin.read().strip()
    else:
        jd = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
    if not jd:
        print("JD 为空", file=sys.stderr)
        sys.exit(1)

    prompt = (
        f"{load_workflow()}\n\n---\n"
        "现在立即执行以上步骤,不要复述步骤、不要等待确认,你的下一轮输出必须是一次工具调用。\n"
        f"待评估 JD 原文:\n{jd}"
    )
    result = subprocess.run(
        [str(OH), "-p", prompt, "--permission-mode", "auto", "--max-turns", "30"],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
