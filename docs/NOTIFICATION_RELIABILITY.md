# Notification reliability deployment notes

## Active-alert migration preflight

Before applying `0006_notification_reliability`, run this read-only query against the target database:

```sql
SELECT atm_id, alert_type, severity, COUNT(*) AS duplicate_count
FROM alerts
WHERE status IN ('OPEN', 'ACKNOWLEDGED')
GROUP BY atm_id, alert_type, severity
HAVING COUNT(*) > 1;
```

The migration refuses to create the active-alert uniqueness index when this query returns any rows. Resolve those duplicates according to the application's alert lifecycle before retrying the migration. The migration does not delete or merge alert records.

## Pre-migration notification jobs

Existing notification deliveries retain their records, but deliveries created before the idempotency implementation have no event key. Existing background jobs may also lack an `event_key` in their payload. Those legacy jobs cannot be deterministically matched to the new per-recipient idempotency records and can cause a one-time duplicate delivery if they are still processed during the rollout. New alert and replenishment events use durable event keys and claim fencing.
