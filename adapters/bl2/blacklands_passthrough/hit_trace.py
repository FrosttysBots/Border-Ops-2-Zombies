"""Primitive diagnostics of native hit references; no discovered methods invoked."""
import math
from itertools import islice


def bullet_schemas():
    """List loaded bullet-related class signatures without creating objects."""
    from unrealsdk import find_all
    result = {}
    for cls in find_all('Class'):
        if 'bullet' not in str(cls.Name).lower():
            continue
        proxy = type('ClassView', (), {'Class': cls})()
        result[cls._path_name()] = dict(functions=function_schema(proxy), properties=[
            dict(name=str(p.Name), type=str(p.Class.Name)) for p in islice(cls._properties(), 96)])
        if len(result) >= 24:
            break
    return result


def function_schema(weapon):
    """Reflect candidate hit/trace APIs; do not execute them."""
    from unrealsdk.unreal import UFunction
    result = {}
    for field in weapon.Class._fields():
        name = str(field.Name)
        if not isinstance(field, UFunction) or not any(t in name.lower() for t in ('hit','trace','bullet','impact','shot','fire')):
            continue
        params = []
        for p in field._properties():
            if not p.PropertyFlags & 0x80:
                continue
            param = dict(name=str(p.Name),type=str(p.Class.Name),flags=p.PropertyFlags)
            if str(p.Class.Name)=='StructProperty':
                param['fields'] = [{'name':str(v.Name),'type':str(v.Class.Name)} for v in p.Struct._properties()][:48]
            params.append(param)
        result[name]=params[:32]
        if len(result)>=128:
            break
    return result


def describe(value, depth=0, budget=None):
    if budget is None:
        budget = [160]
    budget[0] -= 1
    if budget[0] < 0:
        return '<budget reached>'
    if value is None or type(value) in (bool, int, str):
        return value[:256] if isinstance(value, str) else value
    if type(value) is float:
        return value if math.isfinite(value) else None
    if hasattr(value, '_path_name'):
        result = {'object': value._path_name(), 'class': str(value.Class.Name)}
        if depth < 2:
            fields = {}
            for prop in value.Class._properties():
                name = str(prop.Name)
                if not any(word in name.lower() for word in ('weapon', 'causer', 'instigator', 'owner', 'source', 'shot')):
                    continue
                if len(fields) >= 20:
                    break
                try:
                    fields[name] = describe(getattr(value, name), depth+1, budget)
                except Exception as exc:
                    fields[name] = {'unavailable': type(exc).__name__}
            result['references'] = fields
        return result
    if hasattr(value, '_type') and depth < 3:
        result = {}
        for prop in value._type._properties():
            if len(result) >= 32:
                break
            name = str(prop.Name)
            try:
                result[name] = describe(getattr(value, name), depth+1, budget)
            except Exception as exc:
                result[name] = {'unavailable': type(exc).__name__}
        return result
    return {'python_type': type(value).__name__}
