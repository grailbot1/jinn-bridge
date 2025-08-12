from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import os, httpx

app = FastAPI()

class BridgeIn(BaseModel):
    text: str
    mode: str | None = "issue"   # "issue" or "dispatch"
    event_type: str | None = "jinn_trigger"
    client_meta: dict | None = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/version")
def version():
    return {"sha": os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown")}

def gh_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

async def post_issue_comment(repo: str, issue: str, token: str, body: str):
    url = f"https://api.github.com/repos/{repo}/issues/{issue}/comments"
    async with httpx.AsyncClient(timeout=20.0) as cx:
        r = await cx.post(url, headers=gh_headers(token), json={"body": body})
    return r.status_code, r.text

async def repo_dispatch(repo: str, token: str, event_type: str, payload: dict):
    url = f"https://api.github.com/repos/{repo}/dispatches"
    async with httpx.AsyncClient(timeout=20.0) as cx:
        r = await cx.post(url, headers=gh_headers(token),
                          json={"event_type": event_type, "client_payload": payload})
    return r.status_code, r.text

@app.post("/bridge")
async def bridge(data: BridgeIn, authorization: str | None = Header(None)):
    if authorization != f"Bearer {os.getenv('BRIDGE_TOKEN', '')}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    repo = os.getenv("GH_REPO"); issue = os.getenv("GH_ISSUE"); token = os.getenv("GH_TOKEN")
    if not (repo and token and (data.mode == "dispatch" or issue)):
        raise HTTPException(status_code=400, detail="Missing GH_* envs")

    if data.mode == "dispatch":
        code, text = await repo_dispatch(repo, token, data.event_type or "jinn_trigger",
                                         {"text": data.text, "meta": data.client_meta or {}})
    else:
        code, text = await post_issue_comment(repo, issue, token, data.text)

    ok = 200 <= code < 300 or code == 201
    return {"ok": ok, "status": code, "body": (text if not ok else None)}
