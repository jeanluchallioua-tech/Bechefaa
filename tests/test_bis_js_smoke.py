"""Isolated Node.js smoke tests for BIS discount UI and offline totals."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js is required for JavaScript checks")
class BisJsSmokeTests(unittest.TestCase):
    def run_js(self, script):
        subprocess.run(["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True)

    def test_offline_discount_total(self):
        source = (ROOT / "clean_caisse/offline_mode_phase6.py").read_text(encoding="utf-8")
        js = source[source.index("function subtotalOf("):source.index("function ticketType(")]
        self.run_js(js + """
const assert=require('node:assert/strict');
const order={items:[{unit_price:15,qty:2}],manual_discount_percent:10};
assert.equal(subtotalOf(order),30);
assert.equal(discountOf(order),3);
assert.equal(totalOf(order),27);
assert.equal(order.items[0].unit_price,15);
""")

    def test_deliveroo_history_filter_uses_source(self):
        source = (ROOT / "clean_caisse/app.py").read_text(encoding="utf-8")
        js = source[
            source.index("function matchesHistoryFilter("):
            source.index("function render(){", source.index("function matchesHistoryFilter("))
        ]
        self.run_js(js + """
const assert=require('node:assert/strict');
const deliveroo={source:'DELIVEROO',ticket_type:'Livraison'};
const delivery={source:'LIVRAISON',ticket_type:'Livraison'};
const counter={source:'EMPORTER',ticket_type:'Comptoir'};
assert.equal(matchesHistoryFilter(deliveroo,'Deliveroo'),true);
assert.equal(matchesHistoryFilter(delivery,'Deliveroo'),false);
assert.equal(matchesHistoryFilter(counter,'Deliveroo'),false);
assert.equal(matchesHistoryFilter(deliveroo,'Tous'),true);
assert.equal(matchesHistoryFilter(delivery,'Livraison'),true);
assert.equal(matchesHistoryFilter(counter,'Comptoir'),true);
""")

    def test_discount_ui_save(self):
        source = (ROOT / "clean_caisse/app.py").read_text(encoding="utf-8")
        js = source[source.index("function setManualDiscount"):source.index("function sendKitchen(orderId,orderNum)")]
        harness = """
const vm=require('node:vm'), assert=require('node:assert/strict');
let sent; const box={innerHTML:''},message={innerHTML:''};
const context={
 ORDER:[{unit_price:15,qty:2,name:'Burger',options:[]}],
 TICKET_TYPE:'Emporter',MANUAL_DISCOUNT:0,LAST_SAVED_ORDER:null,
 esc:String,alert:()=>{},prompt:()=> '10',CustomEvent:class{},
 document:{querySelector:()=>null,getElementById:id=>id==='order'?box:message,dispatchEvent(){}},
 fetch:async(u,o)=>{sent=JSON.parse(o.body);return {ok:true,json:async()=>({ok:true,id:'test',num:1,total:27,status:'Enregistrée'})}}
};
vm.createContext(context);
vm.runInContext(CODE,context);
(async()=>{
 context.chooseManualDiscount();
 assert(box.innerHTML.includes('27,00 €'));
 assert(box.innerHTML.includes('Remise 10 %'));
 await context.saveOrder();
 assert.equal(sent.manual_discount_percent,10);
 assert.equal(context.ORDER.length,0);
 context.ORDER=[{unit_price:15,qty:2,name:'Burger',options:[]}];
 context.TICKET_TYPE='Salle';context.MANUAL_DISCOUNT=10;context.renderOrder();
 assert(!box.innerHTML.includes('onclick="chooseManualDiscount()"'));
})().catch(e=>{console.error(e);process.exitCode=1});
""".replace("CODE", json.dumps(js))
        self.run_js(harness)


    def test_site_notice_waits_for_click_then_launches_one_pack_per_order(self):
        # Execute the actual injected POS script with a fake DOM and Epson
        # function. No request is made to a real printer or deployed caisse.
        source = (ROOT / "clean_caisse/order_notifications_phase33.py").read_text(encoding="utf-8")
        js = source.split("<script>", 1)[1].split("</script>", 1)[0]
        js = (js.replace("__PAGE__", "pos")
                .replace("__PRINT_ENABLED__", "true")
                .replace("__TEST_MODE__", "false"))
        harness = r"""
const vm=require('node:vm'), assert=require('node:assert/strict');
const storage=new Map(), prints=[], now=Date.now();
let toneStarts=0;
const store={
  getItem:k=>storage.has(k)?storage.get(k):null,
  setItem:(k,v)=>storage.set(k,String(v)),
  removeItem:k=>storage.delete(k)
};
const orders=[
 {id:'site-1',status:'À préparer',sales_channel:'SITE',customer_name:'Alice',ticket_type:'À emporter',updated_at:now},
 {id:'site-2',status:'À préparer',sales_channel:'SITE',customer_name:'Bob',ticket_type:'Livraison',updated_at:now}
];
function makeElement(){
 const flags=new Set(),handlers={};
 return {
  id:'',dataset:{},style:{},textContent:'',tabIndex:0,
  classList:{add:k=>flags.add(k),remove:k=>flags.delete(k),contains:k=>flags.has(k)},
  addEventListener:(name,fn)=>{handlers[name]=fn;},
  setAttribute(){},get offsetWidth(){return 1;},
  click(){if(handlers.click)handlers.click();},
  keydown(e){if(handlers.keydown)handlers.keydown(e);}
 };
}
class FakeAudioContext{
 state='running';currentTime=0;destination={};
 createOscillator(){return {frequency:{setValueAtTime(){}},connect(){},start(){toneStarts++;},stop(){}};}
 createGain(){return {gain:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){}};}
}
function boot(items){
 const elements={};
 const document={
  hidden:false,
  body:{appendChild:el=>{if(el.id)elements[el.id]=el;}},
  getElementById:id=>elements[id]||null,
  createElement:()=>makeElement(),
  addEventListener(){}
 };
 const window={
  AudioContext:FakeAudioContext,
  addEventListener(){},
  bechefaaPrintOrderPack:async id=>{prints.push(id);return true;}
 };
 const context={
  window,document,navigator:{userAgent:'Android',userActivation:{hasBeenActive:true}},
  localStorage:store,sessionStorage:store,console,Date,Promise,AbortController,
  setTimeout:()=>0,clearTimeout(){},setInterval(){},
  fetch:async url=>({ok:true,json:async()=>url==='/api/kitchen/board'?
    {ok:true,orders:items}:{ok:true,pos_enabled:true,pos_volume:82}})
 };
 vm.createContext(context);vm.runInContext(CODE,context);
 return {notice:()=>elements['phase6-site-order-notice'],window};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const first=boot(orders);await tick();
 assert.equal(prints.length,0,'polling must not print');
 assert.equal(toneStarts,3,'one audible three-tone notification per new batch');
 assert(first.notice().classList.contains('show'));
 assert.equal(JSON.parse(store.getItem('bechefaa_site_pending_click_print_v1')).length,2);
 // A browser restart must not acknowledge or lose an unclicked notice.
 const resumed=boot(orders);await tick();
 assert(resumed.notice().classList.contains('show'));
 assert(resumed.notice().textContent.includes('Alice'));
 assert.equal(prints.length,0);
 resumed.notice().click();await tick();
 assert.deepEqual(prints,['site-1']);
 assert(resumed.notice().classList.contains('show'));
 assert(resumed.notice().textContent.includes('Bob'));
 resumed.notice().click();await tick();
 assert.deepEqual(prints,['site-1','site-2']);
 assert.equal(resumed.notice().classList.contains('show'),false);
 resumed.notice().click();await tick();
 assert.equal(prints.length,2,'repeated click must not print twice');
 assert.equal(JSON.parse(store.getItem('bechefaa_site_pending_click_print_v1')).length,0);
 // A replay of the same order after a reload must not print it again.
 const replay=boot(orders);await tick();
 assert.equal(replay.notice().classList.contains('show'),false);
 assert.equal(prints.length,2);
})().catch(e=>{console.error(e);process.exitCode=1;});
""".replace("CODE", json.dumps(js))
        self.run_js(harness)


if __name__ == "__main__":
    unittest.main()
