from collections import deque

import pytest

from acp_adapter import events
from acp_adapter.tools import build_tool_complete, build_tool_start


ORPHAN_REGRESSION_TOOLS = [
    ("skills_list", {}, "read"),
    ("browser_navigate", {"url": "https://example.com"}, "fetch"),
    ("browser_snapshot", {"full": False}, "read"),
    ("browser_console", {"expression": "document.title"}, "execute"),
    ("browser_get_images", {}, "read"),
    ("browser_vision", {"question": "What is visible?"}, "read"),
]


@pytest.mark.parametrize(("tool_name", "args", "kind"), ORPHAN_REGRESSION_TOOLS)
def test_acp_polished_tools_build_start_and_completion_without_orphans(
    tool_name, args, kind
):
    """Polished tools must emit a valid start before completion.

    A previous fallback-path bug raised while building starts for these tools,
    but their completion IDs were still queued, so Zed rendered the completion
    update as "Tool call not found".
    """
    start = build_tool_start("tc-regression", tool_name, args)
    complete = build_tool_complete(
        "tc-regression",
        tool_name,
        result='{"success": true, "result": "ok", "skills": []}',
        function_args=args,
    )

    assert getattr(start, "session_update", None) == "tool_call"
    assert getattr(start, "tool_call_id", None) == "tc-regression"
    assert getattr(start, "kind", None) == kind
    assert getattr(complete, "session_update", None) == "tool_call_update"
    assert getattr(complete, "tool_call_id", None) == "tc-regression"
    assert getattr(complete, "status", None) == "completed"


def test_tool_progress_does_not_queue_id_when_start_update_fails(monkeypatch):
    sent = []

    def fake_send_update(*args, **kwargs):
        sent.append((args, kwargs))
        return False

    monkeypatch.setattr(events, "_send_update", fake_send_update)
    tool_call_ids = {}
    tool_call_meta = {}

    cb = events.make_tool_progress_cb(
        conn=object(),
        session_id="session-1",
        loop=object(),
        tool_call_ids=tool_call_ids,
        tool_call_meta=tool_call_meta,
    )

    cb("tool.started", name="browser_snapshot", args={"full": False})

    assert sent
    assert tool_call_ids == {}
    assert tool_call_meta == {}


def test_tool_progress_queues_id_only_after_successful_start_update(monkeypatch):
    def fake_send_update(*args, **kwargs):
        return True

    monkeypatch.setattr(events, "_send_update", fake_send_update)
    tool_call_ids = {}
    tool_call_meta = {}

    cb = events.make_tool_progress_cb(
        conn=object(),
        session_id="session-1",
        loop=object(),
        tool_call_ids=tool_call_ids,
        tool_call_meta=tool_call_meta,
    )

    cb("tool.started", name="browser_console", args={"expression": "document.title"})

    queue = tool_call_ids.get("browser_console")
    assert isinstance(queue, deque)
    assert len(queue) == 1
    assert queue[0] in tool_call_meta
    assert tool_call_meta[queue[0]]["args"] == {"expression": "document.title"}


def _completion_text(tool_name, result, args=None):
    complete = build_tool_complete(
        "tc-render",
        tool_name,
        result=result,
        function_args=args or {},
    )
    content = getattr(complete, "content", None)
    assert content
    return content[0].content.text


def test_browser_completion_content_avoids_internal_tool_names():
    assert (
        _completion_text(
            "browser_snapshot",
            '{"success": true, "snapshot": "- heading Example"}',
        )
        == "- heading Example"
    )

    assert (
        _completion_text(
            "browser_get_images",
            '{"success": true, "images": []}',
        )
        == "No images found"
    )

    assert (
        _completion_text(
            "browser_vision",
            '{"success": true, "analysis": "Example page visible"}',
        )
        == "Example page visible"
    )

    assert (
        _completion_text(
            "browser_console",
            '{"success": true, "result": "Example Domain"}',
            {"expression": "document.title"},
        )
        == "Example Domain"
    )
