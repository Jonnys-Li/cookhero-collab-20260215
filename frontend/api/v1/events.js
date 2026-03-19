import { ensureMethod, sendJson } from '../_lib/compat.js'

export default async function handler(req, res) {
  if (!ensureMethod(req, res, ['POST'])) return

  res.statusCode = 204
  res.end()
}
