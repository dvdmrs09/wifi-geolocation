import datetime
import json
import urllib3
import subprocess
import logging
import pathlib
import os
from datetime import datetime
from typing import List, Tuple, Optional, Union
from pineapple.helpers.opkg_helpers import OpkgJob
from pineapple.modules import Module, Request
from pineapple.helpers import network_helpers as net
from pineapple.helpers import opkg_helpers as opkg
import pineapple.helpers.notification_helpers as notifier
from pineapple.jobs import Job, JobManager
 

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

errors = {
	"dailyLimitExceeded": "Daily limit exceeded. The Program will try again shortly.",
	"keyInvalid": "Invalid API Key. The Program will try again shortly.",
	"userRateLimitExceeded": "Exceeded the request per second per user limit configured by you",
	"notFound": "Wifi Access Point not geolocated. The Program will try again shortly.",
	"parseError": "Request body is not valid JSON. The Program will try again shortly."
}

fieldLengths = {
	"Latitude": 9,
	"Longitude": 9,
}
# CONSTANTS
_HISTORY_DIRECTORY_PATH = '/root/.geolocate'
_HISTORY_DIRECTORY = pathlib.Path(_HISTORY_DIRECTORY_PATH)
# CONSTANTS

module = Module('geolocate', logging.DEBUG)
job_manager = JobManager(name='geolocate', module=module)


class GeoLocateJob(Job[bool]):

    def __init__(self, command: List[str], file_name: str, input_interface: str, output_interface: str):
        super().__init__()
        self.file_name = file_name
        self.command = command
        self.geolocate_file = f'{_HISTORY_DIRECTORY_PATH}/{file_name}'
        self.input_interface = input_interface
        self.monitor_input_iface = None


    def _stop_monitor_mode(self):
        if self.monitor_input_iface:
            os.system(f'airmon-ng stop {self.monitor_input_iface}')

    def do_work(self) -> bool:

        networks = open(self.geolocate_file, 'w')

        if self.input_interface and self.input_interface != '' and self.input_interface[-3:] != 'mon':
            if os.system(f'airmon-ng start {self.input_interface}') == 0:
                for index, substr in enumerate(self.command):
                    if substr == self.input_interface:
                        self.command[index] = f'{self.input_interface}mon'
                        self.monitor_input_iface = f'{self.input_interface}mon'
            else:
                self.error = 'Error starting monitor mode for input interface.'
                return False



        self._stop_monitor_mode()

        return True

    def stop(self):
        os.system('killall -9 geolocate')
        self._stop_monitor_mode()


    }




@module.on_start()
def _make_history_directory():
    if not _HISTORY_DIRECTORY.exists():
        _HISTORY_DIRECTORY.mkdir(parents=True)


@module.on_shutdown()
def stop_mdk4(signal: int = None) -> Union[str, Tuple[str, bool]]:
    if len(list(filter(lambda job_runner: job_runner.running is True, job_manager.jobs.values()))) > 0:
        if os.system('killall -9 geolocate') != 0:
            return 'Error stopping.', False

    return 'geolocate stopped.'


@module.handles_action('start')
def start(request: Request):
    command = request.command.split(' ')

    filename = f"{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}"
    networks = job_manager.execute_job(GeoLocate(command, filename, request.input_iface))
    formattedNetworks = {}
    formattedNetworks["results"] = []

    new_json_list=[]
    for data in networks:
        new_data = {}
        new_data["macAddress"] = data["bssid"]
        new_data["signalStrength"] = int(data["rssi"])
        formattedNetworks["results"].append(new_data)

    return formattedNetworks
        'job_id': job_id,
        'output_file': filename
    }


@module.handles_action('stop')
def stop(request: Request):
    return stop_geolocate()


@module.handles_action('load_history')
def load_history(request: Request):
    return [item.name for item in _HISTORY_DIRECTORY.iterdir() if item.is_file()]


@module.handles_action('load_output')
def load_output(request: Request):
    output_path = f'{_HISTORY_DIRECTORY_PATH}/{request.output_file}'
    if not os.path.exists(output_path):
        return 'Could not find scan output.', False

    with open(output_path, 'r') as f:
        return f.read()


@module.handles_action('delete_result')
def delete_result(request: Request):
    output_path = pathlib.Path(f'{_HISTORY_DIRECTORY_PATH}/{request.output_file}')
    if output_path.exists() and output_path.is_file():
        output_path.unlink()

    return True


@module.handles_action('clear_history')
def clear_history(request: Request):
    for item in _HISTORY_DIRECTORY.iterdir():
        if item.is_file():
            item.unlink()

    return True


@module.handles_action('startup')
def startup(request: Request):
    return {
        'interfaces': net.get_interfaces(),
    }


@module.handles_action('getGeolocation')
def getGeolocation(apiKey):

    data = getGps(networks, apiKey)

    return json.loads(data)




@module.handles_action('displayGeoLocation')
def displayGeolocation(apiData):
    errorCheck = gpsErrorCheck(apiData)
    if errorCheck is False:
        print('Successfully retrieved geolocation data')
        print(apiData)
    else:
        print('Geolocation not successful: ' + errorCheck)
        displayError(errorCheck)


@module.handles_action('getGps')
def getGps(networks, apiKey):
    http = urllib3.PoolManager()
    url = "https://www.googleapis.com/geolocation/v1/geolocate?key="+apiKey
    payload = json.dumps(networks)
    headers = {'content-Type': 'application/json', 'Accept-Charset': 'UTF-8'}
    r = http.request(
    	'POST',
    	url,
    	headers=headers,
    	body=payload
    )
    return r.data.decode('utf-8')

@module.handles_action('gpsErrorCheck')
def gpsErrorCheck(apiData):
    errorDetected = False
    if 'error' in apiData:
        if str(apiData['error']['errors'][0]['reason'])=='dailyLimitExceeded':
            errorDetected = errors["dailyLimitExceeded"]
        elif str(apiData['error']['errors'][0]['reason'])=='keyInvalid':
            errorDetected = errors["keyInvalid"]
        elif str(apiData['error']['errors'][0]['reason'])=='userRateLimitExceeded':
            errorDetected = errors["userRateLimitExceeded"]
        elif str(apiData['error']['errors'][0]['reason'])=='notFound':
            errorDetected = errors["notFound"]
        else:
            errorDetected = errors["parseError"]
    return errorDetected

@module.handles_action('buildDateTimeHeader')
def buildDateTimeHeader():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d   %X")


@module.handles_action('displayLocation')
def displayLocation(apiData, fieldLengths):
    timeHeader = buildDateTimeHeader()

    data = {}
    data["latitude"] = format(apiData['location']['lat'], '.6f')
    data["longitude"] = format(apiData['location']['lng'], '.6f')

    header = {}
    header['lat'] = "latitude  "
    header['lng'] = "longitude  "




