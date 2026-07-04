import subprocess
from playwright.sync_api import sync_playwright
cdp=subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    pg=ctx.new_page(); errs=[]; pg.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    pg.set_viewport_size({"width":1300,"height":1050})
    pg.goto("http://172.23.112.54:8787/",wait_until="networkidle"); pg.wait_for_timeout(2500)
    pg.eval_on_selector("#anchsvg","e=>e.scrollIntoView({block:'center'})"); pg.wait_for_timeout(600)
    print("overview labels:", pg.eval_on_selector_all("#anchLabels text","e=>e.length"))
    pg.locator(".anchwrap").screenshot(path="/home/kevin/eq/analysis/p3_overview.png")
    # zoom in (wheel up several times over center) to trigger semantic zoom
    box=pg.eval_on_selector("#anchsvg","e=>{const r=e.getBoundingClientRect();return{x:r.x+r.width*0.35,y:r.y+r.height*0.4}}")
    pg.mouse.move(box["x"],box["y"])
    for _ in range(5): pg.mouse.wheel(0,-400)
    pg.wait_for_timeout(500)
    print("zoomed labels:", pg.eval_on_selector_all("#anchLabels text","e=>e.length"),
          "zoom:", pg.evaluate("+anchT.z.toFixed(2)"))
    pg.locator(".anchwrap").screenshot(path="/home/kevin/eq/analysis/p3_zoomed.png")
    print("errors:", errs[:6])
    pg.close()
