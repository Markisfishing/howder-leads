import { useState, type FormEvent } from "react";

import { AUTH_MODE, useAuth } from "../auth/AuthProvider";
import { Button } from "../components/Button";
import { InlineError } from "../components/StateView";
import styles from "./LoginPage.module.css";

// dev 模式的快速登入帳號（假資料，對應後端 BOOTSTRAP_ADMIN_EMAILS 預設值）
const DEV_ACCOUNTS = [
  { email: "admin@example.com", label: "管理員" },
  { email: "sales1@example.com", label: "業務一" },
  { email: "sales2@example.com", label: "業務二" },
];

export function LoginPage() {
  const { loginDev, loginEntra, error } = useAuth();
  const [email, setEmail] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (email.trim()) void loginDev(email);
  };

  return (
    <main className={styles.page}>
      <section className={styles.card} aria-labelledby="login-title">
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            厚
          </span>
          <div>
            <h1 id="login-title" className={styles.title}>
              厚達電子 業務推薦系統
            </h1>
            <p className={styles.sub}>潛在客戶推薦與邀請信</p>
          </div>
        </div>

        {AUTH_MODE === "entra" ? (
          <Button variant="primary" onClick={() => void loginEntra()}>
            使用公司 Microsoft 帳號登入
          </Button>
        ) : (
          <>
            <p className={styles.notice}>開發模式：輸入 email 即可登入，正式環境會改用公司 Microsoft 帳號。</p>
            <form onSubmit={submit} className={styles.form}>
              <label className={styles.field}>
                <span>Email</span>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  autoComplete="username"
                />
              </label>
              <Button type="submit" variant="primary">
                登入
              </Button>
            </form>
            <div className={styles.quick}>
              <span>快速登入：</span>
              {DEV_ACCOUNTS.map((a) => (
                <Button key={a.email} size="sm" onClick={() => void loginDev(a.email)}>
                  {a.label}
                </Button>
              ))}
            </div>
          </>
        )}
        <InlineError error={error} />
      </section>
    </main>
  );
}
