import { useEffect } from "react";
import { NegotiatePage } from "./negotiate/NegotiatePage";
import { ReplayPage } from "./replay/ReplayPage";
import { ReplayFrame } from "./replay/Frame";
import { AdminPage } from "./pages/AdminPage";
import { ConsentPage, LoginPage, RegisterPage } from "./pages/AuthPages";
import { navigate, usePath, withBase } from "./router";
import { Toasts } from "./ui/Toasts";
import { useTheme } from "./negotiate/Header";

function Route({ path }: { path: string }) {
  const p = path.replace(/\/+$/, "") || "/";
  if (p === "/") return null;
  if (p === "/login") return <LoginPage />;
  if (p === "/register") return <RegisterPage />;
  if (p === "/consent") return <ConsentPage />;
  if (p === "/admin") return <AdminPage />;
  if (p === "/replay") return <ReplayPage />;
  if (p === "/replay/frame") return <ReplayFrame />;
  if (p === "/play" || p === "/hanplay" || p === "/guest") return <NegotiatePage key="guest" mode="guest" />;
  if (p === "/app") return <NegotiatePage key="main" mode="main" />;
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-2 text-center">
      <div className="text-lg font-semibold">There is nothing at {p}</div>
      <a className="text-you underline" href={withBase("/app")}>Go to the negotiation</a>
    </div>
  );
}

export default function App() {
  const path = usePath();
  useTheme();
  useEffect(() => {
    if (path === "/") navigate("/app" + location.search, true);
  }, [path]);
  return (
    <>
      <Route path={path} />
      <Toasts />
    </>
  );
}
