from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({'ok': True})

# schedule post endpoint: call this with media_url, caption, ig_user_id, access_token, scheduled_time (ISO)
@app.route('/schedule', methods=['POST'])
def schedule_post():
    data = request.json
    ig_user_id = data['ig_user_id']
    access_token = data['access_token']
    media_url = data['media_url']
    caption = data.get('caption','')
    # scheduled_time ISO e.g. "2025-12-15T18:00:00"
    scheduled_time_iso = data['scheduled_time']
    ts = int(datetime.fromisoformat(scheduled_time_iso).timestamp())

    endpoint = f"https://graph.facebook.com/v17.0/{ig_user_id}/media"
    params = {
        "image_url": media_url,               # or "video_url" for videos
        "caption": caption,
        "published": "false",
        "scheduled_publish_time": ts,
        "access_token": access_token
    }
    r = requests.post(endpoint, data=params)
    return jsonify(r.json()), r.status_code

if __name__ == '__main__':
    app.run()