import subprocess, sys, time
from playwright.sync_api import sync_playwright
cdp = subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
URL = "http://172.23.112.54:8787/"
out = "/home/kevin/eq/analysis/"
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(cdp)
    ctx = b.contexts[0] if b.contexts else b.new_context()
    page = ctx.new_page()
    page.set_viewport_size({"width":1280,"height":1000})
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(2500)  # let canvas layout + fetches settle
    # console errors?
    errs=[]
    page.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
    page.wait_for_timeout(300)
    # full page
    page.screenshot(path=out+"dash_full.png", full_page=True)
    # graph section closeup
    page.eval_on_selector("#graph","e=>e.scrollIntoView()")
    page.wait_for_timeout(1200)
    page.screenshot(path=out+"dash_graph.png")
    # verdict/top
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(400)
    page.screenshot(path=out+"dash_top.png")
    print("title:", page.title())
    print("city bars rendered:", page.eval_on_selector_all("#cityBars .bar","els=>els.length"))
    print("zone rows:", page.eval_on_selector_all("#ztab tbody tr","els=>els.length"))
    print("graph stat:", page.eval_on_selector("#gStat","e=>e.textContent"))
    print("console errors:", errs[:8])
    page.close()
