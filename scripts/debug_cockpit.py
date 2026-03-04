"""Debug cockpit rendering — capture console errors."""
from playwright.sync_api import sync_playwright
import time

def debug():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()

        errors = []
        logs = []

        page.on("console", lambda msg: (
            errors.append(msg.text) if msg.type == "error" else
            logs.append(msg.text)
        ))
        page.on("pageerror", lambda err: errors.append(f"PAGE_ERROR: {err}"))

        page.goto("http://localhost:8420", wait_until="networkidle")
        time.sleep(5)

        print("=== ERRORS ===")
        for e in errors:
            print(f"  {e}")

        print(f"\n=== LOGS ({len(logs)} total, first 20) ===")
        for l in logs[:20]:
            print(f"  {l}")

        if not errors:
            print("\nNo errors! Taking screenshot...")
            page.screenshot(path="/Users/gustavoschneiter/Documents/engineering-brain/docs/assets/hero-dark.png")
            print("Saved hero-dark.png")

        browser.close()

if __name__ == "__main__":
    debug()
