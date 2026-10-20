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
   (temp_data.db)
   
   
   The Storage Service receives HTTP requests and uses SQLite to store the data
"""




from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)

DB = 'temp_data.db'


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


if __name__ == '__main__':
    init_db()
    app.run(port=5002)