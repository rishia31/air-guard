"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

export const DEFAULT_USER_ID = "maya";
const USER_STORAGE_KEY = "airmate_user_id";

/**
 * Hook to retrieve and maintain the current active user ID.
 * Defaults to "maya" unless specified in `?user=` query parameter.
 * Preserves the active user in localStorage and provides a helper
 * `userLink(path)` to automatically keep `?user=...` across navigation links.
 */
export function useUser() {
  const searchParams = useSearchParams();
  const queryUser = searchParams?.get("user");

  const [storedUserId, setStoredUserId] = useState<string>(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(USER_STORAGE_KEY);
      if (stored) return stored;
    }
    return DEFAULT_USER_ID;
  });

  // Derive userId from query param if provided, otherwise stored fallback
  const userId = queryUser || storedUserId;

  useEffect(() => {
    if (queryUser) {
      localStorage.setItem(USER_STORAGE_KEY, queryUser);
    }
  }, [queryUser]);

  const setUserId = useCallback((newId: string) => {
    setStoredUserId(newId);
    if (typeof window !== "undefined") {
      localStorage.setItem(USER_STORAGE_KEY, newId);
      const url = new URL(window.location.href);
      url.searchParams.set("user", newId);
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  const userLink = useCallback(
    (path: string) => {
      // Ensure path ends with slash if required for static export trailingSlash
      const [base, hash] = path.split("#");
      const [pathname, search] = base.split("?");
      const normalizedPath = pathname.endsWith("/") ? pathname : `${pathname}/`;

      const params = new URLSearchParams(search ?? "");
      params.set("user", userId);

      const qs = params.toString();
      const finalUrl = `${normalizedPath}${qs ? `?${qs}` : ""}${hash ? `#${hash}` : ""}`;
      return finalUrl;
    },
    [userId]
  );

  return {
    userId,
    setUserId,
    userLink,
    isDefaultUser: userId === DEFAULT_USER_ID,
  };
}
