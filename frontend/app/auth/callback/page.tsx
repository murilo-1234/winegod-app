"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import {
  exchangeCodeForToken,
  getLastAuthError,
  setToken,
} from "@/lib/auth";
import { toErrorDescriptor } from "@/lib/i18n/translateError";
import { useTranslatedError } from "@/lib/i18n/useTranslatedError";

function CallbackHandler() {
  const t = useTranslations("authCallback");
  const translateErr = useTranslatedError();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    // Apple envia token direto na URL (fluxo form_post via backend)
    const directToken = searchParams.get("token");
    if (directToken) {
      setToken(directToken);
      router.replace("/");
      return;
    }

    const code = searchParams.get("code");
    if (!code) {
      setError(t("errorNoCode"));
      return;
    }

    // Detectar provedor via state param (default: google para retrocompatibilidade)
    const state = searchParams.get("state");
    const provider = (state === "facebook" || state === "apple" || state === "microsoft")
      ? state
      : "google";

    exchangeCodeForToken(code, provider).then((result) => {
      if (result) {
        setToken(result.token);
        router.replace("/");
      } else {
        // F4.0b: le o APIError estruturado que a propria `exchangeCodeForToken`
        // gravou em caso de falha. Fallback generico se nao houver (ex.:
        // servidor indo pro ar e `getLastAuthError()` ainda nulo).
        const structured = getLastAuthError();
        if (structured) {
          setError(translateErr(toErrorDescriptor(structured)));
        } else {
          setError(t("errorServerFallback"));
        }
      }
    });
  }, [searchParams, router, t, translateErr]);

  if (error) {
    return (
      <div className="text-center p-6 max-w-md">
        <p className="text-wine-text mb-4">{error}</p>
        <div className="flex flex-col gap-3 items-center">
          <button
            onClick={() => window.location.href = "/"}
            className="px-4 py-2 bg-wine-accent text-white rounded-lg text-sm hover:opacity-80 transition-opacity"
          >
            {t("retry")}
          </button>
          <a href="/" className="text-wine-muted hover:underline text-xs">
            {t("backToGuest")}
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="text-center">
      <div className="w-8 h-8 border-2 border-wine-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
      <p className="text-wine-muted text-sm">{t("signingIn")}</p>
    </div>
  );
}

function CallbackFallback() {
  const t = useTranslations("authCallback");
  return (
    <div className="text-center">
      <div className="w-8 h-8 border-2 border-wine-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
      <p className="text-wine-muted text-sm">{t("loading")}</p>
    </div>
  );
}

export default function AuthCallback() {
  return (
    <main className="flex items-center justify-center h-dvh bg-wine-bg">
      <Suspense fallback={<CallbackFallback />}>
        <CallbackHandler />
      </Suspense>
    </main>
  );
}
