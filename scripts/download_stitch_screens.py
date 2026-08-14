import json
import os
import re
import urllib.request

JSON_PATH = r"C:\Users\Admin\.gemini\antigravity-ide\brain\ed9b93f3-b625-46da-91e2-5b27050ae925\.system_generated\steps\37\output.txt"
OUTPUT_DIR = r"d:\code_ca_nhan\WindAgent\frontend\stitch_designs"

os.makedirs(os.path.join(OUTPUT_DIR, "html"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "screenshots"), exist_ok=True)

with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

screens = data.get("screens", [])
print(f"Found {len(screens)} screens to download...")

for idx, screen in enumerate(screens, start=1):
    title = screen.get("title", f"screen_{idx}")
    # sanitize filename
    safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)
    screen_id = screen.get("name", "").split("/")[-1]
    
    html_info = screen.get("htmlCode", {})
    html_url = html_info.get("downloadUrl")
    
    screenshot_info = screen.get("screenshot", {})
    screenshot_url = screenshot_info.get("downloadUrl")
    
    if html_url:
        html_file = os.path.join(OUTPUT_DIR, "html", f"{idx:02d}_{safe_title}_{screen_id[:8]}.html")
        print(f"[{idx}/{len(screens)}] Downloading HTML for '{title}' -> {html_file}")
        try:
            req = urllib.request.Request(html_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(html_file, "wb") as out:
                out.write(resp.read())
        except Exception as e:
            print(f"   Failed to download HTML: {e}")

    if screenshot_url:
        img_file = os.path.join(OUTPUT_DIR, "screenshots", f"{idx:02d}_{safe_title}_{screen_id[:8]}.png")
        print(f"[{idx}/{len(screens)}] Downloading Screenshot for '{title}' -> {img_file}")
        try:
            req = urllib.request.Request(screenshot_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(img_file, "wb") as out:
                out.write(resp.read())
        except Exception as e:
            print(f"   Failed to download Screenshot: {e}")

print("All Stitch design downloads completed!")
