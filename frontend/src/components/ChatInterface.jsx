import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import './ChatInterface.css';

function shortName(model) {
  return model.split('/')[1] || model;
}

function FailureNotice({ failures }) {
  const failed = [
    ...(failures?.stage1 || []).map((f) => ({ ...f, stage: 'Stage 1' })),
    ...(failures?.stage2 || []).map((f) => ({ ...f, stage: 'Stage 2' })),
  ];
  if (failed.length === 0) return null;

  return (
    <div className="failure-notice">
      {failed.map((f, i) => (
        <div key={i}>
          ⚠ {shortName(f.model)} failed in {f.stage}: {f.error}
        </div>
      ))}
    </div>
  );
}

function UsageLine({ metadata }) {
  const usage = metadata?.usage;
  if (!usage || (!usage.total_cost && !usage.total_tokens)) return null;
  const parts = [];
  if (usage.total_cost) parts.push(`$${usage.total_cost.toFixed(4)}`);
  if (usage.total_tokens) parts.push(`${usage.total_tokens.toLocaleString()} tokens`);
  const modeLabel = metadata.mode === 'quick' ? ' · quick mode' : '';
  const webLabel = metadata.web_search ? ' · web search' : '';
  return (
    <div className="usage-line">
      Cost: {parts.join(' · ')}{modeLabel}{webLabel}
    </div>
  );
}

export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
}) {
  const [input, setInput] = useState('');
  const [mode, setMode] = useState('full');
  const [webSearch, setWebSearch] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input, { mode, webSearch });
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to LLM Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className="message-group">
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-label">You</div>
                  <div className="message-content">
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assistant-message">
                  <div className="message-label">LLM Council</div>

                  {/* Stage 1 */}
                  {msg.loading?.stage1 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 1: Collecting individual responses...</span>
                    </div>
                  )}
                  {msg.stage1 && <Stage1 responses={msg.stage1} />}

                  {/* Stage 2 */}
                  {msg.loading?.stage2 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 2: Peer review...</span>
                    </div>
                  )}
                  {msg.stage2 && msg.stage2.length > 0 && (
                    <Stage2
                      rankings={msg.stage2}
                      labelToModel={msg.metadata?.label_to_model}
                      aggregateRankings={msg.metadata?.aggregate_rankings}
                    />
                  )}

                  {/* Stage 3 */}
                  {msg.loading?.stage3 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 3: Final synthesis...</span>
                    </div>
                  )}
                  {msg.stage3 && <Stage3 finalResponse={msg.stage3} />}

                  <FailureNotice failures={msg.metadata?.failures} />
                  <UsageLine metadata={msg.metadata} />

                  {msg.error && (
                    <div className="message-error">
                      Something went wrong: {msg.error}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Consulting the council...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form className="input-form" onSubmit={handleSubmit}>
        <div className="input-options">
          <label className="option-toggle" title="Full: 3-stage deliberation with anonymized peer review. Quick: individual answers + synthesis only (faster, cheaper).">
            <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={isLoading}>
              <option value="full">Full council</option>
              <option value="quick">Quick</option>
            </select>
          </label>
          <label className="option-toggle" title="Let council members search the web for current information">
            <input
              type="checkbox"
              checked={webSearch}
              onChange={(e) => setWebSearch(e.target.checked)}
              disabled={isLoading}
            />
            Web search
          </label>
        </div>
        <div className="input-row">
          <textarea
            className="message-input"
            placeholder="Ask your question... (Shift+Enter for new line, Enter to send)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={3}
          />
          <button
            type="submit"
            className="send-button"
            disabled={!input.trim() || isLoading}
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
