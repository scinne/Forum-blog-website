from flask import Flask, render_template, request, redirect, session, url_for
from datetime import timedelta
from werkzeug.utils import secure_filename
import sqlite3
import datetime
import os
import uuid

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'pdf', 'txt'}

app = Flask(__name__)
app.permanent_session_lifetime = timedelta(minutes=10)  # Auto logout after 10 minutes
app.secret_key = "1c93b7b1af765ec02f288dbe7f46ec9c491e7ff175e50a8b800afbe5918c4c11"
ADMIN_PASSWORD = "Password123"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8MB max

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_posts():
    with sqlite3.connect("posts.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, content, image_filename, created_at FROM posts ORDER BY created_at DESC")
        rows = c.fetchall()
        return [
            (post_id, title, content.lstrip(), image_filename, created_at)
            for (post_id, title, content, image_filename, created_at) in rows
        ]

def get_post(post_id):
    with sqlite3.connect("posts.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, content, image_filename, created_at FROM posts WHERE id=?", (post_id,))
        return c.fetchone()

@app.route("/")
def homepage():
    posts = get_posts()
    return render_template("index.html", posts=posts)

@app.route("/post/<int:post_id>")
def single_post(post_id):
    post = get_post(post_id)
    if post:
        return render_template("post.html", post=post)
    return "Post not found", 404

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if session.get("admin_authenticated"):
        if request.method == "POST":
            title = request.form["title"]
            content = request.form["content"]
            image = request.files.get("image")
            image_filename = None

            if image and allowed_file(image.filename) and image.filename:
                original_filename = secure_filename(image.filename)
                ext = os.path.splitext(original_filename)[1]
                unique_filename = f"{uuid.uuid4().hex}{ext}"
                image.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                image_filename = unique_filename

            created_at = datetime.datetime.now()
            with sqlite3.connect("posts.db") as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO posts (title, content, image_filename, created_at) VALUES (?, ?, ?, ?)",
                    (title, content, image_filename, created_at)
                )
                post_id = c.lastrowid
                conn.commit()
            return redirect(f"/post/{post_id}")
        return render_template("admin.html")
    
    if request.method == "POST":
        password = request.form.get("password")
        if password == ADMIN_PASSWORD:
            session.permanent = True
            session["admin_authenticated"] = True
            session["just_logged_in"] = True  # Set a flag in the session
            return redirect(url_for("homepage"))
        else:
            error = "Incorrect password."
            return render_template("admin_login.html", error=error)
    return render_template("admin_login.html")


@app.route("/delete/<int:post_id>", methods=["POST"])
def delete_post(post_id):
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin"))
    with sqlite3.connect("posts.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM posts WHERE id=?", (post_id,))
        conn.commit()
    return redirect("/")

@app.route("/logout")
def logout():
    session.pop("admin_authenticated", None)
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
