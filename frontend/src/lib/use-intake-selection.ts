"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import type { IntakeT } from "./contracts";
import { useGet } from "./hooks";

/**
 * Chọn đợt tuyển và giữ lựa chọn trong URL (?intake=...) để chia sẻ/tải lại được.
 * Mặc định chọn đợt thoả `prefer` (nếu có), rồi đợt đang mở, rồi đợt đầu danh sách.
 */
export function useIntakeSelection(prefer?: (intake: IntakeT) => boolean) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const query = useGet<IntakeT[]>("/intakes");

  const selected = useMemo(() => {
    const list = query.data ?? [];
    const wanted = params.get("intake");
    return list.find((i) => i.id === wanted) ?? (prefer ? list.find(prefer) : undefined) ?? list.find((i) => i.status === "open") ?? list[0];
  }, [query.data, params, prefer]);

  const select = useCallback(
    (id: string) => {
      const next = new URLSearchParams(params.toString());
      next.set("intake", id);
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [params, pathname, router],
  );

  return { query, intakes: query.data ?? [], selected, select };
}
