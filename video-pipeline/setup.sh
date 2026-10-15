#!/usr/bin/env bash
# Instala tudo o que o pipeline Video Use → HyperFrames precisa. Idempotente:
# na segunda execução só confere e sai rápido. Roda sozinho no início de cada
# sessão (hook SessionStart em .claude/settings.json).
set -uo pipefail

VIDEO_USE_DIR="${VIDEO_USE_DIR:-$HOME/Developer/video-use}"
VENV="${VIDEO_VENV:-$HOME/.venvs/video-pipeline}"
WHISPER_MODEL="${WHISPER_MODEL:-medium}"
log() { printf '[video-pipeline] %s\n' "$*" >&2; }

command -v ffmpeg >/dev/null || { log "ffmpeg ausente — instale com: sudo apt-get install -y ffmpeg"; exit 1; }
command -v node >/dev/null || { log "Node.js 22+ ausente (necessário para o HyperFrames)"; exit 1; }

# 1. Video Use (browser-use/video-use) + registro como skill
if [ -d "$VIDEO_USE_DIR/.git" ]; then
  git -C "$VIDEO_USE_DIR" pull --ff-only -q 2>/dev/null || true
else
  mkdir -p "$(dirname "$VIDEO_USE_DIR")"
  git clone -q --depth 1 https://github.com/browser-use/video-use "$VIDEO_USE_DIR" || { log "falha ao clonar video-use"; exit 1; }
fi
mkdir -p "$HOME/.claude/skills"
ln -sfn "$VIDEO_USE_DIR" "$HOME/.claude/skills/video-use"

# 2. Ambiente Python único: dependências do Video Use + faster-whisper
if [ ! -x "$VENV/bin/python" ]; then
  log "criando ambiente Python em $VENV"
  if command -v uv >/dev/null; then uv venv -q "$VENV"; else python3 -m venv "$VENV"; fi
fi
if ! "$VENV/bin/python" -c "import requests, librosa, matplotlib, PIL, numpy, faster_whisper" 2>/dev/null; then
  log "instalando dependências Python"
  if command -v uv >/dev/null; then
    uv pip install -q --python "$VENV/bin/python" requests librosa matplotlib pillow numpy faster-whisper
  else
    "$VENV/bin/pip" install -q requests librosa matplotlib pillow numpy faster-whisper
  fi
fi

# 3. HyperFrames (heygen-com/hyperframes): skills + navegador headless para render
if [ ! -f "$HOME/.claude/skills/talking-head-recut/SKILL.md" ]; then
  log "instalando skills do HyperFrames"
  (cd "$HOME" && npx --yes hyperframes skills update talking-head-recut embedded-captions >/dev/null 2>&1) \
    || log "aviso: não consegui instalar as skills do HyperFrames"
fi
if ! ls "$HOME"/.cache/hyperframes/chrome/chrome-headless-shell/*/chrome-headless-shell-linux64/chrome-headless-shell >/dev/null 2>&1; then
  log "baixando Chrome headless do HyperFrames"
  (cd "$HOME" && npx --yes hyperframes browser ensure >/dev/null 2>&1) || log "aviso: falha no 'hyperframes browser ensure'"
fi

# 4. Modelo de transcrição (só se não houver chave da ElevenLabs)
if [ -z "${ELEVENLABS_API_KEY:-}" ] && ! grep -q '^ELEVENLABS_API_KEY=..' "$VIDEO_USE_DIR/.env" 2>/dev/null; then
  if ! "$VENV/bin/python" - "$WHISPER_MODEL" <<'PY' 2>/dev/null
import sys
from faster_whisper.utils import download_model
download_model(sys.argv[1], local_files_only=True)
PY
  then
    log "baixando modelo Whisper '$WHISPER_MODEL' (Hugging Face)"
    "$VENV/bin/python" -c "from faster_whisper.utils import download_model; download_model('$WHISPER_MODEL')" >/dev/null 2>&1 \
      || log "aviso: sem acesso ao huggingface.co e sem ELEVENLABS_API_KEY — a transcrição não vai funcionar. Libere huggingface.co (e cdn-lfs.huggingface.co) na rede do ambiente, ou forneça a chave da ElevenLabs."
  fi
fi

log "pronto (video-use em $VIDEO_USE_DIR, python em $VENV)"
