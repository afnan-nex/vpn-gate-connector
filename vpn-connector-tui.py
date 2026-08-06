#!/usr/bin/env python3
"""
VPN Gate Auto-Connector
Scrapes VPN Gate servers, downloads .ovpn configs, and connects via OpenVPN.
Requires: requests, openvpn installed on system
"""

import requests
import base64
import csv
import os
import sys
import subprocess
import time
import signal
import argparse
from pathlib import Path

# --- Configuration ---
API_URL = "http://www.vpngate.net/api/iphone/"
OUTPUT_DIR = Path("vpngate_configs")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PythonVPN/1.0)"}

# OpenVPN binary path (adjust if needed)
OPENVPN_PATHS = [
    "openvpn",
    "/usr/sbin/openvpn",
    "/usr/local/sbin/openvpn",
    r"C:\Program Files\OpenVPN\bin\openvpn.exe",
    r"C:\Program Files (x86)\OpenVPN\bin\openvpn.exe",
]


def find_openvpn():
    """Find the OpenVPN binary on the system."""
    for path in OPENVPN_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
        # Also try 'which' / 'where'
        try:
            result = subprocess.run(
                ["which", path] if os.name != "nt" else ["where", path],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                found = result.stdout.strip().split("\n")[0]
                if os.path.isfile(found):
                    return found
        except Exception:
            pass
    return None


def fetch_servers():
    """Fetch VPN Gate server list from the API."""
    print(f"🔍 Fetching server list from {API_URL}...")
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to fetch server list: {e}")
        return []

    # The API returns a weird format: first line is "*vpn_servers", second is headers, last is "*"
    lines = response.text.strip().split("\n")

    # Remove the first line (*vpn_servers) and last line (*)
    if lines and lines[0].startswith("*"):
        lines = lines[1:]
    if lines and lines[-1].startswith("*"):
        lines = lines[:-1]

    if len(lines) < 2:
        print("❌ Invalid API response format.")
        return []

    # Parse CSV
    reader = csv.reader(lines)
    headers = next(reader)

    # Expected columns (from search results):
    # 0:HostName, 1:IP, 2:Score, 3:Ping, 4:Speed, 5:CountryLong, 6:CountryShort,
    # 7:NumVpnSessions, 8:Uptime, 9:TotalUsers, 10:TotalTraffic, 11:LogType,
    # 12:Operator, 13:Message, 14:OpenVPN_ConfigData_Base64

    servers = []
    for row in reader:
        if len(row) < 15:
            continue
        try:
            server = {
                "hostname": row[0],
                "ip": row[1],
                "score": int(row[2]) if row[2].isdigit() else 0,
                "ping": int(row[3]) if row[3].isdigit() else 9999,
                "speed": float(row[4]) if row[4] else 0,
                "country_long": row[5],
                "country_short": row[6],
                "sessions": int(row[7]) if row[7].isdigit() else 0,
                "uptime": row[8],
                "total_users": row[9],
                "total_traffic": row[10],
                "log_type": row[11],
                "operator": row[12],
                "message": row[13],
                "ovpn_b64": row[14],
            }
            # Only keep servers that have an OpenVPN config
            if server["ovpn_b64"] and server["ovpn_b64"].strip():
                servers.append(server)
        except Exception as e:
            continue

    print(f"✅ Found {len(servers)} servers with OpenVPN support.")
    return servers


def save_ovpn_config(server, filepath):
    """Decode base64 config and save to .ovpn file."""
    try:
        config_data = base64.b64decode(server["ovpn_b64"])
        with open(filepath, "wb") as f:
            f.write(config_data)
        return True
    except Exception as e:
        print(f"⚠️ Failed to save config for {server['hostname']}: {e}")
        return False


def list_servers(servers, limit=20):
    """Print a formatted list of top servers."""
    # Sort by score descending (higher score = better)
    sorted_servers = sorted(servers, key=lambda x: x["score"], reverse=True)

    print(f"\n{'Rank':<6}{'Hostname':<30}{'Country':<15}{'Speed':<12}{'Ping':<8}{'Score':<12}")
    print("-" * 85)
    for i, s in enumerate(sorted_servers[:limit], 1):
        speed_mbps = s["speed"] / 1_000_000 if s["speed"] else 0
        print(f"{i:<6}{s['hostname']:<30}{s['country_short']:<15}{speed_mbps:>6.1f} Mbps{s['ping']:>8} ms{s['score']:>12}")
    print()
    return sorted_servers


def connect_openvpn(ovpn_file, openvpn_bin="openvpn"):
    """Connect to VPN using OpenVPN. Returns the process handle."""
    print(f"\n🚀 Starting OpenVPN with config: {ovpn_file}")
    print("   (Press Ctrl+C to disconnect)\n")

    # OpenVPN needs root/admin. Warn if not.
    if os.name != "nt" and os.geteuid() != 0:
        print("⚠️  Warning: OpenVPN usually requires root privileges.")
        print("   Try running with: sudo python3 vpngate_connector.py ...\n")

    cmd = [openvpn_bin, "--config", str(ovpn_file), "--verb", "3"]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # Stream output in real-time
        for line in process.stdout:
            print(line, end="")
            # Detect successful connection
            if "Initialization Sequence Completed" in line:
                print("\n✅ VPN Connected successfully!")
            # Detect auth failure
            if "AUTH_FAILED" in line or "authentication failed" in line.lower():
                print("\n❌ Authentication failed. VPN Gate usually uses 'vpn' as username.")

        process.wait()
        if process.returncode != 0:
            print(f"\n❌ OpenVPN exited with code {process.returncode}")

    except KeyboardInterrupt:
        print("\n\n🛑 Disconnecting VPN...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        print("✅ Disconnected.")
    except FileNotFoundError:
        print(f"❌ OpenVPN binary not found: {openvpn_bin}")
        print("   Please install OpenVPN and ensure it's in your PATH.")
    except Exception as e:
        print(f"❌ Error running OpenVPN: {e}")


def interactive_mode(servers, openvpn_bin):
    """Interactive mode: list servers and let user pick one."""
    sorted_servers = list_servers(servers, limit=30)

    while True:
        try:
            choice = input("Enter server number to connect (or 'q' to quit): ").strip()
            if choice.lower() == 'q':
                return
            idx = int(choice) - 1
            if idx < 0 or idx >= len(sorted_servers):
                print("Invalid selection.")
                continue
        except ValueError:
            print("Please enter a number.")
            continue

        server = sorted_servers[idx]
        OUTPUT_DIR.mkdir(exist_ok=True)
        ovpn_file = OUTPUT_DIR / f"{server['hostname']}.ovpn"

        if not save_ovpn_config(server, ovpn_file):
            print("Failed to save config. Try another server.")
            continue

        print(f"📁 Config saved to: {ovpn_file}")
        connect_openvpn(ovpn_file, openvpn_bin)

        again = input("\nConnect to another server? (y/n): ").strip().lower()
        if again != 'y':
            break


def auto_connect(servers, openvpn_bin, country=None, top_n=5):
    """Auto-connect to the best available server."""
    # Filter by country if specified
    filtered = servers
    if country:
        filtered = [s for s in servers if s["country_short"].upper() == country.upper()]
        if not filtered:
            print(f"❌ No servers found for country: {country}")
            return

    # Sort by score descending
    sorted_servers = sorted(filtered, key=lambda x: x["score"], reverse=True)

    OUTPUT_DIR.mkdir(exist_ok=True)

    for i, server in enumerate(sorted_servers[:top_n], 1):
        ovpn_file = OUTPUT_DIR / f"{server['hostname']}.ovpn"

        print(f"\n[{i}/{top_n}] Trying {server['hostname']} ({server['country_short']})...")

        if not save_ovpn_config(server, ovpn_file):
            continue

        print(f"📁 Config saved to: {ovpn_file}")

        # Try to connect
        cmd = [openvpn_bin, "--config", str(ovpn_file), "--verb", "3"]
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            connected = False
            start_time = time.time()

            for line in process.stdout:
                print(line, end="")
                if "Initialization Sequence Completed" in line:
                    connected = True
                    print("\n✅ Connected! VPN is active.")
                    print("   Press Ctrl+C to disconnect.\n")
                    try:
                        process.wait()
                    except KeyboardInterrupt:
                        print("\n🛑 Disconnecting...")
                        process.terminate()
                        process.wait(timeout=5)
                    return

                # Timeout after 30 seconds if no connection
                if time.time() - start_time > 30:
                    print("\n⏱️ Connection timed out. Trying next server...")
                    process.terminate()
                    process.wait(timeout=5)
                    break

                if "AUTH_FAILED" in line or "Connection refused" in line:
                    print("\n❌ Connection failed. Trying next server...")
                    process.terminate()
                    process.wait(timeout=5)
                    break

        except Exception as e:
            print(f"⚠️ Error: {e}")
            continue

    print("\n❌ Could not connect to any of the top servers.")


def download_all_configs(servers):
    """Download all .ovpn configs without connecting."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    saved = 0

    print(f"\n📥 Downloading all {len(servers)} configs to {OUTPUT_DIR}/ ...")
    for server in servers:
        ovpn_file = OUTPUT_DIR / f"{server['hostname']}.ovpn"
        if save_ovpn_config(server, ovpn_file):
            saved += 1

    print(f"✅ Saved {saved} configs to {OUTPUT_DIR}/")


def main():
    parser = argparse.ArgumentParser(
        description="VPN Gate Auto-Connector - Download and connect to free VPN servers"
    )
    parser.add_argument("--auto", action="store_true", help="Auto-connect to best server")
    parser.add_argument("--country", type=str, help="Filter by country code (e.g., JP, US, DE)")
    parser.add_argument("--download-all", action="store_true", help="Download all configs without connecting")
    parser.add_argument("--list", action="store_true", help="Just list servers and exit")
    parser.add_argument("--top", type=int, default=5, help="Number of servers to try in auto mode (default: 5)")
    parser.add_argument("--openvpn", type=str, default=None, help="Path to openvpn binary")

    args = parser.parse_args()

    # Find OpenVPN
    openvpn_bin = args.openvpn or find_openvpn()
    if not openvpn_bin:
        print("❌ OpenVPN not found. Please install it first:")
        print("   Ubuntu/Debian: sudo apt install openvpn")
        print("   macOS: brew install openvpn")
        print("   Windows: Download from https://openvpn.net/community-downloads/")
        sys.exit(1)

    print(f"🔧 Using OpenVPN: {openvpn_bin}")

    # Fetch servers
    servers = fetch_servers()
    if not servers:
        print("❌ No servers available. Exiting.")
        sys.exit(1)

    # Just list
    if args.list:
        list_servers(servers)
        return

    # Download all
    if args.download_all:
        download_all_configs(servers)
        return

    # Auto-connect
    if args.auto:
        auto_connect(servers, openvpn_bin, country=args.country, top_n=args.top)
        return

    # Interactive mode (default)
    interactive_mode(servers, openvpn_bin)


if __name__ == "__main__":
    main()
