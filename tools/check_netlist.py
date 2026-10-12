"""Compare a kicad-cli exported netlist with design.py (connectivity + fields)."""
import re, sys
sys.path.insert(0, 'tools')
import design, sexpr
from sexpr import find, find1
nl = sexpr.parse(open(sys.argv[1]).read())
P = design.build()
got = {}
for n in find(find1(nl, 'nets'), 'net'):
    nodes = frozenset('%s.%s' % (find1(x, 'ref')[1], find1(x, 'pin')[1]) for x in find(n, 'node'))
    got[nodes] = find1(n, 'name')[1]
want = {}
for r, d in P.items():
    for pin, net in d['pins'].items():
        want.setdefault(net, set()).add('%s.%s' % (r, pin))
bad = 0
gotsets = {k: v for k, v in got.items()}
for net, nodes in want.items():
    if frozenset(nodes) not in gotsets:
        print('MISMATCH', net, sorted(nodes)); bad += 1
    elif not gotsets[frozenset(nodes)].split('/')[-1] == net:
        print('NAME', net, gotsets[frozenset(nodes)])
comps = {find1(c, 'ref')[1]: c for c in find(find1(nl, 'components'), 'comp')}
for r, d in P.items():
    c = comps.get(r)
    if c is None: print('MISSING', r); bad += 1; continue
    if find1(c, 'value')[1] != d['value'] or find1(c, 'footprint')[1] != d['fp']:
        print('FIELD', r); bad += 1
print('extra comps', set(comps) - set(P))
print('netlist check:', 'OK' if not bad else '%d problems' % bad)
