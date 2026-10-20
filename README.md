# SSLE Threat Monitoring

A starting point for the SSLE project, based on Guide 1. A simulated sensor sends temperature readings to an ingestion service, which forwards them to SQLite storage. An analytics service reads the stored data and provides the average temperature.

The ingestion service registers its address with the service registry at startup. Service destinations are currently configured directly in the Python files.

## Setup

You need Python 3 with `venv` and `pip`. The verification commands also use `curl`.

Run all commands from the repository root. Storage and analytics must run from this same directory because they share the `temp_data.db` file.

Create and activate a virtual environment, then install the dependencies listed in `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

Open a separate terminal for each component. In each terminal, go to the repository root and activate the environment:

```bash
source .venv/bin/activate
```

Start the components in this order, keeping each one running:

| Component | Command | Port |
| --- | --- | --- |
| Service registry | `python registry.py` | 5050 |
| Storage | `python storage.py` | 5002 |
| Ingestion | `python ingestion.py` | 5001 |
| Analytics | `python analytics.py` | 5003 |
| Sensor | `python sensor.py` | None |

The sensor generates temperatures between 20 and 30 degrees Celsius and waits five seconds after each request before sending the next reading. It reports accepted readings and request errors in its terminal.

Storage creates `temp_data.db` and its table if they do not exist.

## Check the result

In another terminal, check that ingestion registered successfully:

```bash
curl http://127.0.0.1:5050/services/ingestion-service
```

After the sensor sends a few readings, query the average:

```bash
curl http://127.0.0.1:5003/average
```

The response contains `average_temperature`, rounded to two decimal places. It includes all stored readings and is `null` when the table is empty.

Press `Ctrl+C` in each terminal to stop the components. Stored readings remain in `temp_data.db` for the next run. The database and virtual environment are excluded from Git.
