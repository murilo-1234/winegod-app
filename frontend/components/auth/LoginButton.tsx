"use client";

import { useState, useRef, useEffect } from "react";
import { useTranslations } from "next-intl";
import { getGoogleLoginUrl, getFacebookLoginUrl, getAppleLoginUrl, getMicrosoftLoginUrl } from "@/lib/auth";

interface LoginButtonProps {
  compact?: boolean;
}

export function LoginButton({ compact = false }: LoginButtonProps) {
  const t = useTranslations("loginButton");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  if (compact) {
    return (
      <div className="relative" ref={ref}>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-wine-surface border border-wine-border text-wine-text text-sm hover:border-wine-accent transition-colors"
        >
          <span>{t("signIn")}</span>
        </button>
        {open && (
          <div className="absolute right-0 top-full mt-1 w-56 rounded-xl bg-wine-surface border border-wine-border shadow-lg z-50 p-2 flex flex-col gap-1">
            <ProviderButton provider="google" />
            <ProviderButton provider="facebook" />
            <ProviderButton provider="apple" />
            <ProviderButton provider="microsoft" />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 w-full">
      <ProviderButton provider="google" />
      <ProviderButton provider="facebook" />
      <ProviderButton provider="apple" />
      <ProviderButton provider="microsoft" />
    </div>
  );
}

function ProviderButton({ provider }: { provider: "google" | "facebook" | "apple" | "microsoft" }) {
  const t = useTranslations("loginButton");
  const config = {
    google: {
      label: t("withGoogle"),
      url: getGoogleLoginUrl(),
      icon: <GoogleIcon />,
    },
    facebook: {
      label: t("withFacebook"),
      url: getFacebookLoginUrl(),
      icon: <FacebookIcon />,
    },
    apple: {
      label: t("withApple"),
      url: getAppleLoginUrl(),
      icon: <AppleIcon />,
    },
    microsoft: {
      label: t("withMicrosoft"),
      url: getMicrosoftLoginUrl(),
      icon: <MicrosoftIcon />,
    },
  };

  const { label, url, icon } = config[provider];

  return (
    <button
      onClick={() => { window.location.href = url; }}
      className="flex items-center justify-center gap-3 w-full px-4 py-3 rounded-xl bg-wine-surface border border-wine-border text-wine-text text-sm hover:border-wine-accent transition-colors"
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path
        d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
        fill="#4285F4"
      />
      <path
        d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.26c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z"
        fill="#34A853"
      />
      <path
        d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
        fill="#FBBC05"
      />
      <path
        d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
        fill="#EA4335"
      />
    </svg>
  );
}

function FacebookIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path
        d="M18 9a9 9 0 10-10.406 8.89v-6.29H5.309V9h2.285V7.017c0-2.255 1.343-3.501 3.4-3.501.984 0 2.014.176 2.014.176v2.215h-1.135c-1.118 0-1.467.694-1.467 1.406V9h2.496l-.399 2.6h-2.097v6.29A9.002 9.002 0 0018 9z"
        fill="#1877F2"
      />
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path
        d="M14.94 9.63c-.02-2.1 1.71-3.11 1.79-3.16-0.97-1.42-2.49-1.62-3.03-1.64-1.29-.13-2.52.76-3.18.76-.66 0-1.67-.74-2.75-.72A4.07 4.07 0 004.34 7.1c-1.47 2.55-.37 6.33 1.06 8.4.7 1.01 1.53 2.15 2.63 2.11 1.06-.04 1.46-.68 2.74-.68 1.28 0 1.64.68 2.75.66 1.14-.02 1.85-1.03 2.55-2.05a8.94 8.94 0 001.15-2.37c-.02-.01-2.22-.85-2.24-3.38l-.04-.16zM12.87 3.34A4.07 4.07 0 0013.8.5a4.15 4.15 0 00-2.69 1.39 3.89 3.89 0 00-.97 2.82 3.44 3.44 0 002.73-1.37z"
        fill="currentColor"
      />
    </svg>
  );
}

function MicrosoftIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <rect x="0" y="0" width="8.5" height="8.5" fill="#F25022" />
      <rect x="9.5" y="0" width="8.5" height="8.5" fill="#7FBA00" />
      <rect x="0" y="9.5" width="8.5" height="8.5" fill="#00A4EF" />
      <rect x="9.5" y="9.5" width="8.5" height="8.5" fill="#FFB900" />
    </svg>
  );
}
