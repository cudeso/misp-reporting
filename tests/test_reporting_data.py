"""Pins the counts on the summary and curation reports against a synthetic MISP.

The fake MISP below applies the filters the reports rely on (publication state, timestamp ranges,
pagination, metadata, event IDs) so the counts can be compared with known answers.

Run on its own from the repository root with:
    python -m unittest tests.test_reporting_data
"""
import copy
import logging
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import clsReportingData  # noqa: E402

NOW = 1_760_000_000
DAY = 86400

CONFIG = {
    "reporting_period": "30d",
    "reporting_filter": None,
    "reporting_trending_count": 3,
    "reporting_filter_attribute_type_ids": True,
    "reporting_filter_timestamp": "published",
    "reporting_filter_published": True,
    "log_incomplete": False,
    "misp_url": "https://misp.test",
    "misp_verifycert": True,
    "misp_key": "test",
    "misp_page_size": 2,
    "misp_timeout": 300,
    "cve_timeout": 10,
    "reporting_vulnerabilities": True,
    "reporting_geo_targeting": True,
    "misp_infrastructure_monitor": [],
    "cve_url": "https://cve.test/api/cve/",
    "attribute_summary": {"network": ["ip-src", "ip-dst"], "hashes": ["sha256", "md5"], "vulnerability": ["vulnerability"]},
    "attribute_other": "Other",
    "key_organisations": {},
    "threatlevel_key_mapping": {'1': 'High', '2': 'Medium', '3': 'Low', '4': 'Undefined'},
    "workflow_complete": "workflow:state=\"complete\"",
    "workflow_incomplete": "workflow:state=\"incomplete\"",
    "workflow_rejected": "workflow:state=\"rejected\"",
    "filter_sector": "misp-galaxy:sector",
    "filter_geo": "misp-galaxy:target-information",
    "filter_ttp_actors": ["misp-galaxy:threat-actor"],
    "filter_ttp_pattern": ["misp-galaxy:mitre-attack-pattern"],
}


def attribute(attr_type, to_ids, value="x"):
    return {"type": attr_type, "to_ids": to_ids, "value": value}


def event(event_id, age, published=True, attributes=(), objects=(), tags=(), threat_level="2", date="2025-10-01"):
    return {"Event": {"id": str(event_id), "date": date, "info": "Event {}".format(event_id),
                      "published": published, "publish_timestamp": str(NOW - age),
                      "timestamp": str(NOW - age), "threat_level_id": threat_level,
                      "attribute_count": str(len(attributes) + sum(len(o) for o in objects)),
                      "Orgc": {"name": "Org {}".format(event_id % 2), "uuid": "uuid-{}".format(event_id % 2), "id": str(event_id % 2)},
                      "Attribute": list(attributes),
                      "Object": [{"Attribute": list(o)} for o in objects],
                      "Tag": [{"name": t} for t in tags]}}


class FakeMISP:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def _in_range(self, value, date_filter):
        start, end = date_filter if isinstance(date_filter, (list, tuple)) else (date_filter, None)
        return int(value) >= start and (end is None or int(value) <= end)

    def _attributes(self, event_ids):
        for e in self.events:
            if e["Event"]["id"] in event_ids:
                yield from e["Event"]["Attribute"] + [a for o in e["Event"]["Object"] for a in o["Attribute"]]

    def search(self, controller, **params):
        self.calls.append(dict(params, controller=controller))
        if controller == "attributes":
            found = [mock.Mock(value=a["value"]) for a in self._attributes(params["eventid"]) if a["type"] == params["type_attribute"]]
            page, limit = params["page"], params["limit"]
            return found[(page - 1) * limit:page * limit]
        result = []
        for e in self.events:
            ev = e["Event"]
            if params.get("published") is not None and ev["published"] != params["published"]:
                continue
            if "publish_timestamp" in params and not self._in_range(ev["publish_timestamp"], params["publish_timestamp"]):
                continue
            if "timestamp" in params and not self._in_range(ev["timestamp"], params["timestamp"]):
                continue
            result.append(e)
        page, limit = params["page"], params["limit"]
        result = copy.deepcopy(result[(page - 1) * limit:page * limit])
        if params.get("metadata"):
            for e in result:
                del e["Event"]["Attribute"]
                del e["Event"]["Object"]
        return result

    def direct_call(self, url, query):
        assert url == "attributes/restSearch" and query["returnFormat"] == "count"
        self.calls.append(dict(query, controller="count"))
        return sum(1 for a in self._attributes(query["eventid"])
                   if (not query.get("to_ids") or a["to_ids"]) and (not query.get("type") or a["type"] in query["type"]))


def make_data(events, **config_overrides):
    config = dict(CONFIG, **config_overrides)
    fake = FakeMISP(events)
    with mock.patch.object(clsReportingData, "PyMISP", return_value=fake), \
         mock.patch.object(clsReportingData.time, "time", return_value=NOW):
        data = clsReportingData.ReportingData(config, logging.getLogger("test"))
    return data, fake


# Ages in seconds before NOW. Event 3 sits exactly on the 30d boundary, event 6 on the 60d boundary.
EVENTS = [
    event(1, 3600, attributes=[attribute("ip-src", True), attribute("md5", False)],
          objects=[[attribute("sha256", True), attribute("ip-dst", True)]],
          tags=["tlp:white", "TLP:CLEAR", "tlp: white", "workflow:state=\"complete\""], threat_level="1"),
    event(2, 2 * DAY, attributes=[attribute("vulnerability", True, "CVE-2025-0001")], tags=["tlp:ex:nakd"]),
    event(3, 30 * DAY, attributes=[attribute("domain", True)], tags=["tlp:amber", "tlp:green"]),
    event(4, 30 * DAY + 1, attributes=[attribute("ip-src", True), attribute("ip-src", False)]),
    event(5, 45 * DAY, objects=[[attribute("md5", True)]]),
    event(6, 60 * DAY, attributes=[attribute("url", False)]),
    event(7, 61 * DAY, attributes=[attribute("url", True)]),
    event(8, 95 * DAY, attributes=[attribute("url", True)]),
    event(9, 5 * DAY, published=False, attributes=[attribute("url", True)]),
]


class SummaryCountsTest(unittest.TestCase):
    def setUp(self):
        self.data, self.fake = make_data(EVENTS)
        self.data.get_today_events_attributes()
        self.data.get_trending_events_attributes()

    def test_last_24h(self):
        self.assertEqual(self.data.data["today-events"], 1)
        self.assertEqual(self.data.data["today-attributes"], 4)
        self.assertEqual(self.data.data["today-attributes_ids"], 3)

    def test_reporting_period_includes_its_boundary_and_skips_unpublished(self):
        self.assertEqual(self.data.data["trending-events"][0], 3)
        self.assertEqual(self.data.data["trending-attributes"][0], 6)
        self.assertEqual(self.data.data["trending-attributes_ids"][0], 5)

    def test_trend_periods_do_not_overlap(self):
        self.assertEqual(self.data.data["trending-events"], {0: 3, 30: 3, 60: 1})
        self.assertEqual(self.data.data["trending-attributes"], {0: 6, 30: 4, 60: 1})
        self.assertEqual(self.data.data["trending-attributes_ids"], {0: 5, 30: 2, 60: 1})

    def test_current_period_without_older_periods(self):
        data, _ = make_data(EVENTS, reporting_trending_count=0)
        data.get_trending_events_attributes()
        self.assertEqual(data.data["trending-events"], {0: 3})
        self.assertEqual(data.data["trending-attributes"], {0: 6})

    def test_events_are_only_fetched_as_metadata(self):
        event_searches = [call for call in self.fake.calls if call["controller"] == "events"]
        self.assertTrue(event_searches)
        self.assertTrue(all(call.get("metadata") for call in event_searches))
        self.assertTrue(all(call.get("excludeGalaxy") and call.get("noShadowAttributes") for call in event_searches))

    def test_statistics_json_reports_event_count(self):
        self.data.data["statistics"] = {"event_count": 0, "attribute_count": 0, "user_count": 0, "org_count": 0, "local_org_count": 0}
        self.data.get_statistics_attributes()
        self.data.get_misp_statistics()
        self.assertEqual(self.data.today_statistics["today_event_count"], 1)
        self.assertEqual(self.data.today_statistics["today_attribute_count"], 4)


class DistributionTest(unittest.TestCase):
    def test_attribute_types_only_count_to_ids(self):
        data, _ = make_data(EVENTS)
        data.get_statistics_attributes()
        self.assertEqual(data.data["statistics-attributes"],
                         {"network": [2, 2], "hashes": [1, 1], "vulnerability": [1, 0], "Other": [1, 0]})

    def test_attribute_types_all_attributes_and_overlapping_groups(self):
        summary = {"network": ["ip-src", "ip-dst"], "hashes": ["md5", "sha256", "md5", "ip-src"], "empty": []}
        data, _ = make_data(EVENTS, reporting_filter_attribute_type_ids=False, attribute_summary=summary)
        data.get_statistics_attributes()
        self.assertEqual(data.data["statistics-attributes"], {"network": [2, 2], "hashes": [2, 2], "Other": [2, 0]})

    def test_key_organisations(self):
        data, _ = make_data(EVENTS, key_organisations={"uuid-1": {"logo": "x.png"}, "uuid-9": {"logo": "y.png"}})
        data.get_statistics_keyorgs()
        self.assertEqual(data.data["statistics-keyorgs"]["uuid-1"],
                         {"reporting-period": {"events": 2, "attributes": 5, "attributes_ids": 4},
                          "today": {"events": 1, "attributes": 4, "attributes_ids": 3}})
        self.assertEqual(data.data["statistics-keyorgs"]["uuid-9"]["reporting-period"], {"events": 0, "attributes": 0, "attributes_ids": 0})

    def test_threat_level(self):
        data, _ = make_data(EVENTS)
        data.get_threatlevel()
        self.assertEqual(data.data["statistics-threatlevel"], {"1": 1, "2": 2, "3": 0, "4": 0})

    def test_tlp_counts_each_event_once_per_level(self):
        data, _ = make_data(EVENTS)
        data.get_tlplevel()
        tlp = data.data["statistics-tlp"]
        self.assertNotIn("tlp: white", tlp)
        self.assertEqual(tlp["tlp:clear"], 1)
        self.assertEqual(tlp["tlp:ex:nakd"], 1)
        self.assertEqual(tlp["tlp:amber"], 1)
        self.assertEqual(tlp["tlp:green"], 1)
        self.assertEqual(tlp["no tlp"], 0)


class VulnerabilitiesTest(unittest.TestCase):
    def test_disabled_skips_lookups(self):
        data, _ = make_data(EVENTS, reporting_vulnerabilities=False)
        with mock.patch.object(clsReportingData.requests, "get") as get:
            data.get_vulnerabilities()
        get.assert_not_called()
        self.assertEqual(data.data["vulnerabilities"], {})

    def test_enabled_uses_timeout(self):
        data, _ = make_data(EVENTS)
        with mock.patch.object(clsReportingData.requests, "get", side_effect=OSError("offline")) as get:
            data.get_vulnerabilities()
        self.assertEqual(get.call_args.kwargs["timeout"], 10)
        self.assertEqual(get.call_args.args[0], "https://cve.test/api/cve/CVE-2025-0001")
        self.assertEqual(data.data["vulnerabilities"]["CVE-2025-0001"]["cvss3"], "?")


class RequestGetTest(unittest.TestCase):
    def test_url_has_single_slash(self):
        data, _ = make_data(EVENTS, misp_url="https://misp.test/")
        with mock.patch.object(clsReportingData.requests, "get") as get:
            data._request_get("/users/statistics")
        self.assertEqual(get.call_args.args[0], "https://misp.test/users/statistics")


class GeoTargetingTest(unittest.TestCase):
    def test_disabled_skips_search(self):
        data, _ = make_data(EVENTS, reporting_geo_targeting=False)
        with mock.patch.object(data, "_get_data_for_reporting_period") as get:
            data.get_target_geo()
        get.assert_not_called()
        self.assertEqual(data.data["targeting-geo"], {})


class CurationTest(unittest.TestCase):
    def test_waiting_events_sorted_most_recent_first(self):
        events = [
            event(20, 3600, threat_level="1", date="2025-09-01", tags=["admiralty-scale:source-reliability=\"a\""]),
            event(21, 7200, threat_level="1", date="2025-10-05", tags=["admiralty-scale:source-reliability=\"a\""]),
            event(22, 600, threat_level="1", date="2025-10-05"),
            event(23, 900, threat_level="1", date="2025-10-07", tags=["workflow:state=\"complete\""]),
            event(24, 3 * DAY, threat_level="1", date="2025-10-08"),
            event(25, 8 * DAY, threat_level="1", date="2025-10-09", tags=["admiralty-scale:source-reliability=\"a\""]),
        ]
        data, _ = make_data(events)
        data.get_curation()
        self.assertEqual([e["id"] for e in data.data["curation_incomplete_high"]], ["24", "22", "21", "20"])
        self.assertEqual([e["id"] for e in data.data["curation_incomplete_adm_high"]], ["21", "20"])
        self.assertEqual([e["id"] for e in data.data["curation_complete"]], ["23"])

    def test_last_7d_counts(self):
        data, _ = make_data(EVENTS)
        data.get_curation()
        self.assertEqual([e["id"] for e in data.data["curation_complete_7d"]], ["1"])
        self.assertEqual([e["id"] for e in data.data["curation_incomplete_7d"]], ["2", "9"])
        self.assertEqual([e["id"] for e in data.data["curation_incomplete_today"]], [])

    def test_rejected_events_are_not_counted(self):
        events = [
            event(30, 600, published=False, threat_level="1", tags=["workflow:state=\"rejected\"", "admiralty-scale:source-reliability=\"a\""]),
            event(31, 600, tags=["workflow:state=\"complete\"", "workflow:state=\"rejected\""]),
            event(32, 600, threat_level="1"),
        ]
        data, _ = make_data(events)
        data.get_curation()
        self.assertEqual([e["id"] for e in data.data["curation_incomplete"]], ["32"])
        self.assertEqual([e["id"] for e in data.data["curation_incomplete_high"]], ["32"])
        self.assertEqual(data.data["curation_incomplete_adm_high"], [])
        self.assertEqual(data.data["curation_complete"], [])

    def test_curation_does_not_change_published_data_used_by_contributors(self):
        data, _ = make_data(EVENTS)
        before = [e["Event"]["id"] for e in data._get_data_for_reporting_period()]
        data.get_curation()
        self.assertIn("9", [e["id"] for e in data.data["curation_incomplete"]])
        self.assertEqual([e["Event"]["id"] for e in data._get_data_for_reporting_period()], before)


class ErrorTest(unittest.TestCase):
    def test_search_error_is_raised(self):
        data, fake = make_data(EVENTS)
        fake.search = lambda controller, **params: {"errors": (403, "Authentication failed")}
        with self.assertRaises(RuntimeError):
            data._get_data_for_reporting_period()


if __name__ == "__main__":
    unittest.main()
