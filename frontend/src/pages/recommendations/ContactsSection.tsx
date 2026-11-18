import { useState } from "react";

import type { CompanyDetail, Contact } from "../../api/types";
import { Button } from "../../components/Button";
import { Tag } from "../../components/Tag";
import { CONTACT_SOURCE_LABELS } from "../../lib/labels";
import { ContactConfirmDialog } from "./ContactConfirmDialog";
import { ContactDialog } from "./ContactDialog";
import styles from "./Contacts.module.css";

type Open =
  | { kind: "add" }
  | { kind: "edit"; contact: Contact }
  | { kind: "unsubscribe"; contact: Contact }
  | { kind: "resubscribe"; contact: Contact }
  | { kind: "delete"; contact: Contact }
  | null;

interface Props {
  company: CompanyDetail;
  /** 沒被別人鎖定，或是主管：可以新增、編輯 */
  canAct: boolean;
  /** 主管／管理員才看得到「刪除個資」 */
  isManager: boolean;
}

/** 區塊：聯絡人 · 新增、編輯、退訂、取消退訂（主管，M3-18）、個資刪除（M2-01b）。退訂不受鎖定限制，收到就要能標記 */
export function ContactsSection({ company: c, canAct, isManager }: Props) {
  const [open, setOpen] = useState<Open>(null);
  const close = () => setOpen(null);

  return (
    <section className={styles.section} aria-labelledby="contacts-title">
      <div className={styles.head}>
        <h3 id="contacts-title" className={styles.title}>
          聯絡人
        </h3>
        <Button size="sm" disabled={!canAct} onClick={() => setOpen({ kind: "add" })}>
          新增聯絡人
        </Button>
      </div>

      {c.contacts.length === 0 ? (
        <p className={styles.hint}>還沒有聯絡人；要寄邀請信前，先新增至少一位。</p>
      ) : (
        <ul className={styles.list}>
          {c.contacts.map((p) => (
            <li key={p.contact_id} className={styles.item}>
              <div className={styles.info}>
                <p className={styles.name}>
                  {p.name ?? "（未填姓名）"}
                  {p.title && <span className={styles.muted}> · {p.title}</span>}
                </p>
                <p className={styles.email}>{p.email}</p>
                <div className={styles.tags}>
                  <Tag>{CONTACT_SOURCE_LABELS[p.source] ?? p.source}</Tag>
                  {p.is_verified && <Tag tone="info">已確認</Tag>}
                  {p.unsubscribed && <Tag tone="warning">已退訂</Tag>}
                </div>
              </div>
              <div className={styles.rowActions}>
                <Button
                  size="sm"
                  disabled={!canAct}
                  aria-label={`編輯 ${p.name ?? p.email}`}
                  onClick={() => setOpen({ kind: "edit", contact: p })}
                >
                  編輯
                </Button>
                {!p.unsubscribed && (
                  <Button
                    size="sm"
                    aria-label={`將 ${p.name ?? p.email} 標記退訂`}
                    onClick={() => setOpen({ kind: "unsubscribe", contact: p })}
                  >
                    退訂
                  </Button>
                )}
                {p.unsubscribed && isManager && (
                  <Button
                    size="sm"
                    aria-label={`取消 ${p.name ?? p.email} 的退訂`}
                    onClick={() => setOpen({ kind: "resubscribe", contact: p })}
                  >
                    取消退訂
                  </Button>
                )}
                {isManager && (
                  <Button
                    size="sm"
                    variant="danger"
                    aria-label={`刪除 ${p.name ?? p.email} 的個資`}
                    onClick={() => setOpen({ kind: "delete", contact: p })}
                  >
                    刪除…
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {open?.kind === "add" && <ContactDialog companyId={c.company_id} contact={null} onClose={close} />}
      {open?.kind === "edit" && <ContactDialog companyId={c.company_id} contact={open.contact} onClose={close} />}
      {(open?.kind === "unsubscribe" || open?.kind === "resubscribe" || open?.kind === "delete") && (
        <ContactConfirmDialog kind={open.kind} contact={open.contact} onClose={close} />
      )}
    </section>
  );
}
