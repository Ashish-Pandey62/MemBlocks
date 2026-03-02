import React, { useState, useEffect } from 'react';
import * as api from '../api/client';

/**
 * BlockSelector Component
 * Handles memory block selection and creation
 */
const BlockSelector = ({ currentUser, currentBlock, onBlockSelect }) => {
  const [blocks, setBlocks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newBlockName, setNewBlockName] = useState('');
  const [newBlockDescription, setNewBlockDescription] = useState('');

  // Load blocks when user changes
  useEffect(() => {
    if (currentUser) {
      loadBlocks();
    } else {
      setBlocks([]);
      onBlockSelect(null);
    }
  }, [currentUser]);

  const loadBlocks = async () => {
    try {
      setLoading(true);
      setError(null);
      const fetchedBlocks = await api.listBlocks(currentUser.user_id);
      setBlocks(fetchedBlocks);
    } catch (err) {
      setError(err.message);
      console.error('Failed to load blocks:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateBlock = async (e) => {
    e.preventDefault();
    if (!newBlockName.trim()) {
      setError('Block name cannot be empty');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const createdBlock = await api.createBlock(
        currentUser.user_id,
        newBlockName.trim(),
        newBlockDescription.trim()
      );
      setBlocks([...blocks, createdBlock]);
      onBlockSelect(createdBlock);
      setNewBlockName('');
      setNewBlockDescription('');
      setShowCreateForm(false);
    } catch (err) {
      setError(err.message);
      console.error('Failed to create block:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectBlock = (e) => {
    const blockId = e.target.value;
    if (blockId) {
      const block = blocks.find(b => b.meta_data.id === blockId);
      onBlockSelect(block);
    } else {
      onBlockSelect(null);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-4">
      <h2 className="text-xl font-bold mb-4 text-gray-800">🧩 Memory Block Selection</h2>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
      )}

      {!currentUser ? (
        <div className="text-gray-500 italic py-4">
          Please select a user first
        </div>
      ) : (
        <>
          {/* Block Selection Dropdown */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select Memory Block
            </label>
            <select
              value={currentBlock?.meta_data?.id || ''}
              onChange={handleSelectBlock}
              disabled={loading}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100"
            >
              <option value="">-- Select a block --</option>
              {blocks.map((block) => (
                <option key={block.meta_data.id} value={block.meta_data.id}>
                  {block.name}
                </option>
              ))}
            </select>
          </div>

          {/* Create New Block Toggle */}
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="text-primary-600 hover:text-primary-700 text-sm font-medium mb-4"
          >
            {showCreateForm ? '− Cancel' : '+ Create New Block'}
          </button>

          {/* Create Block Form */}
          {showCreateForm && (
            <form onSubmit={handleCreateBlock} className="mt-4 p-4 bg-gray-50 rounded-md">
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Block Name *
                </label>
                <input
                  type="text"
                  value={newBlockName}
                  onChange={(e) => setNewBlockName(e.target.value)}
                  placeholder="e.g., Work Projects"
                  disabled={loading}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100"
                />
              </div>

              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Description (optional)
                </label>
                <textarea
                  value={newBlockDescription}
                  onChange={(e) => setNewBlockDescription(e.target.value)}
                  placeholder="Describe what this memory block is for..."
                  disabled={loading}
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100"
                />
              </div>

              <button
                type="submit"
                disabled={loading || !newBlockName.trim()}
                className="w-full px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                {loading ? 'Creating...' : 'Create Block'}
              </button>
            </form>
          )}
        </>
      )}

      {loading && (
        <div className="flex items-center justify-center py-4">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-600"></div>
        </div>
      )}
    </div>
  );
};

export default BlockSelector;
