#!/usr/bin/env python3
"""Aether proof: measure a draft before it is published. Finds filler, stock
phrases, over-long sentences, repetition and weak openings, and scores the text.
Local only: no network code. Reads one file, prints JSON.

  python proof.py <file>        .txt, .md, .html, or a page .json (body_html + answer)

It measures; it does not rewrite. Fix what it flags and run it again.
"""
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

STOCK = ["delve", "in today's", "in the world of", "it's important to note", "it is important to note",
         "it's worth noting", "in conclusion", "game-changer", "game changer", "unlock the", "unleash",
         "leverage", "seamless", "robust", "ever-evolving", "landscape", "elevate", "furthermore", "moreover",
         "navigate the", "tapestry", "realm", "cutting-edge", "revolutionize", "look no further",
         "when it comes to", "at the end of the day", "needless to say", "dive into", "deep dive",
         "take your", "to the next level", "whether you're", "let's face it", "the fact that",
         "in order to", "a wide range of", "plays a crucial role", "stands out", "testament to", "supercharge"]
HEDGES = ["might", "could potentially", "may possibly", "perhaps", "somewhat", "arguably", "generally speaking",
          "in some cases", "it seems", "tends to"]
VAGUE = ["many", "various", "numerous", "several", "a lot of", "countless", "significant", "significantly"]


def load(path):
    p = Path(path)
    if not p.is_file():
        fail(f"no such file: {path}")
    if p.stat().st_size > 5_000_000:
        fail("file is larger than 5 MB")
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    if p.suffix == ".json":
        try:
            d = json.loads(text)
            text = f"{d.get('answer', '')}\n\n{d.get('body_html', '')}" if isinstance(d, dict) else text
        except ValueError:
            pass
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)</(p|h[1-6]|li|tr|div)>|<br\s*/?>", ". ", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"[#*_`>|]+", " ", text)


def fail(msg):
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(1)


def syllables(word):
    groups = re.findall(r"[aeiouy]+", word.lower())
    n = len(groups) - (1 if word.lower().endswith("e") and len(groups) > 1 else 0)
    return max(n, 1)


def main(argv):
    if len(argv) != 1:
        fail("usage: proof.py <file>")
    text = load(argv[0])
    low = " " + " ".join(text.lower().split()) + " "
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\.\s*\.", text) if len(s.split()) >= 3]
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    if len(words) < 30:
        fail("the text has fewer than 30 words: nothing to measure")
    issues = []
    flag = lambda sev, what, detail: issues.append({"severity": sev, "issue": what, "detail": detail})

    lengths = [len(s.split()) for s in sentences] or [len(words)]
    long_ones = [" ".join(s.split()[:12]) + " ..." for s in sentences if len(s.split()) > 32]
    if long_ones:
        flag("fix", f"{len(long_ones)} sentence(s) over 32 words", long_ones[:5])
    stock = {p: low.count(" " + p) for p in STOCK if low.count(" " + p)}
    if stock:
        flag("fix", f"{sum(stock.values())} stock phrase(s) a reader has seen a thousand times", stock)
    hedges = {p: low.count(" " + p + " ") for p in HEDGES if low.count(" " + p + " ")}
    if sum(hedges.values()) > max(2, len(words) // 250):
        flag("consider", "hedging: say it plainly or cut it", hedges)
    vague = {p: low.count(" " + p + " ") for p in VAGUE if low.count(" " + p + " ")}
    if sum(vague.values()) > max(3, len(words) // 150):
        flag("consider", "vague quantities: give the number or drop the claim", vague)
    openers = [s.split()[0].lower().strip("\"'(") for s in sentences]
    runs = [openers[i] for i in range(len(openers) - 2) if openers[i] == openers[i + 1] == openers[i + 2]]
    if runs:
        flag("fix", "three sentences in a row start with the same word", sorted(set(runs)))
    toks = [w.lower() for w in words]
    grams = Counter(" ".join(toks[i:i + 4]) for i in range(len(toks) - 3))
    repeats = {g: n for g, n in grams.most_common(8) if n >= 3}
    if repeats:
        flag("consider", "the same four-word phrase appears three or more times", repeats)
    passive = len(re.findall(r"\b(?:is|are|was|were|been|being|be)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b", low))
    if passive > max(2, len(sentences) // 4):
        flag("consider", f"{passive} passive constructions; name who does what", None)
    bangs = text.count("!")
    if bangs > 1:
        flag("fix", f"{bangs} exclamation marks", None)
    first = " ".join(sentences[0].split()[:40]) if sentences else ""
    if re.match(r"(?i)\s*(in today|in the world|are you|have you ever|imagine|when it comes|welcome)", first):
        flag("fix", "the opening sentence warms up instead of answering", first)
    if len(set(lengths)) <= 2 and len(lengths) >= 6:
        flag("consider", "every sentence is the same length; vary the rhythm", None)

    avg = sum(lengths) / len(lengths)
    flesch = 206.835 - 1.015 * avg - 84.6 * (sum(map(syllables, words)) / len(words))
    if flesch < 45:
        flag("consider", f"hard to read (Flesch reading ease {flesch:.0f}); shorter words and sentences", None)
    fixes = sum(i["severity"] == "fix" for i in issues)
    score = max(0, 100 - 12 * fixes - 5 * (len(issues) - fixes))
    print(json.dumps({"words": len(words), "sentences": len(sentences), "avg_sentence_words": round(avg, 1),
                      "reading_ease": round(flesch), "score": score, "fix": fixes,
                      "consider": len(issues) - fixes, "issues": issues,
                      "note": "Measured from the text. A clean score means none of these patterns were found, "
                              "not that the text is true or good: check the facts yourself."}, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # an input nobody planned for: one JSON error line, never a traceback
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        sys.exit(1)
