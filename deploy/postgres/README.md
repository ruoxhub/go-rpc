# Local PostgreSQL recovery

This route is for disposable local development data only. It never targets an
external network or a production database.

Start an isolated database and wait for its health check:

```powershell
docker compose -f deploy/postgres/docker-compose.local.yaml up -d --wait
```

Use `.env.example` as the server configuration baseline, set
`RPC_DISABLE_DATABASE=false`, then start the server and verify readiness:

```powershell
Invoke-WebRequest http://localhost:5612/ready
```

If initialization or a migration fails, inspect the database logs first:

```powershell
docker compose -f deploy/postgres/docker-compose.local.yaml logs postgres
```

To recover, stop the server, then remove only the Compose project and named
volume declared in `docker-compose.local.yaml`. This permanently deletes the
local `go-rpc-local-db` data and must never be used for shared or production
databases:

```powershell
docker compose -f deploy/postgres/docker-compose.local.yaml down --volumes
docker compose -f deploy/postgres/docker-compose.local.yaml up -d --wait
```

The initialization script is rerun only when the named volume is newly
created. Recovery is complete when PostgreSQL is healthy and `/ready` returns
HTTP 200. Stop if either check fails; preserve the logs and do not retry against
another database target.
