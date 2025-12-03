#!/usr/bin/env python3
import os, sys, json, glob, time, subprocess
from datetime import datetime, timezone
import requests
from dateutil import parser
from pathlib import Path

# Config via ENV (set these in GitHub repo Settings -> Secrets)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # optional
# IG accounts: set env names IG_TATTOO1_ID, IG_TATTOO1_TOKEN, IG_TATTOO2_ID, etc.
# Map account slugs to env var names here:
ACCOUNT_ENV = {
    "tattoo1": ("IG_TATTOO1_ID", "IG_TATTOO1_TOKEN"),
    "tattoo2": ("IG_TATTOO2_ID", "IG_TATTOO2_TOKEN"),
    "spa":     ("IG_SPA_ID",     "IG_SPA_TOKEN"),
}

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_DIR = REPO_ROOT / "schedules"
PROCESSED_DIR = SCHEDULE_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

def get_env_account(account_slug):
    if account_slug not in ACCOUNT_ENV:
        raise Exception(f"Unknown account slug: {account_slug}")
    id_var, token_var = ACCOUNT_ENV[account_slug]
    ig_id = os.getenv(id_var)
    token = os.getenv(token_var)
    if not ig_id or not token:
        raise Exception(f"Missing env for {account_slug} ({id_var}/{token_var})")
    return ig_id, token

def openai_generate_caption(brief, tone="professional"):
    if not OPENAI_API_KEY:
        return ""
    prompt = f"Write 2 short Instagram caption options (<140 chars each) for: {brief}. Tone: {tone}."
    url = "https://api.openai.com/v1/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    data = {
        "model": "text-davinci-003",
        "prompt": prompt,
        "max_tokens": 120,
        "temperature": 0.8,
        "n": 1
    }
    r = requests.post(url, headers=headers, json=data, timeout=30)
    r.raise_for_status()
    txt = r.json()["choices"][0]["text"].strip()
    # Return first line as a simple caption
    return txt.splitlines()[0] if txt else ""

def create_ig_media(ig_user_id, token, media_url, caption, scheduled_ts, media_type="image"):
    endpoint = f"https://graph.facebook.com/v17.0/{ig_user_id}/media"
    params = {
        "access_token": token,
        "caption": caption,
        "published": "false",
        "scheduled_publish_time": str(int(scheduled_ts))
    }
    if media_type.startswith("video"):
        params["video_url"] = media_url
    else:
        params["image_url"] = media_url

    r = requests.post(endpoint, data=params, timeout=30)
    try:
        jr = r.json()
    except Exception:
        jr = {"error": f"non-json response: {r.text}"}
    return jr

def git_move_to_processed(src_path):
    # use git to move (rename) and push changes using GITHUB_TOKEN credential already available in Actions
    dest = PROCESSED_DIR / src_path.name
    src_rel = src_path.relative_to(REPO_ROOT)
    dest_rel = dest.relative_to(REPO_ROOT)
    try:
        # make folders if needed
        dest.parent.mkdir(parents=True, exist_ok=True)
        src_path.rename(dest)
        subprocess.run(["git", "add", str(src_rel), str(dest_rel)], check=True)
        subprocess.run(["git", "commit", "-m", f"mark processed: {dest_rel}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print(f"Moved & committed {src_rel} -> {dest_rel}")
    except subprocess.CalledProcessError as e:
        print("Git push failed:", e)
        raise

def process_file(path: Path):
    print("Processing", path)
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        print("Invalid JSON:", e)
        return

    status = data.get("status", "pending")
    if status != "pending":
        print("Skipping, status =", status)
        return

    account = data.get("account")  # expected 'tattoo1' or 'tattoo2' or 'spa'
    if not account:
        print("Missing account in schedule, skipping")
        return

    media_url = data.get("media_url")
    media_type = data.get("media_type", "image/jpeg")
    scheduled_iso = data.get("scheduled_time")
    caption = data.get("caption", "")
    brief = data.get("brief", "")

    if not media_url or not scheduled_iso:
        print("Missing media_url or scheduled_time")
        return

    # parse ISO time -> timestamp (assume ISO contains timezone or is local)
    try:
        dt = parser.isoparse(scheduled_iso)
        # ensure timezone aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ts = int(dt.timestamp())
    except Exception as e:
        print("Bad date:", e)
        return

    if not caption and brief:
        try:
            caption = openai_generate_caption(brief)
            print("Generated caption:", caption)
        except Exception as e:
            print("OpenAI error:", e)
            caption = ""

    try:
        ig_user_id, token = get_env_account(account)
    except Exception as e:
        print("Account env missing:", e)
        return

    print("Calling IG API for", account)
    resp = create_ig_media(ig_user_id, token, media_url, caption, ts, media_type)
    print("IG response:", resp)

    if "id" in resp:
        # success: mark processed by moving file
        # update local JSON to include creation id and status
        data["status"] = "processed"
        data["creation_id"] = resp["id"]
        data["processed_at"] = datetime.now(timezone.utc).isoformat()
        (PROCESSED_DIR / path.name).write_text(json.dumps(data, indent=2))
        # remove original and commit move
        try:
            path.unlink()
        except Exception:
            pass
        git_move_to_processed(PROCESSED_DIR / path.name)
    else:
        print("Failed to schedule:", resp)
        # write error back to file for debugging
        data["last_error"] = resp
        path.write_text(json.dumps(data, indent=2))

def main():
    files = sorted(glob.glob(str(SCHEDULE_DIR / "*.json")))
    if not files:
        print("No schedule files found.")
        return
    for f in files:
        process_file(Path(f))

if __name__ == "__main__":
    main()