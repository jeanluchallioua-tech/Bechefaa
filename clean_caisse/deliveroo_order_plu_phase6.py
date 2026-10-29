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


# Reference read from the original Developer Portal basket test_3009,
# basket_id 0642e052-1c4d-4c94-a271-0fc7e8f528a0 (29 October 2026).
# These English sandbox fixtures are not mappings to the restaurant catalogue.
SANDBOX_ITEM_NAMES = {'MU11002': 'Veggie Burger (V)', 'MU11001': 'Chicken Burger'}


def mismatched_sandbox_plu_paths(payload):
    body = payload.get('body') if isinstance(payload, dict) else None
    order = body.get('order') if isinstance(body, dict) else None
    items = order.get('items') if isinstance(order, dict) else None
    if not isinstance(items, list):
        return []
    normalize = lambda value: ' '.join(str(value or '').split()).casefold()
    by_name = {normalize(name): code for code, name in SANDBOX_ITEM_NAMES.items()}
    mismatches = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        code = str(item.get('pos_item_id') or '').strip()
        name = normalize(item.get('name'))
        if not code:
            continue  # Missing identifiers have their separate failure reason.
        expected_name = SANDBOX_ITEM_NAMES.get(code)
        expected_code = by_name.get(name)
        if ((expected_name is not None and normalize(expected_name) != name)
                or (expected_code is not None and expected_code != code)):
            mismatches.append(f'items[{index}].pos_item_id')
    return mismatches
