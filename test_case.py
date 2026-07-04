import requests

TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyNWE0NmFlMWE4ODg0ZDE0OWQ2OGU4ZDVkYzc2ZWI1OCIsImV4cCI6MTc4MjY3OTE5MH0.eUbOKf1ULPyt_5eQgmakSDyWYfbrtE3pmKUd79rdT7M"
headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
payload = {
    "title": "Investigation - ashwin c h (Parallel2)",
    "seeds": [
        {"type": "name", "value": "ashwin c h"},
        {"type": "phone", "value": "8317464735"},
        {"type": "username", "value": "ash29_03"}
    ]
}

res = requests.post("http://localhost:8005/cases", json=payload, headers=headers)
print("Result:", res.json())
