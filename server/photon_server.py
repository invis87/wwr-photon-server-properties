"""
Copyright 2015 Logvinenko Maksim

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import threading
from threading import Thread
import time

from photon import enums
from photon.enums import StatusCode, DebugLevel
from photon.listener import PeerListener
from photon.peer import PhotonPeer
from photon.typeddict import typed_dict
from photon.utils import now_in_millis


class PhotonServer:
    # data - custom data, that pass to callbacks
    def __init__(self, ip, port, app, data=None):
        super().__init__()

        self.ip = ip
        self.port = port
        self.app = app

        self.data = data
        self.connected = False

        self.listener = PhotonServerListener(self)
        self.pp = PhotonPeer(enums.ConnectionProtocol.Tcp, self.listener)
        self.pp.set_debug_level(DebugLevel.Error)

        self.service_thread = ServiceThread(self.pp)

        self.sync_lock = threading.Lock()
        self.sync_condition = threading.Condition()
        self.sync_mode = True

    def connect(self):
        if not self.pp.connect(self.ip, self.port, self.app):
            return False

        self.service_thread.start()

        while self.connected is False:
            pass

        return True

    def disconnect(self):
        if self.connected:
            self.service_thread.stop()
            self.service_thread.join()
            self.pp.disconnect()

    def stop(self, threshold, timeout, on_success, on_error, update_interval=10000.0):
        def validate_response(response):
            if response is None or response.return_code != 0:
                return False
            return True

        def load_properties(guid):
            op_response = self._sync_request(11, {1: guid})
            if not validate_response(op_response) or 2 not in op_response.params:
                return False

            return op_response.params[2], op_response.params[3]

        def stop_inner():
            start_time = now_in_millis()

            root_component_response = self._sync_request(10, {1: None})

            if not validate_response(root_component_response) or 2 not in root_component_response.params:
                on_error(self, self.data, "Get game server operation error {}".format(root_component_response))
                return

            if len(root_component_response.params[2]) != 1:
                on_error(self, self.data, "Invalid root element: {}".format(root_component_response.params[2]))
                return

            root_element_guid = next(iter(root_component_response.params[2].keys()))

            props = load_properties(root_element_guid)

            if 'Reset' not in props[1]:
                on_error(self, self.data, "Element doesn't contain 'Reset' operation: {}".format(props[1]))

            reset_response = self._sync_request(12, {1: root_element_guid, 2: 'Reset', 3: typed_dict(str, object)})

            if not validate_response(reset_response) or reset_response.params[3] != 1:
                on_error(self, self.data, "Error in 'Reset' operation: {}".format(props[1]))

            props = load_properties(root_element_guid)[0]
            while int(props["actorsCount"]) > threshold and now_in_millis() - start_time < timeout:
                time.sleep(update_interval / 1000.0)
                props = load_properties(root_element_guid)[0]

            on_success(self, self.data)

        Thread(target=stop_inner).start()

    def _sync_request(self, op_code, params):
        with self.sync_lock:
            with self.sync_condition:
                self.pp.op_custom(op_code, params, True)

                self.sync_condition.wait()

                return self.listener.last_op_response


class PhotonServerListener(PeerListener):
    def __init__(self, server):
        super().__init__()

        self.server = server
        self.last_op_response = None
        self.last_event = None

    def on_operation_response(self, operation_response):
        self.last_op_response = operation_response

        if self.server.sync_mode:
            with self.server.sync_condition:
                self.server.sync_condition.notify()

    def on_event(self, event_data):
        self.last_event = event_data

    def debug_return(self, debug_level, message):
        print("[{}] - {}".format(debug_level.name, message))

    def on_status_changed(self, status_code):
        if status_code is StatusCode.Connect:
            self.server.connected = True
        elif status_code is StatusCode.Disconnect \
                or status_code is StatusCode.DisconnectByServer \
                or status_code is StatusCode.DisconnectByServerLogic \
                or status_code is StatusCode.DisconnectByServerUserLimit \
                or status_code is StatusCode.TimeoutDisconnect:
            self.server.connected = False


class ServiceThread(threading.Thread):
    def __init__(self, pp):
        threading.Thread.__init__(self)

        self.pp = pp
        self._run = False

    def run(self):
        self._run = True

        while self._run:
            self.pp.service()

            time.sleep(100.0 / 1000.0)

    def stop(self):
        self._run = False