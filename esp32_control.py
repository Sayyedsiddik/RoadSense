import requests

ESP32_URL = "http://192.168.4.1"
TIMEOUT = 1

_last_connection_state = None


def send_command(command):
    global _last_connection_state

    command = command.upper()

    if command not in ("NORMAL", "SLOW", "STOP"):
        print("Invalid RoadSense command:", command)
        return False

    try:
        response = requests.get(
            f"{ESP32_URL}/command",
            params={"cmd": command},
            timeout=TIMEOUT
        )
        response.raise_for_status()

        if _last_connection_state is not True:
            print("RoadSense ESP32 connected.")

        _last_connection_state = True
        return True

    except requests.RequestException:
        if _last_connection_state is not False:
            print("ESP32 not connected. AI detection continues offline.")

        _last_connection_state = False
        return False


if __name__ == "__main__":
    print("RoadSense ESP32 control test")
    print("Connect to the ESP32 Wi-Fi when the board arrives.")
    send_command("STOP")