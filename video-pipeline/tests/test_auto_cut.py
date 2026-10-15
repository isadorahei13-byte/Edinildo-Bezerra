"""Testes do auto_cut: python -m unittest discover -s video-pipeline/tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auto_cut as ac  # noqa: E402


def words_from(spec):
    """spec: lista de (texto, início, fim)."""
    return [ac.Word(i, t, s, e) for i, (t, s, e) in enumerate(spec)]


def kept(words):
    return " ".join(w.text for w in words if w.keep)


def timeline(text, start=0.0, step=0.3, gaps=None):
    """Palavras de 0.25s espaçadas por `step`; gaps={índice: pausa_extra}."""
    out, t = [], start
    for i, tok in enumerate(text.split()):
        t += (gaps or {}).get(i, 0.0)
        out.append((tok, round(t, 3), round(t + 0.25, 3)))
        t += step
    return out


class Fillers(unittest.TestCase):
    def test_removes_hesitations_keeps_real_words(self):
        w = words_from(timeline("ahn eu acho hum que é um bom dia hã"))
        ac.remove_fillers(w)
        self.assertEqual(kept(w), "eu acho que é um bom dia")

    def test_dragged_vowel(self):
        w = words_from([("Então", 0, 0.4), ("é...", 0.5, 1.3), ("vamos", 1.4, 1.8)])
        ac.remove_fillers(w)
        self.assertEqual(kept(w), "Então vamos")


class Repeats(unittest.TestCase):
    def test_stutter(self):
        w = words_from(timeline("eu eu vou falar"))
        ac.remove_ngram_repeats(w)
        self.assertEqual(kept(w), "eu vou falar")

    def test_ngram_restart_keeps_last(self):
        w = words_from(timeline("eu vou falar eu vou falar sobre saúde"))
        ac.remove_ngram_repeats(w)
        self.assertEqual(kept(w), "eu vou falar sobre saúde")
        self.assertEqual([w.idx for w in w if w.keep][0], 3)  # ficou a 2ª tomada

    def test_emphatic_double_kept(self):
        w = words_from(timeline("isso é muito muito importante"))
        ac.remove_ngram_repeats(w)
        self.assertEqual(kept(w), "isso é muito muito importante")

    def test_false_start_phrase(self):
        w = words_from(timeline("Hoje eu queria Hoje eu queria falar do Outubro Rosa.", gaps={3: 0.8}))
        ac.remove_retakes(w)
        self.assertEqual(kept(w), "Hoje eu queria falar do Outubro Rosa.")

    def test_same_sentence_twice_keeps_last(self):
        w = words_from(timeline("O exame salva vidas. O exame salva muitas vidas.", gaps={4: 1.0}))
        ac.remove_retakes(w)
        self.assertEqual(kept(w), "O exame salva muitas vidas.")

    def test_parallel_structure_not_a_retake(self):
        text = "Não é sobre dinheiro. Não é sobre tempo. É sobre cuidado."
        w = words_from(timeline(text, gaps={4: 0.6, 8: 0.6}))
        ac.remove_retakes(w)
        self.assertEqual(kept(w), text)


class Ranges(unittest.TestCase):
    def test_long_pause_is_cut_and_padded(self):
        w = words_from([("Olá", 1.0, 1.4), ("pessoal", 1.45, 1.9), ("tudo", 4.0, 4.3), ("bem", 4.35, 4.6)])
        res = ac.build_ranges(w, "x", max_pause=0.35, pad_before=0.06, pad_after=0.1, duration=6.0)
        self.assertEqual([(s, e) for s, e, _ in res.ranges], [(0.94, 2.0), (3.94, 4.7)])

    def test_padding_never_enters_removed_word(self):
        w = words_from([("eu", 0.5, 0.7), ("ahn", 0.72, 1.2), ("acho", 1.22, 1.5)])
        ac.remove_fillers(w)
        res = ac.build_ranges(w, "x", 0.35, 0.06, 0.1, 3.0)
        self.assertEqual([(s, e) for s, e, _ in res.ranges], [(0.44, 0.72), (1.2, 1.6)])
        self.assertEqual(res.removals[0].text, "ahn")


if __name__ == "__main__":
    unittest.main()
