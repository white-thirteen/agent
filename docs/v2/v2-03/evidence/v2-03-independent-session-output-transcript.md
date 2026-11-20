# 独立 QA 工具输出逐字摘录

本文件是 QA 根据本会话已返回的工具输出整理的文本摘录，并非进程 stdout 原始字节文件；没有重跑测试。原始命令分别是 `python -m pytest tests/test_tool_progressive_disclosure.py tests/test_refund_checkpoint.py -q --tb=short`、`python docs/v2/v2-03/evidence/v2-03-independent-saver-probe.py`，使用项目 `.venv`。完整受控测试工具输出中的警告行保留如下。

```text
..........................................                               [100%]
============================== warnings summary ===============================
tests/test_tool_progressive_disclosure.py::test_run_compaction_preserves_business_budget_before_source[1-0-0-120]
  D:\py\agent-project\agent\.venv\Lib\site-packages\trustcall\_base.py:46: LangGraphDeprecatedSinceV10: Importing Send from langgraph.constants is deprecated. Please use 'from langgraph.types import Send' instead. Deprecated in LangGraph V1.0 to be removed in V2.0.
    from langgraph.constants import Send

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
42 passed, 1 warning in 4.15s
```

真实隔离 Saver 独立探针的进程退出码 0。其工具输出为：

```text
{"mode": "exception", "outcome": "rejected_unknown", "root_attempts": 0, "floor": 1, "receipts": [{"id": "6fe821ef-4298-4ccd-8d22-1c3afd3c99b3", "task_id": "qa-52e27cda92e94d33a8e843a5ae36cf1d", "run_id": "run1", "status": "selected", "provider_calls": 1, "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8, "status": "known", "estimation_method": null}, "reserved_attempts": 1, "error_code": null}], "inflight": true}
{"mode": "exception", "cleaned": true}
{"mode": "success", "outcome": "confirmed", "root_attempts": 1, "floor": 1, "receipts": [{"id": "07964c6d-7c71-4f45-ac5e-169fd4055b64", "task_id": "qa-303b48c2b6fc418abf802d9bbe8a5f4f", "run_id": "run1", "status": "selected", "provider_calls": 1, "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8, "status": "known", "estimation_method": null}, "reserved_attempts": 1, "error_code": null}], "inflight": false}
{"mode": "success", "cleaned": true}
{"mode": "kill", "exit": 71, "floor": 1, "root_attempts": 0, "inflight": true, "receipts": [{"id": "eb543ac2-a1bb-42c7-abe2-e56f46c43fcb", "task_id": "qa-dce633ed407e43bcb520a83b09232e99", "run_id": "run1", "status": "selected", "provider_calls": 1, "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8, "status": "known", "estimation_method": null}, "reserved_attempts": 1, "error_code": null}]}
{"mode": "kill", "cleaned": true}
```

手动模型组原始字节文件 `v2-03-independent-real-manual.log` 经 Python UTF-8 解码，提取每行 JSON 的 `cases`，逐个比较 `need` 与 fixture 原文，原工具输出：

```text
fixture_sha256 1a3e596e1b7d684a64a25f08b26203c95a8d6209d07093875e967e12b6430725
fixture_need_exact_match True
replacement_char_in_decoded_needs False
cases 5
```

同一原始日志经独立字节检查 `valid_utf8 True replacement False`。源日志是实际原始字节捕获；上列结论仅为检查结果的文本摘录。
