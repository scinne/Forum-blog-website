from flask import Flask, render_template, request, redirect, session, url_for
from datetime import timedelta
from werkzeug.utils import secure_filename
import datetime
import os
import uuid
import re
import requests

# Replace with your actual environment variable name or set securely in your environment
API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")
ACCOUNT_ID = "7db864b79fb0154d888a0af42a713b38"
DATABASE_ID = "e27f62ab-2034-4ea6-9499-ec40dacb34a2"

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'pdf', 'txt'}

app = Flask(__name__)
app.permanent_session_lifetime = timedelta(minutes=10)  # Auto logout after 10 minutes
app.secret_key = "1c93b7b1af765ec02f288dbe7f46ec9c491e7ff175e50a8b800afbe5918c4c11"
ADMIN_PASSWORD = "Password123"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8MB max

# Create upload folder locally only (Vercel is read-only except /tmp)
if not os.environ.get('VERCEL'):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def d1_query(sql, parameters=None):
    """Send a SQL query to Cloudflare D1 and return results."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"sql": sql}
    if parameters:
        payload["parameters"] = parameters

    resp = requests.post(url, json=payload, headers=headers)
    resp.raise_for_status()

    data = resp.json() 
    if not data.get("success", False):
        raise Exception(f"D1 query failed: {data.get('errors')}")

    results = []

    for result_block in data.get("result", []):
        results.extend(result_block.get("results", []))
    return results


def get_posts():
    sql = "SELECT id, title, content, image_filename, created_at FROM posts ORDER BY created_at DESC"
    results = d1_query(sql)
    # Clean leading whitespace in content
    posts = []
    for row in results:
        posts.append((
            row['id'],
            row['title'],
            re.sub(r'^\s+', '', row['content'] or ""),
            row['image_filename'],
            row['created_at']
        ))
    return posts

def get_post(post_id):
    sql = "SELECT id, title, content, image_filename, created_at FROM posts WHERE id = ?"
    params = [post_id]
    results = d1_query(sql, params)
    if results:
        row = results[0]
        return (
            row['id'],
            row['title'],
            re.sub(r'^\s+', '', row['content'] or ""),
            row['image_filename'],
            row['created_at']
        )
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
            title = request.form["title"]
            content = request.form["content"]
            image = request.files.get("image")
            image_filename = None

            # Save upload locally only if allowed and not on Vercel serverless
            if image and allowed_file(image.filename) and image.filename:
                original_filename = secure_filename(image.filename)
                ext = os.path.splitext(original_filename)[1]
                unique_filename = f"{uuid.uuid4().hex}{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

                # Only save file locally if not on Vercel because filesystem is read-only
                if not os.environ.get('VERCEL'):
                    image.save(save_path)
                    image_filename = unique_filename
                else:
                    # On Vercel, you need an external file storage solution
                    image_filename = None  # Optionally handle external upload API here

            created_at = datetime.datetime.now().isoformat()
            sql = (
                "INSERT INTO posts (title, content, image_filename, created_at) VALUES (?, ?, ?, ?)"
            )
            params = [title, content, image_filename, created_at]
            d1_query(sql, params)
            # Get last inserted id is not straightforward via API; consider alternative design
            # Instead redirect to homepage or another page
            return redirect(url_for("homepage"))
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
    sql = "DELETE FROM posts WHERE id = ?"
    params = [post_id]
    d1_query(sql, params)
    return redirect("/")

@app.route("/logout")
def logout():
    session.pop("admin_authenticated", None)
    return redirect("/")

if __name__ == "__main__":
    app.run()
