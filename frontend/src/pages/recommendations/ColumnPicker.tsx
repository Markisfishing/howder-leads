import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import {
  ALL_COLUMNS,
  COLUMN_LABELS,
  type ColumnKey,
  DEFAULT_COLUMNS,
  MAX_COLUMNS,
  REQUIRED_COLUMNS,
  toggleColumn,
} from "../../lib/columns";
import styles from "./Recommendations.module.css";

interface Props {
  open: boolean;
  columns: ColumnKey[];
  onChange: (cols: ColumnKey[]) => void;
  onClose: () => void;
}

/** 區塊：欄位自選對話框（M3-13b、F-REC-8）· 最多 10 欄，記在這台瀏覽器 */
export function ColumnPicker({ open, columns, onChange, onClose }: Props) {
  const full = columns.length >= MAX_COLUMNS;
  return (
    <Modal open={open} onOpenChange={(o) => !o && onClose()} title="顯示欄位">
      <p className={styles.meta} aria-live="polite">
        已選 {columns.length} / {MAX_COLUMNS} 欄{full && "（已達上限，先取消一欄才能再加）"}。這些欄位會顯示在完整清單。
      </p>
      <fieldset className={styles.columnGrid}>
        <legend className="visually-hidden">要顯示的欄位</legend>
        {ALL_COLUMNS.map((k) => {
          const checked = columns.includes(k);
          const required = REQUIRED_COLUMNS.includes(k);
          return (
            <label key={k} className={styles.radio}>
              <input
                type="checkbox"
                checked={checked}
                disabled={required || (!checked && full)}
                onChange={() => onChange(toggleColumn(columns, k))}
              />
              {COLUMN_LABELS[k]}
              {required && "（必選）"}
            </label>
          );
        })}
      </fieldset>
      <div className={styles.headActions}>
        <Button onClick={() => onChange(DEFAULT_COLUMNS)}>還原預設</Button>
        <Button variant="primary" onClick={onClose}>
          完成
        </Button>
      </div>
    </Modal>
  );
}
