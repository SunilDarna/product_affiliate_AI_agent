"""
uploader.py — YouTube Shorts & Instagram Publisher

Mirrors ShortsAutomatorAIAgent/youtube_uploader.py:
- Chunked resumable upload with progress
- #Shorts injected into title & description for algorithm recognition
- SRT caption upload for SEO indexing
- India geo-tagging on recordingDetails
- publishAt scheduling support
"""
import os
import re
from datetime import datetime, timedelta, timezone
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import (
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN,
    WORKSPACE_DIR,
)


URL_RE = re.compile(r"https?://[^\s]+")
SHORTS_SCHEDULE_GAP_HOURS = 4
IMMEDIATE_PUBLISH_GRACE_MINUTES = 10


def _get_authenticated_youtube():
    """Authenticate and return a YouTube API client — mirrors ShortsAutomatorAIAgent."""
    if not YOUTUBE_CLIENT_ID or not YOUTUBE_REFRESH_TOKEN:
        print("YouTube API credentials missing. Skipping upload.")
        return None

    creds = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token"
    )
    creds.refresh(google.auth.transport.requests.Request())
    return build("youtube", "v3", credentials=creds)


def _parse_youtube_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _parse_iso8601_duration_seconds(duration):
    if not duration:
        return 0
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    days, hours, minutes, seconds = [int(part or 0) for part in match.groups()]
    return (((days * 24) + hours) * 60 + minutes) * 60 + seconds


def _to_youtube_rfc3339(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _get_authenticated_channel_uploads_playlist(youtube):
    try:
        response = youtube.channels().list(
            part="contentDetails",
            mine=True,
            maxResults=1,
        ).execute()
        items = response.get("items", [])
        if not items:
            print("Could not find authenticated YouTube channel uploads playlist.")
            return None
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as exc:
        print(f"Could not fetch authenticated channel uploads playlist: {exc}")
        return None


def _list_recent_upload_video_ids(youtube, uploads_playlist_id, max_items=50):
    video_ids = []
    page_token = None
    while len(video_ids) < max_items:
        response = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=min(50, max_items - len(video_ids)),
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            video_id = item.get("contentDetails", {}).get("videoId")
            if video_id:
                video_ids.append(video_id)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def _fetch_videos(youtube, video_ids):
    videos = []
    for index in range(0, len(video_ids), 50):
        batch = video_ids[index:index + 50]
        if not batch:
            continue
        response = youtube.videos().list(
            part="snippet,status,contentDetails",
            id=",".join(batch),
            maxResults=50,
        ).execute()
        videos.extend(response.get("items", []))
    return videos


def _video_slot_time(video):
    status = video.get("status", {})
    snippet = video.get("snippet", {})
    scheduled = _parse_youtube_datetime(status.get("publishAt"))
    published = _parse_youtube_datetime(snippet.get("publishedAt"))
    return scheduled or published


def _compute_next_shorts_publish_at(youtube, gap_hours=SHORTS_SCHEDULE_GAP_HOURS):
    """
    Returns None when the next slot is immediate/public, otherwise an RFC3339 UTC
    timestamp for YouTube scheduled publishing.
    """
    uploads_playlist_id = _get_authenticated_channel_uploads_playlist(youtube)
    if not uploads_playlist_id:
        print("Scheduling fallback: could not inspect uploads playlist, publishing immediately.")
        return None

    video_ids = _list_recent_upload_video_ids(youtube, uploads_playlist_id, max_items=50)
    if not video_ids:
        print("No previous uploads found. Publishing immediately.")
        return None

    latest_shorts_slot = None
    for video in _fetch_videos(youtube, video_ids):
        duration_seconds = _parse_iso8601_duration_seconds(video.get("contentDetails", {}).get("duration"))
        if duration_seconds <= 0 or duration_seconds > 60:
            continue
        slot_time = _video_slot_time(video)
        if slot_time and (latest_shorts_slot is None or slot_time > latest_shorts_slot):
            latest_shorts_slot = slot_time

    if not latest_shorts_slot:
        print("No previous Shorts detected in recent uploads. Publishing immediately.")
        return None

    now = datetime.now(timezone.utc)
    next_slot = latest_shorts_slot + timedelta(hours=gap_hours)
    if next_slot <= now + timedelta(minutes=IMMEDIATE_PUBLISH_GRACE_MINUTES):
        print(
            "Latest Short slot is older than the 4-hour gap. "
            f"Last slot: {_to_youtube_rfc3339(latest_shorts_slot)}. Publishing immediately."
        )
        return None

    scheduled = _to_youtube_rfc3339(next_slot)
    print(
        "Next Shorts schedule slot selected: "
        f"{scheduled} UTC (4 hours after latest Short/scheduled slot)."
    )
    return scheduled


def upload_to_youtube(video_path, metadata, srt_path=None, publish_at="auto"):
    """
    Uploads a video to YouTube as a Short.

    Key Shorts requirements:
    - Video must be ≤60s and 9:16 vertical (handled by composer)
    - Title must contain #Shorts
    - Description must contain #Shorts
    - Uses chunked resumable upload (same as ShortsAutomatorAIAgent)
    - Uploads SRT captions for SEO auto-indexing
    - Tags India location on recordingDetails
    """
    print(f"Uploading to YouTube Shorts: {video_path}")

    youtube = _get_authenticated_youtube()
    if not youtube:
        return None

    if publish_at == "auto":
        publish_at = _compute_next_shorts_publish_at(youtube)

    # Inject #Shorts into title & description — required for Shorts algorithm
    title = metadata.get('title', 'Trending Product Alert!')
    if '#Shorts' not in title and '#shorts' not in title:
        # Keep title under 100 chars with #Shorts appended
        title = f"{title[:90]} #Shorts"

    description = metadata.get('description', '')
    affiliate_link = metadata.get('affiliate_link', '')
    if affiliate_link:
        # Keep the raw URL as its own first line. YouTube linkifies plain https URLs.
        description_without_duplicate = description.replace(affiliate_link, '').strip()
        description = f"{affiliate_link}\n\n{description_without_duplicate}".strip()
    elif description and not URL_RE.search(description):
        print("Warning: upload description does not contain a clickable URL.")

    hashtags = metadata.get('hashtags', '#shorts')
    # Ensure #Shorts is always in the description
    if '#Shorts' not in description and '#shorts' not in description:
        hashtags = f"#Shorts {hashtags}"

    full_description = f"{description}\n\n{hashtags}"

    tags = [tag.strip('#') for tag in hashtags.split() if tag.startswith('#')]
    # Ensure 'shorts' is always a tag
    if 'shorts' not in [t.lower() for t in tags]:
        tags.insert(0, 'Shorts')

    body = {
        "snippet": {
            "title": title,
            "description": full_description,
            "tags": tags,
            "categoryId": "28",   # Science & Technology
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private" if publish_at else "public",
            "selfDeclaredMadeForKids": False,
        },
        # India geo-tag — boosts discoverability for Indian audience
        "recordingDetails": {
            "location": {"latitude": 20.5937, "longitude": 78.9629},
            "locationDescription": "India",
        }
    }

    # Schedule publishing if requested
    if publish_at:
        body["status"]["publishAt"] = publish_at
        print(f"Scheduled publish at: {publish_at} (UTC)")
    else:
        print("Publishing immediately as public: no later 4-hour Shorts slot is needed.")

    try:
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

        request = youtube.videos().insert(
            part="snippet,status,recordingDetails",
            body=body,
            media_body=media
        )

        # Chunked resumable upload with progress — mirrors ShortsAutomatorAIAgent
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Upload progress: {int(status.progress() * 100)}%")

        video_id = response['id']
        print(f"YouTube Shorts Upload Complete! Video ID: {video_id}")

        # Upload SRT captions for SEO auto-indexing — mirrors ShortsAutomatorAIAgent
        if srt_path and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
            print("Uploading SRT captions for SEO indexing...")
            try:
                caption_body = {
                    'snippet': {
                        'videoId': video_id,
                        'language': 'en',
                        'name': 'English',
                        'isDefault': True,
                    }
                }
                media_srt = MediaFileUpload(srt_path, mimetype='text/plain')
                youtube.captions().insert(
                    part='snippet',
                    body=caption_body,
                    media_body=media_srt
                ).execute()
                print("SRT captions uploaded successfully.")
            except Exception as e:
                print(f"SRT upload warning (video is still live): {e}")
        elif srt_path:
            print("SRT captions skipped: subtitle file is missing or empty.")

        return f"https://youtube.com/shorts/{video_id}"

    except Exception as e:
        print(f"YouTube upload error: {e}")
        return None


def upload_to_instagram(video_path, metadata):
    """
    Stub for Instagram Reels upload.
    Will use Instagram Graph API or Playwright automation in a future enhancement.
    The same 9:16 vertical video from the Shorts pipeline is directly compatible.
    """
    print(f"[Instagram STUB] Ready for Reels upload: {metadata.get('title')}")
    print(f"  Video: {video_path}")
    return None
