import {
  buildCompatShoppingList,
  ensureMethod,
  requireAuth,
  sendJson,
  weekStartFromInput,
} from '../../_lib/compat.js'

export default async function handler(req, res) {
  if (!ensureMethod(req, res, ['GET'])) return

  if (!requireAuth(req, res)) return

  const weekStartDate = weekStartFromInput(req.query.week_start_date)
  sendJson(res, 200, buildCompatShoppingList(weekStartDate))
}
