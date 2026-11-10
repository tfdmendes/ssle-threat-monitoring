""""
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

DB = 'readings.db'


def init_db():
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

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute(
        "INSERT INTO temperatures (device_id, temperature) VALUES (?, ?)",
        (data["device_id"], data["temperature"])
    )

    conn.commit()
    conn.close()

    return jsonify({"status": "stored"}), 200



@app.route("/stats", methods=["GET"])
def get_stats():
    conn = sqlite3.connect(DB)     # Open the database that holds the temperature readings

    try:
        # Count the readings and add their temperatures
        count, total = conn.execute(
            # COALESCE makes it so that the sum is 0 when there's no readings 
            """
            SELECT COUNT(temperature),
                   COALESCE(SUM(temperature), 0)
            FROM temperatures
            """
        ).fetchone()
    finally:
        conn.close()

    # Return the values that analytics needs to calculate the average
    return jsonify({"count": count, "sum": total})



if __name__ == '__main__':
    init_db()
    app.run(port=5002)
