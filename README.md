# job-agent

个人求职 Agent:JD 语义匹配、简历定制、面试模拟复盘、职位监控推送,全部本地运行、零 API 成本。

基于 [OpenHarness](https://github.com/HKUDS/OpenHarness)(skills + MCP 扩展)构建:业务逻辑写成 skill 与 MCP 工具,与 harness 内核解耦。

## 30 秒看懂

| 问题 | 这个项目怎么答 |
|---|---|
| 有没有 RAG / 语义匹配? | profile 与 JD 分板块 embedding 召回 + 规则硬过滤 + rubric 精排的三段式匹配([matcher_engine.py](matcher_engine.py)) |
| 有没有评测? | 自建 12 条标注 JD 的评测集与三阶段评测脚本,抽取字段准确率 98%(样例画像口径) |
| 有没有成本意识? | 本地 4B 模型 + 每次匹配埋点,`scripts/cost_report.py` 一条命令出场景×模型成本报表 |
| 有没有工程交付? | FastAPI Web 工作台(画像编辑 / JD 匹配 / 简历上传 / 投递看板)+ 8 个 MCP 工具 + 3 个 skill + 晨报定时任务 |
| 边界在哪里? | 默认只做模拟投递,真实批量投递需二次确认且每日熔断;不爬 BOSS/拉勾,简历与数据库全本地 |

## 当前状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 环境终检(OpenHarness + 远端 Ollama + 64k 定制模型) | ✅ |
| P1 | 项目骨架(SQLite 6 表 + uv 依赖) | ✅ |
| P2 | JD 匹配闭环(三段式 + MCP 落库) | ✅ |
| P3 | 评测基线(抽取 98% / 技能覆盖 100%,样例画像) | ✅ 脚手架完成,**真实画像重标待做** |
| P4 | 自动化晨报推送 | ✅ 脚本与注册完成,**推送通道待配置** |
| P5 | 面试模拟官 + 复盘入库 | ✅ |
| P6 | 成本看板 + 简历定制 A/B | ✅ |
| P7 | 发布包装(README / 博客 / 脱敏开源) | 🚧 进行中 |

架构与数据设计见 [docs/plan.md](docs/plan.md),施工顺序与验收门见 [docs/roadmap.md](docs/roadmap.md),环境与命令见 [docs/setup.md](docs/setup.md),设计决策与踩坑记录见 [docs/README.md](docs/README.md)。

## 快速开始

```bash
uv sync                                  # 依赖已锁定在 uv.lock
copy .env.example .env                   # 填 LLM_BASE_URL / EMBED_BASE_URL(本地 Ollama 可不填 key)
uv run python scripts/init_db.py         # 建 6 张表(幂等)
uv run python scripts/seed_profile.py    # 写入简历画像(样例或自己的 profile.json)
```

**Web 工作台**(推荐):

```bat
start_web.bat
```

默认 http://127.0.0.1:8010。工作台提供画像可视化编辑、在线 JD 匹配工坊、简历原件上传、投递看板与 SMTP 自动投递。

**命令行**:

```bash
uv run python scripts/match_jd.py        # 单条 JD 三段式匹配
uv run python eval/run_eval.py all       # 跑评测并出 Markdown 报告
uv run python scripts/cost_report.py     # 成本报表
uv run python scripts/daily_brief.py     # 晨报(--register 注册 Windows 每日计划任务)
```

## 四个业务能力

| 能力 | 载体 | 说明 |
|---|---|---|
| JD 匹配 | skill [jd-match](.openharness/skills/jd-match/SKILL.md) + [matcher_engine.py](matcher_engine.py) | ① 规则硬过滤(城市/身份/年限,零 token)② 技能重合与语义召回 ③ rubric 加权打分 + 差距清单 + 突击建议 |
| 简历定制 | skill [resume-tailor](.openharness/skills/resume-tailor/SKILL.md) | A 保真版 / B 进取版双版本;B 版每处对齐强制标注画像依据(防造假设计) |
| 面试模拟 | skill [interview-coach](.openharness/skills/interview-coach/SKILL.md) | 计划生成 → 逐题追问与即时反馈 → 四维 rubric 复盘入库 |
| 公司简报 | 未实现(可选项) | 计划中的 `company-brief`,P7 可选项 |

数据访问统一走 [mcp-server/main.py](mcp-server/main.py)(8 个工具:`save_job` / `get_profile` / `semantic_score` / `save_match` / `track_application` / `log_cost` / `list_jobs` / `save_interview`),embedding 召回在服务端完成,模型输出按不可信输入处理。

## 评测数字(诚实口径)

最新报告:[eval/reports/report-20261003-1142-extract.md](eval/reports/report-20261003-1142-extract.md)

| 指标 | 值 | 口径说明 |
|---|---|---|
| 抽取字段准确率 | 98%(11.75/12 字段均值) | 12 条样例 JD,失败 1 例为标注口径分歧 |
| 技能平均覆盖 | 100% | 同上 |
| 单次耗时 / 成本 | 380s / ¥0 | 本地 4B 模型,局域网 Ollama |

> ⚠️ 以上为**样例画像**下的脚手架验证结果,**不能写进简历**。P3 待办:换成真实画像、收集 30-50 条真实 JD 逐条标注后重跑,目标字段准确率 >90%、Top-5 命中率 ≥80%。迭代闭环(58% → 87% → 98%,其中 2/12 是标注错误而非模型错误)记录在 [docs/roadmap.md](docs/roadmap.md)。

## 安全与合规

- **投递是不可逆副作用,所以默认最保守**:单岗位投递默认 `dry_run`;批量投递默认只预览,真实批量必须 `confirm=true`,且单次上限 5、每日真实投递上限 10(`JOB_AGENT_MAX_BATCH` / `JOB_AGENT_MAX_DAILY_SENDS` 可调),额度查询见 `GET /api/apply/quota`;
- **隐私**:简历画像、SQLite 库、上传的简历原件、SMTP 授权码全部在本地 `data/` 与 `profile.json`,已 gitignore,开源前无需清洗代码即可发布;
- **凭据**:优先用环境变量 `SMTP_USER` / `SMTP_PASS`;写进 `data/smtp_config.json` 时会尽量收紧为仅本人可读写,但仍是明文,请勿提交;
- **数据源合规**:只做手动粘贴、招聘邮件转发(IMAP)、RSS/官网招聘页;**明确不爬 BOSS/拉勾**(反爬红线,面试时主动讲这个取舍)。

## 目录结构

```text
job-agent/
  web_server.py          # FastAPI 工作台后端(画像 / 匹配 / 简历 / 投递 20 个路由)
  static/index.html      # 单页工作台前端
  auto_applier.py        # SMTP 投递引擎(含 dry-run / 批量确认 / 每日熔断)
  matcher_engine.py      # 三段式匹配与差距分析
  resume_parser.py       # PDF/DOCX 简历解析
  mcp-server/main.py     # 8 个 MCP 工具(数据库 + embedding)
  .openharness/          # 项目级 plugin(.mcp.json)与 3 个 skill
  scripts/               # 建库 / 画像 / 匹配 / 晨报 / 成本 / 简历同步
  eval/                  # 标注集 + 三阶段评测脚本 + 报告
  docs/                  # plan(架构) / roadmap(施工与验收门) / setup(环境) / 设计决策与踩坑
  data/                  # 本地数据库与产物(gitignored)
```

> `.mcp.json` 用相对路径 + `cwd: "."` 拉起 MCP 服务器(依赖 `uv` 在 PATH 上),换机器/换目录不用改配置——项目级 plugin 本就只在项目根目录被发现。

## 技术栈

OpenHarness v0.1.9(skills / MCP / hooks / headless)· 官方 `mcp` SDK 自建 8 工具 MCP Server · SQLite · FastAPI + uvicorn + Vue 3 单页工作台 · nomic-embed-text · qwen3.5-4b-agent(局域网 Ollama,零 API 成本)

## 已知限制

1. OpenHarness v0.1.9 不回传 token usage(`oh` 会话只能按调用次数记账),成本数字在 harness 暴露 usage 后一行切换;
2. 本地 4B 模型是质量天花板:工具调用偶发空消息、JSON 输出需两阶段解析兜底;
3. 评测集仍是样例数据,真实画像重标未完成(P3 待办);
4. 岗位来源目前依赖手动粘贴 / 邮件转发,自动抓取未接(合规取舍)。

## 与 issue-pr-agent 的关系

评测基座、MCP 骨架与可观测埋点是**搬代码而非重写**;两者共同构成作品集叙事:issue-pr-agent 是自研 harness(证明内核理解力),job-agent 是 OpenHarness 应用(证明工程交付力)。
