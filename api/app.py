from flask import Flask, render_template, request, redirect, session, url_for
from datetime import timedelta
from werkzeug.utils import secure_filename
import os
import uuid
import re
import requests
import base64

# Configuration
API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "cgowbIR5Q_UlDfqhVOVlkv93LpRhUudUiy-ammWf").strip()
ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "7db864b79fb0154d888a0af42a713b38").strip()
DATABASE_ID = os.environ.get("CLOUDFLARE_DATABASE_ID", "e27f62ab-2034-4ea6-9499-ec40dacb34a2").strip()

if not API_TOKEN or not ACCOUNT_ID or not DATABASE_ID:
    raise RuntimeError(
        "Missing Cloudflare D1 configuration environment variables."
    )

app = Flask(__name__)
app.permanent_session_lifetime = timedelta(minutes=10)
app.secret_key = "YOUR_SECRET_KEY"  # Replace with a secure secret!
ADMIN_PASSWORD = "Password123"
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'pdf', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def escape_sql(s):
    return s.replace("'", "''") if s else ""

def d1_query(sql, parameters=None):
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"sql": sql}
    if parameters is not None:
        payload["parameters"] = parameters

    print(f"SQL: {sql}")
    print(f"Parameters: {parameters}")
    print(f"URL: {url}")

    resp = requests.post(url, json=payload, headers=headers)

    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")

    resp.raise_for_status()
    data = resp.json()
    if not data.get("success", False):
        raise Exception(f"D1 query failed: {data.get('errors')}")

    results = []
    for block in data.get("result", []):
        results.extend(block.get("results", []))
    return results

def get_posts():
    sql = "SELECT id, title, content, image_base64, image_mimetype, created_at FROM posts ORDER BY created_at DESC"
    try:
        results = d1_query(sql)
        posts = []
        for row in results:
            posts.append((
                row.get('id'),
                row.get('title'),
                re.sub(r'^\s+', '', row.get('content') or ""),
                row.get('image_base64'),
                row.get('image_mimetype'),
                row.get('created_at')
            ))
        return posts
    except Exception as e:
        print("Error fetching posts:", e)
        return []

def get_post(post_id):
    sql = f"SELECT id, title, content, image_base64, image_mimetype, created_at FROM posts WHERE id = {int(post_id)}"
    try:
        results = d1_query(sql)
        if results:
            row = results[0]
            return (
                row.get('id'),
                row.get('title'),
                re.sub(r'^\s+', '', row.get('content') or ""),
                row.get('image_base64'),
                row.get('image_mimetype'),
                row.get('created_at')
            )
    except Exception as e:
        print(f"Error fetching post {post_id}: {e}")
    return None

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
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()

            image = request.files.get("image")
            image_base64 = None
            image_mimetype = None

            if image and allowed_file(image.filename) and image.filename:
                img_data = image.read()
                image_base64 = base64.b64encode(img_data).decode('utf-8')
                image_mimetype = image.mimetype  # E.g. 'image/png'

            # Compose SQL with escaped literals; use new columns
            title_esc = escape_sql(title)
            content_esc = escape_sql(content)
            image_base64_esc = escape_sql(image_base64) if image_base64 else ""
            image_mimetype_esc = escape_sql(image_mimetype) if image_mimetype else ""

            sql = (
                "INSERT INTO posts (title, content, image_base64, image_mimetype, created_at) "
                f"VALUES ('{title_esc}', '{content_esc}', '{image_base64_esc}', '{image_mimetype_esc}', datetime('now'))"
            )
            try:
                d1_query(sql)
                return redirect(url_for("homepage"))
            except Exception as e:
                print(f"Failed to insert post: {e}")
                return render_template("admin.html", error="Failed to add post. Please try again.")
        return render_template("admin.html")

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session.permanent = True
            session["admin_authenticated"] = True
            session["just_logged_in"] = True
            return redirect(url_for("homepage"))
        else:
            return render_template("admin_login.html", error="Incorrect password.")
    return render_template("admin_login.html")

@app.route("/delete/<int:post_id>", methods=["POST"])
def delete_post(post_id):
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin"))
    sql = f"DELETE FROM posts WHERE id = {int(post_id)}"
    try:
        d1_query(sql)
    except Exception as e:
        print(f"Failed to delete post {post_id}: {e}")
    return redirect("/")

@app.route("/logout")
def logout():
    session.pop("admin_authenticated", None)
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
