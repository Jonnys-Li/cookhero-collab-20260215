# 情感安抚场景：自动饮食预算调整 MCP 接入指南

本指南用于把内置的 MCP 端点接入到自定义 Agent，实现「先安抚，再自动调整当天预算」的稳定演示流程。

## 1. 环境变量

在后端环境中配置：

```bash
MCP_DIET_SERVICE_KEY=cookhero-mcp-demo-key-v1
```

> 该密钥用于 `POST /api/v1/mcp/diet-adjust` 服务端鉴权（Header：`X-MCP-Service-Key`）。

## 2. MCP 默认内置（无需手工添加）

当前版本会在服务启动时自动注册系统 MCP：

- MCP 名称：`diet_auto_adjust`
- Endpoint：`https://cookhero-collab-20260215.onrender.com/api/v1/mcp/diet-adjust`
- Header：`X-MCP-Service-Key: ${MCP_DIET_SERVICE_KEY}`

只要后端环境变量 `MCP_DIET_SERVICE_KEY` 可用，`mcp_diet_auto_adjust_*` 工具会自动出现在 Agent 工具列表中。
无需再到「设置 -> MCP 配置」手动添加。

## 3. 新建自定义 Agent（可选）

建议创建：

- Agent 名称：`emotion_budget_guard`
- 显示名称：`情绪预算守护`
- 工具勾选：
  - `mcp_diet_auto_adjust_get_today_budget`
  - `mcp_diet_auto_adjust_auto_adjust_today_budget`
  - `datetime`（可选）

推荐系统提示词（可直接使用）：

```text
你是情绪预算守护助手。用户表达“吃多了、内疚、焦虑、自责”时，先共情安抚，再给低风险行动建议。

流程：
1) 先简短共情，不评判；
2) 调用 mcp_diet_auto_adjust_get_today_budget 查看当天预算状态；
3) 根据语气判断 emotion_level（low/medium/high），调用 mcp_diet_auto_adjust_auto_adjust_today_budget；
4) 向用户解释本次调整结果（requested/applied/capped/effective_goal）；
5) 明确禁止极端补偿行为（绝食、过度运动、自责惩罚）。

输出风格：
- 中文简洁 Markdown
- 结构：情绪回应 + 今日行动 + 预算说明 + 下一步提醒
```

## 4. MCP 工具说明

该端点提供两个工具：

1. `get_today_budget`
   - 参数：`user_id`（必填）、`target_date`（可选，`YYYY-MM-DD`）
2. `auto_adjust_today_budget`
   - 参数：`user_id`（必填）、`emotion_level`（`low|medium|high`）、`reason`（可选）、`target_date`（可选）
   - 映射规则：`low -> 50`，`medium -> 100`，`high -> 150`（kcal）

## 5. 手工验收

1. 启动后进入 Agent 页面，确认工具区域提示“系统内置 MCP 已启用（diet_auto_adjust）”
2. 在聊天中选择自定义 Agent `emotion_budget_guard`（可选）
3. 输入：`我今天吃多了很内疚`
4. 观察：先安抚 -> 调预算 -> 返回新预算说明
5. 在饮食管理页面核对当天有效预算变化
6. 把 `MCP_DIET_SERVICE_KEY` 改错，确认 MCP 报鉴权错误但系统主流程不崩溃（自动回退本地能力）
