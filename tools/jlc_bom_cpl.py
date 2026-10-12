"""Write JLCPCB assembly BOM + CPL from the KiCad netlist and position file."""
import csv
import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sexpr  # noqa: E402
from sexpr import find, find1  # noqa: E402

net, pos, out = sys.argv[1:4]
nl = sexpr.parse(open(net).read())
groups = OrderedDict()
for c in find(find1(nl, "components"), "comp"):
    ref = find1(c, "ref")[1]
    f = {}
    for x in find(find1(c, "fields"), "field"):
        atoms = [a for a in x[1:] if not isinstance(a, list)]
        f[find1(x, "name")[1]] = atoms[0] if atoms else ""
    if not f.get("LCSC"):
        continue  # mounting holes / fiducials
    key = (find1(c, "value")[1], find1(c, "footprint")[1].split(":")[1], f["LCSC"], f.get("MPN", ""))
    groups.setdefault(key, []).append(ref)


def natkey(r):
    import re
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", r)]


with open(os.path.join(out, "JLCPCB_BOM.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "MPN", "Qty"])
    for (val, fp, lcsc, mpn), refs in groups.items():
        refs.sort(key=natkey)
        w.writerow([val, ",".join(refs), fp, lcsc, mpn, len(refs)])
with open(pos) as fh, open(os.path.join(out, "JLCPCB_CPL.csv"), "w", newline="") as fo:
    w = csv.writer(fo)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for r in csv.DictReader(fh):
        if r["Ref"].startswith(("H", "FID")):
            continue
        w.writerow([r["Ref"], r["PosX"] + "mm", r["PosY"] + "mm",
                    "Top" if r["Side"].lower() == "top" else "Bottom", r["Rot"]])
print("BOM lines:", len(groups))
