import os
import socket
import subprocess
import time

def is_port_open(host='127.0.0.1', port=9222):
    """Checks if the local remote debugging port is active."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.5)
            return s.connect_ex((host, port)) == 0
    except:
        return False

def is_chrome_running_macos():
    """Checks if the Google Chrome process is currently running under the current user on macOS."""
    try:
        uid = os.getuid()
        output = subprocess.check_output(["pgrep", "-u", str(uid), "-f", "Google Chrome"])
        return len(output) > 0
    except Exception as e:
        print(f"Could not inspect Chrome process state: {e}")
        return None

def ensure_chrome_debugging_active():
    """
    Ensures that Google Chrome is running with remote debugging enabled on port 9222.
    - If port 9222 is already open, returns True.
    - If Chrome is completely closed, automatically launches it in remote debugging mode.
    - If Chrome is open but port 9222 is closed, notifies the user to quit Chrome.
    """
    if is_port_open():
        print("✅ Chrome remote debugging port 9222 is active.")
        return True

    print("🔍 Remote debugging port 9222 is closed. Checking Chrome status...")

    chrome_running = is_chrome_running_macos()
    if chrome_running is None:
        print("⚠️  Could not determine whether Chrome is already running. Skipping auto-launch to avoid opening the wrong profile.")
        return False

    if chrome_running:
        print("\n" + "="*80)
        print("⚠️  WARNING: Google Chrome is currently open, but remote debugging is DISABLED.")
        print("   To enable automation:")
        print("   1. Please fully quit Google Chrome (Cmd + Q or right-click dock icon -> Quit).")
        print("   2. Run this script again. It will automatically launch Chrome in debugging mode.")
        print("="*80 + "\n")
        return False

    # Chrome is not running, let's automatically launch it
    print("🚀 Google Chrome is closed. Automatically launching Chrome with remote debugging on port 9222...")
    try:
        user_data_dir = os.path.expanduser("~/Library/Application Support/Google/ChromeDebug")
        default_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome")
        
        # If the debug directory doesn't exist, clone the default profile
        if not os.path.exists(user_data_dir):
            print(f"📁 Cloning default Chrome profile to non-default debugging directory: {user_data_dir}...")
            subprocess.run(["cp", "-R", default_dir, user_data_dir])
            
        cmd = f'"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="{user_data_dir}"'
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Wait for the browser process to initialize and open the socket
        for attempt in range(8):
            print(f"  Waiting for Chrome to initialize (attempt {attempt + 1}/8)...")
            time.sleep(1.5)
            if is_port_open():
                print("✅ Chrome initialized and remote debugging is active.")
                return True
                
        print("❌ Timeout: Chrome launched, but port 9222 is not responding. Please launch Chrome manually.")
        return False
    except Exception as e:
        print(f"❌ Failed to automatically launch Google Chrome: {e}")
        return False

if __name__ == "__main__":
    # Test helper
    ensure_chrome_debugging_active()
