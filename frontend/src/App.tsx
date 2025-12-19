// src/App.tsx
import { useState } from 'react';
import type { ReactElement } from 'react';
import { BookOpen, Menu, LogOut, MessageSquare } from 'lucide-react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { ChatWindow, ChatInput, Sidebar, KnowledgePanel } from './components';
import { useConversation } from './hooks';
import { useTheme, useAuth } from './contexts';
import LoginPage from './pages/Login';
import RegisterPage from './pages/Register';

type MainView = 'chat' | 'knowledge';

function ConversationPage() {
  const { token, username, logout } = useAuth();
  const navigate = useNavigate();
  const {
    messages,
    conversationId,
    conversations,
    totalConversations,
    hasMoreConversations,
    isLoading,
    isStreaming,
    error,
    sendMessage,
    selectConversation,
    clearMessages,
    stopGeneration,
    removeConversation,
    renameConversation,
    loadMoreConversations,
  } = useConversation(token || undefined);

  const { isDark, toggleTheme } = useTheme();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [suggestionText, setSuggestionText] = useState<string>('');
  const [mainView, setMainView] = useState<MainView>('chat');

  const handleNewChat = () => {
    clearMessages();
    setMainView('chat');
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  };

  const handleSelectConversation = (id: string) => {
    selectConversation(id);
    setMainView('chat');
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleSuggestionClick = (text: string) => {
    setSuggestionText(text);
  };

  const handleSuggestionConsumed = () => {
    setSuggestionText('');
  };

  const toggleMainView = () => {
    setMainView((prev) => (prev === 'chat' ? 'knowledge' : 'chat'));
  };

  return (
    <div className="flex h-screen bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 transition-colors duration-200">
      <Sidebar
        isOpen={isSidebarOpen}
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        conversations={conversations}
        totalConversations={totalConversations}
        hasMoreConversations={hasMoreConversations}
        onLoadMoreConversations={loadMoreConversations}
        currentConversationId={conversationId || null}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={removeConversation}
        onRenameConversation={renameConversation}
        isDark={isDark}
        toggleTheme={toggleTheme}
      />

      <div className="flex-1 flex flex-col h-full relative">
        <header className="h-14 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm flex items-center px-4 justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 -ml-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              title={isSidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2">
              <span className="text-2xl">🍳</span>
              <h1 className="font-bold text-gray-800 dark:text-gray-100">CookHero</h1>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-600 dark:text-gray-300">
            {mainView === 'chat' && conversationId && (
              <span className="font-mono bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded break-all whitespace-pre-wrap">
                ID: {conversationId}
              </span>
            )}
            <button
              onClick={toggleMainView}
              className={`flex items-center gap-1 px-3 py-1 rounded-full border transition-colors ${
                mainView === 'knowledge'
                  ? 'border-orange-400 bg-orange-50 text-orange-700 dark:bg-orange-900/30 dark:text-orange-200 dark:border-orange-600'
                  : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              {mainView === 'knowledge' ? (
                <>
                  <MessageSquare className="w-4 h-4" />
                  <span>返回对话</span>
                </>
              ) : (
                <>
                  <BookOpen className="w-4 h-4" />
                  <span>知识库</span>
                </>
              )}
            </button>
            {username && (
              <div className="flex items-center gap-2 bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full">
                <span className="font-semibold">{username}</span>
                <button
                  onClick={handleLogout}
                  className="text-gray-500 hover:text-gray-800 dark:hover:text-gray-100 flex items-center gap-1"
                  title="Log out"
                >
                  <LogOut className="w-4 h-4" />
                  <span>Logout</span>
                </button>
              </div>
            )}
          </div>
        </header>

        <main className="flex-1 flex flex-col overflow-hidden relative bg-gradient-to-b from-white to-gray-50 dark:from-gray-900 dark:to-gray-950">
          {mainView === 'chat' ? (
            <>
              {error && (
                <div className="absolute top-4 left-4 right-4 z-10 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-red-600 dark:text-red-400 text-sm">
                  ⚠️ {error}
                </div>
              )}
              
              <ChatWindow messages={messages} isLoading={isLoading} onSuggestionClick={handleSuggestionClick} />
              
              <div className="p-4 max-w-4xl w-full mx-auto">
                <ChatInput
                  onSend={sendMessage}
                  onCancel={stopGeneration}
                  disabled={isLoading}
                  isStreaming={isStreaming}
                  placeholder="Ask CookHero anything about cooking..."
                  externalValue={suggestionText}
                  onExternalValueConsumed={handleSuggestionConsumed}
                />
                <div className="text-center text-xs text-gray-400 mt-2">
                  CookHero can make mistakes. Consider checking important information.
                </div>
              </div>
            </>
          ) : (
            <KnowledgePanel />
          )}
        </main>
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactElement }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <RequireAuth>
            <ConversationPage />
          </RequireAuth>
        }
      />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
