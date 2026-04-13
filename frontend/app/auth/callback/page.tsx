"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { exchangeCodeForToken, setToken } from "@/lib/auth";

function CallbackHandler() {
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
      setError("Código de autorização não encontrado");
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
        setError("Falha ao conectar com o servidor. O servidor pode estar iniciando — aguarde 30s e tente novamente.");
      }
    });
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="text-center p-6 max-w-md">
        <p className="text-wine-text mb-4">{error}</p>
        <div className="flex flex-col gap-3 items-center">
          <button
            onClick={() => window.location.href = "/"}
            className="px-4 py-2 bg-wine-accent text-white rounded-lg text-sm hover:opacity-80 transition-opacity"
          >
            Tentar novamente
          </button>
          <a href="/" className="text-wine-muted hover:underline text-xs">
            Voltar ao chat sem login
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="text-center">
      <div className="w-8 h-8 border-2 border-wine-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
      <p className="text-wine-muted text-sm">Entrando...</p>
    </div>
  );
}

export default function AuthCallback() {
  return (
    <main className="flex items-center justify-center h-dvh bg-wine-bg">
      <Suspense
        fallback={
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-wine-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-wine-muted text-sm">Carregando...</p>
          </div>
        }
      >
        <CallbackHandler />
      </Suspense>
    </main>
  );
}
