# 求职 Agent —— 基于 OpenHarness 的项目计划

> 定位:求职作品集项目 + 自用工具。技术叙事:Agent Harness、RAG/语义匹配、评测体系、成本控制、定时任务、消息网关。
> 简历一句话:基于 OpenHarness 构建个人求职 Agent:JD 语义匹配、简历定制、面试模拟复盘、职位监控推送;自建评测集与成本看板。

## 一、总体架构

```
┌─────────────────────────────────────────────────┐
│                  消息入口 / 出口                   │
│   ohmo gateway:飞书 / Telegram(推送 + 对话)      │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              OpenHarness 核心 (oh / ohmo)        │
│  engine(agent loop)· permissions · hooks · cron  │
└───┬──────────┬──────────┬──────────┬────────────┘
    │          │          │          │
 Skills     MCP 工具     memory     headless
(SKILL.md) (自写,操作    (~/.ohmo/  (oh -p --json
 4 个业务    求职数据库    soul/user/  批量任务:
 skill)     + 抓取封装)   memory)    抽取/评分/周报)
    │          │
    └────┬─────┘
         ▼
   SQLite(全本地,含 .gitignore 防泄漏)
   jobs / profile / applications / qa_log / cost_log
```

**四个业务 Skill(核心交付物)**

| Skill | 输入 | 输出 | 对应面试考点 |
|---|---|---|---|
| `jd-match` | JD 文本 | 结构化抽取 + 匹配分 + 差距清单 | 结构化抽取、评分 rubric、embedding |
| `resume-tailor` | JD + 简历画像 | 定制版 bullet(A/B 两版) | prompt 策略对比、输出约束 |
| `interview-coach` | JD + 简历 | 多轮模拟面试 + 复盘报告 | 多轮状态管理、persona |
| `company-brief` | 公司名 | 面试前情报简报 | web research agent、信息可信度 |

**数据源策略(合规优先,不碰反爬红线)**
- MVP:手动粘贴 JD / 转发招聘邮件到 agent(邮箱规则自动转发 → IMAP 拉取)
- 二期:RSS / 官网招聘页抓取(robots.txt 允许范围内)
- 明确不做:模拟登录爬 BOSS/拉勾

## 二、SQLite 表设计

- `jobs(id, source, company, title, jd_raw, jd_structured JSON, salary, url, fetched_at)`
- `profile(basename, resume_json JSON, preferences JSON)` —— 简历画像,可存多版本
- `matches(job_id, score, hard_filter_pass, gap_list JSON, eval_label, created_at)` —— `eval_label` 留给人工标注
- `applications(job_id, status, applied_at, next_action, notes)` —— 投递看板
- `cost_log(ts, scene, model, prompt_tokens, completion_tokens, cost_cny)` —— 成本看板数据源
- `interview_sessions(job_id, transcript JSON, rubric_score JSON, created_at)`

## 三、匹配算法(三段式,方便面试讲权衡)

1. **硬性过滤**:地点/年限/薪资底线,规则引擎,不进模型(省钱且可解释)
2. **语义召回**:profile 与 JD 各切板块 embedding,余弦相似度粗排(Ollama 本地 bge 或低价 API)
3. **LLM 精排**:rubric 打分(技能重叠/业务相关/成长性各 1-5 分)+ 输出差距清单,JSON Schema 约束输出

## 四、评测体系(作品集差异化核心,必须做)

- **抽取评测**:30 条 JD 人工标注字段 → 字段级准确率,目标 >90%
- **匹配评测**:50 条 (JD, 相关度 1-5) 人工标注 → Top-5 命中率,目标 ≥80%
- **成本**:¥/次匹配,目标 <0.5 元;周报里展示趋势
- 脚本 `eval/run_eval.py`:跑批 → 输出 metrics 报告(Markdown),README 里贴最终表格

## 五、两周里程碑

**Week 1 —— JD 匹配最小闭环**
- D1-2:装 OpenHarness,配 provider(Ollama 或低价 API),建仓库与 SQLite schema,跑通 `oh` 对话
- D3-4:`jd-match` skill + 数据库 MCP 工具;手动粘贴 JD → 抽取 → 打分 → 入库
- D5:简历画像文件;三段式匹配算法跑通
- D6-7:标注 30-50 条真实历史 JD,跑出第一版命中率;结果推送到飞书

**Week 2 —— 自动化 + 第二功能 + 包装**
- D8-9:邮件转发/RSS 接入,cron 晨报(新职位 + 今日面试安排)
- D10-11:`interview-coach` 多轮模拟 + 复盘报告
- D12:成本记账(cost_log + 每次调用埋点),CLI 看板
- D13:`resume-tailor`(可选再排 `company-brief`)
- D14:README(30 秒 GIF + 架构图 + 指标表)、博客初稿、demo 录屏

## 六、风险与对策

- **反爬合规**:只做粘贴/邮件/RSS,面试时主动讲这个取舍(本身是加分答案)
- **隐私**:简历数据全本地,`.gitignore` 掉 db 与画像文件,开源仓库只含代码与 skill 模板
- **抽取不稳定**:两阶段解析(规则预抽取 + LLM 校正),失败样本进评测集
- **范围蔓延**:company-brief 和看板 Web 版都是可砍项,核心指标(命中率/成本)优先

## 七、仓库结构(建议)

```
job-agent/
  README.md            # GIF + 架构 + 指标表
  skills/              # 4 个 SKILL.md(可直接被 OpenHarness 加载)
  mcp-server/          # 求职数据 MCP 工具(Python)
  eval/                # 评测脚本 + 标注集(脱敏后开源)
  scripts/             # cron 任务、导入脚本
  docs/                # 博客草稿、设计决策记录
```
