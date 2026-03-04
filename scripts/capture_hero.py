"""Capture hero screenshots and GIF frames from the 3D Cockpit."""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ASSETS = Path("/Users/gustavoschneiter/Documents/engineering-brain/docs/assets")
ASSETS.mkdir(parents=True, exist_ok=True)
URL = "http://localhost:8420"


def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # === DARK MODE HERO ===
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            color_scheme="dark",
        )
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle")
        time.sleep(6)  # Let Three.js fully render + animations settle

        page.screenshot(path=str(ASSETS / "hero-dark.png"))
        print(f"Saved: hero-dark.png")

        # === GIF FRAMES (orbital rotation) ===
        gif_dir = ASSETS / "gif_frames"
        gif_dir.mkdir(exist_ok=True)

        # Inject rotation script
        for i in range(40):
            page.evaluate(f"""(() => {{
                const canvas = document.querySelector('canvas');
                if (canvas) {{
                    const event = new MouseEvent('mousemove', {{
                        clientX: {960 + i * 8},
                        clientY: 540,
                        movementX: 8,
                    }});
                }}
                // Try to access OrbitControls via global
                const ctrl = window.__orbitControls || window._ctrl;
                if (ctrl) {{
                    ctrl.autoRotate = true;
                    ctrl.autoRotateSpeed = 2.0;
                    ctrl.update();
                }}
            }})()""")
            time.sleep(0.12)
            page.screenshot(path=str(gif_dir / f"frame_{i:03d}.png"))

        print(f"Saved: {len(list(gif_dir.glob('*.png')))} GIF frames")

        # === LIGHT MODE HERO ===
        ctx2 = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            color_scheme="light",
        )
        page2 = ctx2.new_page()
        page2.goto(URL, wait_until="networkidle")
        time.sleep(6)
        page2.screenshot(path=str(ASSETS / "hero-light.png"))
        print(f"Saved: hero-light.png")

        # === DETAIL VIEW (click a node) ===
        try:
            # Click on a central node
            page.mouse.click(960, 400)
            time.sleep(1.5)
            page.screenshot(path=str(ASSETS / "detail-view.png"))
            print(f"Saved: detail-view.png")
        except Exception as e:
            print(f"Detail view capture failed: {e}")

        browser.close()
        print(f"\nDone! All assets in {ASSETS}")


if __name__ == "__main__":
    capture()
