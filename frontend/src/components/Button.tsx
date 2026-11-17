import type { ButtonHTMLAttributes } from "react";

import styles from "./Button.module.css";

type Variant = "primary" | "ghost" | "danger";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "md" | "sm";
  busy?: boolean;
}

/** 主要按鈕用磚紅；排除／危險動作用 danger（更暗、偏棕），一律附文字（SPEC 6.3） */
export function Button({ variant = "ghost", size = "md", busy = false, className, children, disabled, ...rest }: Props) {
  const cls = [styles.btn, styles[variant], size === "sm" ? styles.sm : "", className ?? ""].join(" ");
  return (
    <button type="button" className={cls} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy ? "處理中…" : children}
    </button>
  );
}
