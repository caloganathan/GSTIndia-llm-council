import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { api, setAuthToken } from './api';
import './App.css';

function LoginScreen({ onSuccess }) {
  const [token, setToken] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setAuthToken(token.trim());
    try {
      await api.checkAuth();
      onSuccess();
    } catch {
      setAuthToken('');
      setError('Invalid access token. Please try again.');
    }
  };

  return (
    <div className="login-screen">
      <form className="login-box" onSubmit={handleSubmit}>
        <h1>LLM Council</h1>
        <p>Enter your access token to continue.</p>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Access token"
          autoFocus
        />
        {error && <div className="login-error">{error}</div>}
        <button type="submit" disabled={!token.trim()}>
          Unlock
        </button>
      </form>
    </div>
  );
}

function App() {
  const [authState, setAuthState] = useState('checking'); // checking | needed | ok
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Verify auth on mount, then load conversations
  useEffect(() => {
    (async () => {
      try {
        await api.checkAuth();
        setAuthState('ok');
      } catch (error) {
        if (error.status === 401) {
          setAuthState('needed');
        } else {
          console.error('Backend unreachable:', error);
          setAuthState('ok'); // let the normal error paths surface it
        }
      }
    })();
  }, []);

  useEffect(() => {
    if (authState === 'ok') {
      loadConversations();
    }
  }, [authState]);

  // Load conversation details when selected
  useEffect(() => {
    if (currentConversationId) {
      loadConversation(currentConversationId);
    }
  }, [currentConversationId]);

  const handleAuthError = (error) => {
    if (error?.status === 401) {
      setAuthToken('');
      setAuthState('needed');
      return true;
    }
    return false;
  };

  const loadConversations = async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (error) {
      if (!handleAuthError(error)) {
        console.error('Failed to load conversations:', error);
      }
    }
  };

  const loadConversation = async (id) => {
    try {
      const conv = await api.getConversation(id);
      setCurrentConversation(conv);
    } catch (error) {
      if (!handleAuthError(error)) {
        console.error('Failed to load conversation:', error);
      }
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await api.createConversation();
      setConversations([
        {
          id: newConv.id,
          created_at: newConv.created_at,
          title: newConv.title,
          message_count: 0,
        },
        ...conversations,
      ]);
      setCurrentConversationId(newConv.id);
    } catch (error) {
      if (!handleAuthError(error)) {
        console.error('Failed to create conversation:', error);
      }
    }
  };

  const handleSelectConversation = (id) => {
    setCurrentConversationId(id);
  };

  const handleDeleteConversation = async (id) => {
    if (!window.confirm('Delete this conversation permanently?')) return;
    try {
      await api.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (id === currentConversationId) {
        setCurrentConversationId(null);
        setCurrentConversation(null);
      }
    } catch (error) {
      if (!handleAuthError(error)) {
        console.error('Failed to delete conversation:', error);
      }
    }
  };

  // Helper: immutably update the last (in-flight) assistant message
  const updateLastMessage = (updater) => {
    setCurrentConversation((prev) => {
      if (!prev) return prev;
      const messages = [...prev.messages];
      const lastMsg = { ...messages[messages.length - 1] };
      updater(lastMsg);
      messages[messages.length - 1] = lastMsg;
      return { ...prev, messages };
    });
  };

  const handleSendMessage = async (content, options) => {
    if (!currentConversationId) return;

    setIsLoading(true);
    try {
      // Optimistically add user message to UI
      const userMessage = { role: 'user', content };
      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        error: null,
        loading: { stage1: false, stage2: false, stage3: false },
      };
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage, assistantMessage],
      }));

      await api.sendMessageStream(currentConversationId, content, options, (eventType, event) => {
        switch (eventType) {
          case 'stage1_start':
            updateLastMessage((msg) => {
              msg.loading = { ...msg.loading, stage1: true };
            });
            break;

          case 'stage1_complete':
            updateLastMessage((msg) => {
              msg.stage1 = event.data;
              msg.loading = { ...msg.loading, stage1: false };
              msg.metadata = {
                ...(msg.metadata || {}),
                failures: {
                  ...(msg.metadata?.failures || {}),
                  stage1: event.failures || [],
                },
              };
            });
            break;

          case 'stage2_start':
            updateLastMessage((msg) => {
              msg.loading = { ...msg.loading, stage2: true };
            });
            break;

          case 'stage2_complete':
            updateLastMessage((msg) => {
              msg.stage2 = event.data;
              msg.loading = { ...msg.loading, stage2: false };
              msg.metadata = {
                ...(msg.metadata || {}),
                ...event.metadata,
                failures: {
                  ...(msg.metadata?.failures || {}),
                  stage2: event.failures || [],
                },
              };
            });
            break;

          case 'stage3_start':
            updateLastMessage((msg) => {
              msg.loading = { ...msg.loading, stage3: true };
            });
            break;

          case 'stage3_complete':
            updateLastMessage((msg) => {
              msg.stage3 = event.data;
              msg.loading = { ...msg.loading, stage3: false };
            });
            break;

          case 'summary':
            // Authoritative metadata for the whole exchange (incl. usage/cost)
            updateLastMessage((msg) => {
              msg.metadata = event.metadata;
            });
            break;

          case 'title_complete':
            loadConversations();
            break;

          case 'complete':
            loadConversations();
            setIsLoading(false);
            break;

          case 'error':
            console.error('Stream error:', event.message);
            updateLastMessage((msg) => {
              msg.error = event.message;
              msg.loading = { stage1: false, stage2: false, stage3: false };
            });
            setIsLoading(false);
            break;

          default:
            console.log('Unknown event type:', eventType);
        }
      });
    } catch (error) {
      console.error('Failed to send message:', error);
      if (handleAuthError(error)) {
        setIsLoading(false);
        return;
      }
      // Mark the in-flight assistant message as failed instead of vanishing it
      updateLastMessage((msg) => {
        msg.error = error.message || 'Request failed';
        msg.loading = { stage1: false, stage2: false, stage3: false };
      });
      setIsLoading(false);
    }
  };

  if (authState === 'checking') {
    return <div className="app-loading">Loading…</div>;
  }

  if (authState === 'needed') {
    return <LoginScreen onSuccess={() => setAuthState('ok')} />;
  }

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
      />
      <ChatInterface
        conversation={currentConversation}
        onSendMessage={handleSendMessage}
        isLoading={isLoading}
      />
    </div>
  );
}

export default App;
