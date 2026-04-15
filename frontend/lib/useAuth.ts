"use client";

import { useState, useEffect } from "react";
import { getUser, isLoggedIn } from "./auth";
import type { UserData, AuthResponse } from "./auth";

interface UseAuthResult {
  user: UserData | null;
  credits: AuthResponse["credits"] | null;
  loading: boolean;
  error: boolean;
}

export function useAuth(): UseAuthResult {
  const [user, setUser] = useState<UserData | null>(null);
  const [credits, setCredits] =
    useState<AuthResponse["credits"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    async function load() {
      if (!isLoggedIn()) {
        setLoading(false);
        return;
      }
      const data = await getUser();
      if (data) {
        setUser(data.user);
        setCredits(data.credits);
      } else if (isLoggedIn()) {
        // Token still present but fetch failed (network error)
        setError(true);
      }
      // else: token removed by getUser() on 401 → guest state
      setLoading(false);
    }
    load();
  }, []);

  return { user, credits, loading, error };
}
