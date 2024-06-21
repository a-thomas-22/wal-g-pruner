# wal-g-pruner
---

wal-g-pruner is a sidecar for cleaning up walg backups saved to s3 compatible storage. It plays nice with the [Zalando Spilo](https://github.com/zalando/spilo) container especially and is configured by default to run within a Kubernetes environment as a sidecar container of Spilo (see [Features and limitations](#features-and-limitations)).

## Features and limitations
---

As mentioned above, wal-g-pruner plays well along Spilo. This includes also Patroni cluster configurations with Spilo. wal-g-pruner will check that it is running on the primary instance of the cluster and ensure that the cluster is not in recovery mode before it starts to prune the backups.

wal-g-pruner relies on having all needed WAL-G environment variables within an envdir under `/run/etc/wal-e.d/env`. This is the default behavior of the Spilo image when you set the WAL-G environment variables (e.g. `AWS_ACCESS_KEY_ID`, `AWS_ENDPOINT`...). 

## Configuration
---

The following environment variables can be used to configure wal-g-pruner.

| Variable name   | Description                                                   | Default value          |
|-----------------|---------------------------------------------------------------|------------------------|
| PRUNE_INTERVAL  | Interval in seconds between prunes                            | `86400`                |
| RETAIN_COUNT    | Number of full backups to retain                              | `2`                    |
| AFTER_TIMESTAMP | Timestamp or name after which backups should be retained      | `None`                 |
| ENVDIR          | Directory containing environment variable files               | `/run/etc/wal-e.d/env` |
| LOG_LEVEL       | Log level for the application                                 | `INFO`                 |
| PGHOST          | Hostname or IP of the Postgres instance to monitor metrics on | `localhost`            |
| PGPORT          | Port of the Postgres instance to monitor metrics on           | `5432`                 |
| PGUSER          | Username with which to connect to the Postgres instance       | `postgres`             |
| PGDATABASE      | Database name of the Postgres instance to connect to          | `postgres`             |
| PGPASSWORD      | Password of the above configured user                         |                        |
| PGSSLMODE       | SSL mode of the Postgres connection                           |                        |

## Running as a sidecar with Spilo
---

Here you find an example sidecar configuration for wal-g-pruner to run along within a Spilo pod.
The most of the configuration is straightforward with one thing to mention. To make the envdir
`/run/etc/wal-e.d/env` shared between the Spilo container and wal-g-pruner, you need to mount
the volume `walg` (as here named in this example) also to the Spilo container. Spilo will take
care of the content in this directory.

```yaml
...
      - env:
        - name: POSTGRES_USER
          value: postgres
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              key: password
              name: postgres.postgres-wal-g-pruner.credentials.postgresql.acid.zalan.do
        - name: PGHOST
          value: 127.0.0.1
        - name: PGPORT
          value: "5432"
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef:
              key: password
              name: postgres.postgres-wal-g-pruner.credentials.postgresql.acid.zalan.do
        - name: PGUSER
          valueFrom:
            secretKeyRef:
              key: username
              name: postgres.postgres-wal-g-pruner.credentials.postgresql.acid.zalan.do
        image: athomas22/wal-g-pruner:latest
        imagePullPolicy: IfNotPresent
        name: wal-g-pruner
        volumeMounts:
        - mountPath: /home/postgres/pgdata
          name: pgdata
        - mountPath: /run/etc
          name: walg
...
      volumes:
      - emptyDir:
          medium: Memory
        name: dshm
      - emptyDir: {}
        name: walg
...
```

An example log output of wal-g-pruner looks like this:

```
2024-06-03 22:52:30,226 - INFO - Waiting for the database to be ready...
2024-06-03 22:52:30,234 - INFO - Reading environment variables from /run/etc/wal-e.d/env
2024-06-03 22:52:30,241 - INFO - Running command: wal-g delete retain FULL 2 --confirm
2024-06-03 22:52:38,024 - INFO - Successfully pruned WAL-G backups
2024-06-03 22:52:38,024 - INFO - Waiting for next prune cycle...
2024-06-04 22:52:38,035 - INFO - Running command: wal-g delete retain FULL 2 --confirm
2024-06-04 22:53:22,806 - INFO - Successfully pruned WAL-G backups
2024-06-04 22:53:22,806 - INFO - Waiting for next prune cycle...
```


# Disclaimer
---

This project is inspired by some of the great work done by [thedatabaseme/wal-g-exporter](https://github.com/thedatabaseme/wal-g-exporter), and modified for a different use case. 
```
