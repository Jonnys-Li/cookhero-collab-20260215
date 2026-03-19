import {
  buildCompatReplanPreview,
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
  const deviation = await fetchBackend(
    `/diet/analysis/deviation?week_start_date=${encodeURIComponent(weekStartDate)}`,
    { authorization }
  )

  if (deviation.status === 401) {
    sendJson(res, 401, deviation.data || { detail: '需要登录' })
    return
  }

  const totalDeviation = Number(deviation.data?.total_deviation || 0)
  sendJson(res, 200, buildCompatReplanPreview(weekStartDate, totalDeviation))
}
