# Distributed Mesh Network Communication Spec

## Scope

This spec defines a distributed mesh communication style for:

1. Intra-robot auto-discovery of component parts (sensors, motors, actuators, controllers).
2. Inter-robot and field-level discovery/communication on a shared playing field.

### Robot auto discovering its own capibilities via the mesh network

<img src="./design/RobotWithSensors2.png" alt="Robot auto discovering its own components" width="400" >

### Robot discovering where it is in the global
space along with other sensors in that space

<img src="./design/RobotField.png" alt="Robot auto discovering its own components" width="400" >

## Goals

- Zero-manual wiring of component relationships at startup.
- Fast discovery and re-discovery of devices after resets or disconnects.
- Stable service naming so nodes can find capabilities, not hardcoded addresses.
- Consistent protocol behavior from single-robot mesh to field-wide mesh.
- Bounded message size suitable for low-bandwidth wireless links.

## Terms

- **Node**: Any network participant (sensor, motor controller, actuator, compute unit, full robot controller, or field beacon).
- **Service**: A capability exposed by a node (for example:`imu.attitude`,`motor.set_rpm`,`field.zone_state`).
- **Service Key**: Compact ID derived from canonical service name and major version.
- **Robot Mesh**: Mesh made from all nodes physically belonging to one robot.
- **Field Mesh**: Mesh made from robot-level nodes plus fixed field sensors/infrastructure.

## Network Model

- Topology: Distributed peer mesh, no single mandatory coordinator.
- Addressing:
  - `node_id`: globally unique per node.
  - `robot_id`: shared by components belonging to same robot.
  - `field_id`: identifies match/field context.
- Discovery domains:
  - **Local domain**: robot-internal traffic.
  - **Field domain**: robot gateway + external robots + field nodes.

## Service Identity

Each service is named canonically:

- `<domain>/<service_name>:<major_version>`

Examples:

- `core/attitude:1`
- `act/motor.set_rpm:1`
- `field/zone_occupancy:1`

A `service_key` is generated from canonical name using a deterministic 16-bit hash. Nodes use `service_key` for compact advertisements and matching.

## Message Families

All messages use a small fixed header plus TLV payload.

Header (required):

- `proto_ver`
- `msg_type`
- `src_node_id`
- `dst_node_id` (or broadcast)
- `seq`
- `timestamp_ms`

Core message types:

- `HELLO`: periodic presence + capability summary.
- `WHO_HAS`: request providers for one or more service keys.
- `I_HAVE`: response with matching service providers.
- `DESCRIBE_NODE`: request full node profile.
- `NODE_PROFILE`: full profile response.
- `DESCRIBE_SERVICE`: request detailed service schema.
- `SERVICE_DESC`: detailed service response.
- `PUBLISH`: telemetry/event data.
- `CALL`: command/RPC invoke.
- `RESULT`: command/RPC response.
- `PING` /`PONG`: liveness check.
- `BYE`: graceful leave.

## Capability Advertisement Contract

`HELLO` contains a compact summary only:

- `node_id`,`robot_id`,`role`,`health`
- `provides[]`: list of
  - `service_key`
  - `service_class` (`sensor`,`actuator`,`compute`,`field`)
  - `confidence` (0-100)
  - `qos_flags`
- `profile_hash`: hash of full node profile for cache validation

Rationale:

- Keeps periodic traffic lightweight.
- Enables fast capability matching.
- Full profile fetched only when needed.

## Full Node Profile (On Demand)

Fetched through `DESCRIBE_NODE` / `NODE_PROFILE`.

Includes:

- Hardware identity (model, serial, firmware)
- Coordinate frame/mount metadata (if sensor/actuator is spatial)
- Units and scaling
- Accuracy, covariance, calibration status
- Supported command set and limits
- Update rates and timing guarantees
- Safety state and fault semantics

## Use Case 1: Single Robot Auto-Discovery

Image reference: `design/RobotWithSensors.png`

### Behavior

1. Node boots and broadcasts`HELLO`.
2. Nodes listen for`HELLO` from peers in same`robot_id`.
3. If required dependency is missing, node sends`WHO_HAS(service_key)`.
4. Provider replies with`I_HAVE`.
5. Node selects best provider by health + confidence + freshness.
6. Node requests`NODE_PROFILE` if deeper compatibility check is needed.
7. Node transitions to`OPERATIONAL` when minimum dependency set is satisfied.

### Failure/Reconfiguration

- Missed heartbeats trigger`PING` retries.
- Provider timeout removes dependency binding.
- Node re-enters discovery and issues`WHO_HAS`.
- If minimum required dependencies are not met, node publishes`MIN_DEP_FAIL` event.

## Use Case 2: Multi-Robot + Field Mesh

Image reference: `design/RobotField.png`

### Behavior

1. Each robot internally forms a robot mesh as in Use Case 1.
2. A robot gateway node advertises robot-level services into field domain.
3. Field infrastructure nodes advertise services (timing, localization beacons, zone state, game-state sensors).
4. Robots discover:
   - Other robot-level services (peer awareness, coordination channels).
   - Field services (official field telemetry).
5. Policy decides visibility:
   - Internal robot-only services stay local.
   - Shareable services are exported to field domain.

### Domain Separation

- **Robot-internal domain**: high-rate component telemetry and actuator control.
- **Field domain**: bounded, policy-filtered, match-relevant data only.

## State Machine

Node lifecycle states:

- `BOOT`
- `UNPROVISIONED` (optional, requests config)
- `DISCOVERING`
- `BINDING`
- `OPERATIONAL`
- `DEGRADED`
- `FAULT`

Required transitions:

- `BOOT -> DISCOVERING`
- `DISCOVERING -> BINDING` when candidate providers found
- `BINDING -> OPERATIONAL` when minimum dependencies met
- `OPERATIONAL -> DEGRADED` when critical dependency lost
- `DEGRADED -> OPERATIONAL` after rebind success

## Reliability and Timing

- `HELLO` interval: 250-1000 ms (profile dependent).
- Dependency timeout: 3x expected`HELLO` interval.
- `CALL`/`RESULT` timeout and retry policy configurable per service class.
- Sequence numbers used for duplicate and stale message rejection.

## Security and Safety

- Signed node identity (or pre-shared trust list) required before binding critical control paths.
- Service authorization policy:
  - Robot-internal actuator commands require trusted role.
  - Field-domain data treated as read-only unless explicitly permitted.
- Safety interlocks:
  - Reject commands outside declared limits.
  - Enter safe mode on repeated auth failures or invalid command envelopes.

## Data Model Requirements

Each service descriptor must declare:

- `service_key`
- canonical name and version
- direction (`publish`,`callable`, or both)
- payload schema reference
- units
- min/max rate
- fault codes

## Acceptance Criteria

- New sensor node can be added to a robot and become discoverable without manual address configuration.
- Robot remains operational if a non-critical node is removed and re-added.
- Multiple robots can coexist in field mesh without service key collisions causing control ambiguity.
- Field-provided services can be discovered and consumed by robots within bounded latency.
- Internal-only robot services are not exposed to unauthorized field peers.

## Implementation Notes

- Keep periodic advertisements compact; fetch detail on demand.
- Prefer deterministic service selection (rank by trust, health, confidence, then latency).
- Maintain profile cache keyed by`node_id + profile_hash`.
- Versioning rule: bump major when payload compatibility breaks.
