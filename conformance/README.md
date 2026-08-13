# Stage-1 SDK conformance

The black-box runner starts the DB-less Go server on a random loopback port and
serially exercises the formal Go, TypeScript/Node, Python, Java, and legacy
clients over real HTTP/WebSocket connections. It prints one `PASS` line per
adapter and never enumerates non-Stage-1 clients.

Prerequisites:

- Go toolchain and the repository's Go dependencies;
- Node/npm with the TypeScript SDK dependencies already available (the runner
  builds the SDK but never installs packages);
- Python with the SDK's Tornado/httpx dependencies;
- Java/Gradle. On the prepared Windows environment, set
  `GRADLE_USER_HOME` to the prepared local Gradle cache when needed.

Run from the repository root:

```text
go run ./conformance/runner
```

The runner does not download or install dependencies. Each adapter loads the
shared fixture, confirms registration and bind, performs an HTTP invoke, checks
the context/response contract, and destroys its client before exiting.
