"""Prepara a pasta de trabalho do HyperFrames a partir do corte do Video Use.

Pega o vídeo já cortado e o EDL, e escreve no formato que a skill
/talking-head-recut do HyperFrames espera — sem precisar transcrever de novo:

  <work_dir>/metadata.json             duração / largura / altura / fps do corte
  <work_dir>/transcript.json           [{text, start, end}] na linha do tempo DO CORTE
  <work_dir>/public/input-video.mp4    corte reencodado com keyframe a cada frame-segundo
                                       (o renderer congela em vídeos com GOP esparso)

Os tempos das palavras são remapeados com a regra 5 do Video Use:
    tempo_saída = palavra.start - trecho.start + deslocamento_do_trecho

Uso:
    python prepare_hyperframes.py --edit-dir <edit> --cut <cut.mp4> --work-dir <hf_dir>
"""

from __future__ import annotations

import argparse
import json
import subprocess
from fractions import Fraction
from pathlib import Path


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    st = data["streams"][0]
    fps = float(Fraction(st["r_frame_rate"]))
    return {"duration": float(data["format"]["duration"]), "width": int(st["width"]),
            "height": int(st["height"]), "fps": round(fps, 3), "r_frame_rate": st["r_frame_rate"]}


def remap_words(edl: dict, edit_dir: Path, duration: float) -> list[dict]:
    cache: dict[str, list[dict]] = {}
    out: list[dict] = []
    offset = 0.0
    for r in edl["ranges"]:
        src = r["source"]
        if src not in cache:
            data = json.loads((edit_dir / "transcripts" / f"{src}.json").read_text())
            cache[src] = [w for w in data.get("words", []) if w.get("type", "word") == "word"]
        s, e = float(r["start"]), float(r["end"])
        for w in cache[src]:
            mid = (w["start"] + w.get("end", w["start"])) / 2
            if s <= mid <= e:
                ws = max(w["start"], s) - s + offset
                we = min(w.get("end", w["start"]), e) - s + offset
                out.append({"text": w["text"].strip(), "start": round(ws, 3),
                            "end": round(min(we, duration), 3)})
        offset += e - s
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edit-dir", type=Path, required=True)
    ap.add_argument("--cut", type=Path, required=True, help="Vídeo cortado pelo Video Use")
    ap.add_argument("--work-dir", type=Path, required=True)
    args = ap.parse_args()

    edit_dir, cut, work = args.edit_dir.resolve(), args.cut.resolve(), args.work_dir.resolve()
    (work / "public").mkdir(parents=True, exist_ok=True)
    edl = json.loads((edit_dir / "edl.json").read_text())

    meta = probe(cut)
    (work / "metadata.json").write_text(json.dumps(meta, indent=2))

    words = remap_words(edl, edit_dir, meta["duration"])
    (work / "transcript.json").write_text(json.dumps(words, ensure_ascii=False, indent=2))

    gop = str(max(1, round(meta["fps"])))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(cut), "-c:v", "libx264", "-crf", "18", "-g", gop,
         "-keyint_min", gop, "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         "-c:a", "aac", "-b:a", "192k", str(work / "public" / "input-video.mp4")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    print(f"HyperFrames pronto em {work}")
    print(f"  {meta['width']}x{meta['height']} @ {meta['fps']} fps, {meta['duration']:.2f}s, "
          f"{len(words)} palavras no transcript")


if __name__ == "__main__":
    main()
