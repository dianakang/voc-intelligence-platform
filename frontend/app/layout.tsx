import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Samsung VOC Intelligence Platform",
  description: "AI-powered customer review analysis for Samsung products",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} bg-gray-50 min-h-screen`} suppressHydrationWarning>
        <nav className="bg-white border-b border-gray-200 sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <div className="flex items-center gap-8">
                <Link href="/" className="flex items-center gap-2">
                  <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center">
                    <span className="text-white font-bold text-sm">S</span>
                  </div>
                  <span className="font-semibold text-gray-900 hidden sm:block">
                    VOC Intelligence
                  </span>
                </Link>
                <div className="flex items-center gap-6 text-sm">
                  <Link href="/" className="text-gray-600 hover:text-gray-900 font-medium">Dashboard</Link>
                  <Link href="/analysis" className="text-gray-600 hover:text-gray-900 font-medium">Run Analysis</Link>
                  <Link href="/reports" className="text-gray-600 hover:text-gray-900 font-medium">Reports</Link>
                </div>
              </div>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
