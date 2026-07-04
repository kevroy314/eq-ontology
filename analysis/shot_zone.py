import subprocess
from playwright.sync_api import sync_playwright
cdp=subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    pg=ctx.new_page(); errs=[]; pg.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    pg.set_viewport_size({"width":1400,"height":1050})
    pg.goto("http://172.23.112.54:8787/",wait_until="networkidle"); pg.wait_for_timeout(2200)
    pg.eval_on_selector("#ontology","e=>e.scrollIntoView()"); pg.wait_for_timeout(800)
    print("zone buttons:", pg.eval_on_selector_all("#zoneBtns .btn","x=>x.length"))
    print("zonefig nodes:", pg.eval_on_selector_all("#zonefig .egonode","x=>x.length"))
    print("stats:", pg.eval_on_selector("#zstats","e=>e.textContent"))
    print("errors:", errs[:6])
    # screenshot the scroll container (top portion)
    pg.eval_on_selector(".zscroll","e=>e.scrollIntoView({block:'start'})"); pg.wait_for_timeout(500)
    pg.locator(".zscroll").screenshot(path="/home/kevin/eq/analysis/zonefig_top.png")
    # scroll figure down inside container to mid
    pg.eval_on_selector(".zscroll","e=>e.scrollTop=e.scrollHeight*0.30"); pg.wait_for_timeout(400)
    pg.locator(".zscroll").screenshot(path="/home/kevin/eq/analysis/zonefig_mid.png")
    pg.close()
