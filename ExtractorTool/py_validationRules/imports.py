import os
import urllib
import pandas as pd
import difflib

from sqlalchemy import create_engine
from dotenv import load_dotenv
from tabulate import tabulate

from ExtractorTool.dbUtils.sql_client import DatabaseClient
from py_validationRules.utilsClass import PyUtils


db = DatabaseClient()
conn = db.engine # Use SQLAlchemy engine for Pandas compatibility
conn_raw = db.conn # Keep raw connection available if needed
uc = PyUtils()