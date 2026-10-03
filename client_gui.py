#!/usr/bin/env python3
"""Tkinter client for the networked library system.

Key ideas:
  * Event-driven: every button/Enter key runs a callback; mainloop() waits for events.
  * Network calls run in background threads so the window never freezes.
    Workers put results on a queue; the GUI thread polls it with root.after(),
    because tkinter widgets must only be touched from the main thread.

Run:  python3 client_gui.py [--host 127.0.0.1] [--port 5050]
"""

import argparse
import csv
import json
import queue
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from datetime import date
from tkinter import filedialog, messagebox, simpledialog, ttk

from client_api import LibraryClient, ServerUnavailable

FINE_PER_DAY = 0.50          # must match the server's Library class (display only)

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
        self.offline_warned = False

        root.title("Library Management System")
        root.geometry("1000x620")
        root.minsize(820, 500)
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
    # Layout: header / notebook of tabs / status bar, each made of nested frames
    # ------------------------------------------------------------------
    def build_header(self):
        bar = tk.Frame(self.root, bg=HEADER_BG)
        bar.pack(side="top", fill="x")
        tk.Label(bar, text="Library Management System", font=TITLE_FONT,
                 bg=HEADER_BG, fg="white", padx=16, pady=12).pack(side="left")
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
        for label, builder in (("Books", self.build_books_tab),
                               ("Members", self.build_members_tab),
                               ("Loans", self.build_loans_tab)):
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
            ("id", "ID", 50), ("title", "Title", 290), ("author", "Author", 200),
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

    # ---------------- Loans tab ----------------
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
            except Exception as error:        # report every failure back to the GUI
                self.results.put((on_success, None, error, quiet))

        threading.Thread(target=worker, daemon=True).start()

    def poll_results(self):
        self.root.after(100, self.poll_results)     # schedule first: callbacks may raise
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
                    if self.offline_warned:          # one dialog per outage, not one per request
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
    # Books
    # ------------------------------------------------------------------
    def refresh_all(self):
        self.load_books(quiet=True)
        self.load_members(quiet=True)
        self.load_loans(self.loans_overdue_only, quiet=True)

    def show_all_books(self):
        self.search_var.set("")
        self.load_books()

    def load_books(self, quiet=False):
        term = self.search_var.get().strip()
        self.run_async(lambda: self.client.request("search", term=term),
                       self.fill_books, "Searching...", quiet)

    def fill_books(self, books):
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

    # ---- remote HTML/JSON server: look up a book by ISBN, download its cover ----
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

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------
    def load_members(self, quiet=False):
        self.run_async(lambda: self.client.request("list_members"),
                       self.fill_members, "Loading members...", quiet)

    def fill_members(self, members):
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

    # ------------------------------------------------------------------
    # Loans
    # ------------------------------------------------------------------
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


def main():
    parser = argparse.ArgumentParser(description="Library GUI client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()

    root = tk.Tk()
    App(root, LibraryClient(args.host, args.port))
    root.mainloop()


if __name__ == "__main__":
    main()
