#!/usr/bin/env python3

import sys
import getopt

from server.photon_server import PhotonServer


__doc__ = """Return photon server parameters.

    Keyword arguments:
    -a (--address) -- ip address of a photon server
    -n (--name) -- photon application name (Game/Master)
    """

GAME = 'Game'
MASTER = 'Master'
MASTER_PORT = 6000
GAME_PORT = 6001

def main(argv=sys.argv):
    try:
        opts, args = getopt.getopt(argv[1:], "h,a:n:", ["help", "address=", "name="])
    except getopt.error as msg:
        print(msg)
        print("for help use --help")
        return 2
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print(__doc__)
            return 0
        elif opt in ("-a", "--address"):
            ip = arg
        elif opt in ("-n", "--name"):
            app_name = arg
            if (app_name != MASTER) and (app_name != GAME):
                print("Application name should be {} or {}".format(MASTER, GAME))
                return 2
            port = MASTER_PORT if app_name == MASTER else GAME_PORT
        else:
            print(__doc__)
            return 2

    props = get_server_properties(ip, port, app_name)
    print('\n'.join("{!s}={!s}".format(key, val) for (key, val) in props.items()))
    return 0


def get_server_properties(ip, port, app_name):
    photon_server = PhotonServer(ip, port, app_name)

    photon_server.connect()

    root_component_response = photon_server._sync_request(10, {1: None})

    if not validate_response(root_component_response) or 2 not in root_component_response.params:
        print("Get game server operation error {}".format(root_component_response))
        return

    if len(root_component_response.params[2]) != 1:
        print("Invalid root element: {}".format(root_component_response.params[2]))
        return

    root_element_guid = next(iter(root_component_response.params[2].keys()))
    properties = photon_server._sync_request(11, {1: root_element_guid})

    if not validate_response(properties) or 2 not in properties.params:
        return False

    photon_server.disconnect()
    return properties.params[2]


def validate_response(response):
    if response is None or response.return_code != 0:
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())