import subprocess
from playwright.sync_api import sync_playwright
cdp = subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
URL="http://172.23.112.54:8787/"
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    errs=[]
    # ---- MOBILE ----
    m=ctx.new_page(); m.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    m.set_viewport_size({"width":390,"height":780})
    m.goto(URL,wait_until="networkidle"); m.wait_for_timeout(1800)
    m.eval_on_selector("#graph","e=>e.scrollIntoView()"); m.wait_for_timeout(900)
    m.screenshot(path="/home/kevin/eq/analysis/m_fit.png")
    # simulate pinch-zoom-in via API, then a pan
    m.evaluate("zoomAt(view.W/2, view.H/2, 2.4); draw();"); m.wait_for_timeout(500)
    m.evaluate("panX+=40; panY-=30; draw();"); m.wait_for_timeout(300)
    m.screenshot(path="/home/kevin/eq/analysis/m_zoom.png")
    zinfo=m.evaluate("({zoom:+zoom.toFixed(2), rk:+rk.toFixed(2), nodes:G.nodes.length})")
    print("mobile zoom state:", zinfo, "errors:", errs[:6])
    m.close()
    # ---- DESKTOP wheel zoom sanity ----
    d=ctx.new_page(); derr=[]; d.on("console",lambda e:derr.append(e.text) if e.type=="error" else None)
    d.set_viewport_size({"width":1280,"height":1000})
    d.goto(URL,wait_until="networkidle"); d.wait_for_timeout(1500)
    d.eval_on_selector("#graph","e=>e.scrollIntoView()"); d.wait_for_timeout(600)
    box=d.eval_on_selector("#cv","e=>{const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}}")
    d.mouse.move(box["x"],box["y"]); d.mouse.wheel(0,-600); d.wait_for_timeout(400)
    d.screenshot(path="/home/kevin/eq/analysis/d_wheelzoom.png")
    print("desktop zoom:", d.evaluate("+zoom.toFixed(2)"), "errors:", derr[:6])
    d.close()
