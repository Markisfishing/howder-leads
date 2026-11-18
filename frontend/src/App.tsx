import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthProvider";
import { AppLayout } from "./components/AppLayout";
import { Empty, Loading } from "./components/StateView";
import { LoginPage } from "./pages/LoginPage";

// 各頁面依路由切分，進到該頁才下載（M-perf：主 bundle 超過 500 kB）
const AdminImportsPage = lazy(() =>
  import("./pages/AdminImportsPage").then((m) => ({
    default: m.AdminImportsPage,
  })),
);
const AdminTemplatesPage = lazy(() =>
  import("./pages/AdminTemplatesPage").then((m) => ({
    default: m.AdminTemplatesPage,
  })),
);
const CasesPage = lazy(() =>
  import("./pages/cases/CasesPage").then((m) => ({ default: m.CasesPage })),
);
const CampaignNewPage = lazy(() =>
  import("./pages/campaigns/CampaignNewPage").then((m) => ({
    default: m.CampaignNewPage,
  })),
);
const CampaignReviewPage = lazy(() =>
  import("./pages/campaigns/CampaignReviewPage").then((m) => ({
    default: m.CampaignReviewPage,
  })),
);
const CampaignsPage = lazy(() =>
  import("./pages/campaigns/CampaignsPage").then((m) => ({
    default: m.CampaignsPage,
  })),
);
const CompanyPage = lazy(() =>
  import("./pages/CompanyPage").then((m) => ({ default: m.CompanyPage })),
);
const OverviewPage = lazy(() =>
  import("./pages/overview/OverviewPage").then((m) => ({
    default: m.OverviewPage,
  })),
);
const AdminModelPage = lazy(() =>
  import("./pages/performance/AdminModelPage").then((m) => ({
    default: m.AdminModelPage,
  })),
);
const PerformancePage = lazy(() =>
  import("./pages/performance/PerformancePage").then((m) => ({
    default: m.PerformancePage,
  })),
);
const RecommendationsPage = lazy(() =>
  import("./pages/RecommendationsPage").then((m) => ({
    default: m.RecommendationsPage,
  })),
);

/** 路由守衛：沒登入看登入頁；/admin/* 只有管理員能進（後端也會再檢查一次） */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth();
  return isAdmin ? (
    children
  ) : (
    <Empty title="沒有權限使用這個頁面">這個頁面只有管理員可以使用。</Empty>
  );
}

/** 名單品質只給主管與管理員（後端也會再檢查一次） */
function RequireManager({ children }: { children: ReactNode }) {
  const { isManager } = useAuth();
  return isManager ? (
    children
  ) : (
    <Empty title="沒有權限使用這個頁面">
      這個頁面只有主管或管理員可以使用。
    </Empty>
  );
}

export function App() {
  const { status } = useAuth();
  if (status === "loading") return <Loading label="登入中…" />;
  if (status === "signedOut") return <LoginPage />;

  return (
    <Suspense fallback={<Loading label="載入頁面…" />}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/overview" replace />} />
          <Route
            path="recommendations"
            element={<RecommendationsPage initialView="review" />}
          />
          <Route path="companies/:id" element={<CompanyPage />} />
          <Route path="campaigns" element={<CampaignsPage />} />
          <Route path="campaigns/new" element={<CampaignNewPage />} />
          <Route path="campaigns/:id" element={<CampaignReviewPage />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="performance" element={<PerformancePage />} />
          <Route path="cases" element={<CasesPage />} />
          <Route path="cases/:id" element={<CasesPage />} />
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
          <Route
            path="admin/model"
            element={
              <RequireManager>
                <AdminModelPage />
              </RequireManager>
            }
          />
          <Route path="home" element={<Navigate to="/overview" replace />} />
          <Route path="*" element={<Empty title="找不到這個頁面" />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
