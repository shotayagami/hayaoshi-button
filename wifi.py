import network
import time


def connect_sta(ssid, password, timeout=10):
    """Try connecting to existing Wi-Fi. Returns wlan or None."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print(f"Already connected: {wlan.ifconfig()[0]}")
        return wlan

    print(f"Connecting to {ssid}...")
    wlan.connect(ssid, password)

    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout:
            print(f"Wi-Fi timeout ({timeout}s)")
            wlan.active(False)
            return None
        time.sleep(0.5)

    print(f"Connected! IP: {wlan.ifconfig()[0]}")
    return wlan


def start_ap(ssid="HayaoshiButton", password="hayaoshi1234"):
    """Start Pico as access point."""
    ap = network.WLAN(network.AP_IF)
    ap.config(essid=ssid, password=password, security=4)  # 4 = WPA2
    ap.active(True)

    while not ap.active():
        time.sleep(0.5)

    ip = ap.ifconfig()[0]
    print(f"AP started: SSID={ssid} Password={password}")
    print(f"IP: {ip}")
    return ap


def auto_connect(config):
    """Try STA first, fall back to AP mode.
    Returns (wlan, mode) where mode is 'sta' or 'ap'.
    """
    ssid = config.get("wifi_ssid", "")
    password = config.get("wifi_password", "")

    # Try STA mode if configured
    if ssid:
        wlan = connect_sta(ssid, password)
        if wlan and wlan.isconnected():
            return wlan, "sta"

    # Fall back to AP mode
    ap_ssid = config.get("ap_ssid", "HayaoshiButton")
    ap_password = config.get("ap_password", "hayaoshi1234")
    ap = start_ap(ap_ssid, ap_password)
    return ap, "ap"


def get_ip(wlan):
    return wlan.ifconfig()[0]
