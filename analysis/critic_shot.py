import subprocess, sys
from playwright.sync_api import sync_playwright
cdp=subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
tag=sys.argv[1] if len(sys.argv)>1 else "v"
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    pg=ctx.new_page(); errs=[]; pg.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    pg.set_viewport_size({"width":1400,"height":1000})
    pg.goto("http://172.23.112.54:8787/",wait_until="networkidle"); pg.wait_for_timeout(2500)
    pg.eval_on_selector("#anchsvg","e=>e.scrollIntoView({block:'center'})"); pg.wait_for_timeout(600)
    st=pg.eval_on_selector("#anchstats","e=>e.textContent")
    pg.locator(".anchwrap").screenshot(path=f"/home/kevin/eq/analysis/critic_{tag}_full.png")
    # zoom into left cluster for label/geometry detail
    box=pg.eval_on_selector("#anchsvg","e=>{const r=e.getBoundingClientRect();return{x:r.x+r.width*0.32,y:r.y+r.height*0.4}}")
    pg.mouse.move(box["x"],box["y"])
    for _ in range(4): pg.mouse.wheel(0,-400)
    pg.wait_for_timeout(500)
    pg.locator(".anchwrap").screenshot(path=f"/home/kevin/eq/analysis/critic_{tag}_zoom.png")
    print("stats:", st, "| errors:", errs[:4])
    pg.close()
