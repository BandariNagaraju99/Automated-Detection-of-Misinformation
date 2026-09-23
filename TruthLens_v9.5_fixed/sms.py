import requests
import re
import time

API_URL = "https://api.vsimpro.com/stubs/handler_api.php"
API_KEY = "18d3346b3c5621727b989f103ad9a67d3f43"
PHONE_NUMBER = "YOUR_PHONE_NUMBER"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

seen = set()

print("Waiting for OTP...")

while True:
    try:
        response = requests.get(
            API_URL,
            headers=headers,
            params={"number": PHONE_NUMBER},
            timeout=10,
        )

        response.raise_for_status()
        data = response.json()

        for message in data.get("messages", []):
            msg_id = message.get("id")
            text = message.get("text", "")

            if msg_id in seen:
                continue

            seen.add(msg_id)

            match = re.search(r"\b\d{4,8}\b", text)
            if match:
                print("OTP:", match.group())
                exit()

    except Exception as e:
        print("Error:", e)

    time.sleep(5)