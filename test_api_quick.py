"""
Quick API endpoint test for accuracy update
"""
import requests
import time
import json

# Wait for server to be ready
print("Waiting for server to start...")
time.sleep(5)

# Test the API endpoint
url = "http://localhost:8000/api/forecasts/accuracy/update"

print("\n" + "="*60)
print("Testing POST /api/forecasts/accuracy/update")
print("="*60)

# Test 1: Default (last month)
print("\n[Test 1] Calling API without target_month parameter...")
try:
    response = requests.post(url, timeout=30)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print("Response:")
        print(json.dumps(data, indent=2))
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Request failed: {e}")

# Test 2: Specific month (September 2025)
print("\n[Test 2] Calling API with target_month=2025-09...")
try:
    response = requests.post(f"{url}?target_month=2025-09", timeout=30)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print("Response:")
        print(json.dumps(data, indent=2))
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Request failed: {e}")

print("\n" + "="*60)
print("API Testing Complete")
print("="*60)
