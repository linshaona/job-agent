---
name: jd-match
description: 解析职位描述(JD)并按三段式(硬性过滤→语义召回→精排)与用户简历画像匹配打分,结果入库并输出差距清单。当用户粘贴 JD、发送职位链接或询问"这个岗位匹配吗"时使用。
---

# JD 匹配

通过 `/jd-match <JD原文>` 调用时,`$ARGUMENTS` 就是要评估的 JD 原文;若参数为空,先向用户索要 JD。

**既定事实:用户的简历画像和求职偏好已经存在数据库里,通过 `mcp__job-agent-data_job-agent-data__get_profile` 工具即可获取。**

**工具名说明:本技能引用的 MCP 工具在系统里的全名带前缀 `mcp__job-agent-data_job-agent-data__`。如果你的工具列表里找不到这些名字,在 `mcp__job-agent-data_job-agent-data__` 前缀下寻找对应功能,禁止断定工具不存在而改问用户。任何情况下都禁止向用户索要简历或个人信息。**

严格按以下步骤执行,每一步都必须用工具完成,不要跳步:

1. **第一步永远是调用 `mcp__job-agent-data_job-agent-data__get_profile` 工具**。它返回用户画像;若返回 error 字段,告知用户运行 `python scripts/seed_profile.py` 后重试,流程终止。
2. **硬性过滤**(纯规则,只看用户底线):`hard_filter_pass=false` 仅当 城市不在期望城市、或 JD 薪资低于用户底线。**JD 要求的经验年限高于用户当前年限属于差距,不算硬性失败**;JD 未提及该项视为通过,并在差距清单注明"JD 未说明"。

   > **在校/应届画像**:若 `resume.basics.身份` 含"在校""应届"或"实习",按校招口径评估——用实习与项目经历替代工作年限,preferences 的 `经验底线` 不参与硬性过滤,薪资底线按 JD 薪资类型(月薪/日薪/年薪)对应比较。
3. **语义召回**:调用 `mcp__job-agent-data_job-agent-data__semantic_score`,传入完整 JD 原文,得到 0-100 相似分。禁止自己估算语义分。
4. **结构化解析**:把 JD 整理成如下结构(不确定的字段填 null,禁止编造):

   ```json
   {"title": "", "company": "", "location": "", "salary": "",
    "experience_required": "", "skills_required": [], "responsibilities": []}
   ```

5. **精排打分**:三个维度各打 1-5 分(整数)——`技能重叠`(对照 skills_required 与画像技能)、`业务相关性`(对照目标岗位与经历)、`成长性`。信息不足的维度按 3 分中性处理并写入差距清单。
   总分公式:`hard_filter_pass ? round(语义分*0.3 + 三维度之和/15*70) : 0`
6. **入库**:调用 `mcp__job-agent-data_job-agent-data__save_job`(含第 4 步结构化字段)拿到 `job_id`;再调用 `mcp__job-agent-data_job-agent-data__save_match` 写入 score、hard_filter_pass、semantic、dimensions、gap_list(3-5 条,按重要性排序,每条一句话)。
7. **汇报**(3-6 行):总分与硬过滤结果 → 三维度分与语义分 → 最关键的 3 条差距 → 一句建议。

## 常见错误(出现即失败)

- ❌ 向用户索要简历/背景 → 画像在数据库里,调 `mcp__job-agent-data_job-agent-data__get_profile`
- ❌ 跳过 `mcp__job-agent-data_job-agent-data__semantic_score`,自己估一个相似度 → 必须用工具返回值
- ❌ 编造 JD 里没有的字段 → 填 null
- ❌ 没调 `mcp__job-agent-data_job-agent-data__save_job` 和 `mcp__job-agent-data_job-agent-data__save_match` 就结束 → 未入库等于任务失败
