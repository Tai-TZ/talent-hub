import type { Metadata, Viewport } from "next";
import { Montserrat } from "next/font/google";
import { I18nProvider } from "@/components/providers";
import { getLocale } from "@/lib/server";
import "./globals.css";

const montserrat = Montserrat({
  subsets: ["latin", "vietnamese"],
  variable: "--font-montserrat",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Talent Hub", template: "%s · Talent Hub" },
  description: "Hệ thống quản lý tuyển sinh và chất lượng đào tạo theo đợt.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#4338CA",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={locale} className={montserrat.variable}>
      <body>
        <I18nProvider locale={locale}>{children}</I18nProvider>
      </body>
    </html>
  );
}
