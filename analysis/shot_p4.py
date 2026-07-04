import subprocess
from playwright.sync_api import sync_playwright
cdp=subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    pg=ctx.new_page(); errs=[]; pg.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    pg.set_viewport_size({"width":1300,"height":1050})
    pg.goto("http://172.23.112.54:8787/",wait_until="networkidle"); pg.wait_for_timeout(2500)
    # focus Guards of Qeynos via JS (find its fac id, set focus)
    r=pg.evaluate("""()=>{const d=anchData[anchCur]; const g=d.groups.find(x=>/Guards of Qeynos/.test(x.label)); if(g){anchFocus=g.fac; anchDraw();} return g?g.label:null;}""")
    pg.wait_for_timeout(800)
    print("focused:", r)
    print("stats:", pg.eval_on_selector("#anchstats","e=>e.textContent"))
    print("super-node circles:", pg.eval_on_selector_all("#anchsvg circle","e=>e.length"),
          "| self-loop paths (approx):", pg.evaluate("""[...document.querySelectorAll('#anchsvg path')].filter(p=>/C /.test(p.getAttribute('d')||'')).length"""))
    pg.eval_on_selector("#anchsvg","e=>e.scrollIntoView({block:'center'})"); pg.wait_for_timeout(500)
    pg.locator(".anchwrap").screenshot(path="/home/kevin/eq/analysis/p4_focus.png")
    print("errors:", errs[:8])
    pg.close()
