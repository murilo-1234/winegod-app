"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { exchangeCodeForToken, setToken } from "@/lib/auth";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    const code = searchParams.get("code");
    if (!code) {
      setError("Codigo de autorizacao nao encontrado");
      return;
    }

    exchangeCodeForToken(code).then((result) => {
      if (result) {
        setToken(result.token);
        router.replace("/");
      } else {
        setError("Falha ao fazer login. Tente novamente.");
      }
    });
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="text-center p-6">
        <p className="text-wine-text mb-4">{error}</p>
        <a href="/" className="text-wine-accent hover:underline text-sm">
          Voltar ao chat
        </a>
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
