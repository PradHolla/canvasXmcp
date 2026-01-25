import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()
# --- CONFIGURATION ---
# Use ONLY the root domain (e.g., https://canvas.instructure.com)
CANVAS_DOMAIN = os.getenv("CANVAS_URL")
ACCESS_TOKEN = os.getenv("CANVAS_TOKEN")
# ---------------------

def run_hardened_audit():
    # 1. URL Cleanup: Remove trailing slashes and common path errors
    base_domain = CANVAS_DOMAIN.rstrip('/').replace('/api/v1', '')
    api_root = f"{base_domain}/api/v1"
    
    # 2. Token Validation: Check for spaces or common copy-paste issues
    token = ACCESS_TOKEN.strip()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    print(f"--- Canvas API Audit ---")
    print(f"Targeting: {api_root}")
    
    endpoints = {
        "User Profile": "users/self",
        "Active Courses": "courses?enrollment_state=active",
        "Todo Items": "users/self/todo",
        "Activity Stream": "users/self/activity_stream"
    }

    for name, path in endpoints.items():
        url = f"{api_root}/{path}"
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                count = len(data) if isinstance(data, list) else 1
                print(f"✅ {name:.<20} [200 OK] (Items: {count})")
            elif response.status_code == 404:
                print(f"❌ {name:.<20} [404 Not Found] <- Check your URL structure!")
            elif response.status_code == 401:
                print(f"❌ {name:.<20} [401 Unauthorized] <- Token is invalid or expired.")
            else:
                print(f"❓ {name:.<20} [{response.status_code}] {response.text[:50]}")
        
        except Exception as e:
            print(f"⚠️ {name:.<20} Connection Error: {e}")

if __name__ == "__main__":
    run_hardened_audit()