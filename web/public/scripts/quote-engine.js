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
   =========================================================================== */
// ---------------------------------------------------------------------------
// DATA HOOK-UP 1 of 2: products, currency and tax rate
// Previously typed straight into this file. Now the page carries them in a
// <script type="application/json" id="tcp-data"> block, built by Astro from
// src/data/products.json and src/config/business.ts. "P" stays a plain
// global variable, exactly as before (the regression tests rely on that).
// Each product: {id, cat, sub (optional subgroup), name, unit, price}.
// ---------------------------------------------------------------------------
const TCP=JSON.parse(document.getElementById("tcp-data").textContent);
const CURRENCY=TCP.currency,TAX_RATE=TCP.taxRate;
const P=TCP.products;

// ---- Shared state and small helpers ----------------------------------------
// cats  the category names, in the order they first appear in the products
// cat   the category tab currently showing; q the search text; qty {id: count}
// $     shorthand for document.querySelector; money() formats GH₵1,392.00
const cats=[...new Set(P.map(p=>p.cat))];
const ICON={"Cement":`<svg viewBox="0 0 28 28" aria-hidden="true"><path d="M6 5h16l3 5v14H3V10z" fill="currentColor"/><rect x="8" y="12" width="12" height="8" fill="#f2c300"/></svg>`,"Iron rods and wire":`<svg viewBox="0 0 28 28" aria-hidden="true"><rect x="2" y="5" width="24" height="4" rx="2" fill="currentColor"/><rect x="2" y="12" width="24" height="4" rx="2" fill="currentColor"/><rect x="2" y="19" width="24" height="4" rx="2" fill="currentColor"/><rect x="11" y="3" width="5" height="22" fill="#f2c300"/></svg>`};
ICON["Iron Rods (Single Piece)"]=ICON["Iron Rods (Per Ton)"]=ICON["Iron rods and wire"];
let cat=cats[0],q="",qty={};
const $=s=>document.querySelector(s);
const money=n=>CURRENCY+n.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});


// ---- Quantity controls ------------------------------------------------------
// A product not yet in the estimate shows an "Add" button; once added it shows
// a − / number / + stepper. Clicks are handled further down by data-inc/data-dec.
const ctrl=p=>{const n=qty[p.id]||0;return n
?`<div class="step"><button data-dec="${p.id}" aria-label="Remove one ${p.name}">−</button><input type="number" min="0" inputmode="numeric" value="${n}" data-qty="${p.id}" aria-label="Quantity of ${p.name}"><button data-inc="${p.id}" aria-label="Add one ${p.name}">+</button></div>`
:`<button class="add" data-inc="${p.id}" aria-label="Add ${p.name} to estimate">Add</button>`};


// ---- Price list: category tabs, swipeable slides and search -----------------
function renderTabs(){
$("#tabs").innerHTML=cats.map(c=>`<button data-cat="${c}" aria-pressed="${c===cat}">${c}</button>`).join("");
}
const rowHTML=p=>`<div class="row"><div class="nm">${p.name}<small>per ${p.unit}</small></div><div class="pr">${money(p.price)}</div>${ctrl(p)}</div>`;
const sec=(g,l)=>{const subs=[...new Set(l.map(p=>p.sub||""))];return `<section><h3>${ICON[g]||""}${g}</h3>${subs.map(x=>(x?`<h4>${x}</h4>`:"")+l.filter(p=>(p.sub||"")===x).map(rowHTML).join("")).join("")}</section>`;};
function fit(){const L=$("#list");if(q||!L.children.length)return;const s=L.children[cats.indexOf(cat)];if(s)L.style.height=s.offsetHeight+"px";}
function renderList(){
const L=$("#list");
if(q){
const M=P.filter(p=>{const h=norm(p.name+" "+p.cat+" "+p.unit+" "+(p.sub||"")+(p.name.startsWith("Iron rod")?" iron rods":"")+(p.unit==="ton"?" tonne":""));return q.split(/\s+/).every(t=>h.includes(norm(t)));});
L.className="flat";L.style.height="";
L.innerHTML=M.length?[...new Set(M.map(p=>p.cat))].map(g=>sec(g,M.filter(p=>p.cat===g))).join(""):`<p class="mute">No products match. Try a shorter search.</p>`;
return;
}
L.className="snap";
L.innerHTML=cats.map(g=>`<div class="slide">${sec(g,P.filter(p=>p.cat===g))}</div>`).join("");
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

// ---- The estimate panel and the WhatsApp message -----------------------------
// Rebuilt after every change. Totals: materials = sum of price × quantity;
// tax is TAX_RATE (0 today); delivery is always quoted separately.
function renderEst(){
const rows=P.filter(p=>qty[p.id]>0);
const sub=rows.reduce((s,p)=>s+p.price*qty[p.id],0);
const tax=sub*TAX_RATE,total=sub+tax;
$("#lines").innerHTML=rows.length?rows.map(p=>`<div class="ln"><div class="nm">${p.name}<small>${money(p.price)} per ${p.unit}</small></div>${ctrl(p)}<div class="amt">${money(p.price*qty[p.id])}</div></div>`).join(""):`<p class="mute empty">Your estimate is empty. Add materials from the price list.</p>`;
$("#tot").innerHTML=`<div><span>Materials</span><span>${money(sub)}</span></div><div><span>Delivery</span><span>Quoted separately</span></div>`+(TAX_RATE?`<div><span>Tax (${+(TAX_RATE*100).toFixed(2)}%)</span><span>${money(tax)}</span></div>`:"")+`<div class="gt"><span>Total before delivery</span><span>${money(total)}</span></div>`;
$("#bar").classList.toggle("on",rows.length>0);
$("#barTxt").textContent=`Estimate: ${money(total)} (${rows.length} ${rows.length===1?"item":"items"})`;
const loc=$("#loc").value.trim();
const msg=`Hello The Cement People,\n\nI would like a quote for *Estimate ${REF}* (${DATE}).\n`
+(loc?`\n*Drop-off location:* ${loc}\n`:"")
+"\n*Items*\n"+rows.map((p,i)=>`${i+1}. ${p.name} (${p.unit})\n   ${qty[p.id]} × ${money(p.price)} = ${money(p.price*qty[p.id])}`).join("\n")
+`\n\n*Materials total: ${money(sub)}*`
+(TAX_RATE?`\nTax (${+(TAX_RATE*100).toFixed(2)}%): ${money(tax)}\nTotal before delivery: ${money(total)}`:"")
+"\n\nPlease confirm availability and the delivery cost"+(loc?" to this location.":".");
renderQuote(rows,sub,tax,total,loc);
const sd=$("#send");
if(rows.length){sd.href="https://wa.me/"+WA_NUMBER+"?text="+encodeURIComponent(msg);sd.classList.remove("off");sd.removeAttribute("aria-disabled")}
else{sd.removeAttribute("href");sd.classList.add("off");sd.setAttribute("aria-disabled","true")}
}

// ---- The printable A4 quotation ---------------------------------------------
// Fills the hidden <section id="quote">. print.css hides everything else when
// printing. esc() makes the customer's typed location safe to display.
const esc=s=>s.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function renderQuote(rows,sub,tax,total,loc){
$("#quote").innerHTML=`<header class="q-head"><div class="q-brand"><svg viewBox="0 0 59 38" aria-hidden="true"><rect x="0" y="26" width="28" height="12" rx="1" fill="#111"/><rect x="31" y="26" width="28" height="12" rx="1" fill="#111"/><rect x="17" y="13" width="42" height="12" rx="1" fill="#111"/><rect x="31" y="0" width="28" height="12" rx="1" fill="#f2c300"/></svg><div><b>The Cement People</b><span>${TCP.business.town} · ${TCP.business.phone} (call or WhatsApp)<br>${TCP.business.website}</span></div></div>`
+`<div class="q-doc"><h1>Estimate</h1><dl><dt>Reference</dt><dd>${REF}</dd><dt>Date</dt><dd>${DATE}</dd></dl></div></header>`
+`<div class="q-to"><div><small>Drop-off location</small><p>${loc?esc(loc):"Not provided"}</p></div><div><small>Delivery</small><p>Quoted separately, by location</p></div></div>`
+`<table><thead><tr><th class="n">#</th><th>Description</th><th class="r">Qty</th><th class="r">Unit price</th><th class="r">Amount</th></tr></thead><tbody>`
+(rows.length?rows.map((p,i)=>`<tr><td class="n">${i+1}</td><td>${p.name}<small>${p.cat}, per ${p.unit}</small></td><td class="r">${qty[p.id]}</td><td class="r">${money(p.price)}</td><td class="r">${money(p.price*qty[p.id])}</td></tr>`).join(""):`<tr class="q-empty"><td colspan="5">No items added yet.</td></tr>`)
+`</tbody></table><div class="q-close"><div class="q-terms"><h2>Delivery and terms</h2><ul>`
+`<li>We deliver to your drop-off location. The delivery cost depends on your order and location, and is agreed with you before delivery.</li>`
+`<li>This estimate is indicative. Final prices and availability are confirmed when you order.</li>`
+`<li>All prices are in Ghana cedis (GH₵).</li></ul>`
+`<h2>To order</h2><p>WhatsApp or call ${TCP.business.phone} and quote reference <b>${REF}</b>.</p></div>`
+`<div class="q-sum"><div><span>Materials</span><span>${money(sub)}</span></div><div><span>Delivery</span><span>Quoted separately</span></div>`
+(TAX_RATE?`<div><span>Tax (${+(TAX_RATE*100).toFixed(2)}%)</span><span>${money(tax)}</span></div>`:"")
+`<div class="gt"><span>Total before delivery</span><span>${money(total)}</span></div></div></div>`;
// Compact running header on continuation pages only (page 2 onwards)
let ps=document.getElementById("qpage");
if(!ps){ps=document.createElement("style");ps.id="qpage";document.head.appendChild(ps);}
ps.textContent=`@page{@top-left{content:"The Cement People  ·  Estimate ${REF}";font:700 7.5pt Montserrat,Arial,sans-serif;color:#111;vertical-align:bottom;padding-bottom:2mm}@top-right{content:"Continued";font:7.5pt Montserrat,Arial,sans-serif;color:#777;vertical-align:bottom;padding-bottom:2mm}}@page:first{@top-left{content:none}@top-right{content:none}}`;
}

// Refresh the quotation just before printing, and name the PDF after the reference.
// The page's own title, put back after printing (the PDF is named after the reference).
const PAGE_TITLE=document.title;
addEventListener("beforeprint",()=>{renderEst();document.title=`The Cement People Estimate ${REF}`;});
addEventListener("afterprint",()=>{document.title=PAGE_TITLE;});

// ---- Changing a quantity: every Add, +, − and typed number goes through set() --
function set(id,n){
n=Math.max(0,Math.min(9999,n));
if(n)qty[id]=n;else delete qty[id];
renderList();renderEst();
}


// ---- Buttons and inputs ------------------------------------------------------
document.addEventListener("click",e=>{
const b=e.target.closest("button");if(!b)return;
const d=b.dataset;
if(d.inc)set(d.inc,(qty[d.inc]||0)+1);
else if(d.dec)set(d.dec,(qty[d.dec]||0)-1);
else if(d.cat!==undefined)goCat(d.cat);
});
document.addEventListener("change",e=>{
const i=e.target;if(i.dataset&&i.dataset.qty)set(i.dataset.qty,parseInt(i.value,10)||0);
});
$("#q").addEventListener("input",e=>{q=e.target.value.trim().toLowerCase();renderList();});
$("#print").addEventListener("click",()=>window.print());
$("#clear").addEventListener("click",()=>{qty={};newQuote();renderList();renderEst();});

// ---- Phones: the estimate opens as a full-screen view -------------------------
const mq=matchMedia("(max-width:899px)");
function openEst(){const e=$("#est");e.classList.add("open");e.scrollTop=0;document.body.style.overflow="hidden";$("#dclose").focus({preventScroll:true});}
function closeEst(){$("#est").classList.remove("open");document.body.style.overflow="";}
$("#barBtn").addEventListener("click",openEst);
$("#dclose").addEventListener("click",closeEst);
document.addEventListener("click",e=>{if(mq.matches&&e.target.closest('a[href="#est"]')){e.preventDefault();openEst();}});
mq.addEventListener("change",()=>{if(!mq.matches)closeEst();});

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
const WA_NUMBER=TCP.business.whatsapp;
$("#loc").addEventListener("input",renderEst);
document.querySelectorAll("[data-wa]").forEach(a=>{if(WA_NUMBER)a.href="https://wa.me/"+WA_NUMBER+"?text="+encodeURIComponent("Hello, I would like to enquire about your materials.")});

// ---- Category tiles under the hero ("Cement", "Iron rods") --------------------
const S='fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"';
const IC={
bag:`<svg class="ic" viewBox="0 0 48 48" aria-hidden="true"><path d="M13 8h22l5 9v26H8V17z" ${S}/><path d="M8 17h32" ${S}/></svg>`,
rods:`<svg class="ic" viewBox="0 0 48 48" aria-hidden="true"><rect x="5" y="12" width="32" height="8" rx="4" ${S}/><rect x="11" y="22" width="32" height="8" rx="4" ${S}/><rect x="5" y="32" width="32" height="8" rx="4" ${S}/></svg>`,
wire:`<svg class="ic" viewBox="0 0 48 48" aria-hidden="true"><ellipse cx="24" cy="27" rx="19" ry="11" ${S}/><ellipse cx="24" cy="22" rx="19" ry="11" ${S}/><ellipse cx="24" cy="22" rx="8" ry="4" ${S}/></svg>`};
const rods=P.filter(p=>p.unit==="30 ft rod").map(p=>p.name.replace("Iron rod ","")).reverse().join(", ");
$("#cats").innerHTML=[
["Cement","Cement","50 kg bags: "+P.filter(p=>p.cat==="Cement").map(p=>p.name).join(", "),IC.bag],
["Iron Rods (Single Piece)","Iron rods","By the piece or the ton: "+rods+", and binding wire",IC.rods]
].map(([c,t,s,i])=>`<a href="#products" data-go="${c}">${i}<div><b>${t}</b><small>${s}</small></div><span class="go" aria-hidden="true">›</span></a>`).join("");
$("#cats").addEventListener("click",e=>{const a=e.target.closest("[data-go]");if(a)goCat(a.dataset.go,true);});

// ---- Mobile menu ---------------------------------------------------------------
$("#menu").addEventListener("click",()=>{const o=$("#nav").classList.toggle("open");$("#menu").setAttribute("aria-expanded",o)});
$("#nav").addEventListener("click",e=>{if(e.target.closest("a"))$("#nav").classList.remove("open")});

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
