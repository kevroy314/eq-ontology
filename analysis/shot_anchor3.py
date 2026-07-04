import subprocess
from playwright.sync_api import sync_playwright
cdp=subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    pg=ctx.new_page(); errs=[]; pg.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    pg.set_viewport_size({"width":1300,"height":1050})
    pg.goto("http://172.23.112.54:8787/",wait_until="networkidle"); pg.wait_for_timeout(2500)
    pg.eval_on_selector("#anchsvg","e=>e.scrollIntoView({block:'center'})"); pg.wait_for_timeout(500)
    box=pg.eval_on_selector("#anchsvg","e=>{const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}}")
    pg.mouse.move(box["x"],box["y"]); pg.mouse.wheel(0,-500); pg.wait_for_timeout(300)
    print("transform after wheel:", pg.eval_on_selector("#anchRoot","e=>e.getAttribute('transform')"))
    pg.mouse.move(box["x"],box["y"]); pg.mouse.down(); pg.mouse.move(box["x"]+90,box["y"]+50,steps=5); pg.mouse.up(); pg.wait_for_timeout(200)
    print("transform after drag:", pg.eval_on_selector("#anchRoot","e=>e.getAttribute('transform')"))
    pg.locator(".anchwrap").screenshot(path="/home/kevin/eq/analysis/anchor_fixed.png")
    print("errors:", errs[:6])
    pg.close()
