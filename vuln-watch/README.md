# VulnWatch: periodic vulnerability monitor for your tech stack

VulnWatch periodically collects newly published or modified vulnerabilities for a
**configurable tech stack** from public feeds. It merges and enriches them and shows
them in a **control-centre dashboard** where you can triage them.

It uses only the Python standard library, so there is nothing to `pip install`.

```
python server.py            # → http://127.0.0.1:8085  (dashboard)  and  /config  (configuration)
```

## What it does

| Step | Source | Notes |
|---|---|---|
| Find CVEs | **NIST NVD CVE API 2.0** | Matches by CPE (precise) and/or keyword (broad), queried incrementally by last-modified date |
| Find advisories | **GitHub Advisory Database** | Matches by package, or a whole ecosystem at a chosen severity (e.g. all critical npm advisories). Gives fixed versions |
| Exploited? | **CISA KEV** | Flags vulnerabilities known to be exploited in the wild, with the federal due date and ransomware use |
| Likely exploited? | **FIRST EPSS** | Probability of exploitation in the next 30 days |
| Alert | Webhook | Teams, Slack or generic. Sent for new items ≥ a chosen severity, and for KEV items |

Records from different sources are merged by CVE id, with GHSA ids kept as aliases.
Each run only asks for records changed since the previous run, plus a small overlap window.
Your triage status, owner and notes are kept across runs.

### Default tech stack
React, JavaScript, Node.js, Python, Azure, PostgreSQL, Kafka, AKS / Kubernetes.
Each one is a set of CPEs, keywords and packages. You can edit it on the **Configuration** page,
or add more from presets (Next.js, Django, Redis, NGINX, Docker, Helm, OpenSSL, Spring, .NET, Entra ID, …).

## Pages
* **Dashboard (`/`)**
  * KPI tiles that you can click to filter: open critical, open high, known exploited, new this week, awaiting triage.
  * Charts: by severity, by tech (stacked by severity) and a 12-week trend.
  * A searchable, sortable, filterable table with bulk status updates and CSV export.
  * A detail drawer with KEV alert, CVSS, EPSS, affected and fixed versions, CWE links, references and a triage form.
* **Configuration (`/config`)**
  * Tech-stack editor: CPEs, keywords and packages for each technology.
  * Schedule interval in minutes, hours, days or weeks, with quick presets.
  * Lookback, minimum CVSS and retention settings.
  * Sources and API keys. Keys are write-only from the browser.
  * Webhook notifications.
  * Theme and font picker.
  * Scan history, run now and cancel.
  * Import and export of the configuration as JSON.
* **Theme & font selectors** are in the top bar of every page and saved per browser.
  * Themes: Midnight, Light, Dark, Dracula, Nord, Ocean, Forest, Sunset, Solarized and System (auto).
  * Fonts: Inter, Plus Jakarta Sans, Poppins, Roboto, IBM Plex Sans, Source Sans 3, Nunito, JetBrains Mono and System.

## Configuration
The first start copies `config.default.json` to `data/config.json`, and the UI edits that file.
A changed interval takes effect immediately. A tech whose queries change gets a fresh lookback.

API keys are optional but recommended. Environment variables override the stored values:

```
export NVD_API_KEY=...     # https://nvd.nist.gov/developers/request-an-api-key  (scans ~10× faster)
export GITHUB_TOKEN=...    # any token, no scopes needed (5000 req/h instead of 60)
```

Without an NVD key, NVD allows 5 requests per 30 s. The first scan of the default stack then takes a few minutes.

## Running it periodically
* **Built-in scheduler (default).** `python server.py` runs scans on the configured interval.
* **cron / systemd timer / Kubernetes CronJob instead.** Run `python server.py --no-scheduler` for the UI only, and schedule the scans separately:
  ```
  0 */6 * * *  cd /opt/vuln-watch && python3 collector.py --once
  ```
* **Docker:**
  ```
  docker build -t vulnwatch . && docker run -d -p 8085:8085 -v vulnwatch-data:/data -e NVD_API_KEY=... vulnwatch
  ```

## Security notes
* By default it binds to `127.0.0.1`, and there is no login. If you expose it on a network, put it behind
  your reverse proxy or SSO (e.g. Azure App Proxy, oauth2-proxy).
* Changes are only accepted as JSON requests, which blocks cross-site form posts. Static file paths are confined to `static/`.

## Data & API
Data is stored in `data/`: `vulns.json`, `state.json` and `config.json`. The `VULNWATCH_DATA_DIR` environment variable changes the location.

| Method | Path | |
|---|---|---|
| GET | `/api/vulns` | all records |
| PATCH | `/api/vulns/{id}` | `{status, notes, owner}` |
| PATCH | `/api/vulns` | bulk `{ids:[…], status}` |
| GET/PUT | `/api/config` | secrets are masked on GET |
| GET | `/api/status` | scheduler state + last 20 runs |
| POST | `/api/scan`, `/api/scan/cancel` | |

Triage statuses: `new`, `investigating`, `affected`, `not_affected`, `mitigated`, `resolved`, `ignored`.

## Tests
```
python -m unittest discover -s tests
```
The feeds are mocked in the tests, so no network is needed.
