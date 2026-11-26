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
     8b. Payments and receipts (phase 2: record, receipts, corrections,
                               refunds)
     8c. Payments tab, cancelling invoices (phase 2.1)
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
    // Phase 2: payments and receipts. Each takes a request id, made once when
    // the form opens and kept for every retry, so the database never records
    // the same payment twice (it returns the first receipt instead).
    recordPayment:a=>sb.rpc("record_payment",a).then(out),
    correctPayment:a=>sb.rpc("correct_payment",a).then(out),
    refundPayment:a=>sb.rpc("refund_payment",a).then(out),
    receipt:id=>sb.rpc("receipt_document",{p_payment_id:id}).then(out),
    // Phase 2.2: internal notes. add_invoice_note adds a note, or a
    // correction of one (never an edit); a request id kept for retries means
    // a note is never added twice. search_notes searches every note the
    // database keeps; note_authors lists who can be picked in its filter.
    addNote:a=>sb.rpc("add_invoice_note",a).then(out),
    searchNotes:a=>sb.rpc("search_notes",a).then(out),
    noteAuthors:()=>sb.rpc("note_authors").then(out),
    // Was this request recorded? The receipt it made, or null.
    byRequest:req=>sb.from("payments").select("id,receipt_no,kind,invoice_id,reverses_payment_id,amount").eq("request_id",req).maybeSingle().then(out),
    // Discarding a draft = the owner-only cancel_invoice (kept, with a reason).
    cancel:(id,reason)=>sb.rpc("cancel_invoice",{p_invoice_id:id,p_reason:reason}).then(out),
    // Phase 2.1: a period's money figures (payment_totals: today, week,
    // month or all), worked out by the database, with the period's dates.
    totals:period=>sb.rpc("payment_totals",{p_period:period}).then(out),
    // A page of the Payments list (payment_ledger), newest first by date,
    // then id, between the dates payment_totals gave (so the list and the
    // totals always cover the same days). terms: see ledgerTerms().
    ledger:({from,to,kind:k,method,terms,offset,limit})=>{
      let q=sb.from("payment_ledger").select("id,receipt_no,kind,amount,method,reference,paid_on,invoice_id,invoice_no,billed_to_name,billed_to_phone,reverses_receipt_no,corrected,customer_note,internal_note",{count:"exact"})
        .order("paid_on",{ascending:false}).order("id",{ascending:false}).range(offset,offset+limit-1);
      if(from)q=q.gte("paid_on",from);
      if(to)q=q.lte("paid_on",to);
      if(k&&k!=="all")q=q.eq("kind",k);
      if(method&&method!=="all")q=q.eq("method",method);
      if(terms&&terms.length)q=q.or(terms.map(t=>`search_text.ilike.${t}`).join(","));
      return q.then(r=>{if(r.error)throw r.error;return{rows:r.data||[],count:r.count||0};});
    },
    // The Home figures, worked out by the database (back_office_home).
    home:()=>sb.from("back_office_home").select("owed,unpaid,part_paid,overdue,drafts,in_credit,in_credit_count").single().then(out),
    // Phase 2.3: credit notes. issue_credit_note and cancel_credit_note take
    // a request id, made once when the form opens and kept for every retry,
    // so the database never issues (or cancels) twice. credit_note_options
    // with no invoice gives just the switch; credit_note_print is the only
    // data the credit note PDF is drawn from.
    creditOptions:a=>sb.rpc("credit_note_options",a).then(out),
    issueCredit:a=>sb.rpc("issue_credit_note",a).then(out),
    cancelCredit:a=>sb.rpc("cancel_credit_note",a).then(out),
    creditDoc:a=>sb.rpc("credit_note_document",a).then(out),
    creditPrint:a=>sb.rpc("credit_note_print",a).then(out),
    setCreditSwitch:a=>sb.rpc("set_credit_notes_switch",a).then(out),
    // Was this credit note issued? The credit note, or null.
    creditByRequest:req=>sb.from("credit_notes").select("id,credit_note_no,invoice_id,amount").eq("request_id",req).maybeSingle().then(out),
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
    try{localStorage.removeItem("tcp-desk-work-"+u.id);localStorage.removeItem("tcp-desk-op-"+u.id);localStorage.removeItem("tcp-desk-cn-"+u.id)}catch(e){}
    ME=null;screen("noaccess");$("#noEmail").textContent=u.email||"";return;
  }
  ME={id:u.id,name:st.full_name,role:st.role};
  $("#who").textContent=`${ME.name} · ${ME.role}`;
  // Finance sees Home and the invoices, read-only (spec section 7): no New
  // invoice tab. The database refuses them saving or issuing anyway.
  ["#tabNew","#hNew","#newBtn2"].forEach(s=>show(s,canEdit()));
  try{PRODUCTS=await api.products()||[];if(!PRODUCTS.length)await stillStaff();}
  catch(err){const k=kind(err);if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");if(k==="expired")return expire();}
  fillAdd();screen("tool");restore();
  // An operation left unconfirmed (e.g. the sign-in ran out while it was
  // being recorded): go straight to its invoice, where it is checked.
  const op=pendingOp()||pendingCn();
  if(op)history.replaceState(null,"",location.pathname+location.search+"#/invoice/"+op.invoiceId);
  await route();
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
  try{localStorage.removeItem(key);dropOp();dropCn()}catch(e){}
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
  ["#hOwed","#hUnpaid","#hPart","#hOverdue","#hDrafts","#hToday","#tNet","#tRec","#tRef","#tCount"].forEach(s=>{$(s).textContent="—";});
  ["#ledRows","#tRecBy","#tRefBy"].forEach(s=>{$(s).innerHTML="";});
  ["#guard","#discardBox","#copyBox","#rCopyBox"].forEach(s=>show(s,false));
  PAY=null;FIX=null;RDOC=null;CN=null;CDOC=null;CC=null;SWITCH=null;show("#soBox",false);
  ["#payList","#rcpt","#cnList","#cnLines","#cv","#cvLines","#cvNotes"].forEach(s=>{$(s).innerHTML="";});
  ["#cvCopyBox","#cnSwitch"].forEach(s=>show(s,false));
  ["#paste","#cName","#cPhone"].forEach(s=>{const el=$(s);if(el)el.value="";});
  screen("signin");$("#signMsg").textContent=why;
  try{await api.signOut();}catch(e){}
}
// Signing out removes an unconfirmed payment, correction or refund from this
// phone, so it warns first.
$("#signOut").addEventListener("click",()=>{const op=pendingOp();
  // (A second tap on Sign out, with the warning showing, signs out.)
  if(op&&$("#soBox").hidden){$("#soMsg").textContent=`A ${OP_WORD[op.type]} of ${money(toP(op.amount))} has not been confirmed as recorded. Signing out abandons it: open its invoice first to check it.`;
    $("#soOpen").href="#/invoice/"+op.invoiceId;show("#soBox",true);return;}
  revoke("Signed out.");});
$("#soGo").addEventListener("click",()=>{show("#soBox",false);revoke("Signed out.");});
$("#soOpen").addEventListener("click",()=>show("#soBox",false));
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
  // Phase 2.2: the customer's note from the estimator ("*Note:* …").
  const note=(t.match(/^\s*\*?Note:\*?\s*(.+)$/im)||[])[1];
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
  return{ref:ref[0]||null,loc:loc?loc.replace(/\*+$/,"").trim():"",note:note?note.replace(/\*+$/,"").trim().slice(0,1000):"",items};
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
  name:"",phone:"",site:"",contact:"",contactPhone:"",items:[],dl:"pending",fee:"",due:"",note:"",estNote:null,dirty:false};}
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
  // A value that was not a number was kept as null on the phone.
  S.items.forEach(l=>{if(l.qty==null)l.qty=NaN;if(l.price==null)l.price=NaN;});
}
// Unsaved work that would be lost if this invoice were replaced.
const unsaved=()=>S.dirty&&!!(S.items.length||S.name.trim()||S.phone.trim());
function fillAdd(){const g={};PRODUCTS.forEach(p=>(g[p.category]=g[p.category]||[]).push(p));
  $("#addSel").innerHTML=Object.entries(g).map(([c,l])=>`<optgroup label="${esc(c)}">${l.map(p=>`<option value="${p.id}">${esc(p.name)} (${esc(p.unit)}) · ${money(toP(p.current_price))}</option>`).join("")}</optgroup>`).join("");}
const lineTotal=l=>Math.round(l.price*l.qty);
// Phase 1.1 (C-02): what is wrong with a line's quantity and price, in the
// words shown under it as they are typed ("" when fine). The database
// refuses the same values anyway (quantity > 0, price >= 0); this only says
// so at once, on the right line. A price of GH₵0.00 is allowed: a free item.
// Letters typed into a number box make it "not a number", never a guess.
// Strict (review of PR #38): what was typed must be one whole, well-formed
// number before it is read, so a slip such as "1.2.3", "1,2,3" or "1-2"
// is "not a number" rather than quietly becoming 123, 1.2 or 1. Accepted:
//   12   12.5   2,5 (decimal comma)   .5   1,392.00 / 50,000 (thousands
//   commas)   1.392,00 (dot thousands, comma decimals)
// with an optional leading minus (then refused as below zero) and an
// optional GH₵ in front. Anything else, letters included, is NaN.
const NUM_FORM=/^-?(?:\d+(?:[.,]\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+,\d+|[.,]\d+)$/;
function typedNum(t){const v=String(t==null?"":t).trim().replace(/^(?:GH)?₵\s*/i,"");
  return NUM_FORM.test(v)?num(v):NaN;}
function lineIssues(l){
  const q=isNaN(l.qty)?(l.qtyText===""?"Enter a quantity":"Enter a number"):l.qty>0?"":"Quantity must be more than 0";
  const p=isNaN(l.price)?(l.priceText===""?"Enter a price":"Enter a number"):l.price<0?"Price can't be below GH₵0":"";
  return{qty:q,price:p};}
const lineOk=l=>{const x=lineIssues(l);return!x.qty&&!x.price;};
function feeIssue(s){if(s.dl!=="fee")return"";const t=String(s.fee||"").trim(),v=typedNum(t);
  return!t?"Enter the delivery fee":isNaN(v)?"Delivery fee: enter a number":v>0?"":"Delivery fee must be more than 0";}

// Phase 1.1 (C-01): lines are the same when product, unit and price all
// match. Only those are ever combined; the same product at another
// (agreed) price stays a separate line.
const sameLine=(a,b)=>!!a.pid&&a.pid===b.pid&&a.unit===b.unit&&a.price===b.price&&lineOk(a)&&lineOk(b);
const addQty=(a,b)=>Math.round((a+b)*1000)/1000;
// The note shown under one line after something was done to it (cleared by
// the next change): {i, text}.
let LINE_NOTE=null;
// Combines every pair of identical lines into the first of them. Returns
// what was combined, in words, so the screen can say so.
function combineIdentical(){
  const said=[];
  for(let i=0;i<S.items.length;i++)for(let j=S.items.length-1;j>i;j--){
    const a=S.items.at(i),b=S.items.at(j);
    if(sameLine(a,b)){a.qty=addQty(a.qty,b.qty);S.items.splice(j,1);
      said.push(`Lines ${i+1} and ${j+1} combined: ${a.name}, ${fmtQ(a.qty)} ${UNIT_WORD(a.unit,a.qty)||a.unit}.`);}
  }
  return said;}
function totals(s){const mat=s.items.some(l=>!lineOk(l))?NaN:s.items.reduce((a,l)=>a+lineTotal(l),0);
  const fee=s.dl==="fee"?(feeIssue(s)?NaN:toP(typedNum(s.fee))):0;return{mat,fee,total:mat+fee};}
// The estimate line the Back Office writes into the invoice's notes column
// ("Estimate TCP-261120-MEBLV2", the estimator's only reference format).
// Matched exactly, so a note to the customer such as "Estimate valid for 7
// days" stays part of the note.
const EST_LINE=/^Estimate TCP-\d{6}-[A-Z0-9]{6}$/;
const DL_TEXT={pending:"Not agreed yet",free:"Free delivery",fee:"Delivery fee",pickup:"Customer pickup"};
// What is missing before the invoice can be saved or issued. The database
// checks everything again; this only saves a wasted trip.
function problems(s,forIssue){
  const out=[];
  if(!s.items.length)out.push("Add at least one item.");
  if(s.items.some(l=>!l.pid))out.push("An item is not in today's price list: remove it or add the right product.");
  // Each line's problem, named by its line number (C-02).
  s.items.forEach((l,i)=>{const x=lineIssues(l);
    if(x.qty)out.push(`Line ${i+1}: ${x.qty.charAt(0).toLowerCase()+x.qty.slice(1)}.`);
    if(x.price)out.push(`Line ${i+1}: ${x.price.charAt(0).toLowerCase()+x.price.slice(1)}.`);});
  if(!s.name.trim()&&!s.phone.replace(/\D/g,""))out.push("Add the customer's phone number or name.");
  if(forIssue&&s.dl==="pending")out.push("Agree the delivery with the customer first.");
  const f=feeIssue(s);if(f)out.push(f+".");
  // Free items are fine, but an invoice must be worth something (the
  // database refuses to issue a zero total too).
  if(forIssue&&!out.length&&!(totals(s).total>0))out.push("The invoice total must be more than GH₵0.00 to issue it.");
  return out;
}
// showForm(): see section 9.
function itemsHTML(){
  if(!S.items.length)return`<p class="dk-help">No items yet. Add them below.</p>`;
  return S.items.map((l,i)=>{
    const changed=l.list!=null&&l.price!==l.list,quotedDiff=l.quoted!=null&&l.list!=null&&l.quoted!==l.list;
    const x=lineIssues(l),twin=S.items.findIndex((o,j)=>j<i&&sameLine(o,l));
    return`<div class="dk-line${x.qty||x.price?" bad":""}" data-i="${i}">
      <div class="dk-ln-name"><b>${i+1}. ${esc(l.name)}</b> <small>per ${esc(l.unit)}</small>
        ${l.pid?"":`<span class="dk-flag">Not in today's price list: remove it and add the right product</span>`}
        ${quotedDiff?`<span class="dk-note">The estimate said ${money(l.quoted)}; today's price is ${money(l.list)}.</span>`:""}</div>
      <label>Qty<input data-f="qty" type="text" inputmode="decimal" value="${l.qtyText!=null?esc(l.qtyText):isNaN(l.qty)?"":fmtQ(l.qty)}" aria-label="Quantity of ${esc(l.name)}" aria-invalid="${!!x.qty}"></label>
      <label>Price (GH₵)<input data-f="price" type="text" inputmode="decimal" value="${l.priceText!=null?esc(l.priceText):isNaN(l.price)?"":(l.price/100).toFixed(2)}" aria-label="Price of ${esc(l.name)}" aria-invalid="${!!x.price}"></label>
      <div class="dk-amt">${amtHTML(l)}</div>
      <button type="button" class="dk-x" data-rm="${i}" aria-label="Remove ${esc(l.name)}">Remove</button>
      <p class="dk-lerr" role="alert">${esc([x.qty,x.price].filter(Boolean).join(". "))}</p>
      <p class="dk-lnote dk-twin"${twin>=0?"":" hidden"}>${twinHTML(i,twin)}</p>
      ${LINE_NOTE&&LINE_NOTE.i===i?`<p class="dk-lnote">${esc(LINE_NOTE.text)}</p>`:""}
    </div>`}).join("");
}
// "Same product and price as line N" with a Combine button (C-01).
const twinHTML=(i,twin)=>twin>=0?`Same product and price as line ${twin+1}. <button type="button" class="dk-link" data-combine="${i}">Combine</button>`:"";
// Updates those notes in place, without re-drawing the boxes (so the box
// just tapped keeps its focus and the phone keeps its keyboard open).
function updateTwins(){document.querySelectorAll("#items .dk-line").forEach(row=>{
  const i=+row.dataset.i,l=S.items[i];if(!l)return;
  const twin=S.items.findIndex((o,j)=>j<i&&sameLine(o,l)),p=row.querySelector(".dk-twin");
  // Only when it changes: tapping Combine also ends the typing in the box
  // before it, and re-writing the note then would remove the button tapped.
  const h=twinHTML(i,twin);if(p.innerHTML!==h)p.innerHTML=h;p.hidden=twin<0;});}
// A line's amount: "—" while a value is wrong; "Free item" at GH₵0.00.
function amtHTML(l){const ch=l.list!=null&&l.price!==l.list;
  if(!lineOk(l))return"—";
  return(l.price===0?`${money(0)}<small>Free item</small>`:money(lineTotal(l)))+(ch?`<small>Agreed price (list ${money(l.list)})</small>`:"");}
function render(){$("#items").innerHTML=itemsHTML();show("#feeBox",S.dl==="fee");refresh();}
function changed(){S.dirty=true;NOTE="";refresh();}
// The delivery fee is checked as it is typed, like the item boxes.
function feeCheck(){const f=feeIssue(S);$("#feeErr").textContent=f;$("#fee").setAttribute("aria-invalid",String(!!f));
  $("#feeBox").classList.toggle("bad",!!f);}
// Totals and the state line (everything except the item boxes).
function refresh(){const t=totals(S),bad=problems(S,true);
  show("#discardBtn",!!(ME&&ME.role==="owner"&&S.invoiceId));
  $("#sMat").textContent=isNaN(t.mat)?"—":money(t.mat);
  $("#sDel").textContent=S.dl==="fee"?money(t.fee):S.dl==="pending"?"Not agreed yet":DL_TEXT[S.dl];
  $("#sTot").textContent=isNaN(t.total)?"—":money(t.total);
  $("#issueBtn").disabled=bad.length>0;$("#saveBtn").disabled=problems(S,false).length>0;
  $("#sMsg").textContent=NOTE||bad.join(" ");
  if(document.getElementById("feeErr"))feeCheck();
  $("#state").textContent=S.invoiceId?(S.dirty?"Draft: changes not saved yet":"Draft saved"):(S.items.length?"Not saved yet":"");
  keep();}
$("#items").addEventListener("input",e=>{
  const row=e.target.closest(".dk-line");if(!row)return;const l=S.items[+row.dataset.i];
  if(e.target.dataset.f==="qty"){l.qtyText=e.target.value.trim();l.qty=typedNum(l.qtyText);}
  if(e.target.dataset.f==="price"){l.priceText=e.target.value.trim();const v=typedNum(l.priceText);l.price=isNaN(v)?NaN:toP(v);}
  // This line's amount and message change at once; the rest of the form is
  // not re-drawn, so the keyboard stays open.
  const x=lineIssues(l);
  row.querySelector(".dk-amt").innerHTML=amtHTML(l);
  row.querySelector(".dk-lerr").textContent=[x.qty,x.price].filter(Boolean).join(". ");
  row.classList.toggle("bad",!!(x.qty||x.price));
  row.querySelector('[data-f="qty"]').setAttribute("aria-invalid",String(!!x.qty));
  row.querySelector('[data-f="price"]').setAttribute("aria-invalid",String(!!x.price));
  LINE_NOTE=null;changed();
});
// Leaving a box: once valid, the typed text is no longer needed, and the
// "Same as line …" notes are brought up to date (without re-drawing).
$("#items").addEventListener("change",e=>{const row=e.target.closest(".dk-line");
  if(row){const l=S.items[+row.dataset.i];if(l&&lineOk(l)){delete l.qtyText;delete l.priceText;}}
  updateTwins();refresh();});
$("#items").addEventListener("click",e=>{
  const c=e.target.closest("[data-combine]");
  if(c){const i=+c.dataset.combine,l=S.items[i],j=S.items.findIndex((o,k)=>k<i&&sameLine(o,l));
    if(j>=0){const a=S.items[j];a.qty=addQty(a.qty,l.qty);S.items.splice(i,1);
      LINE_NOTE={i:j,text:`Combined with line ${i+1}: ${fmtQ(a.qty)} ${UNIT_WORD(a.unit,a.qty)||a.unit} now.`};S.dirty=true;render();}
    return;}
  const b=e.target.closest("[data-rm]");if(!b)return;S.items.splice(+b.dataset.rm,1);LINE_NOTE=null;S.dirty=true;render();});
// Adding a product (C-01): if it is already on the invoice at today's price,
// the quantity goes onto that line; at an agreed (different) price, it is
// added as its own line. Either way the line says what happened.
$("#addBtn").addEventListener("click",()=>{const p=PRODUCTS.find(x=>String(x.id)===$("#addSel").value);if(!p)return;
  const price=toP(p.current_price),fresh={kind:"product",pid:p.id,name:p.name,unit:p.unit,qty:1,price,list:price,quoted:null};
  const same=S.items.findIndex(l=>sameLine(l,fresh)),other=S.items.findIndex(l=>l.pid===p.id&&l.unit===p.unit&&l.price!==price);
  if(same>=0){const l=S.items[same];l.qty=addQty(l.qty,1);
    LINE_NOTE={i:same,text:`Already on the invoice: quantity now ${fmtQ(l.qty)} ${UNIT_WORD(l.unit,l.qty)||l.unit}.`};}
  else{S.items.push(fresh);
    LINE_NOTE=other>=0?{i:S.items.length-1,text:`Line ${other+1} has an agreed price of ${isNaN(S.items[other].price)?"—":money(S.items[other].price)}; this line is at today's price.`}:null;}
  S.dirty=true;render();});
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
  S={...blank(),ref:r.ref,site:r.loc,items:r.items,dirty:true,
     // The customer's note is added to the draft's internal notes on its
     // first save (one request id, so a retry never adds it twice).
     estNote:r.note?{text:r.note,ref:r.ref,req:newId()}:null};
  const merged=combineIdentical();
  const odd=r.items.filter(l=>!l.pid).length,moved=r.items.filter(l=>l.quoted!=null&&l.list!=null&&l.quoted!==l.list).length;
  m.textContent=`Read ${r.items.length} ${r.items.length===1?"item":"items"}${r.ref?" from estimate "+r.ref:""}.`
    +(moved?` ${moved} ${moved===1?"price has":"prices have"} changed since the estimate: today's price is used, edit it if you agreed otherwise.`:"")
    +(odd?` ${odd} ${odd===1?"item is":"items are"} not in today's price list: please check.`:"")
    +(merged.length?" "+merged.join(" "):"");
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
let MERGED=[];   // what the last save combined, for the message after it
async function save(){
  // Identical lines (same product, unit and price) are combined before
  // saving, and the screen says which (C-01). Other lines are never merged.
  MERGED=combineIdentical();if(MERGED.length){LINE_NOTE=null;render();}
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
  await addEstimateNote(id);
  return id;
}
// The estimate's note, once the draft exists. If it can't be added now it
// stays waiting (shown in the notes panel) and is tried on the next save.
async function addEstimateNote(id){
  const n=S.estNote;
  if(!n){if(!$("#form").hidden)renderNotes(NDOC&&NDOC.id===id?NDOC:{id,state:"draft",internal_notes:[]},true);return;}
  try{await api.addNote({p_invoice_id:id,p_body:n.text,p_category:"general",p_estimate_ref:n.ref||null,p_request_id:n.req});
    S.estNote=null;keep();
    const d=await api.document(id).catch(()=>null);
    renderNotes(d||{id,state:"draft",internal_notes:[]},true);}
  catch(err){const k=kind(err);if(k==="revoked"||k==="expired")throw err;
    renderNotes(NDOC&&NDOC.id===id?NDOC:{id,state:"draft",internal_notes:[]},true);
    $("#nMsg").textContent="The estimate's note is not in the internal notes yet"+(k==="offline"?" (no connection)":"")+". It is added on the next save.";}
}
$("#saveBtn").addEventListener("click",async()=>{
  if(problems(S,false).length)return;const btn=$("#saveBtn");busy(btn,true,"Saving…");NOTE="";
  try{await save();NOTE=["Draft saved."].concat(MERGED).join(" ");}catch(err){failed(err);}finally{busy(btn,false);refresh();}
});
$("#issueBtn").addEventListener("click",async()=>{
  if(problems(S,true).length)return;
  // Identical lines are combined first and shown, and the invoice is NOT
  // issued in the same tap: what is issued is always what was on screen
  // (review of PR #38). Tapping Issue again issues the combined invoice.
  const merged=combineIdentical();
  // Combining changes the invoice: it is now unsaved work, so the screen
  // says so and leaving it asks first (review of PR #38).
  if(merged.length){S.dirty=true;LINE_NOTE=null;render();
    NOTE=merged.join(" ")+" Check the combined lines, then tap Issue invoice again.";refresh();
    $("#sMsg").scrollIntoView({block:"center"});return;}
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
  try{doc=await api.document(id);}catch(err){view("#invV");showOnly("#issuedSec");$("#viewTitle").textContent="Invoice";$("#issued").innerHTML="";$("#viewLines").innerHTML="";show("#shareRow",false);show("#shareHelp",false);show("#payBox",false);return readFailed(err,"#iMsg");}
  if(doc.state==="draft"&&canEdit()){const was=S;S=fromDraft(doc);
    if(was.invoiceId===doc.id&&was.estNote)S.estNote=was.estNote;
    NDOC=doc;showForm();return;}
  showView(doc);
}
const STATUS={draft:"Draft",unpaid:"Unpaid",part_paid:"Part paid",overdue:"Overdue",paid:"Paid",cancelled:"Cancelled",
  // Phase 2.3: TCP owes the customer; credited in full (value and money both zero).
  in_credit:"In credit",credited:"Credited in full"};
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
    ${row("Cancelled",doc.state==="cancelled"&&doc.cancelled_at?dateText(doc.cancelled_at)+(doc.cancelled_by?" by "+doc.cancelled_by:""):"")}
    ${row("Cancelled because",doc.state==="cancelled"?doc.cancel_reason||"":"")}
    <div class="dk-total"><span>Total</span><b>${money(toP(doc.total))}</b></div>${moneyBlock(doc)}</div>`;
  $("#viewLines").innerHTML=(doc.lines||[]).map((l,i)=>`<div class="dk-vline"><span>${i+1}. ${esc(l.description)}<small>${fmtQ(l.quantity)} ${esc(UNIT_WORD(l.unit,l.quantity)||l.unit||"")} × ${money(toP(l.unit_price))}</small></span><b>${+l.unit_price===0&&l.kind==="product"?"Free item":money(toP(l.line_total))}</b></div>`).join("");
  $("#iMsg").textContent="";show("#copyBox",false);
  // A cancelled invoice keeps its PDF, marked CANCELLED, for TCP's records
  // (decision 4), but is never shared.
  const cancelled=doc.state==="cancelled"&&!!doc.invoice_no;
  show("#shareRow",issued||cancelled);show("#shareHelp",issued);show("#shareBtn",issued);
  showPayments(doc);
  showCredits(doc);
  $("#shareBtn").disabled=!issued;$("#pdfBtn").disabled=!(issued||cancelled);
  showCancel(doc);
  renderNotes(doc,false);
}
// Phase 2.3: once an invoice has credit notes, its money reads
// Total · Credited · Value · Paid · Owed (or "In credit", when TCP owes the
// customer). Every figure is the database's.
function moneyBlock(doc){
  if(!(doc.credit_notes||[]).length)return"";
  const bal=toP(doc.balance),r=(k,v)=>`<div><span>${k}</span><b>${v}</b></div>`;
  return r("Credited","−"+money(toP(doc.credited||0)))+r("Value",money(toP(doc.total)-toP(doc.credited||0)))
    +r("Paid",money(toP(doc.paid)))+(bal<0?r("In credit",`${money(-bal)} (TCP owes the customer)`):r("Owed",money(bal)));}
function fromDraft(doc){
  const items=doc.lines.filter(l=>l.kind==="product").map(l=>{const p=PRODUCTS.find(x=>x.id===l.product_id);
    return{kind:"product",pid:l.product_id,name:l.description,unit:l.unit,qty:+l.quantity,price:toP(l.unit_price),list:p?toP(p.current_price):null,quoted:null};});
  const fee=doc.lines.find(l=>l.kind==="delivery");
  const notes=String(doc.notes||"").split("\n");
  const dl=fee?"fee":notes.includes("Customer pickup")?"pickup":notes.includes("Free delivery")?"free":"pending";
  const ref=(notes.find(n=>EST_LINE.test(n))||"").slice(9)||null;
  return{...blank(),invoiceId:doc.id,customerId:doc.customer_id,customerCode:doc.customer_code,ref,
    name:doc.billed_to_name||"",phone:doc.billed_to_phone||"",site:doc.deliver_to_location||"",
    contact:doc.deliver_to_contact||"",contactPhone:doc.deliver_to_phone||"",items,dl,
    fee:fee?String(fee.unit_price):"",due:doc.due_date||"",
    note:notes.filter(n=>n&&n!=="Customer pickup"&&n!=="Free delivery"&&!EST_LINE.test(n)).join("\n"),dirty:false};
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
const fileName=doc=>`TCP Invoice ${doc.invoice_no}${doc.state==="cancelled"?" CANCELLED":""}.pdf`;
async function makePdf(doc){
  // An issued invoice, or one cancelled after issue (marked CANCELLED on
  // every page, decision 4 of Phase 2.1).
  const cancelled=!!doc&&doc.state==="cancelled"&&!!doc.invoice_no;
  if(!doc||(doc.state!=="issued"&&!cancelled))throw new Error("Only an issued invoice has a PDF");
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
  const ref=(notes.find(n=>EST_LINE.test(n))||"").slice(9);
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
    // A free item says so on the customer's PDF; its prices stay GH₵0.00.
    const free=l.kind==="product"&&+l.unit_price===0;
    font("semibold",9.5);const nameLines=wrap(l.description+(free?" — Free item":""),dW);
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
  const extra=notes.filter(n=>n!=="Customer pickup"&&n!=="Free delivery"&&!EST_LINE.test(n)).join("\n");
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
  // -- A cancelled invoice: a cancellation section under everything else,
  //    with the WHOLE reason, however long (wrapped, never cut short). If it
  //    doesn't fit above the footer it starts a new page.
  if(cancelled){
    const RED="#b3261e",clh=pt(9)*1.45;
    font("normal",9);const why=wrap(`Reason: ${String(doc.cancel_reason||"").trim()}`,W-8);
    const head=`CANCELLED${doc.cancelled_at?" on "+dateText(doc.cancelled_at):""}${doc.cancelled_by?" by "+doc.cancelled_by:""}`;
    const boxH=4+pt(10)*1.45+2+why.length*clh+3;
    let cy=Math.max(sy+gh,ny)+8;
    if(cy+boxH>BOTTOM){pdf.addPage();cy=TOP+6;}
    pdf.setDrawColor(RED);pdf.setLineWidth(.6);pdf.rect(L,cy,W,boxH);
    font("bold",10,RED);txt(head,L+4,cy+4);
    font("normal",9,INK);why.forEach((l,i)=>txt(l,L+4,cy+4+pt(10)*1.45+2+i*clh));
  }
  // -- Every page: footer; pages 2+ also a "continued" line at the top
  const n=pdf.getNumberOfPages();
  for(let p=1;p<=n;p++){pdf.setPage(p);
    font("normal",7,MUTE);txt(`${B.website}  ·  ${B.phone}`,L,289);txt(`Page ${p} of ${n}`,R,289,{right:1});
    if(p>1){font("bold",7.5);txt(`${B.name}  ·  ${DOC_TITLE} ${doc.invoice_no}`,L,9);font("normal",7.5,MUTE);txt("Continued",R,9,{right:1});}
    if(cancelled){
      // Across the page, faint, so the invoice stays readable.
      pdf.saveGraphicsState();pdf.setGState(new pdf.GState({opacity:0.14}));
      font("bold",64,"#b3261e");pdf.text("CANCELLED",38,205,{angle:35});
      pdf.restoreGraphicsState();
      // Above the footer, on every page: short, so it always fits; the
      // full reason is in the cancellation section.
      font("bold",8,"#b3261e");
      txt(`CANCELLED${doc.cancelled_at?" on "+dateText(doc.cancelled_at):""}. The reason is in the cancellation note.`,L,284);}}
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
// WhatsApp may or may not keep text shared together with a file (it varies
// by version), so the message is never shared with the file: it is copied
// to the clipboard first (while the tap still counts as
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
      // The PDF only, no text (E-01, 23 Nov 2026): some WhatsApp versions put
      // shared text into the caption themselves, so with the copied message
      // pasted it appeared twice. The message now travels one way only: the
      // clipboard, pasted once by the user.
      try{await navigator.share({files:[file],title:file.name});}catch(e){if(e.name!=="AbortError")throw e;}
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

// ---- 8b. Payments and receipts (phase 2) -----------------------------------
// "TCP Back Office: Phase 2 Design, Payments and Receipts (v1)", approved by
// ChatGPT and Daniel on 23 Nov 2026 (GitHub issue #39). The database does
// the money work: record_payment never takes more than is owed, numbers each
// receipt (TCP-RCT-0001…) and stores the balance after it; corrections and
// refunds are new receipts with a reason, never edits. This section only
// asks, and shows what the database says.
//   Who: anyone on the staff records a payment (decision 1); only the owner
//   and finance correct or refund (the database refuses anyone else).
const METHOD={mobile_money:"Mobile Money",cash:"Cash",bank_transfer:"Bank transfer"};
const REF_HINT={mobile_money:"MoMo transaction ID",bank_transfer:"bank reference",cash:"optional"};
const canFix=()=>!!ME&&(ME.role==="owner"||ME.role==="finance");
const canPay=()=>!!ME&&["owner","sales","finance"].includes(ME.role);
// Signed money: refunds and corrections are stored below zero.
const smoney=p=>p<0?"−"+money(-p):money(p);
let PAY=null,FIX=null,RDOC=null;
// -- The unfinished operation kept on this phone (Phase 2 design, amended
//    23 Nov 2026, "Option B", approved by Daniel and ChatGPT).
// When "Record it" is tapped, a payment, correction or refund is noted on
// this phone BEFORE it is sent, and removed once the database has answered.
// If the answer never comes (no connection, the reply lost, the sign-in ran
// out), the note keeps its request id, so the app can ask the database later
// whether it was recorded: if so it shows the original receipt, if not it
// offers the same operation again under the SAME request id. A new request
// id is never made while the outcome is unknown, so nothing is recorded
// twice. The note is temporary recovery data, never a financial record (the
// database is the only ledger). It holds only: invoice id, request id, kind,
// the payment it reverses, amount, method, reference, date and the reason
// (needed for the database to recognise the same request). No customer name
// or phone. It belongs to one staff member, and is removed on success,
// Cancel, sign-out, removed access, or after 24 hours.
const OP_TTL=24*60*60*1000;
const opKey=()=>"tcp-desk-op-"+(ME?ME.id:"");
const OP_WORD={payment:"payment",correction:"correction",refund:"refund"};
let RNOTE="";   // shown on the next receipt (e.g. "already recorded")
function pendingOp(){if(!ME)return null;let o=null;
  try{o=JSON.parse(localStorage.getItem(opKey())||"null")}catch(e){}
  if(o&&(o.user!==ME.id||!(Date.now()-o.at<OP_TTL))){dropOp();return null;}
  return o;}
function keepOp(o){if(!ME)return;const was=pendingOp();
  try{localStorage.setItem(opKey(),JSON.stringify({user:ME.id,at:was&&was.req===o.req?was.at:Date.now(),
    type:o.type,invoiceId:o.invoiceId,payId:o.payId||null,req:o.req,amount:o.amount,method:o.method,
    ref:o.ref||null,date:o.date||null,reason:o.reason||null}))}catch(e){}}
function dropOp(){try{localStorage.removeItem(opKey())}catch(e){}}
// A database refusal carries a Postgres error code: then nothing was saved.
// Any other failure leaves the outcome unknown.
const definite=e=>kind(e)==="refused"&&/^[0-9A-Z]{5}$/.test(String(e&&e.code||""));
// Ask the database whether this operation was recorded. A row with the same
// request id counts only if it is the SAME operation: invoice, kind, the
// payment it reverses and the amount must all match. Anything else is not
// taken as success, and nothing new is recorded (the database would refuse
// that request id for a different operation anyway).
async function recorded(op){
  const r=await api.byRequest(op.req);if(!r)return null;
  const same=+r.invoice_id===+op.invoiceId&&r.kind===op.type&&(r.reverses_payment_id==null?null:+r.reverses_payment_id)===(op.payId==null?null:+op.payId)
    &&Math.abs(Math.abs(toP(r.amount))-Math.abs(toP(op.amount)))===0;
  if(!same)throw Object.assign(new Error(`This request matches a different record (${r.receipt_no}), so it was not taken as recorded and nothing new was recorded. Ask the owner to check ${r.receipt_no}.`),{mismatch:true});
  return r;}

// The invoice's receipts, oldest first, with Correct and Refund where they
// still apply (the database works out "corrected" and "refunded").
function showPayments(doc){
  const pays=doc.payments||[],issued=doc.state==="issued",op=pendingOp();
  show("#payBox",issued||pays.length>0);
  $("#payList").innerHTML=pays.length?pays.map(p=>{
    const amt=toP(p.amount),what=p.kind==="payment"?"Payment":p.kind==="correction"?`Correction of ${esc(p.reverses_receipt_no||"")}`:`Refund of ${esc(p.reverses_receipt_no||"")}`;
    const refunded=toP(p.refunded||0),left=amt-refunded;
    const flag=p.kind!=="payment"?"":p.corrected?"corrected":refunded>0?`${money(refunded)} refunded`:"";
    const acts=p.kind==="payment"&&canFix()&&!p.corrected&&!op?
      `<span class="dk-pay-acts">${refunded===0?`<button type="button" class="dk-link" data-fix="correction" data-pid="${p.id}">Correct</button>`:""}${left>0?`<button type="button" class="dk-link" data-fix="refund" data-pid="${p.id}">Refund</button>`:""}</span>`:"";
    return`<div class="dk-pay"><a href="#/receipt/${p.id}" data-rid="${p.id}">
      <span class="dk-pay-top"><b>${esc(p.receipt_no)}</b><b class="${amt<0?"neg":""}">${smoney(amt)}</b></span>
      <span class="dk-pay-bot"><small>${what} · ${shortDate(p.paid_on)} · ${esc(METHOD[p.method]||p.method)}${p.reference?" · ref "+esc(p.reference):""}</small><small>left ${money(toP(p.balance_after))}</small></span>
      ${flag?`<span class="dk-pay-flag">${flag}</span>`:""}</a>${acts}${payNotesHTML(p,(RECORD_WORD[p.kind]||"payment").replace(/^./,c=>c.toUpperCase())+" note")}</div>`;}).join(""):`<p class="dk-help">No payments yet.</p>`;
  $("#paySum").innerHTML=issued||pays.length?`<span>Paid ${money(toP(doc.paid))}</span><span>${toP(doc.balance)<0?"In credit "+money(-toP(doc.balance)):"Left "+money(toP(doc.balance))}</span>`:"";
  // While an operation's outcome is unknown, nothing new can be started.
  show("#payBtn",issued&&toP(doc.balance)>0&&canPay()&&!op);
  show("#opBox",!!op);show("#opCheck",false);show("#opOpen",false);
  if(op&&op.invoiceId!==doc.id){show("#payBox",true);
    $("#opMsg").textContent=`A ${OP_WORD[op.type]} of ${money(toP(op.amount))} on another invoice has not been confirmed yet. Open that invoice to check it before recording anything new.`;
    $("#opOpen").href="#/invoice/"+op.invoiceId;show("#opOpen",true);}
  else if(op)checkOp(op);
}
// Ask the database whether a kept operation was recorded.
async function checkOp(op){
  const w=OP_WORD[op.type],amt=money(toP(op.amount));
  $("#opMsg").textContent=`Checking whether the ${w} of ${amt} was recorded…`;show("#opCheck",false);
  let r;
  try{r=await recorded(op);}
  catch(err){if(err.mismatch){$("#opMsg").textContent=err.message;return;}
    const k=kind(err);
    if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
    if(k==="expired")return expire();
    $("#opMsg").textContent=`Could not check whether the ${w} of ${amt} was recorded${k==="offline"?": no connection":""}. Nothing new can be recorded on this invoice until it is checked.`;
    show("#opCheck",true);return;}
  if(r){dropOp();RNOTE=`This ${w} was already recorded. Here is its receipt.`;return go("#/receipt/"+r.id);}
  // Not recorded: offer it again under the same request id.
  if(op.type==="payment"){if(DOC&&DOC.state==="issued"&&canPay())return openPay(op);}
  else{const pay=DOC&&(DOC.payments||[]).find(x=>x.id===op.payId);if(pay&&canFix())return openFix(op.type,pay,op);}
  dropOp();if(DOC)showView(DOC);
}
$("#opCheck").addEventListener("click",()=>{const op=pendingOp();if(op)checkOp(op);else if(DOC)showView(DOC);});
// Send a money operation. A retry of one whose outcome is unknown first
// asks the database, and gives back the original receipt if it was saved.
async function sendOp(op,state,call){
  if(state.sent){const r=await recorded(op);if(r)return{r,again:true};}
  keepOp(op);state.sent=true;
  return{r:await call(),again:false};}
function opDone({r,again}){dropOp();PAY=null;FIX=null;
  if(again)RNOTE=`This ${OP_WORD[r.kind]||"payment"} was already recorded. Here is its receipt.`;
  return go("#/receipt/"+r.id);}
// Errors while recording money: removed access signs out (and clears the
// note); an expired sign-in keeps the note for after signing in; a database
// refusal means nothing was saved; anything else leaves the outcome
// unknown, and the retry asks the database first.
async function opFailed(err,state,where){const k=kind(err);
  if(err&&err.mismatch){$(where).textContent=err.message;return;}
  if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
  if(k==="expired")return expire();
  if(definite(err)&&/request id was already used/.test(err.message||"")){
    const op=pendingOp();
    try{const r=op&&op.req===state.req&&await recorded(op);if(r)return opDone({r,again:true});}
    catch(e){if(e.mismatch){$(where).textContent=e.message;return;}}}
  if(definite(err)){dropOp();state.sent=false;$(where).textContent="Not recorded: "+String(err.message||err);return;}
  $(where).textContent=k==="offline"
    ?"No connection: it may or may not have been recorded. Tap Record it again when you have signal: it is checked first, and never recorded twice."
    :"Could not confirm it was recorded. Tap Record it again: it is checked first, and never recorded twice.";}
// Cancel: an operation that was sent with no answer is checked first.
async function cancelOp(state,where,close){
  if(state&&state.sent){let r;
    const op=pendingOp();
    try{r=op&&op.req===state.req?await recorded(op):await api.byRequest(state.req);}
    catch(err){if(err.mismatch){$(where).textContent=err.message;return;}
      const k=kind(err);if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
      if(k==="expired")return expire();
      $(where).textContent="Can't cancel yet: it could not be checked whether this was recorded. Try again when you have signal.";return;}
    if(r)return opDone({r,again:true});}
  dropOp();close();}

// -- Recording a payment (design section 3)
function openPay(kept){
  const doc=DOC;if(!doc)return;
  // One request id per payment, made when the form opens, kept for every
  // retry (double tap, no connection, lost reply) until it is recorded.
  PAY=kept?{invoiceId:kept.invoiceId,req:kept.req,amt:(+kept.amount).toFixed(2),method:kept.method,ref:kept.ref||"",date:kept.date||today(),sent:false}
    :{invoiceId:doc.id,req:newId(),amt:"",method:"",ref:"",date:today(),sent:false};
  // Notes are never kept on the phone (only in this form while it is open).
  PAY.cnote="";PAY.inote="";$("#pCustNote").value="";$("#pIntNote").value="";
  showOnly("#payForm");
  $("#payFor").textContent=`${doc.invoice_no} · ${doc.billed_to_name||""} · left to pay ${money(toP(doc.balance))}`;
  $("#pAmt").value=PAY.amt;$("#pRef").value=PAY.ref;$("#pDate").value=PAY.date;$("#pDate").max=today();
  document.querySelectorAll('input[name="pm"]').forEach(r=>r.checked=r.value===PAY.method);
  ["#pAmtErr","#pErr"].forEach(e=>{$(e).textContent="";});
  $("#pMsg").textContent=kept?"This payment was not recorded. Check it, then tap Continue and Record it. Notes are not kept on this phone: type any notes again.":"";
  show("#payFields",true);show("#pConfirm",false);refLabel("#pRefLabel",PAY.method);
  window.scrollTo(0,0);
}
function refLabel(sel,m){$(sel).textContent="Reference"+(m?` (${REF_HINT[m]})`:"");}
function payProblems(){
  const doc=DOC,out={};const v=typedNum(PAY.amt),p=isNaN(v)?NaN:toP(v),bal=toP(doc.balance);
  if(!String(PAY.amt).trim())out.amt="Enter the amount received.";
  else if(isNaN(p))out.amt="Enter a number.";
  else if(p<=0)out.amt="The amount must be more than GH₵0.00.";
  else if(p>bal)out.amt=`That is more than the ${money(bal)} left to pay.`;
  if(!PAY.method)out.rest="Choose how it was paid.";
  else if(PAY.method!=="cash"&&!PAY.ref.trim())out.rest=`Enter the ${REF_HINT[PAY.method]}.`;
  else if(!PAY.date)out.rest="Enter the date paid.";
  else if(PAY.date>today())out.rest="The date paid can't be in the future.";
  return{out,p};}
["#pAmt","#pRef","#pDate","#pCustNote","#pIntNote"].forEach(sel=>$(sel).addEventListener("input",()=>{if(!PAY)return;
  PAY.amt=$("#pAmt").value;PAY.ref=$("#pRef").value;PAY.date=$("#pDate").value;PAY.cnote=$("#pCustNote").value;PAY.inote=$("#pIntNote").value;
  $("#pAmtErr").textContent="";$("#pErr").textContent="";}));
document.querySelectorAll('input[name="pm"]').forEach(r=>r.addEventListener("change",()=>{if(!PAY)return;
  PAY.method=r.value;refLabel("#pRefLabel",PAY.method);$("#pErr").textContent="";}));
$("#pFull").addEventListener("click",()=>{if(!PAY||!DOC)return;PAY.amt=(toP(DOC.balance)/100).toFixed(2);$("#pAmt").value=PAY.amt;$("#pAmtErr").textContent="";});
$("#payBtn").addEventListener("click",()=>openPay(null));
$("#pCancel").addEventListener("click",()=>cancelOp(PAY,"#pMsg",()=>{PAY=null;if(DOC)showView(DOC);}));
$("#pNext").addEventListener("click",()=>{
  const{out,p}=payProblems();$("#pAmtErr").textContent=out.amt||"";$("#pErr").textContent=out.rest||"";
  if(out.amt||out.rest)return;
  // Confirm before saving: a receipt number is permanent.
  $("#pSummary").textContent=`${money(p)} by ${METHOD[PAY.method]}${PAY.ref.trim()?" (ref "+PAY.ref.trim()+")":""} for ${DOC.invoice_no}, paid ${shortDate(PAY.date)}. Balance after: ${money(toP(DOC.balance)-p)}.`
    +(PAY.cnote.trim()?` Note to the customer: ${PAY.cnote.trim()}`:"")+(PAY.inote.trim()?` Internal note: ${PAY.inote.trim()}`:"");
  show("#payFields",false);show("#pConfirm",true);$("#pMsg").textContent="";});
$("#pChange").addEventListener("click",()=>{show("#pConfirm",false);show("#payFields",true);});
$("#pYes").addEventListener("click",async()=>{
  const btn=$("#pYes");if(btn.disabled||!PAY)return;
  const{p}=payProblems(),st=PAY;busy(btn,true,"Recording…");$("#pMsg").textContent="";
  const op={type:"payment",invoiceId:st.invoiceId,req:st.req,amount:p/100,method:st.method,ref:st.ref.trim(),date:st.date};
  try{await opDone(await sendOp(op,st,()=>api.recordPayment({p_invoice_id:st.invoiceId,p_amount:p/100,p_method:st.method,
      p_reference:st.ref.trim()||null,p_paid_on:st.date,p_request_id:st.req,
      p_customer_note:st.cnote.trim()||null,p_internal_note:st.inote.trim()||null})));}
  catch(err){await opFailed(err,st,"#pMsg");}
  finally{busy(btn,false);}
});

// -- Correcting or refunding a payment (design section 6, owner and finance)
document.addEventListener("click",e=>{const b=e.target.closest("[data-fix]");if(!b||!DOC)return;
  const pay=(DOC.payments||[]).find(x=>x.id===+b.dataset.pid);if(pay)openFix(b.dataset.fix,pay,null);});
function openFix(kindName,pay,kept){
  FIX={kind:kindName,pay,req:kept?kept.req:newId(),amt:kept&&kindName==="refund"?(+kept.amount).toFixed(2):"",
    method:kept&&kindName==="refund"?kept.method:"",ref:kept&&kept.ref||"",why:kept&&kept.reason||"",sent:false,
    cnote:"",inote:""};   // notes are never kept on the phone
  $("#fCustNote").value="";$("#fIntNote").value="";
  showOnly("#fixForm");
  const left=toP(pay.amount)-toP(pay.refunded||0);
  $("#fixTitle").textContent=kindName==="correction"?"Correct a payment":"Refund a payment";
  $("#fixFor").textContent=kindName==="correction"
    ?`Reverses all of ${pay.receipt_no} (${money(toP(pay.amount))} by ${METHOD[pay.method]}). Use it when the payment was recorded wrongly; then record the right payment.`
    :`From ${pay.receipt_no} (${money(toP(pay.amount))} by ${METHOD[pay.method]}). Up to ${money(left)} can be refunded.`;
  // Phase 2.3: an invoice in credit (TCP owes the customer). Both figures,
  // and the smaller one filled in (it can be changed). The database's
  // refund rule is unchanged: never more than the payment's unrefunded amount.
  const inCredit=-toP(DOC.balance);
  if(kindName==="refund"&&inCredit>0){
    $("#fixFor").textContent=`In credit on this invoice: ${money(inCredit)}. Still refundable from this payment (${pay.receipt_no}): ${money(left)}.`;
    if(!kept)FIX.amt=(Math.min(inCredit,left)/100).toFixed(2);}
  show("#fixMoney",kindName==="refund");
  // A correction is internal: no note to the customer.
  show("#fCustNoteBox",kindName==="refund");
  $("#fAmt").value=FIX.amt;$("#fRef").value=FIX.ref;$("#fWhy").value=FIX.why;
  document.querySelectorAll('input[name="fm"]').forEach(r=>r.checked=r.value===FIX.method);
  refLabel("#fRefLabel",FIX.method);$("#fErr").textContent="";
  $("#fMsg").textContent=kept?`This ${OP_WORD[kindName]} was not recorded. Check it, then tap Continue and Record it. Notes are not kept on this phone: type any notes again.`:"";
  show("#fixFields",true);show("#fConfirm",false);window.scrollTo(0,0);
}
function fixProblems(){const out=[];let p=0;
  if(FIX.kind==="refund"){const left=toP(FIX.pay.amount)-toP(FIX.pay.refunded||0),v=typedNum(FIX.amt);p=isNaN(v)?NaN:toP(v);
    if(!String(FIX.amt).trim())out.push("Enter the amount refunded.");else if(isNaN(p))out.push("Enter a number.");
    else if(p<=0)out.push("The amount must be more than GH₵0.00.");else if(p>left)out.push(`At most ${money(left)} can be refunded from ${FIX.pay.receipt_no}.`);
    if(!FIX.method)out.push("Choose how it was given back.");else if(FIX.method!=="cash"&&!FIX.ref.trim())out.push(`Enter the ${REF_HINT[FIX.method]}.`);}
  else p=toP(FIX.pay.amount);
  if(!FIX.why.trim())out.push("Give a reason: it is kept with the record.");
  return{out,p};}
["#fAmt","#fRef","#fWhy","#fCustNote","#fIntNote"].forEach(sel=>$(sel).addEventListener("input",()=>{if(!FIX)return;
  FIX.amt=$("#fAmt").value;FIX.ref=$("#fRef").value;FIX.why=$("#fWhy").value;FIX.cnote=$("#fCustNote").value;FIX.inote=$("#fIntNote").value;$("#fErr").textContent="";}));
document.querySelectorAll('input[name="fm"]').forEach(r=>r.addEventListener("change",()=>{if(!FIX)return;FIX.method=r.value;refLabel("#fRefLabel",r.value);}));
$("#fAll").addEventListener("click",()=>{if(!FIX)return;FIX.amt=((toP(FIX.pay.amount)-toP(FIX.pay.refunded||0))/100).toFixed(2);$("#fAmt").value=FIX.amt;});
$("#fCancel").addEventListener("click",()=>cancelOp(FIX,"#fMsg",()=>{FIX=null;if(DOC)showView(DOC);}));
$("#fNext").addEventListener("click",()=>{const{out,p}=fixProblems();$("#fErr").textContent=out.join(" ");if(out.length)return;
  const after=toP(DOC.balance)+p;
  $("#fSummary").textContent=(FIX.kind==="correction"
    ?`Reverse ${FIX.pay.receipt_no} (${money(p)}) because: ${FIX.why.trim()}. Balance after: ${money(after)}.`
    :`Refund ${money(p)} by ${METHOD[FIX.method]} from ${FIX.pay.receipt_no} because: ${FIX.why.trim()}. Balance after: ${money(after)}.`)
    +(FIX.kind==="refund"&&FIX.cnote.trim()?` Note to the customer: ${FIX.cnote.trim()}`:"")+(FIX.inote.trim()?` Internal note: ${FIX.inote.trim()}`:"");
  show("#fixFields",false);show("#fConfirm",true);$("#fMsg").textContent="";});
$("#fChange").addEventListener("click",()=>{show("#fConfirm",false);show("#fixFields",true);});
$("#fYes").addEventListener("click",async()=>{
  const btn=$("#fYes");if(btn.disabled||!FIX)return;const{p}=fixProblems(),st=FIX;
  busy(btn,true,"Recording…");$("#fMsg").textContent="";
  const corr=st.kind==="correction",why=st.why.trim();
  const op={type:st.kind,invoiceId:DOC.id,payId:st.pay.id,req:st.req,amount:p/100,method:corr?st.pay.method:st.method,
    ref:corr?null:st.ref.trim(),reason:why};
  try{await opDone(await sendOp(op,st,()=>corr
      ?api.correctPayment({p_payment_id:st.pay.id,p_reason:why,p_request_id:st.req,p_internal_note:st.inote.trim()||null})
      :api.refundPayment({p_payment_id:st.pay.id,p_amount:p/100,p_method:st.method,p_reason:why,
          p_reference:st.ref.trim()||null,p_request_id:st.req,
          p_customer_note:st.cnote.trim()||null,p_internal_note:st.inote.trim()||null})));}
  catch(err){await opFailed(err,st,"#fMsg");}
  finally{busy(btn,false);}
});

// -- One receipt (design section 4): read from receipt_document, which is
//    frozen at the moment it was recorded.
const RTITLE={payment:"Receipt",correction:"Correction",refund:"Refund"};
async function showReceipt(id){
  showOnly("#rcptSec");$("#rcpt").innerHTML="";$("#rNotes").innerHTML="";$("#rMsg").textContent="";show("#rCopyBox",false);
  const note=RNOTE;RNOTE="";
  let rd;try{rd=await api.receipt(id);}catch(err){return readFailed(err,"#rMsg");}
  $("#rMsg").textContent=note;
  RDOC={...rd,id};const inv=rd.invoice||{},amt=toP(rd.amount),bal=toP(rd.balance_after),full=rd.kind==="payment"&&bal===0;
  $("#rTitle").textContent=`${RTITLE[rd.kind]||"Receipt"} ${rd.receipt_no}`;
  const row=(k,v)=>v?`<div><span>${k}</span><b>${esc(v)}</b></div>`:"";
  $("#rcpt").innerHTML=`${full?`<span class="dk-paidfull">PAID IN FULL</span>`:""}<div class="dk-sum">
    ${row("Invoice",inv.invoice_no)}
    ${row(rd.kind==="payment"?"Received from":"Customer",[inv.billed_to_name,inv.billed_to_phone].filter(Boolean).join(" · "))}
    ${row("Date",rd.paid_on?dateText(rd.paid_on):"")}
    ${row(rd.kind==="payment"?"Amount received":rd.kind==="refund"?"Amount refunded":"Amount reversed",smoney(amt))}
    ${row("Method",METHOD[rd.method]||rd.method)}
    ${row("Reference",rd.reference||"")}
    ${row("Reverses",rd.reverses_receipt_no||"")}
    ${row("Reason",rd.reason||"")}
    ${row("Invoice total",money(toP(inv.total)))}
    ${row("Paid before this receipt",money(toP(rd.paid_before)))}
    ${row("Recorded by",rd.recorded_by||"")}
    <div class="dk-total"><span>Balance after</span><b>${money(bal)}</b></div></div>`;
  // A correction is internal: a PDF, but no Share (decision 5).
  const internal=rd.kind==="correction";
  show("#rShare",!internal);show("#rInternal",internal);
  $("#rInv").href="#/invoice/"+inv.id;
  // Phase 2.2: both notes, shown to staff (the PDF prints only the note to
  // the customer; the WhatsApp message carries neither).
  $("#rNotes").innerHTML=payNotesHTML({...rd,id:RDOC.id},(RECORD_WORD[rd.kind]||"payment").replace(/^./,c=>c.toUpperCase())+" note");
}
function waReceiptText(rd){const inv=rd.invoice||{},first=String(inv.billed_to_name||"").trim().split(/\s+/)[0]||"",bal=toP(rd.balance_after);
  const what=rd.kind==="refund"?"refund receipt":"receipt";
  return`Hello${first?" "+first:""}, here is your ${what} ${rd.receipt_no} for ${money(Math.abs(toP(rd.amount)))} on invoice ${inv.invoice_no}. `
    +(rd.kind==="payment"&&bal===0?`Invoice ${inv.invoice_no} is now paid in full. Thank you.`:`Balance: ${money(bal)}.`);}
const receiptFileName=rd=>`TCP Receipt ${rd.receipt_no}.pdf`;
// Re-read before every PDF, as for invoices (and a removed staff member
// gets nothing).
async function freshReceipt(){const rd=await api.receipt(RDOC.id);RDOC={...rd,id:RDOC.id};return RDOC;}
async function receiptFile(rd){const pdf=await makeReceiptPdf(rd);return new File([pdf.output("blob")],receiptFileName(rd),{type:"application/pdf"});}
$("#rCopyBtn").addEventListener("click",async()=>{const ta=$("#rCopyText");ta.select();
  let ok=await copyText(ta.value);if(!ok){try{ok=document.execCommand("copy");}catch(e){}}
  $("#rMsg").textContent=ok?"Message copied. Paste it in WhatsApp.":"Select the message above and copy it.";});
$("#rShare").addEventListener("click",async()=>{
  const btn=$("#rShare"),m=$("#rMsg");show("#rCopyBox",false);m.textContent="";
  if(!RDOC||RDOC.kind==="correction")return;
  const copied=copyText(waReceiptText(RDOC));
  busy(btn,true,"Preparing PDF…");
  try{const rd=await freshReceipt(),file=await receiptFile(rd),text=waReceiptText(rd);
    let note;
    if(await copied)note="Message copied. In WhatsApp, paste it as the caption before sending.";
    else{$("#rCopyText").value=text;show("#rCopyBox",true);note="Copy the message below, then paste it in WhatsApp as the caption.";}
    if(navigator.canShare&&navigator.canShare({files:[file]})){
      m.textContent=note;
      // The PDF only, as for invoices (E-01): the message is pasted once.
      try{await navigator.share({files:[file],title:file.name});}catch(e){if(e.name!=="AbortError")throw e;}
    }else{download(file);const to=waNumber((rd.invoice||{}).billed_to_phone);
      if(to)window.open("https://wa.me/"+to+"?text="+encodeURIComponent(text),"_blank","noopener");
      m.textContent="This browser cannot share files: the PDF was downloaded. Attach it in the WhatsApp chat. "+note;}
  }catch(e){kind(e)==="refused"?(m.textContent="Could not prepare the receipt: "+(e.message||e)):failed(e,"#rMsg");}
  finally{busy(btn,false);}});
$("#rPdf").addEventListener("click",async()=>{const btn=$("#rPdf"),m=$("#rMsg");busy(btn,true,"Preparing PDF…");
  try{download(await receiptFile(await freshReceipt()));m.textContent="Receipt PDF downloaded.";}
  catch(e){kind(e)==="refused"?(m.textContent="Could not prepare the receipt: "+(e.message||e)):failed(e,"#rMsg");}
  finally{busy(btn,false);}});

// The receipt PDF (A4), in the invoice's look. Every figure is the
// database's, as recorded at that moment: "paid before" and the balance
// after do not change when later payments come in.
async function makeReceiptPdf(rd){
  const{jsPDF,logo}=await pdfKit(),F=window.TCP_PDF_FONTS,inv=rd.invoice||{};
  const pdf=new jsPDF({unit:"mm",format:"a4",compress:true});
  [["r","normal"],["s","semibold"],["x","bold"]].forEach(([k,st])=>{pdf.addFileToVFS(`M-${k}.ttf`,F[k]);pdf.addFont(`M-${k}.ttf`,"Montserrat",st);});
  const title=(RTITLE[rd.kind]||"Receipt").toUpperCase();
  pdf.setProperties({title:`${B.name} ${title} ${rd.receipt_no}`,author:B.name,creator:"TCP Back Office"});
  const INK="#131514",MUTE="#5a5a5a",LINE="#dcdcdc",OCHRE="#ff9802",BAND="#f4f4f4",GREEN="#1e6b34";
  const L=14,R=196,W=R-L,TOP=16,pt=n=>n*0.3528;
  const font=(st,size,col)=>{pdf.setFont("Montserrat",st);pdf.setFontSize(size);pdf.setTextColor(col||INK);};
  const txt=(str,x,y,o={})=>{const sp=o.sp||0,w=pdf.getTextWidth(str)+sp*Math.max(0,str.length-1);
    pdf.text(str,o.right?x-w:x,y,{baseline:"top",charSpace:sp});return w;};
  const wrap=(str,w)=>pdf.splitTextToSize(str,w);
  const amt=toP(rd.amount),bal=toP(rd.balance_after),full=rd.kind==="payment"&&bal===0;
  // The PDF font has no "−" (U+2212), so the PDF uses an ordinary minus:
  // a reversed amount must never print as if money came in.
  const pmoney=p=>p<0?"-"+money(-p):money(p);
  // -- Header
  pdf.addImage(logo,"PNG",L,TOP,13*5.92329,13);
  font("bold",17);txt(title,R,TOP,{right:1,sp:pt(17)*.08});
  const dl=[["Receipt no.",rd.receipt_no],["Date",dateText(rd.paid_on)],["Invoice no.",inv.invoice_no||""]];
  font("bold",9);const vw=Math.max(...dl.map(r=>pdf.getTextWidth(r[1])));
  let y=TOP+8.5;
  dl.forEach(([k,v])=>{font("bold",9);txt(v,R,y,{right:1});font("normal",9,MUTE);txt(k,R-vw-4,y,{right:1});y+=4.3;});
  y=Math.max(TOP+13,y)+4.5;
  pdf.setFillColor(INK);pdf.rect(L,y,W,.8,"F");pdf.setFillColor(OCHRE);pdf.rect(L,y,28,.8,"F");y+=.8+4.5;
  // -- Grey band: who, how, from
  const how=`${METHOD[rd.method]||rd.method}${rd.reference?`\nRef ${rd.reference}`:""}`;
  const cols=[[rd.kind==="payment"?"Received from":"Customer",[inv.billed_to_name,inv.billed_to_phone].filter(Boolean).join("\n")],
    [rd.kind==="payment"?"Paid by":rd.kind==="refund"?"Refunded by":"Method",how],["From",`${B.name}\n${B.phone} (call or WhatsApp)\n${B.website}\n${B.town}`]];
  const inner=W-.8-7,gap=6,unitW=(inner-2*gap)/3.7,cw=[1.5,1,1.2].map(r=>r*unitW);
  font("semibold",8.5);const lh=pt(8.5)*1.45;
  const lines=cols.map((c,i)=>c[1].split("\n").flatMap(l=>wrap(l,cw[i])));
  const bandH=3+pt(7)*1.2+.6+Math.max(...lines.map(l=>l.length))*lh+3;
  pdf.setFillColor(BAND);pdf.rect(L,y,W,bandH,"F");pdf.setFillColor(OCHRE);pdf.rect(L,y,.8,bandH,"F");
  let x=L+.8+3.5;
  cols.forEach((c,i)=>{font("bold",7,MUTE);txt(c[0].toUpperCase(),x,y+3,{sp:pt(7)*.1});
    font("semibold",8.5);lines[i].forEach((l,j)=>txt(l,x,y+3+pt(7)*1.2+.6+j*lh));x+=cw[i]+gap;});
  y+=bandH+8;
  // -- The amount, large
  font("bold",8,MUTE);txt((rd.kind==="payment"?"Amount received":rd.kind==="refund"?"Amount refunded":"Amount reversed").toUpperCase(),L,y,{sp:pt(8)*.1});
  y+=5;font("bold",24);txt(pmoney(amt),L,y);
  if(full){pdf.setDrawColor(GREEN);pdf.setLineWidth(.8);const sw=52;pdf.rect(R-sw,y-1,sw,11);font("bold",12,GREEN);txt("PAID IN FULL",R-sw/2-pdf.getTextWidth("PAID IN FULL")/2,y+2.2);}
  y+=16;
  // -- Reason and what it reverses (corrections and refunds)
  if(rd.kind!=="payment"){font("bold",7.5,MUTE);txt("REVERSES RECEIPT",L,y,{sp:pt(7.5)*.1});font("semibold",9.5);txt(rd.reverses_receipt_no||"",L+45,y);y+=6;
    font("bold",7.5,MUTE);txt("REASON",L,y,{sp:pt(7.5)*.1});font("normal",9.5);wrap(rd.reason||"",W-45).forEach((l,j)=>txt(l,L+45,y+j*pt(9.5)*1.45));y+=6+pt(9.5)*1.45;}
  // -- The account at that moment
  const TW=110,sx=R-TW,rowH=1.2*2+pt(9.5)*1.45;let sy=y;
  pdf.setFillColor(INK);pdf.rect(sx,sy,TW,.5,"F");sy+=.5;
  const sumRow=(k,v,st)=>{font(st,9.5);txt(k,sx+2.5,sy+1.2);txt(v,R-2.5,sy+1.2,{right:1});sy+=rowH;pdf.setDrawColor(LINE);pdf.setLineWidth(.25);pdf.line(sx,sy,R,sy);};
  sumRow(`Invoice ${inv.invoice_no||""} total`,money(toP(inv.total)),"semibold");
  sumRow("Paid before this receipt",money(toP(rd.paid_before)),"semibold");
  sumRow(`This ${rd.kind==="payment"?"receipt":rd.kind}`,pmoney(amt),"semibold");
  sy+=1.5;const gh=3*2+pt(11)*1.45;
  pdf.setFillColor(INK);pdf.rect(sx,sy,TW,gh,"F");pdf.setFillColor(OCHRE);pdf.rect(sx,sy,1.5,gh,"F");
  font("bold",11,"#ffffff");txt("Balance after",sx+1.5+2.5,sy+3);txt(money(bal),R-2.5,sy+3,{right:1});
  // -- Left of the account: notes
  // Phase 2.2: the note to the customer is printed; the internal note never is.
  let ny=y;const nb=[["Note",rd.customer_note||""],["Recorded by",rd.recorded_by||""],["Questions",`WhatsApp or call ${B.phone} and quote ${rd.receipt_no}.`],["Terms","All amounts are in Ghana cedis (GH₵)."]];
  nb.filter(n=>n[1]).forEach(([h,b])=>{font("bold",7.5,MUTE);txt(h.toUpperCase(),L,ny,{sp:pt(7.5)*.1});ny+=pt(7.5)*1.4+1.5;
    font("normal",7.5,"#333333");wrap(b,W-TW-8).forEach(l=>{txt(l,L,ny);ny+=pt(7.5)*1.4;});ny+=3;});
  font("normal",7,MUTE);txt(`${B.website}  ·  ${B.phone}`,L,289);txt("Page 1 of 1",R,289,{right:1});
  return pdf;
}

// ---- 8c. Payments tab and cancelling invoices (Phase 2.1) ---------------
// "TCP Back Office: Phase 2.1 Design, Payments Ledger and Cancelling
// Invoices (v1.1)", approved by ChatGPT and Daniel on 24 Nov 2026.
// Every figure is the database's (payment_totals); the phone never adds up
// money. The totals cover the whole period whatever the filters, search or
// paging, so the headline never changes because of them.
const PERIOD_WORD={today:"Today",week:"This week",month:"This month",all:"All time"};
const KIND_OK=["all","payment","refund","correction"],METHOD_OK=["all","mobile_money","cash","bank_transfer"];
let LED={period:"today",kind:"all",method:"all",q:"",from:null,to:null,rows:[],count:0,seq:0};
// Search: the database keeps each record's receipt, invoice, customer name,
// reference and phone (as +233… and as 0…) in one lower-case text. Words are
// matched as typed. A phone number typed any way is also matched on its
// digits without the country code or the leading 0 (so "4567" also works).
function ledgerTerms(q){
  const raw=String(q||"").trim(),out=[];
  const clean=raw.toLowerCase().replace(/[^\p{L}\p{N} .\-'&\/]/gu," ").trim().replace(/\s+/g,"*");
  if(clean)out.push(`*${clean}*`);
  // Only something typed like a phone number (digits, spaces, +, -, brackets)
  // is also matched as one: "TCP-INV-0002" must not find every "002".
  if(!/^[\d\s+\-()]+$/.test(raw))return out;
  let d=raw.replace(/\D/g,"");
  if(/^\s*\+\s*233/.test(raw))d=d.slice(3);
  else if(d.startsWith("00233"))d=d.slice(5);
  else if(d.length===12&&d.startsWith("233"))d=d.slice(3);
  else if(d.startsWith("0"))d=d.slice(1);
  if(d.length>=3&&!out.includes(`*${d}*`))out.push(`*${d}*`);
  return out;
}
const ledgerHash=(o)=>{const p=new URLSearchParams();
  if(o.period&&o.period!=="today")p.set("period",o.period);
  if(o.kind&&o.kind!=="all")p.set("kind",o.kind);
  if(o.method&&o.method!=="all")p.set("method",o.method);
  if(o.q)p.set("q",o.q);
  const qs=p.toString();return"#/payments"+(qs?"?"+qs:"");};
const byMethod=t=>[["mobile_money","MoMo"],["cash","Cash"],["bank_transfer","Bank"]]
  .map(([k,w])=>`${w} ${money(toP(t[k]))}`).join(" · ");
function periodText(t){
  if(t.period==="all")return"All time";
  if(t.from===t.to)return`${PERIOD_WORD[t.period]}, ${shortDate(t.from)}`;
  return`${PERIOD_WORD[t.period]}, ${shortDate(t.from)} to ${shortDate(t.to)}`;}
async function showLedger(params){
  view("#ledV","payments");
  const period=PERIOD_WORD[params.get("period")]?params.get("period"):"today";
  const k=KIND_OK.includes(params.get("kind"))?params.get("kind"):"all";
  const m=METHOD_OK.includes(params.get("method"))?params.get("method"):"all";
  const q=params.get("q")||"";
  $("#lq").value=q;
  document.querySelectorAll("#periods button").forEach(b=>b.classList.toggle("on",b.dataset.period===period));
  document.querySelectorAll("#kinds button").forEach(b=>b.classList.toggle("on",b.dataset.kind===k));
  document.querySelectorAll("#methods button").forEach(b=>b.classList.toggle("on",b.dataset.method===m));
  LED={period,kind:k,method:m,q,from:null,to:null,rows:[],count:0,seq:LED.seq+1};
  const my=LED.seq;
  $("#ledRows").innerHTML="";$("#ledMsg").textContent="";$("#ledInfo").textContent="";show("#ledMore",false);
  try{
    const t=await api.totals(period);
    if(my!==LED.seq)return;
    LED.from=t.from;LED.to=t.to;
    $("#ledWhen").textContent=periodText(t);
    $("#tNet").textContent=smoney(toP(t.net));
    $("#tRec").textContent=money(toP(t.received.total));$("#tRecBy").textContent=byMethod(t.received);
    const refunded=toP(t.refunded.total);
    show("#tRefBox",refunded>0);
    $("#tRef").textContent=money(refunded);$("#tRefBy").textContent=byMethod(t.refunded);
    $("#tCount").textContent=t.records;
  }catch(err){if(my===LED.seq)readFailed(err,"#ledMsg");return;}
  await ledgerMore();
}
// One row: the kind is said in words, so the three kinds never depend on
// colour. A corrected payment stays, struck through; a correction moves no
// money ("reverses"); a refund is money out.
function ledgerRowHTML(r){
  const amt=toP(r.amount),how=METHOD[r.method]||r.method;
  let label,amount,cls="";
  if(r.kind==="payment"&&r.corrected){label=`<i class="dk-kind k-corrected">Payment · corrected</i>`;amount=`<span class="amt"><s>${money(amt)}</s></span>`;cls="k-corrected";}
  else if(r.kind==="payment"){label=`<i class="dk-kind k-payment">Payment</i>`;amount=`<span class="amt">+${money(amt)}</span>`;}
  else if(r.kind==="refund"){label=`<i class="dk-kind k-refund">Refund of ${esc(r.reverses_receipt_no||"")}</i>`;amount=`<span class="amt out">−${money(-amt)}</span>`;}
  else{label=`<i class="dk-kind k-correction">Correction of ${esc(r.reverses_receipt_no||"")}</i>`;amount=`<span class="amt rev">Reverses ${money(-amt)}</span>`;}
  return`<a class="dk-led ${cls}" href="#/receipt/${r.id}" data-rid="${r.id}">
    <span class="dk-led-top"><b>${esc(r.receipt_no)}${r.internal_note?`<i class="dk-note-led" title="Has an internal note">note</i>`:""}</b>${label}</span>
    <span class="dk-led-bot"><small>${esc(r.invoice_no||"")} · ${esc(r.billed_to_name||"(no name)")} · ${shortDate(r.paid_on)} · ${esc(how)}${r.reference?" · ref "+esc(r.reference):""}</small>${amount}</span>
  </a>`;}
async function ledgerMore(){
  const my=LED.seq,btn=$("#ledMore");busy(btn,true,"Loading…");$("#ledMsg").textContent="";
  try{
    const res=await api.ledger({from:LED.from,to:LED.to,kind:LED.kind,method:LED.method,terms:ledgerTerms(LED.q),offset:LED.rows.length,limit:PAGE});
    if(my!==LED.seq)return;
    LED.rows=LED.rows.concat(res.rows);LED.count=res.count;
    const narrowed=LED.q||LED.kind!=="all"||LED.method!=="all";
    $("#ledRows").innerHTML=LED.rows.length?LED.rows.map(ledgerRowHTML).join(""):`<p class="dk-help">${narrowed?"No records match.":"No payments recorded in this period."}</p>`;
    $("#ledInfo").textContent=LED.count?`${LED.count} ${LED.count===1?"record":"records"}${narrowed?" match":""} · newest first`:"";
    show("#ledMore",LED.rows.length<LED.count);
  }catch(err){if(my===LED.seq)readFailed(err,"#ledMsg");}
  finally{busy(btn,false);}
}
$("#ledMore").addEventListener("click",ledgerMore);
$("#periods").addEventListener("click",e=>{const b=e.target.closest("[data-period]");if(b)go(ledgerHash({...LED,period:b.dataset.period}));});
$("#kinds").addEventListener("click",e=>{const b=e.target.closest("[data-kind]");if(b)go(ledgerHash({...LED,kind:b.dataset.kind}));});
$("#methods").addEventListener("click",e=>{const b=e.target.closest("[data-method]");if(b)go(ledgerHash({...LED,method:b.dataset.method}));});
// Searching as you type: the list only (the totals are for the period).
let ledTyping=null;
function ledgerSearch(){const q=$("#lq").value.trim(),h=ledgerHash({...LED,q});history.replaceState(null,"",h);HERE=h;
  LED={...LED,q,rows:[],count:0,seq:LED.seq+1};$("#ledRows").innerHTML="";ledgerMore();}
$("#lq").addEventListener("input",()=>{clearTimeout(ledTyping);ledTyping=setTimeout(ledgerSearch,350);});
$("#ledSearchForm").addEventListener("submit",e=>{e.preventDefault();clearTimeout(ledTyping);ledgerSearch();});

// ---- Phase 2.2: internal notes ------------------------------------------------
// Internal notes are for TCP staff only: never on a PDF, a WhatsApp message
// or the address. A note is never edited: a mistake is fixed with a new,
// linked note (a correction), and the original stays, struck through, with
// its latest correction beneath it. Each note can be corrected once, so a
// chain is one straight line: original, correction 1, correction 2…
// ONE renderer (noteHTML) draws a note everywhere it appears (the invoice's
// notes log, the payment history, the receipt view and Notes search), so a
// chain always reads the same in all four places.
const NCAT={general:"General",payment:"Payment",delivery:"Delivery",customer_request:"Customer request",
  complaint:"Complaint",stock:"Stock",follow_up:"Follow-up"};
const RECORD_WORD={payment:"payment",refund:"refund",correction:"correction"};
// A note's time, in Ghana time whatever the phone's clock is set to.
function noteTime(at){if(!at)return"";try{return new Date(at).toLocaleString("en-GB",{timeZone:"Africa/Accra",day:"numeric",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:false});}catch(e){return String(at);}}
const timesText=n=>`Corrected ${n} ${n===1?"time":"times"}`;
// What a correction corrects, in words, linked to it.
function correctsHTML(c){
  if(c.corrects_note_id)return`<span class="dk-note-corrects">Corrects ${esc(c.corrects_by||"a")}'s note of ${esc(noteTime(c.corrects_at))}</span>`;
  if(c.corrects_payment_id)return`<span class="dk-note-corrects">Correction to the internal note on ${RECORD_WORD[c.corrects_kind]||"payment"} <a href="#/receipt/${c.corrects_payment_id}">${esc(c.corrects_receipt_no||"")}</a></span>`;
  return"";}
// The latest correction beneath a corrected note: who, when, its words, and
// how many times the note has been corrected. The same in every view.
function latestHTML(chain){
  if(!chain||!chain.length)return"";const l=chain[chain.length-1];
  return`<div class="dk-note-latest" data-latest="${l.id}"><small>Latest correction · ${esc(l.by||"")} · ${esc(noteTime(l.at))} · ${timesText(chain.length)}</small>${esc(l.body)}</div>`;}
// One note. n: {id, body, by, at, tags[], chain[], corrects (html), acts
// (html), bodyHTML (search: the body with matched words marked)}.
function noteHTML(n){
  const corrected=!!(n.chain&&n.chain.length);
  const tags=(n.tags||[]).map(t=>`<i class="dk-note-tag">${esc(t)}</i>`).join("")
    +(n.correction?`<i class="dk-note-tag t-correction">Correction</i>`:"")
    +(corrected?`<i class="dk-note-tag t-corrected">Corrected</i>`:"");
  return`<div class="dk-note${corrected?" k-corrected":""}"${n.id?` data-note="${n.id}"`:""}>
    <div class="dk-note-head">${tags}<span>${esc(n.by||"")}${n.at?" · "+esc(noteTime(n.at)):""}</span></div>
    ${n.corrects?`<div class="dk-note-head">${n.corrects}</div>`:""}
    <p class="dk-note-body">${n.bodyHTML!=null?n.bodyHTML:esc(n.body)}</p>
    ${latestHTML(n.chain)}
    ${n.acts?`<div class="dk-note-acts">${n.acts}</div>`:""}
  </div>`;}
// "Correct this note" on the latest entry of a chain; on a corrected note
// it reads "Correct the latest" and corrects the end of its chain.
function corrActs(chain,target){
  if(chain&&chain.length)return`<button type="button" class="dk-link" data-ncorr="note" data-nid="${chain[chain.length-1].id}">Correct the latest</button>`;
  return target.note?`<button type="button" class="dk-link" data-ncorr="note" data-nid="${target.note}">Correct this note</button>`
                    :`<button type="button" class="dk-link" data-ncorr="payment" data-pid="${target.payment}">Correct this note</button>`;}
// A payment record's notes (payment history and receipt view): the note
// to the customer as printed, and the internal note with its chain.
function payNotesHTML(p,label){
  let h="";
  if(p.customer_note)h+=`<p><span class="lbl">Note to the customer:</span> ${esc(p.customer_note)}</p>`;
  if(p.internal_note)h+=noteHTML({body:p.internal_note,by:p.recorded_by_name||p.recorded_by||"",at:p.recorded_at,
    tags:[label||"Internal note"],chain:p.internal_note_chain||[],acts:corrActs(p.internal_note_chain,{payment:p.id})});
  return h?`<div class="dk-pay-notes">${h}</div>`:"";}

// -- The invoice's notes log (under the draft form or the invoice view)
let NDOC=null;          // the invoice whose notes are shown: {id,state,internal_notes}
let NADD={req:newId()}; // the note being added; a new request id per new note
// A note's chain in the log: follow corrected_by_note_id to the end.
function chainIn(list,note){const by=new Map(list.map(n=>[n.id,n])),out=[];let c=note;
  while(c&&c.corrected_by_note_id&&out.length<1000){c=by.get(c.corrected_by_note_id);if(c)out.push(c);}
  return out;}
function renderNotes(doc,draftForm){
  NDOC=doc?{id:doc.id,state:doc.state,internal_notes:doc.internal_notes||[]}:null;
  show("#notesSec",true);
  const has=!!(NDOC&&NDOC.id);
  show("#nAdd",has);show("#nNeedSave",!has);
  const list=has?NDOC.internal_notes:[];
  const copy=draftForm&&canEdit();
  $("#nList").innerHTML=list.length?list.map(n=>{
    const chain=chainIn(list,n),was=n.corrects_note_id&&list.find(x=>x.id===n.corrects_note_id);
    const tags=[NCAT[n.category]||n.category].concat(n.estimate_ref?["From estimate "+n.estimate_ref]:[]);
    return noteHTML({id:n.id,body:n.body,by:n.by,at:n.at,tags,chain,correction:!!(n.corrects_note_id||n.corrects_payment_id),
      corrects:correctsHTML({...n,corrects_by:was?was.by:null,corrects_at:was?was.at:null}),acts:corrActs(chain,{note:n.id})+(copy&&n.estimate_ref?`<button type="button" class="dk-link" data-ncopy="${n.id}">Copy to note to customer</button>`:"")});
  }).join(""):(has?`<p class="dk-help">No internal notes yet.</p>`:"");
  // An estimate's note waiting for the draft's first save.
  const est=draftForm&&S.estNote;show("#nEst",!!est);
  $("#nEst").innerHTML=est?`<p class="dk-help">From the customer's estimate${S.estNote.ref?" "+esc(S.estNote.ref):""}. It is added to the internal notes when the draft is saved.</p>
    <p class="dk-note-body">${esc(S.estNote.text)}</p>${canEdit()?`<div class="dk-note-acts"><button type="button" class="dk-link" data-ncopy="est">Copy to note to customer</button></div>`:""}`:"";
}
// Re-read the invoice's notes after a change. In the draft form only the
// notes are refreshed, so unsaved work in the form is never touched.
async function reloadNotes(){
  if(!NDOC)return;const d=await api.document(NDOC.id);
  if($("#issuedSec").hidden){renderNotes(d,true);}else{DOC=d;showView(d);}
}
// Adding a note: the request id stays the same for every retry of the same
// note (a double tap or a lost reply gives one note), and changes when the
// words or the category change.
const nCat=()=>(document.querySelector('input[name="ncat"]:checked')||{}).value||"general";
$("#nBody").addEventListener("input",()=>{NADD.req=newId();$("#nMsg").textContent="";});
document.querySelectorAll('input[name="ncat"]').forEach(r=>r.addEventListener("change",()=>{NADD.req=newId();}));
$("#nSave").addEventListener("click",async()=>{
  const btn=$("#nSave"),m=$("#nMsg"),body=$("#nBody").value.trim();
  if(btn.disabled||!NDOC||!NDOC.id)return;
  if(!body){m.textContent="Type the note first.";return;}
  busy(btn,true,"Saving…");m.textContent="";
  try{await api.addNote({p_invoice_id:NDOC.id,p_body:body,p_category:nCat(),p_request_id:NADD.req});
    NADD={req:newId()};$("#nBody").value="";
    const g=document.querySelector('input[name="ncat"][value="general"]');if(g)g.checked=true;
    await reloadNotes();$("#nMsg").textContent="Note saved.";}
  catch(err){noteFailed(err,m,"Tap Save note again: it is never saved twice.");}
  finally{busy(btn,false);}
});
function noteFailed(err,m,again){const k=kind(err);
  if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
  if(k==="expired")return expire();
  m.textContent=k==="offline"?"Not saved: no connection. "+again:"Not saved: "+String(err&&err.message||err);}
// Copy to note to customer (drafts only): the customer's words go into
// the note to the customer, to tidy before issuing. The internal note stays.
document.addEventListener("click",e=>{const b=e.target.closest("[data-ncopy]");if(!b||!canEdit()||$("#form").hidden)return;
  const n=b.dataset.ncopy==="est"?S.estNote:(NDOC&&NDOC.internal_notes||[]).find(x=>x.id===+b.dataset.ncopy);
  const text=n&&(n.text||n.body);if(!text)return;
  S.note=S.note.trim()?S.note.trim()+"\n"+text:text;$("#iNote").value=S.note;changed();
  $("#nMsg").textContent="Copied into the note to the customer. Save the draft to keep it.";});

// -- Correcting a note: a box opens under the note being corrected (in the
//    notes log, the payment history or the receipt view).
let CORR=null;   // {note|payment, invoiceId, req, where}
function corrBoxHTML(){return`<div class="dk-corr" id="ncBox">
  <label for="ncText">Correction (the original stays, marked corrected)</label>
  <textarea id="ncText" rows="3" maxlength="1000"></textarea>
  <div class="dk-row"><button type="button" id="ncSave" class="dk-btn primary">Save correction</button><button type="button" id="ncCancel" class="dk-btn ghost">Cancel</button></div>
  <p id="ncMsg" class="dk-msg" role="alert"></p></div>`;}
function openCorr(el,target,text,msg){
  const old=$("#ncBox");if(old)old.remove();
  const host=el.closest(".dk-note,.dk-pay-notes")||el;
  host.insertAdjacentHTML("afterend",corrBoxHTML());
  CORR={...target,req:newId()};
  $("#ncText").value=text||"";$("#ncMsg").textContent=msg||"";
  $("#ncText").addEventListener("input",()=>{if(CORR)CORR.req=newId();});
  $("#ncCancel").addEventListener("click",()=>{CORR=null;const b=$("#ncBox");if(b)b.remove();});
  $("#ncSave").addEventListener("click",saveCorr);
  $("#ncText").focus();
}
document.addEventListener("click",e=>{const b=e.target.closest("[data-ncorr]");if(!b)return;
  const invoiceId=!$("#rcptSec").hidden&&RDOC?(RDOC.invoice||{}).id:NDOC&&NDOC.id||DOC&&DOC.id;
  if(!invoiceId)return;
  openCorr(b,b.dataset.ncorr==="note"?{note:+b.dataset.nid,invoiceId}:{payment:+b.dataset.pid,invoiceId});});
async function saveCorr(){
  const btn=$("#ncSave"),m=$("#ncMsg"),body=$("#ncText").value.trim(),st=CORR;
  if(!st||btn.disabled)return;if(!body){m.textContent="Type the correction first.";return;}
  busy(btn,true,"Saving…");m.textContent="";
  try{await api.addNote({p_invoice_id:st.invoiceId,p_body:body,p_corrects_note_id:st.note||null,
      p_corrects_payment_id:st.payment||null,p_request_id:st.req});
    CORR=null;await reloadCorrView();}
  catch(err){
    // Someone else corrected it first: show their correction, and keep the
    // words typed here in a box against the new latest (design v1.5).
    if(/was just corrected by/.test(String(err&&err.message||""))){
      const msg=String(err.message);
      try{await reloadCorrView();}catch(e){}
      const latest=latestAfter(st);
      // The latest entry itself if it is on screen (the notes log), else the
      // line showing it under the corrected note (receipt view).
      const el=latest?document.querySelector(`[data-note="${latest}"]`)||document.querySelector(`[data-latest="${latest}"]`):null;
      if(el&&latest){openCorr(el,{note:latest,invoiceId:st.invoiceId},body,msg);return;}
      m.textContent=msg;return;}
    noteFailed(err,m,"Tap Save correction again: it is never saved twice.");}
  finally{if(btn.isConnected)busy(btn,false);}
}
// Re-read whichever screen the correction was made on.
async function reloadCorrView(){
  if(!$("#rcptSec").hidden&&RDOC){await showReceipt(RDOC.id);return;}
  await reloadNotes();}
// After a lost race: the latest entry of the chain the target is in.
function latestAfter(t){
  if(!$("#rcptSec").hidden&&RDOC){const c=RDOC.internal_note_chain||[];return c.length?c[c.length-1].id:null;}
  const list=NDOC&&NDOC.internal_notes||[];
  if(t.payment){const first=list.find(n=>n.corrects_payment_id===t.payment);if(!first)return null;const c=chainIn(list,first);return(c.length?c[c.length-1]:first).id;}
  const n=list.find(x=>x.id===t.note);if(!n)return null;const c=chainIn(list,n);return c.length?c[c.length-1].id:null;}

// -- Searching notes (#/notes): the database searches; the phone sends the
//    words and filters and shows a page of results at a time. The address
//    holds only the typed words and filters, never a note's text.
let NS={q:"",cat:"all",by:"",from:"",to:"",hide:false,rows:[],count:0,seq:0},AUTHORS=null;
const NKIND={invoice_note:"Internal note",receipt_customer_note:"Note to the customer · receipt",invoice_customer_note:"Note to the customer · invoice"};
function notesHash(o){const p=new URLSearchParams();
  if(o.q)p.set("q",o.q);if(o.cat&&o.cat!=="all")p.set("cat",o.cat);if(o.by)p.set("by",o.by);
  if(o.from)p.set("from",o.from);if(o.to)p.set("to",o.to);if(o.hide)p.set("hide","1");
  const s=p.toString();return"#/notes"+(s?"?"+s:"");}
const noteWords=q=>String(q||"").trim().split(/\s+/).filter(Boolean);
// The note's words with the typed words marked; a long note shows the part
// around the first match.
function markWords(text,words){
  let t=String(text||"");
  if(words.length&&t.length>300){const i=t.toLowerCase().indexOf(words[0].toLowerCase());
    if(i>120){t="…"+t.slice(i-100);}if(t.length>300)t=t.slice(0,300)+"…";}
  if(!words.length)return esc(t);
  const re=new RegExp("("+words.map(w=>w.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")).join("|")+")","ig");
  return t.split(re).map((part,i)=>i%2?`<mark>${esc(part)}</mark>`:esc(part)).join("");}
function noteRowHTML(r,words){
  const kindWord=r.kind==="payment_note"?(r.record_kind==="refund"?"Refund note":r.record_kind==="correction"?"Correction note":"Payment note"):NKIND[r.kind]||r.kind;
  const tags=[kindWord].concat(r.category?[NCAT[r.category]||r.category]:[]);
  const link=r.payment_id&&(r.kind==="payment_note"||r.kind==="receipt_customer_note")?"#/receipt/"+r.payment_id:"#/invoice/"+r.invoice_id;
  const bal=toP(r.balance||0),status=r.invoice_state==="draft"?"Draft":STATUS[r.status]||r.status||"";
  const rec=[r.invoice_no||"Draft",r.receipt_no,r.customer||"(no name)",status+(bal>0&&r.invoice_state==="issued"?`, ${money(bal)} left`:"")].filter(Boolean).map(esc).join(" · ");
  return`<div class="dk-nres"><a class="dk-nres-rec" href="${link}">${rec}</a>`+noteHTML({body:r.body,bodyHTML:markWords(r.body,words),by:r.by,at:r.at,tags,
    chain:r.chain||[],correction:!!(r.corrects_note_id||r.corrects_payment_id),
    corrects:correctsHTML({...r,corrects_kind:r.corrects_record_kind})})+`</div>`;}
async function showNotes(params){
  view("#notesV",null);
  NS={q:params.get("q")||"",cat:params.get("cat")||"all",by:params.get("by")||"",from:params.get("from")||"",to:params.get("to")||"",
      hide:params.get("hide")==="1",rows:[],count:0,seq:NS.seq+1};
  $("#nsq").value=NS.q;$("#nsFrom").value=NS.from;$("#nsTo").value=NS.to;$("#nsHide").checked=NS.hide;
  document.querySelectorAll("#nsCats [data-ncat]").forEach(b=>b.classList.toggle("on",b.dataset.ncat===NS.cat));
  $("#nsRows").innerHTML="";$("#nsInfo").textContent="";$("#nsMsg").textContent="";show("#nsMore",false);
  if(!AUTHORS){try{AUTHORS=await api.noteAuthors()||[];}catch(err){AUTHORS=null;}}
  $("#nsBy").innerHTML=`<option value="">Anyone</option>`+(AUTHORS||[]).map(a=>`<option value="${esc(a.id)}">${esc(a.name)}${a.active?"":" (left)"}</option>`).join("");
  $("#nsBy").value=NS.by;
  notesMore();
}
async function notesMore(){
  const my=NS.seq,btn=$("#nsMore"),words=noteWords(NS.q);
  if(words.some(w=>w.length<3)){$("#nsInfo").textContent="Type at least 3 letters or digits for each word.";$("#nsRows").innerHTML="";show("#nsMore",false);return;}
  busy(btn,true,"Loading…");$("#nsMsg").textContent="";
  try{
    // The words go as one text, the way search_notes takes them (it splits
    // them itself). A list here reached the database as '["word"]' and
    // matched nothing.
    const res=await api.searchNotes({p_words:words.length?words.join(" "):null,p_category:NS.cat==="all"?null:NS.cat,p_author:NS.by||null,
      p_from:NS.from||null,p_to:NS.to||null,p_hide_corrected:NS.hide,p_offset:NS.rows.length,p_limit:PAGE});
    if(my!==NS.seq)return;
    NS.rows=NS.rows.concat(res.rows||[]);NS.count=res.count||0;
    $("#nsRows").innerHTML=NS.rows.length?NS.rows.map(r=>noteRowHTML(r,words)).join(""):`<p class="dk-help">No notes match.</p>`;
    $("#nsInfo").textContent=NS.count?`${NS.count} ${NS.count===1?"note":"notes"} · newest first`:"";
    show("#nsMore",NS.rows.length<NS.count);
  }catch(err){if(my===NS.seq)readFailed(err,"#nsMsg");}
  finally{busy(btn,false);}
}
$("#nsMore").addEventListener("click",notesMore);
// Any change of words or filter: a new search, and the address updated.
function notesSearch(patch){
  NS={...NS,...patch,rows:[],count:0,seq:NS.seq+1};
  const h=notesHash(NS);history.replaceState(null,"",h);HERE=h;
  document.querySelectorAll("#nsCats [data-ncat]").forEach(b=>b.classList.toggle("on",b.dataset.ncat===NS.cat));
  $("#nsRows").innerHTML="";notesMore();}
let nsTyping=null;
$("#nsq").addEventListener("input",()=>{clearTimeout(nsTyping);nsTyping=setTimeout(()=>notesSearch({q:$("#nsq").value.trim()}),350);});
$("#nsForm").addEventListener("submit",e=>{e.preventDefault();clearTimeout(nsTyping);notesSearch({q:$("#nsq").value.trim()});});
$("#nsCats").addEventListener("click",e=>{const b=e.target.closest("[data-ncat]");if(b)notesSearch({cat:b.dataset.ncat});});
$("#nsBy").addEventListener("change",()=>notesSearch({by:$("#nsBy").value}));
$("#nsFrom").addEventListener("change",()=>notesSearch({from:$("#nsFrom").value}));
$("#nsTo").addEventListener("change",()=>notesSearch({to:$("#nsTo").value}));
$("#nsHide").addEventListener("change",()=>notesSearch({hide:$("#nsHide").checked}));

// -- Cancelling an issued invoice (owner only; design "Cancelling an issued
//    invoice"). The database refuses it while money is held, and refuses a
//    second cancel; the screen says why before trying.
function showCancel(doc){
  const own=!!ME&&ME.role==="owner"&&doc.state==="issued";
  show("#cxBox",own);if(!own)return;
  const held=toP(doc.paid),credits=(doc.credit_notes||[]).filter(c=>!c.cancelled).length;
  ["#cxErr","#cxMsg"].forEach(e=>{$(e).textContent="";});
  show("#cxFields",false);show("#cxConfirm",false);$("#cxWhy").value="";
  // Phase 2.3: while a credit note on it is active, the button is replaced.
  $("#cxHeld").textContent=credits
    ?`Cancel its credit notes first: this invoice has ${credits} active credit ${credits===1?"note":"notes"}. Once they are cancelled, the invoice can be cancelled.`
    :held!==0
    ?`This invoice holds ${smoney(held)} in payments. Refund or correct them first, then cancel.`
    :"Cancelling keeps the invoice, its number and its history, marked Cancelled with your reason. It cannot be undone.";
  show("#cxOpen",held===0&&!credits);
}
$("#cxOpen").addEventListener("click",()=>{show("#cxOpen",false);show("#cxFields",true);$("#cxWhy").focus();});
$("#cxBack").addEventListener("click",()=>{if(DOC)showCancel(DOC);});
$("#cxNext").addEventListener("click",()=>{const why=$("#cxWhy").value.trim();
  if(!why){$("#cxErr").textContent="Give a reason: it is kept with the invoice.";return;}
  $("#cxErr").textContent="";
  $("#cxSummary").textContent=`Cancel ${DOC.invoice_no} for ${DOC.billed_to_name||"(no name)"}, ${money(toP(DOC.total))}? It stays on record as Cancelled, with this reason: "${why}". This cannot be undone.`;
  show("#cxFields",false);show("#cxConfirm",true);});
$("#cxKeep").addEventListener("click",()=>{if(DOC)showCancel(DOC);});
$("#cxYes").addEventListener("click",async()=>{
  const btn=$("#cxYes");if(btn.disabled||!DOC)return;const id=DOC.id,why=$("#cxWhy").value.trim();
  busy(btn,true,"Cancelling…");$("#cxMsg").textContent="";
  try{await api.cancel(id,why);const d=await api.document(id);showView(d);$("#iMsg").textContent="Invoice cancelled.";}
  catch(err){const k=kind(err);
    if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
    if(k==="expired")return expire();
    // Whatever happened, show the invoice as the database has it now: a
    // cancel whose answer was lost shows as cancelled, not as an error.
    try{const d=await api.document(id);if(d.state==="cancelled"){showView(d);$("#iMsg").textContent="Invoice cancelled.";return;}}catch(e){}
    $("#cxMsg").textContent=k==="offline"?"Not cancelled: no connection. Try again when you have signal.":"Not cancelled: "+String(err&&err.message||err);}
  finally{busy(btn,false);}
});

// ---- 8d. Credit notes (Phase 2.3) -------------------------------------------
// "TCP Back Office Phase 2.3: Credit Notes Implementation Specification
// (v1.4)", approved by ChatGPT and Daniel on 26 Nov 2026. A credit note
// lowers what an issued invoice is worth; it moves no money (money goes
// back with a refund). The database does all the work: it works out every
// amount again, checks every cap (quantity and value per line, the invoice
// total), numbers the credit note (TCP-CN-0001) and keeps it forever; a
// wrong one is cancelled by the owner, never edited. This section only
// asks, previews and shows what the database says.
//   Who: the owner and finance issue; only the owner adjusts a price,
//   backdates, or cancels. Credit notes can be switched off by the owner:
//   then no new one can be issued, but a wrong one can still be cancelled.
const WHY_WORD={not_supplied:"Not supplied",returned:"Returned",delivery_not_made:"Delivery not made",price_adjustment:"Price adjustment"};
const canCredit=()=>!!ME&&(ME.role==="owner"||ME.role==="finance");
const isOwner=()=>!!ME&&ME.role==="owner";
let CN=null,CDOC=null,CC=null,SWITCH=null,CVNOTE="";
// -- The unfinished credit note kept on this phone (as payments, "Option B").
// Only its identifiers are kept: the invoice and the request id. Never the
// reason or the notes (they are typed again after a reload). Removed on
// success, Cancel, sign-out, removed access, or after 24 hours.
const cnKey=()=>"tcp-desk-cn-"+(ME?ME.id:"");
function pendingCn(){if(!ME)return null;let o=null;
  try{o=JSON.parse(localStorage.getItem(cnKey())||"null")}catch(e){}
  if(o&&(o.user!==ME.id||!(Date.now()-o.at<OP_TTL))){dropCn();return null;}
  return o;}
function keepCn(o){if(!ME)return;try{localStorage.setItem(cnKey(),JSON.stringify({user:ME.id,at:Date.now(),invoiceId:o.invoiceId,req:o.req}))}catch(e){}}
function dropCn(){try{localStorage.removeItem(cnKey())}catch(e){}}
// Was this credit note issued? Asked of the database by its request id.
async function cnIssued(req){return await api.creditByRequest(req);}

// The switch, as staff see it (read-only), from the database.
async function switchState(){const o=await api.creditOptions({p_invoice_id:null});SWITCH=o.switch;return SWITCH;}

// -- The invoice's credit notes (under its payments)
function showCredits(doc){
  const list=doc.credit_notes||[],issued=doc.state==="issued",value=toP(doc.total)-toP(doc.credited||0);
  show("#cnBox",issued||list.length>0);
  $("#cnList").innerHTML=list.length?list.map(c=>`<a class="dk-cn${c.cancelled?" off":""}" href="#/credit/${c.id}">
      <span><span>${esc(c.credit_note_no)}</span><small>Issued ${shortDate(c.issued_on)}${c.effective_on!==c.issued_on?" · effective "+shortDate(c.effective_on):""}${c.cancelled?" · Cancelled "+shortDate(c.cancelled_on):""}</small></span>
      <b>−${money(toP(c.amount))}</b></a>`).join(""):`<p class="dk-help">No credit notes.</p>`;
  show("#cnBtn",false);show("#cnOff",false);
  $("#cnBtn").href=`#/invoice/${doc.id}/credit`;
  const op=pendingCn();show("#cnOp",false);
  if(op&&op.invoiceId===doc.id)return checkCn(op);
  if(!(issued&&value>0&&canCredit()&&!op))return;
  // "Issue credit note" only while credit notes are switched on.
  switchState().then(sw=>{if(DOC!==doc)return;show("#cnBtn",!!sw.on);show("#cnOff",!sw.on);})
    .catch(err=>readFailed(err,"#iMsg"));
}
// A credit note left unconfirmed on this phone: was it issued?
async function checkCn(op){
  show("#cnOp",true);show("#cnOpCheck",false);$("#cnOpMsg").textContent="Checking whether the credit note was issued…";
  let r;
  try{r=await cnIssued(op.req);}
  catch(err){const k=kind(err);
    if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
    if(k==="expired")return expire();
    $("#cnOpMsg").textContent=`Could not check whether the credit note was issued${k==="offline"?": no connection":""}. No new credit note can be issued on this invoice until it is checked.`;
    show("#cnOpCheck",true);return;}
  if(r){dropCn();CVNOTE="This credit note was already issued. Here it is.";return go("#/credit/"+r.id);}
  // Not issued: open the form again with the same request id.
  show("#cnOp",false);
  return go(`#/invoice/${op.invoiceId}/credit`);
}
$("#cnOpCheck").addEventListener("click",()=>{const op=pendingCn();if(op)checkCn(op);else if(DOC)showView(DOC);});

// -- The form (#/invoice/<id>/credit)
async function openCredit(id){
  showOnly("#cnForm");$("#cnMsg").textContent="";$("#cnErr").textContent="";$("#cnLines").innerHTML="";$("#cnFor").textContent="";
  show("#cnFields",false);show("#cnConfirm",false);
  if(!canCredit())return go("#/invoice/"+id);
  let o;try{o=await api.creditOptions({p_invoice_id:id});}catch(err){return readFailed(err,"#cnMsg");}
  if(!o.switch.on){$("#cnMsg").textContent="Credit notes are switched off. The owner can switch them on from Home.";return;}
  if(o.state!=="issued"){$("#cnMsg").textContent="Only an issued invoice can be credited.";return;}
  const kept=pendingCn();
  CN={opt:o,req:kept&&kept.invoiceId===id?kept.req:newId(),sent:false,lines:{}};
  (o.lines||[]).forEach(l=>{CN.lines[l.invoice_line_id]={qty:"",why:"",tick:false};});
  $("#cnFor").textContent=`${o.invoice_no} · value ${money(toP(o.value))} · ${toP(o.balance)<0?"TCP owes the customer "+money(-toP(o.balance)):"owed "+money(toP(o.balance))}`;
  ["#cnWhy","#cnCust","#cnInt","#cnAdj","#cnEff","#cnEffWhy"].forEach(s=>{$(s).value="";});
  $("#cnEff").max=o.today;$("#cnEff").min=o.issued_on;
  show("#cnOwner",isOwner());$("#cnOwner").open=false;
  $("#cnLines").innerHTML=(o.lines||[]).map(cnLineHTML).join("");
  show("#cnFields",true);
  $("#cnMsg").textContent=kept&&kept.invoiceId===id?"This credit note was not issued. Check it, then tap Continue and Issue. The reason and notes are not kept on this phone: type them again.":"";
  cnRefresh();window.scrollTo(0,0);
}
function cnLineHTML(l){const id=l.invoice_line_id,left=toP(l.value_left);
  const head=`<div class="dk-cnl-top"><span>${esc(l.description)}<small>${l.kind==="product"
      ?`${fmtQ(l.quantity_left)} of ${fmtQ(l.quantity)} ${esc(UNIT_WORD(l.unit,l.quantity)||l.unit)} left · ${money(left)} left to credit`
      :`Delivery charge · ${money(left)} left to credit`}</small></span><b id="cnAmt${id}">${money(0)}</b></div>`;
  if(left<=0)return`<div class="dk-cnl">${head}<p class="dk-help">Nothing left to credit on this line.</p></div>`;
  if(l.kind==="delivery")return`<div class="dk-cnl" data-cnl="${id}">${head}
      <label class="dk-check"><input type="checkbox" data-cntick="${id}"> Delivery not made: credit the whole charge left</label></div>`;
  return`<div class="dk-cnl" data-cnl="${id}">${head}<div class="dk-row">
      <label for="cnQ${id}" class="sr">Quantity to credit</label>
      <input id="cnQ${id}" type="text" inputmode="decimal" autocomplete="off" placeholder="Qty" data-cnq="${id}">
      <fieldset class="dk-methods"><legend class="sr">Why</legend>
        <label><input type="radio" name="cnw${id}" value="not_supplied" data-cnw="${id}"> Not supplied</label>
        <label><input type="radio" name="cnw${id}" value="returned" data-cnw="${id}"> Returned</label></fieldset></div>
      <p class="dk-lerr" id="cnE${id}" role="alert"></p></div>`;}
// What one line would credit, worked out as the database does (the
// database works it out again when the credit note is issued).
function cnLineAmount(l,v){
  if(l.kind==="delivery")return v.tick?toP(l.value_left):0;
  const q=typedNum(v.qty);if(!String(v.qty).trim()||isNaN(q)||q<=0)return 0;
  if(Math.round(q*1000)===Math.round(+l.quantity_left*1000))return toP(l.value_left);
  return Math.min(Math.round(q*toP(l.net_value)/+l.quantity),toP(l.value_left));}
function cnPlan(){const o=CN.opt,errs=[],lines=[];let total=0;
  (o.lines||[]).forEach(l=>{const v=CN.lines[l.invoice_line_id];if(!v)return;let e="";
    if(l.kind==="product"&&String(v.qty).trim()){const q=typedNum(v.qty);
      if(isNaN(q))e="Enter a number.";else if(q<=0)e="The quantity must be more than 0.";
      else if(q>+l.quantity_left)e=`Only ${fmtQ(l.quantity_left)} ${UNIT_WORD(l.unit,l.quantity_left)||l.unit} left to credit.`;
      else if(!v.why)e="Say whether they were not supplied or returned.";
      if(!e)lines.push({invoice_line_id:l.invoice_line_id,kind:"quantity",why:v.why,quantity:Math.round(q*1000)/1000});}
    if(l.kind==="delivery"&&v.tick)lines.push({invoice_line_id:l.invoice_line_id,kind:"delivery",why:"delivery_not_made"});
    const a=e?0:cnLineAmount(l,v);total+=a;const el=$("#cnAmt"+l.invoice_line_id);if(el)el.textContent=money(a);
    const er=$("#cnE"+l.invoice_line_id);if(er)er.textContent=e;
    const row=document.querySelector(`[data-cnl="${l.invoice_line_id}"]`);if(row)row.classList.toggle("bad",!!e);
    if(e)errs.push(e);});
  let adj=0;const at=$("#cnAdj").value.trim();
  if(isOwner()&&at){const v=typedNum(at);if(isNaN(v)||v<=0)errs.push("The price adjustment must be an amount above GH₵0.00.");
    else{adj=toP(v);lines.push({kind:"adjustment",why:"price_adjustment",amount:adj/100});total+=adj;}}
  return{lines,total,errs};}
function cnRefresh(){if(!CN)return;const{total}=cnPlan(),o=CN.opt;
  $("#cnTotal").textContent=total?`Credit ${money(total)}. Value after: ${money(toP(o.value)-total)}.`:"";}
document.addEventListener("input",e=>{if(!CN)return;const t=e.target;
  if(t.dataset.cnq){CN.lines[t.dataset.cnq].qty=t.value;$("#cnErr").textContent="";cnRefresh();}
  else if(t.id==="cnAdj"){$("#cnErr").textContent="";cnRefresh();}});
document.addEventListener("change",e=>{if(!CN)return;const t=e.target;
  if(t.dataset.cnw){CN.lines[t.dataset.cnw].why=t.value;cnRefresh();}
  else if(t.dataset.cntick){CN.lines[t.dataset.cntick].tick=t.checked;cnRefresh();}});
function cnProblems(){const{lines,total,errs}=cnPlan(),o=CN.opt,out=[...errs];
  if(!lines.length&&!errs.length)out.push("Choose what to credit: a quantity on a line, a delivery, or (owner) a price adjustment.");
  if(total>toP(o.invoice_left))out.push(`That is more than the ${money(toP(o.invoice_left))} left on the invoice.`);
  const why=$("#cnWhy").value.trim(),eff=$("#cnEff").value,effWhy=$("#cnEffWhy").value.trim();
  if(!why)out.push("Give the reason: it is printed on the credit note.");
  if(isOwner()&&eff&&eff!==o.today){
    if(eff>o.today||eff<o.issued_on)out.push("A credit note cannot take effect before the invoice was issued, or in the future.");
    else if(!effWhy)out.push("Say why it is backdated.");}
  return{out,lines,total,why,eff:isOwner()&&eff&&eff!==o.today?eff:null,effWhy};}
$("#cnNext").addEventListener("click",()=>{if(!CN)return;const p=cnProblems();$("#cnErr").textContent=p.out.join(" ");if(p.out.length)return;
  const o=CN.opt,owed=toP(o.balance)-p.total;
  // Confirm before issuing: a credit note number is permanent.
  $("#cnSummary").textContent=`Credit ${money(p.total)} against ${o.invoice_no}. Value after: ${money(toP(o.value)-p.total)}. `
    +(owed<0?`TCP will owe the customer ${money(-owed)}.`:`Owed after: ${money(owed)}.`)
    +(p.eff?` Takes effect from ${shortDate(p.eff)} (backdated: ${p.effWhy}).`:"");
  const cust=$("#cnCust").value.trim(),int=$("#cnInt").value.trim();
  $("#cnPrinted").textContent=`Printed on the credit note: "${p.why}"`+(cust?` and the note "${cust}"`:"")+"."+(int?" The internal note is never printed.":"");
  show("#cnFields",false);show("#cnConfirm",true);$("#cnMsg").textContent="";});
$("#cnChange").addEventListener("click",()=>{show("#cnConfirm",false);show("#cnFields",true);});
$("#cnCancel").addEventListener("click",async()=>{if(!CN)return;const st=CN;
  // Sent with no answer yet: check first, so nothing is abandoned unseen.
  if(st.sent){let r;try{r=await cnIssued(st.req);}catch(err){const k=kind(err);
      if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");if(k==="expired")return expire();
      $("#cnMsg").textContent="Can't cancel yet: it could not be checked whether this credit note was issued. Try again when you have signal.";return;}
    if(r){dropCn();CN=null;CVNOTE="This credit note was already issued. Here it is.";return go("#/credit/"+r.id);}}
  const id=st.opt.invoice_id;dropCn();CN=null;go("#/invoice/"+id);});
$("#cnYes").addEventListener("click",async()=>{
  const btn=$("#cnYes");if(btn.disabled||!CN)return;const st=CN,p=cnProblems();if(p.out.length)return;
  busy(btn,true,"Issuing…");$("#cnMsg").textContent="";
  try{
    // A retry of one whose outcome is unknown asks the database first.
    if(st.sent){const r=await cnIssued(st.req);if(r){dropCn();CN=null;CVNOTE="This credit note was already issued. Here it is.";return go("#/credit/"+r.id);}}
    keepCn({invoiceId:st.opt.invoice_id,req:st.req});st.sent=true;
    const r=await api.issueCredit({p_invoice_id:st.opt.invoice_id,p_lines:p.lines,p_reason:p.why,
      p_customer_note:$("#cnCust").value.trim()||null,p_internal_note:$("#cnInt").value.trim()||null,
      p_effective_on:p.eff,p_backdate_reason:p.eff?p.effWhy:null,p_request_id:st.req});
    dropCn();CN=null;CVNOTE="Credit note issued.";await go("#/credit/"+r.id);
  }catch(err){const k=kind(err);
    if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
    if(k==="expired")return expire();
    if(definite(err)){dropCn();st.sent=false;$("#cnMsg").textContent="Not issued: "+String(err.message||err);return;}
    $("#cnMsg").textContent=k==="offline"
      ?"No connection: it may or may not have been issued. Tap Issue credit note again when you have signal: it is checked first, and never issued twice."
      :"Could not confirm it was issued. Tap Issue credit note again: it is checked first, and never issued twice.";}
  finally{busy(btn,false);}
});

// -- One credit note (#/credit/<id>): the staff view
async function showCredit(id){
  showOnly("#cnSec");["#cv","#cvLines","#cvNotes"].forEach(s=>{$(s).innerHTML="";});$("#cvMsg").textContent="";show("#cvCopyBox",false);
  const note=CVNOTE;CVNOTE="";
  let d;try{d=await api.creditDoc({p_credit_note_id:id});}catch(err){return readFailed(err,"#cvMsg");}
  CDOC=d;$("#cvMsg").textContent=note;
  $("#cvTitle").textContent=`Credit note ${d.credit_note_no}`;
  const row=(k,v)=>v?`<div><span>${k}</span><b>${esc(v)}</b></div>`:"";
  const owedAfter=toP(d.owed_after);
  $("#cv").innerHTML=`${d.cancelled?`<span class="dk-stamp">CANCELLED</span>`:""}<div class="dk-sum">
    ${row("Invoice",d.invoice_no)}
    ${row("Customer",[d.billed_to_name,d.billed_to_phone].filter(Boolean).join(" · "))}
    ${row("Issued",dateText(d.issued_on))}
    ${row("Takes effect from",d.effective_on!==d.issued_on?dateText(d.effective_on):"")}
    ${row("Why backdated (staff only)",d.backdate_reason||"")}
    ${row("Recorded",noteTime(d.recorded_at))}
    ${row("Issued by",d.recorded_by||"")}
    ${row("Invoice value after",money(toP(d.value_after)))}
    ${row(owedAfter<0?"In credit after (TCP owed)":"Owed after",money(Math.abs(owedAfter)))}
    ${row("Cancelled",d.cancelled?dateText(d.cancelled_on)+(d.cancelled_by?" by "+d.cancelled_by:""):"")}
    ${row("Cancelled because",d.cancelled?d.cancel_reason||"":"")}
    <div class="dk-total"><span>Amount credited</span><b>${money(toP(d.amount))}</b></div></div>`;
  $("#cvLines").innerHTML=(d.lines||[]).map((l,i)=>`<div class="dk-vline"><span>${i+1}. ${esc(l.description)}<small>${l.quantity!=null?`${fmtQ(l.quantity)} ${esc(UNIT_WORD(l.unit,l.quantity)||l.unit||"")} · `:""}${esc(WHY_WORD[l.why]||l.why)}</small></span><b>${money(toP(l.amount))}</b></div>`).join("");
  $("#cvNotes").innerHTML=`<div class="dk-sum">${row("Reason (printed)",d.reason)}${row("Note to the customer (printed)",d.customer_note||"")}${row("Internal note (staff only)",d.internal_note||"")}</div>`;
  // A cancelled credit note keeps its PDF, stamped, for TCP's records, but
  // is not shared.
  show("#cvShare",!d.cancelled);
  $("#cvInv").href="#/invoice/"+d.invoice_id;
  showCreditCancel(d);
}
// What the customer's WhatsApp message says: no amounts, no notes.
function waCreditText(p){const first=String(p.billed_to_name||"").trim().split(/\s+/)[0]||"";
  return`Hello${first?" "+first:""}, here is credit note ${p.credit_note_no} for invoice ${p.invoice_no} from ${B.name}.`;}
const creditFileName=p=>`TCP Credit Note ${p.credit_note_no}${p.cancelled_on?" CANCELLED":""}.pdf`;
// Read again before every PDF: the print data (credit_note_print) is the
// only thing the PDF is drawn from, and it holds no private field.
async function creditFile(){const p=await api.creditPrint({p_credit_note_id:CDOC.id});const pdf=await makeCreditPdf(p);
  return{p,file:new File([pdf.output("blob")],creditFileName(p),{type:"application/pdf"})};}
$("#cvCopyBtn").addEventListener("click",async()=>{const ta=$("#cvCopyText");ta.select();
  let ok=await copyText(ta.value);if(!ok){try{ok=document.execCommand("copy");}catch(e){}}
  $("#cvMsg").textContent=ok?"Message copied. Paste it in WhatsApp.":"Select the message above and copy it.";});
$("#cvShare").addEventListener("click",async()=>{
  const btn=$("#cvShare"),m=$("#cvMsg");show("#cvCopyBox",false);m.textContent="";if(!CDOC||CDOC.cancelled)return;
  const copied=copyText(waCreditText(CDOC));
  busy(btn,true,"Preparing PDF…");
  try{const{p,file}=await creditFile(),text=waCreditText(p);
    let note;
    if(await copied)note="Message copied. In WhatsApp, paste it as the caption before sending.";
    else{$("#cvCopyText").value=text;show("#cvCopyBox",true);note="Copy the message below, then paste it in WhatsApp as the caption.";}
    if(navigator.canShare&&navigator.canShare({files:[file]})){m.textContent=note;
      // The PDF only, as for invoices and receipts: the message is pasted once.
      try{await navigator.share({files:[file],title:file.name});}catch(e){if(e.name!=="AbortError")throw e;}
    }else{download(file);const to=waNumber(p.billed_to_phone);
      if(to)window.open("https://wa.me/"+to+"?text="+encodeURIComponent(text),"_blank","noopener");
      m.textContent="This browser cannot share files: the PDF was downloaded. Attach it in the WhatsApp chat. "+note;}
  }catch(e){kind(e)==="refused"?(m.textContent="Could not prepare the credit note: "+(e.message||e)):failed(e,"#cvMsg");}
  finally{busy(btn,false);}});
$("#cvPdf").addEventListener("click",async()=>{const btn=$("#cvPdf"),m=$("#cvMsg");busy(btn,true,"Preparing PDF…");
  try{download((await creditFile()).file);m.textContent="Credit note PDF downloaded.";}
  catch(e){kind(e)==="refused"?(m.textContent="Could not prepare the credit note: "+(e.message||e)):failed(e,"#cvMsg");}
  finally{busy(btn,false);}});

// -- Cancelling a credit note (owner only; allowed even while switched off).
//    The consequence is shown in GH₵ before confirming.
function showCreditCancel(d){
  const own=isOwner()&&!d.cancelled;show("#ccBox",own);if(!own)return;
  CC={req:newId(),sent:false};["#ccErr","#ccMsg"].forEach(e=>{$(e).textContent="";});$("#ccWhy").value="";
  show("#ccOpen",true);show("#ccFields",false);show("#ccConfirm",false);}
$("#ccOpen").addEventListener("click",()=>{show("#ccOpen",false);show("#ccFields",true);$("#ccWhy").focus();});
$("#ccBack").addEventListener("click",()=>{if(CDOC)showCreditCancel(CDOC);});
$("#ccKeep").addEventListener("click",()=>{if(CDOC)showCreditCancel(CDOC);});
$("#ccNext").addEventListener("click",()=>{const why=$("#ccWhy").value.trim(),d=CDOC;
  if(!why){$("#ccErr").textContent="Give a reason: it is kept with the credit note.";return;}
  $("#ccErr").textContent="";
  const after=toP(d.invoice_balance)+toP(d.amount);
  $("#ccSummary").textContent=`Cancel ${d.credit_note_no} (${money(toP(d.amount))}) on ${d.invoice_no}? The invoice's value goes back up by ${money(toP(d.amount))}: `
    +(after<0?`TCP will still owe the customer ${money(-after)}.`:`the customer will owe ${money(after)}.`)
    +` Reason: "${why}". This cannot be undone.`;
  show("#ccFields",false);show("#ccConfirm",true);});
$("#ccYes").addEventListener("click",async()=>{
  const btn=$("#ccYes");if(btn.disabled||!CDOC||!CC)return;const id=CDOC.id,why=$("#ccWhy").value.trim(),st=CC;
  busy(btn,true,"Cancelling…");$("#ccMsg").textContent="";
  try{st.sent=true;await api.cancelCredit({p_credit_note_id:id,p_reason:why,p_request_id:st.req});
    CVNOTE="Credit note cancelled.";await showCredit(id);}
  catch(err){const k=kind(err);
    if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
    if(k==="expired")return expire();
    // Whatever happened, show the credit note as the database has it now:
    // a cancel whose answer was lost shows as cancelled, not as an error.
    try{const d=await api.creditDoc({p_credit_note_id:id});if(d.cancelled){CVNOTE="Credit note cancelled.";return showCredit(id);}}catch(e){}
    $("#ccMsg").textContent=k==="offline"?"Not cancelled: no connection. Try again when you have signal.":"Not cancelled: "+String(err&&err.message||err);}
  finally{busy(btn,false);}
});

// -- The owner's switch (Home, "Settings")
let SW=null;
async function showSwitch(){
  show("#cnSwitch",isOwner());if(!isOwner())return;
  SW={req:newId()};show("#swFields",false);["#swErr","#swMsg"].forEach(e=>{$(e).textContent="";});$("#swWhy").value="";
  let s;try{s=await switchState();}catch(err){return readFailed(err,"#swMsg");}
  $("#swState").textContent=(s.on?"Credit notes are switched on.":"Credit notes are switched off: no new credit note can be issued.")
    +(s.changed_at?` Last changed ${noteTime(s.changed_at)}${s.changed_by?" by "+s.changed_by:""}: ${s.reason}`:"");
  $("#swOpen").textContent=s.on?"Switch off credit notes":"Switch on credit notes";
  $("#swYes").textContent=s.on?"Switch off":"Switch on";
  show("#swOpen",true);}
$("#swOpen").addEventListener("click",()=>{show("#swOpen",false);show("#swFields",true);$("#swWhy").focus();});
$("#swNo").addEventListener("click",()=>showSwitch());
$("#swYes").addEventListener("click",async()=>{
  const btn=$("#swYes");if(btn.disabled||!SW||!SWITCH)return;const why=$("#swWhy").value.trim();
  if(!why){$("#swErr").textContent="Give a reason: it is kept in the switch's history.";return;}
  busy(btn,true,"Saving…");$("#swErr").textContent="";
  // The same request id for every retry: the switch never flips twice.
  try{const r=await api.setCreditSwitch({p_on:!SWITCH.on,p_reason:why,p_request_id:SW.req});
    await showSwitch();$("#swMsg").textContent=r.message+".";}
  catch(err){const k=kind(err);
    if(k==="revoked")return revoke("Your access has ended. Ask the owner if this is a mistake.");
    if(k==="expired")return expire();
    $("#swMsg").textContent=k==="offline"?"Not changed: no connection. Try again when you have signal (it is never changed twice).":"Not changed: "+String(err&&err.message||err);}
  finally{busy(btn,false);}
});

// -- The credit note PDF (A4), in the invoice's look. Drawn ONLY from
//    credit_note_print, which holds no internal note, backdate reason or
//    staff name. The figures are the snapshots taken when it was issued, so
//    a reprint always matches the original.
async function makeCreditPdf(p){
  const{jsPDF,logo}=await pdfKit(),F=window.TCP_PDF_FONTS;
  const pdf=new jsPDF({unit:"mm",format:"a4",compress:true});
  [["r","normal"],["s","semibold"],["x","bold"]].forEach(([k,st])=>{pdf.addFileToVFS(`M-${k}.ttf`,F[k]);pdf.addFont(`M-${k}.ttf`,"Montserrat",st);});
  pdf.setProperties({title:`${B.name} Credit Note ${p.credit_note_no}`,author:B.name,creator:"TCP Back Office"});
  const INK="#131514",MUTE="#5a5a5a",LINE="#dcdcdc",OCHRE="#ff9802",BAND="#f4f4f4",RED="#b3261e";
  const L=14,R=196,W=R-L,TOP=16,BOTTOM=282,pt=n=>n*0.3528;
  const font=(st,size,col)=>{pdf.setFont("Montserrat",st);pdf.setFontSize(size);pdf.setTextColor(col||INK);};
  const txt=(str,x,y,o={})=>{const sp=o.sp||0,w=pdf.getTextWidth(str)+sp*Math.max(0,str.length-1);
    pdf.text(str,o.right?x-w:x,y,{baseline:"top",charSpace:sp});return w;};
  const wrap=(str,w)=>pdf.splitTextToSize(str,w);
  const short=iso=>{const[y,m,d]=String(iso).slice(0,10).split("-").map(Number);return new Date(y,m-1,d).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"});};
  // -- Header
  pdf.addImage(logo,"PNG",L,TOP,13*5.92329,13);
  font("bold",17);txt("CREDIT NOTE",R,TOP,{right:1,sp:pt(17)*.08});
  const dl=[["Credit note no.",p.credit_note_no],["Issued",dateText(p.issued_on)]]
    .concat(p.effective_on?[["Effective from",dateText(p.effective_on)]]:[]).concat([["Invoice no.",p.invoice_no]]);
  font("bold",9);const vw=Math.max(...dl.map(r=>pdf.getTextWidth(r[1])));
  let y=TOP+8.5;
  dl.forEach(([k,v])=>{font("bold",9);txt(v,R,y,{right:1});font("normal",9,MUTE);txt(k,R-vw-4,y,{right:1});y+=4.3;});
  y=Math.max(TOP+13,y)+4.5;
  pdf.setFillColor(INK);pdf.rect(L,y,W,.8,"F");pdf.setFillColor(OCHRE);pdf.rect(L,y,28,.8,"F");y+=.8+4.5;
  // -- Grey band: the customer (as on the invoice), the invoice, from
  const cols=[["Customer",[p.billed_to_name,p.billed_to_phone].filter(Boolean).join("\n")],
    ["Against invoice",`${p.invoice_no}\nIssued ${dateText(p.invoice_issued_on)}`],["From",`${B.name}\n${B.phone} (call or WhatsApp)\n${B.website}\n${B.town}`]];
  const inner=W-.8-7,gap=6,unitW=(inner-2*gap)/3.7,cw=[1.5,1,1.2].map(r=>r*unitW);
  font("semibold",8.5);const lh=pt(8.5)*1.45;
  const lines=cols.map((c,i)=>c[1].split("\n").flatMap(l=>wrap(l,cw[i])));
  const bandH=3+pt(7)*1.2+.6+Math.max(...lines.map(l=>l.length))*lh+3;
  pdf.setFillColor(BAND);pdf.rect(L,y,W,bandH,"F");pdf.setFillColor(OCHRE);pdf.rect(L,y,.8,bandH,"F");
  let x=L+.8+3.5;
  cols.forEach((c,i)=>{font("bold",7,MUTE);txt(c[0].toUpperCase(),x,y+3,{sp:pt(7)*.1});
    font("semibold",8.5);lines[i].forEach((l,j)=>txt(l,x,y+3+pt(7)*1.2+.6+j*lh));x+=cw[i]+gap;});
  y+=bandH+4.5;
  // -- Lines: description, quantity, reason in words, amount
  const C={n:L+2.5,d:L+8+2.5,q:R-30-34-2.5,w:R-30-30,a:R-2.5},dW=C.q-22-C.d;
  const head=()=>{pdf.setFillColor(INK);pdf.rect(L,y,W,7,"F");font("bold",7.5,"#ffffff");const sp=pt(7.5)*.08,ty=y+2.2;
    txt("#",C.n,ty,{sp});txt("DESCRIPTION",C.d,ty,{sp});txt("QTY",C.q,ty,{right:1,sp});txt("REASON",C.w,ty,{sp});txt("AMOUNT",C.a,ty,{right:1,sp});y+=7;};
  head();const rlh=pt(9.5)*1.45;
  (p.lines||[]).forEach((l,i)=>{font("semibold",9.5);const nameLines=wrap(l.description,dW),h=1.7*2+nameLines.length*rlh;
    if(y+h>BOTTOM){pdf.addPage();y=TOP;head();}
    const ty=y+1.7;txt(String(i+1),C.n,ty);nameLines.forEach((n,j)=>txt(n,C.d,ty+j*rlh));
    font("normal",9.5);if(l.quantity!=null)txt(`${fmtQ(l.quantity)} ${UNIT_WORD(l.unit,l.quantity)||""}`.trim(),C.q,ty,{right:1});
    txt(l.why,C.w,ty);txt(money(toP(l.amount)),C.a,ty,{right:1});
    y+=h;pdf.setDrawColor(LINE);pdf.setLineWidth(.25);pdf.line(L,y,R,y);});
  // -- Totals right: the amount, and what it did, as at the moment of issue
  const TW=98,LW=W-TW-8,tlh=pt(7.5)*1.4,owed=toP(p.owed_after);
  const effect=`When this credit note was issued on ${short(p.issued_on)}: invoice value ${money(toP(p.value_before))} to ${money(toP(p.value_after))}; `
    +(owed<0?`TCP owed you ${money(-owed)}.`:`amount owed ${money(owed)}.`);
  const nb=[["Reason",p.reason]];if(p.customer_note)nb.push(["Note",p.customer_note]);
  nb.push(["Questions",`WhatsApp or call ${B.phone} and quote credit note ${p.credit_note_no}.`]);
  nb.push(["Terms","All amounts are in Ghana cedis (GH₵). A credit note is not a refund: money paid back is shown on a refund receipt."]);
  font("normal",7.5);const noteLines=nb.map(([h,b])=>[h,String(b).split("\n").flatMap(l=>wrap(l,LW))]);
  const notesH=noteLines.reduce((a,[,b])=>a+tlh+1.5+b.length*tlh+3,0);
  font("normal",8);const effLines=wrap(effect,TW-5);
  const gh=3*2+pt(11)*1.45,sumH=.5+1.5+gh+3+effLines.length*pt(8)*1.45;
  if(y+4+Math.max(notesH,sumH)>BOTTOM){pdf.addPage();y=TOP;}else y+=4;
  let ny=y;
  noteLines.forEach(([h,b])=>{font("bold",7.5,MUTE);txt(h.toUpperCase(),L,ny,{sp:pt(7.5)*.1});ny+=tlh+1.5;
    font("normal",7.5,"#333333");b.forEach(l=>{txt(l,L,ny);ny+=tlh;});ny+=3;});
  const sx=R-TW;let sy=y;
  pdf.setFillColor(INK);pdf.rect(sx,sy,TW,.5,"F");sy+=.5+1.5;
  pdf.setFillColor(INK);pdf.rect(sx,sy,TW,gh,"F");pdf.setFillColor(OCHRE);pdf.rect(sx,sy,1.5,gh,"F");
  font("bold",11,"#ffffff");txt("Amount credited",sx+1.5+2.5,sy+3);txt(money(toP(p.amount)),R-2.5,sy+3,{right:1});
  sy+=gh+3;font("normal",8,"#333333");effLines.forEach((l,i)=>txt(l,sx+2.5,sy+i*pt(8)*1.45));
  // -- Every page: footer; a cancelled credit note is stamped (date only,
  //    never the reason: decision 2).
  const n=pdf.getNumberOfPages();
  for(let pg=1;pg<=n;pg++){pdf.setPage(pg);
    font("normal",7,MUTE);txt(`${B.website}  ·  ${B.phone}`,L,289);txt(`Page ${pg} of ${n}`,R,289,{right:1});
    if(p.cancelled_on){pdf.saveGraphicsState();pdf.setGState(new pdf.GState({opacity:0.14}));
      font("bold",64,RED);pdf.text("CANCELLED",38,205,{angle:35});pdf.restoreGraphicsState();
      font("bold",8,RED);txt(`CANCELLED on ${dateText(p.cancelled_on)}. This credit note no longer counts.`,L,284);}}
  return pdf;
}

// ---- 9. Screens and the address -----------------------------------------------
// One page, four screens, picked by the part of the address after "#/":
//   #/  Home · #/invoices  the list · #/invoice/<id>  one invoice · #/new
// Anything else after "#" (a sign-in link's details) is not a screen.
const VIEWS=["#homeV","#listV","#ledV","#notesV","#invV"];
let HERE="#/",SKIP=false;   // HERE: the screen shown now (for "Go back")
const canEdit=()=>!!ME&&(ME.role==="owner"||ME.role==="sales");
function view(name,tab){VIEWS.forEach(v=>show(v,v===name));
  document.querySelectorAll("#tabs a").forEach(a=>a.classList.toggle("on",a.dataset.tab===tab));window.scrollTo(0,0);}
// Inside the invoice screen: the estimate box, the form, or the read-only view.
function showOnly(part){["#start","#form","#issuedSec","#discardBox","#payForm","#fixForm","#rcptSec","#cnForm","#cnSec"].forEach(p=>show(p,p===part));
  // The notes panel is shown again by the form or the view that wants it;
  // an open correction box goes with the screen it was on.
  show("#notesSec",false);CORR=null;const b=$("#ncBox");if(b)b.remove();}
function parseRoute(){
  const h=location.hash||"";
  if(!h.startsWith("#/"))return{name:"home",params:new URLSearchParams()};
  const[path,qs]=h.slice(2).split("?"),parts=path.split("/").filter(Boolean),params=new URLSearchParams(qs||"");
  if(parts[0]==="invoices")return{name:"invoices",params};
  if(parts[0]==="payments")return{name:"payments",params};
  if(parts[0]==="notes")return{name:"notes",params};
  if(parts[0]==="invoice"&&/^\d+$/.test(parts[1]||"")&&parts[2]==="credit")return{name:"credit-form",id:+parts[1],params};
  if(parts[0]==="invoice"&&/^\d+$/.test(parts[1]||""))return{name:"invoice",id:+parts[1],params};
  if(parts[0]==="credit"&&/^\d+$/.test(parts[1]||""))return{name:"credit",id:+parts[1],params};
  if(parts[0]==="new")return{name:"new",params};
  if(parts[0]==="receipt"&&/^\d+$/.test(parts[1]||""))return{name:"receipt",id:+parts[1],params};
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
  if(r.name==="payments")return showLedger(r.params);
  if(r.name==="notes")return showNotes(r.params);
  if(r.name==="receipt"){view("#invV","invoices");return showReceipt(r.id);}
  if(r.name==="credit-form"){view("#invV","invoices");return openCredit(r.id);}
  if(r.name==="credit"){view("#invV","invoices");CN=null;return showCredit(r.id);}
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
  renderNotes(S.invoiceId?(NDOC&&NDOC.id===S.invoiceId?NDOC:{id:S.invoiceId,state:"draft",internal_notes:[]}):null,true);
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
  // Every issued invoice shows its total and what is left to pay (spec
  // section 4); a draft or a cancelled invoice owes nothing.
  const owes=r.state==="issued";
  return`<a class="dk-inv" href="#/invoice/${r.id}" data-id="${r.id}">
    <span class="dk-inv-top"><b>${draft?"Draft":esc(r.invoice_no||"")}</b><i class="dk-badge s-${esc(r.status)}">${esc(STATUS[r.status]||r.status)}</i></span>
    <span class="dk-inv-who">${esc(r.billed_to_name||"(no name)")}${r.billed_to_phone?" · "+esc(r.billed_to_phone):""}</span>
    <span class="dk-inv-bot"><small>${esc(when)}</small><b>${money(toP(r.total))}${owes?`<small class="dk-left">${toP(r.balance)<0?`TCP owes ${money(-toP(r.balance))}`:`${money(toP(r.balance))} left`}</small>`:""}</b></span>
  </a>`;}

// Home: the figures are the database's own (back_office_home); nothing is
// added up on the phone. Each figure opens the matching list.
async function showHome(){
  view("#homeV","home");$("#homeMsg").textContent="";
  $("#unsavedNote").innerHTML=unsaved()?`<div class="dk-card dk-alert"><b>An invoice is in progress and not saved.</b> <a href="${S.invoiceId?"#/invoice/"+S.invoiceId:"#/new"}">Continue it</a></div>`:"";
  try{
    const[h,recent,today]=await Promise.all([api.home(),api.list({status:"all",terms:[],offset:0,limit:5}),api.totals("today")]);
    // Removed access reads as zeros and an empty list, not as an error.
    if(!recent.rows.length)await stillStaff();
    $("#hOwed").textContent=money(toP(h.owed));
    // Received today (decision 1): the same figure as Payments → Today.
    $("#hToday").textContent=smoney(toP(today.net));
    $("#hUnpaid").textContent=h.unpaid;$("#hPart").textContent=h.part_paid;
    $("#hOverdue").textContent=h.overdue;$("#hDrafts").textContent=h.drafts;
    // Phase 2.3 (decision 1): money in credit, apart from what is owed.
    show("#hCreditLink",+h.in_credit_count>0);
    $("#hCreditWhat").textContent=`In credit: TCP owes ${h.in_credit_count} ${+h.in_credit_count===1?"customer":"customers"}`;
    $("#hCredit").textContent=money(toP(h.in_credit||0));
    $("#recent").innerHTML=recent.rows.length?recent.rows.map(rowHTML).join(""):`<p class="dk-help">No invoices yet.</p>`;
  }catch(err){readFailed(err,"#homeMsg");}
  showSwitch();
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
    // The order is by the date an invoice was started (then its id), not
    // the date it was issued: predictable, and paging never skips or repeats
    // one (accepted for v1 by ChatGPT and Daniel, 23 Nov 2026).
    const n=`${LIST.count} ${LIST.count===1?"invoice":"invoices"}`;
    $("#listInfo").textContent=LIST.count?(LIST.status==="owed"?"Owed to TCP: ":"")+n+" · newest first, by date started":"";
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
window.TCPDesk={makeCreditPdf,waCreditText,credit:()=>CDOC,creditForm:()=>CN,cnOp:()=>pendingCn(),parseEstimate,num,totals,problems,waNumber,waText,makePdf,makeReceiptPdf,waReceiptText,linesForDb,searchTerms,ledgerTerms,state:()=>S,doc:()=>DOC,receipt:()=>RDOC,pay:()=>PAY,fix:()=>FIX,op:()=>pendingOp()};
})();
