# Execution System Overview

This folder has two execution paths that work together:

- A **DSL-to-IR compiler** (`dsl_to_ir.py`)
- An **IR schema + validator** (`execution_ir.py`)
- An **execution runtime** (`executionEngine.py`) that supports both classic node flows and IR execution
- Example entry points (`example_usage.py`)

## 1. DSL compiler: `dsl_to_ir.py`

`dsl_to_ir.py` converts a user workflow DSL into a strongly typed `ExecutionIr` graph.

### Input shape (expected DSL)

- Top level:
  - `version` (supports `1`, `1.0`, `1.0.0`)
  - `actor` (string)
  - `rules` (non-empty array)
- Each `rule` has:
  - `id` (required string)
  - `on.event.in` (required list of event names)
  - `start` (at least one action)
  - `stop` (optional; defaults to `stepper.stop`)
  - `timeout` (optional; defaults to `stepper.stop` with reason `timeout`)
  - `until` (optional branch conditions)

### Key compiler steps

`compile_dsl_to_ir()`:

1. Validates payload type and version.
2. Iterates every rule and calls `compile_rule(rule)`.
3. Assembles all compiled nodes into one graph payload.
4. Sets graph entry to the first rule’s `_wait_start` node and exposes all rule entry nodes.

`compile_rule(rule)` builds these node patterns per rule:

- `WAIT_EVENT` node: `<rule>_wait_start`
  - Waits for every event in `on.event.in`.
  - On `ok` transitions to first start action node.
- Action chain for `start`:
  - `<rule>_start_action_0`, `_1`, ...
  - Each node executes one action and transitions to the next.
- `WAIT_MULTI` node: `<rule>_wait_stop`
  - Built from `until` conditions.
  - Supports:
    - `on`: event wait condition
    - `timeout`: ms timeout
  - If `until` is empty, inserts a default timeout option (`ms=10000`, to timeout node).
- `stop` action chain:
  - `<rule>_stop`, `<rule>_stop_1`, ...
- `timeout` action chain:
  - `<rule>_timeout`, `<rule>_timeout_1`, ...
- Terminal node: `<rule>_done` (`END` with `{ "status": "idle" }`)

### Coercion & validation

The compiler normalizes incoming DSL with small helpers:

- `_coerce_name`, `_coerce_event_name`, `_coerce_action`, `_coerce_action_list`
- Raises clear `ValueError` for malformed shapes
- Uses helper node-id prefixing (`-` → `_`) for consistent IDs

## 2. IR data model: `execution_ir.py`

Defines schema classes (Pydantic) for runtime-safe execution graphs:

- `ExecutionIr` with:
  - `schema_version`
  - `graph`
- `Graph` with:
  - `id`, `kind`, `entry`, `nodes`
  - optional `entry_nodes`
  - optional `correlation_mode`
- Node types:
  - `WAIT_EVENT`, `ACTION`, `WAIT_MULTI`, `EMIT`, `PARALLEL`, `END`
- Shared helper types:
  - `EventMatcher`, `Transition`, `ActionCall`, `MultiOption`, `EventTemplate`

Validation behavior is strict:

- Duplicate node IDs are rejected.
- Entry nodes must exist in the node map.
- All transition targets must exist.
- `WAIT_MULTI` must have at least one option.
- `MultiOption` and event/action names are namespace-validated with regex `^[a-z0-9_.-]+$`.

`validate_execution_ir(payload)` is the canonical entry for converting dict payloads into typed `ExecutionIr`.

## 3. Runtime execution: `executionEngine.py`

This module contains:

- a classic event-driven flow engine (`ExecutionEngine` / `Node` / `EventManager`)
- an IR extension (`IrExecutionEngine`)

### Event basics

- `EventManager` keeps subscribers per event name.
- `Event` includes `name`, `parameters`, `timestamp`, and `event_id`.
- Subscribers get invoked asynchronously in background threads.

### Classic node flow (`ExecutionEngine`)

- `Node` supports:
  - one action callback
  - success/failure links (`success_node`, `failure_node`)
  - optional child nodes with parallel/sequential execution mode
  - optional event behavior:
    - pre-execution event
    - success/failure events
    - event subscription to pause execution until trigger
- `ExecutionEngine.execute_flow(start_node)` runs a graph by repeatedly walking `get_next_node`.
- `execute_flow_async` starts it in a thread.
- `publish_event` pushes events into the manager so waiting nodes can continue.
- `stop()` stops flow execution and joins worker threads.

### IR runtime (`IrExecutionEngine`)

`IrExecutionEngine` subclasses `ExecutionEngine` so shared event model is reused.

Workflow:

1. `run_ir(ir_payload, block=False)`:
   - Loads/validates IR via `validate_execution_ir` when needed.
   - Picks entry nodes (`entry_nodes` or fallback to `entry`).
   - Starts one thread per entry.
2. `_run_ir_graph(graph, entry, session_id)`:
   - Builds in-memory map `id -> node`.
   - Loops node by node and updates context (`session_id`, `graph_id`, `node_id`).
   - Behavior by kind:
     - `WAIT_EVENT`: wait for one of configured events, then take `ok` transition
     - `ACTION`: call registered action handler and transition using `ok/error`
     - `WAIT_MULTI`: evaluate event/timeout options with priority, wait logic, and timeout fallback
     - `EMIT`: publish event and continue
     - `PARALLEL`: spawn branch runs then jump to join target
     - `END`: finish thread
3. Action dispatch via `register_action(name, handler)` and `_execute_action`:
   - Supports multiple handler signatures for compatibility.
   - `ExecutionResult.SUCCESS/FAILURE` are mapped directly.
   - Booleans map to success/failure; `None` maps to success.
4. `stop()` disables IR execution flag and joins IR threads before stopping base engine behavior.

## 4. Example coverage: `example_usage.py`

Contains runnable demonstrations for classic engine behavior:

- linear success/failure flow
- parallel child execution
- sequential child execution
- event-driven wait/trigger flow
- multiple consumer threads triggered by repeated event publication

Each example wires nodes, links them with `set_success_node` / `set_failure_node`, and starts execution with `execute_flow` or `execute_flow_async`.

## Mental model

- `dsl_to_ir.py`: authoring layer → IR model
- `execution_ir.py`: contract/validation layer
- `executionEngine.py`: execution layer (`IrExecutionEngine` for IR, `ExecutionEngine` for legacy node flows)
- `example_usage.py`: usage + behavior examples for the legacy flow runtime

The IR path is best for DSL-driven workflows, because it gives schema-validated graph execution with explicit transitions and event waits. The classic path is useful for directly wiring Python callables when you do not need DSL compilation.
