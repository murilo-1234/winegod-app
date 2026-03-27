"use client";

import { useState } from "react";
import type { UserData } from "@/lib/auth";

interface UserMenuProps {
  user: UserData;
  creditsUsed: number;
  creditsLimit: number;
  onLogout: () => void;
}

export function UserMenu({ user, creditsUsed, creditsLimit, onLogout }: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const remaining = Math.max(0, creditsLimit - creditsUsed);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-wine-surface transition-colors"
      >
        {user.picture_url ? (
          <img
            src={user.picture_url}
            alt={user.name}
            width={32}
            height={32}
            className="rounded-full"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-wine-accent flex items-center justify-center text-wine-text text-sm font-bold">
            {user.name?.charAt(0)?.toUpperCase() || "?"}
          </div>
        )}
        <span className="text-wine-muted text-xs hidden sm:block">
          {remaining}/{creditsLimit}
        </span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 z-50 w-56 rounded-xl bg-wine-surface border border-wine-border p-3 shadow-lg">
            <div className="flex items-center gap-3 mb-3">
              {user.picture_url ? (
                <img
                  src={user.picture_url}
                  alt={user.name}
                  width={40}
                  height={40}
                  className="rounded-full"
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div className="w-10 h-10 rounded-full bg-wine-accent flex items-center justify-center text-wine-text font-bold">
                  {user.name?.charAt(0)?.toUpperCase() || "?"}
                </div>
              )}
              <div className="min-w-0">
                <p className="text-wine-text text-sm font-medium truncate">{user.name}</p>
                <p className="text-wine-muted text-xs truncate">{user.email}</p>
              </div>
            </div>

            <div className="border-t border-wine-border pt-2 mb-2">
              <p className="text-wine-muted text-xs">
                {remaining}/{creditsLimit} mensagens hoje
              </p>
              <div className="mt-1 h-1.5 rounded-full bg-wine-bg overflow-hidden">
                <div
                  className="h-full rounded-full bg-wine-accent transition-all"
                  style={{ width: `${(remaining / creditsLimit) * 100}%` }}
                />
              </div>
            </div>

            <button
              onClick={() => {
                setOpen(false);
                onLogout();
              }}
              className="w-full text-left px-2 py-1.5 rounded-lg text-wine-muted text-sm hover:bg-wine-bg hover:text-wine-text transition-colors"
            >
              Sair
            </button>
          </div>
        </>
      )}
    </div>
  );
}
