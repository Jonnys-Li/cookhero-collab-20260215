import {
  buildCompatReplanApply,
  ensureMethod,
  requireAuth,
  sendJson,
} from '../../../_lib/compat.js'

export default async function handler(req, res) {
  if (!ensureMethod(req, res, ['POST'])) return

  if (!requireAuth(req, res)) return

  sendJson(res, 200, buildCompatReplanApply())
}
