# Historical defect regressions

Each test pins one confirmed upstream defect class against the current product
behavior. Evidence: `tasks/plan.md` §16 (upstream increment regressions) and the
frozen sources at `D:\pi @ e14afc648e10fb6c527ea88fa627091ada764306`.

| Defect | Regression test | Confirmed behavior |
|---|---|---|
| JSONL last line written without a trailing newline was rejected or corrupted | `test_session.py::test_reader_accepts_a_complete_final_line_without_trailing_newline` | The strict reader accepts a complete final record without `\n`; later appends keep the file well-formed. |
| Extension-inserted messages could split a ToolCall/ToolResult pair | `test_agent.py::test_extension_message_during_tool_execution_does_not_split_the_pair` | Messages appended by extensions while a tool pair is open are queued until the pair completes. |
| A large tool result was not compacted before the next provider request | `test_agent.py::test_auto_compaction_lands_before_the_next_provider_request` | Threshold compaction runs at turn end, so the next request already sees the summary. |
| Parallel tool results were merged or reordered instead of persisted per tool | `test_agent.py::test_parallel_tool_results_persist_individually_in_model_order` | Every parallel tool result is its own persisted entry, adjacent to its call, in model order. |
| Extension-launched subprocesses survived reload/exit as orphans | `test_tools.py::test_extension_exec_processes_terminate_on_session_close` | In-flight `actions.exec` processes are killed when the extension runtime closes. |
