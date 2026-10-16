"""Regression tests: saving must not hide the pending order or restart upsells."""
import ast
import subprocess
import unittest
from pathlib import Path


class PosSaveWorkflowTests(unittest.TestCase):
    def test_confirmed_save_double_click_failure_and_same_order_edit(self):
        source = Path('clean_caisse/app.py').read_text()
        save = source[source.index('let SAVE_IN_FLIGHT=null;'):source.index('function sendKitchen(orderId,orderNum)')]
        script = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const listeners={},windowListeners={},storage=new Map();let posts=0,fail=false,resolvePost;
const message={html:'',querySelector(){return null},set innerHTML(v){this.html=v},get innerHTML(){return this.html}};
const orderBox={innerHTML:''},button={dataset:{},removeAttribute(){}};
const document={readyState:'complete',getElementById:id=>id==='order-message'?message:id==='order'?orderBox:null,
querySelector:()=>button,addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn),
dispatchEvent:e=>(listeners[e.type]||[]).forEach(fn=>fn(e))};
const line={line_id:'l1',product_id:'burger',name:'Burger',qty:1,unit_price:12,options:[{name:'Sauce'}]};
const order={id:'order-1',num:80,status:'Enregistrée',total:12,ticket_type:'Emporter',items:[line]};
const ctx={document,window:{addEventListener:(name,fn)=>(windowListeners[name]??=[]).push(fn)},
sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail}},
setTimeout:fn=>fn(),MutationObserver:class{observe(){}},alert(){},confirm:()=>true,
ORDER:[line],LAST_SAVED_ORDER:null,TICKET_TYPE:'Emporter',esc:s=>String(s),
renderOrder:()=>{orderBox.innerHTML='EMPTY'},fetch:async(url,opts={})=>{
 if(opts.method==='POST'){posts++;await new Promise(r=>resolvePost=r);if(fail)throw Error('Failed to fetch');return{ok:true,json:async()=>({ok:true,...order})}}
 if(opts.method==='PUT')return{ok:true,json:async()=>({ok:true,...order,total:15})};
 return{ok:true,json:async()=>({ok:true,order:url.endsWith('payment-phase41')?{paid_amount:0,payment_status:'À ENCAISSER'}:order})};
}};
vm.createContext(ctx);
vm.runInContext(SAVE_SOURCE,ctx);
vm.runInContext(fs.readFileSync('clean_caisse/static/pos-pending-edit.js','utf8'),ctx);
(async()=>{
const first=ctx.saveOrder(),second=ctx.saveOrder();assert.equal(posts,1);assert.equal(first,second);
assert.equal(ctx.ORDER.length,1);resolvePost();await first;
assert.equal(ctx.LAST_SAVED_ORDER.id,'order-1');assert.equal(ctx.ORDER.length,0);
assert(orderBox.innerHTML.includes('Burger'));assert(message.html.includes('Envoyer en cuisine'));
assert(storage.has('bechefaa_pending_saved_order_v1'));
await ctx.window.bechefaaPendingEdit.open();assert.equal(ctx.ORDER.length,1);
ctx.ORDER.push({...line,line_id:'drink',name:'Boisson',unit_price:3});
await ctx.window.bechefaaPendingEdit.save();assert.equal(posts,1);assert.equal(ctx.LAST_SAVED_ORDER.id,'order-1');
assert(orderBox.innerHTML.includes('Boisson'));
ctx.LAST_SAVED_ORDER=null;ctx.ORDER=[line];fail=true;
const failed=ctx.saveOrder();resolvePost();await failed;
assert.equal(ctx.ORDER.length,1);assert(message.html.includes('panier conservé'));
assert.equal(ctx.LAST_SAVED_ORDER,null);
console.log('PASS saved summary, duplicate clicks, same order edit, network failure retains cart');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        import json
        subprocess.run(['node', '-e', 'const SAVE_SOURCE=' + json.dumps(save) + ';\n' + script], check=True)

    def test_upsell_interception_removed_and_scripts_valid(self):
        final = Path('clean_caisse/pos_options_modal_final.py').read_text()
        self.assertNotIn('finishUpsellAndSave', final)
        self.assertNotIn('openUpsellPhase', final)
        self.assertIn('/static/pos-pending-edit.js?v=2', final)
        dark = Path('clean_caisse/pos_reference_dark.py').read_text()
        self.assertNotIn('setTimeout(openUpsell', dark)
        self.assertNotIn("upsell=document.createElement", dark)
        import re
        for path in ['clean_caisse/app.py', 'clean_caisse/pos_options_modal_final.py',
                     'clean_caisse/pos_reference_dark.py', 'clean_caisse/pos_design_v2.py']:
            tree = ast.parse(Path(path).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for script in re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', node.value, re.S):
                        subprocess.run(['node', '--check'], input=script, text=True, capture_output=True, check=True)


if __name__ == '__main__':
    unittest.main()
