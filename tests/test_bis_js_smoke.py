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


if __name__ == "__main__":
    unittest.main()
