import { useEffect, useState } from "react";

/** 值停止變動 delay 毫秒後才更新（打字時不要每個字都呼叫後端） */
export function useDebounced<T>(value: T, delay = 400): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}
