"use client";

import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { LoginButton } from "@/components/auth/LoginButton";
import { useAuth } from "@/lib/useAuth";
import { logout as doLogout } from "@/lib/auth";
import { resetSessionId } from "@/lib/api";
import type { UserData } from "@/lib/auth";

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="flex items-center gap-4">
        <div className="w-16 h-16 rounded-full bg-wine-surface" />
        <div className="space-y-2 flex-1">
          <div className="h-4 bg-wine-surface rounded w-1/3" />
          <div className="h-3 bg-wine-surface rounded w-1/2" />
        </div>
      </div>
      <div className="h-3 bg-wine-surface rounded w-2/3" />
      <div className="h-3 bg-wine-surface rounded w-1/4" />
    </div>
  );
}

function GuestState() {
  return (
    <div className="text-center py-12">
      <div className="w-16 h-16 rounded-full bg-wine-surface flex items-center justify-center mx-auto mb-4">
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="text-wine-muted"
        >
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      </div>
      <h2 className="font-display text-lg font-bold text-wine-text mb-2">
        Entre para ver sua conta
      </h2>
      <p className="text-wine-muted text-sm mb-6 max-w-sm mx-auto">
        Faça login para acessar seu perfil, ver seus créditos e gerenciar sua
        conta.
      </p>
      <LoginButton />
    </div>
  );
}

function ErrorState() {
  return (
    <div className="text-center py-12">
      <p className="text-wine-muted text-sm mb-2">
        Não foi possível carregar os dados da conta.
      </p>
      <button
        onClick={() => window.location.reload()}
        className="text-wine-accent text-sm underline"
      >
        Tentar novamente
      </button>
    </div>
  );
}

function formatProvider(provider?: string): string {
  if (!provider) return "—";
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleString("pt-BR", {
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between py-3 border-b border-wine-border last:border-0">
      <span className="text-wine-muted text-sm">{label}</span>
      <span className="text-wine-text text-sm font-medium text-right">
        {value}
      </span>
    </div>
  );
}

function Profile({
  user,
  onLogout,
}: {
  user: UserData;
  onLogout: () => void;
}) {
  return (
    <>
      {/* Avatar + name */}
      <div className="flex items-center gap-4 mb-8">
        {user.picture_url ? (
          <img
            src={user.picture_url}
            alt={user.name}
            width={64}
            height={64}
            className="rounded-full"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="w-16 h-16 rounded-full bg-wine-accent flex items-center justify-center text-white text-2xl font-bold">
            {user.name?.charAt(0)?.toUpperCase() || "?"}
          </div>
        )}
        <div>
          <p className="text-wine-text text-lg font-semibold">{user.name}</p>
          <p className="text-wine-muted text-sm">{user.email}</p>
        </div>
      </div>

      {/* Info rows */}
      <div className="bg-wine-surface rounded-xl p-4 mb-8">
        <InfoRow label="Login via" value={formatProvider(user.provider)} />
        <InfoRow label="Último acesso" value={formatDate(user.last_login)} />
        <InfoRow label="Plano" value="Free" />
      </div>

      {/* Actions */}
      <div className="space-y-3">
        <button
          onClick={onLogout}
          className="w-full py-2.5 rounded-lg border border-wine-border text-wine-text text-sm font-medium hover:bg-wine-surface transition-colors"
        >
          Sair da conta
        </button>
        <a
          href="/data-deletion"
          className="block text-center text-wine-muted text-xs hover:text-wine-accent transition-colors"
        >
          Excluir minha conta e dados
        </a>
      </div>
    </>
  );
}

export function ContaContent() {
  const { user, loading, error } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    await doLogout();
    resetSessionId();
    router.push("/");
  };

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 py-8 overflow-y-auto h-full">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-6">
          Minha conta
        </h1>
        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState />
        ) : !user ? (
          <GuestState />
        ) : (
          <Profile user={user} onLogout={handleLogout} />
        )}
      </div>
    </AppShell>
  );
}
