import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Thread } from "./components/Thread";
import "./index.css";
import { PrefsProvider } from "./lib/prefs";
import { ProfileProvider } from "./lib/profile";
import "./lib/theme";
import { SourcesPage } from "./pages/SourcesPage";

function ErrorPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <p className="text-slate-600 dark:text-slate-400">Please reload the page and try again.</p>
      <button
        onClick={() => location.assign("/")}
        className="rounded-lg bg-brand-500 px-4 py-2 text-white hover:bg-brand-600"
      >
        Back to chat
      </button>
    </div>
  );
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <Thread /> },
      { path: "sources", element: <SourcesPage /> },
      // The Settings page was removed; old links go back to the chat.
      { path: "settings", element: <Navigate to="/" replace /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PrefsProvider>
      <ProfileProvider>
        <RouterProvider router={router} />
      </ProfileProvider>
    </PrefsProvider>
  </StrictMode>,
);
