"""WalletPress AI Agent MCP tool package.

Houses the shared FastMCP instance and the tool submodules that the
`agent.mcp_server` aggregator re-exports:

- instance   — shared FastMCP instance, logger, HITL helpers
- safety     — safety & HITL tools
- wallets    — wallet/vault tools (+ `_evm_sweep`)
- chains     — chain / agent-intel tools
- scheduling — scheduler / anomaly tools
- proof      — proof-of-generation / x402 tools

External importers (orchestrator, scheduler, main, adapters) MUST keep
importing from `agent.mcp_server`, not from this package.
"""
