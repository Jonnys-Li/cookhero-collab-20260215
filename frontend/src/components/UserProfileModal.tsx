import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Settings, Palette } from 'lucide-react';
import { getProfile, updateProfile } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../hooks/useTheme';

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function UserProfileModal({ open, onClose }: Props) {
  const { token, updateProfile: ctxUpdate } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const [username, setUsername] = useState('');
  const [occupation, setOccupation] = useState('');
  const [bio, setBio] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | string[] | null>(null);
  const [activeTab, setActiveTab] = useState('general');

  useEffect(() => {
    if (!open || !token) return;
    let cancelled = false;
    setLoading(true);
    getProfile(token)
      .then((res) => {
        if (cancelled) return;
        setUsername(res.username || '');
        setOccupation(res.occupation || '');
        setBio(res.bio || '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, token]);

  const handleSave = async () => {
    setError(null);
    if (!token) return setError('Not authenticated');
    setLoading(true);
    try {
      const res = await updateProfile({ username, occupation, bio }, token);
      // apply to context
      if (ctxUpdate) await ctxUpdate({ username: res.username, occupation: res.occupation, bio: res.bio });
      onClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg.includes('\n') ? msg.split('\n').map((s) => s.trim()).filter(Boolean) : msg);
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-8">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-4xl bg-white dark:bg-[#0f172a] rounded-2xl shadow-2xl border border-gray-200/70 dark:border-gray-800/70 overflow-hidden flex flex-col h-[80vh]">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200/80 dark:border-gray-800/80 shrink-0">
          <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-50">设置</h3>
          <button onClick={onClose} className="p-2 rounded-md text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"><X /></button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar */}
          <div className="w-56 border-r border-gray-200/80 dark:border-gray-800/80 bg-gray-50/50 dark:bg-gray-900/50 p-3 flex flex-col gap-1 shrink-0">
            <button
              onClick={() => setActiveTab('general')}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'general'
                  ? 'bg-gray-200/60 dark:bg-gray-800 text-gray-900 dark:text-gray-100'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50'
              }`}
            >
              <div className={`p-1.5 rounded-md ${activeTab === 'general' ? 'bg-white dark:bg-gray-700 shadow-sm' : 'bg-transparent'}`}>
                <Settings size={16} />
              </div>
              常规
            </button>

            <button
              onClick={() => setActiveTab('appearance')}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'appearance'
                  ? 'bg-gray-200/60 dark:bg-gray-800 text-gray-900 dark:text-gray-100'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/50'
              }`}
            >
              <div className={`p-1.5 rounded-md ${activeTab === 'appearance' ? 'bg-white dark:bg-gray-700 shadow-sm' : 'bg-transparent'}`}>
                <Palette size={16} />
              </div>
              个性化
            </button>
          </div>

          {/* Right Content */}
          <div className="flex-1 p-6 bg-gradient-to-b from-white/60 via-white to-white/60 dark:from-gray-900/40 dark:via-gray-900/70 dark:to-gray-900/40 flex flex-col">
            {error && (
              <div className="mb-4 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
                {Array.isArray(error) ? (
                  <ul className="list-disc ml-5 space-y-1">{error.map((e, i) => <li key={i}>{e}</li>)}</ul>
                ) : (
                  <div>{error}</div>
                )}
              </div>
            )}

            {activeTab === 'general' && (
              <>
                <div className="flex-1 overflow-y-auto pr-1">
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">基本信息</p>
                    <h4 className="text-xl font-semibold text-gray-900 dark:text-gray-50">个人资料</h4>
                    <p className="text-sm text-gray-500 dark:text-gray-400">更新用户名、职业与简介。</p>
                  </div>

                  <div className="mt-4 space-y-4">
                    <div className="flex flex-col gap-1.5">
                      <label className="text-sm font-medium text-gray-700 dark:text-gray-200">用户名</label>
                      <input
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="w-full rounded-md border border-gray-200 dark:border-gray-700 bg-white/5 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500/40 transition-shadow"
                      />
                    </div>

                    <div className="flex flex-col gap-1.5">
                      <label className="text-sm font-medium text-gray-700 dark:text-gray-200">职业</label>
                      <input
                        value={occupation}
                        onChange={(e) => setOccupation(e.target.value)}
                        className="w-full rounded-md border border-gray-200 dark:border-gray-700 bg-white/5 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500/40 transition-shadow"
                      />
                    </div>

                    <div className="flex flex-col gap-1.5">
                      <label className="text-sm font-medium text-gray-700 dark:text-gray-200">简介</label>
                      <textarea
                        value={bio}
                        onChange={(e) => setBio(e.target.value)}
                        rows={4}
                        className="w-full rounded-md border border-gray-200 dark:border-gray-700 bg-white/5 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-orange-500/40 transition-shadow"
                      />
                    </div>
                  </div>
                </div>

                <div className="pt-3 flex justify-end shrink-0">
                  <button
                    onClick={handleSave}
                    disabled={loading}
                    className="px-4 py-2 rounded-lg bg-orange-500 hover:bg-orange-600 text-white font-medium disabled:opacity-70 transition-colors shadow-sm"
                  >
                    {loading ? '保存中...' : '保存'}
                  </button>
                </div>
              </>
            )}

            {activeTab === 'appearance' && (
              <div className="flex-1 overflow-y-auto">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">个性化</p>
                  <h4 className="text-xl font-semibold text-gray-900 dark:text-gray-50">外观</h4>
                  <p className="text-sm text-gray-500 dark:text-gray-400">切换浅色 / 深色主题，后续也可扩展更多外观选项。</p>
                </div>

                <div className="mt-4 flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-gray-800 dark:text-gray-100">主题模式</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">当前：{isDark ? '深色' : '浅色'}</div>
                  </div>
                  <button
                    onClick={toggleTheme}
                    className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-100 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                  >
                    切换为{isDark ? '浅色' : '深色'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
