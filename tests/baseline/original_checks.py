import sys, urllib.parse, subprocess, json
from playwright.sync_api import sync_playwright

PAGE = "file:///home/claude/repo/index.html"
OUT = "/tmp/claude-0/-home-claude/b235270b-9e6e-5a4f-98b5-b7472ae5ff5a/scratchpad/"
results = []
def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))

def pdfinfo(path):
    t = subprocess.run(["pdfinfo", path], capture_output=True, text=True).stdout
    pages = int([l for l in t.splitlines() if l.startswith("Pages:")][0].split()[-1])
    size = [l for l in t.splitlines() if l.startswith("Page size:")][0]
    return pages, size

def pdftext(path, first=None, last=None):
    cmd = ["pdftotext", "-layout"]
    if first: cmd += ["-f", str(first), "-l", str(last or first)]
    return subprocess.run(cmd + [path, "-"], capture_output=True, text=True).stdout

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])

    # ---------- Desktop: existing estimate behaviour ----------
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "ERR_TUNNEL" not in m.text and errors.append(m.text))
    pg.goto(PAGE); pg.wait_for_timeout(500)

    pg.click('[data-inc="c2"]')                      # Add Supacem 42.5
    for _ in range(9): pg.click('#est [data-inc="c2"]')  # stepper +9 -> 10
    pg.click('[data-inc="i3"]', force=True) if pg.locator('#list [data-inc="i3"]').count() else None
    pg.evaluate("set('i3',25)")                        # iron rod 12 mm x25 (same path the input uses)
    pg.fill('#est input[data-qty="i3"]', "24"); pg.dispatch_event('#est input[data-qty="i3"]', "change")
    pg.click('#est [data-dec="c2"]')                  # 10 -> 9
    tot = pg.inner_text("#tot")
    exp = 9*100 + 24*58
    check("Stepper +/−, typed qty and totals unchanged", f"{exp:,}.00" in tot.replace(" ", ","), tot.replace("\n", " | "))
    pg.fill("#q", "dzata"); pg.wait_for_timeout(100)
    check("Search still filters", "Dzata 42.5" in pg.inner_text("#list") and "Supacem" not in pg.inner_text("#list"))
    pg.fill("#q", ""); pg.wait_for_timeout(100)
    pg.click('#tabs button[data-cat="Iron Rods (Per Ton)"]'); pg.wait_for_timeout(700)
    check("Category tabs still switch", pg.get_attribute('#tabs button[data-cat="Iron Rods (Per Ton)"]', "aria-pressed") == "true")
    check("Quotation hidden on screen", not pg.is_visible("#quote"))

    pg.fill("#loc", "Buduburam, Block 4 near the clinic"); pg.dispatch_event("#loc", "input")
    ref = pg.inner_text("#ref").replace("Ref ", "")
    href = pg.get_attribute("#send", "href")
    msg = urllib.parse.unquote(href.split("text=", 1)[1])
    open(OUT + "wa_message.txt", "w").write(msg)
    check("WhatsApp: estimate reference", ref in msg, ref)
    check("WhatsApp: drop-off location", "Buduburam, Block 4 near the clinic" in msg)
    check("WhatsApp: items, qty, unit price, line totals", "Supacem 42.5 (50 kg bag)" in msg and "9 × GH₵100.00 = GH₵900.00" in msg and "24 × GH₵58.00" in msg)
    check("WhatsApp: materials total", f"Materials total: GH₵{exp:,}.00" in msg)
    check("WhatsApp: confirm availability and delivery", "confirm availability and the delivery cost" in msg)
    pg.fill("#loc", ""); pg.dispatch_event("#loc", "input")
    msg2 = urllib.parse.unquote(pg.get_attribute("#send", "href").split("text=", 1)[1])
    check("WhatsApp: no location line when empty", "Drop-off location" not in msg2)
    pg.fill("#loc", "Buduburam, Block 4 near the clinic"); pg.dispatch_event("#loc", "input")

    # ---------- Desktop PDF ----------
    pg.emulate_media(media="print")
    pg.evaluate("dispatchEvent(new Event('beforeprint'))")
    pg.pdf(path=OUT + "desktop.pdf", prefer_css_page_size=True, print_background=True)
    pages, size = pdfinfo(OUT + "desktop.pdf")
    txt = pdftext(OUT + "desktop.pdf")
    check("A4 page size (595 x 842 pt)", "(A4)" in size, size)
    check("Short estimate fits one page", pages == 1, f"{pages} page(s)")
    check("PDF quantities print as plain numbers", any(l.split()[-3:-2] == ["9"] for l in txt.splitlines() if "Supacem 42.5" in l) or " 9 " in txt, "")
    check("PDF has ref, date, location", ref in txt and "Buduburam" in txt)
    p1 = pdftext(OUT + "desktop.pdf", 1)
    check("Short PDF: page number 'Page 1 of 1'", "Page 1 of 1" in p1)
    check("Short PDF: no continuation header on page 1", "Continued" not in p1)
    check("Short PDF: closing section (terms, to order, ref)", "DELIVERY AND TERMS" in p1.upper().replace(" ","").replace("DELIVERYANDTERMS","DELIVERY AND TERMS") and "TOORDER" in p1.upper().replace(" ","") and p1.count(ref) >= 2)
    check("Same ref on screen, PDF and WhatsApp", ref in p1 and ref in msg, ref)
    check("Ref format TCP-YYMMDD-XXXXXX", __import__("re").fullmatch(r"TCP-\d{6}-[2-9A-HJ-NP-Z]{6}", ref) is not None, ref)
    check("No website controls in PDF", "Add" not in txt.split() and "Send my estimate" not in txt and "Clear estimate" not in txt and "Swipe" not in txt)
    pg.emulate_media(media="screen")

    # ---------- New quotation after Clear ----------
    pg.click("#clear")
    ref2 = pg.inner_text("#ref").replace("Ref ", "")
    pg.evaluate("set('c1',2)")
    msg3 = urllib.parse.unquote(pg.get_attribute("#send", "href").split("text=", 1)[1])
    check("Clear estimate issues a new reference", ref2 != ref and ref2 in msg3 and ref not in msg3, f"{ref} -> {ref2}")
    refs = pg.evaluate("(()=>{const s=new Set();for(let i=0;i<5000;i++){newQuote();s.add(REF);}return s.size})()")
    check("5,000 references generated in one day are all different", refs == 5000, f"{refs} unique")
    pg.click("#clear")
    refL = pg.inner_text("#ref").replace("Ref ", "")
    # ---------- Long estimate: pagination ----------
    pg.evaluate("""for(let k=0;k<45;k++){P.push({id:'t'+k,cat:'Iron Rods (Single Piece)',name:'Test item '+(k+1),unit:'30 ft rod',price:10+k});qty['t'+k]=k+1;} P.forEach(p=>{if(!p.id.startsWith('t'))qty[p.id]=3;}); renderEst();""")
    pg.emulate_media(media="print")
    pg.evaluate("dispatchEvent(new Event('beforeprint'))")
    pg.pdf(path=OUT + "long.pdf", prefer_css_page_size=True, print_background=True)
    lp, lsize = pdfinfo(OUT + "long.pdf")
    p2 = pdftext(OUT + "long.pdf", 2)
    last = pdftext(OUT + "long.pdf", lp)
    allt = pdftext(OUT + "long.pdf")
    rows = sum(1 for l in allt.splitlines() if l.strip()[:3].strip().rstrip('.').isdigit() and "GH₵" in l)
    check("Long estimate flows to extra pages", lp >= 2, f"{lp} pages, {lsize}")
    check("Column headings repeat on page 2", "DESCRIPTION" in p2.upper())
    check("All 62 rows printed, none lost", rows == 62, f"{rows} rows found")
    check("Long PDF: different ref from short PDF", refL != ref and refL in allt, f"{ref} vs {refL}")
    check("Continuation pages: brand, ref, 'Page 2 of N'", "The Cement People" in p2 and refL in p2 and f"Page 2 of {lp}" in p2)
    check("Page 1 of long PDF has no continuation header", "Continued" not in pdftext(OUT + "long.pdf", 1))
    check("Last page: 'Page N of N' and closing section", f"Page {lp} of {lp}" in last and "DELIVERYANDTERMS" in last.upper().replace(" ","") and "TOORDER" in last.upper().replace(" ",""))
    check("Totals block intact on last page", "Total before delivery" in last and "Materials" in last)
    pg.emulate_media(media="screen")
    check("No script errors (desktop)", not errors, "; ".join(errors))

    # ---------- Mobile: estimate opened full-screen, then print ----------
    m = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    merr = []
    m.on("pageerror", lambda e: merr.append(str(e)))
    m.goto(PAGE); m.wait_for_timeout(500)
    m.evaluate("set('c1',40);set('c4',12);set('j3',2);set('i8',5)")
    m.click("#barBtn"); m.wait_for_timeout(200)
    check("Mobile: 'View estimate' still opens full screen", m.evaluate("document.querySelector('#est').classList.contains('open')"))
    m.fill("#loc", "Kasoa, Millennium City"); m.dispatch_event("#loc", "input")
    m.emulate_media(media="print")
    m.evaluate("dispatchEvent(new Event('beforeprint'))")
    m.pdf(path=OUT + "mobile.pdf", prefer_css_page_size=True, print_background=True)
    mp, msize = pdfinfo(OUT + "mobile.pdf")
    mt = pdftext(OUT + "mobile.pdf")
    check("Mobile print: A4, content present while overlay open", "(A4)" in msize and "Ghacem Waterproof 42.5" in mt and "Millennium City" in mt, f"{mp} page(s), {msize}")
    check("No script errors (mobile)", not merr, "; ".join(merr))
    b.close()

src = open("/home/claude/repo/index.html").read()
check("No test items in the site code", "Test item" not in src and "'t'+" not in src)
for n, ok, d in results:
    print(("PASS " if ok else "FAIL ") + n + (f"  [{d}]" if d else ""))
print(f"\n{sum(o for _,o,_ in results)}/{len(results)} passed")
