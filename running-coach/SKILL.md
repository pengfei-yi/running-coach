---
name: running-coach
description: |-
  跑步数据分析与训练指导。通过 intervals.icu API 读取华为运动健康同步的跑步数据，
  提供成绩预测、周期化训练计划生成、每日课程建议、训练数据分析报告。
  触发词：跑步、马拉松、半马、全马、训练计划、成绩预测、课表、跑步分析、配速、长跑、
  intervals、运动健康、华为健康数据、run、marathon、half marathon、race prediction。
agent_created: true
---

# Running Coach — 跑步训练智能助手

## Overview

基于 intervals.icu API 的跑步数据分析与训练指导系统。数据通过华为运动健康自动同步到 intervals.icu，
此 Skill 负责读取数据并提供四项核心能力：成绩预测、训练计划、课程建议、分析报告。

支持多运动员配置（自己+朋友），通过 `~/.running_coach/config.json` 管理 API 凭据。

## 前置条件：API Token 配置

首次使用前，帮助用户获取 intervals.icu API Token 并完成配置：

1. 指导用户打开 https://intervals.icu/settings，在页面底部找到 **"API Key"** 和 **"Athlete ID"**
2. 运行初始化命令：
   ```
   python scripts/intervals_client.py init --athlete-id <ID> --api-key <KEY> --name <profile_name>
   ```
   默认 profile name 为 `default`，朋友用不同 name（如 `friend`）
3. 验证连接：
   ```
   python scripts/intervals_client.py athlete
   ```
   应返回运动员档案 JSON。

## 核心功能

### 1. 成绩预测 (`scripts/race_predictor.py`)

预测指定距离的完赛时间，基于多个模型综合分析。

**使用场景**：用户问 "我全马能跑多少？"、"预测下半马成绩"、"5K能破20分钟吗？"

**执行步骤**：
1. 解析目标距离（支持：`5k`, `10k`, `half`, `marathon` 或具体米数）
2. 运行预测命令：
   ```
   python scripts/race_predictor.py <distance> [--days 180] [--method all]
   ```
3. 解析 JSON 输出中的关键字段：
   - `riegel.predicted_time_str` — Riegel 公式预测时间
   - `riegel.adjusted_time_str` — CTL 修正后的预测
   - `riegel.predicted_pace` — 预测配速
   - `fitness` — 当前 CTL/ATL/TSB
   - `recommendation` — 训练建议列表
4. 用自然语言向用户解释预测结果，重点说明：
   - 不同预测方法的差异（Riegel vs CTL 修正）
   - 基于当前训练状态的置信度
   - 如需更准确预测，建议分析的具体改进方向

**仅查看全部基准成绩**：
```
python scripts/race_predictor.py --benchmark
```

### 2. 训练计划生成 (`scripts/training_plan.py`)

根据目标赛事、比赛日期、当前水平生成周期化训练计划。

**使用场景**：用户问 "给我一个12周的半马训练计划"、"我要跑12月的全马，帮我做计划"、"给我一个10K训练计划"

**执行步骤**：
1. 确认关键参数：比赛距离、比赛日期（`YYYY-MM-DD`）、每周可训练天数（默认5）、水平（auto/beginner/intermediate/advanced）
2. 运行生成命令：
   ```
   python scripts/training_plan.py <distance> --date YYYY-MM-DD [--days 5] [--level auto] [--text]
   ```
3. 计划会自动从 intervals.icu 检测：
   - 当前周跑量（auto-detect）
   - CTL 水平 → 推荐训练强度等级（beginner/intermediate/advanced）
4. 计划包含四阶段：基础期 → 建设期 → 巅峰期 → 减量期
5. 可摘要展示计划结构，提供关键周次的训练详情

**推送计划到 intervals.icu 日历**（用户明确要求时）：
```
python scripts/training_plan.py <distance> --date YYYY-MM-DD --push
```
⚠️ 推送前务必告知用户：此操作会写入日历事件，可能覆盖现有计划。

### 3. 每日课程建议 (`scripts/workout_advisor.py`)

基于当前体能状态（CTL/ATL/TSB）和近期训练构成，推荐今日最佳训练内容。

**使用场景**：用户问 "今天该跑什么？"、"今天适合练间歇吗？"、"我状态怎么样？"

**执行步骤**：
1. 运行：
   ```
   python scripts/workout_advisor.py [--days 30]
   ```
2. 分析返回结果的关键决策依据：
   - `fitness.tsb` — 决定训练强度
     - TSB > 10：适合高强度训练
     - TSB < -20：仅建议恢复跑或休息
   - `recent.workout_types` — 训练平衡性（缺少哪种训练？）
   - `wellness_trend` — HRV/静息心率是否异常
3. 根据 `recommendation.decision` 给出建议：
   - `rest`：明确建议休息
   - `easy`：建议轻松恢复跑
   - `hard_workout`：推荐高质量训练，并展示 `suggested_workout` 结构
   - `normal`：按常规训练
4. 简要解释推荐理由（rationale 列表）

### 4. 数据分析报告 (`scripts/analysis_report.py`)

生成交互式 HTML 训练分析报告，含图表。

**使用场景**：用户问 "分析下我最近的训练"、"生成一份跑步数据报告"、"我的训练状态怎么样？"

**执行步骤**：
1. 运行：
   ```
   python scripts/analysis_report.py [--days 90] [--output report.html]
   ```
2. 报告自动保存到 `~/.running_coach/reports/`
3. 生成的 HTML 包含：
   - CTL/ATL/TSB 体能趋势折线图
   - 周跑量柱状图
   - 心率区间分布饼图
   - 配速趋势散点图
   - 距离成绩预测表
4. 用 `present_files` 展示报告给用户

## Workflow Decision Tree

收到用户请求后，按以下决策树判断使用哪个功能：

```
用户请求
├─ 提到"预测"/"能跑多少"/"成绩"/"目标成绩"
│   → 使用 race_predictor.py
│
├─ 提到"训练计划"/"备战"/"课表"/"几周计划"
│   → 使用 training_plan.py
│
├─ 提到"今天"/"推荐"/"该跑什么"/"课程建议"
│   → 使用 workout_advisor.py
│
├─ 提到"分析"/"报告"/"趋势"/"状态"/"summary"
│   → 使用 analysis_report.py
│
└─ 首次使用 / 提到"配置"/"API Token"/"数据"
    → 引导配置 intervals.icu API
```

## 多运动员管理

当用户提到不同的运动员（自己/朋友），在命令中添加 `--profile` 参数（脚本会自动从 config.json 读取对应配置）。

目前脚本通过 `intervals_client.py` 的 `config_name` 参数支持多 profile。如需切换：
在 Python 代码中实例化 `IntervalsClient(config_name="friend")`，或修改脚本 CLI 增加 `--profile` 参数。

## References

需要深入了解以下主题时，加载对应参考文档：

- `references/intervals_api.md` — intervals.icu API 完整端点参考
- `references/race_prediction.md` — 成绩预测公式详解（Riegel/VDOT/CTL）
- `references/training_templates.md` — 训练计划模板与周期化结构

## Assets

- `assets/config.example.json` — 多运动员配置文件模板

## 注意事项

1. **API Token 安全**：提醒用户 API Key 等同于密码，不要分享或提交到 Git
2. **预测不确定性**：成绩预测基于统计模型，受天气、赛道、状态等因素影响，应给出置信区间
3. **训练计划个性化**：自动生成是起点，建议用户根据反馈调整
4. **数据延迟**：华为运动健康 → intervals.icu 的同步有延迟，以 intervals.icu 最新数据为准
