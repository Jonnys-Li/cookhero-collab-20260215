import {
  buildNutritionSnapshot,
  ensureMethod,
  fetchBackend,
  requireAuth,
  sendJson,
  weekStartFromInput,
} from '../../../_lib/compat.js'

export default async function handler(req, res) {
  if (!ensureMethod(req, res, ['GET'])) return

  const authorization = requireAuth(req, res)
  if (!authorization) return

  const weekStartDate = weekStartFromInput(req.query.week_start_date)
  const weeklySummary = await fetchBackend(
    `/diet/analysis/weekly?week_start_date=${encodeURIComponent(weekStartDate)}`,
    { authorization }
  )
  if (!weeklySummary.ok) {
    sendJson(res, weeklySummary.status, weeklySummary.data || { detail: '周汇总获取失败' })
    return
  }

  const deviation = await fetchBackend(
    `/diet/analysis/deviation?week_start_date=${encodeURIComponent(weekStartDate)}`,
    { authorization }
  )
  if (!deviation.ok) {
    sendJson(res, deviation.status, deviation.data || { detail: '偏差分析获取失败' })
    return
  }

  sendJson(res, 200, {
    weekly_summary: weeklySummary.data,
    deviation: deviation.data,
    goal_context: weeklySummary.data?.goal_context || null,
    compensation_suggestion: null,
    next_meal_correction: null,
    nutrition_snapshot: buildNutritionSnapshot(weeklySummary.data, deviation.data),
  })
}
