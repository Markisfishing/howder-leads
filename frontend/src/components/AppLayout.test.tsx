import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AppLayout } from "./AppLayout";

const logout = vi.fn();
const longName = "王小明明明明明明明明明明明明明明";

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { display_name: longName, role: "manager" },
    isAdmin: false,
    isManager: true,
    logout,
  }),
}));

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/overview"]}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/overview" element={<p>首頁內容</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("AppLayout 帳號選單", () => {
  beforeEach(() => logout.mockClear());

  it("用鍵盤可以打開選單，按 Esc 收起並回到帳號按鈕", async () => {
    renderLayout();
    const trigger = screen.getByRole("button", { name: `帳號選單：${longName}` });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Enter" });

    expect(await screen.findByRole("menuitem", { name: "登出" })).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("選「登出」會呼叫登出並收起選單", async () => {
    renderLayout();
    const trigger = screen.getByRole("button", { name: `帳號選單：${longName}` });
    fireEvent.keyDown(trigger, { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "登出" }));

    expect(logout).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
  });

  it("名字太長被截斷時，滑鼠移上去仍看得到完整名字", () => {
    renderLayout();
    expect(screen.getByTitle(longName)).toHaveTextContent(longName);
    expect(screen.getByText("主管")).toBeInTheDocument();
  });
});
