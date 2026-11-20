"""Select safe public history and coordinate archive publication and bounded reads."""

from app.context.archive_store import digest, make_segment
from app.context.models import Archive


class _ClaimBudget:
    """Bind each gateway attempt to one persisted executor claim."""

    def __init__(self, repository, claim_id):
        self.repository = repository
        self.claim_id = claim_id

    async def reserve_attempt(self, maintenance_id):
        return await self.repository.reserve_attempt(maintenance_id, self.claim_id)

    async def record_attempt(self, maintenance_id, attempt_id, usage):
        await self.repository.record_attempt(maintenance_id, self.claim_id, attempt_id, usage)


def select_prefix(interactions, *, retain_recent, max_messages):
    """Stop at the first uncertain task or boundary; never split an interaction."""
    if retain_recent < 0 or max_messages <= 0:
        raise ValueError("Invalid archive limits")
    eligible = interactions[:-retain_recent] if retain_recent else interactions
    protected_tasks = {item.task_id for item in interactions[len(eligible) :]}
    protected_tasks.update(
        item.task_id for item in interactions if item.task_status not in {"COMPLETED", "REJECTED"}
    )
    selected = []
    ids = set()
    for interaction in eligible:
        messages = interaction.messages
        if (
            interaction.task_status not in {"COMPLETED", "REJECTED"}
            or not interaction.task_id
            or interaction.task_id in protected_tasks
            or not messages
            or messages[0].role != "user"
            or messages[-1].role != "assistant"
            or any(m.task_id != interaction.task_id or not m.message_id for m in messages)
            or len({m.message_id for m in messages}) != len(messages)
            or ids.intersection(m.message_id for m in messages)
        ):
            break
        if len(selected) + len(messages) > max_messages:
            break
        selected.extend(messages)
        ids.update(m.message_id for m in messages)
    # Do not archive only part of a Task if a message limit stopped the prefix.
    if selected:
        included_tasks = {m.task_id for m in selected}
        selected_ids = {m.message_id for m in selected}
        incomplete = {
            item.task_id
            for item in interactions
            if item.task_id in included_tasks
            and any(m.message_id not in selected_ids for m in item.messages)
        }
        if incomplete:
            first = next(i for i, m in enumerate(selected) if m.task_id in incomplete)
            selected = selected[:first]
    return tuple(selected)


class ContextManager:
    def __init__(self, repository, store):
        self.repository, self.store = repository, store

    async def publish(
        self,
        identity,
        checkpoint_id,
        interactions,
        *,
        retain_recent,
        max_messages,
        session_status,
        run_scope=None,
        execution_mode=None,
    ):
        if session_status not in {"COMPLETED", "REJECTED"} and not (
            session_status == "RUNNING"
            and run_scope is not None
            and not run_scope.finished
            and execution_mode == "normal"
        ):
            raise ValueError("Session is not safe for archive maintenance")
        messages = select_prefix(
            interactions, retain_recent=retain_recent, max_messages=max_messages
        )
        if not messages:
            raise ValueError("No safe public history")
        if not checkpoint_id:
            raise ValueError("Checkpoint required")
        segment_id, content_hash, payload = make_segment(identity, checkpoint_id, messages)
        archive = Archive(
            identity=identity,
            archive_ref=identity.archive_ref(segment_id),
            segment_id=segment_id,
            message_ids=tuple(m.message_id for m in messages),
            content_hash=content_hash,
            source_checkpoint_id=checkpoint_id,
            relative_path=self.store.relative_path(identity, segment_id),
            file_hash=None,
            status="PREPARING",
        )
        tasks = tuple(dict.fromkeys(m.task_id for m in messages))
        archive = await self.repository.prepare(archive, tasks)
        _, _, payload = make_segment(identity, archive.source_checkpoint_id, messages)
        if archive.status == "READY":
            self.store.read(archive, max_bytes=len(self.store.encode(payload)))
            return archive
        data = self.store.encode(payload)
        file_hash = self.store.publish(archive.relative_path, data)
        if file_hash != digest(data):
            raise ValueError("Archive publication integrity failure")
        # Verify the published file itself before the database may advertise READY.
        ready = archive.model_copy(update={"status": "READY", "file_hash": file_hash})
        self.store.read(ready, len(data))
        return await self.repository.ready(archive, file_hash)

    async def recover(
        self,
        identity,
        *,
        candidate_limit,
        max_bytes,
        max_tokens,
        token_counter,
        refs=(),
        summary_id=None,
        task_id=None,
        message_id=None,
        expand_neighbor=False,
    ):
        if min(candidate_limit, max_bytes, max_tokens) <= 0:
            raise ValueError("Invalid recovery limits")
        if summary_id is not None:
            if refs:
                raise ValueError("Specify either summary or archive references")
            summary = await self.repository.get_summary(identity, summary_id)
            if summary is None:
                raise ValueError("Summary unavailable")
            refs = summary.archive_refs
        if refs:
            if len(set(refs)) > candidate_limit:
                raise ValueError("Archive references exceed candidate budget")
            candidates = []
            for ref in dict.fromkeys(refs):
                archive = await self.repository.get(identity, ref)
                if archive is None:
                    raise ValueError("Archive reference unavailable")
                candidates.append(archive)
        else:
            candidates = await self.repository.candidates(
                identity,
                limit=candidate_limit - int(expand_neighbor and candidate_limit > 1),
                task_id=task_id,
                message_id=message_id,
            )
        if expand_neighbor and candidates and len(candidates) < candidate_limit:
            candidates += await self.repository.neighbors(
                identity, candidates[0].archive_ref, candidate_limit - len(candidates)
            )
        messages, seen, used_bytes, used_tokens = [], set(), 0, 0
        for archive in candidates:
            if archive.identity != identity:
                raise ValueError("Archive identity mismatch")
            if archive.archive_ref in seen:
                continue
            seen.add(archive.archive_ref)
            if archive.relative_path != self.store.relative_path(identity, archive.segment_id):
                raise ValueError("Invalid archive path")
            path = self.store._path(archive.relative_path)
            size = path.stat().st_size
            if used_bytes + size > max_bytes:
                break
            segment = self.store.read(archive, max_bytes - used_bytes)
            tokens = token_counter(segment)
            if tokens < 0 or used_tokens + tokens > max_tokens:
                break
            used_bytes += size
            used_tokens += tokens
            known = {m.message_id for m in messages}
            messages.extend(m for m in segment if m.message_id not in known)
        return tuple(messages)

    async def _summary_source(
        self,
        identity,
        *,
        archive_refs,
        parent_summary_id,
        source_checkpoint_id,
        version,
        policy_version,
        model_version,
        prompt_version,
        max_bytes,
    ):
        from langchain_core.messages import AIMessage, HumanMessage
        from langmem.short_term import RunningSummary

        from app.context.archive_store import canonical, digest

        if (
            not archive_refs
            or len(set(archive_refs)) != len(archive_refs)
            or not source_checkpoint_id
            or version <= 0
            or not all((policy_version, model_version, prompt_version))
            or max_bytes <= 0
        ):
            raise ValueError("Invalid summary source")
        messages = []
        used = 0
        for ref in archive_refs:
            archive = await self.repository.get(identity, ref)
            if archive is None:
                raise ValueError("Summary archive unavailable")
            size = self.store._path(archive.relative_path).stat().st_size
            used += size
            if used > max_bytes:
                raise ValueError("Summary archive exceeds read budget")
            messages.extend(self.store.read(archive, max_bytes - used + size))
        ids = tuple(m.message_id for m in messages)
        if len(set(ids)) != len(ids):
            raise ValueError("Overlapping summary archives")
        parent = None
        if parent_summary_id:
            parent = await self.repository.get_summary(identity, parent_summary_id)
            if (
                parent is None
                or parent.version >= version
                or ids[: len(parent.message_ids)] != parent.message_ids
                or tuple(archive_refs[: len(parent.archive_refs)]) != parent.archive_refs
            ):
                raise ValueError("Invalid parent summary")
        scope_hash = digest(canonical([m.model_dump() for m in messages]))
        input_hash = digest(
            canonical(
                {
                    "messages": [m.model_dump() for m in messages],
                    "archives": list(archive_refs),
                    "parent": parent_summary_id,
                    "version": version,
                    "policy": policy_version,
                    "model": model_version,
                    "prompt": prompt_version,
                }
            )
        )
        lang_messages = [
            (HumanMessage if m.role == "user" else AIMessage)(content=m.content, id=m.message_id)
            for m in messages
        ]
        running = (
            RunningSummary(parent.text, set(parent.message_ids), parent.message_ids[-1])
            if parent
            else None
        )
        return ids, lang_messages, running, input_hash, scope_hash

    async def compact(
        self,
        identity,
        *,
        archive_refs,
        parent_summary_id,
        source_checkpoint_id,
        version,
        policy_version,
        model_version,
        prompt_version,
        max_bytes,
        gateway,
        token_counter,
        max_input_tokens,
        max_output_tokens,
        settings,
        run_scope=None,
        run_context=None,
        execution_mode=None,
        maintenance=None,
    ):
        """Build a serialized Summary using either the current Run or durable maintenance.

        The caller owns the session execution/maintenance lock and supplies trusted source
        metadata. No database transaction spans a provider call.
        """
        import time
        from uuid import uuid4

        from app.context.compaction import (
            SUMMARY_PROMPT_VERSION,
            CompactionError,
            summarize_for_run,
            summarize_messages,
        )
        from app.context.models import Summary
        from app.runtime.model_gateway import (
            MaintenanceCallContext,
            ModelCallContext,
            ModelCallUsage,
        )

        if prompt_version != SUMMARY_PROMPT_VERSION:
            raise ValueError("Unsupported summary prompt version")
        if (maintenance is None) == (run_scope is None):
            raise ValueError("Exactly one compaction owner is required")
        if run_scope is not None and not isinstance(run_context, ModelCallContext):
            raise ValueError("Run context required")
        if maintenance is not None and (run_context is not None or execution_mode is not None):
            raise ValueError("Maintenance cannot use Run context")
        if (
            settings.context_model_window_tokens is None
            or settings.context_model_output_tokens is None
            or max_input_tokens <= 0
            or max_output_tokens <= 0
            or max_output_tokens > settings.context_model_output_tokens
            or max_input_tokens + max_output_tokens > settings.context_model_window_tokens
            or model_version != settings.model_name
        ):
            raise ValueError("Configured model limits or version do not permit compaction")
        ids, messages, running, input_hash, scope_hash = await self._summary_source(
            identity,
            archive_refs=archive_refs,
            parent_summary_id=parent_summary_id,
            source_checkpoint_id=source_checkpoint_id,
            version=version,
            policy_version=policy_version,
            model_version=model_version,
            prompt_version=prompt_version,
            max_bytes=max_bytes,
        )
        existing = await self.repository.find_summary(
            identity,
            input_hash=input_hash,
            version=version,
            source_checkpoint_id=source_checkpoint_id,
            policy_version=policy_version,
            model_version=model_version,
            prompt_version=prompt_version,
        )
        if existing and (
            existing.message_ids != ids
            or existing.archive_refs != tuple(archive_refs)
            or existing.parent_summary_id != parent_summary_id
        ):
            raise ValueError("Summary source conflict")
        if run_scope is not None:
            if execution_mode != "normal" or run_scope.finished:
                raise ValueError("Summary requires an active normal Run")
            if existing:
                return existing, ()
            result, call_usage, reports = await summarize_for_run(
                messages,
                scope=run_scope,
                context=run_context,
                execution_mode=execution_mode,
                running_summary=running,
                gateway=gateway,
                token_counter=token_counter,
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
            )
        else:
            started = time.monotonic()
            work = await self.repository.register_maintenance(
                identity,
                maintenance_id=maintenance["maintenance_id"],
                source_task_id=maintenance["source_task_id"],
                source_run_id=maintenance["source_run_id"],
                source_checkpoint_id=source_checkpoint_id,
                message_ids=ids,
                content_hash=scope_hash,
                policy_version=policy_version,
                budget_version=maintenance["budget_version"],
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
                archive_refs=archive_refs,
            )
            work_id = work["maintenance_id"]
            if existing and work["status"] == "SUCCEEDED":
                if work["summary_id"] != existing.summary_id:
                    raise ValueError("Maintenance summary conflict")
                return existing, ()
            try:
                claim_id = await self.repository.claim_maintenance(
                    work_id, allow_exhausted=existing is not None
                )
            except ValueError:
                # A concurrent executor may have completed between the first read and claim.
                work = await self.repository.maintenance(work_id)
                if work["status"] == "SUCCEEDED":
                    ready = await self.repository.find_summary(
                        identity,
                        input_hash=input_hash,
                        version=version,
                        source_checkpoint_id=source_checkpoint_id,
                        policy_version=policy_version,
                        model_version=model_version,
                        prompt_version=prompt_version,
                    )
                    if ready and ready.summary_id == work["summary_id"]:
                        return ready, ()
                raise
            try:
                existing = await self.repository.find_summary(
                    identity,
                    input_hash=input_hash,
                    version=version,
                    source_checkpoint_id=source_checkpoint_id,
                    policy_version=policy_version,
                    model_version=model_version,
                    prompt_version=prompt_version,
                )
                if existing:
                    await self.repository.finish_maintenance(
                        work_id, claim_id, summary_id=existing.summary_id
                    )
                    return existing, ()
                work = await self.repository.maintenance(work_id)
                if work["reserved_attempts"] >= 2 or work["remaining"] <= 0:
                    raise ValueError("Maintenance budget exhausted or unavailable")
                result, call_usage, reports = await summarize_messages(
                    messages,
                    running_summary=running,
                    gateway=gateway,
                    context=MaintenanceCallContext(
                        work_id,
                        _ClaimBudget(self.repository, claim_id),
                        started + float(work["remaining"]),
                        max_output_tokens,
                    ),
                    model_usage=ModelCallUsage(work["reserved_attempts"]),
                    token_counter=token_counter,
                    max_input_tokens=max_input_tokens,
                    max_output_tokens=max_output_tokens,
                )
            except Exception:
                await self.repository.finish_maintenance(work_id, claim_id)
                raise
        if result is None or result.summarized_message_ids != set(ids):
            if maintenance is not None:
                await self.repository.finish_maintenance(work_id, claim_id)
            raise ValueError("Summary coverage mismatch")
        summary = Summary(
            identity=identity,
            summary_id=str(uuid4()),
            version=version,
            text=result.summary,
            archive_refs=tuple(archive_refs),
            message_ids=ids,
            parent_summary_id=parent_summary_id,
            input_hash=input_hash,
            status="READY",
        )
        try:
            saved = await self.repository.save_summary(
                summary,
                source_checkpoint_id=source_checkpoint_id,
                policy_version=policy_version,
                model_version=model_version,
                prompt_version=prompt_version,
            )
        except Exception as error:
            if maintenance is not None:
                await self.repository.finish_maintenance(work_id, claim_id)
            if reports:
                raise CompactionError(
                    "Summary publication failed after model invocation",
                    model_usage=call_usage,
                    reports=reports,
                ) from error
            raise
        if maintenance is not None:
            await self.repository.finish_maintenance(work_id, claim_id, summary_id=saved.summary_id)
        return saved, reports

    async def publish_revision(self, revision, *, max_bytes):
        """Check immutable file content before the repository publishes a candidate."""
        from app.context.archive_store import canonical, digest

        messages = []
        archive_hashes = []
        remaining = max_bytes
        for ref in revision.archive_refs:
            archive = await self.repository.get(revision.identity, ref)
            if archive is None:
                raise ValueError("Revision archive unavailable")
            size = self.store._path(archive.relative_path).stat().st_size
            if size > remaining:
                raise ValueError("Revision archive exceeds read budget")
            messages.extend(self.store.read(archive, remaining))
            archive_hashes.append(archive.content_hash)
            remaining -= size
        messages = messages[-len(revision.message_ids) :]
        if (
            tuple(m.message_id for m in messages) != revision.message_ids
            or digest(canonical([m.model_dump() for m in messages])) != revision.content_hash
        ):
            raise ValueError("Revision content mismatch")
        return await self.repository.publish_revision(revision, archive_hashes=archive_hashes)

    async def adoption_plan(self, identity, current, source, candidate, *, max_bytes):
        """Prove a candidate against the source and current trusted Saver snapshots."""
        from langchain_core.messages import AIMessage, HumanMessage

        from app.context.archive_store import canonical, digest

        def ref(values):
            return values.get("context_ref")

        def base(values):
            value = ref(values)
            return value.get("revision") if value else None

        if (
            candidate.identity != identity
            or source.values.get("user_id") != identity.user_id
            or source.values.get("conversation_id") != identity.conversation_id
            or candidate.status != "PUBLISHED"
            or source.config["configurable"].get("checkpoint_id") != candidate.source_checkpoint_id
            or source.next
            or base(source.values) != candidate.base_revision
            or base(current.values) != candidate.base_revision
        ):
            return None
        try:
            base_summary = await self.repository.validate_revision_base(
                identity, candidate.base_revision, candidate.summary_id
            )
        except ValueError:
            return None
        if candidate.base_revision is not None and (
            ref(source.values).get("summary_id") != base_summary
            or ref(current.values).get("summary_id") != base_summary
        ):
            return None
        messages, remaining = [], max_bytes
        for archive_ref in candidate.archive_refs:
            archive = await self.repository.get(identity, archive_ref)
            if archive is None:
                return None
            size = self.store._path(archive.relative_path).stat().st_size
            if size > remaining:
                return None
            messages.extend(self.store.read(archive, remaining))
            remaining -= size
        messages = messages[-len(candidate.message_ids) :]
        if (
            tuple(m.message_id for m in messages) != candidate.message_ids
            or digest(canonical([m.model_dump() for m in messages])) != candidate.content_hash
        ):
            return None
        source_messages = source.values.get("messages", [])
        current_messages = current.values.get("messages", [])
        # Outside-range additions are safe only when the complete original prefix is unchanged.
        if (
            len(current_messages) < len(source_messages)
            or current_messages[: len(source_messages)] != source_messages
        ):
            return None
        if tuple(m.id for m in source_messages[: len(messages)]) != candidate.message_ids:
            return None
        metadata = source.values.get("public_message_metadata", {})
        for archived, hot in zip(messages, source_messages, strict=False):
            expected_type = HumanMessage if archived.role == "user" else AIMessage
            item = metadata.get(archived.message_id)
            if (
                type(hot) is not expected_type
                or hot.content != archived.content
                or (isinstance(hot, AIMessage) and (hot.tool_calls or hot.invalid_tool_calls))
                or item
                != {
                    "task_id": archived.task_id,
                    "run_id": archived.run_id,
                    "task_status": "completed",
                }
                and item
                != {
                    "task_id": archived.task_id,
                    "run_id": archived.run_id,
                    "task_status": "rejected",
                }
                or current.values.get("public_message_metadata", {}).get(archived.message_id)
                != item
            ):
                return None
        return {
            "revision": candidate.revision,
            "summary_id": candidate.summary_id,
            "base_revision": candidate.base_revision,
            "message_ids": list(candidate.message_ids),
            "source_checkpoint_id": candidate.source_checkpoint_id,
            "messages": [(m.message_id, m.role, m.content) for m in messages],
        }
