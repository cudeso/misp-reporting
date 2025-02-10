#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
from config import config
from clsReporting import *
from clsReportingData import *


def main(config):
    logger.info("Start {}".format(config["logname"]))

    data = ReportingData(config, logger)
    data.get_statistics()
    data.get_today_events_attributes()
    data.get_trending_events_attributes()
    data.get_statistics_attributes()
    data.get_statistics_keyorgs()
    data.get_threatlevel()
    data.get_tlplevel()
    #data.get_eventdetails()
    data.get_target_sector()
    data.get_target_geo()
    data.get_ttp()
    data.get_vulnerabilities()

    #data.get_curation()

    #data.get_infrastructure()

    reporting = Reporting(config, logger, data.data)
    reporting.write_index()
    reporting.render_report()
    #reporting.render_curation_report()
    #reporting.render_infrastructure()

    logger.info("End ".format(config["logname"]))


if __name__ == '__main__':
    # export PYTHONIOENCODING='utf8'
    logger = logging.getLogger(config["logname"])
    logger.setLevel(logging.DEBUG)
    ch = logging.FileHandler(config["logfile"], mode='a')
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    main(config)
