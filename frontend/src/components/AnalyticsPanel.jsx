import React, { useState, useEffect } from 'react';
import { getCoreMemory, searchMemories } from '../api/client';

function AnalyticsPanel({ sessionId, currentBlock, chatStats }) {
  const [coreMemory, setCoreMemory] = useState(null);
  const [loading, setLoading] = useState(false);

  // Fetch core memory when block changes
  useEffect(() => {
    if (currentBlock) {
      fetchCoreMemory();
    } else {
      setCoreMemory(null);
    }
  }, [currentBlock?.block_id]);

  // Update core memory from chat stats (live after each chat turn)
  useEffect(() => {
    if (chatStats?.core_memory) {
      setCoreMemory(chatStats.core_memory);
    }
  }, [chatStats?.core_memory]);

  const fetchCoreMemory = async () => {
    try {
      const memory = await getCoreMemory(currentBlock.block_id);
      setCoreMemory(memory);
    } catch (err) {
      console.error('Failed to fetch core memory:', err);
      setCoreMemory(null);
    }
  };

  const summary = chatStats?.summary || '';
  const pipelineRuns = chatStats?.pipeline_runs || [];
  const operationSummary = chatStats?.operation_summary || {};
  const memoryWindowSize = chatStats?.memory_window_size || 0;
  const currentMessageCount = chatStats?.current_message_count || 0;
  const processingTriggered = chatStats?.processing_triggered || false;

  // Estimate token counts
  const estimateTokens = (text) => {
    if (!text) return 0;
    return Math.ceil(text.length / 4); // rough 4 chars per token estimate
  };

  const coreTokens = estimateTokens(coreMemory?.persona_content) + estimateTokens(coreMemory?.human_content);
  const summaryTokens = estimateTokens(summary);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <h2 className="text-white font-semibold">Analytics & Memory</h2>
        {sessionId && (
          <p className="text-gray-500 text-xs mt-1 truncate">
            Session: {sessionId.replace('session_', '').slice(0, 12)}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">

        {/* ── Token Usage ── */}
        {/* <div>
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Token Usage (est.)
          </h3>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-gray-800 rounded-lg p-3 text-center">
              <p className="text-xl font-bold text-indigo-400">{coreTokens}</p>
              <p className="text-gray-500 text-xs">Core Memory</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-3 text-center">
              <p className="text-xl font-bold text-purple-400">{summaryTokens}</p>
              <p className="text-gray-500 text-xs">Summary</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-3 text-center">
              <p className="text-xl font-bold text-emerald-400">{memoryWindowSize}</p>
              <p className="text-gray-500 text-xs">Window Msgs</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-3 text-center">
              <p className="text-xl font-bold text-amber-400">{currentMessageCount}</p>
              <p className="text-gray-500 text-xs">Total Msgs</p>
            </div>
          </div>
        </div> */}

        {/* ── Core Memory ── */}
        <div>
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
            Core Memory
          </h3>
          <div className="bg-gray-800 rounded-lg p-4 space-y-3">
            {coreMemory && (coreMemory.persona_content || coreMemory.human_content) ? (
              <>
                {coreMemory.persona_content && (
                  <div>
                    <div className="flex items-center gap-1 mb-1">
                      <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
                      <h4 className="text-indigo-400 text-xs font-medium">Persona</h4>
                    </div>
                    <p className="text-gray-300 text-sm whitespace-pre-wrap leading-relaxed">
                      {coreMemory.persona_content}
                    </p>
                  </div>
                )}
                {coreMemory.human_content && (
                  <div>
                    <div className="flex items-center gap-1 mb-1">
                      <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                      <h4 className="text-emerald-400 text-xs font-medium">Human</h4>
                    </div>
                    <p className="text-gray-300 text-sm whitespace-pre-wrap leading-relaxed">
                      {coreMemory.human_content}
                    </p>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-2">
                <p className="text-gray-500 text-sm">No core memory yet</p>
                <p className="text-gray-600 text-xs mt-1">Core memory is built through conversations</p>
              </div>
            )}
          </div>
        </div>

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

        {/* ── Quick Search ── */}
        <div>
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            Search Memory
          </h3>
          <SearchSection blockId={currentBlock?.block_id} />
        </div>
      </div>
    </div>
  );
}

// Separate search component to keep state isolated
function SearchSection({ blockId }) {
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim() || !blockId) return;
    setSearching(true);
    try {
      const res = await searchMemories(blockId, searchQuery, 5);
      setResults(res);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleSearch}>
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search memories..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500"
          />
          <button
            type="submit"
            disabled={searching || !blockId}
            className="px-3 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </button>
        </div>
      </form>

      {results.length > 0 && (
        <div className="mt-3 space-y-2">
          {results.map((mem, idx) => (
            <div key={idx} className="bg-gray-800 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${mem.type === 'fact' ? 'bg-blue-500/20 text-blue-400' :
                    mem.type === 'event' ? 'bg-amber-500/20 text-amber-400' :
                      'bg-purple-500/20 text-purple-400'
                  }`}>
                  {mem.type}
                </span>
                <span className="text-gray-500 text-xs">
                  {Math.round((mem.confidence || 0) * 100)}%
                </span>
              </div>
              <p className="text-gray-300 text-sm">{mem.content}</p>
              {mem.keywords && mem.keywords.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {mem.keywords.slice(0, 4).map((kw, i) => (
                    <span key={i} className="text-xs bg-gray-700 text-gray-400 px-1.5 py-0.5 rounded">
                      {kw}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default AnalyticsPanel;
