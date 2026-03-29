# Method Comparison

| method | turn_avg_ms | turn_p95_ms | user_facing_avg_ms | user_facing_p95_ms | total_tokens | tokens_per_turn | user_path_tokens | user_path_tokens_per_turn | background_tokens | background_tokens_per_turn | vs_full_history_total_token_delta | vs_full_history_total_token_delta_pct | vs_full_history_user_path_token_delta | vs_full_history_user_path_token_delta_pct | llm_requests | retrieval_avg_results | pipeline_runs | ps1_extraction_tokens | ps2_conflict_tokens | retrieval_tokens | core_memory_tokens | summary_tokens | conversation_tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| memblocks_full | 253344.97 | 61373.07 | 253344.84 | 61372.93 | 905086 | 9050.86 | 210901 | 2109.01 | 694185 | 6941.85 | 492872 | 119.57 | -201313 | -48.84 | 448 | 7.27 | 18 | 89587 | 499781 | 36867 | 54109 | 50708 | 174034 |
| full_history_baseline | 9976.00 | 16753.80 | None | None | 412214 | 4122.14 | 412214 | 4122.14 | 0 | 0.00 | 0 | 0.00 | 0 | 0.00 | 100 | None | 0 | 0 | 0 | 0 | 0 | 0 | 412214 |
