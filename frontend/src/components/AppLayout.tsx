import { Link, NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import styles from "./AppLayout.module.css";

const ROLE_LABELS = { sales: "業務", manager: "主管", admin: "管理員" } as const;

/** 整體骨架：寬螢幕左側導覽 + 右側內容；手機導覽在上方（照 prototypes/recommendations.html） */
export function AppLayout() {
  const { user, isAdmin, isManager, logout } = useAuth();
  const linkClass = ({ isActive }: { isActive: boolean }) => `${styles.link} ${isActive ? styles.active : ""}`;

  return (
    <div className={styles.app}>
      <nav className={styles.nav} aria-label="主選單">
        <Link to="/overview" className={styles.brand} aria-label="厚達電子業務推薦系統首頁">
          <span className={styles.mark} aria-hidden="true">
            厚
          </span>
          <span className={styles.brandText}>
            厚達電子<small>業務推薦系統</small>
          </span>
        </Link>
        <div className={styles.sections}>
          <section className={styles.homeSection} aria-label="首頁">
            <ul className={styles.list}>
              <li><NavLink to="/overview" className={linkClass}>首頁</NavLink></li>
            </ul>
          </section>
          <section className={styles.section} aria-labelledby="nav-work-title">
            <h2 id="nav-work-title" className={styles.sectionTitle}>工作</h2>
            <ul className={styles.list}>
              <li><NavLink to="/recommendations" className={linkClass}>今日審核</NavLink></li>
              <li><NavLink to="/campaigns" className={linkClass}>邀請信</NavLink></li>
              <li><NavLink to="/cases" className={linkClass}>案件</NavLink></li>
              <li><NavLink to="/performance" className={linkClass}>績效</NavLink></li>
            </ul>
          </section>
          {isManager && (
            <section className={styles.section} aria-labelledby="nav-admin-title">
              <h2 id="nav-admin-title" className={styles.sectionTitle}>管理</h2>
              <ul className={styles.list}>
                {isAdmin && <li><NavLink to="/admin/imports" className={linkClass}>名單管理</NavLink></li>}
                {isAdmin && <li><NavLink to="/admin/templates" className={linkClass}>郵件模板</NavLink></li>}
                <li><NavLink to="/admin/model" className={linkClass}>名單品質</NavLink></li>
              </ul>
            </section>
          )}
        </div>
        {user && (
          <details className={styles.account}>
            <summary className={styles.accountSummary}>
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
