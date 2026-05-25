import requests
import json

url = "http://127.0.0.1:5612/business/invoke"

payload = json.dumps({
   "group": "qwenai",
   "action": "chatCompletions",
   "params": {
      "messages": "hello",
      "model": "qwen3.7-max",
      "chatId": "96fd5257-c5ff-487e-8aab-63bf892ee860"
   }
})
headers = {
   'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
   'Accept': '*/*',
   'Host': '127.0.0.1:5612',
   'Connection': 'keep-alive',
   'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
