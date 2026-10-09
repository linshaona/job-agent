# 求职 Agent 搭建指南(从零到跑通)

> 配套 `plan.md`(架构与里程碑)。本文回答"具体怎么装、每一步怎么验证"。
> 所有命令均核对过 OpenHarness 官方 README(2026-10 版)。

## 搭建路径总览(6 层,自底向上)

```
① Python 环境 → ② 安装 OpenHarness → ③ 配模型 provider
→ ④ 项目仓库(SQLite + skills)→ ⑤ MCP 数据工具 → ⑥ ohmo 网关 + 定时任务
```

每一层都有独立的验证点,上一层没绿不进下一层。

---

## ⓪ 本机已就绪盘点(2026-10-03 实测核对)

- ✅ **Ollama 已装**,模型已 pull:`qwen3.5:4B`(3.4GB)、`qwen3.5-4b-64k`(**issue-pr-agent 时期做的定制版:num_ctx=65536,Q4_K_M,支持 tools 调用**)、`nomic-embed-text`
- ✅ **OpenHarness 已配置过**:`~/.openharness/settings.json` 里 12 个 provider profile 全部初始化(qwen/moonshot/openrouter/gemini 等);当前指向 glm-4.5-flash @ bigmodel.cn
- ✅ **OpenHarness-main 源码 checkout**(v0.1.9 zip 快照 + uv venv)实测可跑,`oh.exe`/`ohmo.exe` 在 `.venv/Scripts/` 下
- ✅ **issue-pr-agent 项目**:切片 0-4 完成,自研 agent loop / 工具注册+Schema / RAG / **评测基座**(Scorer + 失败标注 + run 导出)/ MCP server/client / 权限与注入防御
- ⬜ 待做:注册 Ollama provider profile、job-agent 仓库与 SQLite、`.mcp.json`、50 条标注集、ohmo 网关(第二周)

## ① 前置环境(Windows)

- Python 3.11+,`python --version` 确认
- Git(Git Bash 你已有)
- Node.js 仅在你想改终端 UI 时才需要,**可后置**

**Windows 注意**:OpenHarness 原生支持 Windows,但 PowerShell 里必须用 `openh` 命令(`oh` 会撞上内置 `Out-Host` 别名);**Git Bash 里 `oh` 正常**。建议:安装和日常都在 Git Bash 里做,少踩一半的坑。遇到 Windows 特有的诡异问题(仓库 issue 里确实有 Windows 平台测试失败的记录),备用方案是切 WSL。

## ② 运行 OpenHarness(已定:直接用 OpenHarness-main 源码 checkout)

**已实测跑通**(2026-10-03):`OpenHarness-main` 是 v0.1.9 的 zip 快照,自带 uv 管理的 `.venv`(Python 3.14),`.venv/Scripts/oh.exe` 可直接调用,`~/.openharness` 全局配置通用,零重装。

Git Bash 里加个 alias 就能全局使用(`~/.bashrc`):

```bash
alias oh='"<OpenHarness 目录>/.venv/Scripts/oh.exe"'
alias ohmo='"<OpenHarness 目录>/.venv/Scripts/ohmo.exe"'
```

两个注意点:

1. **别移动/重命名 `OpenHarness-main` 目录**,alias 和 venv 的绝对路径会断;
2. **这是 0.1.9 固定快照**(非 git 仓库,不能 pull)。上游迭代很快,但我们的架构只走 skills + MCP、与 harness 内核解耦,要升级时重新下载 zip 换目录、alias 改一行即可。README 里记一下用的版本号即可——锁定版本是正常工程做法。

顺带的好处:你本来就在读这份源码(读码路线),运行时和研究对象同源,调试时可以直接断进去。

验证:

```bash
oh --version   # openharness 0.1.9
oh --help
```

> Day 1 需验证的一件事:在 `job-agent` 目录里跑 `oh`,`/skills` 应能发现项目级 skill(发现逻辑基于当前目录,与 harness 安装位置无关,理论上没问题,实测确认)。

## ③ 配模型 provider(已定:本地 Ollama + qwen3.5:4B)

开发期固定本地模型,评测说不达标再切云——provider profile 机制让切换只是一条命令。

**模型机(RTX 3060 12G)上:无需新操作。**

模型全部就绪,直接用 **`qwen3.5-4b-64k`**(issue-pr-agent 时期的 Modelfile-64k 定制版:num_ctx=65536,Q4_K_M 量化,**官方支持 tools 调用**)——比我原先建议的 16k 更宽裕,长 JD 完全无压力。`nomic-embed-text` 也已就位,embedding 走它。

**开发机(这台)上注册 provider:**

```bash
# 同机用 http://localhost:11434/v1;异机用 http://<模型机局域网IP>:11434/v1
oh provider add ollama \
  --label "Ollama-4B" \
  --provider Ollama \
  --api-format openai \
  --auth-source openai_api_key \
  --model qwen3.5-4b-64k \
  --base-url http://localhost:11434/v1
oh provider use ollama
```

**云端 API = 质量备胎(评测不达标时一键切换)**:`oh setup` 选 OpenAI-Compatible,填 DeepSeek / DashScope / GLM / Kimi 任一的 key;`oh provider list` 查看全部 profile、`oh provider use` 秒切。这就是架构上的降级阶梯,也是面试素材:本地开发零成本,评测数据告诉你什么时候才值得花钱上大模型。

**embedding 同机解决**:三段式匹配的向量召回不走 OpenHarness,由 MCP server 直接调 Ollama 的 embedding 接口(`nomic-embed-text`),与 4B 共存在同一张卡上。

**4B 的已知短板**:严格 JSON 输出可靠性偏低——按 plan 里的两阶段解析(规则预抽取 + LLM 校正)兜底,失败样本进评测集。这个约束场景正是评测体系发挥价值的地方。

**不花钱的验证三板斧**:

```bash
oh --dry-run                          # readiness=ready 才继续;它会检查 auth/skills/MCP 配置
oh -p "1+1=? 只回答数字" --output-format json   # 真实冒烟,几分钱
```

代理坑:web_search/web_fetch **不继承系统代理**,需要时显式 `export OPENHARNESS_WEB_PROXY=http://127.0.0.1:7890`。

## ④ 项目仓库 + 数据库

```bash
mkdir job-agent && cd job-agent && git init
```

按 plan 里的仓库结构建目录;先写 `.gitignore`(**在写任何代码之前**,隐私红线):

```
*.db
*.sqlite3
.env
profile*.json
jd_cache/
eval/labeled/*.jsonl     # 标注集脱敏后才开源
```

然后 `scripts/init_db.py`:用标准库 sqlite3 建 plan 里的 6 张表(jobs / profile / matches / applications / cost_log / interview_sessions)。依赖管理用 `uv`(锁在 `uv.lock`),只装官方 `mcp` SDK 与 `httpx` 等必要依赖,刻意保持轻。

## ⑤ 挂载扩展(核心步骤,按依赖顺序)

OpenHarness 有 4 种扩展方式,**我们只用前两种**,这是架构决策不是偷懒——MCP 保持进程解耦,面试好讲:

### 5.1 Skills(零代码,先做)

项目级目录会被自动加载(当前目录向上找到 git root):

```
job-agent/.openharness/skills/jd-match/SKILL.md
```

SKILL.md = YAML frontmatter(name/description)+ 工作流步骤 + 输出 JSON Schema。先只写 `jd-match` 一个。

验证:

```bash
oh                     # 进交互,输入 /skills,应列出 jd-match 及其路径
oh --dry-run -p "/jd-match 测试"   # dry-run 会解析 slash command 路径
```

### 5.2 MCP server(求职数据工具)

`mcp-server/main.py` 用官方 `mcp` SDK 的 `MCPServer` 暴露工具(最终 8 个:`save_job` / `list_jobs` / `get_profile` / `semantic_score` / `save_match` / `track_application` / `log_cost` / `save_interview`),内部连 SQLite + embedding API。

注册:项目根放 Claude 风格 `.mcp.json`(`mcpServers` 字段,指向 `python mcp-server/main.py`);子命令 `oh mcp --help` 可查管理命令。

验证:`oh --dry-run` 会显式报告 MCP 配置错误——**dry-run 通过 = server 能被正确拉起**,这是我们免费用的一等公民检查。

### 5.3 Plugin(第二周再说)

需要自定义 slash command、hooks、子 agent 时才上:`.openharness/plugins/job-agent/.claude-plugin/plugin.json` + `commands/*.md` + `hooks/hooks.json`,兼容 claude-code 插件格式,官方 12 个插件实测可用。

### 5.4 内置自定义工具(不做)

继承 `BaseTool` 写 Python 类、改 harness 源码的方式,只在 fork OpenHarness 时用。我们保持"上游可升级"。

## ⑥ ohmo 网关 + 定时任务

**网关(MVP 可跳过,第二周加分项)**:

```bash
ohmo init            # 初始化 ~/.ohmo 工作区
ohmo config          # 选 provider profile + 配频道(Telegram 最简单;飞书国内最顺,建企业自建应用)
ohmo gateway start
ohmo gateway status
```

跑通前,所有交互直接在 Git Bash 里 `oh` 就够了,别让网关阻塞主线。

**定时晨报(推荐系统级,不依赖 agent 常驻)**:Windows 任务计划程序(`schtasks`)跑一个脚本,内容是:

```bash
oh -p "拉取过去24h新职位,按匹配分排序,生成晨报" --output-format text
```

输出接飞书/Telegram webhook 推送。harness 内的 cron 工具适合会话内临时任务,长驻用系统调度更稳。

---

## 端到端验收清单(D3 目标,全绿即闭环)

1. `oh provider list` → 当前 profile `[ready]`
2. `oh --dry-run` → `ready`
3. `/skills` → 能看到 `jd-match`
4. 粘贴一份真实 JD → 返回结构化 JSON 且 `jobs` 表多了 1 行
5. 返回匹配分 + 差距清单,`matches` 表有记录、`cost_log` 有金额
6. `sqlite3 job.db "select count(*) from jobs"` → 大于 0

## 已知坑(来自官方 issue 区 + 2026-10-03 实战,提前防)

- PowerShell 里 `oh` 失效 → 用 `openh`(Git Bash 无此问题)
- **OpenHarness v0.1.9 MCP 客户端与 mcp 2.x 不兼容**(`Tool.inputSchema` 属性改名,工具发现静默失败)→ 已在 OpenHarness venv 内 `uv pip install "mcp<2"`(1.30.0)修复;自建 server 也别用 fastmcp 4.x,用官方 SDK 的 `mcp.server.mcpserver.MCPServer`
- **Git Bash 会把 `/命令` 开头的参数转成 Windows 路径**(`/jd-match` → `D:/Git/jd-match`)→ headless 调用加 `MSYS_NO_PATHCONV=1`;交互会话内不受影响
- print 模式下斜杠命令参数展开不可靠 → 用 `scripts/match_jd.py` 作 headless 入口
- 4B 模型工具调用偶发空消息、公式执行偏差 → 用 agent 调优采样参数(远端 `qwen3.5-4b-agent`:temp 0.6 / presence 0.5);残余问题靠评测集量化
- skills 不执行的 issue 有人报过 → 升级版本,检查 frontmatter 格式
- API key 全局环境变量会互相污染 → 一律用 provider profile 绑定 key(本项目的占位 key 存在 `profile:ollama` 槽位)
