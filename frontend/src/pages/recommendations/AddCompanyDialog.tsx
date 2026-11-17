import { useState, type FormEvent } from "react";

import { useCreateCompany, useDimensions } from "../../api/hooks";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { InlineError } from "../../components/StateView";
import styles from "./Recommendations.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (companyId: number) => void;
}

/** 區塊：手動加入公司 · 業務自己找到、模型漏掉的公司（F-REC-6） */
export function AddCompanyDialog({ open, onClose, onCreated }: Props) {
  const create = useCreateCompany();
  const { data: dims } = useDimensions();
  const [taxId, setTaxId] = useState("");
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [industryId, setIndustryId] = useState("");

  const taxIdValid = /^\d{8}$/.test(taxId);

  const close = () => {
    setTaxId("");
    setName("");
    setWebsite("");
    setIndustryId("");
    create.reset();
    onClose();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!taxIdValid || !name.trim()) return;
    create.mutate(
      {
        tax_id: taxId,
        name: name.trim(),
        website_url: website.trim() || undefined,
        industry_id: industryId ? Number(industryId) : undefined,
      },
      {
        onSuccess: (c) => {
          close();
          onCreated(c.company_id);
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && close()}
      title="手動加入公司"
      description="加入後會進入「待審」，並標記為手動加入。"
      footer={
        <>
          <Button onClick={close}>取消</Button>
          <Button
            variant="primary"
            type="submit"
            form="add-company"
            disabled={!taxIdValid || !name.trim()}
            busy={create.isPending}
          >
            加入
          </Button>
        </>
      }
    >
      <form id="add-company" className={styles.form} onSubmit={submit}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>統編（8 碼）</span>
          <input
            className={`${styles.input} mono`}
            inputMode="numeric"
            maxLength={8}
            required
            value={taxId}
            onChange={(e) => setTaxId(e.target.value.replace(/\D/g, ""))}
            aria-invalid={taxId.length > 0 && !taxIdValid}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>公司名稱</span>
          <input className={styles.input} required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>官網（選填）</span>
          <input
            className={styles.input}
            type="url"
            placeholder="https://"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>產業（選填）</span>
          <select className={styles.input} value={industryId} onChange={(e) => setIndustryId(e.target.value)}>
            <option value="">不確定</option>
            {dims?.industries.map((i) => (
              <option key={i.industry_id} value={i.industry_id}>
                {i.name}
              </option>
            ))}
          </select>
        </label>
        <InlineError error={create.error} />
      </form>
    </Modal>
  );
}
