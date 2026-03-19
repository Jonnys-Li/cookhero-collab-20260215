import {
  buildThreeLinePayload,
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

  const days = Math.min(14, Math.max(7, Number(req.query.days || 14)))
  const endDate = typeof req.query.end_date === 'string' ? req.query.end_date : null

  let weekStartDate = null
  if (endDate && /^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    const date = new Date(`${endDate}T00:00:00Z`)
    date.setUTCDate(date.getUTCDate() - 6)
    weekStartDate = date.toISOString().slice(0, 10)
  } else {
    weekStartDate = weekStartFromInput(null)
  }

  const weeklySummary = await fetchBackend(
    `/diet/analysis/weekly?week_start_date=${encodeURIComponent(weekStartDate)}`,
    { authorization }
  )
  if (!weeklySummary.ok) {
    sendJson(res, weeklySummary.status, weeklySummary.data || { detail: '趋势数据获取失败' })
    return
  }

  sendJson(res, 200, buildThreeLinePayload(weeklySummary.data, days, endDate))
}
