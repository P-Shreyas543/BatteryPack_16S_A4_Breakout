"""Minimal S-expression reader/writer for KiCad files."""
import re

_tok = re.compile(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+)', re.S)


class Sym(str):
    """Unquoted atom."""


def parse(text):
    stack, cur = [], []
    for m in _tok.finditer(text):
        t = m.group(1)
        if t == '(':
            stack.append(cur)
            cur = []
        elif t == ')':
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif t.startswith('"'):
            cur.append(t[1:-1].replace('\\"', '"').replace('\\\\', '\\'))
        else:
            cur.append(Sym(t))
    return cur[0]


def _atom(a):
    if isinstance(a, Sym):
        return str(a)
    if isinstance(a, bool):
        return 'yes' if a else 'no'
    if isinstance(a, (int, float)):
        s = ('%.4f' % a).rstrip('0').rstrip('.')
        return '0' if s in ('-0', '') else s
    return '"' + str(a).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def dump(node, ind=0):
    if not isinstance(node, list):
        return _atom(node)
    if all(not isinstance(x, list) for x in node):
        return '(' + ' '.join(_atom(x) for x in node) + ')'
    out = '(' + ' '.join(_atom(x) for x in node if not isinstance(x, list))
    for x in node:
        if isinstance(x, list):
            out += '\n' + '\t' * (ind + 1) + dump(x, ind + 1)
    return out + '\n' + '\t' * ind + ')'


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def find1(node, key):
    r = find(node, key)
    return r[0] if r else None
