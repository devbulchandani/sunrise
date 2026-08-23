import pytest

HTML_SAMPLE = """
<html><head>
<title>Press Releases</title>
<script type="application/ld+json">
{"@type":"NewsArticle","headline":"Fed cuts rates","url":"https://example.gov/fed-cuts","datePublished":"2026-08-20T14:00:00Z","description":"Rate decision"}
</script>
</head><body>
<div id="press">
  <div class="item">
    <h3><a href="/news/one">First announcement about inflation targets</a></h3>
    <p>Summary text one</p>
    <time datetime="2026-08-21T10:00:00Z">August 21, 2026</time>
  </div>
  <div class="item">
    <h3><a href="/news/two">Second announcement on employment data</a></h3>
    <p>Summary text two</p>
    <time datetime="2026-08-21T09:00:00Z">August 21, 2026</time>
  </div>
  <div class="item">
    <h3>No link here</h3>
  </div>
</div>
<meta property="og:title" content="OG Title Here"/>
</body></html>
"""

STRATEGY = {
    "list_selector": {"method": "css", "selector": "#press .item"},
    "fields": {
        "title": {"method": "css", "selector": "h3 a", "attribute": "text"},
        "url": {"method": "css", "selector": "h3 a", "attribute": "href"},
        "published_at": {"method": "semantic"},
        "summary": {"method": "css", "selector": "p"},
    },
}

BASE_URL = "https://example.gov/press"


def make_executor(html=HTML_SAMPLE):
    from app.services.scraping.extractor import StrategyExecutor

    return StrategyExecutor(html, BASE_URL)


def test_extract_basic_fields():
    entries = make_executor().extract(STRATEGY)
    assert len(entries) == 2  # third item has no url -> skipped
    assert entries[0]["title"] == "First announcement about inflation targets"
    assert entries[0]["url"] == "https://example.gov/news/one"
    assert entries[0]["summary"] == "Summary text one"
    assert entries[0]["published_at"]


def test_missing_fields_skips_item():
    strategy = {
        "list_selector": {"method": "css", "selector": "#press .item"},
        "fields": {
            "title": {"method": "css", "selector": "h3 a", "attribute": "text"},
            "url": {"method": "css", "selector": ".does-not-exist", "attribute": "href"},
        },
    }
    entries = make_executor().extract(strategy)
    assert entries == []


def test_malformed_html_does_not_crash():
    executor = make_executor("<html><body><div class='broken'><p>unclosed")
    entries = executor.extract(STRATEGY)
    assert isinstance(entries, list)


def test_jsonld_extraction():
    strategy = {
        "fields": {
            "title": {"method": "jsonld", "path": "headline"},
            "url": {"method": "jsonld", "path": "url"},
            "published_at": {"method": "jsonld", "path": "datePublished"},
        }
    }
    entries = make_executor().extract(strategy)
    assert len(entries) == 1
    assert entries[0]["title"] == "Fed cuts rates"
    assert entries[0]["url"] == "https://example.gov/fed-cuts"


def test_og_extraction():
    from app.llm.schemas import ExtractionStrategy

    parsed = ExtractionStrategy.model_validate(
        {"fields": {"title": {"method": "og", "path": "og:title"}, "url": {"method": "jsonld", "path": "url"}}}
    )
    entries = make_executor().extract(parsed)
    assert entries[0]["title"] == "OG Title Here"


def test_xpath_extraction():
    strategy = {
        "list_selector": {"method": "xpath", "selector": "//div[@id='press']/div[@class='item']"},
        "fields": {
            "title": {"method": "xpath", "selector": ".//h3/a/text()"},
            "url": {"method": "css", "selector": "h3 a", "attribute": "href"},
        },
    }
    entries = make_executor().extract(strategy)
    assert len(entries) >= 1
    assert "announcement" in entries[0]["title"].lower()
