"""Read-only PLU contract derived from the actual menu exporter, never test fixtures."""
import hashlib
import json


def normalized_name(value):
    return ' '.join(str(value or '').split()).casefold()


def build_plu_map(catalog):
    from .deliveroo_menu_builder_phase6 import _group_values, _choice
    if not isinstance(catalog,dict): raise ValueError('Production catalogue missing')
    mapping={}
    def add(plu,name,parent=None):
        value={'name':normalized_name(name),'parent':parent}
        if plu in mapping and mapping[plu]!=value: raise ValueError('Ambiguous production PLU')
        mapping[plu]=value
    for product in catalog.get('products') or []:
        if not isinstance(product,dict): continue
        if any(product.get(key,True) is False for key in ('active','marketplace_visible','deliveroo_visible')): continue
        product_id=str(product.get('id') or '').strip();name=str(product.get('name') or '').strip()
        if not product_id or not name: continue
        add(product_id[:50],name)
        for group_index,group in enumerate(product.get('options') or []):
            for choice_index,raw in enumerate(_group_values(group)):
                choice=_choice(raw,choice_index)
                if not choice['name']: continue
                plu=f'opt:{product_id}:{group_index}:{choice_index}'
                if len(plu)>50: plu='opt_'+hashlib.sha1(plu.encode()).hexdigest()[:32]
                add(plu,choice['name'],product_id[:50])
    if not mapping: raise ValueError('Production catalogue has no usable PLUs')
    return mapping


def load_plu_map(db):
    with db() as conn:
        row=conn.execute('SELECT data_json FROM catalog_admin_v2 WHERE id=1').fetchone()
    data=row['data_json'] if row else None
    if isinstance(data,str): data=json.loads(data)
    return build_plu_map(data)


def check_order_plus(order,mapping):
    """Return (API fail reason, invalid field paths), or (None, [])."""
    errors=[];unknown=False
    # Real products may be nested as constituents of the two exported bundles.
    # Their own modifiers still belong to that constituent's original PLU.
    drinks={'68','70','71','72','73','74','75','76'}
    bundle_children={'2':{'42','63'} | drinks, '4':{'8','63'} | drinks}
    def walk(items,path,parent=None):
        nonlocal unknown
        for index,item in enumerate(items or []):
            current=f'{path}[{index}]'
            if not isinstance(item,dict): unknown=True;errors.append(current);continue
            plu=str(item.get('pos_item_id') or '').strip();expected=mapping.get(plu)
            if not expected: unknown=True;errors.append(current)
            elif ((expected['parent']!=parent and not
                   (expected['parent'] is None and plu in bundle_children.get(parent,set())))
                  or expected['name']!=normalized_name(item.get('name') or item.get('operational_name'))):
                errors.append(current)
            next_parent=plu if expected and expected['parent'] is None else parent
            walk(item.get('modifiers'),current+'.modifiers',next_parent)
    walk(order.get('items'),'items')
    return ('pos_item_id_not_found' if unknown else 'pos_item_id_mismatched',errors) if errors else (None,[])


def normalized_modifiers(items):
    result=[]
    for item in items or []:
        if not isinstance(item,dict): raise ValueError('Invalid modifier')
        name=str(item.get('name') or item.get('operational_name') or '').strip()
        qty=item.get('quantity',1)
        if not name or not isinstance(qty,int) or isinstance(qty,bool) or qty<=0:
            raise ValueError('Invalid modifier name or quantity')
        result.append({'name':(str(qty)+'× ' if qty>1 else '')+name,'source_name':name,
                       'quantity':qty,'plu':str(item.get('pos_item_id') or '')})
        result.extend(normalized_modifiers(item.get('modifiers')))
    return result

