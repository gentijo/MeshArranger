#!/usr/bin/env python3
"""A compact end-to-end DSL implementation example.

This script demonstrates:
1) parsing a tiny text DSL into structured data,
2) compiling the structured data with the existing `compile_dsl_to_ir`,
3) executing the result with `IrExecutionEngine`.
"""

from __future__ import annotations

import shlex
import time
from typing import Any

from dsl_to_ir import compile_dsl_to_ir
from executionEngine import ExecutionResult, IrExecutionEngine


def _parse_value(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "none":
        return None

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    return value


def parse_args_line(raw: str) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for token in shlex.split(raw):
        if "=" not in token:
            raise ValueError(f"invalid arg token '{token}', expected key=value")
        key, value = token.split("=", 1)
        args[key] = _parse_value(value)
    return args


def parse_dsl(text: str) -> dict[str, Any]:
    """Parse a small line-based workflow DSL.

    Example:
      VERSION 1
      ACTOR robot
      RULE motion_loop
      ON motion.detected motion.restored
      START motor.start speed=1 direction=forward
      START logger.info message='started'
      UNTIL ON motor.done
      UNTIL TIMEOUT 2500
      STOP motor.stop reason=completed
      TIMEOUT motor.stop reason=timeout
      END
    """
    root: dict[str, Any] = {"version": "1", "actor": "default_actor", "rules": []}

    current_rule: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if not parts:
            continue

        keyword = parts[0].upper()
        payload = parts[1:]

        if keyword == "VERSION":
            if not payload:
                raise ValueError("VERSION requires a value")
            root["version"] = payload[0]
        elif keyword == "ACTOR":
            if not payload:
                raise ValueError("ACTOR requires a value")
            root["actor"] = payload[0]
        elif keyword == "RULE":
            if not payload:
                raise ValueError("RULE requires an id")
            current_rule = {
                "id": payload[0],
                "on": {"event": {"in": []}},
                "start": [],
                "until": {"any": []},
                "stop": [],
                "timeout": [],
            }
            root["rules"].append(current_rule)
        elif keyword == "ON":
            if current_rule is None:
                raise ValueError("ON appears before RULE")
            if not payload:
                raise ValueError("ON requires at least one event")
            current_rule["on"]["event"]["in"] = payload
        elif keyword == "START":
            if current_rule is None:
                raise ValueError("START appears before RULE")
            action_name, *rest = payload
            current_rule["start"].append({"do": action_name, "with": parse_args_line(" ".join(rest))})
        elif keyword == "STOP":
            if current_rule is None:
                raise ValueError("STOP appears before RULE")
            action_name, *rest = payload
            current_rule["stop"].append({"do": action_name, "with": parse_args_line(" ".join(rest))})
        elif keyword == "TIMEOUT":
            if current_rule is None:
                raise ValueError("TIMEOUT appears before RULE")
            action_name, *rest = payload
            current_rule["timeout"].append({"do": action_name, "with": parse_args_line(" ".join(rest))})
        elif keyword == "UNTIL":
            if current_rule is None:
                raise ValueError("UNTIL appears before RULE")
            if not payload:
                raise ValueError("UNTIL requires a condition")
            if payload[0].upper() == "ON" and len(payload) >= 2:
                current_rule["until"]["any"].append({"on": payload[1]})
            elif payload[0].upper() == "TIMEOUT" and len(payload) == 2:
                current_rule["until"]["any"].append({"timeout": {"ms": int(payload[1])}})
            else:
                raise ValueError(f"unsupported UNTIL form: {' '.join(payload)}")
        elif keyword == "END":
            current_rule = None
        else:
            raise ValueError(f"unknown keyword: {keyword}")

    if not root["rules"]:
        raise ValueError("no rules defined")
    return root


def run_example():
    sample_dsl = """
VERSION 1
ACTOR demo_robot

RULE patrol
ON motion.start
START log.info message='waiting for motion'
START stepper.start speed=12
UNTIL ON motion.done
UNTIL TIMEOUT 2500
STOP stepper.stop reason=manual
TIMEOUT stepper.stop reason=timeout

RULE emergency
ON emergency.stop
START led.blink color=red count=2
STOP stepper.stop reason=emergency
END
"""

    ir_payload = compile_dsl_to_ir(parse_dsl(sample_dsl)).model_dump()

    engine = IrExecutionEngine(action_handlers={
        "log.info": lambda action_name, args, context=None, trigger=None: (
            print(f"[{context['session_id']}] {action_name} -> {args.get('message', '')}"),
            ExecutionResult.SUCCESS,
        )[1],
        "stepper.start": lambda action_name, args, context=None, trigger=None: (
            print(f"Stepper started at speed={args.get('speed')}"),
            ExecutionResult.SUCCESS,
        )[1],
        "stepper.stop": lambda action_name, args, context=None, trigger=None: (
            print(f"Stepper stopping ({args})"),
            ExecutionResult.SUCCESS,
        )[1],
        "led.blink": lambda action_name, args, context=None, trigger=None: (
            print(f"LED blinking {args.get('color')} x{args.get('count', 1)}"),
            ExecutionResult.SUCCESS,
        )[1],
    })

    engine.run_ir(ir_payload, block=False)
    time.sleep(0.2)
    engine.publish_event("motion.start")
    time.sleep(0.5)
    engine.publish_event("motion.done")
    time.sleep(1.0)
    engine.publish_event("emergency.stop")
    time.sleep(0.5)
    engine.stop()


if __name__ == "__main__":
    run_example()
