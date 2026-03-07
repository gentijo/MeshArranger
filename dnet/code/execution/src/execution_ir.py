from __future__ import annotations

from typing import Any, ClassVar, Literal, Optional
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


NAMESPACED_EVENT = re.compile(r"^[a-z0-9_.-]+$")


def validate_namespaced(value: str) -> str:
    if not isinstance(value, str) or not NAMESPACED_EVENT.match(value):
        raise ValueError("event/action names should match [a-z0-9_.-]+")
    return value


class EventMatcher(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    priority: int = 0
    filter: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_namespaced(value)


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: Literal["ok", "error", "done", "timeout", "event", "default"]
    to: str
    priority: int = 0
    guard: Optional[str] = None
    bind: Optional[str] = None
    preempt: bool = False


class ActionCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    args: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return value


class MultiOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["EVENT", "TIMEOUT"]
    event: Optional[str] = None
    ms: Optional[int] = Field(default=None, gt=0)
    to: str
    priority: int = 0
    preempt: bool = False
    bind: Optional[str] = None

    @model_validator(mode="after")
    def validate_kind_fields(self):
        if self.kind == "EVENT":
            if self.event is None:
                raise ValueError("EVENT option requires event")
            validate_namespaced(self.event)
        else:
            if self.ms is None:
                raise ValueError("TIMEOUT option requires ms")
        return self


class EventTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    target: Optional[str] = None
    priority: int = 0

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_namespaced(value)


class WaitEventNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["WAIT_EVENT"] = "WAIT_EVENT"
    id: str
    on: list[EventMatcher]
    transitions: list[Transition]
    out_default: Optional[str] = None


class ActionNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ACTION"] = "ACTION"
    id: str
    action: ActionCall
    transitions: list[Transition]
    on_error: Optional[str] = None


class WaitMultiNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["WAIT_MULTI"] = "WAIT_MULTI"
    id: str
    options: list[MultiOption]


class EmitNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["EMIT"] = "EMIT"
    id: str
    emit: EventTemplate
    transitions: list[Transition]


class ParallelNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["PARALLEL"] = "PARALLEL"
    id: str
    branches: list[str]
    join: str


class EndNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["END"] = "END"
    id: str
    result: dict[str, Any]


Node = WaitEventNode | ActionNode | WaitMultiNode | EmitNode | ParallelNode | EndNode


class Graph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["state_machine", "flow"]
    entry: str
    entry_nodes: Optional[list[str]] = None
    correlation_mode: Optional[Literal["none", "session"]] = None
    nodes: list[Node]

    @field_validator("entry_nodes")
    @classmethod
    def validate_entry_nodes_not_empty(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is not None and len(value) == 0:
            return None
        return value

    @model_validator(mode="after")
    def validate_graph(self):
        node_ids = [node.id for node in self.nodes]
        missing = [node_id for node_id in set(node_ids) if node_ids.count(node_id) > 1]
        if missing:
            raise ValueError(f"duplicate node ids: {sorted(missing)}")

        node_map = {node.id: node for node in self.nodes}
        entries = self.entry_nodes or [self.entry]
        for entry in entries:
            if entry not in node_map:
                raise ValueError(f"entry node does not exist: {entry}")

        if self.entry not in node_map:
            raise ValueError(f"entry node does not exist: {self.entry}")

        for node in self.nodes:
            if isinstance(node, (WaitEventNode, ActionNode, EmitNode)):
                for transition in node.transitions:
                    if transition.to not in node_map:
                        raise ValueError(f"{node.id} transition points to missing node {transition.to}")
            elif isinstance(node, ParallelNode):
                for branch in node.branches + [node.join]:
                    if branch not in node_map:
                        raise ValueError(f"{node.id} references missing node {branch}")
            elif isinstance(node, WaitMultiNode):
                if not node.options:
                    raise ValueError(f"{node.id} has no wait options")
                for option in node.options:
                    if option.to not in node_map:
                        raise ValueError(f"{node.id} option references missing node {option.to}")

        return self


class ExecutionIr(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0.0"]
    graph: Graph


def validate_execution_ir(payload: dict[str, Any]) -> ExecutionIr:
    """Validate payload and return a strongly typed ExecutionIr."""
    return ExecutionIr.model_validate(payload)
