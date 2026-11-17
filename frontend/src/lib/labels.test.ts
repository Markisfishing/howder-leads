import { activityNote } from "./labels";

describe("往來紀錄備註", () => {
  it("test_m2_01b_contact_activity_note_in_chinese：聯絡人紀錄的代碼翻成中文", () => {
    expect(activityNote("contact_add", "business_card")).toBe("來源：名片");
    expect(activityNote("contact_update", "email,title")).toBe("改了email、職稱");
    expect(activityNote("note", "已電話聯絡")).toBe("已電話聯絡");
    expect(activityNote("contact_add", null)).toBeNull();
  });
});
