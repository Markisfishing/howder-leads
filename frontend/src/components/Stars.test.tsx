import { render, screen } from "@testing-library/react";

import { Stars } from "./Stars";

describe("Stars（CLAUDE.md 7-7：星級旁一定附等級文字）", () => {
  it("test_f_rec_1_stars_have_text_label：有等級文字與無障礙名稱", () => {
    render(<Stars stars={5} priority="A" />);
    expect(screen.getByRole("img")).toHaveAccessibleName(/5 星，A/);
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("test_f_rec_6_unrated_manual_company：手動加入沒評分的公司顯示「未評分」", () => {
    render(<Stars stars={0} priority={null} />);
    expect(screen.getByText("未評分")).toBeInTheDocument();
  });

  it("test_f_rec_1_decimal_fit_stars：小數星等顯示數字，星星四捨五入", () => {
    render(<Stars stars={5} priority="A" fitStars="4.5" />);
    expect(screen.getByRole("img")).toHaveAccessibleName(/4\.5 星，A/);
    expect(screen.getByText("4.5")).toBeInTheDocument();
    expect(screen.getByText("★★★★★")).toBeInTheDocument(); // 4.5 四捨五入成 5 顆
  });
});
