import { useState } from "react";

import { useDeleteContact, useResubscribeContact, useUnsubscribeContact } from "../../api/hooks";
import type { Contact } from "../../api/types";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { InlineError } from "../../components/StateView";
import styles from "./Contacts.module.css";

interface Props {
  kind: "unsubscribe" | "resubscribe" | "delete";
  contact: Contact;
  onClose: () => void;
}

function who(c: Contact): string {
  return c.name ? `${c.name}（${c.email}）` : c.email;
}

/** 區塊：退訂（F-CASE-5）與個資刪除（SPEC 9）的確認對話框 · 都要再確認一次 */
export function ContactConfirmDialog({ kind, contact, onClose }: Props) {
  const unsubscribe = useUnsubscribeContact();
  const resubscribe = useResubscribeContact();
  const remove = useDeleteContact();
  const [text, setText] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [wholeCompany, setWholeCompany] = useState(false);

  const isDelete = kind === "delete";
  const isResubscribe = kind === "resubscribe";
  const mutation = isDelete ? remove : isResubscribe ? resubscribe : unsubscribe;
  const canSubmit = isDelete ? text.trim() !== "" && understood : isResubscribe ? text.trim() !== "" : true;

  const submit = () => {
    if (isDelete) remove.mutate({ id: contact.contact_id, reason: text.trim() }, { onSuccess: onClose });
    else if (isResubscribe) resubscribe.mutate({ id: contact.contact_id, reason: text.trim() }, { onSuccess: onClose });
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
      title={isDelete ? "刪除聯絡人個資" : isResubscribe ? "取消退訂" : "標記退訂"}
      description={
        isResubscribe
          ? `${who(contact)} 會恢復成可聯絡。若公司因退訂而是「不再聯絡」，會退回「已通過」重新進入候選名單，先前的寄信與回覆進度不會帶回來。只在客戶明確同意恢復聯絡時使用。`
          : isDelete
          ? `會永久刪除 ${who(contact)}，以及寄給他的草稿和信件，無法復原。只在對方要求刪除個資時使用。`
          : `只有 ${who(contact)} 改成已退訂，之後不會再寄信給他。這家公司其他聯絡人都退訂，或勾選下方「整家公司不再聯絡」時，公司才會改成「不再聯絡」。`
      }
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="danger" disabled={!canSubmit} busy={mutation.isPending} onClick={submit}>
            {isDelete ? "永久刪除" : isResubscribe ? "確認取消退訂" : "確認退訂"}
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        <label className={styles.field}>
          <span className={styles.label}>
            {isDelete ? "刪除原因（必填）" : isResubscribe ? "取消退訂原因（必填）" : "備註（選填，例如：電話告知）"}
          </span>
          <textarea
            className={styles.input}
            rows={2}
            maxLength={500}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={
              isDelete ? "例如：客戶來信要求刪除個人資料" : isResubscribe ? "例如：客戶來信同意恢復聯絡" : undefined
            }
          />
        </label>
        {kind === "unsubscribe" && (
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
