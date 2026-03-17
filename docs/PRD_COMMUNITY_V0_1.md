# 社区模块 PRD v0.1（共情互助广场强化版）

- 项目：CookHero（cookhero-collab-20260215）
- 模块：社区（Community）
- 版本：v0.1
- 日期：2026-03-17
- Owner：PM/架构协作（占位）

## 1. 目标 / 范围 / 不做什么

### 1.1 目标（Goals）

- 让“需要支持”的帖子更快得到回复，并提升回复质量（温和、具体、可执行）。
- 降低用户打卡发布与互动门槛，提升持续打卡与记录的依从性。
- 让社区与 Diet/Agent 形成弱耦合闭环：社区支持促进回到计划与记录，而不把社区做成独立孤岛。

### 1.2 范围（In Scope）

- P0：内容安全底线补齐（发帖/评论写入前安全检查）
- P0：信息流排序升级（新增 need_support 视图，不替换默认时间流）
- P0：互动质量增强（快速支持短句 chips）
- P0：关键事件埋点与验收指标（复用 /events）
- P1：Diet -> Community 一键打卡入口（复用周摘要）
- P1：AI 辅助体验打磨（复制并编辑、明确降级）

### 1.3 不做什么（Out of Scope）

- 私信、关注、复杂社交关系链
- 审核后台与复杂风控策略（本期仅保证写入前底线）
- 电商化（下单、比价、商家入驻）
- 复杂内容推荐系统（先做可解释的规则排序）
- P2（建议延期）：共情反应 types 与 reaction_summary 展示（避免本期协议/展示复杂度）

## 2. 背景与定位

CookHero 的社区不是泛论坛，而是“打卡互助广场 + 共情支持”，服务于饮食健康共情系统的执行闭环。当前 MVP 已具备：

- 发帖与评论（可匿名）
- 标签与情绪筛选
- 点赞
- 帖子可附带营养周摘要（nutrition_snapshot）
- AI 辅助（tags、reply、card、polish），并通过 capabilities 探针降级

本 PRD 的目标是把社区从“内容展示”升级为“帮助用户更快得到有效支持，并更容易回到可执行的饮食节奏”的核心增长杠杆。

## 3. 北极星指标与成功度量

### 3.1 北极星指标

- “需要支持”帖子发出后 30 分钟内被评论率

### 3.2 辅助指标（建议埋点统计）

- 首条有效回复时长（TTFR）：发帖到第一条评论的时间
- 发帖后 24 小时内回到 Diet 记录/计划的转化率
- Diet -> Community 打卡转化率

## 4. 关键用户流程与验收标准（可直接转为 QA 用例）

### 4.1 流程 A：用户发一条打卡/求助帖

步骤：

1. 进入社区 feed（/community 或 /agent/community）
2. 点击“发帖”打开 CreatePostModal
3. 输入内容，选择 mood、tags，可选匿名、可选附带周摘要、可选上传图片
4. 提交发布
5. 新帖子出现在 feed，点击进入详情页可见正文与摘要卡片

验收标准：

- 发帖成功后 feed 能立即看到该帖子，且 post_id 可打开详情页。
- 选择“附带周摘要”时，详情页渲染摘要卡片，字段缺失时不崩溃。
- 上传图片超限或格式不支持时，前端提示明确，后端返回 4xx/5xx 时前端提示可理解。
- 发帖内容包含明显攻击性/注入/违规信息时，写入被拒绝并返回明确 4xx，且帖子不落库。

### 4.2 流程 B：用户浏览 need_support 信息流并进行互动

步骤：

1. 进入社区 feed
2. 切换到 need_support tab
3. 看到优先展示无评论、带求助类 tag 的帖子
4. 打开帖子详情页
5. 使用快速支持短句 chips 生成一段回复，编辑后发送评论

验收标准：

- need_support 下，comment_count=0 的帖子优先展示。
- 求助类 tag（焦虑、想放弃、暴食后自责、求建议）在 need_support 下排序更靠前。
- chips 点击后评论输入框自动填充，用户仍可编辑。
- 评论成功后，详情页评论列表追加新评论，帖子 comment_count +1。
- 评论内容包含明显违规信息时，写入被拒绝并返回明确 4xx，且评论不落库。

### 4.3 流程 C：AI 辅助生成（润色、建议回复、共情卡片）

步骤：

1. 发帖时点击“AI 润色”
2. 或在帖子详情点击“AI 生成回复”
3. 或在 feed/详情展开“AI 共情卡片”

验收标准：

- capabilities 不支持相应 mode 时，前端提示“后端升级中”并降级，不阻断手动发布/评论。
- AI 生成内容不可自动发送，必须经过用户确认（只填入输入框或提供复制并编辑）。
- AI 生成失败时提示可理解，不影响继续手动输入。

### 4.4 流程 D：Diet -> Community 一键打卡（带周摘要）

步骤：

1. 用户在 Diet 页查看本周情况
2. 点击“一键打卡到社区”
3. 弹出发帖弹窗，默认勾选“附带周摘要”，并预置一段模板文字
4. 用户补充一句感受并发布

验收标准：

- 从 Diet 页可以直达发帖弹窗并成功发布。
- 发布内容带周摘要时，社区详情页能展示摘要卡片。
- 该功能可在无图片、无 AI 的情况下稳定工作。

## 5. 依赖的后端 API 与前端页面

### 5.1 后端 API（/api/v1）

既有接口：

- GET /community/feed
- POST /community/posts
- GET /community/posts/{post_id}
- DELETE /community/posts/{post_id}
- POST /community/posts/{post_id}/comments
- DELETE /community/comments/{comment_id}
- POST /community/posts/{post_id}/reactions/toggle（本期不扩展，仅保留 like）
- POST /community/ai/suggest
- GET /meta/capabilities
- POST /events

本期建议变更：

- GET /community/feed 新增 query：sort=latest|need_support|hot（默认 latest，兼容旧调用）
- POST /community/posts 新增行为：写入前对 content 执行 check_message_security
- POST /community/posts/{post_id}/comments 新增行为：写入前对 content 执行 check_message_security

### 5.2 前端页面/组件

页面路由：

- /community、/agent/community：社区 feed
- /community/:id、/agent/community/:id：帖子详情
- /diet、/agent/diet：饮食管理（新增一键打卡入口）

关键文件（实现点）：

- frontend/src/pages/community/CommunityFeed.tsx
- frontend/src/pages/community/CommunityPostDetail.tsx
- frontend/src/pages/community/CreatePostModal.tsx
- frontend/src/services/api/community.ts
- frontend/src/services/api/meta.ts
- frontend/src/services/api/events.ts
- frontend/src/pages/diet/DietManagement.tsx

后端关键文件（实现点）：

- app/api/v1/endpoints/community.py
- app/community/service.py
- app/community/database/repository.py
- app/api/v1/endpoints/meta.py
- app/api/v1/endpoints/events.py

## 6. P0 详细设计

### 6.1 发帖/评论写入前安全检查补齐

问题：

- 当前社区 AI suggest 流程会对内容做安全检查，但发帖与评论写入前未统一执行，可能让羞辱性/恶意内容进入广场。

方案：

- 在 create_post 与 add_comment 写入前调用 check_message_security(payload.content, request)。
- 对被拒绝内容返回 4xx，并提供可理解 detail。

验收：

- 违规内容不落库。
- 合法内容通过率不下降。

### 6.2 信息流新增 need_support tab（规则可解释）

前端：

- feed 顶部加入 tab：最新 / 需要支持。
- need_support tab 仍允许 tag/mood 筛选。

后端：

- /community/feed 增加 sort 参数。
- need_support 排序建议：comment_count asc, created_at desc，并对求助类 tag 做加权靠前。

验收：

- “无评论 + 求助标签” 的帖子在 need_support 下明显靠前。

### 6.3 互动质量增强（快速支持短句 chips）

前端：

- 在帖子详情评论区加入 chips，点击填入输入框，可编辑再发送。
- chips 文案以温和、具体、可执行为准，不使用指责性词汇。

验收：

- chips 不影响手动输入。
- 发送后评论列表与计数一致。

### 6.4 埋点（/events）与数据闭环

说明：

- 前端已有 trackEvent，后端已有 /events 写入与 props 脱敏（mask token/secret 等）。
- 所有事件上报必须“失败吞掉”，不得影响主流程。
- props 建议控制体积，避免携带正文内容、图片 base64、token 等敏感信息。

事件字典：

| event_name | 触发时机 | props（建议） |
| --- | --- | --- |
| community_feed_viewed | feed 首次加载成功或筛选条件变化后成功渲染 | sort, tag, mood, count, is_agent_mode |
| community_need_support_tab_clicked | 点击“需要支持”tab | tag, mood, is_agent_mode |
| community_post_opened | 从 feed 进入帖子详情 | post_id, from_sort, is_agent_mode |
| community_post_created | 发帖成功后 | is_anonymous, mood, tag_count, has_images, has_weekly_summary, source(diet_entry/manual), is_agent_mode |
| community_quick_reply_chip_used | 点击回复 chips | post_id, chip_id, is_agent_mode |
| community_comment_created | 评论发送成功后 | post_id, is_anonymous, length, used_ai_reply(boolean), is_agent_mode |
| community_ai_used | 调用 AI 建议成功或失败后 | mode(polish/reply/card/tags), success, latency_ms, is_agent_mode |

## 7. P1 详细设计（Week 2）

### 7.1 Diet -> Community 一键打卡入口

方案：

- Diet 页新增入口打开 CreatePostModal。
- 默认勾选附带周摘要，并预置模板文字，用户可编辑。

验收：

- 从 Diet 到发帖闭环打通。
- 发布后带周摘要的帖子在详情页展示正常。

### 7.2 AI 辅助体验打磨（示范与写作辅助）

方案：

- AI reply 仅填入输入框，不自动发送。
- AI card 展示为示范，提供“复制到输入框并编辑”动作。
- capabilities 不支持时显式降级提示。

验收：

- AI 失败不阻断主流程。
- capabilities 缺失时降级提示明确且不闪退。

## 8. 里程碑（按周）与优先级

### Week 1（P0：基础体验与安全）

- 后端：发帖/评论写入前安全检查补齐
- 后端：/community/feed 支持 sort=need_support
- 前端：新增 tab 并接入 sort
- 前端：帖子详情加入快速支持短句 chips
- 埋点：补齐 feed/tab/detail/comment/chips/ai 的关键埋点

交付验收：

- need_support 信息流可用，且规则符合预期
- 发帖/评论安全检查生效
- chips 可用并稳定
- 事件上报失败不影响主流程

### Week 2（P1：闭环与质量提升）

- Diet -> Community 一键打卡入口
- AI 辅助体验打磨：复制并编辑、明确降级
- 本期不做：reaction_type 扩展（延期到 P2）

交付验收：

- Diet 发帖闭环跑通，且带周摘要可展示
- AI 不影响主流程，且失败降级清晰

## 9. 任务拆分（用于分配给前端/后端/测试）

### 后端任务（BE）

- 变更 community endpoints：写入前 check_message_security
- 增加 feed sort 参数与 need_support 排序实现
- 对新增行为补充 pytest 覆盖

### 前端任务（FE）

- CommunityFeed：tab UI + sort 参数透传 + 空态文案 + 埋点
- CommunityPostDetail：快速回复 chips + AI 复制并编辑体验 + 埋点
- DietManagement：新增一键打卡入口复用 CreatePostModal + 埋点

### 测试任务（QA）

- E2E：发帖、筛选、need_support 排序、评论、AI 降级
- 回归：登录态失效、匿名显示、图片上传失败提示
- 安全：违规文本拦截（发帖/评论均覆盖）
- 埋点：关键事件是否触发（可通过 /events/recent 或数据库验证）

## 10. 风险与开放问题

- 内容安全策略严格度：拦截过严可能影响表达，需要逐步调参并通过埋点观察误杀率。
- need_support 排序规则：早期以规则为主，后续再考虑更精细化的质量信号。

