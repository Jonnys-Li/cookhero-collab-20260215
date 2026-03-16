// src/components/layout/MainLayout.tsx
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { BarChart3, BookOpen, ChevronDown, LogOut, Menu, Users, Utensils } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useAuth, useTheme } from '../../contexts';
import { useChat } from '../../hooks/useChat';
import { Sidebar } from './Sidebar';

/**
 * Main layout component with sidebar + top navigation.
 */
export function MainLayout({ children }: { children: ReactNode }) {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const chat = useChat();
  const {
    basePath,
    clearThread,
    hasMoreThreads,
    isAgentMode,
    loadMoreThreads,
    renameThread,
    removeThread,
    selectThread,
    threadId,
    threads,
    totalThreads,
  } = chat;

  const { isDark, toggleTheme } = useTheme();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isAnalyticsMenuOpen, setIsAnalyticsMenuOpen] = useState(false);
  const analyticsMenuRef = useRef<HTMLDivElement>(null);

  // Determine current view from pathname
  const isKnowledgeView = location.pathname.includes('/knowledge');
  const isEvaluationView = location.pathname.includes('/evaluation');
  const isLLMStatsView = location.pathname.includes('/llm-stats');
  const isDietView = location.pathname.includes('/diet');
  const isCommunityView = location.pathname.includes('/community');
  const isAnalyticsView = isEvaluationView || isLLMStatsView;
  const analyticsLabel = isEvaluationView ? '评估监控' : isLLMStatsView ? '模型统计' : '数据分析';

  useEffect(() => {
    setIsAnalyticsMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (analyticsMenuRef.current && !analyticsMenuRef.current.contains(event.target as Node)) {
        setIsAnalyticsMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const goBackToChat = useCallback(() => {
    if (threadId && !threadId.startsWith('temp-')) {
      navigate(`${basePath}/${threadId}`);
    } else {
      navigate(basePath);
    }
  }, [basePath, navigate, threadId]);

  const handleToggleAgentMode = useCallback(() => {
    if (isAgentMode) {
      navigate('/chat');
    } else {
      navigate('/agent');
    }
  }, [isAgentMode, navigate]);

  const handleNewChat = useCallback(() => {
    clearThread();
    navigate(isAgentMode ? '/agent' : '/chat');
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  }, [clearThread, navigate, isAgentMode]);

  const handleSelectConversation = useCallback(
    (id: string) => {
      selectThread(id);
      navigate(`${basePath}/${id}`);
      if (window.innerWidth < 768) {
        setIsSidebarOpen(false);
      }
    },
    [basePath, navigate, selectThread]
  );

  const handleLogout = useCallback(() => {
    logout();
    navigate('/login');
  }, [logout, navigate]);

  return (
    <div className="flex h-screen bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 transition-colors duration-200">
      <Sidebar
        isOpen={isSidebarOpen}
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        conversations={threads}
        totalConversations={totalThreads}
        hasMoreConversations={hasMoreThreads}
        onLoadMoreConversations={loadMoreThreads}
        currentConversationId={threadId || null}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={removeThread}
        onRenameConversation={renameThread}
        isDark={isDark}
        toggleTheme={toggleTheme}
        isAgentMode={isAgentMode}
        onToggleAgentMode={handleToggleAgentMode}
      />

      <div className="flex-1 flex flex-col h-full relative">
        <header className="h-14 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm flex items-center px-4 justify-between z-50">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 -ml-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              title={isSidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
            >
              <Menu className="w-5 h-5" />
            </button>
          </div>
          <div className="flex items-center gap-1.5 sm:gap-3 text-xs text-gray-600 dark:text-gray-300 overflow-visible">
            {!isKnowledgeView &&
              !isEvaluationView &&
              !isLLMStatsView &&
              !isDietView &&
              !isCommunityView &&
              threadId && (
                <span
                  className="hidden sm:inline font-mono bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded truncate"
                  title={threadId}
                >
                  ID: {threadId}
                </span>
              )}
            <button
              onClick={() => {
                if (isDietView) {
                  goBackToChat();
                } else {
                  navigate(isAgentMode ? '/agent/diet' : '/diet');
                }
              }}
              className={`flex items-center gap-1 px-2 sm:px-3 py-1 rounded-full border transition-colors shrink-0 ${
                isDietView
                  ? 'border-green-400 bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-200 dark:border-green-600'
                  : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <Utensils className="w-4 h-4" />
              <span className="hidden sm:inline">{isDietView ? '返回对话' : '饮食管理'}</span>
            </button>
            <button
              onClick={() => {
                if (isKnowledgeView) {
                  goBackToChat();
                } else {
                  navigate(isAgentMode ? '/agent/knowledge' : '/knowledge');
                }
              }}
              className={`flex items-center gap-1 px-2 sm:px-3 py-1 rounded-full border transition-colors shrink-0 ${
                isKnowledgeView
                  ? 'border-blue-400 bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-200 dark:border-blue-600'
                  : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <BookOpen className="w-4 h-4" />
              <span className="hidden sm:inline">{isKnowledgeView ? '返回对话' : '知识库'}</span>
            </button>
            <button
              onClick={() => {
                if (isCommunityView) {
                  goBackToChat();
                } else {
                  navigate(isAgentMode ? '/agent/community' : '/community');
                }
              }}
              className={`flex items-center gap-1 px-2 sm:px-3 py-1 rounded-full border transition-colors shrink-0 ${
                isCommunityView
                  ? 'border-rose-400 bg-rose-50 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200 dark:border-rose-600'
                  : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <Users className="w-4 h-4" />
              <span className="hidden sm:inline">{isCommunityView ? '返回对话' : '社区'}</span>
            </button>
            <div ref={analyticsMenuRef} className="relative">
              <button
                onClick={() => setIsAnalyticsMenuOpen((prev) => !prev)}
                className={`flex items-center gap-1 px-2 sm:px-3 py-1 rounded-full border transition-all duration-200 shrink-0 ${
                  isAnalyticsView
                    ? 'border-orange-400 bg-orange-50 text-orange-700 dark:bg-orange-900/30 dark:text-orange-200 dark:border-orange-600'
                    : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-orange-50 dark:hover:bg-orange-900/20 hover:border-orange-300 dark:hover:border-orange-700'
                }`}
              >
                <BarChart3 className="w-4 h-4" />
                <span className="hidden sm:inline">{analyticsLabel}</span>
                <ChevronDown className="w-4 h-4" />
              </button>
              {isAnalyticsMenuOpen && (
                <div className="absolute right-0 mt-2 rounded-xl border border-gray-200/60 dark:border-gray-700/60 bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm shadow-xl overflow-hidden z-50">
                  {isAnalyticsView && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setIsAnalyticsMenuOpen(false);
                        goBackToChat();
                      }}
                      className="w-full text-left px-4 py-2.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gradient-to-r hover:from-orange-50 hover:to-orange-100/50 dark:hover:from-orange-900/30 dark:hover:to-orange-900/10 border-b border-gray-100/50 dark:border-gray-800/50 transition-all duration-200 flex items-center gap-2"
                    >
                      返回对话
                    </button>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsAnalyticsMenuOpen(false);
                      navigate(isAgentMode ? '/agent/evaluation' : '/evaluation');
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-all duration-200 flex items-center gap-2.5 ${
                      isEvaluationView
                        ? 'text-orange-600 dark:text-orange-400 bg-gradient-to-r from-orange-50 to-orange-100/50 dark:from-orange-900/30 dark:to-orange-900/20 font-medium'
                        : 'text-gray-700 dark:text-gray-200 hover:bg-gradient-to-r hover:from-orange-50 hover:to-orange-100/50 dark:hover:from-orange-900/30 dark:hover:to-orange-900/10'
                    }`}
                  >
                    评估监控
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsAnalyticsMenuOpen(false);
                      navigate(isAgentMode ? '/agent/llm-stats' : '/llm-stats');
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-all duration-200 flex items-center gap-2.5 ${
                      isLLMStatsView
                        ? 'text-orange-600 dark:text-orange-400 bg-gradient-to-r from-orange-50 to-orange-100/50 dark:from-orange-900/30 dark:to-orange-900/20 font-medium'
                        : 'text-gray-700 dark:text-gray-200 hover:bg-gradient-to-r hover:from-orange-50 hover:to-orange-100/50 dark:hover:from-orange-900/30 dark:hover:to-orange-900/10'
                    }`}
                  >
                    模型统计
                  </button>
                </div>
              )}
            </div>
            {username && (
              <div className="flex items-center gap-1 sm:gap-2 bg-gray-100 dark:bg-gray-800 px-2 sm:px-3 py-1 rounded-full shrink-0">
                <span className="font-semibold hidden sm:inline">{username}</span>
                <button
                  onClick={handleLogout}
                  className="text-gray-500 hover:text-gray-800 dark:hover:text-gray-100 flex items-center gap-1"
                  title="Log out"
                >
                  <LogOut className="w-4 h-4" />
                  <span className="hidden md:inline">Logout</span>
                </button>
              </div>
            )}
          </div>
        </header>

        <main className="flex-1 flex flex-col overflow-hidden relative bg-gradient-to-b from-white to-gray-50 dark:from-gray-900 dark:to-gray-950">
          {children}
        </main>
      </div>
    </div>
  );
}

