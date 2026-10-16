# 14S 18650 Battery Pack Breakout (A4)

KiCad 10 project for a 14S (58.8 V max, 50.4 V nominal) 18650 battery pack on a 297 × 210 mm (A4) 4-layer PCB, built as a BMS breakout and training board.

![top](docs/board_top.png)

## Layout architecture
- **Cells:** two mirrored columns of 7. Cells 1–7 run down the left column and cells 8–14 up the right. Every row uses the same **27.6 mm pitch**, so every cell has a 4.8 mm air gap on each side.
- **Equal cell-to-cell resistance (ACIR):** all 13 cell-to-cell links are the same copper strap on F.Cu and B.Cu. The 12 in-column straps are identical 10 mm bars at the holder ends. The cell 7→8 strap across the channel is widened to 16.15 mm so its resistance matches. Checked with a 2-D field solve (`tools/acir.py`, result in `docs/acir_check.txt`): **0.260 mΩ per link, 0.08 % spread**.
- **Centre channel = sense spine.** Each cell node has its own 60 V PPTC right next to it. One routed bus on In1 carries all 15 taps up to J1. NTC pairs run on In2.
- **Top edge = every connection.** Left to right: B− lug · HV indicator + pack TVS · **J1 balance** (centred) · **J2 NTC** · PACK+ lug · fuse.
- **Outer margins = per-cell service area.** Red/black test loops, the reverse-cell LED, and a writable box for cell voltage / IR.

## Symmetry
The board is mirror-symmetric about its vertical centre line. `tools/symcheck.py` lists every footprint without a same-type twin at the mirrored position:
- Mirrored or on the centre line: all 14 holders, the cell straps, the per-cell LED/test-loop groups (the series order of each LED string is chosen so twins use the same parts), the 6 side NTCs, the 12 side PPTCs, the TVS chain under J1, the lugs, holes and fiducials. PPTC 7, NTC4 and J1 sit on the centre line.
- One-of-a-kind, by design: the J2 NTC header (mirrored by the HV indicator + pack TVS block) and the single PACK+ fuse with its blown LED.
- Cell polarity alternates down each column. Because the pack is one series string, the right column's polarity is the reverse of the left's.

## Parts (all JLCPCB / LCSC)
| Block | Parts |
|---|---|
| Cell holders | BH-18650-B1BA002 `C2988620` |
| Per cell | Keystone 5000/5001 test loops (`C5199900` / `C238122`). Reverse-cell LED: 1k `C17513` + red LED `C84256` + 1N4148WS `C2128`. |
| J1 BMS balance | JST XH **B15B-XH-A** `C158020`. Pin 1 = B−, pin 15 = C14+. |
| Tap protection | MF-MSMF010-2 60 V PPTC `C12430` at every node. LKS05D3-B 5 V bidirectional TVS (SOD-323) `C2984829` across every cell, directly under J1. |
| J2 BMS NTC | JST XH **B14B-XH-A** `C158022` with 7× 10k B3950 NTC `C13879` saddled between cells. Pins 2n−1/2n = NTCn. |
| Power path | 5×20 fuse holder `C268205` (fit 10 A), M4 lugs T44009 `C481463`, SMCJ70CA `C840779` |

NTC map: NTC1 = C1/C2, NTC2 = C3/C4, NTC3 = C5/C6 (left column), **NTC4 = board centre line on the cell 7→8 bus**, NTC5 = C13/C14, NTC6 = C11/C12, NTC7 = C9/C10 (right column).

## How to connect
1. Plug the BMS balance lead into **J1** (B− wire on pin 1).
2. Plug the BMS NTC lead into **J2**, or leave it unplugged.
3. Connect the **B− lug** to the BMS B− pad, and the **PACK+ lug** to the load or charger +.
4. Connect the load or charger − to the BMS P−.
5. Insert the cells last. A red LED beside a cell means it is in backwards.

## Files
- `fab/BatteryPack_14S_A4_gerbers.zip`, `fab/JLCPCB_BOM.csv`, `fab/JLCPCB_CPL.csv`: fabrication and assembly files. Check part rotations in JLC's preview.
- `fab/erc.rpt`, `fab/drc.rpt`: 0 ERC violations, 0 DRC violations, 0 unconnected items, 0 schematic-parity issues.
- `docs/`: schematic PDF, renders, and the ACIR check.
- `tools/`: generators. `symcheck.py` runs the symmetry audit. `design.py` holds the parts and nets, `geom.py` the board geometry, `gen_sch.py` / `gen_pcb.py` build the files, and `acir.py` runs the link-resistance check. To rebuild everything, run `tools/build.sh` in the `kicad/kicad:10.0` docker image.

Side-entry XH headers (S15B) are out of stock at LCSC, so the top-entry headers sit right on the top edge. Re-check LCSC stock before ordering. The holder, the test loops and the SOD-323 TVS have the lowest stock.
