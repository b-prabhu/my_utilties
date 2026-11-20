"""VulnWatch collector: pulls newly published / modified vulnerabilities for a
configurable tech stack from public feeds and merges them into a local store.

Sources
  * NVD CVE API 2.0        - CPE match (precise) and keyword search (broad)
  * GitHub Advisory DB     - package / ecosystem advisories (reviewed only)
  * CISA KEV catalog       - flags vulnerabilities known to be exploited in the wild
  * FIRST EPSS             - probability of exploitation in the next 30 days

Pure standard library; run `python collector.py --once` from cron if you do not
want the built-in scheduler in server.py.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("VULNWATCH_DATA_DIR", BASE_DIR / "data"))
CONFIG_PATH = Path(os.environ.get("VULNWATCH_CONFIG", DATA_DIR / "config.json"))
DEFAULT_CONFIG_PATH = BASE_DIR / "config.default.json"
VULNS_PATH = DATA_DIR / "vulns.json"
STATE_PATH = DATA_DIR / "state.json"

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
GHSA_URL = "https://api.github.com/advisories"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"

SEVERITY_ORDER = ["UNKNOWN", "NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
TRIAGE_STATES = ["new", "investigating", "affected", "not_affected", "mitigated", "resolved", "ignored"]
USER_AGENT = "VulnWatch/1.0 (+self-hosted vulnerability monitor)"

log = logging.getLogger("vulnwatch")
_store_lock = threading.RLock()


# --------------------------------------------------------------------------- utils
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        try:
            dt = datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return copy.deepcopy(default)
    except json.JSONDecodeError:
        log.error("Corrupt JSON in %s - starting from default", path)
        return copy.deepcopy(default)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=False)
    os.replace(tmp, path)


def norm_severity(value) -> str:
    if not value:
        return "UNKNOWN"
    v = str(value).upper()
    if v == "MODERATE":
        return "MEDIUM"
    return v if v in SEVERITY_ORDER else "UNKNOWN"


def severity_from_score(score) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    if score > 0:
        return "LOW"
    return "NONE"


def sev_rank(sev: str) -> int:
    try:
        return SEVERITY_ORDER.index(sev)
    except ValueError:
        return 0


# --------------------------------------------------------------------------- config
def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config() -> dict:
    default = read_json(DEFAULT_CONFIG_PATH, {})
    if not CONFIG_PATH.exists():
        write_json(CONFIG_PATH, default)
        return default
    return deep_merge(default, read_json(CONFIG_PATH, {}))


def interval_seconds(cfg: dict) -> int:
    sched = cfg.get("schedule", {})
    value = max(float(sched.get("interval_value", 6) or 6), 0.1)
    unit = sched.get("interval_unit", "hours")
    mult = {"minutes": 60, "hours": 3600, "days": 86400, "weeks": 604800}.get(unit, 3600)
    return max(int(value * mult), 300)  # never more often than every 5 minutes


def validate_config(cfg: dict) -> list[str]:
    errors = []
    sched = cfg.get("schedule", {})
    if sched.get("interval_unit") not in ("minutes", "hours", "days", "weeks"):
        errors.append("schedule.interval_unit must be minutes, hours, days or weeks")
    try:
        if float(sched.get("interval_value", 0)) <= 0:
            errors.append("schedule.interval_value must be > 0")
    except (TypeError, ValueError):
        errors.append("schedule.interval_value must be a number")
    seen = set()
    for i, t in enumerate(cfg.get("tech_stack", [])):
        tid = (t.get("id") or "").strip()
        if not tid or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", tid):
            errors.append(f"tech_stack[{i}].id must be lowercase letters, digits, - or _")
        if tid in seen:
            errors.append(f"duplicate tech id '{tid}'")
        seen.add(tid)
        if not (t.get("name") or "").strip():
            errors.append(f"tech_stack[{i}].name is required")
        for c in t.get("cpes", []):
            if not str(c).startswith("cpe:2.3:"):
                errors.append(f"{tid}: CPE '{c}' must start with cpe:2.3:")
        if not (t.get("cpes") or t.get("keywords") or t.get("packages")):
            errors.append(f"{tid}: add at least one CPE, keyword or package")
    return errors


# --------------------------------------------------------------------------- http
class HttpError(Exception):
    pass


def http_get_json(url: str, params: dict | None = None, headers: dict | None = None,
                  retries: int = 4, timeout: int = 60):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, safe=":,")
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    hdrs.update(headers or {})
    delay = 6
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                return json.loads(body.decode("utf-8")), dict(resp.headers)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 500, 502, 503, 504) and attempt < retries - 1:
                log.warning("HTTP %s from %s - retrying in %ss", e.code, url.split("?")[0], delay)
                time.sleep(delay)
                delay *= 2
                continue
            raise HttpError(f"HTTP {e.code} for {url.split('?')[0]}: {e.read()[:200]!r}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < retries - 1:
                log.warning("Network error %s - retrying in %ss", e, delay)
                time.sleep(delay)
                delay *= 2
                continue
            raise HttpError(f"Network error for {url.split('?')[0]}: {e}") from e
    raise HttpError("unreachable")


# --------------------------------------------------------------------------- NVD
def _nvd_metrics(metrics: dict):
    for key, ver in (("cvssMetricV40", "4.0"), ("cvssMetricV31", "3.1"),
                     ("cvssMetricV30", "3.0"), ("cvssMetricV2", "2.0")):
        items = metrics.get(key) or []
        if not items:
            continue
        primary = next((m for m in items if m.get("type") == "Primary"), items[0])
        data = primary.get("cvssData", {})
        score = data.get("baseScore")
        sev = data.get("baseSeverity") or primary.get("baseSeverity") or severity_from_score(score)
        return score, norm_severity(sev), data.get("vectorString"), ver
    return None, "UNKNOWN", None, None


def _nvd_affected(configurations: list, cpe_prefixes: list[str]) -> list[str]:
    out = []
    for conf in configurations or []:
        for node in conf.get("nodes", []):
            for m in node.get("cpeMatch", []):
                if not m.get("vulnerable"):
                    continue
                crit = m.get("criteria", "")
                parts = crit.split(":")
                if len(parts) < 6:
                    continue
                if cpe_prefixes and not any(crit.startswith(p) for p in cpe_prefixes):
                    continue
                product = f"{parts[3]}:{parts[4]}"
                rng = []
                if m.get("versionStartIncluding"):
                    rng.append(f">= {m['versionStartIncluding']}")
                if m.get("versionStartExcluding"):
                    rng.append(f"> {m['versionStartExcluding']}")
                if m.get("versionEndIncluding"):
                    rng.append(f"<= {m['versionEndIncluding']}")
                if m.get("versionEndExcluding"):
                    rng.append(f"< {m['versionEndExcluding']}")
                if not rng and parts[5] not in ("*", "-"):
                    rng.append(f"= {parts[5]}")
                txt = f"{product} {', '.join(rng)}".strip()
                if txt not in out:
                    out.append(txt)
    return out[:25]


def nvd_to_record(item: dict, tech_id: str, cpe_prefixes: list[str]) -> dict | None:
    cve = item.get("cve", {})
    if cve.get("vulnStatus") == "Rejected":
        return None
    desc = next((d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"), "")
    score, sev, vector, ver = _nvd_metrics(cve.get("metrics", {}))
    cwes = []
    for w in cve.get("weaknesses", []):
        for d in w.get("description", []):
            v = d.get("value")
            if v and v.startswith("CWE-") and v not in cwes:
                cwes.append(v)
    refs = [r.get("url") for r in cve.get("references", []) if r.get("url")]
    cid = cve.get("id")
    return {
        "id": cid,
        "cve": cid,
        "aliases": [],
        "title": (desc.split(". ")[0][:180] if desc else cid),
        "description": desc,
        "severity": sev,
        "cvss": score,
        "cvss_version": ver,
        "vector": vector,
        "cwes": cwes,
        "published": cve.get("published"),
        "modified": cve.get("lastModified"),
        "references": refs[:30] + [f"https://nvd.nist.gov/vuln/detail/{cid}"],
        "affected": _nvd_affected(cve.get("configurations", []), cpe_prefixes),
        "packages": [],
        "techs": [tech_id],
        "sources": ["NVD"],
        "nvd_status": cve.get("vulnStatus"),
    }


def fetch_nvd(tech: dict, since: datetime, until: datetime, api_key: str, stop: threading.Event):
    headers = {"apiKey": api_key} if api_key else {}
    pause = 0.8 if api_key else 6.5  # NVD: 50 req/30s with key, 5 req/30s without
    queries = [("virtualMatchString", c) for c in tech.get("cpes", []) if c] + \
              [("keywordSearch", k) for k in tech.get("keywords", []) if k]
    cpe_prefixes = [c for c in tech.get("cpes", []) if c]
    results = []
    for param, value in queries:
        window_start = since
        while window_start < until and not stop.is_set():
            window_end = min(window_start + timedelta(days=119), until)  # NVD max range is 120 days
            start_index = 0
            while not stop.is_set():
                params = {
                    param: value,
                    "lastModStartDate": window_start.strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
                    "lastModEndDate": window_end.strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
                    "resultsPerPage": 2000,
                    "startIndex": start_index,
                }
                # keywordExactMatch is a value-less flag, so it goes on the URL directly
                base = NVD_URL + "?keywordExactMatch" if param == "keywordSearch" and " " in value else NVD_URL
                data, _ = http_get_json(base, params, headers)
                time.sleep(pause)
                for item in data.get("vulnerabilities", []):
                    rec = nvd_to_record(item, tech["id"], cpe_prefixes if param == "virtualMatchString" else [])
                    if rec:
                        results.append(rec)
                total = data.get("totalResults", 0)
                start_index += data.get("resultsPerPage", 0) or 2000
                if start_index >= total:
                    break
            window_start = window_end
    return results


# --------------------------------------------------------------------------- GitHub advisories
def _next_link(headers: dict) -> str | None:
    link = headers.get("Link") or headers.get("link") or ""
    m = re.search(r'<([^>]+)>;\s*rel="next"', link)
    return m.group(1) if m else None


def ghsa_to_record(adv: dict, tech_id: str) -> dict | None:
    if adv.get("withdrawn_at"):
        return None
    cvss = adv.get("cvss") or {}
    score, vector, ver = cvss.get("score"), cvss.get("vector_string"), None
    sevs = adv.get("cvss_severities") or {}
    for key, v in (("cvss_v4", "4.0"), ("cvss_v3", "3.1")):
        s = sevs.get(key) or {}
        if s.get("score"):
            score, vector, ver = s["score"], s.get("vector_string"), v
            break
    if score == 0:
        score = None
    pkgs = []
    for v in adv.get("vulnerabilities", []) or []:
        p = v.get("package") or {}
        fp = v.get("first_patched_version")
        if isinstance(fp, dict):
            fp = fp.get("identifier")
        pkgs.append({
            "ecosystem": p.get("ecosystem"),
            "name": p.get("name"),
            "vulnerable": v.get("vulnerable_version_range"),
            "patched": fp,
        })
    epss = None
    for e in adv.get("epss") or []:
        if e.get("percentage") is not None:
            epss = {"score": float(e["percentage"]), "percentile": float(e.get("percentile") or 0)}
    gid = adv.get("ghsa_id")
    cve = adv.get("cve_id")
    refs = [r for r in (adv.get("references") or []) if isinstance(r, str)]
    return {
        "id": cve or gid,
        "cve": cve,
        "aliases": [gid] if cve else [],
        "title": adv.get("summary") or gid,
        "description": adv.get("description") or adv.get("summary") or "",
        "severity": norm_severity(adv.get("severity")),
        "cvss": score,
        "cvss_version": ver,
        "vector": vector,
        "cwes": [c.get("cwe_id") for c in adv.get("cwes") or [] if c.get("cwe_id")],
        "published": adv.get("published_at"),
        "modified": adv.get("updated_at"),
        "references": [adv.get("html_url")] + refs[:30],
        "affected": [],
        "packages": pkgs,
        "techs": [tech_id],
        "sources": ["GitHub"],
        "epss": epss,
    }


def fetch_github(tech: dict, since: datetime, token: str, stop: threading.Event):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    results = []
    for pkg in tech.get("packages", []):
        if stop.is_set():
            break
        params = {"type": "reviewed", "per_page": 100, "modified": f">={since.strftime('%Y-%m-%d')}"}
        if pkg.get("ecosystem"):
            params["ecosystem"] = pkg["ecosystem"]
        if pkg.get("name"):
            params["affects"] = pkg["name"]
        if pkg.get("severity"):
            params["severity"] = pkg["severity"]
        url, first = GHSA_URL, True
        pages = 0
        while url and not stop.is_set() and pages < 20:
            data, hdrs = http_get_json(url, params if first else None, headers)
            first = False
            pages += 1
            for adv in data or []:
                rec = ghsa_to_record(adv, tech["id"])
                if rec:
                    results.append(rec)
            url = _next_link(hdrs)
            time.sleep(0.5 if token else 1.5)
    return results


# --------------------------------------------------------------------------- enrichment
def fetch_kev() -> dict:
    data, _ = http_get_json(KEV_URL, timeout=120)
    out = {}
    for v in data.get("vulnerabilities", []):
        out[v.get("cveID")] = {
            "date_added": v.get("dateAdded"),
            "due_date": v.get("dueDate"),
            "ransomware": v.get("knownRansomwareCampaignUse"),
            "action": v.get("requiredAction"),
            "name": v.get("vulnerabilityName"),
        }
    return out


def fetch_epss(cves: list[str]) -> dict:
    out = {}
    for i in range(0, len(cves), 100):
        chunk = cves[i:i + 100]
        data, _ = http_get_json(EPSS_URL, {"cve": ",".join(chunk)})
        for row in data.get("data", []):
            out[row["cve"]] = {"score": float(row.get("epss") or 0), "percentile": float(row.get("percentile") or 0)}
        time.sleep(0.5)
    return out


# --------------------------------------------------------------------------- store
def load_store() -> dict:
    with _store_lock:
        return read_json(VULNS_PATH, {"vulns": {}})


def save_store(store: dict) -> None:
    with _store_lock:
        write_json(VULNS_PATH, store)


def load_state() -> dict:
    return read_json(STATE_PATH, {"cursors": {}, "runs": []})


def save_state(state: dict) -> None:
    write_json(STATE_PATH, state)


def _union(a: list, b: list) -> list:
    out = list(a or [])
    for x in b or []:
        if x and x not in out:
            out.append(x)
    return out


def merge_record(existing: dict | None, new: dict, now: str) -> tuple[dict, bool]:
    """Merge `new` into `existing`. Returns (record, is_new)."""
    if existing is None:
        rec = dict(new)
        rec.update({"first_seen": now, "last_seen": now, "status": "new", "notes": "",
                    "status_updated": None, "kev": None, "epss": new.get("epss")})
        return rec, True
    rec = existing
    rec["last_seen"] = now
    rec["techs"] = _union(rec.get("techs"), new.get("techs"))
    rec["sources"] = _union(rec.get("sources"), new.get("sources"))
    rec["aliases"] = _union(rec.get("aliases"), new.get("aliases"))
    rec["references"] = _union(rec.get("references"), new.get("references"))[:40]
    rec["affected"] = _union(rec.get("affected"), new.get("affected"))[:30]
    rec["cwes"] = _union(rec.get("cwes"), new.get("cwes"))
    known = {(p.get("ecosystem"), p.get("name"), p.get("vulnerable")) for p in rec.get("packages", [])}
    for p in new.get("packages", []):
        if (p.get("ecosystem"), p.get("name"), p.get("vulnerable")) not in known:
            rec.setdefault("packages", []).append(p)
    if new.get("cvss") is not None and (rec.get("cvss") is None or "NVD" in new.get("sources", [])):
        rec["cvss"], rec["vector"], rec["cvss_version"] = new["cvss"], new.get("vector"), new.get("cvss_version")
    if sev_rank(new.get("severity", "UNKNOWN")) > sev_rank(rec.get("severity", "UNKNOWN")) or rec.get("severity") == "UNKNOWN":
        rec["severity"] = new.get("severity", rec.get("severity"))
    if len(new.get("description") or "") > len(rec.get("description") or ""):
        rec["description"] = new["description"]
    if "GitHub" in new.get("sources", []) and new.get("title"):
        rec["title"] = new["title"]  # GHSA summaries are human-written
    if new.get("epss") and not rec.get("epss"):
        rec["epss"] = new["epss"]
    for k in ("published", "nvd_status"):
        if new.get(k) and not rec.get(k):
            rec[k] = new[k]
    if (new.get("modified") or "") > (rec.get("modified") or ""):
        rec["modified"] = new["modified"]
    return rec, False


def passes_filter(rec: dict, cfg: dict) -> bool:
    col = cfg.get("collection", {})
    if rec.get("cvss") is None:
        return bool(col.get("include_unscored", True))
    return float(rec["cvss"]) >= float(col.get("min_cvss", 0) or 0)


# --------------------------------------------------------------------------- notifications
def notify(cfg: dict, new_recs: list[dict]) -> None:
    n = cfg.get("notifications", {})
    url = (n.get("webhook_url") or "").strip()
    if not url or not new_recs:
        return
    floor = sev_rank(n.get("min_severity", "CRITICAL"))
    hits = [r for r in new_recs if sev_rank(r.get("severity")) >= floor or (n.get("kev_always") and r.get("kev"))]
    if not hits:
        return
    hits.sort(key=lambda r: (-sev_rank(r.get("severity")), -(r.get("cvss") or 0)))
    lines = [f"VulnWatch: {len(hits)} new vulnerabilities need attention"]
    for r in hits[:15]:
        kev = " [KNOWN EXPLOITED]" if r.get("kev") else ""
        lines.append(f"- {r['severity']} {r['id']} ({', '.join(r.get('techs', []))}) "
                     f"CVSS {r.get('cvss') or 'n/a'}{kev}: {r.get('title', '')[:120]}")
    body = json.dumps({"text": "\n".join(lines)}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:  # noqa: BLE001 - notification failure must not fail the run
        log.warning("Webhook notification failed: %s", e)


# --------------------------------------------------------------------------- run
def run_scan(cfg: dict | None = None, stop: threading.Event | None = None, progress=None) -> dict:
    cfg = cfg or load_config()
    stop = stop or threading.Event()
    progress = progress or (lambda msg: None)
    started = utcnow()
    state = load_state()
    cursors = state.setdefault("cursors", {})
    col = cfg.get("collection", {})
    src = cfg.get("sources", {})
    overlap = timedelta(hours=float(col.get("overlap_hours", 2)))
    lookback = timedelta(days=int(col.get("initial_lookback_days", 90)))
    nvd_key = os.environ.get("NVD_API_KEY") or src.get("nvd", {}).get("api_key", "")
    gh_token = os.environ.get("GITHUB_TOKEN") or src.get("github", {}).get("token", "")

    run = {"started": iso(started), "finished": None, "status": "running", "errors": [],
           "fetched": 0, "new": 0, "updated": 0, "per_tech": {}}
    collected: list[dict] = []
    techs = [t for t in cfg.get("tech_stack", []) if t.get("enabled", True)]

    for tech in techs:
        if stop.is_set():
            break
        tid = tech["id"]
        run["per_tech"][tid] = 0
        for source, enabled in (("nvd", src.get("nvd", {}).get("enabled", True)),
                                ("github", src.get("github", {}).get("enabled", True))):
            if not enabled or stop.is_set():
                continue
            if source == "nvd" and not (tech.get("cpes") or tech.get("keywords")):
                continue
            if source == "github" and not tech.get("packages"):
                continue
            key = f"{tid}:{source}:{_fingerprint(tech, source)}"
            last = parse_dt(cursors.get(key))
            since = (last - overlap) if last else (started - lookback)
            progress(f"{tech['name']}: querying {source.upper()} since {since:%Y-%m-%d %H:%M}")
            try:
                recs = fetch_nvd(tech, since, started, nvd_key, stop) if source == "nvd" \
                    else fetch_github(tech, since, gh_token, stop)
                collected.extend(recs)
                run["per_tech"][tid] += len(recs)
                if not stop.is_set():
                    cursors[key] = iso(started)
            except Exception as e:  # noqa: BLE001
                msg = f"{tech['name']} / {source}: {e}"
                log.error(msg)
                run["errors"].append(msg)

    progress("Merging results")
    now = iso(utcnow())
    new_recs = []
    with _store_lock:
        store = load_store()
        vulns = store.setdefault("vulns", {})
        alias_index = {a: k for k, v in vulns.items() for a in v.get("aliases", [])}
        touched = set()
        for rec in collected:
            if not passes_filter(rec, cfg):
                continue
            key = rec["id"]
            # A GHSA-only record may later gain a CVE id (or vice-versa) - reconcile.
            if key not in vulns:
                for a in [key] + rec.get("aliases", []):
                    if a in alias_index:
                        key = alias_index[a]
                        break
            merged, is_new = merge_record(vulns.get(key), rec, now)
            vulns[key] = merged
            for a in merged.get("aliases", []):
                alias_index[a] = key
            if key not in touched:
                touched.add(key)
                if is_new:
                    run["new"] += 1
                    new_recs.append(merged)
                else:
                    run["updated"] += 1
        run["fetched"] = len(collected)

        if src.get("cisa_kev", {}).get("enabled", True) and not stop.is_set():
            progress("Checking CISA Known Exploited Vulnerabilities catalog")
            try:
                kev = fetch_kev()
                for k, v in vulns.items():
                    cve = v.get("cve") or (k if k.startswith("CVE-") else None)
                    v["kev"] = kev.get(cve) if cve else None
                state["kev_checked"] = now
            except Exception as e:  # noqa: BLE001
                run["errors"].append(f"CISA KEV: {e}")

        if src.get("epss", {}).get("enabled", True) and not stop.is_set():
            # refresh scores for anything seen this run plus open items from the last 30 days
            cutoff = iso(utcnow() - timedelta(days=30))
            cves = sorted({v["cve"] for k, v in vulns.items() if v.get("cve") and
                           (k in touched or (v.get("status") in ("new", "investigating", "affected")
                                             and (v.get("published") or "") >= cutoff))})
            if cves:
                progress(f"Fetching EPSS scores for {len(cves)} CVEs")
                try:
                    scores = fetch_epss(cves)
                    for k, v in vulns.items():
                        if v.get("cve") in scores:
                            v["epss"] = scores[v["cve"]]
                except Exception as e:  # noqa: BLE001
                    run["errors"].append(f"EPSS: {e}")

        retention = int(col.get("retention_days", 365) or 0)
        if retention:
            cutoff = iso(utcnow() - timedelta(days=retention))
            for k in [k for k, v in vulns.items()
                      if (v.get("last_seen") or "") < cutoff and v.get("status") in ("resolved", "ignored", "not_affected")]:
                del vulns[k]
        store["updated"] = now
        save_store(store)

    try:
        notify(cfg, new_recs)
    except Exception as e:  # noqa: BLE001
        log.warning("notify failed: %s", e)

    run["finished"] = iso(utcnow())
    run["status"] = "cancelled" if stop.is_set() else ("partial" if run["errors"] else "success")
    run["duration_s"] = round((utcnow() - started).total_seconds(), 1)
    state["runs"] = ([run] + state.get("runs", []))[:50]
    state["last_run"] = run["finished"]
    save_state(state)
    progress("Done")
    return run


def _fingerprint(tech: dict, source: str) -> str:
    """Cursor key changes when the queries change, so edited techs get a fresh lookback."""
    if source == "nvd":
        basis = sorted(tech.get("cpes", [])) + sorted(tech.get("keywords", []))
    else:
        basis = sorted(json.dumps(p, sort_keys=True) for p in tech.get("packages", []))
    import hashlib
    return hashlib.sha1("|".join(basis).encode()).hexdigest()[:10]


def main():
    ap = argparse.ArgumentParser(description="VulnWatch collector")
    ap.add_argument("--once", action="store_true", help="run a single scan and exit")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.once:
        result = run_scan(progress=lambda m: log.info(m))
        print(json.dumps(result, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
