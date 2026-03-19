const BACKEND_BASE =
  process.env.BACKEND_BASE || 'https://cookhero-collab-20260215.onrender.com/api/v1'

function normalizeBase(base) {
  return base.endsWith('/') ? base.slice(0, -1) : base
}

function normalizeDate(date) {
  return date.toISOString().slice(0, 10)
}

export function weekStartFromInput(value) {
  if (value && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value

  const today = new Date()
  const local = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()))
  const day = (local.getUTCDay() + 6) % 7
  local.setUTCDate(local.getUTCDate() - day)
  return normalizeDate(local)
}

export function weekEndFromStart(weekStartDate) {
  const start = new Date(`${weekStartDate}T00:00:00Z`)
  start.setUTCDate(start.getUTCDate() + 6)
  return normalizeDate(start)
}

export function sendJson(res, status, payload) {
  res.statusCode = status
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(payload))
}

export function getAuthHeader(req) {
  const value = req.headers.authorization || req.headers.Authorization
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

export function ensureMethod(req, res, allowedMethods) {
  if (allowedMethods.includes(req.method || 'GET')) return true
  res.setHeader('Allow', allowedMethods.join(', '))
  sendJson(res, 405, { detail: 'Method Not Allowed' })
  return false
}

export function requireAuth(req, res) {
  const authorization = getAuthHeader(req)
  if (authorization) return authorization
  sendJson(res, 401, { detail: '需要登录' })
  return null
}

export async function fetchBackend(path, { method = 'GET', authorization, body } = {}) {
  const headers = {}
  if (authorization) headers.Authorization = authorization
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(`${normalizeBase(BACKEND_BASE)}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  return {
    ok: response.ok,
    status: response.status,
    data,
  }
}

export function buildCompatReplanPreview(weekStartDate, totalDeviation = 0) {
  return {
    week_start_date: weekStartDate,
    affected_days: [],
    before_summary: {
      total_deviation: totalDeviation,
      fallback_mode: 'legacy_backend',
      fallback_message: '当前线上后端还没补齐新版自动调整接口，本周先保持现有计划不变。',
    },
    after_summary: {
      applied_shift: 0,
    },
    meal_changes: [],
    write_conflicts: [],
    compensation_summary: null,
    compensation_suggestions: [],
  }
}

export function buildCompatReplanApply() {
  return {
    action: 'compatibility_noop',
    applied_count: 0,
    updated_meal_ids: [],
    write_conflicts: [
      {
        reason: '当前线上兼容模式下，自动改后面几天计划暂时不可用。',
      },
    ],
  }
}

export function buildCompatShoppingList(weekStartDate) {
  return {
    week_start_date: weekStartDate,
    week_end_date: weekEndFromStart(weekStartDate),
    aggregation_basis: 'legacy_backend_unavailable',
    item_count: 0,
    items: [],
    matched_items: [],
    unmatched_dishes: [],
    grouped_ingredients: [],
  }
}

export function buildNutritionSnapshot(weeklySummary, deviation) {
  const totalCalories = Number(weeklySummary?.total_calories || 0)
  const totalProtein = Number(weeklySummary?.total_protein || 0)
  const totalFat = Number(weeklySummary?.total_fat || 0)
  const totalCarbs = Number(weeklySummary?.total_carbs || 0)
  const executionRate = Number(deviation?.execution_rate || 0)
  const totalDeviation = Number(deviation?.total_deviation || 0)

  return {
    title: '本周饮食复盘',
    summary:
      totalDeviation > 0
        ? `本周累计比计划多约 ${Math.abs(totalDeviation)} kcal，接下来优先稳住节奏。`
        : totalDeviation < 0
          ? `本周累计比计划少约 ${Math.abs(totalDeviation)} kcal，接下来优先规律吃够。`
          : '本周整体和计划接近，继续保持当前节奏。',
    total_calories: totalCalories,
    total_protein: totalProtein,
    total_fat: totalFat,
    total_carbs: totalCarbs,
    deviation: totalDeviation,
    execution_rate: executionRate,
  }
}

export function buildThreeLinePayload(weeklySummary, days = 14, endDateInput = null) {
  const endDate = endDateInput && /^\d{4}-\d{2}-\d{2}$/.test(endDateInput)
    ? new Date(`${endDateInput}T00:00:00Z`)
    : new Date()
  const utcEnd = new Date(Date.UTC(endDate.getUTCFullYear(), endDate.getUTCMonth(), endDate.getUTCDate()))
  const dailyBudgetTimeline = Array.isArray(weeklySummary?.daily_budget_timeline)
    ? weeklySummary.daily_budget_timeline
    : []
  const dailyData = weeklySummary?.daily_data || {}
  const defaultGoal =
    weeklySummary?.effective_goal ??
    weeklySummary?.base_goal ??
    weeklySummary?.today_budget?.effective_goal ??
    1800

  const rows = []
  for (let index = days - 1; index >= 0; index -= 1) {
    const current = new Date(utcEnd)
    current.setUTCDate(current.getUTCDate() - index)
    const date = normalizeDate(current)
    const timelineEntry = dailyBudgetTimeline.find((entry) => entry?.date === date) || null
    const actualCalories = Number(dailyData?.[date]?.calories || 0)
    const effectiveGoal = Number(timelineEntry?.effective_goal ?? defaultGoal)
    const goalSource = timelineEntry?.goal_source || weeklySummary?.goal_source || 'default1800'
    const emotionExemption = timelineEntry?.emotion_exemption || null
    rows.push({
      date,
      intake_calories: actualCalories,
      base_goal: Number(timelineEntry?.base_goal ?? weeklySummary?.base_goal ?? defaultGoal),
      effective_goal: effectiveGoal,
      deviation_calories: actualCalories - effectiveGoal,
      goal_source: goalSource,
      goal_source_changed: false,
      emotion_exemption_active: Boolean(
        emotionExemption?.active ?? emotionExemption?.is_active
      ),
      emotion_exemption: emotionExemption,
    })
  }

  const goalSourceChanges = []
  for (let index = 1; index < rows.length; index += 1) {
    if (rows[index].goal_source !== rows[index - 1].goal_source) {
      rows[index].goal_source_changed = true
      goalSourceChanges.push({
        date: rows[index].date,
        from: rows[index - 1].goal_source,
        to: rows[index].goal_source,
      })
    }
  }

  return {
    start_date: rows[0]?.date || normalizeDate(utcEnd),
    end_date: rows[rows.length - 1]?.date || normalizeDate(utcEnd),
    days,
    goal_context: weeklySummary?.goal_context || null,
    estimate_context: weeklySummary?.estimate_context || null,
    daily: rows,
    series: {
      intake: rows.map((row) => ({ date: row.date, value: row.intake_calories })),
      goal: rows.map((row) => ({ date: row.date, value: row.effective_goal })),
      deviation: rows.map((row) => ({ date: row.date, value: row.deviation_calories })),
    },
    goal_source_changes: goalSourceChanges,
  }
}
