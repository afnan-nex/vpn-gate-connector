import subprocess
import getpass
import sys

def run(cmd):
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        shell=False
    )
    if result.returncode != 0:
        print("❌ Error:")
        print(result.stderr)
        sys.exit(1)
    return result.stdout


print("=== VPNGate SSTP Connector ===\n")

vpn_name = input("VPN connection name: ").strip()
server = input("VPNGate SSTP server address (e.g. vpn123.opengw.net): ").strip()

username = "vpn"
password = "vpn"

print("\n🛠 Creating VPN profile...")

powershell_cmd = f"""
Add-VpnConnection `
  -Name "{vpn_name}" `
  -ServerAddress "{server}" `
  -TunnelType SSTP `
  -EncryptionLevel Required `
  -AuthenticationMethod MSChapv2 `
  -SplitTunneling $False `
  -Force
"""

run([
    "powershell",
    "-Command",
    powershell_cmd
])

print("✅ VPN profile created")

print("\n🔌 Connecting to VPNGate...")

output = run([
    "rasdial",
    vpn_name,
    username,
    password
])

print(output)
print("🎉 Connected to VPNGate successfully!")
