Task Objective
Fix missing helpers and broken calls in `apps/backend/tools.py` to make backend tools executable and JSON-consistent.

Current State Assessment
- `_json`, `python_exec`, and `safe_shell` were referenced but undefined.
- Several functions had incorrect indentation and missing imports.
- Shell/Python execution lacked safe wrappers and JSON responses.

Future State Goal
- Tools module self-contained with helpers implemented.
- Consistent JSON outputs for all tools.
- Safe execution wrappers for Python and shell commands.

Implementation Plan
1. Add `_json` utility returning JSON strings. [x]
2. Implement `PythonExec` and `SafeShell` wrappers. [x]
3. Expose `python_exec` and `safe_shell` convenience functions. [x]
4. Fix imports and indentation across tool functions. [x]
5. Update tool functions to use helpers and return JSON. [x]
6. Run lints and verify issues. [x]

Notes
- A linter warning remains for `langchain.tools` not resolved; acceptable until dependency installed.


