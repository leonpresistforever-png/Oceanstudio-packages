# Ocean Terminal Execution & Shell Operations Guide

## 1. Execution Model for Autonomous Agents
- **Tool**: `run_terminal_command` (invoked via the agent tool interface).
- **Shell**: GNU Bash (`$PREFIX/bin/bash -lc "<command>"`).
- **Nature**: Each tool invocation launches a separate non-interactive login shell with the Ocean environment pre-exported.
- **Working Directory**: Defaults to `$HOME` unless explicitly overridden via the `cwd` argument.

---

## 2. Shell Syntax & Chaining Rules
1. **Command Chaining**:
   - Use `&&` to require previous step success before proceeding: `mkdir -p build && cd build`.
   - Use `;` or `\n` only when subsequent commands should run regardless of previous exit status.
2. **Quoting and Escaping**:
   - Always quote variables and paths with spaces: `"$PREFIX/bin/python3" "$HOME/my project/script.py"`.
   - Use single quotes `'...'` for literals to prevent unexpected expansion of `$`, `\`, and backticks.
3. **Subshells & Subcommands**:
   - Prefer separate, atomic commands over deep nested subshell evaluations `$(...)`.
   - Capture intermediate results into shell variables or scratch files in `$TMPDIR`.

---

## 3. Standard I/O, Exit Codes & Diagnostics
- **Exit Code 0**: Signifies unequivocal command success.
- **Non-Zero Exit Codes**: Indicate operational failure.
  - Inspect `stderr` output to understand the root cause.
  - Code `124`: Command timed out (exceeded configured execution duration).
  - Code `127`: Executable not found in `$PATH`.
  - Code `130`: Command terminated by SIGINT / user cancellation.
- **Diagnostics**:
  - Never discard errors (`2>/dev/null`) when troubleshooting or compiling.
  - Report exact error messages transparently to maintain truth in engineering.

---

## 4. Background Services & Long-Running Daemons
- When starting an HTTP server or long-running listener (e.g. Node.js or Python Flask/FastAPI):
  - Launch with `nohup <command> > server.log 2>&1 &` or run via a dedicated background script.
  - Immediately check that the process is running with `ps aux` or `pgrep`.
  - Check listening ports with `netstat -tlpn` or the `list_runtime_ports` tool.
