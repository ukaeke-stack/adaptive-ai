"""OAuth2 social connections with one-time state, PKCE and encrypted token storage."""
from __future__ import annotations
import base64, hashlib, json, os, secrets, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from app.memory.store import _ready_engine
from app.security.sessions import require_user

router = APIRouter(prefix="/v1/social", tags=["social"])
PROVIDERS = {
 "instagram": {"id":"INSTAGRAM_CLIENT_ID","secret":"INSTAGRAM_CLIENT_SECRET","redirect":"INSTAGRAM_REDIRECT_URI","authorize":"https://www.instagram.com/oauth/authorize","token":"https://api.instagram.com/oauth/access_token","scope":"instagram_business_basic","pkce":False},
 "facebook": {"id":"FACEBOOK_CLIENT_ID","secret":"FACEBOOK_CLIENT_SECRET","redirect":"FACEBOOK_REDIRECT_URI","authorize":"https://www.facebook.com/v22.0/dialog/oauth","token":"https://graph.facebook.com/v22.0/oauth/access_token","scope":"public_profile,email","pkce":False},
 "x": {"id":"X_CLIENT_ID","secret":"X_CLIENT_SECRET","redirect":"X_REDIRECT_URI","authorize":"https://twitter.com/i/oauth2/authorize","token":"https://api.twitter.com/2/oauth2/token","scope":"users.read tweet.read offline.access","pkce":True},
 "youtube": {"id":"GOOGLE_CLIENT_ID","secret":"GOOGLE_CLIENT_SECRET","redirect":"YOUTUBE_REDIRECT_URI","authorize":"https://accounts.google.com/o/oauth2/v2/auth","token":"https://oauth2.googleapis.com/token","scope":"openid email profile https://www.googleapis.com/auth/youtube.readonly","pkce":True},
 "tiktok": {"id":"TIKTOK_CLIENT_KEY","secret":"TIKTOK_CLIENT_SECRET","redirect":"TIKTOK_REDIRECT_URI","authorize":"https://www.tiktok.com/v2/auth/authorize/","token":"https://open.tiktokapis.com/v2/oauth/token/","scope":"user.info.basic,video.list","pkce":False},
}

def _ensure_tables():
 with _ready_engine().begin() as conn:
  conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_oauth_states (
   state_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, provider TEXT NOT NULL,
   verifier TEXT NOT NULL, created_at BIGINT NOT NULL)"""))
  conn.execute(text("""CREATE TABLE IF NOT EXISTS adaptive_social_tokens (
   user_id TEXT NOT NULL, provider TEXT NOT NULL, token_ciphertext TEXT NOT NULL,
   scopes TEXT NOT NULL DEFAULT '', connected_at TEXT NOT NULL,
   PRIMARY KEY(user_id,provider))"""))

def _fernet():
 key=os.getenv("SOCIAL_TOKEN_ENCRYPTION_KEY","").strip()
 if not key: raise HTTPException(status_code=503, detail="Social connections require SOCIAL_TOKEN_ENCRYPTION_KEY configured by the service administrator.")
 try: return Fernet(key.encode())
 except Exception as exc: raise HTTPException(status_code=503, detail="SOCIAL_TOKEN_ENCRYPTION_KEY must be a valid Fernet key.") from exc

def _settings(provider):
 cfg=PROVIDERS[provider]
 values={k:os.getenv(cfg[k],"").strip() for k in ("id","secret","redirect")}
 if not values["id"] or not values["redirect"] or (provider not in {"youtube","x"} and not values["secret"]):
  raise HTTPException(status_code=503, detail=f"{provider} OAuth credentials and redirect URI are not fully configured.")
 return cfg,values

def _get_form(url, fields):
 req=urllib.request.Request(url+"?"+urllib.parse.urlencode(fields),headers={"Accept":"application/json"})
 try:
  with urllib.request.urlopen(req,timeout=12) as response: return json.loads(response.read(1_000_000))
 except Exception as exc:
  raise HTTPException(status_code=502,detail="The social provider token exchange failed. No connection was saved.") from exc

def _post_form(url, fields, basic_auth=None):
 data=urllib.parse.urlencode(fields).encode()
 req=urllib.request.Request(url,data=data,headers={"Accept":"application/json","Content-Type":"application/x-www-form-urlencoded"})
 if basic_auth:
  req.add_header("Authorization","Basic "+base64.b64encode(basic_auth.encode()).decode())
 try:
  with urllib.request.urlopen(req,timeout=12) as response: return json.loads(response.read(1_000_000))
 except Exception as exc:
  raise HTTPException(status_code=502,detail="The social provider token exchange failed. No connection was saved.") from exc

@router.get("/providers")
def providers(request: Request):
 user=require_user(request); _ensure_tables()
 with _ready_engine().connect() as conn:
  connected={r["provider"] for r in conn.execute(text("SELECT provider FROM adaptive_social_tokens WHERE user_id=:uid"),{"uid":user["id"]}).mappings()}
 result=[]
 for name,cfg in PROVIDERS.items():
  has_id=bool(os.getenv(cfg["id"],"").strip())
  has_secret=bool(os.getenv(cfg["secret"],"").strip())
  has_redirect=bool(os.getenv(cfg["redirect"],"").strip())
  result.append({"provider":name,"configured":has_id and has_redirect and (has_secret or name in {"x","youtube"}),
   "connected":name in connected,"status":"connected" if name in connected else "ready" if has_id and has_redirect else "needs_provider_credentials"})
 return {"providers":result,"token_storage":"encrypted-at-rest","oauth_state":"one-time-and-expiring"}

@router.get("/{provider}/connect")
def connect(provider: str, request: Request):
 user=require_user(request)
 if provider not in PROVIDERS: raise HTTPException(status_code=404,detail="Unsupported social provider")
 cfg,values=_settings(provider); _fernet(); _ensure_tables()
 state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(64)
 challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
 now=int(time.time())
 with _ready_engine().begin() as conn:
  conn.execute(text("DELETE FROM adaptive_oauth_states WHERE created_at < :cutoff"),{"cutoff":now-600})
  conn.execute(text("INSERT INTO adaptive_oauth_states(state_hash,user_id,provider,verifier,created_at) VALUES (:state,:uid,:provider,:verifier,:created)"),
   {"state":hashlib.sha256(state.encode()).hexdigest(),"uid":user["id"],"provider":provider,"verifier":verifier,"created":now})
 params={"client_id":values["id"],"redirect_uri":values["redirect"],"response_type":"code","scope":cfg["scope"],"state":state}
 if provider in {"youtube","facebook"}: params["access_type"]="offline" if provider=="youtube" else ""
 if cfg["pkce"]:
  params.update({"code_challenge":challenge,"code_challenge_method":"S256"})
 if provider=="youtube": params["prompt"]="consent"
 if provider=="tiktok": params["client_key"]=values["id"]
 url=cfg["authorize"]+"?"+urllib.parse.urlencode({k:v for k,v in params.items() if v})
 return RedirectResponse(url,status_code=302)

@router.get("/{provider}/callback")
def callback(provider: str, request: Request, code: str|None=None, state: str|None=None, error: str|None=None):
 user=require_user(request)
 if provider not in PROVIDERS: raise HTTPException(status_code=404,detail="Unsupported social provider")
 if error: raise HTTPException(status_code=400,detail="The social provider declined authorization.")
 if not code or not state: raise HTTPException(status_code=400,detail="OAuth callback is missing code or state.")
 cfg,values=_settings(provider); cipher=_fernet(); _ensure_tables()
 state_hash=hashlib.sha256(state.encode()).hexdigest(); now=int(time.time())
 with _ready_engine().begin() as conn:
  row=conn.execute(text("SELECT user_id,provider,verifier,created_at FROM adaptive_oauth_states WHERE state_hash=:state"),{"state":state_hash}).mappings().first()
  if row: conn.execute(text("DELETE FROM adaptive_oauth_states WHERE state_hash=:state"),{"state":state_hash})
 if not row or row["provider"]!=provider or row["user_id"]!=user["id"] or now-int(row["created_at"])>600:
  raise HTTPException(status_code=400,detail="OAuth state is invalid, expired, or does not match this account. Restart connection.")
 form={"grant_type":"authorization_code","code":code,"redirect_uri":values["redirect"]}
 if provider=="tiktok": form["client_key"]=values["id"]
 else: form["client_id"]=values["id"]
 if values["secret"]: form["client_secret"]=values["secret"]
 if cfg["pkce"]: form["code_verifier"]=row["verifier"]
 token=_get_form(cfg["token"],form) if provider=="facebook" else _post_form(cfg["token"],form, f'{values["id"]}:{values["secret"]}' if provider=="x" and values["secret"] else None)
 if not isinstance(token,dict) or not token.get("access_token"):
  raise HTTPException(status_code=502,detail="Provider did not return an access token. No connection was saved.")
 payload=json.dumps({"access_token":token["access_token"],"refresh_token":token.get("refresh_token"),"expires_in":token.get("expires_in"),"token_type":token.get("token_type","Bearer")},separators=(",",":")).encode()
 encrypted=cipher.encrypt(payload).decode()
 scopes=token.get("scope",cfg["scope"]); scopes=" ".join(scopes) if isinstance(scopes,list) else str(scopes)
 with _ready_engine().begin() as conn:
  conn.execute(text("""INSERT INTO adaptive_social_tokens(user_id,provider,token_ciphertext,scopes,connected_at)
   VALUES (:uid,:provider,:token,:scopes,:at) ON CONFLICT(user_id,provider) DO UPDATE SET
   token_ciphertext=excluded.token_ciphertext,scopes=excluded.scopes,connected_at=excluded.connected_at"""),
   {"uid":user["id"],"provider":provider,"token":encrypted,"scopes":scopes,"at":datetime.now(timezone.utc).isoformat()})
 return {"connected":True,"provider":provider,"scopes":scopes,"message":"Account connected. Tokens are encrypted at rest and are never returned by this API."}

@router.delete("/{provider}/disconnect")
def disconnect(provider: str, request: Request):
 user=require_user(request)
 if provider not in PROVIDERS: raise HTTPException(status_code=404,detail="Unsupported social provider")
 _ensure_tables()
 with _ready_engine().begin() as conn:
  result=conn.execute(text("DELETE FROM adaptive_social_tokens WHERE user_id=:uid AND provider=:provider"),{"uid":user["id"],"provider":provider})
 return {"disconnected":bool(result.rowcount),"provider":provider,"message":"Local tokens deleted. Revoke provider-side access in the provider's security settings if needed."}

def _get_json(url, access_token):
 req=urllib.request.Request(url,headers={"Accept":"application/json","Authorization":"Bearer "+access_token})
 try:
  with urllib.request.urlopen(req,timeout=12) as response: return json.loads(response.read(1_000_000))
 except Exception as exc:
  raise HTTPException(status_code=502,detail="The provider profile request failed. Reconnect the account if its token expired.") from exc

@router.get("/{provider}/profile")
def connected_profile(provider: str, request: Request):
 user=require_user(request)
 if provider not in PROVIDERS: raise HTTPException(status_code=404,detail="Unsupported social provider")
 cipher=_fernet(); _ensure_tables()
 with _ready_engine().connect() as conn:
  row=conn.execute(text("SELECT token_ciphertext FROM adaptive_social_tokens WHERE user_id=:uid AND provider=:provider"),
   {"uid":user["id"],"provider":provider}).mappings().first()
 if not row: raise HTTPException(status_code=404,detail="This social account is not connected.")
 try: token=json.loads(cipher.decrypt(row["token_ciphertext"].encode()).decode())
 except Exception as exc: raise HTTPException(status_code=500,detail="Stored social token could not be decrypted. Contact the service administrator.") from exc
 access=token.get("access_token","")
 if provider=="instagram": data=_get_json("https://graph.instagram.com/me?fields=user_id,username",access)
 elif provider=="facebook": data=_get_json("https://graph.facebook.com/me?fields=id,name",access)
 elif provider=="x": data=_get_json("https://api.twitter.com/2/users/me?user.fields=name,username",access).get("data",{})
 elif provider=="youtube":
  data=_get_json("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",access)
  items=data.get("items",[])
  data={"channel_id":items[0].get("id"),"title":items[0].get("snippet",{}).get("title")} if items else {}
 elif provider=="tiktok": data=_get_json("https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name,username",access).get("data",{}).get("user",{})
 else: raise HTTPException(status_code=404,detail="Unsupported social provider")
 safe={k:data[k] for k in ("id","user_id","username","name","display_name","open_id","channel_id","title") if isinstance(data,dict) and k in data}
 return {"provider":provider,"connected":True,"profile":safe}
