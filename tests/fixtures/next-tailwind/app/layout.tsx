import './globals.css';

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ja"><body data-retro-theme="windows-7">{children}</body></html>;
}
