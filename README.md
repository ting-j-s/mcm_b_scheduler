# MCM B Scheduler

本项目用于求解五一数学建模竞赛 B 题多工序协同作业调度问题。

## 环境

Python 3.10+

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行方法

```bash
python src/test_p1.py
python src/test_p2.py
python src/test_p3.py
python src/test_p4.py
python src/generate_result_tables.py
```

## 输出文件

- `outputs/q1_schedule.csv` - 问题一调度结果
- `outputs/q2_schedule.csv` - 问题二调度结果
- `outputs/q3_schedule.csv` - 问题三调度结果
- `outputs/q4_schedule.csv` - 问题四调度结果
- `outputs/q4_purchase.csv` - 问题四采购方案
- `outputs/result_tables.xlsx` - 所有问题结果汇总
- `outputs/final_summary.txt` - 最终结果摘要

## 最终结果

- P1: 41600s = 11:33:20
- P2: 163764s = 45:29:24
- P3: 123844s = 34:24:04
- P4: 123844s = 34:24:04
- P4 purchase cost: 445000 / 500000 元