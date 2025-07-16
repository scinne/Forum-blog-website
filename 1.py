import sqlite3
with sqlite3.connect("posts.db") as conn:
    c = conn.cursor()
    c.execute("ALTER TABLE posts ADD COLUMN image_filename TEXT;")
    conn.commit()