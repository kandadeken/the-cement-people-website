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
     8. Payments and receipts  (added 20 Nov 2026, see the notes there)
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
// (Re-opening the desk after a reload happens at the very end of this file,
// once every section below is ready: see "Start".)

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
// payments: the money received against this invoice, in the order it was
// recorded, each {date, amount (pesewas), method, net, ref} (section 8).
function blank(){return{ref:null,code:null,name:"",phone:"",site:"",items:[],dl:"pending",fee:"",date:today(),rev:"1",pay:"",note:"",payments:[]};}
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
  $("#shareBtn").disabled=bad.length>0;
  $("#sMsg").textContent=bad.join(" ");
  renderPays();
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
  if(S.items.length&&!confirm("Start a new invoice? This one and its payments are cleared from the desk (PDFs you saved or shared are kept)."))return;
  S=blank();try{localStorage.removeItem(DRAFT)}catch(e){}$("#paste").value="";$("#readMsg").textContent="";$("#form").hidden=true;window.scrollTo(0,0);});

// ---- 6. The PDF --------------------------------------------------------------------
// The desk draws the invoice PDF itself (jsPDF), so the file can be shared
// straight to WhatsApp from the phone's share menu (20 Nov 2026, Daniel:
// a WhatsApp link can only carry text, so the PDF was not attached).
// It copies the look of the website's estimate PDF (styles/print.css):
// logo and document details on top, a charcoal rule with an ochre start,
// customer and delivery in a grey band, the items table, then notes on the
// left and totals on the right; footer and page numbers on every page.
// The library and the font load only the first time a PDF is made.
const VENDOR="/scripts/vendor/";
const loadScript=src=>new Promise((ok,fail)=>{const s=document.createElement("script");s.src=src;s.onload=ok;s.onerror=()=>fail(new Error("Could not load "+src));document.head.appendChild(s);});
let ready=null;
function pdfKit(){
  if(!ready)ready=Promise.all([
    window.jspdf?0:loadScript(VENDOR+"jspdf.umd.min.js"),
    window.TCP_PDF_FONTS?0:loadScript(VENDOR+"montserrat-pdf.js"),
    logoPng(),
  ]).then(r=>({jsPDF:window.jspdf.jsPDF,logo:r[2]})).catch(e=>{ready=null;throw e;});
  return ready;
}
// The horizontal logo, drawn sharp (4 times its print size) as a PNG.
function logoPng(){return new Promise((ok,fail)=>{const img=new Image();
  img.onload=()=>{const c=document.createElement("canvas");c.width=2369;c.height=400;const g=c.getContext("2d");g.drawImage(img,0,0,c.width,c.height);ok(c.toDataURL("image/png"));};
  img.onerror=()=>fail(new Error("Could not load the logo"));img.src="/brand/tcp-logo-horizontal-on-light.svg";});}
function dateText(iso){const[y,m,d]=(iso||today()).split("-").map(Number);
  return new Date(y,m-1,d).toLocaleDateString("en-GB",{year:"numeric",month:"long",day:"numeric"});}
const fileName=s=>`TCP Invoice ${invoiceNo(s)}.pdf`;
async function makePdf(s){
  const{jsPDF,logo}=await pdfKit(),F=window.TCP_PDF_FONTS;
  const doc=new jsPDF({unit:"mm",format:"a4",compress:true});
  [["r","normal"],["s","semibold"],["x","bold"]].forEach(([k,st])=>{doc.addFileToVFS(`M-${k}.ttf`,F[k]);doc.addFont(`M-${k}.ttf`,"Montserrat",st);});
  doc.setProperties({title:`${B.name} ${DOC_TITLE} ${invoiceNo(s)}`,author:B.name,creator:"TCP Invoice Desk"});
  const INK="#131514",MUTE="#5a5a5a",LINE="#dcdcdc",OCHRE="#ff9802",BAND="#f4f4f4";
  const L=14,R=196,W=R-L,TOP=16,BOTTOM=282,pt=n=>n*0.3528;
  const font=(st,size,col)=>{doc.setFont("Montserrat",st);doc.setFontSize(size);doc.setTextColor(col||INK);};
  // Text drawn from its top edge; "sp" is letter spacing in mm; right-aligned when "right" is set.
  const txt=(str,x,y,o={})=>{const sp=o.sp||0,w=doc.getTextWidth(str)+sp*Math.max(0,str.length-1);
    doc.text(str,o.right?x-w:x,y,{baseline:"top",charSpace:sp});return w;};
  const wrap=(str,w)=>doc.splitTextToSize(str,w);
  const t=totals(s),no=invoiceNo(s);
  // -- Header: logo left; INVOICE, number, date and estimate right
  doc.addImage(logo,"PNG",L,TOP,13*5.92329,13);
  font("bold",17);txt(DOC_TITLE.toUpperCase(),R,TOP,{right:1,sp:pt(17)*.08});
  const dl=[["Invoice no.",no],["Date",dateText(s.date)]].concat(s.ref?[["Estimate",s.ref]]:[]);
  font("bold",9);const vw=Math.max(...dl.map(r=>doc.getTextWidth(r[1])));
  let y=TOP+8.5;
  dl.forEach(([k,v])=>{font("bold",9);txt(v,R,y,{right:1});font("normal",9,MUTE);txt(k,R-vw-4,y,{right:1});y+=4.3;});
  y=Math.max(TOP+13,y)+4.5;
  doc.setFillColor(INK);doc.rect(L,y,W,.8,"F");doc.setFillColor(OCHRE);doc.rect(L,y,28,.8,"F");
  y+=.8+4.5;
  // -- Grey band: bill to, delivery, from
  const site=s.site.trim();
  const dlv=s.dl==="pickup"?`Customer pickup\n${B.pickup}`:(s.dl==="free"?"Free delivery":"Delivery")+(site?` to\n${site}`:"");
  const cols=[["Bill to",`${s.name.trim()}\n${s.phone.trim()}`],["Delivery",dlv],["From",`${B.name}\n${B.phone} (call or WhatsApp)\n${B.website}\n${B.town}`]];
  const inner=W-.8-7,gap=6,unitW=(inner-2*gap)/3.7,cw=[1.5,1,1.2].map(r=>r*unitW);
  font("semibold",8.5);const lh=pt(8.5)*1.45;
  const lines=cols.map((c,i)=>c[1].split("\n").flatMap(l=>wrap(l,cw[i])));
  const bandH=3+pt(7)*1.2+.6+Math.max(...lines.map(l=>l.length))*lh+3;
  doc.setFillColor(BAND);doc.rect(L,y,W,bandH,"F");doc.setFillColor(OCHRE);doc.rect(L,y,.8,bandH,"F");
  let x=L+.8+3.5;
  cols.forEach((c,i)=>{font("bold",7,MUTE);txt(c[0].toUpperCase(),x,y+3,{sp:pt(7)*.1});
    font("semibold",8.5);lines[i].forEach((l,j)=>txt(l,x,y+3+pt(7)*1.2+.6+j*lh));x+=cw[i]+gap;});
  y+=bandH+4.5;
  // -- Items table
  const C={n:L+2.5,d:L+8+2.5,q:R-32-28-2.5,u:R-32-2.5,a:R-2.5},dW=C.q-24-C.d;
  const head=()=>{doc.setFillColor(INK);doc.rect(L,y,W,7,"F");font("bold",7.5,"#ffffff");const sp=pt(7.5)*.08,ty=y+2.2;
    txt("#",C.n,ty,{sp});txt("DESCRIPTION",C.d,ty,{sp});txt("QTY",C.q,ty,{right:1,sp});txt("UNIT PRICE",C.u,ty,{right:1,sp});txt("AMOUNT",C.a,ty,{right:1,sp});y+=7;};
  const newPage=()=>{doc.addPage();y=TOP;};
  head();
  const rlh=pt(9.5)*1.45;
  s.items.forEach((l,i)=>{
    font("semibold",9.5);const nameLines=wrap(l.name,dW);
    font("normal",8);const per=`per ${l.unit}`,perW=doc.getTextWidth(per);
    font("semibold",9.5);const lastW=doc.getTextWidth(nameLines[nameLines.length-1]);
    const perOwn=lastW+1.5+perW>dW,rows=nameLines.length+(perOwn?1:0),h=1.7*2+rows*rlh;
    if(y+h>BOTTOM){newPage();head();}
    const ty=y+1.7;
    font("semibold",9.5);txt(String(i+1),C.n,ty);nameLines.forEach((n,j)=>txt(n,C.d,ty+j*rlh));
    font("normal",8,MUTE);perOwn?txt(per,C.d,ty+nameLines.length*rlh+.3):txt(per,C.d+lastW+1.5,ty+(nameLines.length-1)*rlh+.4);
    font("normal",9.5);txt(`${fmtQ(l.qty)} ${UNIT_WORD(l.unit,l.qty)}`.trim(),C.q,ty,{right:1});txt(money(l.price),C.u,ty,{right:1});txt(money(lineTotal(l)),C.a,ty,{right:1});
    y+=h;doc.setDrawColor(LINE);doc.setLineWidth(.25);doc.line(L,y,R,y);
  });
  // -- Bottom: notes left, totals right (kept together on one page)
  const TW=98,LW=W-TW-8,tlh=pt(7.5)*1.4;
  const notes=[];
  if(s.pay.trim())notes.push(["How to pay",s.pay.trim()]);
  if(s.note.trim())notes.push(["Note",s.note.trim()]);
  notes.push(["Questions",`WhatsApp or call ${B.phone} and quote invoice ${no}.`]);
  notes.push(["Terms","All prices are in Ghana cedis (GH₵)."]);
  font("normal",7.5);const noteLines=notes.map(([h,b])=>[h,b.split("\n").flatMap(l=>wrap(l,LW))]);
  const notesH=noteLines.reduce((a,[,b])=>a+tlh+1.5+b.length*tlh+3,0);
  const rowH=1.2*2+pt(9.5)*1.45,sumH=.5+rowH*2+1.5+3*2+pt(11)*1.45;
  if(y+4+Math.max(notesH,sumH)>BOTTOM)newPage();else y+=4;
  let ny=y;
  noteLines.forEach(([h,b])=>{font("bold",7.5,MUTE);txt(h.toUpperCase(),L,ny,{sp:pt(7.5)*.1});ny+=tlh+1.5;
    font("normal",7.5,"#333333");b.forEach(l=>{txt(l,L,ny);ny+=tlh;});ny+=3;});
  const sx=R-TW;let sy=y;
  doc.setFillColor(INK);doc.rect(sx,sy,TW,.5,"F");sy+=.5;
  const sumRow=(k,v,st)=>{font(st,9.5);txt(k,sx+2.5,sy+1.2);txt(v,R-2.5,sy+1.2,{right:1});sy+=rowH;};
  sumRow("Materials",money(t.mat),"bold");
  sumRow(DL_TEXT[s.dl],s.dl==="fee"?money(t.fee):s.dl==="free"?"Free":"Pickup","semibold");
  sy+=1.5;const gh=3*2+pt(11)*1.45;
  doc.setFillColor(INK);doc.rect(sx,sy,TW,gh,"F");doc.setFillColor(OCHRE);doc.rect(sx,sy,1.5,gh,"F");
  font("bold",11,"#ffffff");txt("Total due",sx+1.5+2.5,sy+3);txt(money(t.total),R-2.5,sy+3,{right:1});
  // -- Every page: footer; pages 2+ also a "continued" line at the top
  const n=doc.getNumberOfPages();
  for(let p=1;p<=n;p++){doc.setPage(p);
    font("normal",7,MUTE);txt(`${B.website}  ·  ${B.phone}`,L,289);txt(`Page ${p} of ${n}`,R,289,{right:1});
    if(p>1){font("bold",7.5);txt(`${B.name}  ·  ${DOC_TITLE} ${no}`,L,9);font("normal",7.5,MUTE);txt("Continued",R,9,{right:1});}}
  return doc;
}

// ---- 7. Sharing ----------------------------------------------------------------------
// "Share invoice": the phone's share menu with the PDF and a one-line
// message; choose WhatsApp, then the customer (20 Nov 2026, Daniel: only
// the PDF and "here is your invoice", not every item in the message).
// Where a browser cannot share files (most computers), the PDF is
// downloaded and the customer's WhatsApp chat opens with the same line.
function waNumber(p){let d=String(p||"").replace(/\D/g,"");
  if(d.startsWith("00"))d=d.slice(2);
  if(d.length===10&&d.startsWith("0"))d="233"+d.slice(1);
  else if(d.length===9)d="233"+d;
  return d.length>=11?d:"";}
function waText(s){const first=s.name.trim().split(/\s+/)[0]||"";
  return`Hello${first?" "+first:""}, here is your invoice ${invoiceNo(s)} from ${B.name}.`;}
function busy(btn,on,label){btn.disabled=on;if(on){btn.dataset.label=btn.textContent;btn.textContent=label;}else if(btn.dataset.label)btn.textContent=btn.dataset.label;}
async function pdfFile(s){const doc=await makePdf(s);return new File([doc.output("blob")],fileName(s),{type:"application/pdf"});}
function download(file){const a=document.createElement("a");a.href=URL.createObjectURL(file);a.download=file.name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),30000);}
$("#shareBtn").addEventListener("click",async()=>{
  if(problems(S).length)return;const btn=$("#shareBtn"),m=$("#sMsg");busy(btn,true,"Preparing PDF…");
  try{const file=await pdfFile(S),text=waText(S);
    if(navigator.canShare&&navigator.canShare({files:[file]})){
      try{await navigator.share({files:[file],text,title:file.name});}catch(e){if(e.name!=="AbortError")throw e;}
    }else{download(file);const to=waNumber(S.phone);
      if(to)window.open("https://wa.me/"+to+"?text="+encodeURIComponent(text),"_blank","noopener");
      m.textContent="This browser cannot share files: the PDF was downloaded. Attach it in the WhatsApp chat.";}
  }catch(e){m.textContent="The PDF could not be made: "+e.message;}
  finally{busy(btn,false);}
});
$("#pdfBtn").addEventListener("click",async()=>{
  if(problems(S).length)return;const btn=$("#pdfBtn");busy(btn,true,"Preparing PDF…");
  try{download(await pdfFile(S));}catch(e){$("#sMsg").textContent="The PDF could not be made: "+e.message;}
  finally{busy(btn,false);}
});

// ---- 8. Payments and receipts ----------------------------------------------------
// Added 20 Nov 2026 (Daniel): when a customer pays, record the payment
// and send a short receipt that reads like the website's "Your order at
// a glance" panel: the amount received, how it was paid, the order as
// plain counts ("205 bags of cement", "5.5 tons of rods") and the balance
// left. Agreed choices:
//   - Short receipt: no item list or prices; the invoice already has those.
//   - Part payments allowed: every payment gets its own receipt with the
//     balance left after it. The last one shows "PAID IN FULL".
//   - Ways to pay: Mobile Money (with the network), cash, bank transfer.
// Payments are kept with the invoice draft on this device, like the rest
// of the desk; the shared or downloaded receipt PDF is the record.
//
// Receipt number: TCP-RCT-YYMMDD-XXXXXX-n = the payment date, the same six
// characters as the invoice (so a receipt leads back to its invoice), and
// n = 1 for the first payment on the order, 2 for the second, and so on.
// Only the latest payment can be removed, so a receipt already sent never
// has its number taken over by another payment.
const METHOD={momo:"Mobile Money",cash:"Cash",bank:"Bank transfer"};
// Money received before payment number i (counting from 0).
const paidBefore=(s,i)=>s.payments.slice(0,i).reduce((a,p)=>a+p.amount,0);
const paidAll=s=>paidBefore(s,s.payments.length);
function receiptNo(s,i){const d=(s.payments[i].date||today()).replace(/-/g,"").slice(2);return`TCP-RCT-${d}-${s.code}-${i+1}`;}
// "MTN MoMo · Ref 4471829", "Cash", "Bank transfer · Ref GCB-55120".
function methodText(p){
  const how=p.method==="momo"&&p.net?p.net:METHOD[p.method];
  return how+(p.method!=="cash"&&p.ref.trim()?" · Ref "+p.ref.trim():"");
}

// "Your order at a glance": one tile per kind of goods, quantities only,
// in the same words and order as the website's estimate panel
// (quote-engine.js renderEst). Single rods and rods by the ton stay
// separate tiles. An item not in today's price list gets its own tile.
const GLANCE=[
  ["Cement",["bag of cement","bags of cement"]],
  ["Iron Rods (Single Piece)",["individual rod","individual rods"]],
  ["Iron Rods (Per Ton)",["ton of rods","tons of rods"]],
  ["Binding Wire",["roll of binding wire","rolls of binding wire"]],
];
function glance(s){
  const tiles=new Map();
  s.items.forEach(l=>{
    const p=l.pid&&byId(l.pid),known=p&&GLANCE.find(g=>g[0]===p.cat);
    const key=known?known[0]:p?"cat:"+p.cat:"item:"+l.name+"|"+l.unit;
    if(!tiles.has(key))tiles.set(key,{key,n:0,words:known?known[1]:null,name:known?null:(p?p.cat:l.name),unit:l.unit});
    tiles.get(key).n+=l.qty;
  });
  const rank=k=>{const i=GLANCE.findIndex(g=>g[0]===k);return i<0?GLANCE.length:i;};
  return[...tiles.values()].sort((a,b)=>rank(a.key)-rank(b.key)).map(t=>{
    const n=Math.round(t.n*1000)/1000;
    let label;
    if(t.words)label=t.words[n===1?0:1];
    else{const w=UNIT_WORD(t.unit,n);label=w?`${w} of ${t.name}`:`× ${t.name}`;}
    return{n,label};
  });
}

// What is missing before a payment can be recorded.
function payProblems(s,p){
  const out=[];
  if(problems(s).length)return["Finish the invoice above first."];
  const bal=totals(s).total-paidAll(s);
  if(bal<=0)return["This invoice is paid in full."];
  if(!(p.amount>0))out.push("Enter the amount received.");
  else if(p.amount>bal)out.push(`That is more than the balance of ${money(bal)}.`);
  if(!p.date)out.push("Enter the date of the payment.");
  if(!METHOD[p.method])out.push("Choose how the customer paid.");
  return out;
}
// The payment being typed into the "Record a payment" boxes.
function newPay(){
  const method=(document.querySelector('input[name="pm"]:checked')||{}).value||"";
  return{date:$("#pDate").value,amount:toP(num($("#pAmt").value)),method,
    net:method==="momo"?$("#pNet").value:"",ref:method==="cash"?"":$("#pRef").value.trim()};
}
function showPayFields(){
  const m=(document.querySelector('input[name="pm"]:checked')||{}).value;
  $("#netBox").hidden=m!=="momo";$("#refBox").hidden=!m||m==="cash";
  $("#refLbl").textContent=m==="bank"?"Bank reference (optional)":"Transaction ID (optional)";
}
// Redraws the payments card: totals, the list of payments, the form.
function renderPays(){
  if(!$("#paySec"))return;
  if(!Array.isArray(S.payments))S.payments=[];
  const t=totals(S),paid=paidAll(S),bal=t.total-paid,open=!problems(S).length;
  $("#pTot").textContent=isNaN(t.total)?"—":money(t.total);
  $("#pPaid").textContent=money(paid);
  $("#pBal").textContent=isNaN(bal)?"—":bal<=0&&S.payments.length?"Paid in full":money(bal);
  $("#pays").innerHTML=S.payments.map((p,i)=>{const last=i===S.payments.length-1,left=t.total-paidBefore(S,i)-p.amount;
    return`<div class="dk-pay">
      <div class="dk-pay-txt"><b>${i+1}. ${money(p.amount)}</b> <span>${esc(dateText(p.date))} · ${esc(methodText(p))}</span>
        <small>${receiptNo(S,i)} · ${left<=0?"Paid in full":"Balance after: "+money(left)}</small></div>
      <div class="dk-row">
        <button type="button" class="dk-btn primary" data-rshare="${i}"${open?"":" disabled"}>Share receipt</button>
        <button type="button" class="dk-btn" data-rpdf="${i}"${open?"":" disabled"}>Download</button>
        ${last?`<button type="button" class="dk-x" data-rrm="${i}" aria-label="Remove payment ${i+1}">Remove</button>`:""}
      </div></div>`;}).join("");
  $("#payForm").hidden=open&&bal<=0&&S.payments.length>0;
  $("#payBtn").disabled=!open;
  if(!open)$("#pMsg").textContent="Finish the invoice above first.";
  else if($("#pMsg").textContent==="Finish the invoice above first.")$("#pMsg").textContent="";
  if(paid>t.total)$("#pMsg").textContent=`The payments recorded (${money(paid)}) are more than the invoice total. Check the invoice.`;
}
if($("#paySec")){
  $("#pDate").value=today();
  document.querySelectorAll('input[name="pm"]').forEach(r=>r.addEventListener("change",showPayFields));
  showPayFields();
  // "Whole balance" fills in what is still owed.
  $("#pFull").addEventListener("click",()=>{const bal=totals(S).total-paidAll(S);if(bal>0)$("#pAmt").value=(bal/100).toFixed(2);});
  $("#payBtn").addEventListener("click",()=>{
    const p=newPay(),bad=payProblems(S,p);
    if(bad.length){$("#pMsg").textContent=bad.join(" ");return;}
    S.payments.push(p);
    $("#pAmt").value="";$("#pRef").value="";$("#pDate").value=today();
    $("#pMsg").textContent=`Payment ${S.payments.length} recorded. Share the receipt with the customer.`;
    refresh();
  });
  $("#pays").addEventListener("click",async e=>{
    const b=e.target.closest("button");if(!b)return;
    if(b.dataset.rrm!=null){const i=+b.dataset.rrm;
      if(!confirm(`Remove payment ${i+1} (${money(S.payments[i].amount)})? Only do this if it was recorded by mistake.`))return;
      S.payments.splice(i,1);$("#pMsg").textContent="";refresh();return;}
    const i=b.dataset.rshare!=null?+b.dataset.rshare:b.dataset.rpdf!=null?+b.dataset.rpdf:null;
    if(i==null||problems(S).length)return;
    busy(b,true,"Preparing PDF…");
    try{const doc=await makeReceipt(S,i),file=new File([doc.output("blob")],receiptFile(S,i),{type:"application/pdf"});
      if(b.dataset.rpdf!=null)download(file);
      else if(navigator.canShare&&navigator.canShare({files:[file]})){
        try{await navigator.share({files:[file],text:receiptText(S,i),title:file.name});}catch(err){if(err.name!=="AbortError")throw err;}
      }else{download(file);const to=waNumber(S.phone);
        if(to)window.open("https://wa.me/"+to+"?text="+encodeURIComponent(receiptText(S,i)),"_blank","noopener");
        $("#pMsg").textContent="This browser cannot share files: the receipt was downloaded. Attach it in the WhatsApp chat.";}
    }catch(err){$("#pMsg").textContent="The receipt could not be made: "+err.message;}
    finally{busy(b,false);}
  });
}
const receiptFile=(s,i)=>`TCP Receipt ${receiptNo(s,i)}.pdf`;
// The one line that goes with the receipt on WhatsApp.
function receiptText(s,i){const first=s.name.trim().split(/\s+/)[0]||"";
  return`Hello${first?" "+first:""}, here is your receipt ${receiptNo(s,i)} for ${money(s.payments[i].amount)} from ${B.name}. Thank you!`;}

// The receipt PDF: A5 (half an A4 page), easy to read on a phone. Same
// look as the invoice: logo and details on top, charcoal rule with an
// ochre start, then the amount received in a dark band, how it was paid,
// the order at a glance in grey tiles, and the balance.
async function makeReceipt(s,i){
  const{jsPDF,logo}=await pdfKit(),F=window.TCP_PDF_FONTS;
  const doc=new jsPDF({unit:"mm",format:"a5",compress:true});
  [["r","normal"],["s","semibold"],["x","bold"]].forEach(([k,st])=>{doc.addFileToVFS(`M-${k}.ttf`,F[k]);doc.addFont(`M-${k}.ttf`,"Montserrat",st);});
  const p=s.payments[i],no=receiptNo(s,i),t=totals(s);
  const before=paidBefore(s,i),bal=t.total-before-p.amount;
  doc.setProperties({title:`${B.name} Receipt ${no}`,author:B.name,creator:"TCP Invoice Desk"});
  const INK="#131514",MUTE="#5a5a5a",LINE="#dcdcdc",OCHRE="#ff9802",BAND="#f4f4f4";
  const L=12,R=136,W=R-L,TOP=12,pt=n=>n*0.3528;
  const font=(st,size,col)=>{doc.setFont("Montserrat",st);doc.setFontSize(size);doc.setTextColor(col||INK);};
  const txt=(str,x,y,o={})=>{const sp=o.sp||0,w=doc.getTextWidth(str)+sp*Math.max(0,str.length-1);
    doc.text(str,o.right?x-w:x,y,{baseline:"top",charSpace:sp});return w;};
  const label=(str,x,y)=>{font("bold",6.5,MUTE);txt(str.toUpperCase(),x,y,{sp:pt(6.5)*.1});};
  // -- Header: logo left; RECEIPT, number, date and invoice right
  doc.addImage(logo,"PNG",L,TOP,9*5.92329,9);
  font("bold",14);txt("RECEIPT",R,TOP,{right:1,sp:pt(14)*.08});
  const dl=[["Receipt no.",no],["Date",dateText(p.date)],["Invoice",invoiceNo(s)]];
  font("bold",7.5);const vw=Math.max(...dl.map(r=>doc.getTextWidth(r[1])));
  let y=TOP+7;
  dl.forEach(([k,v])=>{font("bold",7.5);txt(v,R,y,{right:1});font("normal",7.5,MUTE);txt(k,R-vw-3,y,{right:1});y+=3.6;});
  y+=3;
  doc.setFillColor(INK);doc.rect(L,y,W,.7,"F");doc.setFillColor(OCHRE);doc.rect(L,y,22,.7,"F");
  y+=.7+5;
  // -- Received from
  label("Received from",L,y);y+=3.6;
  font("bold",11);doc.splitTextToSize(s.name.trim(),W).forEach(l=>{txt(l,L,y);y+=pt(11)*1.35;});
  font("normal",8.5,MUTE);txt(s.phone.trim(),L,y);y+=pt(8.5)*1.4+4;
  // -- Amount received, in a dark band
  const bh=17;
  doc.setFillColor(INK);doc.rect(L,y,W,bh,"F");doc.setFillColor(OCHRE);doc.rect(L,y,1.5,bh,"F");
  font("bold",6.5,"#c9c9c9");txt("AMOUNT RECEIVED",L+5,y+3.2,{sp:pt(6.5)*.1});
  font("bold",19,"#ffffff");txt(money(p.amount),L+5,y+7.4);
  y+=bh+4.5;
  // -- Paid by
  label("Paid by",L,y);label("Payment",R-38,y);y+=3.6;
  font("semibold",9);const how=doc.splitTextToSize(methodText(p),W-44);
  how.forEach((l,j)=>txt(l,L,y+j*pt(9)*1.4));
  txt(`${i+1} of this order`,R-38,y);
  y+=how.length*pt(9)*1.4+5;
  // -- Your order at a glance: grey tiles, two to a row
  label("Your order at a glance",L,y);y+=3.4;
  doc.setFillColor(OCHRE);doc.rect(L,y,8,.8,"F");y+=3;
  const gap=3,tw=(W-gap)/2,pad=3,tiles=glance(s);
  for(let k=0;k<tiles.length;k+=2){
    const row=tiles.slice(k,k+2).map(tl=>{
      font("bold",12);const nt=fmtQ(tl.n),nw=doc.getTextWidth(nt);
      font("normal",8);const inline=doc.getTextWidth(tl.label)<=tw-pad*2-nw-1.5;
      const lines=inline?[tl.label]:doc.splitTextToSize(tl.label,tw-pad*2);
      return{nt,nw,inline,lines,h:pad*2+pt(12)*1.1+(inline?0:lines.length*pt(8)*1.35+.6)};});
    const h=Math.max(...row.map(r=>r.h));
    row.forEach((r,j)=>{const x=L+j*(tw+gap);
      doc.setFillColor(BAND);doc.roundedRect(x,y,tw,h,1.5,1.5,"F");
      font("bold",12);txt(r.nt,x+pad,y+pad);
      font("normal",8,MUTE);
      if(r.inline)txt(r.lines[0],x+pad+r.nw+1.5,y+pad+pt(12)*.32);
      else r.lines.forEach((l,q)=>txt(l,x+pad,y+pad+pt(12)*1.1+.6+q*pt(8)*1.35));});
    y+=h+gap;
  }
  y+=2.5;
  // -- Money: invoice total, earlier payments, this payment, balance
  const rh=pt(9)*1.5+1.6;
  const sumRow=(k,v,st,col)=>{font(st,9,col);txt(k,L,y+.8);txt(v,R,y+.8,{right:1});y+=rh;
    doc.setDrawColor(LINE);doc.setLineWidth(.25);doc.line(L,y,R,y);};
  doc.setFillColor(INK);doc.rect(L,y,W,.5,"F");y+=.5;
  sumRow("Invoice total",money(t.total),"semibold");
  if(before>0)sumRow(i===1?"Paid before (1 payment)":`Paid before (${i} payments)`,money(before),"normal",MUTE);
  sumRow("This payment",money(p.amount),"bold");
  y+=3;
  const gh=pt(11)*1.45+6;
  if(bal<=0){
    doc.setDrawColor(OCHRE);doc.setLineWidth(.8);doc.rect(L+.4,y+.4,W-.8,gh-.8,"S");
    font("bold",11);txt("PAID IN FULL",L+4,y+3,{sp:pt(11)*.08});font("semibold",9,MUTE);txt("Balance "+money(0),R-4,y+3.6,{right:1});
  }else{
    doc.setFillColor(BAND);doc.rect(L,y,W,gh,"F");doc.setFillColor(OCHRE);doc.rect(L,y,1.5,gh,"F");
    font("bold",11);txt("Balance due",L+5,y+3);txt(money(bal),R-4,y+3,{right:1});
  }
  y+=gh;
  // -- Footer
  font("semibold",8);txt(`Thank you for buying from ${B.name}.`,L,193);
  font("normal",6.5,MUTE);txt(`Questions? WhatsApp or call ${B.phone} and quote receipt ${no}.`,L,197.5);
  txt(`${B.website}  ·  ${B.email}`,L,201);
  return doc;
}

// ---- Start ------------------------------------------------------------------------
// If the desk was already unlocked in this tab, open it again straight
// away, with the saved draft. This runs last so every section above is
// ready (20 Nov 2026 fix: it used to run before them, and a reload showed
// an empty desk although the draft was still saved).
try{if(sessionStorage.getItem(UNLOCK)==="1")open()}catch(e){}

// For the tests (and nothing else): the desk's own functions.
window.TCPDesk={parseEstimate,num,invoiceNo,totals,problems,waNumber,waText,makePdf,
  receiptNo,glance,methodText,payProblems,makeReceipt,receiptText,state:()=>S};
})();
