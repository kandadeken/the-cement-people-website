/* ===========================================================================
   invoice-desk.js - TCP Invoice Desk (20 Nov 2026)
   ---------------------------------------------------------------------------
   Runs the private page /invoice-desk/ (see src/pages/invoice-desk.astro
   for what it is and is not). Plain script, like quote-engine.js, so the
   tests can reach its functions (window.TCPDesk).

   Sections below:
     1. Settings and helpers   (money in pesewas, number reading)
     2. Passphrase             (PBKDF2, checked in the browser)
     3. Reading the estimate   (the WhatsApp message the website writes)
     4. The invoice            (lines, delivery, number, totals)
     5. The screen             (form, summary, draft kept on this device)
     6. The PDF                (A4, same look as the website's estimate PDF)
     7. WhatsApp
   =========================================================================== */
(()=>{
// ---- 1. Settings and helpers ------------------------------------------------
const D=JSON.parse(document.getElementById("desk-data").textContent);
const P=D.products,CUR=D.currency,B=D.business;
// The document's title. TCP is not VAT-registered (20 Nov 2026), so this is
// an ordinary invoice. If TCP registers for VAT, change this to
// "Proforma invoice": official tax invoices would then come from GRA E-VAT.
const DOC_TITLE="Invoice";
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
// Money is kept in whole pesewas (GH₵1.00 = 100) so totals never pick up
// rounding errors; it is turned back into cedis only for display.
const toP=c=>Math.round(c*100);
const money=p=>CUR+(p/100).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
const fmtQ=n=>(+n).toLocaleString("en-US",{maximumFractionDigits:2});
// Reads a number however it was typed or written: "1,392.00", "1.392,00",
// "2,5", "50,000", "GH₵98.00". Returns NaN when there is no number.
function num(s){
  s=String(s==null?"":s).replace(/[^\d.,-]/g,"");
  if(!s)return NaN;
  const lc=s.lastIndexOf(","),ld=s.lastIndexOf(".");
  if(lc>=0&&ld>=0){ // both: the later one is the decimal point
    s=lc>ld?s.replace(/\./g,"").replace(",","."):s.replace(/,/g,"");
  }else if(lc>=0){ // commas only: groups of three are thousands ("50,000"), else a decimal comma ("2,5")
    s=/^-?\d{1,3}(,\d{3})+$/.test(s)?s.replace(/,/g,""):s.replace(",",".");
  }else if((s.match(/\./g)||[]).length>1){ // "1.234.567" thousands with dots
    s=s.replace(/\./g,"");
  }
  return parseFloat(s);
}
// The unit word after a quantity: "9 bags", "1 ton", "24 rods".
const UNIT_WORD=(u,n)=>{const one=n===1;
  if(/bag/i.test(u))return one?"bag":"bags";
  if(/^ton$/i.test(u))return one?"ton":"tons";
  if(/rod|ft/i.test(u))return one?"rod":"rods";
  if(/roll/i.test(u))return one?"roll":"rolls";
  return "";};
const byId=id=>P.find(p=>p.id===id);

// ---- 2. Passphrase -----------------------------------------------------------
// Only a slow fingerprint (PBKDF2-SHA-256, 310,000 rounds) of the passphrase
// is in this file, never the passphrase itself. The repository is public,
// so the slowness is what makes guessing it from the code impractical.
// This keeps casual visitors out; it is not a login server (see the page).
// To change the passphrase, make a new SALT and HASH with the same settings.
const SALT="31b9b574a5433482f5fa33b6859e44ed",ROUNDS=310000;
const HASH="340406a270dc711f7bf8efd52dd3f6d98881687251a4d6e510df2cc4d9b69e55";
const hex=b=>[...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,"0")).join("");
async function check(pass){
  const key=await crypto.subtle.importKey("raw",new TextEncoder().encode(pass.trim()),"PBKDF2",false,["deriveBits"]);
  const salt=new Uint8Array(SALT.match(/../g).map(h=>parseInt(h,16)));
  const bits=await crypto.subtle.deriveBits({name:"PBKDF2",hash:"SHA-256",salt,iterations:ROUNDS},key,256);
  return hex(bits)===HASH;
}
// Once opened, the desk stays open in this browser tab (not on the device).
const UNLOCK="tcp-desk-open";
function open(){$("#gate").hidden=true;$("#tool").hidden=false;try{sessionStorage.setItem(UNLOCK,"1")}catch(e){}restore();}
$("#gateForm").addEventListener("submit",async e=>{
  e.preventDefault();const m=$("#gateMsg");m.textContent="Checking…";
  let ok=false;try{ok=await check($("#pass").value)}catch(err){m.textContent="This browser cannot check the passphrase. Try Chrome.";return}
  if(ok){m.textContent="";$("#pass").value="";open()}else{m.textContent="That passphrase is not right.";$("#pass").select()}
});
try{if(sessionStorage.getItem(UNLOCK)==="1")open()}catch(e){}

// ---- 3. Reading the estimate -------------------------------------------------
// The website writes (quote-engine.js, renderEst):
//   *Estimate TCP-261120-MEBLV2* (20 November 2026)
//   *Drop-off location:* Buduburam
//   1. Iron rod 12 mm (30 ft rod)
//      24 × GH₵58.00 = GH₵1,392.00
// WhatsApp may drop the * marks when a message is copied or forwarded,
// so they are optional here. Each item is matched to the price list by
// its name and unit ("Iron rod 12 mm" by the piece and by the ton are
// different products).
function parseEstimate(text){
  const t=String(text||"").replace(/\r/g,"").replace(/ /g," ");
  const ref=(t.match(/TCP-(\d{6})-([A-Z0-9]{6})\b/)||[]);
  const loc=(t.match(/Drop-off location:\*?\s*(.+)/i)||[])[1];
  const lines=t.split("\n"),items=[];
  for(let i=0;i<lines.length;i++){
    const m=lines[i].match(/^\s*\d+\.\s*(.+?)\s*\(([^()]+)\)\s*$/);
    if(!m)continue;
    let j=i+1;while(j<lines.length&&!lines[j].trim())j++;
    const q=(lines[j]||"").match(/([\d.,]+)\s*[×xX*]\s*(?:GH[₵¢S]\s*)?([\d.,]+)/);
    if(!q)continue;
    const name=m[1].trim(),unit=m[2].trim(),qty=num(q[1]),quoted=num(q[2]);
    if(!(qty>0))continue;
    const same=s=>s.toLowerCase().replace(/\s+/g," ").trim();
    let p=P.find(x=>same(x.name)===same(name)&&same(x.unit)===same(unit));
    if(!p){const n=P.filter(x=>same(x.name)===same(name));if(n.length===1)p=n[0];}
    items.push({pid:p?p.id:null,name:p?p.name:name,unit:p?p.unit:unit,qty,
      price:p?toP(p.price):toP(quoted),list:p?toP(p.price):null,quoted:isNaN(quoted)?null:toP(quoted)});
    i=j;
  }
  return{ref:ref[0]||null,code:ref[2]||null,loc:loc?loc.replace(/\*+$/,"").trim():"",items};
}

// ---- 4. The invoice ------------------------------------------------------------
// S holds everything on the form; saved as a draft on this device (section 5).
let S=blank();
function blank(){return{ref:null,code:null,name:"",phone:"",site:"",items:[],dl:"pending",fee:"",date:today(),rev:"1",pay:"",note:""};}
function today(){const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");}
// A code of 6 characters for invoices made without an estimate.
function freshCode(){const A="23456789ABCDEFGHJKLMNPQRSTUVWXYZ",r=new Uint8Array(6);crypto.getRandomValues(r);return[...r].map(n=>A[n%32]).join("");}
// Invoice number: TCP-INV-YYMMDD-XXXXXX, the date plus the six characters of
// the customer's estimate reference, so it leads straight back to the
// estimate. A revised invoice adds -2, -3... (agreed 20 Nov 2026; strictly
// running numbers need a database and come with the larger system).
function invoiceNo(s){const d=(s.date||today()).replace(/-/g,"").slice(2);return`TCP-INV-${d}-${s.code}${s.rev&&s.rev!=="1"?"-"+s.rev:""}`;}
const lineTotal=l=>Math.round(l.price*l.qty);
function totals(s){
  const mat=s.items.reduce((a,l)=>a+lineTotal(l),0);
  const fee=s.dl==="fee"?toP(num(s.fee)||0):0;
  return{mat,fee,total:mat+fee};
}
const DL_TEXT={pending:"Not agreed yet",free:"Free delivery",fee:"Delivery fee",pickup:"Customer pickup"};
// What is missing before the invoice can be issued.
function problems(s){
  const out=[];
  if(!s.items.length)out.push("Add at least one item.");
  if(s.items.some(l=>!(l.qty>0)))out.push("Every item needs a quantity.");
  if(s.items.some(l=>!(l.price>=0)||isNaN(l.price)))out.push("Every item needs a price.");
  if(!s.name.trim())out.push("Add the customer's name.");
  if(!s.phone.replace(/\D/g,""))out.push("Add the customer's phone number.");
  if(s.dl==="pending")out.push("Agree the delivery with the customer first.");
  if(s.dl==="fee"&&!(num(s.fee)>0))out.push("Enter the delivery fee.");
  return out;
}

// ---- 5. The screen ---------------------------------------------------------------
const DRAFT="tcp-desk-draft";
function save(){try{localStorage.setItem(DRAFT,JSON.stringify(S))}catch(e){}}
function restore(){
  let d=null;try{d=JSON.parse(localStorage.getItem(DRAFT)||"null")}catch(e){}
  if(d&&d.code){S={...blank(),...d};showForm();}
}
// Product list for "Add item", grouped by category.
(function fillAdd(){const g={};P.forEach(p=>(g[p.cat]=g[p.cat]||[]).push(p));
  $("#addSel").innerHTML=Object.entries(g).map(([c,l])=>`<optgroup label="${esc(c)}">${l.map(p=>`<option value="${p.id}">${esc(p.name)} (${esc(p.unit)}) · ${money(toP(p.price))}</option>`).join("")}</optgroup>`).join("");})();

function showForm(){
  $("#form").hidden=false;
  $("#cName").value=S.name;$("#cPhone").value=S.phone;$("#cSite").value=S.site;
  document.querySelectorAll('input[name="dl"]').forEach(r=>r.checked=r.value===S.dl);
  $("#fee").value=S.fee;$("#iDate").value=S.date;$("#iRev").value=S.rev;$("#iPay").value=S.pay;$("#iNote").value=S.note;
  render();
}
function itemsHTML(){
  if(!S.items.length)return`<p class="dk-help">No items yet. Add them below.</p>`;
  return S.items.map((l,i)=>{
    const changed=l.list!=null&&l.price!==l.list,quotedDiff=l.quoted!=null&&l.list!=null&&l.quoted!==l.list;
    return`<div class="dk-line" data-i="${i}">
      <div class="dk-ln-name"><b>${i+1}. ${esc(l.name)}</b> <small>per ${esc(l.unit)}</small>
        ${l.pid?"":`<span class="dk-flag">Not in today's price list: check the name and price</span>`}
        ${quotedDiff?`<span class="dk-note">The estimate said ${money(l.quoted)}; today's price is ${money(l.list)}.</span>`:""}</div>
      <label>Qty<input data-f="qty" type="text" inputmode="decimal" value="${fmtQ(l.qty)}" aria-label="Quantity of ${esc(l.name)}"></label>
      <label>Price (GH₵)<input data-f="price" type="text" inputmode="decimal" value="${(l.price/100).toFixed(2)}" aria-label="Price of ${esc(l.name)}"></label>
      <div class="dk-amt">${money(lineTotal(l))}${changed?`<small>Agreed price (list ${money(l.list)})</small>`:""}</div>
      <button type="button" class="dk-x" data-rm="${i}" aria-label="Remove ${esc(l.name)}">Remove</button>
    </div>`}).join("");
}
// Redraws the item lines, then the summary.
function render(){
  $("#items").innerHTML=itemsHTML();
  $("#feeBox").hidden=S.dl!=="fee";
  refresh();
}
// Typing in a line's quantity or price updates the totals without
// redrawing the box being typed in.
$("#items").addEventListener("input",e=>{
  const row=e.target.closest(".dk-line");if(!row)return;const l=S.items[+row.dataset.i];
  if(e.target.dataset.f==="qty")l.qty=num(e.target.value);
  if(e.target.dataset.f==="price")l.price=toP(num(e.target.value));
  const a=row.querySelector(".dk-amt");const changed=l.list!=null&&l.price!==l.list;
  a.innerHTML=(isNaN(lineTotal(l))?"—":money(lineTotal(l)))+(changed?`<small>Agreed price (list ${money(l.list)})</small>`:"");
  refresh();
});
// Totals and messages only (used while typing in a line).
function refresh(){const t=totals(S),bad=problems(S);
  $("#sNo").textContent=invoiceNo(S);$("#sMat").textContent=isNaN(t.mat)?"—":money(t.mat);
  $("#sDel").textContent=S.dl==="fee"?money(t.fee):S.dl==="pending"?"Not agreed yet":DL_TEXT[S.dl]+" · "+money(0);
  $("#sTot").textContent=isNaN(t.total)?"—":money(t.total);$("#pdfBtn").disabled=bad.length>0;
  const wa=$("#waBtn"),to=waNumber(S.phone);
  $("#sMsg").textContent=bad.length?bad.join(" "):to?"":"The PDF is ready. For WhatsApp, enter the full phone number (10 digits, e.g. 024 123 4567).";
  if(!bad.length&&to){wa.href="https://wa.me/"+to+"?text="+encodeURIComponent(waText(S));wa.removeAttribute("aria-disabled");wa.classList.remove("off")}
  else{wa.removeAttribute("href");wa.setAttribute("aria-disabled","true");wa.classList.add("off")}
  save();}
$("#items").addEventListener("change",()=>render());
$("#items").addEventListener("click",e=>{const b=e.target.closest("[data-rm]");if(!b)return;S.items.splice(+b.dataset.rm,1);render();});
$("#addBtn").addEventListener("click",()=>{const p=byId($("#addSel").value);if(!p)return;
  S.items.push({pid:p.id,name:p.name,unit:p.unit,qty:1,price:toP(p.price),list:toP(p.price),quoted:null});render();});
[["#cName","name"],["#cPhone","phone"],["#cSite","site"],["#fee","fee"],["#iDate","date"],["#iRev","rev"],["#iPay","pay"],["#iNote","note"]]
  .forEach(([sel,k])=>$(sel).addEventListener("input",e=>{S[k]=e.target.value;refresh();}));
$("#iRev").addEventListener("change",e=>{S.rev=e.target.value;refresh();});
document.querySelectorAll('input[name="dl"]').forEach(r=>r.addEventListener("change",()=>{S.dl=r.value;render();}));

$("#readBtn").addEventListener("click",()=>{
  const r=parseEstimate($("#paste").value),m=$("#readMsg");
  if(!r.items.length){m.textContent="No items found. Paste the whole estimate message, from \"Hello The Cement People\" to the total.";return;}
  S={...blank(),ref:r.ref,code:r.code||freshCode(),site:r.loc,items:r.items};
  const odd=r.items.filter(l=>!l.pid).length,moved=r.items.filter(l=>l.quoted!=null&&l.list!=null&&l.quoted!==l.list).length;
  m.textContent=`Read ${r.items.length} ${r.items.length===1?"item":"items"}${r.ref?" from estimate "+r.ref:""}.`
    +(moved?` ${moved} ${moved===1?"price has":"prices have"} changed since the estimate: today's price is used, edit it if you agreed otherwise.`:"")
    +(odd?` ${odd} ${odd===1?"item is":"items are"} not in today's price list: please check.`:"");
  showForm();$("#cName").focus();
});
$("#blankBtn").addEventListener("click",()=>{S={...blank(),code:freshCode()};$("#readMsg").textContent="";showForm();$("#cName").focus();});
$("#newBtn").addEventListener("click",()=>{
  if(S.items.length&&!confirm("Start a new invoice? This one is cleared from the desk (your saved PDF is kept)."))return;
  S=blank();try{localStorage.removeItem(DRAFT)}catch(e){}$("#paste").value="";$("#readMsg").textContent="";$("#form").hidden=true;window.scrollTo(0,0);});

// ---- 6. The PDF --------------------------------------------------------------------
// Same A4 layout as the website's estimate (styles/print.css): logo and
// document details on top, customer and delivery in the grey band, the
// items table, then notes on the left and totals on the right.
function dateText(iso){const[y,m,d]=(iso||today()).split("-").map(Number);
  return new Date(y,m-1,d).toLocaleDateString("en-GB",{year:"numeric",month:"long",day:"numeric"});}
function invoiceHTML(s){
  const t=totals(s),no=invoiceNo(s);
  const logo=($("#q-logo-svg")||{}).innerHTML||"";
  const rows=s.items.map((l,i)=>`<tr data-row="item"><td class="n">${i+1}</td><td>${esc(l.name)} <small>per ${esc(l.unit)}</small></td><td class="r">${fmtQ(l.qty)} ${UNIT_WORD(l.unit,l.qty)}</td><td class="r">${money(l.price)}</td><td class="r">${money(lineTotal(l))}</td></tr>`).join("");
  const site=s.site.trim();
  const dl=s.dl==="pickup"?`Customer pickup<br>${esc(B.pickup)}`:s.dl==="free"?`Free delivery${site?" to<br>"+esc(site):""}`:`Delivery${site?" to<br>"+esc(site):""}`;
  const dlAmt=s.dl==="fee"?money(t.fee):s.dl==="free"?"Free":"Pickup";
  return`<header class="q-head">${logo}<div class="q-doc"><h1>${DOC_TITLE}</h1><dl><dt>Invoice no.</dt><dd>${no}</dd><dt>Date</dt><dd>${dateText(s.date)}</dd>${s.ref?`<dt>Estimate</dt><dd>${s.ref}</dd>`:""}</dl></div></header>`
  +`<div class="q-to"><div><small>Bill to</small><p>${esc(s.name.trim())}<br>${esc(s.phone.trim())}</p></div><div><small>Delivery</small><p>${dl}</p></div><div><small>From</small><p>${esc(B.name)}<br>${esc(B.phone)} (call or WhatsApp)<br>${esc(B.website)}<br>${esc(B.town)}</p></div></div>`
  +`<table><thead><tr><th class="n">#</th><th>Description</th><th class="r">Qty</th><th class="r">Unit price</th><th class="r">Amount</th></tr></thead><tbody>${rows}</tbody></table>`
  +`<div class="q-close"><div class="q-terms">`
  +(s.pay.trim()?`<h2>How to pay</h2><p class="q-pre">${esc(s.pay.trim())}</p>`:"")
  +(s.note.trim()?`<h2>Note</h2><p class="q-pre">${esc(s.note.trim())}</p>`:"")
  +`<h2>Questions</h2><p>WhatsApp or call ${esc(B.phone)} and quote invoice <b>${no}</b>.</p>`
  +`<h2>Terms</h2><ul><li>All prices are in Ghana cedis (GH₵).</li></ul></div>`
  +`<div class="q-sum"><div class="q-mat"><span>Materials</span><span>${money(t.mat)}</span></div>`
  +`<div class="q-del"><span>${DL_TEXT[s.dl]}</span><span>${dlAmt}</span></div>`
  +`<div class="gt"><span>Total due</span><span>${money(t.total)}</span></div></div></div>`;
}
const PAGE_TITLE=document.title;
function renderPdf(){
  $("#quote").innerHTML=invoiceHTML(S);
  let ps=document.getElementById("qpage");
  if(!ps){ps=document.createElement("style");ps.id="qpage";document.head.appendChild(ps);}
  ps.textContent=`@page{@top-left{content:"The Cement People  ·  ${DOC_TITLE} ${invoiceNo(S)}";font:700 7.5pt Montserrat,Arial,sans-serif;color:#131514;vertical-align:bottom;padding-bottom:2mm}@top-right{content:"Continued";font:7.5pt Montserrat,Arial,sans-serif;color:#5a5a5a;vertical-align:bottom;padding-bottom:2mm}}@page:first{@top-left{content:none}@top-right{content:none}}`;
}
// The saved PDF is named after the invoice number.
addEventListener("beforeprint",()=>{renderPdf();document.title=`The Cement People ${DOC_TITLE} ${invoiceNo(S)}`;});
addEventListener("afterprint",()=>{document.title=PAGE_TITLE;});
$("#pdfBtn").addEventListener("click",()=>{if(problems(S).length)return;renderPdf();window.print();});

// ---- 7. WhatsApp -------------------------------------------------------------------
// A Ghana number as wa.me needs it: 024 123 4567 -> 233241234567.
function waNumber(p){let d=String(p||"").replace(/\D/g,"");
  if(d.startsWith("00"))d=d.slice(2);
  if(d.length===10&&d.startsWith("0"))d="233"+d.slice(1);
  else if(d.length===9)d="233"+d;
  return d.length>=11?d:"";}
function waText(s){const t=totals(s),first=s.name.trim().split(/\s+/)[0]||"";
  return`Hello${first?" "+first:""},\n\nThank you for your order. Here is your invoice from The Cement People.\n\n*Invoice ${invoiceNo(s)}*${s.ref?`\nFor estimate ${s.ref}`:""}\n`
  +s.items.map((l,i)=>`${i+1}. ${l.name} (${l.unit}): ${fmtQ(l.qty)} × ${money(l.price)} = ${money(lineTotal(l))}`).join("\n")
  +`\n\nMaterials: ${money(t.mat)}\n${DL_TEXT[s.dl]}: ${s.dl==="fee"?money(t.fee):money(0)}\n*Total due: ${money(t.total)}*\n\nThe invoice PDF is attached.`;}

// For the tests (and nothing else): the desk's own functions.
window.TCPDesk={parseEstimate,num,invoiceNo,totals,problems,waNumber,waText,invoiceHTML,state:()=>S};
})();
