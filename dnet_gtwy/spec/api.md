# Gateway REST API v1

Base URL: `http://mesh-gateway.local:8080`

## `GET /health`

Response:

```json
{
  "ok": true,
  "service": "mesh-gateway",
  "version": "1.0.0"
}
```

## `POST /command`

Request:

```json
{
  "cmd": "status",
  "args": {}
}
```

Response:

```json
{
  "ok": true,
  "result": {
    "uptime_ms": 12345,
    "ip": "192.168.137.2",
    "hostname": "mesh-gateway.local"
  }
}
```

## `POST /echo`

Request:

```json
{
  "message": "hello"
}
```

Response:

```json
{
  "ok": true,
  "echo": "hello"
}
```
