import { activityNote, CAMPAIGN_STATUS_LABELS, displayTemplateName } from "./labels";

describe("往來紀錄備註", () => {
  it("test_m2_01b_contact_activity_note_in_chinese：聯絡人紀錄的代碼翻成中文", () => {
    expect(activityNote("contact_add", "business_card")).toBe("來源：名片");
    expect(activityNote("contact_update", "email,title")).toBe("改了email、職稱");
    expect(activityNote("note", "已電話聯絡")).toBe("已電話聯絡");
    expect(activityNote("contact_add", null)).toBeNull();
  });
});

describe("批次狀態", () => {
  it("test_m2_16_ready_label：草稿都審完、還沒按寄出顯示「待寄出」", () => {
    expect(CAMPAIGN_STATUS_LABELS.ready).toBe("待寄出");
    expect(CAMPAIGN_STATUS_LABELS.reviewing).toBe("待審核");
  });
});

describe("模板名稱", () => {
  it("test_template_name_hides_internal_placeholder_note：正式 UI 不顯示開發註記", () => {
    expect(displayTemplateName("初版邀請信（佔位文字，待 SPEC 11-5 確認）")).toBe("初版邀請信");
  });
});
