import os
import sqlite3
import base64
import json
import datetime
from io import BytesIO
from flask import Flask, request, redirect, url_for, render_template, send_file, abort
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'img'}
# Whitelisted IP addresses for deletion (update as needed)
ALLOWED_DELETE_IPS = {'127.0.0.1', '::1'}

# Initialize (or upgrade) the database with a new schema
def init_db():
    with sqlite3.connect("uploads.db") as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filenames TEXT,
                datas TEXT, -- JSON encoded list of {"data": <base64>, "content_type": <MIME>}
                upload_time INTEGER
            )
        ''')
init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Define a template filter for formatting the timestamp
@app.template_filter('datetimeformat')
def datetimeformat(value):
    # value is in milliseconds so divide by 1000 before formatting
    return datetime.datetime.fromtimestamp(value/1000).strftime('%Y-%m-%d %H:%M:%S')

# Upload route supports multiple files and groups them in one database record
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        files = request.files.getlist('file')
        if not files or len(files) == 0:
            return "No files uploaded", 400

        filenames = []
        image_list = []
        for file in files:
            if file and allowed_file(file.filename):
                fname = secure_filename(file.filename)
                filenames.append(fname)
                data = file.read()
                encoded_data = base64.b64encode(data).decode('utf-8')
                image_list.append({"data": encoded_data, "content_type": file.content_type})
            else:
                return "Invalid file type", 400

        # Use the same upload timestamp (in milliseconds) for the entire batch
        upload_time = int(datetime.datetime.now().timestamp() * 1000)
        joined_filenames = ', '.join(filenames)
        datas_json = json.dumps(image_list)

        # Insert the entire batch as one row.
        with sqlite3.connect("uploads.db") as conn:
            conn.execute("INSERT INTO uploads (filenames, datas, upload_time) VALUES (?, ?, ?)",
                         (joined_filenames, datas_json, upload_time))
        return redirect(url_for('index'))

    return render_template('frontend.html')

# Main index route: query all upload batches, parse the JSON data,
# and pass a list of dictionaries to the template.
@app.route('/')
def index():
    with sqlite3.connect("uploads.db") as conn:
        rows_raw = conn.execute("SELECT id, filenames, datas, upload_time FROM uploads").fetchall()

    rows = []
    for row in rows_raw:
        id_, filenames, datas, upload_time = row
        try:
            images = json.loads(datas)
        except Exception as e:
            images = []
        rows.append({
            "id": id_,
            "filenames": filenames,
            "upload_time": upload_time,
            "images": images
        })

    allow_delete = request.remote_addr in ALLOWED_DELETE_IPS
    return render_template('index.html', rows=rows, allow_delete=allow_delete)

# New route to serve an individual image from a batch
@app.route('/image/<int:upload_id>/<int:index>')
def get_image(upload_id, index):
    with sqlite3.connect("uploads.db") as conn:
        row = conn.execute("SELECT datas FROM uploads WHERE id=?", (upload_id,)).fetchone()
    if row:
        try:
            images = json.loads(row[0])
        except Exception as e:
            return "Error decoding image data", 500
        if index < 0 or index >= len(images):
            return "Image index out of range", 404
        image_obj = images[index]
        image_data = base64.b64decode(image_obj["data"])
        return send_file(BytesIO(image_data), mimetype=image_obj["content_type"])
    return "Upload not found", 404

# Deletion route: deletes the entire batch – available only to whitelisted IPs.
@app.route('/delete/<int:image_id>', methods=['POST'])
def delete_image(image_id):
    if request.remote_addr not in ALLOWED_DELETE_IPS:
        return abort(403, "Not authorized")
    with sqlite3.connect("uploads.db") as conn:
        conn.execute("DELETE FROM uploads WHERE id=?", (image_id,))
    return redirect(url_for('index'))

def alter_table(db_name, l1):
    with sqlite3.connect(db_name) as conn:
        for i in l1:
            conn.execute(i)

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if value is None:
        return "N/A"
    try:
        # value is in milliseconds so divide by 1000 before formatting
        return datetime.datetime.fromtimestamp(value / 1000).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return "Invalid Date"

if __name__ == '__main__':
    # alter_table("uploads.db", ["ALTER TABLE uploads ADD COLUMN filenames TEXT", "ALTER TABLE uploads ADD COLUMN datas TEXT", "ALTER TABLE uploads ADD COLUMN upload_time INTEGER"])
    app.run(host="0.0.0.0", port=5000, debug=True)
