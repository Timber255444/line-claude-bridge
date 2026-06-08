import os
import hmac
import hashlib
import base64
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from database import (
    init_db, save_message, query_messages, get_recent_messages,
    save_group_name, get_groups, save_user_name, get_users,
)

app = FastAPI()

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
API_KEY = os.environ["BRIDGE_API_KEY"]


def verify_line_signature(body: bytes, signature: str) -> bool:
    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


async def fetch_group_name(group_id: str) -> str:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return group_id
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.line.me/v2/bot/group/{group_id}/summary",
                headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
                timeout=5,
            )
            if r.status_code == 200:
                return r.json().get("groupName", group_id)
    except Exception:
        pass
    return group_id


async def fetch_user_name(user_id: str, group_id: str) -> str:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return user_id
    try:
        async with httpx.AsyncClient() as client:
            url = (
                f"https://api.line.me/v2/bot/group/{group_id}/member/{user_id}"
                if group_id != "direct"
                else f"https://api.line.me/v2/bot/profile/{user_id}"
            )
            r = await client.get(
                url,
                headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
                timeout=5,
            )
            if r.status_code == 200:
                return r.json().get("displayName", user_id)
    except Exception:
        pass
    return user_id


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def startup():
    init_db()


@app.post("/webhook")
async def webhook(request: Request, x_line_signature: str = Header(...)):
    body = await request.body()
    if not verify_line_signature(body, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    data = await request.json()
    print(f"[WEBHOOK] events={len(data.get('events', []))}")
    for event in data.get("events", []):
        source = event.get("source", {})
        group_id = source.get("groupId") or source.get("roomId") or "direct"
        user_id = source.get("userId", "unknown")
        event_type = event.get("type")
        msg_type = event.get("message", {}).get("type") if event_type == "message" else "-"
        print(f"[EVENT] type={event_type} user={user_id[:12] if user_id != 'unknown' else 'unknown'} group={group_id[:12] if group_id != 'direct' else 'direct'} msg_type={msg_type}")

        # joinイベントでグループ名を取得・保存
        if event.get("type") == "join" and group_id != "direct":
            name = await fetch_group_name(group_id)
            save_group_name(group_id, name)

        if event.get("type") != "message":
            continue
        msg = event.get("message", {})
        if msg.get("type") != "text":
            continue

        # グループ名が未登録なら取得
        if group_id != "direct":
            groups = get_groups()
            if group_id not in groups:
                name = await fetch_group_name(group_id)
                save_group_name(group_id, name)

        # ユーザー名が未登録なら取得
        users = get_users()
        if user_id not in users:
            display_name = await fetch_user_name(user_id, group_id)
            save_user_name(user_id, display_name)

        save_message(
            group_id=group_id,
            user_id=user_id,
            text=msg["text"],
            timestamp=datetime.fromtimestamp(event["timestamp"] / 1000),
        )

    return JSONResponse({"status": "ok"})


class SendRequest(BaseModel):
    group_id: str
    text: str


@app.post("/send")
async def send_message(body: SendRequest, x_api_key: str = Header(...)):
    _require_api_key(x_api_key)
    if not LINE_CHANNEL_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="LINE_CHANNEL_ACCESS_TOKEN not set")
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "to": body.group_id,
                "messages": [{"type": "text", "text": body.text}],
            },
            timeout=10,
        )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"LINE API error: {r.text}")
    return {"status": "sent"}


def _require_api_key(key: str):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


def _enrich(rows: list[dict]) -> list[dict]:
    groups = get_groups()
    users = get_users()
    for r in rows:
        r["group_name"] = groups.get(r["group_id"], r["group_id"])
        r["display_name"] = users.get(r["user_id"], r["user_id"])
    return rows


@app.get("/messages/recent")
async def recent(limit: int = 50, group_id: str = None, x_api_key: str = Header(...)):
    _require_api_key(x_api_key)
    return {"messages": _enrich(get_recent_messages(limit=limit, group_id=group_id))}


@app.get("/messages/search")
async def search(q: str, group_id: str = None, x_api_key: str = Header(...)):
    _require_api_key(x_api_key)
    return {"messages": _enrich(query_messages(keyword=q, group_id=group_id))}


@app.get("/groups")
async def list_groups(x_api_key: str = Header(...)):
    _require_api_key(x_api_key)
    return {"groups": get_groups()}
