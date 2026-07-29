# 惜食智备 MVP 实现文档

## 1. 产品目标

惜食智备面向校园食堂、小型餐馆和团餐经营者。用户加载演示数据或上传 CSV/XLSX 后，系统计算损耗、售罄和成本指标，调用 InfiniSynapse 分析星期、天气、活动与菜品需求之间的关系，输出明日备餐量、预计节省金额和行动清单。

核心体验：

```text
一键加载演示数据 → 本地指标 → InfiniSynapse 深度分析 → 明日备餐计划 → 情景模拟 → 报告下载
```

MVP 不包含账户、支付、多门店、供应商、实时数据库和 Partner SSO。

## 2. 技术架构

- 前端：React 18 + TypeScript + Vite；使用 CSS/SVG 绘制轻量图表，避免演示依赖复杂配置。
- 后端：FastAPI + Pydantic + HTTPX + Pandas + OpenPyXL。
- 存储：SQLite 保存任务状态，`APP_DATA_DIR` 保存上传文件和数据库。
- 部署：单 Docker 镜像；FastAPI 托管 `frontend/dist`。
- 配置：`INFINISYNAPSE_API_KEY`、`INFINISYNAPSE_BASE_URL`、`APP_DATA_DIR`、`MAX_UPLOAD_MB`。

API Key 只在服务端环境变量中出现，不进入前端代码、响应体或日志。

## 3. 数据契约

必填字段为 `date`、`meal_period`、`dish_name`、`prepared_qty`、`sold_qty`、`unit_price`、`unit_cost`。可选字段为 `waste_qty`、`weather`、`event_name`、`footfall`。数据至少覆盖 7 天、3 个菜品和 20 条记录；支持 CSV/XLSX，最大 10 MB。

缺失 `waste_qty` 时按 `max(prepared_qty - sold_qty, 0)` 计算。日期、数值、餐次枚举、负数和 `sold_qty > prepared_qty` 均执行行级错误返回。内置演示数据在首次访问时生成 30 天、4 个菜品、2 个餐次的稳定样例，包含雨天、活动、周期性多备和售罄模式。

## 4. 确定性分析

后端先完成本地计算，确保 API 失败时仍有可用结果：

- 损耗量、损耗率、损耗成本、售罄率和毛利估算。
- 按菜品、日期、餐次、星期、天气聚合。
- 基础备餐量为最近 7 天销量与目标星期销量的加权平均。
- 建议量限制在历史最大销量的 80%～120% 安全范围内。
- AI 最终建议只能在基础量 ±20% 内生效。

## 5. InfiniSynapse 接入

实际使用完整 Server API，不使用比赛页面的简化 `/v1/query` 示例：

1. 生成 `taskId`、`connId`。
2. `POST /api/tools/taskUpload/:taskId?subdir=upload_documents&naming=original` 上传标准化 CSV。
3. `GET /api/ai/events?connId=<uuid>` 建立 SSE。
4. `POST /api/ai/message` 发送 `type=newTask`、文件元数据、任务提示词和 `chatSettings.mode=act`。
5. 消费 `message.partial`、`message.add`、错误通知和 `completion_result`。
6. 完成后调用 `GET /api/ai_task/getTaskWorkspace/:id`，用 `POST /api/ai_task/previewFile` 读取 `analysis_result.json` 和 `report.md`。
7. 任务超过 180 秒则超时并保留本地结果。

提示词要求 Agent 严格生成以下 JSON 字段：`executive_summary`、`key_findings`、`dish_recommendations`、`action_items`、`limitations`。非法或超范围结果转为 `PARTIAL`，不能覆盖本地基础建议。

## 6. 业务 API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 健康检查，不泄露密钥 |
| GET | `/api/demo` | 演示数据摘要 |
| GET | `/api/template.csv` | 下载上传模板 |
| POST | `/api/datasets/validate` | 校验文件、返回预览和摘要 |
| POST | `/api/analyses` | 创建演示或上传数据分析 |
| GET | `/api/analyses/{id}` | 轮询任务状态与结果 |
| POST | `/api/analyses/{id}/scenarios` | 下雨、客流、预算情景模拟 |
| GET | `/api/analyses/{id}/report` | 下载 Markdown 报告 |
| GET | `/api/analyses/{id}/downloads/{format}` | 下载 Markdown 或 JSON |

状态流转：`VALIDATING → COMPUTING_BASELINE → UPLOADING → CONNECTING → ANALYZING → READING_RESULTS → COMPLETED`；异常状态为 `PARTIAL`、`FAILED`、`TIMED_OUT`。前端每两秒轮询，终止状态停止轮询。

## 7. 页面与演示流程

- 首页：一句话价值、演示数据按钮、上传入口、减少浪费/降低成本/避免售罄三项价值。
- 数据确认：上传、字段校验、记录预览、模板下载。
- 分析工作台：损耗成本、损耗率、售罄率、预计节省、损耗排行、星期柱状图、AI 发现和 `taskId`。
- 明日计划：原计划、建议备餐、调整量、原因和风险。
- 情景模拟：下雨、客流 +20%、预算 -10%。
- 报告：Markdown 和 JSON 下载。

60 秒 Demo 台词：

> 这是惜食智备。食堂每天最难的问题不是没有数据，而是不知道明天该备多少。点击演示数据，系统先算出当前浪费了多少钱，再由 InfiniSynapse 找出哪些菜长期多备、哪些菜容易售罄。这里给出明日每道菜的调整量和原因：预计少浪费 36 份、节省 427 元。下雨时点一下情景模拟，牛肉面的备餐建议会自动变化。最后可以把行动清单下载给明天的厨房负责人。

## 8. 测试与上线验收

- 正常 CSV/XLSX、演示数据均通过；缺字段、非法日期、负数、销量大于备餐量、空文件和超限文件均返回明确错误。
- 相同输入产生相同本地基础指标和建议。
- 测试 SSE partial、completion、错误、断线和超时，AI 失败仍展示本地结果。
- 确认 API Key 不在前端包、响应体和日志。
- 页面刷新可恢复任务；375px 宽度下主流程可用。
- 连续十次演示至少九次完成；至少三次真实 InfiniSynapse 调用能在平台后台按 taskId 查到。
- Docker 启动后公网可访问，`/app/storage` 使用持久化磁盘。
