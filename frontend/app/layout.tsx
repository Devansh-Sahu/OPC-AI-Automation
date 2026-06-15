import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { Toaster } from "@/components/ui/toaster";
import { QueryProvider } from "@/components/providers/query-provider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "OSE Dashboard — OpenSource AI Engineer",
  description: "Autonomous AI Software Engineering System — Discover, Contribute, Innovate",
  keywords: ["AI", "OpenSource", "Engineering", "Dashboard", "Autonomous"],
  authors: [{ name: "OSE Team" }],
  themeColor: "#0a0a0f",
  viewport: "width=device-width, initial-scale=1",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans bg-background text-foreground antialiased`}>
        <QueryProvider>
          <div className="flex h-screen overflow-hidden">
            {/* Sidebar */}
            <Sidebar />

            {/* Main content */}
            <div className="flex flex-col flex-1 overflow-hidden">
              <Header />
              <main className="flex-1 overflow-y-auto relative">
                {/* Background grid pattern */}
                <div className="fixed inset-0 bg-grid opacity-30 pointer-events-none" />
                {/* Gradient orbs */}
                <div className="fixed top-0 left-1/4 w-96 h-96 rounded-full bg-blue-glow opacity-50 pointer-events-none blur-3xl" />
                <div className="fixed bottom-0 right-1/4 w-96 h-96 rounded-full bg-purple-glow opacity-30 pointer-events-none blur-3xl" />
                <div className="relative z-10 p-6">
                  {children}
                </div>
              </main>
            </div>
          </div>
          <Toaster />
        </QueryProvider>
      </body>
    </html>
  );
}
