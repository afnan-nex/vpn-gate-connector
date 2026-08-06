# VPN Gate Connector

A lightweight **Windows GUI application** that automatically fetches free VPN servers from **VPN Gate**, downloads the required OpenVPN configuration, and connects with a single click.

The application features a clean interface, server search/filtering, connection logs, and system tray support.

```cmd
curl -o vpn-connector.py https://raw.githubusercontent.com/afnan-nex/vpn-connector/main/vpn-connector.py && python -m pip install requests pystray pillow && python vpn-connector.py

```

---

## Features

- 🌍 Fetches the latest VPN Gate servers automatically
- ⚡ Sorts servers by score for better connections
- 🔍 Search servers by hostname or country
- 🌎 Filter servers by country
- 🔗 One-click VPN connection
- ❌ Disconnect or terminate connection anytime
- 📄 Live OpenVPN connection log
- 🖥️ Windows system tray support
- 🔄 Refresh server list instantly
- 📁 Automatically downloads and manages `.ovpn` configuration files
- 🪶 Lightweight Tkinter GUI

---

## Screenshot

> Add a screenshot here

---

## Requirements

- Windows 10 / Windows 11
- Python 3.10+
- OpenVPN

Install OpenVPN:

### Winget

```cmd
winget install OpenVPNTechnologies.OpenVPN
```

### Chocolatey

```cmd
choco install openvpn
```

---

## Python Dependencies

Install the required Python packages:

```cmd
pip install requests pystray pillow
```

---

## Download & Run

Clone the repository:

```cmd
git clone https://github.com/afnan-nex/vpn-connector.git
cd vpn-connector
```

Install dependencies:

```cmd
pip install requests pystray pillow
```

Run:

```cmd
python vpn-connector.py
```

---

## One-Line Download & Run

You can also download and run the application directly:

```cmd
curl -o vpn-connector.py https://raw.githubusercontent.com/afnan-nex/vpn-connector/main/vpn-connector.py && python -m pip install requests pystray pillow && python vpn-connector.py
```

---


## How It Works

1. Downloads the latest VPN server list from VPN Gate.
2. Displays all available servers.
3. Select a server.
4. Double-click or press **Connect**.
5. The application downloads the OpenVPN configuration.
6. OpenVPN launches automatically.
7. Connection status and logs are shown in real time.

---

## Built With

- Python
- Tkinter
- Requests
- Pystray
- Pillow
- OpenVPN
- VPN Gate Public API

---

## License

This project is licensed under the MIT License.

---

## Disclaimer

This project is an unofficial client for the public VPN Gate network.

The VPN servers are provided by volunteers around the world. Their availability, speed, and reliability may vary. This project does not operate or own any VPN servers.

Use at your own discretion.