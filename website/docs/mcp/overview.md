---

title: "MCP Server — AI Agent Wallet Orchestration"
description: "30+ MCP tools for wallet operations. HITL flow: agent_plan → agent_confirm → agent_execute. LangChain, CrewAI, Eliza, OpenAI Agents, Vercel AI adapters included."
keywords: [mcp, model context protocol, ai agents, wallet, langchain, crewai, eliza, openai agents]
unlisted: false
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';


**Beta**

**Every wallet operation is an MCP tool.** The agent plans with `agent_plan`, asks for confirmation with `agent_confirm`, executes with `agent_execute`. The HITL flow is the agent's moral compass.

---

## Quickstart

```bash
# Connect to MCP server (SSE)
mcp-client connect http://localhost:8010/mcp/sse

# Or via stdio (for local agents)
walletpress mcp --stdio
```

**Available in:** REST API, MCP, CLI, WordPress — same operations, four surfaces.

---

## HITL Flow (Human-In-The-Loop)

Every agent interaction follows this pattern:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. agent_plan                                               │
│    Agent proposes action with reasoning and risk assessment │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. agent_confirm                                            │
│    Human reviews: action, params, risk, cost, Arweave proof │
│    → Approve / Reject / Modify                              │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. agent_execute                                            │
│    Executes on approval. Returns tx hash, Arweave proof.   │
└─────────────────────────────────────────────────────────────┘
```

**Code Example:**

```python
from walletpress_mcp import WalletPressMCP

mcp = WalletPressMCP("http://localhost:8010/mcp/sse")

# Agent proposes
plan = await mcp.agent_plan({
    "action": "generate_wallet",
    "params": {"chains": ["ethereum", "solana"], "label": "agent-wallet-001"},
    "reasoning": "Need new wallet for automated trading",
    "risk": "low",
    "estimated_cost_usd": 0.01
})

# Human reviews and confirms
if human_approves(plan):
    result = await mcp.agent_execute(plan.id)
    print(result)  # {"wallet_id": "wlt_...", "tx_hash": "...", "arweave_proof": "..."}
```

---

## Available Tools (30+)

### Wallet Generation

| Tool                   | Description                   | HITL Required |
| ---------------------- | ----------------------------- | ------------- |
| `generate_wallet`      | Create new multi-chain wallet | Yes           |
| `derive_address`       | Derive address at path        | Yes           |
| `derive_batch`         | Derive multiple addresses     | Yes           |
| `wallet_from_mnemonic` | Restore wallet from mnemonic  | Yes           |

### Wallet Management

| Tool            | Description        | HITL Required        |
| --------------- | ------------------ | -------------------- |
| `list_wallets`  | List all wallets   | No                   |
| `get_wallet`    | Get wallet details | No                   |
| `update_wallet` | Update metadata    | Yes                  |
| `delete_wallet` | Soft delete        | Yes                  |
| `purge_wallet`  | Irreversible erase | Yes (double confirm) |

### Address Operations

| Tool             | Description                | HITL Required |
| ---------------- | -------------------------- | ------------- |
| `list_addresses` | List all derived addresses | No            |
| `get_address`    | Get address details        | No            |

### Signing

| Tool               | Description                | HITL Required |
| ------------------ | -------------------------- | ------------- |
| `sign_transaction` | Sign raw transaction       | Yes           |
| `sign_message`     | Sign message (EIP-191/712) | Yes           |
| `sign_typed_data`  | Sign EIP-712 typed data    | Yes           |

### x402 Operations

| Tool                   | Description                      | HITL Required       |
| ---------------------- | -------------------------------- | ------------------- |
| `x402_generate_wallet` | Generate wallet via x402 payment | Yes (payment proof) |
| `x402_check_balance`   | Check x402 credit balance        | No                  |

### Utility

| Tool                | Description                       | HITL Required |
| ------------------- | --------------------------------- | ------------- |
| `get_arweave_proof` | Retrieve Arweave proof for wallet | No            |
| `verify_proof`      | Verify Arweave proof              | No            |
| `health_check`      | System health                     | No            |

---

## Framework Adapters

### LangChain

```python
from langchain.agents import Tool
from walletpress_mcp import WalletPressMCP

mcp = WalletPressMCP("http://localhost:8010/mcp/sse")

tools = [
    Tool(
        name="generate_wallet",
        func=lambda params: mcp.agent_execute("generate_wallet", params),
        description="Generate multi-chain wallet. Requires HITL approval."
    ),
    Tool(
        name="sign_transaction",
        func=lambda params: mcp.agent_execute("sign_transaction", params),
        description="Sign transaction. Requires HITL approval."
    ),
]

agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
```

### CrewAI

```python
from crewai import Agent, Task, Crew
from walletpress_mcp import WalletPressMCP

mcp = WalletPressMCP("http://localhost:8010/mcp/sse")

wallet_agent = Agent(
    role="Wallet Manager",
    goal="Manage wallets for trading operations",
    backstory="Expert in multi-chain wallet operations and security",
    tools=[
        mcp.get_tool("generate_wallet"),
        mcp.get_tool("sign_transaction"),
        mcp.get_tool("list_wallets"),
    ],
    allow_delegation=False
)

task = Task(
    description="Generate wallet for new trading pair and sign first transaction",
    agent=wallet_agent,
    expected_output="Wallet ID, addresses, and signed transaction hash"
)

crew = Crew(agents=[wallet_agent], tasks=[task])
result = crew.kickoff()
```

### Eliza (AI16z)

```typescript
import { WalletPressMCP } from '@walletpress/mcp-client';

const mcp = new WalletPressMCP('http://localhost:8010/mcp/sse');

const walletPlugin = {
  name: 'walletpress',
  description: 'WalletPress MCP integration',
  actions: [
    {
      name: 'GENERATE_WALLET',
      description: 'Generate a new multi-chain wallet',
      handler: async (params) => {
        return await mcp.agent_execute('generate_wallet', params);
      },
    },
  ],
};
```

### OpenAI Agents SDK

```python
from openai_agents import Agent, Runner
from walletpress_mcp import WalletPressMCP

mcp = WalletPressMCP("http://localhost:8010/mcp/sse")

agent = Agent(
    name="Wallet Operator",
    instructions="You manage wallets for users. Always use HITL flow.",
    tools=[
        mcp.get_tool("generate_wallet"),
        mcp.get_tool("sign_transaction"),
        mcp.get_tool("list_wallets"),
    ],
)

result = await Runner.run(agent, "Create wallet for ETH and SOL, then sign a 0.01 ETH transfer")
```

### Vercel AI SDK

```typescript
import { streamText, tool } from 'ai';
import { WalletPressMCP } from '@walletpress/mcp-client';

const mcp = new WalletPressMCP('http://localhost:8010/mcp/sse');

const result = await streamText({
  model: openai('gpt-4o'),
  tools: {
    generate_wallet: tool({
      description: 'Generate multi-chain wallet',
      parameters: z.object({
        chains: z.array(z.string()),
        label: z.string(),
      }),
      execute: async ({ chains, label }) => {
        return await mcp.agent_execute('generate_wallet', { chains, label });
      },
    }),
  },
  prompt: 'Generate wallet for Ethereum and Solana',
});
```

---

## Connection Methods

### SSE (Recommended for Remote)

```python
mcp = WalletPressMCP("http://localhost:8010/mcp/sse")
```

### stdio (For Local Agents)

```bash
walletpress mcp --stdio
```

```python
mcp = WalletPressMCP.stdio()
```

### WebSocket (For Real-Time)

```python
mcp = WalletPressMCP("ws://localhost:8010/mcp/ws")
```

---

## Authentication

```python
# Bearer token (REST API style)
mcp = WalletPressMCP(
    "http://localhost:8010/mcp/sse",
    auth_token="Bearer wp_live_EXAMPLE"
)

# Or API key
mcp = WalletPressMCP(
    "http://localhost:8010/mcp/sse",
    api_key="wp_live_EXAMPLE"
)
```

---

## Error Handling

```python
from walletpress_mcp import MCPError, HITLRejectedError, VaultLockedError

try:
    result = await mcp.agent_execute(plan.id)
except HITLRejectedError as e:
    print(f"Human rejected: {e.reason}")
except VaultLockedError:
    print("Vault is locked — check VAULT_KEY")
except MCPError as e:
    print(f"MCP error: {e.code} — {e.message}")
```

---

## Rate Limits

| Tier       | Requests/Minute | Concurrent Sessions |
| ---------- | --------------- | ------------------- |
| Free       | 60              | 2                   |
| Pro        | 300             | 10                  |
| Enterprise | 1000            | 50                  |

---

## Self-Hosting MCP

```bash
# Enable in docker-compose.yml
environment:
  - MCP_ENABLED=true
  - MCP_PORT=8011  # optional, defaults to 8010/mcp
```

---

## Next

- [MCP Tools Reference →](mcp/tools.md)
- [HITL Flow Deep Dive →](mcp/hitl-flow.md)
- [Framework Adapters →](mcp/framework-adapters.md)
- [REST API Reference →](../api/wallet-generation.md)
