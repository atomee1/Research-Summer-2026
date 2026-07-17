import requests

url = "https://en.wikinews.org/w/api.php"
params = {
    "action": "query",
    "list": "categorymembers",
    "cmtitle": "Category:Politics_and_conflicts",
    "format": "json"
}

response = requests.get(url, params=params)
print("STATUS:", response.status_code)
print(response.json())