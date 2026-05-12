import React, { useState, useEffect, useCallback } from 'react';
import * as api from '../api/client';

const TokenUsageDashboard = ({ isOpen, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tokenData, setTokenData] = useState(null);
  const [selectedBlock, setSelectedBlock] = useState(null);
  const [blockDetails, setBlockDetails] = useState(null);
  const [recentCalls, setRecentCalls] = useState([]);
  const [timeRange, setTimeRange] = useState(7);
  const [activeView, setActiveView] = useState('overview');

  const loadTokenUsage = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getTokenUsagePerBlock(timeRange);
      setTokenData(data);
    } catch (err) {
      setError(err.message);
      console.error('Failed to load token usage:', err);
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    if (isOpen) {
      loadTokenUsage();
    }
  }, [isOpen, loadTokenUsage]);

  const loadBlockDetails = async (blockId) => {
    try {
      const data = await api.getTokenUsageBlock(blockId, timeRange);
      setBlockDetails(data);
    } catch (err) {
      console.error('Failed to load block details:', err);
    }
  };

  const loadRecentCalls = async (blockId = null) => {
    try {
      const calls = await api.getRecentLlmCalls(blockId, 20);
      setRecentCalls(calls);
    } catch (err) {
      console.error('Failed to load recent calls:', err);
    }
  };

  const handleBlockClick = (blockId) => {
    setSelectedBlock(blockId);
    loadBlockDetails(blockId);
    loadRecentCalls(blockId);
    setActiveView('block');
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden border border-gray-700">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700 bg-gray-800">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Token Usage Dashboard
          </h2>
          <div className="flex items-center gap-3">
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(Number(e.target.value))}
              className="bg-gray-800 border border-gray-600 text-white text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-500"
            >
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
            </select>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors p-1"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {error ? (
            <div className="bg-red-500/10 border border-red-500/50 text-red-400 px-4 py-3 rounded-lg">
              {error}
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-500"></div>
            </div>
          ) : tokenData ? (
            <div className="space-y-6">
              {/* Overall Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  label="Total Requests"
                  value={tokenData.overall.total_requests}
                  color="blue"
                />
                <StatCard
                  label="Input Tokens"
                  value={formatNumber(tokenData.overall.total_input_tokens)}
                  color="purple"
                />
                <StatCard
                  label="Output Tokens"
                  value={formatNumber(tokenData.overall.total_output_tokens)}
                  color="amber"
                />
                <StatCard
                  label="Total Tokens"
                  value={formatNumber(tokenData.overall.total_tokens)}
                  color="green"
                />
              </div>

              {/* Per-Block Breakdown */}
              <div>
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                  Per-Block Usage
                </h3>
                
                {tokenData.blocks && Object.keys(tokenData.blocks).length > 0 ? (
                  <div className="space-y-3">
                    {Object.entries(tokenData.blocks).map(([blockId, data]) => (
                      <BlockUsageCard
                        key={blockId}
                        blockId={blockId}
                        data={data}
                        onClick={() => handleBlockClick(blockId)}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="bg-gray-800 rounded-lg p-8 text-center">
                    <p className="text-gray-500">No usage data for this period</p>
                    <p className="text-gray-600 text-sm mt-1">Start a conversation to see token usage tracked here</p>
                  </div>
                )}

                {tokenData.total_blocks_with_usage === 0 && (
                  <p className="text-gray-500 text-sm mt-4 text-center">
                    Start a conversation to see token usage here
                  </p>
                )}
              </div>

              {/* Block Detail View */}
              {activeView === 'block' && blockDetails && (
                <div className="mt-6 pt-6 border-t border-gray-700">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-white">
                      {blockDetails.block_name} - Detailed Breakdown
                    </h3>
                    <button
                      onClick={() => {
                        setActiveView('overview');
                        setSelectedBlock(null);
                        setBlockDetails(null);
                      }}
                      className="text-sm text-indigo-400 hover:text-indigo-300"
                    >
                      ← Back to Overview
                    </button>
                  </div>

                  {/* Call Type Breakdown */}
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
                    {Object.entries(blockDetails.by_call_type).map(([callType, data]) => (
                      <div key={callType} className="bg-gray-800 rounded-lg p-3">
                        <div className="text-xs text-gray-500 uppercase mb-1">{formatCallType(callType)}</div>
                        <div className="text-lg font-bold text-white">{formatNumber(data.total_tokens)}</div>
                        <div className="text-xs text-gray-500">{data.request_count} calls</div>
                        <div className="text-xs text-gray-600">{data.avg_latency_ms}ms avg</div>
                      </div>
                    ))}
                  </div>

                  {/* Recent Calls */}
                  {recentCalls.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 mb-3">Recent LLM Calls</h4>
                      <div className="space-y-2 max-h-64 overflow-y-auto">
                        {recentCalls.slice(0, 10).map((call, idx) => (
                          <div key={idx} className="bg-gray-800 rounded-lg p-3 flex items-center justify-between">
                            <div>
                              <span className={`text-xs px-2 py-0.5 rounded ${
                                call.call_type === 'conversation' ? 'bg-blue-500/20 text-blue-400' :
                                call.call_type === 'ps1_extraction' ? 'bg-purple-500/20 text-purple-400' :
                                call.call_type === 'ps2_conflict' ? 'bg-amber-500/20 text-amber-400' :
                                call.call_type === 'retrieval' ? 'bg-cyan-500/20 text-cyan-400' :
                                'bg-gray-500/20 text-gray-400'
                              }`}>
                                {formatCallType(call.call_type)}
                              </span>
                              <span className="text-gray-500 text-xs ml-2">{call.model}</span>
                            </div>
                            <div className="text-right">
                              <div className="text-white text-sm">{formatNumber(call.total_tokens)} tokens</div>
                              <div className="text-gray-600 text-xs">{call.latency_ms}ms</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              No data available
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 bg-gray-800/50">
          <p className="text-xs text-gray-500 text-center">
            Token usage is persisted to MongoDB for historical tracking.
          </p>
        </div>
      </div>
    </div>
  );
};

function StatCard({ label, value, color }) {
  const colorClasses = {
    blue: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
    amber: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    green: 'text-green-400 bg-green-500/10 border-green-500/20',
  };

  return (
    <div className={`rounded-lg p-4 border ${colorClasses[color]}`}>
      <div className="text-xs text-gray-400 uppercase mb-1">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}

function BlockUsageCard({ blockId, data, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full bg-gray-800 hover:bg-gray-750 rounded-lg p-4 text-left transition-colors border border-transparent hover:border-indigo-500/30"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="font-medium text-white">{data.block_name}</div>
        <div className="text-sm text-gray-400">{formatNumber(data.total_tokens)} tokens</div>
      </div>
      {data.block_description && (
        <div className="text-xs text-gray-500 mb-2">{data.block_description}</div>
      )}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span>{data.request_count} requests</span>
        <span>{(data.total_latency_ms / 1000).toFixed(1)}s total</span>
        <span>{data.avg_latency_ms}ms avg</span>
      </div>
      <div className="flex gap-2 mt-2">
        {Object.entries(data.by_call_type).slice(0, 3).map(([type, dt]) => (
          <span key={type} className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded">
            {formatCallType(type)}: {formatNumber(dt.total_tokens)}
          </span>
        ))}
      </div>
    </button>
  );
}

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

function formatCallType(callType) {
  const labels = {
    'conversation': 'Chat',
    'ps1_extraction': 'Extraction',
    'ps2_conflict': 'Conflict',
    'retrieval': 'Retrieval',
    'core_memory': 'Core',
    'summary': 'Summary',
  };
  return labels[callType] || callType;
}

export default TokenUsageDashboard;