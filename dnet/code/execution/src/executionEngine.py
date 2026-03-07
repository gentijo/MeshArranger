import threading
import time
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from collections import defaultdict
import uuid


class ExecutionResult(Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class Event:
    """Represents an event with a name and parameters."""
    
    def __init__(self, name: str, parameters: Dict[str, Any]):
        self.name = name
        self.parameters = parameters
        self.timestamp = time.time()
        self.event_id = str(uuid.uuid4())


class EventManager:
    """Manages event subscriptions and publishing."""
    
    def __init__(self):
        self._subscribers = defaultdict(list)  # event_name -> list of (node, callback)
        self._published_events = []
        self._lock = threading.Lock()
    
    def subscribe(self, event_name: str, node: 'Node', callback: Callable):
        """Subscribe a node to an event."""
        with self._lock:
            self._subscribers[event_name].append((node, callback))
    
    def publish(self, event: Event):
        """Publish an event to all subscribers."""
        with self._lock:
            self._published_events.append(event)
            subscribers = self._subscribers.get(event.name, [])
            
            for node, callback in subscribers:
                # Create a new thread for each subscriber
                thread = threading.Thread(
                    target=callback,
                    args=(event,),
                    daemon=True
                )
                thread.start()
    
    def unsubscribe(self, event_name: str, node: 'Node'):
        """Unsubscribe a node from an event."""
        with self._lock:
            self._subscribers[event_name] = [
                (n, cb) for n, cb in self._subscribers[event_name] 
                if n != node
            ]


class Node:
    """Basic node object for the event-driven execution system."""
    
    def __init__(self, 
                 name: str,
                 action: Optional[Callable] = None,
                 parent: Optional['Node'] = None):
        self.name = name
        self.action = action or (lambda: ExecutionResult.SUCCESS)
        self.parent = parent
        
        # Navigation links
        self.success_node: Optional['Node'] = None
        self.failure_node: Optional['Node'] = None
        
        # Child nodes for multi-step operations
        self.child_nodes: List['Node'] = []
        self.parallel_execution: bool = False
        
        # Event configuration
        self.pre_execution_event: Optional[str] = None
        self.success_event: Optional[str] = None
        self.failure_event: Optional[str] = None
        
        # Event subscription
        self.subscribed_event: Optional[str] = None
        self._waiting_for_event = False
        self._event_received = threading.Event()
        
        # Execution state
        self._execution_lock = threading.Lock()
        self._is_executing = False
        
    def set_success_node(self, node: 'Node') -> 'Node':
        """Set the node to execute on success."""
        self.success_node = node
        return self
    
    def set_failure_node(self, node: 'Node') -> 'Node':
        """Set the node to execute on failure."""
        self.failure_node = node
        return self
    
    def add_child(self, child: 'Node') -> 'Node':
        """Add a child node."""
        child.parent = self
        self.child_nodes.append(child)
        return self
    
    def set_parallel_execution(self, parallel: bool) -> 'Node':
        """Set whether child nodes should execute in parallel."""
        self.parallel_execution = parallel
        return self
    
    def set_pre_execution_event(self, event_name: str) -> 'Node':
        """Set event to publish before execution."""
        self.pre_execution_event = event_name
        return self
    
    def set_success_event(self, event_name: str) -> 'Node':
        """Set event to publish on successful execution."""
        self.success_event = event_name
        return self
    
    def set_failure_event(self, event_name: str) -> 'Node':
        """Set event to publish on failed execution."""
        self.failure_event = event_name
        return self
    
    def subscribe_to_event(self, event_name: str, event_manager: EventManager) -> 'Node':
        """Subscribe this node to an event."""
        self.subscribed_event = event_name
        event_manager.subscribe(event_name, self, self._on_event_received)
        return self
    
    def _on_event_received(self, event: Event):
        """Callback when subscribed event is received."""
        if self._waiting_for_event:
            self._event_received.set()
    
    def execute(self, event_manager: EventManager) -> ExecutionResult:
        """Execute this node and handle child node execution."""
        with self._execution_lock:
            if self._is_executing:
                return ExecutionResult.FAILURE
            self._is_executing = True
        
        try:
            # Wait for subscribed event if configured
            if self.subscribed_event:
                self._waiting_for_event = True
                self._event_received.wait()  # Block until event is received
                self._waiting_for_event = False
                self._event_received.clear()
            
            # Publish pre-execution event
            if self.pre_execution_event:
                event = Event(self.pre_execution_event, {"node": self})
                event_manager.publish(event)
            
            # Execute the node's action
            try:
                result = self.action()
                if not isinstance(result, ExecutionResult):
                    result = ExecutionResult.SUCCESS if result else ExecutionResult.FAILURE
            except Exception as e:
                print(f"Node {self.name} execution failed: {e}")
                result = ExecutionResult.FAILURE
            
            # Handle child nodes if they exist
            if self.child_nodes:
                child_result = self._execute_children(event_manager)
                if not self.parallel_execution:
                    # For sequential execution, child result determines overall result
                    result = child_result
            
            # Publish success/failure event
            if result == ExecutionResult.SUCCESS and self.success_event:
                event = Event(self.success_event, {"node": self, "result": result})
                event_manager.publish(event)
            elif result == ExecutionResult.FAILURE and self.failure_event:
                event = Event(self.failure_event, {"node": self, "result": result})
                event_manager.publish(event)
            
            return result
            
        finally:
            self._is_executing = False
    
    def _execute_children(self, event_manager: EventManager) -> ExecutionResult:
        """Execute child nodes based on parallel_execution flag."""
        if not self.child_nodes:
            return ExecutionResult.SUCCESS
        
        if self.parallel_execution:
            # Execute children in parallel
            threads = []
            for child in self.child_nodes:
                thread = threading.Thread(
                    target=lambda c=child: c.execute(event_manager),
                    daemon=True
                )
                threads.append(thread)
                thread.start()
            
            # Don't wait for parallel children to complete
            return ExecutionResult.SUCCESS
        else:
            # Execute children sequentially
            last_result = ExecutionResult.SUCCESS
            for child in self.child_nodes:
                last_result = child.execute(event_manager)
                if last_result == ExecutionResult.FAILURE:
                    break
            return last_result
    
    def get_next_node(self, result: ExecutionResult) -> Optional['Node']:
        """Get the next node based on execution result."""
        if result == ExecutionResult.SUCCESS:
            return self.success_node
        else:
            return self.failure_node
    
    def __str__(self):
        return f"Node({self.name})"
    
    def __repr__(self):
        return self.__str__()


class ExecutionEngine:
    """Main execution engine that orchestrates node execution."""
    
    def __init__(self):
        self.event_manager = EventManager()
        self._running = False
        self._execution_threads = []
    
    def execute_flow(self, start_node: Node) -> None:
        """Execute a flow starting from the given node."""
        self._running = True
        current_node = start_node
        
        while current_node and self._running:
            result = current_node.execute(self.event_manager)
            current_node = current_node.get_next_node(result)
    
    def execute_flow_async(self, start_node: Node) -> threading.Thread:
        """Execute a flow asynchronously in a separate thread."""
        thread = threading.Thread(
            target=self.execute_flow,
            args=(start_node,),
            daemon=True
        )
        self._execution_threads.append(thread)
        thread.start()
        return thread
    
    def stop(self):
        """Stop the execution engine."""
        self._running = False
        
        # Wait for all threads to complete
        for thread in self._execution_threads:
            if thread.is_alive():
                thread.join(timeout=1.0)
    
    def create_node(self, name: str, action: Optional[Callable] = None) -> Node:
        """Factory method to create a new node."""
        return Node(name, action)
    
    def publish_event(self, event_name: str, parameters: Dict[str, Any] = None):
        """Publish an event through the event manager."""
        if parameters is None:
            parameters = {}
        event = Event(event_name, parameters)
        self.event_manager.publish(event)


class IrExecutionError(RuntimeError):
    """Raised when an execution graph cannot be loaded or executed."""


class IrExecutionEngine(ExecutionEngine):
    """Run validated execution IR graphs alongside classic node flows."""

    def __init__(self, action_handlers: Optional[Dict[str, Callable]] = None):
        super().__init__()
        self._running_ir = False
        self._ir_threads: List[threading.Thread] = []
        self._action_handlers: Dict[str, Callable] = action_handlers or {}

    def register_action(self, action_name: str, handler: Callable):
        """Register a handler for a DSL action name."""
        self._action_handlers[action_name] = handler

    def run_ir(self, ir_payload: dict, block: bool = False):
        """Run a validated IR payload in parallel threads."""
        graph = self._load_ir(ir_payload)
        graph_entry_nodes = graph.entry_nodes or [graph.entry]

        self._running = True
        self._running_ir = True
        session_root = str(uuid.uuid4())
        threads = []
        for idx, entry_node_id in enumerate(graph_entry_nodes):
            session_id = f"{session_root}:{idx}"
            thread = threading.Thread(
                target=self._run_ir_graph,
                args=(graph, entry_node_id, session_id),
                daemon=True,
            )
            threads.append(thread)
            self._ir_threads.append(thread)
            thread.start()

        if block:
            for thread in threads:
                thread.join()
        return threads

    def run_ir_async(self, ir_payload: dict):
        """Run a validated IR payload asynchronously."""
        return self.run_ir(ir_payload, block=False)

    def _load_ir(self, ir_payload):
        from execution_ir import ExecutionIr, validate_execution_ir

        if isinstance(ir_payload, ExecutionIr):
            return ir_payload
        if isinstance(ir_payload, dict):
            return validate_execution_ir(ir_payload)
        raise IrExecutionError("IR payload must be an ExecutionIr or dict")

    def _run_ir_graph(self, graph, entry_node_id: str, session_id: str):
        nodes = {node.id: node for node in graph.nodes}
        context = {"session_id": session_id, "graph_id": graph.id}
        current_node_id = entry_node_id

        while self._running and self._running_ir and current_node_id in nodes:
            node = nodes[current_node_id]
            context["node_id"] = node.id

            if node.kind == "WAIT_EVENT":
                trigger = self._wait_for_one_of_events(node.on, timeout_ms=None)
                context["trigger"] = {"event": self._event_to_dict(trigger)}
                current_node_id = self._transition_target(node.transitions, "ok")

            elif node.kind == "ACTION":
                result = self._execute_action(node, context)
                status = "ok" if result == ExecutionResult.SUCCESS else "error"
                current_node_id = self._transition_target(node.transitions, status)

            elif node.kind == "WAIT_MULTI":
                trigger = self._wait_for_multi_options(node.options)
                if trigger is None:
                    return
                context["trigger"] = {
                    "kind": trigger["kind"],
                    "payload": self._event_to_dict(trigger.get("event")),
                }
                current_node_id = trigger["to"]

            elif node.kind == "EMIT":
                payload = dict(node.emit.payload)
                payload.update({"session_id": session_id})
                self.publish_event(node.emit.name, payload)
                current_node_id = self._transition_target(node.transitions, "ok")

            elif node.kind == "END":
                return

            elif node.kind == "PARALLEL":
                for branch_id in node.branches:
                    if branch_id in nodes:
                        self._run_ir_graph(graph, branch_id, session_id=f"{session_id}_{branch_id}")
                current_node_id = node.join

            else:
                raise IrExecutionError(f"Unsupported node kind: {node.kind}")

    def _wait_for_one_of_events(self, matchers, timeout_ms: Optional[float]):
        names = [matcher.name for matcher in matchers]
        event = self._wait_for_events(names, timeout_ms)
        if event is None:
            raise IrExecutionError("wait for events timed out")
        return event

    def _wait_for_multi_options(self, options):
        event_names = [o.event for o in options if o.kind == "EVENT" and o.event]
        timeout_options = [o for o in options if o.kind == "TIMEOUT"]
        start_time = time.monotonic()

        while self._running and self._running_ir:
            now = time.monotonic()
            elapsed_ms = (now - start_time) * 1000.0

            due = [option for option in timeout_options if option.ms and option.ms <= elapsed_ms]
            if due:
                selected = max(due, key=lambda option: option.priority)
                return {"kind": "TIMEOUT", "to": selected.to}

            remaining = None
            if timeout_options:
                remaining = min(option.ms - elapsed_ms for option in timeout_options if option.ms is not None)
                if remaining < 0:
                    remaining = 0

            event = self._wait_for_events(event_names, timeout_ms=remaining)
            if event is None:
                continue

            candidates = [option for option in options if option.kind == "EVENT" and option.event == event.name]
            if not candidates:
                continue
            selected = max(candidates, key=lambda option: option.priority)
            return {"kind": "EVENT", "to": selected.to, "event": event}

        return None

    def _wait_for_events(self, event_names: list[str], timeout_ms: Optional[float]):
        if not event_names:
            if timeout_ms is None:
                return None
            return None

        done = threading.Event()
        received: dict[str, Optional[Event]] = {"event": None}
        lock = threading.Lock()
        fake_node = Node(f"_ir_wait_{uuid.uuid4()}")

        def on_event(event: Event):
            with lock:
                received["event"] = event
            done.set()

        for name in event_names:
            self.event_manager.subscribe(name, fake_node, on_event)

        try:
            if timeout_ms is None:
                done.wait()
            else:
                done.wait(timeout_ms / 1000.0)
            with lock:
                return received["event"]
        finally:
            for name in event_names:
                self.event_manager.unsubscribe(name, fake_node)

    def _transition_target(self, transitions, status: str):
        for transition in transitions:
            if transition.on == status:
                return transition.to
        for transition in transitions:
            if transition.on == "default":
                return transition.to
        raise IrExecutionError(f"no transition for status {status}")

    def _execute_action(self, node, context: dict):
        handler = self._action_handlers.get(node.action.name)
        if handler is None:
            print(f"No handler for action: {node.action.name}")
            return ExecutionResult.FAILURE

        action_args = dict(node.action.args)
        trigger = context.get("trigger")
        try:
            result = handler(
                action_name=node.action.name,
                args=action_args,
                context=context,
                trigger=trigger,
            )
        except TypeError:
            try:
                result = handler(node.action.name, action_args, context=context)
            except TypeError:
                result = handler(action_args)
        except Exception as exc:
            print(f"Action {node.action.name} failed: {exc}")
            return ExecutionResult.FAILURE

        if isinstance(result, ExecutionResult):
            return result
        if isinstance(result, bool):
            return ExecutionResult.SUCCESS if result else ExecutionResult.FAILURE
        if result is None:
            return ExecutionResult.SUCCESS
        return ExecutionResult.SUCCESS

    def _event_to_dict(self, event: Optional[Event]):
        if event is None:
            return None
        return {
            "name": event.name,
            "parameters": event.parameters,
            "timestamp": event.timestamp,
            "event_id": event.event_id,
        }

    def stop(self):
        """Stop all classic and IR-based execution."""
        self._running_ir = False
        for thread in list(self._ir_threads):
            if thread.is_alive():
                thread.join(timeout=1.0)
        super().stop()


# Example usage and helper functions
def create_simple_workflow_example():
    """Create a simple workflow example to demonstrate the system."""
    engine = ExecutionEngine()
    
    # Create nodes
    start_node = engine.create_node("start", lambda: print("Starting workflow") or ExecutionResult.SUCCESS)
    process_node = engine.create_node("process", lambda: print("Processing data") or ExecutionResult.SUCCESS)
    end_node = engine.create_node("end", lambda: print("Workflow completed") or ExecutionResult.SUCCESS)
    error_node = engine.create_node("error", lambda: print("Error occurred") or ExecutionResult.SUCCESS)
    
    # Link nodes
    start_node.set_success_node(process_node).set_failure_node(error_node)
    process_node.set_success_node(end_node).set_failure_node(error_node)
    
    # Add event publishing
    start_node.set_success_event("workflow_started")
    process_node.set_success_event("data_processed")
    end_node.set_success_event("workflow_completed")
    
    return engine, start_node


if __name__ == "__main__":
    # Example usage
    engine, start_node = create_simple_workflow_example()
    
    print("Executing simple workflow...")
    engine.execute_flow(start_node)
    
    print("\nStopping engine...")
    engine.stop()
