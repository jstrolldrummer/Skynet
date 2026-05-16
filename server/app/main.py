import json

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import require_auth
from .config import config
from .llm import OllamaClient
from .store import Store

app = FastAPI(title="Skynet", version="0.1.0")
store = Store(config.db_path)
llm = OllamaClient(config.ollama_url, config.model)


class CreateConversationBody(BaseModel):
    title: str = "New conversation"


class RenameConversationBody(BaseModel):
    title: str


class ChatBody(BaseModel):
    conversation_id: str
    content: str


@app.get("/health")
async def health():
    return {"ok": True, "model": config.model}


@app.get("/conversations", dependencies=[Depends(require_auth)])
async def list_conversations():
    return store.list_conversations()


@app.post("/conversations", dependencies=[Depends(require_auth)])
async def create_conversation(body: CreateConversationBody):
    return store.create_conversation(body.title)


@app.get(
    "/conversations/{conversation_id}/messages",
    dependencies=[Depends(require_auth)],
)
async def get_messages(conversation_id: str):
    if not store.get_conversation(conversation_id):
        raise HTTPException(404, "Conversation not found")
    return store.get_messages(conversation_id)


@app.patch(
    "/conversations/{conversation_id}",
    dependencies=[Depends(require_auth)],
)
async def rename_conversation(conversation_id: str, body: RenameConversationBody):
    if not store.get_conversation(conversation_id):
        raise HTTPException(404, "Conversation not found")
    store.rename_conversation(conversation_id, body.title)
    return {"ok": True}


@app.delete(
    "/conversations/{conversation_id}",
    dependencies=[Depends(require_auth)],
)
async def delete_conversation(conversation_id: str):
    store.delete_conversation(conversation_id)
    return {"ok": True}


@app.post("/chat", dependencies=[Depends(require_auth)])
async def chat(body: ChatBody):
    if not store.get_conversation(body.conversation_id):
        raise HTTPException(404, "Conversation not found")

    store.append_message(body.conversation_id, "user", body.content)
    history = store.get_messages(body.conversation_id)
    messages = [{"role": "system", "content": config.system_prompt}] + [
        {"role": m["role"], "content": m["content"]} for m in history
    ]

    async def event_stream():
        buf: list[str] = []
        try:
            async for chunk in llm.stream_chat(messages):
                buf.append(chunk)
                yield f"data: {json.dumps({'type': 'delta', 'content': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return
        full = "".join(buf)
        msg = store.append_message(body.conversation_id, "assistant", full)
        yield f"data: {json.dumps({'type': 'done', 'message_id': msg['id']})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
