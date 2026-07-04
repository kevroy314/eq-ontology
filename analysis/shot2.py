import subprocess
from playwright.sync_api import sync_playwright
cdp = subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(cdp)
    ctx = b.contexts[0] if b.contexts else b.new_context()
    page = ctx.new_page(); page.set_viewport_size({"width":1280,"height":1000})
    page.goto("http://172.23.112.54:8787/", wait_until="networkidle"); page.wait_for_timeout(1500)
    # Shadow Haven contrast
    page.eval_on_selector("#graph","e=>e.scrollIntoView()")
    page.get_by_text("Shadow Haven", exact=True).first.click()
    page.wait_for_timeout(1800)
    page.screenshot(path="/home/kevin/eq/analysis/dash_shadowhaven.png")
    # table sorted by faction diversity
    page.eval_on_selector("#zones","e=>e.scrollIntoView()"); page.wait_for_timeout(400)
    page.get_by_text("factions", exact=True).click(); page.wait_for_timeout(500)
    page.screenshot(path="/home/kevin/eq/analysis/dash_table.png")
    print("ok, sorted table top zone:", page.eval_on_selector("#ztab tbody tr td:nth-child(2)","e=>e.textContent"))
    page.close()
