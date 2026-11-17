import { useState } from "react";

import { useCreateContact, usePatchContact } from "../../api/hooks";
import type { ContactPatch } from "../../api/endpoints";
import type { Contact, ContactSource } from "../../api/types";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { InlineError } from "../../components/StateView";
import { CONTACT_SOURCE_LABELS } from "../../lib/labels";
import styles from "./Contacts.module.css";

interface Props {
  companyId: number;
  /** 有值 = 編輯這位聯絡人；沒有 = 新增 */
  contact: Contact | null;
  onClose: () => void;
}

const SOURCES = Object.keys(CONTACT_SOURCE_LABELS) as ContactSource[];

/** 區塊：新增／編輯聯絡人 · 來源必填（SPEC 9 個資），email 格式與重複由後端檢查（M2-01b） */
export function ContactDialog({ companyId, contact, onClose }: Props) {
  const create = useCreateContact();
  const patch = usePatchContact();
  const [email, setEmail] = useState(contact?.email ?? "");
  const [source, setSource] = useState<ContactSource | "">(contact?.source ?? "");
  const [name, setName] = useState(contact?.name ?? "");
  const [title, setTitle] = useState(contact?.title ?? "");
  const [verified, setVerified] = useState(contact?.is_verified ?? false);

  const mutation = contact ? patch : create;
  const canSubmit = email.trim() !== "" && source !== "";

  const submit = () => {
    if (!source) return;
    if (!contact) {
      create.mutate(
        {
          company_id: companyId,
          email: email.trim(),
          source,
          name: name.trim() || undefined,
          title: title.trim() || undefined,
          is_verified: verified,
        },
        { onSuccess: onClose },
      );
      return;
    }
    // 編輯：只送有改的欄位
    const body: ContactPatch = {};
    if (email.trim().toLowerCase() !== contact.email) body.email = email.trim();
    if (source !== contact.source) body.source = source;
    if (name.trim() !== (contact.name ?? "")) body.name = name.trim() || null;
    if (title.trim() !== (contact.title ?? "")) body.title = title.trim() || null;
    if (verified !== contact.is_verified) body.is_verified = verified;
    if (Object.keys(body).length === 0) {
      onClose();
      return;
    }
    patch.mutate({ id: contact.contact_id, body }, { onSuccess: onClose });
  };

  return (
    <Modal
      open
      onOpenChange={(o) => !o && onClose()}
      title={contact ? "編輯聯絡人" : "新增聯絡人"}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!canSubmit} busy={mutation.isPending} onClick={submit}>
            儲存
          </Button>
        </>
      }
    >
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) submit();
        }}
      >
        <label className={styles.field}>
          <span className={styles.label}>email（必填）</span>
          <input
            className={styles.input}
            type="email"
            inputMode="email"
            autoComplete="off"
            required
            value={email}
            disabled={contact?.unsubscribed}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="contact@example.com"
          />
          {contact?.unsubscribed && <span className={styles.hint}>已退訂，不能改 email</span>}
        </label>
        <label className={styles.field}>
          <span className={styles.label}>來源（必填）</span>
          <select
            className={styles.input}
            required
            value={source}
            onChange={(e) => setSource(e.target.value as ContactSource | "")}
          >
            <option value="">請選擇從哪裡取得</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {CONTACT_SOURCE_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          <span className={styles.label}>姓名（選填）</span>
          <input className={styles.input} value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>職稱（選填）</span>
          <input className={styles.input} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} />
        </label>
        <label className={styles.check}>
          <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
          已確認這個 email 是對的（例如對方回過信、名片上有）
        </label>
        {/* 讓 Enter 可以送出 */}
        <button type="submit" hidden aria-hidden tabIndex={-1} />
      </form>
      <InlineError error={mutation.error} />
    </Modal>
  );
}
