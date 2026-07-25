import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { api } from '../api';
import { EmptyState, Loading } from './shared';
import { formatCost } from '../format';

/**
 * The original multi-model council, retained for open research questions that
 * are not a specific notice — "what is the position on X", reading a circular,
 * comparing arguments. The Compliance Panel is for matters; this is for
 * thinking.
 */
export default function GeneralCouncil({ onAuthError }) {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [conversation, setConversation] = useState(null);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState('full');
  const [webSearch, setWebSearch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const endRef = useRef(null);

  const loadList = async () => {
    try {
      setConversations(await api.listConversations());
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  useEffect(() => {
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activeId) return;
    (async () => {
      try {
        setConversation(await api.getConversation(activeId));
      } catch (err) {
        if (!onAuthError(err)) setError(err.message);
      }
    })();
  }, [activeId, onAuthError]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation]);

  const startNew = async () => {
    try {
      const created = await api.createConversation();
      setConversations((list) => [
        { id: created.id, created_at: created.created_at, title: created.title, message_count: 0 },
        ...list,
      ]);
      setActiveId(created.id);
      setConversation(created);
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  const updateLast = (updater) => {
    setConversation((prev) => {
      if (!prev) return prev;
      const messages = [...prev.messages];
      const last = { ...messages[messages.length - 1] };
      updater(last);
      messages[messages.length - 1] = last;
      return { ...prev, messages };
    });
  };

  const send = async () => {
    if (!activeId || !input.trim() || busy) return;
    setBusy(true);
    setError('');
    const content = input;
    setInput('');

    setConversation((prev) => ({
      ...prev,
      messages: [
        ...prev.messages,
        { role: 'user', content },
        { role: 'assistant', stage1: null, stage3: null, metadata: null, loading: {} },
      ],
    }));

    try {
      await api.sendMessageStream(activeId, content, { mode, webSearch }, (type, event) => {
        switch (type) {
          case 'stage1_start':
            updateLast((m) => { m.loading = { ...m.loading, stage1: true }; });
            break;
          case 'stage1_complete':
            updateLast((m) => { m.stage1 = event.data; m.loading = { ...m.loading, stage1: false }; });
            break;
          case 'stage3_start':
            updateLast((m) => { m.loading = { ...m.loading, stage3: true }; });
            break;
          case 'stage3_complete':
            updateLast((m) => { m.stage3 = event.data; m.loading = { ...m.loading, stage3: false }; });
            break;
          case 'summary':
            updateLast((m) => { m.metadata = event.metadata; });
            break;
          case 'complete':
            loadList();
            setBusy(false);
            break;
          case 'error':
            setError(event.message);
            setBusy(false);
            break;
          default:
            break;
        }
      });
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">General Council</h1>
          <div className="page-subtitle">
            Multi-model deliberation for open research questions. For a specific
            notice, use New Matter instead.
          </div>
        </div>
        <button className="btn btn-primary" onClick={startNew}>New thread</button>
      </div>

      {error && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="council-layout">
        <div className="card council-threads">
          <div className="card-pad" style={{ paddingBottom: 'var(--sp-2)' }}>
            <div className="section-title" style={{ margin: 0 }}>Threads</div>
          </div>
          {conversations.length === 0 ? (
            <div className="muted" style={{ padding: 'var(--sp-4)', fontSize: 'var(--text-sm)' }}>
              No threads yet.
            </div>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                className={`thread-item ${activeId === c.id ? 'active' : ''}`}
                onClick={() => setActiveId(c.id)}
              >
                <div className="thread-title">{c.title || 'New thread'}</div>
                <div className="muted" style={{ fontSize: 'var(--text-xs)' }}>
                  {c.message_count} messages
                </div>
              </button>
            ))
          )}
        </div>

        <div className="card council-thread">
          {!conversation ? (
            <EmptyState title="Select or start a thread">
              Ask a research question and the council will answer, review each
              other's answers, and synthesise.
            </EmptyState>
          ) : (
            <>
              <div className="council-messages">
                {conversation.messages.length === 0 && (
                  <div className="empty muted">Ask your first question.</div>
                )}
                {conversation.messages.map((msg, i) => (
                  <div key={i} className="council-message">
                    {msg.role === 'user' ? (
                      <>
                        <div className="section-title">You</div>
                        <div className="user-bubble">{msg.content}</div>
                      </>
                    ) : (
                      <>
                        <div className="section-title">Council</div>
                        {msg.loading?.stage1 && <Loading label="Collecting opinions…" />}
                        {msg.loading?.stage3 && <Loading label="Synthesising…" />}
                        {msg.stage3 && (
                          <div className="markdown-content">
                            <ReactMarkdown>{msg.stage3.response}</ReactMarkdown>
                          </div>
                        )}
                        {msg.metadata?.usage?.total_cost > 0 && (
                          <div className="muted" style={{ fontSize: 'var(--text-xs)', marginTop: 8 }}>
                            {formatCost(msg.metadata.usage.total_cost)}
                            {msg.metadata.mode === 'quick' && ' · quick'}
                            {msg.metadata.web_search && ' · web search'}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
                <div ref={endRef} />
              </div>

              <div className="council-composer">
                <div className="row" style={{ marginBottom: 'var(--sp-2)' }}>
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                    disabled={busy}
                    style={{ width: 150 }}
                  >
                    <option value="full">Full council</option>
                    <option value="quick">Quick</option>
                  </select>
                  <label className="row" style={{ margin: 0, fontWeight: 400, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={webSearch}
                      onChange={(e) => setWebSearch(e.target.checked)}
                      disabled={busy}
                      style={{ width: 'auto' }}
                    />
                    Web search
                  </label>
                </div>
                <div className="row" style={{ alignItems: 'flex-end' }}>
                  <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        send();
                      }
                    }}
                    placeholder="Ask the council… (Enter to send, Shift+Enter for a new line)"
                    disabled={busy}
                    rows={3}
                  />
                  <button
                    className="btn btn-primary"
                    onClick={send}
                    disabled={busy || !input.trim()}
                  >
                    Send
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
