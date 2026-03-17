# Wave 3 Acceptance: Photo-First Diet Logging

本清单用于第 3 周目标「拍照优先记录流」的人工验收与线上 smoke 增补项设计。

目标用户路径（Happy Path）：

1. 登录后打开 `/diet`
2. 点击“拍照记录”
3. 选择图片（食物照片）
4. 得到识别明细（食物项 + 估算营养）
5. 点击“确认写入”
6. 刷新后，当日 `logs` 出现该餐次记录

兜底路径（Recognition Fallback）：

- 识别失败或未识别到清晰食物时：允许用户手工补 1 条（至少 `food_name`），并成功写入，刷新后可见

---

## 1) 人工验收清单（UI）

### 1.1 拍照优先记录（成功识别）

- 前置：
  - 已登录
  - 生产环境具备可用的视觉能力（后端需启用 `VISION_API_KEY` 或可用的 `LLM_API_KEY`）
- 操作：
  - 打开 `/diet`
  - 点击“拍照记录”
  - 选择 1 张食物照片（建议清晰、包含常见菜品）
  - 等待识别完成，展示“识别明细”
  - 点击“确认写入”
  - 刷新页面或重新选择当天日期
- 预期：
  - 识别明细展示至少 1 条食物项（含名称；营养字段可部分缺失）
  - 写入成功后当日 `logs` 列表新增记录，能看到对应餐次与食物项
  - 反复刷新不丢失（数据持久化成功）

### 1.2 识别失败兜底（手工补 1 条）

- 操作：
  - 重复 1.1 但使用“非食物图片”或在网络较差时触发识别失败
  - 页面出现错误提示或“未识别到清晰食物”的提示
  - 在兜底表单中手工补 1 条（至少填 `food_name`，可选填分量/热量）
  - 点击“确认写入”
  - 刷新页面
- 预期：
  - 即使识别失败，也能完成写入
  - 当日 `logs` 中可见手工补录的那条 item

---

## 2) API 验收点（便于联调/排障）

> 注：以下是推荐的最小契约，用于让 smoke 能稳定验证“识别 -> 确认写入 -> 刷新可见”。

- 识别（无副作用，parse-only）：
  - `POST /api/v1/diet/logs/parse` (auth required)
  - Request: `{ images: [{ data: <base64>, mime_type }], text?: string }`
  - Response: `{ items: [...], meal_type?: string, message?: string, used_vision?: boolean }`
  - 约束：不写库
- 写入：
  - `POST /api/v1/diet/logs` (auth required)
  - Request: `{ log_date, meal_type, items, notes? }`
- 刷新验证：
  - `GET /api/v1/diet/logs?log_date=YYYY-MM-DD` (auth required)

兼容现有端点（如 parse-only 暂未提供）：

- `POST /api/v1/diet/meals/recognize-image` (auth required, no side effects)

---

## 3) 线上 Smoke 增补项（脚本设计）

目标：在 `scripts/smoke-prod.sh` 增加一个可选项，用于验证“拍照优先记录流”。

约束与策略：

- 默认不开启，不影响现有 CI/定时 smoke（防止未上线时误报）
- 手工严格验收时开启：
  - `SMOKE_STRICT=true`
  - `SMOKE_DIET_PHOTO=true`
  - 建议提高超时：`REQUEST_TIMEOUT_SECONDS=90`（视觉识别 + Render 冷启动）
- 图片输入：
  - 若 `SMOKE_PHOTO_IMAGE_B64` 未提供，脚本可用一个极小的占位 PNG 做“连通性”验证
  - 若要验证“识别确实产出 items”，建议在 secrets 中提供一张真实食物照片的 base64：
    - `SMOKE_PHOTO_IMAGE_B64`
    - `SMOKE_PHOTO_MIME_TYPE`（例如 `image/jpeg`）

脚本 pass 条件建议：

- parse/recognize 端点可用（200），返回 JSON 且包含数组字段（`items` 或 `dishes`）
- 无论识别是否产出 items，都能完成写入（识别为空则走手工兜底写入）
- 写入后 `GET /diet/logs?log_date=today` 能查到本次写入的 marker（用 `notes` 做唯一标识）

