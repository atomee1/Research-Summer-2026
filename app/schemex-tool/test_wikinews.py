import requests

url = "https://en.wikinews.org/w/api.php"
params = {
    "action": "query",
    "list": "categorymembers",
    "cmtitle": "Category:Politics_and_conflicts",
    "format": "json"
}

response = requests.get(url, params=params, headers={"User-Agent": "SchemexTool/0.1"})
print("STATUS:", response.status_code)
print("RAW TEXT (first 500 chars):")
print(response.text[:500])