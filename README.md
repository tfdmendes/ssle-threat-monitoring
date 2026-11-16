# Threat Monitoring

This project combines a temperature-reading application with availability monitoring and security detection. It uses Prometheus and Grafana to show service health, NGINX to limit ingestion traffic, and Wazuh to detect repeated invalid requests and temporarily block their source IP.

The repository contains the application, Dockerfiles, Kubernetes manifests and monitoring configuration. The K3s cluster, Incus containers and monitoring servers are set up separately. Saving a configuration here does not apply it to a running deployment.

## How a reading moves through the application

```mermaid
flowchart LR
    Sensor["Simulated sensor"] -->|"POST /ingest"| Proxy["NGINX in Kubernetes"]
    Proxy -->|"Admitted request"| Ingestion["Ingestion: loopback :5001"]
    Ingestion -->|"POST /store"| Storage["Storage :5002"]
    Storage -->|"Write reading"| DB[("SQLite: readings.db")]
    Client["HTTP client"] -->|"GET /average"| Analytics["Analytics :5003"]
    Analytics -->|"GET /stats"| Storage
    Ingestion -.->|"POST /register at startup"| Registry["Registry :5050"]
```

The sensor generates a temperature between 20 and 30. In Kubernetes, NGINX admits or rejects the request before ingestion checks the reading. Local development runs ingestion directly. Ingestion checks the reading before it reaches storage. Storage owns the database, and analytics asks storage for the count and sum needed to calculate the average.

Registry keeps the latest URL and registration time for each service name. Registering the same name replaces its previous entry. Only ingestion registers automatically. Ingestion uses its configured storage URL directly; registry is not consulted for each reading. Registry entries are held in memory and are lost on restart.

| Component | Source | Role |
| --- | --- | --- |
| Sensor | [sensor.py](sensor.py) | Generates and sends readings |
| NGINX | [ingestion.yaml](deploy/k8s/ingestion.yaml) | Limits POST traffic and separates ingestion from metrics access |
| Ingestion | [ingestion.py](ingestion.py) | Validates readings and forwards accepted data |
| Storage | [storage.py](storage.py) | Saves readings and returns database statistics |
| Analytics | [analytics.py](analytics.py) | Calculates the average from storage statistics |
| Registry | [registry.py](registry.py) | Stores and exposes service registrations |
| Health exporter | [monitoring/health_exporter.py](monitoring/health_exporter.py) | Checks the HTTP services and publishes their latest health results |

A reading has this form:

```json
{
  "device_id": "sensor-001",
  "temperature": 25.5
}
```

Ingestion requires a JSON object, a non-empty device ID and a numeric temperature. It rejects booleans as temperatures. It does not check physical temperature limits or authenticate the sender. Storage relies on these checks rather than repeating them.

```mermaid
sequenceDiagram
    participant S as Sensor or test client
    participant P as NGINX
    participant I as Ingestion
    participant D as Storage
    participant DB as SQLite
    S->>P: POST /ingest
    alt Rate limit exceeded
        P-->>S: HTTP 429, Retry-After: 1
    else Request admitted
        P->>I: POST /ingest with observed client IP
    alt Invalid reading
        I->>I: Log the rejection and source IP
        I-->>P: HTTP 400
        P-->>S: HTTP 400
    else Valid reading
        I->>D: POST /store
        D->>DB: Save and commit the reading
        DB-->>D: Write complete
        D-->>I: HTTP 200
        I-->>P: HTTP 200
        P-->>S: HTTP 200
    end
    end
```

Ingestion reports success only after storage accepts the reading. A storage connection failure or unsuccessful response produces HTTP 502. A timeout produces HTTP 504; this does not prove whether storage saved the reading. There is no queue, automatic retry or duplicate detection.

The sensor waits five seconds after each request finishes and discards failed readings. Analytics also uses a five-second request timeout. It returns HTTP 502 for unavailable or invalid storage results, and HTTP 504 for a timeout. Without readings, storage returns a count and sum of zero, and analytics returns a null average.

## Run the application locally

Use Python with `venv` and `pip`; the Dockerfiles use Python 3.13. From the repository root, create an isolated environment and install [requirements.txt](requirements.txt). Dependency versions are not pinned.

```bash
# Create a local Python environment
python3 -m venv .venv

# Activate it in this terminal
source .venv/bin/activate

# Install the application dependencies in that environment
python -m pip install --requirement requirements.txt
```

Open one terminal per service, from the repository root, and activate the same environment in each. Start registry and storage first, then ingestion and analytics, and finally the sensor.

| Start order | Command | Local address |
| --- | --- | --- |
| 1 | `python registry.py` | `http://127.0.0.1:5050` |
| 2 | `python storage.py` | `http://127.0.0.1:5002` |
| 3 | `python ingestion.py` | `http://127.0.0.1:5001` |
| 4 | `python analytics.py` | `http://127.0.0.1:5003` |
| 5 | `python sensor.py` | Sends requests; does not expose an HTTP server |

Stop each process with Ctrl+C. Storage keeps `readings.db` in its working directory, so readings remain after a restart. Ingestion exits if its initial registration fails; start it again after registry is available. It does not renew its registration automatically.

The default URLs work when all processes run on the same machine. Leave `TRUST_LOCAL_PROXY` unset for these direct local runs. The ingestion Dockerfile enables it only for the loopback-only server behind NGINX. These environment variables change the connections between services; they do not change the addresses on which the HTTP servers listen.

| Process | Variable | Default |
| --- | --- | --- |
| Sensor | `DEVICE_ID` | `sensor-001` |
| Sensor | `INGESTION_URL` | `http://127.0.0.1:5001/ingest` |
| Ingestion | `SERVICE_URL` | `http://127.0.0.1:5001` |
| Ingestion | `REGISTRY_URL` | `http://127.0.0.1:5050` |
| Ingestion and analytics | `STORAGE_URL` | `http://127.0.0.1:5002` |

## HTTP endpoints

| Service | Endpoint | Result |
| --- | --- | --- |
| Ingestion | `POST /ingest` | Validates and stores a reading |
| Ingestion | `GET /metrics` | Returns request metrics for Prometheus |
| Storage | `POST /store` | Saves a reading |
| Storage | `GET /stats` | Returns the reading count and temperature sum |
| Analytics | `GET /average` | Returns the average, or null without readings |
| Registry | `POST /register` | Adds or replaces a registration with the same name |
| Registry | `DELETE /unregister` | Removes a registration without stopping the service; returns 404 if absent |
| Registry | `GET /services` | Lists registrations |
| Registry | `GET /services/<name>` | Returns one registration, or 404 if absent |

## Run in Kubernetes

K3s provides the Kubernetes cluster. A **Node** is a machine that runs application containers. Each component runs in a **Pod**, managed by a **Deployment** that keeps one instance running. A **Service** gives a Pod a stable network address when the Pod is replaced. The `threat-monitoring` namespace groups these resources; it is not a separate machine.

```mermaid
flowchart TB
    subgraph Cluster["K3s: namespace threat-monitoring"]
        Sensor["Sensor Pod"] --> IngestionService["Service: ingestion"]
        IngestionService --> Proxy["NGINX :8080, ingestion Pod"]
        Public["NodePort 30502, Local"] --> Proxy
        Proxy --> Ingestion["Ingestion: loopback :5001, same Pod"]
        Ingestion --> StorageService["Service: storage"]
        Analytics["Analytics Pod"] --> StorageService
        StorageService --> Storage["Storage Pod"]
        Ingestion -.-> RegistryService["Service: registry"]
        RegistryService --> Registry["Registry Pod"]
        Storage --> Volume[("Persistent storage on one Node")]
        Metrics["NodePort 30501"] --> MetricsProxy["NGINX :9090, metrics only"]
        MetricsProxy --> Ingestion
        HealthPort["NodePort 30800"] --> Exporter["Health exporter Pod"]
    end
    Prometheus["External Prometheus"] --> Metrics
    Prometheus --> HealthPort
```

The [Kubernetes manifests](deploy/k8s) define the application. The [Dockerfiles](deploy/docker) define its images. Before applying the manifests:

- Prepare the `threat-monitoring` namespace and the `local-path` storage provider.
- Build the images with the names and tags specified in the manifests. Import each image into every Node where its Pod can run. The `Never` image policy means Kubernetes will not download a missing image.
- Start registry and storage before ingestion, then start the remaining components and monitoring endpoints. All manifests use the `threat-monitoring` namespace.

Build ingestion as `ingestion:nginx-rate-limit`, using [its Dockerfile](deploy/docker/ingestion/Dockerfile) and the repository root as the build context. The build includes `security_logging.py`. Rebuild `health-exporter:nginx-rate-limit` with [its Dockerfile](deploy/docker/health-exporter/Dockerfile), which copies the updated health target file into the image. Import both images and `nginx:1.30.6-alpine` into each eligible Node, matching the Node architecture. Apply the ConfigMap in [ingestion.yaml](deploy/k8s/ingestion.yaml) before starting its Deployment. Apply [monitoring.yaml](deploy/k8s/monitoring.yaml) with the same change.

The manifests do not assign the Pods to particular Nodes. If a Pod reports `ErrImageNeverPull`, check that its image exists on the selected Node. In the deployment inspected on 14 November 2026, only ingestion's image was present on both Nodes; some other components could not start if placed on the other Node.

Storage mounts a persistent volume at `/data`, where it keeps `readings.db`. The volume claim, `storage-data`, requests 1 GiB through `local-path`. The data stays on the Node associated with that volume. Replacing the storage Pod does not erase the database, but deleting the volume can lose the readings. There is no database replication or backup.

Sensor, storage and ingestion stop their old Pod before starting a replacement during an update. Ingestion uses `Recreate` so two independent NGINX rate budgets do not overlap during an update. The other Deployments use rolling updates. Each component still has only one instance, so replacement does not guarantee uninterrupted service. Readiness checks control when a Pod can receive traffic: ingestion checks its loopback `/metrics` endpoint, NGINX checks its monitoring listener, analytics checks an open port, and storage and the health exporter check an HTTP endpoint. Registry has no readiness check. Only the health exporter has a liveness check to trigger a restart after repeated failures.

Prometheus, Grafana and the Wazuh manager run outside these Deployments. Wazuh Agents must be installed separately on the Nodes where ingestion can run; the repository does not deploy them through Kubernetes.

### External access in the deployment

A NodePort makes a Service reachable through a Node's IP and an external port. The target manifests define these entry points:

| Entry point | Target | Allowed application endpoint |
| --- | --- | --- |
| `ingestion:5001` | NGINX port `8080` | `POST /ingest` |
| NodePort `30502` | NGINX port `8080` | `POST /ingest` |
| `ingestion-metrics:5001` and NodePort `30501` | NGINX port `9090` | `GET /metrics` |
| NodePort `30800` | Health exporter | Exporter metrics |

The public ingestion Service uses `externalTrafficPolicy: Local`. External clients must contact the Node hosting the ingestion Pod; traffic through a Node without a local ready Pod is not forwarded. This preserves the source IP observed by NGINX. On 14 November 2026, ingestion was on `k3s-node1` at `10.255.255.11`; verify its current placement before choosing an address. Metrics retain cluster-wide forwarding so Prometheus can keep scraping `10.255.255.10:30501`.

### Ingestion rate limiting and client IP

NGINX and ingestion run in the same Pod and share its network namespace. Ingestion binds only to `127.0.0.1:5001`. Other Pods and external clients cannot reach that listener through the Pod IP, ClusterIP or a NodePort. The ingestion Service now targets NGINX port `8080`, and the monitoring Service targets port `9090`. Both listeners reject unconfigured paths; the metrics listener cannot forward `POST /ingest`, and the public listener does not expose `/metrics`. The monitoring listener also provides `/healthz` for readiness checks.

This restriction does not depend on NetworkPolicy enforcement. Administrative access such as `kubectl exec` or port forwarding is outside this client boundary, as is a compromised container inside the ingestion Pod. Storage remains an internal service with its existing trust model; this change does not authenticate clients or restrict direct access to `/store` from other workloads.

The ConfigMap sets a shared rate of **20 POST requests per second**, with **five excess requests allowed as a burst**, across all clients of the single ingestion Pod. `nodelay` forwards an allowed burst immediately; further excess receives JSON with HTTP `429` and `Retry-After: 1`. This is a rate limit, not a limit on requests in progress. The values are initial lab settings, not measured capacity. One client can consume the shared budget. Adding ingestion replicas would create additional independent budgets and requires a separate design for a cluster-wide limit.

NGINX replaces `X-Forwarded-For` and `X-Real-IP` with its observed peer address instead of trusting headers supplied by the client. In the container, `TRUST_LOCAL_PROXY=1` enables Werkzeug `ProxyFix` for exactly one forwarded address, with trust in all other forwarded fields disabled. This is safe only with the loopback listener and the colocated proxy. Do not expose Flask on `0.0.0.0` with this setting. Ingestion's existing `request.remote_addr` then contains the observed client IP, and the Wazuh JSON event keeps the same `srcip` field and format. External IP preservation assumes a direct connection to the NodePort; a NAT or another proxy in front would need its own verified design.

The containers share a Node, so the Agent that reports the rejection is on the Node accepting the public request. The ingestion decoder, rules and Active Response configuration are unchanged. Separate NGINX collection, decoding and alert rules report rate-limit rejections without an Active Response. Requests rejected by NGINX with `429` never reach ingestion validation and do not produce its `400` rejection events. Test repeated invalid readings below the rate limit when validating Wazuh correlation.

NGINX writes JSON access records to the `nginx` container output, including `srcip`, status, duration, upstream status and `limit_status`. The Wazuh Agents collect these container logs, and rules `100211` and `100212` make rate-limit rejections available as alerts. Other NGINX access events are classified without a separate alert. Use these records to distinguish `429` rejections from requests admitted to ingestion. Existing ingestion Prometheus metrics count only requests that reach Flask; they do not count proxy rejections. Health checks use `http://ingestion-metrics:5001/metrics` and remain outside the POST rate budget.

### Installation and validation boundary

On 15 November 2026, the proxy was deployed in the existing `ssle` namespace. The running images are `ssle-ingestion:nginx-c89c0d601e8e`, `ssle-health-exporter:nginx-c89c0d601e8e` and `nginx:1.30.6-alpine`. The deployment keeps the existing `ssle-*` Service names, `ssle_ingestion_*` Prometheus metrics and Wazuh collection path. Ingestion is assigned to `k3s-node1` to keep the public entry point at `http://10.255.255.11:30502/ingest`. The existing `ssle-ingestion` Service supplies NodePort `30502`; no second public Service was created. Storage, its Pod and its volume were preserved. Previous resource specifications and the deployed configuration are saved on Kali under `/var/tmp/ssle-nginx-20261115` for rollback.

The live check sent 40 valid POST requests with concurrency 2: eight returned `200` and 32 returned `429`. A later request succeeded. Direct backend access through the Pod IP failed, and the monitoring listener rejected ingestion requests. Wazuh rule `100201` recorded the actual Kali client IP, `10.255.255.1`, despite forged forwarding headers. All four health checks were healthy and both application Prometheus targets were UP. The ten readings created for this check were removed using their exclusive device IDs. Timed Wazuh blocking and recovery were not repeated during this deployment. These counts describe this run, not a fixed result for every burst.

The repository manifests still use the target names for a future namespace rename. Before another installation, inspect all Services selecting ingestion and map the configuration to the chosen namespace without creating a new database or discarding the existing volume. Reuse the existing NodePort `30502` Service; two Services cannot claim the same NodePort. Keep the metrics Service on the NGINX metrics listener and preserve the existing firewall restriction on port `30501`.

The ConfigMap is mounted using `subPath`; editing it requires restarting the ingestion Deployment to load the new configuration. The single Pod's `Recreate` strategy causes a brief interruption. Restore the previous image, manifests and health target file together to roll back; retain the database volume. Rolling back to the old direct listener removes the proxy protection.

Before calling the deployment verified, check the following in the isolated lab:

- A valid external reading reaches storage through NGINX, and metrics still scrape successfully
- An invalid reading with forged forwarding headers records the actual test client IP in ingestion logs and in a decoded Wazuh alert
- The same bounded workload from Guide 5 produces the expected admitted and rejected requests, with no automatic resubmission of POST requests
- Direct connections to the Pod IP on `5001` fail, and neither `/metrics` on the public listener nor `/ingest` on the monitoring listener reaches Flask
- Wazuh still correlates invalid readings below the rate limit, and its timed block and recovery work on the public entry point

### Naming changes and the running deployment

The resource, image, metric and dashboard names in this checkout are the target names for the next deployment. The running environment has not been renamed.

Deploy these changes together: rebuild and import the application images, update the Wazuh and monitoring configuration, and plan the database migration before switching to the new namespace. A new namespace and volume claim create new resources; they do not transfer readings from the existing volume. Keep the existing data until that migration is complete.

## Availability monitoring

The health exporter checks registry, ingestion, storage and analytics over HTTP. It publishes the latest result as `service_health`: 1 for an HTTP 2xx response, or 0 for an HTTP error or connection failure. It checks services in sequence, with a two-second timeout per request and a five-second wait between cycles.

```mermaid
flowchart LR
    Services["Registry, ingestion, storage and analytics"]
    Exporter["Health exporter"] -->|"HTTP checks"| Services
    Prometheus["Prometheus"] -->|"Read health results: port 30800"| Exporter
    Prometheus -->|"Read request metrics: port 30501"| Ingestion["Ingestion"]
    Grafana["Grafana"] -->|"Query metrics"| Prometheus
    Prometheus --> Alerts["Availability alerts"]
```

The [target list](monitoring/health_targets.json) uses Kubernetes Service names. To run the exporter elsewhere, provide a target file with URLs reachable from that machine. A successful health check proves that the selected endpoint responded, not that the full reading flow works.

[Prometheus configuration](monitoring/prometheus/prometheus.yml) collects application and resource metrics every 15 seconds. It also monitors itself and a Node Exporter at `localhost:9100`. That Node Exporter describes the container running Prometheus; its root filesystem is shared with the K3s Nodes in this lab. The `incus-nodes` and `kubelet-cadvisor` jobs provide the separate Node and Pod/container measurements described below.

Ingestion's [instrumentation](instrumentation.py) publishes:

| Metric | Meaning |
| --- | --- |
| `ingestion_requests_total` | Number of ingestion responses, separated by HTTP status |
| `ingestion_request_duration_seconds` | Request duration, including the wait for storage |

These measurements reset when ingestion restarts. Requests to `/metrics` do not count as ingestion requests.

The [availability rules](monitoring/prometheus/rules/availability.yml) distinguish four conditions:

| Alert | Condition |
| --- | --- |
| `ServiceDown` | A service health result stays at 0 for 15 seconds |
| `MetricsUnavailable` | Prometheus cannot collect ingestion or health exporter metrics, or either target is missing, for one minute |
| `HealthCheckMissing` | The exporter responds but an expected service health result is missing for one minute |
| `ReadingsStopped` | Successful ingestion requests show no increase over a rolling one-minute window, and that condition persists for two minutes while ingestion metrics remain reachable |

Collection and rule-evaluation intervals affect when an alert appears. No external alert destination is configured, so these rules do not send email or other notifications.

The [Grafana dashboard](monitoring/grafana/dashboards/overview.json) shows service health, request rates, request durations, server-error rates and alert history. Its [data source](monitoring/grafana/provisioning/datasources/prometheus.yaml) points to Prometheus at `http://10.255.255.42:9090`. The [dashboard provider](monitoring/grafana/provisioning/dashboards/dashboards.yaml) loads the dashboard from a file; edits cannot be saved through the Grafana UI. Install these files on the Grafana server separately and adapt the addresses to the deployment. The [Grafana service settings](monitoring/grafana/grafana.conf) select the starting dashboard.

### Node and Pod resource monitoring

The resource dashboards use two sources. Incus attributes CPU, memory, disk I/O and network traffic to each K3s Node instance. The kubelet's `/metrics/cadvisor` endpoint exposes CPU usage, effective CFS quotas and memory working sets for Pod and container cgroups. These jobs do not change workload requests or limits.

| Dashboard | Measurements and filters |
| --- | --- |
| [Node Resources](monitoring/grafana/dashboards/nodes.json) | CPU in cores, estimated RAM usage, disk read/write rates and external network traffic, filtered by Node; shared CPU/RAM capacity and root filesystem space |
| [Pod and Container Resources](monitoring/grafana/dashboards/pods.json) | CPU in cores, quota, usage relative to quota, throttled periods, throttled time and RAM working set; filter by Node, namespace, Pod and scope |

The `Scope` selector chooses either the Pod cgroup or the application container cgroups. The scrape configuration adds a `scope` label and excludes sandbox containers. Pod and container measurements are not added together because they represent different levels of the same hierarchy.

Resource legends show `service · Node`. Dashboard queries derive the short service name from Deployment-style Pod names, omitting the optional `ssle-` prefix and generated suffixes. Other Pod names remain unchanged. The full Pod name remains in the `Pod` selector, the query result labels and the `Pod details` table, together with its Node, container and namespace. Short legends do not aggregate replicas or change stored metrics.

CPU quota is the cgroup quota divided by its enforcement period, expressed in cores. The dashboard displays `No CPU limit` when cAdvisor reports a period without a quota. A missing scrape remains `No data`. Quota utilisation and throttling panels only show cgroups that expose quota metrics. The throttled-period fraction is not the fraction of CPU time lost.

The RAM panel reads `container_memory_working_set_bytes` as a gauge and displays it in binary memory units. It estimates memory in use and can include cached memory; it is not a configured request or limit. This is the working-set measure also used by the [Kubernetes Metrics API](https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/#memory). Pod scope reads the Pod cgroup, including its overhead, while container scope shows each application container. Values can differ slightly from `kubectl top` because the collection times and cgroup scopes differ. The panel follows the same filters as CPU and does not add the two scopes together.

RAM usage is estimated as the total minus the available memory reported by Incus. Disk I/O is attributed to each instance and does not include reads served from cache. Network panels select `eth0`; summing loopback, bridges and Pod interfaces would count some traffic more than once.

Both Nodes run inside the same Kali VM. On 15 November 2026, each Node advertised access to the same two CPUs and approximately 7.64 GiB of RAM, without separate Incus CPU or memory limits. Do not add their advertised capacities to calculate physical capacity. Both Nodes also use the same backing filesystem. Root filesystem space is therefore shown once, through the existing Node Exporter, and does not change with the Node filter.

The deployment checked on that date had no CPU or memory requests or limits for ingestion, storage, analytics, registry or sensor. The health exporter had a CPU request of `10m`, a CPU limit of `100m`, a memory request of `32Mi` and a memory limit of `128Mi`. The monitoring setup preserved these values and did not restart the application Pods.

#### Access and installation

The `incus-nodes` job connects to `https://10.255.255.1:8444/1.0/metrics`, using the metrics-only Incus listener on the private bridge. It keeps metrics for `k3s-master` and `k3s-node1` and copies the instance name into the `node` label. Configure a client certificate of type `metrics`, following the [Incus metrics setup](https://linuxcontainers.org/incus/docs/main/metrics/). The Prometheus TLS files are:

| File on the Prometheus container | Purpose |
| --- | --- |
| `/etc/prometheus/tls/incus/server.crt` | Trusted Incus server certificate; `server_name: kali` verifies its DNS identity |
| `/etc/prometheus/tls/incus/metrics.crt` | Metrics-only client certificate |
| `/etc/prometheus/tls/incus/metrics.key` | Private client key |

The installed client certificate is valid for one year from 15 November 2026. Renew the certificate and its Incus trust entry before expiry. Keep TLS verification and client authentication enabled.

Apply [kubelet-metrics-access.yaml](deploy/k8s/kubelet-metrics-access.yaml) to create the `prometheus-kubelet` ServiceAccount in `kube-system`, its token Secret and an RBAC grant limited to `get` on `nodes/metrics`. The external Prometheus reads the Secret's decoded token from `/etc/prometheus/kubelet/token`. It trusts the kubelet serving CA through `/etc/prometheus/kubelet/ca.crt`, copied from the K3s `server-ca.crt`. Requests go directly to each Node on port `10250` with TLS validation enabled. This manually created token persists until revoked; replace the token Secret and the Prometheus token file to rotate it.

Keep keys and tokens outside the repository. The installed files are owned by `root:prometheus` with mode `0640`, inside directories with mode `0750`.

Before applying a Prometheus change, save its active configuration, install the credentials, add the two resource jobs and run `promtool check config` against the resulting file. Reload Prometheus only after that check succeeds. Verify that the Incus target and both kubelet targets report `UP`. Copy both dashboard JSON files into the Grafana provider directory; the provider reads updates every 30 seconds.

The existing live deployment uses datasource UID `ssle-prometheus`, while the repository's target provisioning uses UID `prometheus`. Match dashboard datasource references, including variable queries, to the installed datasource. Resource monitoring can be installed without renaming the existing application jobs, namespace or dashboard folder. The live installation remains in folder `SSLE` with application namespace `ssle`.

To remove this monitoring, remove the two resource scrape jobs and reload Prometheus, then remove the two resource dashboard files. Remove the dedicated kubelet access resources and Incus metrics trust entry when no longer used. Restore the previous Incus metrics listener value if this installation was its only user. These steps do not require changing application limits or deleting stored readings.

## Security detection and IP blocking

Ingestion logs each rejected reading with its source IP, HTTP status and rejection reason. The reasons are `invalid_json_object`, `invalid_device_id` and `invalid_temperature`. Request bodies and client headers are not included.

An **Agent** is the Wazuh program installed on each monitored Node. It reads the local container logs and sends events to the **manager**, which analyses them. The **decoder** reads the log format and extracts fields such as `srcip`, `status` and `reason`. The rules then evaluate those fields.

```mermaid
flowchart TD
    Request["Invalid POST /ingest"] --> Ingestion["Ingestion: reject with HTTP 400"]
    Ingestion --> Log["Log the source IP and rejection reason"]
    Log --> Agent["Wazuh Agent on the Node"]
    Agent --> Decoder["Manager: extract fields from the log"]
    Decoder --> Single["Rule 100201: one rejection"]
    Single --> Repeated["Rule 100202: 10 rejections from one IP in 30 seconds"]
    Single --> Alerts["Store alert"]
    Repeated --> Alerts
    Repeated --> Response["Active Response: firewall-drop"]
    Response --> Firewall["Agent blocks the source IP on its Node"]
    Firewall --> Recovery["Remove the block after 60 seconds"]
    Alerts --> Filebeat["Filebeat forwards alerts"]
    Filebeat --> Indexer["Wazuh indexer stores alerts"]
    Indexer --> Dashboard["Wazuh dashboard displays alerts"]
```

| Rule | Level | Purpose |
| --- | --- | --- |
| `100200` | 0 | Identifies ingestion events without creating a separate alert |
| `100201` | 3 | Identifies one rejected `POST /ingest` with HTTP 400 |
| `100202` | 10 | Detects ten rejection events from the same IP and Agent within 30 seconds |
| `100210` | 0 | Identifies NGINX ingestion access events without a separate alert |
| `100211` | 3 | Reports a rejected `POST /ingest` with status `429` and `limit_status=REJECTED` |
| `100212` | 7 | Reports 20 rate-limit rejections within 30 seconds on the same Agent, across all client IPs |

A rule's level represents alert severity. The count of ten comes from the frequency setting, not from level 10.

The **Active Response** configuration links rule `100202` to `firewall-drop`. When that rule fires, the manager tells the reporting Agent to block the source IP on its Node for 60 seconds. The block affects traffic from that IP, including valid requests. Removing the block does not delete the recorded alerts.

### NGINX rate-limit alerts

The [NGINX Agent fragment](deploy/wazuh/nginx-agent.conf) collects `/var/log/containers/ingestion-*_threat-monitoring_nginx-*.log` on each eligible Node. It uses the prefix `nginx-ingestion:` so the [dedicated decoder](deploy/wazuh/nginx-decoder.xml) can skip the CRI timestamp and stdout header before decoding the JSON. Records from stderr do not match this decoder. The [rules](deploy/wazuh/nginx-rules.xml) require the proxy event name, `POST /ingest`, HTTP `429` and `limit_status=REJECTED` before creating an alert.

Rule `100211` has level 3, matching the manager's current minimum alert level. Rule `100212` raises the event to level 7 at 20 qualifying rejections within 30 seconds. The event that triggers correlation is stored at level 7 instead of producing a second copy at level 3. Accepted requests and unrelated responses do not produce these rate-limit alerts. Full event archiving is not enabled by this integration.

The count includes different client IPs on one Agent because the NGINX request budget is also shared. A higher-level alert describes pressure on the service, not an accusation against its last `srcip`. The 20-event threshold and 30-second window are initial lab settings. A short burst can reach this count; the rule does not require load to last the entire window, and it does not establish a malicious DoS.

Neither rule is linked to an Active Response. Existing IP blocking for rule `100202` remains separate and applies to repeated invalid readings, not to these proxy rejections. No manager-wide alert threshold or archive setting needs to change.

In the Wazuh dashboard's alert search, select the relevant time range and use `rule.groups: nginx_rate_limit` for both alert levels, or `rule.id: 100212` for the higher-level alerts. Useful event fields are `data.srcip`, `data.status`, `data.limit_status`, `data.path` and `agent.name`.

The deployed namespace remains `ssle`. Its Agent collection path is `/var/log/containers/ssle-ingestion-*_ssle_nginx-*.log`; the decoder prefix and the rule IDs are the same as in this checkout. New files are installed as `/var/ossec/etc/decoders/nginx_ingestion.xml` and `/var/ossec/etc/rules/nginx_ingestion.xml`. Validate with `wazuh-analysisd -t` on the manager and `wazuh-logcollector -t` on the Agents before restarting the affected Wazuh services. This does not require restarting NGINX or the application Pods.

On 16 November 2026, these rules and the NGINX collectors were installed on the live manager and both K3s Agents. A bounded check of 40 valid POST requests with concurrency 2 returned eight `200` responses and 32 `429` responses. The indexer contained 31 alerts for rule `100211` at level 3 and one for rule `100212` at level 7, all with the real client IP `10.255.255.1`. The same client received `200` after correlation. The manager's Active Response configuration was unchanged, and no new-rule action appeared in the Agent's Active Response log. All four application health checks passed. The ten readings created by the check were removed using their exclusive device IDs. Original Wazuh configurations are saved on Kali under `/var/tmp/ssle-nginx-wazuh-20261116/rollback`.

To disable this integration, remove its `localfile` block from each Agent and its decoder and rules files from the manager, validate the remaining configuration and restart the affected Wazuh services. Preserve other collection blocks, rules and Active Responses.

### Configuration files

| File | Where it is used |
| --- | --- |
| [ingestion-agent.conf](deploy/wazuh/ingestion-agent.conf) | Add its log-collection block to the Agent's `/var/ossec/etc/ossec.conf` on each eligible Node |
| [ingestion-decoder.xml](deploy/wazuh/ingestion-decoder.xml) | Install as `/var/ossec/etc/decoders/ingestion.xml` on the manager |
| [ingestion-rules.xml](deploy/wazuh/ingestion-rules.xml) | Install as `/var/ossec/etc/rules/ingestion.xml` on the manager |
| [ingestion-active-response.conf](deploy/wazuh/ingestion-active-response.conf) | Add its `active-response` block to the manager's `/var/ossec/etc/ossec.conf` |
| [nginx-agent.conf](deploy/wazuh/nginx-agent.conf) | Add its log-collection block to each eligible Agent's `ossec.conf` |
| [nginx-decoder.xml](deploy/wazuh/nginx-decoder.xml) | Install as `/var/ossec/etc/decoders/nginx_ingestion.xml` on the manager |
| [nginx-rules.xml](deploy/wazuh/nginx-rules.xml) | Install as `/var/ossec/etc/rules/nginx_ingestion.xml` on the manager |

The Agent configuration reads `/var/log/containers/ingestion-*_threat-monitoring_ingestion-*.log`. The decoder skips the container log header before reading the JSON event.

The two `.conf` files contain fragments for `ossec.conf`, not replacements for the full file. Add their child blocks inside an existing `ossec_config` section without nesting another section or duplicating an existing response for `100202`. Install the decoder and rules as separate files in the directories shown above.

The manager needs the standard `firewall-drop` command definition with `timeout_allowed=yes`, and the Agents need its executable. Restart the affected Wazuh services after installation to load the changes. To disable this response later, disable or remove its block and restart the manager.

Kubernetes does not install or load these Wazuh settings. The repository files must be installed on the manager and Agents separately.
