"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { isLoggedIn, deleteAccount } from "@/lib/auth";
import { resetSessionId } from "@/lib/api";

export function DeleteAccountSection() {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(false);
  const loggedIn = isLoggedIn();

  if (!loggedIn) {
    return (
      <p>
        Para excluir sua conta automaticamente, faça login e acesse esta página
        novamente. Se preferir, envie um e-mail para{" "}
        <a href="mailto:privacy@winegod.ai">privacy@winegod.ai</a> com o e-mail
        usado no login e o provedor utilizado.
      </p>
    );
  }

  if (!confirming) {
    return (
      <div>
        <p>
          Você está logado. Clique abaixo para excluir sua conta e todos os
          dados associados. Esta ação é irreversível.
        </p>
        <button
          onClick={() => setConfirming(true)}
          className="mt-3 px-4 py-2 rounded-lg border border-red-400 text-red-500 text-sm font-medium hover:bg-red-50 transition-colors"
        >
          Excluir minha conta
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-red-300 bg-red-50/50 p-4 space-y-3">
      <p className="text-sm font-medium text-red-700">
        Tem certeza? Esta ação é irreversível.
      </p>
      <p className="text-xs text-red-600">
        Seus dados de perfil, conversas e favoritos serão excluídos
        permanentemente.
      </p>
      <div className="flex gap-3">
        <button
          onClick={async () => {
            setDeleting(true);
            setError(false);
            const ok = await deleteAccount();
            if (ok) {
              // Clean all session state before navigating to guest
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
          {deleting ? "Excluindo..." : "Sim, excluir minha conta"}
        </button>
        <button
          onClick={() => {
            setConfirming(false);
            setError(false);
          }}
          disabled={deleting}
          className="px-4 py-2 rounded-lg border border-wine-border text-wine-text text-sm hover:bg-wine-surface transition-colors disabled:opacity-50"
        >
          Cancelar
        </button>
      </div>
      {error && (
        <p className="text-xs text-red-600">
          Erro ao excluir conta. Tente novamente ou entre em contato via{" "}
          <a href="mailto:privacy@winegod.ai">privacy@winegod.ai</a>.
        </p>
      )}
    </div>
  );
}
