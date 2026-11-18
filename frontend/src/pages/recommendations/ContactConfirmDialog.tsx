import { useState } from "react";

import { useDeleteContact, useUnsubscribeContact } from "../../api/hooks";
import type { Contact } from "../../api/types";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { InlineError } from "../../components/StateView";
import styles from "./Contacts.module.css";

interface Props {
  kind: "unsubscribe" | "delete";
  contact: Contact;
  onClose: () => void;
}

function who(c: Contact): string {
  return c.name ? `${c.name}（${c.email}）` : c.email;
}

/** 區塊：退訂（F-CASE-5）與個資刪除（SPEC 9）的確認對話框 · 都要再確認一次 */
export function ContactConfirmDialog({ kind, contact, onClose }: Props) {
  const unsubscribe = useUnsubscribeContact();
  const remove = useDeleteContact();
  const [text, setText] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [wholeCompany, setWholeCompany] = useState(false);

  const isDelete = kind === "delete";
  const mutation = isDelete ? remove : unsubscribe;
  const canSubmit = isDelete ? text.trim() !== "" && understood : true;

  const submit = () => {
    if (isDelete) remove.mutate({ id: contact.contact_id, reason: text.trim() }, { onSuccess: onClose });
    else
      unsubscribe.mutate(
        { id: contact.contact_id, note: text.trim() || undefined, wholeCompany },
        { onSuccess: onClose },
      );
  };

  return (
    <Modal
      open
      onOpenChange={(o) => !o && onClose()}
      title={isDelete ? "刪除聯絡人個資" : "標記退訂"}
      description={
        isDelete
          ? `會永久刪除 ${who(contact)}，以及寄給他的草稿和信件，無法復原。只在對方要求刪除個資時使用。`
          : `只有 ${who(contact)} 改成已退訂，之後不會再寄信給他。這家公司其他聯絡人都退訂，或勾選下方「整家公司不再聯絡」時，公司才會改成「不再聯絡」。`
      }
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="danger" disabled={!canSubmit} busy={mutation.isPending} onClick={submit}>
            {isDelete ? "永久刪除" : "確認退訂"}
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        <label className={styles.field}>
          <span className={styles.label}>{isDelete ? "刪除原因（必填）" : "備註（選填，例如：電話告知）"}</span>
          <textarea
            className={styles.input}
            rows={2}
            maxLength={500}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={isDelete ? "例如：客戶來信要求刪除個人資料" : undefined}
          />
        </label>
        {!isDelete && (
          <label className={styles.check}>
            <input type="checkbox" checked={wholeCompany} onChange={(e) => setWholeCompany(e.target.checked)} />
            客戶表示整家公司都不要再聯絡（公司改成「不再聯絡」，進行中的案件結案為失敗）
          </label>
        )}
        {isDelete && (
          <label className={styles.check}>
            <input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />
            我了解刪除後無法復原
          </label>
        )}
      </div>
      <InlineError error={mutation.error} />
    </Modal>
  );
}
