/**
 * AgentManager Component
 *
 * Agent 管理界面，支持：
 * - 查看内置 agents（只读，可启用/禁用）
 * - 创建自定义 agents
 * - 编辑/删除自定义 agents
 */

import { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, Trash2, Bot, Loader2, AlertCircle, Check } from 'lucide-react';
import { Modal } from '../common/Modal';
import type { SubagentSchema } from '../../types';
import {
  listSubagents,
  toggleSubagent,
  deleteSubagent,
} from '../../services/api/agent';
import { AgentFormModal } from './AgentFormModal';

interface AgentManagerProps {
  open: boolean;
  onClose: () => void;
  token?: string;
  onAgentsChange?: () => void;
}

export function AgentManager({ open, onClose, token, onAgentsChange }: AgentManagerProps) {
  const [subagents, setSubagents] = useState<SubagentSchema[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formModalOpen, setFormModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<SubagentSchema | undefined>();
  const [togglingAgents, setTogglingAgents] = useState<Set<string>>(new Set());
  const [deletingAgent, setDeletingAgent] = useState<string | null>(null);

  // 分离内置和自定义 agents
  const builtinAgents = subagents.filter((a) => a.builtin);
  const customAgents = subagents.filter((a) => !a.builtin);

  const loadSubagents = useCallback(async () => {
    if (!token) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await listSubagents(token);
      setSubagents(response.subagents);
    } catch (err) {
      console.error('Failed to load subagents:', err);
      setError(err instanceof Error ? err.message : 'Failed to load agents');
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (open) {
      loadSubagents();
    }
  }, [open, loadSubagents]);

  const handleToggleAgent = async (agent: SubagentSchema) => {
    if (!token) return;

    const newEnabled = !agent.enabled;

    setTogglingAgents((prev) => new Set(prev).add(agent.name));
    setSubagents((prev) =>
      prev.map((a) => (a.name === agent.name ? { ...a, enabled: newEnabled } : a))
    );

    try {
      await toggleSubagent(agent.name, newEnabled, token);
      onAgentsChange?.();
    } catch (err) {
      console.error('Failed to toggle agent:', err);
      // Revert on error
      setSubagents((prev) =>
        prev.map((a) => (a.name === agent.name ? { ...a, enabled: !newEnabled } : a))
      );
    } finally {
      setTogglingAgents((prev) => {
        const next = new Set(prev);
        next.delete(agent.name);
        return next;
      });
    }
  };

  const handleCreateAgent = () => {
    setEditingAgent(undefined);
    setFormModalOpen(true);
  };

  const handleEditAgent = (agent: SubagentSchema) => {
    setEditingAgent(agent);
    setFormModalOpen(true);
  };

  const handleDeleteAgent = async (agent: SubagentSchema) => {
    if (!token || agent.builtin) return;

    if (!window.confirm(`确定要删除 Agent "${agent.display_name}" 吗？此操作不可撤销。`)) {
      return;
    }

    setDeletingAgent(agent.name);
    try {
      await deleteSubagent(agent.name, token);
      setSubagents((prev) => prev.filter((a) => a.name !== agent.name));
      onAgentsChange?.();
    } catch (err) {
      console.error('Failed to delete agent:', err);
      alert(err instanceof Error ? err.message : '删除失败');
    } finally {
      setDeletingAgent(null);
    }
  };

  const handleFormSave = async () => {
    setFormModalOpen(false);
    await loadSubagents();
    onAgentsChange?.();
  };

  return (
    <>
      <Modal open={open} onClose={onClose} title="Manage Agents">
        <div className="min-w-[500px] max-w-[600px]">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-purple-500" />
              <span className="ml-2 text-gray-500">Loading agents...</span>
            </div>
          ) : error ? (
            <div className="flex items-center gap-2 py-8 text-red-500">
              <AlertCircle className="w-5 h-5" />
              <span>{error}</span>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Built-in Agents Section */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                  Built-in Agents
                </h3>
                <div className="space-y-2">
                  {builtinAgents.map((agent) => (
                    <AgentCard
                      key={agent.name}
                      agent={agent}
                      onToggle={() => handleToggleAgent(agent)}
                      isToggling={togglingAgents.has(agent.name)}
                    />
                  ))}
                  {builtinAgents.length === 0 && (
                    <p className="text-sm text-gray-400">No built-in agents available</p>
                  )}
                </div>
              </div>

              {/* Custom Agents Section */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Custom Agents
                  </h3>
                  <button
                    onClick={handleCreateAgent}
                    className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-purple-600 hover:text-purple-700 dark:text-purple-400 dark:hover:text-purple-300 bg-purple-50 dark:bg-purple-900/20 rounded-md hover:bg-purple-100 dark:hover:bg-purple-900/30 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Create New
                  </button>
                </div>
                <div className="space-y-2">
                  {customAgents.map((agent) => (
                    <AgentCard
                      key={agent.name}
                      agent={agent}
                      onToggle={() => handleToggleAgent(agent)}
                      onEdit={() => handleEditAgent(agent)}
                      onDelete={() => handleDeleteAgent(agent)}
                      isToggling={togglingAgents.has(agent.name)}
                      isDeleting={deletingAgent === agent.name}
                    />
                  ))}
                  {customAgents.length === 0 && (
                    <p className="text-sm text-gray-400">No custom agents yet. Create one!</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* Agent Form Modal */}
      <AgentFormModal
        open={formModalOpen}
        onClose={() => setFormModalOpen(false)}
        agent={editingAgent}
        token={token}
        onSave={handleFormSave}
      />
    </>
  );
}

// Agent Card Component
interface AgentCardProps {
  agent: SubagentSchema;
  onToggle: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  isToggling?: boolean;
  isDeleting?: boolean;
}

function AgentCard({ agent, onToggle, onEdit, onDelete, isToggling, isDeleting }: AgentCardProps) {
  return (
    <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
      {/* Icon */}
      <div
        className={`
        flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
        ${agent.enabled ? 'bg-purple-100 dark:bg-purple-900/30' : 'bg-gray-200 dark:bg-gray-700'}
      `}
      >
        <Bot
          className={`
          w-4 h-4
          ${agent.enabled ? 'text-purple-600 dark:text-purple-400' : 'text-gray-400'}
        `}
        />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
            {agent.display_name}
          </span>
          {agent.builtin && (
            <span className="text-xs px-1.5 py-0.5 bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-300 rounded">
              Built-in
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{agent.description}</p>
      </div>

      {/* Toggle */}
      <button
        onClick={onToggle}
        disabled={isToggling}
        className={`
          relative flex-shrink-0 w-10 h-5 rounded-full transition-colors
          ${agent.enabled ? 'bg-purple-500' : 'bg-gray-300 dark:bg-gray-600'}
          ${isToggling ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
        `}
      >
        {isToggling ? (
          <Loader2 className="absolute inset-0.5 w-4 h-4 animate-spin text-white" />
        ) : (
          <span
            className={`
            absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform
            ${agent.enabled ? 'left-5' : 'left-0.5'}
          `}
          >
            {agent.enabled && <Check className="w-3 h-3 m-0.5 text-purple-500" />}
          </span>
        )}
      </button>

      {/* Actions (for custom agents) */}
      {!agent.builtin && (
        <div className="flex items-center gap-1">
          {onEdit && (
            <button
              onClick={onEdit}
              className="p-1.5 text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded transition-colors"
              title="Edit"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={onDelete}
              disabled={isDeleting}
              className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors disabled:opacity-50"
              title="Delete"
            >
              {isDeleting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
