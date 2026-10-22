import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { BlueNavItem } from "../components/blue/types";
import { BBM_PATH } from "../controllers/BbmController";
import { useCurrentUser } from "../controllers/LoginController";
import AppLayout from "../layouts/AppLayout";
import BbmPage from "../pages/BbmPage";
import BbmReportPage from "../pages/BbmReportPage";
import HomePage from "../pages/HomePage";
import LoginPage from "../pages/LoginPage";
import NotFoundPage from "../pages/NotFoundPage";
import type { User } from "../types/user";
import { language, t } from "./i18n";
import { useLocation } from "./router";

// App shell. Until the Blibli gateway handles sign-in, the user picks who they are on the login page.
// After that, the URL decides the page:
//   /             home
//   /bbm          BBM reports (fuel)
//   /bbm/<code>   one BBM report

function navItems(): BlueNavItem[] {
  return [
    { key: "home", label: t("nav.home"), href: "/" },
    { key: "bbm", label: t("nav.bbm"), href: BBM_PATH },
  ];
}

type Route =
  | { page: "home"; nav: "home"; title: string }
  | { page: "bbm"; nav: "bbm"; title: string }
  | { page: "bbm-report"; nav: "bbm"; title: string; code: string }
  | { page: "not-found"; nav?: undefined; title: string };

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment; // malformed %-escape: use it as typed
  }
}

function routeOf(path: string): Route {
  if (path === "/") return { page: "home", nav: "home", title: t("title.home") };
  if (path === BBM_PATH) return { page: "bbm", nav: "bbm", title: t("title.bbm") };
  const report = /^\/bbm\/([^/]+)$/.exec(path);
  if (report) {
    const code = decodeSegment(report[1]);
    return { page: "bbm-report", nav: "bbm", title: t("title.report", { code }), code };
  }
  return { page: "not-found", title: t("title.notFound") };
}

function Page({ route, user }: { route: Route; user: User }) {
  switch (route.page) {
    case "home":
      return <HomePage user={user} />;
    case "bbm":
      return <BbmPage />;
    case "bbm-report":
      // key: a new report starts fresh (its revision tab, its comment draft).
      return <BbmReportPage key={route.code} code={route.code} user={user} />;
    case "not-found":
      return <NotFoundPage />;
  }
}

export default function App() {
  useTranslation(); // render everything again when the language changes
  const lang = language();
  const { user, signIn, signOut } = useCurrentUser();
  const { path } = useLocation();
  const route = routeOf(path);
  const title = user ? route.title : t("title.signIn");

  useEffect(() => {
    document.title = `${title} · ${t("app.name")}`;
  }, [title]);

  if (!user) return <LoginPage onSignIn={signIn} />;

  return (
    <AppLayout
      user={user}
      onSwitchUser={signOut}
      navItems={navItems()}
      activeNavKey={route.nav}
      wide={route.page === "bbm-report"}
    >
      {/* key: a new language starts the page again, so the texts it keeps (memoised, or a message in its state) are
          made in that language too. */}
      <Page key={lang} route={route} user={user} />
    </AppLayout>
  );
}
