# Sensor impersonation at ingestion

## Problem

Before this change, a client that could reach `POST /ingest` could submit a numeric temperature under another sensor's `device_id`. Ingestion validated the input fields and forwarded the declared identity. [Storage](storage.py#L53) could save a fabricated reading under a legitimate sensor's ID and include it in the measurements used to calculate the average.

## Implemented mitigation

1. An administrator on Kali runs [`provision_sensor`](provision_sensor.py) inside the ingestion container. It generates a random API key, stores its SHA-256 hash against the `device_id` in a persistent SQLite database and returns the key once. The administrator delivers the key to the intended Incus sensor with `incus file push`, or installs it as a Kubernetes Secret for the in-cluster sensor.
2. [The sensor](sensor.py) reads the key from a file, verifies the NGINX certificate and sends the key in the `Authorization: Bearer` header over HTTPS. NGINX terminates TLS and forwards `POST /ingest` to the Python service over the Pod's loopback interface.
3. [Ingestion](ingestion.py) hashes the key and looks up an active device before validating and forwarding the reading. It uses the ID from that lookup. A missing, invalid or revoked key returns HTTP 401. A valid key used with a conflicting `device_id` returns HTTP 403. Both are rejected before calling `/store` and produce a credential rejection event for [Wazuh rule 100203](deploy/wazuh/ingestion-rules.xml).

The server binds each key to one device and checks that binding for every request. Changing the ID in the JSON no longer changes the identity attached to a stored reading. Revoking the key takes effect for checks that begin after the revocation is committed. A sensor with valid credentials can still send an inaccurate temperature. A stolen key can be used until it is revoked or rotated.

The Wazuh rules define a threshold of ten credential rejections within 30 seconds from the same IP on the same agent. Rule `100204` triggers the existing `firewall-drop` command on that Node for 60 seconds. The firewall blocks traffic from the source IP, so clients sharing that IP can lose access to the Node during the block.

## Why ingestion keeps sensor credentials

We kept sensor credentials in `devices.db` so ingestion can authenticate each request with a local SQLite lookup. It rejects invalid or revoked keys before contacting Storage and calls `POST /store` once for each accepted reading. Storage continues to own `readings.db`. This choice adds a separate persistent volume for credentials so sensor registrations and revocations survive ingestion Pod replacement. [Kubernetes deployment](README.md#deploy-to-kubernetes)

We could also add a `devices` table to `readings.db` and have Storage own both tables. With separate verification and write operations, ingestion would make two HTTP calls to Storage for each accepted reading, even though the Pods run on the same node. One operation could verify the key and write the reading in a single call. In that design, requests with invalid keys that pass ingestion's initial validation would also reach Storage. We chose the local lookup to keep the authentication decision at ingestion.

The sensor sends the API key itself over HTTPS in every request. Ingestion hashes it with SHA-256 and looks up the result in `devices.db`. Each key is generated from 32 random bytes, so recovering a usable key from a copy of the database by guessing is impractical. [Key generation](provision_sensor.py#L35) · [Key verification](devices.py#L40)

## Validation

Run the regression suite with `python -m unittest discover -s tests -v`. It verifies that authorized readings use the authenticated ID, rejected readings never reach storage, and duplicate registration, rotation and revocation preserve the expected identity bindings.

A local test with NGINX 1.30.6, Flask, Storage and SQLite exercised the HTTPS path with two provisioned keys and the real `sensor.py`. Accepted readings were present under the expected IDs. Missing, invalid, mismatched and revoked credentials left the readings unchanged. The test also verified certificate hostname checking and that the HTTP metrics listener could not reach `/ingest`. The [Kali deployment procedure](README.md#tls-and-sensor-keys-on-kali) uses the repository resource names. The live deployment used the existing `ssle` namespace and its `ssle-*` resource names.

### Kali deployment and end-to-end test

On 2026-11-18 the six application Deployments were unavailable because the local images required by `imagePullPolicy: Never` were missing on the K3s nodes. The existing dependency images and the new ARM64 ingestion and sensor images were imported on both nodes. All six Deployments returned to `1/1`. The live rollout retained the existing Services and Storage claim. After the rollout, the 56,796 rows from before the change were still present and SQLite `quick_check` returned `ok`.

The external `sensor-A` ran as a systemd service in the Incus container `lab-sensor-a` and made HTTPS requests to `ssle-ingestion:30502` on `k3s-node1`. The sensor Pod inside K3s kept the distinct identity `sensor-k8s-001`. Both identities appeared in new SQLite rows.

| Check from the Incus container | Observed result |
| --- | --- |
| Active key with the registered test ID | HTTP 200 and one SQLite row for the test ID |
| Missing key | HTTP 401 and no new SQLite row |
| Unrecognized key | HTTP 401 and no new SQLite row |
| Active key with a different device ID | HTTP 403 and no new SQLite row |
| Key after revocation | HTTP 401 and no new SQLite row |
| TLS hostname mismatch | The client refused the connection |

Wazuh rule `100203` produced four alerts from the test container, one for each rejected request. Direct TCP access to Storage from the sensor Pod was refused. Analytics still reached Storage with HTTP 200 and the ingestion and health scrape targets remained up. After replacing the ingestion Pod, the two sensor registrations and the revoked test registration were still present. Both sensors then wrote new readings without receiving new keys.

The test recorded a single accepted sample for `sensor-auth-check-1795029274` at 23.625 °C. Rollback metadata and test evidence are in `/var/tmp/ssle-sensor-auth.5hJtEi` on Kali.

### Kali Active Response test

On 2026-11-20, a disposable Incus client at `10.255.255.108` sent HTTPS requests to ingestion without an API key. The first nine received HTTP 401 without a block. The tenth, within five seconds of the first, received HTTP 401 and triggered Wazuh rule `100204`. The agent on `k3s-node1` added source-specific `DROP` entries to `INPUT` and `FORWARD`, and the next request timed out.

The agent removed both entries automatically after 61 seconds, and the client received HTTP 401 again. The manager recorded events `651` and `652` for blocking and unblocking. Storage recorded 12 readings from `sensor-A` during the block and zero for the test device ID. The disposable client was removed. The live Active Response test used HTTP 401. The earlier authentication test covers the individual HTTP 403 alert.

The test log is at `/var/tmp/ssle-sensor-auth-response.jWiySg/validation.log` on Kali. The original manager configuration and ingestion rules are backed up at `/var/backups/ssle-sensor-auth-response.Z2Q9hG` inside `wazuh-container`.
