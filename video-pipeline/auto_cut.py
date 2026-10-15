"""Gera o edl.json do Video Use cortando silêncios, hesitações e repetições.

Lê <edit_dir>/transcripts/<nome>.json (formato Scribe, palavra a palavra) e decide:

  1. Hesitações   — "ahn", "hã", "hum", "éé", "é" arrastado (>= 0.6s)…
  2. Gaguejos     — n-gramas repetidos em sequência: "eu eu vou", "eu vou eu vou falar"
                    → fica a última ocorrência.
  3. Retomadas    — frase interrompida e recomeçada ("Hoje eu queria… Hoje eu queria
                    falar sobre…") ou a mesma frase dita duas vezes → fica a última tomada.
  4. Silêncios    — pausas maiores que --max-pause viram corte, com folga
                    (--pad-before/--pad-after) dentro da janela de 30–200ms do Video Use.

Todo corte cai em fronteira de palavra (regra 6 do Video Use) e a folga nunca invade
uma palavra vizinha. O resultado é um EDL que o render.py do Video Use renderiza, e um
cut_report.md listando tudo o que saiu, com o tempo de origem, para revisão.

Uso:
    python auto_cut.py --edit-dir <dir> <video> [<video> ...]
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

FILLER_RE = re.compile(
    r"^(a+h+n*|a{2,}h*|h+a+n*|a+n+h*|h*u+m{2,}|h+u+m+|h+m+|e+h+|e{2,}h*|u+h+|u{2,}|o{3,})$"
)
SINGLE_VOWEL_RE = re.compile(r"^[aeiou]$")
# Repetições de uma palavra que costumam ser ênfase, não gagueira.
EMPHATIC_DOUBLES = {"nao", "sim", "muito", "bem", "ja", "vai", "isso", "pronto", "calma"}
SENTENCE_END_RE = re.compile(r"[.!?…]$")


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t)


@dataclass
class Word:
    idx: int
    text: str
    start: float
    end: float
    n: str = ""
    keep: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        self.n = norm(self.text)


@dataclass
class Removal:
    start: float
    end: float
    kind: str
    text: str


@dataclass
class Result:
    ranges: list[tuple[float, float, str]] = field(default_factory=list)
    removals: list[Removal] = field(default_factory=list)


def load_words(path: Path) -> list[Word]:
    data = json.loads(path.read_text())
    out: list[Word] = []
    for w in data.get("words", []):
        if w.get("type", "word") != "word" or w.get("start") is None:
            continue
        text = (w.get("text") or "").strip()
        if not text:
            continue
        out.append(Word(len(out), text, float(w["start"]), float(w.get("end", w["start"]))))
    return out


def mark(words: list[Word], reason: str) -> None:
    for w in words:
        if w.keep:
            w.keep = False
            w.reason = reason


def remove_fillers(words: list[Word]) -> None:
    for w in words:
        if not w.n:
            continue
        if FILLER_RE.match(w.n):
            mark([w], "hesitação")
        elif SINGLE_VOWEL_RE.match(w.n) and w.end - w.start >= 0.6:
            mark([w], "hesitação (vogal arrastada)")


def remove_ngram_repeats(words: list[Word], max_n: int = 8, max_gap: float = 2.0) -> None:
    """Gaguejo e recomeço colado: seq[i:i+n] == seq[i+n:i+2n] → remove o primeiro."""
    changed = True
    while changed:
        changed = False
        seq = [w for w in words if w.keep and w.n]
        for n in range(min(max_n, len(seq) // 2), 0, -1):
            for i in range(len(seq) - 2 * n + 1):
                a, b = seq[i:i + n], seq[i + n:i + 2 * n]
                if [w.n for w in a] != [w.n for w in b]:
                    continue
                if b[0].start - a[-1].end > max_gap:
                    continue
                if n == 1 and a[0].n in EMPHATIC_DOUBLES:
                    continue
                mark(a, "repetição" if n > 1 else "gaguejo")
                changed = True
                break
            if changed:
                break


def phrases_of(words: list[Word], gap: float) -> list[list[Word]]:
    phrases: list[list[Word]] = []
    cur: list[Word] = []
    for w in (w for w in words if w.keep and w.n):
        if cur and (w.start - cur[-1].end >= gap or SENTENCE_END_RE.search(cur[-1].text)):
            phrases.append(cur)
            cur = []
        cur.append(w)
    if cur:
        phrases.append(cur)
    return phrases


def remove_retakes(words: list[Word], phrase_gap: float = 0.45, lookahead: int = 2,
                   max_distance: float = 8.0) -> None:
    """Frase abandonada e recomeçada, ou dita duas vezes → mantém a última tomada."""
    changed = True
    while changed:
        changed = False
        ph = phrases_of(words, phrase_gap)
        for i, a in enumerate(ph):
            at = [w.n for w in a]
            for b in ph[i + 1:i + 1 + lookahead]:
                if b[0].start - a[-1].end > max_distance:
                    break
                bt = [w.n for w in b]
                # A é (quase) o começo de B: a pessoa parou e começou de novo.
                k = min(3, len(at))
                prefix = bt[:len(at) + 2]
                contained = difflib.SequenceMatcher(None, at, prefix).find_longest_match(
                    0, len(at), 0, len(prefix)).size
                false_start = len(at) >= 2 and bt[:k] == at[:k] and contained / len(at) >= 0.8
                # Quase toda A reaparece em B, na ordem: a mesma frase gravada de novo
                # (talvez corrigida). Trocar a palavra principal ("Não é sobre dinheiro.
                # Não é sobre tempo.") não conta — é paralelismo, não retomada.
                covered = sum(m.size for m in difflib.SequenceMatcher(None, at, bt).get_matching_blocks())
                same = len(at) >= 3 and covered / len(at) >= 0.85
                if false_start or same:
                    mark(a, "frase repetida (retomada)")
                    changed = True
                    break
            if changed:
                break


def build_ranges(words: list[Word], source: str, max_pause: float, pad_before: float,
                 pad_after: float, duration: float | None) -> Result:
    res = Result()
    for w in words:
        if not w.keep:
            res.removals.append(Removal(w.start, w.end, w.reason, w.text))

    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if not w.keep:
            if cur:
                groups.append(cur)
                cur = []
            continue
        if cur and w.start - cur[-1].end > max_pause:
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)

    for g in groups:
        first, last = g[0], g[-1]
        prev_end = words[first.idx - 1].end if first.idx > 0 else 0.0
        next_start = words[last.idx + 1].start if last.idx + 1 < len(words) else (duration or last.end + 1)
        start = max(prev_end, first.start - pad_before, 0.0)
        end = min(next_start, last.end + pad_after)
        if duration is not None:
            end = min(end, duration)
        if end > start:
            res.ranges.append((round(start, 3), round(end, 3), " ".join(w.text for w in g)))
    return res


def probe_duration(video: Path) -> float | None:
    import subprocess
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", str(video)],
                             capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception:
        return None


def fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+", type=Path, help="Vídeos de origem, na ordem de montagem")
    ap.add_argument("--edit-dir", type=Path, required=True)
    ap.add_argument("--max-pause", type=float, default=0.35, help="Pausa máxima mantida (s). Padrão 0.35")
    ap.add_argument("--pad-before", type=float, default=0.06, help="Folga antes da 1ª palavra (s)")
    ap.add_argument("--pad-after", type=float, default=0.10, help="Folga depois da última palavra (s)")
    ap.add_argument("--keep-repetitions", action="store_true", help="Só corta silêncios e hesitações")
    ap.add_argument("--keep-fillers", action="store_true", help="Não corta hesitações")
    args = ap.parse_args()

    edit_dir = args.edit_dir.resolve()
    sources: dict[str, str] = {}
    ranges: list[dict] = []
    report: list[str] = ["# Relatório de corte automático", ""]
    total_in = 0.0

    for video in args.videos:
        video = video.resolve()
        stem = video.stem
        words = load_words(edit_dir / "transcripts" / f"{stem}.json")
        duration = probe_duration(video)
        total_in += duration or (words[-1].end if words else 0)
        sources[stem] = str(video)

        if not args.keep_fillers:
            remove_fillers(words)
        if not args.keep_repetitions:
            remove_ngram_repeats(words)
            remove_retakes(words)
        res = build_ranges(words, stem, args.max_pause, args.pad_before, args.pad_after, duration)

        for start, end, text in res.ranges:
            ranges.append({"source": stem, "start": start, "end": end, "beat": "",
                           "quote": text, "reason": "auto_cut"})

        kept = sum(e - s for s, e, _ in res.ranges)
        report += [f"## {stem}", "",
                   f"- Duração original: {fmt(duration or 0)}",
                   f"- Duração após corte: {fmt(kept)}",
                   f"- Trechos mantidos: {len(res.ranges)}",
                   f"- Palavras removidas: {len(res.removals)}", ""]
        if res.removals:
            report += ["| Tempo (origem) | Tipo | Texto |", "|---|---|---|"]
            # agrupa palavras vizinhas com o mesmo motivo numa linha só
            merged: list[Removal] = []
            for r in res.removals:
                if merged and merged[-1].kind == r.kind and r.start - merged[-1].end < 0.6:
                    merged[-1] = Removal(merged[-1].start, r.end, r.kind, merged[-1].text + " " + r.text)
                else:
                    merged.append(r)
            report += [f"| {fmt(r.start)}–{fmt(r.end)} | {r.kind} | {r.text} |" for r in merged]
            report.append("")

    total_out = sum(r["end"] - r["start"] for r in ranges)
    edl = {"version": 1, "sources": sources, "ranges": ranges, "grade": "none",
           "overlays": [], "total_duration_s": round(total_out, 3)}
    (edit_dir / "edl.json").write_text(json.dumps(edl, ensure_ascii=False, indent=2))
    report[1:1] = ["", f"**Total:** {fmt(total_in)} → {fmt(total_out)} "
                   f"({100 * (1 - total_out / total_in) if total_in else 0:.0f}% removido)"]
    (edit_dir / "cut_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"edl.json: {len(ranges)} trechos, {fmt(total_in)} → {fmt(total_out)}")
    print(f"relatório: {edit_dir / 'cut_report.md'}")


if __name__ == "__main__":
    main()
