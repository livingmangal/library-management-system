#!/usr/bin/env python3
"""Interactive Command-Line Interface (CLI) for the library management system."""

import sys
from datetime import date
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import FINE_PER_DAY
from core.database import Library


def ask(prompt: str) -> str:
    return input(prompt).strip()


def ask_int(prompt: str) -> int:
    try:
        return int(ask(prompt))
    except ValueError:
        raise ValueError("Please enter a number.")


def print_books(books):
    if not books:
        print("  No books found.")
        return
    print(f"  {'ID':<4} {'Title':<30} {'Author':<20} {'ISBN':<15} Avail")
    for b in books:
        print(f"  {b['id']:<4} {b['title'][:29]:<30} {b['author'][:19]:<20} "
              f"{b['isbn']:<15} {b['available']}/{b['copies']}")


def print_loans(loans):
    if not loans:
        print("  None.")
        return
    today = date.today()
    for l in loans:
        late = (today - date.fromisoformat(l["due_on"])).days
        flag = f"  OVERDUE by {late} day(s), fine ${late * FINE_PER_DAY:.2f}" if late > 0 else ""
        print(f"  Book {l['book_id']} '{l['title']}' -> {l['name']} (member {l['member_id']}), "
              f"due {l['due_on']}{flag}")


MENU = """
===== Library Management =====
 1. Add book            6. Add member
 2. Remove book         7. List members
 3. Search / list books 8. Show active loans
 4. Check out a book    9. Show overdue loans
 5. Return a book       0. Quit
"""


def main(args=None):
    lib = Library()
    while True:
        print(MENU)
        choice = ask("Choose: ")
        try:
            if choice == "1":
                title, author, isbn = ask("Title: "), ask("Author: "), ask("ISBN: ")
                copies = ask_int("Copies: ")
                if not (title and author and isbn) or copies < 1:
                    raise ValueError("All fields are required and copies must be >= 1.")
                print(f"Added book with ID {lib.add_book(title, author, isbn, copies)}.")
            elif choice == "2":
                lib.remove_book(ask_int("Book ID: "))
                print("Book removed.")
            elif choice == "3":
                print_books(lib.search_books(ask("Search (blank for all): ")))
            elif choice == "4":
                due = lib.checkout(ask_int("Book ID: "), ask_int("Member ID: "))
                print(f"Checked out. Due on {due}.")
            elif choice == "5":
                fine = lib.return_book(ask_int("Book ID: "), ask_int("Member ID: "))
                print("Returned." + (f" Late fine: ${fine:.2f}" if fine else ""))
            elif choice == "6":
                name, email = ask("Name: "), ask("Email: ")
                if not name or "@" not in email:
                    raise ValueError("Enter a name and a valid email.")
                print(f"Added member with ID {lib.add_member(name, email)}.")
            elif choice == "7":
                for m in lib.list_members():
                    print(f"  {m['id']:<4} {m['name']:<25} {m['email']}")
            elif choice == "8":
                print_loans(lib.active_loans())
            elif choice == "9":
                print_loans(lib.overdue_loans())
            elif choice == "0":
                print("Goodbye!")
                break
            else:
                print("Invalid choice.")
        except ValueError as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
