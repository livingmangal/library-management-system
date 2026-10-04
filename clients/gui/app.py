#!/usr/bin/env python3
"""Modern Desktop GUI client for the Library Management System.

Features:
  * University Timetable Interactive Matrix (matching college slot system: Mon-Sat)
  * CAT-2 Open Book Collaborative Lending with Visual Phase Timeline
  * KPI Stat Cards (Titles, Copies, Active Loans, Co-Loans, Overdues)
  * Real-Time Live Search (debounce as you type) & Quick Course Filter Chips
  * Book Inspector Panel with Cover Art & Stock Availability Meter
  * Non-blocking background worker threads with thread-safe UI updates
"""

import argparse
import csv
import io
import json
import queue
import sys
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import (
    CAT2_SLOTS,
    CAT2_SUBJECTS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    FINE_PER_DAY,
    SLOT_EXAM_DAYS,
)
from clients.gui.client_api import LibraryClient, ServerUnavailable

# --- Modern Theme & Palette ---
FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "Helvetica"
TITLE_FONT = (FONT_FAMILY, 15, "bold")
SUBTITLE_FONT = (FONT_FAMILY, 9)
HEADER_FONT = (FONT_FAMILY, 11, "bold")
BODY_FONT = (FONT_FAMILY, 10)
SMALL_FONT = (FONT_FAMILY, 9)
MONO_FONT = ("Consolas" if sys.platform.startswith("win") else "Courier", 9)

# Color Scheme: Slate / Indigo / Emerald / Amber
BG = "#f8fafc"               # Slate-50
CARD_BG = "#ffffff"          # Pure White
HEADER_BG = "#0f172a"        # Slate-900
PRIMARY = "#4f46e5"          # Indigo-600
PRIMARY_HOVER = "#4338ca"
SUCCESS = "#059669"          # Emerald-600
WARNING = "#d97706"          # Amber-600
DANGER = "#dc2626"           # Red-600
MUTED = "#64748b"            # Slate-500
BORDER_COLOR = "#e2e8f0"     # Slate-200


def http_get(url):
    """Download a URL from a remote web server and return bytes."""
    request = urllib.request.Request(url, headers={"User-Agent": "LibraryClient/2.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read()


class App:
    def __init__(self, root, client):
        self.root = root
        self.client = client
        self.results = queue.Queue()

        # State and Caches
        self.books_cache = []
        self.loans_cache = []
        self.collab_loans_cache = []
        self.collab_requests_cache = []
        self.members_cache = []
        self.selected_book = None
        self.selected_collab_loan = None
        self.active_course_filter = None
        self.live_search_timer = None
        self.cover_img_ref = None
        self.loans_overdue_only = False
        self.offline_warned = False

        root.title("University Library — CAT-2 Open Book & Collaborative Lending")
        root.geometry("1160x760")
        root.minsize(980, 600)
        root.configure(bg=BG)

        self.apply_modern_styles()

        # Build UI Structure
        self.build_header()
        self.build_kpi_dashboard()
        self.build_tabs()
        self.build_statusbar()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll_results)
        self.refresh_all()

    def apply_modern_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=(FONT_FAMILY, 10, "bold"), padding=[14, 6], background="#e2e8f0")
        style.map("TNotebook.Tab",
                  background=[("selected", CARD_BG), ("active", "#cbd5e1")],
                  foreground=[("selected", PRIMARY), ("active", "#0f172a")])

        style.configure("Treeview", font=BODY_FONT, rowheight=28, background=CARD_BG, fieldbackground=CARD_BG)
        style.configure("Treeview.Heading", font=(FONT_FAMILY, 10, "bold"), background="#f1f5f9", foreground="#1e293b")
        style.map("Treeview", background=[("selected", "#e0e7ff")], foreground=[("selected", "#1e1b4b")])

        style.configure("TButton", font=BODY_FONT, padding=[10, 4])
        style.configure("Primary.TButton", font=(FONT_FAMILY, 10, "bold"), background=PRIMARY, foreground="white")
        style.map("Primary.TButton", background=[("active", PRIMARY_HOVER)])

    # ------------------------------------------------------------------
    # Top Header & Live KPI Dashboard Cards
    # ------------------------------------------------------------------
    def build_header(self):
        bar = tk.Frame(self.root, bg=HEADER_BG, padx=18, pady=10)
        bar.pack(side="top", fill="x")

        left = tk.Frame(bar, bg=HEADER_BG)
        left.pack(side="left")
        tk.Label(left, text="🏛️ University Library System", font=TITLE_FONT, fg="white", bg=HEADER_BG).pack(anchor="w")
        tk.Label(left, text="Open Book CAT-2 Examination & Collaborative Lending Hub",
                 font=SUBTITLE_FONT, fg="#94a3b8", bg=HEADER_BG).pack(anchor="w")

        right = tk.Frame(bar, bg=HEADER_BG)
        right.pack(side="right")
        self.online_label = tk.Label(right, text="● Checking Connection...", font=BODY_FONT, fg="#f59e0b", bg=HEADER_BG)
        self.online_label.pack(side="right", padx=8)

    def build_kpi_dashboard(self):
        bar = tk.Frame(self.root, bg=BG, padx=12, pady=6)
        bar.pack(side="top", fill="x")

        self.kpi_labels = {}
        cards_data = [
            ("books", "📚 Catalog Titles", "0", "#3b82f6"),
            ("avail", "✅ Copies Available", "0", SUCCESS),
            ("loans", "📋 Standard Loans", "0", "#8b5cf6"),
            ("collab", "🤝 CAT-2 Co-Loans", "0", PRIMARY),
            ("overdue", "⚠️ Overdue Loans", "0", DANGER),
        ]

        for key, title, default_val, accent_color in cards_data:
            card = tk.Frame(bar, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1, padx=12, pady=6)
            card.pack(side="left", fill="both", expand=True, padx=4)

            tk.Label(card, text=title, font=SMALL_FONT, fg=MUTED, bg=CARD_BG).pack(anchor="w")
            lbl = tk.Label(card, text=default_val, font=(FONT_FAMILY, 15, "bold"), fg=accent_color, bg=CARD_BG)
            lbl.pack(anchor="w")
            self.kpi_labels[key] = lbl

    def update_kpi_cards(self):
        total_titles = len(self.books_cache)
        avail_copies = sum(b.get("available", 0) for b in self.books_cache)
        standard_loans = len(self.loans_cache)
        collab_loans = len(self.collab_loans_cache)
        overdues = sum(1 for l in self.loans_cache if date.today().isoformat() > l.get("due_on", "9999"))

        self.kpi_labels["books"].config(text=str(total_titles))
        self.kpi_labels["avail"].config(text=str(avail_copies))
        self.kpi_labels["loans"].config(text=str(standard_loans))
        self.kpi_labels["collab"].config(text=str(collab_loans))
        self.kpi_labels["overdue"].config(text=str(overdues))

    def build_statusbar(self):
        self.status = tk.StringVar(value="Ready")
        bar = tk.Frame(self.root, bg="#f1f5f9", highlightbackground=BORDER_COLOR, highlightthickness=1, padx=8, pady=3)
        bar.pack(side="bottom", fill="x")
        tk.Label(bar, textvariable=self.status, font=SMALL_FONT, bg="#f1f5f9", fg=MUTED).pack(side="left")
        tk.Label(bar, text="Zero-Clash Open Book Engine", font=SMALL_FONT, bg="#f1f5f9", fg="#94a3b8").pack(side="right")

    # ------------------------------------------------------------------
    # Main Tabs
    # ------------------------------------------------------------------
    def build_tabs(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        # Tab 1: Books & Catalogue
        tab_books = tk.Frame(notebook, bg=BG)
        notebook.add(tab_books, text="📚 Books & Catalogue")
        self.build_books_tab(tab_books)

        # Tab 2: CAT-2 Collaborative Lending
        tab_collab = tk.Frame(notebook, bg=BG)
        notebook.add(tab_collab, text="🤝 CAT-2 Co-Lending Hub")
        self.build_collab_tab(tab_collab)

        # Tab 3: Standard Loans
        tab_loans = tk.Frame(notebook, bg=BG)
        notebook.add(tab_loans, text="📋 Standard Loans")
        self.build_loans_tab(tab_loans)

        # Tab 4: Members
        tab_members = tk.Frame(notebook, bg=BG)
        notebook.add(tab_members, text="👤 Members Directory")
        self.build_members_tab(tab_members)

    # ------------------------------------------------------------------
    # TAB 1: Books & Inspector Panel
    # ------------------------------------------------------------------
    def build_books_tab(self, parent):
        top_bar = tk.Frame(parent, bg=BG, pady=6)
        top_bar.pack(side="top", fill="x")

        # Search box with live search
        tk.Label(top_bar, text="🔍 Live Search:", font=HEADER_FONT, bg=BG, fg="#1e293b").pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(top_bar, textvariable=self.search_var, width=28, font=BODY_FONT)
        search_entry.pack(side="left", padx=4)
        search_entry.bind("<KeyRelease>", self.on_search_keyrelease)

        # Quick Course Filter Chips
        chips_frame = tk.Frame(top_bar, bg=BG)
        chips_frame.pack(side="left", padx=12)
        tk.Label(chips_frame, text="Filter:", font=SMALL_FONT, bg=BG, fg=MUTED).pack(side="left", padx=4)

        filters = [
            ("All", None),
            ("Python (CSE2004)", "CSE2004"),
            ("C++ (ECE2002)", "ECE2002"),
            ("Discrete (MAT2002)", "MAT2002"),
            ("TOC (CSE3011)", "CSE3011"),
            ("Available Only", "AVAIL"),
        ]
        self.filter_buttons = []
        for label, val in filters:
            btn = tk.Button(chips_frame, text=label, font=SMALL_FONT, relief="flat", bd=1,
                            bg="#e2e8f0" if val is not None else PRIMARY,
                            fg="#1e293b" if val is not None else "white",
                            padx=6, pady=2, cursor="hand2",
                            command=lambda v=val: self.apply_course_filter(v))
            btn.pack(side="left", padx=2)
            self.filter_buttons.append((btn, val))

        ttk.Button(top_bar, text="➕ Add Book...", command=self.open_add_book_dialog).pack(side="right")

        # Split pane: Treeview on Left, Inspector on Right
        center_split = tk.Frame(parent, bg=BG)
        center_split.pack(fill="both", expand=True, pady=4)

        # Left: Books Table
        left_frame = tk.Frame(center_split, bg=BG)
        left_frame.pack(side="left", fill="both", expand=True)

        self.books_tree = ttk.Treeview(left_frame, columns=["id", "title", "author", "isbn", "avail"],
                                       show="headings", selectmode="browse")
        for k, h, w in [("id", "ID", 45), ("title", "Title", 280), ("author", "Author", 170),
                        ("isbn", "ISBN", 125), ("avail", "Available", 85)]:
            self.books_tree.heading(k, text=h)
            self.books_tree.column(k, width=w, anchor="w")

        tree_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.books_tree.yview)
        self.books_tree.configure(yscrollcommand=tree_scroll.set)
        self.books_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.books_tree.bind("<<TreeviewSelect>>", self.on_book_selected)

        # Right: Book Inspector Card
        self.inspector_card = tk.Frame(center_split, bg=CARD_BG, width=280,
                                       highlightbackground=BORDER_COLOR, highlightthickness=1, padx=14, pady=12)
        self.inspector_card.pack(side="right", fill="y", padx=(10, 0))
        self.inspector_card.pack_propagate(False)
        self.build_book_inspector()

    def build_book_inspector(self):
        card = self.inspector_card

        self.inspector_cover_lbl = tk.Label(card, text="[ Book Cover ]", font=SMALL_FONT, bg="#f1f5f9",
                                            fg=MUTED, width=20, height=8, relief="solid", bd=1)
        self.inspector_cover_lbl.pack(pady=(0, 8))

        self.inspector_title = tk.Label(card, text="Select a book", font=HEADER_FONT, bg=CARD_BG,
                                        fg="#0f172a", wraplength=250, justify="left")
        self.inspector_title.pack(anchor="w")

        self.inspector_author = tk.Label(card, text="—", font=BODY_FONT, bg=CARD_BG, fg=MUTED)
        self.inspector_author.pack(anchor="w")

        self.inspector_isbn = tk.Label(card, text="ISBN: —", font=MONO_FONT, bg=CARD_BG, fg="#475569")
        self.inspector_isbn.pack(anchor="w", pady=(2, 6))

        # Stock meter badge
        self.inspector_stock_badge = tk.Label(card, text="Available: —", font=(FONT_FAMILY, 9, "bold"),
                                              bg="#e2e8f0", fg="#1e293b", padx=8, pady=3)
        self.inspector_stock_badge.pack(anchor="w", pady=4)

        # Quick Actions inside Inspector
        actions_frame = tk.Frame(card, bg=CARD_BG)
        actions_frame.pack(fill="x", pady=12)

        ttk.Button(actions_frame, text="⚡ Standard Checkout...", command=self.checkout_selected).pack(fill="x", pady=2)
        ttk.Button(actions_frame, text="🤝 Co-Lend this Book (CAT-2)...", command=self.collab_lend_selected).pack(fill="x", pady=2)
        ttk.Button(actions_frame, text="🌐 Online Cover & Info...", command=self.lookup_selected_isbn).pack(fill="x", pady=2)
        ttk.Button(actions_frame, text="🗑️ Remove Book", command=self.remove_selected).pack(fill="x", pady=2)

    def on_search_keyrelease(self, event):
        if self.live_search_timer:
            self.root.after_cancel(self.live_search_timer)
        self.live_search_timer = self.root.after(150, self.filter_books_list)

    def apply_course_filter(self, course_code):
        self.active_course_filter = course_code
        for btn, val in self.filter_buttons:
            if val == course_code:
                btn.config(bg=PRIMARY, fg="white")
            else:
                btn.config(bg="#e2e8f0", fg="#1e293b")
        self.filter_books_list()

    def filter_books_list(self):
        query = self.search_var.get().strip().lower()
        tree = self.books_tree
        tree.delete(*tree.get_children())

        filtered = []
        for b in self.books_cache:
            title_l = b["title"].lower()
            author_l = b["author"].lower()
            isbn_l = b["isbn"].lower()

            # Course filter match
            if self.active_course_filter == "AVAIL":
                if b["available"] < 1:
                    continue
            elif self.active_course_filter:
                if self.active_course_filter.lower() not in title_l:
                    continue

            # Query match
            if query and not (query in title_l or query in author_l or query in isbn_l):
                continue

            filtered.append(b)

        for b in filtered:
            tag = "out" if b["available"] == 0 else "avail"
            tree.insert("", "end", iid=str(b["id"]),
                        values=(b["id"], b["title"], b["author"], b["isbn"], f"{b['available']}/{b['copies']}"),
                        tags=(tag,))

    def on_book_selected(self, event):
        selection = self.books_tree.selection()
        if not selection:
            return
        book_id = int(selection[0])
        book = next((b for b in self.books_cache if b["id"] == book_id), None)
        if not book:
            return
        self.selected_book = book

        self.inspector_title.config(text=book["title"])
        self.inspector_author.config(text=f"By {book['author']}")
        self.inspector_isbn.config(text=f"ISBN: {book['isbn']}")

        if book["available"] > 0:
            self.inspector_stock_badge.config(
                text=f"🟢 In Stock: {book['available']} of {book['copies']} copies",
                bg="#dcfce7", fg=SUCCESS
            )
        else:
            self.inspector_stock_badge.config(
                text=f"🔴 All {book['copies']} Copies on Loan",
                bg="#fee2e2", fg=DANGER
            )

        # Reset cover placeholder
        self.inspector_cover_lbl.config(image="", text="[ Book Cover ]")
        self.cover_img_ref = None

    def lookup_selected_isbn(self):
        if not self.selected_book:
            messagebox.showinfo("Select Book", "Please select a book first.")
            return
        isbn = self.selected_book["isbn"].replace("-", "")

        def fetch():
            query = urllib.parse.urlencode({"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"})
            data = json.loads(http_get("https://openlibrary.org/api/books?" + query))
            return data.get(f"ISBN:{isbn}")

        self.run_async(fetch, self.apply_cover_to_inspector, "Fetching cover art from Open Library...")

    def apply_cover_to_inspector(self, info):
        if not info or not info.get("cover", {}).get("medium"):
            self.set_status("No cover image found online for this ISBN")
            return
        cover_url = info["cover"]["medium"]

        def download():
            raw_bytes = http_get(cover_url)
            if PIL_AVAILABLE:
                img = Image.open(io.BytesIO(raw_bytes))
                img.thumbnail((140, 190))
                return img
            return None

        self.run_async(download, self.render_cover_image, "Rendering cover...")

    def render_cover_image(self, pil_image):
        if pil_image and PIL_AVAILABLE:
            photo = ImageTk.PhotoImage(pil_image)
            self.cover_img_ref = photo
            self.inspector_cover_lbl.config(image=photo, text="")
            self.set_status("Cover loaded from Open Library")

    # ------------------------------------------------------------------
    # TAB 2: CAT-2 Collaborative Lending Hub with Timetable Matrix
    # ------------------------------------------------------------------
    def build_collab_tab(self, parent):
        # Explanatory Header Banner
        banner = tk.Frame(parent, bg="#1e1b4b", padx=14, pady=8)
        banner.pack(side="top", fill="x")
        tk.Label(banner, text="🤝 CAT-2 Open Book Collaborative Lending Hub",
                 font=("Segoe UI", 12, "bold"), fg="white", bg="#1e1b4b").pack(anchor="w")
        tk.Label(banner,
                 text="University exams are scheduled strictly slot-wise. Students from different slots of the same subject (e.g. A1 & C1) co-lend a single textbook without exam clashes!",
                 font=SMALL_FONT, fg="#cbd5e1", bg="#1e1b4b").pack(anchor="w")

        # Action Toolbar
        toolbar = tk.Frame(parent, bg=BG, padx=8, pady=6)
        toolbar.pack(side="top", fill="x")
        ttk.Button(toolbar, text="⚡ Direct Co-Lend Checkout...", command=self.open_collab_checkout_dialog).pack(side="left", padx=3)
        ttk.Button(toolbar, text="📢 Post Co-Lend Request...", command=self.open_create_request_dialog).pack(side="left", padx=3)
        ttk.Button(toolbar, text="🤝 Join Selected Request", command=self.join_selected_request).pack(side="left", padx=3)
        ttk.Button(toolbar, text="🔄 Confirm Handover (Phase 1 ➔ 2)", command=self.handover_selected_collab).pack(side="left", padx=8)
        ttk.Button(toolbar, text="📥 Return Book to Library", command=self.return_selected_collab).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Refresh", command=self.refresh_collab).pack(side="right", padx=3)

        # Sub-Notebook
        sub_notebook = ttk.Notebook(parent)
        sub_notebook.pack(fill="both", expand=True, padx=4, pady=4)

        # Sub-Tab A: Active Collaborative Loans & Phase Timeline Bar
        loans_panel = tk.Frame(sub_notebook, bg=BG)
        sub_notebook.add(loans_panel, text="📋 Active Collaborative Loans")
        self.build_collab_loans_view(loans_panel)

        # Sub-Tab B: Interactive University Timetable Matrix (Matching Image!)
        timetable_panel = tk.Frame(sub_notebook, bg=BG)
        sub_notebook.add(timetable_panel, text="🗓️ Weekly Slot Matrix (Timetable Guide)")
        self.build_interactive_timetable_matrix(timetable_panel)

        # Sub-Tab C: Matchmaker Open Requests Board
        req_panel = tk.Frame(sub_notebook, bg=BG)
        sub_notebook.add(req_panel, text="📢 Co-Lender Matchmaker (Open Requests)")
        self.build_matchmaker_requests_view(req_panel)

    def build_collab_loans_view(self, parent):
        self.collab_tree = ttk.Treeview(parent, columns=[
            "id", "book", "subject", "holder", "p1", "exam1", "handover", "p2", "exam2", "due", "status"
        ], show="headings", height=8)

        col_defs = [
            ("id", "ID", 45), ("book", "Book Title", 220), ("subject", "Course", 95),
            ("holder", "Current Custody", 130), ("p1", "Phase 1 Student", 145), ("exam1", "Exam 1", 85),
            ("handover", "Handover Date", 95), ("p2", "Phase 2 Student", 145), ("exam2", "Exam 2", 85),
            ("due", "Final Due", 85), ("status", "Status", 110)
        ]
        for k, h, w in col_defs:
            self.collab_tree.heading(k, text=h)
            self.collab_tree.column(k, width=w, anchor="w")

        tree_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.collab_tree.yview)
        self.collab_tree.configure(yscrollcommand=tree_scroll.set)
        self.collab_tree.pack(side="top", fill="both", expand=True, pady=4)
        tree_scroll.pack(side="right", fill="y")
        self.collab_tree.bind("<<TreeviewSelect>>", self.on_collab_loan_selected)

        # Visual Handover & Exam Timeline Bar Container
        self.timeline_card = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1, padx=16, pady=10)
        self.timeline_card.pack(side="bottom", fill="x", pady=6)

        tk.Label(self.timeline_card, text="⏳ Visual Exam & Handover Timeline Tracker",
                 font=HEADER_FONT, bg=CARD_BG, fg="#0f172a").pack(anchor="w")

        self.timeline_content = tk.Frame(self.timeline_card, bg=CARD_BG, pady=6)
        self.timeline_content.pack(fill="x")
        self.render_empty_timeline()

    def render_empty_timeline(self):
        for widget in self.timeline_content.winfo_children():
            widget.destroy()
        tk.Label(self.timeline_content, text="Select any loan above to inspect its live stage & scheduled handover timeline.",
                 font=BODY_FONT, bg=CARD_BG, fg=MUTED).pack(anchor="w")

    def on_collab_loan_selected(self, event):
        selection = self.collab_tree.selection()
        if not selection:
            self.render_empty_timeline()
            return
        collab_id = int(selection[0])
        loan = next((l for l in self.collab_loans_cache if l["id"] == collab_id), None)
        if not loan:
            return
        self.selected_collab_loan = loan
        self.render_active_timeline(loan)

    def render_active_timeline(self, loan):
        for widget in self.timeline_content.winfo_children():
            widget.destroy()

        container = self.timeline_content
        is_phase1 = loan["status"] == "ACTIVE_PHASE_1"
        is_phase2 = loan["status"] == "ACTIVE_PHASE_2"
        is_returned = loan["status"] == "RETURNED"

        # Stage 1: Student 1 (Phase 1)
        s1_bg = "#dcfce7" if is_phase1 else "#f1f5f9"
        s1_fg = SUCCESS if is_phase1 else MUTED
        b1 = tk.Frame(container, bg=s1_bg, highlightbackground=s1_fg, highlightthickness=2 if is_phase1 else 1, padx=10, pady=6)
        b1.pack(side="left", fill="both", expand=True, padx=4)
        tk.Label(b1, text="1️⃣ Phase 1 Custody", font=(FONT_FAMILY, 9, "bold"), fg=s1_fg, bg=s1_bg).pack(anchor="w")
        tk.Label(b1, text=f"👤 {loan['member1_name']} (Slot {loan['slot1']})", font=BODY_FONT, fg="#0f172a", bg=s1_bg).pack(anchor="w")
        tk.Label(b1, text=f"📝 Exam Date: {loan['exam1_date']}", font=SMALL_FONT, fg="#475569", bg=s1_bg).pack(anchor="w")

        # Arrow 1: Handover
        arr1 = tk.Frame(container, bg=CARD_BG, padx=4)
        arr1.pack(side="left")
        tk.Label(arr1, text="──▶\n🔄 Handover", font=SMALL_FONT, fg=WARNING if is_phase1 else SUCCESS, bg=CARD_BG).pack()
        tk.Label(arr1, text=loan["handover_date"], font=(FONT_FAMILY, 8, "bold"), fg=WARNING if is_phase1 else SUCCESS, bg=CARD_BG).pack()

        # Stage 2: Student 2 (Phase 2)
        s2_bg = "#fef3c7" if is_phase2 else "#f1f5f9"
        s2_fg = WARNING if is_phase2 else MUTED
        b2 = tk.Frame(container, bg=s2_bg, highlightbackground=s2_fg, highlightthickness=2 if is_phase2 else 1, padx=10, pady=6)
        b2.pack(side="left", fill="both", expand=True, padx=4)
        tk.Label(b2, text="2️⃣ Phase 2 Custody", font=(FONT_FAMILY, 9, "bold"), fg=s2_fg, bg=s2_bg).pack(anchor="w")
        tk.Label(b2, text=f"👤 {loan['member2_name']} (Slot {loan['slot2']})", font=BODY_FONT, fg="#0f172a", bg=s2_bg).pack(anchor="w")
        tk.Label(b2, text=f"📝 Exam Date: {loan['exam2_date']}", font=SMALL_FONT, fg="#475569", bg=s2_bg).pack(anchor="w")

        # Arrow 2: Return
        arr2 = tk.Frame(container, bg=CARD_BG, padx=4)
        arr2.pack(side="left")
        tk.Label(arr2, text="──▶\n📥 Return", font=SMALL_FONT, fg=PRIMARY if is_phase2 else MUTED, bg=CARD_BG).pack()
        tk.Label(arr2, text=loan["due_on"], font=(FONT_FAMILY, 8, "bold"), fg=PRIMARY if is_phase2 else MUTED, bg=CARD_BG).pack()

        # Stage 3: Return to Library
        s3_bg = "#ede9fe" if is_returned else "#f8fafc"
        s3_fg = PRIMARY if is_returned else MUTED
        b3 = tk.Frame(container, bg=s3_bg, highlightbackground=s3_fg, highlightthickness=1, padx=10, pady=6)
        b3.pack(side="left", fill="both", expand=True, padx=4)
        tk.Label(b3, text="3️⃣ Library Restocked", font=(FONT_FAMILY, 9, "bold"), fg=s3_fg, bg=s3_bg).pack(anchor="w")
        tk.Label(b3, text="🏢 Main Circulation Desk", font=BODY_FONT, fg="#0f172a", bg=s3_bg).pack(anchor="w")
        tk.Label(b3, text=f"Status: {loan['status']}", font=SMALL_FONT, fg=s3_fg, bg=s3_bg).pack(anchor="w")

    # ------------------------------------------------------------------
    # TAB 2-B: Interactive University Timetable Matrix
    # ------------------------------------------------------------------
    def build_interactive_timetable_matrix(self, parent):
        top_info = tk.Frame(parent, bg=BG, pady=6)
        top_info.pack(side="top", fill="x")

        tk.Label(top_info, text="Weekly Course Slot Schedule (Matching Your Class Timetable)",
                 font=HEADER_FONT, bg=BG, fg="#0f172a").pack(anchor="w")
        tk.Label(top_info,
                 text="💡 Click any slot cell below to see which slots have exams on DIFFERENT dates and are 100% compatible for co-lending!",
                 font=SMALL_FONT, bg=BG, fg=MUTED).pack(anchor="w")

        matrix_frame = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1, padx=10, pady=8)
        matrix_frame.pack(side="top", fill="x", pady=4)

        # Timetable headers matching user's image
        headers = ["DAY", "08:30 - 10:00", "10:05 - 11:35", "11:40 - 13:10", "13:15 - 14:45", "14:50 - 16:20", "16:25 - 17:55", "18:00 - 19:30"]
        for col, h in enumerate(headers):
            tk.Label(matrix_frame, text=h, font=(FONT_FAMILY, 9, "bold"), bg="#f1f5f9",
                     fg="#334155", relief="solid", bd=1, padx=6, pady=4).grid(row=0, column=col, sticky="nsew")

        # Slot matrix data referencing the user's timetable image
        timetable_data = [
            ("MON", [("A11", "CSE2004\nPython"), ("B11", "ECE2002\nC++"), ("C11", "CSE3011\nTOC"), ("A21", "Slot A2"), ("A14", "MAT2002\nDiscrete"), ("B21", "Slot B2"), ("C21", "Slot C2")]),
            ("TUE", [("D11", "MAT2002\nDiscrete"), ("E11", "MGT2003\nMgmt"), ("F11", "PLA1004\nAptitude"), ("D21", "Slot D2"), ("E14", "Slot E1"), ("E21", "Slot E2"), ("F21", "Slot F2")]),
            ("WED", [("A12", "CSE2004\nPython"), ("B12", "ECE2002\nC++"), ("C12", "CSE3011\nTOC"), ("A22", "Slot A2"), ("B14", "Slot B1"), ("B22", "Slot B2"), ("A24", "Slot A2")]),
            ("THU", [("D12", "MAT2002\nDiscrete"), ("E12", "MGT2003\nMgmt"), ("F12", "PLA1004\nAptitude"), ("D22", "Slot D2"), ("F14", "Slot F1"), ("E22", "Slot E2"), ("F22", "Slot F2")]),
            ("FRI", [("A13", "CSE2004\nPython"), ("B13", "ECE2002\nC++"), ("C13", "Slot C1"), ("A23", "Slot A2"), ("C14", "Slot C1"), ("B23", "Slot B2"), ("B24", "Slot B2")]),
            ("SAT", [("D13", "Slot D1"), ("E13", "Slot E1"), ("F13", "Slot F1"), ("D23", "Slot D2"), ("D14", "Slot D1"), ("D24", "Slot D2"), ("E23", "Slot E2")]),
        ]

        self.slot_buttons = {}
        for r_idx, (day, slots) in enumerate(timetable_data, start=1):
            tk.Label(matrix_frame, text=day, font=(FONT_FAMILY, 9, "bold"), bg="#f8fafc", fg="#1e293b",
                     relief="solid", bd=1, padx=6, pady=4).grid(row=r_idx, column=0, sticky="nsew")

            for c_idx, (slot_code, course_label) in enumerate(slots, start=1):
                # Standard slot family (e.g. A11 belongs to A1)
                slot_family = slot_code[:2] if len(slot_code) >= 2 else slot_code
                btn = tk.Button(matrix_frame, text=f"{slot_code}\n{course_label}", font=(FONT_FAMILY, 8),
                                bg="#f8fafc", fg="#1e293b", relief="solid", bd=1, padx=4, pady=2,
                                cursor="hand2", command=lambda s=slot_family, c=course_label: self.on_timetable_slot_clicked(s, c))
                btn.grid(row=r_idx, column=c_idx, sticky="nsew", padx=1, pady=1)
                self.slot_buttons[(r_idx, c_idx)] = (btn, slot_family)

        for col in range(8):
            matrix_frame.grid_columnconfigure(col, weight=1)

        # Slot Inspection & Compatibility Details Box
        self.slot_info_card = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1, padx=14, pady=10)
        self.slot_info_card.pack(side="top", fill="x", pady=6)

        self.slot_inspect_title = tk.Label(self.slot_info_card, text="Select any slot above to check co-lending compatibility",
                                           font=HEADER_FONT, bg=CARD_BG, fg="#0f172a")
        self.slot_inspect_title.pack(anchor="w")

        self.slot_inspect_compat = tk.Label(self.slot_info_card, text="Exam Date: — | Compatible Slots: —",
                                            font=BODY_FONT, bg=CARD_BG, fg=MUTED, wraplength=950, justify="left")
        self.slot_inspect_compat.pack(anchor="w", pady=4)

        self.btn_collab_from_slot = ttk.Button(self.slot_info_card, text="⚡ Co-Lend this Course with Partner Slot...",
                                               command=self.open_collab_checkout_dialog)
        self.btn_collab_from_slot.pack(anchor="w", pady=(4, 0))

    def on_timetable_slot_clicked(self, slot_family, course_label):
        course_clean = course_label.replace("\n", " ")
        exam_offset = SLOT_EXAM_DAYS.get(slot_family, 1)

        # Highlight compatible slots in green and conflicting in red
        for (r, c), (btn, family) in self.slot_buttons.items():
            if family == slot_family:
                btn.config(bg="#fee2e2", fg=DANGER)   # Conflicting (Same slot family)
            else:
                btn.config(bg="#dcfce7", fg=SUCCESS)  # Compatible (Different slot family)

        compat_list = [s for s in CAT2_SLOTS if s != slot_family]
        self.slot_inspect_title.config(text=f"Selected: Slot {slot_family} ({course_clean}) — Exam Day {exam_offset}")
        self.slot_inspect_compat.config(
            text=f"✅ 100% Compatible Co-Lending Slots (Non-Clashing Exam Dates):\n{', '.join(compat_list)}",
            fg="#047857"
        )
        self.set_status(f"Slot {slot_family} selected. Compatible with {len(compat_list)} alternate slots.")

    # ------------------------------------------------------------------
    # TAB 2-C: Matchmaker Open Requests Board
    # ------------------------------------------------------------------
    def build_matchmaker_requests_view(self, parent):
        tk.Label(parent, text="📢 Students Looking for a Slot Partner to Co-Borrow Textbooks:",
                 font=HEADER_FONT, bg=BG, fg="#0f172a").pack(anchor="w", pady=6)

        self.collab_req_tree = ttk.Treeview(parent, columns=[
            "id", "subject", "book", "avail", "student", "slot", "exam", "created"
        ], show="headings")

        r_cols = [
            ("id", "Req ID", 55), ("subject", "Subject", 160), ("book", "Book Title", 250),
            ("avail", "Avail", 50), ("student", "Requested By", 160), ("slot", "Slot", 70),
            ("exam", "Exam Date", 90), ("created", "Posted On", 90)
        ]
        for k, h, w in r_cols:
            self.collab_req_tree.heading(k, text=h)
            self.collab_req_tree.column(k, width=w, anchor="w")

        req_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.collab_req_tree.yview)
        self.collab_req_tree.configure(yscrollcommand=req_scroll.set)
        self.collab_req_tree.pack(side="left", fill="both", expand=True, pady=4)
        req_scroll.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    # TAB 3: Standard Loans
    # ------------------------------------------------------------------
    def build_loans_tab(self, parent):
        top = tk.Frame(parent, bg=BG, pady=6)
        top.pack(side="top", fill="x")
        ttk.Button(top, text="All Active Loans", command=lambda: self.load_loans(False)).pack(side="left", padx=3)
        ttk.Button(top, text="Overdue Only", command=lambda: self.load_loans(True)).pack(side="left", padx=3)
        ttk.Button(top, text="Return Selected", command=self.return_selected).pack(side="left", padx=10)
        ttk.Button(top, text="⬇ Export CSV...", command=self.export_loans).pack(side="right")

        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="both", expand=True, pady=4)

        self.loans_tree = ttk.Treeview(frame, columns=["book", "title", "member", "name", "borrowed", "due", "status"],
                                       show="headings")
        for k, h, w in [("book", "Book ID", 60), ("title", "Title", 240), ("member", "Member ID", 75),
                        ("name", "Borrower", 160), ("borrowed", "Borrowed", 95), ("due", "Due On", 95),
                        ("status", "Status", 200)]:
            self.loans_tree.heading(k, text=h)
            self.loans_tree.column(k, width=w, anchor="w")

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.loans_tree.yview)
        self.loans_tree.configure(yscrollcommand=scroll.set)
        self.loans_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.loans_tree.tag_configure("overdue", foreground=DANGER)

    # ------------------------------------------------------------------
    # TAB 4: Members Directory
    # ------------------------------------------------------------------
    def build_members_tab(self, parent):
        top = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER_COLOR, highlightthickness=1, padx=12, pady=8)
        top.pack(side="top", fill="x", pady=6)
        tk.Label(top, text="Add New Member:", font=HEADER_FONT, bg=CARD_BG).pack(side="left", padx=(0, 8))

        self.member_name_var = tk.StringVar()
        self.member_email_var = tk.StringVar()
        tk.Label(top, text="Name:", bg=CARD_BG, font=BODY_FONT).pack(side="left", padx=2)
        tk.Entry(top, textvariable=self.member_name_var, width=18, font=BODY_FONT).pack(side="left", padx=4)
        tk.Label(top, text="Email:", bg=CARD_BG, font=BODY_FONT).pack(side="left", padx=2)
        tk.Entry(top, textvariable=self.member_email_var, width=24, font=BODY_FONT).pack(side="left", padx=4)
        ttk.Button(top, text="Add Member", command=self.add_member).pack(side="left", padx=8)
        ttk.Button(top, text="Refresh", command=self.load_members).pack(side="right")

        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="both", expand=True, pady=4)
        self.members_tree = ttk.Treeview(frame, columns=["id", "name", "email"], show="headings")
        for k, h, w in [("id", "Member ID", 70), ("name", "Full Name", 280), ("email", "Email Address", 340)]:
            self.members_tree.heading(k, text=h)
            self.members_tree.column(k, width=w, anchor="w")

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.members_tree.yview)
        self.members_tree.configure(yscrollcommand=scroll.set)
        self.members_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    # Dialogs & Collaborative Operations
    # ------------------------------------------------------------------
    def open_add_book_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Add a Book to Library")
        win.geometry("480x320")
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Add New Book Title", font=HEADER_FONT, bg=BG, fg="#0f172a").pack(pady=10)
        f = tk.Frame(win, bg=BG, padx=16)
        f.pack(fill="x")

        t_var, a_var, i_var, c_var = tk.StringVar(), tk.StringVar(), tk.StringVar(), tk.StringVar(value="1")
        for idx, (label, var, w) in enumerate([("Title:", t_var, 32), ("Author:", a_var, 32), ("ISBN:", i_var, 20), ("Copies:", c_var, 8)]):
            tk.Label(f, text=label, font=BODY_FONT, bg=BG).grid(row=idx, column=0, sticky="e", pady=4)
            tk.Entry(f, textvariable=var, width=w, font=BODY_FONT).grid(row=idx, column=1, sticky="w", pady=4, padx=6)

        def do_add():
            t, a, i = t_var.get().strip(), a_var.get().strip(), i_var.get().strip()
            try:
                c = int(c_var.get())
            except ValueError:
                c = 0
            if not (t and a and i) or c < 1:
                messagebox.showerror("Error", "All fields required, copies must be >= 1.", parent=win)
                return
            self.run_async(lambda: self.client.request("add_book", title=t, author=a, isbn=i, copies=c),
                           lambda new_id: self.after_add_book_dlg(win, new_id), "Adding book...")

        ttk.Button(win, text="Confirm & Add Book", command=do_add).pack(pady=14)

    def after_add_book_dlg(self, win, new_id):
        win.destroy()
        messagebox.showinfo("Success", f"Book #{new_id} added successfully!")
        self.refresh_all()

    def open_collab_checkout_dialog(self):
        if not self.books_cache:
            messagebox.showinfo("Wait", "Books are loading, please try again in a moment.")
            return

        win = tk.Toplevel(self.root)
        win.title("Direct Collaborative Checkout (CAT-2)")
        win.geometry("560x470")
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="⚡ Direct Collaborative Checkout (Two Students)", font=HEADER_FONT, bg=BG, fg="#1e1b4b").pack(pady=10)

        f = tk.Frame(win, bg=BG, padx=16)
        f.pack(fill="x")

        # Book
        tk.Label(f, text="Select Book:", font=BODY_FONT, bg=BG).grid(row=0, column=0, sticky="e", pady=4)
        book_var = tk.StringVar()
        book_titles = [f"{b['id']}: {b['title']} (Avail: {b['available']})" for b in self.books_cache]
        book_cb = ttk.Combobox(f, textvariable=book_var, values=book_titles, width=38, state="readonly")
        book_cb.grid(row=0, column=1, sticky="w", pady=4, padx=6)
        # Preselect if selected in inspector
        if self.selected_book:
            for idx, item in enumerate(book_titles):
                if item.startswith(f"{self.selected_book['id']}:"):
                    book_cb.current(idx)
                    break
        elif book_titles:
            book_cb.current(0)

        # Subject
        tk.Label(f, text="Course Subject:", font=BODY_FONT, bg=BG).grid(row=1, column=0, sticky="e", pady=4)
        subj_var = tk.StringVar()
        subj_options = [f"{k} - {v}" for k, v in CAT2_SUBJECTS.items()]
        subj_cb = ttk.Combobox(f, textvariable=subj_var, values=subj_options, width=38, state="readonly")
        subj_cb.current(0)
        subj_cb.grid(row=1, column=1, sticky="w", pady=4, padx=6)

        # Student 1
        tk.Label(f, text="Student 1 Member ID:", font=BODY_FONT, bg=BG).grid(row=2, column=0, sticky="e", pady=4)
        s1_id_var = tk.StringVar(value="1")
        tk.Entry(f, textvariable=s1_id_var, width=12, font=BODY_FONT).grid(row=2, column=1, sticky="w", pady=4, padx=6)

        tk.Label(f, text="Student 1 Timetable Slot:", font=BODY_FONT, bg=BG).grid(row=3, column=0, sticky="e", pady=4)
        s1_slot_var = tk.StringVar(value="A1")
        s1_slot_cb = ttk.Combobox(f, textvariable=s1_slot_var, values=CAT2_SLOTS, width=10, state="readonly")
        s1_slot_cb.grid(row=3, column=1, sticky="w", pady=4, padx=6)

        # Student 2
        tk.Label(f, text="Student 2 Member ID:", font=BODY_FONT, bg=BG).grid(row=4, column=0, sticky="e", pady=4)
        s2_id_var = tk.StringVar(value="2")
        tk.Entry(f, textvariable=s2_id_var, width=12, font=BODY_FONT).grid(row=4, column=1, sticky="w", pady=4, padx=6)

        tk.Label(f, text="Student 2 Timetable Slot:", font=BODY_FONT, bg=BG).grid(row=5, column=0, sticky="e", pady=4)
        s2_slot_var = tk.StringVar(value="C1")
        s2_slot_cb = ttk.Combobox(f, textvariable=s2_slot_var, values=CAT2_SLOTS, width=10, state="readonly")
        s2_slot_cb.grid(row=5, column=1, sticky="w", pady=4, padx=6)

        rule_box = tk.Label(win,
                            text="✅ System verifies slots do not clash and automatically assigns Phase 1 to whichever student has the earlier exam!",
                            font=SMALL_FONT, bg="#dcfce7", fg=SUCCESS, padx=8, pady=6, wraplength=480)
        rule_box.pack(pady=10)

        def do_checkout():
            try:
                selected_book = book_var.get()
                if not selected_book:
                    raise ValueError("Please select a book.")
                b_id = int(selected_book.split(":")[0])
                sub_code = subj_var.get().split(" - ")[0]
                m1 = int(s1_id_var.get().strip())
                m2 = int(s2_id_var.get().strip())
                slot1 = s1_slot_var.get().strip()
                slot2 = s2_slot_var.get().strip()

                if m1 == m2:
                    raise ValueError("Student 1 and Student 2 cannot have the same Member ID.")
                if slot1 == slot2:
                    raise ValueError(f"Both students are in {slot1}! Collaborative lending requires different slots so exam dates differ.")

                self.run_async(
                    lambda: self.client.request(
                        "collab_checkout",
                        book_id=b_id,
                        subject_code=sub_code,
                        member1_id=m1,
                        slot1=slot1,
                        member2_id=m2,
                        slot2=slot2
                    ),
                    lambda res: self.after_collab_checkout(win, res),
                    "Activating collaborative loan..."
                )
            except ValueError as err:
                messagebox.showerror("Error", str(err), parent=win)

        ttk.Button(win, text="Confirm & Activate Co-Loan", command=do_checkout).pack(pady=8)

    def after_collab_checkout(self, win, res):
        win.destroy()
        msg = (
            f"🎉 Collaborative Loan #{res['collab_id']} Activated!\n\n"
            f"📘 Book: {res['book_title']} ({res['subject_code']})\n\n"
            f"1️⃣ Phase 1 Student: {res['phase1_member']['name']} (Slot {res['phase1_member']['slot']})\n"
            f"   📝 Exam Date: {res['phase1_member']['exam_date']}\n\n"
            f"🔄 Scheduled Handover Date: {res['handover_date']}\n\n"
            f"2️⃣ Phase 2 Student: {res['phase2_member']['name']} (Slot {res['phase2_member']['slot']})\n"
            f"   📝 Exam Date: {res['phase2_member']['exam_date']}\n\n"
            f"📥 Final Library Return Due: {res['due_on']}"
        )
        messagebox.showinfo("Co-Lending Active", msg)
        self.refresh_all()

    def collab_lend_selected(self):
        self.open_collab_checkout_dialog()

    def open_create_request_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Post Open Co-Lend Request")
        win.geometry("500x320")
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="📢 Post Co-Lending Request (Looking for Slot Partner)", font=HEADER_FONT, bg=BG).pack(pady=10)
        f = tk.Frame(win, bg=BG, padx=16)
        f.pack(fill="x")

        book_var = tk.StringVar()
        book_titles = [f"{b['id']}: {b['title']}" for b in self.books_cache]
        book_cb = ttk.Combobox(f, textvariable=book_var, values=book_titles, width=34, state="readonly")
        if book_titles:
            book_cb.current(0)
        tk.Label(f, text="Select Book:", font=BODY_FONT, bg=BG).grid(row=0, column=0, sticky="e", pady=4)
        book_cb.grid(row=0, column=1, sticky="w", pady=4, padx=6)

        subj_var = tk.StringVar()
        subj_options = [f"{k} - {v}" for k, v in CAT2_SUBJECTS.items()]
        subj_cb = ttk.Combobox(f, textvariable=subj_var, values=subj_options, width=34, state="readonly")
        subj_cb.current(0)
        tk.Label(f, text="Course Subject:", font=BODY_FONT, bg=BG).grid(row=1, column=0, sticky="e", pady=4)
        subj_cb.grid(row=1, column=1, sticky="w", pady=4, padx=6)

        m_var = tk.StringVar(value="1")
        tk.Label(f, text="Your Member ID:", font=BODY_FONT, bg=BG).grid(row=2, column=0, sticky="e", pady=4)
        tk.Entry(f, textvariable=m_var, width=12, font=BODY_FONT).grid(row=2, column=1, sticky="w", pady=4, padx=6)

        slot_var = tk.StringVar(value="A1")
        slot_cb = ttk.Combobox(f, textvariable=slot_var, values=CAT2_SLOTS, width=10, state="readonly")
        tk.Label(f, text="Your Enrolled Slot:", font=BODY_FONT, bg=BG).grid(row=3, column=0, sticky="e", pady=4)
        slot_cb.grid(row=3, column=1, sticky="w", pady=4, padx=6)

        def do_post():
            try:
                b_id = int(book_var.get().split(":")[0])
                sub_code = subj_var.get().split(" - ")[0]
                m_id = int(m_var.get().strip())
                slot = slot_var.get().strip()

                self.run_async(
                    lambda: self.client.request("collab_request", book_id=b_id, subject_code=sub_code,
                                                member_id=m_id, slot=slot),
                    lambda req_id: self.after_post_req(win, req_id),
                    "Posting request..."
                )
            except ValueError as err:
                messagebox.showerror("Error", str(err), parent=win)

        ttk.Button(win, text="Post to Board", command=do_post).pack(pady=12)

    def after_post_req(self, win, req_id):
        win.destroy()
        messagebox.showinfo("Success", f"Request #{req_id} posted! Other students with different slots can now join you.")
        self.refresh_collab()

    def join_selected_request(self):
        selection = self.collab_req_tree.selection()
        if not selection:
            messagebox.showwarning("Select Request", "Please select an open request from the board first.")
            return

        values = self.collab_req_tree.item(selection[0], "values")
        req_id = int(values[0])
        subject = values[1]
        book_title = values[2]
        req_slot = values[5]

        win = tk.Toplevel(self.root)
        win.title(f"Join Co-Lending Request #{req_id}")
        win.geometry("450x240")
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=f"Join Request for: {book_title}", font=HEADER_FONT, bg=BG).pack(pady=8)
        tk.Label(win, text=f"Subject: {subject} | Requester Slot: {req_slot}", font=SMALL_FONT, bg=BG, fg=MUTED).pack()

        f = tk.Frame(win, bg=BG, padx=16, pady=8)
        f.pack(fill="x")

        m_id_var = tk.StringVar(value="2")
        tk.Label(f, text="Your Member ID:", font=BODY_FONT, bg=BG).grid(row=0, column=0, sticky="e", pady=4)
        tk.Entry(f, textvariable=m_id_var, width=12, font=BODY_FONT).grid(row=0, column=1, sticky="w", pady=4, padx=6)

        avail_slots = [s for s in CAT2_SLOTS if s != req_slot]
        slot_var = tk.StringVar(value=avail_slots[0] if avail_slots else "C1")
        slot_cb = ttk.Combobox(f, textvariable=slot_var, values=avail_slots, width=10, state="readonly")
        tk.Label(f, text="Your Slot (Different):", font=BODY_FONT, bg=BG).grid(row=1, column=0, sticky="e", pady=4)
        slot_cb.grid(row=1, column=1, sticky="w", pady=4, padx=6)

        def do_join():
            try:
                m_id = int(m_id_var.get().strip())
                slot = slot_var.get().strip()
                if slot == req_slot:
                    raise ValueError(f"You cannot choose the same slot ({req_slot}) as the requester.")

                self.run_async(
                    lambda: self.client.request(
                        "accept_collab_request",
                        request_id=req_id,
                        joining_member_id=m_id,
                        joining_slot=slot
                    ),
                    lambda res: self.after_collab_checkout(win, res),
                    "Pairing co-lenders..."
                )
            except ValueError as err:
                messagebox.showerror("Error", str(err), parent=win)

        ttk.Button(win, text="Confirm & Pair Co-Loan", command=do_join).pack(pady=8)

    def handover_selected_collab(self):
        selection = self.collab_tree.selection()
        if not selection:
            messagebox.showwarning("Select Loan", "Please select an active collaborative loan first.")
            return

        values = self.collab_tree.item(selection[0], "values")
        collab_id = int(values[0])
        status = values[10]

        if status != "ACTIVE_PHASE_1":
            messagebox.showinfo("Handover Complete", f"Loan #{collab_id} is in status '{status}'. Handover was already performed.")
            return

        if not messagebox.askyesno(
            "Confirm Handover",
            f"Has Student 1 completed Exam 1 and physically handed over the book to Student 2 for Loan #{collab_id}?"
        ):
            return

        self.run_async(
            lambda: self.client.request("collab_handover", collab_id=collab_id),
            lambda _: self.after_change(f"Handover confirmed for Loan #{collab_id}! Custody transferred to Phase 2."),
            "Confirming handover..."
        )

    def return_selected_collab(self):
        selection = self.collab_tree.selection()
        if not selection:
            messagebox.showwarning("Select Loan", "Please select a collaborative loan first.")
            return

        values = self.collab_tree.item(selection[0], "values")
        collab_id = int(values[0])

        if not messagebox.askyesno("Return Book", f"Return the book for Collaborative Loan #{collab_id} back to the library?"):
            return

        self.run_async(
            lambda: self.client.request("collab_return", collab_id=collab_id),
            self.after_collab_return,
            "Returning book..."
        )

    def after_collab_return(self, fine):
        if fine > 0:
            messagebox.showinfo("Returned Late", f"Book returned to library. Late fine due: ${fine:.2f}")
        else:
            messagebox.showinfo("Returned", "Book successfully returned to library and restocked!")
        self.after_change("Collaborative loan closed and book restocked")

    # ------------------------------------------------------------------
    # Standard Books & Loans Actions
    # ------------------------------------------------------------------
    def checkout_selected(self):
        if not self.selected_book:
            messagebox.showwarning("Select Book", "Please select a book from the table first.")
            return
        book_id = self.selected_book["id"]
        member_id = simpledialog.askinteger("Standard Checkout", "Enter Member ID:", parent=self.root, minvalue=1)
        if member_id is None:
            return
        self.run_async(
            lambda: self.client.request("checkout", book_id=book_id, member_id=member_id),
            self.after_checkout, "Checking out book..."
        )

    def after_checkout(self, due):
        messagebox.showinfo("Checked Out", f"Book checked out. Due back on {due}.")
        self.after_change("Book checked out")

    def remove_selected(self):
        if not self.selected_book:
            messagebox.showwarning("Select Book", "Please select a book first.")
            return
        book_id = self.selected_book["id"]
        if not messagebox.askyesno("Remove Book", f"Permanently remove '{self.selected_book['title']}' (#{book_id})?"):
            return
        self.run_async(
            lambda: self.client.request("remove_book", book_id=book_id),
            lambda _: self.after_change(f"Removed book #{book_id}"), "Removing book..."
        )

    def return_selected(self):
        selection = self.loans_tree.selection()
        if not selection:
            messagebox.showwarning("Select Loan", "Please select a loan from the table first.")
            return
        values = self.loans_tree.item(selection[0], "values")
        b_id, m_id = int(values[0]), int(values[2])
        self.run_async(lambda: self.client.request("return", book_id=b_id, member_id=m_id),
                       self.after_standard_return, "Returning...")

    def after_standard_return(self, fine):
        if fine:
            messagebox.showinfo("Returned", f"Book returned late. Late fine: ${fine:.2f}")
        self.after_change("Book returned")

    def export_loans(self):
        if not self.loans_cache:
            messagebox.showinfo("Empty", "No active loans to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="loans.csv",
                                            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Book ID", "Title", "Member ID", "Member", "Borrowed", "Due", "Status"])
            for l in self.loans_cache:
                w.writerow([l["book_id"], l["title"], l["member_id"], l["name"],
                            l["borrowed_on"], l["due_on"], self.loan_status(l)])
        self.set_status(f"Exported {len(self.loans_cache)} loan(s) to {path}")

    @staticmethod
    def loan_status(loan):
        late = (date.today() - date.fromisoformat(loan["due_on"])).days
        return f"OVERDUE {late} day(s) - ${late * FINE_PER_DAY:.2f}" if late > 0 else "On time"

    def add_member(self):
        n, e = self.member_name_var.get().strip(), self.member_email_var.get().strip()
        if not n or "@" not in e:
            messagebox.showwarning("Missing Details", "Enter a valid member name and email.")
            return
        self.run_async(lambda: self.client.request("add_member", name=n, email=e),
                       self.after_add_member, "Adding member...")

    def after_add_member(self, new_id):
        self.member_name_var.set("")
        self.member_email_var.set("")
        self.set_status(f"Added member #{new_id}")
        self.load_members(quiet=True)

    # ------------------------------------------------------------------
    # Data Loading & Async Polling
    # ------------------------------------------------------------------
    def refresh_all(self):
        self.load_books(quiet=True)
        self.load_members(quiet=True)
        self.load_loans(self.loans_overdue_only, quiet=True)
        self.refresh_collab(quiet=True)

    def refresh_collab(self, quiet=False):
        self.load_collab_loans(quiet=quiet)
        self.load_collab_requests(quiet=quiet)

    def load_books(self, quiet=False):
        self.run_async(lambda: self.client.request("search", term=""), self.on_books_loaded, "Loading catalog...", quiet)

    def on_books_loaded(self, books):
        self.books_cache = books
        self.filter_books_list()
        self.update_kpi_cards()

    def load_members(self, quiet=False):
        self.run_async(lambda: self.client.request("list_members"), self.on_members_loaded, "Loading members...", quiet)

    def on_members_loaded(self, members):
        self.members_cache = members
        tree = self.members_tree
        tree.delete(*tree.get_children())
        for m in members:
            tree.insert("", "end", iid=str(m["id"]), values=(m["id"], m["name"], m["email"]))

    def load_loans(self, overdue_only=False, quiet=False):
        self.loans_overdue_only = overdue_only
        cmd = "overdue" if overdue_only else "loans"
        self.run_async(lambda: self.client.request(cmd), self.on_loans_loaded, "Loading loans...", quiet)

    def on_loans_loaded(self, loans):
        self.loans_cache = loans
        tree = self.loans_tree
        tree.delete(*tree.get_children())
        for l in loans:
            status = self.loan_status(l)
            tree.insert("", "end", iid=str(l["id"]),
                        values=(l["book_id"], l["title"], l["member_id"], l["name"],
                                l["borrowed_on"], l["due_on"], status),
                        tags=("overdue",) if status.startswith("OVERDUE") else ())
        self.update_kpi_cards()

    def load_collab_loans(self, quiet=False):
        self.run_async(lambda: self.client.request("active_collab_loans"), self.on_collab_loans_loaded,
                       "Loading co-loans...", quiet)

    def on_collab_loans_loaded(self, loans):
        self.collab_loans_cache = loans
        tree = self.collab_tree
        tree.delete(*tree.get_children())
        for l in loans:
            p1_str = f"{l['member1_name']} ({l['slot1']})"
            p2_str = f"{l['member2_name']} ({l['slot2']})"
            tree.insert("", "end", iid=str(l["id"]),
                        values=(l["id"], l["book_title"], l["subject_code"], l["current_holder_name"],
                                p1_str, l["exam1_date"], l["handover_date"],
                                p2_str, l["exam2_date"], l["due_on"], l["status"]))
        self.update_kpi_cards()

    def load_collab_requests(self, quiet=False):
        self.run_async(lambda: self.client.request("list_collab_requests"), self.on_collab_reqs_loaded,
                       "Loading requests...", quiet)

    def on_collab_reqs_loaded(self, requests):
        self.collab_requests_cache = requests
        tree = self.collab_req_tree
        tree.delete(*tree.get_children())
        for r in requests:
            tree.insert("", "end", iid=str(r["id"]),
                        values=(r["id"], f"{r['subject_code']} - {CAT2_SUBJECTS.get(r['subject_code'], '')}",
                                r["book_title"], r["available"], r["member_name"], r["slot"],
                                r["exam_date"], r["created_on"]))

    def after_change(self, msg):
        self.set_status(msg)
        self.refresh_all()

    def run_async(self, func, on_success=None, status=None, quiet=False):
        if status:
            self.set_status(status)

        def worker():
            try:
                self.results.put((on_success, func(), None, quiet))
            except Exception as error:
                self.results.put((on_success, None, error, quiet))

        threading.Thread(target=worker, daemon=True).start()

    def poll_results(self):
        self.root.after(100, self.poll_results)
        try:
            while True:
                callback, data, error, quiet = self.results.get_nowait()
                self.set_online(self.client.connected)
                if error is None:
                    self.offline_warned = False
                    if callback:
                        callback(data)
                    continue
                self.set_status(f"Error: {error}")
                if quiet:
                    continue
                if isinstance(error, ServerUnavailable):
                    if self.offline_warned:
                        continue
                    self.offline_warned = True
                messagebox.showerror("Error", str(error))
        except queue.Empty:
            pass

    def set_status(self, text):
        self.status.set(text)

    def set_online(self, up):
        self.online_label.config(text="● Connected" if up else "● Offline",
                                 fg="#22c55e" if up else "#f97316")

    def on_close(self):
        self.client.close()
        self.root.destroy()


def main(args=None):
    parser = argparse.ArgumentParser(description="Library GUI client")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parsed_args = parser.parse_args(args)

    root = tk.Tk()
    App(root, LibraryClient(parsed_args.host, parsed_args.port))
    root.mainloop()


if __name__ == "__main__":
    main()
