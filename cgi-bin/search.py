#!/usr/bin/env python3
"""CGI script: handles the catalogue search form (GET /cgi-bin/search.py?q=...)."""

from common import ask_server, esc, form_data, page

term = form_data().get("q", "").strip()

try:
    books = ask_server("search", term=term)
except (OSError, ValueError):
    page("Search results", '<p class="error">The library server is not running. Please try again later.</p>')
else:
    if not books:
        body = f'<p class="none">No books match &ldquo;{esc(term)}&rdquo;.</p>'
    else:
        rows = "\n".join(
            f"<tr><td>{esc(b['title'])}</td><td>{esc(b['author'])}</td><td>{esc(b['isbn'])}</td>"
            f"<td>{'Available' if b['available'] else 'On loan'} ({b['available']}/{b['copies']})</td></tr>"
            for b in books)
        body = (f"<p>{len(books)} result(s) for &ldquo;{esc(term)}&rdquo;</p>"
                "<table><tr><th>Title</th><th>Author</th><th>ISBN</th><th>Status</th></tr>"
                f"{rows}</table>")
    page("Search results", body)
