#!/usr/bin/env python3
"""Tkinter client for the networked library system with CAT-2 Collaborative Lending.

Key ideas:
  * Event-driven: every button/Enter key runs a callback; mainloop() waits for events.
  * Network calls run in background threads so the window never freezes.
    Workers put results on a queue; the GUI thread polls it with root.after(),
    because tkinter widgets must only be touched from the main thread.
  * Dedicated CAT-2 Open Book Collaborative Lending Tab for slot-based textbook sharing.

Run:  python -m clients.gui.app [--host 127.0.0.1] [--port 5050]
"""

import argparse
import csv
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

BG = "#f4f1ea"
HEADER_BG = "#2c3e50"
ACCENT = "#c0392b"
TITLE_FONT = ("Helvetica", 18, "bold")
BODY_FONT = ("Helvetica", 11)
SMALL_FONT = ("Helvetica", 9)


def http_get(url):
    """Download a URL from a remote web server and return the bytes."""
    request = urllib.request.Request(url, headers={"User-Agent": "LibraryClient/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read()


class App:
    def __init__(self, root, client):
        self.root = root
        self.client = client
        self.results = queue.Queue()        # worker threads -> GUI thread
        self.cover_url = None
        self.loans_overdue_only = False
        self.loan_rows = []
        self.books_cache = []
        self.members_cache = []
        self.offline_warned = False

        root.title("Library Management System — CAT-2 Collaborative Lending")
        root.geometry("1060x680")
        root.minsize(860, 520)
        root.configure(bg=BG)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=26, font=BODY_FONT)
        style.configure("Treeview.Heading", font=("Helvetica", 11, "bold"))

        self.status = tk.StringVar(value="Ready")
        self.online = tk.StringVar()
        self.build_header()
        self.build_statusbar()
        self.build_tabs()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll_results)
        self.refresh_all()

    # ------------------------------------------------------------------
    # Layout: header / notebook of tabs / status bar
    # ------------------------------------------------------------------
    def build_header(self):
        bar = tk.Frame(self.root, bg=HEADER_BG)
        bar.pack(side="top", fill="x")
        tk.Label(bar, text="Library Management System", font=TITLE_FONT,
                 bg=HEADER_BG, fg="white", padx=16, pady=10).pack(side="left")
        self.online_label = tk.Label(bar, textvariable=self.online, font=BODY_FONT,
                                     bg=HEADER_BG, padx=16)
        self.online_label.pack(side="right")
        self.set_online(False)

    def build_statusbar(self):
        tk.Label(self.root, textvariable=self.status, anchor="w", relief="sunken", bd=1,
                 font=SMALL_FONT, bg="#e0dcd0", padx=8).pack(side="bottom", fill="x")

    def build_tabs(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        for label, builder in (
            ("Books", self.build_books_tab),
            ("Members", self.build_members_tab),
            ("Standard Loans", self.build_loans_tab),
            ("🤝 CAT-2 Co-Lending (Open Book)", self.build_collab_tab),
        ):
            tab = tk.Frame(notebook, bg=BG)
            notebook.add(tab, text=label)
            builder(tab)

    def field(self, parent, text, var, row, col=0, width=22):
        tk.Label(parent, text=text, bg=BG, font=BODY_FONT).grid(
            row=row, column=col, sticky="e", padx=4, pady=3)
        tk.Entry(parent, textvariable=var, width=width, font=BODY_FONT).grid(
            row=row, column=col + 1, sticky="w", padx=4, pady=3)

    def make_tree(self, parent, columns):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns],
                            show="headings", selectmode="browse")
        for key, heading, width in columns:
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        tree.tag_configure("overdue", foreground=ACCENT)
        tree.tag_configure("out", foreground="#888888")
        return tree

    # ---------------- Books tab ----------------
    def build_books_tab(self, tab):
        top = tk.Frame(tab, bg=BG)
        top.pack(side="top", fill="x", padx=8, pady=8)
        tk.Label(top, text="Search:", bg=BG, font=BODY_FONT).pack(side="left")
        self.search_var = tk.StringVar()
        box = tk.Entry(top, textvariable=self.search_var, width=36, font=BODY_FONT)
        box.pack(side="left", padx=6)
        box.bind("<Return>", lambda event: self.load_books())
        ttk.Button(top, text="Search", command=self.load_books).pack(side="left")
        ttk.Button(top, text="Show all", command=self.show_all_books).pack(side="left", padx=4)

        bottom = tk.Frame(tab, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=8, pady=8)

        actions = tk.LabelFrame(bottom, text="Selected book", bg=BG, font=SMALL_FONT,
                                padx=8, pady=6)
        actions.pack(side="left", fill="y")
        for text, command in (("Check out...", self.checkout_selected),
                              ("Remove", self.remove_selected),
                              ("Save cover...", self.download_cover)):
            ttk.Button(actions, text=text, command=command).pack(fill="x", pady=2)

        form = tk.LabelFrame(bottom, text="Add a book", bg=BG, font=SMALL_FONT,
                             padx=8, pady=6)
        form.pack(side="right")
        self.title_var, self.author_var, self.isbn_var, self.copies_var = (
            tk.StringVar() for _ in range(4))
        self.copies_var.set("1")
        self.field(form, "Title", self.title_var, 0)
        self.field(form, "Author", self.author_var, 1)
        self.field(form, "ISBN", self.isbn_var, 0, col=2)
        self.field(form, "Copies", self.copies_var, 1, col=2, width=6)
        ttk.Button(form, text="Look up ISBN online", command=self.lookup_isbn).grid(
            row=2, column=0, columnspan=2, pady=4)
        ttk.Button(form, text="Add book", command=self.add_book).grid(
            row=2, column=2, columnspan=2, pady=4)

        middle = tk.Frame(tab, bg=BG)
        middle.pack(fill="both", expand=True, padx=8)
        self.books_tree = self.make_tree(middle, [
            ("id", "ID", 50), ("title", "Title", 310), ("author", "Author", 200),
            ("isbn", "ISBN", 130), ("avail", "Available", 90)])

    # ---------------- Members tab ----------------
    def build_members_tab(self, tab):
        top = tk.LabelFrame(tab, text="Add a member", bg=BG, font=SMALL_FONT, padx=8, pady=6)
        top.pack(side="top", fill="x", padx=8, pady=8)
        self.member_name_var, self.member_email_var = tk.StringVar(), tk.StringVar()
        self.field(top, "Name", self.member_name_var, 0)
        self.field(top, "Email", self.member_email_var, 0, col=2, width=30)
        ttk.Button(top, text="Add member", command=self.add_member).grid(row=0, column=4, padx=8)
        ttk.Button(top, text="Refresh", command=self.load_members).grid(row=0, column=5)

        middle = tk.Frame(tab, bg=BG)
        middle.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.members_tree = self.make_tree(middle, [
            ("id", "ID", 60), ("name", "Name", 280), ("email", "Email", 320)])

    # ---------------- Standard Loans tab ----------------
    def build_loans_tab(self, tab):
        top = tk.Frame(tab, bg=BG)
        top.pack(side="top", fill="x", padx=8, pady=8)
        ttk.Button(top, text="All active loans",
                   command=lambda: self.load_loans(False)).pack(side="left")
        ttk.Button(top, text="Overdue only",
                   command=lambda: self.load_loans(True)).pack(side="left", padx=4)
        ttk.Button(top, text="Return selected", command=self.return_selected).pack(side="left", padx=12)
        ttk.Button(top, text="Export CSV...", command=self.export_loans).pack(side="right")

        middle = tk.Frame(tab, bg=BG)
        middle.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.loans_tree = self.make_tree(middle, [
            ("book", "Book ID", 60), ("title", "Title", 220), ("member", "Member ID", 75),
            ("name", "Member", 150), ("borrowed", "Borrowed", 90), ("due", "Due", 90),
            ("status", "Status", 240)])

    # ---------------- CAT-2 Collaborative Lending Tab ----------------
    def build_collab_tab(self, tab):
        banner = tk.Frame(tab, bg="#1a365d", padx=12, pady=8)
        banner.pack(side="top", fill="x")
        tk.Label(banner, text="📖 CAT-2 Open Book Collaborative Lending",
                 font=("Helvetica", 13, "bold"), fg="white", bg="#1a365d").pack(anchor="w")
        tk.Label(banner, text="Solves limited textbook shortages: Two students from different exam slots of the same subject (e.g. Slot A1 & Slot C1) co-lend the same book.",
                 font=SMALL_FONT, fg="#e2e8f0", bg="#1a365d").pack(anchor="w")

        toolbar = tk.Frame(tab, bg=BG, padx=8, pady=6)
        toolbar.pack(side="top", fill="x")
        ttk.Button(toolbar, text="⚡ Direct Co-Lend Checkout...", command=self.open_collab_checkout_dialog).pack(side="left", padx=3)
        ttk.Button(toolbar, text="📢 Post Co-Lend Request...", command=self.open_create_request_dialog).pack(side="left", padx=3)
        ttk.Button(toolbar, text="🤝 Join Selected Request", command=self.join_selected_request).pack(side="left", padx=3)
        ttk.Button(toolbar, text="🔄 Confirm Handover (Phase 1 -> 2)", command=self.handover_selected_collab).pack(side="left", padx=8)
        ttk.Button(toolbar, text="📥 Return Book to Library", command=self.return_selected_collab).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Refresh", command=self.refresh_collab).pack(side="right", padx=3)

        sub_notebook = ttk.Notebook(tab)
        sub_notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 1. Active Co-Loans
        active_frame = tk.Frame(sub_notebook, bg=BG)
        sub_notebook.add(active_frame, text="Active Collaborative Loans")
        self.collab_tree = self.make_tree(active_frame, [
            ("id", "ID", 45),
            ("book", "Book Title", 220),
            ("subject", "Subject Code", 100),
            ("holder", "Current Custody", 130),
            ("p1", "Phase 1 (Student & Slot)", 150),
            ("exam1", "Exam 1 Date", 90),
            ("handover", "Handover Date", 95),
            ("p2", "Phase 2 (Student & Slot)", 150),
            ("exam2", "Exam 2 Date", 90),
            ("due", "Final Due", 85),
            ("status", "Status", 115),
        ])
        self.collab_tree.tag_configure("phase1", foreground="#1e8449")
        self.collab_tree.tag_configure("phase2", foreground="#d35400")

        # 2. Open Requests (Matchmaker)
        req_frame = tk.Frame(sub_notebook, bg=BG)
        sub_notebook.add(req_frame, text="Open Requests (Looking for Slot Partner)")
        self.collab_req_tree = self.make_tree(req_frame, [
            ("id", "Req ID", 55),
            ("subject", "Subject", 160),
            ("book", "Book Title", 240),
            ("avail", "Avail", 50),
            ("student", "Requested By", 160),
            ("slot", "Student Slot", 80),
            ("exam", "Exam Date", 95),
            ("created", "Posted On", 95),
        ])

        # 3. Timetable Reference
        guide_frame = tk.Frame(sub_notebook, bg=BG)
        sub_notebook.add(guide_frame, text="Slot Schedule & Compatibility Reference")
        self.build_timetable_reference(guide_frame)

    def build_timetable_reference(self, parent):
        frame = tk.Frame(parent, bg=BG, padx=12, pady=10)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="University Theory Slot Schedule (CAT-2 Exam Days)",
                 font=("Helvetica", 11, "bold"), bg=BG, fg="#2c3e50").pack(anchor="w", pady=(0, 6))

        intro_text = (
            "CAT-2 Open Book exams are scheduled strictly slot-wise on different days.\n"
            "Students enrolled in the SAME course (e.g. Python Programming) under DIFFERENT slots have different exam days,\n"
            "enabling them to share the exact same physical copy without exam-day clashes!"
        )
        tk.Label(frame, text=intro_text, font=SMALL_FONT, bg=BG, justify="left", fg="#4a5568").pack(anchor="w", pady=(0, 8))

        guide_tree = ttk.Treeview(frame, columns=["slot", "day", "subjects", "rule"], show="headings", height=8)
        guide_tree.heading("slot", text="Theory Slot")
        guide_tree.heading("day", text="Relative Exam Day")
        guide_tree.heading("subjects", text="Standard Courses Enrolled")
        guide_tree.heading("rule", text="Co-Lending Compatibility")

        guide_tree.column("slot", width=80, anchor="center")
        guide_tree.column("day", width=120, anchor="center")
        guide_tree.column("subjects", width=340, anchor="w")
        guide_tree.column("rule", width=320, anchor="w")

        sample_slots = [
            ("Slot A1", "Exam Day 1 (Morning)", "CSE2004 Python Programming, MAT2002 Discrete", "Can co-lend with B1, C1, D1, E1, F1, A2, B2..."),
            ("Slot B1", "Exam Day 2 (Morning)", "ECE2002 C++ & Data Structures", "Can co-lend with A1, C1, D1, E1, F1, A2, B2..."),
            ("Slot C1", "Exam Day 3 (Morning)", "CSE3011 Theory of Computation (TOC)", "Can co-lend with A1, B1, D1, E1, F1, A2, B2..."),
            ("Slot D1", "Exam Day 4 (Morning)", "MAT2002 Discrete Mathematics", "Can co-lend with A1, B1, C1, E1, F1, A2, B2..."),
            ("Slot E1", "Exam Day 5 (Morning)", "MGT2003 Engineering Economics & Mgmt", "Can co-lend with A1, B1, C1, D1, F1, A2, B2..."),
            ("Slot F1", "Exam Day 6 (Morning)", "PLA1004 Professional Aptitude", "Can co-lend with A1, B1, C1, D1, E1, A2, B2..."),
            ("Slot A2", "Exam Day 7 (Afternoon)", "Theory Afternoon Sessions", "Can co-lend with any morning/other slot!"),
            ("Slot B2 / C2", "Exam Days 8 - 9", "Theory Evening Sessions", "Can co-lend with any other slot!"),
        ]
        for row in sample_slots:
            guide_tree.insert("", "end", values=row)
        guide_tree.pack(fill="x")

    # ------------------------------------------------------------------
    # Collaborative Lending Dialogs and Actions
    # ------------------------------------------------------------------
    def open_collab_checkout_dialog(self):
        if not self.books_cache:
            messagebox.showinfo("Wait", "Books are loading, please try again in a moment.")
            return

        win = tk.Toplevel(self.root)
        win.title("Direct Collaborative Checkout (CAT-2)")
        win.geometry("540x440")
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Check Out Book Collaboratively for CAT-2",
                 font=("Helvetica", 12, "bold"), bg=BG, fg="#2c3e50").pack(pady=10)

        f = tk.Frame(win, bg=BG)
        f.pack(fill="x", padx=16, pady=4)

        # Book selection
        tk.Label(f, text="Select Book:", font=BODY_FONT, bg=BG).grid(row=0, column=0, sticky="e", pady=4)
        book_var = tk.StringVar()
        book_titles = [f"{b['id']}: {b['title']} (Avail: {b['available']})" for b in self.books_cache]
        book_cb = ttk.Combobox(f, textvariable=book_var, values=book_titles, width=38, state="readonly")
        if book_titles:
            book_cb.current(0)
        book_cb.grid(row=0, column=1, sticky="w", pady=4, padx=6)

        # Subject selection
        tk.Label(f, text="Subject:", font=BODY_FONT, bg=BG).grid(row=1, column=0, sticky="e", pady=4)
        subject_var = tk.StringVar()
        subj_options = [f"{k} - {v}" for k, v in CAT2_SUBJECTS.items()]
        subj_cb = ttk.Combobox(f, textvariable=subject_var, values=subj_options, width=38, state="readonly")
        subj_cb.current(0)
        subj_cb.grid(row=1, column=1, sticky="w", pady=4, padx=6)

        # Student 1
        tk.Label(f, text="Student 1 Member ID:", font=BODY_FONT, bg=BG).grid(row=2, column=0, sticky="e", pady=4)
        s1_id_var = tk.StringVar()
        tk.Entry(f, textvariable=s1_id_var, width=12, font=BODY_FONT).grid(row=2, column=1, sticky="w", pady=4, padx=6)

        tk.Label(f, text="Student 1 Slot:", font=BODY_FONT, bg=BG).grid(row=3, column=0, sticky="e", pady=4)
        s1_slot_var = tk.StringVar(value="A1")
        s1_slot_cb = ttk.Combobox(f, textvariable=s1_slot_var, values=CAT2_SLOTS, width=10, state="readonly")
        s1_slot_cb.grid(row=3, column=1, sticky="w", pady=4, padx=6)

        # Student 2
        tk.Label(f, text="Student 2 Member ID:", font=BODY_FONT, bg=BG).grid(row=4, column=0, sticky="e", pady=4)
        s2_id_var = tk.StringVar()
        tk.Entry(f, textvariable=s2_id_var, width=12, font=BODY_FONT).grid(row=4, column=1, sticky="w", pady=4, padx=6)

        tk.Label(f, text="Student 2 Slot:", font=BODY_FONT, bg=BG).grid(row=5, column=0, sticky="e", pady=4)
        s2_slot_var = tk.StringVar(value="C1")
        s2_slot_cb = ttk.Combobox(f, textvariable=s2_slot_var, values=CAT2_SLOTS, width=10, state="readonly")
        s2_slot_cb.grid(row=5, column=1, sticky="w", pady=4, padx=6)

        info_lbl = tk.Label(win, text="Both students must be in different slots of the same course so exam dates do not clash.",
                            font=SMALL_FONT, bg=BG, fg="#718096", wraplength=480)
        info_lbl.pack(pady=10)

        def do_checkout():
            try:
                selected_book = book_var.get()
                if not selected_book:
                    raise ValueError("Please select a book.")
                book_id = int(selected_book.split(":")[0])
                sub_code = subject_var.get().split(" - ")[0]
                m1_id = int(s1_id_var.get().strip())
                m2_id = int(s2_id_var.get().strip())
                slot1 = s1_slot_var.get().strip()
                slot2 = s2_slot_var.get().strip()

                if m1_id == m2_id:
                    raise ValueError("Student 1 and Student 2 cannot have the same Member ID.")
                if slot1 == slot2:
                    raise ValueError(f"Both students are in {slot1}! Collaborative lending requires different slots so exam dates differ.")

                self.run_async(
                    lambda: self.client.request(
                        "collab_checkout",
                        book_id=book_id,
                        subject_code=sub_code,
                        member1_id=m1_id,
                        slot1=slot1,
                        member2_id=m2_id,
                        slot2=slot2
                    ),
                    lambda res: self.after_collab_checkout(win, res),
                    "Setting up collaborative loan..."
                )
            except ValueError as err:
                messagebox.showerror("Invalid Input", str(err), parent=win)

        ttk.Button(win, text="Confirm Co-Lend Checkout", command=do_checkout).pack(pady=6)

    def after_collab_checkout(self, dialog, result):
        dialog.destroy()
        msg = (
            f"Collaborative Loan #{result['collab_id']} Created Successfully!\n\n"
            f"📘 Book: {result['book_title']} ({result['subject_code']})\n"
            f"👤 Phase 1: {result['phase1_member']['name']} (Slot {result['phase1_member']['slot']})\n"
            f"   Exam Date: {result['phase1_member']['exam_date']}\n"
            f"🔄 Handover to Phase 2 Date: {result['handover_date']}\n"
            f"👤 Phase 2: {result['phase2_member']['name']} (Slot {result['phase2_member']['slot']})\n"
            f"   Exam Date: {result['phase2_member']['exam_date']}\n"
            f"📥 Final Return Due Date: {result['due_on']}"
        )
        messagebox.showinfo("Collaborative Loan Active", msg)
        self.set_status("Collaborative loan activated")
        self.refresh_all()

    def open_create_request_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Post Open Co-Lending Request (Matchmaker)")
        win.geometry("500x320")
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="Post a Co-Lend Request (Looking for a Slot Partner)",
                 font=("Helvetica", 12, "bold"), bg=BG, fg="#2c3e50").pack(pady=10)

        f = tk.Frame(win, bg=BG)
        f.pack(fill="x", padx=16, pady=4)

        tk.Label(f, text="Select Book:", font=BODY_FONT, bg=BG).grid(row=0, column=0, sticky="e", pady=4)
        book_var = tk.StringVar()
        book_titles = [f"{b['id']}: {b['title']}" for b in self.books_cache]
        book_cb = ttk.Combobox(f, textvariable=book_var, values=book_titles, width=34, state="readonly")
        if book_titles:
            book_cb.current(0)
        book_cb.grid(row=0, column=1, sticky="w", pady=4, padx=6)

        tk.Label(f, text="Subject:", font=BODY_FONT, bg=BG).grid(row=1, column=0, sticky="e", pady=4)
        subject_var = tk.StringVar()
        subj_options = [f"{k} - {v}" for k, v in CAT2_SUBJECTS.items()]
        subj_cb = ttk.Combobox(f, textvariable=subject_var, values=subj_options, width=34, state="readonly")
        subj_cb.current(0)
        subj_cb.grid(row=1, column=1, sticky="w", pady=4, padx=6)

        tk.Label(f, text="Your Member ID:", font=BODY_FONT, bg=BG).grid(row=2, column=0, sticky="e", pady=4)
        m_id_var = tk.StringVar()
        tk.Entry(f, textvariable=m_id_var, width=12, font=BODY_FONT).grid(row=2, column=1, sticky="w", pady=4, padx=6)

        tk.Label(f, text="Your Enrolled Slot:", font=BODY_FONT, bg=BG).grid(row=3, column=0, sticky="e", pady=4)
        slot_var = tk.StringVar(value="A1")
        slot_cb = ttk.Combobox(f, textvariable=slot_var, values=CAT2_SLOTS, width=10, state="readonly")
        slot_cb.grid(row=3, column=1, sticky="w", pady=4, padx=6)

        def do_post():
            try:
                selected_book = book_var.get()
                if not selected_book:
                    raise ValueError("Please select a book.")
                book_id = int(selected_book.split(":")[0])
                sub_code = subject_var.get().split(" - ")[0]
                m_id = int(m_id_var.get().strip())
                slot = slot_var.get().strip()

                self.run_async(
                    lambda: self.client.request(
                        "collab_request",
                        book_id=book_id,
                        subject_code=sub_code,
                        member_id=m_id,
                        slot=slot
                    ),
                    lambda req_id: self.after_post_request(win, req_id),
                    "Posting request..."
                )
            except ValueError as err:
                messagebox.showerror("Invalid Input", str(err), parent=win)

        ttk.Button(win, text="Post Request", command=do_post).pack(pady=12)

    def after_post_request(self, dialog, req_id):
        dialog.destroy()
        messagebox.showinfo("Request Posted", f"Co-Lending Request #{req_id} posted! Other students with different slots can now join you.")
        self.set_status(f"Posted co-lend request #{req_id}")
        self.refresh_collab()

    def join_selected_request(self):
        selection = self.collab_req_tree.selection()
        if not selection:
            messagebox.showwarning("Select Request", "Please select an open request from the table first.")
            return

        values = self.collab_req_tree.item(selection[0], "values")
        req_id = int(values[0])
        subject = values[1]
        book_title = values[2]
        req_slot = values[5]

        # Ask user for their ID and slot
        win = tk.Toplevel(self.root)
        win.title(f"Join Co-Lending Request #{req_id}")
        win.geometry("450x240")
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=f"Join Request for: {book_title}", font=("Helvetica", 11, "bold"), bg=BG).pack(pady=8)
        tk.Label(win, text=f"Subject: {subject} | Requester Slot: {req_slot}", font=SMALL_FONT, bg=BG).pack()

        f = tk.Frame(win, bg=BG)
        f.pack(fill="x", padx=16, pady=8)

        tk.Label(f, text="Your Member ID:", font=BODY_FONT, bg=BG).grid(row=0, column=0, sticky="e", pady=4)
        m_id_var = tk.StringVar()
        tk.Entry(f, textvariable=m_id_var, width=12, font=BODY_FONT).grid(row=0, column=1, sticky="w", pady=4, padx=6)

        tk.Label(f, text="Your Slot:", font=BODY_FONT, bg=BG).grid(row=1, column=0, sticky="e", pady=4)
        # Exclude requester's slot from choices to guide user
        avail_slots = [s for s in CAT2_SLOTS if s != req_slot]
        slot_var = tk.StringVar(value=avail_slots[0] if avail_slots else "B1")
        slot_cb = ttk.Combobox(f, textvariable=slot_var, values=avail_slots, width=10, state="readonly")
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
            messagebox.showinfo("Handover Complete", f"Loan #{collab_id} is already in status '{status}'. Handover was already performed.")
            return

        if not messagebox.askyesno(
            "Confirm Handover",
            f"Has Student 1 completed their exam and physically handed the book over to Student 2 for Loan #{collab_id}?"
        ):
            return

        self.run_async(
            lambda: self.client.request("collab_handover", collab_id=collab_id),
            lambda _: self.after_change(f"Handover confirmed for Loan #{collab_id}"),
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
        self.after_change("Collaborative loan closed and book returned")

    def refresh_collab(self, quiet=False):
        self.load_collab_loans(quiet=quiet)
        self.load_collab_requests(quiet=quiet)

    def load_collab_loans(self, quiet=False):
        self.run_async(
            lambda: self.client.request("active_collab_loans"),
            self.fill_collab_loans,
            "Loading collaborative loans...",
            quiet
        )

    def fill_collab_loans(self, loans):
        tree = self.collab_tree
        tree.delete(*tree.get_children())
        for l in loans:
            tag = "phase1" if l["status"] == "ACTIVE_PHASE_1" else "phase2"
            p1_str = f"{l['member1_name']} ({l['slot1']})"
            p2_str = f"{l['member2_name']} ({l['slot2']})"
            tree.insert(
                "", "end", iid=str(l["id"]),
                values=(
                    l["id"], l["book_title"], l["subject_code"], l["current_holder_name"],
                    p1_str, l["exam1_date"], l["handover_date"],
                    p2_str, l["exam2_date"], l["due_on"], l["status"]
                ),
                tags=(tag,)
            )

    def load_collab_requests(self, quiet=False):
        self.run_async(
            lambda: self.client.request("list_collab_requests"),
            self.fill_collab_requests,
            "Loading co-lending requests...",
            quiet
        )

    def fill_collab_requests(self, requests):
        tree = self.collab_req_tree
        tree.delete(*tree.get_children())
        for r in requests:
            subj_title = f"{r['subject_code']} - {CAT2_SUBJECTS.get(r['subject_code'], '')}"
            tree.insert(
                "", "end", iid=str(r["id"]),
                values=(
                    r["id"], subj_title, r["book_title"], r["available"],
                    r["member_name"], r["slot"], r["exam_date"], r["created_on"]
                )
            )

    # ------------------------------------------------------------------
    # Threading helpers
    # ------------------------------------------------------------------
    def run_async(self, func, on_success=None, status=None, quiet=False):
        """Run func() in a worker thread; call on_success(result) in the GUI thread."""
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
        self.online.set("\u25cf Connected" if up else "\u25cf Offline")
        self.online_label.config(fg="#2ecc71" if up else "#e67e22")

    def on_close(self):
        self.client.close()
        self.root.destroy()

    def selected_id(self, tree, what):
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Nothing selected", f"Please select a {what} first.")
            return None
        return int(selection[0])

    # ------------------------------------------------------------------
    # Books logic
    # ------------------------------------------------------------------
    def refresh_all(self):
        self.load_books(quiet=True)
        self.load_members(quiet=True)
        self.load_loans(self.loans_overdue_only, quiet=True)
        self.refresh_collab(quiet=True)

    def show_all_books(self):
        self.search_var.set("")
        self.load_books()

    def load_books(self, quiet=False):
        term = self.search_var.get().strip()
        self.run_async(lambda: self.client.request("search", term=term),
                       self.fill_books, "Searching...", quiet)

    def fill_books(self, books):
        self.books_cache = books
        tree = self.books_tree
        tree.delete(*tree.get_children())
        for b in books:
            tree.insert("", "end", iid=str(b["id"]),
                        values=(b["id"], b["title"], b["author"], b["isbn"],
                                f'{b["available"]}/{b["copies"]}'),
                        tags=("out",) if b["available"] == 0 else ())
        self.set_status(f"{len(books)} book(s) shown")

    def add_book(self):
        title, author = self.title_var.get().strip(), self.author_var.get().strip()
        isbn = self.isbn_var.get().strip()
        try:
            copies = int(self.copies_var.get())
        except ValueError:
            copies = 0
        if not (title and author and isbn) or copies < 1:
            messagebox.showwarning("Missing details",
                                   "Fill in title, author, ISBN and a copy count of 1 or more.")
            return
        self.run_async(
            lambda: self.client.request("add_book", title=title, author=author,
                                        isbn=isbn, copies=copies),
            self.after_add_book, "Adding book...")

    def after_add_book(self, new_id):
        for var in (self.title_var, self.author_var, self.isbn_var):
            var.set("")
        self.copies_var.set("1")
        self.cover_url = None
        self.set_status(f"Added book #{new_id}")
        self.load_books(quiet=True)

    def remove_selected(self):
        book_id = self.selected_id(self.books_tree, "book")
        if book_id is None:
            return
        if not messagebox.askyesno("Remove book", f"Remove book #{book_id} permanently?"):
            return
        self.run_async(lambda: self.client.request("remove_book", book_id=book_id),
                       lambda _: self.after_change(f"Removed book #{book_id}"), "Removing...")

    def checkout_selected(self):
        book_id = self.selected_id(self.books_tree, "book")
        if book_id is None:
            return
        member_id = simpledialog.askinteger("Check out", "Member ID:", parent=self.root,
                                            minvalue=1)
        if member_id is None:
            return
        self.run_async(
            lambda: self.client.request("checkout", book_id=book_id, member_id=member_id),
            self.after_checkout, "Checking out...")

    def after_checkout(self, due):
        messagebox.showinfo("Checked out", f"Book checked out. Due on {due}.")
        self.after_change("Checked out")

    def after_change(self, message):
        self.set_status(message)
        self.refresh_all()

    def lookup_isbn(self):
        isbn = self.isbn_var.get().strip().replace("-", "")
        if not isbn:
            messagebox.showwarning("ISBN needed", "Type an ISBN first.")
            return

        def fetch():
            query = urllib.parse.urlencode(
                {"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"})
            data = json.loads(http_get("https://openlibrary.org/api/books?" + query))
            return data.get(f"ISBN:{isbn}")

        self.run_async(fetch, self.fill_from_lookup, "Looking up ISBN on openlibrary.org...")

    def fill_from_lookup(self, info):
        if not info:
            self.set_status("ISBN not found online")
            messagebox.showinfo("Not found", "Open Library has no record of that ISBN.")
            return
        self.title_var.set(info.get("title", ""))
        self.author_var.set(", ".join(a["name"] for a in info.get("authors", [])))
        self.cover_url = info.get("cover", {}).get("medium")
        self.set_status("Details filled in from Open Library")

    def download_cover(self):
        if not self.cover_url:
            messagebox.showinfo("No cover", "Use 'Look up ISBN online' first to find a cover image.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".jpg", initialfile="cover.jpg",
                                            filetypes=[("JPEG image", "*.jpg")])
        if not path:
            return

        def fetch():
            with open(path, "wb") as f:
                f.write(http_get(self.cover_url))
            return path

        self.run_async(fetch, lambda p: self.set_status(f"Saved cover to {p}"),
                       "Downloading cover...")

    # ---------------- Members logic ----------------
    def load_members(self, quiet=False):
        self.run_async(lambda: self.client.request("list_members"),
                       self.fill_members, "Loading members...", quiet)

    def fill_members(self, members):
        self.members_cache = members
        tree = self.members_tree
        tree.delete(*tree.get_children())
        for m in members:
            tree.insert("", "end", iid=str(m["id"]), values=(m["id"], m["name"], m["email"]))
        self.set_status(f"{len(members)} member(s)")

    def add_member(self):
        name, email = self.member_name_var.get().strip(), self.member_email_var.get().strip()
        if not name or "@" not in email:
            messagebox.showwarning("Missing details", "Enter a name and a valid email address.")
            return
        self.run_async(lambda: self.client.request("add_member", name=name, email=email),
                       self.after_add_member, "Adding member...")

    def after_add_member(self, new_id):
        self.member_name_var.set("")
        self.member_email_var.set("")
        self.set_status(f"Added member #{new_id}")
        self.load_members(quiet=True)

    # ---------------- Loans logic ----------------
    def load_loans(self, overdue_only=False, quiet=False):
        self.loans_overdue_only = overdue_only
        command = "overdue" if overdue_only else "loans"
        self.run_async(lambda: self.client.request(command), self.fill_loans,
                       "Loading loans...", quiet)

    @staticmethod
    def loan_status(loan):
        late = (date.today() - date.fromisoformat(loan["due_on"])).days
        if late > 0:
            return f"OVERDUE {late} day(s) - fine ${late * FINE_PER_DAY:.2f}"
        return "On time"

    def fill_loans(self, loans):
        self.loan_rows = loans
        tree = self.loans_tree
        tree.delete(*tree.get_children())
        for loan in loans:
            status = self.loan_status(loan)
            tree.insert("", "end", iid=str(loan["id"]),
                        values=(loan["book_id"], loan["title"], loan["member_id"], loan["name"],
                                loan["borrowed_on"], loan["due_on"], status),
                        tags=("overdue",) if status.startswith("OVERDUE") else ())
        self.set_status(f"{len(loans)} loan(s) shown")

    def return_selected(self):
        selection = self.loans_tree.selection()
        if not selection:
            messagebox.showwarning("Nothing selected", "Please select a loan first.")
            return
        values = self.loans_tree.item(selection[0], "values")
        book_id, member_id = int(values[0]), int(values[2])
        self.run_async(
            lambda: self.client.request("return", book_id=book_id, member_id=member_id),
            self.after_return, "Returning...")

    def after_return(self, fine):
        if fine:
            messagebox.showinfo("Returned", f"Book returned late. Fine due: ${fine:.2f}")
        self.after_change("Book returned")

    def export_loans(self):
        if not self.loan_rows:
            messagebox.showinfo("Nothing to export", "There are no loans in the table.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="loans.csv",
                                            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Book ID", "Title", "Member ID", "Member", "Borrowed", "Due", "Status"])
            for l in self.loan_rows:
                writer.writerow([l["book_id"], l["title"], l["member_id"], l["name"],
                                 l["borrowed_on"], l["due_on"], self.loan_status(l)])
        self.set_status(f"Exported {len(self.loan_rows)} loan(s) to {path}")


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
