# job-agent

个人求职 Agent,基于 [OpenHarness](https://github.com/HKUDS/OpenHarness) 构建:JD 语义匹配、简历定制、面试模拟复盘、职位监控推送。

> 施工中。架构与设计决策见 `docs/`,构建路线见仓库外 `../job-agent-roadmap.md`。

## 当前状态

- [x] P0 环境终检(OpenHarness v0.1.9 + Ollama qwen3.5-4b-64k @ 远端 3060)
- [x] P1 项目骨架(SQLite 6 表 + uv 依赖)
- [ ] P2 JD 匹配闭环(进行中)

## 技术栈

OpenHarness(skills + MCP 扩展,与内核解耦)· FastMCP · SQLite · nomic-embed-text · qwen3.5-4b-64k(本地 3060,零 API 成本)
