const express = require('express')
const path = require('path')

const app = express()
const PORT = Number(process.env.PORT || 3000)
const GATEWAY_BASE = process.env.GATEWAY_BASE || 'http://192.168.137.2:8080'
const POLL_MS = Number(process.env.POLL_MS || 1000)
const HEARTBEAT_MS = Number(process.env.HEARTBEAT_MS || 5000)

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

  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed
  }

  return `http://${trimmed}`
}

app.use('/api', express.json({ limit: '128kb' }))
app.use(express.static(path.join(__dirname, 'public')))

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

function eventLine(type, payload) {
  return `event: ${type}\n` + `data: ${JSON.stringify(payload)}\n\n`
}

app.get('/api/events', (req, res) => {
  const gatewayBase = sanitizeGateway(pickGatewayFromRequest(req))

  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache, no-transform')
  res.setHeader('Connection', 'keep-alive')
  res.setHeader('Access-Control-Allow-Origin', '*')

  let closed = false
  let lastStatus = ''
  let lastNodes = ''

  const send = (type, payload) => {
    if (closed) {
      return
    }

    try {
      res.write(eventLine(type, payload))
    } catch (_err) {
      closed = true
      clearInterval(poller)
    }
  }

  const poll = async () => {
    try {
      const [status, nodes, messages] = await Promise.all([
        gatewayFetch('/status', gatewayBase),
        gatewayFetch('/nodes', gatewayBase),
        gatewayFetch('/messages', gatewayBase),
      ])

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
    } catch (err) {
      send('error', { message: err.message || String(err) })
    }
  }

  const poller = setInterval(poll, Math.max(250, POLL_MS))
  const heartbeat = setInterval(() => send('heartbeat', { ts: Date.now() }), HEARTBEAT_MS)

  req.on('close', () => {
    closed = true
    clearInterval(poller)
    clearInterval(heartbeat)
    try {
      res.end()
    } catch (_err) {
      // no-op
    }
  })

  send('welcome', { status: 'connected', gateway: gatewayBase })
  poll()
})

app.get('/api/status', async (_req, res) => {
  const gatewayBase = sanitizeGateway(pickGatewayFromRequest(_req))
  try {
    const payload = await gatewayFetch('/status', gatewayBase)
    res.json(payload)
  } catch (err) {
    res.status(502).json({ status: 'error', error: err.message || String(err) })
  }
})

app.get('/api/nodes', async (_req, res) => {
  const gatewayBase = sanitizeGateway(pickGatewayFromRequest(_req))
  try {
    const payload = await gatewayFetch('/nodes', gatewayBase)
    res.json(payload)
  } catch (err) {
    res.status(502).json({ status: 'error', error: err.message || String(err) })
  }
})

app.get('/api/messages', async (_req, res) => {
  const gatewayBase = sanitizeGateway(pickGatewayFromRequest(_req))
  try {
    const payload = await gatewayFetch('/messages', gatewayBase)
    res.json(payload)
  } catch (err) {
    res.status(502).json({ status: 'error', error: err.message || String(err) })
  }
})

app.get('/', (_req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'))
})

app.listen(PORT, () => {
  console.log(`Gtwy WebUI listening on http://localhost:${PORT}`)
  console.log(`Gateway target: ${GATEWAY_BASE}`)
})
