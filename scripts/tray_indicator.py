#!/usr/bin/env python3
"""
vLLM Dashboard - Native Ayatana/GTK3 System Tray Indicator
Perfetta integrazione con il pannello XFCE / Linux Mint (supporto hover, click nativo, menu GTK).
"""

import os
import sys
import shutil
import subprocess
import webbrowser
import signal

import gi
gi.require_version('Gtk', '3.0')

try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except Exception:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as AppIndicator

from gi.repository import Gtk, GLib

SERVICE_NAME = "vllm-dashboard.service"
DASHBOARD_URL = "http://localhost:5000"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

ICON_ACTIVE = os.path.join(ASSETS_DIR, "icon-active.png")
ICON_INACTIVE = os.path.join(ASSETS_DIR, "icon-inactive.png")
ICON_STARTING = os.path.join(ASSETS_DIR, "icon-starting.png")


class VllmTrayIndicator:
    def __init__(self):
        self.current_status = self.check_service_status()

        # Creazione dell'indicatore nativo Ayatana / AppIndicator
        initial_icon = self.get_icon_for_status(self.current_status)
        self.indicator = AppIndicator.Indicator.new(
            "vllm-dashboard-indicator",
            initial_icon,
            AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("vLLM Dashboard")

        # Costruisce il menu GTK nativo
        self.menu = Gtk.Menu()
        self.build_menu()
        self.indicator.set_menu(self.menu)

        # Polling periodico ogni 2 secondi
        GLib.timeout_add_seconds(2, self.on_timer_tick)

    def get_icon_for_status(self, status: str) -> str:
        if status == "active":
            return ICON_ACTIVE
        elif status in ("activating", "starting", "deactivating"):
            return ICON_STARTING
        else:
            return ICON_INACTIVE

    def check_service_status(self) -> str:
        try:
            res = subprocess.run(
                ["systemctl", "--user", "is-active", SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=2
            )
            status = res.stdout.strip()
            if status in ("active", "inactive", "failed", "activating", "deactivating"):
                return status
            return "inactive"
        except Exception:
            return "unknown"

    def send_notification(self, title: str, message: str):
        if shutil.which("notify-send"):
            try:
                subprocess.Popen([
                    "notify-send",
                    "-a", "vLLM Dashboard",
                    "-i", ICON_ACTIVE if os.path.exists(ICON_ACTIVE) else "utilities-system-monitor",
                    title,
                    message
                ])
            except Exception:
                pass

    def build_menu(self):
        # 1. Voce informativa stato
        self.status_item = Gtk.MenuItem(label=self.get_status_label())
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        # Separatore
        self.menu.append(Gtk.SeparatorMenuItem())

        # 2. Apri Dashboard nel Browser
        self.open_item = Gtk.MenuItem(label="🌐  Apri Dashboard nel Browser")
        self.open_item.connect("activate", self.on_open_dashboard)
        self.menu.append(self.open_item)

        # Separatore
        self.menu.append(Gtk.SeparatorMenuItem())

        # 3. Avvia Servizio
        self.start_item = Gtk.MenuItem(label="▶️  Avvia Servizio")
        self.start_item.connect("activate", self.on_start_service)
        self.menu.append(self.start_item)

        # 4. Ferma Servizio
        self.stop_item = Gtk.MenuItem(label="⏹️  Ferma Servizio")
        self.stop_item.connect("activate", self.on_stop_service)
        self.menu.append(self.stop_item)

        # 5. Riavvia Servizio
        self.restart_item = Gtk.MenuItem(label="🔄  Riavvia Servizio")
        self.restart_item.connect("activate", self.on_restart_service)
        self.menu.append(self.restart_item)

        # Separatore
        self.menu.append(Gtk.SeparatorMenuItem())

        # 6. Visualizza Log
        self.logs_item = Gtk.MenuItem(label="📜  Visualizza Log in Tempo Reale")
        self.logs_item.connect("activate", self.on_view_logs)
        self.menu.append(self.logs_item)

        # Separatore
        self.menu.append(Gtk.SeparatorMenuItem())

        # 7. Esci
        self.quit_item = Gtk.MenuItem(label="❌  Esci (Chiudi Tray)")
        self.quit_item.connect("activate", self.on_quit)
        self.menu.append(self.quit_item)

        self.update_menu_state()
        self.menu.show_all()

    def get_status_label(self) -> str:
        if self.current_status == "active":
            return "● Stato: In Esecuzione 🟢"
        elif self.current_status in ("activating", "starting"):
            return "● Stato: In Avvio... 🟡"
        elif self.current_status == "failed":
            return "● Stato: Errore / Fallito 🔴"
        else:
            return "● Stato: Fermo / Inattivo ⚪"

    def update_menu_state(self):
        self.status_item.set_label(self.get_status_label())
        is_active = (self.current_status == "active")
        self.start_item.set_sensitive(not is_active)
        self.stop_item.set_sensitive(is_active)
        self.restart_item.set_sensitive(is_active)

    def on_timer_tick(self) -> bool:
        new_status = self.check_service_status()
        if new_status != self.current_status:
            self.current_status = new_status
            icon_path = self.get_icon_for_status(new_status)
            self.indicator.set_icon_full(icon_path, f"vLLM Dashboard: {new_status}")
            self.update_menu_state()
        return True  # Continua il loop del timer

    def on_open_dashboard(self, _):
        webbrowser.open(DASHBOARD_URL)

    def on_start_service(self, _):
        self.current_status = "starting"
        self.indicator.set_icon_full(ICON_STARTING, "vLLM Dashboard: Starting")
        self.update_menu_state()
        subprocess.Popen(["systemctl", "--user", "start", SERVICE_NAME])
        GLib.timeout_add_seconds(2, self.on_timer_tick)
        self.send_notification("vLLM Dashboard", "Avvio del servizio in corso...")

    def on_stop_service(self, _):
        self.current_status = "deactivating"
        self.indicator.set_icon_full(ICON_STARTING, "vLLM Dashboard: Stopping")
        self.update_menu_state()
        subprocess.Popen(["systemctl", "--user", "stop", SERVICE_NAME])
        GLib.timeout_add_seconds(2, self.on_timer_tick)
        self.send_notification("vLLM Dashboard", "Arresto del servizio in corso...")

    def on_restart_service(self, _):
        self.current_status = "starting"
        self.indicator.set_icon_full(ICON_STARTING, "vLLM Dashboard: Restarting")
        self.update_menu_state()
        subprocess.Popen(["systemctl", "--user", "restart", SERVICE_NAME])
        GLib.timeout_add_seconds(2, self.on_timer_tick)
        self.send_notification("vLLM Dashboard", "Riavvio del servizio in corso...")

    def on_view_logs(self, _):
        terminals = ["xfce4-terminal", "gnome-terminal", "mate-terminal", "x-terminal-emulator", "xterm"]
        cmd = f"journalctl --user -u {SERVICE_NAME} -f -n 50"
        for term in terminals:
            if shutil.which(term):
                if term == "xfce4-terminal":
                    subprocess.Popen([term, "--title=vLLM Dashboard Logs", "--execute", "bash", "-c", cmd])
                elif term == "gnome-terminal":
                    subprocess.Popen([term, "--title=vLLM Dashboard Logs", "--", "bash", "-c", cmd])
                else:
                    subprocess.Popen([term, "-e", f"bash -c '{cmd}'"])
                return
        self.send_notification("Errore", "Nessun emulatore di terminale trovato.")

    def on_quit(self, _):
        Gtk.main_quit()


def main():
    # Gestione segnali di interruzione (SIGINT, SIGTERM)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    app = VllmTrayIndicator()
    Gtk.main()


if __name__ == "__main__":
    main()
