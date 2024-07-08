from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    for browser_type in [p.chromium, p.firefox, p.webkit]:
        browser = browser_type.launch(headless=True)
        page = browser.new_page()
        page.goto(
            "file:///H:/Bot/%E7%8E%B0%E5%BD%B9Bot/mybot/src/nonebot_plugin_dialectlist/nonebot_plugin_dialectlist/temple/rank_temple.html"
        )
        page.screenshot(path=f"screenshot-{browser_type.name}.png", full_page=True)
        print(page.title())
        browser.close()
