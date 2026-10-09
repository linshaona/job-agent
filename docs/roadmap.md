# 求职 Agent 完整构建路线

> 三份文档分工:`plan.md`=架构与数据设计;`setup.md`=环境与命令;**本文=施工顺序与验收门**。
> 环境前提(已实测就绪):OpenHarness-main v0.1.9(oh.exe)、Ollama + `qwen3.5-4b-64k` + `nomic-embed-text`、issue-pr-agent 可复用资产。
> 标注 ★ 的阶段产出简历数字。

## 总览

| 阶段 | 内容 | 工期 | 验收门 |
|---|---|---|---|
| P0 | 环境终检 | 0.5 天 | dry-run ready + 冒烟 JSON 正确 |
| P1 | 项目骨架 | D1 | 建库脚本幂等,git 无敏感文件 |
| P2 ★ | JD 匹配闭环 | D2-D5 | 6 条端到端验收全绿 |
| P3 ★ | 评测基线 | D6-D7 | 评测报告有三个数字 |
| P4 | 自动化推送 | D8-D9 | 连续 2 天无人值守收到晨报 |
| P5 | 面试模拟官 | D10-D11 | 一次完整模拟+复盘入库 |
| P6 ★ | 成本看板+简历定制 | D12-D13 | 一条命令出成本报告 |
| P7 | 发布包装 | D14+ | 陌生人 3 分钟看懂 README |

---

## P0 环境终检(0.5 天)✅ 2026-10-03 完成

- [x] `~/.bashrc` 加 oh/ohmo alias(新开终端生效)
- [x] 注册并激活 Ollama profile:模型机在同一局域网的另一台机器(RTX 3060),远端原本没有 64k 定制版,**已通过 /api/create 远程重建** `qwen3.5-4b-64k`(num_ctx=65536);凭据写入 `profile:ollama` 槽位(占位 key,Ollama 不校验)→ `oh provider list` 显示 `[ready]`
- [x] `oh --dry-run` → `ready`
- [x] 冒烟:`oh -p "1+1=? 只回答数字"` → 返回 "2",往返 17.6s(含首次加载)
- [x] 临时目录验证项目级 skill 发现:`oh-smoke-test` 成功被发现(score=5)

## P1 项目骨架(D1)✅ 2026-10-03 完成

- [x] `git init job-agent`(main 分支),`.gitignore` 先行并验证生效(`.env`、`data/job.db` 均被忽略)
- [x] `uv init` + `uv add fastmcp httpx`(uv.lock 已锁定)
- [x] `scripts/init_db.py` 建 6 张表 + 2 索引,重复执行幂等
- [x] `.env` + `.env.example`(LLM/EMBED 指向局域网 Ollama,GITHUB_TOKEN 留空)
- [x] 目录:`.openharness/skills/ mcp-server/ eval/ scripts/ docs/ data/`

**验收门**:`init_db.py` 重复执行不报错;`git status` 里无敏感文件。

## P2 JD 匹配闭环 ★(D2-D5,核心)✅ 2026-10-03 完成

- [x] 简历画像:`assets/sample-profile.json`(脱敏样例)+ `scripts/seed_profile.py` 写入 DB;真实画像复制为根目录 `profile.json`(gitignored)后 seed
- [x] 在校身份模板:`assets/sample-profile.student.json`(身份/实习/项目/竞赛字段);SKILL.md 已加校招口径规则(实习与项目替代年限、经验底线不参与硬性过滤);`_resume_text` 覆盖项目与校园经历;get_profile 查无此名时返回 available 名单
- [x] MCP server:`mcp-server/main.py` 官方 `mcp` SDK 的 MCPServer,8 工具;embedding 召回在服务端完成;模型输出按不可信输入处理(类型收敛、单画像兜底)
- [x] 注册:项目 plugin `.openharness/plugins/job-agent-data/`(含 `.mcp.json`),`allow_project_plugins true` → dry-run 显示 48 工具
- [x] `skills/jd-match/SKILL.md`:三段式工作流;硬性过滤定义已修正(经验差距≠硬性失败)
- [x] 两阶段解析与三段式匹配就绪;**端到端实测通过**:semantic 77.0、维度分、差距清单全部正确落库

**验收门**:✅ 粘贴 JD → `jobs`+`matches` 落库 → 返回匹配分与差距清单。

P2 实战记录(踩坑与对策,面试素材):
- OpenHarness v0.1.9 的 MCP 客户端按 mcp 1.x 的 `tool.inputSchema` 编写,但其 venv 装了 mcp 2.2.0 → 工具发现静默失败。**已在 OpenHarness venv 内降级 mcp 到 1.30.0**
- fastmcp 4.x 与上游客户端同样不兼容,已弃用,直接用官方 SDK 的 `mcp.server.mcpserver.MCPServer`
- print 模式下斜杠命令的参数展开不可靠 → `scripts/match_jd.py` 以 SKILL.md 为唯一工作流来源拼提示词
- Git Bash 会把 `/jd-match` 当路径转成 `D:/Git/jd-match` → headless 调用加 `MSYS_NO_PATHCONV=1`
- 4B 工具调用偶发空消息/公式执行偏差 → 远端已建 agent 调优模型 `qwen3.5-4b-agent`(temp 0.6),profile 已切换;残余偏差交给 P3 评测量化

## P3 评测基线 ★(D6-D7,简历数字来源)

- [x] **评测脚手架已建成**:`eval/run_eval.py`(extract / recall / rubric 三阶段,组件级评测——硬性过滤是纯规则不测模型)+ `eval/jd_dataset.jsonl`(12 条样例 JD 带标注)+ `eval/README.md`(标注口径)
- [x] 样例画像全量跑通,报告输出到 `eval/reports/`
- [x] **抽取迭代闭环已完成(样例画像)**:58%(含指标假阴性)→ 87%(修复归一化:全空白剥离)→ 归因失败样本发现 2/12 是标注错误而非模型错误(修正 gt)→ **98%,技能覆盖 100%**。指标也会错、标注也会错——评测卫生学三连,面试故事已就位
- [x] 抽取预测落盘 `predictions-*.jsonl`,支撑逐例归因
- [ ] **换真实画像重标后重跑**(这一步的数字才能进简历):复制学生模板为 `profile.json` 填真实信息(可半脱敏)→ seed → 收集 30-50 条真实 JD 逐条标注 → `python eval/run_eval.py all`
- [ ] 指标目标:抽取字段准确率 >90%、Top-5 命中率 ≥80%、记录召回区分度与阈值
- [ ] 不达标 → 失败样本分类归因 → 改 prompt/两阶段规则 → 重跑(这本身就是面试故事)
- [ ] 若 4B 触及天花板:`oh provider use` 切云端模型,记录"本地 vs 云"对比表(成本意识的实证)

## P4 自动化与推送(D8-D9)

- [x] **晨报脚本已建成**:`scripts/daily_brief.py`(纯 SQL+模板,不调 LLM,cron 场景求稳)——demo 模式已测;飞书/Telegram webhook 推送与落盘降级都已实现,**`--register` 一键注册 Windows 计划任务(每日 08:30)**
- [ ] 配置真实推送通道:`.env` 里填 `FEISHU_WEBHOOK`(飞书群机器人)或 `TELEGRAM_BOT_TOKEN`+`TELEGRAM_CHAT_ID`,然后 `--register`
- [ ] 职位源:邮箱转发规则 → IMAP 拉取;或 RSS。**不爬 BOSS/拉勾**(合规红线,面试时主动讲)
- [ ] 空结果、网络失败、拉取超时的兜底分支(部分已实现:无新职位文案/推送失败落盘)

**验收门**:连续 2 天无人值守收到晨报。

## P5 面试模拟官(D10-D11)✅ 2026-10-03 完成

- [x] `skills/interview-coach/SKILL.md`:面试计划生成(自我介绍深挖/项目深挖/基础/场景/行为)→ 逐题提问+即时反馈 → 复盘;中途禁止入库,结束一次 `save_interview`
- [x] MCP 工具 `save_interview`(transcript + 四维 rubric → interview_sessions 表),进程内验证通过
- [x] headless 冒烟:计划生成与第一题正常,问题贴合画像
- [ ] 真人多轮验证(交互式 /interview-coach,日常使用时完成)
- [ ] 评测:同一答案跑 3 次检查 rubric 方差(留待真实使用期)

## P6 成本看板 + 简历定制 ★(D12-D13)✅ 2026-10-03 完成

- [x] `scripts/cost_report.py`:按场景×模型聚合 + 近 14 天趋势;空库给出埋点指引
- [x] 埋点:match_jd.py 每次运行自动记一条;**已知限制**:OpenHarness v0.1.9 不回传 usage(session 存储为 0),oh 会话只能按调用次数记账——上游暴露 usage 后一行切换,面试可讲的成本工程权衡
- [x] `skills/resume-tailor/SKILL.md`:A 保真版/B 进取版 + 差异说明;B 版每处对齐强制标注 `[对齐:画像依据]`(防造假设计);headless 实测 A/B 落盘 `data/tailored/`

**验收门**:✅ cost_report 一条命令出报表;✅ 一个 JD 产出两版定制简历落盘。

## P7 发布包装(D14+)

- [x] README 三段式:30 秒看懂 → 能力/评测/安全边界 → 目录/限制/技术栈(30 秒 GIF 与架构图待补)
- [ ] 博客一篇:写一个真实坑(推荐"4B 本地模型的 JSON 可靠性与两阶段解析"),提前铺好面试战场
- [ ] 开源脱敏:db/画像/标注集清洗后发布
- [ ] demo 录屏,发 V2EX/掘金
- [ ] 可选加分:`company-brief` skill;给 OpenHarness `docs/SHOWCASE.md` 提 showcase PR(官方明确欢迎)

**验收门**:一个不认识这个项目的人,3 分钟内从 README 理解它是什么、效果如何。

---

## 安全边界(投递类操作,2026-10-03 加固)

投递是不可逆的外部副作用,原实现只有 UI 层默认模拟,服务端与函数层都默认真实发送——已收紧为纵深防御:

- [x] 函数层默认最保守:`deliver_job_application(dry_run=True)`、`batch_deliver_pending_applications(dry_run=True)`
- [x] 真实批量投递必须显式 `confirm=true`,否则 400 拒绝(批量误发无法撤回)
- [x] 单次批量上限 5、每日真实投递上限 10(`JOB_AGENT_MAX_BATCH` / `JOB_AGENT_MAX_DAILY_SENDS` 可覆盖)
- [x] 每日额度按本地日期统计,`GET /api/apply/quota` 可查;熔断时单发与批量都拒绝并给出原因
- [x] SMTP 授权码落盘后尽量收紧为仅本人可读写;优先用环境变量 `SMTP_USER`/`SMTP_PASS`
- [x] 端到端验证:批量 dry-run 200、真实批量无确认 400、无收件邮箱 400

## 风险与回退

| 风险 | 回退方案 |
|---|---|
| 4B 抽取/评分质量不达标 | `oh provider use` 一键切云,保留本地/云对比数据 |
| JSON 输出不稳定 | 两阶段解析(已内建)+ 失败样本进评测集 |
| 职位源抓取受限 | 降级为纯手动粘贴 + 邮件转发,MVP 不受影响 |
| 时间超支 | 砍序:P7 可选项 > P6 resume-tailor > P5;P2/P3 不可砍 |

## 与 issue-pr-agent 的关系

- 评测基座(P3)、MCP 骨架(P2)、observability(P6)直接搬代码,不是重写
- 它的切片 9(可观测+成本)可与本项目 P6 合并做,两边共享
- 简历组合:自研 harness(issue-pr-agent)证明内核理解力,OpenHarness 应用(job-agent)证明工程交付力
