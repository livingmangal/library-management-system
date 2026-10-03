#!/usr/bin/env python3
"""CGI script: handles the membership form (POST /cgi-bin/register.py)."""

from common import ask_server, esc, form_data, page

data = form_data()
name, email = data.get("name", "").strip(), data.get("email", "").strip()

if not name or "@" not in email:
    page("Registration", '<p class="error">Please go back and enter your name and a valid email address.</p>')
else:
    try:
        member_id = ask_server("add_member", name=name, email=email)
    except ValueError as e:                       # e.g. email already registered
        page("Registration", f'<p class="error">{esc(e)}</p>')
    except OSError:
        page("Registration", '<p class="error">The library server is not running. Please try again later.</p>')
    else:
        page("Welcome!", f'<p class="ok">Thanks, {esc(name)}. Your member ID is <b>{member_id}</b>. '
                         "Tell the librarian this number when you borrow a book.</p>")
