"""
Temperature Sensor
       |
       | POST /ingest
       v
 Ingestion Service
     :5001
       |
       | POST /store
       v
  Storage Service
     :5002
       |
       | INSERT INTO temperatures
       v
  SQLite Database
   (readings.db)
   
   
   The Storage Service receives HTTP requests and uses SQLite to store the data
"""




from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)

# Docker uses /data as the working directory, placing readings.db on the volume
DB = 'readings.db'


def init_db():
    # Create missing tables without deleting existing readings
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS temperatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            temperature REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


@app.route('/store', methods=['POST'])
def store():
    data = request.get_json()

    # Give each request its own connection rather than sharing one across threads
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Placeholders keep input values separate from SQL
    c.execute(
        "INSERT INTO temperatures (device_id, temperature) VALUES (?, ?)",
        (data["device_id"], data["temperature"])
    )

    # Commit the write before reporting success to ingestion
    conn.commit()
    conn.close()

    return jsonify({"status": "stored"}), 200



@app.route("/stats", methods=["GET"])
def get_stats():
    conn = sqlite3.connect(DB)

    try:
        # Read count and sum from the same snapshot
        # COALESCE returns zero instead of NULL for an empty table
        count, total = conn.execute(
            """
            SELECT COUNT(temperature),
                   COALESCE(SUM(temperature), 0)
            FROM temperatures
            """
        ).fetchone()
    finally:
        conn.close()

    return jsonify({"count": count, "sum": total})



if __name__ == '__main__':
    init_db()
    app.run(port=5002)
