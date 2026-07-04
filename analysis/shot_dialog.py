import subprocess
from playwright.sync_api import sync_playwright
cdp=subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    pg=ctx.new_page(); errs=[]; pg.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    pg.set_viewport_size({"width":1300,"height":1050})
    pg.goto("http://172.23.112.54:8787/",wait_until="networkidle"); pg.wait_for_timeout(2000)
    # center ego on Captain Tillin via JS
    pg.evaluate("""() => { const n = ONT.g.nodes.find(x=>/Captain Tillin$/.test(x.label) && x.id.startsWith('npc:')); if(n) centerOn(n.id); }""")
    pg.wait_for_timeout(1200)
    pg.eval_on_selector(".ontctl","e=>e.scrollIntoView()"); pg.wait_for_timeout(500)
    pg.screenshot(path="/home/kevin/eq/analysis/dialog_ego.png")
    crumb = pg.eval_on_selector("#ontCrumb","e=>e.textContent")
    # count mention edges in current triples panel
    ment = pg.eval_on_selector_all("#triples .trow .pred","els=>els.filter(e=>/dialog mentioning/.test(e.textContent)).length")
    print("center:", crumb)
    print("dialog-mention rows in triple list:", ment)
    print("schema arrows:", pg.eval_on_selector_all("#schema path","e=>e.length"))
    print("errors:", errs[:6])
    pg.close()
