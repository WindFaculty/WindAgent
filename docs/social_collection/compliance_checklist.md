# Social Collection Compliance Checklist

This document defines the compliance requirements that **must** be satisfied
before social-source collection is run on a new platform, URL, or deployment
environment.  Each item must be reviewed and confirmed before the corresponding
gate in Phase 4 is considered closed.

---

## 1. robots.txt Compliance

| Check | Status | Notes |
|---|---|---|
| `robots.txt` retrieved and parsed for each target domain before crawl | Required | Respect `Disallow` rules for the `User-Agent` used by the pipeline |
| `Crawl-delay` directive honoured as minimum per-domain interval | Required | Value propagated to `PerDomainRateLimiter.interval_seconds` |
| `Sitemap` entries noted but not automatically followed | Recommended | Manual decision only |
| `Allow` overrides checked before rejecting a path | Required | |

> **Policy**: If `robots.txt` is unavailable (non-200 response), the pipeline
> **must not** assume open access.  A missing `robots.txt` is treated as
> *unknown* and the crawl is suspended until a human reviewer decides.

---

## 2. Platform Terms of Service

### 2.1 Facebook / Meta

| Check | Status |
|---|---|
| Collection limited to **public** pages and posts | Required |
| No scraping of private groups, private profiles, or direct messages | Required |
| No automated creation of accounts | Required |
| No extraction of personal identifying information from user profiles | Required |
| Authenticated mode used only with user-owned credentials explicitly provided | Required |
| No more than one request per 2 seconds to facebook.com domains | Required |

### 2.2 YouTube / Google

| Check | Status |
|---|---|
| Collection limited to **public** videos and public metadata | Required |
| YouTube Data API used when available instead of DOM scraping | Recommended |
| No downloading of video content (audio, video stream) | Required |
| No extraction of comment author personal data | Required |
| API quota usage tracked and quota exhaustion handled gracefully | Required |
| No more than one request per 2 seconds to youtube.com domains | Required |

### 2.3 TikTok

| Check | Status |
|---|---|
| Collection limited to **public** videos | Required |
| Region restrictions respected — `BLOCKED_BY_PLATFORM` reported, not bypassed | Required |
| No login challenge bypass, no CAPTCHA solving | Required |
| No extraction of author personal data beyond public username/handle | Required |
| No more than one request per 2 seconds to tiktok.com domains | Required |

---

## 3. Anti-Bot and CAPTCHA Policy

> **Hard requirement**: The pipeline **must never** attempt to bypass CAPTCHA,
> login walls, rate-limit challenges, or any anti-bot mechanism.  If a platform
> returns a challenge, the source is marked `BLOCKED_BY_PLATFORM` and collection
> stops for that source.

- [ ] No stealth browser plugins loaded
- [ ] No headless-detection evasion headers added
- [ ] No third-party CAPTCHA-solving services integrated
- [ ] No rotating proxies or residential proxies to bypass geo-blocks

---

## 4. Personal Data Handling

| Requirement | Implementation |
|---|---|
| Email addresses redacted from normalized records | `PersonalDataFilter._redact_string` via `_EMAIL_RE` |
| Phone numbers redacted from normalized records | `PersonalDataFilter._redact_string` via `_PHONE_RE` |
| Date-of-birth patterns not extracted from content | Out of scope by design; `text` field retains dates in published articles |
| Author names limited to public display names only | Enforced by Qwen extraction prompt ("do not infer private identity data") |
| No persistent storage of cookies or session tokens beyond run lifetime | `BrowserStateRetentionPolicy` governs TTL |
| API keys excluded from browser subprocess environment | `_SECRET_ENV_MARKERS` filter in `agent_browser.py` |

---

## 5. Data Retention Policy

| Artefact | Retention | Notes |
|---|---|---|
| Screenshot files | 30 days | Configurable via `BrowserStateRetentionPolicy` |
| `report.json` / `report.md` | 90 days | Operator may extend for archival |
| Browser state / profile directories | 7 days | Auto-cleaned by `BrowserStateManager.cleanup()` |
| Encrypted session state | 24 hours | Deleted on session close |
| Raw page text (in memory only) | Session lifetime | Not persisted to disk |

---

## 6. Collection Quota

| Limit | Default value | Config key |
|---|---|---|
| Max sources per run | 12 | `SocialResearchConfig.max_sources` |
| Max characters per source | 60,000 | `SocialResearchConfig.max_source_chars` |
| Max aggregate characters per run | 720,000 | `CollectionQuota.max_total_chars` |
| Browser timeout per source | 90 seconds | `SocialResearchConfig.browser_timeout_seconds` |

Any run that would exceed these limits is rejected with a `SocialResearchError`
**before** any browser session is opened.

---

## 7. Pre-Run Sign-Off Checklist

Before running the pipeline against a new platform or URL:

- [ ] robots.txt reviewed for target domain
- [ ] Platform ToS section above confirmed
- [ ] URL is publicly accessible without login (or authenticated mode explicitly
      enabled by human operator)
- [ ] No personal data expected in collected content; if expected, PII filter
      confirmed enabled
- [ ] Collection quota set appropriately for the run
- [ ] Rate limiter interval set to at least the robots.txt `Crawl-delay` value
- [ ] Screenshots disabled if content is sensitive
- [ ] Output directory inside workspace root confirmed

---

*Last reviewed: Phase 4 implementation — 2026-07-31*
