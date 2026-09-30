# Services, Networking & Runtime Ports Guide

## 1. Network Architecture
- **Interface**: Local loopback interface (`127.0.0.1` / `localhost`).
- **Port Allocation**: Choose unprivileged ports (ports above `1024`, such as `3000`, `5000`, `8000`, `8080`).
- **Binding**: Always bind server listeners to `127.0.0.1` or `0.0.0.0`:
  ```bash
  python -m http.server 8080 --bind 127.0.0.1 &
  ```

---

## 2. Agent Tooling for Live Services
The agent is equipped with native tools to inspect and interact with running services:

1. **`list_runtime_ports`**:
   - Discovers all TCP ports currently listening on loopback.
   - Returns port numbers, detected processes, and service titles.
2. **`open_runtime_port`**:
   - Opens the service in the integrated Ocean Runtime Ports browser.
   - Takes `port` (e.g. `8080`) and optional `path` (e.g. `"/dashboard"`).
3. **`interact_runtime_page`**:
   - Programmatically controls and tests the rendered web page.
   - Actions: `screenshot`, `click`, `type`, `evaluate_javascript`, `scroll`.
   - Allows full-loop verification of frontend apps and noVNC desktop sessions.

---

## 3. Best Practices for Server Workflows
1. Start the server in background.
2. Wait 1 second and call `list_runtime_ports` to verify it is actively accepting connections.
3. Call `open_runtime_port` to display the UI to the user.
4. Call `interact_runtime_page` with action `screenshot` to verify visual layout and rendering.
