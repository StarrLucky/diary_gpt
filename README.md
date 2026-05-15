# diary-gpt

**Private diary backed by a Custom GPT that acts as your therapist, with automatic mirror to an Obsidian-friendly GitHub vault.**

Speak (or type) into ChatGPT → the GPT pulls similar past entries, analyses you, then saves your entry with a summary and structured tags → a sync container mirrors each entry as a `.md` file into a private GitHub repo you can open in Obsidian.

```
You ──speak/type──► ChatGPT Custom GPT
                          │
                          │  HTTPS over ngrok
                          ▼
                   FastAPI (your server)
                          │
                          ▼
                       SQLite
                          │
                          │  every 60s
                          ▼
                  diary-sync container
                          │
                          ▼
              GitHub: yourname/diary-vault
                          │
                          ▼
                  Obsidian / git clone
```

## Why this exists

- **Notion-style apps moderate your content.** If you write about sex, anger, or anything raw — they can refuse it. Your diary should be unmoderated.
- **ChatGPT alone forgets you.** Without a backend, every session starts cold. With this, the GPT calls `/stats`, filters by tag, reads only relevant past entries, and answers with continuity.
- **You stay in control.** All data lives on your hardware (or your VPS). The GitHub mirror is **your** private repo. No third party reads the raw text — only OpenAI sees the messages you choose to send, and only when you send them.

## Quick start

See [diary_api/README.md](diary_api/README.md) for the full step-by-step.

```bash
git clone git@github.com:YOUR-USERNAME/diary-gpt.git
cd diary-gpt/diary_api
cp .env.example .env
# fill in DIARY_API_KEY, NGROK_AUTHTOKEN, NGROK_DOMAIN,
#         GITHUB_DIARY_TOKEN, VAULT_REPO
docker compose up -d
```

Then in [chatgpt.com](https://chatgpt.com) → **Explore GPTs** → **Create** → **Configure**:
1. Paste the Instructions block from [diary_api/README.md](diary_api/README.md).
2. Add an Action → paste [diary_api/openapi.yaml](diary_api/openapi.yaml) → authentication = API Key, header `X-API-Key`, value = your `DIARY_API_KEY`.
3. Publish as **Only me**.

## What you need

| Thing | Why | Cost |
|---|---|---|
| ChatGPT Plus | Custom GPTs are a Plus feature | $20/mo |
| ngrok account | Public HTTPS tunnel to your server | free tier works |
| A small server | Where the API and sync run | Raspberry Pi / $5 VPS / spare laptop |
| GitHub account + private repo | For the Obsidian vault mirror | free |

That's the whole list.

## Variants

- **Hardware:** Raspberry Pi at home, any VPS (Hetzner / DigitalOcean / Oracle Free), or your own laptop running 24/7.
- **No GitHub mirror:** drop the `diary-sync` service from `docker-compose.yml` if you only care about the GPT + SQLite. The vault is optional.
- **No SQLite (Obsidian-only):** if you'd rather not run a database at all, see [diary_api/README.md](diary_api/README.md) — section "Alternative: Obsidian-only (no database)".

## Documentation

- [diary_api/README.md](diary_api/README.md) — full architecture, install steps, API reference, ChatGPT GPT instructions, database operations, troubleshooting.

## License

MIT. Take it, fork it, adapt it.
