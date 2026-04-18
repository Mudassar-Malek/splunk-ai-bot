# SplunkBot — Use Case Examples

Real-world scenarios showing what to type and what you get back.

---

## Use Case 1: Incident — 5xx Error Spike

**Situation:** PagerDuty fires at 2 AM. Payment API error rate is spiking.

```
You: We're seeing a spike in 5xx errors on the payments API in the last 15 minutes.
     Which hosts are worst affected?

SplunkBot: Running that now...

index=app_logs service=payments-api status>=500 | stats count by host | sort -count

Results — top offenders in last 15 minutes:
  payments-api-pod-7f9d   → 1,842 errors
  payments-api-pod-3c2a   → 1,203 errors
  payments-api-pod-9b1e   →   47 errors  (healthy baseline)

Two pods are responsible for 97% of errors. This pattern suggests a bad deploy
hit 2 of 3 replicas, or those two pods have a specific downstream dependency issue.

Want me to drill into the error messages on those two pods?
```

---

## Use Case 2: Follow-Up Drill-Down (Multi-Turn)

**Continuing from Use Case 1:**

```
You: Yes, show me the top exception classes on payments-api-pod-7f9d

SplunkBot:
index=app_logs host=payments-api-pod-7f9d level=ERROR earliest=-15m
| rex field=_raw "exception_class=(?<exc>[^\s,]+)"
| stats count by exc
| sort -count

Top exceptions on payments-api-pod-7f9d:
  java.sql.SQLTimeoutException          → 1,621 (88%)
  com.zaxxer.hikari.pool.HikariPool$PoolInitializationException → 189 (10%)
  java.net.SocketTimeoutException       →  32  (2%)

This is a database connection issue, not an application bug. The HikariCP
pool initialization exception confirms the pod can't reach the database.
Check whether the DB is up and whether connection pool limits are exhausted.
```

---

## Use Case 3: Latency Investigation

```
You: p99 latency on the checkout service jumped from 200ms to 4s starting around 14:30.
     What changed?

SplunkBot:
index=app_logs service=checkout-service earliest=14:15 latest=15:00
| timechart span=1m p99(response_time_ms) as p99_latency

index=app_logs service=checkout-service earliest=14:25 latest=14:35 level=WARN OR level=ERROR
| stats count by log_message
| sort -count

Latency trend shows a sharp step-change at 14:31 — not a gradual drift,
which rules out load growth. Step-changes at a specific minute almost always
mean a deploy, config change, or downstream service event.

Top warnings at that time:
  "Slow query detected: SELECT * FROM inventory WHERE..." → 847 occurrences
  "Circuit breaker OPEN for inventory-service"           → 203 occurrences

Root cause: inventory-service circuit breaker opened at 14:31, causing
checkout to wait for timeout on every request instead of failing fast.
Check inventory-service health and whether a deploy happened at 14:30-14:31.
```

---

## Use Case 4: Security — Unusual Login Pattern (Fintech)

```
You: Security team flagged unusual login activity. Can you check for accounts
     with more than 10 failed logins in the last hour?

SplunkBot:
index=auth_logs event_type=login_failed earliest=-1h
| stats count by user_id src_ip
| where count > 10
| sort -count

Found 3 accounts with >10 failed logins:

  user_id=u_48291   src_ip=185.220.x.x   → 847 attempts  ← TOR exit node
  user_id=u_77103   src_ip=91.108.x.x    → 312 attempts
  user_id=u_12045   src_ip=185.220.x.x   → 156 attempts  ← same TOR exit node

The first and third accounts share the same source IP (185.220.x.x is a
known TOR exit node). This looks like a credential stuffing attack targeting
specific accounts.

Recommend: block 185.220.x.x at WAF, alert fraud team for u_48291 and u_12045,
and check whether any of these accounts had a successful login interspersed
with the failures.

Want me to check for successful logins from those IPs?
```

---

## Use Case 5: Disk Usage Alert Triage

```
You: Got an alert that /var/log on splunk-indexer-02 is at 94% capacity.
     What's consuming it?

SplunkBot:
index=infra_metrics host=splunk-indexer-02 metric_name=disk_used_percent mount="/var/log"
| timechart span=1h max(value)

index=os_logs host=splunk-indexer-02 sourcetype=syslog earliest=-6h
| rex "(?<file_path>/var/log/[^\s]+)"
| stats count by file_path
| sort -count

Disk has grown from 78% to 94% in the last 6 hours — 16% in 6 hours is abnormal.

Top log files by reference count:
  /var/log/splunkd.log        → referenced 12,847 times (likely verbose logging)
  /var/log/audit/audit.log    → referenced 4,203 times
  /var/log/syslog             → referenced 891 times

splunkd.log growing this fast usually means DEBUG logging is accidentally
enabled in production. Check outputs.conf or run:
  cat /opt/splunk/etc/log.cfg | grep -i debug

Immediate relief: sudo find /var/log -name "*.gz" -mtime +7 -delete
Permanent fix: set log level back to INFO in Splunk log config.
```

---

## Use Case 6: Transaction Volume Anomaly (Fintech)

```
You: Finance team says transaction volume looks low today compared to yesterday.
     Can you compare?

SplunkBot:
index=transactions earliest=-24h latest=now
| timechart span=1h count as today_volume
| appendcols
  [search index=transactions earliest=-48h latest=-24h
   | timechart span=1h count as yesterday_volume]

Hourly comparison (today vs. yesterday):

  09:00  today=14,203  yesterday=14,891  → -4.6%  (normal variance)
  10:00  today=15,441  yesterday=15,209  → +1.5%
  11:00  today= 8,102  yesterday=15,334  → -47%   ← ANOMALY
  12:00  today= 7,891  yesterday=14,902  → -47%   ← ANOMALY

Transaction volume dropped ~47% starting at 11:00. This is not gradual —
another step-change. Check what happened at 10:55-11:05:
- Deploys
- Circuit breaker events
- Payment gateway upstream issues
- Any maintenance windows

Want me to check error rates for the same window to see if the drop is
due to failed transactions or missing transactions?
```

---

## Use Case 7: List Available Indexes Before Querying

```
You: What indexes do we have? I want to know where to look for Kubernetes events.

SplunkBot: Here are your available indexes:

  main, web_logs, app_logs, auth_logs, transactions, infra_metrics,
  k8s_events, k8s_logs, audit_logs, network_flows, os_logs

For Kubernetes events, use index=k8s_events (reason, namespace, pod_name fields)
and index=k8s_logs (raw container stdout/stderr).

Example query to find recent pod evictions:
index=k8s_events reason=Evicted earliest=-1h
| stats count by namespace pod_name message
| sort -count
```

---

## Running the Examples Yourself

```bash
# Start the CLI
python -m src.cli

# Or pipe a question directly (non-interactive)
echo "How many 5xx errors in the last hour by service?" | python -m src.cli
```

All queries above are real SPL that will execute against your Splunk instance.
Time modifiers and index names will be adapted to your environment by the agent
if you tell it what indexes you have.
