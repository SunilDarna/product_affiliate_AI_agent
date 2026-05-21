import os
import json
import shutil
from google_auth_oauthlib.flow import InstalledAppFlow

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRETS_PATH = os.path.join(BASE_DIR, "secrets.json")
BACKUP_PATH = os.path.join(BASE_DIR, "secrets.json.bak")

# Scopes needed for uploading video and setting captions
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

def load_secrets():
    if os.path.exists(SECRETS_PATH):
        with open(SECRETS_PATH, 'r') as f:
            return json.load(f)
    return {}

def save_secrets(secrets):
    with open(SECRETS_PATH, 'w') as f:
        json.dump(secrets, f, indent=4)

def main():
    print("=" * 65)
    print("       YOUTUBE CHANNEL TOKEN GENERATOR FOR @BestGenZDeals      ")
    print("=" * 65)
    print("This script will guide you through authenticating your new")
    print("YouTube channel and generating a refresh token.\n")

    secrets = load_secrets()
    client_id = secrets.get("youtube_client_id")
    client_secret = secrets.get("youtube_client_secret")

    if not client_id or not client_secret:
        print("[-] Error: 'youtube_client_id' or 'youtube_client_secret' not found in secrets.json.")
        print("    Please ensure your secrets.json contains these values before running.")
        return

    print("[+] Found YouTube Client ID and Client Secret in secrets.json.")
    print("[*] Preparing OAuth 2.0 flow...")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    try:
        # Run local server
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        print("\n[!] A browser window will now open to complete the authentication.")
        print("[!] IMPORTANT: Make sure to select the Google Account and specifically")
        print("[!] the YouTube Channel/Brand Account: @BestGenZDeals")
        print("[!] during the login process.\n")
        
        credentials = flow.run_local_server(port=0)
        refresh_token = credentials.refresh_token

        if not refresh_token:
            print("[-] Warning: No refresh token returned. This usually happens if you've already")
            print("    authorized this app. Go to your Google Account permissions, remove access")
            print("    for this app, and try again.")
            return

        print("\n" + "=" * 50)
        print("                   SUCCESS!                   ")
        print("=" * 50)
        print(f"Generated Refresh Token:\n{refresh_token}")
        print("=" * 50)

        confirm = input("\nWould you like to automatically update secrets.json with this new token? (y/N): ").strip().lower()
        if confirm == 'y':
            # Create a backup of secrets.json first
            if os.path.exists(SECRETS_PATH):
                shutil.copy2(SECRETS_PATH, BACKUP_PATH)
                print(f"[+] Created backup of secrets.json at secrets.json.bak")
            
            secrets["youtube_refresh_token"] = refresh_token
            # Also update target handle to @BestGenZDeals just in case
            secrets["youtube_channel_handle"] = "@BestGenZDeals"
            save_secrets(secrets)
            print("[+] Successfully updated secrets.json with the new refresh token!")
            print("[+] You are now ready to run the automated pipeline with your new channel!")
        else:
            print("\n[-] secrets.json was not updated. You can manually copy the token above and")
            print("    paste it in the 'youtube_refresh_token' field of your secrets.json file.")

    except Exception as e:
        print(f"\n[-] An error occurred during the OAuth flow: {e}")
        print("    Please check your internet connection and ensure your OAuth app in Google Cloud")
        print("    Console is set to 'Testing' or 'In Production' and has your email added as a test user.")

if __name__ == "__main__":
    main()
