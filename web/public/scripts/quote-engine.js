/* ===========================================================================
   quote-engine.js - The Cement People quotation engine
   ---------------------------------------------------------------------------
   Everything interactive on the page lives here: the price list, search,
   category tabs and swiping, the estimate panel, the WhatsApp message, the
   printable A4 quotation and the quotation reference number.

   WHY THIS FILE IS IN public/ AND NOT src/
   Astro normally repackages scripts in src/ into JavaScript "modules", which
   hides their variables from the rest of the page. This engine was written as
   a plain script whose variables (P, qty, REF ...) are shared globally, and
   the regression tests depend on that. Files in public/ are copied to the
   built site byte-for-byte, so the browser loads this as the same kind of
   plain script it always was:
       <script is:inline src="/scripts/quote-engine.js"></script>
   placed at the end of <body> (see src/pages/index.astro), after the
   tcp-data block it reads.

   WHAT CHANGED FROM THE ORIGINAL (index.html at tag v1-single-file)
   Only the two "DATA HOOK-UP" sections: products, currency, tax rate and
   business details are read from the page instead of being typed in here.
   The comments are new. All calculations, the WhatsApp text, the quotation
   layout and every element ID are unchanged.

   PHASE 2 (SEO) CHANGES - presentation only, no calculation touched
   1. In the price list, category headings are now <h3> and subgroup headings
      <h4> (were <h2>/<h3>), so the page has a correct heading outline under
      "Products and prices". site.css was updated to match; nothing looks
      different.
   2. After printing, the page title is restored from the page itself
      instead of a title typed into this file.
   The same price-list markup is also written into the page at build time by
   src/lib/catalog-html.ts; a test keeps the two identical.

   PHASE 3 (Astro parity, Nov 2026) - presentation only, no calculation touched
   Carried over from the live index.html: product thumbnails, the bold rod
   size tags, and the shared iron-rods banner with a "how it's sold" note at
   the top of each rod tab (see "Product photos" below). The data for them
   comes from products.json and categories.json through the tcp-data block.

   ESTIMATE REDESIGN AND BRAND IDENTITY V1.1 (17 Nov 2026) - presentation;
   every price, quantity rule and total is calculated exactly as before.
   1. The estimate is grouped into sections (Cement; Iron rods, single pieces
      and by the ton; Binding wire), each with its quantity and subtotal,
      and "Your order at a glance" at the top. Sections fold away.
   2. Its heading (with "View full estimate" and "Clear estimate") and its
      bottom (totals, WhatsApp, PDF) stay put; only the materials scroll.
   3. "Clear estimate" asks first; Undo is still offered afterwards.
   4. "View full estimate": a large view on computers, full screen on phones.
   5. Every quantity shows its unit (bags, pcs, tons, rolls).
   6. The PDF quotation has the new logo, the same sections, units and
      section subtotals; "Total (excl. delivery)"; delivery "To be confirmed".
   7. One "Enquire" button offers WhatsApp or a call (see "Enquire menus").
   8. Binding wire is its own category in products.json (it was listed
      under single-piece rods, so the PDF called it a rod).
   =========================================================================== */
// ---------------------------------------------------------------------------
// DATA HOOK-UP 1 of 2: products, currency and tax rate
// Previously typed straight into this file. Now the page carries them in a
// <script type="application/json" id="tcp-data"> block, built by Astro from
// src/data/products.json and src/config/business.ts. "P" stays a plain
// global variable, exactly as before (the regression tests rely on that).
// Each product: {id, cat, sub (optional subgroup), name, unit, price}, plus
// optional img (square photo), alt (its description) and size (rod size tag).
// The block also carries "banners" and "categoryInfo" (tab photos and notes,
// from src/data/categories.json).
// ---------------------------------------------------------------------------
const TCP=JSON.parse(document.getElementById("tcp-data").textContent);
const CURRENCY=TCP.currency,TAX_RATE=TCP.taxRate;
const P=TCP.products;

// ---- Shared state and small helpers ----------------------------------------
// cats  the category names, in the order they first appear in the products
// cat   the category tab currently showing; q the search text; qty {id: count}
// $     shorthand for document.querySelector; money() formats GH₵1,392.00
const cats=[...new Set(P.map(p=>p.cat))];
const ICON={"Cement":`<svg viewBox="0 0 28 28" aria-hidden="true"><path d="M6 5h16l3 5v14H3V10z" fill="currentColor"/><rect x="8" y="12" width="12" height="8" fill="#ff9802"/></svg>`,"Iron rods and wire":`<svg viewBox="0 0 28 28" aria-hidden="true"><rect x="2" y="5" width="24" height="4" rx="2" fill="currentColor"/><rect x="2" y="12" width="24" height="4" rx="2" fill="currentColor"/><rect x="2" y="19" width="24" height="4" rx="2" fill="currentColor"/><rect x="11" y="3" width="5" height="22" fill="#ff9802"/></svg>`,"Binding Wire":`<svg viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="10" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="14" cy="14" r="4.5" fill="none" stroke="#ff9802" stroke-width="3"/></svg>`};
ICON["Iron Rods (Single Piece)"]=ICON["Iron Rods (Per Ton)"]=ICON["Iron rods and wire"];
let cat=cats[0],q="",qty={};
const $=s=>document.querySelector(s);
const money=n=>CURRENCY+n.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});


// ---- Quantity controls ------------------------------------------------------
// A product not yet in the estimate shows an "Add" button; once added it shows
// a − / number / + stepper. Clicks are handled further down by data-inc/data-dec.
// Rods sold by the ton (unit "ton") go up and down in half tons (decided
// 14 Nov 2026: only 0.5-ton steps, smallest amount half a ton); "Add"
// starts at 1 ton. Everything else counts in whole items.
// The most of any one product a customer can put in the estimate. Raised
// from 9,999 to 50,000 on 17 Nov 2026 (Daniel). A bigger typed number is
// lowered to this.
const MAX_QTY=50000;
// A quantity as people read it: 50,000 and 2.5 (17 Nov 2026). Used
// everywhere a quantity is shown: the quantity boxes, the estimate's
// summary and headings, the WhatsApp message and the PDF.
const fmtQ=n=>(+n).toLocaleString("en-US",{maximumFractionDigits:2});
// Reading a typed quantity. Commas that group thousands are ignored
// ("50,000" = 50000, "1,234.5" = 1234.5); any other comma is a decimal
// point, as many phones type it ("2,5" tons = 2.5).
function parseQ(v){v=String(v).replace(/\s/g,"");if(/^\d{1,3}(,\d{3})+(\.\d*)?$/.test(v))v=v.replace(/,/g,"");else v=v.replace(",",".");return parseFloat(v);}
const TON=p=>p.unit==="ton";
const STEP=p=>TON(p)?0.5:1;
// The small word shown beside the quantity box so the unit is never in
// doubt: "ton"/"tons" for rods by the ton, "pc"/"pcs" for single rods
// (unit "30 ft rod"; added 15 Nov 2026), and since 17 Nov 2026 also
// "bag"/"bags" for cement and "roll"/"rolls" for binding wire.
const PIECE=p=>/\brod$/.test(p.unit);
const BAG=p=>/\bbag$/.test(p.unit),ROLL=p=>/\broll$/.test(p.unit);
const unitWord=(p,n)=>TON(p)?(n===1?"ton":"tons"):PIECE(p)?(n===1?"pc":"pcs"):BAG(p)?(n===1?"bag":"bags"):ROLL(p)?(n===1?"roll":"rolls"):"";
const QW=v=>v.length>5?"l":v.length>3?"m":"s";
const ctrl=p=>{const n=qty[p.id]||0,t=TON(p),one=t?"half a ton of":"one";return n
?`<div class="qty"><div class="step"><button data-dec="${p.id}" aria-label="Remove ${one} ${p.name}">−</button><input type="text" autocomplete="off" inputmode="${t?"decimal":"numeric"}" value="${fmtQ(n)}" data-w="${QW(fmtQ(n))}" data-qty="${p.id}" aria-label="Quantity of ${p.name}${t?" in tons":PIECE(p)?" in pieces":BAG(p)?" in bags":ROLL(p)?" in rolls":""}"><button data-inc="${p.id}" aria-label="Add ${one} ${p.name}">+</button></div>${unitWord(p,n)?`<span class="u">${unitWord(p,n)}</span>`:""}</div>`
:`<button class="add" data-inc="${p.id}" aria-label="Add ${p.name} to estimate">Add</button>`};


// ---- Price list: category tabs, swipeable slides and search -----------------
// Category tiles (17 Nov 2026): a number, the material in bold and how it
// is sold, so both kinds of iron rods stand out. Phones: a 2 x 2 grid, all
// four visible at once; computers: one row. Must match tabsHTML() in
// src/lib/catalog-html.ts.
const TAB_LABEL={"Cement":["Cement","Bags"],"Iron Rods (Single Piece)":["Iron rods","Single pieces"],"Iron Rods (Per Ton)":["Iron rods","Per ton"],"Binding Wire":["Binding wire","Rolls"]};
const tabHTML=(c,i,on)=>{const[l,s]=TAB_LABEL[c]||[c,""];return `<button data-cat="${c}" aria-pressed="${on}"><span class="tno">${String(i+1).padStart(2,"0")}</span><b>${l}</b>${s?`<small>${s}</small>`:""}</button>`;};
function renderTabs(){
$("#tabs").innerHTML=cats.map((c,i)=>tabHTML(c,i,c===cat)).join("");
}
// ---- Product photos, rod size tags and tab banners (Phase 3: carried over
// from the live index.html, product-images and responsive-thumbnails work) ----
// Products with an "img" get a square thumbnail in front of the name. Each
// photo exists in several sizes: "supacem-32-5-120.webp" is the 120 px copy
// of "supacem-32-5.webp" (the 360 px file, kept as the fallback). The browser
// picks the smallest copy that is still sharp on the visitor's screen: e.g. a
// PC at 125% scaling shows 96 px x 1.25 = 120 screen pixels and takes the
// 120 px copy; a phone at 3x shows 80 px x 3 = 240 and takes 240. Loaded
// straight away (not "lazy"): the cement photos are on screen when the page
// opens, and the files are small. Shown 96 px on computers and tablets, 80 px
// on phones: keep THUMB_SIZES in step with the .thumb sizes in site.css.
const THUMB_WIDTHS=[80,96,120,160,192,240,288];
const THUMB_SIZES="(max-width:560px) 80px, 96px";
const thumbSrcset=src=>THUMB_WIDTHS.map(w=>`${src.replace(/\.webp$/,`-${w}.webp`)} ${w}w`).concat(`${src} 360w`).join(", ");
const thumb=p=>p.img?`<img class="thumb" src="${p.img}" srcset="${thumbSrcset(p.img)}" sizes="${THUMB_SIZES}" alt="${p.alt||""}" width="96" height="96">`:"";
// Rods: the size ("16 mm") becomes a bold tag. The text still reads
// "Iron rod 16 mm" in that order; CSS only moves the tag to the front, so the
// estimate, PDF, WhatsApp message and tests are unchanged.
const label=p=>p.size&&p.name.endsWith(p.size)?`<span class="rn">${p.name.slice(0,-p.size.length)}<b class="sz">${p.size}</b></span>`:p.name;
// Wide photo and "how it's sold" note for a whole tab, from
// src/data/categories.json. Both rod tabs point at the SAME banner object
// (ROD_PHOTO), so the photo is downloaded once. ROD_PHOTO is a global on
// purpose: a test points it at a missing file to check the fallback.
const BANNERS=TCP.banners||{};
const ROD_PHOTO=BANNERS.rods;
const CAT_INFO={};
for(const [c,info] of Object.entries(TCP.categoryInfo||{}))CAT_INFO[c]={note:info.note,banner:info.banner?BANNERS[info.banner]:undefined};
// Width the banner is shown at: the price list column on large screens,
// the screen width minus the side margins on phones.
const BANNER_SIZES="(min-width:1100px) 652px, (min-width:900px) calc(100vw - 448px), calc(100vw - 32px)";
// "shared": the whole tab has one price (today: rods by the ton, all
// GH₵7,000), shown once under the heading. The row keeps its price for
// screen readers and search engines, but hidden from view (class "vh"). If prices ever differ, each row shows its own price again.
// Class "in": the product is in the estimate (shown with an ochre edge and
// "In your estimate"; added 17 Nov 2026).
// Price and Add/stepper sit together in "buy" (17 Nov 2026): on phones the
// stepper moves under the price when the two do not fit side by side (large
// text settings), instead of running into it. Elsewhere "buy" has no box.
const rowHTML=(p,shared)=>`<div class="row${p.img?" has-img":""}${shared?" one":""}${qty[p.id]?" in":""}">${thumb(p)}<div class="nm">${label(p)}<small>per ${p.unit}</small></div><div class="buy"><div class="pr">${shared?`<span class="vh">${money(p.price)}</span>`:money(p.price)}</div>${ctrl(p)}</div></div>`;
const sharedPrice=l=>l.length>1&&l.every(p=>p.price===l[0].price&&p.unit===l[0].unit)?l[0]:null;
// One category section. "browse" is true for the swipeable tabs and false for
// search results; banner photos are only shown when browsing. If the banner
// fails to load, the section gets class "nobanner" and the photo is hidden;
// the heading always stays. Loaded with the page at low priority, so it is
// usually ready before the customer opens a rod tab.
// Category arrows (18 Nov 2026): while browsing, each category heading has
// ‹ › buttons that move to the previous / next category (the same as tapping
// a tile). The first category's ‹ and the last one's › are disabled.
// Swiping by finger or trackpad still works. Mirrored in catalog-html.ts.
const ARR_L=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ARR_R=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const catName=c=>{const[l,s]=TAB_LABEL[c]||[c,""];return s?`${l}, ${s.toLowerCase()}`:l;};
const navHTML=g=>{const i=cats.indexOf(g),a=cats[i-1],z=cats[i+1];return `<span class="snav">`
+(a?`<button type="button" class="sgo" data-go="${a}" aria-label="Previous category: ${catName(a)}">${ARR_L}</button>`:`<button type="button" class="sgo" disabled aria-label="Previous category">${ARR_L}</button>`)
+(z?`<button type="button" class="sgo" data-go="${z}" aria-label="Next category: ${catName(z)}">${ARR_R}</button>`:`<button type="button" class="sgo" disabled aria-label="Next category">${ARR_R}</button>`)
+`</span>`;};
const sec=(g,l,browse)=>{const subs=[...new Set(l.map(p=>p.sub||""))],info=CAT_INFO[g]||{},b=browse&&info.banner,one=browse&&sharedPrice(l);
return `<section>`
+(b?`<img class="banner" src="${b.src}" srcset="${b.srcset}" sizes="${BANNER_SIZES}" alt="" width="${b.w}" height="${b.h}" fetchpriority="low" onerror="this.closest('section').classList.add('nobanner')">`:"")
+`<h3>${ICON[g]||""}${g}${browse?navHTML(g):""}</h3>`+(info.note?`<p class="cat-note">${info.note}</p>`:"")
+(one?`<p class="cat-price"><b>${money(one.price)}</b> per ${one.unit}, all sizes</p>`:"")
+`${subs.map(x=>(x?`<h4>${x}</h4>`:"")+l.filter(p=>(p.sub||"")===x).map(p=>rowHTML(p,!!one)).join("")).join("")}</section>`;};
function fit(){const L=$("#list");if(q||!L.children.length)return;const s=L.children[cats.indexOf(cat)];if(s)L.style.height=s.offsetHeight+"px";}
// Re-measure the visible tab when a picture finishes loading or fails, so the
// price list is never cut short or left with a gap.
$("#list").addEventListener("load",()=>setTimeout(fit),true);
$("#list").addEventListener("error",()=>setTimeout(fit),true);
function renderList(){
const L=$("#list");
if(q){
const M=P.filter(p=>{const h=norm(p.name+" "+p.cat+" "+p.unit+" "+(p.sub||"")+(p.name.startsWith("Iron rod")?" iron rods":"")+(p.unit==="ton"?" tonne":""));return q.split(/\s+/).every(t=>h.includes(norm(t)));});
L.className="flat";L.style.height="";
L.innerHTML=M.length?[...new Set(M.map(p=>p.cat))].map(g=>sec(g,M.filter(p=>p.cat===g))).join(""):`<p class="mute">No products match. Try a shorter search.</p>`;
return;
}
L.className="snap";
L.innerHTML=cats.map(g=>`<div class="slide">${sec(g,P.filter(p=>p.cat===g),true)}</div>`).join("");
L.scrollLeft=cats.indexOf(cat)*L.clientWidth;
fit();
}
const norm=s=>s.toLowerCase().replace(/[^a-z0-9.]/g,"");
if(document.fonts)document.fonts.ready.then(fit);
let lock=false,lt;
function goCat(c,instant){
cat=c;renderTabs();
if(q){q="";$("#q").value="";renderList();return;}
const L=$("#list");
lock=true;clearTimeout(lt);lt=setTimeout(()=>{lock=false},instant?50:500);
L.scrollTo({left:cats.indexOf(c)*L.clientWidth,behavior:instant||RM?"auto":"smooth"});
fit();
}

document.addEventListener("click",e=>{const b=e.target.closest(".sgo[data-go]");if(b)goCat(b.dataset.go);});

// ---- The estimate panel and the WhatsApp message -----------------------------
// Rebuilt after every change. Totals: materials = sum of price × quantity;
// tax is TAX_RATE (0 today); delivery is always quoted separately.
//
// Sections (17 Nov 2026). Every product belongs to one part of the estimate:
//   cem   Cement                      (counted in bags)
//   pc    Iron rods, single pieces    (counted in rods)
//   ton   Iron rods, by the ton       (counted in tons)
//   wire  Binding wire                (counted in rolls)
// Single rods and rods by the ton are never added together. A product in a
// category added later (none today) goes into its own section at the end.
const PART=p=>p.cat==="Cement"?"cem":TON(p)?"ton":PIECE(p)?"pc":p.cat==="Binding Wire"?"wire":"x:"+p.cat;
const SECTIONS=[{k:"cem",name:"Cement",parts:["cem"]},{k:"rod",name:"Iron rods",parts:["pc","ton"]},{k:"wire",name:"Binding wire",parts:["wire"]}];
const PART_NAME={cem:"Cement",pc:"Iron rods, single pieces",ton:"Iron rods, by the ton",wire:"Binding wire"};
const PART_SHORT={pc:"Single pieces",ton:"By the ton"};
// How a part's quantity is written: "205 bags", "85 rods", "5.5 tons", "6 rolls".
const COUNT={cem:["bag","bags"],pc:["rod","rods"],ton:["ton","tons"],wire:["roll","rolls"]};
const howMany=(k,n)=>COUNT[k]?`${fmtQ(n)} ${COUNT[k][n===1?0:1]}`:fmtQ(n);
// Groups the products in the estimate: [{k, name, parts:[{k, rows, n, sum}], n, sum}]
function sections(rows){
const extra=[...new Set(rows.map(PART).filter(k=>k.startsWith("x:")))].map(k=>({k,name:k.slice(2),parts:[k]}));
return SECTIONS.concat(extra).map(S=>{
const parts=S.parts.map(k=>{const r=rows.filter(p=>PART(p)===k);return{k,rows:r,n:r.reduce((s,p)=>s+qty[p.id],0),sum:r.reduce((s,p)=>s+p.price*qty[p.id],0)}}).filter(x=>x.rows.length);
return{...S,parts,sum:parts.reduce((s,x)=>s+x.sum,0)};}).filter(S=>S.parts.length);
}
// Sections the customer has folded away (they stay folded while editing).
const SHUT={};
const CHEV=`<svg class="chev" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 6l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2"/></svg>`;
// Each product in the estimate: its name in a small quiet box (what the
// customer is buying), the unit price under it, then quantity and line total.
// Numbers (18 Nov 2026): every product in the estimate is numbered 1, 2,
// 3... in the order shown, straight across categories; the same numbers as
// the WhatsApp message and the PDF. LN is reset before each render.
let LN=0;
const lineHTML=p=>`<div class="ln"><div class="nm"><span class="lno">${++LN}</span><span class="pn">${p.name}</span><small>${money(p.price)} per ${p.unit}</small></div>${ctrl(p)}<div class="amt">${money(p.price*qty[p.id])}</div></div>`;
function renderEst(){
const rows=P.filter(p=>qty[p.id]>0);
const sub=rows.reduce((s,p)=>s+p.price*qty[p.id],0);
const tax=sub*TAX_RATE,total=sub+tax;
if(rows.length&&undoSnap){undoSnap=null;clearTimeout(undoT);}
const S=sections(rows);
// "Your order at a glance": one tile per part, quantities only.
$("#glance").innerHTML=rows.length?`<h3>Your order at a glance</h3><div class="tiles">`+S.flatMap(x=>x.parts).map(x=>`<div><b>${fmtQ(x.n)}</b> ${{cem:x.n===1?"bag of cement":"bags of cement",pc:x.n===1?"individual rod":"individual rods",ton:x.n===1?"ton of rods":"tons of rods",wire:x.n===1?"roll of binding wire":"rolls of binding wire"}[x.k]||PART_NAME[x.k]||x.k.slice(2)}</div>`).join("")+`</div>`:"";
$("#start").hidden=rows.length>0||!!undoSnap;
$("#etools").hidden=!rows.length;
if(!rows.length){$("#clearAsk").hidden=true;}
LN=0;
$("#lines").innerHTML=rows.length?S.map((x,i)=>`<section class="es${SHUT[x.k]?" shut":""}" data-g="${x.k}"><button type="button" class="esh" data-sec="${x.k}" aria-expanded="${!SHUT[x.k]}">${CHEV}<span class="enm"><b>${x.name}</b><span>${x.parts.map(y=>howMany(y.k,y.n)).join(" · ")}</span></span><span class="esx">${money(x.sum)}</span></button><div class="esb">`
+x.parts.map(y=>(x.parts.length>1||PART_SHORT[y.k]&&x.k==="rod"?`<h4 class="esub">${PART_SHORT[y.k]||PART_NAME[y.k]}<span>${howMany(y.k,y.n)}</span></h4>`:"")+y.rows.map(lineHTML).join("")+(x.k==="rod"&&x.parts.length>1?`<div class="est"><span>${PART_SHORT[y.k]} subtotal</span><b>${money(y.sum)}</b></div>`:"")).join("")
+`<div class="est all"><span>${x.name} subtotal</span><b>${money(x.sum)}</b></div></div></section>`).join(""):(undoSnap?`<p class="mute empty" role="status">Estimate cleared. <button class="ghost undo" id="undo">Undo</button></p>`:`<p class="mute empty">Your estimate is empty. Add materials from the price list.</p>`);
$("#tot").innerHTML=(TAX_RATE?`<div><span>Materials</span><span>${money(sub)}</span></div><div><span>Tax (${+(TAX_RATE*100).toFixed(2)}%)</span><span>${money(tax)}</span></div>`:"")+`<div class="tdl"><span>Delivery</span><span class="tbc">To be confirmed</span></div><div class="gt${total>=1e6?" lg":""}"><span>Total (excl. delivery)</span><span>${money(total)}</span></div>`;
$("#bar").classList.toggle("on",rows.length>0);
$("#barTxt").innerHTML=`<small>${rows.length} ${rows.length===1?"item":"items"}<span class="bl"> in your estimate</span></small>${money(total)}`;
const loc=$("#loc").value.trim();
// Phase 2.2: the customer's optional note for TCP, one line in WhatsApp.
const note=$("#enote").value.trim().replace(/\s+/g," ");
// WhatsApp message (18 Nov 2026): the opening asks the question once; the
// full itemised list, reference, date and total follow unchanged.
const msg=`Hello The Cement People,\n\nI'd like to enquire about the following estimate. Please confirm product availability and delivery cost.\n\n*Estimate ${REF}* (${DATE})\n`
+(loc||note?"\n"+(loc?`*Drop-off location:* ${loc}\n`:"")+(note?`*Note:* ${note}\n`:""):"")
+"\n*Items*\n"+rows.map((p,i)=>`${i+1}. ${p.name} (${p.unit})\n   ${fmtQ(qty[p.id])} × ${money(p.price)} = ${money(p.price*qty[p.id])}`).join("\n")
+`\n\n*Materials total: ${money(sub)}*`
+(TAX_RATE?`\nTax (${+(TAX_RATE*100).toFixed(2)}%): ${money(tax)}\nTotal (excl. delivery): ${money(total)}`:"");
renderQuote(S,sub,tax,total,loc,note);
const sd=$("#send");
if(rows.length){sd.href="https://wa.me/"+WA_NUMBER+"?text="+encodeURIComponent(msg);sd.classList.remove("off");sd.removeAttribute("aria-disabled")}
else{sd.removeAttribute("href");sd.classList.add("off");sd.setAttribute("aria-disabled","true")}
}
// Folding a section away, and opening it again.
document.addEventListener("click",e=>{const b=e.target.closest("[data-sec]");if(!b)return;const k=b.dataset.sec;SHUT[k]=!SHUT[k];b.closest(".es").classList.toggle("shut",SHUT[k]);b.setAttribute("aria-expanded",!SHUT[k]);});

// ---- The printable A4 quotation ---------------------------------------------
// Fills the hidden <section id="quote">. print.css hides everything else when
// printing. esc() makes the customer's typed location safe to display.
// Refinements (17 Nov 2026): the quantity carries the same unit word as
// beside the quantity box on screen ("120 bags", "24 pcs", "2.5 tons"); the contact details are one per line; "Materials" only shows
// when there is tax (otherwise it repeats the total); section rows and
// subtotals stay on the same page as their items (print.css).
// Brand identity V1.1 (17 Nov 2026): the horizontal logo (copied from the
// #q-logo drawing in QuotePieces.astro), the same sections as the estimate
// with quantities and subtotals, and "Total (excl. delivery)". Each row
// gives the unit beside the name ("per 50 kg bag"; the section already says
// what kind of material it is); the Qty column is the number only, so the
// quantity reads the same on screen, in WhatsApp and here.
// The logo's drawing is copied once from the hidden #q-logo in QuotePieces.astro.
const LOGO=(document.getElementById("q-logo")||{}).innerHTML||"";
const esc=s=>s.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function renderQuote(S,sub,tax,total,loc,note){
let n=0;
// PDF (19 Nov 2026): category headings carry no "01 ·" numbers (products are
// numbered 1, 2, 3... instead, as on screen); an empty drop-off location
// reads "To be agreed".
// Product rows are marked data-row="item" so the print styles can find them
// directly (a data attribute, not a class, so rows stay class-free).
const body=S.length?S.map((x,i)=>`<tr class="q-sec"><td colspan="5">${x.name}<span>${x.parts.map(y=>howMany(y.k,y.n)).join(" · ")}</span></td></tr>`
+x.parts.map(y=>(x.k==="rod"?`<tr class="q-sub"><td colspan="5">${PART_SHORT[y.k]}</td></tr>`:"")
+y.rows.map(p=>`<tr data-row="item"><td class="n">${++n}</td><td>${p.name} <small>per ${p.unit}</small></td><td class="r">${fmtQ(qty[p.id])} ${unitWord(p,qty[p.id])}</td><td class="r">${money(p.price)}</td><td class="r">${money(p.price*qty[p.id])}</td></tr>`).join("")
+(x.k==="rod"&&x.parts.length>1?`<tr class="q-st"><td></td><td colspan="3">${PART_NAME[y.k]} subtotal</td><td class="r">${money(y.sum)}</td></tr>`:"")).join("")
+`<tr class="q-st all"><td></td><td colspan="3">${x.name} subtotal</td><td class="r">${money(x.sum)}</td></tr>`).join(""):`<tr class="q-empty"><td colspan="5">No items added yet.</td></tr>`;
$("#quote").innerHTML=`<header class="q-head"><svg class="q-logo" viewBox="0 0 592.329 100" role="img" aria-label="The Cement People">${LOGO}</svg>`
+`<div class="q-doc"><h1>Estimate</h1><dl><dt>Reference</dt><dd>${REF}</dd><dt>Date</dt><dd>${DATE}</dd></dl></div></header>`
+`<div class="q-to"><div><small>Drop-off location</small><p>${loc?esc(loc):"To be agreed"}</p></div><div><small>Delivery</small><p>To be confirmed after you send this estimate</p></div><div><small>Contact</small><p>${TCP.business.phone} (call or WhatsApp)<br>${TCP.business.website}<br>${TCP.business.town}</p></div></div>`
+(note?`<div class="q-note"><small>Your note</small><p>${esc(note)}</p></div>`:"")
+`<table><thead><tr><th class="n">#</th><th>Description</th><th class="r">Qty</th><th class="r">Unit price</th><th class="r">Amount</th></tr></thead><tbody>${body}</tbody></table>`
+`<div class="q-close"><div class="q-terms"><h2>Delivery and terms</h2><ul>`
+`<li>We deliver to your drop-off location. The delivery cost depends on your order and location, and is agreed with you before delivery.</li>`
+`<li>This estimate is indicative. Final prices and availability are confirmed when you order.</li>`
+`<li>All prices are in Ghana cedis (GH₵).</li></ul>`
+`<h2>To order</h2><p>WhatsApp or call ${TCP.business.phone} and quote reference <b>${REF}</b>.</p></div>`
+`<div class="q-sum">`+(TAX_RATE?`<div class="q-mat"><span>Materials</span><span>${money(sub)}</span></div>`:"")
+(TAX_RATE?`<div><span>Tax (${+(TAX_RATE*100).toFixed(2)}%)</span><span>${money(tax)}</span></div>`:"")
+`<div class="q-del"><span>Delivery</span><span>To be confirmed</span></div>`
+`<div class="gt"><span>Total (excl. delivery)</span><span>${money(total)}</span></div></div></div>`;
// Compact running header on continuation pages only (page 2 onwards)
let ps=document.getElementById("qpage");
if(!ps){ps=document.createElement("style");ps.id="qpage";document.head.appendChild(ps);}
ps.textContent=`@page{@top-left{content:"The Cement People  ·  Estimate ${REF}";font:700 7.5pt Montserrat,Arial,sans-serif;color:#131514;vertical-align:bottom;padding-bottom:2mm}@top-right{content:"Continued";font:7.5pt Montserrat,Arial,sans-serif;color:#5a5a5a;vertical-align:bottom;padding-bottom:2mm}}@page:first{@top-left{content:none}@top-right{content:none}}`;
}

// Refresh the quotation just before printing, and name the PDF after the reference.
// The page's own title, put back after printing (the PDF is named after the reference).
const PAGE_TITLE=document.title;
addEventListener("beforeprint",()=>{renderEst();document.title=`The Cement People Estimate ${REF}`;});
addEventListener("afterprint",()=>{document.title=PAGE_TITLE;});

// ---- Changing a quantity: every Add, +, − and typed number goes through set() --
// Looked up each time (not once at start), so products added later are found too.
const byId=id=>P.find(p=>p.id===id);
function set(id,n){
// Whole items: cut to a whole number, as before. Half tons: round to the
// nearest half; a typed amount above zero never rounds down to nothing.
const s=STEP(byId(id));n=Number.isFinite(n)?n:0;
n=s===1?Math.trunc(n):Math.round(n/s)*s;if(s!==1&&n<=0&&arguments[2])n=s;
n=Math.max(0,Math.min(MAX_QTY,n));
if(n)qty[id]=n;else delete qty[id];
renderList();renderEst();
}


// ---- Buttons and inputs ------------------------------------------------------
document.addEventListener("click",e=>{
const b=e.target.closest("button");if(!b)return;
const d=b.dataset;
if(d.inc)set(d.inc,qty[d.inc]?qty[d.inc]+STEP(byId(d.inc)):1);
else if(d.dec)set(d.dec,(qty[d.dec]||0)-STEP(byId(d.dec)));
else if(d.cat!==undefined)goCat(d.cat);
});
// While a quantity box is being edited it shows plain digits ("50000"),
// so deleting or adding a digit can never leave a misplaced comma; leaving
// the box shows it formatted again ("50,000").
// The whole number is selected, so typing replaces it (as before).
document.addEventListener("focusin",e=>{const i=e.target;if(i.dataset&&i.dataset.qty){const raw=String(qty[i.dataset.qty]||0);if(i.value!==raw){i.value=raw;i.select();}}});
document.addEventListener("focusout",e=>{const i=e.target;if(i.dataset&&i.dataset.qty&&i.isConnected&&parseQ(i.value)===(qty[i.dataset.qty]||0))i.value=fmtQ(qty[i.dataset.qty]||0);});
document.addEventListener("change",e=>{
const i=e.target;if(i.dataset&&i.dataset.qty){const v=parseQ(i.value);set(i.dataset.qty,v||0,v>0);}
});
$("#q").addEventListener("input",e=>{q=e.target.value.trim().toLowerCase();renderList();});
$("#print").addEventListener("click",()=>window.print());
// "Clear estimate" empties the estimate and starts a new reference, but for
// 10 seconds an "Undo" button brings everything back: items, drop-off
// location, reference and date (added 14 Nov 2026). Adding anything, or the
// 10 seconds running out, removes the Undo.
// Since 17 Nov 2026 it asks first ("Remove everything from this estimate?"
// with "Keep estimate" and "Clear all"); "Clear all" does the clearing.
let undoSnap=null,undoT;
function dropUndo(){if(!undoSnap)return;undoSnap=null;clearTimeout(undoT);renderEst();}
function askClear(on){$("#clearAsk").hidden=!on;$("#clear").setAttribute("aria-expanded",on);if(on)$("#clearNo").focus();}
$("#clear").addEventListener("click",()=>{
if(!Object.keys(qty).length){dropUndo();newQuote();renderList();renderEst();return;} // nothing to clear: just a fresh reference, as before
askClear($("#clearAsk").hidden);
});
$("#clearNo").addEventListener("click",()=>{askClear(false);$("#clear").focus();});
$("#clearYes").addEventListener("click",()=>{
askClear(false);
undoSnap={qty:{...qty},loc:$("#loc").value,note:$("#enote").value,REF,DATE};
qty={};newQuote();renderList();renderEst();
clearTimeout(undoT);undoT=setTimeout(dropUndo,10000);
const u=$("#undo");if(u)u.focus();
});
document.addEventListener("click",e=>{if(!e.target.closest("#undo")||!undoSnap)return;
const u=undoSnap;undoSnap=null;clearTimeout(undoT);
qty=u.qty;$("#loc").value=u.loc;$("#enote").value=u.note||"";REF=u.REF;DATE=u.DATE;$("#ref").textContent="Ref "+REF;$("#date").textContent=DATE;
renderList();renderEst();$("#clear").focus();});

// ---- Phones: the estimate opens as a full-screen view -------------------------
// Opened from the bar at the bottom of the screen, or from "View full
// estimate" in the estimate's heading (17 Nov 2026). Only the materials
// (#escroll) scroll; the heading and the bottom stay put.
const mq=matchMedia("(max-width:899px)");
function openEst(){const e=$("#est");e.classList.add("open");$("#escroll").scrollTop=0;document.body.style.overflow="hidden";$("#dclose").focus({preventScroll:true});}
function closeEst(){$("#est").classList.remove("open");document.body.style.overflow="";}
$("#barBtn").addEventListener("click",openEst);
// Phones: hide the bar while the estimate panel is on screen, so it never
// covers the panel's last lines (the panel counts as on screen once its top
// is 120 px above the bottom of the screen).
if("IntersectionObserver"in window)new IntersectionObserver(es=>{$("#bar").classList.toggle("away",es[0].isIntersecting)},{rootMargin:"0px 0px -120px 0px"}).observe($("#est"));
$("#dclose").addEventListener("click",closeEst);
document.addEventListener("click",e=>{if(mq.matches&&e.target.closest('a[href="#est"]')){e.preventDefault();openEst();}});
// Computers: "View full estimate" shows the estimate large, in the middle of
// the screen; "Back to the price list", the dimmed background or Escape
// closes it. Phones: it opens the full-screen view above.
function fullEst(on){const e=$("#est"),b=$("#full");e.classList.toggle("full",on);$("#escrim").hidden=!on;document.body.style.overflow=on?"hidden":"";
b.querySelector("span").textContent=on?"Back to the price list":"View full estimate";b.setAttribute("aria-expanded",on);if(on)$("#escroll").scrollTop=0;}
$("#full").addEventListener("click",()=>{if(mq.matches)openEst();else fullEst(!$("#est").classList.contains("full"));});
$("#escrim").addEventListener("click",()=>fullEst(false));
$("#fullX").addEventListener("click",()=>{fullEst(false);$("#full").focus();});
document.addEventListener("keydown",e=>{if(e.key!=="Escape")return;if($("#est").classList.contains("full")){fullEst(false);$("#full").focus();}else if(!$("#clearAsk").hidden){askClear(false);$("#clear").focus();}});
mq.addEventListener("change",()=>{if(!mq.matches)closeEst();else fullEst(false);});

// ---- Enquire menus ------------------------------------------------------------
// Each "Enquire" button (Enquire.astro) opens a small menu with two choices:
// WhatsApp or a call. Computers: it drops down under the button. Phones: it
// slides up from the bottom of the screen over a dimmed page. Tapping
// outside, Escape or choosing an option closes it.
const enqScrim=document.createElement("div");enqScrim.className="enq-scrim";enqScrim.hidden=true;document.body.appendChild(enqScrim);
let enqOpen=null;
function enqClose(focus){if(!enqOpen)return;const b=enqOpen;enqOpen=null;b.setAttribute("aria-expanded","false");$("#"+b.getAttribute("aria-controls")).hidden=true;enqScrim.hidden=true;if(focus)b.focus();}
document.addEventListener("click",e=>{
const b=e.target.closest(".enq-btn");
if(b){const was=enqOpen===b;enqClose();if(was)return;const m=$("#"+b.getAttribute("aria-controls"));m.hidden=false;b.setAttribute("aria-expanded","true");enqOpen=b;enqScrim.hidden=!matchMedia("(max-width:599px)").matches;const a=m.querySelector("a");if(a)a.focus({preventScroll:true});return;}
if(enqOpen&&(!e.target.closest(".enq-menu")||e.target.closest("a")))enqClose();
});
document.addEventListener("keydown",e=>{if(e.key==="Escape")enqClose(true);});
addEventListener("resize",()=>enqClose());

// Each quotation gets its own reference: TCP-YYMMDD-XXXXXX (date plus 6 random characters).
// It stays the same for that quotation across the screen, PDF and WhatsApp, and a new one
// is issued when the customer clears the estimate to start another quotation.

// ---- Quotation reference and date ---------------------------------------------
let REF,DATE;
function newQuote(){
const d=new Date(),A="23456789ABCDEFGHJKLMNPQRSTUVWXYZ",r=new Uint8Array(6);crypto.getRandomValues(r);
REF="TCP-"+String(d.getFullYear()).slice(2)+String(d.getMonth()+1).padStart(2,"0")+String(d.getDate()).padStart(2,"0")+"-"+[...r].map(n=>A[n%32]).join("");
DATE=d.toLocaleDateString(undefined,{year:"numeric",month:"long",day:"numeric"});
$("#ref").textContent="Ref "+REF;
$("#date").textContent=DATE;
}
newQuote();

// ---------------------------------------------------------------------------
// DATA HOOK-UP 2 of 2: business details
// WhatsApp number, phone and town come from src/config/business.ts via the
// data block (also used in the quotation header and "To order" line above).
// ---------------------------------------------------------------------------
// Quantity boxes in the estimate on phones size to their number: s (up
// to 3 characters, "2", "120"), m (4-5, "9,999") or l (6+, "50,000"), so
// no digit is ever hidden and short numbers leave room for the line total.
// Updated while typing too.
document.addEventListener("input",e=>{if(e.target.matches(".step input"))e.target.dataset.w=QW(e.target.value)});
const WA_NUMBER=TCP.business.whatsapp;
$("#loc").addEventListener("input",renderEst);
$("#enote").addEventListener("input",renderEst);
document.querySelectorAll("[data-wa]").forEach(a=>{if(WA_NUMBER)a.href="https://wa.me/"+WA_NUMBER+"?text="+encodeURIComponent("Hello, I would like to enquire about your materials.")});

// ---- Category tiles under the hero: removed in the design-system phase
// (Nov 2026). The tabs above the price list do the same job, and without the
// tiles the first prices appear sooner. goCat() is still used by the tabs.

// ---- Dark mode button ------------------------------------------------------------
// The moon/sun button in the header (17 Nov 2026). Base.astro follows the
// device's own light/dark setting unless a choice is saved (window.tcpTheme);
// this button switches and remembers the choice on this device.
const themeBtn=$("#theme");
function showTheme(){if(!themeBtn)return;const dark=document.documentElement.dataset.theme==="dark";themeBtn.setAttribute("aria-pressed",dark);themeBtn.title=dark?"Switch to light mode":"Switch to dark mode";}
if(themeBtn&&window.tcpTheme){themeBtn.addEventListener("click",()=>{tcpTheme.set(tcpTheme.get()==="dark"?"light":"dark");showTheme();});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change",showTheme);showTheme();}

// ---- Mobile menu ---------------------------------------------------------------
// Since 17 Nov 2026 the open menu dims and covers the page behind it (a
// backdrop, like the Enquire sheet); tapping the backdrop, choosing a link,
// Escape or ☰ again closes it. "Dark mode" keeps the menu open.
const navScrim=document.createElement("div");navScrim.className="nav-scrim";navScrim.hidden=true;document.body.appendChild(navScrim);
function menu(open){$("#nav").classList.toggle("open",open);$("#menu").setAttribute("aria-expanded",open);navScrim.hidden=!open;}
$("#menu").addEventListener("click",()=>menu(!$("#nav").classList.contains("open")));
$("#nav").addEventListener("click",e=>{if(e.target.closest("a"))menu(false)});
navScrim.addEventListener("click",()=>menu(false));
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&$("#nav").classList.contains("open")){menu(false);$("#menu").focus();}});
mq.addEventListener("change",()=>{if(!matchMedia("(max-width:819px)").matches)menu(false);});

// ---- Swiping between category slides keeps the tabs in step --------------------
const RM=matchMedia("(prefers-reduced-motion: reduce)").matches;
const Ls=$("#list");
Ls.addEventListener("scroll",()=>{
if(q||lock)return;
const i=Math.round(Ls.scrollLeft/Ls.clientWidth);
if(cats[i]&&cats[i]!==cat){cat=cats[i];renderTabs();fit();}
},{passive:true});
addEventListener("resize",()=>{if(!q){Ls.scrollLeft=cats.indexOf(cat)*Ls.clientWidth;fit();}});

// ---- Start: draw everything once the page has loaded ------------------------
renderTabs();renderList();renderEst();
