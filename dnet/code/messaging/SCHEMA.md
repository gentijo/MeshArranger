# DistNet Capability Messaging Schema

## Design Targets
- Short broadcast capability advert fits in `<= 205` bytes.
- Long profile is fetched on demand by direct query.
- All messages are JSON objects with short field names.

## Common Envelope
- `v` (int): protocol version, currently `1`
- `t` (str): message type code
- `n` (str): sender node id

## Message Types

### `a` - Short Advertise (broadcast)
Required fields:
- `v`, `t`, `n`
- `h` (str): profile hash/version
- `s` (array[int]): provided `service_id` values (`uint16`)

Example:
```json
{"v":1,"t":"a","n":"d4f5aa10","h":"9c21a7f2","s":[101,102,205]}
```

### `q` - Capability Query
Required fields:
- `v`, `t`, `n`
- `sid` (int): requested service id

Example:
```json
{"v":1,"t":"q","n":"7a11be02","sid":205}
```

### `i` - Query Result (`I_HAVE`)
Required fields:
- `v`, `t`, `n`
- `sid` (int)
- `p` (array[str]): provider node ids

Example:
```json
{"v":1,"t":"i","n":"d4f5aa10","sid":205,"p":["d4f5aa10","e0ab9912"]}
```

### `g` - Get Profile
Required fields:
- `v`, `t`, `n`
- `to` (str): requested target node id

Example:
```json
{"v":1,"t":"g","n":"7a11be02","to":"d4f5aa10"}
```

### `p` - Full Profile (direct response)
Required fields:
- `v`, `t`, `n`
- `h` (str)
- `s` (array[object]): full service records, each with at least `sid`

Optional fields:
- `name` (str), `role` (str), `fw` (str), `meta` (object)

Example:
```json
{"v":1,"t":"p","n":"d4f5aa10","h":"9c21a7f2","name":"imu-node-1","role":"sensor","fw":"0.7.4","s":[{"sid":205,"name":"core/attitude:1","class":"sensor","rate_hz":100}],"meta":{"mount":"front"}}
```

## Sample Node Profile: Servo + Distance Sensor

Node advertises two services from the same hardware node:
- `sid: 1201` -> `act/servo.set_angle:1`
- `sid: 2201` -> `sense/distance.read_mm:1`

Short advertise packet:
```json
{"v":1,"t":"a","n":"a1b2c3d4","h":"servo-dist-v1","s":[1201,2201]}
```

Queried full profile response:
```json
{
  "v": 1,
  "t": "p",
  "n": "a1b2c3d4",
  "h": "servo-dist-v1",
  "name": "servo-distance-node",
  "role": "actuator_sensor",
  "fw": "1.2.0",
  "s": [
    {
      "sid": 1201,
      "name": "act/servo.set_angle:1",
      "class": "actuator",
      "endpoint": "set_angle",
      "in": {
        "angle_deg": {"type": "int", "min": 0, "max": 180},
        "speed_dps": {"type": "int", "min": 10, "max": 720, "default": 180}
      },
      "out": {"ok": "bool", "applied_angle_deg": "int"}
    },
    {
      "sid": 2201,
      "name": "sense/distance.read_mm:1",
      "class": "sensor",
      "endpoint": "read_mm",
      "in": {},
      "out": {
        "distance_mm": {"type": "int", "min": 20, "max": 4000},
        "quality": {"type": "int", "min": 0, "max": 100}
      },
      "rate_hz": 20
    }
  ],
  "meta": {
    "bus": "i2c",
    "mount": "front_center"
  }
}
```
