"use client";

import { AppShell } from "@/components/AppShell";
import { LoginButton } from "@/components/auth/LoginButton";
import { useAuth } from "@/lib/useAuth";
import type { AuthResponse } from "@/lib/auth";

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-4 bg-wine-surface rounded w-1/4" />
      <div className="h-3 bg-wine-surface rounded w-full" />
      <div className="h-3 bg-wine-surface rounded w-1/2" />
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
          <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
          <line x1="1" y1="10" x2="23" y2="10" />
        </svg>
      </div>
      <h2 className="font-display text-lg font-bold text-wine-text mb-2">
        Mais créditos com login
      </h2>
      <p className="text-wine-muted text-sm mb-2 max-w-sm mx-auto">
        Visitantes têm <strong className="text-wine-text">5 mensagens por sessão</strong>.
      </p>
      <p className="text-wine-muted text-sm mb-6 max-w-sm mx-auto">
        Faça login para ganhar <strong className="text-wine-text">15 mensagens por dia</strong>,
        renovadas automaticamente.
      </p>
      <LoginButton />
    </div>
  );
}

function ErrorState() {
  return (
    <div className="text-center py-12">
      <p className="text-wine-muted text-sm mb-2">
        Não foi possível carregar os dados do plano.
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

function PlanDetails({ credits }: { credits: AuthResponse["credits"] }) {
  const remaining = Math.max(0, credits.limit - credits.used);
  const pct = credits.limit > 0 ? (remaining / credits.limit) * 100 : 0;

  return (
    <>
      {/* Current plan */}
      <div className="bg-wine-surface rounded-xl p-5 mb-6">
        <div className="flex items-center justify-between mb-1">
          <span className="text-wine-text text-sm font-semibold">
            Plano Free
          </span>
          <span className="text-wine-muted text-xs bg-wine-bg px-2 py-0.5 rounded">
            Ativo
          </span>
        </div>
        <p className="text-wine-muted text-xs">
          15 mensagens por dia, renovadas à meia-noite UTC
        </p>
      </div>

      {/* Credits bar */}
      <div className="mb-8">
        <div className="flex items-baseline justify-between mb-2">
          <span className="text-wine-text text-sm font-semibold">
            Créditos hoje
          </span>
          <span className="text-wine-muted text-sm">
            {remaining} de {credits.limit} restantes
          </span>
        </div>
        <div className="h-2.5 rounded-full bg-wine-surface overflow-hidden">
          <div
            className="h-full rounded-full bg-wine-accent transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-wine-muted text-xs mt-2">
          {credits.used > 0
            ? `Você usou ${credits.used} crédito${credits.used > 1 ? "s" : ""} hoje.`
            : "Nenhum crédito usado hoje."}
        </p>
      </div>

      {/* Cost table */}
      <div className="mb-8">
        <h2 className="text-wine-text text-sm font-semibold mb-3">
          Custo por mensagem
        </h2>
        <div className="bg-wine-surface rounded-xl divide-y divide-wine-border">
          {[
            ["Texto ou voz", "1 crédito"],
            ["1 foto", "1 crédito"],
            ["2–5 fotos", "3 créditos"],
            ["Vídeo", "3 créditos"],
            ["PDF", "3 créditos"],
          ].map(([type, cost]) => (
            <div
              key={type}
              className="flex justify-between px-4 py-2.5 text-sm"
            >
              <span className="text-wine-text">{type}</span>
              <span className="text-wine-muted">{cost}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Pro teaser */}
      <div className="border border-dashed border-wine-border rounded-xl p-5">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-wine-accent text-sm font-semibold">
            Em breve: Pro
          </span>
        </div>
        <ul className="text-wine-muted text-sm space-y-1">
          <li>Mais créditos diários</li>
          <li>Respostas com modelos avançados</li>
          <li>Recursos exclusivos</li>
        </ul>
        <p className="text-wine-muted text-xs mt-3">
          Estamos trabalhando nisso. Por enquanto, aproveite o plano Free.
        </p>
      </div>
    </>
  );
}

export function PlanoContent() {
  const { user, credits, loading, error } = useAuth();

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto px-4 py-8 overflow-y-auto h-full">
        <h1 className="font-display text-2xl font-bold text-wine-text mb-6">
          Plano & créditos
        </h1>
        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState />
        ) : !user || !credits ? (
          <GuestState />
        ) : (
          <PlanDetails credits={credits} />
        )}
      </div>
    </AppShell>
  );
}
