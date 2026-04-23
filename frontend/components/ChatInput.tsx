"use client";

import { useState, useRef, useCallback, useEffect, type KeyboardEvent } from "react";
import { useTranslations, useLocale } from "next-intl";

type MediaType = "image" | "video" | "pdf";

interface MediaAttachment {
  type: MediaType;
  base64: string;
  preview: string; // data URL or label
  fileName?: string;
}

const MAX_IMAGES = 5;

interface MediaPayload {
  type: MediaType;
  base64: string;
  images?: string[];
  previews?: string[];
}

interface ChatInputProps {
  onSend: (text: string, media?: MediaPayload) => void;
  disabled: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const t = useTranslations("chatInput");
  const uiLocale = useLocale();
  const [text, setText] = useState("");
  const [attachment, setAttachment] = useState<MediaAttachment | null>(null);
  const [images, setImages] = useState<{ base64: string; preview: string }[]>([]);
  const [showMenu, setShowMenu] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [hasSpeechSupport, setHasSpeechSupport] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const videoInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  // Check SpeechRecognition support
  useEffect(() => {
    const SR =
      typeof window !== "undefined"
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : null;
    setHasSpeechSupport(!!SR);
  }, []);

  // Close menu on outside click
  useEffect(() => {
    if (!showMenu) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showMenu]);

  const clearAttachment = useCallback(() => {
    setAttachment(null);
    setImages([]);
    if (imageInputRef.current) imageInputRef.current.value = "";
    if (videoInputRef.current) videoInputRef.current.value = "";
    if (pdfInputRef.current) pdfInputRef.current.value = "";
  }, []);

  const removeImage = useCallback((index: number) => {
    setImages((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleSend = useCallback(() => {
    const hasImages = images.length > 0;
    if ((!text.trim() && !attachment && !hasImages) || disabled) return;

    let mediaPayload: MediaPayload | undefined;

    if (hasImages) {
      mediaPayload = {
        type: "image" as MediaType,
        base64: images[0].base64,
        images: images.map((img) => img.base64),
        previews: images.map((img) => img.preview),
      };
    } else if (attachment) {
      mediaPayload = { type: attachment.type, base64: attachment.base64 };
    }

    const defaultMsg = hasImages || attachment
      ? t("defaultPhotoMessage")
      : "";

    onSend(text || defaultMsg, mediaPayload);
    setText("");
    clearAttachment();
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [text, attachment, images, disabled, onSend, clearAttachment]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setText(e.target.value);
      const el = e.target;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    },
    []
  );

  // --- Image handling ---
  const resizeImage = useCallback(
    (file: File, maxSide: number): Promise<string> => {
      return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
          let { width, height } = img;
          if (width > maxSide || height > maxSide) {
            if (width > height) {
              height = Math.round((height * maxSide) / width);
              width = maxSide;
            } else {
              width = Math.round((width * maxSide) / height);
              height = maxSide;
            }
          }
          const canvas = document.createElement("canvas");
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext("2d");
          if (!ctx) {
            reject(new Error("Canvas not supported"));
            return;
          }
          ctx.drawImage(img, 0, 0, width, height);
          const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
          resolve(dataUrl);
        };
        img.onerror = () => reject(new Error("Failed to load image"));
        img.src = URL.createObjectURL(file);
      });
    },
    []
  );

  const processImageFile = useCallback(
    async (file: File): Promise<{ base64: string; preview: string }> => {
      let dataUrl: string;
      if (file.size > 4 * 1024 * 1024) {
        dataUrl = await resizeImage(file, 1024);
      } else {
        dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(file);
        });
      }
      return { base64: dataUrl.split(",")[1], preview: dataUrl };
    },
    [resizeImage]
  );

  const handleImageSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      setShowMenu(false);

      const remaining = MAX_IMAGES - images.length;
      if (remaining <= 0) {
        alert(t("alertMaxPhotos", { max: MAX_IMAGES }));
        return;
      }

      const filesToProcess = Array.from(files).slice(0, remaining);
      if (files.length > remaining) {
        alert(t("alertAddMorePhotos", { remaining, max: MAX_IMAGES }));
      }

      // Clear video/pdf attachment when adding images
      setAttachment(null);

      const newImages: { base64: string; preview: string }[] = [];
      for (const file of filesToProcess) {
        try {
          const img = await processImageFile(file);
          newImages.push(img);
        } catch {
          // skip failed files
        }
      }

      if (newImages.length > 0) {
        setImages((prev) => [...prev, ...newImages].slice(0, MAX_IMAGES));
      }

      if (imageInputRef.current) imageInputRef.current.value = "";
    },
    [images.length, processImageFile]
  );

  // --- Video handling ---
  const handleVideoSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setShowMenu(false);

      if (file.size > 50 * 1024 * 1024) {
        alert(t("alertVideoTooLarge"));
        return;
      }

      try {
        const dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(file);
        });

        const base64 = dataUrl.split(",")[1];
        setAttachment({
          type: "video",
          base64,
          preview: dataUrl,
          fileName: file.name,
        });
      } catch {
        clearAttachment();
      }
    },
    [clearAttachment]
  );

  // --- PDF handling ---
  const handlePdfSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setShowMenu(false);

      if (file.size > 20 * 1024 * 1024) {
        alert(t("alertPdfTooLarge"));
        return;
      }

      try {
        const dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(file);
        });

        const base64 = dataUrl.split(",")[1];
        setAttachment({
          type: "pdf",
          base64,
          preview: "",
          fileName: file.name,
        });
      } catch {
        clearAttachment();
      }
    },
    [clearAttachment]
  );

  // --- Voice / Mic ---
  const toggleRecording = useCallback(() => {
    if (isRecording && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsRecording(false);
      return;
    }

    const SR =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    const recognition = new SR();
    recognition.lang = uiLocale;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0][0].transcript;
      setText((prev) => (prev ? prev + " " + transcript : transcript));
      setIsRecording(false);
    };

    recognition.onerror = () => {
      setIsRecording(false);
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsRecording(true);
  }, [isRecording, uiLocale]);

  // --- Preview rendering ---
  const renderPreview = () => {
    // Multi-image grid preview
    if (images.length > 0) {
      return (
        <div className="mb-2">
          <div className="flex items-center gap-1 mb-1">
            <span className="text-xs text-wine-muted">{t("photoCount", { count: images.length, max: MAX_IMAGES })}</span>
          </div>
          <div className="flex gap-2 flex-wrap">
            {images.map((img, idx) => (
              <div key={idx} className="relative">
                <img
                  src={img.preview}
                  alt={t("photoAlt", { index: idx + 1 })}
                  className="h-16 w-16 object-cover rounded-lg border border-wine-border"
                />
                <button
                  type="button"
                  onClick={() => removeImage(idx)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center hover:bg-red-600"
                >
                  x
                </button>
              </div>
            ))}
          </div>
        </div>
      );
    }

    if (!attachment) return null;

    if (attachment.type === "video") {
      return (
        <div className="mb-2 relative inline-flex items-center gap-2 bg-wine-input border border-wine-border rounded-lg px-3 py-2">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-wine-accent">
            <polygon points="23 7 16 12 23 17 23 7" />
            <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
          </svg>
          <span className="text-xs text-wine-text truncate max-w-[150px]">
            {attachment.fileName || t("videoFallbackName")}
          </span>
          <button
            type="button"
            onClick={clearAttachment}
            className="w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center hover:bg-red-600 flex-shrink-0"
          >
            x
          </button>
        </div>
      );
    }

    if (attachment.type === "pdf") {
      return (
        <div className="mb-2 relative inline-flex items-center gap-2 bg-wine-input border border-wine-border rounded-lg px-3 py-2">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-red-500">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          <span className="text-xs text-wine-text truncate max-w-[150px]">
            {attachment.fileName || t("pdfFallbackName")}
          </span>
          <button
            type="button"
            onClick={clearAttachment}
            className="w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center hover:bg-red-600 flex-shrink-0"
          >
            x
          </button>
        </div>
      );
    }

    return null;
  };

  return (
    <div className="flex-shrink-0 border-t border-wine-border bg-white px-4 py-3">
      {renderPreview()}

      {/* Hidden file inputs */}
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={handleImageSelect}
      />
      <input
        ref={videoInputRef}
        type="file"
        accept="video/mp4,video/mov,video/webm,video/avi,video/*"
        className="hidden"
        onChange={handleVideoSelect}
      />
      <input
        ref={pdfInputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={handlePdfSelect}
      />

      <div className="flex items-end gap-2">
        {/* Attachment button + menu */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setShowMenu((prev) => !prev)}
            disabled={disabled}
            className="flex-shrink-0 w-10 h-10 rounded-full bg-wine-input border border-wine-border flex items-center justify-center text-wine-muted hover:text-wine-accent hover:border-wine-accent transition-colors disabled:opacity-30 disabled:cursor-not-allowed text-wine-text"
            title={t("attachTooltip")}
          >
            <span className="text-xl leading-none">+</span>
          </button>

          {showMenu && (
            <div className="absolute bottom-12 left-0 bg-white border border-wine-border rounded-lg shadow-lg py-1 min-w-[160px] z-50">
              <button
                type="button"
                onClick={() => imageInputRef.current?.click()}
                className="w-full text-left px-4 py-2 text-sm text-wine-text hover:bg-wine-input transition-colors flex items-center gap-2"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
                {t("menuPhoto")}
              </button>
              <button
                type="button"
                onClick={() => videoInputRef.current?.click()}
                className="w-full text-left px-4 py-2 text-sm text-wine-text hover:bg-wine-input transition-colors flex items-center gap-2"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="23 7 16 12 23 17 23 7" />
                  <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                </svg>
                {t("menuVideo")}
              </button>
              <button
                type="button"
                onClick={() => pdfInputRef.current?.click()}
                className="w-full text-left px-4 py-2 text-sm text-wine-text hover:bg-wine-input transition-colors flex items-center gap-2"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                {t("menuPdf")}
              </button>
            </div>
          )}
        </div>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={t("placeholder")}
          rows={1}
          className="flex-1 bg-wine-input border border-wine-border rounded-2xl px-4 py-2.5 text-sm text-wine-text placeholder-wine-muted resize-none focus:outline-none focus:border-wine-accent transition-colors disabled:opacity-50"
        />

        {/* Mic button */}
        {hasSpeechSupport && (
          <button
            type="button"
            onClick={toggleRecording}
            disabled={disabled}
            className={`flex-shrink-0 w-10 h-10 rounded-full border flex items-center justify-center transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
              isRecording
                ? "bg-red-500 border-red-500 text-white animate-pulse"
                : "bg-wine-input border-wine-border text-wine-muted hover:text-wine-accent hover:border-wine-accent"
            }`}
            title={isRecording ? t("recordStopTooltip") : t("recordStartTooltip")}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          </button>
        )}

        {/* Send button */}
        <button
          type="button"
          onClick={handleSend}
          disabled={disabled || (!text.trim() && !attachment && images.length === 0)}
          className="flex-shrink-0 w-10 h-10 rounded-full bg-wine-accent flex items-center justify-center text-white transition-opacity hover:opacity-80 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  );
}
