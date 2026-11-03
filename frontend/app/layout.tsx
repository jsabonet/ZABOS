import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AuthProvider } from "./auth-context";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lume Studio — vídeos curtos, prontos para publicar",
  description: "Transforma uma ideia num vídeo vertical para as tuas redes.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="pt-PT">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
