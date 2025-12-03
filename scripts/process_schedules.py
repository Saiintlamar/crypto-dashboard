#!/usr/bin/env python3
import os
import json
import glob
import time
import requests
from datetime import datetime
from dateutil import parser

# Configure where schedules live.
SCHEDULES_DIR = "schedules"
PROCESSED_DIR = "schedules/processed"

ACCOUNTS_CONFIG = {
    "tattoo1": {
        "ig_user_id": os.getenv("IG_TATTOO1_ID"),
        "access_token": os.getenv("IG_TATTOO1_TOKEN")
    },
    "tattoo2": {
        "ig_user_id": os.getenv("IG_TATTOO2_ID"),
        "access_token": os.getenv("IG_TATTOO2_TOKEN")
    },
    "spa": {
        "ig_user_id": os.getenv("IG_SPA_ID"),
        "access_token": os.getenv("IG_SPA_TOKEN")
    }
}

def ensure_dirs():
    os.makedirs(SCHEDULES_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

def get_pending_schedules():
    pattern = os.path.join(SCHEDULES_DIR, "*.json")
    files = glob.glob(pattern)
    pending = []

    for file_path in files:
        with open(file_path, "r") as f:
            data = json.load(f)
        
        if data.get("status") == "pending":
            pending.append((file_path, data))

    return pending

def generate_caption_if_needed(schedule):
    openai_key = os.getenv("OPENAI_API_KEY")

    if not schedule.get("caption") and schedule.get("brief") and openai_key:
        prompt = f"Create a short Instagram caption based on this brief: {schedule['brief']}"
        headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}

        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 60,
        }

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            schedule["caption"] = response.json()["choices"][0]["message"]["content"]
        else:
            print("Caption generation failed:", response.text)

    return schedule

def schedule_instagram_post(account_key, schedule):
    account = ACCOUNTS_CONFIG[account_key]
    ig_user_id = account["ig_user_id"]
    access_token = account["access_token"]

    media_url = schedule["media_url"]
    caption = schedule.get("caption", "")
    scheduled_time = parser.parse(schedule["scheduled_time"])
    unix_timestamp = int(scheduled_time.timestamp())

    endpoint = f"https://graph.facebook.com/v17.0/{ig_user_id}/media"

    payload = {
        "image_url": media_url,
        "caption": caption,
        "