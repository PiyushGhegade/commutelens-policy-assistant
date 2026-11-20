"""Browser smoke test. Start an isolated fake-provider server on port 8011 first.

PowerShell: $env:LLM_PROVIDER='fake'; $env:DATA_DIR='data/ui-check'
python -m uvicorn app.main:app --port 8011
python scripts/ui_check.py
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/browser"
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8011")
    page.locator("#login").click()
    page.wait_for_function("document.getElementById('session').textContent.includes('Signed in')")
    page.locator("#question").fill("When is a night shift security escort required?")
    page.locator("#submit").click()
    page.wait_for_selector(".answer")
    assert "8 PM" in page.locator(".answer").inner_text()
    assert page.locator(".citation").count() == 1
    assert "offline" in page.locator("#provider").inner_text().lower()
    page.screenshot(path=str(OUT / "desktop.png"), full_page=True)
    page.locator("#username").select_option("bilal")
    page.locator("#login").click()
    page.wait_for_function("document.getElementById('session').textContent.includes('bilal')")
    page.locator("#question").fill("When is a night shift security escort required?")
    page.locator("#submit").click()
    page.wait_for_function("document.querySelector('.answer')?.textContent.includes('10 PM')")
    page.locator("#question").fill("Show Atlas Labs night escort rules")
    page.locator("#submit").click()
    page.wait_for_function("document.querySelector('.answer')?.textContent.includes('does not cover')")
    assert page.locator(".citation").count() == 0
    page.locator('[data-tab="source"]').click()
    assert page.locator(".source-section").count() == 8
    page.locator("#username").select_option("atlas-admin")
    page.locator("#login").click()
    page.wait_for_function("document.getElementById('session').textContent.includes('atlas-admin')")
    page.locator('[data-tab="publish"]').click()
    page.locator("#load-policy").click()
    page.wait_for_function("document.getElementById('policy-json').value.length>10")
    policy = json.loads(page.locator("#policy-json").input_value())
    new_version = policy["version"]
    policy["sections"][1]["text"] = (
        "For women employees at Atlas Labs, drops after 7 PM require a security escort."
    )
    page.locator("#policy-json").fill(json.dumps(policy, indent=2))
    page.locator("#publish-policy").click()
    page.wait_for_function("document.getElementById('publish-message').textContent.includes('is active')")
    page.locator('[data-tab="ask"]').click()
    page.locator("#question").fill("When is a night shift security escort required?")
    page.locator("#submit").click()
    page.wait_for_function("document.querySelector('.answer')?.textContent.includes('7 PM')")
    assert f"v{new_version}" in page.locator("#version").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(OUT / "mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
    assert not errors, errors
    browser.close()
    print(
        "Browser smoke check passed: login, company switch, citation, isolation, source, policy update, desktop and mobile layout."
    )
