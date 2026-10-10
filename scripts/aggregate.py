"""Bounded public RSS collection and a static build; no accounts, APIs, or database."""
import argparse
import calendar
import concurrent.futures
import gzip
import hashlib
import html
import io
import json
import re
import shutil
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 4 * 1024 * 1024
MAX_ITEMS = 3000
DAYS = 7
CATEGORIES = {"world": "World", "estonia": "Estonia", "technology": "AI & Technology", "russia-ukraine": "Russia & Ukraine", "southeast-asia": "Southeast Asia"}
TRACKERS = {"fbclid", "gclid", "dclid", "mc_cid", "mc_eid", "ref", "ref_src", "ocid", "xtor", "cmpid"}
STOPWORDS = set("a an the of to in on for with and at by from is are as its it this that".split())
CRYPTO_NOISE = re.compile(r"price (prediction|analysis|forecast|today)|presale|sponsored|press release|\b100x\b", re.I)
TECH_NOISE = re.compile(r"\b(deals?|coupon|discount|sale)\b", re.I)
SEA_TOPIC = re.compile(r"\b(thailand|thai|thais|vietnam|vietnamese|viet nam|cambodia|cambodian|khmer|laos|lao|laotian|myanmar|burma|burmese|malaysia|malaysian|singapore|singaporean|indonesia|indonesian|philippines|philippine|filipino|brunei|timor|asean|mekong|southeast asia|south-east asia|bangkok|hanoi|ho chi minh|phnom penh|vientiane|jakarta|manila|kuala lumpur|yangon|chiang mai|chiang rai|phuket)\b", re.I)


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def write_json(path, value, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=None if compact else 2) + "\n", encoding="utf-8")
    temporary.replace(path)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ("p", "br", "div", "li"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif tag in ("p", "div", "li"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain_text(value):
    parser = PlainText()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def excerpt(value, maximum=320):
    text = plain_text(value)
    return text if len(text) <= maximum else text[:maximum].rsplit(" ", 1)[0].rstrip() + "…"


def canonical_url(value):
    parts = urllib.parse.urlsplit(html.unescape(value or ""))
    if parts.scheme.lower() not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        return None
    query = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in TRACKERS]
    port = parts.port
    host = parts.hostname.lower()
    if port and port not in (80, 443):
        host += f":{port}"
    return urllib.parse.urlunsplit((parts.scheme.lower(), host, parts.path or "/", urllib.parse.urlencode(sorted(query)), ""))


def normalize_title(title):
    text = unicodedata.normalize("NFKC", title).casefold()
    text = re.sub(r"^(breaking|exclusive|update)\s*:\s*", "", text)
    return " ".join(re.findall(r"\w+", text, re.UNICODE))


def similar_titles(first, second):
    # Different numbers, negations, or substantive words keep reports separate.
    a, b = normalize_title(first), normalize_title(second)
    words_a, words_b = set(a.split()), set(b.split())
    if min(len(a.split()), len(b.split())) < 5:
        return False
    if a == b:
        return True
    if set(re.findall(r"\d+", a)) != set(re.findall(r"\d+", b)):
        return False
    if (words_a ^ words_b) - STOPWORDS:
        return False
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= .96


def download(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "NewsLolol/1.0 (personal RSS reader; https://news.lolol.party)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Feed exceeds the 4 MiB download limit")
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or b"<!ENTITY" in raw.upper():
            raise ValueError("Oversized feed or unsupported XML entity declarations")
        return raw, response.status, response.url


def entry_date(entry):
    # Atom updated dates are kept and labeled as updates when publication is absent.
    for name in ("published", "updated"):
        value = entry.get(name + "_parsed")
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), timezone.utc), name
    return None, None


def fetch_source(source, now):
    status = {"id": source["id"], "checked_at": iso(now)}
    try:
        raw, code, final_url = download(source["feed"])
        parsed = feedparser.parse(raw)
        if not parsed.get("version") or not parsed.entries:
            raise ValueError("Endpoint did not provide a nonempty RSS/Atom feed")
        records, latest, skipped_dates = [], None, 0
        for entry in parsed.entries[:250]:
            date, basis = entry_date(entry)
            title = plain_text(entry.get("title", ""))
            url = canonical_url(urllib.parse.urljoin(final_url, entry.get("link", "")))
            if not date or date > now + timedelta(hours=6):
                skipped_dates += 1
                continue
            latest = max(latest, date) if latest else date
            if not title or not url or date < now - timedelta(days=DAYS):
                continue
            if source.get("crypto") and CRYPTO_NOISE.search(title):
                continue
            if source["category"] == "technology" and TECH_NOISE.search(title):
                continue
            tags = " ".join(tag.get("term", "") for tag in entry.get("tags", []))
            if re.search(r"sponsored|partner content|press release", tags, re.I):
                continue
            if source.get("region_filter") == "southeast-asia":
                topic = " ".join((title, plain_text(entry.get("summary", "")), tags,
                                  urllib.parse.unquote(urllib.parse.urlsplit(url).path).replace("-", " ")))
                if not SEA_TOPIC.search(topic):
                    continue
            language = entry.get("language") or entry.get("title_detail", {}).get("language") or source["language"]
            language = language.lower().split("-")[0]
            if language not in ("en", "et", "ru", "uk"):
                language = source["language"]
            identifier = hashlib.sha256((source["id"] + "\0" + url).encode()).hexdigest()[:24]
            records.append({"id": identifier, "title": title, "url": url, "original_url": entry.get("link", url),
                            "source": source["id"], "published_at": iso(date), "date_basis": basis,
                            "excerpt": excerpt(entry.get("summary", "")), "category": source["category"], "language": language})
        status.update(status="ok" if records else "stale", http_status=code, parsed_entries=len(parsed.entries),
                      recent_articles=len(records), latest_article=iso(latest) if latest else None,
                      skipped_dates=skipped_dates, feed_format=parsed.version, final_feed_url=final_url)
        if records:
            status["last_success"] = iso(now)
        return records, status
    except Exception as error:
        status.update(status="error", error=f"{type(error).__name__}: {error}")
        return [], status


def retained_articles(articles, sources, now):
    by_source = defaultdict(list)
    for article in articles:
        if article["source"] in sources and now - timedelta(days=DAYS) <= datetime.fromisoformat(article["published_at"]) <= now + timedelta(hours=6):
            by_source[article["source"]].append(article)
    kept = []
    for source_id, items in by_source.items():
        kept.extend(sorted(items, key=lambda item: item["published_at"], reverse=True)[:sources[source_id].get("limit", 150)])
    return sorted(kept, key=lambda item: item["published_at"], reverse=True)[:MAX_ITEMS]


def group_articles(articles):
    groups, by_url, buckets = [], {}, defaultdict(list)
    for article in sorted(articles, key=lambda item: (item["published_at"], item["id"]), reverse=True):
        normalized = normalize_title(article["title"])
        significant = [word for word in normalized.split() if word not in STOPWORDS]
        bucket = (article["language"], article["category"], significant[0] if significant else normalized)
        group = by_url.get(article["url"])
        if group is None:
            for candidate in buckets[bucket]:
                main = candidate["primary"]
                if abs((datetime.fromisoformat(main["published_at"]) - datetime.fromisoformat(article["published_at"])).total_seconds()) > 18 * 3600:
                    continue
                if similar_titles(main["title"], article["title"]):
                    group = candidate
                    break
        if group is None:
            group = {"primary": article, "reports": [], "categories": []}
            groups.append(group)
            buckets[bucket].append(group)
        if article["category"] not in group["categories"]:
            group["categories"].append(article["category"])
        if not any(report["source"] == article["source"] and report["url"] == article["url"] for report in group["reports"]):
            group["reports"].append(article)
        by_url[article["url"]] = group
    return groups


def collect():
    now = utc_now()
    sources = [source for source in read_json(ROOT / "sources.json", []) if source.get("enabled", True)]
    old = read_json(ROOT / "data" / "articles.json", {"articles": []})
    previous_status = {item["id"]: item for item in read_json(ROOT / "data" / "status.json", {"sources": []})["sources"]}
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_source, source, now): source for source in sources}
        for future in concurrent.futures.as_completed(futures):
            records, status = future.result()
            results.append((records, status))
            print(f"{futures[future]['name']}: {status['status']}, {len(records)} recent articles", flush=True)
    successful = sum(status["status"] == "ok" for _, status in results)
    if not successful:
        raise RuntimeError("No source supplied current articles; preserved all last successful data")
    indexed = {item["id"]: item for item in old["articles"]}
    statuses = []
    for records, status in results:
        indexed.update((article["id"], article) for article in records)
        if "last_success" not in status:
            status["last_success"] = previous_status.get(status["id"], {}).get("last_success")
        statuses.append(status)
    source_index = {source["id"]: source for source in sources}
    articles = retained_articles(indexed.values(), source_index, now)
    counts = dict(Counter(article["category"] for article in articles))
    write_json(ROOT / "data" / "articles.json", {"last_successful_refresh": iso(now), "articles": sorted(articles, key=lambda item: item["id"])})
    write_json(ROOT / "data" / "status.json", {"last_successful_refresh": iso(now), "successful_sources": successful,
                                               "article_counts": counts, "sources": sorted(statuses, key=lambda item: item["id"])})
    print(json.dumps({"successful_sources": successful, "retained_articles": len(articles), "categories": counts}, ensure_ascii=False))


def build():
    data = read_json(ROOT / "data" / "articles.json", {"articles": []})
    if not data["articles"]:
        raise RuntimeError("Collect real news before building")
    sources = [source for source in read_json(ROOT / "sources.json", []) if source.get("enabled", True)]
    groups = group_articles(retained_articles(data["articles"], {source["id"]: source for source in sources}, utc_now()))
    if not groups:
        raise RuntimeError("No recent articles available; keep the existing deployment")
    site = ROOT / "site"
    assert site.resolve().parent == ROOT.resolve() and site.name == "site"
    site.mkdir(exist_ok=True)
    for asset in (ROOT / "web").iterdir():
        if asset.is_file():
            shutil.copyfile(asset, site / asset.name)
    status = read_json(ROOT / "data" / "status.json", {})
    payload = {"updated_at": data["last_successful_refresh"], "timezone": "Europe/Tallinn", "categories": CATEGORIES,
               "sources": sources, "source_status": status.get("sources", []), "articles": groups,
               "stats": {"stored_reports": len(data["articles"]), "displayed_stories": len(groups), "duplicates_consolidated": sum(len(group["reports"]) - 1 for group in groups)}}
    write_json(site / "data" / "news.json", payload, compact=True)
    (site / ".nojekyll").touch()
    print(json.dumps({"stories": len(groups), "consolidated_reports": payload["stats"]["duplicates_consolidated"], "site_bytes": sum(path.stat().st_size for path in site.rglob("*") if path.is_file())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("collect", "build", "refresh"))
    command = parser.parse_args().command
    if command in ("collect", "refresh"):
        collect()
    if command in ("build", "refresh"):
        build()
