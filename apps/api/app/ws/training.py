"""WebSocket handler for real-time training sessions.

Protocol (from TZ section 7.8):
- Client sends: session.start, audio.chunk, text.message, session.end
- Server sends: session.ready, transcription.result, character.response, emotion.update, error

Full implementation in Phase 1, Weeks 4-5.
"""

import json

from fastapi import WebSocket, WebSocketDisconnect


async def training_websocket(websocket: WebSocket):
    """Handle a training session WebSocket connection."""
    await websocket.accept()

    try:
        # Send ready signal
        await websocket.send_json({
            "type": "session.ready",
            "data": {"message": "WebSocket connected. Training session ready."},
        })

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "session.start":
                await websocket.send_json({
                    "type": "session.started",
                    "data": {"session_id": message.get("data", {}).get("session_id")},
                })

            elif msg_type == "audio.chunk":
                # Stub: will integrate with STT in Phase 1, Week 4
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Audio processing not yet implemented"},
                })

            elif msg_type == "text.message":
                # Stub: will integrate with LLM in Phase 2
                content = message.get("data", {}).get("content", "")
                await websocket.send_json({
                    "type": "character.response",
                    "data": {
                        "content": f"[Stub] Received: {content[:50]}...",
                        "emotion": "cold",
                    },
                })

            elif msg_type == "session.end":
                await websocket.send_json({
                    "type": "session.ended",
                    "data": {"message": "Session ended"},
                })
                break

            else:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": f"Unknown message type: {msg_type}"},
                })

    except WebSocketDisconnect:
        pass
