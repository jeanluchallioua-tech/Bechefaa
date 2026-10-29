"""Validate presence of POS identifiers without guessing catalogue matches."""


def missing_plu_paths(payload):
    body = payload.get('body') if isinstance(payload, dict) else None
    order = body.get('order') if isinstance(body, dict) else None
    items = order.get('items') if isinstance(order, dict) else None
    if not isinstance(items, list):
        return []  # Structural validation remains the importer's responsibility.
    missing = []
    def walk(nodes, path):
        for index, item in enumerate(nodes):
            if not isinstance(item, dict):
                continue
            node_path = f'{path}[{index}]'
            value = item.get('pos_item_id')
            if not isinstance(value, str) or not value.strip():
                missing.append(node_path + '.pos_item_id')
            modifiers = item.get('modifiers')
            if isinstance(modifiers, list):
                walk(modifiers, node_path + '.modifiers')
    walk(items, 'items')
    return missing
