---
phase: 1
plan: 0
type: checkpoint
wave: 0
depends_on: []
files_modified: []
autonomous: true
requirements:
  - AI-CHAT-COMPLETIONS
must_haves:
  truths:
    - Impact analysis is completed before editing existing route, API, forwarder, or WebSocket symbols.
    - Execution stops if the `sekiro-go` GitNexus index remains unavailable.
  artifacts:
    - GitNexus impact reports for route/API/forwarder/WebSocket symbols
  key_links:
    - `impact reports -> implementation plans`
---

# Plan 000: Pre-Edit Impact Gate

<objective>
Satisfy the repository rule that existing symbols must receive GitNexus impact
analysis before any implementation plan edits them.
</objective>

<tasks>

<task type="checkpoint:impact">
  <name>Analyze route and API symbol impact</name>
  <files>
    <file>pkg/server/bootstrap.go</file>
    <file>pkg/server/api/handlers.go</file>
  </files>
  <action>
    Run GitNexus impact analysis for `registerRoutes`, `APIHandler`,
    `selectTargetClient`, `authorizeRegisteredGroupAccess`, and
    `handleForwardRequest`. If the `sekiro-go` index is unavailable, run
    `npx gitnexus analyze` and retry. If it remains unavailable, stop execution.
  </action>
  <verify>
    <automated>gitnexus_impact({target:"registerRoutes", file_path:"pkg/server/bootstrap.go", direction:"upstream", repo:"sekiro-go"})</automated>
    <automated>gitnexus_impact({target:"APIHandler", file_path:"pkg/server/api/handlers.go", direction:"upstream", repo:"sekiro-go"})</automated>
    <automated>gitnexus_impact({target:"selectTargetClient", file_path:"pkg/server/api/handlers.go", direction:"upstream", repo:"sekiro-go"})</automated>
    <automated>gitnexus_impact({target:"authorizeRegisteredGroupAccess", file_path:"pkg/server/api/handlers.go", direction:"upstream", repo:"sekiro-go"})</automated>
    <automated>gitnexus_impact({target:"handleForwardRequest", file_path:"pkg/server/api/handlers.go", direction:"upstream", repo:"sekiro-go"})</automated>
  </verify>
  <done>
    Route and API blast radius is recorded before code edits.
  </done>
</task>

<task type="checkpoint:impact">
  <name>Analyze forwarder symbol impact</name>
  <files>
    <file>pkg/server/forwarder/timeout.go</file>
  </files>
  <action>
    Run GitNexus impact analysis for `TimeoutManager`, `Complete`, and `Wait`.
    Stop execution if impact analysis cannot be completed.
  </action>
  <verify>
    <automated>gitnexus_impact({target:"TimeoutManager", file_path:"pkg/server/forwarder/timeout.go", direction:"upstream", repo:"sekiro-go"})</automated>
    <automated>gitnexus_impact({target:"Complete", file_path:"pkg/server/forwarder/timeout.go", direction:"upstream", repo:"sekiro-go"})</automated>
    <automated>gitnexus_impact({target:"Wait", file_path:"pkg/server/forwarder/timeout.go", direction:"upstream", repo:"sekiro-go"})</automated>
  </verify>
  <done>
    Forwarder blast radius is recorded before code edits.
  </done>
</task>

<task type="checkpoint:impact">
  <name>Analyze WebSocket symbol impact</name>
  <files>
    <file>pkg/server/websocket/handler.go</file>
  </files>
  <action>
    Run GitNexus impact analysis for `processMessage` and
    `handleInvokeResponse`. Stop execution if impact analysis cannot be
    completed.
  </action>
  <verify>
    <automated>gitnexus_impact({target:"processMessage", file_path:"pkg/server/websocket/handler.go", direction:"upstream", repo:"sekiro-go"})</automated>
    <automated>gitnexus_impact({target:"handleInvokeResponse", file_path:"pkg/server/websocket/handler.go", direction:"upstream", repo:"sekiro-go"})</automated>
  </verify>
  <done>
    WebSocket blast radius is recorded before code edits.
  </done>
</task>

</tasks>

<verification>
<automated>gitnexus_detect_changes({scope:"all", repo:"sekiro-go"})</automated>
</verification>

<success_criteria>
- All required pre-edit impact reports are available.
- Any HIGH or CRITICAL impact is reported before implementation proceeds.
- Execution is blocked if GitNexus remains unavailable.
</success_criteria>
