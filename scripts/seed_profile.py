"""把画像 JSON 写入 profile 表(按 name 覆盖)。

用法:
    python scripts/seed_profile.py assets/sample-profile.json
真实画像:复制样例为项目根的 profile.json(已被 gitignore)填入真实信息后执行
    python scripts/seed_profile.py profile.json
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from init_db import DEFAULT_DB, init_db  # noqa: E402


def seed(path: Path, db_path: Path = DEFAULT_DB) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO profile (name, resume_json, preferences) VALUES (?,?,?)",
            (
                data["name"],
                json.dumps(data["resume"], ensure_ascii=False),
                json.dumps(data.get("preferences", {}), ensure_ascii=False),
            ),
        )
    print(f"profile '{data['name']}' seeded from {path}")


if __name__ == "__main__":
    seed(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets/sample-profile.json"))
