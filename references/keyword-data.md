# Keyword data for `plan.py`

`plan.py` has no network code and never looks anything up. Every number in a
plan was imported from a file, or it is unknown. You bring the data; the script
merges it, scores it and groups it into topics.

## The rules

- Never type in, estimate or round a number. Import only values that are in a
  tool result or an export the user gave you.
- Unknown stays unknown. `list` shows it as `null`; `plan` sets
  `volume_known` or `difficulty_known` to `false` and adds a `note` counting the
  keywords without search volume. Say "unknown" to the user, not 0.
- A keyword with unknown volume is still scored: demand is set to a neutral 0.4
  out of 1, and unknown difficulty becomes a guess from the length of the
  keyword. Tell the user that such a score is assumed, not measured.
- A lookup that costs money needs the price told to the user and their yes
  first, each time. If the price is not known before the call, say so and ask.

## Where the numbers can come from

1. **A keyword tool or connector your client already has**, for example one for
   Semrush, Ahrefs, DataForSEO or Google Search Console. The seed keywords you
   send go to that provider, so tell the user which one you are calling. Save
   the result to a file unchanged and import it.
2. **An export the user downloads** from Semrush, Ahrefs or Search Console and
   puts in the project folder.
3. **No data.** A list of keywords, or `python plan.py add`. Demand is then
   unknown; say so plainly.

If none of these is available, do not invent a source. Plan from the questions
in `python signals.py questions 15` and mark every volume as unknown.

## Importing, by format

```
python plan.py import <file> [source]
```

`source` is a label stored with each keyword, such as `semrush`. Leave it out
and the file name is used. The command prints
`{"added": n, "updated": n, "total": n}`. A file over 20 MB is refused.

### JSON from a keyword tool (DataForSEO format)

```
python plan.py import keywords.json dataforseo
```

The whole file is searched, at any depth, for objects that have a text
`keyword`. These fields are read when present:

| Value | Read from |
|---|---|
| volume | `keyword_info.search_volume`, or `search_volume` beside the keyword |
| difficulty | `keyword_properties.keyword_difficulty`, or `keyword_difficulty` beside the keyword |
| cost per click | `keyword_info.cpc`, or `cpc` beside the keyword |
| intent | `search_intent_info.main_intent`, or `keyword_intent.label` |

An item whose data sits inside `keyword_data` is read the same way. A value of
`null` is stored as unknown.

### Any other JSON

Write the rows yourself, using only values that are in the result, and leave
out a field you do not have:

```
[{"keyword": "invoice reminder email", "volume": 1900, "difficulty": 34, "cpc": 2.15, "intent": "commercial"}]
```

### CSV export (Semrush, Ahrefs, Search Console)

```
python plan.py import export.csv semrush
```

The first line must be the header row. Columns may be separated by commas,
semicolons or tabs. Column names are matched without regard to case; other
columns are ignored.

| Value | Column names that are read |
|---|---|
| keyword | Keyword, Keywords, Query, Search term, Top queries, Term |
| volume | Volume, Search Volume, Avg. monthly searches, SV |
| difficulty | KD, KD %, Keyword Difficulty, Difficulty, SEO Difficulty |
| cost per click | CPC, CPC (USD), Avg. CPC |
| intent | Intent, Intents |

Numbers written as `1,200`, `1.2K`, `34%` or `$2.50` are read. A Search Console
export has clicks and impressions, not search volume: its keywords import, and
their volume stays unknown.

Header cells may be in quotes, and both UTF-8 and UTF-16 exports are read (a
spreadsheet's "Unicode text" export is UTF-16).

After every import, run `python plan.py list 5` and check that the rows are
real keywords with the numbers you expect. If an import went wrong, undo it
with `python plan.py remove --source <name>` (the name is the label you gave at
import, or the file name), or delete one keyword with
`python plan.py remove <id or keyword>`.

### One keyword per line

```
python plan.py import keywords.txt
python plan.py add "keyword one" "keyword two"
```

A plain text file with no header line; a header would be stored as a keyword.
Volume, difficulty and intent are unknown.

## What import does with the rows

- A keyword is lower-cased and its spaces are collapsed. It must be 2 to 120
  characters; a line containing `<`, `>`, `{`, `}`, `[`, `]` or a backslash is
  skipped.
- Rows merge by keyword. A later import fills in or replaces a number, and a
  known number is never replaced by an unknown one, so volume, difficulty and
  intent can come from separate files.
- A difficulty outside 0 to 100 and a negative volume are stored as unknown.
- Intent is kept when it is transactional, commercial, informational or
  navigational. When it is missing, `plan` infers it from the words of the
  keyword and reports `intent_known: false`.

## A sensible pass

1. Seeds: three to five phrases from `intent.strong` in `aether.json` and from
   `python signals.py questions 15`.
2. Get keyword ideas for the seeds from whichever source the user has. Import.
3. `python plan.py list 200`, keep the relevant keywords, then get difficulty
   and intent for those if the source offers them. Import again.
4. `python plan.py plan 10`.
