import { MessageSquare, Plus, PanelLeftClose, Sparkles } from 'lucide-react';
import { useState } from 'react';
import UserProfileModal from './UserProfileModal';
import { useAuth } from '../hooks/useAuth';
import { ThemeToggle } from './ThemeToggle';
import type { ConversationSummary } from '../types';

interface SidebarProps {
  isOpen: boolean;
  toggleSidebar: () => void;
  conversations: ConversationSummary[];
  currentConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  isDark: boolean;
  toggleTheme: () => void;
}

export function Sidebar({
  isOpen,
  toggleSidebar,
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewChat,
  isDark,
  toggleTheme,
}: SidebarProps) {
  const { username } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-20 md:hidden"
          onClick={toggleSidebar}
        />
      )}

      {/* Sidebar Container */}
      <div
        className={`
          fixed md:static inset-y-0 left-0 z-30
          flex flex-col flex-none
          bg-gradient-to-b from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-950 border-r border-gray-200 dark:border-gray-800
          transform transition-all duration-300 ease-in-out shadow-xl md:shadow-none
          ${isOpen ? 'translate-x-0 w-72 md:w-72' : '-translate-x-full md:-translate-x-full md:w-0 md:opacity-0 md:pointer-events-none'}
        `}
      >
        {/* Header */}
        <div className="p-4 border-b border-gray-200 dark:border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-400 to-orange-500 flex items-center justify-center text-white shadow-sm">
                <Sparkles className="w-4 h-4" />
              </div>
              <span className="font-bold text-gray-800 dark:text-gray-100">CookHero</span>
            </div>
            <button 
              onClick={toggleSidebar} 
              className="md:hidden p-2 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg transition-colors"
            >
              <PanelLeftClose className="w-5 h-5" />
            </button>
          </div>
          <button
            onClick={onNewChat}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-orange-400 to-orange-500 hover:from-orange-500 hover:to-orange-600 text-white rounded-xl text-sm font-medium shadow-sm transition-all duration-200 hover:shadow-md"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium px-2 mb-2 uppercase tracking-wider">Recent Chats</p>
          {conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => onSelectConversation(conv.id)}
              className={`
                w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left text-sm transition-all duration-200
                ${
                  currentConversationId === conv.id
                    ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-medium shadow-sm border border-gray-200 dark:border-gray-700'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-white/50 dark:hover:bg-gray-800/50'
                }
              `}
            >
              <MessageSquare className={`w-4 h-4 shrink-0 ${currentConversationId === conv.id ? 'text-orange-500' : ''}`} />
              <span className="truncate">{conv.title || conv.last_message_preview || 'New Conversation'}</span>
            </button>
          ))}
          
          {conversations.length === 0 && (
            <div className="text-center text-gray-400 dark:text-gray-500 text-sm py-12">
              <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>No conversations yet</p>
              <p className="text-xs mt-1">Start a new chat to begin!</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-800 bg-white/50 dark:bg-gray-900/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <button onClick={() => setOpen(true)} className="flex items-center gap-3 focus:outline-none">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white font-bold text-xs shadow-sm">
                  {username ? username.charAt(0).toUpperCase() : 'U'}
                </div>
                <div className="text-left">
                  <div className="font-medium text-gray-900 dark:text-white">{username || 'User'}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">View & edit profile</div>
                </div>
              </button>
            </div>
            <ThemeToggle isDark={isDark} toggleTheme={toggleTheme} />
          </div>
        </div>
        <UserProfileModal open={open} onClose={() => setOpen(false)} />
      </div>
    </>
  );
}
