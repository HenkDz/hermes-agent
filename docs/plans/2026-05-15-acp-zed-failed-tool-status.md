# ACP Zed Failed Tool Status Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Mark failed Hermes tool calls as ACP `status="failed"` so Zed renders failures distinctly instead of showing every tool as completed.

**Architecture:** Add a conservative result classifier in `acp_adapter/tools.py`. Only mark failed when the tool result is clearly a structured failure (`success:false`, `ok:false`, `error`, `exit_code != 0`, etc.) or the formatter already identifies a failed edit/tool operation. Avoid broad string matching that could falsely mark normal test output as a tool infrastructure failure.

**Tech Stack:** Python, ACP Python SDK tool call updates, `acp_adapter/tools.py`, pytest.

---

### Task 1: Add tests for structured failure detection

**Objective:** Define safe failure semantics before implementation.

**Files:**
- Modify: `tests/acp/test_tools.py`

Add tests near `build_tool_complete` coverage:

```python
def test_build_tool_complete_marks_success_false_as_failed():
    update = build_tool_complete("tc-1", "some_tool", result='{"success": false, "error": "boom"}')
    assert update.status == "failed"


def test_build_tool_complete_marks_exit_code_nonzero_as_failed():
    update = build_tool_complete("tc-1", "terminal", result='{"output": "bad", "exit_code": 2}')
    assert update.status == "failed"


def test_build_tool_complete_keeps_plain_error_text_completed():
    update = build_tool_complete("tc-1", "terminal", result="tests failed: 1 assertion error")
    assert update.status == "completed"
```

The third test prevents lazy string matching.

**Run:**

```bash
scripts/run_tests.sh tests/acp/test_tools.py -q
```

Expected: FAIL for first two.

### Task 2: Implement `_tool_result_failed`

**Objective:** Classify only obvious tool-level failures.

**Files:**
- Modify: `acp_adapter/tools.py`

Add near `_is_structured_json_result`:

```python
def _tool_result_failed(result: Optional[str]) -> bool:
    data = _json_loads_maybe(result)
    if not isinstance(data, dict):
        return False

    for key in ("success", "ok"):
        value = data.get(key)
        if value is False:
            return True

    exit_code = data.get("exit_code", data.get("returncode"))
    if isinstance(exit_code, int) and exit_code != 0:
        return True

    if data.get("error") and not data.get("success", True):
        return True

    return False
```

Be careful with tools that return `{"error": "..."}` without `success:false`; decide based on actual tool conventions. If Hermes tools consistently use `error` for failure, expand the heuristic and add tests.

### Task 3: Wire status into tool completion

**Objective:** Emit ACP failed status.

Change in `build_tool_complete`:

```python
status="failed" if _tool_result_failed(result) else "completed",
```

### Task 4: Verify focused suite

Run:

```bash
scripts/run_tests.sh tests/acp/test_tools.py tests/acp/test_events.py -q
```

Expected: PASS.

Manual Zed check: force a failing terminal command and confirm the tool row shows failure while the model still receives the output.
