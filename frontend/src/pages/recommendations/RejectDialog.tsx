import { useState } from "react";
import type { RefObject } from "react";

import { useDimensions, useReview } from "../../api/hooks";
import type { RejectReason } from "../../api/types";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { InlineError } from "../../components/StateView";
import { REJECT_REASON_LABELS } from "../../lib/labels";
import styles from "./Recommendations.module.css";

interface Props {
  open: boolean;
  companyIds: number[];
  onClose: () => void;
  onDone: (count: number) => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
}

/** 區塊：排除對話框 · 排除一定要選原因，原因會進名單品質報表（F-REC-3） */
export function RejectDialog({ open, companyIds, onClose, onDone, returnFocusRef }: Props) {
  const review = useReview();
  const { data: dims } = useDimensions();
  const [reason, setReason] = useState<RejectReason | "">("");
  const [industryId, setIndustryId] = useState("");
  const [note, setNote] = useState("");

  const close = () => {
    setReason("");
    setIndustryId("");
    setNote("");
    review.reset();
    onClose();
  };

  const submit = () => {
    if (!reason) return;
    review.mutate(
      {
        company_ids: companyIds,
        decision: "rejected",
        reject_reason: reason,
        note: note.trim() || undefined,
        corrected_industry_id: reason === "wrong_industry" && industryId ? Number(industryId) : undefined,
      },
      {
        onSuccess: (res) => {
          onDone(res.updated);
          close();
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && close()}
      title={`排除 ${companyIds.length} 家公司`}
      description="請選擇排除原因，原因會列入名單品質報表。"
      returnFocusRef={returnFocusRef}
      footer={
        <>
          <Button onClick={close}>取消</Button>
          <Button variant="danger" onClick={submit} disabled={!reason} busy={review.isPending}>
            確認排除
          </Button>
        </>
      }
    >
      <fieldset className={styles.reasons}>
        <legend className={styles.fieldLabel}>排除原因（必選）</legend>
        {(dims?.reject_reasons ?? (Object.keys(REJECT_REASON_LABELS) as RejectReason[])).map((r) => (
          <label key={r} className={styles.radio}>
            <input type="radio" name="reason" value={r} checked={reason === r} onChange={() => setReason(r)} />
            {REJECT_REASON_LABELS[r]}
          </label>
        ))}
      </fieldset>

      {reason === "wrong_industry" && (
        <label className={styles.field}>
          <span className={styles.fieldLabel}>正確的產業（選填）</span>
          <select className={styles.input} value={industryId} onChange={(e) => setIndustryId(e.target.value)}>
            <option value="">不確定</option>
            {dims?.industries.map((i) => (
              <option key={i.industry_id} value={i.industry_id}>
                {i.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className={styles.field}>
        <span className={styles.fieldLabel}>備註（選填）</span>
        <textarea className={styles.input} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <InlineError error={review.error} />
    </Modal>
  );
}
