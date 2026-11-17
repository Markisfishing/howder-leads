import { Link, useParams } from "react-router-dom";

import { Empty } from "../components/StateView";
import { CompanyDetailPanel } from "./recommendations/CompanyDetailPanel";
import styles from "./Page.module.css";

/** 公司完整頁面（SPEC 6.2 /companies/:id）：和側欄內容相同，方便貼連結給同事 */
export function CompanyPage() {
  const id = Number(useParams().id);
  if (!Number.isInteger(id) || id <= 0) return <Empty title="找不到這家公司" />;

  return (
    <>
      <header className={styles.head}>
        <p className={styles.back}>
          <Link to="/recommendations">← 回推薦清單</Link>
        </p>
        <h1 className={styles.title}>公司詳情</h1>
      </header>
      <section className={styles.card}>
        <CompanyDetailPanel companyId={id} />
      </section>
    </>
  );
}
