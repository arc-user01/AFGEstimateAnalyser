import os
import urllib
import pandas as pd
import difflib

from sqlalchemy import create_engine
from dotenv import load_dotenv
from tabulate import tabulate

from pg_utils.pgsql_client import PgClient
from py_validationRules.utilsClass import PyUtils


pg = PgClient()
conn = pg.engine # Use SQLAlchemy engine for Pandas compatibility
conn_raw = pg.conn # Keep raw connection available if needed
uc = PyUtils()