# Extension guide

## Adding a core tool

A tool has five mandatory properties:

- globally unique stable name;
- precise description for the model;
- restrictive JSON Schema;
- declared baseline risk;
- handler that returns JSON-serializable data.

```python
from jarvis_home.schemas import RiskLevel
from jarvis_home.tool_registry import ToolDefinition

registry.register(
    ToolDefinition(
        name="garden.moisture",
        description="Read the current garden soil moisture percentage.",
        parameters={
            "type": "object",
            "required": ["zone"],
            "properties": {"zone": {"type": "string", "enum": ["north", "south"]}},
            "additionalProperties": False,
        },
        risk=RiskLevel.LOW,
        handler=read_moisture,
    )
)
```

Never use a permissive `arguments: object` schema when the fields are known. The policy engine can only reason about arguments that are represented clearly.

## Dynamic risk

Baseline risk belongs to the tool. Argument-sensitive escalation belongs to `PolicyEngine._dynamic_risk`. Examples:

- `lock.unlock` is high risk regardless of the baseline;
- camera and location reads are privacy-sensitive;
- generic service calls to lights or climate still require confirmation because they change the physical environment.

Do not encode risk only in prompts. Prompts are advisory; policy code is authoritative.

## Plugin contract

A plugin is a local `.py` file in `plugins/` with:

```python
def register(registry, services):
    ...
```

Available services currently include `db`, `settings`, `events`, `memory`, and `audit`. This is a trusted-code extension point, not a sandbox. Plugins are disabled by default and loaded only when both the global flag and exact stem allowlist permit them.

## Adding an integration

Create an adapter in `jarvis_home/integrations/` that:

- owns protocol details;
- uses explicit timeouts;
- raises descriptive domain exceptions;
- never logs credentials;
- returns compact structured data;
- exposes a health method;
- is created from runtime settings rather than hard-coded globals.

Register narrow tools around the adapter. Avoid a generic unrestricted HTTP tool because it creates SSRF and credential-exfiltration paths.

## Database evolution

The current schema version is stored in `schema_meta`. For a future version:

1. Add an idempotent migration function.
2. Run migrations inside an exclusive write phase before serving requests.
3. Back up before destructive transformations.
4. Preserve downgrade or export instructions.
5. Add migration tests using a fixture created by the prior release.

## UI

The dashboard uses dependency-free HTML, CSS, and JavaScript so the backend wheel contains the complete interface and no Node build chain is required. Keep all dynamic content assigned through `textContent`; do not introduce unsanitized `innerHTML`.

## Testing expectations

- Policy test for every new physical or privacy-sensitive action.
- Adapter tests with mocked HTTP responses.
- Approval replay/expiry tests for state-changing tools.
- Root-escape tests for filesystem features.
- API authentication test for every new router.
- Audit assertion for mutations.
