/* ===========================================================================
   back-office.js - TCP Back Office, version 1 (22 Nov 2026)
   ---------------------------------------------------------------------------
   Runs the private page /back-office/. Follows "TCP Back Office: Design
   Specification v1.1" (approved by ChatGPT and Daniel, 22 Nov 2026), built
   on "TCP Invoice Desk on Supabase: Design (v2.1)". It grew out of the
   Invoice Desk (phase 1); the invoice form is that desk, unchanged.

   The one rule: Supabase is the only ledger. This page asks; the database
   decides. Customers, drafts, invoice numbers, totals, statuses and the Home
   figures come from the database (supabase/migrations/). The phone keeps
   only work that has not been saved yet, and never a saved record.

   Sections:
     1. Settings and helpers   (money in pesewas, reading numbers)
     2. The connection         (Supabase, or a stand-in during tests)
     3. Signing in             (email link or code, staff check, signing out)
     4. Reading the estimate   (unchanged from PR #31)
     5. The invoice being prepared (kept on this phone until saved)
     6. Saving and issuing     (the database functions); discarding a draft
     7. The PDF                (drawn from the issued record only)
     8. Sharing                (PDF + the message copied for the caption)
     9. Screens and the address (Home, Invoices, one invoice, New invoice)
    10. Start
   =========================================================================== */
(()=>{
// ---- 1. Settings and helpers ------------------------------------------------
const D=JSON.parse(document.getElementById("desk-data").textContent);
const CUR=D.currency,B=D.business;
// TCP is not VAT-registered (20 Nov 2026), so this is an ordinary invoice.
// If TCP registers for VAT, change this to "Proforma invoice": official tax
// invoices would then come from GRA E-VAT.
const DOC_TITLE="Invoice";
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
// On screen, money is handled in whole pesewas (GH₵1.00 = 100) so nothing
// picks up rounding errors; the database stores exact amounts as well.
const toP=c=>Math.round(Number(c)*100);
const money=p=>CUR+(p/100).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
const fmtQ=n=>(+n).toLocaleString("en-US",{maximumFractionDigits:3});
// Reads a number however it was typed or written: "1,392.00", "1.392,00",
// "2,5", "50,000", "GH₵98.00". NaN when there is no number.
function num(s){
  s=String(s==null?"":s).replace(/[^\d.,-]/g,"");
  if(!s)return NaN;
  const lc=s.lastIndexOf(","),ld=s.lastIndexOf(".");
  if(lc>=0&&ld>=0){s=lc>ld?s.replace(/\./g,"").replace(",","."):s.replace(/,/g,"");}
  else if(lc>=0){s=/^-?\d{1,3}(,\d{3})+$/.test(s)?s.replace(/,/g,""):s.replace(",",".");}
  else if((s.match(/\./g)||[]).length>1){s=s.replace(/\./g,"");}
  return parseFloat(s);
}
const UNIT_WORD=(u,n)=>{const one=+n===1;
  if(/bag/i.test(u))return one?"bag":"bags";
  if(/^ton$/i.test(u))return one?"ton":"tons";
  if(/rod|ft/i.test(u))return one?"rod":"rods";
  if(/roll/i.test(u))return one?"roll":"rolls";
  if(/trip/i.test(u))return one?"trip":"trips";
  return "";};
// A random id for a request, made once and kept for every retry of it.
const newId=()=>crypto.randomUUID?crypto.randomUUID():"10000000-1000-4000-8000-100000000000".replace(/[018]/g,c=>(c^crypto.getRandomValues(new Uint8Array(1))[0]&15>>c/4).toString(16));
function today(){const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");}
const show=(sel,on)=>{const el=$(sel);if(el)el.hidden=!on;};

// ---- 2. The connection ------------------------------------------------------
// The page carries only the project address and the public "anon" key, both
// safe in a browser: every permission is enforced inside the database. The
// secret service-role key never appears here.
// During tests a stand-in is supplied as window.TCPDeskApi instead.
const api=window.TCPDeskApi||supabaseApi();
function supabaseApi(){
  if(!D.supabaseUrl||!D.supabaseKey||!window.supabase)return null;
  const sb=window.supabase.createClient(D.supabaseUrl,D.supabaseKey,{auth:{persistSession:true,autoRefreshToken:true}});
  const out=r=>{if(r.error)throw r.error;return r.data;};
  return{
    // The email's link brings the person back to this page, signed in.
    // (Supabase's free plan sends its standard email, which has a link but
    // no 6-digit code; the code box is for when TCP's own email sending is
    // set up and the template can include the code.) The page address must
    // be allowed under Authentication -> URL Configuration.
    sendCode:email=>sb.auth.signInWithOtp({email,options:{shouldCreateUser:false,emailRedirectTo:location.origin+location.pathname}}).then(out),
    verifyCode:(email,token)=>sb.auth.verifyOtp({email,token,type:"email"}).then(out),
    user:async()=>{const{data}=await sb.auth.getSession();return data.session?data.session.user:null;},
    // "local": forget the session on this phone even when it has expired
    // (a global sign-out needs a working session to reach the server).
    signOut:()=>sb.auth.signOut({scope:"local"}).then(()=>null),
    // Supabase runs this callback while it holds its sign-in lock (see the
    // start of the desk, section 9, for how that is handled).
    onSignOut:fn=>sb.auth.onAuthStateChange(ev=>{if(ev==="SIGNED_OUT")fn();}),
    // Name and role of the signed-in person; refused unless active staff.
    myStaff:()=>sb.rpc("my_staff").then(out),
    products:()=>sb.from("products").select("id,site_id,name,category,unit,current_price").order("category").order("id").then(out),
    customersWithPhone:phone=>sb.rpc("customers_with_phone",{p_phone:phone}).then(out),
    createCustomer:(phone,name,requestId)=>sb.rpc("create_customer",{p_phone:phone||null,p_name:name||null,p_request_id:requestId||null}).then(out),
    saveDraft:a=>sb.rpc("save_draft_invoice",a).then(out),
    issue:id=>sb.rpc("issue_invoice",{p_invoice_id:id}).then(out),
    document:id=>sb.rpc("invoice_document",{p_invoice_id:id}).then(out),
    // Discarding a draft = the owner-only cancel_invoice (kept, with a reason).
    cancel:(id,reason)=>sb.rpc("cancel_invoice",{p_invoice_id:id,p_reason:reason}).then(out),
    // The Home figures, worked out by the database (back_office_home).
    home:()=>sb.from("back_office_home").select("owed,unpaid,part_paid,overdue,drafts").single().then(out),
    // A page of the Invoices list (invoice_list). Order: newest first, then
    // the id, so two invoices started at the same moment always keep the same
    // order and paging never skips or repeats one. terms: see searchTerms().
    list:({status,terms,offset,limit})=>{
      let q=sb.from("invoice_list").select("id,invoice_no,state,status,issued_at,created_at,due_date,total,balance,billed_to_name,billed_to_phone",{count:"exact"})
        .order("created_at",{ascending:false}).order("id",{ascending:false}).range(offset,offset+limit-1);
      if(status==="owed")q=q.in("status",["unpaid","part_paid","overdue"]);
      else if(status&&status!=="all")q=q.eq("status",status);
      if(terms&&terms.length)q=q.or(terms.map(t=>`${t.col}.ilike.${t.pattern}`).join(","));
      return q.then(r=>{if(r.error)throw r.error;return{rows:r.data||[],count:r.count||0};});
    },
  };
}
// What kind of failure an error is:
//   "revoked" - not (or no longer) active TCP staff: clear and sign out
//   "expired" - the sign-in itself ran out: sign in again, work is kept
//   "offline" - the request never got an answer
//   "refused" - the database said no, with a reason to show
function kind(e){
  const m=String(e&&(e.message||e)||"");
  if(/only TCP staff/i.test(m))return"revoked";
  if((e&&(e.code==="PGRST301"||e.code==="PGRST303"||e.status===401||e.name==="AuthSessionMissingError"))
     ||/JWT expired|invalid jwt|refresh token|session (is )?missing/i.test(m))return"expired";
  if(e instanceof TypeError||/fetch|network|offline|timed? ?out/i.test(m))return"offline";
  return"refused";
}

// ---- 3. Signing in -------------------------------------------------------------
// A sign-in email is sent to the staff member. Its link brings them back to
// this page, signed in (Supabase reads the session from the address when the
// page opens). Supabase's free plan only sends its standard email, which has
// the link but no 6-digit code; once TCP has its own email sending, the
// email can carry a code too, typed into the box below. A code works
// whichever browser opens the email, while a link can open in a different
// browser on Android. Staff join by invitation only, so no account is ever
// created from this page.
let ME=null,PRODUCTS=[];
// Whether the email carries a 6-digit code (see emailCode in the page's
// settings). Off on Supabase's free-plan email, which has only the link, so
// the code box stays hidden. (The test stand-in can switch it on.)
const CODE=!!(D.emailCode||(api&&api.emailCode));
function screen(name){["#setup","#signin","#noaccess","#tool"].forEach(s=>show(s,s==="#"+name));}
$("#emailForm").addEventListener("submit",async e=>{
  e.preventDefault();const m=$("#signMsg"),email=$("#email").value.trim();
  if(!email){m.textContent="Enter your email address.";return;}
  m.textContent="Sending the sign-in email…";
  try{await api.sendCode(email);m.textContent=CODE?`A sign-in email was sent to ${email}. Type the 6-digit code from it below, or open its link on this phone.`
                                       :`A sign-in email was sent to ${email}. It can take a minute to arrive. Open its link on this phone.`;
    if(CODE){show("#codeForm",true);$("#code").focus();}}
  catch(err){m.textContent=kind(err)==="offline"?"No connection. Check your signal and try again.":"The sign-in email could not be sent. Check the email address, or ask the owner to invite you.";}
});
$("#codeForm").addEventListener("submit",async e=>{
  e.preventDefault();const m=$("#signMsg"),code=$("#code").value.replace(/\D/g,"");
  if(code.length!==6){m.textContent="The code has 6 digits.";return;}
  m.textContent="Checking…";
  try{await api.verifyCode($("#email").value.trim(),code);$("#code").value="";m.textContent="";await enter();}
  catch(err){m.textContent=kind(err)==="offline"?"No connection. Check your signal and try again.":"That code is not right or has expired. Ask for a new one.";}
});
// After signing in (or on opening the page with a session already there):
// only active staff get the desk; anyone else sees "ask the owner".
async function enter(){
  const u=await api.user();
  if(!u){screen("signin");return;}
  let st=null;
  try{st=await api.myStaff();}
  catch(err){
    const k=kind(err);
    if(k==="offline"){screen("signin");$("#signMsg").textContent="No connection. Check your signal and reload.";return;}
    if(k==="expired"){await expire();return;}
    if(k!=="revoked")throw err;
  }
  if(!st){
    // Not (or no longer) staff: nothing of TCP's stays on this phone.
    try{localStorage.removeItem("tcp-desk-work-"+u.id)}catch(e){}
    ME=null;screen("noaccess");$("#noEmail").textContent=u.email||"";return;
  }
  ME={id:u.id,name:st.full_name,role:st.role};
  $("#who").textContent=`${ME.name} · ${ME.role}`;
  // Finance sees Home and the invoices, read-only (spec section 7): no New
  // invoice tab. The database refuses them saving or issuing anyway.
  ["#tabNew","#hNew","#newBtn2"].forEach(s=>show(s,canEdit()));
  try{PRODUCTS=await api.products()||[];if(!PRODUCTS.length)await stillStaff();}
  catch(err){const k=kind(err);if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");if(k==="expired")return expire();}
  fillAdd();screen("tool");restore();await route();
}
// Plain reads (the price list, a phone lookup) come back EMPTY rather than
// refused once someone's access is removed. So an empty answer is checked:
// my_staff() refuses clearly, and that refusal signs them out.
async function stillStaff(){await api.myStaff();}
// Removing access (or a session that can no longer be used) clears every
// record from the screen and the phone's memory, then signs out
// (Design v2.1, point C).
async function revoke(why){
  const key=draftKey();
  try{localStorage.removeItem(key)}catch(e){}
  await leave(why||"You have been signed out.");
}
// The sign-in ran out (not the same as access removed): the unsaved work
// stays on this phone, under this staff member's name only, and comes back
// when they sign in again. Everything is cleared from the screen meanwhile.
async function expire(){
  keep();
  await leave("Your sign-in has expired. Sign in again: your unsaved work is kept on this phone.");
}
// Clears the screen and memory, then signs out. ME is cleared first, so the
// "signed out" notice that follows does not run a second time.
async function leave(why){
  S=blank();DOC=null;ME=null;PRODUCTS=[];NOTE="";LOOKED="";HERE="#/";
  ["#items","#issued","#matches","#custPicked","#rows","#recent","#viewLines","#unsavedNote"].forEach(s=>{const el=$(s);if(el)el.innerHTML="";});
  ["#hOwed","#hUnpaid","#hPart","#hOverdue","#hDrafts"].forEach(s=>{$(s).textContent="—";});
  ["#guard","#discardBox","#copyBox"].forEach(s=>show(s,false));
  ["#paste","#cName","#cPhone"].forEach(s=>{const el=$(s);if(el)el.value="";});
  screen("signin");$("#signMsg").textContent=why;
  try{await api.signOut();}catch(e){}
}
$("#signOut").addEventListener("click",()=>revoke("Signed out."));
$("#noSignOut").addEventListener("click",()=>revoke("Signed out."));

// ---- 4. Reading the estimate (unchanged from PR #31) -------------------------
// The website writes (quote-engine.js, renderEst):
//   *Estimate TCP-261120-MEBLV2* (20 November 2026)
//   *Drop-off location:* Buduburam
//   1. Iron rod 12 mm (30 ft rod)
//      24 × GH₵58.00 = GH₵1,392.00
// WhatsApp may drop the * marks when a message is forwarded, so they are
// optional here. Items are matched to today's price list in the database by
// name and unit.
function parseEstimate(text){
  const t=String(text||"").replace(/\r/g,"").replace(/ /g," ");
  const ref=(t.match(/TCP-(\d{6})-([A-Z0-9]{6})\b/)||[]);
  const loc=(t.match(/Drop-off location:\*?\s*(.+)/i)||[])[1];
  const lines=t.split("\n"),items=[];
  const same=s=>String(s).toLowerCase().replace(/\s+/g," ").trim();
  for(let i=0;i<lines.length;i++){
    const m=lines[i].match(/^\s*\d+\.\s*(.+?)\s*\(([^()]+)\)\s*$/);
    if(!m)continue;
    let j=i+1;while(j<lines.length&&!lines[j].trim())j++;
    const q=(lines[j]||"").match(/([\d.,]+)\s*[×xX*]\s*(?:GH[₵¢S]\s*)?([\d.,]+)/);
    if(!q)continue;
    const name=m[1].trim(),unit=m[2].trim(),qty=num(q[1]),quoted=num(q[2]);
    if(!(qty>0))continue;
    let p=PRODUCTS.find(x=>same(x.name)===same(name)&&same(x.unit)===same(unit));
    if(!p){const n=PRODUCTS.filter(x=>same(x.name)===same(name));if(n.length===1)p=n[0];}
    items.push(p?{kind:"product",pid:p.id,name:p.name,unit:p.unit,qty,price:toP(p.current_price),list:toP(p.current_price),quoted:isNaN(quoted)?null:toP(quoted)}
               :{kind:"product",pid:null,name,unit,qty,price:isNaN(quoted)?NaN:toP(quoted),list:null,quoted:isNaN(quoted)?null:toP(quoted)});
    i=j;
  }
  return{ref:ref[0]||null,loc:loc?loc.replace(/\*+$/,"").trim():"",items};
}

// ---- 5. The invoice being prepared -------------------------------------------
// S is the work in progress. It is kept on this phone (per staff member)
// until it is saved, so a dropped connection loses nothing. Once saved, the
// draft lives in the database (S.invoiceId) and is reopened from there.
let S=blank(),DOC=null;
// NOTE: the last message from saving or issuing ("Draft saved.", "Not
// saved: no connection…"). It stays until the next edit.
let NOTE="",LOOKED="";
function blank(){return{invoiceId:null,draftRequest:newId(),customerRequest:newId(),ref:null,customerId:null,customerCode:null,
  name:"",phone:"",site:"",contact:"",contactPhone:"",items:[],dl:"pending",fee:"",due:"",note:"",dirty:false};}
const draftKey=()=>"tcp-desk-work-"+(ME?ME.id:"none");
function keep(){if(!ME)return;try{localStorage.setItem(draftKey(),JSON.stringify(S))}catch(e){}}
function forget(){try{localStorage.removeItem(draftKey())}catch(e){}}
// Brings back unsaved work from this phone (for this staff member only).
// Which screen shows is decided by the address (section 9). A saved draft
// or an issued invoice is never shown from the phone's copy: it is read
// again from the database.
function restore(){
  let d=null;try{d=JSON.parse(localStorage.getItem(draftKey())||"null")}catch(e){}
  S=d?{...blank(),...d}:blank();
}
// Unsaved work that would be lost if this invoice were replaced.
const unsaved=()=>S.dirty&&!!(S.items.length||S.name.trim()||S.phone.trim());
function fillAdd(){const g={};PRODUCTS.forEach(p=>(g[p.category]=g[p.category]||[]).push(p));
  $("#addSel").innerHTML=Object.entries(g).map(([c,l])=>`<optgroup label="${esc(c)}">${l.map(p=>`<option value="${p.id}">${esc(p.name)} (${esc(p.unit)}) · ${money(toP(p.current_price))}</option>`).join("")}</optgroup>`).join("");}
const lineTotal=l=>Math.round(l.price*l.qty);
function totals(s){const mat=s.items.reduce((a,l)=>a+lineTotal(l),0);
  const fee=s.dl==="fee"?toP(num(s.fee)||0):0;return{mat,fee,total:mat+fee};}
const DL_TEXT={pending:"Not agreed yet",free:"Free delivery",fee:"Delivery fee",pickup:"Customer pickup"};
// What is missing before the invoice can be saved or issued. The database
// checks everything again; this only saves a wasted trip.
function problems(s,forIssue){
  const out=[];
  if(!s.items.length)out.push("Add at least one item.");
  if(s.items.some(l=>!l.pid))out.push("An item is not in today's price list: remove it or add the right product.");
  if(s.items.some(l=>!(l.qty>0)))out.push("Every item needs a quantity.");
  if(s.items.some(l=>!(l.price>=0)||isNaN(l.price)))out.push("Every item needs a price.");
  if(!s.name.trim()&&!s.phone.replace(/\D/g,""))out.push("Add the customer's phone number or name.");
  if(forIssue&&s.dl==="pending")out.push("Agree the delivery with the customer first.");
  if(s.dl==="fee"&&!(num(s.fee)>0))out.push("Enter the delivery fee.");
  return out;
}
// showForm(): see section 9.
function itemsHTML(){
  if(!S.items.length)return`<p class="dk-help">No items yet. Add them below.</p>`;
  return S.items.map((l,i)=>{
    const changed=l.list!=null&&l.price!==l.list,quotedDiff=l.quoted!=null&&l.list!=null&&l.quoted!==l.list;
    return`<div class="dk-line" data-i="${i}">
      <div class="dk-ln-name"><b>${i+1}. ${esc(l.name)}</b> <small>per ${esc(l.unit)}</small>
        ${l.pid?"":`<span class="dk-flag">Not in today's price list: remove it and add the right product</span>`}
        ${quotedDiff?`<span class="dk-note">The estimate said ${money(l.quoted)}; today's price is ${money(l.list)}.</span>`:""}</div>
      <label>Qty<input data-f="qty" type="text" inputmode="decimal" value="${fmtQ(l.qty)}" aria-label="Quantity of ${esc(l.name)}"></label>
      <label>Price (GH₵)<input data-f="price" type="text" inputmode="decimal" value="${isNaN(l.price)?"":(l.price/100).toFixed(2)}" aria-label="Price of ${esc(l.name)}"></label>
      <div class="dk-amt">${isNaN(lineTotal(l))?"—":money(lineTotal(l))}${changed?`<small>Agreed price (list ${money(l.list)})</small>`:""}</div>
      <button type="button" class="dk-x" data-rm="${i}" aria-label="Remove ${esc(l.name)}">Remove</button>
    </div>`}).join("");
}
function render(){$("#items").innerHTML=itemsHTML();show("#feeBox",S.dl==="fee");refresh();}
function changed(){S.dirty=true;NOTE="";refresh();}
// Totals and the state line (everything except the item boxes).
function refresh(){const t=totals(S),bad=problems(S,true);
  show("#discardBtn",!!(ME&&ME.role==="owner"&&S.invoiceId));
  $("#sMat").textContent=isNaN(t.mat)?"—":money(t.mat);
  $("#sDel").textContent=S.dl==="fee"?money(t.fee):S.dl==="pending"?"Not agreed yet":DL_TEXT[S.dl];
  $("#sTot").textContent=isNaN(t.total)?"—":money(t.total);
  $("#issueBtn").disabled=bad.length>0;$("#saveBtn").disabled=problems(S,false).length>0;
  $("#sMsg").textContent=NOTE||bad.join(" ");
  $("#state").textContent=S.invoiceId?(S.dirty?"Draft: changes not saved yet":"Draft saved"):(S.items.length?"Not saved yet":"");
  keep();}
$("#items").addEventListener("input",e=>{
  const row=e.target.closest(".dk-line");if(!row)return;const l=S.items[+row.dataset.i];
  if(e.target.dataset.f==="qty")l.qty=num(e.target.value);
  if(e.target.dataset.f==="price")l.price=toP(num(e.target.value));
  const a=row.querySelector(".dk-amt"),ch=l.list!=null&&l.price!==l.list;
  a.innerHTML=(isNaN(lineTotal(l))?"—":money(lineTotal(l)))+(ch?`<small>Agreed price (list ${money(l.list)})</small>`:"");
  changed();
});
$("#items").addEventListener("change",()=>render());
$("#items").addEventListener("click",e=>{const b=e.target.closest("[data-rm]");if(!b)return;S.items.splice(+b.dataset.rm,1);S.dirty=true;render();});
$("#addBtn").addEventListener("click",()=>{const p=PRODUCTS.find(x=>String(x.id)===$("#addSel").value);if(!p)return;
  S.items.push({kind:"product",pid:p.id,name:p.name,unit:p.unit,qty:1,price:toP(p.current_price),list:toP(p.current_price),quoted:null});S.dirty=true;render();});
[["#cSite","site"],["#cContact","contact"],["#cContactPhone","contactPhone"],["#fee","fee"],["#iDue","due"],["#iNote","note"]]
  .forEach(([sel,k])=>$(sel).addEventListener("input",e=>{S[k]=e.target.value;changed();}));
// Changing the name or phone means a different (or new) customer.
[["#cName","name"],["#cPhone","phone"]].forEach(([sel,k])=>$(sel).addEventListener("input",e=>{
  // Different details are a different request: a new request id.
  S[k]=e.target.value;S.customerId=null;S.customerCode=null;S.customerRequest=newId();$("#custPicked").textContent="";changed();}));
document.querySelectorAll('input[name="dl"]').forEach(r=>r.addEventListener("change",()=>{S.dl=r.value;S.dirty=true;render();}));

// Existing customers with this phone number (families and companies can
// share one): tap one to use it, otherwise a new customer is added on save.
$("#cPhone").addEventListener("change",findCustomers);
async function findCustomers(){
  const ph=S.phone.replace(/\D/g,""),box=$("#matches");
  // Leaving the box fires "change" again; searching again then would
  // replace the buttons just as one is tapped.
  if(ph===LOOKED)return;
  LOOKED=ph;
  if(ph.length<9){box.innerHTML="";return;}
  try{const list=await api.customersWithPhone(S.phone);
    if(!list||!list.length){await stillStaff();box.innerHTML=`<p class="dk-help">New customer: they will be added when the invoice is saved.</p>`;return;}
    box.innerHTML=`<p class="dk-help">Customers with this number. Tap one to use it:</p>`+list.map(c=>
      `<button type="button" class="dk-btn dk-match" data-cid="${c.id}" data-code="${esc(c.code)}" data-name="${esc(c.name||"")}">${esc(c.name||"(no name)")} · ${esc(c.code)}</button>`).join("");
  }catch(err){const k=kind(err);
    if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
    if(k==="expired")return expire();
    LOOKED="";box.innerHTML=`<p class="dk-help">Could not check existing customers (no connection). You can carry on.</p>`;}
}
$("#matches").addEventListener("click",e=>{const b=e.target.closest("[data-cid]");if(!b)return;
  S.customerId=+b.dataset.cid;S.customerCode=b.dataset.code;S.phone=$("#cPhone").value;if(b.dataset.name){S.name=b.dataset.name;$("#cName").value=S.name;}
  $("#custPicked").textContent=`Existing customer ${S.customerCode}`;$("#matches").innerHTML="";S.dirty=true;refresh();});

$("#readBtn").addEventListener("click",()=>{
  const r=parseEstimate($("#paste").value),m=$("#readMsg");
  if(!r.items.length){m.textContent="No items found. Paste the whole estimate message, from \"Hello The Cement People\" to the total.";return;}
  S={...blank(),ref:r.ref,site:r.loc,items:r.items,dirty:true};
  const odd=r.items.filter(l=>!l.pid).length,moved=r.items.filter(l=>l.quoted!=null&&l.list!=null&&l.quoted!==l.list).length;
  m.textContent=`Read ${r.items.length} ${r.items.length===1?"item":"items"}${r.ref?" from estimate "+r.ref:""}.`
    +(moved?` ${moved} ${moved===1?"price has":"prices have"} changed since the estimate: today's price is used, edit it if you agreed otherwise.`:"")
    +(odd?` ${odd} ${odd===1?"item is":"items are"} not in today's price list: please check.`:"");
  showForm();$("#cPhone").focus();
});
$("#blankBtn").addEventListener("click",()=>{S={...blank(),dirty:true};$("#readMsg").textContent="";showForm();$("#cPhone").focus();});
// "New invoice" buttons: a fresh start. Unsaved changes are asked about
// first (Save it / Discard changes / Go back).
async function newInvoice(){
  if(unsaved()&&(await askGuard())==="back")return;
  S=blank();DOC=null;NOTE="";LOOKED="";forget();
  go("#/new");}
$("#newBtn").addEventListener("click",newInvoice);$("#newBtn2").addEventListener("click",newInvoice);

// ---- 6. Saving and issuing --------------------------------------------------
// Save: the customer (found or added), then the whole draft in one step
// (save_draft_invoice). A new draft carries a request id made once, so a
// retry after a dropped connection returns the same draft, never a second.
// Issue: save, then issue_invoice. The database gives the number, freezes
// who is billed and who issued, and locks the invoice.
function busy(btn,on,label){btn.disabled=on;if(on){btn.dataset.label=btn.textContent;btn.textContent=label;}else if(btn.dataset.label)btn.textContent=btn.dataset.label;}
function failed(err,where){
  const k=kind(err);
  if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
  if(k==="expired")return expire();
  const text=k==="offline"?"Not saved: no connection. Your work is kept on this phone. Tap again when you have signal."
                          :"Not saved: "+String(err&&err.message||err);
  if(!where||where==="#sMsg"){NOTE=text;refresh();}else $(where).textContent=text;
}
async function ensureCustomer(){
  if(S.customerId)return S.customerId;
  // A retry after a dropped connection may already have added them:
  // reuse an exact match (same phone and name) instead of adding a twin.
  if(S.phone.replace(/\D/g,"").length>=9){
    const list=await api.customersWithPhone(S.phone)||[];
    const same=list.find(c=>(c.name||"").trim().toLowerCase()===S.name.trim().toLowerCase());
    if(same){S.customerId=same.id;S.customerCode=same.code;return same.id;}
  }
  // The request id makes a retry return the customer already added, even
  // one with no phone number (nothing to look them up by).
  const c=await api.createCustomer(S.phone.trim(),S.name.trim(),S.customerRequest);
  S.customerId=c.id;S.customerCode=c.code;keep();
  return c.id;
}
function linesForDb(){
  const out=S.items.map(l=>({kind:"product",product_id:l.pid,quantity:l.qty,unit_price:l.price/100}));
  if(S.dl==="fee")out.push({kind:"delivery",quantity:1,unit_price:toP(num(S.fee))/100,
    description:"Delivery"+(S.site.trim()?" to "+S.site.trim():""),unit:"trip"});
  return out;
}
async function save(){
  const custId=await ensureCustomer();
  const id=await api.saveDraft({p_invoice_id:S.invoiceId,p_customer_id:custId,
    p_deliver_to_location:S.dl==="pickup"?null:(S.site.trim()||null),p_deliver_to_contact:S.contact.trim()||null,
    p_deliver_to_phone:S.contactPhone.trim()||null,p_due_date:S.due||null,
    p_notes:[S.dl==="pickup"?"Customer pickup":S.dl==="free"?"Free delivery":"",S.ref?"Estimate "+S.ref:"",S.note.trim()].filter(Boolean).join("\n")||null,
    p_lines:linesForDb(),p_request_id:S.invoiceId?null:S.draftRequest});
  const first=!S.invoiceId;
  S.invoiceId=id;S.dirty=false;refresh();
  // A new draft now has an address of its own, so a reload (or the list)
  // reopens it from the database.
  if(first){history.replaceState(null,"","#/invoice/"+id);HERE=location.hash;}
  return id;
}
$("#saveBtn").addEventListener("click",async()=>{
  if(problems(S,false).length)return;const btn=$("#saveBtn");busy(btn,true,"Saving…");NOTE="";
  try{await save();NOTE="Draft saved.";}catch(err){failed(err);}finally{busy(btn,false);refresh();}
});
$("#issueBtn").addEventListener("click",async()=>{
  if(problems(S,true).length)return;
  if(!confirm("Issue this invoice? It gets its number and can no longer be changed (it can only be cancelled)."))return;
  const btn=$("#issueBtn");busy(btn,true,"Issuing…");NOTE="";
  try{const id=await save();
    try{await api.issue(id);}
    catch(err){
      // The connection may have dropped after the database issued it:
      // look before reporting a failure.
      const doc=await api.document(id).catch(()=>null);
      if(!doc||doc.state!=="issued")throw err;
    }
    await go("#/invoice/"+id);
  }catch(err){failed(err);}finally{busy(btn,false);}
});

// An invoice from the database. A draft goes into the form for the owner
// and sales; everything else (issued, cancelled, or a draft seen by
// finance) is shown read-only, with Share and PDF for an issued one.
async function openInvoice(id){
  let doc;
  try{doc=await api.document(id);}catch(err){view("#invV");showOnly("#issuedSec");$("#viewTitle").textContent="Invoice";$("#issued").innerHTML="";$("#viewLines").innerHTML="";show("#shareRow",false);show("#shareHelp",false);return readFailed(err,"#iMsg");}
  if(doc.state==="draft"&&canEdit()){S=fromDraft(doc);showForm();return;}
  showView(doc);
}
const STATUS={draft:"Draft",unpaid:"Unpaid",part_paid:"Part paid",overdue:"Overdue",paid:"Paid",cancelled:"Cancelled"};
function showView(doc){
  DOC=doc;
  // An invoice just issued (or discarded) is no longer work in progress.
  if(S.invoiceId===doc.id){S=blank();forget();}
  showOnly("#issuedSec");
  const issued=doc.state==="issued",draft=doc.state==="draft";
  $("#viewTitle").textContent=draft?"Draft (read-only)":doc.state==="cancelled"?"Cancelled invoice":"Invoice "+(doc.invoice_no||"");
  const notes=String(doc.notes||"").split("\n");
  // As agreed: pickup, free, a fee line, or not agreed yet (a draft).
  const to=doc.deliver_to_location?" to "+doc.deliver_to_location:"",fee=(doc.lines||[]).some(l=>l.kind==="delivery");
  const dlv=notes.includes("Customer pickup")?"Customer pickup":notes.includes("Free delivery")?"Free delivery"+to:fee?"Delivery fee"+to:"Not agreed yet"+to;
  const row=(k,v,cls)=>v?`<div${cls?` class="${cls}"`:""}><span>${k}</span><b>${esc(v)}</b></div>`:"";
  $("#issued").innerHTML=`<div class="dk-sum">
    ${row("Invoice number",doc.invoice_no||"No number yet (draft)","dk-no-line")}
    ${row("Status",STATUS[doc.status]||doc.status)}
    ${row("Billed to",[doc.billed_to_name,doc.billed_to_phone].filter(Boolean).join(" · "))}
    ${row("Issued",doc.issued_at?dateText(doc.issued_at):"")}
    ${row("Issued by",doc.issued_by||"")}
    ${row("Pay by",doc.due_date?dateText(doc.due_date):"")}
    ${row("Delivery",dlv)}
    ${row("Cancelled because",doc.state==="cancelled"?doc.cancel_reason||"":"")}
    <div class="dk-total"><span>Total</span><b>${money(toP(doc.total))}</b></div></div>`;
  $("#viewLines").innerHTML=(doc.lines||[]).map((l,i)=>`<div class="dk-vline"><span>${i+1}. ${esc(l.description)}<small>${fmtQ(l.quantity)} ${esc(UNIT_WORD(l.unit,l.quantity)||l.unit||"")} × ${money(toP(l.unit_price))}</small></span><b>${money(toP(l.line_total))}</b></div>`).join("");
  $("#iMsg").textContent="";show("#copyBox",false);
  show("#shareRow",issued);show("#shareHelp",issued);
  $("#shareBtn").disabled=!issued;$("#pdfBtn").disabled=!issued;
}
function fromDraft(doc){
  const items=doc.lines.filter(l=>l.kind==="product").map(l=>{const p=PRODUCTS.find(x=>x.id===l.product_id);
    return{kind:"product",pid:l.product_id,name:l.description,unit:l.unit,qty:+l.quantity,price:toP(l.unit_price),list:p?toP(p.current_price):null,quoted:null};});
  const fee=doc.lines.find(l=>l.kind==="delivery");
  const notes=String(doc.notes||"").split("\n");
  const dl=fee?"fee":notes.includes("Customer pickup")?"pickup":notes.includes("Free delivery")?"free":"pending";
  const ref=(notes.find(n=>/^Estimate /.test(n))||"").replace(/^Estimate /,"")||null;
  return{...blank(),invoiceId:doc.id,customerId:doc.customer_id,customerCode:doc.customer_code,ref,
    name:doc.billed_to_name||"",phone:doc.billed_to_phone||"",site:doc.deliver_to_location||"",
    contact:doc.deliver_to_contact||"",contactPhone:doc.deliver_to_phone||"",items,dl,
    fee:fee?String(fee.unit_price):"",due:doc.due_date||"",
    note:notes.filter(n=>n&&n!=="Customer pickup"&&n!=="Free delivery"&&!/^Estimate /.test(n)).join("\n"),dirty:false};
}

// ---- 7. The PDF --------------------------------------------------------------
// Drawn only from an issued invoice's database record (invoice_document):
// the frozen "billed to", the lines as sold, the totals the database
// calculated. So any invoice can be produced again, exactly, at any time.
// The layout is the one from PR #31 (the website's estimate look).
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
function logoPng(){return new Promise((ok,fail)=>{const img=new Image();
  img.onload=()=>{const c=document.createElement("canvas");c.width=2369;c.height=400;c.getContext("2d").drawImage(img,0,0,c.width,c.height);ok(c.toDataURL("image/png"));};
  img.onerror=()=>fail(new Error("Could not load the logo"));img.src="/brand/tcp-logo-horizontal-on-light.svg";});}
function dateText(iso){const[y,m,d]=String(iso||today()).slice(0,10).split("-").map(Number);
  return new Date(y,m-1,d).toLocaleDateString("en-GB",{year:"numeric",month:"long",day:"numeric"});}
const fileName=doc=>`TCP Invoice ${doc.invoice_no}.pdf`;
async function makePdf(doc){
  if(!doc||doc.state!=="issued")throw new Error("Only an issued invoice has a PDF");
  const{jsPDF,logo}=await pdfKit(),F=window.TCP_PDF_FONTS;
  const pdf=new jsPDF({unit:"mm",format:"a4",compress:true});
  [["r","normal"],["s","semibold"],["x","bold"]].forEach(([k,st])=>{pdf.addFileToVFS(`M-${k}.ttf`,F[k]);pdf.addFont(`M-${k}.ttf`,"Montserrat",st);});
  pdf.setProperties({title:`${B.name} ${DOC_TITLE} ${doc.invoice_no}`,author:B.name,creator:"TCP Back Office"});
  const INK="#131514",MUTE="#5a5a5a",LINE="#dcdcdc",OCHRE="#ff9802",BAND="#f4f4f4";
  const L=14,R=196,W=R-L,TOP=16,BOTTOM=282,pt=n=>n*0.3528;
  const font=(st,size,col)=>{pdf.setFont("Montserrat",st);pdf.setFontSize(size);pdf.setTextColor(col||INK);};
  const txt=(str,x,y,o={})=>{const sp=o.sp||0,w=pdf.getTextWidth(str)+sp*Math.max(0,str.length-1);
    pdf.text(str,o.right?x-w:x,y,{baseline:"top",charSpace:sp});return w;};
  const wrap=(str,w)=>pdf.splitTextToSize(str,w);
  const notes=String(doc.notes||"").split("\n").filter(Boolean);
  const ref=(notes.find(n=>/^Estimate /.test(n))||"").replace(/^Estimate /,"");
  const pickup=notes.includes("Customer pickup"),free=notes.includes("Free delivery");
  const products=doc.lines.filter(l=>l.kind==="product"),delivery=doc.lines.filter(l=>l.kind==="delivery"),discounts=doc.lines.filter(l=>l.kind==="discount");
  const sum=ls=>ls.reduce((a,l)=>a+toP(l.line_total),0);
  // -- Header
  pdf.addImage(logo,"PNG",L,TOP,13*5.92329,13);
  font("bold",17);txt(DOC_TITLE.toUpperCase(),R,TOP,{right:1,sp:pt(17)*.08});
  const dl=[["Invoice no.",doc.invoice_no],["Date",dateText(doc.issued_at)]].concat(ref?[["Estimate",ref]]:[]).concat(doc.due_date?[["Due",dateText(doc.due_date)]]:[]);
  font("bold",9);const vw=Math.max(...dl.map(r=>pdf.getTextWidth(r[1])));
  let y=TOP+8.5;
  dl.forEach(([k,v])=>{font("bold",9);txt(v,R,y,{right:1});font("normal",9,MUTE);txt(k,R-vw-4,y,{right:1});y+=4.3;});
  y=Math.max(TOP+13,y)+4.5;
  pdf.setFillColor(INK);pdf.rect(L,y,W,.8,"F");pdf.setFillColor(OCHRE);pdf.rect(L,y,28,.8,"F");
  y+=.8+4.5;
  // -- Grey band: bill to (as frozen at issue), delivery, from
  const site=String(doc.deliver_to_location||"").trim();
  const contact=[doc.deliver_to_contact,doc.deliver_to_phone].filter(Boolean).join(" · ");
  const dlv=pickup?`Customer pickup\n${B.pickup}`:(free?"Free delivery":"Delivery")+(site?` to\n${site}`:"")+(contact?`\nSite contact: ${contact}`:"");
  const cols=[["Bill to",[doc.billed_to_name,doc.billed_to_phone].filter(Boolean).join("\n")],["Delivery",dlv],["From",`${B.name}\n${B.phone} (call or WhatsApp)\n${B.website}\n${B.town}`]];
  const inner=W-.8-7,gap=6,unitW=(inner-2*gap)/3.7,cw=[1.5,1,1.2].map(r=>r*unitW);
  font("semibold",8.5);const lh=pt(8.5)*1.45;
  const lines=cols.map((c,i)=>c[1].split("\n").flatMap(l=>wrap(l,cw[i])));
  const bandH=3+pt(7)*1.2+.6+Math.max(...lines.map(l=>l.length))*lh+3;
  pdf.setFillColor(BAND);pdf.rect(L,y,W,bandH,"F");pdf.setFillColor(OCHRE);pdf.rect(L,y,.8,bandH,"F");
  let x=L+.8+3.5;
  cols.forEach((c,i)=>{font("bold",7,MUTE);txt(c[0].toUpperCase(),x,y+3,{sp:pt(7)*.1});
    font("semibold",8.5);lines[i].forEach((l,j)=>txt(l,x,y+3+pt(7)*1.2+.6+j*lh));x+=cw[i]+gap;});
  y+=bandH+4.5;
  // -- Items table (product lines, then a delivery charge, then discounts)
  const C={n:L+2.5,d:L+8+2.5,q:R-32-28-2.5,u:R-32-2.5,a:R-2.5},dW=C.q-24-C.d;
  const head=()=>{pdf.setFillColor(INK);pdf.rect(L,y,W,7,"F");font("bold",7.5,"#ffffff");const sp=pt(7.5)*.08,ty=y+2.2;
    txt("#",C.n,ty,{sp});txt("DESCRIPTION",C.d,ty,{sp});txt("QTY",C.q,ty,{right:1,sp});txt("UNIT PRICE",C.u,ty,{right:1,sp});txt("AMOUNT",C.a,ty,{right:1,sp});y+=7;};
  const newPage=()=>{pdf.addPage();y=TOP;};
  head();
  const rlh=pt(9.5)*1.45;
  doc.lines.forEach((l,i)=>{
    font("semibold",9.5);const nameLines=wrap(l.description,dW);
    font("normal",8);const per=l.kind==="product"?`per ${l.unit}`:"",perW=pdf.getTextWidth(per);
    font("semibold",9.5);const lastW=pdf.getTextWidth(nameLines[nameLines.length-1]);
    const perOwn=per&&lastW+1.5+perW>dW,rows=nameLines.length+(perOwn?1:0),h=1.7*2+rows*rlh;
    if(y+h>BOTTOM){newPage();head();}
    const ty=y+1.7;
    font("semibold",9.5);txt(String(i+1),C.n,ty);nameLines.forEach((n,j)=>txt(n,C.d,ty+j*rlh));
    if(per){font("normal",8,MUTE);perOwn?txt(per,C.d,ty+nameLines.length*rlh+.3):txt(per,C.d+lastW+1.5,ty+(nameLines.length-1)*rlh+.4);}
    font("normal",9.5);txt(`${fmtQ(l.quantity)} ${UNIT_WORD(l.unit,l.quantity)}`.trim(),C.q,ty,{right:1});
    txt(money(toP(l.unit_price)),C.u,ty,{right:1});txt(money(toP(l.line_total)),C.a,ty,{right:1});
    y+=h;pdf.setDrawColor(LINE);pdf.setLineWidth(.25);pdf.line(L,y,R,y);
  });
  // -- Bottom: notes left, totals right (kept together on one page)
  const TW=98,LW=W-TW-8,tlh=pt(7.5)*1.4;
  const extra=notes.filter(n=>n!=="Customer pickup"&&n!=="Free delivery"&&!/^Estimate /.test(n)).join("\n");
  const nb=[];
  if(extra)nb.push(["Note",extra]);
  nb.push(["Questions",`WhatsApp or call ${B.phone} and quote invoice ${doc.invoice_no}.`]);
  nb.push(["Terms","All prices are in Ghana cedis (GH₵)."]);
  font("normal",7.5);const noteLines=nb.map(([h,b])=>[h,b.split("\n").flatMap(l=>wrap(l,LW))]);
  const notesH=noteLines.reduce((a,[,b])=>a+tlh+1.5+b.length*tlh+3,0);
  const rowH=1.2*2+pt(9.5)*1.45,rowsN=2+(discounts.length?1:0),sumH=.5+rowH*rowsN+1.5+3*2+pt(11)*1.45;
  if(y+4+Math.max(notesH,sumH)>BOTTOM)newPage();else y+=4;
  let ny=y;
  noteLines.forEach(([h,b])=>{font("bold",7.5,MUTE);txt(h.toUpperCase(),L,ny,{sp:pt(7.5)*.1});ny+=tlh+1.5;
    font("normal",7.5,"#333333");b.forEach(l=>{txt(l,L,ny);ny+=tlh;});ny+=3;});
  const sx=R-TW;let sy=y;
  pdf.setFillColor(INK);pdf.rect(sx,sy,TW,.5,"F");sy+=.5;
  const sumRow=(k,v,st)=>{font(st,9.5);txt(k,sx+2.5,sy+1.2);txt(v,R-2.5,sy+1.2,{right:1});sy+=rowH;};
  sumRow("Materials",money(sum(products)),"bold");
  sumRow(pickup?"Customer pickup":free?"Free delivery":"Delivery",delivery.length?money(sum(delivery)):pickup?"Pickup":"Free","semibold");
  if(discounts.length)sumRow("Discount",money(sum(discounts)),"semibold");
  sy+=1.5;const gh=3*2+pt(11)*1.45;
  pdf.setFillColor(INK);pdf.rect(sx,sy,TW,gh,"F");pdf.setFillColor(OCHRE);pdf.rect(sx,sy,1.5,gh,"F");
  font("bold",11,"#ffffff");txt("Total due",sx+1.5+2.5,sy+3);txt(money(toP(doc.total)),R-2.5,sy+3,{right:1});
  // -- Every page: footer; pages 2+ also a "continued" line at the top
  const n=pdf.getNumberOfPages();
  for(let p=1;p<=n;p++){pdf.setPage(p);
    font("normal",7,MUTE);txt(`${B.website}  ·  ${B.phone}`,L,289);txt(`Page ${p} of ${n}`,R,289,{right:1});
    if(p>1){font("bold",7.5);txt(`${B.name}  ·  ${DOC_TITLE} ${doc.invoice_no}`,L,9);font("normal",7.5,MUTE);txt("Continued",R,9,{right:1});}}
  return pdf;
}

// ---- 8. Sharing ------------------------------------------------------------
// "Share invoice": the phone's share menu with the PDF and one short line
// (kept from PR #31, decided by Daniel on 21 Nov 2026). Where a browser
// cannot share files, the PDF downloads and the customer's chat opens.
function waNumber(p){let d=String(p||"").replace(/\D/g,"");
  if(d.startsWith("00"))d=d.slice(2);
  if(d.length===10&&d.startsWith("0"))d="233"+d.slice(1);
  else if(d.length===9)d="233"+d;
  return d.length>=11?d:"";}
function waText(doc){const first=String(doc.billed_to_name||"").trim().split(/\s+/)[0]||"";
  return`Hello${first?" "+first:""}, here is your invoice ${doc.invoice_no} from ${B.name}.`;}
async function pdfFile(doc){const pdf=await makePdf(doc);return new File([pdf.output("blob")],fileName(doc),{type:"application/pdf"});}
function download(file){const a=document.createElement("a");a.href=URL.createObjectURL(file);a.download=file.name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),30000);}
// Always read the record again just before making the PDF, so the file
// matches the database (and a removed staff member gets nothing).
async function freshDoc(){const d=await api.document(DOC.id);DOC=d;return d;}
// WhatsApp on Android drops any text shared together with a file, so the
// message is copied to the clipboard first (while the tap still counts as
// the user's own action) and the user pastes it as the caption. Where the
// browser blocks the clipboard, the message is shown with a Copy button.
function copyText(t){
  try{if(navigator.clipboard&&navigator.clipboard.writeText)return navigator.clipboard.writeText(t).then(()=>true,()=>false);}catch(e){}
  return Promise.resolve(false);}
function showCopyBox(t){$("#copyText").value=t;show("#copyBox",true);}
$("#copyBtn").addEventListener("click",async()=>{const ta=$("#copyText");ta.select();
  let ok=await copyText(ta.value);if(!ok){try{ok=document.execCommand("copy");}catch(e){}}
  $("#iMsg").textContent=ok?"Message copied. Paste it in WhatsApp.":"Select the message above and copy it.";});
$("#shareBtn").addEventListener("click",async()=>{
  const btn=$("#shareBtn"),m=$("#iMsg");show("#copyBox",false);m.textContent="";
  const copied=copyText(waText(DOC));
  busy(btn,true,"Preparing PDF…");
  try{const doc=await freshDoc(),file=await pdfFile(doc),text=waText(doc);
    let note;
    if(await copied)note="Message copied. In WhatsApp, paste it as the caption before sending.";
    else{showCopyBox(text);note="Copy the message below, then paste it in WhatsApp as the caption.";}
    if(navigator.canShare&&navigator.canShare({files:[file]})){
      m.textContent=note;
      try{await navigator.share({files:[file],text,title:file.name});}catch(e){if(e.name!=="AbortError")throw e;}
    }else{download(file);const to=waNumber(doc.billed_to_phone);
      if(to)window.open("https://wa.me/"+to+"?text="+encodeURIComponent(text),"_blank","noopener");
      m.textContent="This browser cannot share files: the PDF was downloaded. Attach it in the WhatsApp chat. "+note;}
  }catch(e){kind(e)==="refused"?m.textContent="The PDF could not be made: "+e.message:failed(e,"#iMsg");}
  finally{busy(btn,false);}
});
$("#pdfBtn").addEventListener("click",async()=>{
  const btn=$("#pdfBtn");busy(btn,true,"Preparing PDF…");
  try{download(await pdfFile(await freshDoc()));}catch(e){kind(e)==="refused"?$("#iMsg").textContent="The PDF could not be made: "+e.message:failed(e,"#iMsg");}
  finally{busy(btn,false);}
});

// Discard draft (owner only, spec section 5): the existing cancel_invoice,
// with a reason. The draft is cancelled, never deleted, and stays in the
// records under "Cancelled". The button is locked while it works, so a
// double tap sends one request; if the answer is lost on the way back, the
// draft is read again before anything is reported.
$("#discardBtn").addEventListener("click",()=>{show("#discardBox",true);$("#discardMsg").textContent="";$("#discardWhy").value="";
  $("#discardBox").scrollIntoView({block:"center"});$("#discardWhy").focus();});
$("#discardNo").addEventListener("click",()=>show("#discardBox",false));
$("#discardYes").addEventListener("click",async()=>{
  const btn=$("#discardYes"),m=$("#discardMsg"),why=$("#discardWhy").value.trim(),id=S.invoiceId;
  if(btn.disabled||!id)return;
  if(!why){m.textContent="Give a reason: it is kept with the record.";return;}
  busy(btn,true,"Discarding…");
  try{
    try{await api.cancel(id,why);}
    catch(err){const doc=await api.document(id).catch(()=>null);if(!doc||doc.state!=="cancelled")throw err;}
    show("#discardBox",false);S=blank();DOC=null;NOTE="";forget();
    await go("#/invoice/"+id);
  }catch(err){const k=kind(err);
    if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
    if(k==="expired")return expire();
    m.textContent=k==="offline"?"Not discarded: no connection. Try again when you have signal.":"Not discarded: "+String(err&&err.message||err);}
  finally{busy(btn,false);}
});

// ---- 9. Screens and the address -----------------------------------------------
// One page, four screens, picked by the part of the address after "#/":
//   #/  Home · #/invoices  the list · #/invoice/<id>  one invoice · #/new
// Anything else after "#" (a sign-in link's details) is not a screen.
const VIEWS=["#homeV","#listV","#invV"];
let HERE="#/",SKIP=false;   // HERE: the screen shown now (for "Go back")
const canEdit=()=>!!ME&&(ME.role==="owner"||ME.role==="sales");
function view(name,tab){VIEWS.forEach(v=>show(v,v===name));
  document.querySelectorAll("#tabs a").forEach(a=>a.classList.toggle("on",a.dataset.tab===tab));window.scrollTo(0,0);}
// Inside the invoice screen: the estimate box, the form, or the read-only view.
function showOnly(part){["#start","#form","#issuedSec","#discardBox"].forEach(p=>show(p,p===part));}
function parseRoute(){
  const h=location.hash||"";
  if(!h.startsWith("#/"))return{name:"home",params:new URLSearchParams()};
  const[path,qs]=h.slice(2).split("?"),parts=path.split("/").filter(Boolean),params=new URLSearchParams(qs||"");
  if(parts[0]==="invoices")return{name:"invoices",params};
  if(parts[0]==="invoice"&&/^\d+$/.test(parts[1]||""))return{name:"invoice",id:+parts[1],params};
  if(parts[0]==="new")return{name:"new",params};
  return{name:"home",params};
}
async function go(hash){if(location.hash===hash)await route();else location.hash=hash;}
window.addEventListener("hashchange",()=>{if(SKIP){SKIP=false;return;}route();});
async function route(){
  if(!ME)return;
  const r=parseRoute();
  if(r.name==="new"&&!canEdit())return go("#/");
  if(r.name==="invoice"||r.name==="new"){
    // Does this screen show the invoice being prepared? If not, and it has
    // unsaved changes, ask before replacing it (spec section 5).
    const same=r.name==="new"?!S.invoiceId:S.invoiceId===r.id;
    if(!same){
      if(unsaved()&&(await askGuard())==="back"){SKIP=location.hash!==HERE;location.hash=HERE;return;}
      S=blank();DOC=null;NOTE="";LOOKED="";forget();
    }
  }
  HERE=location.hash||"#/";
  if(r.name==="home")return showHome();
  if(r.name==="invoices")return showList(r.params);
  view("#invV",r.name==="new"?"new":"invoices");
  if(r.name==="new"){
    if(S.items.length||S.name||S.phone||S.dirty)return showForm();
    $("#paste").value="";$("#readMsg").textContent="";$("#matches").innerHTML="";return showOnly("#start");
  }
  // This invoice's own unsaved changes are on the phone: carry on with them.
  if(S.invoiceId===r.id&&S.dirty)return showForm();
  return openInvoice(r.id);
}

// "This invoice has changes that are not saved": Save it, Discard changes,
// or Go back. Answers "save" (only once saved), "discard" or "back".
function askGuard(){return new Promise(done=>{
  const box=$("#guard"),m=$("#guardMsg");m.textContent="";show("#guard",true);box.scrollIntoView({block:"start"});
  const end=a=>{show("#guard",false);["#guardSave","#guardDiscard","#guardBack"].forEach(b=>$(b).onclick=null);done(a);};
  $("#guardBack").onclick=()=>end("back");
  $("#guardDiscard").onclick=()=>{S.dirty=false;forget();end("discard");};
  $("#guardSave").onclick=async()=>{
    const bad=problems(S,false);if(bad.length){m.textContent="Can't save yet: "+bad.join(" ");return;}
    const b=$("#guardSave");busy(b,true,"Saving…");
    try{await save();end("save");}
    catch(err){const k=kind(err);if(k==="revoked"||k==="expired"){end("back");return failed(err);}
      m.textContent=k==="offline"?"Not saved: no connection. Try again, or go back.":"Not saved: "+String(err&&err.message||err);}
    finally{busy(b,false);}
  };
});}
function showForm(){view("#invV",S.invoiceId?"invoices":"new");showOnly("#form");
  $("#cName").value=S.name;$("#cPhone").value=S.phone;$("#cSite").value=S.site;
  $("#cContact").value=S.contact;$("#cContactPhone").value=S.contactPhone;
  document.querySelectorAll('input[name="dl"]').forEach(r=>r.checked=r.value===S.dl);
  $("#fee").value=S.fee;$("#iDue").value=S.due;$("#iNote").value=S.note;
  $("#custPicked").textContent=S.customerCode?`Existing customer ${S.customerCode}`:"";
  render();
}

// Errors while reading a screen: removed access signs out, an expired
// sign-in keeps the work, anything else is said on the screen.
function readFailed(err,where){const k=kind(err);
  if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
  if(k==="expired")return expire();
  $(where).textContent=k==="offline"?"Can't load this: no connection. Check your signal and try again.":"Can't load this: "+String(err&&err.message||err);}

// A row in the lists (Home's latest, and Invoices).
function shortDate(iso){if(!iso)return"";const[y,m,d]=String(iso).slice(0,10).split("-").map(Number);
  return new Date(y,m-1,d).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"});}
function rowHTML(r){
  const draft=r.status==="draft",when=draft?"Started "+shortDate(r.created_at):r.status==="overdue"?"Due "+shortDate(r.due_date):r.issued_at?"Issued "+shortDate(r.issued_at):"";
  const owes=r.state==="issued"&&r.status!=="paid"&&+r.balance!==+r.total;
  return`<a class="dk-inv" href="#/invoice/${r.id}" data-id="${r.id}">
    <span class="dk-inv-top"><b>${draft?"Draft":esc(r.invoice_no||"")}</b><i class="dk-badge s-${esc(r.status)}">${esc(STATUS[r.status]||r.status)}</i></span>
    <span class="dk-inv-who">${esc(r.billed_to_name||"(no name)")}${r.billed_to_phone?" · "+esc(r.billed_to_phone):""}</span>
    <span class="dk-inv-bot"><small>${esc(when)}</small><b>${money(toP(r.total))}${owes?`<small> · ${money(toP(r.balance))} left</small>`:""}</b></span>
  </a>`;}

// Home: the figures are the database's own (back_office_home); nothing is
// added up on the phone. Each figure opens the matching list.
async function showHome(){
  view("#homeV","home");$("#homeMsg").textContent="";
  $("#unsavedNote").innerHTML=unsaved()?`<div class="dk-card dk-alert"><b>An invoice is in progress and not saved.</b> <a href="${S.invoiceId?"#/invoice/"+S.invoiceId:"#/new"}">Continue it</a></div>`:"";
  try{
    const[h,recent]=await Promise.all([api.home(),api.list({status:"all",terms:[],offset:0,limit:5})]);
    // Removed access reads as zeros and an empty list, not as an error.
    if(!recent.rows.length)await stillStaff();
    $("#hOwed").textContent=money(toP(h.owed));
    $("#hUnpaid").textContent=h.unpaid;$("#hPart").textContent=h.part_paid;
    $("#hOverdue").textContent=h.overdue;$("#hDrafts").textContent=h.drafts;
    $("#recent").innerHTML=recent.rows.length?recent.rows.map(rowHTML).join(""):`<p class="dk-help">No invoices yet.</p>`;
  }catch(err){readFailed(err,"#homeMsg");}
}

// Search: by number, part of a name, or a phone number in any Ghana format.
// Phone numbers are stored as +233XXXXXXXXX (the database writes them so).
// The digits typed are matched inside that, after removing the country code
// (only when it really is one: a leading "+233", "00233", or 12 digits
// starting with 233) or a leading 0. Every match is listed; nothing is ever
// picked for the user. Characters that mean something to the database's
// filter syntax are dropped; spaces become wildcards.
function searchTerms(q){
  const raw=String(q||"").trim(),out=[];
  const clean=raw.replace(/[^\p{L}\p{N} .\-'&\/]/gu," ").trim().replace(/\s+/g,"*");
  if(clean){out.push({col:"invoice_no",pattern:`*${clean}*`});out.push({col:"billed_to_name",pattern:`*${clean}*`});}
  let d=raw.replace(/\D/g,"");
  if(/^\s*\+\s*233/.test(raw))d=d.slice(3);
  else if(d.startsWith("00233"))d=d.slice(5);
  else if(d.length===12&&d.startsWith("233"))d=d.slice(3);
  else if(d.startsWith("0"))d=d.slice(1);
  if(d.length>=3)out.push({col:"billed_to_phone",pattern:`*${d}*`});
  return out;
}
const PAGE=30;
let LIST={status:"all",q:"",rows:[],count:0,seq:0};
async function showList(params){
  view("#listV","invoices");
  const status=params.get("status")||"all",q=params.get("q")||"";
  $("#q").value=q;
  document.querySelectorAll("#filters button").forEach(b=>b.classList.toggle("on",b.dataset.status===status));
  LIST={status,q,rows:[],count:0,seq:LIST.seq+1};
  $("#rows").innerHTML="";$("#listMsg").textContent="";
  await loadMore();
}
async function loadMore(){
  const my=LIST.seq,btn=$("#moreBtn");busy(btn,true,"Loading…");$("#listMsg").textContent="";
  try{
    const res=await api.list({status:LIST.status,terms:searchTerms(LIST.q),offset:LIST.rows.length,limit:PAGE});
    if(my!==LIST.seq)return;   // a newer search or filter has replaced this one
    if(!res.rows.length&&!LIST.rows.length)await stillStaff();
    LIST.rows=LIST.rows.concat(res.rows);LIST.count=res.count;
    $("#rows").innerHTML=LIST.rows.length?LIST.rows.map(rowHTML).join(""):`<p class="dk-help">${LIST.q||LIST.status!=="all"?"No invoices match.":"No invoices yet."}</p>`;
    $("#listInfo").textContent=LIST.status==="owed"?`Owed to TCP: ${LIST.count} ${LIST.count===1?"invoice":"invoices"}`:LIST.count?`${LIST.count} ${LIST.count===1?"invoice":"invoices"}`:"";
    show("#moreBtn",LIST.rows.length<LIST.count);
  }catch(err){if(my===LIST.seq)readFailed(err,"#listMsg");}
  finally{busy(btn,false);}
}
$("#moreBtn").addEventListener("click",loadMore);
const listHash=(status,q)=>"#/invoices"+((status&&status!=="all")||q?"?"+new URLSearchParams(Object.assign(status&&status!=="all"?{status}:{},q?{q}:{})).toString():"");
$("#filters").addEventListener("click",e=>{const b=e.target.closest("[data-status]");if(b)go(listHash(b.dataset.status,LIST.q));});
// Searching as you type: after a short pause, without filling the Back
// button's history with every letter.
let typing=null;
$("#q").addEventListener("input",()=>{clearTimeout(typing);typing=setTimeout(()=>{
  const h=listHash(LIST.status,$("#q").value.trim());history.replaceState(null,"",h);HERE=h;
  LIST={...LIST,q:$("#q").value.trim(),rows:[],count:0,seq:LIST.seq+1};$("#rows").innerHTML="";loadMore();},350);});
$("#searchForm").addEventListener("submit",e=>{e.preventDefault();clearTimeout(typing);
  const h=listHash(LIST.status,$("#q").value.trim());history.replaceState(null,"",h);HERE=h;
  LIST={...LIST,q:$("#q").value.trim(),rows:[],count:0,seq:LIST.seq+1};$("#rows").innerHTML="";loadMore();});

// ---- 10. Start -----------------------------------------------------------------
// Not connected to a database (no project address in this build): say so.
if(!api){screen("setup");}
else{
  // A sign-in link that has expired or was already used comes back with
  // the reason in the address. Say so, and tidy the address.
  const back=new URLSearchParams((location.hash||"").replace(/^#/,"")+"&"+location.search.replace(/^\?/,""));
  const linkError=back.get("error_code")||back.get("error");
  // Signed out by Supabase itself (the sign-in could not be renewed): the
  // same as an expired sign-in. (Our own sign-outs clear ME first, so they
  // don't come through here.)
  // Supabase delivers this notice while it holds its sign-in lock: calling
  // any Supabase function inside it can freeze the page. So the notice only
  // schedules the work for just afterwards, and does nothing else.
  if(api.onSignOut)api.onSignOut(()=>{setTimeout(()=>{if(ME)expire();},0);});
  enter().then(()=>{
    if(linkError&&!ME){screen("signin");$("#signMsg").textContent="That sign-in link has expired or was already used. Send a new one.";}
    if(linkError||back.get("access_token"))history.replaceState(null,"",location.pathname);
  }).catch(err=>{screen("signin");$("#signMsg").textContent=kind(err)==="offline"?"No connection. Check your signal and reload.":"";});
}

// For the tests (and nothing else): the desk's own functions.
window.TCPDesk={parseEstimate,num,totals,problems,waNumber,waText,makePdf,linesForDb,searchTerms,state:()=>S,doc:()=>DOC};
})();
