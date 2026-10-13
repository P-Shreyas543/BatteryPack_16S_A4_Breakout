"""List footprints with no mirror partner across the vertical centre line (x = 148.5)."""
import sys
import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
MX, TOL = 148.5, 0.6
def centre(f):
    bb = f.GetBoundingBox(False)       # body + pads, independent of the anchor pad
    c = bb.GetCenter()
    return pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)


fps = [(f.GetReference(), f.GetFPIDAsString()) + centre(f) for f in b.GetFootprints()]
alone = []
for ref, fp, x, y in fps:
    if abs(x - MX) < TOL:
        continue                                   # on the centre line
    mate = [r for r, f2, x2, y2 in fps if f2 == fp and abs(x2 - (2 * MX - x)) < TOL and abs(y2 - y) < TOL]
    if not mate:
        alone.append((ref, fp.split(":")[1], round(x, 1), round(y, 1)))
print("footprints:", len(fps), " without a mirror partner:", len(alone))
for a in sorted(alone, key=lambda t: (t[3], t[2])):
    print("  ", a)
