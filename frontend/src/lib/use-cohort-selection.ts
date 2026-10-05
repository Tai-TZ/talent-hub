"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import type { ProgramT } from "./contracts";
import { useGet } from "./hooks";

export interface CohortOption {
  id: string;
  code: string;
  name: string;
  programName: string;
  status: string;
}

/** Chọn khoá học, giữ trong URL (?cohort=...). Mặc định: khoá đang học, rồi khoá sắp mở sớm nhất, rồi khoá cuối danh sách. */
export function useCohortSelection() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const query = useGet<ProgramT[]>("/programs");

  const cohorts = useMemo<CohortOption[]>(
    () =>
      (query.data ?? []).flatMap((p) =>
        p.cohorts.map((c) => ({ id: c.id, code: c.code, name: c.name, programName: p.name["vi"] ?? p.code, status: c.status })),
      ),
    [query.data],
  );

  const selected = useMemo(() => {
    const wanted = params.get("cohort");
    return cohorts.find((c) => c.id === wanted) ?? cohorts.find((c) => c.status === "active") ?? cohorts.find((c) => c.status === "planned") ?? cohorts.at(-1);
  }, [cohorts, params]);

  const select = useCallback(
    (id: string) => {
      const next = new URLSearchParams(params.toString());
      next.set("cohort", id);
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [params, pathname, router],
  );

  return { query, cohorts, selected, select };
}
