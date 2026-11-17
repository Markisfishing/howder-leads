import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

import styles from "./Modal.module.css";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  /** side = 從右側滑出的詳情側欄 */
  variant?: "center" | "side";
}

/** 對話框與側欄：互動與無障礙交給 Radix（焦點鎖定、Esc 關閉），外觀用 tokens */
export function Modal({ open, onOpenChange, title, description, children, footer, variant = "center" }: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={styles.overlay} />
        <Dialog.Content
          className={`${styles.content} ${styles[variant]}`}
          {...(description ? {} : { "aria-describedby": undefined })}
        >
          <header className={styles.head}>
            <Dialog.Title className={styles.title}>{title}</Dialog.Title>
            <Dialog.Close className={styles.close} aria-label="關閉">
              ✕
            </Dialog.Close>
          </header>
          {description && <Dialog.Description className={styles.desc}>{description}</Dialog.Description>}
          <div className={styles.body}>{children}</div>
          {footer && <footer className={styles.foot}>{footer}</footer>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
