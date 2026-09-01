# NINA

A realtime voice AI assistant built on [LiveKit Agents](https://docs.livekit.io/agents/).
You talk, she answers out loud, and she can look things up and remember what you
tell her between conversations.

Speech-to-speech through Gemini Live by default, with a swappable STT → LLM → TTS
pipeline as an alternative. Configuration is validated up front, tools fail into
a sentence instead of a stack trace, and the whole thing is covered by a test
suite that needs no network and no API keys.

---

## Quick start

```bash
git clone https://github.com/geek007git/NINA.git
cd NINA

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[dev]"

cp .env.example .env               # Windows: copy .env.example .env
# fill in LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, GOOGLE_API_KEY

nina doctor                        # validates config and dependencies
nina console                       # talk to NINA in your terminal
```

`nina console` needs no LiveKit room and no frontend — it is the fastest way to
hear whether she works. When you are ready for a real client, run `nina dev` and
connect with the [LiveKit Agents Playground](https://agents-playground.livekit.io/).

You will need:

| What | Where |
| --- | --- |
| LiveKit project URL and API keys | <https://cloud.livekit.io> (free tier is fine) |
| Google Gemini API key | <https://aistudio.google.com/apikey> |

---

## Commands

```
nina dev                 Run a worker with hot reload
nina console             Talk to NINA in the terminal, no room needed
nina start               Run a worker in production mode
nina download-files      Pre-download model files (use this in your Dockerfile)

nina doctor              Validate configuration and dependencies
nina prompt              Print the generated system prompt
nina memory list         Show saved memories
nina memory forget KEY   Delete one memory
nina memory clear        Delete all memories
```

`python agent.py <command>` still works and does the same thing, so existing
muscle memory and any scripts you already had keep working.

**`nina doctor` is the first thing to run when something is wrong.** It checks
every dependency and every setting without connecting to anything, and prints
your resolved configuration with secrets redacted.

---

## What she can do

Tools are enabled with `NINA_TOOLS` and are described to the model only when they
are actually turned on, so she never offers a capability she does not have.

| Tool | What it does | Needs |
| --- | --- | --- |
| `clock` | Current date and time in any timezone. Understands `IST`, `Asia/Kolkata`, and `Chennai` alike. | nothing |
| `weather` | Current conditions and today's range for any place, via [Open-Meteo](https://open-meteo.com/). | nothing |
| `search` | Web lookup for facts and recent events. | nothing (DuckDuckGo) or a Tavily key |
| `memory` | `remember`, `recall`, `forget`, `list` — persists to a JSON file across sessions. | nothing |

The DuckDuckGo backend is keyless but only answers entity and definition queries.
For real coverage, set `NINA_SEARCH_PROVIDER=tavily` and a `TAVILY_API_KEY`.

---

## Configuration

Everything is environment variables, read from the process environment or a local
`.env`. `.env.example` documents every one; the essentials:

| Variable | Default | Notes |
| --- | --- | --- |
| `LIVEKIT_URL` | — | **Required.** Must start with `ws://` or `wss://` |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | — | **Required** |
| `GOOGLE_API_KEY` | — | **Required** for the default provider |
| `NINA_PROVIDER` | `google_realtime` | or `pipeline` |
| `NINA_REALTIME_MODEL` | `gemini-2.0-flash-exp` | Gemini Live model |
| `NINA_VOICE` | `Puck` | Gemini Live voice |
| `NINA_TEMPERATURE` | `0.8` | 0.0 – 2.0 |
| `NINA_TOOLS` | all four | Comma-separated, or `none` |
| `NINA_SEARCH_PROVIDER` | `duckduckgo` | `duckduckgo`, `tavily`, `none` |
| `NINA_USER_NAME` | `Shan` | Who she is talking to |
| `NINA_INTERESTS` | (see `.env.example`) | Comma-separated |
| `NINA_EXTRA_INSTRUCTIONS` | — | Appended to the system prompt |
| `NINA_MEMORY_PATH` | `.nina/memory.json` | Where memories are stored |
| `NINA_NOISE_CANCELLATION` | `bvc` | `bvc`, `bvc_telephony`, `none` |
| `NINA_LOG_LEVEL` / `NINA_LOG_FORMAT` | `info` / `text` | Use `json` in containers |

Bad configuration fails at startup with **every** problem listed at once, not one
per restart:

```
Invalid NINA configuration:
  - LIVEKIT_URL='http://x' must start with ws:// or wss://
  - NINA_TEMPERATURE=9.0 is outside the allowed range [0.0, 2.0]
  - NINA_TOOLS contains unknown entries: teleprt (allowed: clock, weather, search, memory)
```

### Choosing a provider

**`google_realtime`** (default) — one speech-to-speech model. Lowest latency,
most natural interruptions and turn-taking, fewest moving parts.

**`pipeline`** — separate STT, LLM and TTS stages through LiveKit's inference
gateway. Higher latency, but each stage is swappable and you get a readable
transcript at every step. Set `NINA_PROVIDER=pipeline` plus `NINA_STT_MODEL`,
`NINA_LLM_MODEL` and `NINA_TTS_MODEL`.

---

## Architecture

```
agent.py                  thin launcher, keeps `python agent.py dev` working
src/nina/
  __main__.py             CLI: doctor, prompt, memory; delegates the rest to LiveKit
  config.py               env → validated, immutable Settings
  persona.py              builds the system prompt and greeting from config
  providers.py            picks and builds the model stack
  agent.py                the Agent, and the tool registration/guarding
  runtime.py              worker and session lifecycle
  memory.py               atomic, size-capped JSON memory store
  http_client.py          async HTTP seam the tools depend on
  compat.py               all version-sensitive LiveKit imports, in one place
  tools/                  clock, weather, websearch — plain async functions
```

Two rules hold the layout together:

**LiveKit is only imported in three files.** `compat.py`, `providers.py` and
`runtime.py` (plus `agent.py`, lazily). Everything else — config, persona,
memory, tools — is plain Python, so it runs in tests without the agent framework
installed and without a network.

**Tools do not know they are tools.** `tools/weather.py` is an async function
that takes a place and an HTTP client and returns a sentence. `agent.py` wraps it
in `@function_tool` and a guard. That is why the tools are cheap to test and why
swapping frameworks would not touch them.

### Failure handling

A tool that raises kills the conversation. Every tool here is wrapped so that
failures become something the model can read out instead:

- `ToolError` → spoken as-is (*"I could not find a place called Atlantis"*)
- anything unexpected → logged with a traceback, spoken as a generic apology
- a corrupt memory file → quarantined to `.corrupt`, store starts empty, agent still boots
- a missing noise-cancellation plugin → warned about, session continues without it

---

## Development

```bash
pip install -e ".[dev]"

pytest                  # 132 tests, no network, no API keys
ruff check .            # lint
ruff format .           # format
mypy                    # strict type checking
```

Or all of it at once, if you have `make`:

```bash
make check
```

The test suite replaces the HTTP layer with a fake and injects the clock, so it
is fast and deterministic. Nothing in it reads your `.env` or touches the
network.

---

## Deployment

```bash
docker build -t nina .
docker run --env-file .env nina
```

The image runs as a non-root user, pre-downloads model files at build time so
cold starts are fast, and defaults to `NINA_LOG_FORMAT=json` for log shippers.
Mount a volume at `/app/.nina` if you want memories to survive a restart.

---

## Notes on the rewrite

The original version was a single 40-line `agent.py` plus two prompt constants.
The behavioural fixes worth knowing about:

- **The greeting prompt was a sample answer.** `AGENT_RESPONSE` contained an
  invented heart-rate reading and VO₂ max projection, and was passed as
  `instructions` to both the model and `generate_reply` — so NINA was being told
  to open every conversation by reciting fake biometrics. It is now an
  instruction to greet, and the system prompt explicitly forbids inventing
  sensor data.
- **Voice output rules.** Nothing previously stopped the model emitting markdown
  and emoji, which a TTS engine reads aloud character by character.
- **`.env` was committed** early in the history. The keys in it should be
  considered compromised and rotated — deleting the file does not remove it from
  the git history.
- **`.gitignore` was a Play framework template** and did not ignore
  `__pycache__`, virtualenvs, or tooling caches.

---

## License

MIT — see [LICENSE](LICENSE).
