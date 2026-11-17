import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { useMailConnection } from "../api/hooks";
import styles from "./AppLayout.module.css";

const ROLE_LABELS = { sales: "業務", manager: "主管", admin: "管理員" } as const;

/** 整體骨架：寬螢幕左側導覽 + 右側內容；手機導覽在上方（照 prototypes/recommendations.html） */
export function AppLayout() {
  const { user, isAdmin, logout } = useAuth();
  const mailConnection = useMailConnection();
  const [isCollapsed, setIsCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem("howder.sidebarCollapsed") === "true";
    } catch {
      return false;
    }
  });
  const linkClass = ({ isActive }: { isActive: boolean }) => `${styles.link} ${isActive ? styles.active : ""}`;

  useEffect(() => {
    try {
      window.localStorage.setItem("howder.sidebarCollapsed", String(isCollapsed));
    } catch {
      // 儲存空間不可用時仍保留本次工作階段的收合功能。
    }
  }, [isCollapsed]);

  return (
    <div className={`${styles.app} ${isCollapsed ? styles.appCollapsed : ""}`}>
      <nav className={styles.nav} aria-label="主選單">
        <div className={styles.brandRow}>
          <Link to="/overview" className={styles.brand} aria-label="厚達電子業務推薦系統首頁">
            <span className={styles.mark} aria-hidden="true">
              厚
            </span>
            <span className={styles.brandText}>
              厚達電子<small>業務推薦系統</small>
            </span>
          </Link>
          {mailConnection.data?.mail_mode === "sandbox" && <span className={styles.environmentBadge}>TEST 測試模式</span>}
          <button
            type="button"
            className={styles.collapseToggle}
            onClick={() => setIsCollapsed((current) => !current)}
            aria-label={isCollapsed ? "展開側選單" : "收合側選單"}
            aria-expanded={!isCollapsed}
            title={isCollapsed ? "展開側選單" : "收合側選單"}
          >
            {isCollapsed ? "›" : "‹"}
          </button>
        </div>
        <div className={styles.sections}>
          <section className={styles.homeSection} aria-label="首頁">
            <ul className={styles.list}>
              <li><NavLink to="/overview" className={linkClass} aria-label="首頁" title="首頁"><span className={styles.navIcon} aria-hidden="true">⌂</span><span className={styles.linkText}>首頁</span></NavLink></li>
            </ul>
          </section>
          <section className={styles.section} aria-labelledby="nav-work-title">
            <h2 id="nav-work-title" className={styles.sectionTitle}>工作</h2>
            <ul className={styles.list}>
              <li><NavLink to="/recommendations" className={linkClass} aria-label="今日審核" title="今日審核"><span className={styles.navIcon} aria-hidden="true">✓</span><span className={styles.linkText}>今日審核</span></NavLink></li>
              <li><NavLink to="/campaigns" className={linkClass} aria-label="邀請信" title="邀請信"><span className={styles.navIcon} aria-hidden="true">✉</span><span className={styles.linkText}>邀請信</span></NavLink></li>
              <li><NavLink to="/cases" className={linkClass} aria-label="案件" title="案件"><span className={styles.navIcon} aria-hidden="true">◷</span><span className={styles.linkText}>案件</span></NavLink></li>
            </ul>
          </section>
          {isAdmin && (
            <section className={styles.section} aria-labelledby="nav-admin-title">
              <h2 id="nav-admin-title" className={styles.sectionTitle}>管理</h2>
              <ul className={styles.list}>
                <li><NavLink to="/admin/imports" className={linkClass} aria-label="名單管理" title="名單管理"><span className={styles.navIcon} aria-hidden="true">▤</span><span className={styles.linkText}>名單管理</span></NavLink></li>
                <li><NavLink to="/admin/templates" className={linkClass} aria-label="郵件模板" title="郵件模板"><span className={styles.navIcon} aria-hidden="true">▰</span><span className={styles.linkText}>郵件模板</span></NavLink></li>
              </ul>
            </section>
          )}
        </div>
        {user && (
          <details className={styles.account}>
            <summary className={styles.accountSummary}>
              <span className={styles.accountAvatar} aria-hidden="true">{user.display_name.trim().slice(0, 1) || "U"}</span>
              <span className={styles.userName}>
                {user.display_name}
                <small>{ROLE_LABELS[user.role]}</small>
              </span>
            </summary>
            <div className={styles.accountMenu}>
              <button type="button" className={styles.logout} onClick={logout}>登出</button>
            </div>
          </details>
        )}
      </nav>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
