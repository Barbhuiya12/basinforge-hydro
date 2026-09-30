"""Optional Material documentation browser check (playwright + Chrome)."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    errors = []
    base = args.url.rstrip("/") + "/"
    with sync_playwright() as engine:
        browser = engine.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base, wait_until="networkidle")
        assert page.locator(".md-sidebar--primary").is_visible()
        assert page.locator(".md-sidebar--secondary").is_visible()
        assert "BasinForge for Hydrology" in page.locator("article h1").inner_text()
        search = page.locator(".md-search__input")
        search.fill("ABCD")
        page.locator(".md-search-result__item").first.wait_for(state="visible")
        assert "ABCD" in page.locator(".md-search-result").inner_text()
        page.keyboard.press("Escape")
        search.fill("")
        page.keyboard.press("Escape")
        page.goto(base + "models/GR4J.html", wait_until="networkidle")
        assert page.locator("article h1").inner_text().startswith("GR4J")
        assert page.locator("article table tbody tr").count() >= 4
        page.goto(base, wait_until="networkidle")
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(args.screenshots / "desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator('.md-header label[for="__drawer"]').click()
        assert page.locator("#__drawer").is_checked()
        routes = ["", "installation.html", "calibration.html", "multi-basin.html", "models/ABCD.html", "study.html", "credits.html", "api.html"]
        for route in routes:
            page.goto(base + route, wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"Mobile overflow: {route}"
            assert page.locator("article h1").count() == 1
        page.goto(base, wait_until="networkidle")
        if args.screenshots:
            page.screenshot(path=str(args.screenshots / "mobile.png"))
        assert not errors, errors
        browser.close()
    print(json.dumps({"status": "passed", "sidebar": True, "full_text_search": True, "mobile_pages": len(routes), "javascript_errors": errors}))


if __name__ == "__main__":
    main()
