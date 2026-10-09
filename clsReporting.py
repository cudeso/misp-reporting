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
from matplotlib.ticker import MultipleLocator
import numpy as np


# Chart colours for each stylesheet: a colour map for bars and the colours for trend lines
CHART_THEMES = {
    "orange": {"cmap": "Oranges", "line": "#FF6600", "line_pair": ["#ffcc00", "#ff1e00"]},
    "blue": {"cmap": "Blues", "line": "#003366", "line_pair": ["#5b9bd5", "#003366"]},
    "red": {"cmap": "RdPu", "line": "#802c59", "line_pair": ["#d48aa8", "#802c59"]},
}

TLP_COLOURS = {"tlp:red": "#d9534f", "tlp:amber": "#f0ad4e", "tlp:amber+strict": "#e67e22", "tlp:green": "#5cb85c",
               "tlp:clear": "#e8e6e6", "no tlp": "#b0b0b0"}


class Reporting:
    def __init__(self, config, logger, data, output_dir="report_output"):
        self.config = config
        self.logger = logger
        self.data = data
        self.data_for_report = {}

        self.report_date = datetime.now().strftime("%Y-%m-%d")
        self.report_misp_server = self.config["misp_url"]
        self.reporting_period = self.config["reporting_period"]
        self.output_dir = self.config["output_dir"]
        self.template_css = "{}/{}".format(self.config["install_dir"], self.config["template_css"])
        self.template_html = "{}/{}".format(self.config["install_dir"], self.config["template_html"])
        self.template_curation_html = "{}/{}".format(self.config["install_dir"], self.config["template_curation_html"])
        self.template_infrastructure_html = "{}/{}".format(self.config["install_dir"], self.config["template_infrastructure_html"])
        self.template_contributors_html = "{}/{}".format(self.config["install_dir"], self.config["template_contributors_html"])
        self.assets_dir = os.path.join(self.output_dir, self.config["output_assets"])
        os.makedirs(self.assets_dir, exist_ok=True)

        self.events_trending_path = os.path.join(self.output_dir, "events_trending.png")
        self.attributes_trending_path = os.path.join(self.output_dir, "attributes_trending.png")
        self.attributes_type_bar_chart_path = os.path.join(self.output_dir, "attributes_type_bar_chart.png")
        self.attributes_type_daily_bar_chart_path = os.path.join(self.output_dir, "attributes_type_daily_bar_chart.png")
        self.threatlevel_bar_chart_path = os.path.join(self.output_dir, "threatlevel_bar_chart.png")
        self.tlp_pie_chart_path = os.path.join(self.output_dir, "tlp_pie_chart.png")
        self.geo_targeting_map_path = os.path.join(self.output_dir, "geo_targeting_map.png")
        self.sector_targeting_bar_chart_path = os.path.join(self.output_dir, "sector_targeting_bar_chart.png")
        self.noimage_path = self.config["noimage_path"]

        self.threatlevel_key_mapping = self.config["threatlevel_key_mapping"]
        self.tlp_ignore_graph = self.config["tlp_ignore_graph"]
        self.attribute_summary = self.config["attribute_summary"]
        self.attribute_other = self.config["attribute_other"]
        self.key_organisations = self.config["key_organisations"]
        self.chart_theme = CHART_THEMES[self.config["chart_theme"]]

        if self.config["misp_verifycert"] is False:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.misp = PyMISP(self.config["misp_url"], self.config["misp_key"], self.config["misp_verifycert"])

    def write_index(self):
        html_content = """<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8" />
            <title>Redirecting...</title>
            <!-- This meta tag will cause the page to redirect immediately to misp_summary.html -->
            <meta http-equiv="refresh" content="0; url=misp_summary.html" />
        </head>
        <body>
            <!-- In case automatic redirection doesn’t work, provide a link for the user -->
            <p>If you are not automatically redirected, please <a href="misp_summary.html">click here</a>.</p>
        </body>
        </html>
        """

        with open("{}/index.html".format(self.config["output_dir"]), 'w') as f:
            f.write(html_content)

    def render_infrastructure(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))

        template_css_file = self.template_css
        with open(template_css_file, "r") as f:
            css_content = f.read()

        template_file = self.template_infrastructure_html
        with open(template_file, "r") as f:
            html_template = f.read()

        # Render the HTML
        template = Template(html_template, autoescape=True)
        html_content = template.render(
            css=css_content,
            show_contributors=self.config["reporting_contributors"],
            title="MISP Infrastructure summary",
            logo=self.config["logo"],
            report_date=self.report_date,
            report_timestamp=datetime.now().strftime('%Y%m%d %H%M%S'),
            report_timestamp_hm=datetime.now().strftime('%Y-%m-%d'),
            report_misp_server=self.report_misp_server,
            report_misp_results=self.data.get("infrastructure_misp", {}),
            
        )

        # Save the HTML file
        output_html_path = os.path.join(self.output_dir, "misp_infrastructure.html")
        with open(output_html_path, "w") as f:
            f.write(html_content)
        return True
    
    def render_contributors(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))

        print_misp_filters = None
        if self.config["reporting_filter"] is not None:
            print_misp_filters = self.config["reporting_filter"]

        days = int(self.config["reporting_period"].strip("d"))
        current_date = datetime.now()
        past_date = current_date - timedelta(days=days)
        print_period = f"(until {past_date.strftime('%Y-%m-%d')})"
            
        # ###############  Contributing organisations
        key = "contributor_orgs"
        if key in self.data:
            dataset = self.data[key]
            updated_dataset = {}
            for orgid in dataset:
                try:
                    org = self.misp.get_organisation(orgid)
                    if "Organisation" in org:
                        org_name = org["Organisation"]["name"]
                        uuid = org["Organisation"]["uuid"]
                        logo = None
                        if uuid in self.key_organisations:
                            logo = self.key_organisations[uuid]["logo"]
                        period_events = dataset[orgid]["reporting-period"]
                        today_events = dataset[orgid]["today"]
                        alltime_events = dataset[orgid]["all_time"]
                        updated_dataset[org_name] = {"logo": logo, "org_uuid": uuid, "period_events": period_events,
                                                    "today_events": today_events, "alltime_events": alltime_events}
                    else:
                        self.logger.error("Unable to get organisation info for {}".format(orgid))
                except Exception as e:
                    self.logger.error("Unable to get organisation info for {} - {}".format(orgid, e))
            self.data_for_report[key] = updated_dataset
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))
            
        reporting_filter = ""
        if self.config["reporting_filter"] is not None:
            reporting_filter = "MISP filters: {} ".format(self.config["reporting_filter"])

        template_css_file = self.template_css
        with open(template_css_file, "r") as f:
            css_content = f.read()

        template_file = self.template_contributors_html
        with open(template_file, "r") as f:
            html_template = f.read()

        # Render the HTML
        template = Template(html_template, autoescape=True)
        html_content = template.render(
            css=css_content,
            show_contributors=self.config["reporting_contributors"],
            title="MISP Contributors summary",
            logo=self.config["logo"],
            report_date=self.report_date,
            report_misp_filters=print_misp_filters,
            report_timestamp=datetime.now().strftime('%Y%m%d %H%M%S'),
            report_timestamp_hm=datetime.now().strftime('%Y-%m-%d'),
            reporting_period=self.config["reporting_period"],
            summary={"period": print_period},            
            report_misp_server=self.report_misp_server,
            contributors_org = self.data_for_report["contributor_orgs"],
            contributors_user = {}            
        )

        # Save the HTML file
        output_html_path = os.path.join(self.output_dir, "misp_contributors.html")
        with open(output_html_path, "w") as f:
            f.write(html_content)
        return True    

    def render_curation_report(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))

        print_misp_filters = None
        # ###############  General statistics
        key = "statistics"
        if key in self.data:
            dataset = self.data[key]
            updated_dataset = {}
            days = int(self.config["reporting_period"].strip("d"))
            current_date = datetime.now()
            past_date = current_date - timedelta(days=days)
            reporting_period = self.config["reporting_period"]
            updated_dataset["period"] = f"(until {past_date.strftime('%Y-%m-%d')})"
            if self.config["reporting_filter"] is not None:
                print_misp_filters = self.config["reporting_filter"]
            #updated_dataset["events"] = dataset["event_count"]
            #updated_dataset["attributes"] = dataset["attribute_count"]
            self.data_for_report[key] = updated_dataset
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Curation events
        key = "curation_complete"
        curation_complete_count = 0
        curation_complete_today_count = 0
        curation_incomplete_count = 0
        curation_incomplete_today_count = 0
        curation_complete_events = []
        curation_incomplete_events = []
        curation_incomplete_high_events = []
        curation_incomplete_high_count = 0
        curation_incomplete_adm_high_events = []
        curation_incomplete_adm_high_count = 0

        if key in self.data:
            dataset = self.data[key]
            curation_complete_count = len(dataset)
            curation_complete_events = dataset
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        if "curation_complete_today" in self.data:
            dataset = self.data["curation_complete_today"]
            curation_complete_today_count = len(dataset)
            self.logger.debug(" Created {}".format("curation_complete_today"))
        else:
            self.data_for_report["curation_complete_today"] = {}
            self.logger.error(" Not found: {}".format("curation_complete_today"))

        key = "curation_incomplete"
        if key in self.data:
            dataset = self.data[key]
            curation_incomplete_count = len(dataset)
            curation_incomplete_events = dataset
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        if "curation_incomplete_today" in self.data:
            dataset = self.data["curation_incomplete_today"]
            curation_incomplete_today_count = len(dataset)
            self.logger.debug(" Created {}".format("curation_incomplete_today"))
        else:
            self.data_for_report["curation_incomplete_today"] = {}
            self.logger.error(" Not found: {}".format("curation_incomplete_today"))

        if "curation_incomplete_high" in self.data:
            dataset = self.data["curation_incomplete_high"]
            curation_incomplete_high_count = len(dataset)
            curation_incomplete_high_events = dataset
            self.logger.debug(" Created {}".format("curation_incomplete_high"))
        else:
            self.data_for_report["curation_incomplete_high"] = {}
            self.logger.error(" Not found: {}".format("curation_incomplete_high"))

        if "curation_incomplete_adm_high" in self.data:
            dataset = self.data["curation_incomplete_adm_high"]
            curation_incomplete_adm_high_count = len(dataset)
            curation_incomplete_adm_high_events = dataset
            self.logger.debug(" Created {}".format("curation_incomplete_adm_high"))
        else:
            self.data_for_report["curation_incomplete_adm_high"] = {}
            self.logger.error(" Not found: {}".format("curation_incomplete_adm_high"))

        template_css_file = self.template_css
        with open(template_css_file, "r") as f:
            css_content = f.read()

        template_file = self.template_curation_html
        with open(template_file, "r") as f:
            html_template = f.read()

        # Render the HTML
        template = Template(html_template, autoescape=True)
        html_content = template.render(
            css=css_content,
            show_contributors=self.config["reporting_contributors"],
            title="MISP Curation summary",
            logo=self.config["logo"],
            report_date=self.report_date,
            report_misp_filters=print_misp_filters,
            report_timestamp=datetime.now().strftime('%Y%m%d %H%M%S'),
            report_timestamp_hm=datetime.now().strftime('%Y-%m-%d'),
            reporting_period=self.config["reporting_period"],

            report_misp_server=self.report_misp_server,
            summary=self.data_for_report.get("statistics", {}),
            curation_incomplete_today_count=curation_incomplete_today_count,
            curation_complete_today_count=curation_complete_today_count,
            curation_complete_count=curation_complete_count,
            curation_incomplete_count=curation_incomplete_count,

            curation_complete=curation_complete_events,
            show_curated_events=self.config["reporting_curated_events"],
            curation_incomplete=curation_incomplete_events,

            curation_incomplete_high=curation_incomplete_high_events,
            curation_incomplete_high_count=curation_incomplete_high_count,
            curation_incomplete_adm_high=curation_incomplete_adm_high_events,
            curation_incomplete_adm_high_count=curation_incomplete_adm_high_count,
        )

        # Save the HTML file
        output_html_path = os.path.join(self.output_dir, "misp_curation.html")
        with open(output_html_path, "w") as f:
            f.write(html_content)
        return True

    def render_report(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))

        self.logger.debug("Removing older images")
        for img in [self.events_trending_path,
                    self.attributes_trending_path,
                    self.attributes_type_bar_chart_path,
                    self.attributes_type_daily_bar_chart_path,
                    self.threatlevel_bar_chart_path,
                    self.tlp_pie_chart_path,
                    self.geo_targeting_map_path,
                    self.sector_targeting_bar_chart_path
                    ]:
            if os.path.exists(img):
                os.remove(img)

        print_misp_filters = None
        # ###############  Trending events
        key = "trending-events"
        if key in self.data:
            dataset = self.data[key]
            days = int(self.config["reporting_period"].strip("d"))
            sorted_keys = sorted(dataset.keys(), reverse=True)
            updated_dataset = {}
            highest_key = sorted_keys[0]
            updated_dataset[f"{highest_key + days}d-{highest_key}d"] = dataset[highest_key]
            for start, end in zip(sorted_keys[1:], sorted_keys):
                updated_dataset[f"{end}d-{start}d"] = dataset[start]
            self.data_for_report[key] = updated_dataset
            self.create_trending_graph(self.data_for_report[key], self.events_trending_path, "Trending events")
            self.logger.debug(" Created {}".format(self.events_trending_path))
        else:
            self.events_trending_path = self.noimage_path
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Trending attributes
        key = "trending-attributes"
        if key in self.data:
            dataset = self.data[key]
            dataset2 = self.data["trending-attributes_ids"]

            days = int(self.config["reporting_period"].strip("d"))
            sorted_keys = sorted(dataset.keys(), reverse=True)
            updated_dataset = {}
            highest_key = sorted_keys[0]
            updated_dataset[f"{highest_key + days}d-{highest_key}d"] = [dataset[highest_key], dataset2[highest_key]]
            for start, end in zip(sorted_keys[1:], sorted_keys):
                updated_dataset[f"{end}d-{start}d"] = [dataset[start], dataset2[start]]

            self.data_for_report[key] = updated_dataset
            self.create_trending_graph_double(self.data_for_report[key], self.attributes_trending_path, "Trending attributes", "Attributes", "With to_ids")
            self.logger.debug(" Created {}".format(self.attributes_trending_path))
        else:
            self.attributes_trending_path = self.noimage_path
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Statistics attributes
        key = "statistics-attributes"
        if key in self.data:
            dataset = dict(sorted(self.data[key].items(), key=lambda item: item[1], reverse=True))
            self.data_for_report[key] = dataset
            self.create_bar_chart(self.data_for_report[key], self.attributes_type_bar_chart_path, "Attributes type distribution ({})".format(self.config["reporting_period"]), full_width=False, value_index=0)
            self.create_bar_chart(self.data_for_report[key], self.attributes_type_daily_bar_chart_path, "Attributes type distribution (24h)", full_width=False, value_index=1)
            self.logger.debug(" Created {}".format(self.attributes_type_bar_chart_path))
            self.logger.debug(" Created {}".format(self.attributes_type_daily_bar_chart_path))
        else:
            self.attributes_type_bar_chart_path = self.noimage_path
            self.attributes_type_daily_bar_chart_path = self.noimage_path
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Statistics threatlevel
        key = "statistics-threatlevel"
        if key in self.data:
            dataset = self.data[key]
            updated_dataset = {self.threatlevel_key_mapping[key]: value for key, value in dataset.items()}
            self.data_for_report[key] = updated_dataset
            self.create_bar_chart(self.data_for_report[key], self.threatlevel_bar_chart_path, "Threat level", value_index=-1)
            self.logger.debug(" Created {}".format(self.threatlevel_bar_chart_path))
        else:
            self.threatlevel_bar_chart_path = self.noimage_path
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Statistics TLP
        key = "statistics-tlp"
        if key in self.data:
            dataset = self.data[key]
            updated_dataset = {}
            for delkey in dataset:
                if delkey not in self.tlp_ignore_graph and dataset[delkey] > 0:
                    updated_dataset[delkey] = dataset[delkey]
            self.data_for_report[key] = dataset
            self.create_pie_chart(updated_dataset, self.tlp_pie_chart_path, "TLP", colors=[TLP_COLOURS.get(tlp, "gray") for tlp in updated_dataset])
            self.logger.debug(" Created {}".format(self.tlp_pie_chart_path))
        else:
            self.tlp_pie_chart_path = self.noimage_path
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Statistics key organisations
        key = "statistics-keyorgs"
        if key in self.data:
            dataset = self.data[key]
            updated_dataset = {}
            for uuid in dataset:
                if uuid in self.key_organisations:
                    try:
                        org = self.misp.get_organisation(uuid)
                        if "Organisation" in org:
                            org_name = org["Organisation"]["name"]
                            logo = self.key_organisations[uuid]["logo"]
                            period_events = dataset[uuid]["reporting-period"]["events"]
                            period_attributes = dataset[uuid]["reporting-period"]["attributes"]
                            period_attributes_ids = dataset[uuid]["reporting-period"]["attributes_ids"]
                            today_events = dataset[uuid]["today"]["events"]
                            today_attributes = dataset[uuid]["today"]["attributes"]
                            today_attributes_ids = dataset[uuid]["today"]["attributes_ids"]
                            updated_dataset[org_name] = {"logo": f"{logo}", "org_uuid": f"{uuid}", "period_events": f"{period_events}",
                                                        "period_attributes": f"{period_attributes}",
                                                        "period_attributes_ids": f"{period_attributes_ids}",
                                                        "today_events": f"{today_events}",
                                                        "today_attributes": f"{today_attributes}",
                                                        "today_attributes_ids": f"{today_attributes_ids}"}
                        else:
                            self.logger.error("Unable to get organisation info for {}".format(uuid))
                    except Exception as e:
                        self.logger.error("Unable to get organisation info for {} - {}".format(uuid, e))
            self.data_for_report[key] = updated_dataset
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  General statistics
        key = "statistics"
        if key in self.data:
            dataset = self.data[key]
            updated_dataset = {}
            days = int(self.config["reporting_period"].strip("d"))
            current_date = datetime.now()
            past_date = current_date - timedelta(days=days)
            reporting_period = self.config["reporting_period"]
            updated_dataset["period"] = f"(until {past_date.strftime('%Y-%m-%d')})"
            if self.config["reporting_filter"] is not None:
                print_misp_filters = self.config["reporting_filter"]
            if "trending-events" in self.data:
                updated_dataset["period_events"] = self.data["trending-events"][0]
                updated_dataset["period_attributes"] = self.data["trending-attributes"][0]
                updated_dataset["period_attributes_ids"] = self.data["trending-attributes_ids"][0]
            else:
                updated_dataset["period_events"] = "No data"
                updated_dataset["period_attributes"] = "No data"
                updated_dataset["period_attributes_ids"] = "No data"
            if "today-events" in self.data:
                updated_dataset["today_events"] = self.data["today-events"]
                updated_dataset["today_attributes"] = self.data["today-attributes"]
                updated_dataset["today_attributes_ids"] = self.data["today-attributes_ids"]
            else:
                updated_dataset["today_events"] = "No data"
                updated_dataset["today_attributes"] = "No data"
                updated_dataset["today_attributes_ids"] = "No data"
            updated_dataset["events"] = dataset["event_count"]
            updated_dataset["attributes"] = dataset["attribute_count"]
            updated_dataset["correlations"] = dataset["correlation_count"]
            updated_dataset["organisations"] = dataset["org_count"]
            updated_dataset["local_organisations"] = dataset["local_org_count"]
            updated_dataset["users"] = dataset["user_count"]
            self.data_for_report[key] = updated_dataset
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Event details
        key = "detailed_events"
        if key in self.data:
            dataset = self.data[key]
            self.data_for_report[key] = dataset
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Targeting geo
        key = "targeting-geo"
        if not self.config["reporting_geo_targeting"]:
            self.data_for_report[key] = {}
        elif key in self.data and len(self.data[key]) > 0:
            dataset = self.data[key]
            sorted_data = dict(sorted(dataset.items(), key=lambda item: item[1], reverse=True))
            if self.config["filter_geo_count"] > 0:
                self.data_for_report[key] = dict(list(sorted_data.items())[:self.config["filter_geo_count"]])
            else:
                self.data_for_report[key] = sorted_data
            self.create_geo_targeting_map(self.data_for_report[key], self.geo_targeting_map_path)
            self.logger.debug(" Created {}".format(self.events_trending_path))
        else:
            self.geo_targeting_map_path = self.noimage_path
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Targeting sector
        key = "targeting-sector"
        if key in self.data and len(self.data[key]) > 0:
            dataset = self.data[key]
            sorted_data = dict(sorted(dataset.items(), key=lambda item: item[1], reverse=True))
            if self.config["filter_sector_count"] > 0:
                self.data_for_report[key] = dict(list(sorted_data.items())[:self.config["filter_sector_count"]])
            else:
                self.data_for_report[key] = sorted_data
            self.create_horizontal_bar_chart(self.data_for_report[key], self.sector_targeting_bar_chart_path, "Sector targeting")
            self.logger.debug(" Created {}".format(self.events_trending_path))
        else:
            self.sector_targeting_bar_chart_path = self.noimage_path
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  TTP pattern
        key = "ttp_pattern"
        if key in self.data and len(self.data[key]) > 0:
            dataset = self.data[key]
            sorted_data = dict(sorted(dataset.items(), key=lambda item: item[1], reverse=True))
            if self.config["filter_ttp_pattern_count"] > 0:
                self.data_for_report[key] = dict(list(sorted_data.items())[:self.config["filter_ttp_pattern_count"]])
            else:
                self.data_for_report[key] = sorted_data
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  TTP actors
        key = "ttp_actors"
        if key in self.data and len(self.data[key]) > 0:
            dataset = self.data[key]
            self.data_for_report[key] = dataset
            sorted_data = dict(sorted(dataset.items(), key=lambda item: item[1], reverse=True))
            if self.config["filter_ttp_actors_count"] > 0:
                self.data_for_report[key] = dict(list(sorted_data.items())[:self.config["filter_ttp_actors_count"]])
            else:
                self.data_for_report[key] = sorted_data
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ###############  Vulnerabilities
        key = "vulnerabilities"
        if key in self.data and len(self.data[key]) > 0:
            dataset = self.data[key]
            self.data_for_report[key] = {}
            sorted_data = dict(sorted(dataset.items(), key=lambda item: item[1]["count"], reverse=True))
            self.data_for_report[key] = sorted_data
            self.logger.debug(" Created {}".format(key))
        else:
            self.data_for_report[key] = {}
            self.logger.error(" Not found: {}".format(key))

        # ############### Labels
        if self.config["reporting_filter_timestamp"] == "timestamp":
            reporting_filter_timestamp = "recently changed"
        else:
            reporting_filter_timestamp = "published"

        if self.config["reporting_filter_attribute_type_ids"] == True:
            attributes_with_ids_or_not = "(only attributes where to_ids is set to true)"
        else:
            attributes_with_ids_or_not = "(all attributes, regardless of the to_ids flag)"

        template_css_file = self.template_css
        with open(template_css_file, "r") as f:
            css_content = f.read()

        template_file = self.template_html
        with open(template_file, "r") as f:
            html_template = f.read()

        template = Template(html_template, autoescape=True)
        html_content = template.render(
            css=css_content,
            show_contributors=self.config["reporting_contributors"],
            title="MISP Summary",
            logo=self.config["logo"],
            report_date=self.report_date,
            report_misp_filters=print_misp_filters,
            report_timestamp=datetime.now().strftime('%Y%m%d %H%M%S'),
            report_timestamp_hm=datetime.now().strftime('%Y-%m-%d'),
            reporting_period=self.config["reporting_period"],
            report_misp_server=self.report_misp_server,
            summary=self.data_for_report.get("statistics", {}),
            trending_events=self.data_for_report.get("trending-events", {}),
            trending_attributes=self.data_for_report.get("trending-attributes", {}),
            detailed_events=self.data_for_report["detailed_events"],
            print_event_details=self.config["print_event_details"],
            attributes_type=self.data_for_report["statistics-attributes"],
            threatlevel=self.data_for_report["statistics-threatlevel"],
            tlp=self.data_for_report["statistics-tlp"],
            keyorgs=self.data_for_report["statistics-keyorgs"],
            target_geo=self.data_for_report["targeting-geo"],
            target_sector=self.data_for_report["targeting-sector"],
            ttp_pattern=self.data_for_report["ttp_pattern"],
            ttp_actors=self.data_for_report["ttp_actors"],
            vulnerabilities=self.data_for_report["vulnerabilities"],

            events_trending_path=os.path.basename(self.events_trending_path),
            attributes_trending_path=os.path.basename(self.attributes_trending_path),
            attributes_type_bar_chart_path=os.path.basename(self.attributes_type_bar_chart_path),
            attributes_type_daily_bar_chart_path=os.path.basename(self.attributes_type_daily_bar_chart_path),
            threatlevel_bar_chart_path=os.path.basename(self.threatlevel_bar_chart_path),
            tlp_pie_chart_path=os.path.basename(self.tlp_pie_chart_path),
            geo_targeting_map_path=os.path.basename(self.geo_targeting_map_path),
            sector_targeting_bar_chart_path=os.path.basename(self.sector_targeting_bar_chart_path),

            reporting_filter_timestamp=reporting_filter_timestamp,
            vulnerability_lookup_url=self.config["vulnerability_lookup_url"].rstrip("/"),
            show_vulnerabilities=self.config["reporting_vulnerabilities"],
            show_geo_targeting=self.config["reporting_geo_targeting"],
            attributes_with_ids_or_not=attributes_with_ids_or_not,
            cve_highlight=self.config["reporting_cve_highlight"],
        )

        output_html_path = os.path.join(self.output_dir, "misp_summary.html")
        with open(output_html_path, "w") as f:
            f.write(html_content)
        return True

    def create_geo_targeting_map(self, data, output_path):
        countries = list(data.keys())
        counts = list(data.values())
        fig = px.choropleth(
            locations=countries,
            locationmode="country names",
            color=counts,
            labels={"color": "Count"},
        )
        fig.write_image(output_path)

    def create_horizontal_bar_chart(self, data, output_path, title):
        labels = list(data.keys())
        values = list(data.values())

        if all(v == 0 for v in values):
            values = [0.1] * len(values)  # Avoid fully empty chart

        colors = self._chart_colours(len(labels))

        plt.figure(figsize=(6, 4))
        plt.barh(labels, values, color=colors)
        plt.title(title)
        plt.xlabel("Count")

        # If all values are just dummy 0.1
        if all(v == 0.1 for v in values):
            plt.text(
                0.5, 0.5,
                "No data available",
                fontsize=12, ha="center",
                transform=plt.gca().transAxes
            )
            # Just keep a simple 0,1 scale
            plt.xticks([0, 1])
        else:
            max_val = max(values)
            # We'll consider integer ticks up to at least ceil of max_val
            max_int = int(np.ceil(max_val))

            if max_int > 5:
                # Generate exactly 5 ticks (0 to max_val)
                ticks = np.linspace(0, max_val, 5)
                # Round them to integers if desired
                tick_labels = [int(round(t)) for t in ticks]
                plt.xticks(ticks, tick_labels)
            else:
                # Less than or equal to 5, so just show integer ticks
                ticks = range(0, max_int + 1)
                plt.xticks(ticks, ticks)

        plt.tight_layout()
        plt.savefig(output_path, dpi=100)
        plt.close()

    def create_bar_chart(self, data, output_path, title, full_width=False, value_index=0):
        labels = list(data.keys())
        if value_index == -1:
            values = list(data.values())
        else:
            values = [v[value_index] for v in data.values()]

        if all(v == 0 for v in values):
            values = [0.1] * len(values)  # Avoid fully empty chart

        figsize = (8, 4) if full_width else (4, 3)

        colors = self._chart_colours(len(labels))

        plt.figure(figsize=figsize)
        plt.bar(labels, values, color=colors)
        plt.title(title, fontsize=10)
        plt.ylabel("Count", fontsize=8)

        ax = plt.gca()
        ax.xaxis.set_major_locator(MultipleLocator(1))
        plt.xticks(fontsize=8, rotation=45)
        plt.yticks(fontsize=8)

        # If dummy values were used, indicate it
        if all(v == 0.1 for v in values):
            plt.text(0.5, 0.5, "No data available", fontsize=12, ha="center", transform=plt.gca().transAxes)

        plt.tight_layout()
        plt.savefig(output_path, dpi=100)
        plt.close()

    def _chart_colours(self, count):
        # Skip the palest end of the colour map so that every bar stays visible on white
        cmap = plt.colormaps[self.chart_theme["cmap"]]
        return [cmap(0.95 - 0.55 * i / max(count - 1, 1)) for i in range(count)]

    def create_pie_chart(self, data, output_path, title, colors):
        labels = list(data.keys())
        sizes = list(data.values())

        if sum(sizes) == 0:
            self.logger.info("No data to display in pie chart.")
            plt.figure(figsize=(4, 3))
            plt.pie(
                [1],  # Single value to create a full circle
                labels=["No data"],
                colors=["lightgrey"],
                startangle=90,
                wedgeprops={'width': 0.4}
            )
            plt.title(title, fontsize=10)
            plt.axis("equal")
            plt.tight_layout()
            plt.savefig(output_path, dpi=100)
            plt.close()
        else:
            plt.figure(figsize=(4, 3))
            # Labels go in the legend and only the larger slices show a percentage, so that small slices do not overlap
            plt.pie(
                sizes,
                autopct=lambda pct: "{:.1f}%".format(pct) if pct >= 4 else "",
                pctdistance=0.8,
                startangle=90,
                colors=colors,
                textprops={'fontsize': 8},
                wedgeprops={'width': 0.4}
            )
            total = sum(sizes)
            plt.legend(["{} ({:.1f}%)".format(label, 100 * size / total) for label, size in zip(labels, sizes)],
                       loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8, frameon=False)
            plt.title(title, fontsize=10)
            plt.axis("equal")
            plt.tight_layout()
            plt.savefig(output_path, dpi=100)
            plt.close()

    def create_trending_graph(self, data, output_path, title):
        months = list(data.keys())
        values = list(data.values())

        plt.figure(figsize=(4, 3))
        plt.plot(months, values, marker="o", color=self.chart_theme["line"])
        plt.ylim(bottom=0)
        plt.title(title, fontsize=10)
        plt.ylabel("Count", fontsize=8)
        plt.xticks(fontsize=8, rotation=45)
        plt.yticks(fontsize=8)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(output_path, dpi=100)
        plt.close()

    def create_trending_graph_double(self, data, output_path, title, label1, label2):
        months = list(data.keys())
        pairs = list(data.values())

        # Separate out the first/second data points in each pair
        first_values = [p[0] for p in pairs]
        second_values = [p[1] for p in pairs]

        plt.figure(figsize=(4, 3))
        plt.plot(months, first_values, marker="o", color=self.chart_theme["line_pair"][0], label=label1)
        plt.plot(months, second_values, marker="o", color=self.chart_theme["line_pair"][1], label=label2)
        plt.ylim(bottom=0)

        plt.title(title, fontsize=10)
        plt.ylabel("Count", fontsize=8)
        plt.xticks(fontsize=8, rotation=45)
        plt.yticks(fontsize=8)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig(output_path, dpi=100)
        plt.close()
