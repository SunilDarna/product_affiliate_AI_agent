import os
import json
from dotenv import load_dotenv

load_dotenv()

# We look for a central secrets file, falling back to environment variables
SECRETS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "secrets.json")

def load_secrets():
    if os.path.exists(SECRETS_PATH):
        with open(SECRETS_PATH, 'r') as f:
            return json.load(f)
    return {}

SECRETS = load_secrets()

# LLM Configuration (Online Endpoint via Gemini)
GEMINI_API_KEY = SECRETS.get("llm_api_key", os.getenv("GEMINI_API_KEY", ""))

# Other APIs
YOUTUBE_API_KEY = SECRETS.get("youtube_api_key", "")
YOUTUBE_CLIENT_ID = SECRETS.get("youtube_client_id", "")
YOUTUBE_CLIENT_SECRET = SECRETS.get("youtube_client_secret", "")
YOUTUBE_REFRESH_TOKEN = SECRETS.get("youtube_refresh_token", "")
YOUTUBE_CHANNEL_HANDLE = SECRETS.get("youtube_channel_handle", "@BestGenZDeals")

# Future Enhancements
SARVAM_API_KEY = SECRETS.get("sarvam_api_key", "")
ELEVENLABS_API_KEY = SECRETS.get("elevenlabs_api_key", "")

# Directory configurations
WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)
