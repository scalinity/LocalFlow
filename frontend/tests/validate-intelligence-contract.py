"""Validate synthetic Hub payloads against native schemas, without handlers.

Only Field constructors and literal schema assignments are evaluated. No app,
provider, database, clipboard, filesystem reader, or registered handler runs.
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys


def schemas(root: Path):
    target = root / 'localflow/v2/ui/companion/surfaces/intelligence.py'
    bridge_path = root / 'localflow/v2/ui/companion/bridge.py'
    spec = importlib.util.spec_from_file_location('hub_contract_bridge', bridge_path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    authoring = ast.parse((root / 'localflow/v2/transforms/authoring.py').read_text())
    text_fields = next(ast.literal_eval(node.value) for node in authoring.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(name, ast.Name) and name.id == 'TEXT_FIELDS'
                               for name in node.targets))
    env = {'__builtins__': {}, 'TEXT_FIELDS': text_fields}
    env.update({name: getattr(bridge, name) for name in
                ('Bool', 'Enum', 'Int', 'List', 'Nullable', 'Obj', 'Str')})
    tree = ast.parse(target.read_text())
    names = {'EXAMPLE', 'DRAFT', 'CHOICE', 'SCOPE', 'DEPTH', 'SESSION',
             'inspection', 'inspection_copy_fields', 'suggestion_filter', 'kinds', 'filters'}
    result = {}

    def evaluate(node):
        return eval(compile(ast.Expression(node), str(target), 'eval'), env)

    def read(statements):
        for node in statements:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                name = node.targets[0]
                if isinstance(name, ast.Name) and name.id in names:
                    env[name.id] = evaluate(node.value)
            elif isinstance(node, ast.FunctionDef) and node.name in ('register', '_register_memory'):
                read(node.body)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Name) and call.func.id == 'command':
                    result[ast.literal_eval(call.args[0])] = evaluate(call.args[1])
    read(tree.body)
    return bridge, result


def main():
    payload = json.load(sys.stdin)
    bridge, registered = schemas(Path(payload['root']))
    errors = []
    for case in payload['cases']:
        name = case['command']
        if name not in registered:
            errors.append({'command': name, 'reason': 'not_registered'})
            continue
        try:
            bridge.validate(case['payload'], registered[name])
        except bridge.SchemaError as exc:
            errors.append({'command': name, 'reason': str(exc)})
    print(json.dumps({'checked': len(payload['cases']), 'errors': errors,
                      'registered': sorted(registered)}))
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
