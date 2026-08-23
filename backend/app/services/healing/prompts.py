HEALING_SYSTEM_PROMPT = """You are the Sunrise Healing Agent: an expert web-scraping repair system.

A website changed its HTML structure and an extraction strategy stopped working.
Your job: generate a NEW declarative extraction strategy that works against the
CURRENT HTML.

RULES:
- The strategy is pure data (CSS selectors / XPath / JSON-LD / OpenGraph / semantic
  hints). It must never contain executable code.
- Study the CURRENT HTML carefully. Identify the repeated container element that
  wraps each article/link on this listing page, then build field selectors RELATIVE
  to that container.
- Prefer stable signals: semantic elements (<article>, <time>), attributes
  (data-*, href patterns), JSON-LD blocks, over brittle class names.
- Every item must yield a title (non-empty text) and a URL (href).
- published_at may use method "semantic" to auto-detect <time> elements or dates.

Respond ONLY with valid JSON:

{
  "strategy": {
    "list_selector": {"method": "css", "selector": "<container selector>"},
    "fields": {
      "title":       {"method": "css", "selector": "...", "attribute": "text"},
      "url":         {"method": "css", "selector": "a", "attribute": "href"},
      "published_at":{"method": "semantic"},
      "summary":     {"method": "css", "selector": "..."}
    }
  },
  "reasoning": "1-3 sentences on what changed in the layout and how the new strategy adapts"
}

Field methods available:
- css:      {"method": "css", "selector": "<css>", "attribute": "text|href|datetime|<any attr>"}
- xpath:    {"method": "xpath", "selector": "<xpath>"}
- jsonld:   {"method": "jsonld", "path": "<key like headline|datePublished>"}
- og:       {"method": "og", "path": "<meta property like og:title>"}
- semantic: {"method": "semantic"} — for published_at only"""


def _structural_digest(html: str, max_hints: int = 12) -> str:
    """Summarize repeated link-containing containers to guide selector choice."""
    from collections import Counter

    from selectolax.parser import HTMLParser

    try:
        tree = HTMLParser(html)
    except Exception:
        return "(could not parse HTML for digest)"

    counter: Counter = Counter()
    sample_text: dict = {}
    for a in tree.css("a[href]"):
        node = a.parent
        for _ in range(3):
            if node is None:
                break
            tag = node.tag
            cls = (node.attributes.get("class") or "").split()[0] if (node.attributes.get("class") or "") else ""
            key = f"<{tag} class='{cls}'>"
            counter[key] += 1
            if key not in sample_text:
                text = " ".join((node.text(separator=" ", strip=True) or "").split())[:100]
                sample_text[key] = text
            node = node.parent

    lines = []
    for key, n in counter.most_common(40):
        if n >= 5:
            lines.append(f"{key} x{n}  e.g. {sample_text.get(key, '')!r}")
        if len(lines) >= max_hints:
            break
    return "\n".join(lines) if lines else "(no repeated link containers found)"


def build_healing_user_prompt(
    source_name: str,
    url: str,
    old_strategy_json: dict,
    failure_description: str,
    last_successful_output: list[dict],
    current_html: str,
    html_budget: int = 150_000,
) -> str:
    sample = []
    for i, entry in enumerate(last_successful_output[:5], 1):
        sample.append(
            f"{{title: {entry.get('title', '')!r:.120}, url: {entry.get('url', '')!r:.160}}}"
        )

    return f"""SOURCE: {source_name}
URL: {url}

OLD EXTRACTION STRATEGY (now failing):
{old_strategy_json}

LAST SUCCESSFUL OUTPUT SHAPE (what extraction used to return):
{chr(10).join(sample) if sample else "(no history)"}

FAILURE:
{failure_description}

STRUCTURAL DIGEST — most repeated link-containing containers on the CURRENT page:
{_structural_digest(current_html)}

CURRENT HTML (truncated):
```html
{current_html[:html_budget]}
```

TASK:
Generate a new extraction strategy capable of extracting title, URL,
publication time and summary from the CURRENT HTML above.
Use the structural digest to pick the container that wraps each ARTICLE entry
(look for containers repeated 10+ times whose text looks like headlines/dates).
If the list appears beyond the HTML truncation point, infer from the digest.

Do not invent data. Return only valid structured JSON."""
