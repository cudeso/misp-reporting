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
    def __init__(self, config, logger, data, output_dir="report_output"):
        self.config = config
        self.logger = logger
        self.data = data
        self.data_for_report = {}

        self.report_date = datetime.now().strftime("%Y-%m-%d")
        self.report_misp_server = self.config["misp_url"]
        self.reporting_period = self.config["reporting_period"]
        self.output_dir = self.config["output_dir"]

    def render_statistics(self):
        self.logger.info("Render statistics")
