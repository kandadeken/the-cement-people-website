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
  $("#shareBtn").disabled=bad.length>0;
  $("#sMsg").textContent=bad.join(" ");
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

// For the tests (and nothing else): the desk's own functions.
window.TCPDesk={parseEstimate,num,invoiceNo,totals,problems,waNumber,waText,makePdf,state:()=>S};
})();
