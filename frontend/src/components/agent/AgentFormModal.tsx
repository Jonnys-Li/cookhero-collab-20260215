/**
 * AgentFormModal Component
 *
 * 用于创建和编辑自定义 Agent 的表单模态框
 */

import { useState, useEffect, useCallback } from 'react';
import { Loader2, AlertCircle } from 'lucide-react';
import { Modal } from '../common/Modal';
import type { SubagentSchema, CreateSubagentRequest, UpdateSubagentRequest } from '../../types';
import { createSubagent, updateSubagent, getAvailableTools } from '../../services/api/agent';
import { TOOLS_UPDATED_EVENT } from '../../constants';

interface AgentFormModalProps {
  open: boolean;
  onClose: () => void;
  agent?: SubagentSchema; // undefined = create mode
  token?: string;
  onSave: () => void;
}

interface FormData {
  name: string;
  display_name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  max_iterations: number;
  category: string;
}

const DEFAULT_FORM_DATA: FormData = {
  name: '',
  display_name: '',
  description: '',
  system_prompt: '',
  tools: [],
  max_iterations: 10,
  category: 'custom',
};

export function AgentFormModal({ open, onClose, agent, token, onSave }: AgentFormModalProps) {
  const isEditMode = !!agent;
  const [formData, setFormData] = useState<FormData>(DEFAULT_FORM_DATA);
  const [availableTools, setAvailableTools] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Load available tools
  const loadAvailableTools = useCallback(async () => {
    if (!token) return;

    setIsLoading(true);
    try {
      const response = await getAvailableTools(token);
      const toolNames = response.servers
        .flatMap((s) => s.tools.map((t) => t.name))
        .filter((toolName) => !toolName.startsWith('subagent_'));
      setAvailableTools(toolNames);
    } catch (err) {
      console.error('Failed to load tools:', err);
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (open) {
      loadAvailableTools();

      if (agent) {
        // Edit mode: populate form with agent data
        setFormData({
          name: agent.name,
          display_name: agent.display_name,
          description: agent.description,
          system_prompt: agent.system_prompt ?? '',
          tools: agent.tools || [],
          max_iterations: agent.max_iterations || 10,
          category: agent.category || 'custom',
        });
      } else {
        // Create mode: reset form
        setFormData(DEFAULT_FORM_DATA);
      }

      setError(null);
      setValidationErrors({});
    }
  }, [open, agent, loadAvailableTools]);

  useEffect(() => {
    if (!open) return;
    const handleToolsUpdated = () => {
      loadAvailableTools();
    };
    window.addEventListener(TOOLS_UPDATED_EVENT, handleToolsUpdated);
    return () => {
      window.removeEventListener(TOOLS_UPDATED_EVENT, handleToolsUpdated);
    };
  }, [open, loadAvailableTools]);

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    if (!isEditMode) {
      if (!formData.name.trim()) {
        errors.name = 'Name is required';
      } else if (!/^[a-z0-9_]{2,64}$/.test(formData.name)) {
        errors.name = 'Name must be 2-64 characters, lowercase letters, numbers, and underscores only';
      }
    }

    if (!formData.display_name.trim()) {
      errors.display_name = 'Display name is required';
    }

    if (!formData.description.trim()) {
      errors.description = 'Description is required';
    } else if (formData.description.length < 10) {
      errors.description = 'Description must be at least 10 characters';
    }

    if (!formData.system_prompt.trim()) {
      errors.system_prompt = 'System prompt is required';
    } else if (formData.system_prompt.length < 20) {
      errors.system_prompt = 'System prompt must be at least 20 characters';
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async () => {
    if (!token || !validateForm()) return;

    setIsSubmitting(true);
    setError(null);

    try {
      if (isEditMode) {
        if (!agent) {
          throw new Error('Agent is required in edit mode');
        }
        // Update existing agent
        const updateData: UpdateSubagentRequest = {
          display_name: formData.display_name,
          description: formData.description,
          system_prompt: formData.system_prompt,
          tools: formData.tools,
          max_iterations: formData.max_iterations,
          category: formData.category,
        };
        await updateSubagent(agent.name, updateData, token);
      } else {
        // Create new agent
        const createData: CreateSubagentRequest = {
          name: formData.name,
          display_name: formData.display_name,
          description: formData.description,
          system_prompt: formData.system_prompt,
          tools: formData.tools,
          max_iterations: formData.max_iterations,
          category: formData.category,
        };
        await createSubagent(createData, token);
      }

      onSave();
      onClose();
    } catch (err) {
      console.error('Failed to save agent:', err);
      setError(err instanceof Error ? err.message : 'Failed to save agent');
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleTool = (toolName: string) => {
    setFormData((prev) => ({
      ...prev,
      tools: prev.tools.includes(toolName)
        ? prev.tools.filter((t) => t !== toolName)
        : [...prev.tools, toolName],
    }));
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEditMode ? 'Edit Agent' : 'Create New Agent'}
    >
      <div className="min-w-[450px] max-w-[550px] max-h-[70vh] overflow-y-auto">
        {error && (
          <div className="flex items-center gap-2 p-3 mb-4 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 rounded-lg">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="space-y-4">
          {/* Name (only for create mode) */}
          {!isEditMode && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="my_custom_agent"
                className={`
                  w-full px-3 py-2 text-sm border rounded-lg
                  bg-white dark:bg-gray-800
                  text-gray-900 dark:text-gray-100
                  placeholder-gray-400
                  ${validationErrors.name ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'}
                `}
              />
              {validationErrors.name && (
                <p className="mt-1 text-xs text-red-500">{validationErrors.name}</p>
              )}
              <p className="mt-1 text-xs text-gray-400">
                Unique identifier (lowercase, numbers, underscores)
              </p>
            </div>
          )}

          {/* Display Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Display Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.display_name}
              onChange={(e) => setFormData((prev) => ({ ...prev, display_name: e.target.value }))}
              placeholder="My Custom Agent"
              className={`
                w-full px-3 py-2 text-sm border rounded-lg
                bg-white dark:bg-gray-800
                text-gray-900 dark:text-gray-100
                placeholder-gray-400
                ${validationErrors.display_name ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'}
              `}
            />
            {validationErrors.display_name && (
              <p className="mt-1 text-xs text-red-500">{validationErrors.display_name}</p>
            )}
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description <span className="text-red-500">*</span>
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
              placeholder="Describe what this agent does..."
              rows={2}
              className={`
                w-full px-3 py-2 text-sm border rounded-lg resize-none
                bg-white dark:bg-gray-800
                text-gray-900 dark:text-gray-100
                placeholder-gray-400
                ${validationErrors.description ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'}
              `}
            />
            {validationErrors.description && (
              <p className="mt-1 text-xs text-red-500">{validationErrors.description}</p>
            )}
          </div>

          {/* System Prompt */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              System Prompt <span className="text-red-500">*</span>
            </label>
            <textarea
              value={formData.system_prompt}
              onChange={(e) => setFormData((prev) => ({ ...prev, system_prompt: e.target.value }))}
              placeholder="You are a helpful assistant that specializes in..."
              rows={6}
              className={`
                w-full px-3 py-2 text-sm border rounded-lg resize-none font-mono
                bg-white dark:bg-gray-800
                text-gray-900 dark:text-gray-100
                placeholder-gray-400
                ${validationErrors.system_prompt ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'}
              `}
            />
            {validationErrors.system_prompt && (
              <p className="mt-1 text-xs text-red-500">{validationErrors.system_prompt}</p>
            )}
          </div>

          {/* Available Tools */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Available Tools
            </label>
            {isLoading ? (
              <div className="flex items-center gap-2 py-2 text-sm text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading tools...
              </div>
            ) : availableTools.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 p-2 bg-gray-50 dark:bg-gray-800/50 rounded-lg max-h-32 overflow-y-auto">
                {availableTools.map((tool) => (
                  <button
                    key={tool}
                    type="button"
                    onClick={() => toggleTool(tool)}
                    className={`
                      px-2 py-1 text-xs rounded-full transition-colors
                      ${
                        formData.tools.includes(tool)
                          ? 'bg-purple-500 text-white'
                          : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                      }
                    `}
                  >
                    {tool}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400">No tools available</p>
            )}
          </div>

          {/* Max Iterations */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Max Iterations
            </label>
            <input
              type="number"
              value={formData.max_iterations}
              onChange={(e) =>
                setFormData((prev) => ({
                  ...prev,
                  max_iterations: Math.max(1, Math.min(50, parseInt(e.target.value) || 10)),
                }))
              }
              min={1}
              max={50}
              className="w-24 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
            <p className="mt-1 text-xs text-gray-400">Maximum number of reasoning steps (1-50)</p>
          </div>

          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Category
            </label>
            <input
              type="text"
              value={formData.category}
              onChange={(e) => setFormData((prev) => ({ ...prev, category: e.target.value }))}
              placeholder="custom"
              className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {isEditMode ? 'Save Changes' : 'Create Agent'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
