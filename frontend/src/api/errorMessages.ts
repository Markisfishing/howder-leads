// 後端錯誤碼 → 給業務看的中文訊息。沒有列在這裡的錯誤碼，顯示後端給的訊息。
const MESSAGES: Record<string, string> = {
  NETWORK_ERROR: "無法連線到伺服器，請確認網路後再試一次",
  UNAUTHORIZED: "請先登入",
  INVALID_TOKEN: "登入已失效，請重新登入",
  USER_DISABLED: "這個帳號已停用，請聯絡管理員",
  FORBIDDEN: "沒有權限使用這個功能",
  NOT_FOUND: "找不到這個頁面或資料",
  VALIDATION_ERROR: "輸入資料格式不正確",
  COMPANY_NOT_FOUND: "找不到這家公司",
  COMPANY_EXISTS: "這個統編已經在名單裡了",
  INVALID_TAX_ID: "統編必須是 8 碼數字",
  COMPANY_LOCKED: "這家公司由其他業務負責中",
  NOT_OWNER: "只有負責業務或主管可以釋出這家公司",
  REJECT_REASON_REQUIRED: "排除時一定要選原因",
  INVALID_TRANSITION: "這家公司目前的狀態不能這樣變更",
  INVALID_EMAIL: "email 格式不正確",
  INVALID_SOURCE: "請選擇聯絡人來源",
  CONTACT_EXISTS: "這家公司已經有這個 email 的聯絡人",
  CONTACT_NOT_FOUND: "找不到這位聯絡人，可能已被刪除",
  CONTACT_UNSUBSCRIBED: "已退訂的聯絡人不能改 email",
  DELETE_REASON_REQUIRED: "刪除個資要填寫原因",
  IMPORT_FILE_TOO_LARGE: "檔案超過 10 MB",
  IMPORT_UNSUPPORTED_TYPE: "只支援 .csv 或 .xlsx 檔",
  IMPORT_DECODE_FAILED: "無法讀取檔案編碼，請存成 UTF-8 或 Big5 的 CSV",
  IMPORT_NO_PRIORITY: "找不到含「優先級」欄位的工作表",
  IMPORT_NOT_PREVIEWED: "這個匯入批次已經確認或取消過了",
};

// 這些錯誤的後端訊息比較具體（會列出哪幾家公司、哪一列），直接顯示後端訊息
const PREFER_SERVER = new Set(["REVIEW_REJECTED", "INVALID_TRANSITION", "COMPANY_LOCKED"]);

export function errorMessage(code: string, serverMessage: string): string {
  if (PREFER_SERVER.has(code) && serverMessage) return serverMessage;
  return MESSAGES[code] ?? (serverMessage || "發生未預期的錯誤，請稍後再試");
}
