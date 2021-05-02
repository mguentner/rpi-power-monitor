from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBServerError
from datetime import datetime
import random
from time import sleep
from config import logger, db_settings, enabled_cts
from requests.exceptions import ConnectionError

# For development only
import sys, traceback

# Changes to these settings should be made in config.py!
client = InfluxDBClient(
    host=db_settings['host'],
    port=db_settings['port'],
    username=db_settings['username'],
    password=db_settings['password'],
    database=db_settings['database']
)

def result_to_point(time, key, value):
    if key.startswith("ct"):
        return {
            "measurement" : "raw_cts",
            "fields" : {
                "current" : value["current"],
                "power" : value["power"],
                "pf" : value["pf"],
            },
            "tags" : {
                'ct' : key.replace("ct", "")
            },
            "time" : time
        }
    elif key == 'voltage':
        return {
                "measurement" : "voltages",
                "fields" : {
                    "voltage" : value,
                },
                "tags" : {
                    'v_input' : "grid"
                },
                "time" : time
            }
    else:
         raise "Unexpected type"

def init_db():
    try:
        client.create_database(db_settings['database'])
        logger.info("... DB initalized.")
        return True
    except ConnectionRefusedError:
        logger.debug("Could not connect to InfluxDB")
        return False
    except Exception:
        logger.debug(f"Could not connect to {db_settings['host']}:{db_settings['port']}")
        return False

def close_db():
    client.close()

def result_should_be_written(key):
    if key.startswith("ct"):
        return int(key.replace("ct", "")) in enabled_cts
    else:
        return True

def write_to_influx(results):
    now = datetime.now()
    points = [ result_to_point(now, key, value) for key, value in results.items() if result_should_be_written(key) ]
    try:
        client.write_points(points, time_precision='ms')
    except InfluxDBServerError as e:
        logger.critical(f"Failed to write data to Influx. Reason: {e}")
    except ConnectionError:
        logger.info("Connection to InfluxDB lost. Please investigate!")
        sys.exit()
