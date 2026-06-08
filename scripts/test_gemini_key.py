import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
for line in open(os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml"), encoding="utf-8"):
    line = line.strip()
    if line.startswith("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"')

from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
try:
    resp = client.models.generate_content(model="gemini-2.5-flash", contents="Reply with exactly: OK")
    print("SUCCESS:", (resp.text or "").strip()[:80])
except Exception as exc:
    print("FAILED:", type(exc).__name__)
    print(str(exc)[:400])
