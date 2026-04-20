"""WS event type constants and payload schemas for MCP tool lifecycle.

All three events flow from the training/pvp WS endpoints to the frontend.
They are emitted by ``ws/training.py`` (Phase 1.7) after ``dispatch()`` returns.

Keeping the names in a separate module makes them easy to grep for and
gives the frontend a single import point when we add typing for the WS
message union.
"""

from __future__ import annotations

# Emitted BEFORE the tool handler runs so the frontend can render a
# "AI is generating an image…" indicator. Payload shape:
#   {
#       "type": "assistant.tool_call",
#       "call_id": str,          # unique per invocation, matches result/error
#       "name": str,             # registered tool name
#       "arguments": dict,       # exact arguments the model produced
#   }
TOOL_CALL_EVENT = "assistant.tool_call"

# Emitted AFTER a successful handler return. Payload shape:
#   {
#       "type": "assistant.tool_result",
#       "call_id": str,
#       "name": str,
#       "result": dict,          # whatever the handler returned
#   }
TOOL_RESULT_EVENT = "assistant.tool_result"

# Emitted when the handler raised or a guard fired. Payload shape:
#   {
#       "type": "assistant.tool_error",
#       "call_id": str,
#       "name": str,
#       "error": {"code": str, "message": str},
#       "fatal": bool,           # if true, LLM turn is aborted
#   }
TOOL_ERROR_EVENT = "assistant.tool_error"
