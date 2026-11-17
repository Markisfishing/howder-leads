import { useMailConnection, useMailConnectionActions } from "../../api/hooks";
import { Button } from "../../components/Button";
import { InlineError } from "../../components/StateView";
import { formatDateTime } from "../../lib/labels";
import c from "./Campaigns.module.css";

/** Outlook 寄信連結狀態（M2-07c、ADR 0005）。sandbox 只提示「不會真的寄出」。 */
export function MailConnectionBanner() {
  const { data } = useMailConnection();
  const { connect, disconnect } = useMailConnectionActions();
  if (!data) return null;

  if (data.mail_mode === "sandbox") return null;

  const warn = data.status !== "connected";
  return (
    <div className={`${c.banner} ${warn ? c.bannerWarn : ""}`} role={warn ? "alert" : "note"}>
      {data.status === "connected" && (
        <p>Outlook 已連結（{data.connected_at ? formatDateTime(data.connected_at) : ""}），信會從您本人的信箱寄出。</p>
      )}
      {data.status === "not_connected" && <p>寄信前要先連結您的 Outlook，信才能從您本人的信箱寄出。</p>}
      {data.status === "needs_reconnect" && (
        <p>Outlook 連結已失效，排程中的信已暫停。重新連結後會自動恢復寄送。</p>
      )}
      {connect.data && connect.data.resumed > 0 && <p>已恢復 {connect.data.resumed} 封暫停的信。</p>}
      <div className={c.tags}>
        {data.status === "connected" ? (
          <Button size="sm" busy={disconnect.isPending} onClick={() => disconnect.mutate()}>
            取消連結
          </Button>
        ) : (
          <Button size="sm" variant="primary" busy={connect.isPending} onClick={() => connect.mutate()}>
            {data.status === "needs_reconnect" ? "重新連結 Outlook" : "連結 Outlook"}
          </Button>
        )}
      </div>
      <InlineError error={connect.error ?? disconnect.error} />
    </div>
  );
}
