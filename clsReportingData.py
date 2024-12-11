import sys
import json
import requests
from datetime import datetime, timedelta
import logging
from pymisp import *
import inspect
import os
import matplotlib.pyplot as plt
from jinja2 import Template
import plotly.express as px
import matplotlib.cm as cm
import numpy as np


class ReportingData():
    def __init__(self, config, logger):
        self.filters = config["reporting_filter"]
        self.config = config
        self.logger = logger
        self.misp_headers = {"Authorization": self.config["misp_key"],  "Content-Type": "application/json", "Accept": "application/json"}
        if self.config["misp_verifycert"] is False:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.misp = PyMISP(self.config["misp_url"], self.config["misp_key"], self.config["misp_verifycert"])
        self.data = {}
        self.data_for_reporting_period = False

        self.attribute_summary = self.config["attribute_summary"]
        self.attribute_other = self.config["attribute_other"]
        self.key_organisations = self.config["key_organisations"]
        self.threatlevel_key_mapping = self.config["threatlevel_key_mapping"]

        self.workflow_complete = self.config["workflow_complete"]
        self.workflow_incomplete = self.config["workflow_incomplete"]

        self.filter_sector = self.config["filter_sector"]
        self.filter_geo = self.config["filter_geo"]

        self.filter_ttp_actors = self.config["filter_ttp_actors"]
        self.filter_ttp_pattern = self.config["filter_ttp_pattern"]

    def print(self):
        print(self.data)

    def get_statistics(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))

        statistics = self._request_get("/users/statistics")
        self.data["statistics"] = {"user_count": 0, "org_count": 0, "local_org_count": 0, "event_count": 0, "attribute_count": 0,
                                   "correlation_count": 0}
        if statistics and statistics.json().get("stats", False):
            json_statistics = statistics.json()["stats"]
            self.data["statistics"]["user_count"] = json_statistics["user_count"]
            self.data["statistics"]["org_count"] = json_statistics["org_count"]
            self.data["statistics"]["local_org_count"] = json_statistics["local_org_count"]
            self.data["statistics"]["event_count"] = json_statistics["event_count"]
            self.data["statistics"]["attribute_count"] = json_statistics["attribute_count"]
            self.data["statistics"]["correlation_count"] = json_statistics["correlation_count"]

    def get_trending_events_attributes(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))

        self.data["trending-events"] = {}
        self.data["trending-attributes"] = {}

        days = int(''.join(filter(str.isdigit, self.config["reporting_period"])))
        self.logger.debug(" Get {}".format(days))
        response = self._get_data_for_reporting_period()
        self.data["trending-events"][0] = len(response)

        attributesqt = 0
        for event in response:
            attributesqt += len(event["Event"]["Attribute"])
            for misp_object in event["Event"]["Object"]:
                attributesqt += len(misp_object["Attribute"])
        self.data["trending-attributes"][0] = attributesqt

        count = 1
        while self.config["reporting_trending_count"] > count:
            start_period = days * count
            end_period = days * (count + 1)
            timestamp_filter = ["{}d".format(start_period), "{}d".format(end_period)]
            self.logger.debug(" Get {} - {}".format(start_period, end_period))

            current_page = 1
            tmp_len = 0
            response = []
            while True:
                tmp_response = self.misp.search("events", limit=self.config["misp_page_size"], page=current_page, published=True, publish_timestamp=["{}d".format(start_period), "{}d".format(end_period)], tags=self.config["reporting_filter"])
                if len(tmp_response) > 0:
                    tmp_len = tmp_len + len(tmp_response)
                    response += tmp_response
                else:
                    break
                current_page += 1
            self.data["trending-events"][start_period] = tmp_len

            attributesqt = 0
            for event in response:
                attributesqt += len(event["Event"]["Attribute"])
                for misp_object in event["Event"]["Object"]:
                    attributesqt += len(misp_object["Attribute"])
            self.data["trending-attributes"][start_period] = attributesqt

            count += 1

    def get_statistics_attributes(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["statistics-attributes"] = {}
        response = self._get_data_for_reporting_period()
        for event in response:
            for attribute in event["Event"]["Attribute"]:
                attribute_type = self._convert_attribute_category(attribute["type"])
                if attribute_type in self.data["statistics-attributes"]:
                    self.data["statistics-attributes"][attribute_type] += 1
                else:
                    self.data["statistics-attributes"][attribute_type] = 1

    def get_statistics_keyorgs(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["statistics-keyorgs"] = {}

        org_uuid_list = list(self.key_organisations)
        if len(org_uuid_list) > 0:
            for orgc in org_uuid_list:
                if self.config["reporting_keyorgs_allevents"]:
                    self.data["statistics-keyorgs"][orgc] = {"reporting-period": {"events": 0, "attributes": 0},
                                                             "all": {"events": 0, "attributes": 0}}
                else:
                    self.data["statistics-keyorgs"][orgc] = {"reporting-period": {"events": 0, "attributes": 0},
                                                             "all": {"events": "-", "attributes": "-"}}

            response = self._get_data_for_reporting_period()
            self._process_get_statistics_keyorgs(response, "reporting-period")
            if self.config["reporting_keyorgs_allevents"]:
                tmp_reponse = []
                current_page = 1
                while True:
                    response = self.misp.search("events", limit=self.config["misp_page_size"], page=current_page, published=True, orgc=org_uuid_list, tags=self.config["reporting_filter"])
                    if len(response) > 0:
                        tmp_reponse = tmp_reponse + response
                    else:
                        break
                    current_page += 1
                self._process_get_statistics_keyorgs(tmp_reponse, "all")

    def get_threatlevel(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["statistics-threatlevel"] = {"1": 0, "2": 0, "3": 0, "4": 0}
        response = self._get_data_for_reporting_period()
        for event in response:
            threat_level_id = event["Event"]["threat_level_id"]
            self.data["statistics-threatlevel"][threat_level_id] += 1

    def get_tlplevel(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["statistics-tlp"] = {"tlp:red": 0, "tlp:amber": 0, "tlp:amber+strict": 0, "tlp:green": 0, "tlp:clear": 0, "tlp:ex:chr": 0, "tlp:unclear": 0}
        response = self._get_data_for_reporting_period()

        for event in response:
            tags = event["Event"].get("Tag", [])
            if len(tags) > 0:
                for tag in tags:
                    if tag["name"].startswith("tlp:"):
                        if tag["name"] == "tlp:white":
                            tag_tlp = "tlp:clear"
                        else:
                            tag_tlp = tag["name"]
                        self.data["statistics-tlp"][tag_tlp] += 1

    def get_eventdetails(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["detailed_events"] = []
        response = self._get_data_for_reporting_period()
        self.distribution = self.config["distribution"]
        self.analysis_state = self.config["analysis"]

        for event in response:
            process_event = False
            if self.config["reporting_eventdetails_onlykeyorgs"]:
                if event["Event"]["Orgc"]["uuid"] in self.config["key_organisations"]:
                    process_event = True
            else:
                process_event = True
            if process_event:
                tags = event["Event"].get("Tag", [])
                tag_tlp = ""
                if len(tags) > 0:
                    for tag in tags:
                        if tag["name"].startswith("tlp:"):
                            if tag["name"] == "tlp:white":
                                tag_tlp = "tlp:clear"
                            else:
                                tag_tlp = tag["name"]
                entry = {"date": event["Event"]["date"],
                         "id": event["Event"]["id"],
                         "org": event["Event"]["Orgc"]["name"],
                         "distribution": self.distribution[int(event["Event"]["distribution"])],
                         "analysis":  self.analysis_state[int(event["Event"]["analysis"])],
                         "published": event["Event"]["published"],
                         "threat_level": self.threatlevel_key_mapping[event["Event"]["threat_level_id"]],
                         "tlp": tag_tlp,
                         "info": event["Event"]["info"][:30],
                         "indicators":  event["Event"]["attribute_count"]}
                self.data["detailed_events"].append(entry)

    def get_ttp(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["ttp_pattern"] = {}
        self.data["ttp_actors"] = {}
        response = self._get_data_for_reporting_period()
        for event in response:
            tags = event["Event"].get("Tag", [])
            if len(tags) > 0:
                for tag in tags:
                    for ttp in self.filter_ttp_pattern:
                        if ttp in tag["name"]:
                            item = tag["name"].split("{}=".format(ttp))[1].replace("\"", "")
                            if item in self.data["ttp_pattern"]:
                                self.data["ttp_pattern"][item] += 1
                            else:
                                self.data["ttp_pattern"][item] = 1
                    for ttp in self.filter_ttp_actors:
                        if ttp in tag["name"]:
                            item = tag["name"].split("{}=".format(ttp))[1].replace("\"", "")
                            if item in self.data["ttp_actors"]:
                                self.data["ttp_actors"][item] += 1
                            else:
                                self.data["ttp_actors"][item] = 1

    def get_target_sector(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["targeting-sector"] = {}
        response = self._get_data_for_reporting_period()
        for event in response:
            tags = event["Event"].get("Tag", [])
            if len(tags) > 0:
                for tag in tags:
                    if self.filter_sector in tag["name"]:
                        sector = tag["name"].split("{}=".format(self.filter_sector))[1].replace("\"", "")
                        if sector in self.data["targeting-sector"]:
                            self.data["targeting-sector"][sector] += 1
                        else:
                            self.data["targeting-sector"][sector] = 1

    def get_target_geo(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["targeting-geo"] = {}
        response = self._get_data_for_reporting_period()
        for event in response:
            tags = event["Event"].get("Tag", [])
            if len(tags) > 0:
                for tag in tags:
                    if self.filter_geo in tag["name"]:
                        geo = tag["name"].split("{}=".format(self.filter_geo))[1].replace("\"", "")
                        if geo in self.data["targeting-geo"]:
                            self.data["targeting-geo"][geo] += 1
                        else:
                            self.data["targeting-geo"][geo] = 1

    def get_vulnerabilities(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["vulnerabilities"] = {}
        tmp_data = {}
        response = self._get_data_for_reporting_period()
        for event in response:
            for attribute in event["Event"]["Attribute"]:
                if attribute["type"] == "vulnerability":
                    if attribute["value"] in tmp_data:
                        tmp_data[attribute["value"]] += 1
                    else:
                        tmp_data[attribute["value"]] = 1
            for misp_object in event["Event"]["Object"]:
                for attribute in misp_object["Attribute"]:
                    if attribute["type"] == "vulnerability":
                        if attribute["value"] in tmp_data:
                            tmp_data[attribute["value"]] += 1
                        else:
                            tmp_data[attribute["value"]] = 1

        for cve in tmp_data:
            cve_url = self.config["cve_url"]
            response = requests.get(f"{cve_url}/{cve}")
            summary = ""
            cvss3 = "?"
            if response.ok:
                summary = response.json().get("summary", "")
                cvss3 = response.json().get("cvss3", "?")
            entry = {"count": tmp_data[cve], "summary": summary, "cvss3": cvss3}
            self.data["vulnerabilities"][cve] = entry

    def get_curation(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))
        self.data["curation_complete"] = []
        self.data["curation_incomplete"] = []
        self.data["curation_complete_date"] = {}
        self.data["curation_incomplete_date"] = {}
        self.data["curation_orgs_complete"] = {}
        self.data["curation_orgs_incomplete"] = {}
        self.distribution = self.config["distribution"]
        self.analysis_state = self.config["analysis"]

        # Reset to get curation data (published, and not published
        self.data_for_reporting_period = None
        response = self._get_data_for_reporting_period(published=None)

        for event in response:
            complete_event = False
            entry = {"date": event["Event"]["date"],
                     "id": event["Event"]["id"],
                     "org": event["Event"]["Orgc"]["name"],
                     "info": event["Event"]["info"][:30],
                     "indicators":  event["Event"]["attribute_count"]}
            if event["Event"]["published"]:
                tags = event["Event"].get("Tag", [])
                if len(tags) > 0:
                    for tag in tags:
                        if tag["name"] == self.workflow_complete:
                            self.data["curation_complete"].append(entry)
                            if event["Event"]["date"] in self.data["curation_complete_date"]:
                                self.data["curation_complete_date"][event["Event"]["date"]] += 1
                            else:
                                self.data["curation_complete_date"][event["Event"]["date"]] = 1
                            if event["Event"]["Orgc"]["name"] in self.data["curation_orgs_complete"]:
                                self.data["curation_orgs_complete"][event["Event"]["Orgc"]["name"]] += 1
                            else:
                                self.data["curation_orgs_complete"][event["Event"]["Orgc"]["name"]] = 1
                            complete_event = True
                            break

            if not complete_event:
                if event["Event"]["date"] in self.data["curation_incomplete_date"]:
                    self.data["curation_incomplete_date"][event["Event"]["date"]] += 1
                else:
                    self.data["curation_incomplete_date"][event["Event"]["date"]] = 1
                if event["Event"]["Orgc"]["name"] in self.data["curation_orgs_incomplete"]:
                    self.data["curation_orgs_incomplete"][event["Event"]["Orgc"]["name"]] += 1
                else:
                    self.data["curation_orgs_incomplete"][event["Event"]["Orgc"]["name"]] = 1
                self.data["curation_incomplete"].append(entry)

    def get_infrastructure(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))

    def _process_get_statistics_keyorgs(self, response, period):
        for event in response:
            orgc = event["Event"]["Orgc"]["uuid"]
            if self.key_organisations.get(orgc, False):
                attributesqt = len(event["Event"]["Attribute"])
                for misp_object in event["Event"]["Object"]:
                    attributesqt += len(misp_object["Attribute"])

                self.data["statistics-keyorgs"][orgc][period]["events"] += 1
                self.data["statistics-keyorgs"][orgc][period]["attributes"] += attributesqt

    def _get_data_for_reporting_period(self, published=True):
        response = []
        if not self.data_for_reporting_period:
            current_page = 1
            while True:
                tmp_reponse = self.misp.search("events", limit=self.config["misp_page_size"], page=current_page, published=published, publish_timestamp=self.config["reporting_period"], tags=self.config["reporting_filter"])
                if len(tmp_reponse) > 0:
                    response = response + tmp_reponse
                else:
                    break
                current_page += 1
            self.data_for_reporting_period = response
        return self.data_for_reporting_period

    def _convert_attribute_category(self, category):
        found_key = None
        for key, values in self.attribute_summary.items():
            if category in values:
                found_key = key
                break
        if found_key:
            return found_key
        return self.attribute_other

    def _request_get(self, endpoint):
        response = requests.get("{}/{}".format(self.config["misp_url"], endpoint), headers=self.misp_headers, verify=self.config["misp_verifycert"])
        if response.ok:
            return response
        elif 400 <= response.status_code < 500:
            self.logger.error(f"[{response.status_code}] Client Error: {response.reason}")
        elif 500 <= response.status_code < 600:
            self.logger.error(f"[{response.status_code}] Server Error: {response.reason}")
        else:
            self.logger.error(f"[{response.status_code}] Other: {response.reason}")
        return False