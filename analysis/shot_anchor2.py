import subprocess
from playwright.sync_api import sync_playwright
cdp=subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    pg=ctx.new_page(); errs=[]; pg.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    pg.set_viewport_size({"width":1300,"height":1050})
    pg.goto("http://172.23.112.54:8787/",wait_until="networkidle"); pg.wait_for_timeout(2500)
    print("edge <line> count:", pg.eval_on_selector_all("#anchsvg line","e=>e.length"))
    print("group rects:", pg.eval_on_selector_all("#anchsvg rect[rx='13']","e=>e.length"))
    print("has anchRoot:", pg.eval_on_selector_all("#anchRoot","e=>e.length"))
    # simulate wheel zoom over the svg, then check transform changed
    box=pg.eval_on_selector("#anchsvg","e=>{const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}}")
    pg.mouse.move(box["x"],box["y"]); pg.mouse.wheel(0,-500); pg.wait_for_timeout(300)
    print("transform after wheel:", pg.eval_on_selector("#anchRoot","e=>e.getAttribute('transform')"))
    # drag to pan
    pg.mouse.move(box["x"],box["y"]); pg.mouse.down(); pg.mouse.move(box["x"]+80,box["y"]+40); pg.mouse.up(); pg.wait_for_timeout(200)
    print("transform after drag:", pg.eval_on_selector("#anchRoot","e=>e.getAttribute('transform')"))
    pg.eval_on_selector("#anchsvg","e=>e.scrollIntoView({block:'center'})"); pg.wait_for_timeout(400)
    pg.locator(".anchwrap").screenshot(path="/home/kevin/eq/analysis/anchor_fixed.png")
    print("errors:", errs[:6])
    pg.close()
