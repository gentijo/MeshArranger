const express = require('express')
const path = require('path')
const packageJson = require('./package.json')

const app = express()
const PORT = Number(process.env.PORT || 3000)
const GATEWAY_BASE = process.env.GATEWAY_BASE || 'http://192.168.8.195:80'
const POLL_MS = Number(process.env.POLL_MS || 1000)
const HEARTBEAT_MS = Number(process.env.HEARTBEAT_MS || 5000)
const UI_VERSION = packageJson.version || 'unknown'

function log(msg) {
  console.log(`[gtwy-webui] ${new Date().toISOString()} ${msg}`)
}

function pickGatewayFromRequest(req) {
  const gatewayFromQuery = req.query && typeof req.query.gateway === 'string' ? req.query.gateway.trim() : ''
  if (gatewayFromQuery) {
    return gatewayFromQuery
  }

  return GATEWAY_BASE
}

function sanitizeGateway(url) {
  if (!url) {
    return GATEWAY_BASE
  }

  const trimmed = String(url).trim()
  if (!trimmed) {
    return GATEWAY_BASE
  }

  const normalized = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`
  return normalized.replace(/\/$/, '')
}

function requestOrigin(req) {
  const direct = req.socket && req.socket.remoteAddress
  const forwarded = req.headers && req.headers['x-forwarded-for']
  return [forwarded, direct]
    .filter(Boolean)
    .map((v) => String(v).split(',')[0].trim())
    .filter(Boolean)
    .join(' / ') || 'unknown'
}

function setNoCache(res) {
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate')
  res.setHeader('Pragma', 'no-cache')
  res.setHeader('Expires', '0')
}

async function gatewayFetch(pathname, gatewayBase) {
  const gw = sanitizeGateway(gatewayBase || GATEWAY_BASE)
  const response = await fetch(`${gw}${pathname}`, {
    headers: {
      'accept': 'application/json',
    },
  })

  const text = await response.text()
  if (!response.ok) {
    throw new Error(`gateway ${pathname} ${response.status}: ${text}`)
  }

  return text ? JSON.parse(text) : {}
}

async function gatewayVersions(gatewayBase) {
  try {
    const versionPayload = await gatewayFetch('/version', gatewayBase)
    return {
      component: versionPayload.component || 'dnet_gtwy',
      version: versionPayload.version || 'unknown',
      service: versionPayload.service || 'dnet_gtwy',
    }
  } catch (_err) {
    return {
      component: 'dnet_gtwy',
      version: 'unreachable',
      service: 'dnet_gtwy',
    }
  }
}

function eventLine(type, payload) {
  return `event: ${type}\n` + `data: ${JSON.stringify(payload)}\n\n`
}

app.use('/api', express.json({ limit: '128kb' }))
app.use(express.static(path.join(__dirname, 'public')))

app.get('/api/events', (req, res) => {
  const gatewayBase = sanitizeGateway(pickGatewayFromRequest(req))
  const who = requestOrigin(req)

  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache, no-transform')
  res.setHeader('Connection', 'keep-alive')
  res.setHeader('Access-Control-Allow-Origin', '*')

  log(`events opened from ${who} gateway=${gatewayBase}`)

  let closed = false
  let lastStatus = ''
  let lastNodes = ''
  let lastGatewayVersion = ''

  const send = (type, payload) => {
    if (closed) {
      return
    }

    try {
      res.write(eventLine(type, payload))
    } catch (_err) {
      closed = true
      clearInterval(poller)
      clearInterval(heartbeat)
    }
  }

  const poll = async () => {
    try {
      const [status, nodes, messages, version] = await Promise.all([
        gatewayFetch('/status', gatewayBase),
        gatewayFetch('/nodes', gatewayBase),
        gatewayFetch('/messages', gatewayBase),
        gatewayVersions(gatewayBase),
      ])

      const versionText = JSON.stringify(version)
      if (versionText !== lastGatewayVersion) {
        lastGatewayVersion = versionText
        send('version', {
          ui: { component: 'gtwy-webui', version: UI_VERSION },
          gateway: version,
        })
      }

      const statusText = JSON.stringify(status)
      if (statusText !== lastStatus) {
        lastStatus = statusText
        send('status', status)
      }

      const nodesText = JSON.stringify(nodes)
      if (nodesText !== lastNodes) {
        lastNodes = nodesText
        send('nodes', nodes)
      }

      if (messages && Array.isArray(messages.messages)) {
        messages.messages.forEach((msg) => {
          send('message', msg)
        })
      }

      send('heartbeat', { ts: Date.now(), connected: true, gateway: gatewayBase })
    } catch (err) {
      send('error', { message: err.message || String(err), gateway: gatewayBase })
      log(`events poll failure gateway=${gatewayBase} err=${err.message || String(err)}`)
    }
  }

  const poller = setInterval(poll, Math.max(250, POLL_MS))
  const heartbeat = setInterval(() => send('heartbeat', { ts: Date.now(), gateway: gatewayBase }), HEARTBEAT_MS)

  req.on('close', () => {
    closed = true
    clearInterval(poller)
    clearInterval(heartbeat)
    log(`events closed from ${who} gateway=${gatewayBase}`)
    try {
      res.end()
    } catch (_err) {
      // no-op
    }
  })

  send('welcome', { status: 'connected', gateway: gatewayBase, ui_version: UI_VERSION })
  poll()
})

app.get('/api/status', async (_req, res) => {
  const gatewayBase = sanitizeGateway(pickGatewayFromRequest(_req))
  try {
    setNoCache(res)
    const payload = await gatewayFetch('/status', gatewayBase)
    res.json(payload)
  } catch (err) {
    log(`status poll from ${requestOrigin(_req)} gateway=${gatewayBase} failed: ${err.message || String(err)}`)
    res.status(502).json({ status: 'error', error: err.message || String(err) })
  }
})

app.get('/api/nodes', async (_req, res) => {
  const gatewayBase = sanitizeGateway(pickGatewayFromRequest(_req))
  try {
    setNoCache(res)
    const payload = await gatewayFetch('/nodes', gatewayBase)
    res.json(payload)
  } catch (err) {
    log(`nodes poll from ${requestOrigin(_req)} gateway=${gatewayBase} failed: ${err.message || String(err)}`)
    res.status(502).json({ status: 'error', error: err.message || String(err) })
  }
})

app.get('/api/messages', async (_req, res) => {
  const gatewayBase = sanitizeGateway(pickGatewayFromRequest(_req))
  try {
    setNoCache(res)
    const payload = await gatewayFetch('/messages', gatewayBase)
    res.json(payload)
  } catch (err) {
    log(`messages poll from ${requestOrigin(_req)} gateway=${gatewayBase} failed: ${err.message || String(err)}`)
    res.status(502).json({ status: 'error', error: err.message || String(err) })
  }
})

app.get('/api/version', async (_req, res) => {
  const gatewayBase = sanitizeGateway(pickGatewayFromRequest(_req))
  try {
    setNoCache(res)
    const gateway = await gatewayVersions(gatewayBase)
    res.json({
      status: 'ok',
      ui: {
        component: 'gtwy-webui',
        version: UI_VERSION,
      },
      gateway,
      gatewayBase,
    })
  } catch (err) {
    log(`version fetch failed gateway=${gatewayBase} from ${requestOrigin(_req)} err=${err.message || String(err)}`)
    res.status(502).json({
      status: 'error',
      ui: { component: 'gtwy-webui', version: UI_VERSION },
      gateway: { component: 'dnet_gtwy', version: 'unknown', service: 'dnet_gtwy' },
      gatewayBase,
      error: err.message || String(err),
    })
  }
})

app.get('/', (_req, res) => {
  setNoCache(res)
  res.sendFile(path.join(__dirname, 'public', 'index.html'))
})

app.listen(PORT, () => {
  log(`Gtwy WebUI listening on http://localhost:${PORT}`)
  log(`Default gateway target: ${GATEWAY_BASE}`)
  log(`WebUI version: ${UI_VERSION}`)
})
