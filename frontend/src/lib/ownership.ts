// 認領鎖定的畫面判斷。真正的規則在後端 domain/company_rules.py，這裡只決定按鈕要不要停用

interface Owned {
  owner_id: number | null;
  owner_locked_until: string | null;
}

/** 這家公司是否被「別的業務」鎖定中（SPEC 第 4 節認領規則：鎖定 30 天） */
export function isLockedByOther(c: Owned, userId: number | undefined, now: number): boolean {
  if (c.owner_id === null || c.owner_id === userId || c.owner_locked_until === null) return false;
  return new Date(c.owner_locked_until).getTime() > now;
}
