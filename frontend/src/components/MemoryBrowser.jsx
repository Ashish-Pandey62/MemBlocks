import React, { useState, useEffect, useCallback } from 'react';
import * as api from '../api/client';

const MemoryBrowser = ({ isOpen, onClose, blocks, currentBlock, onSelectBlock }) => {
  const [selectedBlock, setSelectedBlock] = useState(null);
  const [memories, setMemories] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('core');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (currentBlock && isOpen) {
      setSelectedBlock(currentBlock);
    } else if (blocks && blocks.length > 0 && isOpen) {
      setSelectedBlock(blocks[0]);
    }
  }, [isOpen, currentBlock, blocks]);

  useEffect(() => {
    if (selectedBlock) {
      loadMemories(selectedBlock.block_id);
    }
  }, [selectedBlock?.block_id]);

  const loadMemories = async (blockId) => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getAllBlockMemories(blockId, 10, 0);
      setMemories(data);
    } catch (err) {
      setError(err.message);
      console.error('Failed to load memories:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadMoreMemories = async () => {
    if (!memories || !memories.pagination.has_more || loadingMore) return;
    
    try {
      setLoadingMore(true);
      const data = await api.getAllBlockMemories(
        selectedBlock.block_id,
        10,
        memories.pagination.offset + memories.pagination.loaded
      );
      
      setMemories({
        ...data,
        semantic_memories: [
          ...memories.semantic_memories,
          ...data.semantic_memories
        ],
        pagination: data.pagination,
      });
    } catch (err) {
      console.error('Failed to load more memories:', err);
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim() || !selectedBlock) return;
    
    try {
      setSearching(true);
      const results = await api.searchBlockMemory(
        selectedBlock.block_id,
        searchQuery,
        'all',
        20
      );
      setSearchResults(results);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setSearching(false);
    }
  }, [searchQuery, selectedBlock]);

  useEffect(() => {
    const debounce = setTimeout(() => {
      if (searchQuery.trim()) {
        handleSearch();
      } else {
        setSearchResults(null);
      }
    }, 300);
    
    return () => clearTimeout(debounce);
  }, [searchQuery, handleSearch]);

  const handleBlockSelect = (block) => {
    setSelectedBlock(block);
    setSearchQuery('');
    setSearchResults(null);
    if (onSelectBlock) onSelectBlock(block);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-xl shadow-2xl w-full max-w-6xl max-h-[90vh] flex flex-col overflow-hidden border border-gray-700">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700 bg-gray-800">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            My Memories
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors p-1"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Block List Sidebar */}
          <div className="w-64 border-r border-gray-700 bg-gray-800/50 overflow-y-auto">
            <div className="p-3">
              <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                Select Block
              </h3>
              <div className="space-y-1">
                {blocks && blocks.length > 0 ? (
                  blocks.map(block => (
                    <button
                      key={block.block_id}
                      onClick={() => handleBlockSelect(block)}
                      className={`w-full text-left p-2 rounded-lg transition-all ${
                        selectedBlock?.block_id === block.block_id
                          ? 'bg-indigo-600/20 border border-indigo-500/50 text-white'
                          : 'hover:bg-gray-700/50 text-gray-300 hover:text-white'
                      }`}
                    >
                      <div className="text-sm font-medium truncate">{block.name}</div>
                      {block.description && (
                        <div className="text-xs text-gray-500 truncate">{block.description}</div>
                      )}
                    </button>
                  ))
                ) : (
                  <p className="text-gray-500 text-sm text-center py-4">No blocks found</p>
                )}
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Search Bar */}
            <div className="p-4 border-b border-gray-700 bg-gray-800/30">
              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={`Search in ${selectedBlock?.name || 'selected block'}...`}
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-4 py-2 pl-10 text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
                />
                <svg className="w-5 h-5 absolute left-3 top-2.5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                {searching && (
                  <div className="absolute right-3 top-2.5">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-500"></div>
                  </div>
                )}
              </div>
            </div>

            {/* Search Results or Memory Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {error ? (
                <div className="bg-red-500/10 border border-red-500/50 text-red-400 px-4 py-3 rounded-lg">
                  {error}
                </div>
              ) : loading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500"></div>
                </div>
              ) : searchResults ? (
                <SearchResultsView results={searchResults} />
              ) : memories ? (
                <MemoryContentView
                  memories={memories}
                  activeTab={activeTab}
                  setActiveTab={setActiveTab}
                  onLoadMore={loadMoreMemories}
                  loadingMore={loadingMore}
                />
              ) : (
                <div className="text-center py-12 text-gray-500">
                  Select a block to view its memories
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

function SearchResultsView({ results }) {
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-white">
        Search Results
      </h3>
      
      {results.core_matches && Object.keys(results.core_matches).length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4">
          <h4 className="text-sm font-medium text-indigo-400 mb-2">Core Memory Matches</h4>
          {results.core_matches.persona_content && (
            <div className="mb-2">
              <span className="text-xs text-gray-500">Persona:</span>
              <p className="text-gray-300 text-sm whitespace-pre-wrap">{results.core_matches.persona_content}</p>
            </div>
          )}
          {results.core_matches.human_content && (
            <div>
              <span className="text-xs text-gray-500">Human:</span>
              <p className="text-gray-300 text-sm whitespace-pre-wrap">{results.core_matches.human_content}</p>
            </div>
          )}
        </div>
      )}

      {results.semantic_matches && results.semantic_matches.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-400">Semantic Memories ({results.semantic_matches.length})</h4>
          {results.semantic_matches.map((mem, idx) => (
            <div key={idx} className="bg-gray-800 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                  mem.type === 'event' ? 'bg-amber-500/20 text-amber-400' :
                  mem.type === 'fact' ? 'bg-blue-500/20 text-blue-400' :
                  'bg-purple-500/20 text-purple-400'
                }`}>
                  {mem.type}
                </span>
                {mem.memory_time && (
                  <span className="text-gray-500 text-xs">
                    {new Date(mem.memory_time).toLocaleDateString()}
                  </span>
                )}
              </div>
              <p className="text-gray-300 text-sm whitespace-pre-wrap">{mem.content}</p>
            </div>
          ))}
        </div>
      )}

      {(!results.core_matches || Object.keys(results.core_matches).length === 0) && 
       (!results.semantic_matches || results.semantic_matches.length === 0) && (
        <p className="text-gray-500 text-center py-8">No matches found</p>
      )}
    </div>
  );
}

function MemoryContentView({ memories, activeTab, setActiveTab, onLoadMore, loadingMore }) {
  return (
    <div>
      {/* Tabs */}
      <div className="flex gap-2 mb-4 border-b border-gray-700 pb-2">
        <button
          onClick={() => setActiveTab('core')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'core'
              ? 'bg-indigo-600 text-white'
              : 'text-gray-400 hover:text-white hover:bg-gray-800'
          }`}
        >
          Core Memory
        </button>
        <button
          onClick={() => setActiveTab('semantic')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'semantic'
              ? 'bg-indigo-600 text-white'
              : 'text-gray-400 hover:text-white hover:bg-gray-800'
          }`}
        >
          Semantic ({memories.pagination.total_semantic})
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'core' && (
        <div className="space-y-4">
          {memories.core_memory ? (
            <>
              {memories.core_memory.persona_content && (
                <div className="bg-gray-800 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-indigo-400 mb-2 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
                    Persona
                  </h4>
                  <p className="text-gray-300 text-sm whitespace-pre-wrap">
                    {memories.core_memory.persona_content}
                  </p>
                </div>
              )}
              {memories.core_memory.human_content && (
                <div className="bg-gray-800 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-emerald-400 mb-2 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                    Human Facts
                  </h4>
                  <p className="text-gray-300 text-sm whitespace-pre-wrap">
                    {memories.core_memory.human_content}
                  </p>
                </div>
              )}
              {!memories.core_memory.persona_content && !memories.core_memory.human_content && (
                <p className="text-gray-500 text-center py-8">No core memory yet</p>
              )}
            </>
          ) : (
            <p className="text-gray-500 text-center py-8">No core memory for this block</p>
          )}
        </div>
      )}

      {activeTab === 'semantic' && (
        <div className="space-y-3">
          {memories.semantic_memories && memories.semantic_memories.length > 0 ? (
            <>
              {memories.semantic_memories.map((mem, idx) => (
                <div key={mem.id || idx} className="bg-gray-800 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      mem.type === 'event' ? 'bg-amber-500/20 text-amber-400' :
                      mem.type === 'fact' ? 'bg-blue-500/20 text-blue-400' :
                      'bg-purple-500/20 text-purple-400'
                    }`}>
                      {mem.type}
                    </span>
                    {mem.memory_time && (
                      <span className="text-gray-500 text-xs">
                        {new Date(mem.memory_time).toLocaleDateString()}
                      </span>
                    )}
                    {mem.source && (
                      <span className="text-gray-600 text-xs">• {mem.source}</span>
                    )}
                  </div>
                  <p className="text-gray-300 text-sm whitespace-pre-wrap">{mem.content}</p>
                  {mem.keywords && mem.keywords.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {mem.keywords.map((kw, i) => (
                        <span key={i} className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded">
                          {kw}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              
              {memories.pagination.has_more && (
                <button
                  onClick={onLoadMore}
                  disabled={loadingMore}
                  className="w-full py-3 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors disabled:opacity-50"
                >
                  {loadingMore ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-400"></div>
                      Loading...
                    </span>
                  ) : (
                    `Load More (${memories.pagination.total_semantic - memories.pagination.loaded} remaining)`
                  )}
                </button>
              )}
            </>
          ) : (
            <p className="text-gray-500 text-center py-8">No semantic memories yet</p>
          )}
        </div>
      )}
    </div>
  );
}

export default MemoryBrowser;