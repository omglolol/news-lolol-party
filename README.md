# News · lolol.party

A small, public, text-only RSS reader for World, Estonia, AI & Technology, Russia & Ukraine, and Southeast Asia. Original headlines and short feed excerpts link to the publishers. Times use Europe/Tallinn. No article images, AI rewriting, accounts, tracking, or database.

## Hosting

GitHub Actions collects feeds and publishes the static `site/` directory to GitHub Pages. Refreshes run every four hours, at minute 17 in UTC, with a manual **Run workflow** trigger. Scheduled GitHub jobs can be delayed; the displayed update time reports the actual last successful collection.

An open reader checks for a newer published edition every five minutes while visible and when returning to the tab. Filters, search, and the number of loaded stories are preserved. Article times are the publishers' original dates, which can be earlier than the edition's last refresh. A temporary network error keeps the currently loaded edition available.

Each run starts from the current `main` branch. Saving refreshed data retries a failed GitHub push up to three times, with 5- and 10-second pauses. If all attempts fail, deployment stops and the last published edition stays available.

Cloudflare is used only for the `news.lolol.party` DNS record. This project has no Cloudflare Worker, D1, R2, Pages build, billing integration, or connection to theye.news. The existing lolol.party gallery and forum are independent too.

## Collection and duplicates

`sources.json` lists only public publisher feeds. Each feed has a 12-second timeout and a 4 MiB download limit; six requests run concurrently. RSS 2.0, RSS/RDF, and Atom are supported. Broken feeds are independent, and their recent cached articles remain available. A refresh with no current successful source fails before replacing the previous data or deployment.

The initial collection verified 38 working feeds on 9 October 2026: World 9, Estonia 7, AI & Technology 12, and Russia & Ukraine 10. Pealinn and The Insider are disabled because their tested endpoints did not provide usable feeds. Publishers listed as predominantly paywalled in the project brief are excluded. AP and ISW are not included without a verified public feed.

Articles without usable dates are omitted. Original published dates are preferred; feed update dates are explicitly marked when publication is absent. Dates more than six hours in the future are rejected. Up to seven days are retained, with 150 items per source and 3,000 total. The two cryptocurrency feeds have smaller limits, and routine price predictions, presales, and promotional items are excluded.

Tracking parameters are removed from URLs. Identical URLs are consolidated. Identical meaningful headlines and very close variants within 18 hours can be grouped, keeping every original report accessible. Matching does not cross languages; different numbers, negations, or substantive wording keep reports separate. This deliberately favors preserving distinct developments and analyses over aggressive merging.

Source and category filters inspect all reports in a group. Search checks original headlines. The initial view contains 25 stories, with an explicit Load more control. `noindex` discourages search indexing; this remains a public website, not password protection.

## Southeast Asia

Added 10 English-language publications on 10 October 2026, with the largest source selection devoted to Thailand:

- Thailand: Bangkok Post, Khaosod English, Thai Enquirer, The Thaiger.
- Vietnam: VnExpress International, Viet Nam News (society feed).
- Cambodia: Cambodia Investment Review (business and economic reporting).
- Laos: The Laotian Times.
- Regional coverage: CNA (Asia feed, filtered to Southeast Asian countries, cities, ASEAN and the Mekong); The Irrawaddy (Myanmar).

Feed URLs and publisher websites are in `sources.json`. Khmer Times and The Phnom Penh Post worked locally but returned HTTP 403 from GitHub Actions, so they were replaced with an accessible Cambodian publication. Cambodia coverage is also provided by CNA and the Thai publications, particularly for cross-border developments. Only publisher feeds with recent, dated English-language articles were selected; Thai PBS World did not provide a usable feed, and Tuoi Tre News supplied no parseable publication dates in its tested feed. Headlines and excerpts remain in their original form. Feed availability is checked on every scheduled refresh.

## Local use

Use Python 3.13 or newer:

```sh
python -m venv .venv
# Activate .venv using your shell's normal command.
python -m pip install -r requirements.txt
python scripts/aggregate.py refresh
python -m http.server 4180 --directory site --bind 127.0.0.1
```

The repository contains only this project's non-sensitive source configuration and short public news records. Credentials are not required for collection and are never placed in the source or published site. GitHub's built-in workflow token is scoped through job permissions.

To configure a new repository, select GitHub Actions as the Pages source, enable the workflow, and set the custom domain to `news.lolol.party` before creating a DNS-only CNAME for `news` pointing to the account's `github.io` hostname. Enable HTTPS once GitHub has provisioned its certificate. Official instructions: [Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) and [custom domains](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).
