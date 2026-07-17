# Actions

Actions execute side effects based on decisions from the processed data. They are the final stage of the pipeline.

## Overview

Actions are responsible for:
- Reading decisions from the ActionDataObject
- Executing side effects (save to database, send notifications, publish events)
- Logging completion status

**Important:** Actions should be idempotent when possible—running the same action twice with the same data should produce the same result.

## Creating an Action

### Basic Structure

```python
from mi.core.actions import BaseAction, BaseActionConfig
from my_project.objects import MyActionObject

class MyActionConfig(BaseActionConfig):
    # Add configuration fields
    destination: str
    notify_on_complete: bool = True

class MyAction(BaseAction[MyActionObject]):
    def __init__(self, config: MyActionConfig | None = None) -> None:
        super().__init__(config)
        self.destination = config.destination if config else "default"
        self.notify = config.notify_on_complete if config else True

    def act(self, data_object: MyActionObject, *, metadata=None) -> None:
        """Execute the action.

        Args:
            data_object: The ActionDataObject containing decisions
            metadata: Optional pipeline metadata

        Returns:
            None - actions do not return values
        """
        # Read decisions
        summary = data_object.get_decision("summary")

        # Execute side effect
        self.save_summary(summary)

        if self.notify:
            self.send_notification(summary)

        self.logger.info(f"Action completed: saved to {self.destination}")

    def save_summary(self, summary: dict) -> None:
        # Implementation
        pass

    def send_notification(self, summary: dict) -> None:
        # Implementation
        pass
```

### Key Points

1. **No return value** - `act()` returns `None`
2. **Side effects** - Actions perform external operations
3. **Read decisions** - Use `get_decision()` to access data
4. **Logging** - Use `self.logger` for observability

## Working with Decisions

### Reading Decisions

```python
def act(self, data_object, *, metadata=None):
    # Get a specific decision
    summary = data_object.get_decision("summary")

    # Get optional decision with default
    alerts = data_object.decisions.get("alerts", [])

    # List all decisions
    all_decisions = data_object.list_decisions()
```

### Using Typed ActionDataObject

```python
class ReportAction(BaseAction[ReportActionObject]):
    def act(self, data_object: ReportActionObject, *, metadata=None):
        # Use typed property accessors
        report = data_object.report  # @property accessor
        recipients = data_object.recipients

        self.send_report(report, recipients)
```

## Using Pipeline Metadata

Access metadata for context-aware actions:

```python
def act(self, data_object, *, metadata=None):
    if metadata:
        unit = metadata.unit  # e.g., tenant_id
        self.logger.info(f"Executing action for unit: {unit}")

        # Customize action based on metadata
        destination = f"results/{unit}"
        self.save_to(destination)
```

## Common Action Types

### Database Action

```python
class DatabaseSaveAction(BaseAction[MyActionObject]):
    def __init__(self, config=None):
        super().__init__(config)
        self.connection = create_db_connection()

    def act(self, data_object, *, metadata=None):
        summary = data_object.get_decision("summary")

        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO summaries (data, created_at) VALUES (?, ?)",
                (json.dumps(summary), datetime.now())
            )
            self.connection.commit()

        self.logger.info("Saved summary to database")
```

### Notification Action

```python
class EmailNotificationAction(BaseAction[AlertActionObject]):
    def __init__(self, config=None):
        super().__init__(config)
        self.smtp_client = create_smtp_client()

    def act(self, data_object, *, metadata=None):
        alerts = data_object.get_decision("alerts")

        if not alerts:
            self.logger.info("No alerts to send")
            return

        for alert in alerts:
            self.send_email(
                subject=f"Alert: {alert['type']}",
                body=alert['message'],
                recipients=alert.get('recipients', ['admin@example.com'])
            )

        self.logger.info(f"Sent {len(alerts)} alert emails")
```

### API Action

```python
class WebhookAction(BaseAction[EventActionObject]):
    def __init__(self, config=None):
        super().__init__(config)
        self.webhook_url = config.webhook_url if config else None

    def act(self, data_object, *, metadata=None):
        event = data_object.get_decision("event")

        response = requests.post(
            self.webhook_url,
            json=event,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code != 200:
            self.logger.error(f"Webhook failed: {response.status_code}")
            raise RuntimeError(f"Webhook returned {response.status_code}")

        self.logger.info("Event published to webhook")
```

### File Export Action

```python
class CsvExportAction(BaseAction[ReportActionObject]):
    def __init__(self, config=None):
        super().__init__(config)
        self.output_dir = Path(config.output_dir if config else "output")

    def act(self, data_object, *, metadata=None):
        report_data = data_object.get_decision("report_data")

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.output_dir / f"report_{timestamp}.csv"

        # Write CSV
        df = pd.DataFrame(report_data)
        df.to_csv(filename, index=False)

        self.logger.info(f"Exported report to {filename}")
```

## Multiple Actions

Pipelines can have multiple actions that run in sequence:

```python
pipeline = (
    PipelineBuilder()
    # ... retrievers, processors, hydrators ...
    .add_action(DatabaseSaveAction())
    .add_action(EmailNotificationAction())
    .add_action(WebhookAction())
    .with_action_hydrator(FinalizeHydrator())
    .build()
)
```

All actions receive the same `ActionDataObject` and run in the order they were added.

## Error Handling

### Handling Action Failures

```python
class ResilientAction(BaseAction[MyActionObject]):
    def act(self, data_object, *, metadata=None):
        try:
            self.perform_action(data_object)
        except ConnectionError as e:
            self.logger.error(f"Connection failed: {e}")
            # Optionally retry or fall back
            self.fallback_action(data_object)
        except Exception as e:
            self.logger.error(f"Action failed: {e}")
            raise  # Re-raise to mark pipeline as failed
```

### Validation Before Acting

```python
class ValidatingAction(BaseAction[MyActionObject]):
    def act(self, data_object, *, metadata=None):
        # Validate required decisions exist
        if "summary" not in data_object.decisions:
            self.logger.warning("No summary decision, skipping action")
            return

        summary = data_object.get_decision("summary")

        # Validate decision content
        if not summary.get("total"):
            self.logger.warning("Summary missing 'total', skipping")
            return

        self.perform_action(summary)
```

## Best Practices

1. **Idempotent when possible** - Same input should produce same result
2. **Handle failures gracefully** - Log errors, consider retries
3. **Validate inputs** - Check decisions exist before using
4. **Keep actions focused** - One action, one responsibility
5. **Use logging** - Track what actions are doing
6. **Don't modify data** - Actions should only read, not write to data objects
7. **Consider ordering** - Actions run in sequence; order matters

---

## See Also

- [Hydrators](hydrators.md) — the process hydrator that creates `ActionDataObject` for actions
- [Data Objects](data-objects.md) — the `ActionDataObject` structure actions consume
- [Orchestrator](../orchestrator.md) — running actions at scale across multiple items
