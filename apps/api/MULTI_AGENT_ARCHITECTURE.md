# LangGraph Assistant Architecture

## Runtime

- `AssistantOrchestrator` is the central AI runtime for `/api/v1/ai/assistant`, `/ai/plan`, `/ai/create-event`, voice command parsing, and image import preview.
- The first reasoning hop is always `gpt-4o-mini`.
- `gpt-5.4-mini` is exposed to the frontline agent as the `delegate_to_smarter_model` tool for planning, optimization, conflict resolution, destructive actions, and batch changes.
- Billing feature classification is deterministic and runs before the agent call.

## Graph Flow

1. Load conversation state, memory, timezone, pending confirmation, and compact chat history.
2. Resolve pending confirmations or rejections from Redis-backed conversation state.
3. Build the `gpt-4o-mini` frontend agent context and expose safe calendar tools plus `delegate_to_smarter_model`.
4. Let the model decide whether to answer, call tools directly, or delegate to `gpt-5.4-mini`.
5. Run selected tools against `AssistantToolRegistry`; delegated model mutations are forced to dry-run previews.
6. Derive response routing metadata from actual tool usage and return the existing `AssistantMessageResponse` shape expected by the frontend.

## Safety

- Simple single-event creation can execute immediately.
- Complex, destructive, bulk, conflict, and optimization flows run as previews first.
- Previewed actions are stored in `ConversationState.planning_state` with a confirmation token.
- The frontend applies changes by sending `confirm=true` and the token; stale tokens are rejected.
