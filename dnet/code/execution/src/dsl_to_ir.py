from __future__ import annotations

from typing import Any

from execution_ir import (
    ActionCall,
    ActionNode,
    EndNode,
    EventMatcher,
    ExecutionIr,
    Graph,
    MultiOption,
    Transition,
    WaitEventNode,
    WaitMultiNode,
)


def _ensure_list(value: Any, *, field_name: str) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _coerce_name(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _coerce_event_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _coerce_name(value.get("name"), field="event")
    raise ValueError(f"invalid event entry: {value}")


def _coerce_action(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("action entry must be a dict")
    if "do" not in value:
        raise ValueError("action entry missing 'do'")
    return {
        "name": _coerce_name(value["do"], field="action"),
        "args": value.get("with", {}),
    }


def _coerce_action_list(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _ensure_list(value, field_name="actions"):
        if not isinstance(item, dict):
            raise ValueError("each action must be a dict")
        if "do" in item and "action" in item:
            raise ValueError("action must use 'do' or 'action', not both")
        if "do" in item:
            out.append(_coerce_action(item))
        else:
            name = _coerce_name(item.get("action", {}).get("name"), field="action")
            args = item.get("action", {}).get("args", {})
            out.append({"name": name, "args": args})
    return out


def _coerce_transition_targets(prefix: str, wait_node_id: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _compile_until(rule_id: str, rule: dict[str, Any], stop_id: str, timeout_id: str) -> list[MultiOption]:
    until_spec = rule.get("until") or {}
    conds = until_spec.get("any") or []
    out: list[MultiOption] = []

    for cond in conds:
        if not isinstance(cond, dict):
            raise ValueError(f"invalid until condition: {cond}")
        if "on" in cond:
            out.append(
                MultiOption(
                    kind="EVENT",
                    event=_coerce_event_name(cond["on"]),
                    to=stop_id,
                    priority=int(cond.get("priority", 0)),
                    preempt=bool(cond.get("preempt", False)),
                    bind="trigger",
                )
            )
            continue

        if "timeout" in cond:
            timeout = cond["timeout"]
            if not isinstance(timeout, dict) or "ms" not in timeout:
                raise ValueError("timeout condition requires ms")
            out.append(
                MultiOption(
                    kind="TIMEOUT",
                    ms=int(timeout["ms"]),
                    to=timeout_id,
                    priority=int(timeout.get("priority", 0)),
                    bind="trigger",
                )
            )
            continue

        raise ValueError(f"unsupported until condition: {cond}")

    if not out:
        out.append(
            MultiOption(
                kind="TIMEOUT",
                ms=10000,
                to=timeout_id,
                priority=1,
                bind="trigger",
            )
        )
    return out


def compile_rule(rule: dict[str, Any]) -> list[object]:
    rule_id = _coerce_name(rule.get("id"), field="rule.id")
    prefix = rule_id.replace("-", "_")

    on_events = rule.get("on", {}).get("event", {}).get("in", [])
    event_matchers = [EventMatcher(name=_coerce_event_name(e)) for e in _ensure_list(on_events, field_name="on events")]
    if not event_matchers:
        raise ValueError(f"rule {rule_id}: on.event.in cannot be empty")

    start_actions = _coerce_action_list(rule.get("start"))
    if not start_actions:
        raise ValueError(f"rule {rule_id}: start block cannot be empty")
    stop_actions = _coerce_action_list(rule.get("stop"))
    if not stop_actions:
        stop_actions = [{"name": "stepper.stop", "args": {}}]

    timeout_actions = _coerce_action_list(rule.get("timeout"))
    if not timeout_actions:
        timeout_actions = [{"name": "stepper.stop", "args": {"reason": "timeout"}}]

    node_wait_start = WaitEventNode(
        id=f"{prefix}_wait_start",
        on=event_matchers,
        transitions=[Transition(on="ok", to=f"{prefix}_start_action_0")],
    )

    nodes: list[object] = [node_wait_start]

    # Start action chain
    last_start_id = node_wait_start.id
    for index, action in enumerate(start_actions):
        node_id = f"{prefix}_start_action_{index}"
        next_id = (
            f"{prefix}_start_action_{index + 1}" if index + 1 < len(start_actions) else f"{prefix}_wait_stop"
        )
        nodes.append(
            ActionNode(
                id=node_id,
                action=ActionCall(name=action["name"], args=action["args"]),
                transitions=[Transition(on="ok", to=next_id)],
            )
        )
        last_start_id = node_id

    # If for some reason there is no action step, jump directly to wait_stop.
    if not start_actions:
        node_wait_start.transitions = [Transition(on="ok", to=f"{prefix}_wait_stop")]
    else:
        node_wait_start.transitions = [Transition(on="ok", to=f"{prefix}_start_action_0")]

    stop_id = f"{prefix}_stop"
    timeout_id = f"{prefix}_timeout"

    nodes.append(
        WaitMultiNode(
            id=f"{prefix}_wait_stop",
            options=_compile_until(rule_id, rule, stop_id=stop_id, timeout_id=timeout_id),
        )
    )

    # stop action chain
    for index, action in enumerate(stop_actions):
        nodes.append(
            ActionNode(
                id=stop_id if index == 0 else f"{prefix}_stop_{index}",
                action=ActionCall(name=action["name"], args=action["args"]),
                transitions=[
                    Transition(on="ok", to=f"{prefix}_done" if index + 1 == len(stop_actions) else f"{prefix}_stop_{index + 1}")
                ],
            )
        )

    # timeout action chain
    for index, action in enumerate(timeout_actions):
        nodes.append(
            ActionNode(
                id=timeout_id if index == 0 else f"{prefix}_timeout_{index}",
                action=ActionCall(name=action["name"], args=action["args"]),
                transitions=[
                    Transition(on="ok", to=f"{prefix}_done" if index + 1 == len(timeout_actions) else f"{prefix}_timeout_{index + 1}")
                ],
            )
        )

    nodes.append(EndNode(id=f"{prefix}_done", result={"status": "idle"}))

    # Re-point any generated node that currently points to internal placeholder IDs
    return nodes


def compile_dsl_to_ir(dsl: dict[str, Any]) -> ExecutionIr:
    if not isinstance(dsl, dict):
        raise ValueError("dsl payload must be a dict")

    version = str(dsl.get("version", "1"))
    if version not in ("1", "1.0", "1.0.0"):
        raise ValueError("unsupported dsl version")

    actor = str(dsl.get("actor", "default_actor"))
    rules = dsl.get("rules", [])
    if not isinstance(rules, list) or not rules:
        raise ValueError("dsl must contain at least one rule")

    nodes: list[object] = []
    entry_nodes: list[str] = []

    for rule in rules:
        compiled = compile_rule(rule)
        nodes.extend(compiled)
        rule_id = _coerce_name(rule.get("id"), field="rule.id").replace("-", "_")
        entry_nodes.append(f"{rule_id}_wait_start")

    return ExecutionIr(
        schema_version="1.0.0",
        graph=Graph(
            id=actor,
            kind="state_machine",
            entry=entry_nodes[0],
            entry_nodes=entry_nodes,
            correlation_mode="session",
            nodes=nodes,
        ),
    )
