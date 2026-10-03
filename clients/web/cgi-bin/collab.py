#!/usr/bin/env python3
"""CGI script: handles CAT-2 Collaborative Lending requests and timetable co-lending."""

from common import ask_server, esc, form_data, page

data = form_data()
action = data.get("action", "list")

try:
    if action == "checkout":
        book_id = int(data.get("book_id", 0))
        subject_code = data.get("subject_code", "").strip().upper()
        m1_id = int(data.get("m1_id", 0))
        slot1 = data.get("slot1", "").strip().upper()
        m2_id = int(data.get("m2_id", 0))
        slot2 = data.get("slot2", "").strip().upper()

        if not (book_id and subject_code and m1_id and slot1 and m2_id and slot2):
            raise ValueError("All fields (Book ID, Subject, Student 1 ID & Slot, Student 2 ID & Slot) are required.")

        res = ask_server(
            "collab_checkout",
            book_id=book_id,
            subject_code=subject_code,
            member1_id=m1_id,
            slot1=slot1,
            member2_id=m2_id,
            slot2=slot2
        )
        body = f"""
        <div style="background: #e8f8f5; border: 1px solid #27ae60; padding: 1.2rem; border-radius: 6px;">
            <h2 class="ok" style="margin-top:0;">Collaborative Loan #{res['collab_id']} Activated!</h2>
            <p><b>Book:</b> {esc(res['book_title'])} (Course: <code>{esc(res['subject_code'])}</code>)</p>
            <p><b>Phase 1:</b> {esc(res['phase1_member']['name'])} (Slot {esc(res['phase1_member']['slot'])}) &mdash; Exam Date: <b>{esc(res['phase1_member']['exam_date'])}</b></p>
            <p><b>🔄 Scheduled Handover Date:</b> <span style="background: #fff3cd; padding: 2px 6px; font-weight: bold;">{esc(res['handover_date'])}</span></p>
            <p><b>Phase 2:</b> {esc(res['phase2_member']['name'])} (Slot {esc(res['phase2_member']['slot'])}) &mdash; Exam Date: <b>{esc(res['phase2_member']['exam_date'])}</b></p>
            <p><b>📥 Final Library Return Due:</b> <b>{esc(res['due_on'])}</b></p>
        </div>
        <p style="margin-top: 1.5rem;"><a href="/cgi-bin/collab.py?action=list" style="font-weight: bold;">&larr; View Active Co-Loans & Requests</a></p>
        """
        page("Co-Lending Confirmed", body)

    elif action == "request":
        book_id = int(data.get("book_id", 0))
        subject_code = data.get("subject_code", "").strip().upper()
        member_id = int(data.get("member_id", 0))
        slot = data.get("slot", "").strip().upper()

        if not (book_id and subject_code and member_id and slot):
            raise ValueError("All fields are required to post a co-lending request.")

        req_id = ask_server(
            "collab_request",
            book_id=book_id,
            subject_code=subject_code,
            member_id=member_id,
            slot=slot
        )
        body = f"""
        <div style="background: #e8f8f5; border: 1px solid #27ae60; padding: 1.2rem; border-radius: 6px;">
            <h2 class="ok" style="margin-top:0;">Request #{req_id} Posted!</h2>
            <p>Your request has been published on the matchmaker board. A student taking <code>{esc(subject_code)}</code> in a different slot can now pair with you!</p>
        </div>
        <p style="margin-top: 1.5rem;"><a href="/cgi-bin/collab.py?action=list" style="font-weight: bold;">&larr; View Active Co-Loans & Requests</a></p>
        """
        page("Request Posted", body)

    elif action == "handover":
        collab_id = int(data.get("collab_id", 0))
        res = ask_server("collab_handover", collab_id=collab_id)
        body = f"""
        <div style="background: #e8f8f5; border: 1px solid #27ae60; padding: 1.2rem; border-radius: 6px;">
            <h2 class="ok" style="margin-top:0;">Handover Confirmed for Loan #{res['collab_id']}</h2>
            <p>Custody has successfully transitioned to Student 2 (Phase 2). Student 2 now holds the book for their exam!</p>
        </div>
        <p style="margin-top: 1.5rem;"><a href="/cgi-bin/collab.py?action=list" style="font-weight: bold;">&larr; Return to Co-Lending Dashboard</a></p>
        """
        page("Handover Confirmed", body)

    elif action == "return":
        collab_id = int(data.get("collab_id", 0))
        fine = ask_server("collab_return", collab_id=collab_id)
        fine_msg = f" Late fine owed: ${fine:.2f}" if fine > 0 else " No fine owed."
        body = f"""
        <div style="background: #e8f8f5; border: 1px solid #27ae60; padding: 1.2rem; border-radius: 6px;">
            <h2 class="ok" style="margin-top:0;">Book Returned to Library!</h2>
            <p>Collaborative Loan #{collab_id} is completed and the book has been restocked.{esc(fine_msg)}</p>
        </div>
        <p style="margin-top: 1.5rem;"><a href="/cgi-bin/collab.py?action=list" style="font-weight: bold;">&larr; Return to Co-Lending Dashboard</a></p>
        """
        page("Return Completed", body)

    else:
        # Default: List active loans and requests
        active_loans = ask_server("active_collab_loans")
        open_requests = ask_server("list_collab_requests")

        loans_html = ""
        if not active_loans:
            loans_html = "<p class='none'>No active collaborative loans currently in progress.</p>"
        else:
            rows = []
            for l in active_loans:
                status_color = "#27ae60" if l["status"] == "ACTIVE_PHASE_1" else "#e67e22"
                rows.append(f"""
                <tr>
                    <td>#{l['id']}</td>
                    <td><b>{esc(l['book_title'])}</b><br><small>Course: {esc(l['subject_code'])}</small></td>
                    <td><b>{esc(l['current_holder_name'])}</b></td>
                    <td>{esc(l['member1_name'])} (Slot {esc(l['slot1'])})<br><small>Exam: {esc(l['exam1_date'])}</small></td>
                    <td><b>{esc(l['handover_date'])}</b></td>
                    <td>{esc(l['member2_name'])} (Slot {esc(l['slot2'])})<br><small>Exam: {esc(l['exam2_date'])}</small></td>
                    <td>{esc(l['due_on'])}</td>
                    <td><span style="color: {status_color}; font-weight: bold;">{esc(l['status'])}</span></td>
                    <td>
                        {'<form action="/cgi-bin/collab.py" method="post" style="display:inline;"><input type="hidden" name="action" value="handover"><input type="hidden" name="collab_id" value="' + str(l['id']) + '"><button type="submit" style="padding:2px 8px;font-size:11px;background:#e67e22;color:white;border:none;border-radius:3px;cursor:pointer;">Handover</button></form>' if l['status'] == 'ACTIVE_PHASE_1' else ''}
                        <form action="/cgi-bin/collab.py" method="post" style="display:inline;"><input type="hidden" name="action" value="return"><input type="hidden" name="collab_id" value="{l['id']}"><button type="submit" style="padding:2px 8px;font-size:11px;background:#2c3e50;color:white;border:none;border-radius:3px;cursor:pointer;">Return</button></form>
                    </td>
                </tr>
                """)
            loans_html = f"""
            <table>
                <tr>
                    <th>ID</th><th>Book & Subject</th><th>Current Custody</th><th>Phase 1</th><th>Handover Date</th><th>Phase 2</th><th>Final Due</th><th>Status</th><th>Actions</th>
                </tr>
                {''.join(rows)}
            </table>
            """

        reqs_html = ""
        if not open_requests:
            reqs_html = "<p class='none'>No open co-lending requests at the moment.</p>"
        else:
            r_rows = []
            for r in open_requests:
                r_rows.append(f"""
                <tr>
                    <td>#{r['id']}</td>
                    <td><b>{esc(r['book_title'])}</b></td>
                    <td><code>{esc(r['subject_code'])}</code></td>
                    <td>{esc(r['member_name'])}</td>
                    <td><b>Slot {esc(r['slot'])}</b> (Exam: {esc(r['exam_date'])})</td>
                    <td>{esc(r['created_on'])}</td>
                </tr>
                """)
            reqs_html = f"""
            <table>
                <tr>
                    <th>Req ID</th><th>Book Title</th><th>Subject</th><th>Student</th><th>Enrolled Slot</th><th>Posted On</th>
                </tr>
                {''.join(r_rows)}
            </table>
            """

        body = f"""
        <div style="background:#1a365d;color:white;padding:0.8rem 1rem;border-radius:4px;margin-bottom:1.5rem;">
            <h2 style="margin:0;font-size:1.2rem;">📚 CAT-2 Open Book Collaborative Lending Hub</h2>
            <p style="margin:0.3rem 0 0;font-size:0.85rem;color:#cbd5e1;">Allows two students taking the same subject in different timetable slots (e.g. Slot A1 & Slot C1) to co-lend and share a book for their respective exams.</p>
        </div>

        <h3 style="color:#2c3e50;">Active Collaborative Loans</h3>
        {loans_html}

        <h3 style="color:#2c3e50;margin-top:2rem;">Open Co-Lending Matchmaker Requests</h3>
        <p style="font-size:0.9rem;color:#555;">Students looking for a partner in another slot to co-borrow the textbook together:</p>
        {reqs_html}

        <div style="margin-top:2rem;padding:1rem;background:#f9f8f5;border:1px solid #ddd;border-radius:6px;">
            <h4 style="margin-top:0;">Timetable Slot Compatibility Rule</h4>
            <p style="font-size:0.88rem;color:#444;">
                Slots A1, B1, C1, D1, E1, F1, A2, B2... correspond to distinct exam dates in the CAT-2 timetable.
                Two students from different slots can safely co-borrow a single textbook: Student 1 uses it for Exam 1, hands it over to Student 2, and Student 2 uses it for Exam 2 before returning it.
            </p>
        </div>
        """
        page("CAT-2 Collaborative Lending", body)

except ValueError as e:
    page("Co-Lending Error", f"""
    <div style="background: #fdeed9; border: 1px solid #e67e22; padding: 1.2rem; border-radius: 6px;">
        <h3 class="error" style="margin-top:0;">Action Failed</h3>
        <p>{esc(e)}</p>
    </div>
    <p style="margin-top: 1.5rem;"><a href="/cgi-bin/collab.py?action=list">&larr; Return to Collaborative Lending</a></p>
    """)
except (OSError, ConnectionError):
    page("Server Offline", '<p class="error">The library TCP server is not running. Please start the server and try again.</p>')
