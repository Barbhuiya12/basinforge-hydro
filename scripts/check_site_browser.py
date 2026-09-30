"""Optional real-browser check. Requires playwright and Google Chrome.

Serve _site first, then: python scripts/check_site_browser.py --url http://127.0.0.1:8000
No package model code depends on these browser-testing tools.
"""
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
    with sync_playwright() as engine:
        browser = engine.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_function("document.querySelectorAll('#model-list details').length === 61")
        assert page.locator(".chart-row").count() == 5
        page.locator("#search").fill("sacramento")
        assert page.locator("#model-list details").count() == 1
        page.locator("#model-list summary").click()
        assert page.locator("#model-list details[open] tbody tr").count() == 16
        page.locator("#search").fill("")
        page.locator("#backend").select_option("python")
        assert page.locator("#model-list details").count() == 14
        page.locator("#timestep").select_option("monthly")
        assert page.locator("#model-list details").count() == 2
        page.locator("#backend").select_option("")
        page.locator("#timestep").select_option("")
        page.locator("#theme").click()
        assert page.locator("body.dark").count() == 1
        page.reload(wait_until="networkidle")
        assert page.locator("body.dark").count() == 1
        page.locator("#theme").click()
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(args.screenshots / "desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        for route in ["", "guide.html", "research.html", "study.html", "credits.html", "roadmap.html"]:
            page.goto(args.url.rstrip("/") + "/" + route, wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"Mobile overflow: {route}"
            assert page.locator("h1").count() >= 1
        page.goto(args.url, wait_until="networkidle")
        if args.screenshots:
            page.screenshot(path=str(args.screenshots / "mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()
    print(json.dumps({"status": "passed", "registry": 61, "result_rows": 5, "mobile_pages": 6, "javascript_errors": errors}))


if __name__ == "__main__":
    main()
