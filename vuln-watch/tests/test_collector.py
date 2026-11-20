"""Offline tests: feeds are mocked, so no network is needed.
    python -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collector as c  # noqa: E402

NVD_ITEM = {"cve": {
    "id": "CVE-2026-1111", "vulnStatus": "Analyzed",
    "published": "2026-11-10T10:00:00.000", "lastModified": "2026-11-12T10:00:00.000",
    "descriptions": [{"lang": "en", "value": "Apache Kafka clients allow RCE via crafted SASL config. More text."}],
    "metrics": {"cvssMetricV31": [{"type": "Primary", "cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL",
                "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}}]},
    "weaknesses": [{"description": [{"lang": "en", "value": "CWE-502"}]}],
    "configurations": [{"nodes": [{"cpeMatch": [{"vulnerable": True, "criteria": "cpe:2.3:a:apache:kafka:*:*:*:*:*:*:*:*",
                                                "versionStartIncluding": "3.0.0", "versionEndExcluding": "3.9.1"}]}]}],
    "references": [{"url": "https://kafka.apache.org/cve-list"}]}}
GHSA_ITEM = {"ghsa_id": "GHSA-aaaa-bbbb-cccc", "cve_id": "CVE-2026-1111", "summary": "Kafka client deserialization RCE",
             "description": "Long description " * 10, "severity": "critical", "published_at": "2026-11-10T00:00:00Z",
             "updated_at": "2026-11-13T00:00:00Z", "html_url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc",
             "vulnerabilities": [{"package": {"ecosystem": "maven", "name": "org.apache.kafka:kafka-clients"},
                                  "vulnerable_version_range": ">= 3.0.0, < 3.9.1", "first_patched_version": "3.9.1"}],
             "cvss": {"score": 9.8, "vector_string": "x"}, "cwes": [{"cwe_id": "CWE-502"}]}
GHSA_ONLY = dict(GHSA_ITEM, ghsa_id="GHSA-zzzz-yyyy-xxxx", cve_id=None, summary="kafkajs prototype pollution",
                 severity="moderate", cvss={"score": 0})


def fake_get(url, params=None, headers=None, **kw):
    if url.startswith(c.NVD_URL):
        return {"vulnerabilities": [NVD_ITEM] if "kafka" in str(params) else [], "totalResults": 1, "resultsPerPage": 1}, {}
    if url.startswith(c.GHSA_URL):
        if params and "kafkajs" in params.get("affects", ""):
            return [GHSA_ONLY], {}
        return ([GHSA_ITEM] if params and "kafka-clients" in params.get("affects", "") else []), {}
    if url == c.KEV_URL:
        return {"vulnerabilities": [{"cveID": "CVE-2026-1111", "dateAdded": "2026-11-14", "dueDate": "2026-12-05",
                                     "knownRansomwareCampaignUse": "Unknown"}]}, {}
    if url == c.EPSS_URL:
        return {"data": [{"cve": "CVE-2026-1111", "epss": "0.91", "percentile": "0.99"}]}, {}
    raise AssertionError(url)


class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.patches = [mock.patch.object(c, n, d / f) for n, f in
                        (("DATA_DIR", ""), ("CONFIG_PATH", "config.json"), ("VULNS_PATH", "vulns.json"), ("STATE_PATH", "state.json"))]
        for p in self.patches:
            p.start()
        self.patches.append(mock.patch.object(c, "http_get_json", side_effect=fake_get))
        self.patches.append(mock.patch.object(c.time, "sleep"))
        self.patches[-2].start(); self.patches[-1].start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def cfg(self):
        cfg = c.load_config()
        cfg["tech_stack"] = [t for t in cfg["tech_stack"] if t["id"] == "kafka"]
        return cfg

    def test_default_config_valid(self):
        self.assertEqual(c.validate_config(json.load(open(c.DEFAULT_CONFIG_PATH))), [])

    def test_scan_merges_sources_and_enriches(self):
        run = c.run_scan(self.cfg())
        self.assertEqual(run["status"], "success", run["errors"])
        vulns = c.load_store()["vulns"]
        self.assertEqual(set(vulns), {"CVE-2026-1111", "GHSA-zzzz-yyyy-xxxx"})
        v = vulns["CVE-2026-1111"]
        self.assertEqual(sorted(v["sources"]), ["GitHub", "NVD"])
        self.assertEqual(v["aliases"], ["GHSA-aaaa-bbbb-cccc"])
        self.assertEqual(v["severity"], "CRITICAL")
        self.assertEqual(v["kev"]["due_date"], "2026-12-05")
        self.assertAlmostEqual(v["epss"]["score"], 0.91)
        self.assertEqual(v["packages"][0]["patched"], "3.9.1")
        self.assertIn("apache:kafka >= 3.0.0, < 3.9.1", v["affected"])
        g = vulns["GHSA-zzzz-yyyy-xxxx"]
        self.assertEqual(g["severity"], "MEDIUM")
        self.assertIsNone(g["cvss"])
        self.assertEqual(run["new"], 2)

    def test_second_run_is_incremental_and_keeps_triage(self):
        c.run_scan(self.cfg())
        store = c.load_store()
        store["vulns"]["CVE-2026-1111"]["status"] = "mitigated"
        c.save_store(store)
        run = c.run_scan(self.cfg())
        self.assertEqual(run["new"], 0)
        self.assertEqual(c.load_store()["vulns"]["CVE-2026-1111"]["status"], "mitigated")
        self.assertEqual(len(c.load_state()["runs"]), 2)

    def test_min_cvss_filter(self):
        cfg = self.cfg()
        cfg["collection"]["min_cvss"] = 9.9
        cfg["collection"]["include_unscored"] = False
        c.run_scan(cfg)
        self.assertEqual(c.load_store()["vulns"], {})

    def test_interval_and_validation(self):
        cfg = self.cfg()
        cfg["schedule"].update(interval_value=2, interval_unit="days")
        self.assertEqual(c.interval_seconds(cfg), 172800)
        cfg["schedule"].update(interval_value=1, interval_unit="minutes")
        self.assertEqual(c.interval_seconds(cfg), 300)
        cfg["tech_stack"].append({"id": "Bad Id", "name": "", "cpes": ["foo"]})
        errs = c.validate_config(cfg)
        self.assertTrue(any("id must be" in e for e in errs) and any("cpe:2.3" in e for e in errs))

    def test_cancel(self):
        stop = threading.Event(); stop.set()
        run = c.run_scan(self.cfg(), stop)
        self.assertEqual(run["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
