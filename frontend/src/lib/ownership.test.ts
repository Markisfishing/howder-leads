import { isLockedByOther } from "./ownership";

const NOW = Date.parse("2026-11-17T00:00:00Z");
const future = "2026-12-01T00:00:00Z";
const past = "2026-11-01T00:00:00Z";

describe("認領鎖定（SPEC 第 4 節）", () => {
  it("test_lock_other_owner_within_period：別人認領且未過期 → 鎖定", () => {
    expect(isLockedByOther({ owner_id: 2, owner_locked_until: future }, 1, NOW)).toBe(true);
  });
  it("test_lock_own_company：自己認領的不算鎖定", () => {
    expect(isLockedByOther({ owner_id: 1, owner_locked_until: future }, 1, NOW)).toBe(false);
  });
  it("test_lock_expired：鎖定過期就可以操作", () => {
    expect(isLockedByOther({ owner_id: 2, owner_locked_until: past }, 1, NOW)).toBe(false);
  });
  it("test_lock_no_owner：沒人負責不鎖定", () => {
    expect(isLockedByOther({ owner_id: null, owner_locked_until: null }, 1, NOW)).toBe(false);
  });
});
