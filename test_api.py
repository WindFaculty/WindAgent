import requests

invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
stream = False

headers = {
  "Authorization": "Bearer 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",
  "Accept": "text/event-stream" if stream else "application/json"
}

payload = {
  "model": "z-ai/glm-5.2",
  "messages": [{"role":"user","content":""}],
  "max_tokens": 8192,
  "temperature": 1.00,
  "top_p": 0.95,
  "stream": stream,
  
}

# MiniMax-M3 is multimodal. To send images or video, set a message's
# "content" to a list of parts (a public URL or a base64 data URI):
#   payload["messages"] = [{"role": "user", "content": [
#       {"type": "text", "text": "Describe this."},
#       {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}},
#       {"type": "video_url", "video_url": {"url": "https://example.com/video.mp4"}},
#   ]}]
# To use base64 instead of a URL:
#   import base64
#   b64 = base64.b64encode(open("image.png", "rb").read()).decode()
#   {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}

response = requests.post(invoke_url, headers=headers, json=payload, stream=stream)
if stream:
    for line in response.iter_lines():
        if line:
            print(line.decode("utf-8"))
else:
    print(response.json())