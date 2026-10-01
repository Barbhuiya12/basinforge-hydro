"""Optional Read the Docs browser check (playwright + Chrome)."""
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
        assert page.locator(".wy-nav-side").is_visible()
        assert page.locator(".wy-breadcrumbs").is_visible()
        assert "Welcome to BasinForge" in page.locator(".rst-content h1").inner_text()
        search = page.locator('.wy-side-nav-search input[name="q"]')
        search.fill("ABCD")
        search.press("Enter")
        page.locator("#search-results li").first.wait_for(state="visible")
        assert "ABCD" in page.locator("#search-results").inner_text()
        page.goto(base + "models/GR4J.html", wait_until="networkidle")
        assert page.locator(".rst-content h1").inner_text().startswith("GR4J")
        assert page.locator(".rst-content table tbody tr").count() >= 4
        page.goto(base, wait_until="networkidle")
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(args.screenshots / "desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator(".wy-nav-top .fa-bars").click()
        assert "shift" in page.locator(".wy-nav-side").get_attribute("class")
        routes = ["", "quickstart.html", "installation.html", "configuration.html", "calibration.html", "multi-basin.html", "models/ABCD.html", "study.html", "credits.html", "api.html"]
        for route in routes:
            page.goto(base + route, wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"Mobile overflow: {route}"
            assert page.locator(".rst-content h1").count() == 1
        page.goto(base, wait_until="networkidle")
        if args.screenshots:
            page.screenshot(path=str(args.screenshots / "mobile.png"))
        assert not errors, errors
        browser.close()
    print(json.dumps({"status": "passed", "sidebar": True, "full_text_search": True, "mobile_pages": len(routes), "javascript_errors": errors}))


if __name__ == "__main__":
    main()
