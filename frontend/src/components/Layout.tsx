import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { BookOpen, Menu, MessageSquare, Settings, SquarePen, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { createAdvisorAdapter } from "../lib/adapter";
import { ChatContext } from "../lib/chat";
import { clearChat, loadChat, saveChat } from "../lib/history";
import { useProfile } from "../lib/profile";
import { Logo, LogoIcon } from "./Logo";
import { useTheme, type Theme } from "../lib/theme";
import { ProfilePanel } from "./ProfilePanel";

export type LayoutContext = { theme: Theme; setTheme: (t: Theme) => void };

const NAV = [
  { to: "/", label: "Chat", icon: MessageSquare },
  { to: "/sources", label: "Sources", icon: BookOpen },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Layout() {
  const { profileRef } = useProfile();
  const [theme, setTheme] = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  // Runtime lives here so the conversation survives switching between pages; it is also
  // saved in this browser so it survives a reload.
  const adapter = useMemo(() => createAdvisorAdapter(() => profileRef.current), [profileRef]);
  const [initialMessages] = useState(loadChat);
  const runtime = useLocalRuntime(adapter, { initialMessages });

  useEffect(
    () => runtime.thread.subscribe(() => saveChat(runtime.thread.getState().messages)),
    [runtime],
  );

  const chat = useMemo(
    () => ({
      runtime,
      newChat: () => {
        runtime.thread.reset();
        clearChat();
      },
    }),
    [runtime],
  );

  const sidebar = (
    <div className="flex h-full flex-col gap-6 p-4">
      <Logo className="mx-auto h-24 w-auto" />
      <button
        onClick={() => {
          chat.newChat();
          setMenuOpen(false);
          navigate("/");
        }}
        className="flex items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium hover:border-coral-300 hover:bg-coral-50 dark:border-slate-700 dark:hover:bg-slate-800"
      >
        <SquarePen size={16} /> New chat
      </button>
      <nav className="-mt-3 flex flex-col gap-1">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end
            onClick={() => setMenuOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                isActive
                  ? "bg-brand-50 font-medium text-brand-700 dark:bg-slate-800 dark:text-brand-100"
                  : "hover:bg-slate-100 dark:hover:bg-slate-800"
              }`
            }
          >
            <Icon size={16} /> {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-slate-200 pt-4 dark:border-slate-800">
        <ProfilePanel />
      </div>
    </div>
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
     <ChatContext.Provider value={chat}>
      <div className="flex h-full">
        <aside className="hidden w-72 shrink-0 overflow-y-auto border-r border-slate-200 bg-slate-50 md:block dark:border-slate-800 dark:bg-slate-900/50">
          {sidebar}
        </aside>

        {menuOpen && (
          <div className="fixed inset-0 z-20 md:hidden">
            <div className="absolute inset-0 bg-black/40" onClick={() => setMenuOpen(false)} />
            <aside className="absolute inset-y-0 left-0 w-72 overflow-y-auto bg-white dark:bg-slate-900">
              <button
                aria-label="Close menu"
                onClick={() => setMenuOpen(false)}
                className="absolute top-3 right-3 p-1"
              >
                <X size={18} />
              </button>
              {sidebar}
            </aside>
          </div>
        )}

        <main className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-2 md:hidden dark:border-slate-800">
            <button aria-label="Open menu" onClick={() => setMenuOpen(true)} className="p-1">
              <Menu size={20} />
            </button>
            <LogoIcon className="h-8 w-auto" />
            <span className="font-display text-lg font-extrabold text-brand-500 dark:text-brand-100">
              Kopi <span className="text-coral-500">&amp;</span> Keys
            </span>
          </header>
          <div className="min-h-0 flex-1">
            <Outlet context={{ theme, setTheme } satisfies LayoutContext} />
          </div>
        </main>
      </div>
     </ChatContext.Provider>
    </AssistantRuntimeProvider>
  );
}
