# Utilities

The `mi_utilities` package provides shared infrastructure for caching and thread-safe execution.

## Installation

Utilities are included with `mi-core`:

```python
from mi.utilities import cache, root_executor, bound
```

## Cache Adapter

Thread-safe TTL cache with singleflight semantics—prevents duplicate work when multiple threads request the same cached value simultaneously.

### Basic Usage

```python
from mi.utilities import cache

@cache()
def expensive_operation(key):
    # This result is cached
    return compute_something(key)

# First call computes and caches
result1 = expensive_operation("key1")

# Second call returns cached value
result2 = expensive_operation("key1")
```

### With Custom Key Function

```python
from mi.utilities import cache, resolved_path_key

@cache(key_fn=lambda path: resolved_path_key(path))
def load_file(path):
    return Path(path).read_text()

# Both calls use the same cache entry (resolved to same path)
load_file("./data/file.txt")
load_file("data/file.txt")
```

### For Methods

```python
from mi.utilities import cached_method

class DataLoader:
    @cached_method()
    def load(self, key):
        # Cached per instance + key
        return fetch_data(key)
```

### Cache Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `key_fn` | None | Custom function to generate cache keys |
| `namespace` | function name | Cache namespace for isolation |
| `log_misses` | False | Log cache misses for debugging |

### Singleflight Behavior

When multiple threads request the same uncached key simultaneously:

1. First thread starts computing
2. Other threads wait (don't duplicate work)
3. All threads receive the same result

```python
# Thread 1 and Thread 2 call simultaneously
# Only one computation happens
result1 = expensive_operation("same_key")  # Thread 1 - computes
result2 = expensive_operation("same_key")  # Thread 2 - waits, gets same result
```

### Cache Control

```python
@cache()
def my_function(key):
    return compute(key)

# Clear the entire shared cache
my_function.cache_clear()
```

## Root Executor

Enables worker threads and child processes to execute functions on the main thread—essential for libraries that aren't thread-safe.

### Problem

Some libraries fail when called from worker threads:

```python
# This may crash or produce wrong results in a worker thread
import thread_unsafe_library

def worker():
    thread_unsafe_library.process(data)  # NOT THREAD SAFE!
```

### Solution

Use `RootExecutor` to route calls back to the main thread:

```python
from mi.utilities import root_executor, bound

# Initialize in main thread BEFORE spawning workers
root_executor.initialize()

@bound
def safe_operation(data):
    # Always runs on main thread, even when called from workers
    return thread_unsafe_library.process(data)

def worker():
    result = safe_operation(data)  # Redirected to main thread
```

### Basic Usage

#### Module-Level API

```python
from mi.utilities import root_executor

# Initialize (call from main thread)
root_executor.initialize()

# Explicit execution
result = root_executor.run(unsafe_func, arg1, arg2)

# Cleanup
root_executor.shutdown()
```

#### Decorator API

```python
from mi.utilities import bound

@bound
def unsafe_operation(data):
    return thread_unsafe_library.process(data)

# Called from any thread - automatically routed to main
result = unsafe_operation(data)
```

#### Context Manager

```python
from mi.utilities import RootExecutor

with RootExecutor() as executor:
    # Workers can use executor.run() or @bound
    orchestrator.run(items)
# Automatically cleaned up
```

### How It Works

1. **Context Detection**: Automatically detects if code is running in:
   - Root context (main process + main thread) → executes directly
   - Child thread → routes via thread queue
   - Child process → routes via process queue

2. **Request Queue**: Workers put requests on a queue
3. **Pump Thread**: Background thread processes requests on main thread
4. **Response**: Results (or exceptions) returned to caller

### With Pipeline Orchestrator

```python
from mi.utilities import root_executor, bound
from mi.core import PipelineOrchestrator, OrchestratorConfig

# Initialize before creating orchestrator
root_executor.initialize()

class MyProcessor(BaseProcessor):
    @bound
    def call_unsafe_library(self, data):
        return unsafe_library.process(data)

    def process(self, data_object, *, metadata=None):
        result = self.call_unsafe_library(data_object.data)
        data_object.set_artifact("result", result)

# Run orchestrator with multiple workers
orchestrator = PipelineOrchestrator(
    builder=builder,
    adapter=adapter,
    config=OrchestratorConfig(runtime="threaded", max_workers=4),
)

receipts = orchestrator.run(items)

# Cleanup
root_executor.shutdown()
```

### API Reference

#### Module Functions

| Function | Description |
|----------|-------------|
| `initialize()` | Start the global executor (call from main thread) |
| `shutdown()` | Stop the global executor |
| `run(func, *args, **kwargs)` | Execute function via executor |
| `get_executor()` | Get the global executor instance |

#### Decorator

```python
@bound
def my_function():
    pass

@bound(executor=custom_executor)
def my_function():
    pass
```

#### RootExecutor Class

```python
executor = RootExecutor()
executor.start()

result = executor.run(func, *args, **kwargs)
context = executor.get_context()  # ROOT, CHILD_THREAD, or CHILD_PROCESS

executor.stop()
```

### Execution Contexts

```python
from mi.utilities import ExecutionContext

context = executor.get_context()

if context == ExecutionContext.ROOT:
    # Main process, main thread
    pass
elif context == ExecutionContext.CHILD_THREAD:
    # Main process, worker thread
    pass
elif context == ExecutionContext.CHILD_PROCESS:
    # Child process (any thread)
    pass
```

### Exception Handling

Exceptions from the main thread are propagated back to the caller:

```python
@bound
def failing_function():
    raise ValueError("Something went wrong")

try:
    failing_function()  # Called from worker
except ValueError as e:
    # Exception propagated from main thread
    print(f"Caught: {e}")
```

### Serialization (Process Mode)

For process-based execution, functions and arguments must be picklable:

```python
# OK - module-level function
@bound
def process_data(data):
    return unsafe_lib.process(data)

# NOT OK - lambda or closure
bound_lambda = bound(lambda x: x)  # Will fail in process mode
```

## Best Practices

### Caching

1. **Use for expensive operations** - File I/O, network calls, computations
2. **Consider key functions** - Normalize paths, canonicalize inputs
3. **Log misses during development** - `log_misses=True`
4. **Clear cache when needed** - `.cache_clear()` after data changes

### Root Executor

1. **Initialize early** - Before creating workers
2. **Shutdown properly** - Use context manager or explicit `shutdown()`
3. **Minimize routed calls** - Only route what's truly unsafe
4. **Test thread safety** - Verify libraries actually need routing
5. **Handle exceptions** - They propagate across thread boundaries

---

## See Also

- [Orchestrator](orchestrator.md) — parallel pipeline execution where these utilities are most needed
- [Retrievers](components/retrievers.md) — using `@cache` in retriever implementations
