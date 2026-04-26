from flask import Flask, jsonify, request
from flask_cors import CORS
import pymysql
import pymysql.cursors
import os
import logging

# ─── App Setup───────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)  # Allow requests from CloudFront / browser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── DB Connection ────────────────────────────────────────────────────────────

def get_db():
    return pymysql.connect(
        host     = os.environ.get('DB_HOST',     'localhost'),
        user     = os.environ.get('DB_USER',     'root'),
        password = os.environ.get('DB_PASSWORD', ''),
        database = os.environ.get('DB_NAME',     'school_db'),
        port     = int(os.environ.get('DB_PORT', 3306)),
        cursorclass = pymysql.cursors.DictCursor,
        connect_timeout = 5
    )

# ─── Create Table on Startup ─────────────────────────────────────────────────

def init_db():
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    id       INT AUTO_INCREMENT PRIMARY KEY,
                    roll_no  VARCHAR(20)  UNIQUE NOT NULL,
                    name     VARCHAR(100) NOT NULL,
                    course   VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        db.commit()
        db.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"DB init failed: {e}")

# ─── Health Check ─────────────────────────────────────────────────────────────

@app.route('/api/health', methods=['GET'])
def health():
    try:
        db = get_db()
        db.ping()
        db.close()
        return jsonify({"status": "ok", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "error", "database": str(e)}), 500

# ─── GET All Students ─────────────────────────────────────────────────────────

@app.route('/api/students', methods=['GET'])
def get_students():
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT id, roll_no, name, course, created_at FROM students ORDER BY created_at DESC")
            students = cur.fetchall()
        db.close()

        # Convert datetime to string for JSON
        for s in students:
            if s.get('created_at'):
                s['created_at'] = s['created_at'].strftime('%Y-%m-%d %H:%M:%S')

        return jsonify(students), 200

    except Exception as e:
        logger.error(f"GET /api/students failed: {e}")
        return jsonify({"error": "Failed to fetch students"}), 500

# ─── GET Single Student by Roll No ───────────────────────────────────────────

@app.route('/api/students/<roll_no>', methods=['GET'])
def get_student(roll_no):
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT id, roll_no, name, course, created_at FROM students WHERE roll_no = %s", (roll_no,))
            student = cur.fetchone()
        db.close()

        if not student:
            return jsonify({"error": "Student not found"}), 404

        if student.get('created_at'):
            student['created_at'] = student['created_at'].strftime('%Y-%m-%d %H:%M:%S')

        return jsonify(student), 200

    except Exception as e:
        logger.error(f"GET /api/students/{roll_no} failed: {e}")
        return jsonify({"error": "Failed to fetch student"}), 500

# ─── POST Add Student ─────────────────────────────────────────────────────────

@app.route('/api/students', methods=['POST'])
def add_student():
    data = request.get_json()

    # Validate
    required = ['roll_no', 'name', 'course']
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    roll_no = data['roll_no'].strip()
    name    = data['name'].strip()
    course  = data['course'].strip()

    if not roll_no or not name or not course:
        return jsonify({"error": "Fields cannot be empty"}), 400

    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO students (roll_no, name, course) VALUES (%s, %s, %s)",
                (roll_no, name, course)
            )
        db.commit()
        db.close()

        logger.info(f"Student added: {roll_no} - {name}")
        return jsonify({"message": "Student added successfully", "roll_no": roll_no}), 201

    except pymysql.err.IntegrityError:
        return jsonify({"error": f"Roll number '{roll_no}' already exists"}), 409

    except Exception as e:
        logger.error(f"POST /api/students failed: {e}")
        return jsonify({"error": "Failed to add student"}), 500

# ─── PUT Update Student ───────────────────────────────────────────────────────

@app.route('/api/students/<roll_no>', methods=['PUT'])
def update_student(roll_no):
    data = request.get_json()

    name   = data.get('name', '').strip()
    course = data.get('course', '').strip()

    if not name and not course:
        return jsonify({"error": "Provide at least name or course to update"}), 400

    try:
        db = get_db()
        with db.cursor() as cur:
            if name and course:
                cur.execute("UPDATE students SET name=%s, course=%s WHERE roll_no=%s", (name, course, roll_no))
            elif name:
                cur.execute("UPDATE students SET name=%s WHERE roll_no=%s", (name, roll_no))
            else:
                cur.execute("UPDATE students SET course=%s WHERE roll_no=%s", (course, roll_no))

            if cur.rowcount == 0:
                db.close()
                return jsonify({"error": "Student not found"}), 404

        db.commit()
        db.close()

        return jsonify({"message": "Student updated successfully"}), 200

    except Exception as e:
        logger.error(f"PUT /api/students/{roll_no} failed: {e}")
        return jsonify({"error": "Failed to update student"}), 500

# ─── DELETE Student ───────────────────────────────────────────────────────────

@app.route('/api/students/<roll_no>', methods=['DELETE'])
def delete_student(roll_no):
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("DELETE FROM students WHERE roll_no = %s", (roll_no,))
            if cur.rowcount == 0:
                db.close()
                return jsonify({"error": "Student not found"}), 404
        db.commit()
        db.close()

        logger.info(f"Student deleted: {roll_no}")
        return jsonify({"message": "Student deleted successfully"}), 200

    except Exception as e:
        logger.error(f"DELETE /api/students/{roll_no} failed: {e}")
        return jsonify({"error": "Failed to delete student"}), 500

# ─── 404 Handler ──────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Route not found"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405

# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)