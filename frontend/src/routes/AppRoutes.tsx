// src/routes/AppRoutes.tsx
import { useEffect } from 'react';
import type { ReactElement, ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

import { KnowledgePanel, MainLayout } from '../components';
import { useAuth } from '../contexts';
import CommunityFeedPage from '../pages/community/CommunityFeed';
import CommunityPostDetailPage from '../pages/community/CommunityPostDetail';
import DietManagementPage from '../pages/diet/DietManagement';
import EvaluationPage from '../pages/Evaluation';
import LLMStatsPage from '../pages/LLMStats';
import LoginPage from '../pages/Login';
import RegisterPage from '../pages/Register';
import ChatView from '../pages/chat/ChatView';

function RequireAuth({ children }: { children: ReactElement }) {
  const { isAuthenticated, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Listen for auth-unauthorized event (triggered when 401 response received)
  useEffect(() => {
    const handleUnauthorized = () => {
      logout();
      navigate('/login', { replace: true });
    };

    window.addEventListener('auth-unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth-unauthorized', handleUnauthorized);
  }, [logout, navigate]);

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

function ProtectedShell({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <MainLayout>{children}</MainLayout>
    </RequireAuth>
  );
}

export default function AppRoutes() {
  return (
    <Routes>
      {/* Protected routes with main layout */}
      <Route
        path="/chat"
        element={
          <ProtectedShell>
            <ChatView />
          </ProtectedShell>
        }
      />
      <Route
        path="/chat/:id"
        element={
          <ProtectedShell>
            <ChatView />
          </ProtectedShell>
        }
      />
      <Route
        path="/knowledge"
        element={
          <ProtectedShell>
            <KnowledgePanel />
          </ProtectedShell>
        }
      />
      <Route
        path="/agent/knowledge"
        element={
          <ProtectedShell>
            <KnowledgePanel />
          </ProtectedShell>
        }
      />
      <Route
        path="/evaluation"
        element={
          <ProtectedShell>
            <EvaluationPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/agent/evaluation"
        element={
          <ProtectedShell>
            <EvaluationPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/llm-stats"
        element={
          <ProtectedShell>
            <LLMStatsPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/agent/llm-stats"
        element={
          <ProtectedShell>
            <LLMStatsPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/diet"
        element={
          <ProtectedShell>
            <DietManagementPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/agent/diet"
        element={
          <ProtectedShell>
            <DietManagementPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/community"
        element={
          <ProtectedShell>
            <CommunityFeedPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/community/:id"
        element={
          <ProtectedShell>
            <CommunityPostDetailPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/agent/community"
        element={
          <ProtectedShell>
            <CommunityFeedPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/agent/community/:id"
        element={
          <ProtectedShell>
            <CommunityPostDetailPage />
          </ProtectedShell>
        }
      />
      <Route
        path="/agent"
        element={
          <ProtectedShell>
            <ChatView />
          </ProtectedShell>
        }
      />
      <Route
        path="/agent/:id"
        element={
          <ProtectedShell>
            <ChatView />
          </ProtectedShell>
        }
      />

      {/* Auth routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Default redirect to agent */}
      <Route path="/" element={<Navigate to="/agent" replace />} />
      <Route path="*" element={<Navigate to="/agent" replace />} />
    </Routes>
  );
}

