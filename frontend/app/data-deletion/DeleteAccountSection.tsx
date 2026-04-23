"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { isLoggedIn, deleteAccount } from "@/lib/auth";
import { resetSessionId } from "@/lib/api";

export function DeleteAccountSection() {
  const router = useRouter();
  const t = useTranslations("dataDeletion");
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(false);
  const loggedIn = isLoggedIn();

  const emailChunk = (chunks: React.ReactNode) => (
    <a href="mailto:privacy@winegod.ai">{chunks}</a>
  );

  if (!loggedIn) {
    return <p>{t.rich("loggedOutIntro", { email: emailChunk })}</p>;
  }

  if (!confirming) {
    return (
      <div>
        <p>{t("loggedInIntro")}</p>
        <button
          onClick={() => setConfirming(true)}
          className="mt-3 px-4 py-2 rounded-lg border border-red-400 text-red-500 text-sm font-medium hover:bg-red-50 transition-colors"
        >
          {t("deleteCta")}
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-red-300 bg-red-50/50 p-4 space-y-3">
      <p className="text-sm font-medium text-red-700">{t("confirmTitle")}</p>
      <p className="text-xs text-red-600">{t("confirmBody")}</p>
      <div className="flex gap-3">
        <button
          onClick={async () => {
            setDeleting(true);
            setError(false);
            const ok = await deleteAccount();
            if (ok) {
              resetSessionId();
              sessionStorage.removeItem("winegod_conversation_id");
              sessionStorage.removeItem("winegod_messages");
              localStorage.removeItem("winegod_messages");
              router.push("/");
            } else {
              setError(true);
              setDeleting(false);
            }
          }}
          disabled={deleting}
          className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
        >
          {deleting ? t("confirmCtaDeleting") : t("confirmCta")}
        </button>
        <button
          onClick={() => {
            setConfirming(false);
            setError(false);
          }}
          disabled={deleting}
          className="px-4 py-2 rounded-lg border border-wine-border text-wine-text text-sm hover:bg-wine-surface transition-colors disabled:opacity-50"
        >
          {t("cancelCta")}
        </button>
      </div>
      {error && (
        <p className="text-xs text-red-600">
          {t.rich("errorMessage", { email: emailChunk })}
        </p>
      )}
    </div>
  );
}
