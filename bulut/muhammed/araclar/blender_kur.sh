#!/usr/bin/env bash
# Blender 4.2'yi (headless modelleme için) indirir ve açar. Linux x64.
# Kullanım: bash araclar/blender_kur.sh [hedef_klasor]
# Sonra:    $BLENDER -b -P araclar/blender_modelle.py -- --cikti cikti/mm-asistan-muhammed.glb
# Windows'ta: https://www.blender.org/download/ üzerinden 4.2 LTS kurun ve
#   "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" -b -P araclar\blender_modelle.py -- --cikti cikti\mm-asistan-muhammed.glb
set -euo pipefail
HEDEF="${1:-${TMPDIR:-/tmp}/blender}"
SURUM=4.2.3
mkdir -p "$HEDEF"
if [ ! -x "$HEDEF/blender-$SURUM-linux-x64/blender" ]; then
  echo "Blender $SURUM indiriliyor → $HEDEF"
  curl -sSL -o "$HEDEF/blender.tar.xz" "https://download.blender.org/release/Blender4.2/blender-$SURUM-linux-x64.tar.xz"
  tar -xJf "$HEDEF/blender.tar.xz" -C "$HEDEF"
  rm -f "$HEDEF/blender.tar.xz"
fi
echo "export BLENDER=$HEDEF/blender-$SURUM-linux-x64/blender"
"$HEDEF/blender-$SURUM-linux-x64/blender" -b --version | head -1
