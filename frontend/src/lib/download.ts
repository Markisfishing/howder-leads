/** 把後端回傳的檔案（CSV）存到使用者電腦。檔名帶台灣日期。 */
export function saveBlob(blob: Blob, prefix: string): void {
  const day = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Taipei" }).format(new Date());
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${prefix}_${day}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
