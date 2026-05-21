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


def upload_to_youtube(video_path, metadata, srt_path=None, publish_at=None):
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
            "privacyStatus": "private",   # Safe default — review before making public
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
        if srt_path and os.path.exists(srt_path):
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
