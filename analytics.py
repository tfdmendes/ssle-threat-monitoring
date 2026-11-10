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
       | INSERT
       v
    SQLite DB
  (readings.db)
       |
       | SELECT AVG(temperature)
       v
 Analytics Service
     :5003
       |
       | GET /average
       v
   HTTP Client
"""


from flask import Flask, jsonify
import sqlite3

app = Flask(__name__)

DB = 'readings.db'


@app.route('/average', methods=['GET'])
def average_temp():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("SELECT AVG(temperature) FROM temperatures")

    avg = c.fetchone()[0]

    conn.close()

    return jsonify({
        "average_temperature": round(avg, 2) if avg is not None else None
    })


if __name__ == '__main__':
    app.run(port=5003)
