# Shellshock attempts and IP reputation on Apache

## Problem

The Apache service in the Incus lab is separate from the telemetry application. Shellshock (CVE-2014-6271) is a Bash vulnerability that an HTTP request can reach when an Apache CGI script invokes an affected Bash installation. Wazuh reads the Apache access log after the request reaches the server. A Shellshock alert identifies a suspicious request. Establishing whether a command ran requires separate evidence. [Ubuntu security advisory](https://ubuntu.com/security/CVE-2014-6271)

## Implemented mitigation

The [Apache agent configuration](deploy/wazuh/apache-agent.conf) collects `/var/log/apache2/access.log` in its original format. The combined access log includes the client address and User-Agent. Wazuh uses its built-in web decoder and Shellshock rules.

[Rule 100100](deploy/wazuh/apache-reputation-rules.xml) checks the decoded source IP from the `apache-container` access log against the reputation list. A normal HTTP request from a listed address can trigger this rule. The [manager configuration](deploy/wazuh/apache-reputation-manager.conf) runs `firewall-drop` on the reporting Apache agent and removes the block after 60 seconds. An address absent from the list can still produce a built-in Shellshock alert.

The block limits subsequent traffic from the listed address. A patched Bash addresses the vulnerability. Disable CGI if it is unused.

## Apply in the lab

1. Confirm that the agent is registered as `apache-container`, Apache writes a combined access log at `/var/log/apache2/access.log`, and the firewall sees the client IP recorded in the log. A proxy or shared NAT address can cause the block to affect other clients. Use a dedicated client for the demonstration.
2. From the repository root, generate the source file for the Wazuh CDB list. Set `TEST_CLIENT_IP` to the IPv4 address of the dedicated client as seen by Apache.

   ```bash
   python3 deploy/wazuh/build-apache-reputation-list.py \
     --test-ip "$TEST_CLIENT_IP" > blacklist-alienvault
   ```

   The builder also accepts a reviewed IPv4 ipset as a positional argument before `--test-ip`. The [FireHOL mirror of the AlienVault list](https://iplists.firehol.org/files/alienvault_reputation.ipset) provides a snapshot from November 2021. Use the dedicated client entry for a reproducible lab demonstration. Wazuh compiles the CDB list when the manager starts. [Wazuh CDB lists](https://documentation.wazuh.com/current/user-manual/ruleset/cdb-list.html)
3. On the Wazuh manager, install the generated file at `/var/ossec/etc/lists/blacklist-alienvault` and the rule file in `/var/ossec/etc/rules`. Add the list entry to the existing `<ruleset>` and merge the Active Response block into `/var/ossec/etc/ossec.conf`. Keep the existing `firewall-drop` command definition with timeout allowed. If the Guide 4 rule and response are already installed, replace their definitions for `100100` and keep one list registration. Back up the affected files before merging.
4. On the Apache agent, merge the collector into `/var/ossec/etc/ossec.conf` if the access log is not already collected. On the manager, run `/var/ossec/bin/wazuh-analysisd -t` to check the rules and list. On the agent, run `/var/ossec/bin/wazuh-logcollector -t` to check the collector configuration. Restart `wazuh-manager` and `wazuh-agent` on their respective containers to load the changes. To roll back, restore the backed-up configuration and remove the new rule and list files if they were added for this scenario, then restart the affected services.

## Validation

Use ordinary HTTP requests. Set `APACHE_URL` to the private Apache URL. Run this command from each client to print the response. The timeout keeps the check short while the firewall is dropping packets.

```bash
curl --include --max-time 3 "$APACHE_URL"
```

| Check | Expected result |
| --- | --- |
| First request from the listed client | The page responds. Wazuh raises rule `100100` with the client's IP in `data.srcip`. |
| After the block appears in `/var/ossec/logs/active-responses.log` on the Apache agent | A fresh request from the listed client times out. A request from an unlisted client can still reach Apache. |
| 60 seconds after the block | The removal appears in the Active Response log. A new request from the listed client gets a response and can trigger another block. |
| Shellshock detector in a separate log test | A synthetic Apache log fixture from an unlisted address can match a built-in Shellshock rule independently of rule `100100`. |

Use the timestamped Wazuh alert and the Active Response log to record the source, when the block was added and removed, and the HTTP results from both clients. The table describes the checks to run after applying the configuration.

The project follows the detection and reputation response in SSLE Guide 4, sections 5–7 (pp. 4–8). The custom rule limits the response to Apache access events from the lab agent.

### Kali end-to-end test

On 2026-11-19, the Wazuh 4.14.10 manager loaded the Apache-scoped rule. The existing Apache access-log collector, CDB list registration and 60-second Active Response were reused. A disposable Incus container supplied the listed client address. Kali supplied the unlisted control address.

| Check | Observed result |
| --- | --- |
| First request from the listed client | HTTP 200 and Wazuh alert `100100` from Apache agent `004` at 19:25:28 UTC |
| Next request from the same client | Timed out after four seconds while `iptables` showed source-specific `DROP` rules in `INPUT` and `FORWARD` |
| Request from the unlisted client during the block | HTTP 200 |
| Request from the listed client after automatic removal | HTTP 200. The agent logged `add` at 19:25:28 UTC and `delete` at 19:26:29 UTC. |

The firewall rules were visible for 61 seconds at the test's one-second polling resolution. The Wazuh alert ID was `1795116328.12223289`. The test used ordinary HTTP and exercised the reputation rule and firewall response. Evidence is in `/var/tmp/ssle-apache-reputation.vt57Ju/validation.log` on Kali.

The original list of 609 entries was restored after the test and the disposable client was removed. The Apache-scoped rule remains installed. The pre-deployment Wazuh files are backed up at `/var/backups/ssle-apache-reputation.vt57Ju` inside `wazuh-container`.
