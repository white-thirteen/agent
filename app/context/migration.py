"""Recover public message associations only from completed checkpoint snapshots."""

from langchain_core.messages import AIMessage, HumanMessage

from app.runtime.models import TaskStatus


async def recover_public_metadata(graph, thread_id, user_id, conversation_id, saved):
    """Inspect one session's checkpoint history without modifying old checkpoints."""
    metadata = dict(saved.get("public_message_metadata", {}))
    messages = saved.get("messages", [])
    missing = {m.id for m in messages if m.id and m.id not in metadata}
    if missing:
        current = {m.id: m for m in messages if m.id}
        seen = set()
        claims = {}
        async for snapshot in graph.aget_state_history({"configurable": {"thread_id": thread_id}}):
            values = snapshot.values
            if not values:
                continue
            owner = values.get("user_id"), values.get("conversation_id")
            if None in owner:
                # The Saver can contain an input checkpoint before identity channels exist.
                continue
            if owner != (user_id, conversation_id):
                raise ValueError("Checkpoint owner mismatch")
            task_id = values.get("task_id")
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            if (
                values.get("workflow_id") != task_id
                or snapshot.next
                or getattr(snapshot, "interrupts", ())
                or values.get("pending_task") is not None
                or values.get("task_status") not in (TaskStatus.COMPLETED, TaskStatus.REJECTED)
            ):
                continue
            ids = values.get("task_message_ids")
            if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
                continue
            historic = {m.id: m for m in values.get("messages", []) if m.id in ids}
            if set(historic) != set(ids) or any(
                mid not in current
                or historic[mid] != current[mid]
                or type(current[mid]) not in (HumanMessage, AIMessage)
                or not isinstance(current[mid].content, str)
                or isinstance(current[mid], AIMessage)
                and (current[mid].tool_calls or current[mid].invalid_tool_calls)
                for mid in ids
            ):
                continue
            for mid in ids:
                claims.setdefault(mid, []).append((task_id, values["task_status"]))
        for mid in missing:
            matches = claims.get(mid, [])
            if len(matches) == 1:
                task_id, status = matches[0]
                metadata[mid] = {
                    "task_id": task_id,
                    "run_id": None,
                    "task_status": TaskStatus(status).value,
                }
    incomplete = any(not m.id or m.id not in metadata for m in messages)
    return metadata, "incomplete" if incomplete else "complete"
