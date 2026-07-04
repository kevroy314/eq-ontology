import subprocess
from playwright.sync_api import sync_playwright
cdp = subprocess.check_output(["/home/kevin/.claude/skills/edge-cdp-browser/scripts/cdp_url.sh"]).decode().strip()
URL="http://172.23.112.54:8787/"
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp(cdp); ctx=b.contexts[0] if b.contexts else b.new_context()
    pg=ctx.new_page(); errs=[]; pg.on("console",lambda e:errs.append(e.text) if e.type=="error" else None)
    pg.set_viewport_size({"width":1300,"height":1050})
    pg.goto(URL,wait_until="networkidle"); pg.wait_for_timeout(2000)
    pg.eval_on_selector("#ontology","e=>e.scrollIntoView()"); pg.wait_for_timeout(1200)
    # schema panel
    pg.screenshot(path="/home/kevin/eq/analysis/onto_schema.png")
    # ego + triples: scroll a bit down
    pg.evaluate("document.querySelector('.ontctl').scrollIntoView()"); pg.wait_for_timeout(600)
    pg.screenshot(path="/home/kevin/eq/analysis/onto_ego.png")
    print("center:", pg.eval_on_selector("#ontCrumb","e=>e.textContent"))
    print("ego nodes:", pg.eval_on_selector_all("#ego .egonode","e=>e.length"))
    print("triples rows:", pg.eval_on_selector_all("#triples .trow","e=>e.length"))
    print("schema arrows:", pg.eval_on_selector_all("#schema path","e=>e.length"))
    # click a featured NPC chip to traverse
    pg.eval_on_selector_all("#ontChips .chip","els=>{const c=els.find(x=>/Ran Walker|beggar|Apprentice/.test(x.textContent));if(c)c.click();}")
    pg.wait_for_timeout(900)
    pg.evaluate("document.querySelector('.ontctl').scrollIntoView()"); pg.wait_for_timeout(500)
    pg.screenshot(path="/home/kevin/eq/analysis/onto_ego2.png")
    print("after chip center:", pg.eval_on_selector("#ontCrumb","e=>e.textContent"))
    print("errors:", errs[:8])
    pg.close()
