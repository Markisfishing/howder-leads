import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import styles from "./AppLayout.module.css";

const ROLE_LABELS = { sales: "業務", manager: "主管", admin: "管理員" } as const;

/** 整體骨架：寬螢幕左側導覽 + 右側內容；手機導覽在上方（照 prototypes/recommendations.html） */
export function AppLayout() {
  const { user, isAdmin, logout } = useAuth();
  const linkClass = ({ isActive }: { isActive: boolean }) => `${styles.link} ${isActive ? styles.active : ""}`;

  return (
    <div className={styles.app}>
      <nav className={styles.nav} aria-label="主選單">
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            厚
          </span>
          <span className={styles.brandText}>
            厚達電子<small>業務推薦系統</small>
          </span>
        </div>
        <ul className={styles.list}>
          <li>
            <NavLink to="/" end className={linkClass}>
              推薦清單
            </NavLink>
          </li>
          <li>
            <span className={`${styles.link} ${styles.disabled}`} aria-disabled="true" title="M2 開放">
              邀請信<small>即將推出</small>
            </span>
          </li>
          <li>
            <span className={`${styles.link} ${styles.disabled}`} aria-disabled="true" title="M4 開放">
              績效<small>即將推出</small>
            </span>
          </li>
          {isAdmin && (
            <li>
              <NavLink to="/admin/imports" className={linkClass}>
                名單匯入
              </NavLink>
            </li>
          )}
          {isAdmin && (
            <li>
              <NavLink to="/admin/templates" className={linkClass}>
                郵件模板
              </NavLink>
            </li>
          )}
        </ul>
        {user && (
          <div className={styles.user}>
            <span className={styles.userName}>
              {user.display_name}
              <small>{ROLE_LABELS[user.role]}</small>
            </span>
            <button type="button" className={styles.logout} onClick={logout}>
              登出
            </button>
          </div>
        )}
      </nav>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
