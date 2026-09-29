#!/usr/bin/env python3
"""Snayw Tools — boîte à outils graphique interactive."""

import base64
import hashlib
import ipaddress
import json
import math
import os
import platform
import random
import re
import secrets
import shutil
import socket
import string
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


class SnaywApp:
    VERSION = "1.0"
    BG = "#090a0b"
    PANEL = "#121315"
    PANEL2 = "#1b1c1f"
    TEXT = "#f1f1f2"
    MUTED = "#a4a5a7"
    CYAN = "#e5e5e6"
    GREEN = "#e1e1e2"
    FLOATING = "#b8babe"

    def __init__(self, root):
        self.root = root
        root.title(f"Snayw v{self.VERSION} — Boîte à outils")
        root.geometry("1180x780")
        root.minsize(900, 620)
        root.configure(bg=self.BG)
        self.motion_enabled = tk.BooleanVar(master=root, value=True)
        self.transparency = tk.DoubleVar(master=root, value=.86)
        self.animation_rate = tk.IntVar(master=root, value=360)
        self.particle_count = tk.IntVar(master=root, value=32)
        self.mouse_radius = tk.DoubleVar(master=root, value=150)
        self.settings_dir = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Snayw Tools")
        self.settings_path = os.path.join(self.settings_dir, "settings.json")
        self.settings_save_job = None
        self._load_settings()
        try:
            root.attributes("-alpha", self.transparency.get())
        except tk.TclError:
            pass
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.description_labels = []
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
            style.configure("TCombobox", fieldbackground="#191a1c", background="#292a2d",
                            foreground=self.TEXT, arrowcolor=self.CYAN, bordercolor="#424347")
            style.configure("Snayw.Vertical.TScrollbar", background="#2a2b2e", troughcolor=self.PANEL,
                            bordercolor=self.PANEL, arrowcolor=self.MUTED, relief="flat")
            style.map("TCombobox", fieldbackground=[("readonly", "#191a1c")],
                      foreground=[("readonly", self.TEXT)], selectbackground=[("readonly", "#292a2d")],
                      selectforeground=[("readonly", self.TEXT)])
        except tk.TclError:
            pass
        cursor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snayw_cursor.cur")
        self.pointer_cursor = "arrow"
        if os.path.isfile(cursor_path):
            candidate = "@" + cursor_path.replace("\\", "/")
            try:
                root.configure(cursor=candidate)
                root.option_add("*cursor", candidate)
                self.pointer_cursor = candidate
            except tk.TclError:
                pass
        self.canvas = tk.Canvas(root, bg=self.BG, highlightthickness=0)
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.particles = []
        self.ripples = []
        self.pointer_rings = None
        self.mouse = [500, 300]
        self.particle_area = None
        self.last_ripple = 0
        self.last_frame = time.perf_counter()
        self.next_frame_at = self.last_frame + (1 / 360)
        self.last_drawn_mouse = None
        self.canvas.bind("<Configure>", lambda _e: self.draw_particles())
        root.bind_all("<Motion>", self.track_mouse, add="+")
        self.draw_particles()
        self.build_shell()
        self.show_page("Accueil")
        self.refresh_effects()
        self.animate()

    def _load_settings(self):
        try:
            with open(self.settings_path, "r", encoding="utf-8") as file:
                settings = json.load(file)
            self.motion_enabled.set(bool(settings.get("motion_enabled", True)))
            self.transparency.set(max(.70, min(1.0, float(settings.get("transparency", .86)))))
            self.animation_rate.set(max(30, min(360, int(settings.get("animation_rate", 360)))))
            self.particle_count.set(max(12, min(64, int(settings.get("particle_count", 32)))))
            self.mouse_radius.set(max(60, min(240, float(settings.get("mouse_radius", 150)))))
        except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
            pass

    def schedule_settings_save(self):
        if self.settings_save_job:
            try:
                self.root.after_cancel(self.settings_save_job)
            except tk.TclError:
                pass
        self.settings_save_job = self.root.after(500, self._save_settings)

    def _save_settings(self):
        self.settings_save_job = None
        settings = {
            "motion_enabled": self.motion_enabled.get(),
            "transparency": self.transparency.get(),
            "animation_rate": self.animation_rate.get(),
            "particle_count": self.particle_count.get(),
            "mouse_radius": self.mouse_radius.get(),
        }
        try:
            os.makedirs(self.settings_dir, exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as file:
                json.dump(settings, file, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def close(self):
        self._save_settings()
        self.root.destroy()

    def _scroll_content(self, event):
        if event.widget is not self.content_canvas and not str(event.widget).startswith(str(self.content)):
            return None
        if getattr(event, "num", None) == 4:
            amount = -1
        elif getattr(event, "num", None) == 5:
            amount = 1
        else:
            delta = getattr(event, "delta", 0)
            amount = -int(delta / 120) if delta else 0
            if amount == 0 and delta:
                amount = -1 if delta > 0 else 1
        if amount:
            if isinstance(event.widget, tk.Text):
                event.widget.yview_scroll(amount * 3, "units")
            else:
                self.content_canvas.yview_scroll(amount * 3, "units")
            return "break"
        return None

    def _content_resized(self, _event=None):
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
        self.update_card_width()

    def track_mouse(self, event):
        position = [event.x_root - self.root.winfo_rootx(), event.y_root - self.root.winfo_rooty()]
        now = time.monotonic()
        if self.motion_enabled.get() and now - self.last_ripple > .09 and abs(position[0] - self.mouse[0]) + abs(position[1] - self.mouse[1]) > 12:
            if len(self.ripples) >= 10:
                old = self.ripples.pop(0)
                self.canvas.delete(old[4])
                self.canvas.delete(old[5])
            shadow = self.canvas.create_oval(position[0]-2, position[1]-2, position[0]+2, position[1]+2,
                                             outline="#050505", width=3, tags="particle")
            ring = self.canvas.create_oval(position[0]-2, position[1]-2, position[0]+2, position[1]+2,
                                           outline="#f4f4f4", width=1, tags="particle")
            self.ripples.append([position[0], position[1], 2, .32, shadow, ring])
            self.last_ripple = now
        self.mouse = position

    def draw_particles(self):
        width, height = max(self.root.winfo_width(), 850), max(self.root.winfo_height(), 600)
        if self.particle_area != (width, height):
            for particle in self.particles:
                particle[0] = random.randrange(width)
                particle[1] = random.randrange(height)
            self.particle_area = (width, height)
        target = max(12, min(64, self.particle_count.get()))
        while len(self.particles) < target:
            i = len(self.particles)
            x, y, radius, speed = ((i * 137) % width), ((i * 83) % height), 1 + (i % 2), 4 + (i % 5) * 2
            oval = self.canvas.create_oval(x-radius, y-radius, x+radius, y+radius, fill=self.FLOATING,
                                           stipple="gray12", outline="", tags="particle")
            self.particles.append([x, y, radius, speed, oval, None])
        while len(self.particles) > target:
            self.canvas.delete(self.particles.pop()[4])
        for particle in self.particles:
            x, y, radius, _speed, oval, was_near = particle
            dx, dy = x - self.mouse[0], y - self.mouse[1]
            radius_limit = self.mouse_radius.get()
            near = dx * dx + dy * dy < radius_limit * radius_limit
            self.canvas.coords(oval, x-radius, y-radius, x+radius, y+radius)
            if near != was_near:
                self.canvas.itemconfigure(oval, fill="#f0f0f0" if near else self.FLOATING,
                                          stipple="gray25" if near else "gray12")
                particle[5] = near
        for x, y, radius, _life, shadow, ring in self.ripples:
            bounds = (x-radius, y-radius, x+radius, y+radius)
            self.canvas.coords(shadow, *bounds)
            self.canvas.coords(ring, *bounds)
        x, y = self.mouse
        if self.pointer_rings is None:
            outer = self.canvas.create_oval(x-12, y-12, x+12, y+12, outline="#050505", width=3, tags="particle")
            inner = self.canvas.create_oval(x-9, y-9, x+9, y+9, outline="#f4f4f4", width=1, tags="particle")
            self.pointer_rings = (outer, inner)
        if self.last_drawn_mouse != tuple(self.mouse):
            self.canvas.coords(self.pointer_rings[0], x-12, y-12, x+12, y+12)
            self.canvas.coords(self.pointer_rings[1], x-9, y-9, x+9, y+9)
            self.last_drawn_mouse = tuple(self.mouse)

    def animate(self):
        width, height = max(self.root.winfo_width(), 850), max(self.root.winfo_height(), 600)
        if self.root.state() == "iconic" or not self.motion_enabled.get():
            self.root.after(250, self.animate)
            return
        now = time.perf_counter()
        delta = min(now - self.last_frame, .05)
        self.last_frame = now
        for particle in self.particles:
            particle[1] -= particle[3] * delta
            if particle[1] < 0:
                particle[1] = height
                particle[0] = random.randrange(width)
        for ripple in self.ripples:
            ripple[2] += 125 * delta
            ripple[3] -= delta
        live_ripples = []
        for ripple in self.ripples:
            if ripple[3] > 0:
                live_ripples.append(ripple)
            else:
                self.canvas.delete(ripple[4])
                self.canvas.delete(ripple[5])
        self.ripples = live_ripples
        self.draw_particles()
        # Request up to 360 updates/s; Tk, Windows and the display impose the real limit.
        rate = max(30, min(360, self.animation_rate.get()))
        self.next_frame_at += 1 / rate
        now = time.perf_counter()
        delay = max(1, math.ceil((self.next_frame_at - now) * 1000))
        if now - self.next_frame_at > .03:
            self.next_frame_at = now
        self.root.after(delay, self.animate)

    def build_shell(self):
        shell = tk.Frame(self.root, bg=self.BG)
        shell.place(relx=.025, rely=.035, relwidth=.95, relheight=.93)
        top = tk.Frame(shell, bg=self.BG)
        top.pack(fill="x", pady=(0, 18))
        tk.Label(top, text="S N A Y W", fg=self.CYAN, bg=self.BG, font=("Consolas", 23, "bold")).pack(side="left")
        tk.Label(top, text=f"V{self.VERSION}  ·  BOÎTE À OUTILS", fg=self.MUTED, bg=self.BG, font=("Consolas", 10)).pack(side="left", padx=14, pady=(8, 0))
        self.make_button(top, "⚙  PARAMÈTRES", lambda: self.show_page("Paramètres")).pack(side="right", pady=(5, 0))
        body = tk.Frame(shell, bg=self.BG)
        body.pack(fill="both", expand=True)
        nav = tk.Frame(body, bg=self.PANEL, width=205, padx=13, pady=15)
        nav.pack(side="left", fill="y", padx=(0, 16))
        nav.pack_propagate(False)
        tk.Label(nav, text="MENU", fg=self.MUTED, bg=self.PANEL, font=("Consolas", 9, "bold")).pack(anchor="w", padx=8, pady=(4, 12))
        for name, icon in [("Accueil", "⌂"), ("IP & réseau", "⌁"), ("Pseudo", "@"), ("Générateurs", "✳"), ("Sécurité e-mail", "✓"), ("Serveur Discord", "#"), ("Performance PC", "⚡"), ("PC approfondi", "▣"), ("Personnaliser PC", "✦"), ("Outils texte", "⌘")]:
            self.make_button(nav, f"{icon}   {name}", lambda n=name: self.show_page(n), compact=True).pack(fill="x", pady=2)
        content_host = tk.Frame(body, bg=self.PANEL)
        content_host.pack(side="left", fill="both", expand=True)
        self.content_canvas = tk.Canvas(content_host, bg=self.PANEL, highlightthickness=0, bd=0)
        self.content_canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(content_host, orient="vertical", command=self.content_canvas.yview,
                               style="Snayw.Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        self.content_canvas.configure(yscrollcommand=scroll.set)
        self.content = tk.Frame(self.content_canvas, bg=self.PANEL, padx=26, pady=23)
        self.content_window = self.content_canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._content_resized)
        self.content_canvas.bind("<Configure>", lambda event: self.content_canvas.itemconfigure(self.content_window, width=event.width))
        self.root.bind_all("<MouseWheel>", self._scroll_content, add="+")
        self.root.bind_all("<Button-4>", self._scroll_content, add="+")
        self.root.bind_all("<Button-5>", self._scroll_content, add="+")

    def make_button(self, parent, text, command, compact=False):
        button = tk.Button(parent, text=text, command=command, bg=self.PANEL2, fg=self.TEXT,
                           activebackground="#2b2d30", activeforeground=self.CYAN, relief="flat",
                           bd=0, cursor=self.pointer_cursor if self.motion_enabled.get() else "arrow",
                           anchor="w" if compact else "center",
                           padx=13, pady=8 if compact else 10,
                           font=("Consolas", 10, "bold"))
        button.bind("<Enter>", lambda _e: button.configure(fg=self.CYAN))
        button.bind("<Leave>", lambda _e: button.configure(fg=self.TEXT))
        return button

    def apply_cursor(self, cursor):
        self.root.option_add("*cursor", cursor)
        try:
            self.root.configure(cursor=cursor)
        except tk.TclError:
            pass
        pending = list(self.root.winfo_children())
        while pending:
            widget = pending.pop()
            try:
                widget.configure(cursor=cursor)
            except tk.TclError:
                pass
            pending.extend(widget.winfo_children())

    def refresh_effects(self):
        enabled = self.motion_enabled.get()
        self.apply_cursor(self.pointer_cursor if enabled else "arrow")
        try:
            self.canvas.itemconfigure("particle", state="normal" if enabled else "hidden")
        except tk.TclError:
            pass
        if enabled:
            self.last_frame = time.perf_counter()
            self.draw_particles()

    def set_transparency(self, value):
        try:
            self.root.attributes("-alpha", float(value))
        except (tk.TclError, ValueError):
            pass
        self.schedule_settings_save()

    def clear_content(self):
        for widget in self.content.winfo_children():
            widget.destroy()
        self.description_labels = []

    def update_card_width(self, _event=None):
        wrap = max(260, self.content.winfo_width() - 96)
        for label in self.description_labels:
            if label.winfo_exists():
                label.configure(wraplength=wrap)

    def title(self, heading, subtitle):
        tk.Label(self.content, text=heading, fg="#ededee", bg=self.PANEL, font=("Consolas", 22, "bold")).pack(anchor="w")
        tk.Label(self.content, text=subtitle, fg=self.MUTED, bg=self.PANEL, font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 20))

    def card(self, title, description):
        card = tk.Frame(self.content, bg=self.PANEL2, padx=17, pady=15)
        card.pack(fill="x", pady=7)
        tk.Label(card, text=title, fg=self.CYAN, bg=self.PANEL2, font=("Consolas", 12, "bold")).pack(anchor="w")
        label = tk.Label(card, text=description, fg=self.MUTED, bg=self.PANEL2,
                         font=("Segoe UI", 10), justify="left",
                         wraplength=max(260, self.content.winfo_width() - 96))
        label.pack(anchor="w", fill="x", pady=(6, 0))
        self.description_labels.append(label)
        return card

    def entry(self, parent, hint=""):
        field = tk.Entry(parent, bg="#0e0f11", fg=self.TEXT, insertbackground=self.CYAN,
                         relief="flat", font=("Consolas", 12), highlightthickness=1,
                         highlightbackground="#424347", highlightcolor=self.CYAN)
        field.pack(fill="x", pady=(8, 11), ipady=8)
        if hint:
            field.insert(0, hint)
            field.config(fg=self.MUTED)
            field.bind("<FocusIn>", lambda _e: (field.delete(0, "end"), field.config(fg=self.TEXT)) if field.get() == hint else None)
        return field

    def output(self, parent, initial=""):
        frame = tk.Frame(parent, bg=self.PANEL2)
        frame.pack(fill="x", pady=(12, 0))
        box = tk.Text(frame, height=6, bg="#0e0f11", fg=self.GREEN, insertbackground=self.CYAN,
                      relief="flat", font=("Consolas", 10), wrap="word", padx=10, pady=9)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=scrollbar.set)
        box.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        if initial:
            box.insert("1.0", initial)
        return box

    def show_page(self, page):
        self.clear_content()
        if page == "Accueil":
            self.title("Boîte à outils", "Des outils simples, accessibles en un clic.")
            self.card("ANALYSE IP", "Résous un nom de domaine et vérifie si une adresse est publique ou réservée.")
            self.card("PSEUDO", "Ouvre le profil public d'un pseudo sur une plateforme choisie. Aucune identification entre sites.")
            self.card("PERFORMANCE PC", "Aperçu des fichiers temporaires anciens avant nettoyage et conseils PC sûrs.")
            row = tk.Frame(self.content, bg=self.PANEL)
            row.pack(fill="x", pady=13)
            for name in ("IP & réseau", "Pseudo", "Performance PC"):
                self.make_button(row, name, lambda n=name: self.show_page(n)).pack(side="left", padx=(0, 9))
        elif page == "IP & réseau":
            self.title("IP & réseau", "Résolution DNS, URL de profil et classification d’adresse IP.")
            card = self.card("Analyser un site, un lien ou une IP", "Exemples : google.com, https://www.facebook.com/nom.profil ou 8.8.8.8. L’outil affiche l’adresse réseau, jamais l’identité ou la position exacte d’une personne.")
            field = self.entry(card, "google.com")
            out = self.output(card)
            resolve_button = None
            def resolve():
                target = field.get().strip()
                try:
                    if not target or target == "google.com" and field.cget("fg") == self.MUTED:
                        raise ValueError("Entre une adresse IP, un nom de domaine ou une URL.")
                    candidate = target
                    if "://" in target:
                        candidate = urlsplit(target).hostname or ""
                    elif any(mark in target for mark in ("/", "?", "#")):
                        candidate = urlsplit("//" + target).hostname or ""
                    if not candidate:
                        raise ValueError("Aucun nom de domaine détecté dans cette entrée.")
                    direct_ip = None
                    try:
                        direct_ip = str(ipaddress.ip_address(candidate.strip("[]")))
                    except ValueError:
                        direct_ip = None
                except (socket.gaierror, ValueError, OSError) as exc:
                    out.delete("1.0", "end")
                    out.insert("1.0", f"Résolution impossible : {exc}")
                    return
                resolve_button.config(state="disabled")
                out.delete("1.0", "end")
                out.insert("1.0", "Résolution de l’hôte…")
                def lookup():
                    try:
                        addresses = [direct_ip] if direct_ip else sorted({x[4][0] for x in socket.getaddrinfo(candidate, None, type=socket.SOCK_STREAM)})
                        if not addresses:
                            raise socket.gaierror("Aucune adresse IP retournée par le DNS.")
                        lines = [f"Nom analysé : {candidate}", f"Adresses trouvées : {len(addresses)}"]
                        for address in addresses:
                            parsed_ip = ipaddress.ip_address(address.split("%")[0])
                            category = "publique" if parsed_ip.is_global else "privée / réservée / locale"
                            lines.append(f"• {address}  —  IPv{parsed_ip.version}, {category}")
                        lines.append("\nLa résolution DNS ne révèle pas l’identité ni l’adresse exacte d’une personne.")
                        result_text = "\n".join(lines)
                    except (socket.gaierror, ValueError, OSError) as exc:
                        result_text = f"Résolution impossible : {exc}"
                    try:
                        self.root.after(0, lambda text=result_text: finish_lookup(text))
                    except tk.TclError:
                        pass
                def finish_lookup(text):
                    if out.winfo_exists():
                        out.delete("1.0", "end")
                        out.insert("1.0", text)
                    if resolve_button.winfo_exists():
                        resolve_button.config(state="normal")
                threading.Thread(target=lookup, daemon=True).start()
            resolve_button = self.make_button(card, "RÉSOUDRE", resolve)
            resolve_button.pack(anchor="w")
            ping = self.card("Tester le ping", "Mesure le délai vers un hôte. Un test ne peut pas garantir une baisse du ping.")
            host = self.entry(ping, "google.com")
            pingout = self.output(ping)
            ping_button = None
            def do_ping():
                target = host.get().strip()
                if not target or any(ch.isspace() for ch in target) or target.startswith("-"):
                    return messagebox.showerror("Snayw Tools", "Nom d'hôte invalide.")
                ping_button.config(state="disabled")
                pingout.delete("1.0", "end")
                pingout.insert("1.0", "Test en cours…")
                def run_ping():
                    try:
                        result = subprocess.run(["ping", "-n" if os.name == "nt" else "-c", "4", target], capture_output=True, text=True, timeout=12)
                        result_text = (result.stdout or result.stderr or "Aucune réponse.")[-1800:]
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        result_text = f"Test impossible : {exc}"
                    try:
                        self.root.after(0, lambda text=result_text: finish_ping(text))
                    except tk.TclError:
                        pass
                def finish_ping(text):
                    if pingout.winfo_exists():
                        pingout.delete("1.0", "end")
                        pingout.insert("1.0", text)
                    if ping_button.winfo_exists():
                        ping_button.config(state="normal")
                threading.Thread(target=run_ping, daemon=True).start()
            ping_button = self.make_button(ping, "LANCER LE TEST", do_ping)
            ping_button.pack(anchor="w")
        elif page == "Pseudo":
            self.title("Profil public", "Ouvre un pseudo exact sur une plateforme sélectionnée.")
            card = self.card("Recherche ciblée", "Choisis un site et ouvre le profil correspondant. Snayw Tools ne recherche pas une personne sur tous les sites et ne confirme pas qu'il s'agit de la même personne.")
            field = self.entry(card, "pseudo")
            tk.Label(card, text="Plateforme", fg=self.MUTED, bg=self.PANEL2, font=("Segoe UI", 10)).pack(anchor="w")
            sites = {"GitHub": "https://github.com/{}", "GitLab": "https://gitlab.com/{}",
                     "Reddit": "https://www.reddit.com/user/{}/", "Twitch": "https://www.twitch.tv/{}",
                     "Instagram": "https://www.instagram.com/{}/", "TikTok": "https://www.tiktok.com/@{}",
                     "YouTube": "https://www.youtube.com/@{}", "Bluesky": "https://bsky.app/profile/{}",
                     "X": "https://x.com/{}", "Facebook": "https://www.facebook.com/{}",
                     "Pinterest": "https://www.pinterest.com/{}"}
            choice = tk.StringVar(value="GitHub")
            selector = ttk.Combobox(card, textvariable=choice, values=list(sites), state="readonly", font=("Segoe UI", 10))
            selector.pack(anchor="w", fill="x", pady=(6, 12), ipady=4)
            out = self.output(card)
            def open_profile():
                username = field.get().strip().lstrip("@")
                if not username or username == "pseudo" or any(ch.isspace() for ch in username):
                    return messagebox.showerror("Snayw Tools", "Entre un pseudo valide.")
                url = sites[choice.get()].format(quote(username, safe="._-"))
                webbrowser.open(url)
                out.delete("1.0", "end")
                out.insert("1.0", f"Profil ouvert dans ton navigateur :\n{url}\n\nLe site décide si le profil existe et s'il est public.")
            self.make_button(card, "OUVRIR LE PROFIL", open_profile).pack(anchor="w")
            gen = self.card("Créer un pseudo", "Génère une combinaison originale ; vérifie ensuite sa disponibilité sur le site choisi.")
            generated = self.output(gen, "Ton pseudo apparaîtra ici.")
            def make_handle():
                left = secrets.choice(["Pixel", "Nova", "Frost", "Shadow", "Comet", "Lunar", "Snay", "Echo", "Rogue", "Cloud", "Storm", "Neon"])
                right = secrets.choice(["Fox", "Wolf", "Byte", "Rider", "Ninja", "Spark", "Drift", "Quest", "Wave", "Viper", "Knight", "Ghost"])
                handle = left + right
                if secrets.randbelow(2):
                    handle += str(secrets.randbelow(1000)).zfill(3)
                generated.delete("1.0", "end")
                generated.insert("1.0", handle)
            self.make_button(gen, "GÉNÉRER UN PSEUDO", make_handle).pack(anchor="w")
            self.make_button(gen, "COPIER LE PSEUDO", lambda: self.copy_text(generated, "Pseudo")).pack(anchor="w", pady=(7, 0))
        elif page == "Sécurité e-mail":
            self.title("E-mail & sécurité", "Vérifications locales et accès au service officiel de surveillance des fuites.")
            card = self.card("Vérifier le format d’une adresse", "Le contrôle se fait sur cet ordinateur. Il ne confirme pas que la boîte existe et n’envoie pas l’adresse à Snayw Tools.")
            address = self.entry(card, "nom@exemple.com")
            email_out = self.output(card)
            def validate_email():
                candidate = address.get().strip()
                valid = candidate != "nom@exemple.com" and bool(re.fullmatch(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}", candidate, flags=re.IGNORECASE))
                email_out.delete("1.0", "end")
                email_out.insert("1.0", "Format plausible. Cela ne confirme ni l’existence de la boîte, ni une fuite." if valid else "Format invalide ou incomplet. Exemple : nom@domaine.fr")
                return valid
            def open_monitor():
                if not validate_email():
                    return
                webbrowser.open("https://monitor.mozilla.org/")
                email_out.insert("end", "\n\nMozilla Monitor s’est ouvert. Saisis l’adresse sur le site officiel ; Snayw ne la lui transmet pas automatiquement.")
            row = tk.Frame(card, bg=self.PANEL2)
            row.pack(anchor="w")
            self.make_button(row, "VÉRIFIER LE FORMAT", validate_email).pack(side="left", padx=(0, 8))
            self.make_button(row, "OUVRIR MOZILLA MONITOR", open_monitor).pack(side="left")
            password_card = self.card("Indice de robustesse du mot de passe", "L’analyse est locale et indicative. Elle ne recherche pas les fuites et n’enregistre ni ne transmet le mot de passe.")
            password_field = tk.Entry(password_card, show="•", bg="#0e0f11", fg=self.TEXT, insertbackground=self.CYAN,
                                      relief="flat", font=("Consolas", 12), highlightthickness=1,
                                      highlightbackground="#424347", highlightcolor=self.CYAN)
            password_field.pack(fill="x", pady=(8, 10), ipady=8)
            password_out = self.output(password_card)
            password_check_button = None
            def inspect_password():
                value = password_field.get()
                if not value:
                    password_out.delete("1.0", "end")
                    password_out.insert("1.0", "Saisis un mot de passe pour obtenir un indice local.")
                    return
                pool = sum(size for pattern, size in ((r"[a-z]", 26), (r"[A-Z]", 26), (r"[0-9]", 10), (r"[^a-zA-Z0-9]", 33)) if re.search(pattern, value))
                estimate = len(value) * math.log2(pool) if pool else 0
                if len(value) < 10:
                    level = "À renforcer"
                    tip = "Privilégie une phrase longue ou un mot de passe d’au moins 12 caractères."
                elif estimate >= 80 and len(value) >= 14:
                    level = "Robuste selon cet indice"
                    tip = "Garde-le unique pour chaque service et stocke-le dans un gestionnaire fiable."
                else:
                    level = "Intermédiaire"
                    tip = "Augmente sa longueur et mélange plusieurs types de caractères."
                password_out.delete("1.0", "end")
                password_out.insert("1.0", f"Indice : {level}\nLongueur : {len(value)} caractères\nEstimation théorique : {estimate:.0f} bits\n{tip}\n\nUne phrase courante peut être devinée malgré sa longueur : cet indice ne remplace pas un test de fuite.")
            def check_password_breach():
                value = password_field.get()
                if not value:
                    password_out.delete("1.0", "end")
                    password_out.insert("1.0", "Saisis un mot de passe pour lancer la recherche.")
                    return
                password_check_button.config(state="disabled")
                password_out.delete("1.0", "end")
                password_out.insert("1.0", "Recherche facultative… Seul un préfixe de hash sera envoyé.")
                def query_range():
                    try:
                        full_hash = hashlib.sha1(value.encode("utf-8")).hexdigest().upper()
                        request = Request(
                            f"https://api.pwnedpasswords.com/range/{full_hash[:5]}",
                            headers={"Add-Padding": "true", "User-Agent": f"Snayw Tools/{self.VERSION}"},
                        )
                        with urlopen(request, timeout=12) as response:
                            rows = response.read().decode("ascii", "replace").splitlines()
                        occurrences = 0
                        for row_text in rows:
                            suffix, separator, count = row_text.strip().partition(":")
                            if separator and suffix.upper() == full_hash[5:]:
                                occurrences = int(count)
                                break
                        if occurrences:
                            result_text = f"Mot de passe repéré {occurrences:,} fois dans la base des mots de passe compromis. Change-le immédiatement partout où tu l’as utilisé."
                        else:
                            result_text = "Aucune correspondance trouvée dans cette base. Cela ne garantit pas que le mot de passe n’a jamais été exposé ailleurs."
                    except (OSError, ValueError, UnicodeError) as exc:
                        result_text = f"Recherche indisponible : {exc}"
                    try:
                        self.root.after(0, lambda text=result_text: finish_password_check(text))
                    except tk.TclError:
                        pass
                def finish_password_check(text):
                    if password_out.winfo_exists():
                        password_out.delete("1.0", "end")
                        password_out.insert("1.0", text)
                    if password_check_button.winfo_exists():
                        password_check_button.config(state="normal")
                threading.Thread(target=query_range, daemon=True).start()
            check_description = tk.Label(password_card,
                                         text="Recherche optionnelle des mots de passe exposés : Snayw calcule le hash localement et n’envoie qu’un préfixe partiel à Have I Been Pwned. Le mot de passe complet n’est pas envoyé.",
                                         fg=self.MUTED, bg=self.PANEL2, font=("Segoe UI", 9),
                                         justify="left", wraplength=max(260, self.content.winfo_width() - 110))
            check_description.pack(anchor="w", fill="x", pady=(10, 4))
            self.description_labels.append(check_description)
            password_buttons = tk.Frame(password_card, bg=self.PANEL2)
            password_buttons.pack(anchor="w")
            self.make_button(password_buttons, "ANALYSER LOCALEMENT", inspect_password).pack(side="left", padx=(0, 8))
            password_check_button = self.make_button(password_buttons, "VÉRIFIER LES FUITES CONNUES", check_password_breach)
            password_check_button.pack(side="left")
            self.card("Réagir à une fuite", "Change le mot de passe du service touché et de tout compte où il a été réutilisé. Active la double authentification, ferme les sessions inconnues et vérifie les méthodes de récupération.")
        elif page == "Serveur Discord":
            self.title("Créateur de serveur Discord", "Prépare une structure de serveur à reproduire dans Discord.")
            card = self.card("Modèle de serveur", "Prépare les catégories, salons et rôles, puis ouvre Discord pour terminer la création dans ton compte. Snayw Tools ne te demandera jamais ton mot de passe Discord.")
            server_name = self.entry(card, "Nom du serveur")
            kind = tk.StringVar(value="Gaming")
            ttk.Combobox(card, textvariable=kind, values=["Gaming", "Communauté", "Études", "Créateur"], state="readonly").pack(anchor="w", fill="x", pady=6)
            result = self.output(card)
            plans = {
                "Gaming": ("ACCUEIL\n  #bienvenue · #règles · #annonces\nCOMMUNAUTÉ\n  #général · #recherche-de-joueurs · #clips\nJEUX\n  #jeu-1 · #jeu-2 · #tournois\nVOCAL\n  Vocal 1 · Vocal 2 · AFK", "Admin · Modérateur · Membre · Bot", "Restreins les liens et mentions des nouveaux membres ; limite les permissions d'administration aux personnes de confiance."),
                "Communauté": ("ACCUEIL\n  #bienvenue · #règles · #annonces\nDISCUSSION\n  #général · #médias · #suggestions\nACTIVITÉS\n  #événements · #présentations\nVOCAL\n  Salon vocal · Événements", "Admin · Modérateur · Membre · Nouveau", "Active le filtrage des contenus indésirables et garde les salons d'annonces en lecture seule pour les membres."),
                "Études": ("ACCUEIL\n  #bienvenue · #règles · #annonces\nCOURS\n  #aide · #ressources · #devoirs\nGROUPES\n  #groupe-1 · #groupe-2\nVOCAL\n  Étude silencieuse · Travail en groupe", "Admin · Modérateur · Étudiant · Tuteur", "Évite de publier des données personnelles ou des informations scolaires sensibles dans les salons."),
                "Créateur": ("ACCUEIL\n  #bienvenue · #règles · #annonces\nCONTENU\n  #nouveautés · #vidéos · #coulisses\nCOMMUNAUTÉ\n  #discussion · #idées · #questions\nVOCAL\n  Live · Détente", "Admin · Modérateur · Abonné · Invité", "Sépare les annonces des discussions et précise les règles de partage et de modération du contenu.")}
            def build_server():
                name = server_name.get().strip() or "Mon serveur"
                channels, roles, guidance = plans[kind.get()]
                result.delete("1.0", "end")
                result.insert("1.0", f"SERVEUR : {name}\nMODÈLE : {kind.get()}\n\nCATÉGORIES ET SALONS\n{channels}\n\nRÔLES À CRÉER\n{roles}\n\nCONSEILS DE CONFIGURATION\n{guidance}\n\nAvant d'inviter des membres : relis les permissions, active la modération et protège les invitations.")
            def export_server():
                build_server()
                path = filedialog.asksaveasfilename(title="Enregistrer le modèle Discord", defaultextension=".txt", filetypes=[("Fichier texte", "*.txt")], initialfile="modele-serveur-discord.txt")
                if path:
                    with open(path, "w", encoding="utf-8") as file:
                        file.write(result.get("1.0", "end-1c"))
                    messagebox.showinfo("Snayw Tools", "Modèle enregistré.")
            row = tk.Frame(card, bg=self.PANEL2)
            row.pack(anchor="w")
            self.make_button(row, "CRÉER LE PLAN", build_server).pack(side="left", padx=(0, 8))
            self.make_button(row, "EXPORTER EN .TXT", export_server).pack(side="left")
            def prepare_and_open_discord():
                build_server()
                webbrowser.open("https://discord.com/channels/@me")
            self.make_button(card, "PRÉPARER LE PLAN ET OUVRIR DISCORD", prepare_and_open_discord).pack(anchor="w", pady=(10, 0))
            self.card("Terminer dans Discord", "Connecte-toi directement sur Discord, clique sur + dans la barre des serveurs, puis sur Créer mon serveur. Reprends ensuite les catégories du plan. La connexion et la validation de création restent dans Discord.")
        elif page == "Générateurs":
            self.title("Générateurs", "Génère localement des mots de passe et données de démonstration.")
            card = self.card("Code à 4 chiffres", "Code aléatoire uniquement pour une maquette ou un test local. Il ne peut pas authentifier un compte.")
            out = self.output(card)
            def generate():
                out.delete("1.0", "end")
                out.insert("1.0", f"{secrets.randbelow(10000):04d}")
            self.make_button(card, "GÉNÉRER UN CODE DE DÉMO", generate).pack(anchor="w")
            self.make_button(card, "COPIER LE CODE", lambda: self.copy_text(out, "Code de démonstration")).pack(anchor="w", pady=(7, 0))
            card2 = self.card("Mot de passe aléatoire", "Garantit une minuscule, une majuscule et un chiffre ; ajoute des symboles selon ton choix. Génération locale avec le module secrets.")
            length = tk.StringVar(value="20")
            tk.Label(card2, text="Longueur (8 à 128 caractères)", fg=self.MUTED, bg=self.PANEL2,
                     font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 2))
            length_box = tk.Spinbox(card2, from_=8, to=128, textvariable=length, width=8,
                                    bg="#0e0f11", fg=self.TEXT, insertbackground=self.CYAN,
                                    buttonbackground="#252629", relief="flat", font=("Consolas", 12))
            length_box.pack(anchor="w", pady=(0, 8), ipady=5)
            use_symbols = tk.BooleanVar(value=True)
            avoid_ambiguous = tk.BooleanVar(value=False)
            for label, variable in (("Inclure des symboles", use_symbols), ("Éviter les caractères ambigus", avoid_ambiguous)):
                tk.Checkbutton(card2, text=label, variable=variable, bg=self.PANEL2, fg=self.TEXT,
                               activebackground=self.PANEL2, activeforeground=self.CYAN,
                               selectcolor=self.BG, font=("Segoe UI", 10)).pack(anchor="w", pady=2)
            pwout = self.output(card2)
            def make_password():
                try:
                    n = int(length.get())
                    if not 8 <= n <= 128: raise ValueError
                except ValueError:
                    return messagebox.showerror("Snayw Tools", "Choisis une longueur entre 8 et 128.")
                groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits]
                if use_symbols.get():
                    groups.append("!@#$%^&*()-_=+?")
                if avoid_ambiguous.get():
                    ambiguous = set("Il1O0o")
                    groups = ["".join(char for char in group if char not in ambiguous) for group in groups]
                alphabet = "".join(groups)
                if n < len(groups):
                    return messagebox.showerror("Snayw Tools", "La longueur choisie est trop courte pour les options actives.")
                chars = [secrets.choice(group) for group in groups]
                chars.extend(secrets.choice(alphabet) for _ in range(n - len(chars)))
                secrets.SystemRandom().shuffle(chars)
                pwout.delete("1.0", "end")
                pwout.insert("1.0", "".join(chars))
            self.make_button(card2, "GÉNÉRER LE MOT DE PASSE", make_password).pack(anchor="w")
            self.make_button(card2, "COPIER LE MOT DE PASSE", lambda: self.copy_text(pwout)).pack(anchor="w", pady=(7, 0))
            phone = self.card("Numéro de démonstration", "Numéro fictif dans la plage réservée aux exemples : +1 202-555-0100 à 0199.")
            phoneout = self.output(phone, "Clique pour créer un exemple.")
            def make_phone():
                phoneout.delete("1.0", "end")
                phoneout.insert("1.0", f"+1 202-555-{100 + secrets.randbelow(100)}")
            self.make_button(phone, "GÉNÉRER UN NUMÉRO FICTIF", make_phone).pack(anchor="w")
            self.make_button(phone, "COPIER LE NUMÉRO", lambda: self.copy_text(phoneout, "Numéro fictif")).pack(anchor="w", pady=(7, 0))
            email_card = self.card("Adresse e-mail fictive", "Crée une adresse de démonstration sur un domaine réservé. Elle ne reçoit pas de messages et ne peut pas créer de compte.")
            email_out = self.output(email_card, "Clique pour générer une adresse de test.")
            def make_fake_email():
                email_out.delete("1.0", "end")
                email_out.insert("1.0", f"utilisateur{secrets.randbelow(1_000_000):06d}@example.invalid")
            self.make_button(email_card, "GÉNÉRER UNE ADRESSE FICTIVE", make_fake_email).pack(anchor="w")
            self.make_button(email_card, "COPIER L’ADRESSE", lambda: self.copy_text(email_out, "Adresse fictive")).pack(anchor="w", pady=(7, 0))
        elif page == "Performance PC":
            self.title("Performance PC", "Nettoyage prudent et raccourcis utiles.")
            card = self.card("Fichiers temporaires", "Aperçu des fichiers directement dans %TEMP% datant de plus de 7 jours. Le nettoyage demande confirmation et ignore les dossiers ou fichiers utilisés.")
            out = self.output(card)
            def preview():
                temp = os.environ.get("TEMP") or os.environ.get("TMP")
                if not temp or not os.path.isdir(temp):
                    return out.insert("1.0", "Dossier temporaire introuvable.")
                cutoff = time.time() - 7 * 24 * 3600
                found = []
                total = 0
                for name in os.listdir(temp):
                    path = os.path.join(temp, name)
                    try:
                        if os.path.isfile(path) and not os.path.islink(path) and os.path.getmtime(path) < cutoff:
                            size = os.path.getsize(path)
                            found.append(path)
                            total += size
                    except OSError:
                        pass
                out.delete("1.0", "end")
                out.insert("1.0", f"{len(found)} fichier(s) ancien(s), environ {total / (1024*1024):.1f} Mo récupérables.\nDossier : {temp}\n\nLe nettoyage ne promet pas un gain de FPS.")
            def cleanup():
                temp = os.environ.get("TEMP") or os.environ.get("TMP")
                if not temp or not os.path.isdir(temp):
                    return messagebox.showerror("Snayw Tools", "Dossier temporaire introuvable.")
                if not messagebox.askyesno("Confirmer le nettoyage", "Supprimer uniquement les fichiers directement dans %TEMP% qui datent de plus de 7 jours ? Les fichiers verrouillés seront ignorés."):
                    return
                cutoff = time.time() - 7 * 24 * 3600
                deleted = 0
                for name in os.listdir(temp):
                    path = os.path.join(temp, name)
                    try:
                        if os.path.isfile(path) and not os.path.islink(path) and os.path.getmtime(path) < cutoff:
                            os.remove(path)
                            deleted += 1
                    except OSError:
                        pass
                out.delete("1.0", "end")
                out.insert("1.0", f"Nettoyage terminé : {deleted} fichier(s) supprimé(s).\nLes dossiers, liens et fichiers verrouillés sont ignorés.\nCe nettoyage ne garantit pas de hausse des FPS.")
            row = tk.Frame(card, bg=self.PANEL2)
            row.pack(anchor="w")
            self.make_button(row, "ANALYSER %TEMP%", preview).pack(side="left", padx=(0, 8))
            self.make_button(row, "NETTOYER LES ANCIENS FICHIERS", cleanup).pack(side="left")
            card2 = self.card("Réglages de jeu et alimentation", "Ouvre les réglages officiels de Windows pour vérifier le Mode Jeu et le profil d’alimentation. Snayw ne modifie pas le registre, les pilotes ni les réglages cachés et ne promet pas de FPS supplémentaires.")
            row = tk.Frame(card2, bg=self.PANEL2)
            row.pack(anchor="w", pady=(10, 0))
            def open_game_settings():
                if os.name != "nt":
                    return messagebox.showinfo("Snayw Tools", "Ces réglages sont disponibles sous Windows.")
                try:
                    os.startfile("ms-settings:gaming-gamemode")
                except OSError as exc:
                    messagebox.showerror("Snayw Tools", f"Impossible d’ouvrir les paramètres : {exc}")
            def open_power_settings():
                if os.name != "nt":
                    return messagebox.showinfo("Snayw Tools", "Ces réglages sont disponibles sous Windows.")
                try:
                    subprocess.Popen(["control.exe", "powercfg.cpl"])
                except OSError as exc:
                    messagebox.showerror("Snayw Tools", f"Impossible d’ouvrir les options d’alimentation : {exc}")
            def open_task_manager():
                if os.name != "nt":
                    return messagebox.showinfo("Snayw Tools", "Ouvre le moniteur système de ton ordinateur.")
                try:
                    subprocess.Popen(["taskmgr.exe"])
                except OSError as exc:
                    messagebox.showerror("Snayw Tools", f"Impossible d’ouvrir le Gestionnaire des tâches : {exc}")
            self.make_button(row, "MODE JEU WINDOWS", open_game_settings).pack(side="left", padx=(0, 8))
            self.make_button(row, "ALIMENTATION", open_power_settings).pack(side="left", padx=(0, 8))
            self.make_button(row, "GESTIONNAIRE DES TÂCHES", open_task_manager).pack(side="left")
            self.card("Conseils rapides", "Ferme uniquement les applications que tu reconnais et n’utilises pas. Mets à jour Windows et les pilotes depuis Windows Update ou le fabricant. En jeu, limite les overlays inutiles et préfère Ethernet au Wi-Fi si possible.")
        elif page == "PC approfondi":
            self.title("Diagnostic PC approfondi", "Composants, utilisation des ressources, stockage, réseau et système.")
            card = self.card("Informations de l'appareil", "Lecture seule. Les détails affichés dépendent des capteurs et des pilotes disponibles sur ton PC.")
            out = self.output(card, "Clique sur Analyser mon PC pour collecter les détails.")
            out.configure(height=14)
            analyze_button = None
            def inspect_pc():
                analyze_button.config(state="disabled")
                out.delete("1.0", "end")
                out.insert("1.0", "Collecte des composants et statistiques…")
                screen = f"{self.root.winfo_screenwidth()} × {self.root.winfo_screenheight()} pixels"

                def collect_details():
                    lines = [f"Système : {platform.system()} {platform.release()}",
                             f"Version Python : {platform.python_version()}",
                             f"Processeur : {platform.processor() or 'indisponible'}",
                             f"Écran : {screen}"]
                    drive = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
                    try:
                        usage = shutil.disk_usage(drive)
                        lines.append(f"Stockage {drive} : {usage.free / (1024**3):.1f} Go libres / {usage.total / (1024**3):.1f} Go")
                    except OSError:
                        pass
                    if os.name == "nt":
                        ps = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$sys = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$board = Get-CimInstance Win32_BaseBoard | Select-Object -First 1
$bios = Get-CimInstance Win32_BIOS | Select-Object -First 1
$freeRam = [double]$os.FreePhysicalMemory * 1KB
$ramPercent = 0
if ($sys.TotalPhysicalMemory -gt 0) { $ramPercent = [math]::Round((($sys.TotalPhysicalMemory - $freeRam) / $sys.TotalPhysicalMemory) * 100, 1) }
$gpus = (Get-CimInstance Win32_VideoController | ForEach-Object {
  $vram = 'non communiquée'
  if ($_.AdapterRAM) { $vram = "$([math]::Round($_.AdapterRAM / 1GB, 1)) Go VRAM" }
  "$($_.Name) — $vram — pilote $($_.DriverVersion)"
}) -join '; '
$disks = (Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
  "$($_.DeviceID) : $([math]::Round($_.FreeSpace / 1GB, 1)) Go libres / $([math]::Round($_.Size / 1GB, 1)) Go"
}) -join '; '
$network = (Get-CimInstance Win32_NetworkAdapter -Filter 'NetEnabled=True' | ForEach-Object {
  $speed = if ($_.Speed) { "$([math]::Round($_.Speed / 1000000, 0)) Mbit/s" } else { 'débit inconnu' }
  "$($_.Name) ($speed)"
}) -join '; '
$batteryItems = @(Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue)
$battery = if ($batteryItems.Count) { ($batteryItems | ForEach-Object { "$($_.EstimatedChargeRemaining)% — état $($_.BatteryStatus)" }) -join '; ' } else { 'Aucune batterie détectée' }
$uptime = (Get-Date) - $os.LastBootUpTime
[pscustomobject]@{
  CPU = $cpu.Name
  CPU_Cores = $cpu.NumberOfCores
  CPU_Threads = $cpu.NumberOfLogicalProcessors
  CPU_Load = $cpu.LoadPercentage
  RAM_Total_GB = [math]::Round($sys.TotalPhysicalMemory / 1GB, 1)
  RAM_Free_GB = [math]::Round($freeRam / 1GB, 1)
  RAM_Used_Pct = $ramPercent
  Windows = $os.Caption
  Windows_Build = $os.BuildNumber
  Uptime = "$([int]$uptime.TotalDays) j $($uptime.Hours) h $($uptime.Minutes) min"
  Manufacturer = $sys.Manufacturer
  Model = $sys.Model
  Motherboard = "$($board.Manufacturer) $($board.Product)"
  BIOS = "$($bios.SMBIOSBIOSVersion) — $($bios.ReleaseDate)"
  GPU = $gpus
  Disks = $disks
  Network = $network
  Battery = $battery
} | ConvertTo-Json -Compress
"""
                        try:
                            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25, check=False)
                            if result.returncode == 0 and result.stdout.strip():
                                data = json.loads(result.stdout.strip())
                                labels = (("Windows", "Windows"), ("Windows_Build", "Build Windows"),
                                          ("Uptime", "Depuis le démarrage"), ("Manufacturer", "Fabricant"),
                                          ("Model", "Modèle du PC"), ("Motherboard", "Carte mère"), ("BIOS", "BIOS"),
                                          ("CPU", "Modèle CPU"), ("CPU_Cores", "Cœurs CPU"),
                                          ("CPU_Threads", "Threads CPU"), ("CPU_Load", "Charge CPU actuelle (%)"),
                                          ("RAM_Total_GB", "RAM totale (Go)"), ("RAM_Free_GB", "RAM disponible (Go)"),
                                          ("RAM_Used_Pct", "RAM utilisée (%)"), ("GPU", "GPU, mémoire vidéo et pilote"),
                                          ("Disks", "Volumes et espace libre"), ("Network", "Interfaces réseau actives"),
                                          ("Battery", "Batterie"))
                                for key, label in labels:
                                    value = data.get(key)
                                    if value not in (None, ""):
                                        lines.append(f"{label} : {value}")
                            else:
                                lines.append("Windows n'a pas retourné toutes les données matérielles.")
                                if result.stderr.strip():
                                    lines.append(result.stderr.strip()[-500:])
                        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, UnicodeError) as exc:
                            lines.append(f"Détails matériels indisponibles : {exc}")
                    try:
                        self.root.after(0, lambda result_lines=lines: finish_scan(result_lines))
                    except tk.TclError:
                        pass

                def finish_scan(lines):
                    if out.winfo_exists():
                        out.delete("1.0", "end")
                        out.insert("1.0", "\n".join(lines))
                    if analyze_button.winfo_exists():
                        analyze_button.config(state="normal")

                threading.Thread(target=collect_details, daemon=True).start()

            analyze_button = self.make_button(card, "ANALYSER MON PC", inspect_pc)
            analyze_button.pack(anchor="w")
            self.card("À propos des performances", "Le diagnostic affiche les données exposées par Windows. Les températures et statistiques fines par cœur dépendent souvent des pilotes ou d'un logiciel constructeur. Cette lecture ne modifie aucun réglage.")
        elif page == "Personnaliser PC":
            self.title("Personnaliser Windows", "Ouvre directement les réglages officiels de Windows.")
            card = self.card("Apparence", "Choisis les couleurs, le thème sombre ou clair, et les effets visuels dans les paramètres Windows.")
            row = tk.Frame(card, bg=self.PANEL2)
            row.pack(anchor="w", pady=(10, 0))
            def open_settings(uri):
                if os.name == "nt":
                    try:
                        os.startfile(uri)
                    except OSError as exc:
                        messagebox.showerror("Paramètres Windows", str(exc))
                else:
                    messagebox.showinfo("Paramètres Windows", "Cette action est disponible sous Windows.")
            for label, uri in (("COULEURS & THÈME", "ms-settings:personalization-colors"),
                               ("FOND D'ÉCRAN", "ms-settings:personalization-background"),
                               ("ÉCRAN", "ms-settings:display"),
                               ("THÈMES", "ms-settings:themes")):
                self.make_button(row, label, lambda u=uri: open_settings(u)).pack(side="left", padx=(0, 8))
            self.card("Personnalisation dans Snayw Tools", "Le bouton Paramètres en haut à droite ajuste la transparence de l'application et active ou désactive les effets du pointeur.")
        elif page == "Paramètres":
            self.title("Paramètres", "Ajuste la fluidité, la transparence et les effets du pointeur.")
            card = self.card("Effets visuels", "Les particules flottent et réagissent au pointeur. Tu peux couper tous les effets à tout moment.")
            tk.Checkbutton(card, text="Activer les effets du pointeur et les particules flottantes",
                           variable=self.motion_enabled,
                           command=lambda: (self.refresh_effects(), self.schedule_settings_save()),
                           bg=self.PANEL2, fg=self.TEXT, activebackground=self.PANEL2,
                           activeforeground=self.CYAN, selectcolor=self.BG,
                           font=("Segoe UI", 10),
                           cursor=self.pointer_cursor if self.motion_enabled.get() else "arrow").pack(anchor="w", pady=(12, 5))
            translucency = self.card("Opacité de la fenêtre", "Plus bas = plus transparent ; plus haut = plus lisible. L’opacité peut dépendre du système Windows.")
            tk.Scale(translucency, from_=.70, to=1.0, resolution=.01, orient="horizontal",
                     variable=self.transparency, command=self.set_transparency,
                     bg=self.PANEL2, fg=self.TEXT, troughcolor="#45474a",
                     activebackground=self.CYAN, highlightthickness=0,
                     showvalue=True, length=420).pack(anchor="w", fill="x", pady=(8, 6))
            self.make_button(translucency, "RÉGLAGE LISIBLE", lambda: (self.transparency.set(.86), self.set_transparency(.86))).pack(anchor="w")
            detail = self.card("Fluidité et densité", "La fréquence choisie est un objectif. Tkinter, Windows et l’écran limitent la fréquence réellement affichée. Les préférences sont mémorisées sur cet ordinateur.")
            row = tk.Frame(detail, bg=self.PANEL2)
            row.pack(fill="x", pady=(8, 4))
            tk.Label(row, text="Objectif d’animation", fg=self.MUTED, bg=self.PANEL2, font=("Segoe UI", 10)).pack(side="left", padx=(0, 12))
            rate = ttk.Combobox(row, textvariable=self.animation_rate, values=[30, 60, 120, 144, 240, 360], state="readonly", width=8)
            rate.pack(side="left")
            rate.bind("<<ComboboxSelected>>", lambda _event: (setattr(self, "next_frame_at", time.perf_counter()), self.schedule_settings_save()))
            tk.Label(detail, text="Nombre de particules", fg=self.MUTED, bg=self.PANEL2, font=("Segoe UI", 10)).pack(anchor="w", pady=(7, 0))
            tk.Scale(detail, from_=12, to=64, resolution=4, orient="horizontal",
                     variable=self.particle_count, bg=self.PANEL2, fg=self.TEXT,
                     troughcolor="#45474a", activebackground=self.CYAN,
                     highlightthickness=0, showvalue=True, length=420,
                     command=lambda _value: self.schedule_settings_save()).pack(anchor="w", fill="x")
            tk.Label(detail, text="Portée de réaction de la souris", fg=self.MUTED, bg=self.PANEL2, font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))
            tk.Scale(detail, from_=60, to=240, resolution=10, orient="horizontal",
                     variable=self.mouse_radius, bg=self.PANEL2, fg=self.TEXT,
                     troughcolor="#45474a", activebackground=self.CYAN,
                     highlightthickness=0, showvalue=True, length=420,
                     command=lambda _value: self.schedule_settings_save()).pack(anchor="w", fill="x")
            presets = tk.Frame(detail, bg=self.PANEL2)
            presets.pack(anchor="w", pady=(10, 0))
            def apply_preset(fps, particles, alpha):
                self.animation_rate.set(fps)
                self.particle_count.set(particles)
                self.transparency.set(alpha)
                self.next_frame_at = time.perf_counter()
                self.set_transparency(alpha)
                self.refresh_effects()
            for label, values in (("ÉQUILIBRÉ", (60, 20, .92)),
                                  ("FLUIDE", (120, 32, .88)),
                                  ("INTENSE", (360, 48, .84))):
                self.make_button(presets, label, lambda v=values: apply_preset(*v), compact=True).pack(side="left", padx=(0, 7))
            def reset_preferences():
                self.motion_enabled.set(True)
                self.particle_count.set(32)
                self.mouse_radius.set(150)
                apply_preset(360, 32, .86)
                self.schedule_settings_save()
            self.make_button(presets, "RÉINITIALISER", reset_preferences, compact=True).pack(side="left")
        else:
            self.title("Outils texte", "Encodage et empreintes cryptographiques.")
            card = self.card("Base64", "Encode ou décode un texte localement.")
            value = self.entry(card, "Texte à traiter")
            mode = tk.StringVar(value="Encoder")
            ttk.Combobox(card, textvariable=mode, values=["Encoder", "Décoder"], state="readonly").pack(anchor="w", pady=5)
            out = self.output(card)
            def process():
                try:
                    raw = value.get().encode("utf-8")
                    result = base64.b64encode(raw).decode() if mode.get() == "Encoder" else base64.b64decode(value.get(), validate=True).decode("utf-8")
                    out.delete("1.0", "end")
                    out.insert("1.0", result)
                except (ValueError, UnicodeDecodeError) as exc:
                    out.delete("1.0", "end")
                    out.insert("1.0", f"Texte invalide : {exc}")
            self.make_button(card, "TRAITER", process).pack(anchor="w")
            card2 = self.card("Hash SHA-256", "Calcule l'empreinte d'un texte.")
            text = self.entry(card2, "Texte")
            hashout = self.output(card2)
            def digest():
                hashout.delete("1.0", "end")
                hashout.insert("1.0", hashlib.sha256(text.get().encode()).hexdigest())
            self.make_button(card2, "CALCULER", digest).pack(anchor="w")

    def copy_text(self, widget, label="Mot de passe"):
        value = widget.get("1.0", "end-1c").strip()
        if value.startswith(("Clique pour", "Ton pseudo apparaîtra")):
            value = ""
        if value:
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            messagebox.showinfo("Snayw Tools", f"{label} copié dans le presse-papiers.")


def main():
    root = tk.Tk()
    SnaywApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)
