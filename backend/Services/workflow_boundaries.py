"""Pure validation and coverage helpers for artifact workflows."""


def chunk_size(value) -> int:
    if value is None:
        return 80
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("chunk_size must be an integer from 1 to 10000")
    try:
        size = int(value)
    except ValueError:
        raise ValueError("chunk_size must be an integer from 1 to 10000") from None
    if not 1 <= size <= 10000:
        raise ValueError("chunk_size must be an integer from 1 to 10000")
    return size


def taxonomy_forest(nodes, edges):
    by_id = {str(n.get("term_id") or n.get("uri") or ""): n for n in nodes}
    by_id.pop("", None)
    children = {key: set() for key in by_id}
    child_ids = set()
    for edge in edges:
        child, parent = str(edge.get("source_term") or ""), str(edge.get("target_term") or "")
        if child in by_id and parent in by_id:
            children[parent].add(child)
            child_ids.add(child)
    ordered = lambda values: sorted(values, key=lambda key: (str(by_id[key].get("label") or key).casefold(), key))
    roots, forest, covered = [], [], set()
    # Remaining IDs seed disconnected cycles after all normal roots.
    for root in ordered(set(by_id) - child_ids) + ordered(by_id):
        if root in covered:
            continue
        roots.append(root)
        target = []
        stack = [(root, target)]
        while stack:
            key, output = stack.pop()
            node = by_id[key]
            item = {"term_id": key, "uri": node.get("uri"), "label": node.get("label") or key,
                    "definition": node.get("definition") or "", "children": []}
            output.append(item)
            if key in covered:
                item["reference"] = True
                continue
            covered.add(key)
            for child in reversed(ordered(children[key])):
                stack.append((child, item["children"]))
        forest.extend(target)
    return roots, forest
