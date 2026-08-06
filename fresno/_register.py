"""Complete the Realauction bidder registration wizard (all steps).
Reusable; safe to re-run — if already registered, it stops gracefully.
"""
import asyncio, os, sys, json
from playwright.async_api import async_playwright

SESSION_DIR = r"C:\Users\chuck\Downloads\county_pipeline\fresno\.playwright_session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
REG_URL = "https://fresnocounty.california.taxdefaultsale.com/index.cfm?zaction=Register&zmethod=START"

STEP1 = {
    "first_name": "Charles",
    "last_name": "Terrell",
    "email": "chuckterrell740@gmail.com",
    "email2": "chuckterrell740@gmail.com",
    "phone": "5305265675",
    "address_1": "1355 1st st",
    "address_2": "",
    "city": "Red Bluff",
    "ZipCode": "96080",
    "state": "CA",
}

STEP2 = {
    "nickName": "CTerrell",
    "aliasText": "Charles Terrell",
    "aliasAddress_1": "1355 1st st",
    "aliasAddress_2": "",
    "aliasCity": "Red Bluff",
    "aliasStateAbbr": "CA",
    "aliasZip": "96080",
    "titlePhone1": "5305265675",
    "titlePhone2": "",
    "Owner_First_Name": "Charles",
    "Owner_Last_Name": "Terrell",
    "Owner_Initial": "",
    "Co_Owner_Last": "",
    "Co_Owner_First": "",
    "Co_Owner_Initial": "",
}

async def visible_fields(page):
    return await page.evaluate(
        "Array.from(document.querySelectorAll('.register-field, .regfield')).map(e=>{"
        "const r=e.getBoundingClientRect();"
        "return {name:e.name||e.id, tag:e.tagName, type:e.type||'', "
        "cls:(e.className||'').toString().slice(0,60), vis:r.width>0&&r.height>0};})"
        ".filter(f=>f.vis)")

async def fill_step(page, data):
    for name, val in data.items():
        if val == "":
            continue
        try:
            el = page.locator(f"#{name}").first
            if await el.evaluate("e=>e.tagName") == "SELECT":
                await el.select_option(val)
            else:
                await el.fill(val)
                await page.wait_for_timeout(60)
                await el.dispatch_event("blur")
                await page.wait_for_timeout(150)
        except Exception:
            pass
    await page.wait_for_timeout(2500)

def ok(v):
    return "OK " if "valid" in v["cls"] else "BAD" if "error" in v["cls"] else "-- "

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR, headless=True,
            user_agent=UA, viewport={"width": 1440, "height": 1000})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        await page.goto(REG_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        print("STEP 0 TEXT:", (await page.evaluate("document.body.innerText"))[:180].replace("\n", " "))

        # ----- STEP 1 -----
        await fill_step(page, STEP1)
        print("\nSTEP 1 VALIDATION:")
        for f in await visible_fields(page):
            print(f"  {ok(f)} {f['name']:14s} {f['cls'][:45]}")
        msgs = await page.evaluate(
            "document.getElementById('errorMessage') ? document.getElementById('errorMessage').innerText : ''")
        print("errorMessage:", repr(msgs))
        b = page.locator("#nextButton1")
        cls = await b.get_attribute("class")
        print("nextButton1 class:", cls)
        await b.click(force=True)
        await page.wait_for_timeout(4000)
        step = await page.evaluate("document.getElementById('currentStep').value")
        print("currentStep after Next:", step)
        if step == "1":
            print("STILL ON STEP 1")
            await ctx.close(); return

        # ----- STEP 2 -----
        await fill_step(page, STEP2)
        print("\nSTEP 2 VALIDATION:")
        for f in await visible_fields(page):
            print(f"  {ok(f)} {f['name']:14s} {f['cls'][:45]}")
        b = page.locator("#nextButton2")
        cls = await b.get_attribute("class")
        print("nextButton2 class:", cls)
        await b.click(force=True)
        await page.wait_for_timeout(4000)
        step = await page.evaluate("document.getElementById('currentStep').value")
        print("currentStep after Next on step 2:", step)
        if step == "2":
            print("STILL ON STEP 2")
            await ctx.close(); return

        # ----- STEP 3 -----
        print("\nSTEP 3 FIELDS:")
        for f in await visible_fields(page):
            print(f"  {ok(f)} {f['name']:14s} {f['cls'][:45]}")

        import random, string
        pw = "Td!" + "".join(random.choices(string.ascii_letters + string.digits, k=14))
        print("Generated password (write down / reset later):", pw)

        step3 = {
            "user_name": "chuckterrell740@gmail.com",
            "user_pass": pw,
            "password2": pw,
            "securityquestion": await page.evaluate(
                "document.getElementById('securityquestion').options[1].value"),
            "securityanswer": "Red Bluff",
        }
        await fill_step(page, step3)
        print("\nSTEP 3 VALIDATION:")
        for f in await visible_fields(page):
            print(f"  {ok(f)} {f['name']:14s} {f['cls'][:45]}")
        b = page.locator("#nextButton3")
        cls = await b.get_attribute("class")
        print("nextButton3 class:", cls)
        await b.click(force=True)
        await page.wait_for_timeout(4000)
        step = await page.evaluate("document.getElementById('currentStep').value")
        print("currentStep after Next on step 3:", step)

        print("\nSTEP 4 FIELDS:")
        for f in await visible_fields(page):
            print(f"  {ok(f)} {f['name']:14s} {f['cls'][:45]}")
        body = (await page.evaluate("document.body.innerText"))
        print("STEP 4 TEXT:", body[:400].encode("ascii", "replace").decode())

        # check confirmInfo + any required checkboxes, then click Register Account
        try:
            cb = page.locator("#confirmCheckBox")
            if await cb.count() and await cb.first.is_visible():
                await cb.first.click(force=True)
                await page.wait_for_timeout(500)
                print("confirmCheckBox clicked")
            else:
                await page.evaluate(
                    "document.getElementById('confirmCheckBox').click()")
                await page.wait_for_timeout(500)
                print("confirmCheckBox clicked via JS")
            state = await page.evaluate(
                "(()=>{const b=document.getElementById('registerButton');"
                "return {cls:b.className, checked:document.getElementById('confirmInfo').checked};})()")
            print("registerButton:", json.dumps(state))
        except Exception as e:
            print("confirm click failed:", type(e).__name__, str(e)[:120])

        reg_btns = await page.evaluate(
            "Array.from(document.querySelectorAll('button, a, input[type=submit], input[type=button]')).map(e=>({"
            "t:(e.innerText||e.value||'').trim().slice(0,50), id:e.id||'', cls:(e.className||'').toString().slice(0,60),"
            "vis:(e.offsetWidth||0)>0&&(e.offsetHeight||0)>0}))"
            ".filter(x=>/register|account|submit|confirm/i.test(x.t+x.id+x.cls))")
        print("REGISTER CONTROLS:", json.dumps(reg_btns))

        clicked = False
        for ctl in reg_btns:
            if not ctl["vis"]:
                continue
            sel = f"#{ctl['id']}" if ctl["id"] else f"button:text-is('{ctl['t']}')"
            try:
                await page.locator(sel).first.click(force=True)
                clicked = True
                print("clicked:", ctl["t"], sel)
                break
            except Exception as e:
                print("click fail", ctl["t"], type(e).__name__)
        await page.wait_for_timeout(6000)

        body = (await page.evaluate("document.body.innerText"))
        print("FINAL PAGE:", body[:600].encode("ascii", "replace").decode())
        await ctx.close()

asyncio.run(main())
