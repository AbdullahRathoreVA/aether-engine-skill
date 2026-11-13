#!/usr/bin/env python3
"""Aether site: store pages, render them with structured data and internal
links, and audit the files that were written. Local only: no network code.
Run it from the project folder.

  python site.py add <page.json> [--replace] [--allow-thin]
  python site.py list | remove <slug> | publish | audit

Pages are rendered at publish time against the whole site, so an old page
gains a link to a new one and no page is left without inbound links.
"""
import html
import json
import re
import sqlite3
import sys
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path.cwd()
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MIN_WORDS = 300
SCHEMA = """CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY, slug TEXT UNIQUE, title TEXT,
 keyword TEXT, cluster TEXT, description TEXT, answer TEXT, body TEXT, faqs TEXT, created REAL,
 updated REAL, published INTEGER DEFAULT 0);"""
ALLOWED = {"p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "b", "i", "code", "pre",
           "blockquote", "table", "thead", "tbody", "tr", "th", "td", "a", "br", "hr"}
DROPPED = {"script", "style", "iframe", "object", "embed", "svg", "math", "template", "noscript", "form", "head", "title"}
CSS = """:root{--bg:#0b0d12;--fg:#e6e9f0;--mut:#9aa4b8;--acc:#ffc857}*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:48px 20px 80px}h1{font-size:2.1rem;line-height:1.25;margin:0 0 8px}
h2{font-size:1.35rem;margin:40px 0 12px;color:#fff}.meta{color:var(--mut);font-size:.9rem;margin-bottom:32px}
ul,ol{padding-left:22px}li{margin:8px 0}code{background:#1b2030;padding:2px 7px;border-radius:5px;font-size:.9em}
table{border-collapse:collapse;width:100%;margin:18px 0}th,td{border:1px solid #242c3f;padding:8px 12px;text-align:left}
.answer{background:#11202b;border-left:3px solid #22d3ee;border-radius:10px;padding:18px 22px;margin:0 0 28px;font-size:1.06rem}
.cta{background:#141824;border:1px solid #242c3f;border-left:3px solid var(--acc);border-radius:12px;padding:26px;margin:44px 0}
.cta h3{margin:0 0 8px}.cta p{color:var(--mut);margin:0 0 18px}
.btn{display:inline-block;background:var(--acc);color:#111;font-weight:700;text-decoration:none;padding:13px 26px;border-radius:9px}
.faq h3{font-size:1.02rem;margin:22px 0 6px;color:#fff}.faq p{color:var(--mut);margin:0}
.related{margin:44px 0 0;padding:22px;border:1px solid #232b3d;border-radius:12px}.related h2{margin:0 0 12px;font-size:1.05rem}
footer{margin-top:56px;padding-top:24px;border-top:1px solid #1e2433;color:var(--mut);font-size:.85rem}a{color:var(--acc)}"""
esc = lambda s: html.escape(str(s or ""), quote=True)


def fail(msg):
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(1)


def save(path, text):
    """UTF-8 with LF line ends on every platform. (Path.write_text takes newline only from Python 3.10.)"""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


MARK = "aether-site"  # written into every generated file, so publish can tell its own files from yours


def is_url(u):
    return bool(re.match(r"^https?://[^\s<>\"']+$", u or ""))


def cfg():
    p = ROOT / "aether.json"
    if not p.is_file():
        fail("no aether.json in this folder - create it first (see references/profile.md)")
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        fail(f"aether.json is not valid JSON: {e}")
    part = lambda k: d[k] if isinstance(d, dict) and isinstance(d.get(k), dict) else {}
    pr, st, cta = part("product"), part("site"), part("cta")
    s = lambda v: str(v or "").strip()
    folder = s(st.get("dir")) or "site"
    if Path(folder).is_absolute() or ".." in Path(folder).parts or not Path(folder).parts:
        fail("site.dir must be a folder inside the project (for example site or docs), not the project folder itself")
    if not s(pr.get("name")):
        fail("aether.json needs product.name")
    return {"name": s(pr.get("name")), "desc": s(pr.get("description")), "price": s(pr.get("price")),
            "checkout": s(pr.get("checkout_url")) if is_url(s(pr.get("checkout_url"))) else "",
            "base": s(st.get("base_url")).rstrip("/") if is_url(s(st.get("base_url"))) else "",
            "dir": ROOT / folder, "title": s(st.get("title")), "lede": s(st.get("lede")),
            "author": s(st.get("author")), "track": st.get("track_ref", True) is not False,
            "cta": {k: s(cta.get(k)) for k in ("title", "body", "button")}}


def db():
    (ROOT / ".aether").mkdir(exist_ok=True)
    c = sqlite3.connect(ROOT / ".aether" / "aether.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def safe_href(h):
    h = (h or "").strip()
    return h if re.match(r"^(https?://|mailto:)[^\s<>\"']+$", h, re.I) or \
        re.match(r"^[a-z0-9][a-z0-9\-]*\.html(#[\w\-]*)?$", h) else ""


class Sanitiser(HTMLParser):
    """The trust boundary for page bodies: an allowlist of harmless tags. No
    scripts, no event handlers, no script links, no embeds."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.open, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in DROPPED:
            self.skip += 1
        elif not self.skip and tag in ALLOWED:
            if tag == "a":
                href = safe_href(dict(attrs).get("href"))
                if not href:
                    return
                self.out.append(f'<a href="{esc(href)}"' + (' rel="nofollow noopener"' if href[:4] == "http" else "") + ">")
            else:
                self.out.append(f"<{tag}>")
            if tag not in ("br", "hr"):
                self.open.append(tag)

    def handle_endtag(self, tag):
        if tag in DROPPED:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in self.open:
            while self.open:
                t = self.open.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))


def sanitize(fragment):
    s = Sanitiser()
    s.feed(re.sub(r"```html?|```", "", fragment or ""))
    s.close()
    return ("".join(s.out) + "".join(f"</{t}>" for t in reversed(s.open))).strip()


def words(fragment):
    return len(html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).split())


def cmd_add(c, args):
    flags = {a for a in args if a.startswith("--")}
    files = [a for a in args if not a.startswith("--")]
    if not files or not Path(files[0]).is_file():
        fail("usage: add <page.json> [--replace] [--allow-thin]")
    try:
        d = json.loads(Path(files[0]).read_text(encoding="utf-8-sig"))
    except ValueError as e:
        fail(f"page file is not valid JSON: {e}")
    if not isinstance(d, dict):
        fail("page file must be one JSON object")
    one = lambda k, n: " ".join(str(d.get(k) or "").split())[:n]
    title, kw, desc, answer = one("title", 200), one("keyword", 120).lower(), one("description", 400), one("answer", 1000)
    slug = str(d.get("slug") or "").strip() or re.sub(r"[^a-z0-9]+", "-", (kw or title).lower()).strip("-")[:80].strip("-")
    body = sanitize(str(d.get("body_html") or ""))
    n, errors, warnings = words(body), [], []
    if not 10 <= len(title) <= 110:
        errors.append("title must be 10-110 characters")
    elif len(title) > 65:
        warnings.append(f"title is {len(title)} characters; search results cut it near 60")
    if not SLUG.match(slug) or len(slug) > 80 or slug == "index":
        errors.append("slug must be lowercase letters, digits and hyphens (max 80), not 'index'")
    if not 50 <= len(desc) <= 200:
        errors.append("description must be 50-200 characters (aim for 120-160)")
    if not 40 <= len(answer) <= 600:
        errors.append("answer must be 40-600 characters: the direct answer in one or two sentences")
    if n < MIN_WORDS and "--allow-thin" not in flags:
        errors.append(f"body has {n} words; the minimum is {MIN_WORDS}")
    if body.count("<h2>") < 2:
        warnings.append("fewer than two <h2> sections; the page will be hard to skim")
    faqs = [{"q": " ".join(str(f.get("q") or "").split())[:300], "a": " ".join(str(f.get("a") or "").split())[:1200]}
            for f in (d.get("faqs") if isinstance(d.get("faqs"), list) else []) if isinstance(f, dict)]
    faqs = [f for f in faqs if f["q"] and f["a"]][:8]
    if len(faqs) < 2:
        warnings.append("fewer than 2 FAQs; FAQ data is what answer engines quote")
    old = c.execute("SELECT id FROM pages WHERE slug=?", (slug,)).fetchone()
    if old and "--replace" not in flags:
        errors.append(f"a page with slug '{slug}' exists; pass --replace to overwrite it")
    if c.execute("SELECT 1 FROM pages WHERE lower(title)=? AND slug!=?", (title.lower(), slug)).fetchone():
        errors.append("another page already has this exact title")
    if errors:
        fail("; ".join(errors))
    now, vals = time.time(), (title, kw or title.lower(), one("cluster", 120).lower(), desc, answer, body, json.dumps(faqs))
    if old:
        c.execute("UPDATE pages SET title=?,keyword=?,cluster=?,description=?,answer=?,body=?,faqs=?,updated=?,"
                  "published=0 WHERE id=?", vals + (now, old["id"]))
    else:
        c.execute("INSERT INTO pages(title,keyword,cluster,description,answer,body,faqs,slug,created,updated)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?)", vals + (slug, now, now))
    return {"slug": slug, "words": n, "faqs": len(faqs), "warnings": warnings, "next": "run `publish`, then `audit`"}


def related(row, rows):
    """Same cluster first, then others, plus a ring link to the next page in
    sorted order: the ring makes zero orphan pages structural."""
    others = sorted((r for r in rows if r["slug"] != row["slug"]), key=lambda r: r["slug"])
    if not others:
        return ""
    same = [r for r in others if row["cluster"] and r["cluster"] == row["cluster"]]
    picked = (same[:4] + [r for r in others if r not in same][:2])[:6]
    slugs = sorted(r["slug"] for r in rows)
    nxt = slugs[(slugs.index(row["slug"]) + 1) % len(slugs)]
    if nxt not in [r["slug"] for r in picked]:
        picked.append(next(r for r in others if r["slug"] == nxt))
    items = "".join(f'<li><a href="{esc(r["slug"])}.html">{esc(r["title"])}</a></li>' for r in picked)
    return f'<nav class="related" aria-label="Related guides"><h2>Related guides</h2><ul>{items}</ul></nav>'


def buy_link(g, slug):
    """The checkout link, tagged with the page it sits on, so the seller's own
    checkout analytics show which page earned each sale."""
    url = g["checkout"]
    if not url or not g["track"] or "utm_campaign=" in url:
        return url
    base, hash_, frag = url.partition("#")
    tag = urllib.parse.urlencode({"utm_source": "aether", "utm_medium": "seo", "utm_campaign": slug})
    return f"{base}{'&' if '?' in base else '?'}{tag}{hash_}{frag}"


def render(g, row, rows):
    slug, faqs = row["slug"], json.loads(row["faqs"] or "[]")
    canonical = f"{g['base']}/{slug}.html" if g["base"] else f"{slug}.html"
    day = lambda t: time.strftime("%Y-%m-%d", time.localtime(t or time.time()))
    article = {"@type": "Article", "headline": row["title"][:110], "description": row["description"],
               "datePublished": day(row["created"]), "dateModified": day(row["updated"]), "inLanguage": "en",
               "about": {"@type": "Thing", "name": row["keyword"]},
               "mainEntityOfPage": {"@type": "WebPage", "@id": canonical}}
    if g["author"]:
        article["author"] = {"@type": "Person", "name": g["author"]}
    graph = [article]
    if faqs:
        graph.append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in faqs]})
    if g["base"]:
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Guides", "item": f"{g['base']}/index.html"},
            {"@type": "ListItem", "position": 2, "name": row["title"][:70], "item": canonical}]})
    # No "<" may appear inside the script block, whatever the text contains.
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, separators=(",", ":")).replace("<", "\\u003c")
    content = f'<div class="answer"><strong>{esc(row["answer"])}</strong></div>' + row["body"]
    if faqs:
        content += '<section class="faq"><h2>Common questions</h2>' + "".join(
            f"<h3>{esc(f['q'])}</h3><p>{esc(f['a'])}</p>" for f in faqs) + "</section>"
    content += related(row, rows)
    link, cta = buy_link(g, slug), ""
    if link:  # no checkout link, no buy box: never a dead button
        fill = lambda t: t.replace("{product}", g["name"]).replace("{price}", g["price"])
        cta = (f'<div class="cta"><h3>{esc(fill(g["cta"]["title"] or "Get " + g["name"]))}</h3>'
               f'<p>{esc(fill(g["cta"]["body"] or g["desc"]))}</p><a class="btn" href="{esc(link)}">'
               f'{esc(fill(g["cta"]["button"] or ("Get it - " + g["price"] if g["price"] else "Learn more")))}</a></div>')
    return (f'<!doctype html>\n<html lang="en"><head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n<meta name="generator" content="{MARK}">\n<title>{esc(row["title"])}</title>\n'
            f'<meta name="description" content="{esc(row["description"])}">\n<link rel="canonical" href="{esc(canonical)}">\n'
            f'<meta property="og:title" content="{esc(row["title"])}">\n<meta property="og:type" content="article">\n'
            f'<script type="application/ld+json">{ld}</script>\n<style>{CSS}</style></head><body><div class="wrap">\n'
            f'<h1>{esc(row["title"])}</h1>\n<div class="meta">Updated {time.strftime("%d %B %Y", time.localtime(row["updated"]))}'
            f' &middot; {max(2, words(content) // 220)} min read</div>\n{content}\n{cta}\n'
            f'<footer><a href="{"index.html"}">More guides</a> &middot; {esc(g["name"])}</footer>\n</div></body></html>')


def cmd_publish(c, args):
    g = cfg()
    rows = c.execute("SELECT * FROM pages ORDER BY slug").fetchall()
    extra = ["index.html", "robots.txt"] + (["sitemap.xml"] if g["base"] else [])
    theirs = [p.name for p in [g["dir"] / f"{r['slug']}.html" for r in rows] + [g["dir"] / n for n in extra]
              if p.is_file() and MARK not in p.read_text(encoding="utf-8", errors="replace")]
    if theirs and "--force" not in args:
        fail(f"{len(theirs)} file(s) in {g['dir'].name}/ were not written by this script and would be replaced: "
             + ", ".join(theirs[:8]) + ". Move them, set another site.dir, or run `publish --force` once the user agrees.")
    g["dir"].mkdir(parents=True, exist_ok=True)
    written = 0
    for row in rows:
        page, path = render(g, row, rows), g["dir"] / f"{row['slug']}.html"
        if not path.exists() or path.read_text(encoding="utf-8", errors="replace") != page:
            save(path, page)
            written += 1
        c.execute("UPDATE pages SET published=1 WHERE id=?", (row["id"],))
    groups = {}
    for r in rows:
        groups.setdefault(r["cluster"] or "guides", []).append(r)
    listing = "".join(f"<h2>{esc(k.title())}</h2><ul>" + "".join(
        f'<li><a href="{esc(r["slug"])}.html">{esc(r["title"])}</a></li>' for r in v) + "</ul>"
        for k, v in sorted(groups.items())) or "<p>No guides published yet.</p>"
    title, link = g["title"] or f"{g['name']} guides", buy_link(g, "index")
    hero = f'<div class="cta"><h3>{esc(g["name"])}</h3><p>{esc(g["desc"])}</p><a class="btn" href="{esc(link)}">' \
           f'{esc("Get it - " + g["price"] if g["price"] else "Learn more")}</a></div>' if link else ""
    save(g["dir"] / "index.html", (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n<meta name="generator" content="{MARK}">\n'
        f'<meta name="viewport" '
        f'content="width=device-width,initial-scale=1">\n<title>{esc(title)}</title>\n<meta name="description" '
        f'content="{esc(g["lede"] or g["desc"])}">\n<style>{CSS}</style></head><body><div class="wrap">\n<h1>{esc(title)}</h1>\n'
        f'<p class="meta">{esc(g["lede"])}</p>\n{hero}\n{listing}\n</div></body></html>'))
    lines = [f"# {MARK}", "User-agent: *", "Allow: /"]
    if g["base"]:
        urls = [f"<url><loc>{g['base']}/index.html</loc></url>"] + [
            f"<url><loc>{g['base']}/{r['slug']}.html</loc><lastmod>{time.strftime('%Y-%m-%d', time.localtime(r['updated']))}"
            f"</lastmod></url>" for r in rows]
        save(g["dir"] / "sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<!-- {MARK} -->\n' '<urlset xmlns="http://www.sitemaps.org/'
                                              'schemas/sitemap/0.9">' + "".join(urls) + "</urlset>")
        lines.append(f"Sitemap: {g['base']}/sitemap.xml")
    save(g["dir"] / "robots.txt", "\n".join(lines) + "\n")
    return {"files_written": written, "pages": len(rows), "site_dir": str(g["dir"]), "also_written": extra,
            "sitemap": "written" if g["base"] else "skipped: set site.base_url to get a sitemap",
            "buy_link": "set" if g["checkout"] else "not set: pages carry no buy box"}


class Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = self.desc = self.canonical = ""
        self.h1, self.words, self.answer, self.hrefs, self.ld, self._in = 0, 0, False, [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name") == "description":
            self.desc = a.get("content") or ""
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href") or ""
        elif tag == "h1":
            self.h1 += 1
        elif tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        elif tag == "div" and a.get("class") == "answer":
            self.answer = True
        if tag == "script" and a.get("type") == "application/ld+json":
            self._in.append("ld")
            self.ld.append("")
        elif tag in ("script", "style", "title"):
            self._in.append(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "title") and self._in:
            self._in.pop()

    def handle_data(self, data):
        where = self._in[-1] if self._in else ""
        if where == "ld":
            self.ld[-1] += data
        elif where == "title":
            self.title += data
        elif not where:
            self.words += len(data.split())


def cmd_audit(c, args):
    """Measure the published files on disk. Nothing here is estimated."""
    g = cfg()
    slugs = [r["slug"] for r in c.execute("SELECT slug FROM pages WHERE published=1 ORDER BY slug")]
    if not slugs:
        return {"pages": 0, "note": "nothing published yet"}
    inbound, issues, seen = {s: 0 for s in slugs}, [], {"title": {}, "meta description": {}}
    flag = lambda page, sev, issue: issues.append({"page": page, "severity": sev, "issue": issue})
    faq = buy = 0
    for slug in slugs:
        path = g["dir"] / f"{slug}.html"
        if not path.exists():
            flag(slug, "error", "published but the file is missing; run `publish`")
            continue
        s = Scan()
        s.feed(path.read_text(encoding="utf-8", errors="replace"))
        for label, text, lo, hi in (("title", s.title, 10, 65), ("meta description", s.desc, 70, 165)):
            text = " ".join(text.split())
            if not text:
                flag(slug, "error", f"no {label}")
            else:
                seen[label].setdefault(text.lower(), []).append(slug)
                if not lo <= len(text) <= hi:
                    flag(slug, "warn", f"{label} is {len(text)} characters; aim for {lo}-{hi}")
        if s.h1 != 1:
            flag(slug, "error", f"{s.h1} <h1> tags; a page needs exactly one")
        if not s.canonical or (g["base"] and s.canonical != f"{g['base']}/{slug}.html"):
            flag(slug, "error" if not s.canonical else "warn", "canonical link missing or stale; run `publish`")
        types = set()
        for block in s.ld:
            try:
                types |= {n.get("@type") for n in json.loads(block).get("@graph", [])}
            except (ValueError, AttributeError):
                flag(slug, "error", "a structured-data block does not parse")
        if "Article" not in types:
            flag(slug, "error", "no Article structured data")
        faq += "FAQPage" in types
        if not s.answer:
            flag(slug, "warn", "no answer box at the top")
        if s.words < MIN_WORDS:
            flag(slug, "warn", f"thin content: {s.words} words")
        for h in s.hrefs:
            m = re.match(r"^([a-z0-9][a-z0-9\-]*)\.html(?:#.*)?$", h)
            if m and m.group(1) in inbound and m.group(1) != slug:
                inbound[m.group(1)] += 1
            elif m and m.group(1) not in ("index", slug) and not (g["dir"] / f"{m.group(1)}.html").exists():
                flag(slug, "error", f"broken internal link to {m.group(1)}.html")
        buy += bool(g["checkout"]) and any(h.startswith(g["checkout"].split("?")[0].split("#")[0]) for h in s.hrefs)
    for label, groups in seen.items():
        for group in groups.values():
            if len(group) > 1:
                flag(group[0], "warn", f"same {label} as {', '.join(group[1:4])}")
    orphans = [s for s, n in inbound.items() if n == 0] if len(slugs) > 1 else []
    for s in orphans:
        flag(s, "error", "orphan: no other page links here; run `publish`")
    sitemap = "skipped: site.base_url is not set"
    if g["base"]:
        sm = g["dir"] / "sitemap.xml"
        text = sm.read_text(encoding="utf-8", errors="replace") if sm.exists() else ""
        missing = [s for s in slugs if f"{g['base']}/{s}.html" not in text]
        sitemap = "lists every page" if text and not missing else "missing or incomplete; run `publish`"
        if missing or not text:
            flag("sitemap.xml", "error", sitemap)
    errors = sum(i["severity"] == "error" for i in issues)
    return {"pages": len(slugs), "errors": errors, "warnings": len(issues) - errors, "orphans": len(orphans),
            "avg_inbound_links": round(sum(inbound.values()) / len(slugs), 1), "with_faq_data": faq,
            "with_buy_link": buy, "sitemap": sitemap,
            "buy_link": "set" if g["checkout"] else "not set: pages carry no buy box",
            "issues": issues[:60], "issues_not_shown": max(0, len(issues) - 60)}


def main(argv):
    cmds = {"add": cmd_add, "publish": cmd_publish, "audit": cmd_audit}
    if not argv or argv[0] not in (*cmds, "list", "remove"):
        fail("usage: site.py <add|list|remove|publish|audit> ...")
    c = db()
    with c:
        if argv[0] == "list":
            result = [dict(r) for r in c.execute("SELECT slug,title,keyword,cluster,published FROM pages ORDER BY slug")]
        elif argv[0] == "remove":
            slug = argv[1] if len(argv) > 1 else ""
            ok = bool(SLUG.match(slug)) and c.execute("DELETE FROM pages WHERE slug=?", (slug,)).rowcount > 0
            if ok and (cfg()["dir"] / f"{slug}.html").exists():
                (cfg()["dir"] / f"{slug}.html").unlink()
            result = {"removed": ok, "next": "run `publish` to relink the remaining pages"}
        else:
            result = cmds[argv[0]](c, argv[1:])
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # an input nobody planned for: one JSON error line, never a traceback
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        sys.exit(1)
