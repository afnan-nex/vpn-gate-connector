#!/usr/bin/env python3
"""
VPN Gate Auto-Connector - Windows GUI Edition
Scrapes VPN Gate servers, downloads .ovpn configs, and connects via OpenVPN.
Minimizes to system tray. Click 'Terminate' to disconnect and exit.

Requirements: pip install requests pystray pillow
"""

import requests
import base64
import csv
import os
import sys
import subprocess
import time
import threading
import tempfile
from pathlib import Path
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# System tray
import pystray
from PIL import Image, ImageDraw

# --- Windows-only check ---
if os.name != "nt":
    messagebox.showerror("Platform Error", "This application is Windows-only.")
    sys.exit(1)

# --- Configuration ---
API_URL = "http://www.vpngate.net/api/iphone/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# OpenVPN paths on Windows
OPENVPN_PATHS = [
    r"C:\Program Files\OpenVPN\bin\openvpn.exe",
    r"C:\Program Files (x86)\OpenVPN\bin\openvpn.exe",
    "openvpn.exe",
]

APP_NAME = "VPN Gate Connector"


@dataclass
class VPNServer:
    hostname: str
    ip: str
    score: int
    ping: int
    speed: float
    country_long: str
    country_short: str
    sessions: int
    uptime: str
    ovpn_b64: str


class VPNGateApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("900x650")
        self.root.minsize(800, 550)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # State
        self.servers: list[VPNServer] = []
        self.ovpn_process: subprocess.Popen | None = None
        self.ovpn_file: Path | None = None
        self.is_connected = False
        self.is_connecting = False
        self.tray_icon = None
        self.tray_thread = None
        self.log_lines: list[str] = []
        self.max_log_lines = 500

        # Temp dir for ovpn files
        self.temp_dir = Path(tempfile.gettempdir()) / "vpngate_connector"
        self.temp_dir.mkdir(exist_ok=True)

        # Find OpenVPN
        self.openvpn_bin = self.find_openvpn()

        self.build_ui()
        self.create_tray_icon()

        # Start background fetch
        self.fetch_servers_async()

    # ===================== UI BUILDING =====================

    def build_ui(self):
        # Top frame: Status + Controls
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        # Status label
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(top_frame, text="Status:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.status_label = ttk.Label(top_frame, textvariable=self.status_var, font=("Segoe UI", 10))
        self.status_label.pack(side=tk.LEFT, padx=(5, 20))

        # Buttons
        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(side=tk.RIGHT)

        self.connect_btn = ttk.Button(btn_frame, text="Connect", command=self.on_connect, width=12)
        self.connect_btn.pack(side=tk.LEFT, padx=2)

        self.disconnect_btn = ttk.Button(btn_frame, text="Disconnect", command=self.on_disconnect, width=12, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=2)

        self.terminate_btn = ttk.Button(btn_frame, text="Terminate", command=self.on_terminate, width=12)
        self.terminate_btn.pack(side=tk.LEFT, padx=2)

        ttk.Button(btn_frame, text="Refresh", command=self.on_refresh, width=10).pack(side=tk.LEFT, padx=2)

        # Filter frame
        filter_frame = ttk.Frame(self.root, padding=(10, 0))
        filter_frame.pack(fill=tk.X)

        ttk.Label(filter_frame, text="Filter Country:").pack(side=tk.LEFT)
        self.country_var = tk.StringVar()
        self.country_combo = ttk.Combobox(filter_frame, textvariable=self.country_var, width=10, state="readonly")
        self.country_combo.pack(side=tk.LEFT, padx=5)
        self.country_combo.bind("<<ComboboxSelected>>", self.on_country_filter)

        ttk.Label(filter_frame, text="Search:").pack(side=tk.LEFT, padx=(15, 0))
        self.search_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.search_var, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Search", command=self.on_search).pack(side=tk.LEFT, padx=2)
        ttk.Button(filter_frame, text="Clear", command=self.on_clear_search).pack(side=tk.LEFT, padx=2)

        # Server list
        list_frame = ttk.LabelFrame(self.root, text="VPN Servers", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Treeview with scrollbar
        cols = ("rank", "hostname", "country", "speed", "ping", "score", "sessions")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=12)

        self.tree.heading("rank", text="#")
        self.tree.heading("hostname", text="Hostname")
        self.tree.heading("country", text="Country")
        self.tree.heading("speed", text="Speed")
        self.tree.heading("ping", text="Ping")
        self.tree.heading("score", text="Score")
        self.tree.heading("sessions", text="Users")

        self.tree.column("rank", width=30, anchor=tk.CENTER)
        self.tree.column("hostname", width=250)
        self.tree.column("country", width=80, anchor=tk.CENTER)
        self.tree.column("speed", width=80, anchor=tk.CENTER)
        self.tree.column("ping", width=60, anchor=tk.CENTER)
        self.tree.column("score", width=70, anchor=tk.CENTER)
        self.tree.column("sessions", width=60, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        # Double-click to connect
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Log area
        log_frame = ttk.LabelFrame(self.root, text="Connection Log", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)

        # Progress bar
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=10, pady=(0, 5))

        # OpenVPN warning
        if not self.openvpn_bin:
            self.log("WARNING: OpenVPN not found! Install it first.")
            self.log("  winget install OpenVPNTechnologies.OpenVPN")
            self.log("  or: choco install openvpn")

    # ===================== SYSTEM TRAY =====================

    def create_tray_icon(self):
        # Create a simple icon image
        icon_image = self._create_icon_image()

        menu = pystray.Menu(
            pystray.MenuItem("Show", self.show_window),
            pystray.MenuItem("Connect", self.on_connect),
            pystray.MenuItem("Disconnect", self.on_disconnect),
            pystray.MenuItem("Terminate", self.on_terminate),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.on_terminate),
        )

        self.tray_icon = pystray.Icon(APP_NAME, icon_image, APP_NAME, menu)

    def _create_icon_image(self) -> Image.Image:
        width = 64
        height = 64
        image = Image.new("RGB", (width, height), "white")
        dc = ImageDraw.Draw(image)
        # Draw a simple shield-like shape in blue
        dc.ellipse([8, 8, 56, 56], fill="#2563EB", outline="#1E40AF", width=3)
        dc.text((22, 22), "VPN", fill="white", font=None)
        return image

    def run_tray(self):
        self.tray_icon.run()

    def show_window(self):
        self.tray_icon.stop()
        self.root.after(0, self._deiconify)

    def _deiconify(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def on_close(self):
        """Minimize to tray instead of closing."""
        self.root.withdraw()
        if self.tray_thread is None or not self.tray_thread.is_alive():
            self.tray_thread = threading.Thread(target=self.run_tray, daemon=True)
            self.tray_thread.start()

    # ===================== OPENVPN =====================

    def find_openvpn(self) -> str | None:
        for path in OPENVPN_PATHS:
            if os.path.isfile(path):
                return path
        # Try PATH
        try:
            result = subprocess.run(["where", "openvpn.exe"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0].strip()
        except Exception:
            pass
        return None

    def save_ovpn(self, server: VPNServer) -> Path | None:
        try:
            config_data = base64.b64decode(server.ovpn_b64)
            filepath = self.temp_dir / f"{server.hostname}.ovpn"
            with open(filepath, "wb") as f:
                f.write(config_data)
            return filepath
        except Exception as e:
            self.log(f"Error saving config: {e}")
            return None

    def kill_openvpn(self):
        """Force kill any running openvpn.exe processes."""
        try:
            subprocess.run(["taskkill", "/F", "/IM", "openvpn.exe"], capture_output=True, timeout=10)
        except Exception:
            pass
        self.ovpn_process = None
        self.is_connected = False
        self.is_connecting = False

    # ===================== CONNECTION LOGIC =====================

    def on_connect(self, server: VPNServer | None = None):
        if self.is_connecting or self.is_connected:
            self.log("Already connected or connecting. Disconnect first.")
            return

        if not self.openvpn_bin:
            messagebox.showerror("OpenVPN Not Found", 
                "OpenVPN is not installed.\n\nInstall it with:\n"
                "winget install OpenVPNTechnologies.OpenVPN\n"
                "or: choco install openvpn")
            return

        # If no server passed, use selected one
        if server is None:
            selected = self.tree.selection()
            if not selected:
                messagebox.showinfo("Select Server", "Please select a server from the list first.")
                return
            item = self.tree.item(selected[0])
            hostname = item["values"][1]
            server = next((s for s in self.servers if s.hostname == hostname), None)
            if not server:
                return

        self.connect_to_server(server)

    def connect_to_server(self, server: VPNServer):
        def _connect():
            self.is_connecting = True
            self.set_status(f"Connecting to {server.hostname}...")
            self.log(f"\n{'='*50}")
            self.log(f"Connecting to {server.hostname} ({server.country_short})")
            self.log(f"Speed: {server.speed/1_000_000:.1f} Mbps | Ping: {server.ping}ms | Score: {server.score}")
            self.log("="*50)

            # Save config
            ovpn_path = self.save_ovpn(server)
            if not ovpn_path:
                self.is_connecting = False
                self.set_status("Failed to save config")
                return

            self.ovpn_file = ovpn_path
            self.log(f"Config saved: {ovpn_path}")

            # Run OpenVPN
            cmd = [
                self.openvpn_bin,
                "--config", str(ovpn_path),
                "--verb", "3",
                "--dev", "tun",
            ]

            try:
                self.ovpn_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                start_time = time.time()
                for line in self.ovpn_process.stdout:
                    self.log(line.rstrip())

                    if "Initialization Sequence Completed" in line:
                        self.is_connected = True
                        self.is_connecting = False
                        self.set_status(f"Connected: {server.hostname}")
                        self.update_buttons()
                        self.tray_icon.title = f"{APP_NAME} - Connected"

                    if "AUTH_FAILED" in line or "connection refused" in line.lower():
                        self.log("Authentication failed or connection refused.")
                        break

                    # Timeout after 45 seconds
                    if time.time() - start_time > 45 and not self.is_connected:
                        self.log("Connection timed out.")
                        break

                # Process ended
                self.ovpn_process.wait(timeout=5)
                self.is_connected = False
                self.is_connecting = False
                self.set_status("Disconnected")
                self.update_buttons()
                if self.tray_icon:
                    self.tray_icon.title = f"{APP_NAME} - Disconnected"
                self.log("\n--- Connection closed ---\n")

            except Exception as e:
                self.log(f"Connection error: {e}")
                self.is_connected = False
                self.is_connecting = False
                self.set_status("Error")
                self.update_buttons()

        threading.Thread(target=_connect, daemon=True).start()
        self.update_buttons()

    def on_disconnect(self):
        if self.ovpn_process and self.ovpn_process.poll() is None:
            self.log("\nDisconnecting...")
            try:
                self.ovpn_process.terminate()
                self.ovpn_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ovpn_process.kill()
            except Exception as e:
                self.log(f"Error disconnecting: {e}")
        self.kill_openvpn()
        self.set_status("Disconnected")
        self.update_buttons()
        if self.tray_icon:
            self.tray_icon.title = f"{APP_NAME} - Disconnected"

    def on_terminate(self):
        """Kill everything and exit the app."""
        self.log("\n*** TERMINATING ***")
        self.on_disconnect()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(100, self._exit_app)

    def _exit_app(self):
        self.root.destroy()
        sys.exit(0)

    # ===================== SERVER FETCHING =====================

    def fetch_servers_async(self):
        self.set_status("Fetching servers...")
        self.progress.start()
        threading.Thread(target=self._fetch_servers, daemon=True).start()

    def _fetch_servers(self):
        try:
            response = requests.get(API_URL, headers=HEADERS, timeout=30)
            response.raise_for_status()
        except Exception as e:
            self.root.after(0, lambda: self.set_status(f"Fetch failed: {e}"))
            self.root.after(0, self.progress.stop)
            return

        lines = response.text.strip().split("\n")
        if lines and lines[0].startswith("*"):
            lines = lines[1:]
        if lines and lines[-1].startswith("*"):
            lines = lines[:-1]

        if len(lines) < 2:
            self.root.after(0, lambda: self.set_status("Invalid API response"))
            self.root.after(0, self.progress.stop)
            return

        reader = csv.reader(lines)
        next(reader)  # skip headers

        servers = []
        countries = set()
        for row in reader:
            if len(row) < 15:
                continue
            try:
                s = VPNServer(
                    hostname=row[0],
                    ip=row[1],
                    score=int(row[2]) if row[2].isdigit() else 0,
                    ping=int(row[3]) if row[3].isdigit() else 9999,
                    speed=float(row[4]) if row[4] else 0,
                    country_long=row[5],
                    country_short=row[6],
                    sessions=int(row[7]) if row[7].isdigit() else 0,
                    uptime=row[8],
                    ovpn_b64=row[14],
                )
                if s.ovpn_b64 and s.ovpn_b64.strip():
                    servers.append(s)
                    countries.add(s.country_short)
            except Exception:
                continue

        self.servers = sorted(servers, key=lambda x: x.score, reverse=True)
        self.root.after(0, self.populate_tree)
        self.root.after(0, lambda: self.set_status(f"Loaded {len(self.servers)} servers"))
        self.root.after(0, self.progress.stop)

        # Populate country filter
        sorted_countries = sorted(countries)
        self.root.after(0, lambda: self.country_combo.configure(values=["All"] + sorted_countries))
        self.root.after(0, lambda: self.country_combo.set("All"))

    def populate_tree(self, server_list: list[VPNServer] | None = None):
        for item in self.tree.get_children():
            self.tree.delete(item)

        servers = server_list if server_list is not None else self.servers
        for i, s in enumerate(servers, 1):
            speed_str = f"{s.speed/1_000_000:.1f} Mbps" if s.speed > 0 else "N/A"
            self.tree.insert("", tk.END, values=(
                i, s.hostname, s.country_short, speed_str,
                s.ping, s.score, s.sessions
            ))

    # ===================== UI EVENTS =====================

    def on_tree_double_click(self, event):
        self.on_connect()

    def on_refresh(self):
        self.fetch_servers_async()

    def on_country_filter(self, event=None):
        country = self.country_var.get()
        if country == "All" or not country:
            self.populate_tree(self.servers)
        else:
            filtered = [s for s in self.servers if s.country_short == country]
            self.populate_tree(filtered)

    def on_search(self):
        query = self.search_var.get().strip().lower()
        if not query:
            self.populate_tree(self.servers)
            return
        filtered = [s for s in self.servers if query in s.hostname.lower() or query in s.country_long.lower()]
        self.populate_tree(filtered)

    def on_clear_search(self):
        self.search_var.set("")
        self.country_var.set("All")
        self.populate_tree(self.servers)

    def set_status(self, text: str):
        self.status_var.set(text)
        if "Connected" in text and "Connecting" not in text:
            self.status_label.configure(foreground="green")
        elif "Disconnected" in text or "Error" in text or "failed" in text.lower():
            self.status_label.configure(foreground="red")
        else:
            self.status_label.configure(foreground="black")

    def update_buttons(self):
        if self.is_connecting:
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.DISABLED)
        elif self.is_connected:
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
        else:
            self.connect_btn.config(state=tk.NORMAL)
            self.disconnect_btn.config(state=tk.DISABLED)

    def log(self, message: str):
        self.log_lines.append(message)
        if len(self.log_lines) > self.max_log_lines:
            self.log_lines = self.log_lines[-self.max_log_lines:]

        def _update():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        self.root.after(0, _update)


def main():
    root = tk.Tk()
    # Set DPI awareness for crisp text on high-DPI displays
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = VPNGateApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()