import requests
import re
import subprocess
import sys
import random
import string

# --- Configuration ---
URL = "https://www.vpngate.net/en/"
OUTPUT_FILE = "opengw_hosts.txt"

# NEW PATTERN: Only matches 'public-vpn-' followed by numbers
# This ignores vpn123..., n26..., etc.
PATTERN = re.compile(r'\bpublic-vpn-\d+\.opengw\.net\b')

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PythonScraper/1.0)"}

def get_random_vpn_name():
    """Generates a random 6-letter lowercase name like 'jsdfsk'."""
    return ''.join(random.choices(string.ascii_lowercase, k=6))

def run_cmd(cmd):
    """Helper to run system commands and handle errors."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        shell=False
    )
    if result.returncode != 0:
        print(f"⚠️ Command warning/error:\n{result.stderr}")
    return result.stdout

def get_vpn_hosts():
    """Scrapes the website and returns a sorted list of unique hosts."""
    print(f"🔍 Scraping {URL} for 'public-vpn' hosts...")
    try:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()

        matches = set(PATTERN.findall(response.text))
        
        # Sort based on the numeric part of the hostname to look cleaner
        # e.g., extracts 108 from public-vpn-108.opengw.net
        sorted_hosts = sorted(matches, key=lambda x: int(re.search(r'(\d+)', x).group(1)))

        # Save to file
        with open(OUTPUT_FILE, "w") as f:
            for host in sorted_hosts:
                f.write(host + "\n")
        
        return sorted_hosts

    except requests.exceptions.RequestException as e:
        print(f"❌ Network Error: {e}")
        return []

def connect_to_vpn(server_address):
    """Creates the VPN profile with a random name and connects."""
    username = "vpn"
    password = "vpn"
    
    # Generate a unique name (e.g., 'abvcak')
    vpn_name = get_random_vpn_name()

    print(f"\n🛠 Creating VPN profile '{vpn_name}' for {server_address}...")

    ps_script = f"""
    Add-VpnConnection `
        -Name "{vpn_name}" `
        -ServerAddress "{server_address}" `
        -TunnelType SSTP `
        -EncryptionLevel Required `
        -AuthenticationMethod MSChapv2 `
        -SplitTunneling $False `
        -Force
    """

    run_cmd(["powershell", "-Command", ps_script])
    
    print("✅ VPN profile created.")
    print(f"🔌 Connecting to {server_address} using profile '{vpn_name}'...")

    output = run_cmd(["rasdial", vpn_name, username, password])

    print(output)
    
    if "Command completed successfully" in output:
        print(f"🎉 Successfully connected to VPNGate! (Profile: {vpn_name})")
    else:
        print("❗ Connection might have failed. Check the output above.")

def main():
    hosts = get_vpn_hosts()

    if not hosts:
        print("No 'public-vpn' hosts found. The list might be empty or the site changed.")
        sys.exit(1)

    print(f"\nFound {len(hosts)} Public VPN networks:\n")
    print("-" * 40)
    for i, host in enumerate(hosts, 1):
        print(f"[{i:03d}] {host}")
    print("-" * 40)

    while True:
        choice = input("\nEnter the number of the VPN to connect to (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            print("Exiting...")
            break
        
        try:
            index = int(choice) - 1
            if 0 <= index < len(hosts):
                selected_server = hosts[index]
                print(f"\nYou selected: {selected_server}")
                connect_to_vpn(selected_server)
                break
            else:
                print("❌ Invalid selection. Number out of range.")
        except ValueError:
            print("❌ Invalid input. Please enter a number.")

if __name__ == "__main__":
    if sys.platform != "win32":
        print("This script is designed for Windows.")
    else:
        main()
