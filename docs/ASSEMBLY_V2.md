# JARVIS Home — Assembly Architecture v2

Status: integration baseline for the `assembly-v2` branch. The existing `main` branch remains untouched and is the rollback target.

## Product boundary

JARVIS Home is not another general agent framework and not another device hub. It is the household safety and semantics layer between a personal AI runtime and the physical home.

```text
Voice / phone / browser / messages
                 |
                 v
OpenJarvis — models, agents, skills, memory, evaluation, channels
                 |
                 | authenticated MCP; narrow typed tools only
                 v
JARVIS Home Gateway — validation, policy, approval, workflow,
                      state verification, audit, household semantics
                 |
                 v
Home Assistant — devices, deterministic automations, protocols
                 |
        Zigbee / Matter / Z-Wave / MQTT / LAN devices
```

The language model never receives a Home Assistant token and never calls a generic Home Assistant service API directly.

## Selected components

The evidence and rejected alternatives are recorded in `ADR-0001-COMPONENT_SELECTION.md`. Immutable and pending upstream revisions are tracked in `upstreams.lock.yml`.

### OpenJarvis: personal AI runtime

OpenJarvis supplies the general intelligence substrate instead of JARVIS Home rebuilding agent loops, model routing, skills, memory backends, evaluations, telemetry, channels, or continuous operators.

Pinned upstream: `open-jarvis/OpenJarvis@6240c59ca3305c5656075cc54cd7ff32df8dca0e`.

The assembly builds the pinned upstream's official Dockerfile directly. It does not maintain a fork or a simplified replacement image.

### Home Assistant: physical control plane

Home Assistant remains the sole device abstraction and deterministic automation system. Physical controls and essential automations must continue to work when OpenJarvis, OPA, or the local LLM is unavailable.

JARVIS Home uses a dedicated token and exposes only reviewed capabilities.

### MCP: AI-to-home protocol boundary

JARVIS Home runs an authenticated Streamable HTTP MCP server. The first implemented catalog is deliberately small:

- `home_gateway_status`
- `home_observe`
- `home_propose_light_action`
- `home_list_pending_approvals`

The model cannot approve its own proposal. Approval remains in the owner-facing JARVIS Home interface. Raw generic service calls, shell access, locks, alarms, cameras, microphones, doors, and location writes are not exposed.

### OPA: pre-action policy decision point

Every write proposal is evaluated outside the LLM process by a deny-by-default Open Policy Agent policy. The gateway fails closed if OPA is unavailable, returns no decision, or denies the request.

Policy input includes:

- authenticated actor, role, and source;
- capability and exact arguments;
- target entity and domain;
- time and eventual occupancy evidence;
- emergency state;
- eventual action budget, predicted effect, and approval freshness.

OPA decides whether a proposal may enter the owner approval queue. Typed application invariants remain a separate mandatory layer.

### DBOS: durable physical workflows

DBOS is selected for the first single-home workflow layer because it embeds into the Python service and uses Postgres rather than adding a separate workflow cluster.

A production workflow must provide:

- stable workflow and action IDs;
- idempotent Home Assistant activities;
- timeouts and bounded retries;
- cancellation and compensation;
- human approval signals;
- post-action state witnesses;
- restart recovery and duplicate suppression.

Temporal remains the migration target if multi-home or multi-region scale outgrows DBOS.

### NATS JetStream: durable event bus

NATS subjects form the internal event contract and JetStream supplies replay, durable consumers, key-value state, and recovery. MQTT remains a device-edge protocol used by Home Assistant and Frigate; it is not the internal safety control plane.

Planned subjects include:

```text
home.observation.v1
home.intent.v1
home.plan.proposed.v1
home.plan.authorized.v1
home.action.requested.v1
home.action.completed.v1
home.action.failed.v1
home.alert.v1
```

### Brick Schema + Oxigraph: household digital twin

Brick represents rooms, floors, equipment, sensors, points, feeds, controls, and relationships. Oxigraph provides an embedded RDF/SPARQL store without requiring a large graph-database service.

The twin will retain reported, desired, and predicted state plus freshness, confidence, provenance, relationships, and safety constraints. Presence remains uncertain evidence, not proof of identity.

### Voice and vision profiles

Home Assistant Voice and Wyoming are selected for room satellites, local wake words, local speech pipelines, physical microphone mute, and degraded-mode home control.

LiveKit is an optional browser/phone realtime media profile. Frigate is an optional local vision/NVR profile. Continuous camera footage never enters general conversational memory; only reviewed structured events and explicitly requested images cross the boundary.

### Operations and supply chain

- OpenTelemetry instrumentation with Grafana-compatible backends;
- restic encrypted and verifiable backups;
- SOPS + age for declarative secrets;
- SBOM, dependency, image, and policy scanning in CI;
- pinned upstream revisions and image digests;
- staged upgrades with compatibility tests and rollback;
- no unattended production auto-update of home-control services;
- private LAN or WireGuard-based remote access, never direct public exposure.

## Components deliberately not selected for the first assembly

- A second general agent runtime such as OpenClaw: duplicates OpenJarvis and expands attack surface.
- Direct state-changing Home Assistant MCP tools: bypass the household safety gateway.
- Cedar and OPA together: two policy systems would drift; Cedar is deferred to a formal-verification profile.
- Temporal: excellent but operationally heavier than the first single-home deployment needs.
- Restate: technically attractive, but the server is BSL-1.1 rather than OSI open source.
- Eclipse Ditto: too much operational weight for the initial single-home semantic model.
- Node-RED or n8n as safety authority: useful integrations may call the gateway, but cannot replace it.
- Kubernetes for the first deployment: Compose has a smaller initial failure surface.

## Degradation hierarchy

1. Physical controls and Home Assistant deterministic automations.
2. JARVIS Home owner UI, policy gateway, and safe manual actions.
3. OpenJarvis local agents, skills, and memory.
4. Open-ended conversation and optional remote/cloud collaboration.

Failure of a higher layer must not disable a lower layer.

## Current executable slice

Implemented on `assembly-v2`:

1. OpenJarvis is pinned and built from its official upstream Dockerfile.
2. OpenJarvis receives only four authenticated MCP tools.
3. Home observations are read-only.
4. The only write proposal is a typed light action.
5. OPA is deny-by-default and fails closed.
6. An allowed proposal enters the existing owner approval queue.
7. The model has no approval capability.
8. Existing owner UI, encrypted Home Assistant credential, and audit chain remain in place.
9. OPA policy tests, Python tests, static checks, Compose validation, and container builds are defined in CI.
10. `main` remains unchanged.

## Promotion gate

The slice is not promoted to `main` until it additionally proves:

1. owner approval enters a DBOS durable workflow;
2. every action carries an idempotency key;
3. duplicate delivery cannot duplicate the physical action;
4. the reported entity state satisfies a postcondition;
5. failures and restart recovery are tested;
6. NATS contains a replayable event trail;
7. the user sees success only after state verification;
8. disabling OpenJarvis leaves Home Assistant automations operational;
9. all CI and real Docker integration tests pass.
