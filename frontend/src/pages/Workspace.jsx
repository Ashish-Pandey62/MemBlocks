import React, { useState, useEffect, useRef } from 'react';
import { useAuth, useUser } from '@clerk/react';
import { setAuthToken, getCurrentUser, listBlocks, createBlock, deleteBlock } from '../api/client';
import BlockManager from '../components/BlockManager';
import ChatInterface from '../components/ChatInterface';
import AnalyticsPanel from '../components/AnalyticsPanel';
import MemoryBrowser from '../components/MemoryBrowser';
import TokenUsageDashboard from '../components/TokenUsageDashboard';

function Workspace() {
  const { user, isLoaded } = useUser();
  const { getToken, signOut } = useAuth();
  const [blocks, setBlocks] = useState([]);
  const [activeBlocks, setActiveBlocks] = useState([]);
  const [currentBlock, setCurrentBlock] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [chatStats, setChatStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tokenReady, setTokenReady] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newBlockName, setNewBlockName] = useState('');
  const [newBlockDescription, setNewBlockDescription] = useState('');
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);
  const [blockError, setBlockError] = useState(null);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showMemoryBrowser, setShowMemoryBrowser] = useState(false);
  const [showTokenUsage, setShowTokenUsage] = useState(false);
  const userMenuRef = useRef(null);

  useEffect(() => {
    const initAuth = async () => {
      if (!user) {
        setLoading(false);
        return;
      }
      try {
        let token = await getToken();
        let attempts = 0;
        while (!token && attempts < 5) {
          await new Promise(r => setTimeout(r, 500));
          token = await getToken();
          attempts++;
        }

        if (!token) {
          console.error('Failed to get token after attempts');
          setLoading(false);
          return;
        }

        setAuthToken(token);
        setTokenReady(true);
        await fetchBlocks();
      } catch (err) {
        console.error('Auth error:', err);
      } finally {
        setLoading(false);
      }
    };

    if (isLoaded) {
      initAuth();
    }
  }, [isLoaded, user, getToken]);

  const fetchBlocks = async () => {
    try {
      const userId = user?.id;
      console.log('Fetching blocks for user:', userId);
      if (userId) {
        const userBlocks = await listBlocks(userId);
        console.log('Blocks:', userBlocks);
        setBlocks(userBlocks);
      }
    } catch (err) {
      console.error('Failed to fetch blocks:', err);
      setBlockError(err.message);
    }
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSignOut = async () => {
    await signOut();
    window.location.href = '/';
  };

  const handleCreateBlock = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      console.log('Creating block:', newBlockName, newBlockDescription);
      const newBlock = await createBlock(newBlockName, newBlockDescription);
      console.log('Block created:', newBlock);
      setShowCreateModal(false);
      setNewBlockName('');
      setNewBlockDescription('');
      await fetchBlocks();
      setActiveBlocks([...activeBlocks, newBlock]);
      setCurrentBlock(newBlock);
    } catch (err) {
      console.error('Failed to create block:', err);
      setError(err.message || 'Failed to create block');
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteBlock = async (blockId) => {
    try {
      await deleteBlock(blockId);
      await fetchBlocks();
      setActiveBlocks(activeBlocks.filter(b => b.block_id !== blockId));
      if (currentBlock?.block_id === blockId) {
        setCurrentBlock(null);
        setChatStats(null);
      }
    } catch (err) {
      console.error('Failed to delete block:', err);
    }
  };

  const handleToggleBlock = (block) => {
    const isActive = activeBlocks.some(b => b.block_id === block.block_id);
    if (isActive) {
      setActiveBlocks(activeBlocks.filter(b => b.block_id !== block.block_id));
    } else {
      setActiveBlocks([...activeBlocks, block]);
    }
  };

  const handleSelectBlock = (block) => {
    setCurrentBlock(block);
    setChatStats(null); // Reset stats when changing blocks
    if (!activeBlocks.some(b => b.block_id === block.block_id)) {
      setActiveBlocks([...activeBlocks, block]);
    }
  };

  const handleChatStats = (stats) => {
    setChatStats(stats);
  };

  if (loading || !isLoaded) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-gray-950 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="flex-none h-14 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-4 relative">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg overflow-hidden">
            <img src="/logo.png" alt="MemBlocks" className="w-full h-full object-cover" />
          </div>
          <span className="text-white font-semibold text-lg">MemBlocks</span>
        </div>

        {/* Active Context Display */}
        <div className="flex items-center gap-2">
          <span className="text-gray-400 text-sm">Current Context:</span>
          {activeBlocks.length === 0 ? (
            <span className="text-gray-500 text-sm italic">No blocks selected</span>
          ) : (
            <div className="flex gap-1">
              {activeBlocks.slice(0, 3).map(block => (
                <span
                  key={block.block_id}
                  className="px-2 py-1 bg-indigo-600/20 text-indigo-400 text-xs rounded-md flex items-center gap-1"
                >
                  {block.name}
                  <button
                    onClick={() => handleToggleBlock(block)}
                    className="hover:text-white"
                  >
                    ×
                  </button>
                </span>
              ))}
              {activeBlocks.length > 3 && (
                <span className="text-gray-400 text-xs">+{activeBlocks.length - 3}</span>
              )}
            </div>
          )}
        </div>
        
        {/* Additional Tools */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowMemoryBrowser(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-300 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
            title="View all memories"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <span className="hidden sm:inline">My Memories</span>
          </button>
          <button
            onClick={() => setShowTokenUsage(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-300 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
            title="Token usage dashboard"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <span className="hidden sm:inline">Usage</span>
          </button>
        </div>

        <div className="flex items-center gap-3" ref={userMenuRef}>
          {user?.imageUrl && (
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="relative"
            >
              <img
                src={user.imageUrl}
                alt={user.fullName}
                className="w-8 h-8 rounded-full border border-gray-700 hover:border-gray-500 transition-colors cursor-pointer"
              />
            </button>
          )}
          {showUserMenu && (
            <div className="absolute top-12 right-0 z-50 w-48 bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1">
              <div className="px-4 py-3 border-b border-gray-700">
                <p className="text-white text-sm font-medium truncate">{user?.fullName}</p>
                <p className="text-gray-400 text-xs truncate">{user?.primaryEmailAddress?.emailAddress}</p>
              </div>
              <button
                onClick={() => setShowUserMenu(false)}
                className="w-full px-4 py-2 text-left text-gray-300 hover:bg-gray-700 flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
                Profile
              </button>
              <button
                onClick={handleSignOut}
                className="w-full px-4 py-2 text-left text-red-400 hover:bg-gray-700 flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
                Sign Out
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main 3-Panel Layout */}
      <main className="flex-1 flex overflow-hidden">
        {blockError && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 z-50 bg-red-500/20 border border-red-500/50 text-red-400 px-4 py-2 rounded-lg">
            Error: {blockError}
            <button onClick={() => setBlockError(null)} className="ml-2">×</button>
          </div>
        )}
        {/* Left Panel - Block Manager */}
        <div className="w-72 flex-none bg-gray-900 border-r border-gray-800 flex flex-col">
          <BlockManager
            blocks={blocks}
            activeBlocks={activeBlocks}
            currentBlock={currentBlock}
            onSelectBlock={handleSelectBlock}
            onToggleBlock={handleToggleBlock}
            onDeleteBlock={handleDeleteBlock}
            onCreateBlock={() => setShowCreateModal(true)}
          />
        </div>

        {/* Center Panel - Chat Interface */}
        <div className="flex-1 flex flex-col min-w-0">
          <ChatInterface
            activeBlocks={activeBlocks}
            sessionId={sessionId}
            onSessionChange={setSessionId}
            onChatStats={handleChatStats}
          />
        </div>

        {/* Right Panel - Analytics */}
        <div className="w-80 flex-none bg-gray-900 border-l border-gray-800">
          <AnalyticsPanel
            sessionId={sessionId}
            currentBlock={currentBlock}
            chatStats={chatStats}
          />
        </div>
      </main>

      {/* Create Block Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-xl p-6 w-full max-w-md border border-gray-800">
            <h2 className="text-xl font-semibold text-white mb-4">Create Memory Block</h2>
            <form onSubmit={handleCreateBlock}>
              <div className="mb-4">
                <label className="block text-gray-400 text-sm mb-2">Block Name</label>
                <input
                  type="text"
                  value={newBlockName}
                  onChange={(e) => setNewBlockName(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500"
                  placeholder="e.g., Research Notes"
                  required
                />
              </div>
              <div className="mb-6">
                <label className="block text-gray-400 text-sm mb-2">Description</label>
                <textarea
                  value={newBlockDescription}
                  onChange={(e) => setNewBlockDescription(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 h-24 resize-none"
                  placeholder="What kind of information will this block store?"
                />
              </div>
              <div className="flex gap-3">
                {error && (
                  <div className="w-full mb-3 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                    {error}
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || !newBlockName.trim()}
                  className="flex-1 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Create Block'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Memory Browser Modal */}
      <MemoryBrowser
        isOpen={showMemoryBrowser}
        onClose={() => setShowMemoryBrowser(false)}
        blocks={blocks}
        currentBlock={currentBlock}
        onSelectBlock={handleSelectBlock}
      />

      {/* Token Usage Dashboard Modal */}
      <TokenUsageDashboard
        isOpen={showTokenUsage}
        onClose={() => setShowTokenUsage(false)}
      />
    </div>
  );
}

export default Workspace;
