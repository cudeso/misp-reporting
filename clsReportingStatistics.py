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
from collections import defaultdict


class ReportingStatistics:
    def __init__(self, config, logger, statistics, today_statistics, statistics_attributes, output_dir="report_output"):
        self.config = config
        self.logger = logger

        self.statistics = statistics
        self.today_statistics = today_statistics
        self.statistics_attributes = statistics_attributes

        self.report_date = datetime.now().strftime("%Y-%m-%d")
        self.report_misp_server = self.config["misp_url"]
        self.reporting_period = self.config["reporting_period"]
        self.output_dir = self.config["output_dir"]

    def render_statistics(self):
        self.logger.debug("Started {}".format(inspect.currentframe().f_code.co_name))

        statistics_json = {"misp_server": self.report_misp_server,
                           "report_date": self.report_date,
                           "statistics": f"{self.statistics}",
                           "today_statistics": f"{self.today_statistics}",
                           "today_statistics_attributes": f"{self.statistics_attributes}",
                           }

        try:
            json_file = "{}/statistics.json".format(self.config["output_dir"])
            with open(json_file, "w") as out_file:
                json.dump(statistics_json, out_file, indent=4)
        except Exception as e:
            self.logger.error("Error writing statistics json file: {}".format(e))
        self.logger.info("Render statistics")
