import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { Button } from "./Button";
import { Modal } from "./Modal";

function FocusHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>開啟對話框</Button>
      <Modal open={open} onOpenChange={setOpen} title="測試對話框">
        <p>內容</p>
      </Modal>
    </>
  );
}

describe("Modal 焦點管理", () => {
  it("開啟時聚焦關閉鈕，關閉後回到原本觸發按鈕", async () => {
    render(<FocusHarness />);
    const trigger = screen.getByRole("button", { name: "開啟對話框" });
    trigger.focus();
    fireEvent.click(trigger);
    const close = await screen.findByRole("button", { name: "關閉" });
    expect(close).toHaveFocus();

    fireEvent.click(close);
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
