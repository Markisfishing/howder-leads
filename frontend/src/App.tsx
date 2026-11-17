import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthProvider";
import { AppLayout } from "./components/AppLayout";
import { Empty, Loading } from "./components/StateView";
import { AdminImportsPage } from "./pages/AdminImportsPage";
import { AdminTemplatesPage } from "./pages/AdminTemplatesPage";
import { CompanyPage } from "./pages/CompanyPage";
import { LoginPage } from "./pages/LoginPage";
import { RecommendationsPage } from "./pages/RecommendationsPage";

/** 路由守衛：沒登入看登入頁；/admin/* 只有管理員能進（後端也會再檢查一次） */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth();
  return isAdmin ? children : <Empty title="沒有權限使用這個頁面">這個頁面只有管理員可以使用。</Empty>;
}

export function App() {
  const { status } = useAuth();
  if (status === "loading") return <Loading label="登入中…" />;
  if (status === "signedOut") return <LoginPage />;

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<RecommendationsPage />} />
        <Route path="companies/:id" element={<CompanyPage />} />
        <Route
          path="admin/imports"
          element={
            <RequireAdmin>
              <AdminImportsPage />
            </RequireAdmin>
          }
        />
        <Route
          path="admin/templates"
          element={
            <RequireAdmin>
              <AdminTemplatesPage />
            </RequireAdmin>
          }
        />
        <Route path="home" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Empty title="找不到這個頁面" />} />
      </Route>
    </Routes>
  );
}
