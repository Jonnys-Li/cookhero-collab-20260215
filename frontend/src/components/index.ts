// src/components/index.ts
/**
 * Components - Central export
 */

// Common components
export * from './common';

// Chat components
export * from './chat';

// Layout components
export * from './layout';

// Knowledge components
export { default as KnowledgePanel } from './KnowledgePanel';

// Legacy exports for backward compatibility
// These can be removed once all imports are updated
export { ChatInput } from './chat';
export { ChatWindow } from './chat';
export { MessageBubble } from './chat';
export { MarkdownRenderer } from './chat';
export { Header } from './layout';
export { Sidebar } from './layout';

