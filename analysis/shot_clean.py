import subprocess
from playwright.sync_api import sync_playwright
cdp=subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    pg=ctx.new_page(); errs=[]; pg.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    pg.set_viewport_size({"width":1400,"height":1000})
    pg.goto("http://172.23.112.54:8787/",wait_until="networkidle"); pg.wait_for_timeout(2500)
    pg.eval_on_selector("#anchsvg","e=>e.scrollIntoView({block:'center'})"); pg.wait_for_timeout(500)
    pg.locator(".anchwrap").screenshot(path="/home/kevin/eq/analysis/clean_edges_on.png")
    pg.eval_on_selector("#anchedges","b=>b.click()"); pg.wait_for_timeout(700)   # connections off
    pg.locator(".anchwrap").screenshot(path="/home/kevin/eq/analysis/clean_edges_off.png")
    print("edge lines after toggle-off:", pg.eval_on_selector_all("#anchsvg path,#anchsvg line","els=>els.filter(e=>e.getAttribute('stroke')&&/7ee0a0|c98bdb/.test(e.getAttribute('stroke'))).length"))
    print("errors:", errs[:5])
    pg.close()
