# 本地记忆（部署与 MCP 必要配置）

> 用于避免重复确认同一组演示配置；默认按本文件执行。

## 固定地址

- 前端（Vercel）：`https://frontend-one-gray-39.vercel.app`
- 后端（Render）：`https://cookhero-collab-20260215.onrender.com`
- MCP Endpoint：`https://cookhero-collab-20260215.onrender.com/api/v1/mcp/diet-adjust`

## MCP 固定配置

- MCP 名称：`diet_auto_adjust`
- 认证 Header 名称：`X-MCP-Service-Key`
- 服务密钥环境变量：`MCP_DIET_SERVICE_KEY`
- 当前演示值：`cookhero-mcp-demo-key-v1`
- 默认行为：后端启动时自动注册 `diet_auto_adjust`（无需前端手动添加）

## 自定义 Agent 推荐模板

- Agent 名称：`emotion_budget_guard`
- 工具：
  - `mcp_diet_auto_adjust_get_today_budget`
  - `mcp_diet_auto_adjust_auto_adjust_today_budget`
  - `datetime`（可选）

## 说明

- 上述演示密钥已写入 `render.yaml`。
- 生产环境应改为高强度随机密钥并定期轮换。

## 协作默认动作

- 默认在任务完成并通过必要校验后，执行 `git push origin main`。
- 若用户明确要求“不 push”或“先别提交”，则以用户要求为准。

## 自动化配置记忆（新增）

- 自动同步脚本：`scripts/sync-render-env.sh`
- 自动同步工作流：`.github/workflows/cloud-config-sync.yml`
- 需要一次性配置的 GitHub Secrets：
  - `MCP_DIET_SERVICE_KEY`
  - `RENDER_API_KEY`
  - `RENDER_SERVICE_ID`（推荐）或 `RENDER_SERVICE_NAME=cookhero-backend`
  - `PROD_BACKEND_URL=https://cookhero-collab-20260215.onrender.com`
- 烟测会读取 `MCP_DIET_SERVICE_KEY` 做 `diet-adjust` 端点可用性验证。

## 三系统协作默认策略（新增）

- 主链路默认：主聊天一句话触发三系统协作（识别→规划→共情），未勾选节点自动跳过。
- 编排默认：按用户已勾选 Agent/工具做条件串行；支持用户自定义 Subagent 插入链路。
- 可视化默认：必须在聊天气泡展示“协作时间线卡 + 智能推荐总卡”。
- 超时默认：`10s` 后仅转建议模式（`timeout_suggest_only`），不自动写库。
- 写入默认：所有写入型动作必须由用户显式点击触发（预算调整/计划餐次）。
- 周进度默认：支持自然语言触发（如“看本周进度”），返回周摘要与偏差结果块。
