import { Suspense } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Link, NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { Loading } from "./StateView";
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
          <div className={styles.account}>
            {/* 帳號選單用 Radix：點外面、按 Esc 會收起，可用方向鍵操作；空間不夠時自動換邊展開 */}
            <DropdownMenu.Root>
              <DropdownMenu.Trigger className={styles.accountSummary} aria-label={`帳號選單：${user.display_name}`}>
                <span className={styles.userName}>
                  <span className={styles.userNameText} title={user.display_name}>{user.display_name}</span>
                  <small>{ROLE_LABELS[user.role]}</small>
                </span>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content className={styles.accountMenu} side="top" align="start" sideOffset={8} collisionPadding={8}>
                  <DropdownMenu.Item className={styles.logout} onSelect={logout}>登出</DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        )}
      </nav>
      <main className={styles.main}>
        {/* 頁面是延遲載入的（App.tsx），下載期間只在內容區顯示載入中，導覽列不動 */}
        <Suspense fallback={<Loading />}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
