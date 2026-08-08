import requests
import json
import time

BASE_URL = "http://localhost:30021/api"
USERNAME = "verify_user"
PASSWORD = "Password123!"

def main():
    print("=== Trigger Reflexion in Docker ===")
    
    # 1. Register/Login
    print(f"1. Authenticating as {USERNAME}...")
    token = None
    
    # Try Login first
    try:
        resp = requests.post(f"{BASE_URL}/auth/token", data={
            "username": USERNAME,
            "password": PASSWORD
        })
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            print("   Logged in successfully.")
        else:
            print(f"   Login failed ({resp.status_code}), trying to register...")
            # Try Register
            resp = requests.post(f"{BASE_URL}/auth/register", json={
                "username": USERNAME,
                "password": PASSWORD
            })
            if resp.status_code == 200:
                token = resp.json()["access_token"]
                print("   Registered successfully.")
            else:
                print(f"   Register failed: {resp.text}")
                return
    except Exception as e:
        print(f"   Auth error: {e}")
        return

    if not token:
        print("   Failed to get token.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 2. Send Chat Message
    print("2. Sending Chat Message...")
    chat_payload = {
        "message": "我们见一面吧",
        "session_id": f"test_reflexion_{int(time.time())}"
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/chat", json=chat_payload, headers=headers)
        if resp.status_code == 200:
            print("   Chat response received.")
            print(f"   AI Response: {resp.json().get('response', 'No response field')}")
        else:
            print(f"   Chat failed: {resp.text}")
    except Exception as e:
        print(f"   Chat error: {e}")

    print("3. Done. Check docker logs now.")

if __name__ == "__main__":
    main()
