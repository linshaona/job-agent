# 评测报告 20261003-1142
- 画像:student(注意:样例画像的结果仅验证脚手架,不可写进简历)
- 模型:qwen3.5-4b-agent @ http://10.102.170.214:11434/v1
- 数据集:jd_dataset.jsonl(12 条)

## 1. 抽取字段准确率

| 用例 | 字段判定 | 技能覆盖 |
|---|---|---|
| jd-01 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-02 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-03 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-04 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-05 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-06 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-07 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-08 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-09 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-10 | title:√ company:√ location:√ salary:√ experience_required:× | 技能覆盖 100% |
| jd-11 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |
| jd-12 | title:√ company:√ location:√ salary:√ experience_required:√ | 技能覆盖 100% |

**字段准确率**: title 12/12 / company 12/12 / location 12/12 / salary 12/12 / experience_required 11/12

**总字段准确率 98% · 技能平均覆盖 100%**(目标:字段 >90%)


---
耗时 380s · 本地模型,成本 ¥0