import { useRefreshSiteSummary } from "../../api/hooks";
import type { CompanyDetail } from "../../api/types";
import { Button } from "../../components/Button";
import { InlineError } from "../../components/StateView";
import { Tag } from "../../components/Tag";
import { errorMessage } from "../../api/errorMessages";
import { formatDateTime } from "../../lib/labels";
import styles from "./Contacts.module.css";

interface Props {
  company: CompanyDetail;
  /** 沒被別人鎖定，或是主管 */
  canAct: boolean;
}

/** 區塊：官網摘要（M4-08e、SPEC 7.4）· AI 寫信用的公司背景；抓不到時寫信改用推薦理由，不擋產生草稿 */
export function SiteSummarySection({ company: c, canAct }: Props) {
  const refresh = useRefreshSiteSummary();
  const s = c.site_summary;
  const hasSite = !!c.website_url;

  return (
    <section className={styles.section} aria-labelledby="site-summary-title">
      <div className={styles.head}>
        <h3 id="site-summary-title" className={styles.title}>
          官網摘要
        </h3>
        <Button
          size="sm"
          disabled={!canAct || !hasSite}
          busy={refresh.isPending}
          onClick={() => refresh.mutate(c.company_id)}
        >
          重新抓取
        </Button>
      </div>

      {!hasSite ? (
        <p className={styles.hint}>這家公司沒有官網，寫信時會改用推薦理由。</p>
      ) : s === null || s === undefined ? (
        <p className={styles.hint}>還沒有摘要：系統會在背景抓取官網（可能需要幾分鐘），也可以按「重新抓取」。</p>
      ) : s.status === "ok" ? (
        <>
          <p>{s.summary}</p>
          <p className={styles.hint}>
            <Tag tone="info">AI 整理</Tag> 抓取時間 {formatDateTime(s.fetched_at)}。只收產品與產業描述，不含人名、email、電話。
          </p>
        </>
      ) : (
        <p className={styles.hint} role="status">
          <Tag tone="warning">抓取失敗</Tag> {errorMessage(s.error_code ?? "", "原因不明")}。寫信時會改用推薦理由。
        </p>
      )}
      <InlineError error={refresh.error} />
    </section>
  );
}
