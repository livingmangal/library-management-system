#!/usr/bin/env python3
"""Interactive Command-Line Interface (CLI) for the library management system with CAT-2 Collaborative Lending."""

import sys
from datetime import date
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import CAT2_SLOTS, CAT2_SUBJECTS, FINE_PER_DAY
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
    print(f"  {'ID':<4} {'Title':<35} {'Author':<20} {'ISBN':<15} Avail")
    for b in books:
        print(f"  {b['id']:<4} {b['title'][:34]:<35} {b['author'][:19]:<20} "
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


def print_collab_loans(loans):
    if not loans:
        print("  No active collaborative loans.")
        return
    print(f"  {'ID':<4} {'Book':<28} {'Subject':<10} {'Phase 1 (Slot)':<22} {'Handover':<12} {'Phase 2 (Slot)':<22} {'Due':<12} {'Custody'}")
    for l in loans:
        p1 = f"{l['member1_name'][:14]} ({l['slot1']})"
        p2 = f"{l['member2_name'][:14]} ({l['slot2']})"
        print(f"  {l['id']:<4} {l['book_title'][:27]:<28} {l['subject_code']:<10} {p1:<22} {l['handover_date']:<12} {p2:<22} {l['due_on']:<12} {l['current_holder_name']}")


MENU = """
===== Library Management (CAT-2 Edition) =====
 Standard Library Actions:
  1. Add book            6. Add member
  2. Remove book         7. List members
  3. Search books        8. Show standard active loans
  4. Check out a book    9. Show overdue loans
  5. Return a book

 CAT-2 Open Book Collaborative Lending:
 10. Check out book collaboratively (2 students, different slots)
 11. View active collaborative loans / Confirm Handover / Return
 12. Post / Accept co-lending partner request
  0. Quit
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
            elif choice == "10":
                print("\n--- Direct Collaborative Checkout (CAT-2) ---")
                print("Subjects: " + ", ".join(f"{k} ({v})" for k, v in CAT2_SUBJECTS.items()))
                print("Valid Slots: " + ", ".join(CAT2_SLOTS))
                b_id = ask_int("Book ID: ")
                subj = ask("Course Subject Code (e.g. CSE2004, MAT2002, ECE2002): ")
                m1_id = ask_int("Student 1 Member ID: ")
                slot1 = ask("Student 1 Slot (e.g. A1): ")
                m2_id = ask_int("Student 2 Member ID: ")
                slot2 = ask("Student 2 Slot (e.g. C1): ")

                res = lib.collab_checkout(b_id, subj, m1_id, slot1, m2_id, slot2)
                print(f"\nCo-Loan #{res['collab_id']} Activated!")
                print(f"  Book: {res['book_title']} ({res['subject_code']})")
                print(f"  Phase 1: {res['phase1_member']['name']} (Slot {res['phase1_member']['slot']}) -> Exam: {res['phase1_member']['exam_date']}")
                print(f"  Handover Date: {res['handover_date']}")
                print(f"  Phase 2: {res['phase2_member']['name']} (Slot {res['phase2_member']['slot']}) -> Exam: {res['phase2_member']['exam_date']}")
                print(f"  Final Due Date: {res['due_on']}")

            elif choice == "11":
                loans = lib.active_collab_loans()
                print_collab_loans(loans)
                if loans:
                    sub = ask("\nEnter 'h' to confirm handover, 'r' to return book, or Enter to go back: ").lower()
                    if sub == "h":
                        c_id = ask_int("Collaborative Loan ID to handover: ")
                        lib.collab_handover(c_id)
                        print(f"Handover confirmed for Loan #{c_id}! Custody transferred to Phase 2 student.")
                    elif sub == "r":
                        c_id = ask_int("Collaborative Loan ID to return: ")
                        fine = lib.collab_return(c_id)
                        print(f"Book returned to library!" + (f" Late fine: ${fine:.2f}" if fine else ""))

            elif choice == "12":
                print("\n1. Post a Co-Lending Request\n2. View & Accept Open Request")
                opt = ask("Choose (1/2): ")
                if opt == "1":
                    b_id = ask_int("Book ID: ")
                    subj = ask("Subject Code (e.g. CSE2004): ")
                    m_id = ask_int("Your Member ID: ")
                    slot = ask("Your Slot (e.g. A1): ")
                    req_id = lib.create_collab_request(b_id, subj, m_id, slot)
                    print(f"Request #{req_id} posted to matchmaker board!")
                elif opt == "2":
                    reqs = lib.list_collab_requests()
                    if not reqs:
                        print("  No open requests.")
                    else:
                        print(f"  {'Req ID':<8} {'Book':<28} {'Subject':<10} {'Student':<18} {'Slot':<8} {'Exam Date'}")
                        for r in reqs:
                            print(f"  {r['id']:<8} {r['book_title'][:27]:<28} {r['subject_code']:<10} {r['member_name'][:17]:<18} {r['slot']:<8} {r['exam_date']}")
                        pair_id = ask_int("\nEnter Request ID to join (or 0 to cancel): ")
                        if pair_id > 0:
                            jm_id = ask_int("Your Member ID: ")
                            jslot = ask("Your Enrolled Slot: ")
                            res = lib.accept_collab_request(pair_id, jm_id, jslot)
                            print(f"Paired! Collaborative Loan #{res['collab_id']} active.")

            elif choice == "0":
                print("Goodbye!")
                break
            else:
                print("Invalid choice.")
        except ValueError as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
