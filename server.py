import os
import sqlite3
import json
import base64
import datetime
import time
import threading
from io import BytesIO
from flask import Flask, request, redirect, url_for, render_template, send_file, abort, session
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
app.secret_key = "your_secret_key"  # Replace with your secret key

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'img'}
ALLOWED_DELETE_IPS = {'127.0.0.1', '::1'}

def init_db():
    with sqlite3.connect("uploads.db") as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filenames TEXT,
                datas TEXT,
                upload_time INTEGER
            )
        ''')
init_db()

def migrate_db():
    with sqlite3.connect("uploads.db") as conn:
        cursor = conn.cursor()
        # Check the current columns in the table
        columns = [col[1] for col in cursor.execute("PRAGMA table_info(uploads)")]
        if "analysis_status" not in columns:
            cursor.execute("ALTER TABLE uploads ADD COLUMN analysis_status TEXT")
        if "analysis_data" not in columns:
            cursor.execute("ALTER TABLE uploads ADD COLUMN analysis_data TEXT")
        conn.commit()
migrate_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if value is None:
        return "N/A"
    try:
        return datetime.datetime.fromtimestamp(value / 1000).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return "Invalid Date"

@app.errorhandler(413)
def too_large(e):
    return "Uploaded file is too large. Maximum allowed size is 16 MB total.", 413

def do_analysis(upload_id):
    """
    This background function simulates analysis.
    It waits (to mimic a time-consuming process) and then updates the record for the given upload.
    """
    # Simulate a delay for processing (e.g., 5 seconds)
    time.sleep(5)
    
    # Dummy analysis – replace with actual image analysis if desired.
    analysis_paragraphs = [
       "Analysis Result: Your uploaded images show promising characteristics based on our preliminary automated checks.",
       "Detailed computational analysis confirms that the images meet the necessary criteria for optimal display.",
       "Final Evaluation: Processed successfully; the results are now available for further review."
    ]
    analysis_table = {
       "headers": ["Metric", "Value", "Range", "Unit", "Status"],
       "rows": [
         ["Image Quality", "85", "0-100", "Score", "Good"],
         ["Resolution", "1080p", "720p-4K", "", "Optimal"],
         ["Color Balance", "Balanced", "Unbalanced", "", "Normal"]
       ]
    }
    analysis_report = {
      "paragraphs": analysis_paragraphs,
      "table": analysis_table
    }
    
    analysis_report_json = json.dumps(analysis_report)
    
    # Update the record to indicate that analysis is complete.
    with sqlite3.connect("uploads.db") as conn:
        conn.execute(
            "UPDATE uploads SET analysis_status = ?, analysis_data = ? WHERE id = ?",
            ("complete", analysis_report_json, upload_id)
        )
        conn.commit()

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        files = request.files.getlist('file')
        if not files or len(files) == 0:
            return "No files uploaded", 400

        # Enforce a maximum of 10 images per upload.
        if len(files) > 10:
            return "Error: Maximum 10 images allowed per upload. Please upload 10 or fewer images.", 400

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

        # Set upload timestamp in milliseconds.
        upload_time = int(datetime.datetime.now().timestamp() * 1000)
        joined_filenames = ', '.join(filenames)
        datas_json = json.dumps(image_list)

        # Insert record with analysis_status set to "pending"
        with sqlite3.connect("uploads.db") as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO uploads (filenames, datas, upload_time, analysis_status, analysis_data) VALUES (?, ?, ?, ?, ?)",
                (joined_filenames, datas_json, upload_time, "pending", "")
            )
            last_id = cur.lastrowid
            conn.commit()

        session['last_upload_id'] = last_id

        # Start background analysis
        threading.Thread(target=do_analysis, args=(last_id,), daemon=True).start()

        # Immediately redirect to /uploaded
        return redirect(url_for('uploaded'))

    return render_template('frontend.html')

@app.route('/uploaded')
def uploaded():
    last_id = session.get('last_upload_id')
    if last_id is None:
        return "Access Denied", 403

    with sqlite3.connect("uploads.db") as conn:
        row = conn.execute(
            "SELECT id, filenames, datas, upload_time, analysis_status, analysis_data FROM uploads WHERE id = ?",
            (last_id,)
        ).fetchone()
        
    if not row:
        return "Upload not found", 404

    id_, filenames, datas, upload_time, analysis_status, analysis_data = row
    try:
        images = json.loads(datas)
    except Exception:
        images = []

    # Check if analysis is complete.
    if analysis_status != "complete":
        analysis_report = {
            "pending": True,
            "message": "Analysis is still in progress. Please wait—the page will refresh automatically when complete."
        }
    else:
        try:
            analysis_report = json.loads(analysis_data)
        except Exception:
            analysis_report = {}

    return render_template(
        'uploaded.html',
        upload={"id": id_, "filenames": filenames, "upload_time": upload_time, "images": images},
        analysis_report=analysis_report
    )

@app.route('/')
def index():
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=25, type=int)
    sort_by = request.args.get('sort_by', default='upload_time')
    order = request.args.get('order', default='desc')

    if sort_by not in ['upload_time', 'filenames']:
        sort_by = 'upload_time'
    if order not in ['asc', 'desc']:
        order = 'desc'

    with sqlite3.connect("uploads.db") as conn:
        total_count = conn.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]
        offset = (page - 1) * per_page
        query = f"SELECT id, filenames, datas, upload_time FROM uploads ORDER BY {sort_by} {order} LIMIT ? OFFSET ?"
        rows_raw = conn.execute(query, (per_page, offset)).fetchall()

    rows = []
    for row in rows_raw:
        id_, filenames, datas, upload_time = row
        try:
            images = json.loads(datas)
        except Exception:
            images = []
        rows.append({
            "id": id_,
            "filenames": filenames,
            "upload_time": upload_time,
            "images": images
        })

    allow_delete = request.remote_addr in ALLOWED_DELETE_IPS
    total_pages = (total_count + per_page - 1) // per_page

    return render_template(
        'index.html',
        rows=rows,
        allow_delete=allow_delete,
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
        sort_by=sort_by,
        order=order
    )

@app.route('/image/<int:upload_id>/<int:index>')
def get_image(upload_id, index):
    with sqlite3.connect("uploads.db") as conn:
        row = conn.execute("SELECT datas FROM uploads WHERE id=?", (upload_id,)).fetchone()
    if row:
        try:
            images = json.loads(row[0])
        except Exception:
            return "Error decoding image data", 500
        if index < 0 or index >= len(images):
            return "Image index out of range", 404
        image_obj = images[index]
        image_data = base64.b64decode(image_obj["data"])
        return send_file(BytesIO(image_data), mimetype=image_obj["content_type"])
    return "Upload not found", 404

@app.route('/delete/<int:image_id>', methods=['POST'])
def delete_image(image_id):
    if request.remote_addr not in ALLOWED_DELETE_IPS:
        return abort(403, "Not authorized")
    with sqlite3.connect("uploads.db") as conn:
        conn.execute("DELETE FROM uploads WHERE id=?", (image_id,))
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
