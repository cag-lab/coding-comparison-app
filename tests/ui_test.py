# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end check in headless Chromium: loads the built page from file://,
drives every tab, and asserts no console errors, no CSP violations and no
network requests. Requires: pip install playwright && playwright install chromium

Usage: python3 tests/ui_test.py
"""
import asyncio, sys, tempfile
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent.parent
F=[str(ROOT/'examples'/n) for n in ('synthetic-icu-progress-note__cag__coding.json','synthetic-icu-progress-note__cag2__coding.json')]
OUT=Path(tempfile.mkdtemp())
failures=[]
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for scheme in ['light','dark']:
            pg=await b.new_page(viewport={'width':1440,'height':1000}, color_scheme=scheme)
            msgs=[]; reqs=[]
            pg.on('console', lambda m: msgs.append(m.type+': '+m.text))
            pg.on('pageerror', lambda e: msgs.append('PAGEERROR '+str(e)))
            pg.on('request', lambda r: reqs.append(r.url))
            await pg.goto((ROOT/'coder-agreement-viewer.html').as_uri())
            await pg.set_input_files('#fileA', F)
            await pg.wait_for_selector('#mainCard:not(.hidden)')
            await pg.screenshot(path=f'{OUT}/s_view_{scheme}.png', full_page=True)
            await pg.click('#bodyA .seg >> nth=3')
            await pg.click('[data-tab=stats]'); await pg.screenshot(path=f'{OUT}/s_stats_{scheme}.png', full_page=True)
            if scheme=='light':
                await pg.click('[data-tab=spans]'); await pg.screenshot(path=f'{OUT}/s_spans.png', full_page=True)
                await pg.click('#tab-spans tbody tr >> nth=5'); 
                await pg.select_option('#viewSel','merged'); await pg.screenshot(path=f'{OUT}/s_merged.png')
                await pg.select_option('#unitSel','char'); await pg.click('[data-tab=export]')
                async with pg.expect_download() as d: await pg.click('text=Full report (.json)')
                dl=await d.value; print('download', dl.suggested_filename)
                async with pg.expect_download() as d: await pg.click('text=Span table (.csv)')
                await (await d.value).save_as(OUT/'spans.csv')
            net=[r for r in reqs if not r.startswith('file:') and not r.startswith('blob:')]
            print(scheme, 'console:', msgs, 'network requests:', net)
            if msgs: failures.append(f'{scheme}: console output {msgs}')
            if net: failures.append(f'{scheme}: network requests {net}')
        await xss_probe(b)
        await b.close()

async def xss_probe(browser):
    """Note text, codes, ids and comments containing markup must render as inert text."""
    import json
    payload = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script>'
    text = 'Pt stable. ' + payload + ' end.'
    s = text.index('<img')
    def mk(coder):
        return {'schema': 'note-coder/v1', 'coder_id': coder, 'note': {'text': text, 'char_count': len(text)},
                'annotations': [{'id': payload, 'code': payload, 'label': payload, 'comment': payload,
                                 'start': s, 'end': s + len(payload), 'text': payload}]}
    files = []
    for c in ('x1', 'x2'):
        f = OUT / f'xss_{c}.json'; f.write_text(json.dumps(mk(c))); files.append(str(f))
    pg = await browser.new_page()
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    await pg.goto((ROOT/'coder-agreement-viewer.html').as_uri())
    await pg.set_input_files('#fileA', files)
    await pg.wait_for_selector('#mainCard:not(.hidden)')
    await pg.click('#bodyA .seg')
    for tab in ('stats', 'spans', 'export', 'view'):
        await pg.click(f'[data-tab={tab}]')
    res = await pg.evaluate("""() => ({ pwned: window.__pwned === 1,
        imgs: document.querySelectorAll('main img').length,
        scripts: document.querySelectorAll('main script').length,
        shown: document.getElementById('bodyA').textContent.includes('<script>') })""")
    print('xss probe', res, errs)
    if res['pwned'] or res['imgs'] or res['scripts'] or not res['shown'] or errs:
        failures.append(f'markup injection probe failed: {res} {errs}')
asyncio.run(main())
print('screenshots in', OUT)
if failures:
    sys.exit('FAIL: ' + '; '.join(failures))
print('PASS')
