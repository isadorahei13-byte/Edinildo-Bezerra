# Edinildo Bezerra — edição de vídeo

Além das páginas HTML (agenda de gravações), este repositório edita os vídeos enviados
no chat em duas etapas, sempre nesta ordem:

1. **Video Use** ([browser-use/video-use](https://github.com/browser-use/video-use)) —
   corta silêncios, hesitações e repetições.
2. **HyperFrames** ([heygen-com/hyperframes](https://github.com/heygen-com/hyperframes)) —
   em cima do corte, adiciona animações e visualizações ligadas ao que está sendo dito.

O hook `SessionStart` roda `video-pipeline/setup.sh`, que instala o Video Use em
`~/Developer/video-use` (skill `video-use`), as skills do HyperFrames
(`talking-head-recut`, `hyperframes-*`), o Chrome headless de render e um venv Python
em `~/.venvs/video-pipeline`. Se algo faltar, rode o script de novo.

## Quando chegar um vídeo

Leia `video-pipeline/preferencias.md` primeiro.

### Etapa 1 — corte (Video Use)

```bash
video-pipeline/editar.sh <caminho-do-video> <nome-do-projeto>
```

Faz transcrição → `auto_cut.py` (EDL) → `render.py` do Video Use → `prepare_hyperframes.py`.
Tudo vai para `videos/<nome>/` (fora do Git):

- `edit/cut.mp4` — vídeo cortado
- `edit/cut_report.md` — tudo o que foi removido, com o tempo de origem
- `edit/edl.json` — decisões de corte (formato EDL do Video Use)
- `hyperframes/` — pasta pronta para a etapa 2: `metadata.json`, `transcript.json`
  (já na linha do tempo do corte) e `public/input-video.mp4`

O corte de silêncios e repetições já está autorizado: **não** peça confirmação da
estratégia de corte (isso substitui a regra 11 do Video Use para este projeto). Depois do
render, faça a autoavaliação da skill `video-use` (timeline_view nas fronteiras de corte,
`ffprobe`, loudness) e mostre um resumo do `cut_report.md`. Se a pessoa quiser algo de
volta, edite `edit/edl.json`, rode de novo o `render.py` e o `prepare_hyperframes.py`.

Ajustes úteis do `auto_cut.py` (passe depois do nome do projeto no `editar.sh`):
`--max-pause 0.25` (mais ritmo), `--keep-repetitions`, `--keep-fillers`.

### Etapa 2 — animações (HyperFrames)

Siga a skill **`talking-head-recut`** a partir do passo 5, usando
`videos/<nome>/hyperframes/` como `WORK_DIR` (os passos 2–4 — pasta, metadados, áudio,
transcrição — já foram feitos pelo `prepare_hyperframes.py`; o vídeo já está em
`public/input-video.mp4` com keyframes densos).

- As perguntas visuais do passo 7 (proporção, layout, estilo, nº de cards) só na primeira
  vez; grave as respostas em `video-pipeline/preferencias.md` e reutilize depois.
- Os cards nascem do que é dito: números viram contadores/gráficos, listas viram
  revelações em sequência, frases fortes viram citações, termos novos viram
  lower-thirds. Sincronize a chegada de cada animação com a palavra-chave no
  `transcript.json`.
- Texto em português do Brasil, com acentuação; confira que a fonte carregou.
- `npx hyperframes lint` sem erros, depois render:
  `cd videos/<nome>/hyperframes/public && npx hyperframes render . -o ../../final.mp4`
- Confira o resultado (`ffprobe` + alguns frames) antes de entregar.

### Entrega

Envie `videos/<nome>/final.mp4` com `SendUserFile` (e o `cut.mp4` se pedirem só o
corte). Vídeos nunca vão para o Git; mudanças nos scripts e em `preferencias.md`, sim.

## Transcrição

`video-pipeline/transcribe.py` usa o ElevenLabs Scribe (motor do Video Use, verbatim)
quando há `ELEVENLABS_API_KEY` no ambiente ou em `~/Developer/video-use/.env`; senão,
faster-whisper local (modelo `medium`, português). O Whisper baixa o modelo do
`huggingface.co`, e o Scribe usa `api.elevenlabs.io` — um dos dois precisa estar liberado
na rede do ambiente. Para vídeos longos, `WHISPER_MODEL=small` é mais rápido.

## Testes

```bash
~/.venvs/video-pipeline/bin/python -m unittest discover -s video-pipeline/tests
```
