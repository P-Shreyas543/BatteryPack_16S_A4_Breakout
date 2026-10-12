#!/bin/bash
# Regenerate schematic + PCB + fab outputs. Run inside the KiCad 10 container
# (e.g. docker run -v $PWD:/prj -w /prj kicad/kicad:10.0 bash tools/build.sh)
set -e
cd "$(dirname "$0")/.."
mkdir -p ~/.config/kicad/10.0 && cp -n /usr/share/kicad/template/*-lib-table ~/.config/kicad/10.0/ 2>/dev/null || true
P=BatteryPack_16S_A4_Breakout
python3 tools/gen_sch.py /usr/share/kicad/symbols .
kicad-cli sch erc --severity-all --exit-code-violations -o fab/erc.rpt $P.kicad_sch
kicad-cli sch export netlist --format kicadsexpr -o fab/$P.net $P.kicad_sch
python3 tools/check_netlist.py fab/$P.net
python3 tools/gen_pcb.py . fab/$P.net
kicad-cli pcb drc --schematic-parity --refill-zones --severity-all --exit-code-violations -o fab/drc.rpt $P.kicad_pcb
rm -rf fab/gerbers && mkdir -p fab/gerbers
kicad-cli pcb export gerbers --no-protel-ext -o fab/gerbers/ \
  -l F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts $P.kicad_pcb
kicad-cli pcb export drill --format excellon --excellon-separate-th -o fab/gerbers/ $P.kicad_pcb
python3 -c "import zipfile,glob,os; z=zipfile.ZipFile('fab/BatteryPack_14S_A4_gerbers.zip','w',zipfile.ZIP_DEFLATED); [z.write(f,os.path.basename(f)) for f in sorted(glob.glob('fab/gerbers/*'))]"
kicad-cli pcb export pos --format csv --units mm --side both -o fab/pos_kicad.csv $P.kicad_pcb
python3 tools/jlc_bom_cpl.py fab/$P.net fab/pos_kicad.csv fab
kicad-cli sch export pdf -o docs/BatteryPack_14S_Schematic.pdf $P.kicad_sch
kicad-cli pcb render --side top -w 2400 -h 1700 --quality high -o docs/board_top.png $P.kicad_pcb
kicad-cli pcb render --side bottom -w 2400 -h 1700 -o docs/board_bottom.png $P.kicad_pcb
rm -f fab/pos_kicad.csv
