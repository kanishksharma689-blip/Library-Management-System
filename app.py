from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
from datetime import date, timedelta

app = Flask(__name__)

app.secret_key = "library_management_secret"

DATABASE = "library.db"

# Fine charged per late day
FINE_PER_DAY = 10


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# CREATE DATABASE TABLES
# =========================================================

def init_db():

    conn = get_db()

    # ---------------- USERS ----------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    # ---------------- BOOKS ----------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            category TEXT,
            quantity INTEGER NOT NULL,
            available INTEGER NOT NULL
        )
    """)

    # ---------------- ISSUED BOOKS ----------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            return_date TEXT,
            fine REAL DEFAULT 0,
            paid REAL DEFAULT 0,
            status TEXT DEFAULT 'Issued'
        )
    """)

    # ---------------- NOTIFICATIONS ----------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0
        )
    """)

    # =====================================================
    # DEFAULT LIBRARIAN
    # =====================================================

    conn.execute("""
        INSERT OR IGNORE INTO users
        (id, name, email, password, role)
        VALUES
        (1, 'Library Admin', 'admin@gmail.com', 'admin123', 'librarian')
    """)

    # =====================================================
    # DEFAULT STUDENT
    # =====================================================

    conn.execute("""
        INSERT OR IGNORE INTO users
        (id, name, email, password, role)
        VALUES
        (2, 'Rahul Sharma', 'student@gmail.com', 'student123', 'student')
    """)

    conn.commit()
    conn.close()


# =========================================================
# UPDATE OVERDUE BOOKS AND NOTIFICATIONS
# =========================================================

def update_overdue_books():

    conn = get_db()

    today = date.today()

    issues = conn.execute("""
        SELECT *
        FROM issues
        WHERE status = 'Issued'
    """).fetchall()

    for issue in issues:

        due_date = date.fromisoformat(issue["due_date"])

        # Check whether book is overdue
        if today > due_date:

            late_days = (today - due_date).days

            fine = late_days * FINE_PER_DAY

            conn.execute("""
                UPDATE issues
                SET fine = ?
                WHERE id = ?
            """, (fine, issue["id"]))

            # Check if overdue notification already exists
            existing = conn.execute("""
                SELECT id
                FROM notifications
                WHERE student_id = ?
                AND message LIKE ?
            """, (
                issue["student_id"],
                "%overdue%"
            )).fetchone()

            if existing is None:

                conn.execute("""
                    INSERT INTO notifications
                    (student_id, message)
                    VALUES (?, ?)
                """, (
                    issue["student_id"],
                    f"Your book is overdue. Current fine is ₹{fine}."
                ))

    conn.commit()
    conn.close()


# =========================================================
# LOGIN
# =========================================================

@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ?
            AND password = ?
        """, (email, password)).fetchone()

        conn.close()

        if user:

            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "librarian":
                return redirect("/librarian")

            if user["role"] == "student":
                return redirect("/student")

        flash("Invalid email or password.")

        return redirect("/")

    return render_template("login.html")


# =========================================================
# LIBRARIAN DASHBOARD
# =========================================================

@app.route("/librarian")
def librarian():

    if session.get("role") != "librarian":
        return redirect("/")

    # Update overdue information
    update_overdue_books()

    conn = get_db()

    # Get all books
    books = conn.execute("""
        SELECT *
        FROM books
        ORDER BY id DESC
    """).fetchall()

    # Get all students
    students = conn.execute("""
        SELECT *
        FROM users
        WHERE role = 'student'
        ORDER BY id DESC
    """).fetchall()

    # Get all issue records
    issues = conn.execute("""
        SELECT
            issues.*,
            books.title AS book_title,
            users.name AS student_name
        FROM issues

        JOIN books
        ON issues.book_id = books.id

        JOIN users
        ON issues.student_id = users.id

        ORDER BY issues.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "librarian.html",
        books=books,
        students=students,
        issues=issues
    )


# =========================================================
# ADD BOOK
# =========================================================

@app.route("/add_book", methods=["POST"])
def add_book():

    if session.get("role") != "librarian":
        return redirect("/")

    title = request.form.get("title")
    author = request.form.get("author")
    category = request.form.get("category")
    quantity = int(request.form.get("quantity"))

    conn = get_db()

    conn.execute("""
        INSERT INTO books
        (title, author, category, quantity, available)
        VALUES (?, ?, ?, ?, ?)
    """, (
        title,
        author,
        category,
        quantity,
        quantity
    ))

    conn.commit()
    conn.close()

    flash("Book added successfully.")

    return redirect("/librarian")


# =========================================================
# ISSUE BOOK
# =========================================================

@app.route("/issue_book", methods=["POST"])
def issue_book():

    if session.get("role") != "librarian":
        return redirect("/")

    student_id = request.form.get("student_id")
    book_id = request.form.get("book_id")

    conn = get_db()

    book = conn.execute("""
        SELECT *
        FROM books
        WHERE id = ?
    """, (book_id,)).fetchone()

    if book is None:

        conn.close()

        flash("Book not found.")

        return redirect("/librarian")

    if book["available"] <= 0:

        conn.close()

        flash("This book is currently not available.")

        return redirect("/librarian")

    # Issue date = today
    issue_date = date.today()

    # Book is due after 20 days
    due_date = issue_date + timedelta(days=20)

    conn.execute("""
        INSERT INTO issues
        (
            student_id,
            book_id,
            issue_date,
            due_date,
            fine,
            paid,
            status
        )
        VALUES (?, ?, ?, ?, 0, 0, 'Issued')
    """, (
        student_id,
        book_id,
        issue_date.isoformat(),
        due_date.isoformat()
    ))

    # Reduce available book count
    conn.execute("""
        UPDATE books
        SET available = available - 1
        WHERE id = ?
    """, (book_id,))

    # Notification
    conn.execute("""
        INSERT INTO notifications
        (student_id, message)
        VALUES (?, ?)
    """, (
        student_id,
        f"Book issued successfully. Please return it by {due_date}."
    ))

    conn.commit()
    conn.close()

    flash("Book issued successfully.")

    return redirect("/librarian")


# =========================================================
# RETURN BOOK
# =========================================================

@app.route("/return_book/<int:issue_id>")
def return_book(issue_id):

    if session.get("role") != "librarian":
        return redirect("/")

    conn = get_db()

    issue = conn.execute("""
        SELECT *
        FROM issues
        WHERE id = ?
    """, (issue_id,)).fetchone()

    if issue is None:

        conn.close()

        flash("Issue record not found.")

        return redirect("/librarian")

    if issue["status"] == "Returned":

        conn.close()

        flash("This book has already been returned.")

        return redirect("/librarian")

    today = date.today()

    due_date = date.fromisoformat(issue["due_date"])

    # Calculate late days
    late_days = (today - due_date).days

    if late_days < 0:
        late_days = 0

    # Calculate fine
    fine = late_days * FINE_PER_DAY

    conn.execute("""
        UPDATE issues

        SET
            return_date = ?,
            fine = ?,
            status = 'Returned'

        WHERE id = ?
    """, (
        today.isoformat(),
        fine,
        issue_id
    ))

    # Increase available books
    conn.execute("""
        UPDATE books

        SET available = available + 1

        WHERE id = ?
    """, (issue["book_id"],))

    # Notification to student
    if fine > 0:

        conn.execute("""
            INSERT INTO notifications
            (student_id, message)
            VALUES (?, ?)
        """, (
            issue["student_id"],
            f"Book returned late. Your fine is ₹{fine}."
        ))

    else:

        conn.execute("""
            INSERT INTO notifications
            (student_id, message)
            VALUES (?, ?)
        """, (
            issue["student_id"],
            "Book returned successfully. No fine is pending."
        ))

    conn.commit()
    conn.close()

    flash(f"Book returned successfully. Fine: ₹{fine}")

    return redirect("/librarian")


# =========================================================
# PAY FINE
# =========================================================

@app.route("/pay_fine/<int:issue_id>", methods=["POST"])
def pay_fine(issue_id):

    if session.get("role") != "librarian":
        return redirect("/")

    amount = float(request.form.get("amount"))

    conn = get_db()

    issue = conn.execute("""
        SELECT *
        FROM issues
        WHERE id = ?
    """, (issue_id,)).fetchone()

    if issue is None:

        conn.close()

        flash("Record not found.")

        return redirect("/librarian")

    fine = float(issue["fine"])
    paid = float(issue["paid"])

    pending = fine - paid

    if amount <= 0:

        conn.close()

        flash("Enter a valid payment amount.")

        return redirect("/librarian")

    if amount > pending:

        conn.close()

        flash(f"Payment cannot be more than pending amount ₹{pending}.")

        return redirect("/librarian")

    new_paid = paid + amount

    conn.execute("""
        UPDATE issues

        SET paid = ?

        WHERE id = ?
    """, (
        new_paid,
        issue_id
    ))

    conn.execute("""
        INSERT INTO notifications
        (student_id, message)
        VALUES (?, ?)
    """, (
        issue["student_id"],
        f"₹{amount} payment recorded. Total paid: ₹{new_paid}."
    ))

    conn.commit()
    conn.close()

    flash("Payment recorded successfully.")

    return redirect("/librarian")


# =========================================================
# STUDENT DASHBOARD
# =========================================================

@app.route("/student")
def student():

    if session.get("role") != "student":
        return redirect("/")

    # Update overdue books
    update_overdue_books()

    student_id = session.get("user_id")

    conn = get_db()

    # Student's issue records
    issues = conn.execute("""
        SELECT
            issues.*,
            books.title AS book_title,
            books.author AS author
        FROM issues

        JOIN books
        ON issues.book_id = books.id

        WHERE issues.student_id = ?

        ORDER BY issues.id DESC
    """, (student_id,)).fetchall()

    # Student notifications
    notifications = conn.execute("""
        SELECT *
        FROM notifications

        WHERE student_id = ?

        ORDER BY id DESC
    """, (student_id,)).fetchall()

    # Calculate totals
    total_fine = sum(float(row["fine"]) for row in issues)

    total_paid = sum(float(row["paid"]) for row in issues)

    total_pending = total_fine - total_paid

    conn.close()

    return render_template(
        "student.html",
        issues=issues,
        notifications=notifications,
        total_fine=total_fine,
        total_paid=total_paid,
        total_pending=total_pending
    )
# =========================================================
# ADD TEST FINE
# =========================================================

@app.route("/test_fine/<int:issue_id>")
def test_fine(issue_id):

    if session.get("role") != "librarian":
        return redirect("/")

    conn = get_db()

    issue = conn.execute("""
        SELECT *
        FROM issues
        WHERE id = ?
    """, (issue_id,)).fetchone()

    if issue is None:
        conn.close()
        flash("Issue record not found.")
        return redirect("/librarian")

    # Add a test fine of ₹50
    conn.execute("""
        UPDATE issues
        SET fine = 50
        WHERE id = ?
    """, (issue_id,))

    # Send notification to student
    conn.execute("""
        INSERT INTO notifications
        (student_id, message)
        VALUES (?, ?)
    """, (
        issue["student_id"],
        "A test fine of ₹50 has been added to your library account."
    ))

    conn.commit()
    conn.close()

    flash("Test fine of ₹50 added successfully.")

    return redirect("/librarian")

# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    init_db()

    app.run(debug=True)