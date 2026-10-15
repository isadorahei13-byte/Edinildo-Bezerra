#!/usr/bin/env bash
# Etapa 1 do pipeline (Video Use): transcreve, corta silêncios/hesitações/repetições,
# renderiza o corte e prepara a pasta do HyperFrames para a etapa 2 (animações).
#
# Uso: video-pipeline/editar.sh <video> [nome-do-projeto] [opções extras do auto_cut.py]
# Ex.: video-pipeline/editar.sh ~/uploads/gravacao.mp4 outubro-rosa --max-pause 0.25
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
VIDEO_USE_DIR="${VIDEO_USE_DIR:-$HOME/Developer/video-use}"
PY="${VIDEO_VENV:-$HOME/.venvs/video-pipeline}/bin/python"

[ $# -ge 1 ] || { sed -n '2,7p' "$0"; exit 1; }
SRC="$(realpath "$1")"; shift
NAME="$(basename "${SRC%.*}")"
if [ $# -ge 1 ] && [[ "$1" != --* ]]; then NAME="$1"; shift; fi
PROJ="$REPO/videos/$NAME"
EDIT="$PROJ/edit"

mkdir -p "$PROJ" "$EDIT"
# A fonte fica intocada dentro do projeto (o Video Use nunca altera a origem).
[ -e "$PROJ/$(basename "$SRC")" ] || cp "$SRC" "$PROJ/"
VIDEO="$PROJ/$(basename "$SRC")"

echo "▶ 1/4 transcrição"
"$PY" "$HERE/transcribe.py" "$VIDEO" --edit-dir "$EDIT"
"$PY" "$VIDEO_USE_DIR/helpers/pack_transcripts.py" --edit-dir "$EDIT" >/dev/null

echo "▶ 2/4 decisões de corte (silêncios, hesitações, repetições)"
"$PY" "$HERE/auto_cut.py" --edit-dir "$EDIT" "$VIDEO" "$@"

echo "▶ 3/4 render do corte (Video Use)"
"$PY" "$VIDEO_USE_DIR/helpers/render.py" "$EDIT/edl.json" -o "$EDIT/cut.mp4" --no-subtitles

echo "▶ 4/4 preparando HyperFrames"
"$PY" "$HERE/prepare_hyperframes.py" --edit-dir "$EDIT" --cut "$EDIT/cut.mp4" --work-dir "$PROJ/hyperframes"

echo
echo "Corte pronto: $EDIT/cut.mp4"
echo "Relatório:    $EDIT/cut_report.md"
echo "Próximo passo: animações com /talking-head-recut em $PROJ/hyperframes"
