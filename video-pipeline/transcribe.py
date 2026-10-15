"""Transcrição palavra a palavra no formato Scribe (ElevenLabs) usado pelo Video Use.

Escolhe o motor sozinho:
  1. ElevenLabs Scribe (motor nativo do Video Use), se ELEVENLABS_API_KEY existir
     no ambiente ou em ~/Developer/video-use/.env. É verbatim: mantém "é...", "ahn",
     falsos começos — o melhor sinal para cortar repetições.
  2. faster-whisper local (modelo multilíngue, português), caso contrário. O prompt
     inicial cheio de hesitações faz o Whisper transcrevê-las em vez de limpá-las.

Saída: <edit_dir>/transcripts/<nome>.json com {"language_code", "words": [...]},
onde cada item tem type ("word" | "spacing"), text, start, end, speaker_id —
exatamente o que pack_transcripts.py e render.py do Video Use leem.

Uso:
    python transcribe.py <video> --edit-dir <dir> [--language pt] [--engine auto|scribe|whisper]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

VIDEO_USE_DIR = Path(os.environ.get("VIDEO_USE_DIR", Path.home() / "Developer" / "video-use"))

# Hesitações em português no prompt: o Whisper imita o estilo do prompt, então ele
# passa a escrever as hesitações em vez de apagá-las.
WHISPER_PROMPT = (
    "Ahn, então, é... hum, eu, eu vou, eu vou falar sobre isso. Hã, tipo, né? "
    "Ééé, deixa eu, deixa eu começar de novo."
)


def scribe_key() -> str | None:
    env_file = VIDEO_USE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "ELEVENLABS_API_KEY" and v.strip():
                return v.strip().strip('"').strip("'")
    return os.environ.get("ELEVENLABS_API_KEY") or None


def extract_audio(video: Path, dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-map", "0:a:0", "-vn", "-ac", "1",
         "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def transcribe_scribe(video: Path, edit_dir: Path, language: str | None) -> None:
    # Delega ao helper do próprio Video Use (ele já grava em transcripts/ e faz cache).
    cmd = [sys.executable, str(VIDEO_USE_DIR / "helpers" / "transcribe.py"), str(video),
           "--edit-dir", str(edit_dir)]
    if language:
        cmd += ["--language", language]
    subprocess.run(cmd, check=True)


def transcribe_whisper(video: Path, out_path: Path, language: str | None, model_name: str) -> dict:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        extract_audio(video, wav)
        segments, info = model.transcribe(
            str(wav),
            language=language,
            word_timestamps=True,
            initial_prompt=WHISPER_PROMPT,
            condition_on_previous_text=False,  # evita alucinação em loop em vídeos longos
            vad_filter=False,  # o corte de silêncio é nosso; não deixe o VAD engolir hesitações
        )
        words: list[dict] = []
        prev_end: float | None = None
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if not text:
                    continue
                if prev_end is not None and w.start > prev_end:
                    words.append({"type": "spacing", "text": " ", "start": prev_end,
                                  "end": round(w.start, 3), "speaker_id": "speaker_0"})
                words.append({"type": "word", "text": text, "start": round(w.start, 3),
                              "end": round(w.end, 3), "speaker_id": "speaker_0",
                              "logprob": round(w.probability, 3)})
                prev_end = round(w.end, 3)
    payload = {
        "language_code": info.language,
        "engine": f"faster-whisper/{model_name}",
        "text": " ".join(w["text"] for w in words if w["type"] == "word"),
        "words": words,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, required=True)
    ap.add_argument("--language", default="pt", help="Código ISO; padrão pt. Use '' para autodetectar.")
    ap.add_argument("--engine", choices=["auto", "scribe", "whisper"], default="auto")
    ap.add_argument("--whisper-model", default=os.environ.get("WHISPER_MODEL", "medium"),
                    help="Modelo faster-whisper multilíngue (small, medium, large-v3). Padrão medium.")
    args = ap.parse_args()

    video = args.video.resolve()
    edit_dir = args.edit_dir.resolve()
    out_path = edit_dir / "transcripts" / f"{video.stem}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        print(f"cache: {out_path}")
        return

    language = args.language or None
    engine = args.engine
    if engine == "auto":
        engine = "scribe" if scribe_key() else "whisper"
    print(f"transcrevendo {video.name} com {engine}…", flush=True)
    if engine == "scribe":
        transcribe_scribe(video, edit_dir, language)
    else:
        payload = transcribe_whisper(video, out_path, language, args.whisper_model)
        n = sum(1 for w in payload["words"] if w["type"] == "word")
        print(f"  {n} palavras → {out_path}")


if __name__ == "__main__":
    main()
