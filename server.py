import os
import sqlite3
from flask import Flask, request, redirect, url_for, render_template, send_file
from werkzeug.utils import secure_filename
from io import BytesIO

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'img'}

# Initialize database
def init_db():
    with sqlite3.connect("uploads.db") as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                content_type TEXT,
                data BLOB
            )
        ''')
init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Serve upload page from separate HTML file
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            data = file.read()
            content_type = file.content_type

            with sqlite3.connect("uploads.db") as conn:
                conn.execute("INSERT INTO uploads (filename, content_type, data) VALUES (?, ?, ?)",
                             (filename, content_type, data))

            return redirect(url_for('index'))
        else:
            return "Invalid file type", 400

    return render_template('frontend.html')

@app.route('/')
def index():
    with sqlite3.connect("uploads.db") as conn:
        rows = conn.execute("SELECT id, filename FROM uploads").fetchall()

    return render_template('index.html', rows=rows)

@app.route('/image/<int:image_id>')
def get_image(image_id):
    with sqlite3.connect("uploads.db") as conn:
        row = conn.execute("SELECT content_type, data FROM uploads WHERE id=?", (image_id,)).fetchone()
        if row:
            return send_file(BytesIO(row[1]), mimetype=row[0])
    return "Image not found", 404

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
