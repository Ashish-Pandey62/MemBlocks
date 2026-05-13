import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  createSession,
  sendMessage,
  getFullSessionContext,
  listBlockSessions,
  saveActiveSession,
  getActiveSession,
  flushSession,
} from '../api/client';

function ChatInterface({ activeBlocks, sessionId, onSessionChange, onChatStats }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [currentBlock, setCurrentBlock] = useState(null);
  const [error, setError] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [showSessionList, setShowSessionList] = useState(false);
  const [resuming, setResuming] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const ignoreNextLoadRef = useRef(false);

  // Track current block
  useEffect(() => {
    if (activeBlocks.length > 0 && !currentBlock) {
      setCurrentBlock(activeBlocks[0]);
    } else if (activeBlocks.length === 0) {
      setCurrentBlock(null);
    } else if (currentBlock && !activeBlocks.find(b => b.block_id === currentBlock.block_id)) {
      setCurrentBlock(activeBlocks[0]);
    } else if (activeBlocks.length === 1 && activeBlocks[0].block_id !== currentBlock?.block_id) {
      setCurrentBlock(activeBlocks[0]);
    }
  }, [activeBlocks]);

  // Clear messages when sessionId becomes null (block switched)
  useEffect(() => {
    if (!sessionId && currentBlock) {
      setMessages([]);
    }
  }, [sessionId, currentBlock]);

  // Load session list when block changes (no auto-resume)
  useEffect(() => {
    if (!currentBlock) return;

    const loadSessions = async () => {
      try {
        const blockSessions = await listBlockSessions(currentBlock.block_id);
        setSessions(blockSessions);
      } catch (err) {
        console.error('Failed to list sessions:', err);
      }
    };

    loadSessions();
  }, [currentBlock?.block_id]);

  // Load full context when session changes externally
  useEffect(() => {
    if (sessionId && !resuming) {
      if (ignoreNextLoadRef.current) {
        ignoreNextLoadRef.current = false;
        return;
      }
      loadFullContext();
    }
  }, [sessionId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (sessionId && inputRef.current) {
      inputRef.current.focus();
    }
  }, [sessionId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadFullContext = async () => {
    if (!sessionId) return;
    try {
      const ctx = await getFullSessionContext(sessionId);
      if (ctx) {
        setMessages(ctx.messages || []);
        if (onChatStats) {
          onChatStats({
            core_memory: ctx.core_memory,
            summary: ctx.summary,
            pipeline_runs: ctx.pipeline_runs,
            message_count: ctx.message_count,
          });
        }
      }
    } catch (err) {
      console.error('Failed to load full context:', err);
    }
  };

  const handleStartSession = async () => {
    if (!currentBlock) return;
    setError(null);
    try {
      // Flush current session before abandoning it to ensure recent messages are processed
      if (sessionId) {
        try {
          // Fire and forget so we don't wait for the frontend blocked response
          flushSession(sessionId).catch(e => console.error(e));
        } catch (e) {
          console.error('Failed to flush prior session context:', e);
        }
      }

      ignoreNextLoadRef.current = true;
      const session = await createSession(currentBlock.block_id);
      onSessionChange(session.session_id);
      saveActiveSession(currentBlock.block_id, session.session_id);
      setMessages([]);
      // Refresh session list
      const blockSessions = await listBlockSessions(currentBlock.block_id);
      setSessions(blockSessions);
    } catch (err) {
      console.error('Failed to start session:', err);
      setError('Failed to start session: ' + err.message);
    }
  };

  const handleResumeSession = async (sid) => {
    setShowSessionList(false);
    setResuming(true);
    try {
      const ctx = await getFullSessionContext(sid);
      if (ctx) {
        setMessages(ctx.messages || []);
        onSessionChange(sid);
        saveActiveSession(currentBlock.block_id, sid);
        if (onChatStats) {
          onChatStats({
            core_memory: ctx.core_memory,
            summary: ctx.summary,
            pipeline_runs: ctx.pipeline_runs,
            message_count: ctx.message_count,
          });
        }
      }
    } catch (err) {
      console.error('Failed to resume session:', err);
      setError('Failed to resume session: ' + err.message);
    } finally {
      setResuming(false);
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || !sessionId || loading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const response = await sendMessage(sessionId, userMessage);
      setMessages(prev => [...prev, { role: 'assistant', content: response.response }]);

      // Push updated stats to parent (AnalyticsPanel)
      if (onChatStats) {
        onChatStats({
          core_memory: response.core_memory,
          summary: response.summary,
          processing_triggered: response.processing_triggered,
          pipeline_runs: response.pipeline_runs,
          operation_summary: response.operation_summary,
          memory_window_size: response.memory_window_size,
          current_message_count: response.current_message_count,
          memory_context_used: response.memory_context_used,
        });
      }
    } catch (err) {
      console.error('Failed to send message:', err);
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, something went wrong: ' + err.message }]);
    } finally {
      setLoading(false);
    }
  };

  if (!currentBlock) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-950">
        <div className="text-center p-8">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gray-800 flex items-center justify-center">
            <svg className="w-8 h-8 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <h3 className="text-gray-400 text-lg font-medium mb-2">Select a block to start</h3>
          <p className="text-gray-500 text-sm">Check a memory block in the sidebar to start chatting</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-gray-950">
      {/* Chat Header */}
      <div className="flex-none p-4 border-b border-gray-800">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-white font-semibold">{currentBlock.name}</h2>
            <p className="text-gray-500 text-sm">
              {sessionId ? `Session active • ${messages.length} messages` : 'No active session'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Session list toggle */}
            {sessions.length > 0 && (
              <div className="relative">
                <button
                  onClick={() => setShowSessionList(!showSessionList)}
                  className="px-3 py-2 bg-gray-800 text-gray-300 text-sm rounded-lg hover:bg-gray-700 transition-colors flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Sessions ({sessions.length})
                </button>

                {showSessionList && (
                  <div className="absolute right-0 top-full mt-1 w-72 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 max-h-60 overflow-y-auto">
                    {sessions.map((s) => (
                      <button
                        key={s.session_id}
                        onClick={() => handleResumeSession(s.session_id)}
                        className={`w-full text-left px-4 py-3 hover:bg-gray-700 transition-colors border-b border-gray-700 last:border-0 ${s.session_id === sessionId ? 'bg-indigo-600/20 border-l-2 border-l-indigo-500' : ''
                          }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-white text-sm font-medium truncate">
                            {s.session_id.replace('session_', '').slice(0, 8)}
                          </span>
                          <span className="text-gray-400 text-xs">{s.message_count} msgs</span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-gray-500 text-xs">
                            {new Date(s.created_at).toLocaleDateString()}
                          </span>
                          {s.has_summary && (
                            <span className="text-emerald-400 text-xs">● has summary</span>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* New session button */}
            <button
              onClick={handleStartSession}
              className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors cursor-pointer"
            >
              {sessionId ? 'New Chat' : 'Start Chat'}
            </button>
          </div>
        </div>
        {error && (
          <div className="mt-2 p-2 bg-red-500/20 text-red-400 text-sm rounded">
            {error}
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {resuming ? (
          <div className="flex flex-col items-center justify-center h-full">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500 mb-4"></div>
            <p className="text-gray-400 text-sm">Resuming session...</p>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h3 className="text-white font-medium mb-1">Ready to chat</h3>
            <p className="text-gray-500 text-sm max-w-xs">
              Your messages will be stored in {currentBlock.name} and used to build context
            </p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[70%] px-4 py-2 rounded-2xl ${msg.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-100'
                  }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                {msg.timestamp && (
                  <p className={`text-xs mt-1 ${msg.role === 'user' ? 'text-indigo-300' : 'text-gray-500'}`}>
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                )}
              </div>
            </div>
          ))
        )}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 px-4 py-2 rounded-2xl">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="flex-none p-4 border-t border-gray-800">
        <form onSubmit={handleSend} className="flex gap-3">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={sessionId ? "Type your message..." : "Click 'Start Chat' to begin"}
            readOnly={!sessionId}
            className={`flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 ${!sessionId ? 'opacity-50 cursor-not-allowed' : ''}`}
          />
          <button
            type="submit"
            disabled={!sessionId || loading || !input.trim()}
            className="px-6 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}

export default ChatInterface;
