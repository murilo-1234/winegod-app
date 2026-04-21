import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const nextConfig: NextConfig = {
  reactStrictMode: true,
};

// F2.3: registra o plugin do next-intl. O request config real (resolver de
// locale + carga de messages) e tratado em F2.3b/F2.4 via ./i18n/request.ts.
const withNextIntl = createNextIntlPlugin();

export default withNextIntl(nextConfig);
