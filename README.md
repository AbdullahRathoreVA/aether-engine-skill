# Aether Engine skill

Get found by people who are already looking for what you sell. A free skill
for AI agents (Claude Code, Codex CLI, Cursor and any agent that reads
`SKILL.md`) that takes your agent from "who needs this?" to published,
audited SEO pages.

1. **Listen.** Finds public posts on Hacker News, Reddit, StackExchange and
   RSS feeds where people describe the problem your product solves, and ranks
   them by buying intent. After 20 of your approve or reject decisions, a small
   local model learns your taste and reports its own accuracy.
2. **Plan.** Turns keyword data you import (or keywords you type) into a ranked
   page plan, and says plainly when demand was assumed rather than measured.
3. **Publish.** Writes long-tail pages as static HTML with structured data,
   internal links, a sitemap and robots.txt, then audits the files it wrote.
4. **Proofread.** Measures a page or reply draft for filler and vague claims
   before it goes out.

It never posts, uploads or deploys anything for you, and it promises no
ranking. Five standard-library Python scripts: the one that uses the network
reads no files, and the four that read your files have no network code. No API
keys, nothing to install.

| Script | Does |
|---|---|
| `scripts/listen.py` | fetches recent public posts (network only) |
| `scripts/signals.py` | ranks posts, lists questions, holds reply drafts for your approval |
| `scripts/plan.py` | keyword data to a ranked page plan and a writing brief |
| `scripts/site.py` | stores pages, publishes static files, audits them |
| `scripts/proof.py` | measures a draft for filler; writes nothing |

## Install

With the skills CLI:

```bash
npx skills add AbdullahRathoreVA/aether-engine-skill
```

Or copy this folder into your agent's skills directory (for Claude Code:
`~/.claude/skills/aether-engine`). Then tell your agent what you sell and ask:
"Who is asking for this, and which pages should I write first?"

## Run it by hand

Settings live in `aether.json` in your project; the format is in
[references/profile.md](references/profile.md).

```bash
python scripts/listen.py --hn "invoice software" --reddit smallbusiness > posts.json
```

```bash
python scripts/signals.py ingest posts.json
```

```bash
python scripts/signals.py top 10
```

```bash
python scripts/plan.py add "how to monitor a cron job" "cron job failed silently"
```

```bash
python scripts/plan.py plan 10
```

```bash
python scripts/site.py publish
```

```bash
python scripts/site.py audit
```

With no imported keyword data, `plan` still ranks the topics and says so in
its output, for example: "4 of 4 keywords have no search-volume data; their
demand is assumed neutral, not measured." To use real volume and difficulty,
see [references/keyword-data.md](references/keyword-data.md).

## Limits

- Sources are public posts only; no private or logged-in data.
- Topic grouping uses shared words, not search-result overlap.
- The scripts need a shell with Python. In a chat-only client the guidance
  still applies, but nothing is run or measured.
- Publishing writes static files. Hosting, indexing and ranking are up to you
  and the search engines; the audit measures the files, not Google.

The standalone engine this skill grew from is at
<https://github.com/AbdullahRathoreVA/aether-engine>.

## More free skills

| Skill | What it does |
|---|---|
| **Aether Engine** | This one |
| [Aether Listen](https://github.com/AbdullahRathoreVA/aether-listen) | Only the listening half: finds and ranks people who need your product |
| [Agent Team](https://github.com/AbdullahRathoreVA/agent-team) | Plans a task for a team of AI agents and coordinates their handoffs through Git |
| [Secret Scan](https://github.com/AbdullahRathoreVA/secret-scan) | Finds leaked keys in a repository's Git history before you make it public |

## Licence

MIT. See [LICENSE](LICENSE).
