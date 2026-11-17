import type { ReactNode } from "react";

import type { Tone } from "../lib/labels";
import styles from "./Tag.module.css";

/** 狀態標籤：一律淡底 + 深字 */
export function Tag({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`${styles.tag} ${styles[tone]}`}>{children}</span>;
}
