# 评测基线(P3)

## 数据集

`jd_dataset.jsonl`,每行一个用例:

```json
{"id": "jd-01", "label": {"relevant": 5}, "gt": {"title": "...", "skills_required": ["..."]}, "jd_raw": "JD 原文"}
```

- `label.relevant`:人工标注的相关度,口径:
  - **5** 高度匹配(方向/城市/薪资/技能全中)
  - **4** 明确值得投(核心匹配,有小差距)
  - **3** 边界情况(可投可不投)
  - **2** 基本不匹配(方向或硬条件偏差)
  - **1** 完全不匹配
- `gt`:抽取评测的 ground truth,以 JD 原文中实际出现的信息为准,JD 没写的字段不参与判分

## 指标

| 阶段 | 指标 | 目标 |
|---|---|---|
| 抽取 | 字段准确率 / 技能覆盖率 | >90% / 记录基线 |
| 召回 | 相关 vs 不相关的语义分均值差、二分类准确率 | 记录间隔与阈值 |
| 精排 | Top-5 命中率 | ≥80% |

## 扩充真实标注集(重要)

当前 12 条是**样例画像(李四)的标注**,数字只用于验证脚手架。可写进简历的基线:

1. 换真实画像:`cp assets/sample-profile.student.json profile.json` → 填真实信息(可半脱敏)→ `python scripts/seed_profile.py profile.json`
2. 收集 30-50 条**你真实会看到的 JD**(邮件转发、网站粘贴),存入 jsonl
3. 逐条标注 `label.relevant` 与 `gt`(平时用 agent 时顺手标,`matches.eval_label` 字段也可回填)
4. 重跑:`python eval/run_eval.py all --profile default`

## 用法

```bash
python eval/run_eval.py all               # 全部三个阶段
python eval/run_eval.py recall            # 只跑召回(最快,纯 embedding)
python eval/run_eval.py extract --profile student
```

报告输出到 `eval/reports/`,本地模型跑批成本 ¥0。
