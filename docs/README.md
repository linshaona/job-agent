# job-agent 设计决策与踩坑记录

本目录收录**为什么这么写**——架构细节见 [../../job-agent-plan.md](../../job-agent-plan.md),施工顺序与验收门见 [../../job-agent-roadmap.md](../../job-agent-roadmap.md),环境命令见 [../../job-agent-setup.md](../../job-agent-setup.md)。这里只留可复用的判断与代价。

## 1. 职责切分:skill 管流程,MCP 管数据

业务逻辑全部落在两处,不写进 harness 内核:

- **skill**(`.openharness/skills/*/SKILL.md`)承载工作流与口径。例如校招口径(实习与项目可替代年限、经验差距不等同硬性失败)写在 skill 里,改口径不用碰代码;
- **MCP 工具**(`mcp-server/main.py`)承载数据访问,embedding 召回在服务端完成,模型只负责决策。

代价:skill 是提示词,约束力弱于代码;因此凡"错了就有损失"的规则(投递上限、硬性过滤)一律下沉到 Python。

同理,**属于画像的数据不进代码**:匹配建议里的项目名从 `resume.projects` 读([matcher_engine.py](../matcher_engine.py)),而不是写死在引擎里——否则换画像不生效,开源还会带出个人信息。

## 2. 结构化抽取:两阶段解析

4B 本地模型的 JSON 输出不可靠,所以抽取走"规则预抽取(正则拿薪资/地点/年限等强格式字段)+ LLM 校正与补全",再对模型输出做类型收敛(单画像兜底、`_as_float` / `_as_bool` / `_as_obj`)。

配套原则:**模型输出一律当不可信输入**,即使在自家进程里也一样。

## 3. 三段式匹配:先省钱,再花钱

| 阶段 | 手段 | 为什么 |
|---|---|---|
| ① 硬性过滤 | 纯规则(城市 / 身份 / 年限 / 薪资底线) | 零 token、100% 可解释,面试时能讲清每一分为何被扣 |
| ② 召回 | profile 与 JD 分板块 embedding 余弦 | 便宜,负责"不漏" |
| ③ 精排 | rubric 加权(技能 45% / 业务 35% / 加分 20%)+ 差距清单 | 贵,只对少量候选做 |

硬性过滤不通过时综合分封顶 55:让"不匹配"在排序上自然沉底,而不是直接丢弃(可能需要人工复核)。

## 4. 评测卫生学:指标也会错,标注也会错

抽取准确率迭代记录:58%(含指标假阴性)→ 87%(修归一化:全空白剥离)→ 98%(逐例归因发现 **2/12 是标注错误而非模型错误**)。

结论:评测失败先怀疑评测本身。因此脚本会把逐例预测落盘 `eval/predictions-*.jsonl`,保证任何数字都能回溯到具体用例,再谈改 prompt。

## 5. 投递安全边界(不可逆操作一律默认最保守)

邮件发出去就收不回来,所以:

- 单岗位投递 `dry_run` 默认 `True`;
- 真实批量投递必须 `confirm=true`,否则 400 拒绝;
- 单次批量上限 5、每日真实投递上限 10(`JOB_AGENT_MAX_BATCH` / `JOB_AGENT_MAX_DAILY_SENDS`);
- 每日额度按 `applications.applied_at` 的本地日期统计,`GET /api/apply/quota` 可查。

设计取舍:额度用现有表统计而不是新建投递日志表,避免为安全边界改 schema;代价是重复投递同一岗位也会占额度(保守方向,可接受)。

## 6. 环境适配踩坑(Windows + OpenHarness v0.1.9)

| 现象 | 根因 | 处理 |
|---|---|---|
| MCP 工具发现静默失败 | OpenHarness 客户端按 mcp 1.x 的 `tool.inputSchema` 编写,而 venv 装了 2.x | 在 **OpenHarness venv** 内把 mcp 降到 1.30.0(本项目用官方 SDK 2.x 写服务端,不受影响) |
| fastmcp 4.x 连不上上游 | 同上,客户端兼容性 | 弃用 fastmcp,改用官方 `mcp.server.mcpserver.MCPServer` |
| 斜杠命令参数展开不可靠 | print 模式限制 | `scripts/match_jd.py` 以 SKILL.md 为唯一工作流来源自己拼提示词 |
| `/jd-match` 被 Git Bash 当路径 | MSYS 路径转换 | headless 调用加 `MSYS_NO_PATHCONV=1` |
| 4B 工具调用偶发空消息 | 模型能力 | 远端单独建调优模型 `qwen3.5-4b-agent`(temp 0.6),残余偏差交给评测量化 |
| 换机器后 MCP 起不来 | `.mcp.json` 写死了解释器绝对路径 | 改为 `command: "uv"` + 相对 `cwd: "."`(项目级 plugin 只在项目根被发现,所以相对路径是安全的) |

## 7. 已知限制与未来切换点

1. **usage 不回传**:OpenHarness v0.1.9 的会话记账为 0,`cost_report.py` 只能按调用次数估算;上游暴露 usage 后改一行即可;
2. **4B 质量天花板**:定位类、长 JSON 生成仍需兜底;
3. **评测集是样例数据**:真实画像重标(P3 待办)完成前,README 里的数字不能写进简历;
4. **岗位来源**:目前手动粘贴 / 邮件转发;RSS 与官网招聘页抓取未接,BOSS/拉勾不做(合规红线);
5. **端口**:工作台默认 8010(issue-pr-agent 控制台占 8000),`set PORT=xxxx` 可覆盖。
