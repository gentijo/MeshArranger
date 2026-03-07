#!/usr/bin/env python3
"""
Example usage of the ExecutionEngine module.
This demonstrates all the key features including:
- Basic node execution with success/failure routing
- Parallel and sequential child node execution
- Event publishing and subscription
- Event-driven workflow coordination
"""

import time
import random
from executionEngine import ExecutionEngine, ExecutionResult, Node


def simulate_work(task_name: str, duration: float = 1.0, fail_chance: float = 0.0):
    """Simulate some work that might succeed or fail."""
    def work():
        print(f"  🔄 Starting {task_name}...")
        time.sleep(duration)
        
        if random.random() < fail_chance:
            print(f"  ❌ {task_name} failed!")
            return ExecutionResult.FAILURE
        else:
            print(f"  ✅ {task_name} completed successfully!")
            return ExecutionResult.SUCCESS
    
    return work


def create_basic_workflow_example():
    """Create a basic linear workflow."""
    print("\n=== Basic Workflow Example ===")
    
    engine = ExecutionEngine()
    
    # Create nodes
    start = engine.create_node("start", simulate_work("Initialize system"))
    validate = engine.create_node("validate", simulate_work("Validate inputs"))
    process = engine.create_node("process", simulate_work("Process data"))
    cleanup = engine.create_node("cleanup", simulate_work("Cleanup resources"))
    error_handler = engine.create_node("error", simulate_work("Handle error"))
    
    # Link nodes for success/failure routing
    start.set_success_node(validate).set_failure_node(error_handler)
    validate.set_success_node(process).set_failure_node(error_handler)
    process.set_success_node(cleanup).set_failure_node(error_handler)
    
    # Add event publishing
    start.set_success_event("workflow_started")
    process.set_success_event("data_processed")
    cleanup.set_success_event("workflow_completed")
    error_handler.set_success_event("error_handled")
    
    return engine, start


def create_parallel_execution_example():
    """Create a workflow with parallel child execution."""
    print("\n=== Parallel Execution Example ===")
    
    engine = ExecutionEngine()
    
    # Create main workflow nodes
    start = engine.create_node("start", simulate_work("Initialize parallel processing"))
    parallel_coordinator = engine.create_node("coordinator", simulate_work("Coordinate parallel tasks", 0.5))
    finish = engine.create_node("finish", simulate_work("Finalize results"))
    
    # Create parallel child tasks
    task1 = engine.create_node("task1", simulate_work("Parallel Task 1", 2.0))
    task2 = engine.create_node("task2", simulate_work("Parallel Task 2", 1.5))
    task3 = engine.create_node("task3", simulate_work("Parallel Task 3", 1.0))
    
    # Add child nodes to coordinator with parallel execution
    parallel_coordinator.add_child(task1)
    parallel_coordinator.add_child(task2)
    parallel_coordinator.add_child(task3)
    parallel_coordinator.set_parallel_execution(True)
    
    # Link main workflow
    start.set_success_node(parallel_coordinator)
    parallel_coordinator.set_success_node(finish)
    
    # Add events
    start.set_success_event("parallel_workflow_started")
    parallel_coordinator.set_pre_execution_event("starting_parallel_tasks")
    parallel_coordinator.set_success_event("parallel_tasks_initiated")
    finish.set_success_event("parallel_workflow_completed")
    
    return engine, start


def create_sequential_child_example():
    """Create a workflow with sequential child execution."""
    print("\n=== Sequential Child Execution Example ===")
    
    engine = ExecutionEngine()
    
    # Create main workflow
    start = engine.create_node("start", simulate_work("Start sequential processing"))
    sequential_coordinator = engine.create_node("coordinator", simulate_work("Coordinate sequential tasks", 0.5))
    finish = engine.create_node("finish", simulate_work("Complete sequential workflow"))
    error_handler = engine.create_node("error", simulate_work("Handle sequential error"))
    
    # Create sequential child tasks (one might fail)
    step1 = engine.create_node("step1", simulate_work("Sequential Step 1", 1.0))
    step2 = engine.create_node("step2", simulate_work("Sequential Step 2", 1.0, fail_chance=0.3))
    step3 = engine.create_node("step3", simulate_work("Sequential Step 3", 1.0))
    
    # Add child nodes with sequential execution
    sequential_coordinator.add_child(step1)
    sequential_coordinator.add_child(step2)
    sequential_coordinator.add_child(step3)
    sequential_coordinator.set_parallel_execution(False)
    
    # Link main workflow
    start.set_success_node(sequential_coordinator)
    sequential_coordinator.set_success_node(finish).set_failure_node(error_handler)
    
    # Add events
    start.set_success_event("sequential_workflow_started")
    sequential_coordinator.set_success_event("sequential_tasks_completed")
    sequential_coordinator.set_failure_event("sequential_tasks_failed")
    
    return engine, start


def create_event_driven_example():
    """Create a workflow that demonstrates event subscription and coordination."""
    print("\n=== Event-Driven Workflow Example ===")
    
    engine = ExecutionEngine()
    
    # Create producer node that will publish events
    producer = engine.create_node("producer", simulate_work("Produce data items", 0.5))
    producer.set_success_event("data_produced")
    
    # Create consumer nodes that wait for events
    consumer1 = engine.create_node("consumer1", simulate_work("Process data (Consumer 1)", 1.0))
    consumer2 = engine.create_node("consumer2", simulate_work("Process data (Consumer 2)", 1.5))
    consumer3 = engine.create_node("consumer3", simulate_work("Process data (Consumer 3)", 0.8))
    
    # Subscribe consumers to the event
    consumer1.subscribe_to_event("data_produced", engine.event_manager)
    consumer2.subscribe_to_event("data_produced", engine.event_manager)
    consumer3.subscribe_to_event("data_produced", engine.event_manager)
    
    # Set up event publishing on success
    consumer1.set_success_event("consumer1_completed")
    consumer2.set_success_event("consumer2_completed")
    consumer3.set_success_event("consumer3_completed")
    
    # Start consumers in background (they will wait for events)
    print("  🚀 Starting consumers (they will wait for events)...")
    engine.execute_flow_async(consumer1)
    engine.execute_flow_async(consumer2)
    engine.execute_flow_async(consumer3)
    
    # Give consumers time to start waiting
    time.sleep(0.5)
    
    return engine, producer


def demonstrate_multiple_event_publishing():
    """Demonstrate publishing multiple events to trigger multiple consumer instances."""
    print("\n=== Multiple Event Publishing Example ===")
    
    engine = ExecutionEngine()
    
    # Create a consumer that can handle multiple events
    consumer = engine.create_node("multi_consumer", simulate_work("Handle event", 0.8))
    consumer.subscribe_to_event("batch_data", engine.event_manager)
    consumer.set_success_event("batch_processed")
    
    # Start multiple consumer instances
    print("  🚀 Starting multiple consumer instances...")
    for i in range(3):
        engine.execute_flow_async(consumer)
    
    time.sleep(0.5)
    
    # Publish multiple events
    print("  📢 Publishing multiple events...")
    for i in range(5):
        engine.publish_event("batch_data", {"batch_id": i, "data": f"batch_{i}"})
        time.sleep(0.3)
    
    return engine


def run_all_examples():
    """Run all examples to demonstrate the execution engine."""
    print("🚀 ExecutionEngine Demonstration")
    print("=" * 50)
    
    # Example 1: Basic workflow
    engine1, start1 = create_basic_workflow_example()
    engine1.execute_flow(start1)
    engine1.stop()
    
    # Example 2: Parallel execution
    engine2, start2 = create_parallel_execution_example()
    engine2.execute_flow(start2)
    time.sleep(3)  # Give parallel tasks time to complete
    engine2.stop()
    
    # Example 3: Sequential child execution
    engine3, start3 = create_sequential_child_example()
    engine3.execute_flow(start3)
    engine3.stop()
    
    # Example 4: Event-driven workflow
    engine4, producer = create_event_driven_example()
    # Execute producer to trigger events
    engine4.execute_flow(producer)
    time.sleep(2)  # Give consumers time to process
    engine4.stop()
    
    # Example 5: Multiple event publishing
    engine5 = demonstrate_multiple_event_publishing()
    time.sleep(3)  # Give time for all events to be processed
    engine5.stop()
    
    print("\n🎉 All examples completed!")


if __name__ == "__main__":
    run_all_examples() 