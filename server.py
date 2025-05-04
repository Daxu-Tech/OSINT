import os
import sqlite3
import json
import base64
import datetime
import time
import threading
import logging
import requests
from io import BytesIO
from flask import Flask, request, redirect, url_for, render_template, send_file, abort, session
from werkzeug.utils import secure_filename
import xml.etree.ElementTree as ET

# ------------------ Logging Setup ------------------ #
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ------------------ Flask App Setup ------------------ #
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
app.secret_key = "your_secret_key"  # Replace with your secret key

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'img'}
ALLOWED_DELETE_IPS = {'127.0.0.1', '::1'}

# ------------------ API Username Rotation Setup ------------------ #
# Update this list with your actual API usernames.
API_USERNAMES = ["jibs-opaque-88", "03.dinner-swathe"]
# Set the per-username request limit (adjust as needed)
USERNAME_LIMIT = 10
# Dictionary to maintain usage counts
username_usage = {username: 0 for username in API_USERNAMES}
username_index = 0

def get_next_username():
    """Return a username that has not exceeded USERNAME_LIMIT.
       Rotates through available usernames."""
    global username_index
    attempts = 0
    while attempts < len(API_USERNAMES):
        username = API_USERNAMES[username_index]
        if username_usage[username] < USERNAME_LIMIT:
            username_usage[username] += 1
            username_index = (username_index + 1) % len(API_USERNAMES)
            logger.debug("Using API username: %s (usage: %s/%s)", username, username_usage[username], USERNAME_LIMIT)
            return username
        else:
            username_index = (username_index + 1) % len(API_USERNAMES)
            attempts += 1
    logger.error("All API usernames have exceeded their limits")
    return None

def check_registration(reg_number):
    """Makes a POST request to the registration API using a rotated username."""
    username = get_next_username()
    if not username:
        logger.error("No available API username for registration check")
        return None

    payload = {
        "RegistrationNumber": reg_number,
        "username": username
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    url = "http://www.carregistrationapi.in/api/reg.asmx/CheckIndia"  # Use HTTPS if available

    try:
        response = requests.post(url, data=payload, headers=headers)
        logger.info("Called registration API for %s using username %s, status: %s", reg_number, username, response.status_code)
        if response.status_code == 200:
            logger.debug("API response: %s", response.text)
            return response.text
        else:
            logger.error("API call failed with status %s and content %s", response.status_code, response.text)
            return None
    except Exception as e:
        logger.exception("Exception while calling registration API: %s", e)
        return None

# ------------------ Database Initialization ------------------ #
def init_db():
    """Initializes the uploads table if it does not already exist."""
    with sqlite3.connect("uploads.db") as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filenames TEXT,
                datas TEXT,
                upload_time INTEGER,
                analysis_status TEXT,
                analysis_data TEXT,
                registration_number TEXT
            )
        ''')
    logger.debug("Initialized database and ensured table 'uploads' exists.")

init_db()

def init_registration_db():
    """Creates a separate table to store registration API responses."""
    with sqlite3.connect("uploads.db") as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS registration_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registration_number TEXT,
                details TEXT,
                upload_time INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    logger.debug("Initialized table 'registration_details' for registration API responses.")

init_registration_db()

def migrate_db():
    """Ensures required columns exist in the existing uploads table."""
    with sqlite3.connect("uploads.db") as conn:
        cursor = conn.cursor()
        columns = [col[1] for col in cursor.execute("PRAGMA table_info(uploads)")]
        if "analysis_status" not in columns:
            cursor.execute("ALTER TABLE uploads ADD COLUMN analysis_status TEXT")
            logger.info("Added column 'analysis_status' to 'uploads' table.")
        if "analysis_data" not in columns:
            cursor.execute("ALTER TABLE uploads ADD COLUMN analysis_data TEXT")
            logger.info("Added column 'analysis_data' to 'uploads' table.")
        if "registration_number" not in columns:
            cursor.execute("ALTER TABLE uploads ADD COLUMN registration_number TEXT")
            logger.info("Added column 'registration_number' to 'uploads' table.")
        conn.commit()
    logger.debug("Database migration complete.")

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
    logger.error("File too large: %s", e)
    return "Uploaded file is too large. Maximum allowed size is 16 MB total.", 413

def do_analysis(upload_id):
    """Background analysis function that simulates image analysis."""
    logger.info("Starting background analysis for upload_id: %s", upload_id)
    try:
        time.sleep(5)  # Simulate analysis delay
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
        
        with sqlite3.connect("uploads.db") as conn:
            conn.execute(
                "UPDATE uploads SET analysis_status = ?, analysis_data = ? WHERE id = ?",
                ("complete", analysis_report_json, upload_id)
            )
            conn.commit()
        logger.info("Background analysis completed for upload_id: %s", upload_id)
    except Exception as e:
        logger.exception("Error during background analysis for upload_id %s: %s", upload_id, e)

def process_registration_details(upload_id, reg_number, upload_time):
    """
    Background thread function to process the registration API integration,
    extract key fields, and save details only if they contain valid information.
    If the extracted data is equivalent to no results (empty model, owner, fuel_type,
    and default registration/insurance dates), then do not save it.
    """
    logger.info("Processing registration details for reg_number: %s (upload_id: %s)", reg_number, upload_id)
    
    # Get the next available API username.
    api_username = get_next_username()
    if not api_username:
        logger.error("No available API username for registration check.")
        return

    # Prepare payload and headers.
    payload = {
        "RegistrationNumber": reg_number,
        "username": api_username
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    url = "https://www.carregistrationapi.in/api/reg.asmx/CheckIndia"  # Use HTTPS

    try:
        response = requests.post(url, data=payload, headers=headers)
        logger.info("Called registration API for %s using username %s, status: %s", reg_number, api_username, response.status_code)
        if response.status_code != 200:
            logger.error("Registration API call failed (%s): %s", response.status_code, response.text)
            return

        # Parse the XML response.
        root = ET.fromstring(response.text)
        ns = {'ns': 'http://regcheck.org.uk'}
        vehicle_json_text = root.find('ns:vehicleJson', ns).text

        # Parse the JSON string embedded within the XML.
        vehicle_data = json.loads(vehicle_json_text)

        # Extract key details.
        extracted_details = {
            "model": vehicle_data.get("CarModel", {}).get("CurrentTextValue", ""),
            "owner": vehicle_data.get("Owner", ""),
            "location": vehicle_data.get("Location", ""),
            "variant": vehicle_data.get("Variant", ""),
            "fuel_type": vehicle_data.get("FuelType", {}).get("CurrentTextValue", ""),
            "registration_date": vehicle_data.get("RegistrationDate", ""),
            "insurance_expiry": vehicle_data.get("Insurance", ""),
            "image_url": vehicle_data.get("ImageUrl", "")
        }
        logger.debug("Extracted registration details: %s", json.dumps(extracted_details))
        
        # Check if the response is equivalent to "no valid result"
        if (not extracted_details["model"] and
            not extracted_details["owner"] and
            not extracted_details["fuel_type"]):
            
            logger.info("No additional vehicle details found for registration number: %s", reg_number)
            with sqlite3.connect("uploads.db") as conn:
                # Update the uploads row with a marker (e.g., "N/A") indicating no details were found.
                conn.execute("UPDATE uploads SET registration_number = ? WHERE id = ?", ("N/A", upload_id))
                conn.commit()
            return
        
        # Otherwise, save the extracted details.
        details_json = json.dumps(extracted_details)
        with sqlite3.connect("uploads.db") as conn:
            # Save API response details in registration_details table.
            conn.execute(
                "INSERT INTO registration_details (registration_number, details, upload_time) VALUES (?, ?, ?)",
                (reg_number, details_json, upload_time)
            )
            # Update the uploads table with a valid registration number.
            conn.execute("UPDATE uploads SET registration_number = ? WHERE id = ?", (reg_number, upload_id))
            conn.commit()
        logger.info("Saved registration details for registration number: %s", reg_number)
        
    except Exception as e:
        logger.exception("Error processing registration details for %s: %s", reg_number, e)
        
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        files = request.files.getlist('file')
        logger.debug("Received %s files for upload.", len(files))
        if not files or len(files) == 0:
            logger.warning("No files uploaded.")
            return "No files uploaded", 400

        if len(files) > 10:
            logger.warning("Too many files uploaded: %s files.", len(files))
            return "Error: Maximum 10 images allowed per upload.", 400

        filenames = []
        image_list = []
        for file in files:
            if file and allowed_file(file.filename):
                fname = secure_filename(file.filename)
                filenames.append(fname)
                data = file.read()
                encoded_data = base64.b64encode(data).decode('utf-8')
                image_list.append({"data": encoded_data, "content_type": file.content_type})
                logger.debug("Processed file: %s", fname)
            else:
                logger.error("Invalid file type detected: %s", file.filename)
                return "Invalid file type", 400

        upload_time = int(datetime.datetime.now().timestamp() * 1000)
        joined_filenames = ', '.join(filenames)
        datas_json = json.dumps(image_list)

        with sqlite3.connect("uploads.db") as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO uploads (filenames, datas, upload_time, analysis_status, analysis_data) VALUES (?, ?, ?, ?, ?)",
                (joined_filenames, datas_json, upload_time, "pending", "")
            )
            last_id = cur.lastrowid
            conn.commit()
        logger.info("Inserted new upload with id: %s", last_id)

        session['last_upload_id'] = last_id

        # Start background analysis for the uploaded images
        threading.Thread(target=do_analysis, args=(last_id,), daemon=True).start()
        logger.debug("Started background analysis thread for upload_id: %s", last_id)

        # If a registration number is provided in the form, process the API call in background.
        reg_number = request.form.get("registration_number")
        if reg_number:
            threading.Thread(target=process_registration_details, args=(last_id, reg_number, upload_time), daemon=True).start()
            logger.info("Started registration details processing for registration number: %s", reg_number)

        return redirect(url_for('uploaded'))

    return render_template('frontend.html')

@app.route('/uploaded')
def uploaded():
    last_id = session.get('last_upload_id')
    if last_id is None:
        logger.warning("Access denied to /uploaded; no upload id in session.")
        return "Access Denied", 403

    with sqlite3.connect("uploads.db") as conn:
        row = conn.execute(
            "SELECT id, filenames, datas, upload_time, analysis_status, analysis_data, registration_number FROM uploads WHERE id = ?",
            (last_id,)
        ).fetchone()
    if not row:
        logger.error("Upload not found for id: %s", last_id)
        return "Upload not found", 404

    id_, filenames, datas, upload_time, analysis_status, analysis_data, reg_num = row
    try:
        images = json.loads(datas)
    except Exception as e:
        logger.exception("Error decoding images for upload id: %s: %s", id_, e)
        images = []

    if analysis_status != "complete":
        analysis_report = {
            "pending": True,
            "message": "Your submission is currently undergoing automated analysis. Please allow a moment while we compile your detailed report."
        }
        logger.debug("Analysis pending for upload id: %s", id_)
    else:
        try:
            analysis_report = json.loads(analysis_data)
            logger.info("Analysis complete for upload id: %s", id_)
        except Exception as e:
            logger.exception("Error decoding analysis data for upload id: %s: %s", id_, e)
            analysis_report = {}

    return render_template(
        'uploaded.html',
        upload={"id": id_, "filenames": filenames, "upload_time": upload_time, "images": images, "registration_number": reg_num},
        analysis_report=analysis_report
    )

@app.route('/image/<int:upload_id>/<int:index>')
def get_image(upload_id, index):
    with sqlite3.connect("uploads.db") as conn:
        row = conn.execute("SELECT datas FROM uploads WHERE id=?", (upload_id,)).fetchone()
    if row:
        try:
            images = json.loads(row[0])
        except Exception as e:
            logger.exception("Error decoding image data for upload id: %s: %s", upload_id, e)
            return "Error decoding image data", 500
        if index < 0 or index >= len(images):
            logger.warning("Image index out of range for upload id: %s index: %s", upload_id, index)
            return "Image index out of range", 404
        image_obj = images[index]
        image_data = base64.b64decode(image_obj["data"])
        logger.debug("Serving image index %s for upload id: %s", index, upload_id)
        return send_file(BytesIO(image_data), mimetype=image_obj["content_type"])
    logger.error("Upload not found for image request with id: %s", upload_id)
    return "Upload not found", 404

@app.route('/delete/<int:image_id>', methods=['POST'])
def delete_image(image_id):
    if request.remote_addr not in ALLOWED_DELETE_IPS:
        logger.warning("Unauthorized delete request from: %s", request.remote_addr)
        return abort(403, "Not authorized")
    with sqlite3.connect("uploads.db") as conn:
        conn.execute("DELETE FROM uploads WHERE id=?", (image_id,))
    logger.info("Deleted upload with id: %s", image_id)
    return redirect(url_for('index'))

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
    logger.debug("Rendering index page: page %s of %s", page, total_pages)

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

if __name__ == '__main__':
    logger.info("Starting Flask app...")
    app.run(host="0.0.0.0", port=5000, debug=True)
