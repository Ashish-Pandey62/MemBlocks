import React from 'react';

function AnalyticsPanel({ sessionId, currentBlock, chatStats }) {
  const summary = chatStats?.summary || '';
  const pipelineRuns = chatStats?.pipeline_runs || [];
  const operationSummary = chatStats?.operation_summary || {};
  const processingTriggered = chatStats?.processing_triggered || false;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <h2 className="text-white font-semibold">Analytics</h2>
        {sessionId && (
          <p className="text-gray-500 text-xs mt-1 truncate">
            Session: {sessionId.replace('session_', '').slice(0, 12)}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">

        {/* ── Recursive Summary ── */}
        <div>
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Conversation Summary
          </h3>
          <div className="bg-gray-800 rounded-lg p-4">
            {summary ? (
              <p className="text-gray-300 text-sm whitespace-pre-wrap leading-relaxed">{summary}</p>
            ) : (
              <div className="text-center py-2">
                <p className="text-gray-500 text-sm">No summary yet</p>
                <p className="text-gray-600 text-xs mt-1">Summary is generated after memory processing</p>
              </div>
            )}
          </div>
        </div>

        {/* ── Processing Pipeline ── */}
        <div>
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            Memory Pipeline
            {processingTriggered && (
              <span className="ml-auto text-xs text-amber-400 animate-pulse">● Processing</span>
            )}
          </h3>
          {pipelineRuns.length > 0 ? (
            <div className="space-y-2">
              {pipelineRuns.slice(0, 3).map((run, idx) => (
                <div key={idx} className="bg-gray-800 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded ${run.status === 'success' ? 'bg-emerald-500/20 text-emerald-400' :
                        run.status === 'running' ? 'bg-amber-500/20 text-amber-400' :
                          'bg-red-500/20 text-red-400'
                      }`}>
                      {run.status}
                    </span>
                    <span className="text-gray-500 text-xs">
                      {run.input_message_count} msgs processed
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-1 text-xs">
                    {run.extracted_semantic_count > 0 && (
                      <span className="text-gray-400">
                        📝 {run.extracted_semantic_count} memories
                      </span>
                    )}
                    {run.core_memory_updated && (
                      <span className="text-gray-400">🧠 Core updated</span>
                    )}
                    {run.summary_generated && (
                      <span className="text-gray-400">📄 Summary gen</span>
                    )}
                    {run.conflicts_resolved_count > 0 && (
                      <span className="text-gray-400">
                        ⚡ {run.conflicts_resolved_count} conflicts
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-gray-800 rounded-lg p-4 text-center">
              <p className="text-gray-500 text-sm">No pipeline runs yet</p>
              <p className="text-gray-600 text-xs mt-1">
                Pipeline triggers after {10} messages
              </p>
            </div>
          )}
        </div>

        {/* ── Operations Summary ── */}
        {Object.keys(operationSummary).length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
              </svg>
              DB Operations
            </h3>
            <div className="bg-gray-800 rounded-lg p-3">
              <div className="flex flex-wrap gap-2">
                {Object.entries(operationSummary).map(([op, count]) => (
                  <span key={op} className="text-xs bg-gray-700 text-gray-300 px-2 py-1 rounded">
                    {op}: <span className="text-white font-medium">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AnalyticsPanel;