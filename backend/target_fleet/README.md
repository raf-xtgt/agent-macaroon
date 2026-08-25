# target_fleet/

Drop your ADK multi-agent system here.

agent-macaroon will auto-discover, register, and govern it.

## How to use

1. Clone or copy your ADK agent package into this folder.
2. The package must have an `agent.py` that exports `root_agent`.
3. Run `adk web ./agents/governed` — your fleet runs with zero-trust governance.

## Example (global-kyc-agent)

```bash
# Symlink Google's KYC sample into target_fleet/
ln -s /path/to/adk-samples/python/agents/global-kyc-agent/global_kyc_agent target_fleet/global_kyc_agent
```

## What happens automatically

- All agents in the tree are registered with scope ceilings derived from their tools.
- Every tool call and agent handoff is intercepted by the GatewayPlugin.
- Unknown tools are denied by default (fail-closed).
- If you provide a `tool_map.yaml` in this folder, it overrides the default verb mapping.
